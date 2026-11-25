"""Grafica della linea Delibird (e della forma Ferrosacco della R).

Effetti istantanei (handler in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (palla di neve e getto d'acqua a ricerca dell'attacco
base, pacco che si apre, coriandoli), disegni persistenti letti dallo stato
del Match a ogni frame (pacchi della Q in volo, Punte a terra, bomba di Pacco
a Sorpresa, Consegna Speciale in arrivo), l'icona della passiva con la coda
dei pacchi, il mirino e i segni sulle unità (Propulsione Quark).

Pixel art: i PACCHI sono bitmap disegnate a mano a bassa risoluzione e
scalate NEAREST (in cache); luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

SNOW = (236, 244, 255)
SNOW_SH = (150, 178, 214)
SNOW_DK = (70, 96, 140)
ICE = (128, 206, 255)
ICE_HI = (222, 246, 255)
ICE_DK = (40, 92, 150)
RED = (214, 58, 52)
RED_DK = (110, 24, 26)
WATER = (64, 150, 255)
WATER_HI = (196, 232, 255)
WATER_DK = (20, 56, 140)
QUARK = (255, 226, 80)
QUARK_HI = (255, 250, 200)
GOLD = (246, 200, 70)
HEAL = (120, 230, 140)
WHITE = (255, 255, 255)
OUT = (34, 26, 30)

DELI_DEX = (225, 991)
PACK_NAMES = {"s": "Piccolo", "m": "Medio", "l": "Grande", "g": "Regalo"}

# --- pacchi pixel art -------------------------------------------------------------
# Lettere: O contorno, B scatola, D lato in ombra, H luce, R nastro, r nastro
# scuro, Y fiocco (oro), . vuoto. Ogni pacco ha il suo colore e la sua taglia.
_PACK_ROWS = {
    "s": ["..YY.YY..",
          "..YrYrY..",
          ".OOORROOO",
          ".OHBRRBDO",
          ".OBBRRBDO",
          ".ORRRRRRO",
          ".OBBRRBDO",
          ".ODDRRDDO",
          ".OOOOOOOO"],
    "m": ["...YY.YY...",
          "...YrYrY...",
          ".OOOORROOOO",
          ".OHHBRRBBDO",
          ".OHBBRRBBDO",
          ".ORRRRRRRRO",
          ".ORRRRRRRRO",
          ".OBBBRRBBDO",
          ".OBBBRRBBDO",
          ".ODDDRRDDDO",
          ".OOOOOOOOOO"],
    "l": ["....YYY.YYY....",
          "...YYrYYYrYY...",
          "....YYYrYYY....",
          ".OOOOOOrrOOOOOO",
          ".OHHHHBRRBBBBDO",
          ".OHHBBBRRBBBBDO",
          ".OHBBBBRRBBBBDO",
          ".ORRRRRRRRRRRRO",
          ".ORRRRRRRRRRRRO",
          ".OBBBBBRRBBBBDO",
          ".OBBBBBRRBBBBDO",
          ".OBBBBBRRBBBBDO",
          ".ODDDDDRRDDDDDO",
          ".OOOOOOOOOOOOOO"],
    "g": ["..RR...RR..",
          ".RrrR.RrrR.",
          "..RRRRRRR..",
          ".OOOORROOOO",
          ".OHHBRRBBDO",
          ".OHBBRRBBDO",
          ".OYYYYYYYYO",
          ".OBBBRRBBDO",
          ".OBBBRRBBDO",
          ".ODDDRRDDDO",
          ".OOOOOOOOOO"],
}
_PACK_COLS = {
    # (scatola, ombra, luce, nastro, nastro scuro)
    "s": ((196, 150, 96), (140, 98, 56), (232, 196, 140), (214, 58, 52), (130, 30, 30)),
    "m": ((86, 150, 230), (46, 92, 170), (170, 210, 255), (246, 246, 252), (170, 180, 200)),
    "l": ((214, 58, 52), (130, 28, 30), (250, 140, 120), (246, 200, 70), (170, 120, 30)),
    "g": ((236, 236, 244), (176, 180, 204), (255, 255, 255), (232, 96, 168), (150, 40, 100)),
}
_pack_cache: dict = {}


def pack_sprite(kind: str, scale: int = 2):
    """Sprite del pacco (in cache per tipo e scala, NEAREST)."""
    key = (kind, scale)
    img = _pack_cache.get(key)
    if img is None:
        rows = _PACK_ROWS.get(kind, _PACK_ROWS["s"])
        box, dk, hi, rib, rib_dk = _PACK_COLS.get(kind, _PACK_COLS["s"])
        cmap = {"O": OUT, "B": box, "D": dk, "H": hi, "R": rib, "r": rib_dk, "Y": GOLD}
        if kind == "g":
            cmap["Y"] = (232, 96, 168)
        w = max(len(r) for r in rows)
        base = pygame.Surface((w, len(rows)), pygame.SRCALPHA)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in cmap:
                    base.set_at((x, y), (*cmap[ch], 255))
        img = pygame.transform.scale(base, (w * scale, len(rows) * scale))
        _pack_cache[key] = img
    return img


def draw_pack(surface, cx, cy, kind, scale=2, alpha=255, ang=0.0):
    img = pack_sprite(kind, scale)
    if ang:
        img = pygame.transform.rotate(img, ang)
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    surface.blit(img, img.get_rect(center=(int(cx), int(cy))))


def _al(f, k=2.0):
    return int(255 * max(0.0, min(1.0, f * k)))


def is_deli(u) -> bool:
    return getattr(u, "dex", 0) in DELI_DEX


def _xy(c):
    return (c.x, c.y) if hasattr(c, "x") else (c[0], c[1])


def _snowball(surface, x, y, r, al):
    r = max(2, int(r))
    pygame.draw.circle(surface, (*SNOW_DK, al), (int(x) + 1, int(y) + 1), r)
    pygame.draw.circle(surface, (*SNOW_SH, al), (int(x), int(y)), r)
    pygame.draw.circle(surface, (*SNOW, al), (int(x) - 1, int(y) - 1), max(1, r - 1))
    surface.fill((*WHITE, al), pygame.Rect(int(x) - r // 2 - 1, int(y) - r // 2 - 1, 2, 2))


def _droplet(surface, x, y, r, ang, al, cols=(WATER_DK, WATER, WATER_HI)):
    """Goccia allungata nella direzione del moto."""
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    tip = (x + ux * r * 1.6, y + uy * r * 1.6)
    tail = (x - ux * r * 1.2, y - uy * r * 1.2)
    pts = [tip, (x + px * r, y + py * r), tail, (x - px * r, y - py * r)]
    pygame.draw.polygon(surface, (*cols[0], al), [(p[0] + 1, p[1] + 1) for p in pts])
    pygame.draw.polygon(surface, (*cols[1], al), pts)
    surface.fill((*cols[2], al), pygame.Rect(int(x - px * r * 0.4), int(y - py * r * 0.4 - 1), 2, 2))


# --- forme (FXSystem._draw_shapes) --------------------------------------------------
SHAPES = ("delisnowball", "ferrojet", "delipackopen", "deliconfetti", "deliquark")
AA_TRAVEL = {"delisnowball": 0.85, "ferrojet": 0.85}


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    age = s["maxlife"] - s["life"]
    if kind == "delisnowball":
        # Palla di neve (attacco base): fiocchi che restano indietro.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.85)
        if u >= 1.0:
            return
        lift = s.get("lift", 0.4) * ts
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - lift
        al = 255 if "hom" in s else _al(f, 4.0)
        rnd = random.Random(s.get("seed", 1))
        for k in range(4):
            uk = max(0.0, u - 0.05 * (k + 1))
            qx = ax + (bx - ax) * uk + rnd.uniform(-2, 2)
            qy = ay + (by - ay) * uk - lift + rnd.uniform(-2, 2)
            overlay.fill((*(ICE_HI if k % 2 else SNOW), max(0, al - 50 * k)),
                         pygame.Rect(int(qx), int(qy), 2, 2))
        _snowball(overlay, x, y, s.get("sz", 0.13) * ts, al)
    elif kind == "ferrojet":
        # Getto d'acqua (attacco base di Ferrosacco): goccia + spruzzi in scia.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.85)
        if u >= 1.0:
            return
        lift = s.get("lift", 0.42) * ts
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - lift
        ang = math.atan2(by - ay, bx - ax)
        al = 255 if "hom" in s else _al(f, 4.0)
        for k in range(1, 5):
            uk = max(0.0, u - 0.045 * k)
            qx, qy = ax + (bx - ax) * uk, ay + (by - ay) * uk - lift
            _droplet(overlay, qx, qy, max(1, 0.1 * ts - k), ang, max(0, al - 45 * k))
        _droplet(overlay, x, y, 0.12 * ts, ang, al)
    elif kind == "delipackopen":
        # Il pacco si apre: coperchio che salta e ruota, scatola che svanisce.
        cx, cy = S(*s["c"])
        cy -= int(0.45 * ts)
        al = _al(f, 2.5)
        k = s.get("pack", "s")
        sc = s.get("scale", 2)
        if t < 0.35:
            draw_pack(overlay, cx, cy - math.sin(t / 0.35 * math.pi) * 3, k, sc, al)
        else:
            img = pack_sprite(k, sc)
            w, h = img.get_size()
            body = img.subsurface(pygame.Rect(0, h // 3, w, h - h // 3)).copy()
            body.set_alpha(al)
            overlay.blit(body, body.get_rect(center=(int(cx), int(cy + h // 6))))
            lid = img.subsurface(pygame.Rect(0, 0, w, h // 3)).copy()
            u = (t - 0.35) / 0.65
            lid = pygame.transform.rotate(lid, -u * 140)
            lid.set_alpha(al)
            overlay.blit(lid, lid.get_rect(center=(int(cx + u * 0.5 * ts),
                                                   int(cy - h // 3 - u * 0.7 * ts + u * u * 0.6 * ts))))
    elif kind == "deliconfetti":
        # Coriandoli/fiocchi che escono dal pacco e ricadono.
        cx, cy = S(*s["c"])
        rnd = random.Random(s.get("seed", 7))
        al = _al(f, 2.0)
        cols = s.get("cols", (RED, GOLD, SNOW, ICE))
        for i in range(s.get("n", 14)):
            an = rnd.uniform(-math.pi, 0)
            v = rnd.uniform(0.6, 1.4) * s.get("spd", 1.6) * ts
            x = cx + math.cos(an) * v * t
            y = cy - 0.45 * ts + math.sin(an) * v * t + 2.2 * ts * t * t
            c = cols[i % len(cols)]
            sz = 2 if (i + int(age * 20)) % 3 else 1
            overlay.fill((*c, al), pygame.Rect(int(x), int(y), sz + 1, sz))
    elif kind == "deliquark":
        # Propulsione Quark: saette gialle che salgono dal corpo.
        cx, cy = S(*s["c"])
        rnd = random.Random(s.get("seed", 3))
        al = _al(f, 2.0)
        for i in range(6):
            x0 = cx + rnd.uniform(-0.45, 0.45) * ts
            y0 = cy - rnd.uniform(0.1, 0.6) * ts - t * 0.5 * ts
            pts = [(x0, y0)]
            for j in range(3):
                pts.append((pts[-1][0] + rnd.choice((-3, 3)), pts[-1][1] - 4))
            pygame.draw.lines(overlay, (*QUARK, al), False, pts, 2)
            pygame.draw.lines(overlay, (*QUARK_HI, al), False, pts, 1)


# --- handler degli eventi (FXSystem._FX_STYLES) -----------------------------------------

def _ab(e):
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return None
    return tuple(a), tuple(b)


def _bits(fx, c, n, cols, speed=2.0, life=(0.2, 0.4), size=1, up=0.0, spread=0.0):
    for _ in range(n):
        an = random.uniform(0, math.tau)
        v = random.uniform(0.4, 1.0) * speed
        x = c[0] + random.uniform(-spread, spread)
        y = c[1] + random.uniform(-spread, spread) * 0.5
        fx._add(x, y, math.cos(an) * v, math.sin(an) * v * 0.5 - up, random.uniform(*life),
                random.choice(cols), size)


def fx_delisnow(fx, e, col):
    """Attacco base di Delibird: palla di neve, sbuffo di neve all'arrivo."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    fx._shape(kind="delisnowball", a=a, b=b, col=SNOW, life=0.2 + L / 30.0, sz=0.13,
              seed=random.randrange(999))


def fx_ferrojet(fx, e, col):
    """Attacco base di Ferrosacco: getto d'acqua."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    fx._shape(kind="ferrojet", a=a, b=b, col=WATER, life=0.18 + L / 34.0)


def fx_deligiftthrow(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    _bits(fx, (c[0], c[1] - 0.4), 5, (SNOW, ICE_HI), speed=1.5, life=(0.15, 0.3))


def fx_deligiftopen(fx, e, col):
    """Pacco che arriva: si apre (coperchio che salta) con coriandoli;
    a vuoto solo un tonfo di neve."""
    c = e.get("c")
    if c is None:
        return
    k = e.get("pack", "s")
    sc = 1
    fx._shape(kind="delipackopen", c=tuple(c), pack=k, scale=sc, col=SNOW, life=0.55)
    if e.get("miss"):
        _bits(fx, (c[0], c[1] - 0.2), 8, (SNOW, SNOW_SH), speed=1.4, life=(0.2, 0.4))
        return
    if k == "g":
        fx._shape(kind="deliconfetti", c=tuple(c), n=16, seed=random.randrange(999),
                  cols=((232, 96, 168), HEAL, WHITE, GOLD), col=HEAL, life=0.7, wait=0.15)
        return
    n = {"s": 8, "m": 14, "l": 22}.get(k, 8)
    fx._shape(kind="deliconfetti", c=tuple(c), n=n, spd=1.2 + 0.4 * n / 8,
              seed=random.randrange(999), col=SNOW, life=0.6, wait=0.15)
    fx._shape(kind="impactstar", c=(c[0], c[1] - 0.45), r=0.22 + 0.08 * n / 8,
              cols=(ICE_DK, ICE, ICE_HI), col=ICE, life=0.22, wait=0.12)


def fx_deligiftheal(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="florplus", c=(c[0], c[1] - 0.6), col=HEAL, life=0.8)
    fx._shape(kind="ring", c=tuple(c), r0=0.2, r1=0.8, col=HEAL, life=0.35, wd=0.05)


def fx_deligiftboom(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.0))
    fx._shape(kind="ring", c=tuple(c), r0=0.3, r1=r, col=ICE, life=0.35, wd=0.06)
    _bits(fx, c, 18, (SNOW, ICE_HI, ICE, GOLD), speed=r * 2.2, life=(0.3, 0.55), size=2)


def fx_deliicywind(fx, e, col):
    """Ventogelato: getto di neve nel cono con raffiche di vento."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    ang = math.atan2(d[1], d[0])
    half = math.radians(float(e.get("angle", 35)))
    rng = float(e.get("range", 5.0))
    fx._shape(kind="snowcone", o=tuple(o), ang=ang, half=half, rng=rng, n=30, wind=True,
              seed=random.randrange(999), col=SNOW, life=0.5)


def fx_delispikes(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    _bits(fx, c, 10, (ICE, ICE_HI, SNOW), speed=1.8, life=(0.2, 0.4), spread=0.6)


def fx_delispikehit(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="iceburst", c=tuple(c), col=ICE, life=0.35)
    _bits(fx, (c[0], c[1] - 0.2), 10, (ICE, ICE_HI, SNOW), speed=2.4, life=(0.2, 0.4), size=2)


def _beam(fx, e, cols, w):
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="mothbeam", a=a, b=b, col=cols[1], life=0.45, w=w, motif="rings", cols=cols)
    fx._shape(kind="flash", c=(b[0], b[1] - 0.3), r=0.35, col=cols[1], life=0.25, wait=0.1)


def fx_delifreezedry(fx, e, col):
    _beam(fx, e, (ICE_DK, ICE, ICE_HI), 0.26)


def fx_ferropump(fx, e, col):
    _beam(fx, e, (WATER_DK, WATER, WATER_HI), 0.36)
    ab = _ab(e)
    if ab:
        _bits(fx, ab[1], 12, (WATER, WATER_HI, WHITE), speed=2.6, life=(0.2, 0.45), size=2)


def fx_delidash(fx, e, col):
    """Volo Postale: scia di vento e piume rosse/bianche lungo il percorso."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="windline", a=a, b=b, col=SNOW, life=0.3)
    dx, dy = b[0] - a[0], b[1] - a[1]
    for k in range(3):   # piume rosse e bianche lungo la scia
        u = (k + 0.5) / 3
        p = (a[0] + dx * u, a[1] + dy * u - 0.3)
        _bits(fx, p, 3, (SNOW, RED, (255, 190, 180)), speed=0.9, life=(0.25, 0.45), size=2)


def fx_delibomb(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.0))
    fx._shape(kind="flash", c=(c[0], c[1] - 0.2), r=0.6, col=ICE_HI, life=0.2)
    fx._shape(kind="ring", c=tuple(c), r0=0.3, r1=r, col=ICE, life=0.35, wd=0.07)
    fx._shape(kind="deliconfetti", c=tuple(c), n=24, spd=r, seed=random.randrange(999),
              col=SNOW, life=0.7)
    fx.shake_until_ms = max(getattr(fx, "shake_until_ms", 0), pygame.time.get_ticks() + 120)


def fx_delideliveryland(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 4.0))
    fx._shape(kind="flash", c=(c[0], c[1] - 0.3), r=1.0, col=ICE_HI, life=0.25)
    fx._shape(kind="ring", c=tuple(c), r0=0.5, r1=r, col=ICE, life=0.45, wd=0.08)
    fx._shape(kind="ring", c=tuple(c), r0=0.2, r1=r * 0.6, col=HEAL, life=0.4, wd=0.05, wait=0.08)
    fx._shape(kind="deliconfetti", c=tuple(c), n=40, spd=r * 1.1, seed=random.randrange(999),
              col=SNOW, life=0.9)
    fx.shake_until_ms = max(getattr(fx, "shake_until_ms", 0), pygame.time.get_ticks() + 250)


def fx_deliparadox(fx, e, col):
    """Paradosso Futuro: lampo d'acqua e anello, poi compare Ferrosacco."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="flash", c=(c[0], c[1] - 0.4), r=0.9, col=WATER_HI, life=0.3)
    fx._shape(kind="ring", c=tuple(c), r0=1.4, r1=0.2, col=WATER, life=0.4, wd=0.07)
    _bits(fx, c, 18, (WATER, WATER_HI, ICE_HI), speed=2.4, life=(0.3, 0.6), up=1.0, spread=0.4)


def fx_deliparadoxend(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=tuple(c), r0=0.2, r1=1.2, col=SNOW, life=0.35, wd=0.06)
    _bits(fx, c, 12, (SNOW, ICE_HI, RED), speed=1.8, life=(0.3, 0.5), up=0.6)


def fx_ferroquark(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="deliquark", c=tuple(c), seed=random.randrange(999), col=QUARK, life=0.6)
    fx._shape(kind="ring", c=tuple(c), r0=0.3, r1=1.3, col=QUARK, life=0.35, wd=0.06)


def fx_ferroflip(fx, e, col):
    """Inversione: scatto d'acqua verso il nemico e ritorno all'indietro."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="windline", a=a, b=b, col=WATER_HI, life=0.3)
    _bits(fx, b, 10, (WATER, WATER_HI, WHITE), speed=2.0, life=(0.2, 0.4), size=2)


STYLES = {
    "delisnow": fx_delisnow, "ferrojet": fx_ferrojet,
    "deligift": fx_deligiftthrow, "deligiftthrow": fx_deligiftthrow,
    "deligiftopen": fx_deligiftopen, "deligiftheal": fx_deligiftheal,
    "deligiftboom": fx_deligiftboom, "deliicywind": fx_deliicywind,
    "delispikes": fx_delispikes, "delispikehit": fx_delispikehit,
    "delifreezedry": fx_delifreezedry, "ferropump": fx_ferropump,
    "delidash": fx_delidash, "delibomb": fx_delibomb,
    "delideliveryland": fx_delideliveryland, "deliparadox": fx_deliparadox,
    "deliparadoxend": fx_deliparadoxend, "ferroquark": fx_ferroquark,
    "ferroflip": fx_ferroflip,
}


# --- disegni persistenti (game/world_fx.py) ------------------------------------------------

def _shadow(surface, x, y, w, al=90):
    rect = pygame.Rect(0, 0, max(4, int(w)), max(2, int(w * 0.4)))
    rect.center = (int(x), int(y))
    s = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, al), s.get_rect())
    surface.blit(s, rect)


def draw_gift(surface, camera, g, now):
    """Pacco della Q in volo: rotea, arco basso, ombra a terra."""
    ts = config.TILE_SIZE
    x, y = _xy(g["pos"])
    sx, sy = camera.world_to_screen(x * ts, y * ts)
    k = g.get("kind", "s")
    _shadow(surface, sx, sy, 0.5 * ts)
    hop = abs(math.sin(now * 9.0 + (g.get("caster_id", 0) or 0))) * 0.12 * ts
    draw_pack(surface, sx, sy - 0.5 * ts - hop, k, 1,
              ang=math.sin(now * 12.0) * 14)


_spike_cache: dict = {}


def _spike_sprite():
    """Punta di ghiaccio 9x9: tre cristalli col contorno scuro."""
    img = _spike_cache.get(0)
    if img is None:
        rows = ["....O....",
                "...OHO...",
                "...OCO.O.",
                ".O.OCOOHO",
                "OHOOCDOCO",
                "OCOOCDOCO",
                "OCDOCDOCO",
                "OODDDDDOO",
                ".OOOOOOO."]
        cmap = {"O": ICE_DK, "C": ICE, "H": ICE_HI, "D": (80, 150, 210)}
        base = pygame.Surface((9, 9), pygame.SRCALPHA)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in cmap:
                    base.set_at((x, y), (*cmap[ch], 255))
        img = pygame.transform.scale(base, (18, 18))
        _spike_cache[0] = img
    return img


def draw_spike(surface, camera, sp, now):
    ts = config.TILE_SIZE
    x, y = _xy(sp["c"])
    sx, sy = camera.world_to_screen(x * ts, y * ts)
    start, end = sp.get("start", now), sp.get("end", now + 30)
    fade = min(1.0, (now - start) / 0.25, max(0.0, end - now) / 1.0)
    if fade <= 0:
        return
    _shadow(surface, sx + 2, sy + 2, 0.45 * ts, int(70 * fade))
    img = _spike_sprite()
    if fade < 1.0:
        img = img.copy()
        img.set_alpha(int(255 * fade))
    surface.blit(img, img.get_rect(midbottom=(int(sx), int(sy + 4))))
    ph = (now * 0.8 + (sp.get("seed", 0) % 7) / 7) % 1.0
    if ph < 0.12:   # scintilla
        surface.fill((*WHITE, 255), pygame.Rect(int(sx) - 3, int(sy) - 12, 2, 2))


def draw_bomb(surface, camera, b, now):
    """Pacco a Sorpresa: pacco a terra che trema, miccia e cerchio che si chiude."""
    ts = config.TILE_SIZE
    x, y = _xy(b["c"])
    sx, sy = camera.world_to_screen(x * ts, y * ts)
    start, at = b.get("start", now), b.get("at", now + 1)
    u = max(0.0, min(1.0, (now - start) / max(0.05, at - start)))
    r = float(b.get("radius", 2.0)) * ts
    rect = pygame.Rect(0, 0, int(r * 2), int(r * 1.2))
    rect.center = (int(sx), int(sy))
    s = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.ellipse(s, (*RED, int(40 + 50 * u)), s.get_rect())
    pygame.draw.ellipse(s, (*RED, 200), s.get_rect(), 2)
    inner = s.get_rect().inflate(-int(rect.w * (1 - u)), -int(rect.h * (1 - u)))
    if inner.w > 2 and inner.h > 2:
        pygame.draw.ellipse(s, (255, 230, 200, 200), inner, 1)
    surface.blit(s, rect)
    shake = int(math.sin(now * 60) * 2 * u)
    _shadow(surface, sx, sy, 0.5 * ts)
    draw_pack(surface, sx + shake, sy - 0.3 * ts, "l", 1)
    if int(now * (6 + 14 * u)) % 2 == 0:   # miccia che sfrigola, sempre più veloce
        fx, fy = int(sx + shake + 0.25 * ts), int(sy - 0.75 * ts)
        surface.fill((*GOLD, 255), pygame.Rect(fx, fy, 3, 3))
        surface.fill((*WHITE, 255), pygame.Rect(fx + 1, fy - 2, 1, 2))


def draw_drop(surface, camera, d, now):
    """Consegna Speciale: area che si riempie e pacco gigante che cade col
    paracadute dall'alto, con l'ombra che cresce."""
    ts = config.TILE_SIZE
    x, y = _xy(d["c"])
    sx, sy = camera.world_to_screen(x * ts, y * ts)
    start, at = d.get("start", now), d.get("at", now + 1)
    u = max(0.0, min(1.0, (now - start) / max(0.05, at - start)))
    r = float(d.get("radius", 4.0)) * ts
    rect = pygame.Rect(0, 0, int(r * 2), int(r * 1.2))
    rect.center = (int(sx), int(sy))
    s = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.ellipse(s, (*ICE, int(30 + 40 * u)), s.get_rect())
    inner = s.get_rect().inflate(-int(rect.w * (1 - u)), -int(rect.h * (1 - u)))
    if inner.w > 2 and inner.h > 2:
        pygame.draw.ellipse(s, (*ICE, int(50 + 60 * u)), inner)
    n = max(24, int(math.tau * r / (0.45 * ts)) // 2 * 2)
    for k in range(0, n, 2):
        a0 = k / n * math.tau + now * 0.6
        a1 = a0 + math.tau / n
        p0 = (rect.w / 2 + math.cos(a0) * r, rect.h / 2 + math.sin(a0) * r * 0.6)
        p1 = (rect.w / 2 + math.cos(a1) * r, rect.h / 2 + math.sin(a1) * r * 0.6)
        pygame.draw.line(s, (*ICE_HI, 220), p0, p1, 2)
    surface.blit(s, rect)
    _shadow(surface, sx, sy, (0.4 + 0.8 * u) * ts, int(60 + 80 * u))
    h = (1.0 - u) ** 1.4 * 7.0 * ts
    px, py = sx, sy - 0.6 * ts - h
    # paracadute: cupola rossa/bianca a spicchi con i fili
    cw = int(1.6 * ts)
    dome = pygame.Rect(0, 0, cw, int(cw * 0.6))
    dome.midbottom = (int(px), int(py - 0.5 * ts))
    pygame.draw.ellipse(surface, OUT, pygame.Rect(dome.left - 1, dome.top - 1,
                                                  dome.w + 2, dome.h * 2 + 2), 1)
    for i in range(4):
        sub = pygame.Rect(dome.left + i * cw // 4, dome.top, cw // 4 + 1, dome.h)
        col = RED if i % 2 == 0 else SNOW
        clip = surface.get_clip()
        surface.set_clip(sub.clip(surface.get_rect()))
        pygame.draw.ellipse(surface, col, pygame.Rect(dome.left, dome.top, dome.w, dome.h * 2))
        surface.set_clip(clip)
    for fxp in (dome.left + 2, dome.centerx, dome.right - 2):
        pygame.draw.line(surface, OUT, (fxp, dome.bottom), (int(px), int(py - 0.15 * ts)), 1)
    draw_pack(surface, px, py, "l", 2)


# --- sulle unità ---------------------------------------------------------------------------

def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Ferrosacco con Propulsione Quark: scintille gialle che salgono."""
    if not getattr(u, "quark_active", False):
        return
    r = int(getattr(u, "radius", 0.5) * ts)
    for k in range(4):
        ph = (now * 1.6 + k / 4) % 1.0
        x = gx + math.sin(k * 2.3 + now * 3) * r
        y = gy - r * 0.3 - ph * r * 1.8
        al = int(255 * math.sin(ph * math.pi))
        surface.fill((*QUARK, al), pygame.Rect(int(x), int(y), 2, 3))
        surface.fill((*QUARK_HI, al), pygame.Rect(int(x), int(y), 1, 1))


# --- interfaccia ---------------------------------------------------------------------------

def draw_hud(surface, font, p, bx, y0, bh, now):
    """Pacco in Arrivo: il pacco pronto grande nel riquadro, i 2 successivi
    piccoli in colonna accanto (verso la casella Q). Ferrosacco: secondi della
    forma e Propulsione Quark."""
    box = pygame.Rect(bx, y0, bh, bh)
    ferro = getattr(p, "passive_id", "") == "propulsionequark"
    pygame.draw.rect(surface, (22, 40, 70) if ferro else (52, 30, 34), box)
    if ferro:
        left = max(0.0, getattr(p, "ferro_until", now) - now)
        quark = getattr(p, "quark_active", False)
        cx, cy = box.center
        _droplet(surface, cx, cy - 2, max(4, bh // 6), -math.pi / 2, 255)
        t = font.render("%d" % math.ceil(left), True, WHITE)
        surface.blit(t, t.get_rect(midbottom=(box.centerx, box.bottom - 2)))
        frame = QUARK if quark else WATER_HI
        name = "Propulsione Quark!" if quark else "Ferrosacco"
        pygame.draw.rect(surface, frame, box, 2)
        surface.blit(font.render(name, True, frame), (bx - 4, y0 - 18))
        return
    q = list(getattr(p, "deli_queue", ()) or ())
    if q:
        scale = 3 if bh >= 40 else 2
        draw_pack(surface, box.centerx, box.centery, q[0], scale)
    pygame.draw.rect(surface, GOLD, box, 2)
    x = box.right + 8
    step = bh // 2
    for i, k in enumerate(q[1:3]):
        draw_pack(surface, x, y0 + step // 2 + i * step, k, 1)
    name = "Pacco: " + PACK_NAMES.get(q[0], "?") if q else "Pacco in Arrivo"
    surface.blit(font.render(name, True, GOLD), (bx - 4, y0 - 18))


def draw_aim(surface, S, ts, ox, oy, nx, ny, dist, move, queue=None) -> bool:
    """Mirino delle mosse della linea. Ritorna False se la forma non è sua."""
    shape = move.shape
    rng = move.range
    if shape in ("deligift", "delibeam"):
        ex, ey = ox + nx * rng, oy + ny * rng
        w = move.radius
        px, py = -ny * w, nx * w
        col = WATER if move.type == "Water" else ICE
        for sg in (1, -1):
            pygame.draw.line(surface, col, S(ox + px * sg, oy + py * sg),
                             S(ex + px * sg, ey + py * sg), 1)
        pygame.draw.line(surface, WHITE, S(ox, oy), S(ex, ey), 1)
        if shape == "deligift" and queue:
            draw_pack(surface, *S(ex, ey - 0.3), queue[0], 1)
        return True
    if shape == "delispikes":
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        d = min(dist, rng)
        cx, cy = ox + nx * d, oy + ny * d
        sp = float(move.effects.get("spread", 0.9))
        base = math.atan2(ny, nx)
        for i in range(int(move.effects.get("count", 3))):
            a = base + i * math.tau / 3
            pygame.draw.circle(surface, ICE, S(cx + math.cos(a) * sp, cy + math.sin(a) * sp),
                               max(3, int(move.radius * ts)), 1)
        return True
    if shape == "delidash":
        ex, ey = ox + nx * min(dist, rng), oy + ny * min(dist, rng)
        pygame.draw.line(surface, SNOW, S(ox, oy), S(ex, ey), 2)
        r = float((move.effects.get("bomb") or {}).get("radius", 2.0))
        cx, cy = S(ox, oy)
        rect = pygame.Rect(0, 0, int(r * ts * 2), int(r * ts * 1.2))
        rect.center = (cx, cy)
        pygame.draw.ellipse(surface, RED, rect, 1)
        return True
    if shape == "delidelivery":
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        d = min(dist, rng)
        cx, cy = S(ox + nx * d, oy + ny * d)
        r = int(move.radius * ts)
        pygame.draw.circle(surface, ICE, (cx, cy), r, 2)
        draw_pack(surface, cx, cy - 4, "l", 1)
        return True
    if shape == "deliparadox":
        pygame.draw.circle(surface, WATER, S(ox, oy), int(0.9 * ts), 1)
        return True
    return False
