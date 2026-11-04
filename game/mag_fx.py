"""Grafica della linea Magnemite > Magneton > Magnezone: effetti istantanei
(handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (saetta a zig-zag tra due punti, linee di campo
magnetico, badge della carica che "scoppia", frecce dell'inversione),
disegni persistenti letti dallo stato del Match a ogni frame (Tuonoshock in
volo con la saetta che lo segue, cariche sui muri, Scia Ionica, pilastro di
Bombagnete, Campo Elettrico, trascinamenti e spinte in corso), il badge + / -
sulle unità, l'icona della passiva e il mirino (con il selettore di polarità
della R: rotella del mouse o Tab mentre si mira).

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

ELEC = (255, 222, 72)          # Elettro (giallo)
ELEC_HI = (255, 252, 214)
ELEC_DK = (120, 82, 10)
STEEL = (178, 190, 208)        # Acciaio
STEEL_HI = (238, 244, 252)
STEEL_DK = (54, 62, 80)
POS = (236, 64, 62)            # carica + (rosso)
POS_HI = (255, 196, 186)
POS_DK = (96, 14, 22)
NEG = (66, 132, 244)           # carica - (blu)
NEG_HI = (196, 224, 255)
NEG_DK = (16, 36, 104)
FIELD = (190, 150, 255)        # linee di campo (attrazione)
WEB = (150, 236, 255)          # Elettrotela

MAG_DEX = (81, 82, 462)


def _al(f, k=2.0):
    return int(255 * max(0.0, min(1.0, f * k)))


def sign_cols(sign):
    return (POS_DK, POS, POS_HI) if sign > 0 else (NEG_DK, NEG, NEG_HI)


def is_mag(u) -> bool:
    return getattr(u, "dex", 0) in MAG_DEX


# --- selettore di polarità della R --------------------------------------------------

_POLARITY = {"sign": 1}


def polarity() -> int:
    return _POLARITY["sign"]


def toggle_polarity() -> None:
    _POLARITY["sign"] = -_POLARITY["sign"]


def has_polarity(move) -> bool:
    return move is not None and bool(move.effects.get("polarity"))


def cast_hold(move, hold: float) -> float:
    """Valore del campo `hold` da mandare col lancio: per le R a polarità porta
    il segno scelto (1,0 = "-", 0,0 = "+"), per le altre la pressione vera."""
    if has_polarity(move):
        return 1.0 if polarity() < 0 else 0.0
    return hold


# --- piccoli disegni -----------------------------------------------------------

_badge_cache: dict = {}


def badge(sign, s=1):
    """Badge della carica: dischetto rosso con "+" o blu con "-" (9x9 px +
    contorno), luce in alto a sinistra. In cache."""
    key = (sign, s)
    img = _badge_cache.get(key)
    if img is None:
        dk, md, hi = sign_cols(sign)
        img = pygame.Surface((11, 11), pygame.SRCALPHA)
        pygame.draw.circle(img, dk, (5, 5), 5)
        pygame.draw.circle(img, md, (5, 5), 4)
        img.set_at((3, 3), hi)
        img.set_at((4, 2), hi)
        img.set_at((2, 4), hi)
        pygame.draw.line(img, (255, 255, 255), (3, 5), (7, 5))
        if sign > 0:
            pygame.draw.line(img, (255, 255, 255), (5, 3), (5, 7))
        if s > 1:
            img = pygame.transform.scale(img, (11 * s, 11 * s))
        _badge_cache[key] = img
    return img


def blit_badge(surface, x, y, sign, s=1, alpha=255):
    img = badge(sign, s)
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    surface.blit(img, (int(x) - img.get_width() // 2, int(y) - img.get_height() // 2))


def _zig_pts(ax, ay, bx, by, amp, seg_len, rnd):
    L = math.hypot(bx - ax, by - ay)
    if L < 1:
        return [(ax, ay), (bx, by)]
    n = max(2, int(L / max(2.0, seg_len)))
    px, py = -(by - ay) / L, (bx - ax) / L
    pts = [(ax, ay)]
    for i in range(1, n):
        u = i / n
        j = rnd.uniform(-amp, amp)
        pts.append((ax + (bx - ax) * u + px * j, ay + (by - ay) * u + py * j))
    pts.append((bx, by))
    return pts


def _zig(surface, a, b, cols, al, amp, seg_len, rnd, width=3, branch=True):
    """Saetta a zig-zag a tre strati (alone, corpo, nucleo) con un rametto."""
    pts = _zig_pts(a[0], a[1], b[0], b[1], amp, seg_len, rnd)
    pygame.draw.lines(surface, (*cols[0], al // 2), False, pts, width + 2)
    pygame.draw.lines(surface, (*cols[1], al), False, pts, width)
    pygame.draw.lines(surface, (*cols[2], al), False, pts, 1)
    if branch and len(pts) > 3:
        k = rnd.randrange(1, len(pts) - 1)
        x0, y0 = pts[k]
        an = rnd.uniform(0, math.tau)
        L = seg_len * rnd.uniform(0.8, 1.6)
        bp = _zig_pts(x0, y0, x0 + math.cos(an) * L, y0 + math.sin(an) * L, amp * 0.6,
                      seg_len * 0.5, rnd)
        pygame.draw.lines(surface, (*cols[1], al), False, bp, 1)
    return pts


def _field_lines(surface, a, b, col, al, n=3, bulge=0.35, phase=0.0, width=1):
    """Linee di campo magnetico tra due poli: archi che si gonfiano ai lati."""
    ax, ay = a
    bx, by = b
    L = math.hypot(bx - ax, by - ay)
    if L < 2:
        return
    px, py = -(by - ay) / L, (bx - ax) / L
    for k in range(n):
        off = (k - (n - 1) / 2) / max(1, (n - 1) / 2) if n > 1 else 0.0
        h = L * bulge * off
        pts = []
        for i in range(13):
            u = i / 12
            bend = 4 * u * (1 - u) * h
            pts.append((ax + (bx - ax) * u + px * bend, ay + (by - ay) * u + py * bend))
        pygame.draw.lines(surface, (*col, al), False, pts, width)
        # un "granello" che corre lungo la linea
        q = (phase + k * 0.33) % 1.0
        i = int(q * 12)
        pygame.draw.circle(surface, (255, 255, 255, al), (int(pts[i][0]), int(pts[i][1])), 1)


# --- forme per FXSystem._draw_shapes --------------------------------------------

SHAPES = ("ziglink", "fieldlines", "signpop", "fliparrows", "magring")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "ziglink":
        # Saetta tra A e B, rifatta a ogni frame (crepita).
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        lift = s.get("lift", 0.4) * ts
        rnd = random.Random()
        cols = s.get("cols", (ELEC_DK, ELEC, ELEC_HI))
        _zig(overlay, (ax, ay - lift), (bx, by - lift), cols, _al(f, 2.0),
             s.get("amp", 0.22) * ts, 0.45 * ts, rnd, s.get("w", 2), s.get("branch", True))
    elif kind == "fieldlines":
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        lift = s.get("lift", 0.4) * ts
        _field_lines(overlay, (ax, ay - lift), (bx, by - lift), s.get("col", FIELD),
                     _al(f, 2.0), n=s.get("n", 3), bulge=s.get("bulge", 0.3),
                     phase=t * 2.5, width=s.get("w", 1))
    elif kind == "signpop":
        # Badge della carica che compare: anello che si chiude + badge che rimbalza.
        cx, cy = S(*s["c"])
        cy -= s.get("lift", 1.0) * ts
        sign = s.get("sign", 1)
        dk, md, hi = sign_cols(sign)
        al = _al(f, 2.5)
        r = int((0.25 + 0.25 * f) * ts)
        pygame.draw.circle(overlay, (*md, al), (cx, cy), max(2, r), 1)
        sc = 2 if t < 0.15 else 1
        img = badge(sign, sc).copy()
        img.set_alpha(al)
        overlay.blit(img, (cx - img.get_width() // 2, cy - img.get_height() // 2))
    elif kind == "fliparrows":
        # Voltcambio inverte una carica: due frecce curve che girano.
        cx, cy = S(*s["c"])
        cy -= s.get("lift", 0.6) * ts
        R = s.get("r", 0.45) * ts
        al = _al(f, 2.5)
        rot = t * 7.0
        for k in range(2):
            a0 = rot + k * math.pi
            pts = [(cx + math.cos(a0 + i * 0.25) * R, cy + math.sin(a0 + i * 0.25) * R * 0.7)
                   for i in range(9)]
            col = POS if k == 0 else NEG
            pygame.draw.lines(overlay, (*ELEC_DK, al), False, pts, 3)
            pygame.draw.lines(overlay, (*col, al), False, pts, 1)
            ex, ey = pts[-1]
            an = a0 + 8 * 0.25 + math.pi / 2
            tx, ty = math.cos(an), math.sin(an) * 0.7
            pygame.draw.polygon(overlay, (*col, al), [(ex + tx * 4, ey + ty * 4),
                                                       (ex - ty * 3, ey + tx * 3),
                                                       (ex + ty * 3, ey - tx * 3)])
    elif kind == "magring":
        # Anello schiacciato in prospettiva (impulso del pilastro / del campo);
        # "inward" = si chiude verso il centro (attrazione).
        cx, cy = S(*s["c"])
        r0, r1 = s.get("r0", 0.3), s.get("r1", 2.0)
        u = min(1.0, t * s.get("speed", 1.6))
        if s.get("inward"):
            u = 1.0 - u
        R = (r0 + (r1 - r0) * u) * ts
        cols = s.get("cols", (ELEC_DK, ELEC, ELEC_HI))
        al = _al(f, 2.0)
        rect = pygame.Rect(int(cx - R), int(cy - R * 0.5), int(R * 2), max(2, int(R)))
        pygame.draw.ellipse(overlay, (*cols[0], al // 2), rect.inflate(4, 2), 4)
        pygame.draw.ellipse(overlay, (*cols[1], al), rect, 2)
        n = max(10, int(R / 5))
        rnd = random.Random(int(t * 40))
        for i in range(n):   # crepitio sul bordo
            if rnd.random() < 0.5:
                continue
            an = i / n * math.tau
            x, y = cx + math.cos(an) * R, cy + math.sin(an) * R * 0.5
            pygame.draw.line(overlay, (*cols[2], al), (x, y),
                             (x + rnd.uniform(-3, 3), y - rnd.uniform(1, 4)), 1)


# --- handler degli eventi (FXSystem._FX_STYLES) --------------------------------


def _ab(e):
    a, b = e.get("a"), e.get("b")
    return (a, b) if a is not None and b is not None else None


def _bits(fx, c, n, cols, speed=2.0, life=(0.15, 0.35), size=1, up=0.0, spread=0.0):
    for _ in range(n):
        an = random.uniform(0, math.tau)
        v = random.uniform(0.4, 1.0) * speed
        x = c[0] + random.uniform(-spread, spread)
        y = c[1] + random.uniform(-spread, spread) * 0.5
        fx._add(x, y, math.cos(an) * v, math.sin(an) * v * 0.5 - up, random.uniform(*life),
                random.choice(cols), size)


def _sparks(fx, c, n=4, r=0.6, cols=(ELEC_DK, ELEC, ELEC_HI), life=0.18):
    """Piccole saette che schizzano fuori dal punto."""
    for _ in range(n):
        an = random.uniform(0, math.tau)
        L = random.uniform(0.5, 1.0) * r
        fx._shape(kind="ziglink", a=c, b=(c[0] + math.cos(an) * L, c[1] + math.sin(an) * L * 0.6),
                  lift=0.4, amp=0.08, w=1, branch=False, cols=cols, col=cols[1],
                  life=random.uniform(life * 0.7, life))


def fx_magshot(fx, e, col):
    """Attacco base: pallina d'energia giallo-acciaio con una scarica."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="energy", a=a, b=b, col=ELEC, life=0.22, sz=0.12, lift_a=0.45, lift_b=0.3)
    fx._shape(kind="ziglink", a=a, b=b, lift=0.4, amp=0.12, w=1, branch=False,
              col=ELEC, life=0.08, wait=0.05)
    fx._shape(kind="flash", c=(b[0], b[1] - 0.3), r=0.25, col=ELEC_HI, life=0.1, wait=0.2)


def fx_magbolthit(fx, e, col):
    """Tuonoshock a segno: lampo giallo, scariche (Elettrotela: maglie
    azzurre; Falcecannone: urto metallico grosso)."""
    c = e.get("c")
    if c is None:
        return
    top = (c[0], c[1] - 0.4)
    big = e.get("big")
    cols = (ELEC_DK, WEB, ELEC_HI) if e.get("web") else (ELEC_DK, ELEC, ELEC_HI)
    fx._shape(kind="flash", c=top, r=0.55 if big else 0.4, col=cols[2], life=0.12)
    fx._shape(kind="ring", c=top, r0=0.2, r1=1.0 if big else 0.7, col=cols[1], life=0.25, wd=0.06)
    _sparks(fx, c, 6 if big else 4, 1.0 if big else 0.7, cols)
    if big:
        fx._shape(kind="impactstar", c=top, r=0.55, n=8, rot=random.uniform(0, 1),
                  cols=(STEEL_DK, STEEL, STEEL_HI), col=STEEL, life=0.25)
    _bits(fx, top, 10, cols[1:], speed=2.6)


def fx_magboltwall(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    top = (c[0], c[1] - 0.3)
    fx._shape(kind="flash", c=top, r=0.4, col=ELEC_HI, life=0.12)
    _sparks(fx, c, 5, 0.8)
    _bits(fx, top, 10, (ELEC, ELEC_HI, STEEL), speed=2.2)


def fx_magfizzle(fx, e, col):
    c = e.get("c")
    if c is not None:
        _bits(fx, (c[0], c[1] - 0.4), 6, (ELEC, ELEC_HI), speed=1.4)


def fx_magcharge(fx, e, col):
    """Carica applicata: badge + / - che compare sopra (unità) o sul muro."""
    c = e.get("c")
    if c is None:
        return
    sign = e.get("sign", 1)
    lift = 0.7 if e.get("wall") else 1.45
    fx._shape(kind="signpop", c=c, sign=sign, lift=lift, col=sign_cols(sign)[1], life=0.35)


def fx_magfield(fx, e, col):
    """Campo Magnetico: linee di campo dal lanciatore al bersaglio; sul
    nemico un anello d'acciaio blu, sull'alleato lo scudo esagonale."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="fieldlines", a=a, b=b, col=NEG_HI, n=3, bulge=0.1, life=0.3)
    fx._shape(kind="ziglink", a=a, b=b, lift=0.4, amp=0.1, w=1, branch=False,
              cols=(NEG_DK, NEG, NEG_HI), col=NEG, life=0.15)
    if e.get("ally"):
        fx._shape(kind="hexshell", c=b, r=0.75, col=NEG, life=0.5)
    else:
        fx._shape(kind="magring", c=b, r0=1.0, r1=0.25, cols=(NEG_DK, NEG, NEG_HI),
                  col=NEG, life=0.35, speed=2.5)
        _bits(fx, (b[0], b[1] - 0.4), 8, (NEG, NEG_HI, STEEL), speed=2.0)


def fx_magchain(fx, e, col):
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="ziglink", a=a, b=b, lift=0.45, amp=0.2, cols=(NEG_DK, NEG, NEG_HI),
              col=NEG, life=0.25)
    fx._shape(kind="ziglink", a=a, b=b, lift=0.45, amp=0.3, w=1, branch=False,
              cols=(NEG_DK, NEG_HI, (255, 255, 255)), col=NEG, life=0.18, wait=0.06)


def fx_voltdash(fx, e, col):
    """Voltcambio: saetta gialla lungo lo scatto, scintille ai due capi."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="ziglink", a=a, b=b, lift=0.35, amp=0.3, w=3, col=ELEC, life=0.25)
    fx._shape(kind="ziglink", a=a, b=b, lift=0.35, amp=0.18, w=1, branch=False,
              cols=(ELEC_DK, ELEC_HI, (255, 255, 255)), col=ELEC, life=0.18, wait=0.05)
    for pt in (a, b):
        fx._shape(kind="flash", c=(pt[0], pt[1] - 0.35), r=0.35, col=ELEC_HI, life=0.12)
        _sparks(fx, pt, 3, 0.6)


def fx_magflip(fx, e, col):
    c = e.get("c")
    if c is not None:
        fx._shape(kind="fliparrows", c=c, lift=1.0, r=0.42, col=ELEC, life=0.45)


def fx_magsnap(fx, e, col):
    """Due cariche interagiscono: attrazione = linee di campo viola tese;
    respinta = due saette corte che si allontanano."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    if e.get("attract"):
        fx._shape(kind="fieldlines", a=a, b=b, col=FIELD, n=3, bulge=0.1, w=1, life=0.25)
        fx._shape(kind="ziglink", a=a, b=b, lift=0.4, amp=0.15, w=1, branch=False,
                  col=FIELD, cols=((60, 30, 110), FIELD, (240, 226, 255)), life=0.2)
    else:
        for p, q in ((a, b), (b, a)):
            dx, dy = p[0] - q[0], p[1] - q[1]
            L = math.hypot(dx, dy) or 1.0
            fx._shape(kind="ziglink", a=p, b=(p[0] + dx / L * 1.2, p[1] + dy / L * 1.2),
                      lift=0.4, amp=0.12, w=2, branch=False, col=ELEC, life=0.3)
        fx._shape(kind="ring", c=((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 0.3), r0=0.2,
                  r1=0.9, col=ELEC, life=0.25, wd=0.05)


def fx_magclash(fx, e, col):
    """Urto magnetico: stella d'acciaio, lampo, scariche e polvere."""
    c = e.get("c")
    if c is None:
        return
    top = (c[0], c[1] - 0.4)
    fx._shape(kind="impactstar", c=top, r=0.6, n=8, rot=random.uniform(0, 1),
              cols=(STEEL_DK, ELEC, ELEC_HI), col=ELEC, life=0.3)
    fx._shape(kind="flash", c=top, r=0.5, col=ELEC_HI, life=0.12)
    _sparks(fx, c, 5, 1.0)
    fx._dust(c, 0.5, n=6)


def fx_magpillarland(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    sign = e.get("sign", 1)
    cols = sign_cols(sign)
    fx._shape(kind="flash", c=(c[0], c[1] - 0.5), r=0.7, col=ELEC_HI, life=0.14)
    fx._shape(kind="magring", c=c, r0=0.5, r1=2.5, cols=cols, col=cols[1], life=0.35, speed=2.5)
    _sparks(fx, c, 6, 1.2)
    fx._dust(c, 0.9, n=12)


def fx_magpulse(fx, e, col):
    """Impulso del pilastro: anello che corre fino al bordo dell'area (6 tile)."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 6.0))
    cols = sign_cols(e.get("sign", 1))
    fx._shape(kind="magring", c=c, r0=0.6, r1=r, cols=cols, col=cols[1], life=0.45, speed=2.3)


def fx_magpillarend(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    _bits(fx, (c[0], c[1] - 0.6), 14, (STEEL, STEEL_HI, ELEC), speed=2.0)
    fx._dust(c, 0.6, n=8)


def fx_magterrain(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 5.0))
    fx._shape(kind="magring", c=c, r0=0.3, r1=r, col=ELEC, life=0.5, speed=2.0)
    fx._shape(kind="flash", c=c, r=0.8, col=ELEC_HI, life=0.15)


def fx_magterrainpulse(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 5.0))
    cols = sign_cols(e.get("sign", 1))
    fx._shape(kind="magring", c=c, r0=r, r1=r * 0.2, cols=cols, col=cols[1], life=0.4,
              speed=2.5)


STYLES = {
    "magshot": fx_magshot, "magbolthit": fx_magbolthit, "magboltwall": fx_magboltwall,
    "magfizzle": fx_magfizzle, "magcharge": fx_magcharge, "magfield": fx_magfield,
    "magchain": fx_magchain, "voltdash": fx_voltdash, "magflip": fx_magflip,
    "magsnap": fx_magsnap, "magclash": fx_magclash, "magpillarland": fx_magpillarland,
    "magpulse": fx_magpulse, "magpillarend": fx_magpillarend, "magterrain": fx_magterrain,
    "magterrainpulse": fx_magterrainpulse,
}


# --- disegni persistenti (stato del Match) ---------------------------------------


def _layer(R):
    g = pygame.Surface((R * 2 + 12, R + 12), pygame.SRCALPHA)
    return g, (R + 6, R // 2 + 6)


def draw_bolt(surface, camera, o, now):
    """Tuonoshock in volo: testa luminosa con la SAETTA che la segue (rifatta
    a ogni frame); Elettrotela = rete azzurra che gira; Falcecannone = sfera
    d'acciaio lenta e grossa con un anello di scariche."""
    ts = config.TILE_SIZE
    p = o["pos"]
    d = o["dir"]
    hx, hy = camera.world_to_screen(p.x * ts, (p.y - 0.45) * ts)
    fx = o.get("fx", "magbolt")
    rnd = random.Random(int(now * 30) + o.get("caster_id", 0))
    # coda: la saetta parte da dietro (fino a 2,2 tile, non oltre il lancio)
    org = o.get("origin", p)
    back = min(2.2, math.hypot(p.x - org.x, p.y - org.y))
    tx, ty = camera.world_to_screen((p.x - d.x * back) * ts, (p.y - d.y * back - 0.45) * ts)
    g = surface
    if fx == "steelcannon":
        R = max(5, int(0.36 * ts))
        if back > 0.2:
            _zig(g, (tx, ty), (hx, hy), (ELEC_DK, ELEC, ELEC_HI), 200, 0.25 * ts, 0.4 * ts, rnd, 2)
        pygame.draw.circle(g, STEEL_DK, (hx, hy), R + 1)
        pygame.draw.circle(g, STEEL, (hx, hy), R)
        pygame.draw.circle(g, (120, 132, 156), (hx + R // 4, hy + R // 4), R // 2)
        pygame.draw.circle(g, STEEL_HI, (hx - R // 3, hy - R // 3), max(1, R // 3))
        # anello di scariche che gira attorno
        for k in range(6):
            an = now * 9.0 + k / 6 * math.tau
            x0 = hx + math.cos(an) * (R + 3)
            y0 = hy + math.sin(an) * (R + 3) * 0.6
            pygame.draw.line(g, ELEC, (x0, y0), (x0 + rnd.uniform(-3, 3), y0 + rnd.uniform(-3, 3)), 1)
    elif fx == "electroweb":
        R = max(4, int(0.3 * ts))
        if back > 0.2:
            _zig(g, (tx, ty), (hx, hy), (ELEC_DK, WEB, ELEC_HI), 190, 0.2 * ts, 0.4 * ts, rnd, 1)
        rot = now * 6.0
        pts = [(hx + math.cos(rot + k * math.tau / 6) * R,
                hy + math.sin(rot + k * math.tau / 6) * R * 0.75) for k in range(6)]
        inner = [((x + hx) / 2, (y + hy) / 2) for x, y in pts]
        pygame.draw.polygon(g, ELEC_DK, pts, 3)
        pygame.draw.polygon(g, WEB, pts, 1)
        pygame.draw.polygon(g, WEB, inner, 1)
        for x, y in pts:
            pygame.draw.line(g, WEB, (hx, hy), (x, y), 1)
        pygame.draw.circle(g, ELEC_HI, (hx, hy), 2)
    else:
        R = max(3, int(0.17 * ts))
        if back > 0.2:
            _zig(g, (tx, ty), (hx, hy), (ELEC_DK, ELEC, ELEC_HI), 230, 0.22 * ts, 0.35 * ts, rnd, 2)
        glow = pygame.Surface((R * 6, R * 6), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*ELEC, 70), (R * 3, R * 3), R * 3)
        pygame.draw.circle(glow, (*ELEC, 120), (R * 3, R * 3), R * 2)
        g.blit(glow, (hx - R * 3, hy - R * 3))
        pygame.draw.circle(g, ELEC_DK, (hx, hy), R + 1)
        pygame.draw.circle(g, ELEC, (hx, hy), R)
        pygame.draw.circle(g, ELEC_HI, (hx - 1, hy - 1), max(1, R // 2))
    # ombra a terra
    sx, sy = camera.world_to_screen(p.x * ts, p.y * ts)
    sh = pygame.Surface((12, 5), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 70), sh.get_rect())
    surface.blit(sh, (sx - 6, sy - 2))


def draw_wall_charge(surface, camera, w, now):
    """Carica su un muro (visibile a tutti): badge + / - sul punto colpito,
    anello che pulsa e scintille; lampeggia nell'ultimo secondo."""
    ts = config.TILE_SIZE
    c = w["c"]
    x, y = camera.world_to_screen(c.x * ts, (c.y - 0.5) * ts)
    left = w["until"] - now
    if left <= 0:
        return
    if left < 1.0 and (now * 8.0) % 1.0 < 0.35:
        return
    dk, md, hi = sign_cols(w["sign"])
    pulse = 0.5 + 0.5 * math.sin(now * 6.0)
    R = int(0.35 * ts + 3 * pulse)
    g = pygame.Surface((R * 2 + 4, R * 2 + 4), pygame.SRCALPHA)
    pygame.draw.circle(g, (*md, 60), (R + 2, R + 2), R)
    pygame.draw.circle(g, (*md, 200), (R + 2, R + 2), R, 1)
    surface.blit(g, (x - R - 2, y - R - 2))
    rnd = random.Random(int(now * 12) + w["tx"] * 31 + w["ty"])
    for _ in range(2):
        an = rnd.uniform(0, math.tau)
        x0, y0 = x + math.cos(an) * R, y + math.sin(an) * R
        pygame.draw.line(surface, ELEC, (x0, y0), (x0 + rnd.uniform(-3, 3), y0 + rnd.uniform(-3, 3)))
    blit_badge(surface, x, y, w["sign"])


def draw_ion_trail(surface, camera, tr, now):
    """Scia Ionica: corsia gialla che crepita con piccoli "+" rossi."""
    ts = config.TILE_SIZE
    a, b = tr["a"], tr["b"]
    left = tr["end"] - now
    fade = max(0.0, min(1.0, left / 0.4)) * max(0.0, min(1.0, (now - tr["start"]) / 0.1))
    if fade <= 0:
        return
    ax, ay = camera.world_to_screen(a.x * ts, a.y * ts)
    bx, by = camera.world_to_screen(b.x * ts, b.y * ts)
    minx, miny = min(ax, bx) - 16, min(ay, by) - 16
    g = pygame.Surface((abs(bx - ax) + 32, abs(by - ay) + 32), pygame.SRCALPHA)
    A, B = (ax - minx, ay - miny), (bx - minx, by - miny)
    pygame.draw.line(g, (*ELEC, int(40 * fade)), A, B, 7)
    pygame.draw.line(g, (*ELEC_HI, int(60 * fade)), A, B, 2)
    rnd = random.Random(int(now * 16) + int(a.x * 7))
    _zig(g, A, B, (ELEC_DK, ELEC, ELEC_HI), int(220 * fade), 0.15 * ts, 0.3 * ts, rnd, 1, False)
    L = math.hypot(B[0] - A[0], B[1] - A[1])
    n = max(1, int(L / (0.9 * ts)))
    for i in range(n):
        u = (i + 0.5) / n
        px, py = A[0] + (B[0] - A[0]) * u, A[1] + (B[1] - A[1]) * u - 4 - math.sin(now * 5 + i) * 2
        pygame.draw.line(g, (*POS, int(255 * fade)), (px - 2, py), (px + 2, py))
        pygame.draw.line(g, (*POS, int(255 * fade)), (px, py - 2), (px, py + 2))
    surface.blit(g, (minx, miny))


def _pillar_sprite(ts, sign):
    """Pilastro di Bombagnete: grande calamita a FERRO DI CAVALLO in piedi
    (arco in alto, due gambe), corpo del colore della polarità e punte
    d'acciaio in basso; contorno scuro, luce da in alto a sinistra, gamba
    destra in ombra. Disegnata pixel per pixel (in cache)."""
    w = max(14, int(0.85 * ts)) | 1
    h = max(20, int(1.35 * ts))
    leg = max(4, w // 4)
    ro = w / 2.0
    ri = ro - leg
    cx = (w - 1) / 2.0
    cy = ro
    tip = max(4, h // 5)
    dk, md, hi = sign_cols(sign)
    shade = tuple(int(c * 0.72) for c in md)

    def inside(x, y):
        if x < 0 or y < 0 or x >= w or y >= h:
            return False
        if y < cy:
            d = math.hypot(x - cx, y - cy)
            return ri <= d <= ro
        return x < leg or x >= w - leg

    out = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    for y in range(-1, h + 1):
        for x in range(-1, w + 1):
            if inside(x, y):
                continue
            if any(inside(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                out.set_at((x + 1, y + 1), (20, 18, 28))
    for y in range(h):
        for x in range(w):
            if not inside(x, y):
                continue
            col = md
            if y >= h - tip:
                col = STEEL if x < w / 2 else (120, 132, 156)
                if y == h - tip:
                    col = STEEL_DK
            elif x > cx + 1 and y >= cy - 1:
                col = shade
            # luce: bordo esterno in alto/sinistra e bordo interno della gamba destra
            if (not inside(x - 1, y) or not inside(x, y - 1)) and (x < cx or y < cy - ri * 0.3):
                col = STEEL_HI if y >= h - tip else hi
            out.set_at((x + 1, y + 1), col)
    return out


_pillar_cache: dict = {}


def draw_mag_pillar(surface, camera, pl, now):
    """Bombagnete (visibile a tutti): prima dell'arrivo un mirino che si chiude;
    poi il pilastro-calamita, l'area di 6 tile tratteggiata col colore della
    polarità, linee di campo che corrono verso il centro (attira) o fuori
    (respinge) e la barra del tempo."""
    ts = config.TILE_SIZE
    c = pl["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    sign = pl["sign"]
    dk, md, hi = sign_cols(sign)
    R = int(pl["radius"] * ts)
    if now < pl["land"]:
        u = max(0.0, min(1.0, (now - pl["start"]) / max(1e-6, pl["land"] - pl["start"])))
        g, o = _layer(int(0.9 * ts))
        r = int(0.9 * ts * (1.4 - 0.9 * u))
        pygame.draw.ellipse(g, (*md, 160), pygame.Rect(o[0] - r, o[1] - r // 2, r * 2, r), 2)
        pygame.draw.ellipse(g, (0, 0, 0, int(60 + 80 * u)),
                            pygame.Rect(o[0] - int(0.4 * ts), o[1] - int(0.2 * ts),
                                        int(0.8 * ts), int(0.4 * ts)))
        surface.blit(g, (cx - o[0], cy - o[1]))
        # il pilastro cade dall'alto
        key = (ts, sign)
        spr = _pillar_cache.get(key) or _pillar_cache.setdefault(key, _pillar_sprite(ts, sign))
        drop = int((1.0 - u) * 4 * ts)
        surface.blit(spr, (cx - spr.get_width() // 2, cy - spr.get_height() + 4 - drop))
        return
    left = pl["end"] - now
    fade = max(0.0, min(1.0, left / 0.4))
    g, o = _layer(R)
    rect = pygame.Rect(o[0] - R, o[1] - R // 2, R * 2, R)
    pygame.draw.ellipse(g, (*md, int(26 * fade)), rect)
    n = 40
    for i in range(0, n, 2):   # bordo tratteggiato che gira
        a0 = i / n * math.tau + now * 0.5 * (1 if sign > 0 else -1)
        a1 = a0 + math.tau / n
        pygame.draw.line(g, (*md, int(210 * fade)),
                         (o[0] + math.cos(a0) * R, o[1] + math.sin(a0) * R * 0.5),
                         (o[0] + math.cos(a1) * R, o[1] + math.sin(a1) * R * 0.5), 2)
    # linee di campo radiali: granelli che scorrono (verso il centro: attira i "-"
    # se il pilastro è "+", ecc.: qui solo il movimento ciclico)
    for k in range(10):
        an = k / 10 * math.tau + 0.2
        q = (now * 0.7 + k * 0.37) % 1.0
        for j in range(3):
            qq = (q + j * 0.12) % 1.0
            rr = R * (0.18 + 0.8 * qq)
            x = o[0] + math.cos(an) * rr
            y = o[1] + math.sin(an) * rr * 0.5
            al = int(170 * fade * (1.0 - abs(qq - 0.5) * 1.6))
            if al > 0:
                g.fill((*hi, al), pygame.Rect(int(x), int(y), 2, 2))
    surface.blit(g, (cx - o[0], cy - o[1]))
    # ombra + pilastro
    sh = pygame.Surface((int(0.9 * ts), int(0.4 * ts)), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 90), sh.get_rect())
    surface.blit(sh, (cx - sh.get_width() // 2 + 2, cy - sh.get_height() // 2 + 2))
    key = (ts, sign)
    spr = _pillar_cache.get(key) or _pillar_cache.setdefault(key, _pillar_sprite(ts, sign))
    surface.blit(spr, (cx - spr.get_width() // 2, cy - spr.get_height() + 4))
    rnd = random.Random(int(now * 14) + pl.get("tx", 0))
    top_y = cy - spr.get_height() + 6
    for _ in range(2):   # scariche tra i poli
        x0 = cx + rnd.uniform(-0.25, 0.25) * ts
        pygame.draw.line(surface, ELEC, (x0, top_y), (x0 + rnd.uniform(-4, 4), top_y - rnd.uniform(2, 6)))
    blit_badge(surface, cx, top_y - 10, sign, 1)
    if left > 0.0:
        bw = int(0.6 * ts)
        bx, by = cx - bw // 2, top_y - 19
        pygame.draw.rect(surface, (20, 20, 30), pygame.Rect(bx - 1, by - 1, bw + 2, 4))
        tot = max(0.1, pl["end"] - pl["land"])
        pygame.draw.rect(surface, md, pygame.Rect(bx, by, int(bw * min(1.0, left / tot)), 2))


def draw_mag_field(surface, camera, z, now):
    """Campo Elettrico (visibile a tutti): area gialla che crepita sul bordo,
    simboli della polarità che galleggiano dentro, barra del tempo."""
    ts = config.TILE_SIZE
    c = z["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    R = int(z["radius"] * ts)
    left = z["end"] - now
    fade = max(0.0, min(1.0, left / 0.5)) * max(0.0, min(1.0, (now - z["start"]) / 0.25))
    if fade <= 0:
        return
    sign = z["sign"]
    dk, md, hi = sign_cols(sign)
    g, o = _layer(R)
    rect = pygame.Rect(o[0] - R, o[1] - R // 2, R * 2, R)
    pygame.draw.ellipse(g, (*ELEC, int(34 * fade)), rect)
    # griglia di "binari" elettrici (linee diagonali tenui dentro l'ellisse)
    step = max(6, int(0.9 * ts))
    for gx in range(-R, R + 1, step):
        x0 = o[0] + gx
        h = int(math.sqrt(max(0.0, 1.0 - (gx / R) ** 2)) * R * 0.5)
        if h > 2:
            pygame.draw.line(g, (*ELEC, int(40 * fade)), (x0, o[1] - h), (x0, o[1] + h))
    pygame.draw.ellipse(g, (*ELEC_DK, int(200 * fade)), rect, 3)
    rnd = random.Random(int(now * 18))
    n = 48
    pts = []
    for i in range(n + 1):   # bordo che crepita
        an = i / n * math.tau
        j = rnd.uniform(-2, 2)
        pts.append((o[0] + math.cos(an) * (R + j), o[1] + math.sin(an) * (R + j) * 0.5))
    pygame.draw.lines(g, (*ELEC, int(230 * fade)), False, pts, 1)
    for k in range(5):   # scariche che corrono a terra dentro l'area
        an = rnd.uniform(0, math.tau)
        rr = R * rnd.uniform(0.15, 0.8)
        x0, y0 = o[0] + math.cos(an) * rr, o[1] + math.sin(an) * rr * 0.5
        a2 = rnd.uniform(0, math.tau)
        L = rnd.uniform(0.4, 0.9) * ts
        _zig(g, (x0, y0), (x0 + math.cos(a2) * L, y0 + math.sin(a2) * L * 0.5),
             (ELEC_DK, ELEC, ELEC_HI), int(200 * fade), 0.08 * ts, 0.2 * ts, rnd, 2, False)
    # simboli della polarità che salgono piano
    for k in range(9):
        an = k * 2.399 + 0.5
        rr = R * (0.25 + 0.6 * ((k * 0.37) % 1.0))
        x = o[0] + math.cos(an) * rr
        y = o[1] + math.sin(an) * rr * 0.5 - ((now * 0.6 + k * 0.29) % 1.0) * 10
        al = int(200 * fade)
        pygame.draw.line(g, (*md, al), (x - 2, y), (x + 2, y))
        if sign > 0:
            pygame.draw.line(g, (*md, al), (x, y - 2), (x, y + 2))
    surface.blit(g, (cx - o[0], cy - o[1]))
    blit_badge(surface, cx, cy - R // 2 - 10, sign, 1, int(255 * fade))
    if left > 0.0:
        bw = int(0.8 * ts)
        bx, by = cx - bw // 2, cy - R // 2 - 19
        pygame.draw.rect(surface, (20, 20, 30), pygame.Rect(bx - 1, by - 1, bw + 2, 4))
        tot = max(0.1, z["end"] - z["start"])
        pygame.draw.rect(surface, ELEC, pygame.Rect(bx, by, int(bw * min(1.0, left / tot)), 2))


def draw_mag_link(surface, camera, ln, now):
    """Interazione in corso: trascinamento = linee di campo viola tese tra i
    due (o verso l'ancora); spinta = scia di scariche dietro chi vola via."""
    ts = config.TILE_SIZE
    a, b = ln.get("a"), ln.get("b")
    if a is None or b is None:
        return
    ax, ay = camera.world_to_screen(a.x * ts, (a.y - 0.4) * ts)
    bx, by = camera.world_to_screen(b.x * ts, (b.y - 0.4) * ts)
    kind = ln.get("kind")
    minx, miny = min(ax, bx) - 20, min(ay, by) - 20
    g = pygame.Surface((abs(bx - ax) + 40, abs(by - ay) + 40), pygame.SRCALPHA)
    A, B = (ax - minx, ay - miny), (bx - minx, by - miny)
    rnd = random.Random(int(now * 24) + ln.get("a_id", 0))
    if kind == "push":
        dx, dy = A[0] - B[0], A[1] - B[1]
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        for k in (-1, 0, 1):   # tre strisce dietro
            px, py = -uy * k * 4, ux * k * 4
            tail = (A[0] - ux * 0.9 * ts + px, A[1] - uy * 0.9 * ts + py)
            pygame.draw.line(g, (*ELEC, 200), (A[0] + px, A[1] + py), tail, 1)
        _zig(g, (A[0] - ux * 0.3 * ts, A[1] - uy * 0.3 * ts),
             (A[0] - ux * 1.2 * ts, A[1] - uy * 1.2 * ts),
             (ELEC_DK, ELEC, ELEC_HI), 220, 0.12 * ts, 0.25 * ts, rnd, 1, False)
    else:
        _field_lines(g, A, B, FIELD, 200, n=3, bulge=0.1, phase=now * 3.0, width=1)
        _zig(g, A, B, ((60, 30, 110), FIELD, (240, 226, 255)), 200, 0.1 * ts, 0.35 * ts, rnd, 1, False)
    surface.blit(g, (minx, miny))


# --- sulle unità --------------------------------------------------------------


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Badge della carica (+ rosso / - blu) sopra la barra della vita,
    visibile a tutti; lampeggia nell'ultimo secondo. Se l'unità è anche
    agitata (Hatterene) si sposta a destra della vena di rabbia."""
    sign = getattr(u, "mag_sign", 0)
    left = getattr(u, "mag_until", -1.0) - now
    if not sign or left <= 0:
        return
    if left < 1.0 and (now * 8.0) % 1.0 < 0.35:
        return
    r = int(getattr(u, "radius", 0.5) * ts)
    x = gx + (9 if getattr(u, "agitated_until", -1.0) > now else 0)
    bob = 1 if (now * 3.0) % 1.0 < 0.5 else 0
    y = gy - 2 * r - 17 - bob
    # piccolo alone del colore della carica
    dk, md, hi = sign_cols(sign)
    halo = pygame.Surface((17, 17), pygame.SRCALPHA)
    pygame.draw.circle(halo, (*md, 70), (8, 8), 8)
    surface.blit(halo, (x - 8, y - 8))
    blit_badge(surface, x, y, sign)


# --- interfaccia ---------------------------------------------------------------


def count_charged(world, p, now, visible=None) -> int:
    """Nemici con una carica di questo Magnemite (per l'icona della passiva)."""
    if getattr(p, "passive_id", None) != "magnetismo":
        return 0
    n = 0
    for e in world.pokemons():
        if (e.team != p.team and e.alive and getattr(e, "mag_sign", 0)
                and getattr(e, "mag_until", -1.0) > now
                and (visible is None or visible(e))):
            n += 1
    return n


def draw_magnet_icon(surface, cx, cy, s):
    """Calamita a ferro di cavallo (rossa/blu con poli d'acciaio): icona della
    passiva Magnetismo."""
    w = s * 2
    rect = pygame.Rect(cx - s, cy - s, w, w)
    pygame.draw.arc(surface, (20, 20, 30), rect.inflate(2, 2), 0, math.pi, s // 2 + 2)
    pygame.draw.arc(surface, POS, rect, math.pi / 2, math.pi, s // 2)
    pygame.draw.arc(surface, NEG, rect, 0, math.pi / 2, s // 2)
    leg = s // 2
    pygame.draw.rect(surface, (20, 20, 30), pygame.Rect(cx - s - 1, cy - 1, leg + 2, s + 2))
    pygame.draw.rect(surface, (20, 20, 30), pygame.Rect(cx + s - leg - 1, cy - 1, leg + 2, s + 2))
    pygame.draw.rect(surface, POS, pygame.Rect(cx - s, cy, leg, s // 2))
    pygame.draw.rect(surface, NEG, pygame.Rect(cx + s - leg, cy, leg, s // 2))
    pygame.draw.rect(surface, STEEL_HI, pygame.Rect(cx - s, cy + s // 2, leg, s - s // 2))
    pygame.draw.rect(surface, STEEL_HI, pygame.Rect(cx + s - leg, cy + s // 2, leg, s - s // 2))


# --- mirino ---------------------------------------------------------------------


def draw_aim(surface, S, ts, ox, oy, nx, ny, dist, move) -> bool:
    """Mirino delle mosse della linea. Ritorna False se la forma non è sua."""
    shape = move.shape
    rng = move.range
    if shape == "magbolt":
        ex, ey = ox + nx * rng, oy + ny * rng
        w = move.radius
        px, py = -ny * w, nx * w
        col = WEB if move.effects.get("pierce") else ELEC
        for sg in (1, -1):
            pygame.draw.line(surface, col, S(ox + px * sg, oy + py * sg),
                             S(ex + px * sg, ey + py * sg), 1)
        pygame.draw.line(surface, (255, 255, 255), S(ox, oy), S(ex, ey), 1)
        return True
    if shape == "magfield":
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        d = min(dist, rng)
        cx, cy = S(ox + nx * d, oy + ny * d)
        pygame.draw.circle(surface, NEG, (cx, cy), int(move.radius * ts), 1)
        blit_badge(surface, cx, cy - int(0.6 * ts), -1)
        return True
    if shape == "voltdash":
        d = min(dist, rng)
        ex, ey = ox + nx * d, oy + ny * d
        w = move.radius
        px, py = -ny * w, nx * w
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        for sg in (1, -1):
            pygame.draw.line(surface, ELEC, S(ox + px * sg, oy + py * sg),
                             S(ex + px * sg, ey + py * sg), 1)
        pygame.draw.circle(surface, (255, 255, 255), S(ex, ey), max(3, int(0.3 * ts)), 1)
        return True
    if shape in ("magpillar", "magterrain"):
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        d = min(dist, rng)
        cx, cy = S(ox + nx * d, oy + ny * d)
        sign = polarity()
        dk, md, hi = sign_cols(sign)
        pygame.draw.circle(surface, md, (cx, cy), int(move.radius * ts), 2)
        if shape == "magpillar":
            pygame.draw.rect(surface, (255, 255, 255),
                             pygame.Rect(cx - ts // 2, cy - ts // 2, ts, ts), 1)
        blit_badge(surface, cx, cy - int(0.7 * ts), sign, 2)
        return True
    return False
