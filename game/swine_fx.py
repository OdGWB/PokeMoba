"""Grafica della linea Swinub > Piloswine > Mamoswine: effetti istantanei
(handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (cono di neve, roccia in volo a parabola, roccia che
cade, raggiera di cristalli, frecce che salgono), disegni persistenti letti
dallo stato del Match a ogni frame (impronte di Fiuto, Scia Ghiacciata,
blocco di Era Glaciale in volo, bufera), gli accumuli di Gelo e lo scudo di
Grassospesso sulla barra della vita, le rocce di Forzantica attorno a
Mamoswine, l'icona della passiva e il mirino.

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

from .sneasel_fx import draw_flake

ICE = (150, 220, 255)
ICE_HI = (240, 252, 255)
ICE_DK = (36, 82, 150)
ICE_MID = (104, 168, 228)
SNOW = (232, 242, 250)
WHITE = (255, 255, 255)
ROCK = (150, 124, 92)          # Roccia (Forzantica)
ROCK_HI = (214, 192, 150)
ROCK_DK = (64, 50, 36)
DUST = (176, 156, 120)
FUR = (128, 92, 64)            # pelo (icona della passiva)
FUR_DK = (62, 42, 28)
TRACK = (190, 120, 255)        # impronte del Fiuto (viola tenue: si legge nella nebbia)
TRACK_DK = (40, 18, 70)
FAT = (226, 238, 248)          # scudo di Grassospesso

SWINE_DEX = (220, 221, 473)


def _al(f, k=2.0):
    return int(255 * max(0.0, min(1.0, f * k)))


def is_swine(u) -> bool:
    return getattr(u, "dex", 0) in SWINE_DEX


# --- piccoli disegni ------------------------------------------------------------

def _rock_poly(cx, cy, r, seed, n=7):
    rnd = random.Random(seed)
    return [(cx + math.cos(k / n * math.tau + rnd.uniform(-0.25, 0.25)) * r * rnd.uniform(0.7, 1.05),
             cy + math.sin(k / n * math.tau + rnd.uniform(-0.25, 0.25)) * r * rnd.uniform(0.6, 0.9))
            for k in range(n)]


def draw_rock(surface, cx, cy, r, seed, alpha=255, cols=(ROCK_DK, ROCK, ROCK_HI)):
    """Sasso spigoloso: contorno scuro, corpo, faccia in luce in alto a sinistra."""
    r = max(2.0, r)
    pts = _rock_poly(cx, cy, r, seed)
    pygame.draw.polygon(surface, (*cols[0], alpha), [(x, y) for x, y in pts], 0)
    inner = [(cx + (x - cx) * 0.78, cy + (y - cy) * 0.78) for x, y in pts]
    pygame.draw.polygon(surface, (*cols[1], alpha), inner, 0)
    hi = [(cx + (x - cx) * 0.45 - r * 0.22, cy + (y - cy) * 0.45 - r * 0.2) for x, y in pts[3:7]]
    if len(hi) >= 3:
        pygame.draw.polygon(surface, (*cols[2], alpha), hi, 0)


def draw_ice_block(surface, cx, cy, s, spin=0.0, alpha=255):
    """Blocco di ghiaccio 2.5D (cima chiara, faccia frontale, lato in ombra) con
    riflesso e crepe. `s` = mezzo lato in pixel."""
    s = max(3, int(s))
    k = int(s * 0.55)                                 # profondità della cima
    top = [(cx - s, cy - s), (cx + s, cy - s), (cx + s - k // 2, cy - s - k),
           (cx - s - k // 2, cy - s - k)]
    front = pygame.Rect(cx - s, cy - s, 2 * s, 2 * s)
    side = [(cx + s, cy - s), (cx + s - k // 2, cy - s - k), (cx + s - k // 2, cy + s - k),
            (cx + s, cy + s)]
    pygame.draw.polygon(surface, (*ICE_DK, alpha), [(x - 1, y - 1) for x, y in top], 0)
    pygame.draw.rect(surface, (*ICE_DK, alpha), front.inflate(2, 2))
    pygame.draw.rect(surface, (*ICE_MID, alpha), front)
    pygame.draw.polygon(surface, (*ICE_HI, alpha), top, 0)
    pygame.draw.polygon(surface, (*ICE_DK, alpha), top, 1)
    # luce in alto a sinistra sulla faccia frontale
    pygame.draw.polygon(surface, (*ICE, alpha), [(cx - s + 1, cy - s + 1), (cx + s // 3, cy - s + 1),
                                                 (cx - s + 1, cy + s // 3)], 0)
    pygame.draw.line(surface, (*WHITE, alpha), (cx - s + 2, cy - s + 2), (cx - s + 2, cy), 1)
    pygame.draw.line(surface, (*WHITE, alpha), (cx - s + 2, cy - s + 2), (cx - s // 4, cy - s + 2), 1)
    # crepa
    pygame.draw.lines(surface, (*ICE_DK, alpha), False,
                      [(cx + s // 3, cy - s + 1), (cx + s // 6, cy), (cx + s // 2, cy + s // 3),
                       (cx + s // 3, cy + s - 1)], 1)
    pygame.draw.rect(surface, (*ICE_DK, alpha), front, 1)


# --- forme per FXSystem._draw_shapes -------------------------------------------

SHAPES = ("snowcone", "rockarc", "rockfall", "iceburst", "uparrows", "icefangs")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "snowcone":
        # Valanga / Bora: getto di neve che si apre nel cono (sbuffi + fiocchi);
        # Bora aggiunge strisce di vento bianche.
        ox, oy = S(*s["o"])
        ang, half, rng = s["ang"], s["half"], s["rng"] * ts
        rnd = random.Random(s.get("seed", 3))
        grow = min(1.0, t / 0.35)
        al = _al(f, 2.2)
        for i in range(s.get("n", 26)):
            u = rnd.uniform(0.15, 1.0) * grow
            an = ang + rnd.uniform(-half, half) * (0.5 + 0.5 * u)
            d = u * rng
            x, y = ox + math.cos(an) * d, oy + math.sin(an) * d - 0.3 * ts
            r = max(1, int((0.06 + 0.12 * u) * ts * rnd.uniform(0.7, 1.2)))
            col = SNOW if rnd.random() < 0.7 else ICE
            pygame.draw.circle(overlay, (*ICE_DK, al // 3), (int(x) + 1, int(y) + 1), r)
            pygame.draw.circle(overlay, (*col, al), (int(x), int(y)), r)
            if r >= 3:
                pygame.draw.circle(overlay, (*WHITE, al), (int(x) - 1, int(y) - 1), max(1, r // 3))
        if s.get("wind"):
            # tre raffiche corte che scorrono in avanti (non fili tesi da un capo all'altro)
            for i in range(3):
                an = ang + (i - 1) * half * 0.6
                head = rng * (0.35 + 0.65 * min(1.0, t / 0.5)) - i * 0.08 * rng
                d0, d1 = max(0.0, head - rng * 0.35), head
                pts = []
                for k in range(6):
                    u = k / 5
                    dd = d0 + (d1 - d0) * u
                    wob = math.sin(u * 4.0 + i * 2.0) * 0.07 * ts
                    pts.append((ox + math.cos(an) * dd - math.sin(an) * wob,
                                oy + math.sin(an) * dd + math.cos(an) * wob - 0.3 * ts))
                pygame.draw.lines(overlay, (*ICE, al // 3), False, pts, 3)
                pygame.draw.lines(overlay, (*WHITE, int(al * 0.8)), False, pts, 1)
    elif kind == "rockarc":
        # Forzantica: sasso che vola a parabola dal lanciatore all'area.
        u = min(1.0, t * s.get("speed", 1.6))
        ax, ay = s["a"]
        bx, by = s["b"]
        wx, wy = ax + (bx - ax) * u, ay + (by - ay) * u
        h = 4.0 * u * (1.0 - u) * s.get("h", 1.6)
        px, py = S(wx, wy - 0.3 - h)
        gx, gy = S(wx, wy)
        r = s.get("sz", 0.18) * ts
        al = 255 if u < 1.0 else _al(f, 2.5)
        sh = max(2, int(r * (1.0 - 0.3 * min(1.0, h))))
        pygame.draw.ellipse(overlay, (0, 0, 0, 70), pygame.Rect(gx - sh, gy - sh // 3, sh * 2, max(2, sh * 2 // 3)))
        draw_rock(overlay, px, py, r, s.get("seed", 1), al, s.get("cols", (ROCK_DK, ROCK, ROCK_HI)))
    elif kind == "rockfall":
        # Frana: sasso che cade dall'alto sul punto.
        u = min(1.0, t * s.get("speed", 2.2))
        cx, cy = s["c"]
        h = (1.0 - u) * s.get("h", 4.0)
        px, py = S(cx, cy - 0.3 - h)
        gx, gy = S(cx, cy)
        r = s.get("sz", 0.24) * ts
        sh = max(2, int(r * (0.5 + 0.5 * u)))
        pygame.draw.ellipse(overlay, (0, 0, 0, int(40 + 50 * u)),
                            pygame.Rect(gx - sh, gy - sh // 3, sh * 2, max(2, sh * 2 // 3)))
        if h > 0.4:   # scia di caduta
            pygame.draw.line(overlay, (*DUST, 90), (px, py - r * 2.2), (px, py - r), max(1, int(r // 2)))
        draw_rock(overlay, px, py, r, s.get("seed", 1), 255 if u < 1.0 else _al(f, 2.5))
    elif kind == "iceburst":
        # Raggiera di cristalli di ghiaccio che spuntano e si frantumano.
        cx, cy = S(*s["c"])
        cy -= int(s.get("lift", 0.3) * ts)
        rnd = random.Random(s.get("seed", 5))
        n = s.get("n", 8)
        R = s.get("r", 0.8) * ts * min(1.0, t / 0.18 + 0.2)
        al = _al(f, 2.0)
        for i in range(n):
            an = i / n * math.tau + rnd.uniform(-0.2, 0.2)
            L = R * rnd.uniform(0.6, 1.0)
            w = max(2, L * 0.22)
            tip = (cx + math.cos(an) * L, cy + math.sin(an) * L * 0.6)
            b1 = (cx + math.cos(an + 1.57) * w * 0.5, cy + math.sin(an + 1.57) * w * 0.3)
            b2 = (cx + math.cos(an - 1.57) * w * 0.5, cy + math.sin(an - 1.57) * w * 0.3)
            pygame.draw.polygon(overlay, (*ICE_DK, al), [b1, tip, b2], 0)
            mid = ((b1[0] + tip[0]) / 2, (b1[1] + tip[1]) / 2)
            pygame.draw.polygon(overlay, (*ICE, al), [b1, tip, ((b1[0] + b2[0]) / 2, (b1[1] + b2[1]) / 2)], 0)
            pygame.draw.line(overlay, (*ICE_HI, al), b1, mid, 1)
    elif kind == "icefangs":
        # Gelodenti: due zanne di ghiaccio dall'alto e due dal basso che si
        # chiudono sul bersaglio (azzurre con contorno scuro: si vedono anche su
        # uno sprite chiaro).
        cx, cy = S(*s["c"])
        close = min(1.0, t / 0.3)
        close = close * close * (3 - 2 * close)
        L = s.get("len", 0.42) * ts
        gap = (1.0 - close) * 0.45 * ts
        al = 255 if f > 0.35 else int(255 * f / 0.35)
        w = max(3, int(0.12 * ts))
        for row in (-1, 1):
            for dx in (-0.2, 0.2):
                x = cx + dx * ts + (0.05 * ts if row > 0 else 0)
                root = cy + row * (gap + L)
                tip = cy + row * gap
                tri = [(x - w, root), (x + w, root), (x, tip)]
                pygame.draw.polygon(overlay, (*ICE_DK, al), [(x - w - 1, root), (x + w + 1, root),
                                                             (x, tip + row)], 0)
                pygame.draw.polygon(overlay, (*ICE, al), tri, 0)
                pygame.draw.line(overlay, (*WHITE, al), (x - w + 1, root), (x - 1, tip - row * 2), 1)
        if close >= 1.0 and f > 0.35:
            pygame.draw.circle(overlay, (*WHITE, al), (int(cx), int(cy)), max(2, int(0.1 * ts)))
    elif kind == "uparrows":
        # Forzantica: tre frecce (chevron) che salgono attorno al Pokémon.
        cx, cy = S(*s["c"])
        al = _al(f, 2.0)
        col = s.get("col", ROCK_HI)
        for i, dx in enumerate((-0.45, 0.0, 0.45)):
            ph = (t * 1.4 + i * 0.3) % 1.0
            x = cx + dx * ts
            y = cy - (0.3 + ph * 1.1) * ts
            w = max(3, int(0.14 * ts))
            pts = [(x - w, y + w), (x, y), (x + w, y + w)]
            pygame.draw.lines(overlay, (*ROCK_DK, al), False, [(px, py + 1) for px, py in pts], 3)
            pygame.draw.lines(overlay, (*col, al), False, pts, 2)


# --- handler degli eventi (FXSystem._FX_STYLES) --------------------------------


def _ab(e):
    a, b = e.get("a"), e.get("b")
    return (a, b) if a is not None and b is not None else None


def _bits(fx, c, n, cols, speed=2.0, life=(0.2, 0.4), size=1, up=0.0, spread=0.0):
    for _ in range(n):
        an = random.uniform(0, math.tau)
        v = random.uniform(0.4, 1.0) * speed
        x = c[0] + random.uniform(-spread, spread)
        y = c[1] + random.uniform(-spread, spread) * 0.5
        fx._add(x, y, math.cos(an) * v, math.sin(an) * v * 0.5 - up, random.uniform(*life),
                random.choice(cols), size)


def fx_icetrail(fx, e, col):
    """Scia Ghiacciata: scivolata con spruzzi di neve ai lati e cristalli ai capi
    (la corsia di ghiaccio è disegnata a parte, finché dura)."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(2, int(L * 2.5))
    for i in range(n):
        u = i / max(1, n - 1)
        c = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        _bits(fx, c, 2, (SNOW, ICE, ICE_HI), speed=1.6, life=(0.25, 0.5))
    fx._shape(kind="iceburst", c=b, r=0.7, n=7, col=ICE, life=0.35, seed=int(b[0] * 13))
    fx._shape(kind="windline", a=(a[0], a[1] - 0.3), b=(b[0], b[1] - 0.3), col=ICE_HI, w=0.12,
              life=0.25)


def fx_takedown(fx, e, col):
    """Riduttore: carica con polvere e strisce di vento dietro."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="windline", a=(a[0], a[1] - 0.35), b=(b[0], b[1] - 0.35), col=(236, 226, 206),
              w=0.16, life=0.3)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    for i in range(max(2, int(L * 2))):
        u = i / max(1, int(L * 2))
        c = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u + 0.1)
        _bits(fx, c, 2, (DUST, ROCK_HI, (120, 104, 80)), speed=1.0, life=(0.3, 0.55), up=0.4)


def fx_takedownhit(fx, e, col):
    """Riduttore a segno: stella d'urto, anello a terra e sassi."""
    c = e.get("c")
    if c is None:
        return
    top = (c[0], c[1] - 0.35)
    fx._shape(kind="impactstar", c=top, r=0.5, n=7, rot=random.uniform(0, 1),
              cols=((92, 70, 40), (240, 228, 200), WHITE), col=(240, 228, 200), life=0.24)
    fx._shape(kind="groundring", c=c, r0=0.3, r1=1.2, col=DUST, life=0.35, w=0.08)
    d = e.get("dir", (1.0, 0.0))
    for _ in range(5):
        v = (d[0] * random.uniform(0.6, 1.4) + random.uniform(-0.4, 0.4),
             d[1] * random.uniform(0.6, 1.4) + random.uniform(-0.4, 0.4))
        fx._shape(kind="pebble", c=c, v=v, h=0.5, sz=0.06, col=ROCK, life=0.4)


def _cone_args(e):
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return None
    return o, d, float(e.get("range", 2.5)), math.radians(float(e.get("angle", 45))), math.atan2(d[1], d[0])


def fx_powdersnow(fx, e, col):
    """Valanga: getto di neve nel cono + nuvoletta in fondo."""
    ca = _cone_args(e)
    if ca is None:
        return
    o, d, rng, half, ang = ca
    fx._shape(kind="snowcone", o=o, ang=ang, half=half, rng=rng, n=28,
              seed=random.randrange(999), col=SNOW, life=0.45)
    end = (o[0] + d[0] * rng * 0.8, o[1] + d[1] * rng * 0.8)
    _bits(fx, end, 8, (SNOW, ICE_HI, ICE), speed=2.0, life=(0.3, 0.6), spread=0.5)


def fx_bora(fx, e, col):
    """Bora: cono più largo con strisce di vento e fiocchi che restano un po'."""
    ca = _cone_args(e)
    if ca is None:
        return
    o, d, rng, half, ang = ca
    fx._shape(kind="snowcone", o=o, ang=ang, half=half, rng=rng, n=34, wind=True,
              seed=random.randrange(999), col=SNOW, life=0.55)
    for _ in range(6):
        an = ang + random.uniform(-half, half)
        dd = random.uniform(0.5, 1.0) * rng
        c = (o[0] + math.cos(an) * dd, o[1] + math.sin(an) * dd)
        _bits(fx, c, 2, (SNOW, ICE_HI), speed=1.5, life=(0.3, 0.6))


def fx_icefang(fx, e, col):
    """Gelodenti: mascelle di ghiaccio che si chiudono sul bersaglio."""
    c = e.get("c")
    if c is None:
        return
    top = (c[0], c[1] - 0.35)
    if e.get("miss"):
        fx._shape(kind="icefangs", c=top, len=0.32, col=ICE, life=0.3)
        return
    fx._shape(kind="icefangs", c=top, col=ICE, life=0.42)
    fx._shape(kind="iceburst", c=c, r=0.6, n=6, lift=0.35, col=ICE, life=0.3, wait=0.12,
              seed=random.randrange(999))
    _bits(fx, top, 8, (ICE, ICE_HI, WHITE), speed=2.4, life=(0.2, 0.4))


def fx_ancientpower(fx, e, col):
    """Forzantica: rocce lanciate a parabola dal Pokémon nell'area, polvere
    all'arrivo."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.0))
    a = e.get("a") or (c[0] - 2.0, c[1] + 1.0)
    rnd = random.Random()
    n = 6
    for i in range(n):
        an = rnd.uniform(0, math.tau)
        d = math.sqrt(rnd.random()) * r * 0.85
        b = (c[0] + math.cos(an) * d, c[1] + math.sin(an) * d * 0.9)
        fl = 0.32 + rnd.uniform(-0.04, 0.06)       # tempo di volo
        w = i * 0.04
        life = fl / 0.55                             # atterra al 55% della vita, poi svanisce
        fx._shape(kind="rockarc", a=a, b=b, h=1.4 + rnd.uniform(0, 0.6), sz=rnd.uniform(0.13, 0.2),
                  seed=rnd.randrange(999), speed=1.0 / 0.55, col=ROCK, life=life, wait=w)
        _dust_later(fx, b, w + fl, rnd)


def _dust_later(fx, c, wait, rnd):
    """Due sassolini che rimbalzano quando un sasso tocca terra."""
    for _ in range(2):
        fx._shape(kind="pebble", c=c, v=(rnd.uniform(-0.7, 0.7), rnd.uniform(-0.5, 0.2)), h=0.35,
                  sz=0.05, col=ROCK_HI, life=0.3, wait=wait)


def fx_swinerockslide(fx, e, col):
    """Frana: tanti sassi che cadono dall'alto sull'area + crepe e polvere."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 3.0))
    rnd = random.Random()
    for i in range(11):
        an = rnd.uniform(0, math.tau)
        d = math.sqrt(rnd.random()) * r * 0.9
        p = (c[0] + math.cos(an) * d, c[1] + math.sin(an) * d * 0.9)
        w = rnd.uniform(0.0, 0.25)
        fx._shape(kind="rockfall", c=p, h=3.5 + rnd.uniform(0, 1.5), sz=rnd.uniform(0.16, 0.28),
                  seed=rnd.randrange(999), speed=2.6, col=ROCK, life=0.75, wait=w)
        _dust_later(fx, p, w + 0.29, rnd)


def fx_ancientbuff(fx, e, col):
    """Forzantica a segno: frecce color roccia che salgono + scintille."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="uparrows", c=c, col=ROCK_HI, life=0.9)
    _bits(fx, (c[0], c[1] - 0.4), 6, (ROCK_HI, (255, 236, 180)), speed=1.2, up=1.2)


def fx_swinestun(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    _bits(fx, (c[0], c[1] - 0.2), 6, (DUST, ROCK_HI), speed=1.4, up=0.8)


def fx_fatregen(fx, e, col):
    """Grassospesso torna pieno: anello chiaro che si chiude sul Pokémon."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=(c[0], c[1] - 0.4), r0=1.0, r1=0.5, col=FAT, life=0.35, wd=0.05)
    _bits(fx, (c[0], c[1] - 0.4), 5, (FAT, ICE_HI), speed=1.0, up=0.6)


def fx_frostgain(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="flake", c=(c[0], c[1] - 0.9), r=0.14, col=ICE, life=0.4, rise=0.25)


def fx_frostfreeze(fx, e, col):
    """Gelo: il quarto accumulo congela. Raggiera di cristalli + lampo."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="flash", c=(c[0], c[1] - 0.4), r=0.5, col=ICE_HI, life=0.14)
    fx._shape(kind="iceburst", c=c, r=1.0, n=9, col=ICE, life=0.45, seed=random.randrange(999))
    _bits(fx, (c[0], c[1] - 0.4), 10, (ICE, ICE_HI, WHITE), speed=2.6)


def fx_iceagehit(fx, e, col):
    """Era Glaciale a segno: il blocco si frantuma, grande raggiera e schegge."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="flash", c=(c[0], c[1] - 0.5), r=0.4, col=ICE_HI, life=0.14)
    fx._shape(kind="iceburst", c=c, r=1.5, n=12, lift=0.4, col=ICE, life=0.6,
              seed=random.randrange(999))
    fx._shape(kind="ring", c=(c[0], c[1] - 0.2), r0=0.4, r1=2.0, col=ICE, life=0.4, wd=0.06)
    for _ in range(8):
        an = random.uniform(0, math.tau)
        fx._shape(kind="pebble", c=c, v=(math.cos(an) * 1.4, math.sin(an) * 0.9), h=0.8,
                  sz=0.07, col=ICE_HI, life=0.5)


def fx_iceageburst(fx, e, col):
    """Era Glaciale a vuoto: il blocco esplode in neve a fine corsa."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="flash", c=(c[0], c[1] - 0.4), r=0.6, col=SNOW, life=0.16)
    fx._shape(kind="iceburst", c=c, r=1.0, n=9, col=ICE, life=0.45, seed=random.randrange(999))
    _bits(fx, (c[0], c[1] - 0.4), 14, (SNOW, ICE, ICE_HI), speed=3.0, spread=0.3)


STYLES = {
    "icetrail": fx_icetrail, "takedown": fx_takedown, "takedownhit": fx_takedownhit,
    "powdersnow": fx_powdersnow, "bora": fx_bora, "icefang": fx_icefang,
    "ancientpower": fx_ancientpower, "swinerockslide": fx_swinerockslide,
    "ancientbuff": fx_ancientbuff, "swinestun": fx_swinestun, "fatregen": fx_fatregen,
    "frostgain": fx_frostgain, "frostfreeze": fx_frostfreeze, "iceagehit": fx_iceagehit,
    "iceageburst": fx_iceageburst,
}


# --- disegni persistenti (stato del Match) ---------------------------------------

_print_cache: dict = {}


def _print_sprite(big: bool, ang_idx: int):
    """Impronta di zampa (cuscinetto + 3 dita) rivolta lungo la direzione
    (8 angoli in cache). Viola tenue con contorno scuro: si legge anche
    sopra la nebbia."""
    key = (big, ang_idx)
    img = _print_cache.get(key)
    if img is not None:
        return img
    s = 2 if big else 1
    # disegnata rivolta in SU (dita in alto, cuscinetto sotto), poi ruotata
    # a passi di 90° (nitida) o 45° (una sola rotazione, pixel puliti)
    base = pygame.Surface((9, 10), pygame.SRCALPHA)
    pad = [(2, 5), (6, 5), (7, 7), (6, 9), (2, 9), (1, 7)]
    pygame.draw.polygon(base, TRACK_DK, pad)
    pygame.draw.polygon(base, TRACK, [(3, 6), (5, 6), (6, 7), (5, 8), (3, 8), (2, 7)])
    for (x, y) in ((1, 2), (4, 0), (7, 2)):     # tre dita staccate
        pygame.draw.rect(base, TRACK_DK, pygame.Rect(x - 1, y, 3, 3))
        base.set_at((x, y + 1), TRACK)
    if s > 1:
        base = pygame.transform.scale(base, (9 * s, 10 * s))
    # ang_idx: 0 = verso +x (destra); lo sprite guarda in su (-y) => -90°
    img = pygame.transform.rotate(base, -(ang_idx * 45 + 90))
    _print_cache[key] = img
    return img


def draw_tracks(surface, camera, tracks, team, now):
    """Fiuto: impronte dei nemici (solo per la squadra che fiuta), più
    trasparenti man mano che invecchiano; sopra la nebbia di guerra."""
    ts = config.TILE_SIZE
    for tr in tracks:
        if tr.get("viewer") != team:
            continue
        age = now - tr["t"]
        if age < 0 or age >= 8.0:
            continue
        p = tr["pos"]
        dx, dy = tr.get("dir", (1.0, 0.0))
        side = 1 if tr.get("side", 0) else -1
        off = 0.16 * side
        wx, wy = p.x - dy * off, p.y + dx * off
        x, y = camera.world_to_screen(wx * ts, wy * ts)
        idx = int(round(math.degrees(math.atan2(dy, dx)) / 45.0)) % 8
        img = _print_sprite(bool(tr.get("big")), idx)
        al = int(230 * (1.0 - age / 8.0) ** 0.7)
        if age < 0.15:
            al = int(al * age / 0.15)
        im = img.copy()
        im.set_alpha(al)
        surface.blit(im, (x - im.get_width() // 2, y - im.get_height() // 2))


def draw_ice_trail(surface, camera, tr, now):
    """Scia Ghiacciata: corsia di ghiaccio (bordo frastagliato, riflessi,
    cristalli) che si scioglie negli ultimi istanti."""
    ts = config.TILE_SIZE
    a, b = tr["a"], tr["b"]
    left = tr["end"] - now
    fade = max(0.0, min(1.0, left / 0.6)) * max(0.0, min(1.0, (now - tr["start"]) / 0.12))
    if fade <= 0:
        return
    ax, ay = camera.world_to_screen(a.x * ts, a.y * ts)
    bx, by = camera.world_to_screen(b.x * ts, b.y * ts)
    W = int(tr.get("w", 0.7) * ts)
    minx, miny = min(ax, bx) - W - 4, min(ay, by) - W - 4
    g = pygame.Surface((abs(bx - ax) + 2 * W + 8, abs(by - ay) + 2 * W + 8), pygame.SRCALPHA)
    A, B = (ax - minx, ay - miny), (bx - minx, by - miny)
    L = math.hypot(B[0] - A[0], B[1] - A[1]) or 1.0
    ux, uy = (B[0] - A[0]) / L, (B[1] - A[1]) / L
    nx, ny = -uy, ux
    rnd = random.Random(tr.get("seed", 0) * 7 + int(a.x * 3))
    n = max(3, int(L / 5))
    edge1, edge2 = [], []
    for i in range(n + 1):
        u = i / n
        taper = min(1.0, u / 0.12, (1.0 - u) / 0.12 + 0.35)
        w1 = W * taper * rnd.uniform(0.75, 1.0)
        w2 = W * taper * rnd.uniform(0.75, 1.0)
        cx, cy = A[0] + (B[0] - A[0]) * u, A[1] + (B[1] - A[1]) * u
        edge1.append((cx + nx * w1, cy + ny * w1 * 0.75))
        edge2.append((cx - nx * w2, cy - ny * w2 * 0.75))
    poly = edge1 + edge2[::-1]
    pygame.draw.polygon(g, (*ICE_MID, int(120 * fade)), poly, 0)
    pygame.draw.polygon(g, (*ICE_DK, int(170 * fade)), poly, 1)
    # bordo in luce (lato in alto a sinistra) e riflessi diagonali
    side = edge1 if ny < 0 or (ny == 0 and nx < 0) else edge2
    pygame.draw.lines(g, (*ICE_HI, int(200 * fade)), False, side, 1)
    for i in range(max(1, int(L / (0.6 * ts)))):
        u = rnd.uniform(0.1, 0.9)
        cx, cy = A[0] + (B[0] - A[0]) * u, A[1] + (B[1] - A[1]) * u
        k = rnd.uniform(-0.4, 0.4) * W
        x0, y0 = cx + nx * k, cy + ny * k * 0.75
        pygame.draw.line(g, (*WHITE, int(170 * fade)), (x0 - 3, y0 + 2), (x0 + 2, y0 - 3), 1)
    # brillio che scorre
    ph = (now * 0.8 + tr.get("seed", 0) * 0.13) % 1.0
    sx, sy = A[0] + (B[0] - A[0]) * ph, A[1] + (B[1] - A[1]) * ph
    pygame.draw.circle(g, (*WHITE, int(200 * fade)), (int(sx), int(sy)), 1)
    surface.blit(g, (minx, miny))


def draw_glacial_block(surface, camera, o, now):
    """Era Glaciale in volo: grande blocco di ghiaccio sospeso con scia di
    neve e ombra a terra."""
    ts = config.TILE_SIZE
    p = o["pos"]
    d = o["dir"]
    x, y = camera.world_to_screen(p.x * ts, (p.y - 0.75) * ts)
    gx, gy = camera.world_to_screen(p.x * ts, p.y * ts)
    sh = pygame.Surface((int(0.9 * ts), int(0.35 * ts)), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 80), sh.get_rect())
    surface.blit(sh, (gx - sh.get_width() // 2, gy - sh.get_height() // 2))
    # scia: sbuffi di neve dietro
    rnd = random.Random(int(now * 20) + o.get("caster_id", 0))
    for k in range(7):
        back = 0.25 + k * 0.28
        jx = rnd.uniform(-0.18, 0.18)
        jy = rnd.uniform(-0.18, 0.18)
        tx, ty = camera.world_to_screen((p.x - d.x * back + jx) * ts,
                                        (p.y - d.y * back - 0.75 + jy) * ts)
        r = max(1, int((0.16 - k * 0.018) * ts))
        col = SNOW if k % 2 else ICE
        pygame.draw.circle(surface, col, (tx, ty), r)
    draw_ice_block(surface, x, y, int(0.38 * ts), now * 4.0)
    # brina che si stacca
    for _ in range(2):
        an = rnd.uniform(0, math.tau)
        rr = 0.5 * ts
        surface.set_at((int(x + math.cos(an) * rr), int(y + math.sin(an) * rr * 0.6)), ICE_HI)


def draw_ice_storm(surface, camera, z, now):
    """Era Glaciale: bufera di 3 tile (area azzurra con bordo tratteggiato che
    gira, fiocchi che vorticano, strisce di vento)."""
    ts = config.TILE_SIZE
    c = z["c"]
    R = z["radius"] * ts
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    age = now - z["start"]
    left = z["end"] - now
    fade = max(0.0, min(1.0, age / 0.25)) * max(0.0, min(1.0, left / 0.4))
    if fade <= 0:
        return
    w, h = int(R * 2 + 8), int(R + 8)
    g = pygame.Surface((w, h + int(1.2 * ts)), pygame.SRCALPHA)
    ox, oy = w // 2, h // 2 + int(1.2 * ts)
    rect = pygame.Rect(ox - R, oy - R / 2, R * 2, R)
    pygame.draw.ellipse(g, (*ICE_MID, int(55 * fade)), rect)
    pygame.draw.ellipse(g, (*ICE, int(40 * fade)), rect.inflate(-R * 0.5, -R * 0.25))
    # bordo tratteggiato che gira
    n = 28
    rot = now * 0.9
    for i in range(n):
        if i % 2:
            continue
        a0 = rot + i / n * math.tau
        a1 = a0 + math.tau / n
        p0 = (ox + math.cos(a0) * R, oy + math.sin(a0) * R / 2)
        p1 = (ox + math.cos(a1) * R, oy + math.sin(a1) * R / 2)
        pygame.draw.line(g, (*ICE_HI, int(220 * fade)), p0, p1, 2)
    # strisce di vento curve
    for k in range(4):
        a0 = now * 2.2 + k * math.pi / 2
        rr = R * (0.45 + 0.15 * (k % 2))
        pts = [(ox + math.cos(a0 + j * 0.18) * rr, oy + math.sin(a0 + j * 0.18) * rr / 2 - 0.4 * ts)
               for j in range(7)]
        pygame.draw.lines(g, (*WHITE, int(150 * fade)), False, pts, 1)
    # fiocchi che vorticano e cadono in diagonale (deterministici nel tempo)
    for i in range(40):
        rnd = random.Random(i * 7919 + int(z.get("start", 0) * 10))
        r0 = math.sqrt(rnd.random()) * R
        a = rnd.uniform(0, math.tau) + now * (1.6 + rnd.uniform(0, 1.0))
        fall = ((now * rnd.uniform(0.5, 0.9) + rnd.random()) % 1.0)
        x = ox + math.cos(a) * r0
        y = oy + math.sin(a) * r0 / 2 - (1.0 - fall) * 1.1 * ts
        col = WHITE if i % 3 else ICE
        if i % 5 == 0:
            draw_flake(g, int(x), int(y), 2, int(230 * fade), ICE)
        else:
            pygame.draw.rect(g, (*col, int(230 * fade)), pygame.Rect(int(x), int(y), 2, 2))
    surface.blit(g, (cx - ox, cy - oy))


# --- sulle unità ---------------------------------------------------------------

def draw_hp_extras(surface, u, gx, top, w, row=0):
    """Sulla barra della vita: lo scudo di Grassospesso (segmento bianco-
    ghiaccio in coda) e, sotto, gli accumuli di Gelo (fiocchi, visibili a
    tutti). `row` = righe già occupate sotto la barra (vasetti, ping...)."""
    sh = getattr(u, "fat_shield", 0.0)
    mx = max(1.0, getattr(u, "max_hp", 1.0))
    if sh > 0.5:
        x0 = gx - w // 2
        hpw = int(w * max(0.0, u.hp / mx))
        sw = max(1, int(w * sh / mx))
        start = min(hpw, w - sw)
        pygame.draw.rect(surface, FAT, pygame.Rect(x0 + start, top, sw, 3))
        pygame.draw.line(surface, ICE_DK, (x0 + start, top + 3), (x0 + start + sw - 1, top + 3))
    n = int(getattr(u, "frost_stacks", 0))
    if n > 0:
        y = top + 8 + row * 6
        full = n >= 4
        for k in range(4):
            x = gx - 10 + k * 7
            surface.blit(_pip(k < n, full), (x - 3, y - 3))


_pip_cache: dict = {}


def _pip(on: bool, full: bool):
    """Accumulo di Gelo: fiocchetto 7x7 (croce con le punte) con contorno
    scuro; bianco quando sono 4 (pronto a congelare), grigio se vuoto."""
    key = (on, full)
    img = _pip_cache.get(key)
    if img is None:
        img = pygame.Surface((7, 7), pygame.SRCALPHA)
        if not on:   # posto libero: puntino spento
            img.set_at((3, 3), (90, 100, 116))
            _pip_cache[key] = img
            return img
        arms = [(3, 1), (3, 2), (3, 3), (3, 4), (3, 5), (1, 3), (2, 3), (4, 3), (5, 3)]
        out = set()
        for x, y in arms:   # contorno a 4 vicini: resta una croce, non un quadrato
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                out.add((x + dx, y + dy))
        for x, y in out - set(arms):
            img.set_at((x, y), (*ICE_DK, 255))
        for x, y in arms:
            img.set_at((x, y), WHITE if full else ICE)
        img.set_at((3, 3), WHITE)
        _pip_cache[key] = img
    return img


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Forzantica attiva: tre sassi che orbitano attorno al Pokémon (visibile
    a tutti)."""
    if getattr(u, "ancient_until", -1.0) <= now:
        return
    r = int(getattr(u, "radius", 0.5) * ts)
    for k in range(3):
        an = now * 2.4 + k * math.tau / 3
        x = gx + math.cos(an) * (r + 5)
        y = gy - r + math.sin(an) * (r * 0.45 + 2)
        if math.sin(an) < 0:   # dietro: un filo più scuri
            draw_rock(surface, x, y, 4, 11 + k, 210, (ROCK_DK, (110, 90, 66), ROCK))
        else:
            draw_rock(surface, x, y, 4, 11 + k, 255)


# --- interfaccia ---------------------------------------------------------------

def count_frozen_ready(world, p, now, visible=None) -> int:
    """Nemici con 4 accumuli di Gelo pronti a essere congelati."""
    if getattr(p, "passive_id", None) != "gelo":
        return 0
    n = 0
    for e in world.pokemons():
        if (e.team != p.team and e.alive and getattr(e, "frost_stacks", 0) >= 4
                and getattr(e, "frost_until", -1.0) > now
                and getattr(e, "frost_lock_until", -1.0) <= now
                and (visible is None or visible(e))):
            n += 1
    return n


def draw_snout_icon(surface, cx, cy, s):
    """Icona della passiva: muso di Swinub che annusa (naso + impronta)."""
    pygame.draw.circle(surface, FUR_DK, (cx, cy), s + 2)
    pygame.draw.circle(surface, FUR, (cx, cy), s + 1)
    pygame.draw.circle(surface, (170, 130, 96), (cx - s // 3, cy - s // 3), max(1, s // 2))
    # naso rosa
    nw = max(4, s)
    nose = pygame.Rect(cx - nw // 2, cy + s // 4, nw, max(3, nw * 2 // 3))
    pygame.draw.ellipse(surface, (110, 50, 60), nose.inflate(2, 2))
    pygame.draw.ellipse(surface, (232, 150, 160), nose)
    surface.set_at((nose.centerx - 2, nose.centery), (110, 50, 60))
    surface.set_at((nose.centerx + 1, nose.centery), (110, 50, 60))


# --- mirino --------------------------------------------------------------------

def draw_aim(surface, S, ts, ox, oy, nx, ny, dist, move) -> bool:
    """Mirino delle mosse della linea. Ritorna False se la forma non è sua."""
    shape = move.shape
    rng = move.range
    if shape in ("icetrail", "takedown"):
        d = rng if shape == "takedown" else min(dist, rng)
        ex, ey = ox + nx * d, oy + ny * d
        w = move.radius
        px, py = -ny * w, nx * w
        col = ICE if shape == "icetrail" else (236, 226, 206)
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        for sg in (1, -1):
            pygame.draw.line(surface, col, S(ox + px * sg, oy + py * sg),
                             S(ex + px * sg, ey + py * sg), 1)
        if shape == "takedown":   # punta di freccia della carica
            tip = S(ex, ey)
            l = S(ex - nx * 0.5 + px, ey - ny * 0.5 + py)
            r = S(ex - nx * 0.5 - px, ey - ny * 0.5 - py)
            pygame.draw.lines(surface, (255, 255, 255), False, [l, tip, r], 1)
        else:
            pygame.draw.circle(surface, (255, 255, 255), S(ex, ey), max(3, int(0.3 * ts)), 1)
        return True
    if shape == "icefang":
        half = math.radians(move.angle)
        base = math.atan2(ny, nx)
        pts = [S(ox, oy)]
        for i in range(9):
            a = base - half + 2 * half * i / 8
            pts.append(S(ox + math.cos(a) * rng, oy + math.sin(a) * rng))
        pygame.draw.lines(surface, ICE, True, pts, 1)
        return True
    if shape == "ancientpower":
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        d = min(dist, rng)
        cx, cy = S(ox + nx * d, oy + ny * d)
        pygame.draw.circle(surface, ROCK_HI, (cx, cy), int(move.radius * ts), 1)
        return True
    if shape == "iceage":
        ex, ey = ox + nx * rng, oy + ny * rng
        w = move.radius
        px, py = -ny * w, nx * w
        for sg in (1, -1):
            pygame.draw.line(surface, ICE, S(ox + px * sg, oy + py * sg),
                             S(ex + px * sg, ey + py * sg), 1)
        pygame.draw.line(surface, (255, 255, 255), S(ox, oy), S(ex, ey), 1)
        sr = float(move.effects.get("storm_radius", 3.0))
        pygame.draw.circle(surface, ICE_MID, S(ex, ey), int(sr * ts), 1)
        draw_ice_block(surface, *S(ex, ey - 0.5), max(3, int(0.22 * ts)))
        return True
    return False
