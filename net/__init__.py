"""Multiplayer online: WebRTC con signaling manuale (nessun server).

Interfaccia pubblica (il resto del gioco usa solo questa):
    HostSession     l'host: slot, simulazione autoritativa, snapshot
    ClientSession   un giocatore: input, snapshot, ping
    ManualSignaling codici da scambiare a mano (sostituibile da un server)
    RtcPeer         trasporto WebRTC (aiortc);  LoopbackTransport in memoria

Struttura:
    protocol.py    formato di TUTTI i pacchetti (unico file condiviso)
    signaling.py   SDP -> codice compatto (deflate-raw + base64url)
    rtc.py         aiortc in un thread asyncio dedicato + code thread-safe
    transport.py   interfaccia Transport + LoopbackTransport
    host.py        HostSession          client.py   ClientSession
    snapshot.py    stato del Match -> tuple quantizzate per squadra
    prediction.py  predizione + riconciliazione del proprio personaggio
    interp.py      interpolazione delle altre entità (~100 ms)
    validation.py  clamp, rate limiting, controlli lato host
    stats.py       ping, clock, perdita, byte (HUD di debug)
    ice_config.py  server STUN/TURN
    lan/           vecchia modalità LAN UDP (riferimento, verrà rimossa)
"""
from .client import ClientSession
from .host import HostSession
from .signaling import ManualSignaling, SignalingError
from .transport import LoopbackTransport

__all__ = ["ClientSession", "HostSession", "ManualSignaling", "SignalingError",
           "LoopbackTransport"]
