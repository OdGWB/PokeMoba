"""Grafica della linea Charcadet > Armarouge / Ceruledge: effetti istantanei
(handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (lingua di fuoco, goccia di lava, artigliata, mezzaluna,
spada) e disegni persistenti letti dallo stato del Match a ogni frame (Ombra
Notturna, Pulifumo, carica di Armor Cannon, Psichico, Lama dei Rancori) e
sulle unità (spallacci di Armatura Fluttuante, Ombrartigli, Calmamente).

Pixel art: forme piene a contorno scuro, niente smoothscale; luce da in alto a
sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

FIRE = (255, 138, 44)
FIRE_HI = (255, 226, 122)
FIRE_DK = (150, 36, 18)
LAVA = (255, 92, 28)
ROCK = (58, 40, 36)
SMOKE = (88, 76, 74)
SHADOW = (34, 18, 52)
SHADOW_MID = (86, 46, 130)
SHADOW_HI = (176, 120, 236)
CLAW = (154, 78, 236)          # artigliata d'ombra: viola acceso, si legge sui bersagli scuri
CLAW_HI = (236, 210, 255)
GHOST = (96, 128, 255)
GHOST_HI = (206, 222, 255)
GHOST_DK = (30, 34, 110)
PSY = (244, 104, 196)
PSY_HI = (255, 196, 240)
SMOG = (196, 186, 208)
SMOG_DK = (120, 104, 136)
GOLD = (246, 200, 84)
GOLD_HI = (255, 240, 170)
ARMOR = (206, 40, 52)
ARMOR_DK = (96, 14, 26)
HEAL = (140, 240, 150)
CALM = (120, 180, 255)


def _disc(surface, cx, cy, r, col, a, width=0):
    if r < 1:
        return
    g = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
    pygame.draw.circle(g, (*col, a), (r + 1, r + 1), r, width)
    surface.blit(g, (cx - r - 1, cy - r - 1))


def _ellipse(surface, rect, col, a, width=0):
    if rect.w < 2 or rect.h < 2:
        return
    g = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.ellipse(g, (*col, a), g.get_rect(), width)
    surface.blit(g, rect.topleft)


def _rot(px, py, ca, sa):
    return px * ca - py * sa, px * sa + py * ca


def draw_flame(surface, cx, cy, h, w, alpha=255, cols=(FIRE_DK, FIRE, FIRE_HI)):
    """Lingua di fuoco a goccia (punta in alto) a tre strati con contorno."""
    if h < 3:
        return
    for k, col in enumerate(cols):
        s = 1.0 - 0.3 * k
        hh, ww = h * s, w * s
        base = cy - (h - hh) * 0.15
        pts = [(cx, base - hh), (cx + ww * 0.55, base - hh * 0.35), (cx + ww * 0.5, base - hh * 0.05),
               (cx, base), (cx - ww * 0.5, base - hh * 0.05), (cx - ww * 0.55, base - hh * 0.35)]
        pygame.draw.polygon(surface, (*col, alpha), pts)


def draw_claw(surface, cx, cy, ang, size, prog, alpha=255):
    """Tre graffi d'ombra paralleli e curvi che si tracciano (prog 0..1)."""
    ca, sa = math.cos(ang), math.sin(ang)
    for k in (-1, 0, 1):
        pts = []
        n = 6
        for i in range(n + 1):
            u = i / n * prog
            x = (u - 0.5) * size * 2.0
            y = k * size * 0.38 + math.sin(u * math.pi) * size * 0.28
            rx, ry = _rot(x, y, ca, sa)
            pts.append((cx + rx, cy + ry))
        if len(pts) < 2:
            continue
        pygame.draw.lines(surface, (*SHADOW, alpha), False, pts, max(4, int(size * 0.36)))
        pygame.draw.lines(surface, (*CLAW, alpha), False, pts, max(2, int(size * 0.22)))
        pygame.draw.lines(surface, (*CLAW_HI, alpha), False, pts, 1)


def draw_crescent(surface, cx, cy, ang, r, thick, alpha=255, cols=(GHOST_DK, GHOST, GHOST_HI)):
    """Mezzaluna di un fendente (due archi concentrici sfalsati)."""
    half = 0.85
    for k, col in enumerate(cols):
        t = thick * (1.0 - 0.32 * k)
        outer, inner = [], []
        n = 12
        for i in range(n + 1):
            a = ang - half + 2 * half * i / n
            bulge = math.sin(i / n * math.pi)
            outer.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
            rr = r - t * bulge
            inner.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        pygame.draw.polygon(surface, (*col, alpha), outer + inner[::-1])


def draw_sword(surface, cx, cy, ang, size, alpha=255):
    """Spadina d'acciaio (Danzaspada): lama chiara, elsa dorata."""
    ca, sa = math.cos(ang), math.sin(ang)

    def P(x, y):
        rx, ry = _rot(x, y, ca, sa)
        return (cx + rx, cy + ry)

    blade = [P(size, 0), P(size * 0.1, -size * 0.13), P(-size * 0.25, -size * 0.1),
             P(-size * 0.25, size * 0.1), P(size * 0.1, size * 0.13)]
    pygame.draw.polygon(surface, (60, 70, 96, alpha), blade)
    pygame.draw.polygon(surface, (220, 230, 250, alpha),
                        [((x - cx) * 0.78 + cx, (y - cy) * 0.78 + cy) for x, y in blade])
    pygame.draw.line(surface, (*GOLD, alpha), P(-size * 0.28, -size * 0.3), P(-size * 0.28, size * 0.3), 2)
    pygame.draw.line(surface, (120, 70, 30, alpha), P(-size * 0.3, 0), P(-size * 0.55, 0), 2)


def draw_pauldron(surface, cx, cy, ang, size, alpha=255, cracked=False):
    """Spallaccio di Armarouge: piastra rossa a scudo con bordo dorato."""
    ca, sa = math.cos(ang), math.sin(ang)

    def P(x, y):
        rx, ry = _rot(x, y, ca, sa)
        return (cx + rx, cy + ry)

    pts = [P(-size, -size * 0.55), P(size * 0.6, -size * 0.7), P(size, 0),
           P(size * 0.6, size * 0.7), P(-size, size * 0.55)]
    base = (110, 60, 60) if cracked else ARMOR
    pygame.draw.polygon(surface, (*ARMOR_DK, alpha), [((x - cx) * 1.2 + cx, (y - cy) * 1.2 + cy)
                                                       for x, y in pts])
    pygame.draw.polygon(surface, (*base, alpha), pts)
    pygame.draw.polygon(surface, (*(GOLD if not cracked else (150, 120, 70)), alpha), pts, 1)
    pygame.draw.line(surface, (*(GOLD_HI if not cracked else (170, 150, 120)), alpha),
                     P(-size * 0.6, -size * 0.3), P(size * 0.4, -size * 0.4), 1)
    if cracked:
        pygame.draw.lines(surface, (30, 10, 10, alpha), False,
                          [P(-size * 0.2, -size * 0.5), P(0, 0), P(-size * 0.3, size * 0.4)], 1)


# --- forme per FXSystem._draw_shapes ------------------------------------------
SHAPES = ("flametongue", "lavablob", "claw", "crescent", "sword")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    age = s["maxlife"] - s["life"]
    if kind == "flametongue":
        # Lingua di fuoco: sale, si allunga e poi si spegne restringendosi.
        cx, cy = S(s["c"][0] + s.get("v", (0, 0))[0] * age, s["c"][1] + s.get("v", (0, 0))[1] * age)
        h = s.get("h", 0.6) * ts * (0.55 + 0.45 * math.sin(min(1.0, t * 2.0) * math.pi * 0.5)) * (0.45 + 0.55 * f)
        w = s.get("w", 0.35) * ts * (0.6 + 0.4 * f)
        cols = s.get("cols", (FIRE_DK, FIRE, FIRE_HI))
        draw_flame(overlay, cx, cy + int(math.sin(age * 30 + s.get("ph", 0)) * 1), h, w,
                   int(255 * min(1.0, f * 2.5)), cols)
    elif kind == "lavablob":
        # Goccia di lava lanciata in aria: parabola, poi schizza a terra.
        u = min(1.0, t / 0.85)
        gx = s["c"][0] + s["v"][0] * u
        gy = s["c"][1] + s["v"][1] * u
        z = s.get("z", 1.2) * 4.0 * u * (1.0 - u)
        cx, cy = S(gx, gy)
        r = max(2, int(s.get("r", 0.12) * ts))
        if u < 1.0:
            _ell = pygame.Rect(cx - r, cy - r // 2, r * 2, r)          # ombra a terra
            pygame.draw.ellipse(overlay, (0, 0, 0, int(70 * f)), _ell)
            py = cy - int(z * ts)
            pygame.draw.circle(overlay, (*FIRE_DK, a), (cx, py), r + 1)
            pygame.draw.circle(overlay, (*LAVA, a), (cx, py), r)
            pygame.draw.circle(overlay, (*FIRE_HI, a), (cx - r // 3, py - r // 3), max(1, r // 2))
        else:
            pygame.draw.circle(overlay, (*ROCK, a), (cx, cy), r + 1)
            pygame.draw.circle(overlay, (*LAVA, int(a * 0.8)), (cx, cy), max(1, r - 1))
    elif kind == "claw":
        cx, cy = S(*s["c"])
        prog = min(1.0, t / 0.35)
        draw_claw(overlay, cx, cy, s.get("ang", 0.0), s.get("size", 0.45) * ts, prog,
                  int(255 * min(1.0, f * 2.0)))
    elif kind == "crescent":
        cx, cy = S(*s["c"])
        sweep = s.get("sweep", 1.4) * (min(1.0, t / 0.3) - 0.5)
        draw_crescent(overlay, cx, cy, s.get("ang", 0.0) + sweep, s.get("r", 1.0) * ts,
                      s.get("thick", 0.35) * ts, int(240 * min(1.0, f * 2.0)),
                      s.get("cols", (GHOST_DK, GHOST, GHOST_HI)))
    elif kind == "sword":
        cx, cy = S(*s["c"])
        ang = s.get("a0", 0.0) + age * s.get("spin", 6.0)
        rad = s.get("orbit", 0.8) * ts * (0.6 + 0.4 * min(1.0, t * 3))
        sx = cx + math.cos(ang) * rad
        sy = cy + math.sin(ang) * rad * 0.55 - int(0.35 * ts)
        draw_sword(overlay, sx, sy, ang + math.pi / 2, s.get("size", 0.38) * ts,
                   int(255 * min(1.0, f * 2.5)))


# --- handler degli eventi (FXSystem._FX_STYLES) --------------------------------


def _tongues(fx, c, n, spread, h=0.6, w=0.35, life=(0.3, 0.55), up=0.4, cols=None):
    for _ in range(n):
        a = random.uniform(0, math.tau)
        r = random.uniform(0.0, spread)
        kw = {}
        if cols:
            kw["cols"] = cols
        fx._shape(kind="flametongue", c=(c[0] + math.cos(a) * r, c[1] + math.sin(a) * r * 0.7),
                  v=(random.uniform(-0.2, 0.2), -up * random.uniform(0.5, 1.0)),
                  h=h * random.uniform(0.7, 1.2), w=w * random.uniform(0.8, 1.2),
                  ph=random.uniform(0, 6), col=FIRE, life=random.uniform(*life), **kw)


def _embers(fx, c, n, spread, col=FIRE_HI, speed=2.0):
    for _ in range(n):
        a = random.uniform(0, math.tau)
        r = random.uniform(0.0, spread)
        fx._add(c[0] + math.cos(a) * r, c[1] + math.sin(a) * r, math.cos(a) * speed * 0.4,
                -random.uniform(0.6, 1.0) * speed, random.uniform(0.35, 0.7),
                col if random.random() < 0.6 else FIRE, 1)


def _sparkles(fx, c, n, col):
    """Puntini che risalgono (cura, potenziamento): piccoli, non coprono lo sprite."""
    for _ in range(n):
        fx._add(c[0] + random.uniform(-0.45, 0.45), c[1] + random.uniform(-0.2, 0.2),
                random.uniform(-0.2, 0.2), -random.uniform(1.2, 2.2), random.uniform(0.4, 0.7),
                col, 1)


def fx_incinerate(fx, e, col):
    """Bruciatutto: ventaglio di lingue di fuoco nel cono + braci."""
    o, d = e.get("o"), e.get("dir")
    if o is None:
        return
    rng = e.get("range", 2.5)
    half = math.radians(e.get("angle", 45))
    base = math.atan2(d[1], d[0])
    fx._shape(kind="arc", o=o, base=base, half=half, rng=rng, col=FIRE_DK, life=0.22)
    for i in range(9):
        a = base - half + 2 * half * (i + random.random()) / 9
        u = random.uniform(0.35, 1.0)
        c = (o[0] + math.cos(a) * rng * u, o[1] + math.sin(a) * rng * u + 0.2)
        fx._shape(kind="flametongue", c=c, v=(math.cos(a) * 0.6, -0.5),
                  h=random.uniform(0.3, 0.5) + 0.15 * u, w=random.uniform(0.24, 0.34),
                  ph=random.uniform(0, 6), col=FIRE, life=0.3 + 0.2 * u)
    _embers(fx, (o[0] + d[0] * rng * 0.6, o[1] + d[1] * rng * 0.6), 10, rng * 0.4)


def fx_shieldbreak(fx, e, col):
    """Scudo bruciato: anello che si incrina e schegge chiare."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=0.9, r1=1.15, col=(220, 240, 255), life=0.25, wd=0.08)
    for _ in range(10):
        a = random.uniform(0, math.tau)
        fx._add(c[0] + math.cos(a) * 0.8, c[1] + math.sin(a) * 0.8, math.cos(a) * 3.0,
                math.sin(a) * 3.0, random.uniform(0.25, 0.45), (230, 245, 255), 1)


def fx_lavaplume(fx, e, col):
    """Lavasbuffo: sbuffo di vulcano attorno a sé (cratere, gocce di lava
    lanciate in alto che ricadono, fumo che sale)."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.2))
    fx._shape(kind="flash", c=c, r=0.7, col=FIRE_HI, life=0.14)
    fx._shape(kind="ring", c=c, r0=0.4, r1=r, col=LAVA, life=0.4, wd=0.22)
    fx._shape(kind="ring", c=c, r0=0.2, r1=r * 0.7, col=FIRE_DK, life=0.5, wd=0.12)
    for k in range(14):
        a = k / 14 * math.tau + random.uniform(-0.2, 0.2)
        dist = random.uniform(0.5, 1.0) * r
        fx._shape(kind="lavablob", c=c, v=(math.cos(a) * dist, math.sin(a) * dist * 0.75),
                  z=random.uniform(0.5, 1.0), r=random.uniform(0.12, 0.19), col=LAVA,
                  life=random.uniform(0.55, 0.75))
    for _ in range(6):   # colonna di fumo che sale dal cratere
        fx._shape(kind="puff", c=(c[0] + random.uniform(-0.4, 0.4), c[1] - 0.2),
                  v=(random.uniform(-0.3, 0.3), -random.uniform(1.0, 1.8)),
                  r0=0.2, r1=random.uniform(0.45, 0.7), col=SMOKE, life=random.uniform(0.7, 1.0))
    _tongues(fx, c, 3, 0.6, h=0.45, w=0.3, up=0.6)


def fx_burned(fx, e, col):
    c = e.get("c")
    if c is not None:
        _tongues(fx, (c[0], c[1] - 0.1), 3, 0.3, h=0.45, w=0.28, life=(0.3, 0.45))


def fx_nightshade(fx, e, col):
    """Ombra Notturna (lancio): pozza d'ombra ai piedi da cui parte l'ombra."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=0.9, r1=0.2, col=SHADOW_MID, life=0.35, wd=0.14)
    fx._dust(c, 0.5, n=6, col=SHADOW, speed=(0.4, 1.0))


def fx_nightshadehit(fx, e, col):
    """L'ombra raggiunge il bersaglio e si solleva in spuntoni scuri."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="flash", c=c, r=0.5, col=SHADOW_HI, life=0.14)
    fx._shape(kind="ring", c=c, r0=0.2, r1=1.0, col=SHADOW_MID, life=0.3, wd=0.16)
    _tongues(fx, c, 6, 0.45, h=0.6, w=0.24, up=1.0, life=(0.3, 0.5),
             cols=(SHADOW, SHADOW_MID, (124, 82, 176)))


def fx_clearsmog(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.0))
    fx._shape(kind="ring", c=c, r0=0.3, r1=r, col=SMOG, life=0.4, wd=0.14)
    fx._dust(c, r * 0.8, n=16, col=SMOG, speed=(0.6, 1.6))


def fx_purged(fx, e, col):
    """Pulifumo toglie un potenziamento: anello che si spegne verso il basso."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=1.0, r1=0.2, col=SMOG, life=0.35, wd=0.1)
    for k in range(4):
        fx._add(c[0] - 0.3 + k * 0.2, c[1] - 0.8, 0, 1.6, 0.4, SMOG_DK, 1)


def fx_calmmind(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    for k in range(3):
        fx._shape(kind="ring", c=(c[0], c[1] - 0.2), r0=1.5 - 0.3 * k, r1=0.3, col=CALM,
                  life=0.45 + 0.1 * k, wd=0.08)
    fx._shape(kind="flash", c=(c[0], c[1] - 0.6), r=0.3, col=(220, 240, 255), life=0.2)
    _sparkles(fx, c, 8, CALM)


def fx_swordsdance(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    for k in range(4):
        fx._shape(kind="sword", c=c, a0=k * math.pi / 2, spin=7.0, orbit=0.85, size=0.4,
                  col=(220, 230, 250), life=0.7)
    fx._shape(kind="ring", c=c, r0=0.3, r1=1.2, col=(240, 140, 110), life=0.4, wd=0.1)


def fx_flamecharge(fx, e, col):
    """Nitrocarica: scia di fuoco lungo lo scatto."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    fx._shape(kind="beam", a=a, b=b, col=FIRE_DK, w=0.5, life=0.22)
    fx._shape(kind="beam", a=a, b=b, col=FIRE, w=0.2, life=0.26)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(3, int(L * 2.2))
    for i in range(n):
        u = (i + 0.5) / n
        side = random.uniform(-0.25, 0.25)
        c = (a[0] + (b[0] - a[0]) * u - (b[1] - a[1]) / max(L, 1e-6) * side,
             a[1] + (b[1] - a[1]) * u + (b[0] - a[0]) / max(L, 1e-6) * side + 0.15)
        fx._shape(kind="flametongue", c=c, v=(0, -0.3), h=random.uniform(0.22, 0.45),
                  w=random.uniform(0.2, 0.3), ph=i, col=FIRE, life=0.2 + 0.3 * u)
    _embers(fx, b, 6, 0.3)


def fx_armorcannonfire(fx, e, col):
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    fx._shape(kind="flash", c=b, r=0.6, col=FIRE_HI, life=0.14)
    fx._shape(kind="ring", c=b, r0=0.2, r1=1.0, col=FIRE, life=0.25, wd=0.12)
    fx._dust(a, 0.4, n=6, col=SMOKE, speed=(0.6, 1.4))


def fx_armorcannonhit(fx, e, col):
    """Armor Cannon all'impatto: esplosione grande."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="flash", c=c, r=1.0, col=FIRE_HI, life=0.18)
    fx._shape(kind="ring", c=c, r0=0.3, r1=1.8, col=FIRE, life=0.4, wd=0.24)
    fx._shape(kind="ring", c=c, r0=0.2, r1=1.2, col=GOLD, life=0.3, wd=0.1)
    _tongues(fx, c, 7, 0.8, h=0.45, w=0.3, up=0.6)
    _embers(fx, c, 14, 0.8, speed=3.0)
    fx._dust(c, 0.9, n=10, col=SMOKE, speed=(1.0, 2.4))


def fx_floatarmor(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=0.4, r1=1.5, col=GOLD, life=0.4, wd=0.12)
    fx._shape(kind="ring", c=c, r0=1.4, r1=0.6, col=ARMOR, life=0.4, wd=0.14)
    _embers(fx, c, 10, 0.8, col=GOLD_HI)


def fx_armorblock(fx, e, col):
    """Uno spallaccio intercetta un proiettile: scintille dorate dove lo ferma."""
    b = e.get("b")
    if b is None:
        return
    fx._shape(kind="flash", c=b, r=0.45, col=GOLD_HI, life=0.14)
    fx._shape(kind="ring", c=b, r0=0.2, r1=0.8, col=GOLD, life=0.25, wd=0.1)
    _embers(fx, b, 8, 0.2, col=GOLD_HI, speed=3.0)


def fx_floatarmorboom(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.6))
    fx._shape(kind="flash", c=c, r=r * 0.5, col=FIRE_HI, life=0.18)
    fx._shape(kind="ring", c=c, r0=0.4, r1=r, col=ARMOR, life=0.45, wd=0.24)
    fx._shape(kind="ring", c=c, r0=0.3, r1=r * 0.8, col=GOLD, life=0.35, wd=0.1)
    for k in range(8):
        a = k / 8 * math.tau
        fx._shape(kind="lavablob", c=c, v=(math.cos(a) * r * 0.9, math.sin(a) * r * 0.7), z=0.8,
                  r=0.12, col=FIRE, life=0.5)
    _tongues(fx, c, 8, r * 0.6, h=0.4, w=0.28)


def fx_psychicburst(fx, e, col):
    """Psichico: l'area si accende di rosa e solleva."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.3))
    fx._shape(kind="flash", c=c, r=r * 0.5, col=PSY_HI, life=0.16)
    fx._shape(kind="flash", c=c, r=r * 0.9, col=PSY, life=0.22)
    for k in range(3):
        fx._shape(kind="ring", c=c, r0=0.3 + 0.2 * k, r1=r * (1.0 - 0.15 * k), col=PSY,
                  life=0.4 + 0.08 * k, wd=0.16)
    for _ in range(16):
        a = random.uniform(0, math.tau)
        rr = random.uniform(0, r)
        fx._add(c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr, 0, -random.uniform(1.5, 3.0),
                random.uniform(0.4, 0.7), PSY_HI if random.random() < 0.5 else PSY, 1)


def fx_bitterblade(fx, e, col):
    """Bitter Blade: grande mezzaluna di fiamma spettrale e cura che risale."""
    o, d = e.get("o"), e.get("dir")
    if o is None:
        return
    rng = e.get("range", 2.6)
    ang = math.atan2(d[1], d[0])
    fx._shape(kind="crescent", c=(o[0], o[1] - 0.3), ang=ang, r=rng * 0.7, thick=0.26, sweep=1.2,
              col=GHOST, life=0.26)
    c = (o[0] + d[0] * rng * 0.6, o[1] + d[1] * rng * 0.6)
    _tongues(fx, c, 4, 0.5, h=0.4, w=0.24, cols=(GHOST_DK, GHOST, GHOST_HI))
    _sparkles(fx, o, 7, HEAL)


def fx_grudgeblade(fx, e, col):
    """Lama dei Rancori (scatto): striscia spettrale fino al bersaglio."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    fx._shape(kind="beam", a=a, b=b, col=GHOST_DK, w=0.6, life=0.25)
    fx._shape(kind="beam", a=a, b=b, col=GHOST, w=0.22, life=0.28)
    _tongues(fx, a, 3, 0.3, cols=(GHOST_DK, GHOST, GHOST_HI))


def fx_grudgehit(fx, e, col):
    """Un fendente della raffica: mezzaluna con angolo diverso a ogni colpo."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    n = int(e.get("n", 0))
    ang = math.atan2(b[1] - a[1], b[0] - a[0]) + (0.9 if n % 2 else -0.9) + random.uniform(-0.3, 0.3)
    fx._shape(kind="crescent", c=(b[0] - math.cos(ang) * 0.6, b[1] - math.sin(ang) * 0.6), ang=ang,
              r=0.9, thick=0.3, sweep=1.8, col=GHOST, life=0.2)
    fx._shape(kind="flash", c=b, r=0.3, col=GHOST_HI, life=0.08)
    _embers(fx, b, 4, 0.2, col=GHOST_HI, speed=2.5)


def fx_shadowclaw(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=1.4, r1=0.3, col=SHADOW_MID, life=0.45, wd=0.16)
    fx._shape(kind="claw", c=(c[0], c[1] - 0.4), ang=-0.6, size=0.5, col=SHADOW_MID, life=0.4)
    fx._dust(c, 0.7, n=8, col=SHADOW, speed=(0.6, 1.4))


def fx_shadowclawhit(fx, e, col):
    """Attacco base con Ombrartigli: artigliata d'ombra sul bersaglio."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    ang = math.atan2(b[1] - a[1], b[0] - a[0]) + math.pi / 2 + random.uniform(-0.4, 0.4)
    fx._shape(kind="claw", c=(b[0], b[1] - 0.3), ang=ang, size=0.55, col=SHADOW_MID, life=0.32,
              hit=True)
    fx._shape(kind="flash", c=(b[0], b[1] - 0.3), r=0.35, col=SHADOW_HI, life=0.1)


def fx_ghostslash(fx, e, col):
    """Secondo colpo di Doppia Lama: fendente spettrale traslucido, incrociato."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    ang = math.atan2(b[1] - a[1], b[0] - a[0]) - 0.5
    r = 0.55
    fx._shape(kind="crescent", c=(b[0] - math.cos(ang) * r, b[1] - math.sin(ang) * r - 0.3),
              ang=ang, r=r, thick=0.2, sweep=-0.8, col=GHOST, life=0.2,
              cols=(GHOST_DK, GHOST, GHOST_HI))
    fx._shape(kind="flash", c=(b[0], b[1] - 0.3), r=0.25, col=GHOST_HI, life=0.08)


def fx_guardshield(fx, e, col):
    """Guardia: un lampo dorato va da Armarouge all'alleato e lo avvolge."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    fx._shape(kind="beam", a=a, b=b, col=GOLD, w=0.1, life=0.3)
    fx._shape(kind="ring", c=b, r0=1.3, r1=0.5, col=GOLD, life=0.45, wd=0.14)
    fx._shape(kind="ring", c=b, r0=0.6, r1=1.0, col=ARMOR, life=0.35, wd=0.08)
    _embers(fx, b, 8, 0.6, col=GOLD_HI)


STYLES = {
    "incinerate": fx_incinerate, "shieldbreak": fx_shieldbreak, "lavaplume": fx_lavaplume,
    "burned": fx_burned, "nightshade": fx_nightshade, "nightshadehit": fx_nightshadehit,
    "clearsmog": fx_clearsmog, "purged": fx_purged, "calmmind": fx_calmmind,
    "swordsdance": fx_swordsdance, "flamecharge": fx_flamecharge,
    "armorcannonfire": fx_armorcannonfire, "armorcannonhit": fx_armorcannonhit,
    "floatarmor": fx_floatarmor, "armorblock": fx_armorblock,
    "floatarmorboom": fx_floatarmorboom, "psychicburst": fx_psychicburst,
    "bitterblade": fx_bitterblade, "grudgeblade": fx_grudgeblade, "grudgehit": fx_grudgehit,
    "shadowclaw": fx_shadowclaw, "shadowclawhit": fx_shadowclawhit,
    "ghostslash": fx_ghostslash, "guardshield": fx_guardshield,
}


# --- disegni persistenti (stato del Match) -------------------------------------


def draw_shade(surface, camera, sh, now):
    """Ombra Notturna in viaggio: macchia d'ombra piatta a terra con riccioli
    che la seguono (scivola sul pavimento verso il bersaglio)."""
    ts = config.TILE_SIZE
    p = sh["pos"]
    cx, cy = camera.world_to_screen(p.x * ts, p.y * ts)
    w = int(0.9 * ts)
    h = max(4, int(0.42 * ts))
    wob = math.sin(now * 12 + sh.get("start", 0) * 7)
    d = sh.get("dir")
    if d is not None:   # scia d'ombra che si assottiglia dietro
        for k in range(1, 5):
            tx = cx - int(d.x * k * 0.35 * ts)
            ty = cy - int(d.y * k * 0.35 * ts)
            ww, hh = max(2, int(w * (1 - 0.18 * k))), max(2, int(h * (1 - 0.18 * k)))
            _ellipse(surface, pygame.Rect(tx - ww // 2, ty - hh // 2, ww, hh), SHADOW, 150 - 30 * k)
    _ellipse(surface, pygame.Rect(cx - w // 2 - 2, cy - h // 2 - 1, w + 4, h + 2), SHADOW, 110)
    _ellipse(surface, pygame.Rect(cx - w // 2, cy - h // 2, w, h), SHADOW, 220)
    _ellipse(surface, pygame.Rect(cx - w // 3, cy - h // 3, w * 2 // 3, h * 2 // 3), SHADOW_MID, 200)
    # due "occhi" che brillano nell'ombra
    for dx in (-3, 3):
        pygame.draw.rect(surface, SHADOW_HI, pygame.Rect(cx + dx - 1, cy - 1 + int(wob), 2, 1))
    # riccioli d'ombra che salgono
    for k in range(3):
        ph = (now * 2.5 + k / 3.0) % 1.0
        rx = cx + int(math.sin(now * 5 + k * 2) * w * 0.3)
        ry = cy - int(ph * 0.8 * ts)
        _disc(surface, rx, ry, max(1, int((1.0 - ph) * 0.12 * ts)), SHADOW_MID, int(180 * (1 - ph)))


def draw_smog(surface, camera, s, now):
    """Pulifumo: nube bianco-violacea a cuscinetti che ondeggia; sfuma alla fine."""
    ts = config.TILE_SIZE
    c = s["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    r = int(s["radius"] * ts)
    fade = max(0.0, min(1.0, (s["end"] - now) / 0.5, (now - s["start"]) / 0.25))
    _disc(surface, cx, cy, r, SMOG_DK, int(40 * fade))
    _disc(surface, cx, cy, r, SMOG, int(120 * fade), 1)
    rnd = random.Random(int(s["start"] * 1000))
    for k in range(11):
        a = rnd.uniform(0, math.tau)
        rr = rnd.uniform(0.15, 0.8) * r
        wob = math.sin(now * 1.8 + k)
        px = cx + int(math.cos(a) * rr + wob * 2)
        py = cy + int(math.sin(a) * rr * 0.75 - abs(wob) * 2)
        pr = max(3, int(rnd.uniform(0.3, 0.5) * ts))
        _disc(surface, px, py, pr, SMOG_DK, int(90 * fade))
        _disc(surface, px - pr // 4, py - pr // 4, max(2, pr * 2 // 3), SMOG, int(120 * fade))


def draw_cannon_charge(surface, camera, cc, now):
    """Armor Cannon in carica: braci risucchiate verso la bocca del cannone,
    sfera che cresce e linea di mira tratteggiata."""
    ts = config.TILE_SIZE
    p, d = cc["pos"], cc["dir"]
    prog = max(0.0, min(1.0, (now - cc["start"]) / max(1e-6, cc["end"] - cc["start"])))
    mx, my = p.x + d.x * 0.55, p.y + d.y * 0.55 - 0.35
    cx, cy = camera.world_to_screen(mx * ts, my * ts)
    rng = cc.get("range", 9.5)
    ex, ey = camera.world_to_screen((p.x + d.x * rng) * ts, (p.y + d.y * rng) * ts)
    L = math.hypot(ex - cx, ey - cy)
    n = max(2, int(L // 6))
    for i in range(0, n, 2):
        t0, t1 = i / n, (i + 1) / n
        pygame.draw.line(surface, FIRE, (cx + (ex - cx) * t0, cy + (ey - cy) * t0),
                         (cx + (ex - cx) * t1, cy + (ey - cy) * t1), 1)
    for k in range(8):   # braci che convergono
        a = k / 8 * math.tau + now * 3
        rr = (1.0 - ((now * 2.5 + k / 8) % 1.0)) * 0.9 * ts
        pygame.draw.rect(surface, FIRE_HI, pygame.Rect(cx + math.cos(a) * rr, cy + math.sin(a) * rr, 2, 2))
    r = max(2, int((0.15 + 0.3 * prog) * ts))
    _disc(surface, cx, cy, r + 3, FIRE, 90)
    pygame.draw.circle(surface, FIRE_DK, (cx, cy), r + 1)
    pygame.draw.circle(surface, FIRE, (cx, cy), r)
    pygame.draw.circle(surface, FIRE_HI, (cx - r // 3, cy - r // 3), max(1, r // 2))


def draw_cannonball(surface, camera, pr, now):
    """Palla di fuoco di Armor Cannon in volo: sfera grande con scia a cometa."""
    ts = config.TILE_SIZE
    p, d = pr["pos"], pr["dir"]
    cx, cy = camera.world_to_screen(p.x * ts, (p.y - 0.35) * ts)
    r = max(3, int(pr["radius"] * ts))
    for k in range(5, 0, -1):   # scia
        tx = cx - d.x * k * r * 0.7
        ty = cy - d.y * k * r * 0.7
        _disc(surface, int(tx), int(ty), max(1, int(r * (1.0 - k * 0.15))),
              FIRE if k < 3 else FIRE_DK, int(150 - 25 * k))
    fl = 1 + int(math.sin(now * 40) * 1.5)
    _disc(surface, cx, cy, r + 3 + fl, FIRE, 80)
    pygame.draw.circle(surface, FIRE_DK, (cx, cy), r + 1)
    pygame.draw.circle(surface, LAVA, (cx, cy), r)
    pygame.draw.circle(surface, FIRE_HI, (cx - r // 4, cy - r // 4), max(1, r * 2 // 3))
    pygame.draw.circle(surface, (255, 255, 230), (cx - r // 3, cy - r // 3), max(1, r // 3))


def draw_psy_zone(surface, camera, z, now):
    """Psichico in arrivo: area rosa con un anello che si chiude fino allo scatto."""
    ts = config.TILE_SIZE
    c = z["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    r = int(z["radius"] * ts)
    prog = max(0.0, min(1.0, (now - z["start"]) / max(1e-6, z["end"] - z["start"])))
    _disc(surface, cx, cy, r, PSY, int(60 + 60 * prog))
    _disc(surface, cx, cy, r, PSY, 255, 3)
    _disc(surface, cx, cy, r - 3, PSY_HI, 220, 1)
    _disc(surface, cx, cy, max(2, int(r * (1.0 - prog))), PSY_HI, 200, 1)
    for k in range(6):
        a = k / 6 * math.tau + now * 2
        px, py = cx + math.cos(a) * r * 0.75, cy + math.sin(a) * r * 0.75
        pygame.draw.rect(surface, PSY_HI, pygame.Rect(px - 1, py - 1, 2, 2))


def draw_flurry(surface, camera, fl, now):
    """Lama dei Rancori: vortice di tagli spettrali attorno al bersaglio."""
    ts = config.TILE_SIZE
    c = fl["pos"]
    cx, cy = camera.world_to_screen(c.x * ts, (c.y - 0.3) * ts)
    r = int(0.9 * ts)
    _disc(surface, cx, cy + int(0.3 * ts), r, GHOST_DK, 70)
    rnd = random.Random(int(now * 18))
    for k in range(3):
        a = rnd.uniform(0, math.tau)
        rr = rnd.uniform(0.45, 0.7) * r
        ox, oy = cx - math.cos(a) * rr, cy - math.sin(a) * rr
        draw_crescent(surface, ox, oy, a, rr * 1.6, max(3, int(0.18 * ts)), 230)


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Stati della linea Charcadet sull'unità: spallacci in orbita (Armatura
    Fluttuante), artigli d'ombra (Ombrartigli), aura calma (Calmamente)."""
    r = int(u.radius * ts)
    if getattr(u, "calm_until", -1.0) > now:
        for k in range(2):
            ph = (now * 0.9 + k * 0.5) % 1.0
            _ellipse(surface, pygame.Rect(gx - r - 4, gy - 3 - int(ph * r * 2), 2 * r + 8, 6), CALM,
                     int(150 * (1.0 - ph)), 1)
    if getattr(u, "shadowclaw_until", -1.0) > now:
        for side in (-1, 1):
            hx = gx + side * (r + 2)
            hy = gy - r
            for k in range(3):
                x = hx + side * k * 2
                fl = int(math.sin(now * 14 + k + side) * 1.5)
                pygame.draw.line(surface, SHADOW, (x, hy - 5 + fl), (x + side * 4, hy + 4), 4)
                pygame.draw.line(surface, CLAW, (x, hy - 5 + fl), (x + side * 4, hy + 4), 2)
                pygame.draw.line(surface, (236, 210, 255), (x, hy - 5 + fl), (x + side * 2, hy), 1)
    if getattr(u, "floatarmor_until", -1.0) > now:
        blocks = int(getattr(u, "armor_blocks", 0))
        orbit = r + int(0.35 * ts)
        for k in range(3):
            a = now * 3.2 + k * math.tau / 3
            px = gx + math.cos(a) * orbit
            py = gy - r + math.sin(a) * orbit * 0.45
            draw_pauldron(surface, px, py, a + math.pi / 2, max(3, int(0.2 * ts)), 255,
                          cracked=k >= blocks)
