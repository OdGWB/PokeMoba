"""Signaling MANUALE: l'SDP diventa un codice da incollare su Discord/WhatsApp.

Flusso (un codice per slot):
  1. l'host crea l'offerta per lo slot N -> codice "PKO<N>-...";
  2. l'amico la incolla nel gioco, che genera la risposta "PKA<N>-...";
  3. l'host incolla la risposta nello slot N e la connessione parte.

COME SI ACCORCIA IL CODICE (obiettivo: sotto 1 KB)
L'SDP di aiortc è ~1100 caratteri ma quasi tutto è testo fisso. Si estraggono
solo i campi che cambiano (ufrag, pwd, fingerprint sha-256 come 32 byte grezzi,
ruolo DTLS, candidati ICE in binario) e l'altra parte ricostruisce l'SDP
completo da un modello. Formato 2: credenziali ICE ricavate da 9 byte di seme
(rtc.py), impronta troncata a 16 byte, candidati senza priorita'/raddr (si
ricalcolano), al massimo MAX_CANDS candidati utili, nessun deflate (sono dati
casuali). Base64url senza padding: ~75 caratteri invece di ~150. Se l'SDP
contiene qualcosa che il formato compatto non conosce si ripiega sull'SDP
intero compresso (deflate-raw + base64url).

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

# Formato 2 (dalla 3.0.1): corpo grezzo, niente deflate. I codici del formato 1
# non si leggono piu': i due giochi devono essere della stessa versione.
_FMT_COMPACT = 0xC2
_FMT_FULL = 0xC0
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


# Credenziali ICE "corte": rtc.py fa generare ad aioice ufrag/pwd ricavati da 9
# byte casuali (72 bit) invece di 26 caratteri casuali; nel codice viaggiano
# solo quei 9 byte. Un SDP con credenziali normali le porta per intero.
SEED_LEN = 9
_PWD_TAIL = "PokeMobaPK"       # 12 car. di seme + 10 fissi = 22 (minimo ICE)


def creds_from_seed(seed: bytes) -> tuple:
    s = base64.b64encode(seed).decode("ascii")      # 12 car. [A-Za-z0-9+/]
    return s[:4], s + _PWD_TAIL


def _seed_of(ufrag: str, pwd: str):
    if len(pwd) != 12 + len(_PWD_TAIL) or not pwd.endswith(_PWD_TAIL) or ufrag != pwd[:4]:
        return None
    try:
        seed = base64.b64decode(pwd[:12], validate=True)
    except ValueError:
        return None
    return seed if creds_from_seed(seed) == (ufrag, pwd) else None


# Impronta del certificato DTLS: ne viaggiano i primi 16 byte (128 bit, ben oltre
# il necessario contro una seconda preimmagine). rtc._patch_dtls accetta
# un'impronta sha-256 "corta" come PREFISSO di quella del certificato.
FP_LEN = 16
MAX_CANDS = 6                  # bastano: srflx (Internet) + qualche host (LAN)
_SETUP = ["actpass", "active", "passive"]
_TYPES = ["host", "srflx", "prflx", "relay"]
_TYPE_PREF = {"host": 126, "srflx": 100, "prflx": 110, "relay": 0}
_DEF_SCTP, _DEF_MAXMSG = 5000, 65536


def _useful(ip) -> bool:
    """Indirizzi che a un amico non servono mai: loopback, link-local IPv6."""
    return not (ip.is_loopback or ip.is_unspecified
                or (ip.version == 6 and ip.is_link_local))


def _compact(sdp: str) -> bytes:
    """Estrae i campi variabili dell'SDP. Solleva _NotCompact se qualcosa non
    rientra nel modello (allora si usa l'SDP intero). I candidati che il modello
    non sa scrivere (TCP, mDNS ".local", componente 2) si SCARTANO invece di
    ripiegare sull'SDP intero: aiortc usa comunque solo UDP componente 1."""
    ufrag = pwd = fp = setup = None
    sctp_port, max_msg = _DEF_SCTP, _DEF_MAXMSG
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
            # foundation component transport priority ip port typ TYPE [...]
            if len(p) < 8 or p[1] != "1" or p[2].lower() != "udp" or p[6] != "typ":
                continue
            if p[7] not in _TYPE_PREF:
                continue
            try:
                ip = ipaddress.ip_address(p[4])
            except ValueError:
                continue                      # es. candidati mDNS ".local"
            if not _useful(ip):
                continue
            key = (p[4], int(p[5]))
            if all((c[1], c[2]) != key for c in cands):
                cands.append((p[7], p[4], int(p[5]), int(p[3])))
        elif line.startswith("m=") and "webrtc-datachannel" not in line:
            raise _NotCompact(line)          # media audio/video: non ci servono
    if not (ufrag and pwd and fp and len(fp) >= FP_LEN and setup in _SETUP and cands):
        raise _NotCompact("campi mancanti")
    if len(ufrag) > 255 or len(pwd) > 255:
        raise _NotCompact("credenziali troppo lunghe")
    # prima i riflessi (Internet), poi gli host IPv4, poi il resto; a parita'
    # vale la priorita' data da aioice
    order = {"srflx": 0, "prflx": 1, "relay": 2, "host": 3}
    cands.sort(key=lambda c: (order[c[0]], ":" in c[1], -c[3]))
    cands = cands[:MAX_CANDS]
    seed = _seed_of(ufrag, pwd)
    default_sctp = (sctp_port, max_msg) == (_DEF_SCTP, _DEF_MAXMSG)
    # byte di testa: bit0-1 setup, bit2 credenziali da seme, bit3 sctp standard,
    # bit4-7 numero di candidati
    head = (_SETUP.index(setup) | (4 if seed else 0) | (8 if default_sctp else 0)
            | (len(cands) << 4))
    w = Writer()
    w.u8(head)
    if seed:
        w.b += seed
    else:
        w.s(ufrag).s(pwd)
    w.b += fp[:FP_LEN]
    if not default_sctp:
        w.u16(sctp_port).u32(max_msg)
    for ctype, ip, port, _prio in cands:
        a = ipaddress.ip_address(ip)
        w.u8(_TYPES.index(ctype) | (4 if a.version == 6 else 0))   # bit2 = IPv6
        w.b += a.packed
        w.u16(port)
    return w.bytes()


def _take(r: Reader, n: int) -> bytes:
    if r.i + n > len(r.d):
        raise ProtocolError("codice troncato")
    out = bytes(r.d[r.i:r.i + n]); r.i += n
    return out


def _expand(r: Reader) -> str:
    """Ricostruisce un SDP completo (formato aiortc) dalla forma compatta."""
    head = r.u8()
    if head & 3 == 3:
        raise ProtocolError("setup non valido")
    setup = _SETUP[head & 3]
    if head & 4:
        ufrag, pwd = creds_from_seed(_take(r, SEED_LEN))
    else:
        ufrag, pwd = r.s(), r.s()
    fp = _take(r, FP_LEN)
    sctp_port, max_msg = (_DEF_SCTP, _DEF_MAXMSG) if head & 8 else (r.u16(), r.u32())
    cand_lines = []
    first = None
    for i in range(head >> 4):
        b = r.u8()
        ctype = _TYPES[b & 3]
        ip = str(ipaddress.ip_address(_take(r, 16 if b & 4 else 4)))
        port = r.u16()
        # priorita' standard RFC 8445: preferenza del tipo, poi l'ordine nel codice
        prio = (_TYPE_PREF[ctype] << 24) | ((65535 - i) << 8) | 255
        line = f"a=candidate:{ctype}{i} 1 udp {prio} {ip} {port} typ {ctype}"
        if ctype != "host":
            line += " raddr 0.0.0.0 rport 0"
        cand_lines.append(line)
        if first is None:
            first = (ip, port)
    if first is None:
        raise ProtocolError("nessun candidato")
    if r.i != len(r.d):
        raise ProtocolError("byte in piu'")
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
        # Tipo e slot stanno gia' nel prefisso "PKO3-": nel corpo solo formato
        # e sessione. La forma compatta e' quasi tutta casuale (seme, impronta,
        # indirizzi): comprimerla la allungherebbe, quindi resta grezza.
        w = Writer()
        try:
            body = _compact(msg.sdp)
            w.u8(_FMT_COMPACT)
        except _NotCompact:
            body = deflate_raw(msg.sdp.encode("utf-8"))
            w.u8(_FMT_FULL)
        w.u32(msg.session)
        w.b += body
        return f"PK{msg.kind}{msg.slot}-{b64url(w.bytes())}"

    @staticmethod
    def decode(text: str) -> SignalMessage:
        # Discord/WhatsApp possono aggiungere spazi, a capo o ``` attorno al codice.
        clean = re.sub(r"[\s`'\"]", "", text or "")
        m = _CODE_RE.search(clean)
        if not m:
            raise SignalingError("Codice non riconosciuto: deve iniziare con PKO o PKA.")
        k, slot = m.group(1), int(m.group(2))
        try:
            r = Reader(unb64url(m.group(3)))
            fmt, session = r.u8(), r.u32()
            if fmt == _FMT_COMPACT:
                sdp = _expand(r)
            elif fmt == _FMT_FULL:
                sdp = inflate_raw(bytes(r.d[r.i:])).decode("utf-8")
            else:
                raise SignalingError("Codice di una versione diversa del gioco: "
                                     "aggiornate entrambi all'ultima versione.")
        except SignalingError:
            raise
        except Exception:
            raise SignalingError("Codice danneggiato o di una versione diversa del "
                                 "gioco: ricopialo per intero.")
        return SignalMessage(k, slot, session, sdp)
