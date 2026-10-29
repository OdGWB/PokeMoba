"""Interfaccia di trasporto: due canali (state / reliable) verso UN peer.

HostSession e ClientSession parlano solo con questa interfaccia, quindi non
sanno se sotto c'è WebRTC (net/rtc.py) o un tubo in memoria (LoopbackTransport:
il giocatore dell'host, e i test).

Tutti i metodi sono chiamabili da QUALSIASI thread.
"""
from __future__ import annotations

import collections
import random
import threading
import time

from .protocol import CH_RELIABLE, CH_STATE

# Stati del trasporto (stringhe, così si mostrano direttamente in lobby).
NEW = "new"
GATHERING = "gathering"      # raccolta candidati ICE in corso
WAITING = "waiting"          # offerta pronta, si aspetta la risposta
CONNECTING = "connecting"
CONNECTED = "connected"
FAILED = "failed"
CLOSED = "closed"


class Transport:
    state: str = NEW
    error: str = ""
    last_rx: float = 0.0      # time.monotonic() dell'ultimo byte ricevuto
    bytes_in: int = 0
    bytes_out: int = 0

    def send(self, channel: int, data: bytes) -> None:
        raise NotImplementedError

    def recv(self) -> list:
        """Messaggi arrivati dall'ultima chiamata: lista di (canale, bytes)."""
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def send_state(self, data: bytes) -> None:
        self.send(CH_STATE, data)

    def send_reliable(self, data: bytes) -> None:
        self.send(CH_RELIABLE, data)


class LoopbackTransport(Transport):
    """Un capo di un tubo in memoria. Per i test si possono simulare latenza
    (secondi, solo andata) e perdita (solo sul canale state, come WebRTC)."""

    def __init__(self, latency=0.0, loss=0.0, seed=None):
        self.state = CONNECTED
        self.peer = None
        self.latency = latency
        self.loss = loss
        self._rng = random.Random(seed)
        self._q = collections.deque()      # (consegna_a, canale, dati)
        self._lock = threading.Lock()
        self.last_rx = time.monotonic()
        self.bytes_in = self.bytes_out = 0

    @classmethod
    def pair(cls, latency=0.0, loss=0.0, seed=None):
        a = cls(latency, loss, seed)
        b = cls(latency, loss, None if seed is None else seed + 1)
        a.peer, b.peer = b, a
        return a, b

    def send(self, channel, data):
        if self.state != CONNECTED or self.peer is None or self.peer.state != CONNECTED:
            return
        self.bytes_out += len(data)
        if channel == CH_STATE and self.loss and self._rng.random() < self.loss:
            return
        with self.peer._lock:
            self.peer._q.append((time.monotonic() + self.latency, channel, bytes(data)))

    def recv(self):
        now = time.monotonic()
        out = []
        with self._lock:
            # Il canale reliable resta ordinato; lo state con latenza costante
            # arriva comunque in ordine (basta per i test).
            while self._q and self._q[0][0] <= now:
                _t, ch, d = self._q.popleft()
                out.append((ch, d))
                self.bytes_in += len(d)
        if out:
            self.last_rx = now
        elif self.peer is not None and self.peer.state == CONNECTED:
            self.last_rx = now          # in memoria il peer è vivo finché non chiude
        return out

    def close(self):
        self.state = CLOSED
        if self.peer is not None:
            self.peer.state = CLOSED
