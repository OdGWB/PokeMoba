"""Effetti LEGGERI dell'attacco base: scintilla d'impatto e fendente corpo a corpo.

Solo grafica. Ogni effetto e' un piccolo sprite pixel-art a risoluzione nativa,
disegnato UNA volta per (colore, fotogramma[, direzione]) e messo in cache: a
ogni frame solo un blit per colpo vivo (nessuna Surface a schermo intero,
nessuna particella). Il colpo resta ANCORATO al bersaglio (segue chi si muove).

  - scintilla: stella a 4 raggi + 4 diagonali corte, nucleo bianco, bordo del
    colore del tipo; 4 fotogrammi in ~0,2 s (esplode, si apre, si stacca, svanisce);
  - fendente (solo corpo a corpo): mezzaluna con contorno scuro, perpendicolare
    al colpo, che si apre in 3 fotogrammi (~0,13 s).
Il lampo bianco sullo sprite colpito e' in SpriteAnimator (hit_flash).
"""
from __future__ import annotations

import math

import pygame

SPARK_T = 0.2
SWIPE_T = 0.13
CHEST = 0.42          # tile: altezza del busto sopra il punto a terra
MAX_HITS = 64

_spark_cache: dict = {}
_swipe_cache: dict = {}


def _lighten(c, f):
    return tuple(int(v + (255 - v) * f) for v in c)


def _darken(c, f):
    return tuple(int(v * f) for v in c)


def spark_sprite(col, frame: int, big: bool) -> pygame.Surface:
    key = (col, frame, big)
    s = _spark_cache.get(key)
    if s is not None:
        return s
    R = 9 if big else 7
    n = R * 2 + 1
    s = pygame.Surface((n, n), pygame.SRCALPHA)
    c = R
    out = (*_darken(col, 0.35), 255)
    mid = (*col, 255)
    hi = (*_lighten(col, 0.6), 255)
    white = (255, 255, 250, 255)
    # lunghezze dei raggi per fotogramma: (dritti, diagonali, buco centrale)
    ray, dia, hole = [(R - 3, R - 5, 0), (R, R - 3, 0), (R, R - 2, R - 4), (R, R - 2, R - 2)][frame]

    def px(x, y, color):
        if 0 <= x < n and 0 <= y < n:
            s.set_at((x, y), color)

    for dx, dy, ln in ((1, 0, ray), (-1, 0, ray), (0, 1, ray), (0, -1, ray),
                       (1, 1, dia), (-1, -1, dia), (1, -1, dia), (-1, 1, dia)):
        for i in range(hole, ln + 1):
            x, y = c + dx * i, c + dy * i
            tip = i >= ln - 1
            px(x, y, hi if not tip else mid)
            # contorno scuro ai lati del raggio (leggibile su erba e sprite chiari)
            if dx == 0:
                px(x - 1, y, out); px(x + 1, y, out)
            elif dy == 0:
                px(x, y - 1, out); px(x, y + 1, out)
        px(c + dx * (ln + 1), c + dy * (ln + 1), out)
    if frame <= 1:   # nucleo
        rr = 2 if frame == 0 else 3
        pygame.draw.circle(s, out, (c, c), rr + 1)
        pygame.draw.circle(s, white, (c, c), rr)
    if frame == 3:   # svanisce: dimezza l'alfa
        s.fill((255, 255, 255, 120), None, pygame.BLEND_RGBA_MULT)
    _spark_cache[key] = s
    return s


def swipe_sprite(col, d8: int, frame: int) -> pygame.Surface:
    """Mezzaluna del fendente rivolta verso la direzione d8 (0 = destra, senso orario)."""
    key = (col, d8, frame)
    s = _swipe_cache.get(key)
    if s is not None:
        return s
    R = 14
    n = R * 2 + 3
    s = pygame.Surface((n, n), pygame.SRCALPHA)
    c = n // 2
    base = d8 * math.pi / 4
    sweep = (0.55, 1.0, 1.0)[frame] * math.radians(140)
    thick = (2.6, 3.6, 1.8)[frame]
    out = (*_darken(col, 0.3), 255)
    body = (*_lighten(col, 0.35), 255)
    edge = (255, 255, 245, 255)
    a0 = base - math.radians(70)
    for y in range(n):
        for x in range(n):
            dx, dy = x - c, y - c
            r = math.hypot(dx, dy)
            ang = (math.atan2(dy, dx) - a0) % math.tau
            if ang > sweep:
                continue
            # spessore che si assottiglia ai due capi (mezzaluna)
            k = math.sin(math.pi * ang / max(1e-3, sweep))
            w = thick * (0.35 + 0.65 * k)
            if R - w - 1 <= r <= R + 0.5:
                if r > R - 0.7:
                    s.set_at((x, y), edge)
                elif r >= R - w:
                    s.set_at((x, y), body)
                else:
                    s.set_at((x, y), out)
    if frame == 2:
        s.fill((255, 255, 255, 150), None, pygame.BLEND_RGBA_MULT)
    _swipe_cache[key] = s
    return s


class HitFx:
    """Colpi vivi: [tgt, x, y, eta, colore, corpo_a_corpo, direzione8]."""

    def __init__(self):
        self.hits: list[list] = []

    def add(self, tgt, c, col, melee: bool, ang: float | None) -> None:
        if len(self.hits) >= MAX_HITS:
            self.hits.pop(0)
        d8 = int(round(ang / (math.pi / 4))) % 8 if ang is not None else 0
        self.hits.append([tgt, c[0], c[1], 0.0, col, melee, d8])

    def update(self, dt: float) -> None:
        if self.hits:
            for h in self.hits:
                h[3] += dt
            self.hits = [h for h in self.hits if h[3] < SPARK_T]

    def draw(self, surface, camera, ts: int, pos_of=None) -> None:
        for h in self.hits:
            tgt, x, y, age, col, melee, d8 = h
            if pos_of is not None and tgt is not None:
                p = pos_of(tgt)
                if p is not None:
                    h[1], h[2] = x, y = p
            sx, sy = camera.world_to_screen(x * ts, (y - CHEST) * ts)
            sp = spark_sprite(col, min(3, int(age / SPARK_T * 4)), not melee)
            surface.blit(sp, (sx - sp.get_width() // 2, sy - sp.get_height() // 2))
            if melee and age < SWIPE_T:
                # mezzaluna SOPRA la scintilla, col centro arretrato verso
                # l'attaccante: l'arco taglia il corpo del bersaglio
                sw = swipe_sprite(col, d8, min(2, int(age / SWIPE_T * 3)))
                ox = int(round(math.cos(d8 * math.pi / 4) * 11))
                oy = int(round(math.sin(d8 * math.pi / 4) * 11))
                surface.blit(sw, (sx - ox - sw.get_width() // 2, sy - oy - sw.get_height() // 2))
