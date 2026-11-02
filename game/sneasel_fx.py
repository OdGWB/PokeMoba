"""Grafica della linea Sneasel > Weavile / Sneasler: effetti istantanei
(handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (scheggia di ghiaccio in volo, fendente buio dritto,
moneta/sfera che vola ad arco, cristallo di brina, punta velenosa, stella
d'impatto) e disegni persistenti letti dallo stato del Match a ogni frame
(fango di Sporcolancio in volo e pozza tossica, balzi di Sneasler), sulle
unità (cure ridotte, cariche di Arraffalesto, ombra di Notte Fonda) e
nell'interfaccia (luna/sole di Sole e Luna).

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config
from .noivern_fx import draw_soundarc

ICE = (150, 220, 255)
ICE_HI = (240, 252, 255)
ICE_DK = (36, 82, 150)
DARK = (110, 76, 160)
DARK_HI = (214, 190, 255)
DARK_DK = (26, 16, 44)
CRIMSON = (226, 58, 82)        # piume di Weavile
CRIMSON_HI = (255, 170, 170)
CRIMSON_DK = (96, 14, 30)
GOLD = (250, 206, 70)
GOLD_HI = (255, 246, 180)
GOLD_DK = (136, 84, 18)
POISON = (178, 92, 214)
POISON_HI = (240, 196, 255)
POISON_DK = (64, 22, 92)
SLUDGE = (110, 62, 126)
SLUDGE_HI = (196, 126, 226)
SLUDGE_DK = (40, 18, 52)
TOXIC = (170, 226, 96)         # bolle tossiche
FIGHT = (240, 132, 60)
FIGHT_HI = (255, 230, 160)
FIGHT_DK = (110, 40, 14)
ROCK = (170, 140, 100)
ROCK_HI = (226, 204, 160)
ROCK_DK = (72, 54, 36)
GHOST = (150, 110, 230)
GHOST_DK = (40, 22, 90)
WHITE = (255, 255, 255)
HEAL = (110, 230, 130)
MOON = (232, 236, 255)
MOON_DK = (80, 96, 160)
SUN = (255, 196, 60)
SUN_HI = (255, 244, 170)
SUN_DK = (176, 70, 20)


def _al(f, k=2.0):
    return int(255 * max(0.0, min(1.0, f * k)))


def _rot(px, py, ca, sa):
    return px * ca - py * sa, px * sa + py * ca


# --- disegni base ---------------------------------------------------------------


def draw_shard(surface, cx, cy, ang, L, alpha=255):
    """Scheggia di ghiaccio: rombo allungato a punta in avanti, contorno scuro,
    corpo azzurro, faccia illuminata e filo bianco in alto a sinistra."""
    ca, sa = math.cos(ang), math.sin(ang)
    w = L * 0.3
    pts = [(L * 0.6, 0.0), (0.0, -w), (-L * 0.4, 0.0), (0.0, w)]
    poly = [(cx + x, cy + y) for x, y in (_rot(px, py, ca, sa) for px, py in pts)]
    pygame.draw.polygon(surface, (*ICE_DK, alpha), [(x, y) for x, y in poly])
    inner = [(cx + (x - cx) * 0.72, cy + (y - cy) * 0.72) for x, y in poly]
    pygame.draw.polygon(surface, (*ICE, alpha), inner)
    # faccia alta (verso la luce): mezzo rombo più chiaro
    top = [inner[0], inner[1], inner[2]]
    if (inner[1][1] > inner[3][1]):   # la faccia "alta" è quella con y minore
        top = [inner[0], inner[3], inner[2]]
    pygame.draw.polygon(surface, (*ICE_HI, alpha), [top[0], top[1], ((top[0][0] + top[2][0]) / 2,
                                                                     (top[0][1] + top[2][1]) / 2)])
    pygame.draw.line(surface, (*WHITE, alpha), top[0], top[1], 1)


def draw_flake(surface, cx, cy, r, alpha, col=ICE):
    """Cristallo di brina a sei punte (pixel art)."""
    for k in range(3):
        a = k * math.pi / 3
        dx, dy = math.cos(a) * r, math.sin(a) * r
        pygame.draw.line(surface, (*ICE_DK, alpha), (cx - dx, cy - dy), (cx + dx, cy + dy), 3)
    for k in range(3):
        a = k * math.pi / 3
        dx, dy = math.cos(a) * r, math.sin(a) * r
        pygame.draw.line(surface, (*col, alpha), (cx - dx, cy - dy), (cx + dx, cy + dy), 1)
    pygame.draw.circle(surface, (*WHITE, alpha), (int(cx), int(cy)), 1)


def draw_coin(surface, cx, cy, r, spin, alpha=255, cols=(GOLD_DK, GOLD, GOLD_HI)):
    """Moneta che gira: ellisse che si stringe e si allarga."""
    w = max(2, int(r * 2 * abs(math.cos(spin))))
    h = max(3, int(r * 2))
    rect = pygame.Rect(int(cx - w / 2), int(cy - h / 2), w, h)
    pygame.draw.ellipse(surface, (*cols[0], alpha), rect.inflate(2, 2))
    pygame.draw.ellipse(surface, (*cols[1], alpha), rect)
    if w > 3:
        pygame.draw.line(surface, (*cols[2], alpha), (rect.left + 1, rect.top + 2),
                         (rect.left + 1, rect.bottom - 3), 1)


def draw_moon_icon(surface, cx, cy, r, alpha=255):
    """Falce di luna (pixel art): disco chiaro, morso scuro a destra, crateri."""
    g = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
    o = r + 2
    pygame.draw.circle(g, (*MOON_DK, alpha), (o, o), r + 1)
    pygame.draw.circle(g, (*MOON, alpha), (o, o), r)
    pygame.draw.circle(g, (0, 0, 0, 0), (o + r // 2 + 1, o - r // 4), r)
    pygame.draw.circle(g, (*MOON_DK, alpha), (o - r // 2, o + r // 3), max(1, r // 5))
    pygame.draw.circle(g, (*WHITE, alpha), (o - r // 2, o - r // 2), max(1, r // 6))
    surface.blit(g, (cx - o, cy - o))


def draw_sun_icon(surface, cx, cy, r, now=0.0, alpha=255):
    """Sole (pixel art): disco arancio con raggi che girano piano."""
    for k in range(8):
        a = k * math.pi / 4 + now * 0.6
        x0, y0 = cx + math.cos(a) * (r + 2), cy + math.sin(a) * (r + 2)
        x1, y1 = cx + math.cos(a) * (r + 2 + r * 0.55), cy + math.sin(a) * (r + 2 + r * 0.55)
        pygame.draw.line(surface, SUN_DK, (x0, y0), (x1, y1), 4)
        pygame.draw.line(surface, SUN, (x0, y0), (x1, y1), 2)
    pygame.draw.circle(surface, SUN_DK, (cx, cy), r + 1)
    pygame.draw.circle(surface, SUN, (cx, cy), r)
    pygame.draw.circle(surface, SUN_HI, (cx - r // 3, cy - r // 3), max(2, r // 2))


_HEART = (".XX.XX.",
          "XXXXXXX",
          "XXXXXXX",
          ".XXXXX.",
          "..XXX..",
          "...X...")
_CRACK = ((3, 1), (2, 2), (3, 3), (3, 4))


def draw_broken_heart(surface, x, y, s=1):
    """Cure ridotte: cuoricino verde (pixel art 7x6) spezzato da una crepa rossa."""
    w, h = len(_HEART[0]), len(_HEART)
    ox, oy = x - (w * s) // 2, y - (h * s) // 2
    for yy, row in enumerate(_HEART):   # contorno scuro: ogni pixel allargato di 1
        for xx, ch in enumerate(row):
            if ch == "X":
                surface.fill((16, 34, 20), pygame.Rect(ox + xx * s - 1, oy + yy * s - 1, s + 2, s + 2))
    for yy, row in enumerate(_HEART):
        for xx, ch in enumerate(row):
            if ch == "X":
                col = (190, 255, 200) if (xx, yy) in ((1, 1), (1, 2)) else HEAL
                surface.fill(col, pygame.Rect(ox + xx * s, oy + yy * s, s, s))
    for xx, yy in _CRACK:
        surface.fill((210, 30, 44), pygame.Rect(ox + xx * s, oy + yy * s, s, s))


# --- forme per FXSystem._draw_shapes ------------------------------------------

SHAPES = ("iceshard", "darkslash", "coin", "flake", "stab", "impactstar")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "iceshard":
        # Scheggia in volo da A a B (velocissima) con scia di brina.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.6)
        ang = math.atan2(by - ay, bx - ax)
        px, py = ax + (bx - ax) * u, ay + (by - ay) * u
        al = _al(f, 4.0)
        L = s.get("size", 0.42) * ts
        for k in range(1, 4):   # scia: puntini di brina che restano indietro
            uk = max(0.0, u - 0.09 * k)
            qx, qy = ax + (bx - ax) * uk, ay + (by - ay) * uk
            q = max(1, int(3 - k * 0.7))
            pygame.draw.rect(overlay, (*(ICE_HI if k == 1 else ICE), al * (4 - k) // 4),
                             pygame.Rect(int(qx) - q // 2, int(qy) - q // 2, q, q))
        pygame.draw.line(overlay, (*ICE, al // 2), (ax + (bx - ax) * max(0.0, u - 0.3),
                                                    ay + (by - ay) * max(0.0, u - 0.3)), (px, py), 1)
        if u < 1.0:
            draw_shard(overlay, px, py, ang, L, al)
    elif kind == "darkslash":
        # Fendente dritto: lama sottile e leggermente curva, affusolata ai capi,
        # che si disegna da A a B e sbiadisce (contorno scuro, corpo, filo chiaro).
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        L = math.hypot(bx - ax, by - ay)
        if L < 2:
            return
        ux, uy = (bx - ax) / L, (by - ay) / L
        nx, ny = uy, -ux                      # normale verso l'alto
        reveal = min(1.0, t / 0.2)
        w0 = s.get("w", 0.09) * ts
        bulge = s.get("bulge", 0.22) * ts
        cols = s.get("cols", (DARK_DK, DARK, DARK_HI))
        al = _al(f, 2.2)
        n = 14
        mid, wid = [], []
        for i in range(n + 1):
            u = i / n * reveal
            k = math.sin(math.pi * u)
            mid.append((ax + ux * L * u + nx * bulge * k, ay + uy * L * u + ny * bulge * k))
            wid.append(w0 * k + 0.4)

        def band(extra, scale):
            top = [(x + nx * (w * scale + extra), y + ny * (w * scale + extra))
                   for (x, y), w in zip(mid, wid)]
            bot = [(x - nx * (w * scale + extra), y - ny * (w * scale + extra))
                   for (x, y), w in zip(mid, wid)]
            return top, bot

        top, bot = band(1.2, 1.0)
        pygame.draw.polygon(overlay, (*cols[0], al), top + bot[::-1])
        top, bot = band(0.0, 0.85)
        pygame.draw.polygon(overlay, (*cols[1], al), top + bot[::-1])
        pygame.draw.lines(overlay, (*cols[2], al), False, top[1:-1], 1)
    elif kind == "coin":
        # Moneta (o sfera, style="orb") che vola ad arco da A a B girando.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.8)
        h = s.get("h", 0.8) * ts
        px = ax + (bx - ax) * u
        py = ay + (by - ay) * u - h * 4 * u * (1 - u)
        al = _al(f, 3.0)
        r = s.get("r", 0.12) * ts
        if s.get("style") == "orb":
            cols = s.get("cols", (CRIMSON_DK, CRIMSON, CRIMSON_HI))
            pygame.draw.circle(overlay, (*cols[0], al), (int(px), int(py)), int(r) + 1)
            pygame.draw.circle(overlay, (*cols[1], al), (int(px), int(py)), int(r))
            pygame.draw.circle(overlay, (*cols[2], al), (int(px - r / 3), int(py - r / 3)),
                               max(1, int(r / 2)))
        else:
            draw_coin(overlay, px, py, r, t * 18 + s.get("ph", 0.0), al)
    elif kind == "flake":
        cx, cy = S(*s["c"])
        r = s.get("r", 0.25) * ts * (0.5 + 0.5 * min(1.0, t * 4))
        draw_flake(overlay, cx, cy - t * s.get("rise", 0.0) * ts, r, _al(f, 2.0),
                   s.get("col", ICE))
    elif kind == "stab":
        # Punta velenosa che scatta in avanti e si ritira.
        ox, oy = S(*s["o"])
        ang = s.get("ang", 0.0)
        ext = math.sin(math.pi * min(1.0, t / 0.6))
        L = s.get("len", 1.8) * ts * (0.2 + 0.8 * ext)
        w = s.get("w", 0.18) * ts
        ca, sa = math.cos(ang), math.sin(ang)
        base = s.get("base", 0.3) * ts
        pts = [(base, -w), (base + L, 0.0), (base, w)]
        poly = [(ox + x, oy + y) for x, y in (_rot(px, py, ca, sa) for px, py in pts)]
        cols = s.get("cols", (POISON_DK, POISON, POISON_HI))
        al = _al(f, 2.5)
        pygame.draw.polygon(overlay, (*cols[0], al), poly)
        inner = [(ox + x, oy + y) for x, y in (_rot(px, py, ca, sa) for px, py in
                                               [(base + 2, -w * 0.55), (base + L - 3, 0.0),
                                                (base + 2, w * 0.55)])]
        pygame.draw.polygon(overlay, (*cols[1], al), inner)
        pygame.draw.line(overlay, (*cols[2], al), inner[0], inner[1], 1)
    elif kind == "impactstar":
        # Stella d'impatto spigolosa (colpi di Picchiaduro, agguato).
        cx, cy = S(*s["c"])
        r = s.get("r", 0.4) * ts * (0.6 + 0.4 * min(1.0, t * 5))
        rot = s.get("rot", 0.0)
        n = s.get("n", 7)
        pts = []
        for i in range(n * 2):
            rr = r if i % 2 == 0 else r * 0.45
            aa = rot + i * math.pi / n
            pts.append((cx + math.cos(aa) * rr, cy + math.sin(aa) * rr))
        cols = s.get("cols", (FIGHT_DK, FIGHT, FIGHT_HI))
        al = _al(f, 2.5)
        pygame.draw.polygon(overlay, (*cols[0], al), pts)
        inner = [(cx + (x - cx) * 0.7, cy + (y - cy) * 0.7) for x, y in pts]
        pygame.draw.polygon(overlay, (*cols[1], al), inner)
        pygame.draw.circle(overlay, (*cols[2], al), (int(cx - r * 0.12), int(cy - r * 0.12)),
                           max(1, int(r * 0.25)))


# --- handler degli eventi (FXSystem._FX_STYLES) --------------------------------


def _ab(e):
    a, b = e.get("a"), e.get("b")
    return (a, b) if a is not None and b is not None else None


def _cone_args(e):
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return None
    return o, d, float(e.get("range", 2.5)), math.radians(float(e.get("angle", 60))), math.atan2(d[1], d[0])


def _bits(fx, c, n, cols, speed=2.0, life=(0.2, 0.4), size=1, up=0.0):
    for _ in range(n):
        a = random.uniform(0, math.tau)
        v = random.uniform(0.4, 1.0) * speed
        fx._add(c[0], c[1], math.cos(a) * v, math.sin(a) * v - up, random.uniform(*life),
                random.choice(cols), size)


def fx_iceshard(fx, e, col):
    """Geloscheggia: scheggia che vola rapidissima, poi brina all'arrivo."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="iceshard", a=(a[0], a[1] - 0.25), b=(b[0], b[1] - 0.25), size=0.62,
              col=ICE, life=0.14)
    fx._shape(kind="flake", c=(b[0], b[1] - 0.25), r=0.28, col=ICE, life=0.3, wait=0.08)
    _bits(fx, (b[0], b[1] - 0.25), 7, (ICE, ICE_HI, WHITE), speed=2.4)


def fx_thief(fx, e, col):
    """Furto: graffio buio rapido con un luccichio."""
    ca = _cone_args(e)
    if ca is None:
        return
    o, d, rng, half, ang = ca
    c = (o[0] + d[0] * rng * 0.6, o[1] + d[1] * rng * 0.6 - 0.25)
    fx._shape(kind="claw", c=c, ang=ang + math.pi / 2, size=0.42, col=DARK, life=0.26)
    fx._shape(kind="flash", c=c, r=0.18, col=GOLD_HI, life=0.08, wait=0.1)


def fx_goldsteal(fx, e, col):
    """Furto a segno: monete che volano dal derubato a Sneasel."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    for k in range(3):
        fx._shape(kind="coin", a=(a[0], a[1] - 0.4), b=(b[0], b[1] - 0.4), h=0.9 + 0.25 * k,
                  r=0.11, ph=k * 1.3, col=GOLD, life=0.45, wait=0.06 * k)
    _bits(fx, (a[0], a[1] - 0.4), 6, (GOLD, GOLD_HI), speed=1.8)


def fx_sneaclaw(fx, e, col):
    """Ombrartigli (W): tre artigliate d'ombra e un fendente spettrale."""
    ca = _cone_args(e)
    if ca is None:
        return
    o, d, rng, half, ang = ca
    c = (o[0] + d[0] * rng * 0.62, o[1] + d[1] * rng * 0.62 - 0.3)
    fx._shape(kind="claw", c=c, ang=ang + math.pi / 2, size=0.6, col=GHOST, life=0.34)
    fx._shape(kind="flash", c=c, r=0.3, col=(226, 210, 255), life=0.08, wait=0.08)
    _bits(fx, c, 6, (GHOST, (226, 210, 255)), speed=1.6)


def fx_poisonjab(fx, e, col):
    """Velenpuntura: punta viola che scatta in avanti, bolle velenose."""
    ca = _cone_args(e)
    if ca is None:
        return
    o, d, rng, half, ang = ca
    fx._shape(kind="stab", o=(o[0], o[1] - 0.25), ang=ang, len=rng * 0.75, w=0.11, col=POISON,
              life=0.26)
    tip = (o[0] + d[0] * rng * 0.85, o[1] + d[1] * rng * 0.85 - 0.25)
    fx._shape(kind="flash", c=tip, r=0.2, col=POISON_HI, life=0.08, wait=0.1)
    _bits(fx, tip, 8, (POISON, POISON_HI, TOXIC), speed=1.4, size=2, up=0.8)


def _speedlines(fx, a, b, col=WHITE, n=4, life=0.22):
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 1e-6:
        return
    nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
    for k in range(n):
        off = (k - (n - 1) / 2) * 0.16
        sh = random.uniform(0.0, 0.35)
        fx._shape(kind="windline",
                  a=(a[0] + nx * off + (b[0] - a[0]) * sh, a[1] + ny * off - 0.25 + (b[1] - a[1]) * sh),
                  b=(b[0] + nx * off, b[1] + ny * off - 0.25), col=col, life=life + 0.03 * k)


def fx_quickattack(fx, e, col):
    """Rapidattacco: linee di velocità bianche e polvere all'arrivo."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    _speedlines(fx, a, b)
    fx._shape(kind="flash", c=(b[0], b[1] - 0.25), r=0.22, col=WHITE, life=0.07)
    fx._dust(b, 0.3, n=5)


def fx_quickdance(fx, e, col):
    """Rapidattacco + Danzaspada: lo scatto e poi le spade che girano."""
    fx_quickattack(fx, e, col)
    b = e.get("b")
    if b is None:
        return
    for k in range(4):
        fx._shape(kind="sword", c=b, a0=k * math.pi / 2, spin=8.0, orbit=0.75, size=0.36,
                  col=(220, 230, 250), life=0.6, wait=0.1)
    fx._shape(kind="ring", c=b, r0=0.3, r1=1.0, col=(240, 140, 110), life=0.35, wd=0.08,
              wait=0.1)


def fx_nightslash(fx, e, col):
    """Nottesferza: fendente buio dritto con il filo cremisi, schegge viola."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    a2, b2 = (a[0], a[1] - 0.3), (b[0], b[1] - 0.3)
    fx._shape(kind="darkslash", a=a2, b=b2, w=0.08, bulge=0.16, col=DARK, life=0.32,
              cols=(DARK_DK, DARK, CRIMSON_HI))
    for k in range(6):
        u = random.uniform(0.2, 1.0)
        c = (a2[0] + (b2[0] - a2[0]) * u, a2[1] + (b2[1] - a2[1]) * u)
        fx._add(c[0], c[1], random.uniform(-0.8, 0.8), random.uniform(-1.2, -0.2),
                random.uniform(0.25, 0.4), random.choice((DARK_HI, CRIMSON)), 1)


def fx_nightfall(fx, e, col):
    """Notte Fonda: il buio si chiude su Weavile (anelli che si stringono,
    fumo scuro), poi sparisce."""
    c = e.get("c")
    if c is None:
        return
    for k in range(3):   # anelli d'ombra che si stringono su di lui
        fx._shape(kind="soundarc", c=(c[0], c[1] - 0.2), ang=0.0, r0=1.7 - 0.35 * k, r1=0.2,
                  half=math.pi, w=0.08, col=DARK, life=0.5 + 0.1 * k,
                  cols=(DARK_DK, DARK, CRIMSON))
    fx._dust(c, 0.8, n=10, col=DARK_DK, speed=(0.4, 1.2))
    _bits(fx, (c[0], c[1] - 0.4), 10, (DARK, DARK_HI, CRIMSON), speed=1.2, up=0.6)


def fx_nightfallend(fx, e, col):
    """Fine dell'invisibilità: sbuffo d'ombra."""
    c = e.get("c")
    if c is None:
        return
    fx._dust(c, 0.5, n=6, col=DARK_DK, speed=(0.6, 1.4))
    fx._shape(kind="soundarc", c=(c[0], c[1] - 0.2), ang=0.0, r0=0.2, r1=0.9, half=math.pi,
              w=0.06, col=DARK, life=0.25, cols=(DARK_DK, DARK, DARK_HI))


def fx_ambushhit(fx, e, col):
    """Colpo dall'invisibilità: grande X cremisi e lampo."""
    ab = _ab(e)
    if ab is None:
        return
    _, b = ab
    c = (b[0], b[1] - 0.35)
    for s_ in (-1, 1):
        fx._shape(kind="darkslash", a=(c[0] - 0.6, c[1] - 0.5 * s_), b=(c[0] + 0.6, c[1] + 0.5 * s_),
                  w=0.07, bulge=0.08, col=CRIMSON, life=0.36,
                  cols=(CRIMSON_DK, CRIMSON, CRIMSON_HI))
    fx._shape(kind="flash", c=c, r=0.4, col=CRIMSON_HI, life=0.1)
    _bits(fx, c, 10, (CRIMSON, CRIMSON_HI, DARK_HI), speed=2.4)


def fx_snatch(fx, e, col):
    """Arraffalesto: sfere cremisi rubate al bersaglio volano su Weavile."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    for k in range(2):
        fx._shape(kind="coin", a=(a[0], a[1] - 0.4), b=(b[0], b[1] - 0.5), h=0.6 + 0.3 * k,
                  r=0.08, style="orb", col=CRIMSON, life=0.38, wait=0.07 * k)


def fx_beatuphit(fx, e, col):
    """Picchiaduro: stella d'impatto per colpo; i colpi degli alleati arrivano
    come ombre viola da direzioni diverse."""
    ab = _ab(e)
    if ab is None:
        return
    _, b = ab
    n = int(e.get("n", 1))
    rnd = random.Random(n * 977)
    c = (b[0] + rnd.uniform(-0.3, 0.3), b[1] - 0.35 + rnd.uniform(-0.25, 0.2))
    ally = bool(e.get("ally"))
    cols = (GHOST_DK, GHOST, (226, 210, 255)) if ally else (FIGHT_DK, FIGHT, FIGHT_HI)
    fx._shape(kind="impactstar", c=c, r=0.38, rot=rnd.uniform(0, 1), col=cols[1], life=0.2,
              cols=cols)
    if ally:   # l'ombra di un alleato che colpisce
        fx._shape(kind="claw", c=c, ang=rnd.uniform(0, math.pi), size=0.45, col=GHOST, life=0.24)
        a2 = rnd.uniform(0, math.tau)
        fx._shape(kind="windline", a=(c[0] + math.cos(a2) * 1.4, c[1] + math.sin(a2) * 1.0),
                  b=c, col=GHOST, life=0.18)
    _bits(fx, c, 4, (cols[1], cols[2]), speed=2.0)


def fx_beatup(fx, e, col):
    """Picchiaduro (scatto iniziale): linee di velocità arancio."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    _speedlines(fx, a, b, col=FIGHT, n=3)


def fx_direclaw(fx, e, col):
    """Dire Claw: tre artigliate velenose larghe."""
    ca = _cone_args(e)
    if ca is None:
        return
    o, d, rng, half, ang = ca
    fx._shape(kind="claw3", c=o, ang=ang, r=rng * 0.62, half=half * 0.8, col=POISON, life=0.32,
              cols=(POISON_DK, POISON, POISON_HI))
    for _ in range(8):
        a = ang + random.uniform(-half, half)
        rr = random.uniform(0.6, rng)
        fx._add(o[0] + math.cos(a) * rr, o[1] + math.sin(a) * rr, math.cos(a) * 1.6,
                math.sin(a) * 1.6 - 0.6, random.uniform(0.2, 0.4), random.choice((POISON, TOXIC)), 2)


def fx_direclaw_status(kind):
    def fx_status(fx, e, col):
        """Dire Claw: lo stato inflitto (veleno, paralisi o sonno)."""
        c = e.get("c")
        if c is None:
            return
        top = (c[0], c[1] - 0.8)
        if kind == "poison":
            _bits(fx, top, 10, (POISON, POISON_HI, TOXIC), speed=1.0, size=2, up=0.8)
        elif kind == "paralysis":
            for k in range(4):
                a = k * math.pi / 2 + random.uniform(-0.3, 0.3)
                fx._shape(kind="windline", a=top, b=(top[0] + math.cos(a) * 0.7, top[1] + math.sin(a) * 0.5),
                          col=(255, 226, 80), life=0.25)
            fx._shape(kind="flash", c=top, r=0.25, col=(255, 240, 140), life=0.1)
        else:
            fx._shape(kind="zzz", c=top, col=(150, 200, 255), life=0.8)
    return fx_status


def fx_cliffambushjump(fx, e, col):
    """Agguato dalla Rupe (stacco): sassi e polvere dove salta."""
    ab = _ab(e)
    if ab is None:
        return
    a, _ = ab
    fx._dust(a, 0.6, n=8, col=ROCK)
    for k in range(5):
        an = k / 5 * math.tau
        fx._shape(kind="pebble", c=a, v=(math.cos(an) * 0.8, math.sin(an) * 0.4), h=0.4,
                  sz=0.06, col=ROCK, life=0.4)


def fx_cliffambushland(fx, e, col):
    """Agguato dalla Rupe (atterraggio): crepe, onda di roccia, sassi, lampo."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="groundcrack", c=c, r=1.1, n=6, seed=random.randint(0, 9999), col=ROCK,
              life=0.8)
    fx._shape(kind="groundring", c=c, r0=0.2, r1=1.4, w=0.12, col=ROCK, life=0.38,
              cols=(ROCK_DK, ROCK, ROCK_HI))
    fx._shape(kind="impactstar", c=(c[0], c[1] - 0.35), r=0.45, rot=0.3, n=5, col=ROCK,
              life=0.16, cols=(ROCK_DK, ROCK, ROCK_HI))
    for k in range(5):
        an = k / 5 * math.tau + random.uniform(-0.4, 0.4)
        sp = random.uniform(0.9, 1.5)
        fx._shape(kind="pebble", c=c, v=(math.cos(an) * sp, math.sin(an) * sp * 0.55), h=0.6,
                  sz=0.06, col=ROCK, life=0.5)
    fx._dust(c, 0.6, n=8, col=ROCK)


def fx_climbjump(fx, e, col):
    """Scalaroccia (stacco): polvere e qualche sassolino."""
    ab = _ab(e)
    if ab is None:
        return
    a, _ = ab
    fx._dust(a, 0.4, n=6, col=ROCK)
    for k in range(3):
        an = math.pi + random.uniform(-1.0, 1.0)
        fx._shape(kind="pebble", c=a, v=(math.cos(an) * 0.6, math.sin(an) * 0.3), h=0.35,
                  sz=0.05, col=ROCK, life=0.35)


def fx_climbland(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._dust(c, 0.4, n=6, col=ROCK)
    fx._shape(kind="groundring", c=c, r0=0.15, r1=0.7, w=0.06, col=ROCK, life=0.25,
              cols=(ROCK_DK, ROCK, ROCK_HI))


def fx_sludgelob(fx, e, col):
    """Sporcolancio (al lancio): schizzi di fango dalle zampe."""
    return


def fx_sludgelobhit(fx, e, col):
    """Sporcolancio (impatto): splash di fango tossico e gocce."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.8))
    fx._shape(kind="groundring", c=c, r0=0.3, r1=r, w=0.14, col=SLUDGE, life=0.45,
              cols=(SLUDGE_DK, SLUDGE, SLUDGE_HI))
    fx._shape(kind="flash", c=(c[0], c[1] - 0.2), r=0.5, col=SLUDGE_HI, life=0.1)
    for _ in range(22):
        a = random.uniform(0, math.tau)
        v = random.uniform(1.0, 3.2)
        fx._add(c[0], c[1] - 0.2, math.cos(a) * v, math.sin(a) * v * 0.6 - 1.2,
                random.uniform(0.3, 0.55), random.choice((SLUDGE, SLUDGE_HI, TOXIC)), 2)


STYLES = {
    "iceshard": fx_iceshard, "thief": fx_thief, "goldsteal": fx_goldsteal,
    "sneaclaw": fx_sneaclaw, "poisonjab": fx_poisonjab, "quickattack": fx_quickattack,
    "quickdance": fx_quickdance, "nightslash": fx_nightslash, "nightfall": fx_nightfall,
    "nightfallend": fx_nightfallend, "ambushhit": fx_ambushhit, "snatch": fx_snatch,
    "beatup": fx_beatup, "beatuphit": fx_beatuphit, "direclaw": fx_direclaw,
    "direclaw_poison": fx_direclaw_status("poison"),
    "direclaw_paralysis": fx_direclaw_status("paralysis"),
    "direclaw_sleep": fx_direclaw_status("sleep"),
    "cliffambushjump": fx_cliffambushjump, "cliffambushland": fx_cliffambushland,
    "climbjump": fx_climbjump, "climbland": fx_climbland,
    "sludgelob": fx_sludgelob, "sludgelobhit": fx_sludgelobhit,
}


# --- disegni persistenti (stato del Match) -------------------------------------


def draw_lob(surface, camera, lb, now):
    """Sporcolancio: palla di fango che vola ad arco con il mirino a terra,
    poi una pozza tossica che ribolle e sbiadisce."""
    ts = config.TILE_SIZE
    c = lb["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    R = lb["radius"] * ts
    land = lb["land"]
    if now < land:
        span = max(1e-6, land - lb["start"])
        u = max(0.0, min(1.0, (now - lb["start"]) / span))
        # mirino che si chiude
        g = pygame.Surface((int(R * 2) + 6, int(R) + 6), pygame.SRCALPHA)
        o = (g.get_width() // 2, g.get_height() // 2)
        rect = pygame.Rect(o[0] - R, o[1] - R / 2, R * 2, R)
        pygame.draw.ellipse(g, (*SLUDGE_DK, int(40 + 50 * u)), rect)
        pygame.draw.ellipse(g, (*SLUDGE_HI, 200), rect, 2)
        ir = max(2, int(R * (1.0 - u)))
        pygame.draw.ellipse(g, (*POISON_HI, 200), pygame.Rect(o[0] - ir, o[1] - ir // 2, ir * 2, ir), 1)
        surface.blit(g, (cx - o[0], cy - o[1]))
        # palla in volo
        a = lb["a"]
        ax, ay = camera.world_to_screen(a.x * ts, a.y * ts)
        px = ax + (cx - ax) * u
        py = ay + (cy - ay) * u - 2.2 * ts * 4 * u * (1 - u) - 0.3 * ts
        r = int(0.36 * ts)
        pygame.draw.ellipse(surface, (0, 0, 0), pygame.Rect(int(ax + (cx - ax) * u) - r,
                                                            int(ay + (cy - ay) * u) - r // 3,
                                                            r * 2, max(2, r // 1.5)), 0)
        pygame.draw.circle(surface, SLUDGE_DK, (int(px), int(py)), r + 2)
        pygame.draw.circle(surface, SLUDGE, (int(px), int(py)), r)
        pygame.draw.circle(surface, SLUDGE_HI, (int(px - r * 0.35), int(py - r * 0.35)), max(2, r // 3))
        pygame.draw.rect(surface, TOXIC, pygame.Rect(int(px + r * 0.2), int(py + r * 0.1), 2, 2))
        for k in range(3):   # gocce che cadono dalla palla
            ph = (now * 3 + k / 3) % 1.0
            pygame.draw.rect(surface, SLUDGE, pygame.Rect(int(px - r * 0.5 + k * r * 0.5),
                                                          int(py + r + ph * 0.5 * ts), 2, 3))
        return
    life = max(0.0, min(1.0, (lb["end"] - now) / 0.8))
    g = pygame.Surface((int(R * 2) + 6, int(R) + 6), pygame.SRCALPHA)
    o = (g.get_width() // 2, g.get_height() // 2)
    rnd = random.Random(int(lb["start"] * 1000))
    for k in range(7):   # pozza irregolare: chiazze sovrapposte
        a = rnd.uniform(0, math.tau)
        rr = rnd.uniform(0.0, 0.5) * R
        br = rnd.uniform(0.35, 0.55) * R
        px, py = o[0] + math.cos(a) * rr, o[1] + math.sin(a) * rr * 0.5
        pygame.draw.ellipse(g, (*SLUDGE_DK, int(150 * life)),
                            pygame.Rect(px - br - 2, py - br / 2 - 1, br * 2 + 4, br + 2))
    for k in range(7):
        a = rnd.uniform(0, math.tau)
        rr = rnd.uniform(0.0, 0.5) * R
        br = rnd.uniform(0.35, 0.55) * R
        px, py = o[0] + math.cos(a) * rr, o[1] + math.sin(a) * rr * 0.5
        pygame.draw.ellipse(g, (*SLUDGE, int(150 * life)),
                            pygame.Rect(px - br, py - br / 2, br * 2, br))
    surface.blit(g, (cx - o[0], cy - o[1]))
    for k in range(6):   # bolle tossiche che scoppiano
        ph = (now * 1.4 + k / 6) % 1.0
        a = k * 2.3
        rr = (0.15 + 0.55 * ((k * 37) % 10) / 10) * R
        bx = cx + math.cos(a) * rr
        by = cy + math.sin(a) * rr * 0.5
        br = 1 + int(3 * ph)
        al = int(230 * life * (1.0 - ph * 0.6))
        if al <= 10:
            continue
        pygame.draw.circle(surface, SLUDGE_DK, (int(bx), int(by)), br + 1)
        pygame.draw.circle(surface, TOXIC if k % 2 else SLUDGE_HI, (int(bx), int(by)), br, 1)


def draw_claw_leap(surface, camera, lp, now):
    """Balzi di Sneasler: per l'Agguato il mirino di roccia sul bersaglio che si
    chiude (lo vede anche chi è preso di mira); per lo scavalcamento l'ombra
    del punto d'arrivo."""
    ts = config.TILE_SIZE
    c = lp["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    span = max(1e-6, lp["end"] - lp["start"])
    prog = max(0.0, min(1.0, (now - lp["start"]) / span))
    if lp.get("kind") != "ambush":
        r = int(0.45 * ts * (0.6 + 0.4 * prog))
        g = pygame.Surface((r * 2 + 2, r + 2), pygame.SRCALPHA)
        pygame.draw.ellipse(g, (0, 0, 0, int(60 + 60 * prog)), pygame.Rect(1, 1, r * 2, r))
        surface.blit(g, (cx - r - 1, cy - r // 2 - 1))
        return
    R = int(1.1 * ts)
    g = pygame.Surface((R * 2 + 6, R + 6), pygame.SRCALPHA)
    o = (R + 3, R // 2 + 3)
    rect = pygame.Rect(o[0] - R, o[1] - R // 2, R * 2, R)
    pygame.draw.ellipse(g, (*ROCK_DK, int(60 + 60 * prog)), rect)
    pygame.draw.ellipse(g, (*ROCK_HI, 230), rect, 2)
    ir = max(2, int(R * (1.0 - prog)))
    pygame.draw.ellipse(g, (*SUN, 230), pygame.Rect(o[0] - ir, o[1] - ir // 2, ir * 2, ir), 2)
    for k in range(3):   # tre artigli a terra
        x = o[0] + (k - 1) * R * 0.3
        pygame.draw.line(g, (*ROCK_DK, 230), (x - R * 0.1, o[1] - R * 0.18), (x + R * 0.1, o[1] + R * 0.18), 3)
    surface.blit(g, (cx - o[0], cy - o[1]))


# --- sulle unità --------------------------------------------------------------


def draw_unit_under(surface, u, gx, gy, now, ts):
    """Sotto lo sprite: ombra che fuma di Notte Fonda (visibile a chi la vede)."""
    if getattr(u, "nightfall_until", -1.0) > now:
        r = int(0.7 * ts)
        g = pygame.Surface((r * 2 + 4, r + 4), pygame.SRCALPHA)
        pulse = 0.5 + 0.5 * math.sin(now * 5.0)
        pygame.draw.ellipse(g, (*DARK_DK, int(90 + 40 * pulse)), pygame.Rect(2, 2, r * 2, r))
        pygame.draw.ellipse(g, (*CRIMSON, 160), pygame.Rect(2, 2, r * 2, r), 1)
        surface.blit(g, (gx - r - 2, gy - r // 2 - 2))
        for k in range(4):   # fumo che sale
            ph = (now * 0.9 + k / 4) % 1.0
            px = gx + int(math.sin(now * 2 + k * 1.7) * r * 0.6)
            py = gy - int(ph * 1.1 * ts)
            s = 2 + int(2 * (1 - ph))
            pygame.draw.rect(surface, DARK, pygame.Rect(px - s // 2, py, s, s))


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Sopra lo sprite: cure ridotte (cuore spezzato) e cariche di Arraffalesto
    (triangolini cremisi: in giù sul derubato, in su su Weavile)."""
    r = int(getattr(u, "radius", 0.5) * ts)
    top = gy - 2 * r - 8
    w = max(14, r * 2)
    if getattr(u, "healcut_until", -1.0) > now:
        draw_broken_heart(surface, gx - w // 2 - 6, top + 1)
    down, up = int(getattr(u, "snatch_down", 0)), int(getattr(u, "snatch_up", 0))
    n = down or up
    if n:   # sotto la barra della vita, centrati
        x0 = gx - (n * 6 - 1) // 2
        y = top + 5
        for k in range(n):
            x = x0 + k * 6
            pts = ([(x, y), (x + 4, y), (x + 2, y + 3)] if down
                   else [(x, y + 3), (x + 4, y + 3), (x + 2, y)])
            pygame.draw.polygon(surface, CRIMSON_DK, pts, 3)
            pygame.draw.polygon(surface, CRIMSON_HI if up else CRIMSON, pts)
