"""Sessione CLIENT: manda input, riceve e ricostruisce gli snapshot.

Non simula nulla di autoritativo. Interfaccia per il gioco:
- poll(now)                     da chiamare a ogni frame (riceve, invia, ping)
- send_move / send_attack / ... comandi (stessi nomi del vecchio client LAN)
- on_frame(frame, now)          callback a ogni snapshot ricostruito
- on_command(seq, kind, fields) callback a ogni comando (per la predizione)
- phase / lost_reason / end_info stato della connessione per la UI

INPUT A 60 Hz CON RIDONDANZA
Il canale state non ritrasmette. Per non perdere click, ogni pacchetto di
input porta TUTTI i comandi non ancora confermati dall'host (fino a 16): se
un pacchetto si perde, il successivo (16 ms dopo) li ripete. L'host scarta i
numeri di sequenza già applicati. Quando non c'è niente di nuovo si manda un
keepalive a 10 Hz (serve anche a confermare gli snapshot).
"""
from __future__ import annotations

import collections
import time

import config

from . import protocol as P
from .stats import ClockSync, LossMeter, Rate
from .transport import CLOSED, CONNECTED, FAILED

HOST_TIMEOUT = 3.0          # s senza nulla dall'host = host caduto
INPUT_DT = 1.0 / 60
KEEPALIVE_DT = 0.1
PING_DT = 1.0
FRAME_HISTORY = 64          # snapshot tenuti come possibili basi del delta

CONNECTING, LOBBY, DRAFT, LOADING, MATCH, ENDED, LOST = (
    "connecting", "lobby", "draft", "loading", "match", "ended", "lost")


class ClientSession:
    def __init__(self, transport, name="Giocatore", avatar=0):
        self.transport = transport
        self.name = name
        self.avatar = avatar            # n. di Pokédex dell'immagine profilo (0 = nessuna)
        self.phase = CONNECTING
        self.slot = None
        self.max_slots = 0
        self.lobby = None
        self.draft = None               # ultimo stato del draft (P.dec_draft)
        self._draft_rx = 0.0            # quando è arrivato (per il conto alla rovescia)
        self.start_info = None
        self.end_info = None
        self.lost_reason = ""
        self.events = collections.deque(maxlen=8)    # (tempo, testo) per la UI
        self.chat = collections.deque(maxlen=8)      # (nome, testo)
        self.frames: collections.OrderedDict = collections.OrderedDict()
        self.latest = None
        self.fx_queue: list = []
        self.visual: dict = {}           # ultimo stato visivo (net/visual.py)
        self.on_frame = None
        self.on_command = None
        self.unacked: collections.deque = collections.deque()
        self._seq = 0
        self._act_seq = 0
        self._ack_dirty = False
        self._last_input = -1e9
        self._last_ping = -1e9
        self._hello_sent = False
        self._connected_once = False
        self._t0 = time.monotonic()
        # misure per l'HUD
        self.clock = ClockSync()
        self.loss = LossMeter()
        self.snap_bytes = Rate()
        self.input_bytes = Rate()
        self.keyframes = 0
        self.missing_base = 0
        self.bad_packets = 0

    @property
    def client_id(self):                 # compatibilità con NetMatchScene
        return self.slot

    # --- ciclo -------------------------------------------------------------------
    def poll(self, now=None) -> None:
        now = time.monotonic() if now is None else now
        tr = self.transport
        if tr.state == CONNECTED:
            self._connected_once = True
            if not self._hello_sent:
                tr.send_reliable(P.enc_hello(self.name, self.avatar))
                self._hello_sent = True
        for ch, data in tr.recv():
            try:
                self._handle(ch, data, now)
            except (P.ProtocolError, ValueError, KeyError, IndexError):
                self.bad_packets += 1
        if self.phase in (ENDED, LOST):
            return
        if tr.state == FAILED:
            self._lose(tr.error or "Connessione fallita.")
        elif tr.state == CLOSED and self._connected_once:
            self._lose("L'host ha chiuso la connessione.")
        elif self._connected_once and now - tr.last_rx > HOST_TIMEOUT:
            self._lose("L'host non risponde più: la partita è finita (connessione persa).")
        if self.phase in (ENDED, LOST) or tr.state != CONNECTED:
            return
        if now - self._last_ping >= PING_DT:
            self._last_ping = now
            tr.send_reliable(P.enc_ping(self._ms(now)))
        if self.phase == MATCH:
            due = INPUT_DT if (self.unacked or self._ack_dirty) else KEEPALIVE_DT
            if now - self._last_input >= due:
                self._send_input(now)

    def _ms(self, now) -> int:
        return int((now - self._t0) * 1000) & 0xFFFFFFFF

    def _lose(self, reason) -> None:
        self.phase = LOST
        self.lost_reason = reason

    def _send_input(self, now) -> None:
        ack = self.latest.seq if self.latest is not None else None
        data = P.enc_input(ack, list(self.unacked))
        self.transport.send_state(data)
        self.input_bytes.add(len(data))
        self._last_input = now
        self._ack_dirty = False

    # --- ricezione ---------------------------------------------------------------------
    def _handle(self, ch, data, now) -> None:
        t = P.msg_type(data)
        if t == P.S_SNAP:
            self._on_snapshot(data, now)
        elif t == P.S_FX:
            if self.phase == MATCH:
                self.fx_queue.extend(P.dec_fx(data)[1])
        elif ch != P.CH_RELIABLE:
            self.bad_packets += 1          # sul canale state arrivano solo SNAP/FX
        elif t == P.R_WELCOME:
            w = P.dec_welcome(data)
            self.slot, self.max_slots = w["slot"], w["max_slots"]
            if self.phase == CONNECTING:
                self.phase = LOBBY
        elif t == P.R_LOBBY:
            self.lobby = P.dec_lobby(data)
        elif t == P.R_DRAFT:
            self.draft = P.dec_draft(data)
            self._draft_rx = now
            if self.phase in (LOBBY, DRAFT):
                self.phase = DRAFT
        elif t == P.R_START:
            info = P.dec_start(data)
            for p in info["players"]:
                p["client_id"] = p["slot"]
            self.start_info = info
            self.frames.clear()
            self.latest = None
            self.unacked.clear()
            self.phase = LOADING
        elif t == P.R_VIS:
            if self.phase == MATCH:
                self.visual = P.dec_vis(data)
        elif t == P.R_EVENT:
            e = P.dec_event(data)
            txt = {P.EV_DISCONNECT: "si è disconnesso", P.EV_RECONNECT: "è rientrato",
                   P.EV_JOIN: "è entrato"}.get(e["kind"], "?")
            self.events.append((now, f"{e['name']} {txt}"))
        elif t == P.R_CHAT:
            c = P.dec_chat(data)
            self.chat.append((self._name_of(c["slot"]), c["text"]))
        elif t == P.R_END:
            self.end_info = P.dec_end(data)
            self.phase = ENDED
        elif t == P.R_PONG:
            p = P.dec_pong(data)
            sent = self._t0 + p["t_client"] / 1000.0
            self.clock.add(sent, p["host_time"], now)
        elif t == P.R_BYE:
            self._lose("L'host ha chiuso la partita.")
        else:
            self.bad_packets += 1

    def _name_of(self, slot) -> str:
        for p in (self.lobby or {}).get("players", []):
            if p["slot"] == slot:
                return p["name"]
        return f"Slot {slot}"

    def _on_snapshot(self, data, now) -> None:
        seq, _base, key = P.peek_snapshot(data)
        if self.latest is not None and not P.seq_newer(seq, self.latest.seq):
            return                               # vecchio o duplicato
        try:
            frame = P.dec_snapshot(data, self.frames.get)
        except P.MissingBase:
            self.missing_base += 1               # base persa: l'host manderà un keyframe
            return
        self.frames[seq] = frame
        while len(self.frames) > FRAME_HISTORY:
            self.frames.popitem(last=False)
        self.latest = frame
        self._ack_dirty = True
        self.loss.on_seq(seq)
        self.snap_bytes.add(len(data))
        if key:
            self.keyframes += 1
        self.clock.seed(frame.tick * config.TICK_DT, now)
        if frame.me is not None and frame.me[3] & P.ME_HAS_ACK:
            self.on_ack(frame.me[4])
        if self.on_frame is not None:
            self.on_frame(frame, now)

    # --- invio: lobby -------------------------------------------------------------------------
    def send_choice(self, team, pokemon, ready) -> None:
        self.transport.send_reliable(P.enc_choice(team, pokemon, ready))

    # --- draft ----------------------------------------------------------------------------------
    def send_pick(self, pokemon, lock=False, color=0) -> None:
        """Anteprima (lock=False, la vedono tutti) o scelta definitiva del Pokémon
        (con il colore dei fiori di Flabébé, indice 0-4)."""
        self.transport.send_reliable(P.enc_pick(pokemon, lock, color))

    def draft_my_turn(self) -> bool:
        d = self.draft
        return bool(d and d["turn"] is not None and d["entries"][d["turn"]]["slot"] == self.slot)

    def draft_taken(self) -> set:
        return {e["poke"] for e in (self.draft or {}).get("entries", []) if e["poke"] is not None}

    def draft_time_left(self, now=None) -> float:
        if not self.draft:
            return 0.0
        now = time.monotonic() if now is None else now
        return max(0.0, self.draft["time_left"] - (now - self._draft_rx))

    def send_loaded(self) -> None:
        self.transport.send_reliable(P.enc_loaded())
        if self.phase == LOADING:
            self.phase = MATCH

    def send_chat(self, text) -> None:
        if text.strip():
            self.transport.send_reliable(P.enc_chat(0, text))

    # --- invio: comandi (canale state, ridondanti) ------------------------------------------------
    def _cmd(self, kind, **f) -> None:
        if self.phase != MATCH:
            return
        self._seq = P.seq_next(self._seq)
        c = {"seq": self._seq, "kind": kind, **f}
        self.unacked.append(c)
        while len(self.unacked) > 64:
            self.unacked.popleft()
        if self.on_command is not None:
            self.on_command(self._seq, kind, f)
        self._last_input = -1e9                  # parte subito, senza aspettare il tick input

    def on_ack(self, ack_seq) -> None:
        """Toglie i comandi confermati dall'host (chiamato dallo snapshot)."""
        while self.unacked and P.seq_diff(self.unacked[0]["seq"], ack_seq) <= 0:
            self.unacked.popleft()

    def send_move(self, x, y): self._cmd(P.CMD_MOVE, x=x, y=y)
    def send_attack(self, target_id): self._cmd(P.CMD_ATTACK, target_id=target_id)
    def send_attackmove(self, x, y, champs_only=False):
        self._cmd(P.CMD_ATTACKMOVE_CHAMP if champs_only else P.CMD_ATTACKMOVE, x=x, y=y)
    def send_cast(self, slot, x, y, hold=0.0):
        if hold > 0.0:   # pressione del tasto (Tiro Lungo)
            self._cmd(P.CMD_CAST, slot=slot, x=x, y=y, hold=hold)
        else:
            self._cmd(P.CMD_CAST, slot=slot, x=x, y=y)
    def send_stop(self): self._cmd(P.CMD_STOP)
    def send_recall(self): self._cmd(P.CMD_RECALL)

    # --- invio: azioni critiche (canale reliable) ----------------------------------------------
    def _act(self, kind, **f) -> None:
        self._act_seq = P.seq_next(self._act_seq)
        self.transport.send_reliable(P.enc_action(self._act_seq, kind, **f))

    def send_rank(self, slot): self._act(P.ACT_RANK, slot=slot)
    def send_choose(self, slot, index): self._act(P.ACT_CHOOSE, slot=slot, index=index)
    def send_buy(self, item_id): self._act(P.ACT_BUY, item_id=item_id)
    def send_sell(self, slot): self._act(P.ACT_SELL, slot=slot)
    def send_use_item(self, slot): self._act(P.ACT_USE, slot=slot)

    def close(self) -> None:
        try:
            self.transport.send_reliable(P.enc_bye())
        finally:
            self.transport.close()
