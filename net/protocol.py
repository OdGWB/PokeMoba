"""Formato di TUTTI i pacchetti del multiplayer online (unico file condiviso).

Host e client importano solo da qui: se cambia un campo, cambia in un posto.
Tutto binario (modulo struct), little-endian, niente JSON.

QUANTIZZAZIONE
- Posizioni: int16 = tile × POS_SCALE (128) -> ±256 tile, passo 1/128 di tile
  (la mappa più grande, 5v5, è 150×150).
- Angoli: uint8, 0..255 = 0..360°. La direzione dello sprite (0..7) viaggia
  come angolo (indice × 32).
- HP: uint16 arrotondati. Raggi: uint8 = tile × 100.

DUE DATA CHANNEL (negotiated, id fissi, vedi CH_*)
- state    (id 0): non ordinato, maxRetransmits 0. Input, snapshot delta, FX.
                   Un pacchetto perso non si ritrasmette: arriva il successivo.
- reliable (id 1): ordinato e affidabile. Lobby, chat, keyframe, azioni
                   critiche (acquisti, gradi, scelte), eventi, fine partita, ping.

NUMERI DI SEQUENZA a 16 bit con ARITMETICA CIRCOLARE (RFC 1982): a 20 Hz un
contatore u16 si riavvolge dopo ~55 minuti, quindi MAI confronti con "<": si
usa seq_newer(). Nessun valore è riservato come sentinella: il keyframe si
segnala con un BIT dei flag (F_KEYFRAME), non con base_seq = 0xFFFF.

Ogni messaggio inizia con un byte di tipo. Il byte HEARTBEAT (0x01) è del
trasporto (net/rtc.py) e non arriva mai al gioco.
"""
from __future__ import annotations

import math
import struct

PROTO_VERSION = 4       # 2: avatar; 3: draft (R_DRAFT/R_PICK); 4: stato visivo (R_VIS)

# --- data channel -------------------------------------------------------------
CH_STATE = 0
CH_RELIABLE = 1

# --- tipi di messaggio ----------------------------------------------------------
HEARTBEAT = 0x01        # trasporto: tiene viva la connessione (filtrato da rtc.py)

# canale state
C_INPUT = 0x10          # client -> host: comandi non confermati (ridondanti) + ack snapshot
S_SNAP = 0x20           # host -> client: snapshot (delta; keyframe sul canale reliable)
S_FX = 0x21             # host -> client: eventi visivi cosmetici (persi = pazienza)

# canale reliable
R_HELLO = 0x40          # client -> host: versione protocollo + nome + avatar
R_WELCOME = 0x41        # host -> client: il tuo slot
R_LOBBY = 0x42          # host -> client: stato della lobby
R_CHOICE = 0x43         # client -> host: squadra, Pokémon, pronto
R_START = 0x44          # host -> client: partita avviata (mappa, la tua entità, giocatori)
R_LOADED = 0x45         # client -> host: mappa caricata, pronto a ricevere snapshot
R_ACTION = 0x46         # client -> host: azione critica (grado, scelta, compra, vendi)
R_CHAT = 0x47           # entrambi i versi
R_EVENT = 0x48          # host -> client: giocatore disconnesso / rientrato
R_END = 0x49            # host -> client: fine partita (vittoria o host chiuso)
R_PING = 0x4A           # client -> host: tempo del client
R_PONG = 0x4B           # host -> client: eco + tempo e tick dell'host
R_BYE = 0x4C            # chiusura volontaria
R_DRAFT = 0x4D          # host -> client: stato del draft (ordine, scelte, turno, tempo)
R_PICK = 0x4E           # client -> host: Pokémon in anteprima o confermato nel draft
R_VIS = 0x4F            # host -> client: STATO VISIVO (stati sulle unità, effetti che
                        # durano, pilastri, spiriti, ricariche): vedi net/visual.py

# --- comandi sul canale state (dentro C_INPUT) -----------------------------------
CMD_MOVE = 0
CMD_ATTACK = 1
CMD_ATTACKMOVE = 2
CMD_CAST = 3
CMD_STOP = 6
CMD_RECALL = 9
CMD_ATTACKMOVE_CHAMP = 10   # attacco-movimento col tasto "solo Pokémon"
STATE_CMDS = (CMD_MOVE, CMD_ATTACK, CMD_ATTACKMOVE, CMD_CAST, CMD_STOP, CMD_RECALL,
              CMD_ATTACKMOVE_CHAMP)
MAX_CMDS_PER_INPUT = 16      # comandi ridondanti al massimo per pacchetto
SLOTS_QWER = ["Q", "W", "E", "R"]   # indice di slot mossa 0..3 nei comandi
# Nel byte dello slot di CMD_CAST i 6 bit alti portano la pressione del tasto
# (mosse a carica, Tiro Lungo) a passi di CAST_HOLD_STEP s: il formato non cambia.
CAST_HOLD_STEP = 0.05


def pack_cast_slot(slot: int, hold: float = 0.0) -> int:
    q = max(0, min(63, int(round(float(hold or 0.0) / CAST_HOLD_STEP))))
    return (int(slot) & 3) | (q << 2)

# --- azioni sul canale reliable (dentro R_ACTION) --------------------------------
ACT_RANK = 4
ACT_CHOOSE = 5
ACT_BUY = 7
ACT_SELL = 8
ACT_USE = 9             # attiva l'oggetto di uno slot (Mentalerba, Palla Fumo)
ACTIONS = (ACT_RANK, ACT_CHOOSE, ACT_BUY, ACT_SELL, ACT_USE)

# --- tipi di entità --------------------------------------------------------------
K_POKEMON = 0
K_MINION = 1
K_TOWER = 2
K_CORE = 3
K_WILD = 4              # neutrali della giungla (campi, leggendario, Arceus)

# Significato del campo `extra` per tipo di entità.
#   Pokémon: numero di dex (forma attuale)   Torre: tier
#   Minion: indice in MINION_TYPES           Neutrale: kind | (meteo << 2)
MINION_TYPES = ["melee", "caster", "cannon"]
WILD_KINDS = ["camp", "meteo", "arceus"]
WILD_WEATHERS = ["", "sun", "rain", "wind"]

# --- snapshot ----------------------------------------------------------------------
F_KEYFRAME = 0x01       # nessuna base: tutte le entità sono complete
F_GLOBAL = 0x02         # blocco globale presente (cambiato rispetto alla base)
F_HUD = 0x04            # blocco HUD presente (cambiato rispetto alla base)
F_ME = 0x08             # blocco "io" presente (sempre, se il giocatore ha un'entità)

# Maschera dei campi di un'entità nel delta.
M_NEW = 0x01            # entità nuova rispetto alla base: tutti i campi
M_POS = 0x02
M_HP = 0x04
M_LOOK = 0x08           # angolo + flag
M_SIZE = 0x10           # hp max + raggio
M_EXTRA = 0x20          # squadra + extra (dex / tipo minion / tier)

# Indici della tupla-entità (valori GIÀ quantizzati, confrontabili con ==).
E_KIND, E_TEAM, E_X, E_Y, E_ANG, E_FLAGS, E_HP, E_MAXHP, E_RAD, E_EXTRA = range(10)
EF_MOVING = 0x01
EF_ALIVE = 0x02
EF_DISCONNECTED = 0x04  # Pokémon di un giocatore caduto

# Blocco "io" (per la riconciliazione).
ME_ALIVE = 0x01
ME_CAN_MOVE = 0x02
ME_MOVING = 0x04        # l'host lo sta muovendo (per capire che è arrivato)
ME_HAS_ACK = 0x08       # ack_seq è valido (all'inizio non c'è ancora nessun comando)

# Fine partita.
END_VICTORY = 0
END_HOST_QUIT = 1
END_KICKED = 2

# Eventi.
EV_DISCONNECT = 1
EV_RECONNECT = 2
EV_JOIN = 3

# Stato degli slot in lobby.
SLOT_EMPTY = 0
SLOT_WAITING = 1
SLOT_CONNECTED = 2
SLOT_DISCONNECTED = 3

POS_SCALE = 128
MAX_STATE_PACKET = 1100  # oltre, il pacchetto va sul canale reliable (che frammenta)
SEQ_MOD = 1 << 16


class ProtocolError(ValueError):
    """Pacchetto malformato o troncato."""


# --- aritmetica dei numeri di sequenza --------------------------------------------
def seq_next(s: int) -> int:
    return (s + 1) & 0xFFFF


def seq_diff(a: int, b: int) -> int:
    """a - b in aritmetica circolare a 16 bit, nell'intervallo [-32768, 32767]."""
    d = (a - b) & 0xFFFF
    return d - SEQ_MOD if d >= 0x8000 else d


def seq_newer(a: int, b: int) -> bool:
    """True se a è più recente di b (vale anche dopo il riavvolgimento)."""
    return seq_diff(a, b) > 0


# --- quantizzazione ------------------------------------------------------------------
def q_pos(v: float) -> int:
    return max(-32768, min(32767, round(v * POS_SCALE)))


def dq_pos(q: int) -> float:
    return q / POS_SCALE


def q_angle(rad: float) -> int:
    return round(rad / (2 * math.pi) * 256) & 0xFF


def dq_angle(q: int) -> float:
    return q / 256 * 2 * math.pi


def facing_to_angle(idx: int) -> int:
    return (int(idx) % 8) * 32


def angle_to_facing(q: int) -> int:
    return round(q / 32) % 8


# --- scrittura / lettura ---------------------------------------------------------------
class Writer:
    __slots__ = ("b",)

    def __init__(self):
        self.b = bytearray()

    def u8(self, v): self.b += struct.pack("<B", int(v) & 0xFF); return self
    def i8(self, v): self.b += struct.pack("<b", max(-128, min(127, int(v)))); return self
    def u16(self, v): self.b += struct.pack("<H", int(v) & 0xFFFF); return self
    def i16(self, v): self.b += struct.pack("<h", max(-32768, min(32767, int(v)))); return self
    def u32(self, v): self.b += struct.pack("<I", int(v) & 0xFFFFFFFF); return self
    def i32(self, v): self.b += struct.pack("<i", max(-2**31, min(2**31 - 1, int(v)))); return self
    def f32(self, v): self.b += struct.pack("<f", float(v)); return self
    def f64(self, v): self.b += struct.pack("<d", float(v)); return self

    def pos(self, v):
        return self.i16(q_pos(v))

    def s(self, text, limit=255):
        data = (text or "").encode("utf-8")[:min(255, limit)]
        self.u8(len(data)); self.b += data
        return self

    def bytes(self):
        return bytes(self.b)


class Reader:
    __slots__ = ("d", "i")

    def __init__(self, data):
        self.d = data
        self.i = 0

    def _unpack(self, fmt, n):
        if self.i + n > len(self.d):
            raise ProtocolError("pacchetto troncato")
        v = struct.unpack_from(fmt, self.d, self.i)[0]
        self.i += n
        return v

    def u8(self): return self._unpack("<B", 1)
    def i8(self): return self._unpack("<b", 1)
    def u16(self): return self._unpack("<H", 2)
    def i16(self): return self._unpack("<h", 2)
    def u32(self): return self._unpack("<I", 4)
    def i32(self): return self._unpack("<i", 4)
    def f32(self): return self._unpack("<f", 4)
    def f64(self): return self._unpack("<d", 8)
    def pos(self): return dq_pos(self.i16())

    def s(self):
        n = self.u8()
        if self.i + n > len(self.d):
            raise ProtocolError("stringa troncata")
        v = bytes(self.d[self.i:self.i + n]).decode("utf-8", "replace")
        self.i += n
        return v

    def remaining(self):
        return len(self.d) - self.i


def msg_type(data) -> int:
    return data[0] if data else 0


# ==================================================================================
# CANALE STATE
# ==================================================================================
def enc_input(ack_snap, cmds) -> bytes:
    """ack_snap: ultimo snapshot applicato (None = nessuno ancora).
    cmds: lista di dict {seq, kind, ...} NON ancora confermati, dal più vecchio.
    Ogni pacchetto li ripete tutti: se un pacchetto si perde, il successivo
    porta gli stessi comandi e l'host scarta quelli già applicati."""
    cmds = cmds[-MAX_CMDS_PER_INPUT:]
    w = Writer().u8(C_INPUT).u8(0 if ack_snap is None else 1).u16(ack_snap or 0).u8(len(cmds))
    for c in cmds:
        k = c["kind"]
        w.u16(c["seq"]).u8(k)
        if k in (CMD_MOVE, CMD_ATTACKMOVE, CMD_ATTACKMOVE_CHAMP):
            w.pos(c["x"]).pos(c["y"])
        elif k == CMD_ATTACK:
            w.u16(c["target_id"])
        elif k == CMD_CAST:
            w.u8(pack_cast_slot(c["slot"], c.get("hold", 0.0))).pos(c["x"]).pos(c["y"])
        elif k in (CMD_STOP, CMD_RECALL):
            pass
        else:
            raise ValueError(f"comando sconosciuto {k}")
    return w.bytes()


def dec_input(data) -> dict:
    r = Reader(data); r.u8()
    has_ack = r.u8() & 1
    ack = r.u16()
    n = r.u8()
    if n > MAX_CMDS_PER_INPUT:
        raise ProtocolError("troppi comandi")
    cmds = []
    for _ in range(n):
        c = {"seq": r.u16(), "kind": r.u8()}
        k = c["kind"]
        if k in (CMD_MOVE, CMD_ATTACKMOVE, CMD_ATTACKMOVE_CHAMP):
            c["x"] = r.pos(); c["y"] = r.pos()
        elif k == CMD_ATTACK:
            c["target_id"] = r.u16()
        elif k == CMD_CAST:
            b = r.u8()
            c["slot"] = b & 3; c["x"] = r.pos(); c["y"] = r.pos()
            if b >> 2:
                c["hold"] = (b >> 2) * CAST_HOLD_STEP
        elif k in (CMD_STOP, CMD_RECALL):
            pass
        else:
            raise ProtocolError(f"comando sconosciuto {k}")
        cmds.append(c)
    return {"ack": ack if has_ack else None, "cmds": cmds}


# --- snapshot ------------------------------------------------------------------------
class MissingBase(Exception):
    """Il delta si riferisce a una base che il client non ha (più)."""


class Frame:
    """Stato COMPLETO ricostruito di uno snapshot (dopo aver applicato il delta)."""
    __slots__ = ("seq", "tick", "ents", "glob", "hud", "me", "keyframe", "size")

    def __init__(self, seq, tick, ents, glob, hud, me, keyframe=False, size=0):
        self.seq = seq
        self.tick = tick
        self.ents = ents        # {id: tupla E_*}
        self.glob = glob        # (core0, core1, winner, weather, arceus)
        self.hud = hud          # tupla HUD (vedi _w_hud)
        self.me = me            # (x, y, speed_q, flags, ack_seq, ack_tick) o None
        self.keyframe = keyframe
        self.size = size


def _w_ent_full(w, e):
    w.u8(e[E_KIND]).u8(e[E_TEAM]).i16(e[E_X]).i16(e[E_Y]).u8(e[E_ANG]).u8(e[E_FLAGS])
    w.u16(e[E_HP]).u16(e[E_MAXHP]).u8(e[E_RAD]).u16(e[E_EXTRA])


def _r_ent_full(r):
    return (r.u8(), r.u8(), r.i16(), r.i16(), r.u8(), r.u8(), r.u16(), r.u16(), r.u8(), r.u16())


def _w_hud(w, h):
    # (level, xp_q, points, pending, v,r,cd ×4, gold, items)
    w.u8(h[0]).u32(h[1]).u8(h[2]).u8(h[3])
    for i in range(4):
        w.i8(h[4 + i * 3]).u8(h[5 + i * 3]).u16(h[6 + i * 3])
    w.u32(h[16]).u8(len(h[17]))
    for iid in h[17]:
        w.s(iid, 48)


def _r_hud(r):
    out = [r.u8(), r.u32(), r.u8(), r.u8()]
    for _ in range(4):
        out += [r.i8(), r.u8(), r.u16()]
    out.append(r.u32())
    n = r.u8()
    if n > 12:
        raise ProtocolError("troppi oggetti")
    out.append(tuple(r.s() for _ in range(n)))
    return tuple(out)


def enc_snapshot(seq, tick, ents, glob, hud, me, base=None) -> bytes:
    """Codifica uno snapshot. base = Frame confermato dal client (None = keyframe).

    DELTA ENCODING: per ogni entità si scrivono solo i gruppi di campi cambiati
    rispetto alla base; le entità uguali non si scrivono affatto; quelle che
    nella base c'erano e ora no finiscono nella lista "rimosse"."""
    key = base is None
    flags = F_KEYFRAME if key else 0
    if key or glob != base.glob:
        flags |= F_GLOBAL
    if hud is not None and (key or hud != base.hud):
        flags |= F_HUD
    if me is not None:
        flags |= F_ME
    w = Writer().u8(S_SNAP).u16(seq).u16(0 if key else base.seq).u8(flags).u32(tick)
    if flags & F_ME:
        x, y, spd, mf, aseq, atick = me
        w.i16(x).i16(y).u16(spd).u8(mf).u16(aseq).u32(atick)
    if flags & F_GLOBAL:
        w.u16(glob[0]).u16(glob[1]).i8(glob[2]).u8(glob[3]).u8(glob[4])
    if flags & F_HUD:
        _w_hud(w, hud)

    upd = Writer()
    n_upd = 0
    bents = {} if key else base.ents
    for eid, e in ents.items():
        b = bents.get(eid)
        if b is None or b[E_KIND] != e[E_KIND]:
            upd.u16(eid).u8(M_NEW)
            _w_ent_full(upd, e)
            n_upd += 1
            continue
        if b == e:
            continue
        m = 0
        if b[E_X] != e[E_X] or b[E_Y] != e[E_Y]:
            m |= M_POS
        if b[E_HP] != e[E_HP]:
            m |= M_HP
        if b[E_ANG] != e[E_ANG] or b[E_FLAGS] != e[E_FLAGS]:
            m |= M_LOOK
        if b[E_MAXHP] != e[E_MAXHP] or b[E_RAD] != e[E_RAD]:
            m |= M_SIZE
        if b[E_TEAM] != e[E_TEAM] or b[E_EXTRA] != e[E_EXTRA]:
            m |= M_EXTRA
        upd.u16(eid).u8(m)
        if m & M_POS:
            upd.i16(e[E_X]).i16(e[E_Y])
        if m & M_HP:
            upd.u16(e[E_HP])
        if m & M_LOOK:
            upd.u8(e[E_ANG]).u8(e[E_FLAGS])
        if m & M_SIZE:
            upd.u16(e[E_MAXHP]).u8(e[E_RAD])
        if m & M_EXTRA:
            upd.u8(e[E_TEAM]).u16(e[E_EXTRA])
        n_upd += 1
    removed = [eid for eid in bents if eid not in ents]
    w.u16(n_upd)
    w.b += upd.b
    w.u16(len(removed))
    for eid in removed:
        w.u16(eid)
    return w.bytes()


def peek_snapshot(data) -> tuple:
    """(seq, base_seq, keyframe) senza decodificare tutto."""
    r = Reader(data); r.u8()
    seq, base, flags = r.u16(), r.u16(), r.u8()
    return seq, base, bool(flags & F_KEYFRAME)


def dec_snapshot(data, get_base) -> Frame:
    """Decodifica e ricostruisce lo stato completo. get_base(seq) -> Frame|None."""
    r = Reader(data); r.u8()
    seq, base_seq, flags, tick = r.u16(), r.u16(), r.u8(), r.u32()
    key = bool(flags & F_KEYFRAME)
    base = None
    if not key:
        base = get_base(base_seq)
        if base is None:
            raise MissingBase(base_seq)
    me = None
    if flags & F_ME:
        me = (r.i16(), r.i16(), r.u16(), r.u8(), r.u16(), r.u32())
    if flags & F_GLOBAL:
        glob = (r.u16(), r.u16(), r.i8(), r.u8(), r.u8())
    else:
        glob = base.glob if base is not None else (0, 0, -1, 0, 0)
    if flags & F_HUD:
        hud = _r_hud(r)
    else:
        hud = base.hud if base is not None else None
    ents = {} if key else dict(base.ents)
    for _ in range(r.u16()):
        eid = r.u16()
        m = r.u8()
        if m & M_NEW:
            ents[eid] = _r_ent_full(r)
            continue
        old = ents.get(eid)
        if old is None:
            raise ProtocolError(f"delta su entità sconosciuta {eid}")
        e = list(old)
        if m & M_POS:
            e[E_X] = r.i16(); e[E_Y] = r.i16()
        if m & M_HP:
            e[E_HP] = r.u16()
        if m & M_LOOK:
            e[E_ANG] = r.u8(); e[E_FLAGS] = r.u8()
        if m & M_SIZE:
            e[E_MAXHP] = r.u16(); e[E_RAD] = r.u8()
        if m & M_EXTRA:
            e[E_TEAM] = r.u8(); e[E_EXTRA] = r.u16()
        ents[eid] = tuple(e)
    for _ in range(r.u16()):
        ents.pop(r.u16(), None)
    return Frame(seq, tick, ents, glob, hud, me, keyframe=key, size=len(data))


# --- eventi FX (codifica generica di dict semplici) -------------------------------------
_T_NONE, _T_TRUE, _T_FALSE, _T_INT, _T_FLOAT, _T_STR, _T_NUMS = range(7)


def _w_value(w, v) -> bool:
    if v is None:
        w.u8(_T_NONE)
    elif v is True:
        w.u8(_T_TRUE)
    elif v is False:
        w.u8(_T_FALSE)
    elif isinstance(v, int):
        w.u8(_T_INT).i32(v)
    elif isinstance(v, float):
        w.u8(_T_FLOAT).f32(v)
    elif isinstance(v, str):
        w.u8(_T_STR).s(v, 64)
    elif isinstance(v, (tuple, list)) and len(v) <= 8 and all(
            isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        w.u8(_T_NUMS).u8(len(v))
        for x in v:
            w.f32(x)
    elif hasattr(v, "x") and hasattr(v, "y"):     # Vec2
        w.u8(_T_NUMS).u8(2).f32(v.x).f32(v.y)
    else:
        return False
    return True


def _r_value(r):
    t = r.u8()
    if t == _T_NONE:
        return None
    if t == _T_TRUE:
        return True
    if t == _T_FALSE:
        return False
    if t == _T_INT:
        return r.i32()
    if t == _T_FLOAT:
        return r.f32()
    if t == _T_STR:
        return r.s()
    if t == _T_NUMS:
        n = r.u8()
        if n > 8:
            raise ProtocolError("tupla troppo lunga")
        return tuple(r.f32() for _ in range(n))
    raise ProtocolError(f"tipo valore sconosciuto {t}")


# --- valori annidati (stato visivo): dict, liste e Vec2 sopra i valori semplici ----------
_T_LIST, _T_DICT, _T_VEC = 7, 8, 9
MAX_NEST = 6


def _w_any(w, v, depth=0) -> bool:
    """Come _w_value, più dict (chiavi str/int), liste e Vec2. Ciò che non si
    sa rappresentare (oggetti del motore, set) si salta: è solo grafica."""
    if depth > MAX_NEST:
        return False
    if isinstance(v, dict):
        items = []
        for k, x in v.items():
            if not isinstance(k, (str, int)) or isinstance(k, bool):
                continue
            xw = Writer()
            if _w_any(xw, x, depth + 1):
                items.append((k, xw.b))
        w.u8(_T_DICT).u16(len(items))
        for k, xb in items:
            if isinstance(k, str):
                w.u8(0).s(k, 48)
            else:
                w.u8(1).i32(k)
            w.b += xb
        return True
    if isinstance(v, (list, tuple)) and not (
            len(v) <= 8 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                for x in v)):
        parts = []
        for x in v:
            xw = Writer()
            if _w_any(xw, x, depth + 1):
                parts.append(xw.b)
        w.u8(_T_LIST).u16(len(parts))
        for xb in parts:
            w.b += xb
        return True
    if hasattr(v, "x") and hasattr(v, "y") and not isinstance(v, (int, float, str)):
        w.u8(_T_VEC).f32(v.x).f32(v.y)
        return True
    return _w_value(w, v)


def _r_any(r, depth=0):
    if depth > MAX_NEST:
        raise ProtocolError("annidamento eccessivo")
    t = r.d[r.i] if r.i < len(r.d) else None
    if t == _T_DICT:
        r.u8()
        out = {}
        for _ in range(r.u16()):
            k = r.s() if r.u8() == 0 else r.i32()
            out[k] = _r_any(r, depth + 1)
        return out
    if t == _T_LIST:
        r.u8()
        return [_r_any(r, depth + 1) for _ in range(r.u16())]
    if t == _T_VEC:
        r.u8()
        from engine.vec import Vec2
        return Vec2(r.f32(), r.f32())
    return _r_value(r)


def enc_vis(state: dict) -> bytes:
    w = Writer().u8(R_VIS)
    _w_any(w, state)
    return w.bytes()


def dec_vis(data) -> dict:
    r = Reader(data); r.u8()
    v = _r_any(r)
    if not isinstance(v, dict):
        raise ProtocolError("stato visivo non valido")
    return v


def enc_fx(tick, events, limit=MAX_STATE_PACKET) -> list:
    """Eventi FX -> lista di pacchetti, ognuno sotto `limit` byte. I campi con
    valori non rappresentabili (oggetti complessi) si saltano: sono cosmetici."""
    packets = []
    cur, n = Writer(), 0
    for ev in events:
        ew = Writer()
        items = []
        for k, v in ev.items():
            vw = Writer()
            if _w_value(vw, v):
                items.append((k, vw.b))
        ew.u8(len(items))
        for k, vb in items:
            ew.s(k, 32)
            ew.b += vb
        if n and len(cur.b) + len(ew.b) + 6 > limit:
            packets.append(Writer().u8(S_FX).u32(tick).u8(n).bytes() + cur.bytes())
            cur, n = Writer(), 0
        if len(ew.b) + 6 > limit or n >= 255:
            continue
        cur.b += ew.b
        n += 1
    if n:
        packets.append(Writer().u8(S_FX).u32(tick).u8(n).bytes() + cur.bytes())
    return packets


def dec_fx(data) -> tuple:
    r = Reader(data); r.u8()
    tick = r.u32()
    out = []
    for _ in range(r.u8()):
        ev = {}
        for _ in range(r.u8()):
            k = r.s()
            ev[k] = _r_value(r)
        out.append(ev)
    return tick, out


# ==================================================================================
# CANALE RELIABLE
# ==================================================================================
def enc_hello(name, avatar=0) -> bytes:
    """avatar = numero di Pokédex del ritratto profilo (0 = nessuno)."""
    return Writer().u8(R_HELLO).u8(PROTO_VERSION).s(name, 24).u16(avatar).bytes()


def dec_hello(data) -> dict:
    r = Reader(data); r.u8()
    version = r.u8()
    if version != PROTO_VERSION:             # versione vecchia: il resto può non tornare
        return {"version": version, "name": "", "avatar": 0}
    return {"version": version, "name": r.s(), "avatar": r.u16()}


def enc_welcome(slot, max_slots) -> bytes:
    return Writer().u8(R_WELCOME).u8(slot).u8(max_slots).bytes()


def dec_welcome(data) -> dict:
    r = Reader(data); r.u8()
    return {"slot": r.u8(), "max_slots": r.u8()}


def enc_lobby(map_index, max_slots, players) -> bytes:
    """players: lista di dict {slot, team, pokemon, ready, conn, name, avatar}."""
    w = Writer().u8(R_LOBBY).u8(map_index).u8(max_slots).u8(len(players))
    for p in players:
        w.u8(p["slot"]).u8(p["team"]).u8(p["pokemon"]).u8(1 if p["ready"] else 0)
        w.u8(p["conn"]).s(p["name"], 24).u16(p.get("avatar", 0))
    return w.bytes()


def dec_lobby(data) -> dict:
    r = Reader(data); r.u8()
    map_index, max_slots, n = r.u8(), r.u8(), r.u8()
    players = []
    for _ in range(n):
        players.append({"slot": r.u8(), "team": r.u8(), "pokemon": r.u8(),
                        "ready": bool(r.u8()), "conn": r.u8(), "name": r.s(),
                        "avatar": r.u16()})
    return {"map_index": map_index, "max_slots": max_slots, "players": players}


def enc_choice(team, pokemon, ready) -> bytes:
    return Writer().u8(R_CHOICE).u8(team).u8(pokemon).u8(1 if ready else 0).bytes()


def dec_choice(data) -> dict:
    r = Reader(data); r.u8()
    return {"team": r.u8(), "pokemon": r.u8(), "ready": bool(r.u8())}


NONE8 = 0xFF            # "nessuno" in un campo u8 del draft (bot / non ancora scelto)


def enc_draft(map_index, entries, turn, hover, time_left, done) -> bytes:
    """entries: [{team, pos, slot (None = bot), poke (None), name, avatar}] nell'ordine
    di scelta; turn = indice di chi sceglie (None = finito); time_left in s."""
    def n8(v):
        return NONE8 if v is None else v
    w = Writer().u8(R_DRAFT).u8(map_index).u8(len(entries)).u8(n8(turn)).u8(n8(hover))
    w.u16(min(0xFFFF, int(time_left * 1000))).u8(1 if done else 0)
    for e in entries:
        w.u8(e["team"]).u8(e["pos"]).u8(n8(e["slot"])).u8(n8(e["poke"]))
        w.s(e.get("name", ""), 24).u16(e.get("avatar", 0))
    return w.bytes()


def dec_draft(data) -> dict:
    def o8(v):
        return None if v == NONE8 else v
    r = Reader(data); r.u8()
    map_index, n, turn, hover = r.u8(), r.u8(), o8(r.u8()), o8(r.u8())
    time_left, done = r.u16() / 1000.0, bool(r.u8())
    entries = []
    for _ in range(n):
        entries.append({"team": r.u8(), "pos": r.u8(), "slot": o8(r.u8()), "poke": o8(r.u8()),
                        "name": r.s(), "avatar": r.u16()})
    return {"map_index": map_index, "entries": entries, "turn": turn, "hover": hover,
            "time_left": time_left, "done": done}


def enc_pick(pokemon, lock, color=0) -> bytes:
    # bit 0 = scelta definitiva; bit 1-3 = colore dei fiori (Flabébé, 0-4)
    return Writer().u8(R_PICK).u8(pokemon).u8((1 if lock else 0) | ((color & 7) << 1)).bytes()


def dec_pick(data) -> dict:
    r = Reader(data); r.u8()
    poke = r.u8()
    fl = r.u8()
    return {"pokemon": poke, "lock": bool(fl & 1), "color": (fl >> 1) & 7}


def enc_start(map_path, your_entity_id, players) -> bytes:
    w = Writer().u8(R_START).s(map_path).u16(your_entity_id).u8(len(players))
    for p in players:
        w.u8(p["slot"]).u16(p["entity_id"]).u8(p["team"]).u8(p["pokemon"]).s(p["name"], 24)
        w.u16(p.get("avatar", 0))
    return w.bytes()


def dec_start(data) -> dict:
    r = Reader(data); r.u8()
    map_path, your, n = r.s(), r.u16(), r.u8()
    players = []
    for _ in range(n):
        players.append({"slot": r.u8(), "entity_id": r.u16(), "team": r.u8(),
                        "pokemon": r.u8(), "name": r.s(), "avatar": r.u16()})
    return {"map": map_path, "your_entity_id": your, "players": players}


def enc_loaded() -> bytes:
    return bytes([R_LOADED])


def enc_action(seq, kind, **f) -> bytes:
    w = Writer().u8(R_ACTION).u16(seq).u8(kind)
    if kind == ACT_RANK:
        w.u8(f["slot"])
    elif kind == ACT_CHOOSE:
        w.u8(f["slot"]).u8(f["index"])
    elif kind == ACT_BUY:
        w.s(f["item_id"], 48)
    elif kind in (ACT_SELL, ACT_USE):
        w.u8(f["slot"])
    else:
        raise ValueError(f"azione sconosciuta {kind}")
    return w.bytes()


def dec_action(data) -> dict:
    r = Reader(data); r.u8()
    out = {"seq": r.u16(), "kind": r.u8()}
    k = out["kind"]
    if k == ACT_RANK:
        out["slot"] = r.u8()
    elif k == ACT_CHOOSE:
        out["slot"] = r.u8(); out["index"] = r.u8()
    elif k == ACT_BUY:
        out["item_id"] = r.s()
    elif k in (ACT_SELL, ACT_USE):
        out["slot"] = r.u8()
    else:
        raise ProtocolError(f"azione sconosciuta {k}")
    return out


def enc_chat(slot, text) -> bytes:
    """Dal client lo slot è ignorato (lo mette l'host: niente impersonificazioni)."""
    return Writer().u8(R_CHAT).u8(slot).s(text, 120).bytes()


def dec_chat(data) -> dict:
    r = Reader(data); r.u8()
    return {"slot": r.u8(), "text": r.s()}


def enc_event(kind, slot, name="") -> bytes:
    return Writer().u8(R_EVENT).u8(kind).u8(slot).s(name, 24).bytes()


def dec_event(data) -> dict:
    r = Reader(data); r.u8()
    return {"kind": r.u8(), "slot": r.u8(), "name": r.s()}


def enc_end(winner, reason, message="") -> bytes:
    return Writer().u8(R_END).i8(-1 if winner is None else winner).u8(reason).s(message).bytes()


def dec_end(data) -> dict:
    r = Reader(data); r.u8()
    w = r.i8()
    return {"winner": None if w < 0 else w, "reason": r.u8(), "message": r.s()}


def enc_ping(t_client_ms) -> bytes:
    return Writer().u8(R_PING).u32(t_client_ms).bytes()


def dec_ping(data) -> int:
    r = Reader(data); r.u8()
    return r.u32()


def enc_pong(t_client_ms, host_time, host_tick) -> bytes:
    return Writer().u8(R_PONG).u32(t_client_ms).f64(host_time).u32(host_tick).bytes()


def dec_pong(data) -> dict:
    r = Reader(data); r.u8()
    return {"t_client": r.u32(), "host_time": r.f64(), "host_tick": r.u32()}


def enc_bye(reason=0) -> bytes:
    return Writer().u8(R_BYE).u8(reason).bytes()
