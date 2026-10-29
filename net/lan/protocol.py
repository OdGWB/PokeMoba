"""Protocollo di rete: serializzazione binaria compatta (modulo struct).

Niente JSON per i messaggi: tutto impacchettato in byte. UDP preserva i confini
dei datagrammi, quindi ogni messaggio è un singolo pacchetto senza framing.

Il primo byte è il tipo di messaggio. I valori di gioco usano la virgola fissa
(posizioni ×100 in i16, hp arrotondati in u16) per restare compatti.
"""
from __future__ import annotations

import struct

# --- tipi di messaggio -------------------------------------------------------
C_HELLO = 1      # client -> server: entra (nome)
S_WELCOME = 2    # server -> client: il tuo client_id
C_LOBBY = 3      # client -> server: scelta (team, pokemon, pronto)
S_LOBBY = 4      # server -> client: stato lobby
S_START = 5      # server -> client: partita avviata (mappa, il tuo entity_id, giocatori)
C_INPUT = 6      # client -> server: un comando con numero di sequenza
S_SNAPSHOT = 7   # server -> client: stato filtrato per la sua squadra
S_END = 8        # server -> client: fine partita (vincitore)
C_BYE = 9        # client -> server: disconnessione
C_PING = 10      # client -> server: tieni viva la connessione
S_PONG = 11

# tipi di comando (dentro C_INPUT)
CMD_MOVE = 0
CMD_ATTACK = 1
CMD_ATTACKMOVE = 2
CMD_CAST = 3
CMD_RANK = 4
CMD_CHOOSE = 5
CMD_STOP = 6
CMD_BUY = 7
CMD_SELL = 8
CMD_RECALL = 9

# tipi di entità (negli snapshot)
K_POKEMON = 0
K_MINION = 1
K_TOWER = 2
K_CORE = 3

SLOTS = ["Q", "W", "E", "R"]


class Writer:
    def __init__(self):
        self.b = bytearray()

    def u8(self, v): self.b += struct.pack("<B", int(v) & 0xFF); return self
    def i8(self, v): self.b += struct.pack("<b", max(-128, min(127, int(v)))); return self
    def u16(self, v): self.b += struct.pack("<H", int(v) & 0xFFFF); return self
    def i16(self, v): self.b += struct.pack("<h", max(-32768, min(32767, int(v)))); return self
    def u32(self, v): self.b += struct.pack("<I", int(v) & 0xFFFFFFFF); return self
    def f32(self, v): self.b += struct.pack("<f", float(v)); return self

    def fx(self, v):       # posizione in virgola fissa (tile ×100)
        return self.i16(round(v * 100))

    def hp(self, v):
        return self.u16(max(0, min(65535, round(v))))

    def rad(self, v):
        return self.u8(max(0, min(255, round(v * 100))))

    def s(self, text):
        data = (text or "").encode("utf-8")[:255]
        self.u8(len(data)); self.b += data
        return self

    def bytes(self):
        return bytes(self.b)


class Reader:
    def __init__(self, data):
        self.d = data
        self.i = 0

    def _take(self, n):
        v = self.d[self.i:self.i + n]
        self.i += n
        return v

    def u8(self): return struct.unpack_from("<B", self._take(1))[0]
    def i8(self): return struct.unpack_from("<b", self._take(1))[0]
    def u16(self): return struct.unpack_from("<H", self._take(2))[0]
    def i16(self): return struct.unpack_from("<h", self._take(2))[0]
    def u32(self): return struct.unpack_from("<I", self._take(4))[0]
    def f32(self): return struct.unpack_from("<f", self._take(4))[0]
    def fx(self): return self.i16() / 100.0
    def hp(self): return float(self.u16())
    def rad(self): return self.u8() / 100.0

    def s(self):
        n = self.u8()
        return self._take(n).decode("utf-8", "replace")

    def remaining(self):
        return len(self.d) - self.i


def msg_type(data) -> int:
    return data[0] if data else 0


# --- messaggi di lobby / handshake ------------------------------------------
def enc_hello(name): return Writer().u8(C_HELLO).s(name).bytes()
def enc_welcome(cid): return Writer().u8(S_WELCOME).u8(cid).bytes()
def enc_lobby_choice(team, poke, ready, map_index=0):
    return Writer().u8(C_LOBBY).u8(team).u8(poke).u8(1 if ready else 0).u8(map_index).bytes()
def enc_bye(): return Writer().u8(C_BYE).bytes()
def enc_ping(): return Writer().u8(C_PING).bytes()
def enc_pong(): return Writer().u8(S_PONG).bytes()
def enc_end(winner): return Writer().u8(S_END).i8(-1 if winner is None else winner).bytes()


def enc_lobby_state(players: list, map_index: int = 0) -> bytes:
    """players: lista di dict {client_id, team, pokemon, ready, name}."""
    w = Writer().u8(S_LOBBY).u8(map_index).u8(len(players))
    for p in players:
        w.u8(p["client_id"]).u8(p["team"]).u8(p["pokemon"]).u8(1 if p["ready"] else 0).s(p["name"])
    return w.bytes()


def dec_lobby_state(data) -> dict:
    r = Reader(data); r.u8()
    map_index = r.u8()
    n = r.u8()
    players = []
    for _ in range(n):
        players.append({"client_id": r.u8(), "team": r.u8(), "pokemon": r.u8(),
                        "ready": bool(r.u8()), "name": r.s()})
    return {"map_index": map_index, "players": players}


def enc_start(map_name, your_entity_id, players: list) -> bytes:
    w = Writer().u8(S_START).s(map_name).u16(your_entity_id).u8(len(players))
    for p in players:
        w.u8(p["client_id"]).u16(p["entity_id"]).u8(p["team"]).u8(p["pokemon"]).s(p["name"])
    return w.bytes()


def dec_start(data) -> dict:
    r = Reader(data); r.u8()
    map_name = r.s()
    your = r.u16()
    n = r.u8()
    players = []
    for _ in range(n):
        players.append({"client_id": r.u8(), "entity_id": r.u16(), "team": r.u8(),
                        "pokemon": r.u8(), "name": r.s()})
    return {"map": map_name, "your_entity_id": your, "players": players}


# --- input (comando con numero di sequenza) ---------------------------------
def enc_input(seq, kind, **f) -> bytes:
    w = Writer().u8(C_INPUT).u32(seq).u8(kind)
    if kind in (CMD_MOVE, CMD_ATTACKMOVE):
        w.fx(f["x"]).fx(f["y"])
    elif kind == CMD_ATTACK:
        w.u16(f["target_id"])
    elif kind == CMD_CAST:
        w.u8(f["slot"]).fx(f["x"]).fx(f["y"])
    elif kind == CMD_RANK:
        w.u8(f["slot"])
    elif kind == CMD_CHOOSE:
        w.u8(f["slot"]).u8(f["index"])
    elif kind == CMD_BUY:
        w.s(f["item_id"])
    elif kind == CMD_SELL:
        w.u8(f["slot"])
    # CMD_STOP: nessun campo
    return w.bytes()


def dec_input(data) -> dict:
    r = Reader(data); r.u8()
    seq = r.u32()
    kind = r.u8()
    out = {"seq": seq, "kind": kind}
    if kind in (CMD_MOVE, CMD_ATTACKMOVE):
        out["x"] = r.fx(); out["y"] = r.fx()
    elif kind == CMD_ATTACK:
        out["target_id"] = r.u16()
    elif kind == CMD_CAST:
        out["slot"] = r.u8(); out["x"] = r.fx(); out["y"] = r.fx()
    elif kind == CMD_RANK:
        out["slot"] = r.u8()
    elif kind == CMD_CHOOSE:
        out["slot"] = r.u8(); out["index"] = r.u8()
    elif kind == CMD_BUY:
        out["item_id"] = r.s()
    elif kind == CMD_SELL:
        out["slot"] = r.u8()
    return out
