"""Grafica della linea Eevee: effetti istantanei (handler registrati in
FXSystem._FX_STYLES), forme nuove per FXSystem._draw_shapes (denti di Morso,
stelle) e disegni persistenti letti dallo stato del Match a ogni frame (stelle di
Comete, Desiderio, nube del Tuono, Bora, Divinazione) e sulle unità (pozza di
Acidarmatura, ghiaccio, cuori, sabbia negli occhi, Resistenza).

Pixel art: forme piene a contorno scuro, niente smoothscale; luce da in alto a
sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

STAR = (255, 226, 92)
STAR_HI = (255, 250, 210)
STAR_OUT = (120, 84, 20)
HEART = (246, 120, 176)
HEART_OUT = (110, 30, 70)
ICE = (170, 230, 250)
ICE_HI = (235, 252, 255)
ICE_OUT = (60, 120, 160)
SAND = (214, 182, 118)
PSY = (210, 120, 220)
PSY_HI = (250, 210, 255)
BOLT = (255, 236, 90)
CLOUD = (40, 40, 58)
MOON = (230, 236, 255)
TOOTH = (250, 250, 240)
TOOTH_OUT = (70, 60, 60)

# --- helper di disegno ---------------------------------------------------------


def star_points(cx, cy, r, rot=0.0, inner=0.45):
    pts = []
    for i in range(10):
        a = rot - math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return pts


def draw_star(surface, cx, cy, r, rot=0.0, col=STAR, alpha=255):
    """Stella a 5 punte con contorno scuro e luce in alto a sinistra."""
    r = max(2, int(r))
    if alpha < 255:
        tmp = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        draw_star(tmp, r + 2, r + 2, r, rot, col)
        tmp.set_alpha(alpha)
        surface.blit(tmp, (cx - r - 2, cy - r - 2))
        return
    pygame.draw.polygon(surface, STAR_OUT, star_points(cx, cy, r + 1, rot))
    pygame.draw.polygon(surface, col, star_points(cx, cy, r, rot))
    if r >= 4:
        pygame.draw.polygon(surface, STAR_HI, star_points(cx - 1, cy - 1, r * 0.45, rot))


def draw_heart(surface, cx, cy, s, alpha=255):
    s = max(2, int(s))
    tmp = pygame.Surface((s * 4 + 2, s * 4 + 2), pygame.SRCALPHA)
    o = s * 2 + 1

    def heart(col, k):
        pygame.draw.circle(tmp, col, (o - s + 1 - k + k, o - s // 2), s + k)
        pygame.draw.circle(tmp, col, (o + s - 1, o - s // 2), s + k)
        pygame.draw.polygon(tmp, col, [(o - 2 * s - k, o - s // 3), (o + 2 * s + k - 1, o - s // 3),
                                       (o, o + 2 * s + k)])
    heart(HEART_OUT, 1)
    heart(HEART, 0)
    tmp.fill((255, 220, 236), pygame.Rect(o - s, o - s, max(1, s // 2), max(1, s // 2)))
    tmp.set_alpha(alpha)
    surface.blit(tmp, (cx - o, cy - o))


def _disc(surface, cx, cy, r, col, a, width=0):
    if r < 1:
        return
    g = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
    pygame.draw.circle(g, (*col, a), (r + 1, r + 1), r, width)
    surface.blit(g, (cx - r - 1, cy - r - 1))


# --- forme per FXSystem._draw_shapes ------------------------------------------
SHAPES = ("jaws", "star")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    if kind == "jaws":
        # Morso: due arcate (mascella sopra e sotto) che si chiudono sul bersaglio;
        # i denti a punta si INCASTRANO (file sfalsate di mezzo dente), poi svaniscono.
        cx, cy = S(*s["c"])
        t = 1.0 - f
        close = min(1.0, t / 0.4)
        close = close * close * (3 - 2 * close)            # scatto morbido
        w = max(6, int(s.get("w", 0.5) * ts))             # mezza larghezza dell'arcata
        th = max(3, int(0.28 * ts))                       # altezza di un dente
        gap = int((1.0 - close) * 0.5 * ts)               # distanza delle punte dal centro
        n = 3
        tw = (2 * w) // n
        aa = 255 if f > 0.3 else int(255 * f / 0.3)
        for row in (-1, 1):                               # -1 = mascella sopra
            # le punte arrivano a cy -/+ gap; l'arcata è curva (bordi più alti)
            off = 0 if row < 0 else tw // 2
            gum_y = cy + row * (gap + th)
            gum = []
            for i in range(n + (0 if row < 0 else -1)):
                x0 = cx - w + off + i * tw
                bend = int(2 * abs((x0 + tw / 2 - cx) / max(1, w)))   # curva dell'arcata
                by = gum_y + row * bend
                tip = (x0 + tw // 2, cy + row * gap + row * bend // 2)
                pygame.draw.polygon(overlay, (*TOOTH_OUT, aa),
                                    [(x0 - 1, by), (x0 + tw, by), (tip[0], tip[1] - row)])
                pygame.draw.polygon(overlay, (*TOOTH, aa), [(x0, by), (x0 + tw - 1, by), tip])
                gum.append((x0, by))
                gum.append((x0 + tw, by))
            if len(gum) >= 2:                              # gengiva scura sopra/sotto i denti
                pygame.draw.lines(overlay, (*s["col"], aa), False, gum, 2)
        if close >= 1.0 and f > 0.3:   # scatto: lampo sul punto di chiusura
            pygame.draw.line(overlay, (255, 255, 255, aa), (cx - w + 2, cy), (cx + w - 2, cy), 1)
    elif kind == "star":
        # stellina che vola/ruota (scintille di Comete, Desiderio, Magibrillio)
        age = s["maxlife"] - s["life"]
        px, py = S(s["c"][0] + s["v"][0] * age, s["c"][1] + s["v"][1] * age)
        draw_star(overlay, px, py, s.get("r", 0.18) * ts, age * 6 + s.get("rot", 0.0),
                  s["col"], int(255 * f))


# --- handler degli eventi (FXSystem._FX_STYLES) --------------------------------


def _stars(fx, c, n, col=STAR, spread=0.5, speed=1.6, r=0.16, life=(0.35, 0.6)):
    for _ in range(n):
        a = random.uniform(0, math.tau)
        v = random.uniform(0.4, 1.0) * speed
        fx._shape(kind="star", c=(c[0] + math.cos(a) * spread * 0.3, c[1] + math.sin(a) * spread * 0.3),
                  v=(math.cos(a) * v, math.sin(a) * v - 0.4), r=r * random.uniform(0.7, 1.2),
                  rot=random.uniform(0, 6), col=col, life=random.uniform(*life))


def fx_tackle(fx, e, col):
    """Azione: impatto corto (urto) davanti a Eevee."""
    o, d = e.get("o"), e.get("dir")
    if o is None:
        return
    rng = e.get("range", 2.0)
    c = (o[0] + d[0] * rng * 0.7, o[1] + d[1] * rng * 0.7)
    fx._shape(kind="flash", c=c, r=0.45, col=(255, 250, 230), life=0.12)
    fx._shape(kind="ring", c=c, r0=0.15, r1=0.75, col=col, life=0.25, wd=0.14)
    fx._dust(c, 0.4, n=6, col=col, speed=(1.0, 2.2))


def fx_doubleedge(fx, e, col):
    """Sdoppiatore: urto più grosso + scintilla rossa di contraccolpo su Eevee."""
    fx_tackle(fx, e, col)
    o, d = e.get("o"), e.get("dir")
    rng = e.get("range", 2.2)
    c = (o[0] + d[0] * rng * 0.7, o[1] + d[1] * rng * 0.7)
    fx._shape(kind="ring", c=c, r0=0.3, r1=1.2, col=_hi(col), life=0.32, wd=0.2)
    fx._shape(kind="ring", c=o, r0=0.7, r1=0.2, col=(240, 80, 70), life=0.3, wd=0.1)


def fx_jaws(fx, e, col):
    """Morso: denti che si chiudono sul primo bersaglio davanti."""
    o, d = e.get("o"), e.get("dir")
    if o is None:
        return
    rng = e.get("range", 2.3)
    c = (o[0] + d[0] * rng * 0.65, o[1] + d[1] * rng * 0.65 - 0.2)
    fx._shape(kind="jaws", c=c, col=_dk(col), w=0.55, life=0.42)
    fx._dust(c, 0.3, n=5, col=col, speed=(0.6, 1.6))


def fx_sandattack(fx, e, col):
    """Turbosabbia: getto di sabbia (granelli che volano)."""
    seg = fx._ab(e)
    if seg is None:
        return
    ax, ay, bx, by = seg
    for _ in range(12):
        u = random.uniform(0.1, 1.0)
        fx._add(ax + (bx - ax) * u, ay + (by - ay) * u,
                (bx - ax) * 3 + random.uniform(-1, 1), (by - ay) * 3 + random.uniform(-1, 1),
                random.uniform(0.25, 0.5), SAND, random.randint(1, 2))


def fx_quickattack(fx, e, col):
    """Rapidattacco: scia bianca veloce con linee di velocità."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    fx._shape(kind="beam", a=a, b=b, col=(240, 244, 255), w=0.35, life=0.18)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    px, py = -math.sin(ang), math.cos(ang)
    for k in (-1, 1):
        off = 0.35 * k
        fx._shape(kind="beam", a=(a[0] + px * off, a[1] + py * off),
                  b=(b[0] + px * off * 0.4, b[1] + py * off * 0.4), col=col, w=0.08, life=0.22)
    fx._dust(b, 0.4, n=8, col=(220, 220, 210))


def fx_tailwhip(fx, e, col):
    """Colpocoda: frustata circolare + piccoli simboli 'giù' sui nemici."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.6))
    fx._shape(kind="arc", o=c, base=random.uniform(0, 6.28), half=math.radians(160), rng=r * 0.8,
              col=col, life=0.3)
    fx._shape(kind="ring", c=c, r0=0.4, r1=r, col=(150, 170, 230), life=0.4, wd=0.12)


def fx_wishcast(fx, e, col):
    c = e.get("c")
    if c is not None:
        _stars(fx, (c[0], c[1] - 1.5), 5, spread=0.6, speed=0.8)


def fx_wishheal(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="flash", c=c, r=0.7, col=STAR_HI, life=0.2)
    fx._shape(kind="ring", c=c, r0=0.2, r1=1.2, col=(140, 240, 140), life=0.45, wd=0.14)
    _stars(fx, c, 8, spread=0.8, speed=2.2)
    fx._rise(c, (140, 240, 140))


def fx_starhit(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="flash", c=c, r=0.35, col=STAR_HI, life=0.12)
    _stars(fx, c, 3, speed=2.0, r=0.1, life=(0.2, 0.35))


def fx_endure(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=1.2, r1=0.4, col=(255, 120, 90), life=0.4, wd=0.18)
    fx._rise(c, (255, 170, 120))


def fx_thundercloud(fx, e, col):
    c = e.get("c")
    if c is not None:
        fx._shape(kind="ring", c=c, r0=0.5, r1=float(e.get("radius", 3.0)), col=BOLT, life=0.35,
                  wd=0.12)


def fx_thunderstrike(fx, e, col):
    """Tuono: un fulmine cade dal cielo e scoppia a terra."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 1.1))
    top = (c[0] + random.uniform(-0.6, 0.6), c[1] - 6.0)
    fx._shape(kind="bolt", a=top, b=c, col=BOLT, life=0.2)
    fx._shape(kind="bolt", a=top, b=c, col=(255, 255, 230), life=0.12)
    fx._shape(kind="flash", c=c, r=r * 0.8, col=(255, 250, 200), life=0.14)
    fx._shape(kind="ring", c=c, r0=0.2, r1=r, col=BOLT, life=0.3, wd=0.14)
    for _ in range(6):
        a = random.uniform(0, math.tau)
        fx._add(c[0], c[1], math.cos(a) * 3, math.sin(a) * 3, 0.25, BOLT, 1)


def fx_flareblitz(fx, e, col):
    """Fuococarica: scia di fiamme lungo la carica + esplosione all'arrivo."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    fx._shape(kind="beam", a=a, b=b, col=(255, 120, 40), w=0.9, life=0.35)
    fx._shape(kind="beam", a=a, b=b, col=(255, 220, 120), w=0.35, life=0.25)
    n = 10
    for i in range(n):
        u = i / n
        p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        fx._shape(kind="puff", c=p, v=(random.uniform(-0.3, 0.3), -random.uniform(0.6, 1.4)),
                  r0=0.12, r1=0.3, col=random.choice(((255, 140, 40), (240, 70, 30))),
                  life=random.uniform(0.3, 0.55))
    fx._shape(kind="flash", c=b, r=1.0, col=(255, 230, 160), life=0.18)
    fx._shape(kind="ring", c=b, r0=0.3, r1=1.6, col=(255, 110, 40), life=0.4, wd=0.25)


def fx_leafblade(fx, e, col):
    """Fendifoglia: taglio verde lungo lo scatto + foglie."""
    a, b = e.get("a"), e.get("b")
    if a is None:
        return
    fx._shape(kind="beam", a=a, b=b, col=(120, 220, 110), w=0.25, life=0.25)
    fx._shape(kind="beam", a=a, b=b, col=(230, 255, 210), w=0.08, life=0.2)
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    fx._slash(a, b, (140, 230, 120))
    for _ in range(8):
        u = random.random()
        p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        fx._shape(kind="leaf", a=p, b=(p[0] + random.uniform(-1, 1), p[1] + random.uniform(-1, 0.5)),
                  col=(110, 200, 90), sz=0.22, spin=True, life=random.uniform(0.3, 0.5))
    fx._shape(kind="ring", c=mid, r0=0.2, r1=1.0, col=(150, 240, 130), life=0.3, wd=0.1)


def fx_futuremark(fx, e, col):
    c = e.get("c")
    if c is not None:
        fx._shape(kind="flash", c=c, r=0.6, col=PSY_HI, life=0.2)


def fx_futureblast(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.6))
    fx._shape(kind="flash", c=c, r=r * 0.9, col=PSY_HI, life=0.22)
    fx._shape(kind="ring", c=c, r0=0.3, r1=r, col=PSY, life=0.45, wd=0.35)
    fx._shape(kind="ring", c=c, r0=0.2, r1=r * 1.2, col=PSY_HI, life=0.3, wd=0.12)
    fx._splash(c, r, PSY, n=24)


def fx_blizzardcast(fx, e, col):
    c = e.get("c")
    if c is not None:
        fx._shape(kind="ring", c=c, r0=0.5, r1=float(e.get("radius", 4.0)), col=ICE, life=0.4,
                  wd=0.2)


def fx_freeze(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="flash", c=c, r=0.6, col=ICE_HI, life=0.2)
    fx._shape(kind="ring", c=c, r0=1.0, r1=0.3, col=ICE, life=0.35, wd=0.16)
    for _ in range(8):
        a = random.uniform(0, math.tau)
        fx._add(c[0], c[1], math.cos(a) * 2.5, math.sin(a) * 2.5, 0.4, ICE_HI, 1)


def fx_moonlight(fx, e, col):
    """Lucelunare: colonna di luce lunare che scende su Umbreon."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="beam", a=(c[0], c[1] - 5.0), b=c, col=MOON, w=0.9, life=0.5)
    fx._shape(kind="beam", a=(c[0], c[1] - 5.0), b=c, col=(255, 250, 170), w=0.3, life=0.4)
    fx._shape(kind="ring", c=c, r0=0.3, r1=1.6, col=(255, 240, 150), life=0.5, wd=0.16)
    _stars(fx, c, 6, col=(255, 240, 150), spread=1.0, speed=1.0)


def fx_gleam(fx, e, col):
    """Magibrillio: esplosione di luce rosa con stelline."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 3.6))
    fx._shape(kind="flash", c=c, r=r * 0.7, col=(255, 230, 245), life=0.2)
    for k in range(3):
        fx._shape(kind="ring", c=c, r0=0.3, r1=r * (0.6 + 0.2 * k), col=HEART, life=0.45,
                  wd=0.14, wait=k * 0.08)
    _stars(fx, c, 14, col=(255, 200, 230), spread=r, speed=3.0)


def fx_acidarmor(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._splash(c, 1.0, (90, 150, 230), n=18)
    fx._shape(kind="ring", c=c, r0=0.2, r1=1.3, col=(150, 110, 210), life=0.4, wd=0.14)


def fx_hydration(fx, e, col):
    c = e.get("c")
    if c is not None:
        fx._shape(kind="ring", c=c, r0=0.9, r1=0.2, col=(120, 190, 255), life=0.35, wd=0.12)
        fx._splash(c, 0.6, (120, 190, 255), n=8)


def fx_voltabsorb(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    for _ in range(3):
        a = random.uniform(0, math.tau)
        fx._shape(kind="bolt", a=(c[0] + math.cos(a) * 1.4, c[1] + math.sin(a) * 1.4), b=c,
                  col=BOLT, life=0.2)
    fx._shape(kind="ring", c=c, r0=1.0, r1=0.2, col=(140, 255, 140), life=0.35, wd=0.12)


def fx_flashfire(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=0.2, r1=1.1, col=(255, 150, 40), life=0.35, wd=0.16)
    for _ in range(6):
        fx._shape(kind="puff", c=(c[0] + random.uniform(-0.4, 0.4), c[1]),
                  v=(0, -random.uniform(1.0, 2.0)), r0=0.1, r1=0.25, col=(255, 130, 40),
                  life=random.uniform(0.3, 0.5))


def fx_charm(fx, e, col):
    c = e.get("c")
    if c is not None:
        fx._shape(kind="ring", c=c, r0=0.8, r1=0.2, col=HEART, life=0.35, wd=0.12)


def fx_miss(fx, e, col):
    """Attacco base accecato: sbuffo di sabbia e nessun colpo."""
    c = e.get("c")
    if c is not None:
        fx._dust(c, 0.3, n=6, col=SAND, speed=(0.6, 1.4))


def fx_sync(fx, e, col):
    a, b = e.get("a"), e.get("b")
    if a is not None:
        fx._shape(kind="beam", a=a, b=b, col=PSY, w=0.12, life=0.3)
        fx._shape(kind="ring", c=b, r0=0.8, r1=0.2, col=PSY_HI, life=0.3, wd=0.1)


def _hi(c):
    return tuple(min(255, int(v + (255 - v) * 0.5)) for v in c)


def _dk(c):
    return tuple(int(v * 0.45) for v in c)


STYLES = {
    "tackle": fx_tackle, "doubleedge": fx_doubleedge, "jaws": fx_jaws,
    "sandattack": fx_sandattack, "quickattack": fx_quickattack, "tailwhip": fx_tailwhip,
    "wishcast": fx_wishcast, "wishheal": fx_wishheal, "starhit": fx_starhit,
    "endure": fx_endure, "thundercloud": fx_thundercloud, "thunderstrike": fx_thunderstrike,
    "flareblitz": fx_flareblitz, "leafblade": fx_leafblade, "futuremark": fx_futuremark,
    "futureblast": fx_futureblast, "blizzardcast": fx_blizzardcast, "freeze": fx_freeze,
    "moonlight": fx_moonlight, "gleam": fx_gleam, "acidarmor": fx_acidarmor,
    "hydration": fx_hydration, "voltabsorb": fx_voltabsorb, "flashfire": fx_flashfire,
    "charm": fx_charm, "miss": fx_miss, "sync": fx_sync,
}


# --- disegni persistenti (stato del Match) -------------------------------------


def draw_swift_star(surface, camera, st, now):
    ts = config.TILE_SIZE
    if now < st["start"]:
        return
    x, y = st["pos"].x, st["pos"].y
    dx, dy = st["dir"].x, st["dir"].y
    for k in range(4, 0, -1):      # scia di scintille
        sx, sy = camera.world_to_screen((x - dx * 0.22 * k) * ts, (y - dy * 0.22 * k) * ts)
        surface.fill(STAR if k < 3 else STAR_OUT, pygame.Rect(sx - 1, sy - 1, 2, 2))
    sx, sy = camera.world_to_screen(x * ts, y * ts)
    _disc(surface, sx, sy, 7, STAR, 50)
    draw_star(surface, sx, sy, 5, st["spin"])


def draw_wish(surface, camera, w, world, now):
    """Desiderio: una stella scende piano sul bersaglio nei 2 secondi d'attesa."""
    ts = config.TILE_SIZE
    tgt = world.get(w["target_id"])
    if tgt is None or not tgt.alive:
        return
    span = max(1e-6, w["at"] - w["start"])
    t = max(0.0, min(1.0, (now - w["start"]) / span))
    x, y = tgt.pos.x, tgt.pos.y - 0.9 - 2.4 * (1.0 - t)
    sx, sy = camera.world_to_screen(x * ts, y * ts)
    pulse = 0.5 + 0.5 * math.sin(now * 10)
    _disc(surface, sx, sy, 9 + int(2 * pulse), STAR_HI, 60)
    draw_star(surface, sx, sy, 6, now * 2.0)
    gx, gy = camera.world_to_screen(tgt.pos.x * ts, tgt.pos.y * ts)
    pygame.draw.ellipse(surface, STAR, pygame.Rect(gx - 8, gy - 3, 16, 6), 1)   # punto d'arrivo


def draw_thunder(surface, camera, th, now):
    """Tuono: nube scura sopra l'area con bagliori elettrici al bordo."""
    ts = config.TILE_SIZE
    cx, cy = camera.world_to_screen(th["c"].x * ts, th["c"].y * ts)
    r = int(th["radius"] * ts)
    _disc(surface, cx, cy, r, CLOUD, 70)
    flick = (int(now * 20) % 3 == 0)
    _disc(surface, cx, cy, r, BOLT if flick else (180, 170, 90), 150, 1)
    for i in range(6):                         # sbuffi di nube che girano
        a = now * 0.8 + i * math.tau / 6
        px = cx + int(math.cos(a) * r * 0.6)
        py = cy + int(math.sin(a) * r * 0.35) - 4
        _disc(surface, px, py, max(4, r // 4), (60, 60, 82), 110)


def draw_blizzard(surface, camera, bz, now):
    """Bora: disco di ghiaccio sempre più fitto di fiocchi; anello che si chiude
    (chi resta dentro fino alla fine si congela)."""
    ts = config.TILE_SIZE
    cx, cy = camera.world_to_screen(bz["c"].x * ts, bz["c"].y * ts)
    r = int(bz["radius"] * ts)
    span = max(1e-6, bz["end"] - bz["start"])
    t = max(0.0, min(1.0, (now - bz["start"]) / span))
    _disc(surface, cx, cy, r, ICE, int(40 + 60 * t))
    _disc(surface, cx, cy, r, ICE_HI, 200, 2)
    _disc(surface, cx, cy, max(2, int(r * (1.0 - t))), ICE_OUT, 160, 1)   # timer
    n = 14 + int(30 * t)
    rnd = random.Random(int(bz["start"] * 1000))
    for i in range(n):
        a0 = rnd.uniform(0, math.tau)
        rr = r * math.sqrt(rnd.random())
        a = a0 + now * (1.2 + 0.8 * t)
        px = cx + int(math.cos(a) * rr)
        py = cy + int(math.sin(a) * rr * 0.8)
        col = ICE_HI if i % 3 else (255, 255, 255)
        surface.fill(col, pygame.Rect(px, py, 2, 2))
        if i % 5 == 0:
            pygame.draw.line(surface, col, (px - 2, py), (px + 2, py))
            pygame.draw.line(surface, col, (px, py - 2), (px, py + 2))


def draw_future_sight(surface, camera, fs, now):
    """Divinazione: cerchio viola con anelli che convergono fino all'esplosione."""
    ts = config.TILE_SIZE
    cx, cy = camera.world_to_screen(fs["c"].x * ts, fs["c"].y * ts)
    r = int(fs["radius"] * ts)
    span = max(1e-6, fs["at"] - fs["start"])
    t = max(0.0, min(1.0, (now - fs["start"]) / span))
    _disc(surface, cx, cy, r, PSY, int(30 + 70 * t))
    _disc(surface, cx, cy, r, PSY_HI, 220, 2)
    for k in range(3):
        u = (t * 2.0 + k / 3.0) % 1.0
        rr = int(r * (1.0 - u))
        if rr > 2:
            _disc(surface, cx, cy, rr, PSY_HI, int(160 * u), 1)
    _disc(surface, cx, cy, max(2, int(r * t)), (255, 255, 255), 80)


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Stati della linea Eevee disegnati sull'unità (sopra lo sprite)."""
    r = int(u.radius * ts)
    if u.frozen_until > now:                    # congelato: blocco di ghiaccio
        w, h = r * 2 + 6, r * 2 + 8
        blk = pygame.Surface((w, h), pygame.SRCALPHA)
        blk.fill((*ICE, 120))
        pygame.draw.rect(blk, (*ICE_OUT, 230), blk.get_rect(), 1)
        pygame.draw.line(blk, (*ICE_HI, 230), (2, 2), (w - 4, 2))
        pygame.draw.line(blk, (*ICE_HI, 230), (2, 2), (2, h - 4))
        pygame.draw.line(blk, (*ICE_HI, 160), (w // 3, 4), (w // 2, h // 2))
        surface.blit(blk, (gx - w // 2, gy - h + 3))
    if u.charm_until > now:                     # affascinato: cuori che girano
        for i in range(2):
            a = now * 3.0 + i * math.pi
            draw_heart(surface, gx + int(math.cos(a) * (r + 3)), gy - 2 * r - 6 + int(math.sin(a) * 2), 2)
    if u.blind_until > now:                     # sabbia negli occhi
        for i in range(5):
            a = now * 6.0 + i * 1.3
            surface.fill(SAND, pygame.Rect(gx + int(math.cos(a) * (r + 1)) - 1,
                                           gy - r - 2 + int(math.sin(a) * 2), 2, 1))
    if u.endure_until > now:                    # Resistenza: contorno rosso pulsante
        pulse = 0.5 + 0.5 * math.sin(now * 12)
        _disc(surface, gx, gy - r, r + 4, (255, 90, 70), int(70 + 80 * pulse), 2)


def draw_puddle(surface, u, gx, gy, now, ts):
    """Acidarmatura: Vaporeon sciolto in una pozza che ondeggia (al posto dello
    sprite), con due occhietti."""
    r = int(u.radius * ts) + 4
    w, h = r * 2 + 4, r + 4
    pud = pygame.Surface((w, h), pygame.SRCALPHA)
    wob = int(1.5 * math.sin(now * 5))
    pygame.draw.ellipse(pud, (30, 60, 120, 200), pygame.Rect(0, 1, w, h - 2))
    pygame.draw.ellipse(pud, (70, 130, 220, 220), pygame.Rect(2, 2, w - 4 + wob, h - 5))
    pygame.draw.ellipse(pud, (150, 200, 255, 200), pygame.Rect(4, 3, w // 3, 3))
    for k in range(2):
        rr = int(((now * 1.5 + k * 0.5) % 1.0) * r)
        pygame.draw.ellipse(pud, (190, 225, 255, 120), pygame.Rect(w // 2 - rr, h // 2 - rr // 3,
                                                                    rr * 2, max(2, rr * 2 // 3)), 1)
    pud.fill((20, 20, 40, 255), pygame.Rect(w // 2 - 3, h // 2 - 1, 1, 2))
    pud.fill((20, 20, 40, 255), pygame.Rect(w // 2 + 2, h // 2 - 1, 1, 2))
    surface.blit(pud, (gx - w // 2, gy - h // 2))


# --- interfaccia ---------------------------------------------------------------
PASSIVE_NAMES = {"assorbivolt": "Assorbivolt", "fuocardore": "Fuocardore",
                 "sincronismo": "Sincronismo", "mantelneve": "Mantelneve",
                 "fogliamanto": "Fogliamanto", "forzainteriore": "Forza Interiore",
                 "incantevole": "Incantevole", "idratazione": "Idratazione"}
CHOICE_AXES = {"Q": ("Offensivo", "Protettivo"), "W": ("Ravvicinato", "A distanza"),
               "E": ("Rapido", "Solido")}


def readable(col):
    """Colore della forma leggibile su fondo scuro (Umbreon è quasi nero)."""
    col = tuple(col)
    if sum(col) < 200:
        return (150, 150, 175)
    return col
