"""Grafica della linea Teddiursa > Ursaring > Ursaluna: effetti istantanei
(handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (tre artigliate, pugno che cala dall'alto, crepe nel
terreno, onda d'urto schiacciata a terra, sassi che saltano, "Z" del sonno,
vasetto di miele, luna) e disegni persistenti letti dallo stato del Match a
ogni frame (nuvola di Profumino, Luna Piena in arrivo, Terremoto) e sulle unità
(vasetti di miele sotto la barra della vita, alone di Luna Piena, Z di Riposo).

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config
from .noivern_fx import draw_soundarc

HONEY = (244, 178, 48)
HONEY_HI = (255, 230, 140)
HONEY_DK = (132, 70, 18)
CLAW = (246, 240, 226)
CLAW_DK = (70, 46, 34)
FIST = (255, 138, 40)
FIST_HI = (255, 218, 140)
FIST_DK = (120, 44, 14)
EARTH = (150, 108, 66)
EARTH_HI = (206, 170, 118)
EARTH_DK = (70, 48, 30)
MOON = (240, 226, 160)
MOON_HI = (255, 252, 228)
MOON_DK = (120, 96, 60)
ROAR = (255, 104, 60)
ROAR_DK = (120, 26, 18)
SLEEP = (150, 200, 255)
SLEEP_DK = (40, 64, 120)
GUTS = (255, 84, 54)

HONEY_DEX = (216, 217, 901)    # Teddiursa, Ursaring, Ursaluna (online il passive_id altrui non arriva)
MOON_GROW = 1.3                # Luna Piena: sprite più grande


def _al(f, k=2.0):
    return int(255 * max(0.0, min(1.0, f * k)))


def _crack_pts(rnd, cx, cy, ang, L, segs=4, jit=0.35):
    pts = [(cx, cy)]
    x, y = cx, cy
    for i in range(segs):
        a = ang + rnd.uniform(-jit, jit)
        step = L / segs
        x += math.cos(a) * step
        y += math.sin(a) * step * 0.62   # schiacciato: è a terra
        pts.append((x, y))
    return pts


def draw_jar(surface, x, y, s, full, alpha=255):
    """Vasetto di miele pixel-art (s = lato del corpo in px)."""
    body = pygame.Rect(x, y + 1, s, s)
    if full:
        pygame.draw.rect(surface, (*HONEY_DK, alpha), body.inflate(2, 2))
        pygame.draw.rect(surface, (*HONEY, alpha), body)
        surface.fill((*HONEY_HI, alpha), pygame.Rect(x, y + 1, max(1, s // 3), max(1, s // 3)))
    else:
        pygame.draw.rect(surface, (20, 16, 14, alpha), body.inflate(2, 2))
        pygame.draw.rect(surface, (64, 54, 46, alpha), body)
    lid = pygame.Rect(x - 1, y - 1, s + 2, 2)
    pygame.draw.rect(surface, (*((214, 196, 170) if full else (90, 84, 78)), alpha), lid)


# --- forme per FXSystem._draw_shapes ------------------------------------------

SHAPES = ("claw3", "fist", "groundcrack", "groundring", "pebble", "zzz", "honeypot", "moonglow")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "claw3":
        # Tre artigliate parallele che spazzano un arco davanti (Lacerazione):
        # il tratto si disegna man mano, poi resta e sbiadisce.
        cx, cy = S(*s["c"])
        r = s["r"] * ts
        half = s.get("half", 1.0)
        ang = s.get("ang", 0.0)
        cols = s.get("cols", (CLAW_DK, CLAW, (255, 255, 255)))
        reveal = min(1.0, t / 0.3)
        al = _al(f, 2.2)
        n = 12
        wmax = max(2, int(0.07 * ts))
        for k in (-1, 0, 1):
            rr = r + k * 0.2 * ts
            pts = []
            for i in range(int(n * reveal) + 1):
                u = i / n
                aa = ang - half + 2 * half * u
                pts.append((cx + math.cos(aa) * rr, cy + math.sin(aa) * rr * 0.8))
            # graffio affusolato: spesso al centro, a punta alle estremità
            for i in range(len(pts) - 1):
                u = (i + 0.5) / n
                w = max(1, int(round(wmax * math.sin(math.pi * u))))
                pygame.draw.line(overlay, (*cols[0], al), pts[i], pts[i + 1], w + 2)
            for i in range(len(pts) - 1):
                u = (i + 0.5) / n
                w = max(1, int(round(wmax * math.sin(math.pi * u))))
                pygame.draw.line(overlay, (*cols[1], al), pts[i], pts[i + 1], w)
                if w >= 2:
                    pygame.draw.line(overlay, (*cols[2], al), pts[i], pts[i + 1], 1)
    elif kind == "fist":
        # Pugno arancione che cala dall'alto e si schianta (Martelpugno).
        cx, cy = S(*s["c"])
        u = min(1.0, t / 0.32)                  # caduta
        drop = (1.0 - u * u) * 1.8 * ts
        size = s.get("size", 0.42) * ts
        squash = 1.0 if u < 1.0 else 1.0 + 0.25 * min(1.0, (t - 0.32) / 0.1)
        al = _al(f, 2.5)
        w, h = size * 1.15 * squash, size / squash
        x, y = cx - w / 2, cy - h - drop - 0.25 * ts
        if u < 1.0:   # linee di velocità sopra il pugno
            for k in (-1, 0, 1):
                lx = cx + k * w * 0.32
                pygame.draw.line(overlay, (*FIST_HI, al // 2), (lx, y - 0.7 * ts), (lx, y - 0.1 * ts), 2)
        body = pygame.Rect(int(x), int(y), int(w), int(h))
        pygame.draw.rect(overlay, (*FIST_DK, al), body.inflate(4, 4), border_radius=max(2, int(h * 0.3)))
        pygame.draw.rect(overlay, (*FIST, al), body, border_radius=max(2, int(h * 0.3)))
        # nocche (in basso: il pugno colpisce di sotto)
        for k in range(1, 4):
            kx = int(x + w * k / 4)
            pygame.draw.line(overlay, (*FIST_DK, al), (kx, int(y + h * 0.45)), (kx, int(y + h - 1)), 1)
        # pollice e luce in alto a sinistra
        pygame.draw.rect(overlay, (*FIST_DK, al), pygame.Rect(int(x - w * 0.12), int(y + h * 0.25),
                                                             max(2, int(w * 0.22)), max(2, int(h * 0.45))))
        pygame.draw.rect(overlay, (*FIST_HI, al), pygame.Rect(int(x + 2), int(y + 2),
                                                             max(2, int(w * 0.4)), max(1, int(h * 0.2))))
        # polsino
        pygame.draw.rect(overlay, (*FIST_DK, al), pygame.Rect(int(x + w * 0.2), int(y - h * 0.3),
                                                             int(w * 0.6), max(2, int(h * 0.32))))
    elif kind == "groundcrack":
        # Crepe nel terreno che si aprono dal centro (spezzate, schiacciate).
        cx, cy = S(*s["c"])
        rnd = random.Random(s.get("seed", 1))
        L = s.get("r", 1.0) * ts * min(1.0, t / 0.18 + 0.15)
        al = _al(f, 1.6)
        n = s.get("n", 6)
        for k in range(n):
            ang = k / n * math.tau + rnd.uniform(-0.5, 0.5)
            pts = _crack_pts(rnd, cx, cy, ang, L * rnd.uniform(0.35, 1.0), segs=4, jit=0.6)
            pygame.draw.lines(overlay, (*EARTH_DK, al), False, pts, 2)
            pygame.draw.lines(overlay, (24, 16, 10, al), False, pts, 1)
            if rnd.random() < 0.6:   # ramificazione
                bx, by = pts[2]
                br = _crack_pts(rnd, bx, by, ang + rnd.choice((-0.9, 0.9)), L * 0.25, segs=2)
                pygame.draw.lines(overlay, (24, 16, 10, al), False, br, 1)
            # bordo chiaro della crepa (luce da alto-sinistra)
            hi = [(x - 1, y - 1) for x, y in pts[:3]]
            pygame.draw.lines(overlay, (*EARTH_HI, al // 2), False, hi, 1)
    elif kind == "groundring":
        # Onda d'urto schiacciata a terra (prospettiva): anello marrone a 3 strati.
        cx, cy = S(*s["c"])
        r = (s["r0"] + (s["r1"] - s["r0"]) * min(1.0, t * s.get("speed", 1.0))) * ts
        if r < 2:
            return
        al = _al(f, 2.0)
        cols = s.get("cols", (EARTH_DK, EARTH, EARTH_HI))
        rect = pygame.Rect(int(cx - r), int(cy - r * 0.55), int(r * 2), int(r * 1.1))
        w = max(2, int(s.get("w", 0.12) * ts))
        pygame.draw.ellipse(overlay, (*cols[0], al), rect.inflate(2, 2), w + 2)
        pygame.draw.ellipse(overlay, (*cols[1], al), rect, w)
        pygame.draw.arc(overlay, (*cols[2], al), rect, math.pi * 0.55, math.pi * 1.05, 1)
    elif kind == "pebble":
        # Sasso che salta a parabola e ricade (terreno che trema).
        age = s["maxlife"] - s["life"]
        u = age / s["maxlife"]
        px, py = S(s["c"][0] + s["v"][0] * u, s["c"][1] + s["v"][1] * u)
        hop = 4.0 * u * (1.0 - u) * s.get("h", 0.5) * ts
        r = max(1, int(s.get("sz", 0.07) * ts))
        al = _al(f, 3.0)
        pygame.draw.rect(overlay, (*EARTH_DK, al), pygame.Rect(px - r - 1, py - hop - r - 1, r * 2 + 2, r * 2 + 2))
        pygame.draw.rect(overlay, (*s.get("col", EARTH), al), pygame.Rect(px - r, py - hop - r, r * 2, r * 2))
        overlay.fill((*EARTH_HI, al), pygame.Rect(px - r, py - hop - r, max(1, r), max(1, r)))
    elif kind == "zzz":
        # "Z" che sale ondeggiando e si ingrandisce (sonno di Riposo).
        age = s["maxlife"] - s["life"]
        u = age / s["maxlife"]
        px, py = S(s["c"][0] + math.sin(u * 5.0 + s.get("ph", 0)) * 0.18 + u * 0.4,
                   s["c"][1] - u * 1.0)
        z = max(3, int((0.14 + 0.16 * u) * ts))
        al = _al(f, 2.5)
        pts = [(px - z, py - z), (px + z, py - z), (px - z, py + z), (px + z, py + z)]
        pygame.draw.lines(overlay, (*SLEEP_DK, al), False, pts, 4)
        pygame.draw.lines(overlay, (*SLEEP, al), False, pts, 2)
    elif kind == "honeypot":
        # Vasetto di miele che sale e sbiadisce (vasetto preso / usato).
        age = s["maxlife"] - s["life"]
        px, py = S(s["c"][0], s["c"][1] - age * s.get("rise", 1.2))
        sz = max(4, int(0.22 * ts))
        draw_jar(overlay, int(px - sz / 2), int(py - sz), sz, True, _al(f, 2.0))
    elif kind == "moonglow":
        # Luna che si accende sopra il punto d'atterraggio (Luna Piena).
        cx, cy = S(*s["c"])
        r = s.get("r", 0.6) * ts * (0.6 + 0.4 * min(1.0, t / 0.2))
        py = cy - s.get("h", 1.6) * ts
        al = _al(f, 1.6)
        g = pygame.Surface((int(r * 4) + 4, int(r * 4) + 4), pygame.SRCALPHA)
        o = int(r * 2) + 2
        pygame.draw.circle(g, (*MOON, al // 4), (o, o), int(r * 1.9))
        pygame.draw.circle(g, (*MOON, al // 3), (o, o), int(r * 1.4))
        pygame.draw.circle(g, (*MOON_DK, al), (o, o), int(r) + 1)
        pygame.draw.circle(g, (*MOON, al), (o, o), int(r))
        pygame.draw.circle(g, (*MOON_HI, al), (o - int(r * 0.3), o - int(r * 0.3)), max(1, int(r * 0.45)))
        for dx, dy, cr in ((0.3, 0.2, 0.2), (-0.2, 0.4, 0.13), (0.45, -0.25, 0.1)):   # crateri
            pygame.draw.circle(g, (*MOON_DK, al // 2), (o + int(r * dx), o + int(r * dy)), max(1, int(r * cr)))
        overlay.blit(g, (cx - o, py - o))


# --- handler degli eventi (FXSystem._FX_STYLES) --------------------------------


def _cone_args(e):
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return None
    return o, d, float(e.get("range", 2.5)), math.radians(float(e.get("angle", 60))), math.atan2(d[1], d[0])


def fx_ursaslash(fx, e, col):
    """Lacerazione: tre artigliate larghe che spazzano tutto l'arco davanti."""
    ca = _cone_args(e)
    if ca is None:
        return
    o, d, rng, half, ang = ca
    fx._shape(kind="claw3", c=o, ang=ang, r=rng * 0.62, half=half * 0.8, col=CLAW, life=0.32)
    for _ in range(10):
        a = ang + random.uniform(-half, half)
        rr = random.uniform(0.6, rng)
        fx._add(o[0] + math.cos(a) * rr, o[1] + math.sin(a) * rr, math.cos(a) * 2.2,
                math.sin(a) * 2.2, random.uniform(0.2, 0.35), random.choice((CLAW, HONEY_HI)), 1)


def fx_hammerarm(fx, e, col):
    """Martelpugno: pugno arancione che cala dall'alto, poi crepe, onda e polvere."""
    ca = _cone_args(e)
    if ca is None:
        return
    o, d, rng, half, ang = ca
    c = (o[0] + d[0] * rng * 0.62, o[1] + d[1] * rng * 0.62)
    fx._shape(kind="fist", c=c, size=0.5, col=FIST, life=0.5)
    fx._shape(kind="groundcrack", c=c, r=0.9, n=5, seed=random.randint(0, 9999), col=EARTH,
              life=0.7, wait=0.16)
    fx._shape(kind="groundring", c=c, r0=0.2, r1=1.2, w=0.1, col=FIST, life=0.35, wait=0.16,
              cols=(FIST_DK, FIST, FIST_HI))
    fx._shape(kind="flash", c=c, r=0.25, col=FIST_HI, life=0.08, wait=0.16)
    for k in range(8):
        a = k / 8 * math.tau
        fx._shape(kind="pebble", c=c, v=(math.cos(a) * 0.9, math.sin(a) * 0.5), h=0.5, sz=0.06,
                  col=EARTH, life=0.45, wait=0.16)
    fx._dust(c, 0.4, n=4)


def fx_roar(fx, e, col):
    """Ruggito: onde rosso-arancio a zig-zag che si allargano nel cono."""
    ca = _cone_args(e)
    if ca is None:
        return
    o, d, rng, half, ang = ca
    for k in range(4):
        fx._shape(kind="soundarc", c=o, ang=ang, r0=0.4, r1=rng, half=half, w=0.1 - 0.015 * k,
                  col=ROAR, life=0.45, wait=0.07 * k, jag=0.06,
                  cols=(ROAR_DK, ROAR, (255, 214, 170)))


def fx_rest(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=1.0, r1=0.3, col=SLEEP, life=0.45, wd=0.08)
    for _ in range(10):
        fx._add(c[0] + random.uniform(-0.5, 0.5), c[1] + random.uniform(-0.2, 0.2),
                random.uniform(-0.2, 0.2), -random.uniform(0.8, 1.4), random.uniform(0.4, 0.7),
                random.choice((SLEEP, (170, 240, 120))), 1)


def fx_bodyslam(fx, e, col):
    """Corposcontro: impatto a terra, stelline e polvere."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="groundring", c=c, r0=0.2, r1=1.1, w=0.1, col=EARTH, life=0.35)
    for k in range(5):
        a = -math.pi / 2 + (k - 2) * 0.5
        fx._add(c[0], c[1] - 0.4, math.cos(a) * 2.6, math.sin(a) * 2.0, 0.35,
                random.choice(((255, 230, 120), CLAW)), 2)
    fx._dust(c, 0.5, n=4)


def fx_bulldoze(fx, e, col):
    """Battiterra: il terreno si spacca, onde d'urto e sassi che saltano su
    tutta l'area per qualche istante (la terra trema)."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.4))
    seed = random.randint(0, 9999)
    fx._shape(kind="groundcrack", c=c, r=r * 0.75, n=6, seed=seed, col=EARTH, life=0.9)
    fx._shape(kind="groundring", c=c, r0=0.3, r1=r, w=0.08, col=EARTH, life=0.4)
    for k in range(18):   # sassi che saltellano su tutta l'area, sfalsati
        a = random.uniform(0, math.tau)
        rr = random.uniform(0.2, 0.95) * r
        p = (c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr * 0.75)
        fx._shape(kind="pebble", c=p, v=(random.uniform(-0.2, 0.2), random.uniform(-0.1, 0.1)),
                  h=random.uniform(0.15, 0.35), sz=random.uniform(0.04, 0.08),
                  col=random.choice((EARTH, EARTH_HI)), life=0.3, wait=random.uniform(0.0, 0.5))
    fx._dust(c, r * 0.6, n=6)


def fx_honeyscent(fx, e, col):
    """Profumino (al lancio): spruzzo di gocce di miele sul punto."""
    c = e.get("c")
    if c is None:
        return
    for _ in range(18):
        a = random.uniform(0, math.tau)
        sp = random.uniform(0.8, 2.4)
        fx._add(c[0], c[1] - 0.3, math.cos(a) * sp, math.sin(a) * sp * 0.6 - 0.8,
                random.uniform(0.4, 0.7), random.choice((HONEY, HONEY_HI, (255, 170, 200))), 2)


def fx_honeyclaws(fx, e, col):
    """Unghiaguzze: artigli che brillano e scintille che salgono."""
    c = e.get("c")
    if c is None:
        return
    for k in range(3):
        x = c[0] - 0.25 + k * 0.25
        fx._shape(kind="beam", a=(x + 0.18, c[1] - 0.9), b=(x - 0.12, c[1] - 0.35), w=0.04,
                  col=CLAW, life=0.3, wait=0.05 * k)
    fx._shape(kind="ring", c=c, r0=1.1, r1=0.3, col=GUTS, life=0.4, wd=0.08)
    for _ in range(8):
        fx._add(c[0] + random.uniform(-0.4, 0.4), c[1] + random.uniform(-0.2, 0.2),
                random.uniform(-0.2, 0.2), -random.uniform(1.2, 2.0), random.uniform(0.4, 0.6),
                random.choice((CLAW, GUTS)), 1)


def fx_honeygain(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="honeypot", c=(c[0], c[1] - 0.9), col=HONEY, life=0.9)
    for _ in range(6):
        fx._add(c[0] + random.uniform(-0.3, 0.3), c[1] - 0.6, random.uniform(-0.4, 0.4),
                -random.uniform(0.6, 1.2), random.uniform(0.4, 0.7), HONEY_HI, 1)


def fx_honeyheal(fx, e, col):
    """Miele consumato: vasetto, gocce dorate e cura che sale."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="honeypot", c=(c[0], c[1] - 0.9), col=HONEY, life=0.7, rise=0.6)
    fx._shape(kind="ring", c=c, r0=1.1, r1=0.2, col=HONEY, life=0.5, wd=0.1)
    for _ in range(14):
        fx._add(c[0] + random.uniform(-0.5, 0.5), c[1] + random.uniform(-0.2, 0.2),
                random.uniform(-0.2, 0.2), -random.uniform(1.0, 2.0), random.uniform(0.5, 0.8),
                random.choice((HONEY, HONEY_HI, (170, 240, 120))), 2)


def fx_fullmoonland(fx, e, col):
    """Luna Piena all'atterraggio: la luna si accende in cielo, onde d'urto
    color luna, crepe, sassi e polvere."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.4))
    fx._shape(kind="moonglow", c=c, r=0.5, h=2.7, col=MOON, life=0.9)
    fx._shape(kind="flash", c=c, r=1.0, col=MOON_HI, life=0.12)
    fx._shape(kind="groundring", c=c, r0=0.3, r1=r, w=0.16, col=MOON, life=0.45,
              cols=(MOON_DK, MOON, MOON_HI))
    fx._shape(kind="groundring", c=c, r0=0.2, r1=r * 0.75, w=0.1, col=EARTH, life=0.5, wait=0.08)
    fx._shape(kind="groundcrack", c=c, r=r * 0.7, n=8, seed=random.randint(0, 9999), col=EARTH, life=1.0)
    for k in range(12):
        a = k / 12 * math.tau
        fx._shape(kind="pebble", c=c, v=(math.cos(a) * r * 0.6, math.sin(a) * r * 0.35),
                  h=random.uniform(0.4, 0.8), sz=random.uniform(0.05, 0.09), col=EARTH, life=0.55)
    fx._dust(c, r * 0.7, n=16)


def fx_mooncleave(fx, e, col):
    """Attacco base di Luna Piena: artigliata color luna sull'area colpita."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 1.3))
    fx._shape(kind="claw3", c=c, ang=random.uniform(0, math.tau), r=r * 0.55, half=1.1,
              col=MOON, life=0.25, cols=(MOON_DK, MOON, MOON_HI))


def fx_earthquakepulse(fx, e, col):
    """Terremoto (ogni onda): anello di terra, crepe, sassi che saltano."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 3.5))
    fx._shape(kind="groundring", c=c, r0=0.5, r1=r, w=0.14, col=EARTH, life=0.45)
    for _ in range(10):
        a = random.uniform(0, math.tau)
        rr = random.uniform(0.6, 1.0) * r
        p = (c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr * 0.75)
        fx._shape(kind="pebble", c=p, v=(0.0, 0.0), h=random.uniform(0.15, 0.3),
                  sz=random.uniform(0.04, 0.07), col=random.choice((EARTH, EARTH_HI)),
                  life=0.3, wait=random.uniform(0.0, 0.2))
    fx._dust(c, r * 0.9, n=6)


STYLES = {
    "ursaslash": fx_ursaslash, "hammerarm": fx_hammerarm, "roar": fx_roar, "rest": fx_rest,
    "bodyslam": fx_bodyslam, "bulldoze": fx_bulldoze, "honeyscent": fx_honeyscent,
    "honeclaws": fx_honeyclaws, "honeygain": fx_honeygain, "honeyheal": fx_honeyheal,
    "fullmoonland": fx_fullmoonland, "mooncleave": fx_mooncleave,
    "earthquakepulse": fx_earthquakepulse,
}


# --- disegni persistenti (stato del Match) -------------------------------------


def draw_honey_zone(surface, camera, z, now):
    """Profumino: nuvola dorata-rosata traslucida a terra, bordo tratteggiato,
    volute che girano e gocce/cuoricini che salgono piano."""
    ts = config.TILE_SIZE
    c = z["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    R = z["radius"] * ts
    life = max(0.0, min(1.0, (now - z["start"]) / 0.3, (z["end"] - now) / 0.5))
    w, h = int(R * 2) + 8, int(R * 1.3) + 8
    g = pygame.Surface((w, h), pygame.SRCALPHA)
    o = (w // 2, h // 2)
    pink = (255, 170, 190)
    # macchie di nuvola sovrapposte (forma morbida ma a bordi netti)
    rnd = random.Random(int(z["start"] * 1000))
    for k in range(9):
        a = rnd.uniform(0, math.tau) + now * 0.25 * (1 if k % 2 else -1)
        rr = rnd.uniform(0.2, 0.55) * R
        px, py = o[0] + math.cos(a) * rr, o[1] + math.sin(a) * rr * 0.6
        br = rnd.uniform(0.35, 0.55) * R
        pygame.draw.ellipse(g, (*(HONEY_HI if k % 3 else pink), int(30 * life)),
                            pygame.Rect(px - br, py - br * 0.6, br * 2, br * 1.2))
    # bordo tratteggiato che gira piano
    n = 36
    for i in range(0, n, 2):
        a0 = i / n * math.tau + now * 0.4
        a1 = (i + 1) / n * math.tau + now * 0.4
        p0 = (o[0] + math.cos(a0) * R, o[1] + math.sin(a0) * R * 0.6)
        p1 = (o[0] + math.cos(a1) * R, o[1] + math.sin(a1) * R * 0.6)
        pygame.draw.line(g, (*HONEY_DK, int(200 * life)), p0, p1, 3)
        pygame.draw.line(g, (*HONEY_HI, int(220 * life)), p0, p1, 1)
    surface.blit(g, (cx - o[0], cy - o[1]))
    # gocce di profumo che salgono (cuoricini rosa e puntini dorati)
    for k in range(8):
        ph = (now * 0.6 + k / 8) % 1.0
        a = k * 2.4
        rr = (0.25 + 0.6 * ((k * 37) % 10) / 10) * R
        px = cx + math.cos(a) * rr + math.sin(now * 2 + k) * 3
        py = cy + math.sin(a) * rr * 0.6 - ph * 1.2 * ts
        al = int(220 * life * (1.0 - ph))
        if al <= 10:
            continue
        if k % 2:
            hcol = (255, 130, 170)
            pygame.draw.circle(surface, hcol, (int(px) - 1, int(py)), 2)
            pygame.draw.circle(surface, hcol, (int(px) + 2, int(py)), 2)
            pygame.draw.polygon(surface, hcol, [(px - 3, py + 1), (px + 4, py + 1), (px + 0.5, py + 5)])
        else:
            pygame.draw.rect(surface, HONEY_HI, pygame.Rect(int(px), int(py), 2, 2))


def draw_leap(surface, camera, lp, now):
    """Balzo in corso: per Luna Piena cerchio d'atterraggio che si chiude con la
    luna disegnata a terra (lo vedono anche i nemici); per i balzi brevi solo
    l'ombra del punto d'arrivo."""
    ts = config.TILE_SIZE
    c = lp["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    span = max(1e-6, lp["end"] - lp["start"])
    prog = max(0.0, min(1.0, (now - lp["start"]) / span))
    if lp.get("fx") != "fullmoon":
        r = int(0.5 * ts)
        pygame.draw.ellipse(surface, EARTH_DK, pygame.Rect(cx - r, cy - r // 2, r * 2, r), 1)
        return
    R = int(2.4 * ts)
    g = pygame.Surface((R * 2 + 6, R + 6), pygame.SRCALPHA)
    o = (R + 3, R // 2 + 3)
    rect = pygame.Rect(o[0] - R, o[1] - R // 2, R * 2, R)
    pygame.draw.ellipse(g, (*MOON_DK, int(50 + 60 * prog)), rect)
    pygame.draw.ellipse(g, (*MOON, 220), rect, 2)
    ir = max(2, int(R * (1.0 - prog)))
    pygame.draw.ellipse(g, (*MOON_HI, 220), pygame.Rect(o[0] - ir, o[1] - ir // 2, ir * 2, ir), 2)
    # falce di luna a terra al centro
    mr = int(0.5 * ts)
    pygame.draw.ellipse(g, (*MOON, 200), pygame.Rect(o[0] - mr, o[1] - mr // 2, mr * 2, mr))
    pygame.draw.ellipse(g, (*MOON_DK, 220), pygame.Rect(o[0] - mr // 3, o[1] - mr // 2 - 1, mr * 2, mr))
    surface.blit(g, (cx - o[0], cy - o[1]))


def draw_quake(surface, camera, q, now):
    """Terremoto: terreno che vibra attorno a Ursaluna (bordo dell'area a
    trattini che pulsa, crepe fisse che tremano, polvere)."""
    ts = config.TILE_SIZE
    c = q["c"]
    shake = random.choice((-1, 0, 1))
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    cx += shake
    R = q["radius"] * ts
    life = max(0.0, min(1.0, (now - q["start"]) / 0.2, (q["end"] - now) / 0.3))
    pulse = 0.5 + 0.5 * math.sin(now * 12.0)
    g = pygame.Surface((int(R * 2) + 8, int(R * 1.2) + 8), pygame.SRCALPHA)
    o = (g.get_width() // 2, g.get_height() // 2)
    rect = pygame.Rect(o[0] - R, o[1] - R * 0.55, R * 2, R * 1.1)
    pygame.draw.ellipse(g, (*EARTH_DK, int((40 + 30 * pulse) * life)), rect)
    n = 40
    for i in range(0, n, 2):
        a0, a1 = i / n * math.tau, (i + 1) / n * math.tau
        p0 = (o[0] + math.cos(a0) * R, o[1] + math.sin(a0) * R * 0.55)
        p1 = (o[0] + math.cos(a1) * R, o[1] + math.sin(a1) * R * 0.55)
        pygame.draw.line(g, (*EARTH_DK, int(220 * life)), p0, p1, 3)
        pygame.draw.line(g, (*EARTH_HI, int(200 * life)), p0, p1, 1)
    rnd = random.Random(int(q["start"] * 1000))
    for k in range(6):   # crepe corte attorno ai piedi (non attraversano tutta l'area)
        ang = k / 6 * math.tau + rnd.uniform(-0.4, 0.4)
        pts = _crack_pts(rnd, o[0], o[1] + R * 0.05, ang, R * rnd.uniform(0.22, 0.42), segs=3,
                         jit=0.6)
        pts = [(x + random.choice((-1, 0, 1)), y) for x, y in pts]
        pygame.draw.lines(g, (*EARTH_DK, int(230 * life)), False, pts, 3)
        pygame.draw.lines(g, (20, 14, 10, int(230 * life)), False, pts, 1)
    surface.blit(g, (cx - o[0], cy - o[1]))


# --- sulle unità --------------------------------------------------------------


def has_honey(u) -> bool:
    return (getattr(u, "passive_id", "") in ("miele", "dentistretti")
            or getattr(u, "dex", 0) in HONEY_DEX)


def grow(u, now) -> float:
    """Luna Piena: lo sprite cresce in 0,25 s, resta grande, poi torna normale."""
    end = getattr(u, "moon_until", -1.0)
    if end <= now:
        return 1.0
    k = min(1.0, (end - now) / 0.25)
    return 1.0 + (MOON_GROW - 1.0) * k


def draw_honey_pips(surface, u, cx, top_y, width):
    """Vasetti di miele sotto la barra della vita (visibili a tutti)."""
    n = int(getattr(u, "honey", 0))
    s, gap = 3, 2
    total = 3 * s + 2 * gap
    x = cx - total // 2
    y = top_y + 5
    for k in range(3):
        draw_jar(surface, x + k * (s + gap), y, s, k < n)


def draw_unit_under(surface, u, gx, gy, now, ts):
    """Sotto lo sprite: alone lunare di Luna Piena, bagliore rosso di Dentistretti."""
    if getattr(u, "moon_until", -1.0) > now:
        r = int(0.95 * ts)
        g = pygame.Surface((r * 2 + 4, r + 4), pygame.SRCALPHA)
        pulse = 0.5 + 0.5 * math.sin(now * 4.0)
        rect = pygame.Rect(2, 2, r * 2, r)
        pygame.draw.ellipse(g, (*MOON, int(50 + 30 * pulse)), rect)
        pygame.draw.ellipse(g, (*MOON_HI, 200), rect, 2)
        surface.blit(g, (gx - r - 2, gy - r // 2 - 2))
    elif getattr(u, "guts_active", False):
        r = int(0.7 * ts)
        g = pygame.Surface((r * 2 + 4, r + 4), pygame.SRCALPHA)
        pulse = 0.5 + 0.5 * math.sin(now * 7.0)
        pygame.draw.ellipse(g, (*GUTS, int(60 + 50 * pulse)), pygame.Rect(2, 2, r * 2, r), 2)
        surface.blit(g, (gx - r - 2, gy - r // 2 - 2))


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Sopra lo sprite: le "Z" di Riposo e i segni di Dentistretti."""
    if getattr(u, "rest_until", -1.0) > now:
        r = int(getattr(u, "radius", 0.5) * ts)
        top = gy - 2 * r
        for k in range(3):
            ph = (now * 0.8 + k / 3) % 1.0
            z = 1 + int(2 * ph)
            px = gx + r + 4 + int(ph * 8) + int(math.sin(now * 3 + k) * 2)
            py = top - int(ph * 10)
            pts = [(px - z, py - z), (px + z, py - z), (px - z, py + z), (px + z, py + z)]
            pygame.draw.lines(surface, SLEEP_DK, False, pts, 3)
            pygame.draw.lines(surface, SLEEP, False, pts, 1)
    elif getattr(u, "guts_active", False):
        # vena di rabbia rossa (pixel art) vicino alla testa
        top = gy - int(getattr(u, "radius", 0.5) * ts * 2.2)
        x, y = gx + int(0.35 * ts), top
        s = 2 + int(1 * (0.5 + 0.5 * math.sin(now * 8)))
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            pygame.draw.line(surface, (90, 10, 10), (x + dx * 1, y + dy * 1), (x + dx * (s + 2), y + dy * (s + 2)), 3)
            pygame.draw.line(surface, GUTS, (x + dx * 1, y + dy * 1), (x + dx * (s + 2), y + dy * (s + 2)), 1)
