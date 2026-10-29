"""Interpolazione delle ALTRE entità con un buffer di ~100 ms.

Gli snapshot arrivano a 20 Hz (uno ogni 50 ms) e a volte se ne perde uno. Se
disegnassimo l'ultima posizione ricevuta le unità avanzerebbero a scatti.
Invece si disegna il mondo com'era INTERP_DELAY secondi fa (sull'orologio
dell'host): in quel momento abbiamo quasi sempre due campioni che lo
racchiudono, e si interpola linearmente fra i due. 100 ms = due snapshot di
margine, quindi uno perso non si nota.
"""
from __future__ import annotations

import bisect
import collections

INTERP_DELAY = 0.10
MAX_EXTRAPOLATE = 0.10     # oltre l'ultimo campione si prosegue al massimo così
TELEPORT_DIST = 3.0        # salto più lungo (tile) = teletrasporto: niente scivolata


class InterpBuffer:
    def __init__(self, keep: int = 24):
        self.keep = keep
        self._t: dict = {}       # id -> deque dei tempi
        self._p: dict = {}       # id -> deque di (x, y)

    def push(self, eid: int, t: float, x: float, y: float) -> None:
        ts = self._t.get(eid)
        if ts is None:
            ts = self._t[eid] = collections.deque(maxlen=self.keep)
            self._p[eid] = collections.deque(maxlen=self.keep)
        if ts and t <= ts[-1]:
            return
        ts.append(t)
        self._p[eid].append((x, y))

    def forget(self, keep_ids) -> None:
        for eid in [e for e in self._t if e not in keep_ids]:
            del self._t[eid]
            del self._p[eid]

    def sample(self, eid: int, render_t: float):
        ts = self._t.get(eid)
        if not ts:
            return None
        ps = self._p[eid]
        if render_t <= ts[0] or len(ts) == 1:
            return ps[0] if render_t <= ts[0] else ps[-1]
        if render_t >= ts[-1]:
            # Estrapolazione breve (pacchetto in ritardo), poi ci si ferma.
            (t0, (x0, y0)), (t1, (x1, y1)) = (ts[-2], ps[-2]), (ts[-1], ps[-1])
            if t1 - t0 <= 1e-6 or abs(x1 - x0) + abs(y1 - y0) > TELEPORT_DIST:
                return x1, y1
            a = min(render_t - t1, MAX_EXTRAPOLATE) / (t1 - t0)
            return x1 + (x1 - x0) * a, y1 + (y1 - y0) * a
        i = bisect.bisect_right(ts, render_t)
        t0, t1 = ts[i - 1], ts[i]
        (x0, y0), (x1, y1) = ps[i - 1], ps[i]
        if abs(x1 - x0) + abs(y1 - y0) > TELEPORT_DIST:
            return x0, y0
        a = (render_t - t0) / (t1 - t0)
        return x0 + (x1 - x0) * a, y0 + (y1 - y0) * a
