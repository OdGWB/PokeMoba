"""Richiamo in base: effetto sul Pokémon che canalizza (visibile a tutti).

Sotto lo sprite: anello azzurro schiacciato ai piedi che si CHIUDE verso il
corpo con l'avanzare del richiamo + colonna di luce traslucida che sale.
Sopra lo sprite: scintille pixel art che risalgono.
Anelli e colonna sono sprite in cache (a frame solo blit); le scintille sono
pochi fill 2x2 con posizioni ricavate dal tempo (niente stato).
Offline e online: serve `recalling` (UNIT_FLAGS in rete) e `recall_until`
(passa da solo come timer).
"""
import math

import pygame

import config

RING = (120, 200, 255)
RING_HI = (225, 245, 255)
COLUMN = (110, 185, 255)
SPARK = (200, 235, 255)
SPARK_HI = (255, 255, 255)

_ring_cache = {}
_col_cache = {}


def active(u, now) -> bool:
    return bool(getattr(u, "recalling", False)) and getattr(u, "recall_until", -1.0) > now


def _progress(u, now) -> float:
    left = getattr(u, "recall_until", now) - now
    return max(0.0, min(1.0, 1.0 - left / config.RECALL_TIME))


def _ring(rx):
    """Ellisse a 2 px: contorno azzurro con il lato alto-sinistro più chiaro."""
    spr = _ring_cache.get(rx)
    if spr is None:
        ry = max(2, rx // 2)
        spr = pygame.Surface((rx * 2 + 2, ry * 2 + 2), pygame.SRCALPHA)
        rect = pygame.Rect(1, 1, rx * 2, ry * 2)
        pygame.draw.ellipse(spr, (*RING, 70), rect)
        pygame.draw.ellipse(spr, (0, 0, 0, 0), rect.inflate(-4, -4))
        pygame.draw.ellipse(spr, (*RING, 230), rect, 2)
        pygame.draw.arc(spr, (*RING_HI, 255), rect, math.radians(100), math.radians(200), 1)
        _ring_cache[rx] = spr
    return spr


def _column(w, h):
    """Colonna di luce: alfa che cala verso l'alto, bordi più tenui (a bande)."""
    key = (w, h)
    spr = _col_cache.get(key)
    if spr is None:
        spr = pygame.Surface((w, h), pygame.SRCALPHA)
        bands = 6
        for i in range(bands):   # dal basso (forte) all'alto (tenue), a gradini
            y0 = h - (i + 1) * h // bands
            y1 = h - i * h // bands
            a = int(130 * (1 - i / bands))
            spr.fill((*COLUMN, a // 2), (0, y0, w, y1 - y0))
            spr.fill((*COLUMN, a), (w // 4, y0, w - 2 * (w // 4), y1 - y0))
        _col_cache[key] = spr
    return spr


def draw_under(surface, u, gx, gy, now, ts):
    if not active(u, now):
        return
    p = _progress(u, now)
    base = int(u.radius * ts) + 3
    rx = int(base + (1.0 - p) * ts * 0.9)   # si chiude verso il corpo
    rx -= rx % 2
    spr = _ring(max(4, rx))
    surface.blit(spr, (gx - spr.get_width() // 2, gy - spr.get_height() // 2))
    # colonna che si alza con la carica
    w = max(6, int(u.radius * ts * 1.4)) & ~1
    h = max(8, int(ts * (0.6 + 1.4 * p))) & ~3
    col = _column(w, h)
    surface.blit(col, (gx - w // 2, gy - h + 2))


def draw_over(surface, u, gx, gy, now, ts):
    if not active(u, now):
        return
    p = _progress(u, now)
    half = int(u.radius * ts) + 2
    rise = ts * 1.6
    n = 7 + int(6 * p)
    seed = (u.id * 37) % 97
    for i in range(n):
        ph = (now * 0.9 + i / n + seed * 0.013) % 1.0
        dx = int(((i * 53 + seed * 7) % (2 * half + 1)) - half
                 + math.sin(now * 3 + i) * 1.5)
        y = int(gy - ph * rise)
        c = SPARK_HI if ph < 0.35 else SPARK
        sz = 2 if ph < 0.7 else 1
        surface.fill(c, (gx + dx, y, sz, sz))
