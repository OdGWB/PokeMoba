"""Client-side prediction del PROPRIO personaggio, con riconciliazione.

PERCHÉ
Con 80 ms di ping, se il client aspettasse l'host il proprio Pokémon
partirebbe 80 ms dopo il click: si sente "gommoso". Invece il client MUOVE
SUBITO il personaggio da solo (predizione) e usa gli snapshot dell'host solo
per CORREGGERSI quando la sua previsione era sbagliata (riconciliazione).
L'host resta l'unica autorità: la predizione cambia solo cosa si DISEGNA.

COME FUNZIONA
- Il client avanza la propria simulazione a tick fissi (1/30 s, come l'host)
  e per ogni tick salva lo stato predetto in `hist[tick]` (ring buffer).
- Ogni comando dato (click destro, ...) va in `inputs` (ring buffer dei
  comandi NON ancora confermati) con il tick locale in cui è stato dato e il
  PERCORSO già calcolato. L'A* si fa UNA volta sola, qui, al momento del click.
- Ogni snapshot dice: "ho applicato il tuo comando N al mio tick ack_tick, e
  ora (tick T) sei in P". Il comando N era stato dato al nostro tick locale
  t_N, quindi lo stato dell'host al tick T corrisponde al nostro tick locale
            L = t_N + (T - ack_tick)
  (offset fra i due orologi di tick, ricalcolato a ogni conferma).
- Si confronta hist[L] con P. Se coincidono (caso normale) non si fa nulla.
  Se no si RIAVVOLGE: si riparte da P al tick L e si RIGIOCANO i tick da L+1
  ad adesso, riapplicando i comandi non confermati al loro tick. Nel replay
  NON si rilancia mai l'A*: si riusa il percorso salvato nel comando e si
  rigioca solo l'avanzamento lungo di esso (a 20 snapshot/s un A* per tick
  vorrebbe dire centinaia di pathfinding al secondo in Python puro).
- La differenza fra la vecchia previsione e la nuova non si applica di colpo
  (scatto visibile) ma si smaltisce in ~100 ms (`smooth`); se è enorme
  (scatto, spinta, teletrasporto) si salta subito alla posizione giusta.
- Quando l'host dice che il personaggio NON può muoversi (stordito, radicato,
  morto, in richiamo) o il comando non è prevedibile (attacca un bersaglio,
  lancia una mossa) si smette di predire e si segue l'host ("follow").

Il modulo non conosce il gioco: il movimento vero lo fa `model`, che deve
avere plan(pos, kind, target) e advance(pos, path, speed, dt).
"""
from __future__ import annotations

import collections
import math

from .protocol import seq_diff

HISTORY = 128           # tick di storia (~4 s a 30 Hz)
MATCH_EPS = 0.04        # tile: sotto questo errore la previsione è giusta
SNAP_DIST = 1.5         # tile: errore oltre il quale si salta senza smussare
SMOOTH_TIME = 0.10      # s: costante di smaltimento della correzione


class _Input:
    __slots__ = ("seq", "tick", "path")

    def __init__(self, seq, tick, path):
        self.seq = seq
        self.tick = tick
        self.path = path      # tuple di waypoint, () = fermati, None = non prevedibile


class Predictor:
    def __init__(self, model, tick_dt: float):
        self.model = model
        self.dt = tick_dt
        self.tick = 0                   # prossimo tick locale da simulare
        self.pos = None                 # (x, y) predetta
        self.path = ()
        self.follow = True              # True = niente predizione, si segue l'host
        self.can_move = True
        self.speed = 0.0
        self.facing = 0
        self.moving = False
        self.inputs: collections.deque = collections.deque()
        self.hist: dict = {}            # tick -> (pos, path, follow)
        self.tick_offset = None         # L - T (tick locale - tick host)
        self.smooth = (0.0, 0.0)
        # statistiche per l'HUD di debug
        self.last_error = 0.0
        self.replays = 0
        self.snaps = 0

    # --- comandi del giocatore -------------------------------------------------
    def command(self, seq: int, kind: int, target=None) -> None:
        path = self.model.plan(self.pos, kind, target) if self.pos is not None else None
        e = _Input(seq, self.tick, path)
        self.inputs.append(e)
        while len(self.inputs) > HISTORY:
            self.inputs.popleft()
        self.path, self.follow = self._effect(e, self.path)

    @staticmethod
    def _effect(e, path):
        if e.path is None:
            return (), True
        return e.path, False

    # --- avanzamento locale (un tick) ------------------------------------------------
    def step(self) -> None:
        if self.pos is None:
            return
        self.moving = False
        if not self.follow and self.can_move and self.path:
            self.pos, self.path, self.facing = self.model.advance(
                self.pos, self.path, self.speed, self.dt)
            self.moving = True
        self.hist[self.tick] = (self.pos, self.path, self.follow)
        self.hist.pop(self.tick - HISTORY, None)
        self.tick += 1

    # --- riconciliazione con lo snapshot dell'host -------------------------------------
    def reconcile(self, server_pos, speed, can_move, server_moving, ack_seq, ack_tick,
                  server_tick, server_facing=0) -> None:
        self.speed = speed
        self.can_move = can_move
        if self.pos is None:
            self.pos = server_pos
            self.facing = server_facing
            return

        # 1) Via dal ring buffer i comandi che l'host ha confermato.
        acked = None
        if ack_seq is not None:
            while self.inputs and seq_diff(self.inputs[0].seq, ack_seq) <= 0:
                e = self.inputs.popleft()
                if e.seq == ack_seq:
                    acked = e
            if acked is not None:
                self.tick_offset = acked.tick - ack_tick

        # 2) Casi in cui non si predice: si segue l'host.
        if not can_move:
            self._correct_to(server_pos)     # il percorso resta: riprende a CC finito
            self.facing = server_facing
            return
        if not self.inputs:
            if self.follow or self.tick_offset is None:
                self._correct_to(server_pos)
                self.facing = server_facing
                return
            if not server_moving:
                # Arrivato (o l'host ha interrotto il percorso): fermo dove dice lui.
                self.path = ()
                self._correct_to(server_pos)
                return
        if self.tick_offset is None:
            self._correct_to(server_pos)
            return

        # 3) Lo stato dell'host al tick T corrisponde al nostro tick locale L.
        L = server_tick + self.tick_offset
        past = self.hist.get(L)
        if past is None or L >= self.tick:
            self._correct_to(server_pos)
            return
        err = math.hypot(past[0][0] - server_pos[0], past[0][1] - server_pos[1])
        self.last_error = err
        if err <= MATCH_EPS:
            return                      # la previsione era giusta: niente da fare

        # 4) RIAVVOLGI E RIGIOCA. Si riparte dalla posizione vera al tick L con il
        #    percorso che avevamo a L (che include già i comandi dati fino a L,
        #    anche quelli che l'host non ha ancora ricevuto), poi si rigiocano i
        #    tick successivi riapplicando i comandi non confermati al loro tick.
        #    Il percorso di ogni comando è quello salvato al click: niente A*.
        self.replays += 1
        old = self.pos
        pos, path, follow = server_pos, past[1], past[2]
        self.hist[L] = (pos, path, follow)
        pending = [e for e in self.inputs if e.tick > L]
        k = 0
        facing = self.facing
        for t in range(L + 1, self.tick):
            while k < len(pending) and pending[k].tick <= t:
                path, follow = self._effect(pending[k], path)
                k += 1
            if not follow and path:
                pos, path, facing = self.model.advance(pos, path, speed, self.dt)
            self.hist[t] = (pos, path, follow)
        while k < len(pending):          # comandi dati dopo l'ultimo tick simulato
            path, follow = self._effect(pending[k], path)
            k += 1
        self.pos, self.path, self.follow, self.facing = pos, path, follow, facing
        self._absorb(old)

    def _correct_to(self, server_pos) -> None:
        old = self.pos
        self.pos = server_pos
        self._absorb(old)

    def _absorb(self, old) -> None:
        """Trasforma il salto old -> pos in uno scostamento visivo che si smaltisce."""
        dx, dy = old[0] - self.pos[0], old[1] - self.pos[1]
        if math.hypot(dx, dy) > SNAP_DIST:
            self.smooth = (0.0, 0.0)
            self.snaps += 1
        else:
            self.smooth = (self.smooth[0] + dx, self.smooth[1] + dy)

    # --- disegno -------------------------------------------------------------------------
    def display(self, dt: float):
        """Posizione da disegnare: predetta + correzione residua che si smaltisce."""
        if self.pos is None:
            return None
        k = math.exp(-dt / SMOOTH_TIME)
        self.smooth = (self.smooth[0] * k, self.smooth[1] * k)
        return self.pos[0] + self.smooth[0], self.pos[1] + self.smooth[1]
