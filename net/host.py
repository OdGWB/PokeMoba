"""Sessione HOST: topologia a stella, l'host esegue TUTTA la simulazione.

    amico 1 ──┐
    amico 2 ──┼── HOST (simulazione autoritativa a 30 tick/s)
    amico N ──┘      + il giocatore dell'host, collegato in memoria (loopback)

Una RTCPeerConnection SEPARATA per ogni slot; i client parlano solo con
l'host, mai fra loro. I client mandano solo intenzioni (input); l'host le
valida (net/validation.py), le applica e rimanda a ciascuno uno snapshot
delta a 20 Hz, filtrato per visione della sua squadra.

THREAD
La simulazione gira in un thread proprio (HostSession._run), indipendente dal
rendering dell'host. La UI della lobby (thread di gioco) non tocca mai gli
slot direttamente: chiama open_slot/submit_answer/request_start, che mettono
un comando in una queue.Queue letta dal thread dell'host, e legge `view`, una
fotografia degli slot ripubblicata a ogni giro (sostituzione atomica di una
lista). Il WebRTC vive nel suo thread asyncio (net/rtc.py).

ROBUSTEZZA
- Client caduto in partita: il suo Pokémon resta ESATTAMENTE dov'è, fermo,
  bersagliabile e uccidibile; smette solo di ricevere comandi (staccare il
  cavo non salva da un gank). L'host può riaprire lo slot con una nuova
  offerta e il giocatore rientra con lo stesso Pokémon.
- Host chiuso: manda R_END(END_HOST_QUIT) a tutti; se invece muore di colpo
  i client se ne accorgono da soli in 3 s (net/client.py HOST_TIMEOUT).
"""
from __future__ import annotations

import collections
import json
import queue
import threading
import time
from pathlib import Path

import config

from . import protocol as P
from . import validation as V
from .client import ClientSession
from .draft import DONE_TIME, Draft
from .signaling import ANSWER, OFFER, ManualSignaling, SignalingError, SignalMessage, new_session_id
from .transport import CLOSED, CONNECTED, FAILED, LoopbackTransport

ROOT = Path(__file__).resolve().parent.parent
MAX_SLOTS = 10                 # 5v5
CLIENT_TIMEOUT = 3.0           # s senza nulla dal client = caduto
CONNECT_TIMEOUT = 45.0         # s per completare ICE dopo la risposta
LOAD_TIMEOUT = 90.0            # s massimo di attesa del caricamento mappa
SNAP_DT = 1.0 / config.SNAPSHOT_RATE
SNAP_HISTORY = 64              # snapshot inviati tenuti come basi (~3.2 s)
KEY_RESEND = 1.0               # s: keyframe non confermato -> se ne manda un altro
LANES = ["top", "mid", "bot"]

# Stato di uno slot, mostrato in lobby.
S_EMPTY = "new"
S_GATHERING = "gathering"
S_WAITING = "waiting"
S_CONNECTING = "connecting"
S_CONNECTED = "connected"
S_FAILED = "failed"
S_DISCONNECTED = "disconnected"
S_LOCAL = "host"


def map_team_size(map_index: int) -> int:
    path = ROOT / config.MAPS[map_index][1]
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("team_size", 3))
    except (OSError, ValueError):
        return 3


class Slot:
    def __init__(self, index):
        self.index = index
        self.reset()

    def reset(self):
        self.transport = None
        self.status = S_EMPTY
        self.error = ""
        self.code = ""
        self.session = 0
        self.offer_future = None
        self.answer_future = None
        self.connect_deadline = 0.0
        self.name = ""
        self.avatar = 0               # immagine profilo (n. di Pokédex, 0 = nessuna)
        self.team = 0
        self.pokemon = 0
        self.ready = False
        self.joined = False           # HELLO ricevuto
        self.loaded = False           # mappa caricata dal client
        self.entity_id = 0
        self.guard = V.ClientGuard()
        self.reset_net()

    def reset_net(self):
        """Stato di rete di una sessione client (si azzera a ogni (ri)connessione)."""
        self.history: collections.OrderedDict = collections.OrderedDict()
        self.snap_seq = 0
        self.ack = None
        self.last_key = None          # (seq, istante) dell'ultimo keyframe
        self.last_cmd_seq = None
        self.last_cmd_tick = 0
        self.snap_bytes = 0
        self.last_vis = None          # ultimo stato visivo mandato (si rimanda se cambia)


class HostSession:
    def __init__(self, map_index=0, host_name="Host", host_plays=True, host_avatar=0):
        self.map_index = map_index
        self.team_size = map_team_size(map_index)
        self.slots = [Slot(i) for i in range(MAX_SLOTS)]
        self.phase = "lobby"          # lobby / draft / loading / match / ended / closed
        self.message = ""
        self.view: list = []
        self.local = None
        self.match = self.world = self.sim = None
        self.disconnected: set = set()
        self.rejected_total = 0
        self._cmds: queue.Queue = queue.Queue()
        self._fx: list = []
        self._running = False
        self._thread = None
        self._defs = {}
        self._next_tick = 0.0
        self._next_snap = 0.0
        self._last_step_wall = 0.0
        self._load_deadline = 0.0
        self._ended_sent = False
        self.draft = None             # net/draft.Draft durante la fase "draft"
        self._draft_done_at = None
        from engine.items import ItemCatalog
        self._item_ids = set(ItemCatalog.load(str(ROOT / "data/items.json")).items)
        if host_plays:
            a, b = LoopbackTransport.pair()
            s0 = self.slots[0]
            s0.transport, s0.status = a, S_LOCAL
            self.local = ClientSession(b, V.clean_text(host_name, 24) or "Host", host_avatar)
        self._publish()

    # ==================================================================================
    # API per la UI (thread di gioco). Nessuna tocca gli slot: solo code e `view`.
    # ==================================================================================
    @property
    def max_players(self) -> int:
        return min(MAX_SLOTS, 2 * self.team_size)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, name="host-sim", daemon=True)
        self._thread.start()

    def open_slot(self, i):
        """Crea (o rigenera) l'offerta per lo slot i."""
        self._cmds.put(("open", i))

    def attach_transport(self, i, transport):
        """Collega allo slot i un trasporto GIÀ connesso (test, o un futuro
        signaling server che fa la negoziazione per conto suo)."""
        self._cmds.put(("attach", i, transport))

    def close_slot(self, i):
        self._cmds.put(("close", i))

    def submit_answer(self, i, text) -> str | None:
        """Risposta incollata dall'host per lo slot i. Ritorna un errore leggibile o None."""
        try:
            msg = ManualSignaling.decode(text)
        except SignalingError as e:
            return str(e)
        if msg.kind != ANSWER:
            return "Questo è un codice OFFERTA: serve la RISPOSTA che ti ha mandato l'amico."
        if msg.slot != i:
            return f"Questa risposta è per lo slot {msg.slot}, non per lo slot {i}."
        v = self.view[i] if i < len(self.view) else None
        if v is None or v["status"] != S_WAITING or v["session"] != msg.session:
            return "Risposta vecchia o di un'altra offerta: rigenera il codice e rimandalo."
        self._cmds.put(("answer", i, msg))
        return None

    def set_map(self, map_index):
        self._cmds.put(("map", map_index))

    def request_start(self):
        self._cmds.put(("start",))

    def shutdown(self, message="L'host ha chiuso la partita."):
        """Chiusura PULITA: avvisa tutti, poi chiude le connessioni."""
        self._cmds.put(("shutdown", message))
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._running = False

    # ==================================================================================
    # Thread dell'host
    # ==================================================================================
    def _run(self):
        try:
            while self._running:
                now = time.monotonic()
                self._process_cmds(now)
                if not self._running:
                    break
                self._poll_futures()
                for s in self.slots:
                    if s.transport is None:
                        continue
                    for ch, data in s.transport.recv():
                        try:
                            self._on_message(s, ch, data, now)
                        except (P.ProtocolError, ValueError, KeyError, IndexError):
                            self._strike(s)
                self._check_links(now)
                self._advance(now)
                self._publish()
                wake = self._next_tick if self.phase == "match" else now + 0.01
                time.sleep(min(0.01, max(0.001, wake - time.monotonic())))
        finally:
            self._close_all()

    def _advance(self, now):
        if self.phase == "draft":
            self._draft_step(now)
        if self.phase == "loading":
            if (all(s.loaded for s in self._players()) or now > self._load_deadline):
                self.phase = "match"
                self._next_tick = self._next_snap = now
                self._last_step_wall = now
        if self.phase != "match":
            return
        steps = 0
        while now >= self._next_tick and steps < 8:
            self.sim.step()
            self._last_step_wall = now
            if self.match.fx_events:
                self._fx.extend(self.match.fx_events)
                self.match.fx_events.clear()
            self._next_tick += config.TICK_DT
            steps += 1
        if steps == 8:                           # rallentamento: niente spirale di recupero
            self._next_tick = now + config.TICK_DT
        if now >= self._next_snap:
            self._send_snapshots(now)
            self._next_snap = max(self._next_snap + SNAP_DT, now)
        if self.match.winner is not None and not self._ended_sent:
            self._ended_sent = True
            self.phase = "ended"
            self._send_snapshots(now)
            self._broadcast(P.enc_end(self.match.winner, P.END_VICTORY))

    def host_clock(self, now=None) -> float:
        """Orologio della partita (s) continuo: tick * dt + frazione del tick in corso."""
        if self.sim is None:
            return 0.0
        now = time.monotonic() if now is None else now
        return (self.sim.tick_count * config.TICK_DT
                + min(config.TICK_DT, max(0.0, now - self._last_step_wall)))

    def _players(self):
        """Slot con un giocatore presente (HELLO ricevuto e connesso)."""
        return [s for s in self.slots[:self.max_players]
                if s.joined and s.status in (S_CONNECTED, S_LOCAL)]

    def _publish(self):
        view = []
        for s in self.slots:
            view.append({"index": s.index, "status": s.status, "error": s.error,
                         "code": s.code, "session": s.session, "name": s.name,
                         "team": s.team, "pokemon": s.pokemon, "ready": s.ready,
                         "joined": s.joined, "entity_id": s.entity_id,
                         "rejected": s.guard.rejected, "snap_bytes": s.snap_bytes,
                         "local": s.status == S_LOCAL})
        self.view = view

    # --- comandi dalla UI -------------------------------------------------------------------
    def _process_cmds(self, now):
        while True:
            try:
                cmd = self._cmds.get_nowait()
            except queue.Empty:
                return
            op = cmd[0]
            if op == "open":
                self._open_slot(cmd[1], now)
            elif op == "close":
                s = self._slot(cmd[1])
                if s is not None and s.status != S_LOCAL:
                    self._drop(s, "chiuso dall'host")
                    if self.phase == "lobby":
                        s.reset()
            elif op == "attach":
                s = self._slot(cmd[1])
                if s is not None and s.status not in (S_LOCAL, S_CONNECTED):
                    if s.transport is not None:
                        s.transport.close()
                    s.transport, s.status, s.error = cmd[2], S_CONNECTING, ""
                    s.connect_deadline = now + CONNECT_TIMEOUT
            elif op == "answer":
                self._accept_answer(cmd[1], cmd[2], now)
            elif op == "map":
                self._set_map(cmd[1])
            elif op == "start":
                self._start_draft(now)
            elif op == "shutdown":
                self._broadcast(P.enc_end(None, P.END_HOST_QUIT, cmd[1]))
                time.sleep(0.3)                  # lascia partire il messaggio
                self._running = False
                self.phase = "closed"
                return

    def _slot(self, i):
        if isinstance(i, int) and 0 <= i < self.max_players:
            return self.slots[i]
        return None

    def _open_slot(self, i, now):
        s = self._slot(i)
        if s is None or s.status in (S_LOCAL, S_CONNECTED):
            return
        if self.phase != "lobby" and not s.entity_id:
            s.error = "Partita già iniziata: si può riaprire solo lo slot di chi è caduto."
            return
        from . import rtc
        if not rtc.available():
            s.status, s.error = S_FAILED, "Manca aiortc: installa con  pip install aiortc"
            return
        if s.transport is not None:
            s.transport.close()
        s.transport = rtc.RtcPeer()
        s.session = new_session_id()
        s.status, s.error, s.code = S_GATHERING, "", ""
        s.offer_future = s.transport.create_offer()
        s.answer_future = None

    def _accept_answer(self, i, msg, now):
        s = self._slot(i)
        if s is None or s.status != S_WAITING or msg.session != s.session:
            return
        s.status = S_CONNECTING
        s.connect_deadline = now + CONNECT_TIMEOUT
        s.answer_future = s.transport.accept_answer(msg.sdp)

    def _poll_futures(self):
        for s in self.slots:
            f = s.offer_future
            if f is not None and f.done():
                s.offer_future = None
                try:
                    sdp = f.result()
                    s.code = ManualSignaling.encode(SignalMessage(OFFER, s.index, s.session, sdp))
                    s.status = S_WAITING
                except Exception as e:
                    s.status, s.error = S_FAILED, f"Errore nel creare l'offerta: {e}"
            f = s.answer_future
            if f is not None and f.done():
                s.answer_future = None
                try:
                    f.result()
                except Exception as e:
                    s.status, s.error = S_FAILED, f"Risposta non valida: {e}"

    def _set_map(self, map_index):
        if self.phase != "lobby" or not (0 <= map_index < len(config.MAPS)):
            return
        ts = map_team_size(map_index)
        busy = [s for s in self.slots if s.status not in (S_EMPTY, S_FAILED)]
        if any(s.index >= 2 * ts for s in busy):
            self.message = "Troppi slot aperti per questa mappa: chiudi gli ultimi slot prima."
            return
        self.map_index, self.team_size = map_index, ts
        self._broadcast_lobby()

    # --- connessioni ------------------------------------------------------------------------
    def _check_links(self, now):
        for s in self.slots:
            tr = s.transport
            if tr is None or s.status == S_LOCAL:
                continue
            if s.status in (S_GATHERING, S_WAITING, S_CONNECTING):
                if tr.state == FAILED:
                    s.status, s.error = S_FAILED, tr.error or "Connessione fallita."
                elif tr.state == CONNECTED:
                    s.status, s.error = S_CONNECTED, ""
                elif s.status == S_CONNECTING and now > s.connect_deadline:
                    s.status = S_FAILED
                    s.error = ("Nessuna risposta dalla rete dell'amico. Probabile NAT "
                               "simmetrico: servirebbe un server TURN.")
                    tr.close()
            elif s.status == S_CONNECTED:
                if tr.state in (FAILED, CLOSED):
                    self._drop(s, "connessione persa")
                elif now - tr.last_rx > CLIENT_TIMEOUT:
                    self._drop(s, "non risponde")

    def _drop(self, s, reason):
        """Un client se n'è andato (o è caduto)."""
        was_joined = s.joined
        if s.transport is not None:
            s.transport.close()
            s.transport = None
        s.joined = s.loaded = False
        s.offer_future = s.answer_future = None
        s.code, s.session = "", 0           # il vecchio codice non vale più
        if self.phase == "lobby" or not s.entity_id:
            name = s.name
            if self.phase == "draft" and self.draft.drop_slot(s.index, time.monotonic()):
                self._broadcast_draft(time.monotonic())     # il suo posto passa a un bot
            s.reset()
            if was_joined:
                self._broadcast_lobby()
                self._broadcast(P.enc_event(P.EV_DISCONNECT, s.index, name))
            return
        s.status, s.error = S_DISCONNECTED, reason
        p = self.world.get(s.entity_id)
        if p is not None:
            # Resta dov'è: niente ritorno in base (sarebbe una fuga dai gank).
            p.order = "stop"
            p.order_target_id = None
            p.order_point = None
            p.target_id = None
            p.pending_cast = None
            p.stop()
        self.disconnected.add(s.entity_id)
        self._broadcast(P.enc_event(P.EV_DISCONNECT, s.index, s.name))
        self._broadcast_lobby()

    def _strike(self, s):
        self.rejected_total += 1
        if s.guard.strike() and s.status != S_LOCAL:
            if s.transport is not None:
                s.transport.send_reliable(P.enc_end(None, P.END_KICKED,
                                                    "Espulso: troppi pacchetti non validi."))
            self._drop(s, "espulso")

    def _send(self, s, data, reliable=True):
        if s.transport is not None:
            if reliable:
                s.transport.send_reliable(data)
            else:
                s.transport.send_state(data)

    def _broadcast(self, data):
        for s in self.slots:
            if s.joined:
                self._send(s, data)

    def _broadcast_lobby(self):
        players = []
        for s in self.slots[:self.max_players]:
            if s.joined or s.status == S_DISCONNECTED:
                conn = P.SLOT_DISCONNECTED if s.status == S_DISCONNECTED else P.SLOT_CONNECTED
                players.append({"slot": s.index, "team": s.team, "pokemon": s.pokemon,
                                "ready": s.ready, "conn": conn, "name": s.name,
                                "avatar": s.avatar})
        self._broadcast(P.enc_lobby(self.map_index, self.max_players, players))

    # --- messaggi ---------------------------------------------------------------------------
    def _on_message(self, s, ch, data, now):
        t = P.msg_type(data)
        if ch == P.CH_STATE:
            if t != P.C_INPUT:
                raise P.ProtocolError("tipo non ammesso sul canale state")
            if s.joined:
                self._on_input(s, data)
            return
        if t == P.R_HELLO:
            self._on_hello(s, P.dec_hello(data))
        elif not s.joined:
            raise P.ProtocolError("messaggio prima di HELLO")
        elif t == P.R_CHOICE:
            if self.phase == "lobby":
                c = P.dec_choice(data)
                s.team = c["team"] % 2
                s.pokemon = c["pokemon"] % len(config.ROSTER)
                s.ready = c["ready"]
                self._broadcast_lobby()
        elif t == P.R_PICK:
            pk = P.dec_pick(data)
            d = self.draft
            if self.phase == "draft" and d is not None and d.current_slot() == s.index:
                ok = (d.lock(s.index, pk["pokemon"], now) if pk["lock"]
                      else d.hover_pick(s.index, pk["pokemon"]))
                if ok and pk["lock"]:
                    s.flower_color = pk.get("color", 0)   # Flabébé: colore dei fiori
                if ok:
                    self._broadcast_draft(now)
        elif t == P.R_LOADED:
            if s.entity_id:
                s.loaded = True
        elif t == P.R_ACTION:
            self._on_action(s, P.dec_action(data))
        elif t == P.R_CHAT:
            text = V.clean_text(P.dec_chat(data)["text"])
            if not s.guard.chat.take():
                self._strike(s)
            elif text:
                self._broadcast(P.enc_chat(s.index, text))
        elif t == P.R_PING:
            self._send(s, P.enc_pong(P.dec_ping(data), self.host_clock(now),
                                     self.sim.tick_count if self.sim else 0))
        elif t == P.R_BYE:
            self._drop(s, "uscito")
        else:
            raise P.ProtocolError(f"tipo sconosciuto {t}")

    def _on_hello(self, s, h):
        if h["version"] != P.PROTO_VERSION:
            self._send(s, P.enc_end(None, P.END_KICKED,
                                    "Versione del gioco diversa da quella dell'host: aggiornate."))
            self._drop(s, "versione diversa")
            return
        if s.joined:
            return
        s.name = V.clean_text(h["name"], 24) or f"Giocatore {s.index}"
        s.avatar = V.valid_avatar(h["avatar"])
        s.joined = True
        s.reset_net()
        self._send(s, P.enc_welcome(s.index, self.max_players))
        if self.phase == "lobby":
            t0 = sum(1 for x in self._players() if x.team == 0 and x is not s)
            t1 = sum(1 for x in self._players() if x.team == 1 and x is not s)
            s.team = 0 if t0 <= t1 else 1
            s.ready = False
            self._broadcast(P.enc_event(P.EV_JOIN, s.index, s.name))
            self._broadcast_lobby()
            return
        if s.entity_id:
            # RIENTRO dopo una disconnessione: stesso slot, stesso Pokémon.
            self.disconnected.discard(s.entity_id)
            self._send(s, P.enc_start(config.MAPS[self.map_index][1], s.entity_id,
                                      self._players_info()))
            self._broadcast(P.enc_event(P.EV_RECONNECT, s.index, s.name))
            self._broadcast_lobby()
            if self.phase == "ended" and self.match is not None:
                self._send(s, P.enc_end(self.match.winner, P.END_VICTORY))
        else:
            self._send(s, P.enc_end(None, P.END_KICKED, "La partita è già iniziata."))
            self._drop(s, "partita già iniziata")

    # --- input (canale state) -----------------------------------------------------------------
    def _on_input(self, s, data):
        if not s.guard.packets.take():
            self._strike(s)
            return
        m = P.dec_input(data)
        ack = m["ack"]
        if ack is not None and ack in s.history and (s.ack is None or P.seq_newer(ack, s.ack)):
            s.ack = ack
        if self.phase != "match" or not s.loaded:
            return
        p = self.world.get(s.entity_id)
        if p is None:
            return
        for c in m["cmds"]:
            if s.last_cmd_seq is not None:
                d = P.seq_diff(c["seq"], s.last_cmd_seq)
                if d <= 0:
                    continue                     # già applicato (copia ridondante)
                if d > 1024:
                    self._strike(s)              # fuori finestra: pacchetto falso
                    continue
            s.last_cmd_seq = c["seq"]
            # Si applica all'inizio del prossimo step: lo stato DOPO quello step
            # è il tick tick_count+1 (serve alla riconciliazione del client).
            s.last_cmd_tick = self.sim.tick_count + 1
            if not s.guard.commands.take():
                self._strike(s)
                continue
            cmd = self._validate_cmd(s, p, c)
            if cmd is None:
                self._strike(s)
                continue
            self.sim.queue_command(cmd)

    def _validate_cmd(self, s, p, c):
        from sim.commands import (AttackCommand, AttackMoveCommand, CastMoveCommand,
                                  MoveCommand, RecallCommand, StopCommand)
        g = self.world.grid
        k, eid, seq = c["kind"], s.entity_id, c["seq"]   # entità SEMPRE dallo slot
        if k in (P.CMD_MOVE, P.CMD_ATTACKMOVE, P.CMD_ATTACKMOVE_CHAMP, P.CMD_CAST):
            pt = V.clamp_point(c["x"], c["y"], g.width, g.height)
            if pt is None:
                return None
            if k == P.CMD_MOVE:
                return MoveCommand(seq=seq, entity_id=eid, x=pt[0], y=pt[1])
            if k in (P.CMD_ATTACKMOVE, P.CMD_ATTACKMOVE_CHAMP):
                return AttackMoveCommand(seq=seq, entity_id=eid, x=pt[0], y=pt[1],
                                         champs_only=k == P.CMD_ATTACKMOVE_CHAMP)
            if not V.valid_move_slot(c["slot"]):
                return None
            return CastMoveCommand(seq=seq, entity_id=eid, slot=P.SLOTS_QWER[c["slot"]],
                                   x=pt[0], y=pt[1], hold=float(c.get("hold", 0.0)))
        if k == P.CMD_ATTACK:
            from engine.entities import Structure
            tgt = self.world.get(c["target_id"])
            if (tgt is None or not getattr(tgt, "alive", False)
                    or getattr(tgt, "team", s.team) == s.team):
                return None
            if not isinstance(tgt, Structure) and not self.match.vision.is_enemy_visible(
                    s.team, tgt.id):
                return None                      # nella nebbia: non si può mirare
            return AttackCommand(seq=seq, entity_id=eid, target_id=tgt.id)
        if k == P.CMD_STOP:
            return StopCommand(seq=seq, entity_id=eid)
        if k == P.CMD_RECALL:
            return RecallCommand(seq=seq, entity_id=eid)
        return None

    def _on_action(self, s, a):
        from sim.commands import (BuyItemCommand, ChooseUpgradeCommand, RankMoveCommand,
                                  SellItemCommand, UseItemCommand)
        if not s.guard.actions.take():
            self._strike(s)
            return
        if self.phase != "match" or not s.entity_id:
            return
        k, eid, seq = a["kind"], s.entity_id, a["seq"]
        cmd = None
        if k == P.ACT_RANK and V.valid_move_slot(a["slot"]):
            cmd = RankMoveCommand(seq=seq, entity_id=eid, slot=P.SLOTS_QWER[a["slot"]])
        elif k == P.ACT_CHOOSE and V.valid_move_slot(a["slot"]) and V.valid_choice(a["index"]):
            cmd = ChooseUpgradeCommand(seq=seq, entity_id=eid, slot=P.SLOTS_QWER[a["slot"]],
                                       index=a["index"])
        elif k == P.ACT_BUY and a["item_id"] in self._item_ids:
            cmd = BuyItemCommand(seq=seq, entity_id=eid, item_id=a["item_id"])
        elif k == P.ACT_SELL and V.valid_item_slot(a["slot"]):
            cmd = SellItemCommand(seq=seq, entity_id=eid, slot=a["slot"])
        elif k == P.ACT_USE and V.valid_item_slot(a["slot"]):
            cmd = UseItemCommand(seq=seq, entity_id=eid, slot=a["slot"])
        if cmd is None:
            self._strike(s)
        else:
            self.sim.queue_command(cmd)

    # --- avvio partita ---------------------------------------------------------------------------
    def _start_draft(self, now):
        """INVIO dell'host in lobby: controlli, poi si passa al DRAFT (net/draft.py)."""
        if self.phase != "lobby":
            return
        players = self._players()
        if not players:
            self.message = "Nessun giocatore."
            return
        if not all(s.ready for s in players):
            self.message = "Non sono tutti pronti."
            return
        for team in (0, 1):
            if sum(1 for s in players if s.team == team) > self.team_size:
                self.message = f"Squadra {'BLU' if team == 0 else 'ROSSA'} troppo numerosa."
                return
        # Gli slot non usati (offerte mai accettate) si chiudono: da qui non entra più nessuno.
        for s in self.slots:
            if not s.joined and s.status not in (S_LOCAL,):
                if s.transport is not None:
                    s.transport.close()
                s.reset()
        humans = {t: [s.index for s in players if s.team == t] for t in (0, 1)}
        self.draft = Draft(self.team_size, humans, len(config.ROSTER), now)
        self._draft_done_at = None
        self.phase = "draft"
        self.message = ""
        self._broadcast_draft(now)

    def _draft_step(self, now):
        d = self.draft
        if d.tick(now):
            self._broadcast_draft(now)
        if d.done and self._draft_done_at is None:
            self._draft_done_at = now
            self._broadcast_draft(now)
        if self._draft_done_at is not None and now - self._draft_done_at >= DONE_TIME:
            self._start_match(now)

    def _broadcast_draft(self, now):
        d = self.draft
        entries = []
        for e in d.entries:
            s = self.slots[e["slot"]] if e["slot"] is not None else None
            entries.append({**e, "name": s.name if s else "", "avatar": s.avatar if s else 0})
        self._broadcast(P.enc_draft(self.map_index, entries, d.turn, d.hover,
                                    d.time_left(now), d.done))

    def _start_match(self, now):
        """Fine del draft: si costruisce la partita coi Pokémon scelti (umani e bot)."""
        from engine.content import load_map
        from engine.match import Match
        from engine.world import World
        from sim.simulation import Simulation
        map_data = load_map(str(ROOT / config.MAPS[self.map_index][1]))
        self.world = World(map_data.grid)
        self.match = Match(self.world, map_data)
        for e in sorted(self.draft.entries, key=lambda e: (e["team"], e["pos"])):
            lane = LANES[e["pos"] % 3]
            s = self.slots[e["slot"]] if e["slot"] is not None else None
            if s is not None and s.joined:
                s.team, s.pokemon = e["team"], e["poke"]
                p = self._spawn(map_data, e["team"], lane, e["poke"], False)
                s.entity_id = p.id
                from engine.florges import COLORS as _FCOL
                p.flower_color = _FCOL[min(len(_FCOL) - 1, getattr(s, "flower_color", 0))]
            else:
                self._spawn(map_data, e["team"], lane, e["poke"], True)
        self.match.assign_junglers()
        self.match.vision.update(self.world, 0)
        self.match.vision.update(self.world, 1)
        self.sim = Simulation(self.world, config.TICK_DT, match=self.match)
        info = self._players_info()
        for s in self._players():
            if s.entity_id:
                s.reset_net()
                self._send(s, P.enc_start(config.MAPS[self.map_index][1], s.entity_id, info))
        self.phase = "loading"
        self._load_deadline = now + LOAD_TIMEOUT
        self.message = ""

    def _players_info(self):
        return [{"slot": s.index, "entity_id": s.entity_id, "team": s.team,
                 "pokemon": s.pokemon, "name": s.name, "avatar": s.avatar}
                for s in self.slots if s.entity_id]

    def _get_def(self, idx):
        if idx not in self._defs:
            from engine.content import load_pokemon_def
            self._defs[idx] = load_pokemon_def(str(ROOT / config.ROSTER[idx]))
        return self._defs[idx]

    def _spawn(self, map_data, team, lane, poke_idx, is_bot):
        from engine.vec import Vec2
        offset = {"top": Vec2(-1.2, 0.0), "mid": Vec2(0.0, 0.0), "bot": Vec2(0.0, 1.2)}
        pdef = self._get_def(poke_idx)
        pos = Vec2(*map_data.spawns[f"team{team}"]) + Vec2(0.5, 0.5) + offset[lane]
        p = self.world.spawn_pokemon(pos=pos, team=team, dex=pdef.dex, name=pdef.name,
                                     color=config.TEAM_COLORS[team], speed=pdef.base_speed,
                                     is_bot=is_bot, assigned_lane=lane, types=pdef.types,
                                     base_stats=pdef.base_stats, growth=pdef.growth,
                                     moves=pdef.moves, evolutions=pdef.evolutions,
                                     role=pdef.role, passive=pdef.passive,
                                     attack_range=pdef.attack_range,
                                     attack_cooldown=pdef.attack_cooldown,
                                     attack_fx=pdef.attack_fx,
                                     rec_items=pdef.recommended_items)
        p.radius = pdef.radius
        return p

    # --- snapshot -----------------------------------------------------------------------------------
    def _base_for(self, s, now):
        """Base del delta: l'ultimo snapshot CONFERMATO dal client. Se non c'è (inizio,
        rientro, buco più lungo della storia) si usa il keyframe appena mandato sul
        canale reliable, che arriverà di sicuro; altrimenti None = nuovo keyframe."""
        if s.ack is not None and s.ack in s.history:
            return s.history[s.ack]
        if s.last_key is not None and s.last_key[0] in s.history and now - s.last_key[1] < KEY_RESEND:
            return s.history[s.last_key[0]]
        return None

    def _send_snapshots(self, now):
        from .snapshot import capture_global, capture_hud, capture_me, capture_team, fx_visible
        from .visual import capture_visual
        tick = self.sim.tick_count
        glob = capture_global(self.match)
        teams = {}
        fx = self._fx
        self._fx = []
        for s in self.slots:
            if not (s.joined and s.loaded and s.transport is not None):
                continue
            ents = teams.get(s.team)
            if ents is None:
                ents = teams[s.team] = capture_team(self.match, s.team, self.disconnected)
            p = self.world.get(s.entity_id)
            hud = capture_hud(p)
            me = capture_me(self.match, p, s.last_cmd_seq, s.last_cmd_tick)
            base = self._base_for(s, now)
            s.snap_seq = P.seq_next(s.snap_seq)
            data = P.enc_snapshot(s.snap_seq, tick, ents, glob, hud, me, base)
            s.history[s.snap_seq] = P.Frame(s.snap_seq, tick, ents, glob, hud, me)
            while len(s.history) > SNAP_HISTORY:
                s.history.popitem(last=False)
            if base is None:
                s.last_key = (s.snap_seq, now)
            # Keyframe e delta troppo grandi vanno sul reliable, che frammenta e
            # riassembla da sé; il canale state resta per i delta piccoli.
            self._send(s, data, reliable=base is None or len(data) > P.MAX_STATE_PACKET)
            s.snap_bytes = len(data)
            # Stato visivo (stati, effetti che durano, ricariche): solo se è cambiato.
            vis = P.enc_vis(capture_visual(self.match, s.team, p))
            if vis != s.last_vis:
                s.last_vis = vis
                self._send(s, vis)
            if fx:
                vis = [e for e in fx if fx_visible(self.match, s.team, e)]
                for pkt in P.enc_fx(tick, vis):
                    self._send(s, pkt, reliable=False)

    def _close_all(self):
        for s in self.slots:
            if s.transport is not None and s.status != S_LOCAL:
                s.transport.close()
        if self.slots[0].transport is not None and self.slots[0].status == S_LOCAL:
            self.slots[0].transport.close()
        self.phase = "closed"
