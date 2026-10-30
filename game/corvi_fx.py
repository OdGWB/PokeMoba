"""Grafica della linea Rookidee > Corvisquire > Corviknight: effetti istantanei
(handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (becco, piuma, ala) e disegni persistenti letti dallo
stato del Match a ogni frame (corrente di Ventoincoda, Taxi Volante) e sulle
unità (provocato, Trespolo).

Pixel art: forme piene a contorno scuro, niente smoothscale; luce da in alto a
sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

BEAK = (246, 196, 72)
BEAK_HI = (255, 236, 160)
BEAK_OUT = (96, 60, 20)
FEATHER = (58, 72, 132)
FEATHER_HI = (120, 140, 210)
FEATHER_OUT = (20, 24, 52)
STEEL = (186, 194, 214)
STEEL_HI = (240, 244, 255)
STEEL_DK = (84, 92, 120)
WIND = (214, 240, 255)
WIND_DK = (120, 170, 210)
TAUNT = (236, 66, 52)
TAUNT_DK = (110, 18, 18)
HEAL = (140, 240, 150)


def _disc(surface, cx, cy, r, col, a, width=0):
    if r < 1:
        return
    g = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
    pygame.draw.circle(g, (*col, a), (r + 1, r + 1), r, width)
    surface.blit(g, (cx - r - 1, cy - r - 1))


def _rot(px, py, ca, sa):
    return px * ca - py * sa, px * sa + py * ca


def beak_points(cx, cy, ang, size, gap=0.0):
    """Becco a due valve (sopra/sotto) che punta lungo `ang`; `gap` = apertura."""
    ca, sa = math.cos(ang), math.sin(ang)
    L, H = size, size * 0.42
    up = [(-L * 0.35, -H - gap), (L, -gap * 0.3), (-L * 0.35, -gap * 0.3)]
    dn = [(-L * 0.35, gap * 0.3), (L * 0.8, gap * 0.6), (-L * 0.35, H * 0.8 + gap)]
    out = []
    for poly in (up, dn):
        out.append([(cx + x, cy + y) for x, y in (_rot(px, py, ca, sa) for px, py in poly)])
    return out


def draw_beak(surface, cx, cy, ang, size, alpha=255, gap=0.0):
    """Becco giallo con contorno scuro e luce sulla valva superiore."""
    up, dn = beak_points(cx, cy, ang, size, gap)
    for poly, col in ((dn, (214, 152, 48)), (up, BEAK)):
        pygame.draw.polygon(surface, (*BEAK_OUT, alpha), poly)
        inner = [((x * 3 + sum(p[0] for p in poly) / 3) / 4, (y * 3 + sum(p[1] for p in poly) / 3) / 4)
                 for x, y in poly]
        pygame.draw.polygon(surface, (*col, alpha), inner)
    pygame.draw.line(surface, (*BEAK_HI, alpha), up[0], up[1], 1)


def draw_feather(surface, cx, cy, ang, size, col=FEATHER, alpha=255):
    """Piuma: ellisse allungata con rachide chiara."""
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for i in range(10):
        t = i / 10 * math.tau
        x, y = math.cos(t) * size, math.sin(t) * size * 0.32
        rx, ry = _rot(x, y, ca, sa)
        pts.append((cx + rx, cy + ry))
    pygame.draw.polygon(surface, (*FEATHER_OUT, alpha), pts)
    inner = [((x - cx) * 0.75 + cx, (y - cy) * 0.75 + cy) for x, y in pts]
    pygame.draw.polygon(surface, (*col, alpha), inner)
    a = _rot(-size, 0, ca, sa)
    b = _rot(size * 0.9, 0, ca, sa)
    pygame.draw.line(surface, (*FEATHER_HI, alpha), (cx + a[0], cy + a[1]), (cx + b[0], cy + b[1]), 1)


def draw_wing(surface, cx, cy, side, spread, size, alpha=255):
    """Ala d'acciaio stilizzata (3 penne remiganti) aperta di `spread` (0..1)."""
    for k in range(3):
        ang = -math.pi / 2 + side * (0.5 + 0.45 * spread + k * 0.32)
        L = size * (1.0 - 0.18 * k)
        ex, ey = cx + math.cos(ang) * L, cy + math.sin(ang) * L * 0.8
        nx, ny = -math.sin(ang) * size * 0.16, math.cos(ang) * size * 0.16
        poly = [(cx + nx, cy + ny), (ex, ey), (cx - nx, cy - ny)]
        pygame.draw.polygon(surface, (*STEEL_DK, alpha), poly)
        pygame.draw.polygon(surface, (*(STEEL if k else FEATHER_HI), alpha),
                            [((x - cx) * 0.8 + cx, (y - cy) * 0.8 + cy) for x, y in poly])


def draw_bang(surface, x, y):
    """Punto esclamativo rosso pixel-art (stato provocato), base in (x, y)."""
    bar = [(x - 2, y - 11), (x + 2, y - 11), (x + 1, y - 4), (x - 1, y - 4)]
    pygame.draw.polygon(surface, TAUNT_DK, [(x - 3, y - 12), (x + 3, y - 12), (x + 2, y - 3), (x - 2, y - 3)])
    pygame.draw.polygon(surface, TAUNT, bar)
    pygame.draw.rect(surface, TAUNT_DK, pygame.Rect(x - 2, y - 2, 5, 4))
    pygame.draw.rect(surface, TAUNT, pygame.Rect(x - 1, y - 1, 3, 2))
    pygame.draw.line(surface, (255, 200, 180), (x - 1, y - 10), (x - 1, y - 7))


# --- forme per FXSystem._draw_shapes ------------------------------------------
SHAPES = ("beak", "feather", "wing", "bang")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "beak":
        # Il becco scatta in avanti (0..35% della vita), resta, poi svanisce.
        thrust = min(1.0, t / 0.35)
        thrust = 1.0 - (1.0 - thrust) ** 3
        d = s["dir"]
        back = s.get("reach", 0.6) * (1.0 - thrust)
        cx, cy = S(s["c"][0] - d[0] * back, s["c"][1] - d[1] * back)
        aa = 255 if f > 0.35 else int(255 * f / 0.35)
        gap = s.get("open", 0.0) * ts * (1.0 - thrust)
        draw_beak(overlay, cx, cy, math.atan2(d[1], d[0]), s.get("size", 0.45) * ts, aa, gap)
    elif kind == "feather":
        age = s["maxlife"] - s["life"]
        sway = math.sin(age * 7 + s.get("ph", 0.0)) * 0.25
        px, py = S(s["c"][0] + s["v"][0] * age + sway, s["c"][1] + s["v"][1] * age)
        draw_feather(overlay, px, py, s.get("rot", 0.0) + age * s.get("spin", 2.0),
                     s.get("size", 0.2) * ts, s["col"], int(255 * f))
    elif kind == "wing":
        cx, cy = S(*s["c"])
        spread = math.sin(t * math.pi)
        for side in (-1, 1):
            draw_wing(overlay, cx, cy, side, spread, s.get("size", 0.8) * ts, int(230 * f))
    elif kind == "bang":
        # Simbolo di provocazione: "!" rosso con contorno, rimbalza un attimo.
        cx, cy = S(*s["c"])
        hop = int(math.sin(min(1.0, t * 3.0) * math.pi) * 4)
        aa = int(255 * min(1.0, f * 2.0))
        h = max(6, int(0.42 * ts))
        r = pygame.Rect(cx - 2, cy - h - hop, 4, h - 4)
        pygame.draw.rect(overlay, (*TAUNT_DK, aa), r.inflate(2, 2))
        pygame.draw.rect(overlay, (*TAUNT, aa), r)
        dot = pygame.Rect(cx - 2, cy - 2 - hop, 4, 3)
        pygame.draw.rect(overlay, (*TAUNT_DK, aa), dot.inflate(2, 2))
        pygame.draw.rect(overlay, (*TAUNT, aa), dot)


# --- handler degli eventi (FXSystem._FX_STYLES) --------------------------------


def _feathers(fx, c, n, col=FEATHER, spread=0.4, up=0.6, life=(0.45, 0.8), size=0.18):
    for _ in range(n):
        a = random.uniform(0, math.tau)
        v = random.uniform(0.3, 1.0)
        fx._shape(kind="feather", c=(c[0] + math.cos(a) * spread * 0.4, c[1] + math.sin(a) * spread * 0.4),
                  v=(math.cos(a) * v, math.sin(a) * v * 0.5 + up * 0.5), rot=random.uniform(0, 6),
                  spin=random.uniform(-3, 3), ph=random.uniform(0, 6), size=size * random.uniform(0.8, 1.2),
                  col=col if random.random() < 0.7 else FEATHER_HI, life=random.uniform(*life))


def _front(e, frac=0.75):
    o, d = e.get("o"), e.get("dir")
    rng = e.get("range", 2.0)
    return (o[0] + d[0] * rng * frac, o[1] + d[1] * rng * frac), d


def fx_peck(fx, e, col):
    """Beccata: un becco che scatta in avanti e colpisce."""
    if e.get("o") is None:
        return
    c, d = _front(e, 0.7)
    fx._shape(kind="beak", c=c, dir=d, size=0.5, reach=0.9, open=0.2, col=BEAK, life=0.34)
    hit = (c[0] + d[0] * 0.6, c[1] + d[1] * 0.6)
    fx._shape(kind="flash", c=hit, r=0.3, col=(255, 248, 220), life=0.12)
    ang = math.atan2(d[1], d[0])
    for k in (-1, 0, 1):   # tre tratti d'urto a raggiera davanti alla punta
        a2 = ang + k * 0.6
        fx._shape(kind="beam", a=(hit[0] + math.cos(a2) * 0.25, hit[1] + math.sin(a2) * 0.25),
                  b=(hit[0] + math.cos(a2) * 0.6, hit[1] + math.sin(a2) * 0.6),
                  col=BEAK_HI, w=0.05, life=0.16)


def fx_drillpeck(fx, e, col):
    """Perforbecco: becco davanti allo scatto, scia ad avvitamento e piume."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    d = (b[0] - a[0], b[1] - a[1])
    L = math.hypot(*d) or 1.0
    d = (d[0] / L, d[1] / L)
    fx._shape(kind="beam", a=a, b=b, col=WIND_DK, w=0.42, life=0.22)
    fx._shape(kind="beam", a=a, b=b, col=WIND, w=0.14, life=0.26)
    tip = (b[0] + d[0] * 0.35, b[1] + d[1] * 0.35)
    fx._shape(kind="beak", c=tip, dir=d, size=0.5, reach=1.0, col=BEAK, life=0.3)
    px, py = -d[1], d[0]
    n = max(3, int(L * 2))
    for k in range(n):   # trivella: tratti obliqui alternati lungo lo scatto
        u = (k + 0.5) / n
        cx, cy = a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
        s = 1 if k % 2 else -1
        fx._shape(kind="beam", a=(cx + px * 0.35 * s - d[0] * 0.15, cy + py * 0.35 * s - d[1] * 0.15),
                  b=(cx - px * 0.35 * s + d[0] * 0.15, cy - py * 0.35 * s + d[1] * 0.15),
                  col=WIND if k % 2 else STEEL, w=0.05, life=0.2 + 0.02 * k)
    _feathers(fx, a, 3, spread=0.3)
    _feathers(fx, b, 4, spread=0.6, size=0.2)


def fx_pluck(fx, e, col):
    """Spennata: schiaffo d'ala ravvicinato che strappa piume."""
    if e.get("o") is None:
        return
    c, d = _front(e, 0.6)
    ang = math.atan2(d[1], d[0])
    fx._shape(kind="arc", o=e["o"], base=ang, half=math.radians(55), rng=e.get("range", 2.0) * 0.85,
              col=STEEL, life=0.2)
    fx._shape(kind="slash", c=c, ang=ang, rng=0.55, col=STEEL_HI, life=0.18)
    fx._shape(kind="flash", c=c, r=0.4, col=(255, 252, 240), life=0.1)
    _feathers(fx, c, 6, spread=0.5, up=-0.4, size=0.2)


def fx_leer(fx, e, col):
    """Fulmisguardo: due occhi severi e un cono di sguardo a strisce."""
    if e.get("o") is None:
        return
    o, d = e["o"], e["dir"]
    fx._shape(kind="arc", o=o, base=math.atan2(d[1], d[0]), half=math.radians(e.get("angle", 40)),
              rng=e.get("range", 4.5), col=(200, 60, 60), life=0.35)
    for k in range(3):
        u = 0.3 + 0.25 * k
        fx._shape(kind="ring", c=(o[0] + d[0] * e.get("range", 4.5) * u, o[1] + d[1] * e.get("range", 4.5) * u),
                  r0=0.2, r1=0.7 + 0.3 * k, col=(250, 120, 110), life=0.3 + 0.05 * k, wd=0.08)


def fx_taunt(fx, e, col):
    """Provocazione: onda d'urto rossa nel cono + ali spalancate."""
    if e.get("o") is None:
        return
    o, d = e["o"], e["dir"]
    fx._shape(kind="arc", o=o, base=math.atan2(d[1], d[0]), half=math.radians(e.get("angle", 40)),
              rng=e.get("range", 4.0), col=TAUNT, life=0.4)
    fx._shape(kind="wing", c=(o[0], o[1] - 0.3), size=0.85, col=STEEL, life=0.45)
    fx._shape(kind="ring", c=o, r0=0.3, r1=1.3, col=TAUNT, life=0.3, wd=0.12)


def fx_taunted(fx, e, col):
    """Il "!" resta sopra la testa (draw_unit_overlay); qui solo lo scatto rosso."""
    c = e.get("c")
    if c is not None:
        fx._shape(kind="ring", c=c, r0=0.9, r1=0.3, col=TAUNT, life=0.3, wd=0.1)


def fx_defog(fx, e, col):
    """Scacciabruma: raffica che parte dal becco e spazza l'area."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 3.0))
    o = e.get("o", c)
    fx._shape(kind="beam", a=o, b=c, col=WIND, w=0.2, life=0.25)
    for k in range(3):
        fx._shape(kind="ring", c=c, r0=0.3 + 0.2 * k, r1=r * (1.0 - 0.12 * k), col=WIND,
                  life=0.45 + 0.08 * k, wd=0.1)
    for _ in range(18):
        a = random.uniform(0, math.tau)
        rr = random.uniform(0.3, 1.0) * r
        x, y = c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr
        fx._add(x, y, math.cos(a) * 3.0 - math.sin(a) * 2.0, math.sin(a) * 3.0 + math.cos(a) * 2.0,
                random.uniform(0.3, 0.55), WIND if random.random() < 0.6 else WIND_DK, 2)
    if e.get("cleared"):
        fx._shape(kind="flash", c=c, r=r * 0.5, col=(255, 255, 255), life=0.15)


def fx_tailwind(fx, e, col):
    """Ventoincoda (lancio): una raffica che traccia la corrente."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    fx._shape(kind="beam", a=a, b=b, col=WIND, w=0.12, life=0.35)
    _feathers(fx, a, 3, spread=0.4, col=FEATHER_HI)


def fx_tailwindbuff(fx, e, col):
    c = e.get("c")
    if c is not None:
        fx._shape(kind="ring", c=c, r0=0.9, r1=0.3, col=WIND, life=0.3, wd=0.1)


def fx_roost(fx, e, col):
    """Trespolo: si posa, piume che cadono e luce di cura."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=1.2, r1=0.3, col=HEAL, life=0.5, wd=0.14)
    _feathers(fx, (c[0], c[1] - 0.8), 6, spread=0.9, up=1.2, life=(0.7, 1.1))
    fx._rise(c, HEAL)


def fx_bulkup(fx, e, col):
    """Granfisico: armatura d'acciaio che si gonfia (anelli verso l'interno)."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=1.4, r1=0.5, col=STEEL, life=0.45, wd=0.18)
    fx._shape(kind="ring", c=c, r0=0.4, r1=1.0, col=(240, 120, 80), life=0.35, wd=0.1)
    fx._shape(kind="wing", c=(c[0], c[1] - 0.2), size=0.75, col=STEEL, life=0.4)
    fx._rise(c, (240, 150, 110))


def fx_taxi(fx, e, col):
    """Taxi Volante (lancio): segno d'atterraggio (lo disegna anche draw_taxi)."""
    c = e.get("c")
    if c is not None:
        fx._shape(kind="ring", c=c, r0=0.4, r1=float(e.get("radius", 2.5)), col=WIND, life=0.6, wd=0.12)


def fx_taxitakeoff(fx, e, col):
    c = e.get("a")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=0.3, r1=1.6, col=WIND, life=0.4, wd=0.14)
    fx._dust(c, 0.9, n=12, col=(200, 200, 190), speed=(1.4, 3.0))
    _feathers(fx, c, 5, spread=0.8)


def fx_taxiland(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.5))
    fx._shape(kind="flash", c=c, r=0.8, col=(255, 255, 255), life=0.12)
    fx._shape(kind="ring", c=c, r0=0.4, r1=r, col=WIND, life=0.45, wd=0.18)
    fx._shape(kind="ring", c=c, r0=0.2, r1=r * 0.7, col=STEEL, life=0.35, wd=0.1)
    fx._dust(c, r * 0.8, n=18, col=(200, 200, 190), speed=(1.4, 3.2))
    _feathers(fx, c, 6, spread=1.2)


def fx_bravebird(fx, e, col):
    """Baldeali: picchiata (scia infuocata d'aria) e impatto che solleva."""
    kind = e.get("kind")
    if kind == "dash":
        a, b = e.get("a"), e.get("b")
        if a is None:
            return
        fx._shape(kind="beam", a=a, b=b, col=(120, 160, 255), w=0.7, life=0.28)
        fx._shape(kind="beam", a=a, b=b, col=(240, 248, 255), w=0.25, life=0.3)
        _feathers(fx, a, 4, spread=0.5, col=FEATHER_HI)
    elif kind == "area":
        c = e.get("c")
        if c is None:
            return
        r = float(e.get("radius", 2.0))
        fx._shape(kind="flash", c=c, r=r * 0.6, col=(230, 240, 255), life=0.15)
        fx._shape(kind="ring", c=c, r0=0.3, r1=r, col=(120, 160, 255), life=0.45, wd=0.22)
        fx._shape(kind="wing", c=(c[0], c[1] - 0.4), size=1.1, col=STEEL, life=0.45)
        fx._dust(c, r, n=20, col=(210, 210, 200), speed=(1.6, 3.4))
        _feathers(fx, c, 8, spread=r)


def fx_mirror(fx, e, col):
    """Specchiarmatura: lampo d'acciaio su Corviknight e riflesso verso chi l'ha lanciato."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    fx._shape(kind="ring", c=a, r0=0.4, r1=1.1, col=STEEL_HI, life=0.3, wd=0.16)
    fx._shape(kind="beam", a=a, b=b, col=STEEL, w=0.1, life=0.3)
    fx._shape(kind="ring", c=b, r0=0.9, r1=0.2, col=STEEL, life=0.3, wd=0.1)


def fx_steal(fx, e, col):
    """Spennata: il potenziamento rubato vola dal bersaglio a Corviknight."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    fx._shape(kind="beam", a=a, b=b, col=(250, 200, 90), w=0.1, life=0.35)
    fx._shape(kind="ring", c=b, r0=1.0, r1=0.3, col=(250, 210, 110), life=0.4, wd=0.1)


STYLES = {
    "peck": fx_peck, "drillpeck": fx_drillpeck, "pluck": fx_pluck, "leer": fx_leer,
    "taunt": fx_taunt, "taunted": fx_taunted, "defog": fx_defog, "tailwind": fx_tailwind,
    "tailwindbuff": fx_tailwindbuff, "roost": fx_roost, "bulkup": fx_bulkup, "taxi": fx_taxi,
    "taxitakeoff": fx_taxitakeoff, "taxiland": fx_taxiland, "bravebird": fx_bravebird,
    "mirror": fx_mirror, "steal": fx_steal,
}


# --- disegni persistenti (stato del Match) -------------------------------------


def draw_tailwind(surface, camera, w, now):
    """Ventoincoda: corsia d'aria chiara con strisce di vento che scorrono nella
    direzione della corrente; sfuma nell'ultimo mezzo secondo."""
    ts = config.TILE_SIZE
    a, b = w["a"], w["b"]
    ax, ay = camera.world_to_screen(a.x * ts, a.y * ts)
    bx, by = camera.world_to_screen(b.x * ts, b.y * ts)
    L = math.hypot(bx - ax, by - ay)
    if L < 2:
        return
    ux, uy = (bx - ax) / L, (by - ay) / L
    px, py = -uy, ux
    half = w["width"] * ts
    fade = max(0.0, min(1.0, (w["end"] - now) / 0.5, (now - w["start"]) / 0.2))
    x0, y0 = min(ax, bx) - half - 2, min(ay, by) - half - 2
    lay = pygame.Surface((int(abs(bx - ax) + 2 * half + 4), int(abs(by - ay) + 2 * half + 4)),
                         pygame.SRCALPHA)

    def P(x, y):
        return (x - x0, y - y0)

    band = [P(ax + px * half, ay + py * half), P(bx + px * half, by + py * half),
            P(bx - px * half, by - py * half), P(ax - px * half, ay - py * half)]
    pygame.draw.polygon(lay, (*WIND, int(22 * fade)), band)
    for s in (1, -1):
        pygame.draw.line(lay, (*WIND_DK, int(110 * fade)), P(ax + px * half * s, ay + py * half * s),
                         P(bx + px * half * s, by + py * half * s), 1)
    rnd = random.Random(int(w["start"] * 1000))
    n = max(4, int(L / 10))
    for i in range(n):
        lane = rnd.uniform(-0.8, 0.8)
        speed = rnd.uniform(0.9, 1.4)
        seg = rnd.uniform(6, 14)
        u = ((now * speed * 90 + rnd.uniform(0, L)) % (L + seg)) - seg
        sx, sy = ax + ux * u + px * half * lane, ay + uy * u + py * half * lane
        ex, ey = sx + ux * seg, sy + uy * seg
        # ritaglia la striscia dentro la corsia
        t0 = max(0.0, u) / L
        t1 = min(L, u + seg) / L
        if t1 <= t0:
            continue
        sx, sy = ax + ux * L * t0 + px * half * lane, ay + uy * L * t0 + py * half * lane
        ex, ey = ax + ux * L * t1 + px * half * lane, ay + uy * L * t1 + py * half * lane
        col = WIND if i % 3 else (255, 255, 255)
        pygame.draw.line(lay, (*col, int(200 * fade)), P(sx, sy), P(ex, ey), 1)
        if i % 4 == 0:   # ricciolo di vento in punta
            pygame.draw.circle(lay, (*col, int(160 * fade)), P(ex, ey - 2), 2, 1)
    surface.blit(lay, (x0, y0))


def draw_taxi(surface, camera, fl, now):
    """Taxi Volante: bersaglio d'atterraggio (lo vedono anche i nemici) che si
    stringe durante la canalizzazione e il volo; in canalizzazione, anello di
    carica attorno a Corviknight."""
    ts = config.TILE_SIZE
    d = fl["dest"]
    cx, cy = camera.world_to_screen(d.x * ts, d.y * ts)
    r = int(fl["radius"] * ts)
    if fl["phase"] == "channel":
        prog = max(0.0, min(1.0, (now - fl["start"]) / max(1e-6, fl["end"] - fl["start"])))
    else:
        span = max(1e-6, fl.get("t1", now) - fl.get("t0", now))
        prog = 1.0 + max(0.0, min(1.0, (now - fl.get("t0", now)) / span))
    pulse = 0.5 + 0.5 * math.sin(now * 10)
    _disc(surface, cx, cy, r, WIND, int(26 + 20 * pulse))
    _disc(surface, cx, cy, r, WIND_DK, 220, 2)
    inner = max(3, int(r * (1.0 - 0.5 * (prog / 2.0))))
    _disc(surface, cx, cy, inner, (255, 255, 255), 140 + int(80 * pulse), 1)
    # mirino a 4 tacche
    for k in range(4):
        a = k * math.pi / 2 + now * 0.8
        x1, y1 = cx + math.cos(a) * (r - 6), cy + math.sin(a) * (r - 6)
        x2, y2 = cx + math.cos(a) * (r + 3), cy + math.sin(a) * (r + 3)
        pygame.draw.line(surface, STEEL_HI, (x1, y1), (x2, y2), 2)
    if fl["phase"] == "channel":
        o = fl["origin"]
        ox, oy = camera.world_to_screen(o.x * ts, o.y * ts)
        rr = int(0.9 * ts)
        rect = pygame.Rect(ox - rr, oy - rr, rr * 2, rr * 2)
        pygame.draw.arc(surface, WIND, rect, math.pi / 2, math.pi / 2 + math.tau * prog, 2)
        for side in (-1, 1):   # ali che sbattono pronte al decollo
            flap = 0.5 + 0.5 * math.sin(now * 16)
            draw_wing(surface, ox, oy - int(0.5 * ts), side, flap, 0.7 * ts, 170)
    else:
        pos = fl.get("pos", d)
        px, py = camera.world_to_screen(pos.x * ts, pos.y * ts)
        # traiettoria tratteggiata dal punto attuale all'atterraggio
        L = math.hypot(cx - px, cy - py)
        if L > 4:
            n = int(L // 8)
            for i in range(n):
                if i % 2:
                    continue
                t0, t1 = i / n, (i + 1) / n
                pygame.draw.line(surface, WIND, (px + (cx - px) * t0, py + (cy - py) * t0),
                                 (px + (cx - px) * t1, py + (cy - py) * t1), 1)


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Stati della linea Rookidee sull'unità: provocato ("!" rosso che pulsa
    sopra la testa) e Trespolo (piccolo nido di rametti sotto i piedi)."""
    r = int(u.radius * ts)
    if getattr(u, "taunt_until", -1.0) > now:
        draw_bang(surface, gx, gy - 2 * r - 12 + int(1.5 * math.sin(now * 14)))
    if getattr(u, "roost_until", -1.0) > now and getattr(u, "root_until", -1.0) > now:
        w = r * 2 + 8
        nest = pygame.Rect(gx - w // 2, gy - 2, w, 6)
        pygame.draw.ellipse(surface, (70, 46, 24), nest)
        pygame.draw.ellipse(surface, (140, 98, 52), nest.inflate(-4, -2), 1)
        for k in range(4):
            x = nest.x + 3 + k * (w - 6) // 3
            pygame.draw.line(surface, (176, 128, 70), (x - 3, nest.y + 1), (x + 3, nest.y + 4))
