"""Grafica della linea Noibat > Noivern: effetti istantanei (handler registrati
in FXSystem._FX_STYLES), forme nuove per FXSystem._draw_shapes (arco sonoro,
onda in volo, lama d'aria, meteora, folata) e disegni persistenti letti dallo
stato del Match a ogni frame (ping di Ecolocalizzazione, Tifone, Dragobolide in
arrivo) e sulle unità (cariche del ping sotto la barra della vita).

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

SOUND = (190, 160, 255)        # onde sonore: viola chiaro
SOUND_HI = (244, 238, 255)
SOUND_DK = (78, 52, 150)
SCREECH = (255, 128, 176)      # Stridio: rosa acceso, stridente
SCREECH_DK = (130, 30, 80)
SONAR = (110, 236, 220)        # ping: verde acqua (orecchie di Noivern)
SONAR_DK = (24, 110, 110)
DRAGON = (124, 84, 240)
DRAGON_HI = (214, 196, 255)
DRAGON_DK = (40, 22, 110)
WIND = (214, 240, 246)
WIND_DK = (112, 156, 176)
METEOR = (255, 132, 58)
METEOR_HI = (255, 232, 150)
METEOR_DK = (120, 34, 30)
ROCK = (66, 44, 70)

ECHO_DEX = (714, 715)          # Noibat, Noivern (online il passive_id degli altri non arriva)


def _disc(surface, cx, cy, r, col, a, width=0):
    if r < 1:
        return
    g = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
    pygame.draw.circle(g, (*col, a), (r + 1, r + 1), r, width)
    surface.blit(g, (cx - r - 1, cy - r - 1))


def _arc_pts(cx, cy, ang, r, half, n=None, jag=0.0, squash=1.0):
    n = n or max(4, int(r * half / 3) + 2)
    pts = []
    for i in range(n + 1):
        a = ang - half + 2 * half * i / n
        rr = r + (jag if i % 2 else -jag)
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr * squash))
    return pts


def draw_soundarc(surface, cx, cy, ang, r, half, width, alpha,
                  cols=(SOUND_DK, SOUND, SOUND_HI), jag=0.0):
    """Arco d'onda sonora a tre strati (contorno, colore, luce)."""
    if r < 2 or alpha <= 0:
        return
    pts = _arc_pts(cx, cy, ang, r, half, jag=jag)
    w = max(1, int(width))
    pygame.draw.lines(surface, (*cols[0], alpha), False, pts, w + 2)
    pygame.draw.lines(surface, (*cols[1], alpha), False, pts, w)
    if w >= 2:
        pygame.draw.lines(surface, (*cols[2], alpha), False, pts, 1)


def draw_blade(surface, cx, cy, ang, size, alpha):
    """Lama d'aria: mezzaluna bianco-azzurra con il filo chiaro davanti."""
    ca, sa = math.cos(ang), math.sin(ang)
    outer, inner = [], []
    for i in range(9):
        t = -1.0 + 2.0 * i / 8
        a = t * 1.15
        ox, oy = math.cos(a) * size, math.sin(a) * size
        ix, iy = math.cos(a) * size * 0.62 - size * 0.18, math.sin(a) * size * 0.7
        outer.append((cx + ox * ca - oy * sa, cy + ox * sa + oy * ca))
        inner.append((cx + ix * ca - iy * sa, cy + ix * sa + iy * ca))
    poly = outer + inner[::-1]
    pygame.draw.polygon(surface, (*WIND_DK, alpha), poly)
    shrink = [(cx + (x - cx) * 0.86, cy + (y - cy) * 0.86) for x, y in poly]
    pygame.draw.polygon(surface, (*WIND, alpha), shrink)
    pygame.draw.lines(surface, (255, 255, 255, alpha), False, outer[1:-1], 1)


# --- forme per FXSystem._draw_shapes ------------------------------------------

SHAPES = ("soundarc", "sonicbolt", "airblade", "dragonbeam", "windline", "crater", "gust")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "soundarc":
        # Arco che si allarga dal centro (onde di Stridio, Granvoce, impatti).
        cx, cy = S(*s["c"])
        r = (s["r0"] + (s["r1"] - s["r0"]) * min(1.0, t * s.get("speed", 1.0))) * ts
        al = int(255 * min(1.0, f * 2.2))
        draw_soundarc(overlay, cx, cy, s.get("ang", 0.0), r, s.get("half", math.pi),
                      s.get("w", 0.12) * ts, al, s.get("cols", (SOUND_DK, SOUND, SOUND_HI)),
                      s.get("jag", 0.0) * ts)
    elif kind == "sonicbolt":
        # Onda in volo da A a B: tre archetti ")))" che avanzano insieme.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.8)
        ang = math.atan2(by - ay, bx - ax)
        sc = s.get("sc", 1.0)
        cols = s.get("cols", (SOUND_DK, SOUND, SOUND_HI))
        for k in range(3):
            uk = max(0.0, u - 0.07 * k)
            px, py = ax + (bx - ax) * uk, ay + (by - ay) * uk
            wob = math.sin(uk * 18 + k) * s.get("wob", 0.0) * ts
            px += -math.sin(ang) * wob
            py += math.cos(ang) * wob
            r = (0.22 + 0.07 * k) * ts * sc
            draw_soundarc(overlay, px, py, ang, r, 0.95, max(1, 0.07 * ts * sc),
                          int(255 * (1.0 - 0.22 * k) * min(1.0, f * 3)), cols)
    elif kind == "airblade":
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.85)
        ang = math.atan2(by - ay, bx - ax)
        px, py = ax + (bx - ax) * u, ay + (by - ay) * u
        for k in (2, 1):   # scia: due lame più tenui dietro
            draw_blade(overlay, px - math.cos(ang) * k * 0.3 * ts, py - math.sin(ang) * k * 0.3 * ts,
                       ang, s.get("size", 0.32) * ts * (1 - 0.15 * k), int(70 * f / k))
        draw_blade(overlay, px, py, ang, s.get("size", 0.32) * ts, int(255 * min(1.0, f * 3)))
    elif kind == "dragonbeam":
        # Raggio di Dragopulsar: corpo viola che pulsa a onde, contorno scuro,
        # nucleo chiaro e anelli che scorrono verso la punta.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        L = math.hypot(bx - ax, by - ay)
        if L < 2:
            return
        ux, uy = (bx - ax) / L, (by - ay) / L
        px, py = -uy, ux
        age = s["maxlife"] - s["life"]
        grow = min(1.0, age / 0.06)   # il raggio esce in un lampo
        w0 = s.get("w", 0.36) * ts * (0.35 + 0.65 * f)
        n = max(6, int(L / 4))
        top, bot = [], []
        for i in range(n + 1):
            u = i / n * grow
            wob = 1.0 + 0.22 * math.sin(u * L / ts * 3.0 - age * 40.0)
            w = w0 * wob * (0.55 + 0.45 * min(1.0, u * 6))   # più stretto alla bocca
            x, y = ax + ux * L * u, ay + uy * L * u
            top.append((x + px * w, y + py * w))
            bot.append((x - px * w, y - py * w))
        poly = top + bot[::-1]
        al = int(255 * min(1.0, f * 2.0))
        pygame.draw.polygon(overlay, (*DRAGON_DK, al), poly)
        mid = [((tx + bx_) / 2, (ty + by_) / 2) for (tx, ty), (bx_, by_) in zip(top, bot)]
        body = [(m[0] + (t[0] - m[0]) * 0.72, m[1] + (t[1] - m[1]) * 0.72) for m, t in zip(mid, top)]
        body += [(m[0] + (b[0] - m[0]) * 0.72, m[1] + (b[1] - m[1]) * 0.72)
                 for m, b in zip(mid[::-1], bot[::-1])]
        pygame.draw.polygon(overlay, (*DRAGON, al), body)
        tip = (ax + ux * L * grow, ay + uy * L * grow)
        pygame.draw.line(overlay, (*DRAGON_HI, al), (ax, ay), tip, max(2, int(w0 * 0.45)))
        pygame.draw.line(overlay, (255, 255, 255, al), (ax, ay), tip, 1)
        for k in range(4):   # anelli che scorrono
            u = ((age * 3.5 + k / 4) % 1.0) * grow
            cx_, cy_ = ax + ux * L * u, ay + uy * L * u
            draw_soundarc(overlay, cx_, cy_, math.atan2(uy, ux), w0 * 1.5, 1.1, 2, al,
                          (DRAGON_DK, (120, 230, 210), (230, 255, 250)))
        pygame.draw.circle(overlay, (*DRAGON_HI, al), (int(tip[0]), int(tip[1])), max(2, int(w0 * 1.1)))
        pygame.draw.circle(overlay, (255, 255, 255, al), (int(tip[0]), int(tip[1])), max(1, int(w0 * 0.5)))
    elif kind == "windline":
        # Scia di vento sottile che si ritira verso la punta (scatti, respinte).
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u0 = min(1.0, t * 1.3)
        sx, sy = ax + (bx - ax) * u0, ay + (by - ay) * u0
        al = int(230 * min(1.0, f * 2.0))
        pygame.draw.line(overlay, (*WIND_DK, al), (sx, sy), (bx, by), 3)
        pygame.draw.line(overlay, (*WIND, al), (sx, sy), (bx, by), 1)
    elif kind == "crater":
        # Punto d'impatto di una meteora: anello di fuoco che si allarga e
        # chiazza bruciata a terra.
        cx, cy = S(*s["c"])
        r = s.get("r", 0.5) * ts
        rr = int(r * (0.4 + 0.6 * min(1.0, t * 3)))
        al = int(255 * min(1.0, f * 2.0))
        pygame.draw.ellipse(overlay, (*ROCK, int(al * 0.9)), pygame.Rect(cx - rr, cy - rr // 2, rr * 2, rr))
        pygame.draw.ellipse(overlay, (*METEOR, al), pygame.Rect(cx - rr, cy - rr // 2, rr * 2, rr), 2)
        if t < 0.4:
            pygame.draw.ellipse(overlay, (*METEOR_HI, al),
                                pygame.Rect(cx - rr // 2, cy - rr // 4, rr, max(2, rr // 2)))
    elif kind == "gust":
        # Folata che gira attorno a un centro e si allarga.
        cx, cy = S(*s["c"])
        age = s["maxlife"] - s["life"]
        r = (s["r0"] + (s["r1"] - s["r0"]) * t) * ts
        ang = s.get("a0", 0.0) + age * s.get("spin", 7.0)
        pts = _arc_pts(cx, cy, ang, r, s.get("half", 0.55), n=8, squash=0.8)
        al = int(230 * min(1.0, f * 2.5))
        pygame.draw.lines(overlay, (*WIND_DK, al), False, pts, 3)
        pygame.draw.lines(overlay, (*WIND, al), False, pts, 1)


# --- handler degli eventi (FXSystem._FX_STYLES) --------------------------------


def _ab(e):
    a, b = e.get("a"), e.get("b")
    return (a, b) if a is not None and b is not None else None


def _ang(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def fx_sonic(fx, e, col):
    """Attacco base: onda sonora in volo e piccolo anello d'impatto."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="sonicbolt", a=a, b=b, col=SOUND, life=0.2, sc=1.0)
    fx._shape(kind="soundarc", c=b, ang=_ang(a, b), r0=0.15, r1=0.6, half=1.1, w=0.08,
              col=SOUND, life=0.22, wait=0.15)


def fx_echoping(fx, e, col):
    """Ping: tre onde verde acqua che si allargano fino al raggio rivelato."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 6.0))
    cols = (SONAR_DK, SONAR, (230, 255, 250))
    fx._shape(kind="soundarc", c=c, ang=0.0, r0=0.3, r1=r, half=math.pi, w=0.06,
              col=SONAR, life=0.5, cols=cols)
    fx._shape(kind="soundarc", c=c, ang=0.0, r0=0.15, r1=0.9, half=math.pi, w=0.06,
              col=SONAR, life=0.3, cols=cols)


def fx_supersonic(fx, e, col):
    """Supersuono: onda tremolante (confonde) e spirale sull'impatto."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="sonicbolt", a=a, b=b, col=SOUND, life=0.4, sc=1.6, wob=0.18)
    for k in range(3):
        fx._shape(kind="soundarc", c=b, ang=_ang(a, b) + k * 2.1, r0=0.2, r1=0.8,
                  half=0.9, w=0.08, col=SOUND, life=0.35, wait=0.3 + 0.06 * k)


def fx_dragonpulse(fx, e, col):
    """Dragopulsar: raggio a tre strati viola, anelli che lo percorrono e
    lampo all'estremità."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="dragonbeam", a=a, b=b, w=0.36, col=DRAGON, life=0.45)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    for _ in range(int(6 + L)):
        u = random.random()
        fx._add(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u,
                random.uniform(-0.8, 0.8), random.uniform(-1.4, -0.4),
                random.uniform(0.3, 0.55), random.choice((DRAGON_HI, (120, 230, 210))), 1)


def fx_aircutter(fx, e, col):
    """Aerasoio: una lama d'aria per proiettile (il ventaglio ne manda tre)."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="airblade", a=a, b=b, col=WIND, life=0.3, size=0.34)
    fx._shape(kind="soundarc", c=b, ang=_ang(a, b) + math.pi / 2, r0=0.1, r1=0.45, half=0.6,
              w=0.07, col=WIND, life=0.16, wait=0.25, cols=(WIND_DK, WIND, (255, 255, 255)))


def fx_screech(fx, e, col):
    """Stridio: archi rosa a zig-zag che si allargano nel cono."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    rng = float(e.get("range", 4.0))
    half = math.radians(float(e.get("angle", 40)))
    ang = math.atan2(d[1], d[0])
    for k in range(5):
        fx._shape(kind="soundarc", c=o, ang=ang, r0=0.4, r1=rng, half=half, w=0.06,
                  col=SCREECH, life=0.4, wait=0.06 * k, jag=0.035,
                  cols=(SCREECH_DK, SCREECH, (255, 220, 236)))


def fx_boomburst(fx, e, col):
    """Granvoce: cinque grandi onde sonore che attraversano anche i muri."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    rng = float(e.get("range", 5.5))
    half = math.radians(float(e.get("angle", 42)))
    ang = math.atan2(d[1], d[0])
    fx._shape(kind="flash", c=(o[0] + d[0] * 0.5, o[1] + d[1] * 0.5), r=0.6, col=SOUND_HI,
              life=0.15)
    for k in range(5):
        fx._shape(kind="soundarc", c=o, ang=ang, r0=0.5, r1=rng + 0.4, half=half,
                  w=0.2 - 0.02 * k, col=SOUND, life=0.5, wait=0.07 * k)
    for _ in range(14):
        a = ang + random.uniform(-half, half)
        rr = random.uniform(0.6, rng)
        fx._add(o[0] + math.cos(a) * rr, o[1] + math.sin(a) * rr, math.cos(a) * 2.0,
                math.sin(a) * 2.0, random.uniform(0.25, 0.45), SOUND_HI, 1)


def fx_whirlwind(fx, e, col):
    """Turbine: folate che girano attorno a Noivern; i nemici respinti lasciano
    una scia di vento (eventi "dash" della respinta)."""
    if e.get("kind") == "dash":
        ab = _ab(e)
        if ab is None:
            return
        a, b = ab
        ang = _ang(a, b)
        px, py = -math.sin(ang), math.cos(ang)
        for off in (-0.22, 0.0, 0.22):
            fx._shape(kind="windline", a=(a[0] + px * off, a[1] + py * off - 0.3),
                      b=(b[0] + px * off, b[1] + py * off - 0.3), col=WIND, life=0.35)
        fx._shape(kind="puff", c=(b[0], b[1]), v=(math.cos(ang) * 0.5, -0.3), r0=0.15, r1=0.4,
                  col=(214, 222, 222), life=0.45)
        return
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.6))
    for k in range(9):
        fx._shape(kind="gust", c=(c[0], c[1] - 0.2), r0=0.3 + 0.1 * (k % 3),
                  r1=r * (0.55 + 0.2 * (k % 3)), a0=k * math.tau / 9 + random.uniform(-0.3, 0.3),
                  spin=9.0, half=0.5, col=WIND, life=0.45 + 0.05 * (k % 3), wait=0.03 * (k % 3))
    for _ in range(10):
        a = random.uniform(0, math.tau)
        fx._add(c[0] + math.cos(a) * 0.5, c[1] + math.sin(a) * 0.4, math.cos(a) * 3.5,
                math.sin(a) * 2.8, random.uniform(0.25, 0.4), WIND, 1)


def fx_acrobatics(fx, e, col):
    """Acrobazia: tre scie d'aria parallele e sbuffi lungo lo scatto."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    ang = _ang(a, b)
    px, py = -math.sin(ang), math.cos(ang)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    back = max(0.0, 1.0 - 2.2 / max(0.1, L))   # scia solo sugli ultimi ~2 tile
    a2 = (a[0] + (b[0] - a[0]) * back, a[1] + (b[1] - a[1]) * back)
    for off, lf in ((-0.26, 0.22), (0.0, 0.28), (0.26, 0.2)):
        fx._shape(kind="windline", a=(a2[0] + px * off, a2[1] + py * off - 0.35),
                  b=(b[0] + px * off, b[1] + py * off - 0.35), col=WIND, life=lf)
    for _ in range(8):
        u = random.random()
        fx._add(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u - 0.3,
                -math.cos(ang) * 1.2, -math.sin(ang) * 1.2 - 0.3, random.uniform(0.25, 0.45),
                random.choice((WIND, SONAR)), 1)
    fx._shape(kind="soundarc", c=b, ang=ang, r0=0.2, r1=0.8, half=1.0, w=0.08, col=WIND,
              life=0.25, cols=(WIND_DK, WIND, (255, 255, 255)))


def fx_agility(fx, e, col):
    """Agilità: linee di velocità attorno e scintille verde acqua che salgono."""
    c = e.get("c")
    if c is None:
        return
    for k in range(6):
        y = c[1] - 0.6 + k * 0.2
        x = c[0] + random.uniform(-0.3, 0.3)
        fx._shape(kind="beam", a=(x + 0.5, y), b=(x - 0.6, y), w=0.05, col=SONAR, life=0.3,
                  wait=0.04 * k)
    for _ in range(8):
        fx._add(c[0] + random.uniform(-0.45, 0.45), c[1] + random.uniform(-0.2, 0.2),
                random.uniform(-0.2, 0.2), -random.uniform(1.2, 2.2), random.uniform(0.4, 0.7),
                SONAR, 1)


def fx_hurricane(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 1.5))
    fx._shape(kind="ring", c=c, r0=0.2, r1=r * 1.3, col=DRAGON, life=0.4, wd=0.12)
    for k in range(4):
        fx._shape(kind="gust", c=c, r0=0.3, r1=r, a0=k * math.tau / 4, spin=10.0, col=WIND,
                  life=0.45)


def fx_hurricaneend(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 1.5))
    for k in range(8):
        a = k / 8 * math.tau
        fx._shape(kind="puff", c=(c[0] + math.cos(a) * r * 0.5, c[1] + math.sin(a) * r * 0.3),
                  v=(math.cos(a) * 1.4, math.sin(a) * 0.8 - 0.3), r0=0.2, r1=0.55,
                  col=(196, 190, 220), life=0.6)
    for k in range(4):
        fx._shape(kind="gust", c=c, r0=r * 0.6, r1=r * 1.6, a0=k * math.tau / 4, spin=4.0,
                  col=WIND, life=0.5)


def fx_dracometeorhit(fx, e, col):
    """Dragobolide: lampo, onde d'urto, schegge di roccia e braci."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 3.0))
    fx._shape(kind="flash", c=c, r=0.9, col=METEOR_HI, life=0.14)
    fx._shape(kind="ring", c=c, r0=0.4, r1=r, col=METEOR, life=0.4, wd=0.12)
    fx._shape(kind="ring", c=c, r0=0.2, r1=r * 0.8, col=DRAGON, life=0.5, wd=0.08)
    for k in range(9):   # crateri dei singoli impatti
        a = random.uniform(0, math.tau)
        rr = random.uniform(0.1, 0.85) * r
        p = (c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr * 0.8)
        fx._shape(kind="crater", c=p, r=random.uniform(0.35, 0.6), col=METEOR,
                  life=0.7 + 0.05 * k, wait=0.03 * k)
    for _ in range(26):
        a = random.uniform(0, math.tau)
        sp = random.uniform(1.5, 4.5)
        fx._add(c[0] + math.cos(a) * 0.3, c[1] + math.sin(a) * 0.3, math.cos(a) * sp,
                math.sin(a) * sp - 1.0, random.uniform(0.35, 0.8),
                random.choice((METEOR_HI, METEOR, ROCK, DRAGON_HI)), random.choice((1, 2)))
    for _ in range(4):
        fx._shape(kind="puff", c=(c[0] + random.uniform(-r, r) * 0.5, c[1] + random.uniform(-r, r) * 0.3),
                  v=(random.uniform(-0.4, 0.4), -random.uniform(0.6, 1.2)), r0=0.2,
                  r1=random.uniform(0.4, 0.6), col=(92, 80, 96), life=random.uniform(0.6, 0.9))


STYLES = {
    "sonic": fx_sonic, "echoping": fx_echoping, "supersonic": fx_supersonic,
    "dragonpulse": fx_dragonpulse, "aircutter": fx_aircutter, "screech": fx_screech,
    "boomburst": fx_boomburst, "whirlwind": fx_whirlwind, "acrobatics": fx_acrobatics,
    "agility": fx_agility, "hurricane": fx_hurricane, "hurricaneend": fx_hurricaneend,
    "dracometeorhit": fx_dracometeorhit,
}


# --- disegni persistenti (stato del Match) -------------------------------------


def draw_ping(surface, camera, pg, now):
    """Ping attivo: increspature verde acqua che partono dal centro e il bordo
    della zona rivelata, che sfuma negli ultimi istanti."""
    ts = config.TILE_SIZE
    c = pg["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    R = pg["radius"] * ts
    fade = max(0.0, min(1.0, (pg["end"] - now) / 0.5))
    # bordo tratteggiato che ruota piano
    n = 40
    for i in range(0, n, 2):
        a0 = i / n * math.tau + now * 0.25
        a1 = (i + 1) / n * math.tau + now * 0.25
        p0 = (cx + math.cos(a0) * R, cy + math.sin(a0) * R)
        p1 = (cx + math.cos(a1) * R, cy + math.sin(a1) * R)
        if fade > 0.5:
            pygame.draw.line(surface, SONAR_DK, p0, p1, 3)
        pygame.draw.line(surface, SONAR, p0, p1, 1)
    g = pygame.Surface((int(R * 2) + 4, int(R * 2) + 4), pygame.SRCALPHA)
    o = int(R) + 2
    for k in range(2):
        ph = ((now - pg["start"]) / 0.9 + k * 0.5) % 1.0
        rr = int(R * ph)
        if rr > 2:
            al = int(150 * (1.0 - ph) * fade)
            pygame.draw.circle(g, (*SONAR, al), (o, o), rr, 2)
    surface.blit(g, (cx - o, cy - o))


def draw_hurricane(surface, camera, h, now):
    """Tifone: imbuto di vento (stretto a terra, largo in alto) col corpo
    traslucido, contorno scuro, strisce chiare che girano attorno, polvere
    alla base, detriti in orbita e il cerchio di presa a terra."""
    ts = config.TILE_SIZE
    c = h["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    R = h["radius"] * ts
    life = max(0.0, min(1.0, (now - h["start"]) / 0.3, (h["end"] - now) / 0.4))
    rain = h.get("rain")
    body = (128, 132, 182) if rain else (140, 122, 190)
    dark = (52, 42, 96)
    light = (232, 228, 255)
    H = R * 2.1
    w, hh = int(R * 2.8) + 10, int(H + R) + 10
    g = pygame.Surface((w, hh), pygame.SRCALPHA)
    gx, gy = w // 2, hh - int(R * 0.5) - 4
    # ombra e cerchio di presa a terra
    pygame.draw.ellipse(g, (16, 12, 28, int(80 * life)),
                        pygame.Rect(gx - R, gy - R * 0.45, R * 2, R * 0.9))
    pygame.draw.ellipse(g, (*light, int(90 * life)),
                        pygame.Rect(gx - R, gy - R * 0.45, R * 2, R * 0.9), 1)
    # silhouette dell'imbuto: bordo che ondeggia e si piega col vento
    n = 14
    left, right = [], []
    for i in range(n + 1):
        u = i / n
        y = gy - u * H
        half = R * (0.18 + 0.82 * u ** 1.3)
        sway = math.sin(now * 2.6 + u * 3.5) * R * 0.18 * u
        wob = math.sin(now * 11 + u * 9) * R * 0.04
        left.append((gx + sway - half - wob, y))
        right.append((gx + sway + half + wob, y))
    poly = left + right[::-1]
    pygame.draw.polygon(g, (*body, int(120 * life)), poly)
    pygame.draw.polygon(g, (*dark, int(200 * life)), poly, 2)
    # strisce che avvolgono l'imbuto (solo il lato davanti)
    for k in range(11):
        u = (k + 0.5) / 11
        y = gy - u * H
        half = R * (0.18 + 0.82 * u ** 1.3)
        sway = math.sin(now * 2.6 + u * 3.5) * R * 0.18 * u
        ph = now * 7.0 + k * 1.7
        pts = []
        for j in range(6):
            a = ph + j * 0.28
            if math.sin(a) < -0.1:
                continue
            pts.append((gx + sway + math.cos(a) * half, y + math.sin(a) * half * 0.22))
        if len(pts) >= 2:
            pygame.draw.lines(g, (*light, int(210 * life)), False, pts, 2 if u > 0.4 else 1)
    # polvere che gira alla base
    for k in range(7):
        a = now * 6.0 + k * math.tau / 7
        px = gx + math.cos(a) * R * 0.75
        py = gy + math.sin(a) * R * 0.3
        rr = max(1, int(R * 0.07))
        pygame.draw.circle(g, (150, 140, 150, int(150 * life)), (int(px), int(py)), rr)
    # detriti e gocce in orbita
    rnd = random.Random(int(h["start"] * 1000))
    for k in range(10):
        u = rnd.random()
        a = now * (5 + rnd.random() * 3) + rnd.random() * math.tau
        half = R * (0.18 + 0.82 * u ** 1.3) * 1.05
        px = gx + math.cos(a) * half
        py = gy - u * H + math.sin(a) * half * 0.22
        col = (110, 160, 240) if rain and k % 2 else (96, 80, 74)
        pygame.draw.rect(g, (*col, int(230 * life)), pygame.Rect(int(px), int(py), 2, 2))
    surface.blit(g, (cx - gx, cy - gy))


def draw_meteor_warn(surface, camera, m, now):
    """Dragobolide in arrivo: cerchio d'avviso che si chiude e meteore che
    cadono dal cielo verso l'area nell'ultimo mezzo secondo."""
    ts = config.TILE_SIZE
    c = m["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    R = int(m["radius"] * ts)
    span = max(1e-6, m["hit_at"] - m["start"])
    prog = max(0.0, min(1.0, (now - m["start"]) / span))
    g = pygame.Surface((R * 2 + 6, R * 2 + 6), pygame.SRCALPHA)
    o = R + 3
    pygame.draw.circle(g, (*METEOR_DK, int(40 + 50 * prog)), (o, o), R)
    pygame.draw.circle(g, (*METEOR, 210), (o, o), R, 2)
    ir = max(1, int(R * (1.0 - prog)))
    pygame.draw.circle(g, (*METEOR_HI, 200), (o, o), ir, 2)
    surface.blit(g, (cx - o, cy - o))
    rnd = random.Random(int(m["start"] * 1000))
    for k in range(9):
        a = rnd.uniform(0, math.tau)
        rr = rnd.uniform(0.1, 0.9) * R
        t0 = 0.35 + rnd.uniform(0.0, 0.5)   # ogni meteora parte a un istante diverso
        u = (prog - t0) / (1.0 - t0 + 1e-6)
        if u <= 0.0:
            continue
        u = min(1.0, u)
        gx, gy = cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.8
        hx, hy = 3.2 * ts, -5.0 * ts
        px, py = gx + hx * (1 - u), gy + hy * (1 - u)
        r = max(2, int(rnd.uniform(0.16, 0.28) * ts))
        tail = 1.3 * ts
        n = math.hypot(hx, hy)
        tx, ty = hx / n * tail, hy / n * tail
        pygame.draw.line(surface, METEOR_DK, (px, py), (px + tx, py + ty), r * 2)
        pygame.draw.line(surface, METEOR, (px, py), (px + tx * 0.7, py + ty * 0.7), r)
        pygame.draw.line(surface, METEOR_HI, (px, py), (px + tx * 0.3, py + ty * 0.3),
                         max(1, r // 2))
        pygame.draw.circle(surface, ROCK, (int(px), int(py)), r + 1)
        pygame.draw.circle(surface, METEOR, (int(px), int(py)), r)
        pygame.draw.circle(surface, METEOR_HI, (int(px - r / 3), int(py - r / 3)), max(1, r // 2))


# --- sulle unità --------------------------------------------------------------


def has_echo(u) -> bool:
    return getattr(u, "passive_id", "") == "ecolocalizzazione" or getattr(u, "dex", 0) in ECHO_DEX


def draw_echo_pips(surface, u, cx, top_y, width):
    """Cariche del ping sotto la barra della vita: tre tacche, si accendono a
    ogni attacco base; alla terza parte il ping (le vedono tutti)."""
    n = int(getattr(u, "echo_count", 0))
    size, gap = 3, 2
    total = 3 * size + 2 * gap
    x = cx - total // 2
    y = top_y + 5
    pygame.draw.rect(surface, (14, 14, 22), pygame.Rect(x - 1, y - 1, total + 2, size + 2))
    for k in range(3):
        r = pygame.Rect(x + k * (size + gap), y, size, size)
        if k < n:
            pygame.draw.rect(surface, SONAR, r)
            surface.fill((230, 255, 250), pygame.Rect(r.x, r.y, 1, 1))
        else:
            pygame.draw.rect(surface, (52, 60, 72), r)
