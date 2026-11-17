"""Stile comune dei menu (redesign): colori, font, sfondi e piccoli widget.

Solo disegno: nessuna logica di gioco. I colori base restano quelli storici
(BG, PANEL, GOLD...) così le schermate non ancora rifatte restano coerenti.
Font dei titoli: assets/ui/fonts/PixelifySans.ttf se presente (Google Fonts,
licenza OFL), altrimenti Consolas grassetto.
"""
from __future__ import annotations

from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parents[1]

BG = (14, 20, 17)
PANEL = (24, 34, 29)
PANEL_HI = (38, 56, 44)
BORDER = (60, 84, 66)
GOLD = (235, 210, 90)
TEXT = (230, 232, 225)
DIM = (150, 160, 150)

# Nuovi toni (redesign): più morbidi, meno bordi.
CARD = (21, 30, 25)          # carta non selezionata
CARD_LINE = (31, 43, 36)     # bordo leggero delle carte
SEL = (34, 49, 40)           # carta selezionata
LINE = (38, 52, 43)          # divisori, bordi dei pulsanti fantasma
SOFT = (200, 204, 196)       # testo secondario chiaro
FAINT = (111, 122, 112)      # testo terziario
GOLD_SHADOW = (58, 44, 8)
GREEN = (62, 128, 73)        # pulsante principale
GREEN_HI = (71, 144, 79)
ON_GREEN = (242, 245, 238)
BLUE = (111, 163, 242)
RED = (238, 122, 113)

_fonts: dict = {}
_images: dict = {}
_cover_cache: dict = {}


def font(size, bold=False):
    key = ("mono", size, bold)
    if key not in _fonts:
        _fonts[key] = pygame.font.SysFont("consolas", size, bold=bold)
    return _fonts[key]


def title_font(size):
    """Font pixel per i titoli (ripiega su Consolas grassetto)."""
    key = ("title", size)
    if key not in _fonts:
        path = ROOT / "assets" / "ui" / "fonts" / "PixelifySans.ttf"
        f = None
        if path.is_file():
            try:
                f = pygame.font.Font(str(path), size)
            except (OSError, pygame.error):
                f = None
        _fonts[key] = f or pygame.font.SysFont("consolas", size, bold=True)
    return _fonts[key]


def alpha_rect(surface, color, rect, radius=0, width=0):
    """Rettangolo (anche con alpha: color a 4 valori) arrotondato."""
    rect = pygame.Rect(rect)
    if len(color) == 4 and color[3] < 255:
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, color, s.get_rect(), width, border_radius=radius)
        surface.blit(s, rect.topleft)
    else:
        pygame.draw.rect(surface, color[:3], rect, width, border_radius=radius)


def title(surface, text, x, y, size, center=False, shadow=3):
    """Titolo oro con l'ombra piena sotto (stile pixel)."""
    f = title_font(size)
    sh = f.render(text, True, GOLD_SHADOW)
    tx = f.render(text, True, GOLD)
    if center:
        x -= tx.get_width() // 2
    surface.blit(sh, (x, y + shadow))
    surface.blit(tx, (x, y))
    return pygame.Rect(x, y, tx.get_width(), tx.get_height() + shadow)


def keycap(surface, label, x, y, size=11, h=22, fill=(24, 34, 29)):
    """Tasto della tastiera disegnato: ritorna la larghezza."""
    f = font(size)
    t = f.render(label, True, DIM)
    w = max(h, t.get_width() + 12)
    r = pygame.Rect(x, y, w, h)
    pygame.draw.rect(surface, fill, r, border_radius=5)
    pygame.draw.rect(surface, BORDER, r, 1, border_radius=5)
    pygame.draw.line(surface, BORDER, (r.x + 3, r.bottom - 1), (r.right - 4, r.bottom - 1))
    surface.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2 - 1))
    return w


def hints(surface, items, x, y, center=False, W=None):
    """Riga di aiuti: [(tasto, testo), ...]."""
    f = font(12)
    parts = [(k, f.render(t, True, DIM)) for k, t in items]
    widths = [max(22, font(11).size(k)[0] + 12) + 8 + t.get_width() for k, t in parts]
    total = sum(widths) + 22 * (len(parts) - 1)
    if center and W:
        x = W // 2 - total // 2
    for (k, t), w in zip(parts, widths):
        kw = keycap(surface, k, x, y)
        surface.blit(t, (x + kw + 8, y + 11 - t.get_height() // 2))
        x += w + 22


def back_button(surface, label, x, y, hover=False):
    """Pulsante "← Indietro  [Esc]" in alto a sinistra: ritorna il rect."""
    f = font(13)
    t = f.render("← " + label, True, TEXT if hover else DIM)
    w = 12 + t.get_width() + 10 + 32 + 8
    r = pygame.Rect(x, y, w, 34)
    pygame.draw.rect(surface, LINE if hover else CARD_LINE, r, 1, border_radius=8)
    surface.blit(t, (r.x + 12, r.centery - t.get_height() // 2))
    keycap(surface, "Esc", r.x + 12 + t.get_width() + 10, r.y + 7, size=10, h=20, fill=BG)
    return r


def primary_button(surface, rect, label, key=None, hover=False, size=17):
    """Pulsante verde principale (Gioca, Conferma...)."""
    r = pygame.Rect(rect)
    pygame.draw.rect(surface, GREEN_HI if hover else GREEN, r, border_radius=10)
    alpha_rect(surface, (0, 0, 0, 60), (r.x, r.bottom - 3, r.w, 3), radius=0)
    t = font(size, bold=True).render(label, True, ON_GREEN)
    kw = 0
    k = None
    if key:
        k = font(10).render(key, True, ON_GREEN)
        kw = k.get_width() + 12 + 12
    x = r.centerx - (t.get_width() + kw) // 2
    surface.blit(t, (x, r.centery - t.get_height() // 2 - 1))
    if k is not None:
        kr = pygame.Rect(x + t.get_width() + 12, r.centery - 10, k.get_width() + 12, 20)
        alpha_rect(surface, (0, 0, 0, 56), kr, radius=4)
        surface.blit(k, (kr.x + 6, kr.centery - k.get_height() // 2))
    return r


def top_glow(surface, W, H):
    """Leggera luce verde dall'alto (sfondo delle schermate interne)."""
    key = ("glow", W, H)
    if key not in _cover_cache:
        h = int(H * 0.4)
        s = pygame.Surface((W, h), pygame.SRCALPHA)
        for i in range(h):
            a = int(56 * (1 - i / h) ** 1.6)
            pygame.draw.line(s, (60, 90, 60, a), (0, i), (W, i))
        _cover_cache[key] = s
    surface.blit(_cover_cache[key], (0, 0))


def image(rel):
    if rel not in _images:
        path = ROOT / rel
        img = None
        if path.is_file():
            try:
                img = pygame.image.load(str(path)).convert()
            except pygame.error:
                img = None
        _images[rel] = img
    return _images[rel]


def cover(surface, rel, W, H, fx=0.5, fy=0.5):
    """Immagine a tutto schermo (come CSS background-size: cover).
    fx/fy = punto dell'immagine da tenere visibile (0..1). False se manca."""
    key = ("cover", rel, W, H, fx, fy)
    if key not in _cover_cache:
        img = image(rel)
        if img is None:
            return False
        iw, ih = img.get_size()
        k = max(W / iw, H / ih)
        sw, sh = int(iw * k + 0.5), int(ih * k + 0.5)
        big = pygame.transform.smoothscale(img, (sw, sh))
        ox = int((sw - W) * fx)
        oy = int((sh - H) * fy)
        _cover_cache[key] = big.subsurface(pygame.Rect(ox, oy, W, H)).copy()
    surface.blit(_cover_cache[key], (0, 0))
    return True


def menu_shade(surface, W, H):
    """Velo scuro da sinistra (dove sta il menu) + sfumatura in basso."""
    key = ("shade", W, H)
    if key not in _cover_cache:
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        stops = [(0.0, 242), (0.28, 219), (0.52, 90), (0.75, 0), (1.0, 0)]
        for x in range(W):
            p = x / max(1, W - 1)
            for (p0, a0), (p1, a1) in zip(stops, stops[1:]):
                if p0 <= p <= p1:
                    a = a0 + (a1 - a0) * (p - p0) / (p1 - p0)
                    break
            pygame.draw.line(s, (*BG, int(a)), (x, 0), (x, H))
        bh = int(H * 0.22)
        b = pygame.Surface((W, bh), pygame.SRCALPHA)
        for i in range(bh):
            pygame.draw.line(b, (*BG, int(217 * (i / bh))), (0, i), (W, i))
        s.blit(b, (0, H - bh))
        _cover_cache[key] = s
    surface.blit(_cover_cache[key], (0, 0))


def profile_chip(surface, app, W, y=28, right=40, sub="modifica profilo"):
    """In alto a destra: nickname + immagine profilo. Ritorna il rect."""
    from . import avatars as A
    prof = getattr(app, "profile", None) or {}
    nm = font(14, bold=True).render(prof.get("name", "?"), True, TEXT)
    st = font(11).render(sub, True, DIM) if sub else None
    tw = max(nm.get_width(), st.get_width() if st else 0)
    side = 40
    r = pygame.Rect(W - right - (16 + tw + 12 + side + 6), y, 16 + tw + 12 + side + 6, side + 12)
    alpha_rect(surface, (*BG, 184), r, radius=10)
    pygame.draw.rect(surface, CARD_LINE, r, 1, border_radius=10)
    ax = r.right - 6 - side
    if st:
        surface.blit(nm, (ax - 12 - nm.get_width(), r.centery - nm.get_height() - 1))
        surface.blit(st, (ax - 12 - st.get_width(), r.centery + 1))
    else:
        surface.blit(nm, (ax - 12 - nm.get_width(), r.centery - nm.get_height() // 2))
    A.draw_avatar(surface, prof.get("avatar", 0), (ax, r.y + 6, side, side), GOLD)
    return r


def menu_backdrop(surface, rel, W, H, fx=0.5, fy=0.5):
    """Sfondo del menu (cover + menu_shade) fuso UNA volta in una Surface opaca:
    a ogni frame un solo blit pieno invece di immagine + velo SRCALPHA.
    False se l'immagine manca."""
    key = ("backdrop", rel, W, H, fx, fy)
    if key not in _cover_cache:
        s = pygame.Surface((W, H)).convert()
        s.fill(BG)
        if not cover(s, rel, W, H, fx, fy):
            return False
        menu_shade(s, W, H)
        _cover_cache[key] = s
        # i due pezzi non servono piu': solo la versione fusa resta in memoria
        _cover_cache.pop(("cover", rel, W, H, fx, fy), None)
        _cover_cache.pop(("shade", W, H), None)
    surface.blit(_cover_cache[key], (0, 0))
    return True
