"""Configurazione ICE: UNICO posto dove stanno i server STUN/TURN.

Per aggiungere un TURN in futuro (serve quando uno dei due è dietro un NAT
simmetrico) basta aggiungere una voce qui sotto, senza toccare la logica:

    {"urls": "turn:mio.server.turn:3478", "username": "utente", "credential": "segreto"},

Nota su aiortc/aioice: di serie usano UN SOLO server STUN. net/rtc.py li
interroga tutti in parallelo e tiene le risposte (vedi _patch_aioice).
"""
from __future__ import annotations

ICE_SERVERS: list[dict] = [
    {"urls": "stun:stun.l.google.com:19302"},
    {"urls": "stun:stun.cloudflare.com:3478"},
]

# Attesa massima del gathering ICE prima di mostrare il codice. I candidati
# devono essere già nell'SDP (signaling manuale = niente trickle ICE).
GATHER_TIMEOUT = 3.0
# Appena uno STUN risponde si aspettano solo altri GATHER_GRACE secondi per le
# altre interfacce: una VPN o un adattatore virtuale che non risponderà mai non
# deve far aspettare tutti i 3 s.
GATHER_GRACE = 0.5
