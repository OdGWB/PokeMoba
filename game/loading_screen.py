"""Schermata di caricamento: paesaggio a tutto schermo + indicatore rotante al centro.

Si disegna a piena risoluzione (draw_fullres). Lo sfondo e' scalato "cover" una
volta per dimensione finestra (cache); a ogni frame solo blit + lo spinner.
"""
from __future__ import annotations

import math
from pathlib import Path

import pygame

_BG_PATH = Path(__file__).resolve().parents[1] / "assets" / "ui" / "loading_bg.jpg"
GOLD = (235, 210, 90)

_src = None
_cache: dict = {}
_fonts: dict = {}


def _background(W: int, H: int):
    global _src
    key = (W, H)
    if key in _cache:
        return _cache[key]
    if _src is None:
        try:
            _src = pygame.image.load(str(_BG_PATH)).convert()
        except (pygame.error, FileNotFoundError):
            _src = False
    if _src is False:
        surf = None
    else:
        sw, sh = _src.get_size()
        k = max(W / sw, H / sh)
        big = pygame.transform.scale(_src, (int(sw * k) + 1, int(sh * k) + 1))
        surf = pygame.Surface((W, H)).convert()
        surf.blit(big, ((W - big.get_width()) // 2, (H - big.get_height()) // 2))
        veil = pygame.Surface((W, H))
        veil.fill((8, 16, 12))
        veil.set_alpha(70)                  # velo scuro: spinner e testo leggibili
        surf.blit(veil, (0, 0))
    for k in [k for k in _cache if k[0] != "disc"]:
        del _cache[k]
    _cache[key] = surf
    return surf


def _disc(r: int):
    d = _cache.get(("disc", r))
    if d is None:
        d = pygame.Surface((2 * r, 2 * r), pygame.SRCALPHA)
        pygame.draw.circle(d, (8, 16, 12, 150), (r, r), r)
        _cache[("disc", r)] = d
    return d


def draw(surface, t: float, label: str = "Caricamento...") -> None:
    W, H = surface.get_size()
    bg = _background(W, H)
    if bg is None:
        surface.fill((14, 20, 17))
    else:
        surface.blit(bg, (0, 0))
    cx, cy = W // 2, H // 2
    R = max(24, H // 12)
    disc = _disc(int(R * 1.55))
    surface.blit(disc, (cx - disc.get_width() // 2, cy - disc.get_height() // 2))
    # Spinner: 12 tacche, la "testa" gira e le altre sfumano in coda.
    n = 12
    head = int(t * 12) % n
    for i in range(n):
        age = (head - i) % n
        a = 1.0 - age / n
        col = tuple(int(c * (0.25 + 0.75 * a)) for c in GOLD)
        ang = -math.pi / 2 + i * 2 * math.pi / n
        p0 = (cx + math.cos(ang) * R * 0.62, cy + math.sin(ang) * R * 0.62)
        p1 = (cx + math.cos(ang) * R, cy + math.sin(ang) * R)
        w = max(3, R // 8)
        pygame.draw.line(surface, (10, 14, 12), p0, p1, w + 3)
        pygame.draw.line(surface, col, p0, p1, w)
    size = max(18, H // 32)
    f = _fonts.get(size)
    if f is None:
        f = _fonts[size] = pygame.font.SysFont("consolas", size, bold=True)
    txt = f.render(label, True, (240, 236, 210))
    sh = f.render(label, True, (10, 14, 12))
    x, y = cx - txt.get_width() // 2, cy + R + max(16, H // 30)
    surface.blit(sh, (x + 2, y + 2))
    surface.blit(txt, (x, y))
