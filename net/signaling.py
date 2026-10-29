"""Signaling MANUALE: l'SDP diventa un codice da incollare su Discord/WhatsApp.

Flusso (un codice per slot):
  1. l'host crea l'offerta per lo slot N -> codice "PKO<N>-...";
  2. l'amico la incolla nel gioco, che genera la risposta "PKA<N>-...";
  3. l'host incolla la risposta nello slot N e la connessione parte.

COME SI ACCORCIA IL CODICE (obiettivo: sotto 1 KB)
L'SDP di aiortc è ~1100 caratteri ma quasi tutto è testo fisso. Si estraggono
solo i campi che cambiano (ufrag, pwd, fingerprint sha-256 come 32 byte grezzi,
ruolo DTLS, candidati ICE in binario) e l'altra parte ricostruisce l'SDP
completo da un modello. Poi deflate-raw (zlib wbits=-15, l'equivalente di
CompressionStream('deflate-raw')) e base64url senza padding. Risultato tipico:
~150 caratteri. Se l'SDP contiene qualcosa che il formato compatto non conosce
si ripiega sull'SDP intero compresso (sempre deflate-raw + base64url).

Nel codice ci sono anche lo SLOT e un ID DI SESSIONE casuale: una risposta
incollata nello slot sbagliato, o vecchia, viene rifiutata con un messaggio.

Per passare in futuro a un signaling server basta implementare un'altra classe
con la stessa interfaccia di ManualSignaling (encode/decode di SignalMessage):
host e client non sanno come viaggia il messaggio.
"""
from __future__ import annotations

import base64
import ipaddress
import random
import re
import zlib
from dataclasses import dataclass

from .protocol import ProtocolError, Reader, Writer

OFFER = "O"
ANSWER = "A"

_FMT_COMPACT = 1
_FMT_FULL = 0
_SETUP = ["actpass", "active", "passive"]
_CTYPE = ["host", "srflx", "prflx", "relay"]
_CODE_RE = re.compile(r"PK([OA])(\d)-([A-Za-z0-9_\-]+)")


class SignalingError(ValueError):
    """Codice incollato non valido (con un messaggio per l'utente)."""


@dataclass
class SignalMessage:
    kind: str        # OFFER / ANSWER
    slot: int
    session: int     # u32 casuale scelto dall'host per quello slot
    sdp: str


def new_session_id() -> int:
    return random.getrandbits(32)


# --- compressione ---------------------------------------------------------------
def deflate_raw(data: bytes) -> bytes:
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()


def inflate_raw(data: bytes, limit: int = 64 * 1024) -> bytes:
    d = zlib.decompressobj(-15)
    out = d.decompress(data, limit)
    if d.unconsumed_tail:
        raise SignalingError("codice troppo grande")
    return out


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- SDP <-> forma compatta ---------------------------------------------------------
class _NotCompact(Exception):
    pass


def _w_ip(w: Writer, ip: str):
    a = ipaddress.ip_address(ip)
    w.u8(a.version)
    w.b += a.packed


def _r_ip(r: Reader) -> str:
    v = r.u8()
    n = 4 if v == 4 else 16 if v == 6 else 0
    if not n or r.i + n > len(r.d):
        raise ProtocolError("ip non valido")
    raw = bytes(r.d[r.i:r.i + n]); r.i += n
    return str(ipaddress.ip_address(raw))


def _compact(sdp: str) -> bytes:
    """Estrae i campi variabili dell'SDP. Solleva _NotCompact se qualcosa non
    rientra nel modello (allora si usa l'SDP intero)."""
    ufrag = pwd = fp = setup = None
    sctp_port, max_msg = 5000, 65536
    cands = []
    for line in sdp.splitlines():
        line = line.strip()
        if line.startswith("a=ice-ufrag:"):
            ufrag = line[12:]
        elif line.startswith("a=ice-pwd:"):
            pwd = line[10:]
        elif line.startswith("a=fingerprint:sha-256 "):
            fp = bytes.fromhex(line[22:].replace(":", ""))
        elif line.startswith("a=setup:"):
            setup = line[8:]
        elif line.startswith("a=sctp-port:"):
            sctp_port = int(line[12:])
        elif line.startswith("a=max-message-size:"):
            max_msg = int(line[19:])
        elif line.startswith("a=candidate:"):
            p = line[12:].split()
            # foundation component transport priority ip port typ TYPE [raddr IP rport P]
            if len(p) < 8 or p[1] != "1" or p[2].lower() != "udp" or p[6] != "typ":
                raise _NotCompact(line)
            ctype = p[7]
            if ctype not in _CTYPE:
                raise _NotCompact(line)
            try:
                ipaddress.ip_address(p[4])
            except ValueError:
                raise _NotCompact(line)       # es. candidati mDNS ".local"
            raddr = rport = None
            if ctype != "host":
                if "raddr" not in p or "rport" not in p:
                    raise _NotCompact(line)
                raddr = p[p.index("raddr") + 1]
                rport = int(p[p.index("rport") + 1])
                try:
                    ipaddress.ip_address(raddr)
                except ValueError:
                    raise _NotCompact(line)
            cands.append((ctype, int(p[3]), p[4], int(p[5]), raddr, rport))
        elif line.startswith("m=") and "webrtc-datachannel" not in line:
            raise _NotCompact(line)          # media audio/video: non ci servono
    if not (ufrag and pwd and fp and len(fp) == 32 and setup in _SETUP and cands):
        raise _NotCompact("campi mancanti")
    if len(cands) > 32:
        raise _NotCompact("troppi candidati")
    w = Writer()
    w.s(ufrag).s(pwd).u8(_SETUP.index(setup))
    w.b += fp
    w.u16(sctp_port).u32(max_msg).u8(len(cands))
    for ctype, prio, ip, port, raddr, rport in cands:
        w.u8(_CTYPE.index(ctype)).u32(prio)
        _w_ip(w, ip)
        w.u16(port)
        if ctype != "host":
            _w_ip(w, raddr)
            w.u16(rport)
    return w.bytes()


def _expand(r: Reader) -> str:
    """Ricostruisce un SDP completo (formato aiortc) dalla forma compatta."""
    ufrag, pwd = r.s(), r.s()
    setup = _SETUP[r.u8() % 3]
    if r.i + 32 > len(r.d):
        raise ProtocolError("fingerprint troncata")
    fp = bytes(r.d[r.i:r.i + 32]); r.i += 32
    sctp_port, max_msg = r.u16(), r.u32()
    cand_lines = []
    first = None
    for i in range(r.u8()):
        ctype = _CTYPE[r.u8() % 4]
        prio = r.u32()
        ip = _r_ip(r)
        port = r.u16()
        line = f"a=candidate:{ctype}{i} 1 udp {prio} {ip} {port} typ {ctype}"
        if ctype != "host":
            raddr = _r_ip(r)
            rport = r.u16()
            line += f" raddr {raddr} rport {rport}"
        cand_lines.append(line)
        if first is None:
            first = (ip, port)
    if first is None:
        raise ProtocolError("nessun candidato")
    ip, port = first
    fam = "IP6" if ":" in ip else "IP4"
    sid = random.getrandbits(31)
    fp_hex = ":".join(f"{b:02X}" for b in fp)
    lines = [
        "v=0",
        f"o=- {sid} {sid} IN IP4 0.0.0.0",
        "s=-",
        "t=0 0",
        "a=group:BUNDLE 0",
        "a=msid-semantic:WMS *",
        f"m=application {port} UDP/DTLS/SCTP webrtc-datachannel",
        f"c=IN {fam} {ip}",
        "a=mid:0",
        f"a=sctp-port:{sctp_port}",
        f"a=max-message-size:{max_msg}",
        *cand_lines,
        "a=end-of-candidates",
        f"a=ice-ufrag:{ufrag}",
        f"a=ice-pwd:{pwd}",
        f"a=fingerprint:sha-256 {fp_hex}",
        f"a=setup:{setup}",
    ]
    return "\r\n".join(lines) + "\r\n"


# --- codec del codice da incollare ----------------------------------------------------
class ManualSignaling:
    """Codifica/decodifica dei codici scambiati a mano."""

    @staticmethod
    def encode(msg: SignalMessage) -> str:
        w = Writer()
        try:
            body = _compact(msg.sdp)
            w.u8(_FMT_COMPACT)
        except _NotCompact:
            body = msg.sdp.encode("utf-8")
            w.u8(_FMT_FULL)
        w.u8(0 if msg.kind == OFFER else 1).u8(msg.slot).u32(msg.session)
        w.b += body
        return f"PK{msg.kind}{msg.slot}-{b64url(deflate_raw(w.bytes()))}"

    @staticmethod
    def decode(text: str) -> SignalMessage:
        # Discord/WhatsApp possono aggiungere spazi, a capo o ``` attorno al codice.
        clean = re.sub(r"[\s`'\"]", "", text or "")
        m = _CODE_RE.search(clean)
        if not m:
            raise SignalingError("Codice non riconosciuto: deve iniziare con PKO o PKA.")
        try:
            raw = inflate_raw(unb64url(m.group(3)))
            r = Reader(raw)
            fmt, kind, slot, session = r.u8(), r.u8(), r.u8(), r.u32()
            if fmt == _FMT_COMPACT:
                sdp = _expand(r)
            elif fmt == _FMT_FULL:
                sdp = bytes(r.d[r.i:]).decode("utf-8")
            else:
                raise SignalingError("Codice di una versione diversa del gioco.")
        except SignalingError:
            raise
        except Exception:
            raise SignalingError("Codice danneggiato: ricopialo per intero.")
        k = OFFER if kind == 0 else ANSWER
        if k != m.group(1) or str(slot) != m.group(2):
            raise SignalingError("Codice danneggiato: ricopialo per intero.")
        return SignalMessage(k, slot, session, sdp)
