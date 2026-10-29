"""Misure di rete per l'HUD di debug: ping, offset di clock, perdita, byte.

SINCRONIZZAZIONE DEL CLOCK (sul canale reliable, una volta al secondo)
Il client manda PING(t_client); l'host risponde PONG(t_client, t_host). Al
ritorno:   RTT    = adesso - t_client
           offset = t_host + RTT/2 - adesso     (orologio host - orologio client)
Il campione con RTT MINIMO fra gli ultimi è il più affidabile (meno tempo in
coda = meno asimmetria), quindi l'offset si prende da quello.
"""
from __future__ import annotations

import collections


class ClockSync:
    def __init__(self, window: int = 16):
        self.samples = collections.deque(maxlen=window)    # (rtt, offset)
        self.rtt = None             # RTT per l'HUD: mediana degli ultimi 5 campioni
        self.offset = None          # orologio host - orologio locale (s)

    def add(self, t_sent: float, t_host: float, t_now: float) -> None:
        rtt = max(0.0, t_now - t_sent)
        self.samples.append((rtt, t_host + rtt / 2 - t_now))
        # Mediana, non media: un PONG letto in ritardo perché il gioco era
        # bloccato (caricamento mappa) non deve gonfiare il ping per secondi.
        recent = sorted(r for r, _ in list(self.samples)[-5:])
        self.rtt = recent[len(recent) // 2]
        self.offset = min(self.samples)[1]

    def seed(self, t_host: float, t_now: float) -> None:
        """Stima grezza (senza RTT) finché non arriva il primo PONG."""
        if self.offset is None:
            self.offset = t_host - t_now

    def host_time(self, t_now: float) -> float:
        return t_now + (self.offset or 0.0)


class LossMeter:
    """Perdita stimata dai buchi nei numeri di sequenza degli snapshot."""

    def __init__(self, window: int = 100):
        self.window = collections.deque(maxlen=window)   # 1 = arrivato, 0 = perso
        self.last = None

    def on_seq(self, seq: int) -> None:
        from .protocol import seq_diff
        if self.last is not None:
            gap = seq_diff(seq, self.last)
            if gap <= 0:
                return               # duplicato / fuori ordine
            for _ in range(min(gap - 1, 50)):
                self.window.append(0)
        self.window.append(1)
        self.last = seq

    @property
    def loss(self) -> float:
        if not self.window:
            return 0.0
        return 1.0 - sum(self.window) / len(self.window)


class Rate:
    """Media mobile esponenziale di un valore (es. byte per pacchetto)."""

    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha
        self.value = 0.0
        self.last = 0

    def add(self, v: float) -> None:
        self.last = v
        self.value = v if self.value == 0.0 else self.value * (1 - self.alpha) + v * self.alpha
