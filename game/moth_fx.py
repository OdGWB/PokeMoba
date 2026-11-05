"""Grafica della linea Venonat > Venomoth: effetti istantanei (handler
registrati in FXSystem._FX_STYLES), forme nuove per FXSystem._draw_shapes
(scaglia in volo, raggio di Psicoraggio/Ventargenteo, stelline della
confusione, ali che battono, polvere che sale), disegni persistenti letti
dallo stato del Match a ogni frame (nubi di Velenpolvere/Paralizzante/
Sonnifero e Tempesta di Polveri), gli accumuli di veleno sotto la barra della
vita, l'aura di Eledanza e Ventargenteo sulle unità, l'icona della passiva e
il mirino.

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

VEN = (178, 96, 216)           # veleno
VEN_HI = (238, 190, 255)
VEN_DK = (58, 22, 84)
TOX = (164, 228, 96)           # riflesso tossico (accumuli pieni)
SCALE = (220, 218, 238)        # scaglie argentate
SCALE_HI = (255, 255, 255)
SCALE_DK = (92, 86, 124)
PSY = (255, 126, 200)          # Psicoraggio
PSY_HI = (255, 214, 240)
PSY_DK = (120, 32, 96)
BUG = (178, 210, 76)           # Ronzio
BUG_HI = (232, 248, 170)
BUG_DK = (56, 76, 18)
STUN = (250, 224, 84)          # Paralizzante
STUN_DK = (110, 84, 10)
SLEEP = (156, 180, 255)        # Sonnifero
SLEEP_DK = (40, 52, 120)
WHITE = (255, 255, 255)

MOTH_DEX = (48, 49)
POWDER_COLS = {"poison": (VEN, VEN_HI, VEN_DK), "stun": (STUN, (255, 248, 190), STUN_DK),
               "sleep": (SLEEP, (226, 234, 255), SLEEP_DK)}


def _al(f, k=2.0):
    return int(255 * max(0.0, min(1.0, f * k)))


def is_moth(u) -> bool:
    return getattr(u, "dex", 0) in MOTH_DEX


# --- piccoli disegni -----------------------------------------------------------

def draw_scale(surface, cx, cy, r, ang, alpha=255, cols=(SCALE_DK, SCALE, SCALE_HI)):
    """Scaglia d'ala: piccola goccia allungata (punta in avanti) con contorno
    scuro e riflesso in alto a sinistra."""
    r = max(2.0, r)
    ca, sa = math.cos(ang), math.sin(ang)

    def P(u, v):
        return (cx + ca * u - sa * v, cy + sa * u + ca * v)
    pts = [P(r * 1.3, 0), P(r * 0.2, r * 0.7), P(-r * 0.8, r * 0.5), P(-r, 0),
           P(-r * 0.8, -r * 0.5), P(r * 0.2, -r * 0.7)]
    pygame.draw.polygon(surface, (*cols[0], alpha), pts)
    inner = [(cx + (x - cx) * 0.68, cy + (y - cy) * 0.68) for x, y in pts]
    pygame.draw.polygon(surface, (*cols[1], alpha), inner)
    pygame.draw.circle(surface, (*cols[2], alpha), (int(cx - r * 0.25), int(cy - r * 0.25)),
                       max(1, int(r * 0.3)))


def draw_star4(surface, cx, cy, r, alpha, col):
    """Stellina a 4 punte (scintilla, confusione)."""
    pts = []
    for i in range(8):
        rr = r if i % 2 == 0 else r * 0.3
        a = i * math.pi / 4
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    pygame.draw.polygon(surface, (*col, alpha), pts)


def draw_wing(surface, cx, cy, side, span, open_, alpha, cols=(VEN_DK, VEN, VEN_HI)):
    """Ala di falena vista da dietro: due lobi (sopra grande, sotto piccolo),
    `open_` 0..1 = quanto è aperta, `side` = +1 destra / -1 sinistra."""
    sx = side * span * (0.35 + 0.65 * open_)
    up = [(cx, cy), (cx + sx * 0.4, cy - span * 0.75), (cx + sx, cy - span * 0.55),
          (cx + sx * 0.95, cy - span * 0.05)]
    lo = [(cx, cy), (cx + sx * 0.75, cy + span * 0.05), (cx + sx * 0.6, cy + span * 0.45),
          (cx + sx * 0.2, cy + span * 0.35)]
    for poly in (up, lo):
        pygame.draw.polygon(surface, (*cols[0], alpha), poly)
        inner = [(cx + (x - cx) * 0.78, cy + (y - cy) * 0.78) for x, y in poly]
        pygame.draw.polygon(surface, (*cols[1], alpha), inner)
    # occhio dell'ala
    ex, ey = cx + sx * 0.6, cy - span * 0.4
    pygame.draw.circle(surface, (*cols[2], alpha), (int(ex), int(ey)), max(1, int(span * 0.12)))


# --- forme per FXSystem._draw_shapes -------------------------------------------------

SHAPES = ("mothscale", "mothbeam", "dizzy", "wingflap", "dustrise")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "mothscale":
        # Scaglia in volo da A a B che rotea, con due granelli di polvere dietro.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.85)
        lift = s.get("lift", 0.3) * ts
        px, py = ax + (bx - ax) * u, ay + (by - ay) * u - lift
        ang = math.atan2(by - ay, bx - ax)
        al = _al(f, 3.0)
        cols = s.get("cols", (VEN_DK, VEN, VEN_HI))
        for k in (1, 2):
            uk = max(0.0, u - 0.09 * k)
            qx, qy = ax + (bx - ax) * uk, ay + (by - ay) * uk - lift
            pygame.draw.circle(overlay, (*cols[1], al // (k + 1)), (int(qx), int(qy)),
                               max(1, 3 - k))
        spin = ang + math.sin(u * 14.0) * 0.6
        draw_scale(overlay, px, py, s.get("sz", 0.13) * ts, spin, al, cols)
    elif kind == "mothbeam":
        # Raggio: corpo che ondeggia, nucleo chiaro e motivi che scorrono verso
        # la punta (anelli rosa per Psicoraggio, scaglie argentate per Ventargenteo).
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        L = math.hypot(bx - ax, by - ay) or 1.0
        ux, uy = (bx - ax) / L, (by - ay) / L
        px, py = -uy, ux
        lift = 0.3 * ts
        grow = min(1.0, t / 0.18)
        al = _al(f, 2.0)
        cols = s.get("cols", (PSY_DK, PSY, PSY_HI))
        w = s.get("w", 0.32) * ts
        age = s["maxlife"] - s["life"]
        n = max(4, int(L / 4))
        pts_l, pts_r, mid = [], [], []
        for i in range(n + 1):
            d = L * grow * i / n
            wob = math.sin(d / ts * 2.2 - age * 18.0) * 0.08 * ts
            ww = w * (0.55 + 0.45 * math.sin(d / ts * 1.4 - age * 10.0) ** 2)
            cx, cy = ax + ux * d + px * wob, ay + uy * d + py * wob - lift
            mid.append((cx, cy))
            pts_l.append((cx + px * ww, cy + py * ww))
            pts_r.append((cx - px * ww, cy - py * ww))
        if len(mid) >= 2:
            pygame.draw.polygon(overlay, (*cols[0], al // 2), pts_l + pts_r[::-1])
            inner_l = [((x + m[0]) / 2 * 1, (y + m[1]) / 2) for (x, y), m in zip(pts_l, mid)]
            inner_r = [((x + m[0]) / 2, (y + m[1]) / 2) for (x, y), m in zip(pts_r, mid)]
            soft = 0.5 if s.get("soft") else 1.0   # Ventargenteo: vento traslucido
            pygame.draw.polygon(overlay, (*cols[1], int(al * soft)), inner_l + inner_r[::-1])
            pygame.draw.lines(overlay, (*cols[2], al), False, mid, 2)
        motif = s.get("motif", "rings")
        for k in range(5):
            d = ((age * 9.0 * ts + k * L / 5) % max(1.0, L * grow))
            cx, cy = ax + ux * d, ay + uy * d - lift
            if motif == "rings":
                rr = w * 1.1
                rect = pygame.Rect(0, 0, max(2, int(rr * 0.7)), max(2, int(rr * 2)))
                rect.center = (int(cx), int(cy))
                surf = pygame.Surface(rect.size, pygame.SRCALPHA)
                pygame.draw.ellipse(surf, (*cols[2], al), surf.get_rect(), 2)
                rs = pygame.transform.rotate(surf, -math.degrees(math.atan2(uy, ux)))
                overlay.blit(rs, rs.get_rect(center=(int(cx), int(cy))))
            else:
                off = math.sin(k * 2.3 + age * 6) * w * 0.9
                draw_scale(overlay, cx + px * off, cy + py * off, 0.09 * ts,
                           math.atan2(uy, ux) + age * 8 + k, al,
                           (SCALE_DK, SCALE, SCALE_HI))
    elif kind == "dizzy":
        # Tre stelline che girano sopra la testa (confusione).
        cx, cy = S(*s["c"])
        age = s["maxlife"] - s["life"]
        r = s.get("r", 0.35) * ts
        al = _al(f, 3.0)
        cols = s.get("cols", (PSY, PSY_HI))
        for k in range(3):
            an = age * 7.0 + k * math.tau / 3
            x = cx + math.cos(an) * r
            y = cy + math.sin(an) * r * 0.4
            draw_star4(overlay, x + 1, y + 1, max(2, int(0.1 * ts)), al // 2, PSY_DK)
            draw_star4(overlay, x, y, max(2, int(0.1 * ts)), al, cols[k % 2])
    elif kind == "wingflap":
        # Due ali che battono una volta (Raffica, Eledanza).
        cx, cy = S(*s["c"])
        span = s.get("span", 0.6) * ts
        flap = abs(math.sin(t * math.pi * s.get("beats", 1.0)))
        al = int(_al(f, 2.5) * s.get("fade", 1.0))
        cols = s.get("cols", (VEN_DK, VEN, VEN_HI))
        for side in (-1, 1):
            draw_wing(overlay, cx, cy, side, span, 1.0 - flap * 0.7, al, cols)
    elif kind == "dustrise":
        # Granelli di polvere che salgono ondeggiando da un'area (polveri, buff).
        cx, cy = S(*s["c"])
        rnd = random.Random(s.get("seed", 5))
        r = s.get("r", 0.6) * ts
        age = s["maxlife"] - s["life"]
        al = _al(f, 2.0)
        cols = s.get("cols", (VEN, VEN_HI))
        for i in range(s.get("n", 12)):
            an = rnd.uniform(0, math.tau)
            d = rnd.uniform(0.2, 1.0) * r
            sp = rnd.uniform(0.6, 1.4)
            x = cx + math.cos(an) * d + math.sin(age * 5 + i) * 0.06 * ts
            y = cy + math.sin(an) * d * 0.5 - age * sp * ts * 0.9
            c = cols[i % len(cols)]
            sz = 2 if i % 3 else 1
            overlay.fill((*c, al), pygame.Rect(int(x), int(y), sz, sz))


# --- handler degli eventi (FXSystem._FX_STYLES) ------------------------------------

def _ab(e):
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return None
    return a, b


def _bits(fx, c, n, cols, speed=2.0, life=(0.2, 0.4), size=1, up=0.0, spread=0.0):
    for _ in range(n):
        an = random.uniform(0, math.tau)
        v = random.uniform(0.4, 1.0) * speed
        x = c[0] + random.uniform(-spread, spread)
        y = c[1] + random.uniform(-spread, spread) * 0.5
        fx._add(x, y, math.cos(an) * v, math.sin(an) * v * 0.5 - up, random.uniform(*life),
                random.choice(cols), size)


def fx_venomshot(fx, e, col):
    """Attacco base: scaglia velenosa in volo e sbuffo viola all'impatto."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="mothscale", a=a, b=b, col=VEN, life=0.22, sz=0.13)
    top = (b[0], b[1] - 0.3)
    fx._shape(kind="dustrise", c=top, r=0.3, n=7, seed=random.randrange(999),
              cols=(VEN, VEN_HI, TOX), col=VEN, life=0.45, wait=0.18)


def fx_mothpsybeam(fx, e, col):
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="mothbeam", a=a, b=b, col=PSY, life=0.45, w=0.3, motif="rings",
              cols=(PSY_DK, PSY, PSY_HI))
    fx._shape(kind="flash", c=(b[0], b[1] - 0.3), r=0.35, col=PSY, life=0.25, wait=0.1)


def fx_mothsilver(fx, e, col):
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="mothbeam", a=a, b=b, col=SCALE, life=0.5, w=0.24, motif="scales", soft=True,
              cols=((150, 156, 190), (206, 212, 236), SCALE_HI))
    for k in range(5):   # raffiche di vento lungo il raggio
        u = (k + 0.5) / 5
        off = random.uniform(-0.4, 0.4)
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        px, py = -dy / L * off, dx / L * off
        p0 = (a[0] + dx * u + px, a[1] + dy * u + py - 0.3)
        p1 = (p0[0] + dx / L * 1.2, p0[1] + dy / L * 1.2)
        fx._shape(kind="windline", a=p0, b=p1, col=SCALE, life=0.3, wait=0.04 * k)


def fx_mothbuzz(fx, e, col):
    """Ronzio: onde sonore verdi che si allargano nel cono."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    ang = math.atan2(d[1], d[0])
    half = math.radians(e.get("angle", 35))
    rng = e.get("range", 4.5)
    for k in range(4):
        fx._shape(kind="soundarc", c=(o[0], o[1] - 0.25), ang=ang, r0=0.3, r1=rng, half=half,
                  w=0.09, cols=(BUG_DK, BUG, BUG_HI), col=BUG, life=0.42, wait=0.05 * k)


def fx_mothconfuse(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="dizzy", c=(c[0], c[1] - 0.95), r=0.32, col=PSY, life=1.0)


def fx_mothsilverbuff(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="dustrise", c=(c[0], c[1] - 0.2), r=0.55, n=14, seed=random.randrange(999),
              cols=(SCALE, SCALE_HI, (190, 200, 230)), col=SCALE, life=0.7)


def fx_mothpowder(fx, e, col):
    """Comparsa della nube: sbuffo che si apre (il resto lo disegna world_fx)."""
    c = e.get("c")
    if c is None:
        return
    kind = e.get("powder", "poison")
    cols = POWDER_COLS.get(kind, POWDER_COLS["poison"])
    r = e.get("radius", 3.0)
    fx._shape(kind="ring", c=c, r0=r * 0.3, r1=r, col=cols[0], life=0.35, wd=0.12)
    fx._shape(kind="dustrise", c=c, r=r * 0.8, n=26, seed=random.randrange(999),
              cols=(cols[0], cols[1]), col=cols[0], life=0.7)


def fx_mothstorm(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    r = e.get("radius", 5.0)
    for k, kind in enumerate(("poison", "stun", "sleep")):
        cols = POWDER_COLS[kind]
        fx._shape(kind="ring", c=c, r0=r * 0.2, r1=r, col=cols[0], life=0.45, wd=0.12,
                  wait=0.06 * k)
    fx._shape(kind="dustrise", c=c, r=r * 0.8, n=40, seed=random.randrange(999),
              cols=(VEN, STUN, SLEEP), col=VEN, life=0.8)


def fx_mothpara(fx, e, col):
    """Paralisi: due scintille gialle a zig-zag sul bersaglio."""
    c = e.get("c")
    if c is None:
        return
    for k in range(2):
        x = c[0] + (k - 0.5) * 0.45
        fx._shape(kind="ziglink", a=(x, c[1] - 0.5), b=(x + 0.12, c[1] + 0.3), lift=0.4,
                  amp=0.12, w=1, branch=False, cols=(STUN_DK, STUN, (255, 250, 210)), col=STUN,
                  life=0.3, wait=0.08 * k)
    _bits(fx, (c[0], c[1] - 0.4), 8, (STUN, (255, 248, 190)), speed=2.2, life=(0.15, 0.35))


def fx_mothsleep(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    top = (c[0] + 0.2, c[1] - 0.8)
    fx._shape(kind="zzz", c=top, col=SLEEP, life=0.9)
    fx._shape(kind="dustrise", c=(c[0], c[1] - 0.3), r=0.35, n=8, seed=random.randrange(999),
              cols=(SLEEP, (226, 234, 255)), col=SLEEP, life=0.6)


def fx_mothpoison(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="dustrise", c=(c[0], c[1] - 0.3), r=0.35, n=9, seed=random.randrange(999),
              cols=(VEN, VEN_HI, TOX), col=VEN, life=0.6)


def fx_mothgust(fx, e, col):
    """Raffica: battito d'ali e folate in avanti (cono dei respinti)."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    rng = e.get("range", 2.0)
    ang = math.atan2(d[1], d[0])
    fx._shape(kind="wingflap", c=(o[0], o[1] - 0.45), span=0.55, beats=1.0, col=VEN,
              cols=((70, 60, 110), (160, 150, 210), (230, 220, 255)), life=0.3, fade=0.45)
    for k in range(6):   # raffiche CORTE a distanze diverse (lunghe sembrano fili tesi)
        an = ang + (k % 3 - 1) * 0.45 + random.uniform(-0.1, 0.1)
        d0 = 0.5 + (k // 3) * rng * 0.45 + random.uniform(0.0, 0.3)
        p0 = (o[0] + math.cos(an) * d0, o[1] + math.sin(an) * d0 - 0.25)
        p1 = (o[0] + math.cos(an) * (d0 + 0.7), o[1] + math.sin(an) * (d0 + 0.7) - 0.25)
        fx._shape(kind="windline", a=p0, b=p1, col=SCALE, life=0.25, wait=0.03 * k)
    fx._shape(kind="dustrise", c=(o[0] + math.cos(ang) * rng * 0.6, o[1] + math.sin(ang) * rng * 0.6),
              r=rng * 0.5, n=14, seed=random.randrange(999), cols=(VEN, SCALE), col=VEN, life=0.5)


def fx_mothgustdash(fx, e, col):
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    for k in range(6):   # scaglie che restano lungo lo scatto
        u = k / 5
        c = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        fx._shape(kind="dustrise", c=c, r=0.25, n=5, seed=random.randrange(999),
                  cols=(VEN, SCALE, VEN_HI), col=VEN, life=0.5, wait=0.03 * k)


def fx_mothshield(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="hexshell", c=c, r=0.7, col=(206, 180, 236), life=0.5)
    fx._shape(kind="dustrise", c=c, r=0.6, n=16, seed=random.randrange(999),
              cols=(SCALE, VEN_HI), col=SCALE, life=0.7)


def fx_mothquiver(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="dustrise", c=c, r=0.8, n=22, seed=random.randrange(999),
              cols=(SCALE, VEN_HI, PSY_HI), col=SCALE, life=0.9)
    fx._shape(kind="ring", c=c, r0=0.3, r1=1.3, col=VEN_HI, life=0.4, wd=0.08)


STYLES = {
    "venomshot": fx_venomshot, "mothpsybeam": fx_mothpsybeam, "mothsilver": fx_mothsilver,
    "mothbuzz": fx_mothbuzz, "mothconfuse": fx_mothconfuse, "mothsilverbuff": fx_mothsilverbuff,
    "mothpowder": fx_mothpowder, "mothstorm": fx_mothstorm, "mothpara": fx_mothpara,
    "mothsleep": fx_mothsleep, "mothpoison": fx_mothpoison, "mothgust": fx_mothgust,
    "mothgustdash": fx_mothgustdash, "mothshield": fx_mothshield, "mothquiver": fx_mothquiver,
}


# --- disegni persistenti (world_fx) ---------------------------------------------------

def draw_powder_cloud(surface, camera, cl, now):
    """Nube di polvere a terra: chiazze traslucide che respirano, bordo a
    trattini che gira, granelli che salgono. Tempesta di Polveri: tre colori
    che vorticano."""
    ts = config.TILE_SIZE
    c = cl["c"]
    cx, cy = camera.world_to_screen(c[0] * ts if not hasattr(c, "x") else c.x * ts,
                                    c[1] * ts if not hasattr(c, "y") else c.y * ts)
    r = cl["radius"] * ts
    start, end = cl.get("start", now), cl.get("end", now + 1)
    age = now - start
    fade = min(1.0, age / 0.3, max(0.0, end - now) / 0.4)
    if fade <= 0:
        return
    kind = cl.get("kind", "poison")
    storm = kind == "storm"
    sw, sh = int(r * 2 + 8), int(r * 1.3 + 8)
    surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
    ox, oy = sw / 2, sh / 2
    rnd = random.Random(cl.get("seed", 1) * 7 + (3 if storm else 0))
    palette = ([POWDER_COLS["poison"], POWDER_COLS["stun"], POWDER_COLS["sleep"]] if storm
               else [POWDER_COLS.get(kind, POWDER_COLS["poison"])])
    # fondo: chiazze di polvere (cerchi pieni, alfa bassa) che respirano
    n = 26 if storm else 10
    blob_a = (26, 18) if storm else (42, 30)
    for i in range(n):
        an = rnd.uniform(0, math.tau) + (age * 0.35 if storm else age * 0.08)
        d = math.sqrt(rnd.random()) * r * 0.72
        x = ox + math.cos(an) * d
        y = oy + math.sin(an) * d * 0.6
        pr = r * rnd.uniform(0.22, 0.36) * (0.6 if storm else 1.0) * (1 + 0.06 * math.sin(age * 2 + i))
        cols = palette[i % len(palette)]
        pygame.draw.circle(surf, (*cols[0], int(blob_a[0] * fade)), (int(x), int(y)), int(pr))
        pygame.draw.circle(surf, (*cols[1], int(blob_a[1] * fade)), (int(x - pr * 0.25), int(y - pr * 0.25)),
                           int(pr * 0.5))
    # bordo a trattini che gira
    seg = max(24, int(math.tau * r / (0.45 * ts)) // 2 * 2)   # trattini corti anche se grande
    for k in range(seg):
        if k % 2:
            continue
        a0 = k / seg * math.tau + age * (0.8 if storm else 0.35)
        a1 = a0 + math.tau / seg
        cols = palette[(k // 2) % len(palette)]
        p0 = (ox + math.cos(a0) * r, oy + math.sin(a0) * r * 0.6)
        p1 = (ox + math.cos(a1) * r, oy + math.sin(a1) * r * 0.6)
        pygame.draw.line(surf, (*cols[2], int(160 * fade)), p0, p1, 3)
        pygame.draw.line(surf, (*cols[0], int(220 * fade)), p0, p1, 1)
    # granelli che salgono e ricadono (cicli sfalsati)
    m = 70 if storm else 22
    for i in range(m):
        ph = rnd.random()
        an = rnd.uniform(0, math.tau)
        d = math.sqrt(rnd.random()) * r * 0.9
        u = (age * rnd.uniform(0.4, 0.8) + ph) % 1.0
        if storm:
            an += age * 1.2 * (1.0 - d / r)
        x = ox + math.cos(an) * d + math.sin(u * 6 + i) * 2
        y = oy + math.sin(an) * d * 0.6 - u * ts * 0.9
        cols = palette[i % len(palette)]
        al = int(230 * fade * math.sin(u * math.pi))
        surf.fill((*cols[1 if i % 3 == 0 else 0], al), pygame.Rect(int(x), int(y), 2, 2))
    surface.blit(surf, (cx - ox, cy - oy))


# --- sulle unità ------------------------------------------------------------------------

_drop_cache: dict = {}


def _drop(full: bool):
    """Accumulo di veleno: goccia 5x6 viola col bordo scuro e un riflesso
    (verde tossico quando sono 6)."""
    img = _drop_cache.get(full)
    if img is None:
        img = pygame.Surface((5, 6), pygame.SRCALPHA)
        rows = ["..O..",
                ".OCO.",
                "OCCCO",
                "OHCCO",
                "OCCCO",
                ".OOO."]
        cmap = {"O": VEN_DK, "C": TOX if full else VEN, "H": WHITE if full else VEN_HI}
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in cmap:
                    img.set_at((x, y), (*cmap[ch], 255))
        _drop_cache[full] = img
    return img


def draw_venom_pips(surface, u, gx, top, w, row=0):
    """Accumuli di veleno sotto la barra della vita (visibili a tutti)."""
    n = int(getattr(u, "venom_stacks", 0))
    if n <= 0:
        return False
    y = top + 5 + row * 6
    full = n >= 6
    x0 = gx - (n * 6 - 1) // 2
    for k in range(n):
        surface.blit(_drop(full), (x0 + k * 6, y))
    return True


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Eledanza: scaglie che girano attorno e alone viola; Ventargenteo:
    scintille argentate; Polvoscudo: velo di polvere."""
    r = int(getattr(u, "radius", 0.5) * ts)
    if getattr(u, "quiver_until", -1.0) > now:
        for k in range(6):
            an = now * 3.0 + k * math.tau / 6
            x = gx + math.cos(an) * (r + 6)
            y = gy - r + math.sin(an) * (r * 0.45 + 3)
            cols = (VEN_DK, (206, 156, 240), VEN_HI) if k % 2 else (SCALE_DK, SCALE, SCALE_HI)
            draw_scale(surface, x, y, 3, an + math.pi / 2, 235 if math.sin(an) > 0 else 160, cols)
    if getattr(u, "silver_until", -1.0) > now:
        for k in range(3):
            ph = (now * 1.4 + k / 3) % 1.0
            x = gx + math.sin(k * 2.1 + now * 2) * r * 0.9
            y = gy - r * 0.4 - ph * r * 1.6
            draw_star4(surface, x, y, 3, int(255 * math.sin(ph * math.pi)), SCALE_HI)
    if getattr(u, "powdershield_until", -1.0) > now:
        rr = r + 5
        rect = pygame.Rect(0, 0, rr * 2, int(rr * 1.7))
        rect.center = (gx, gy - r // 2)
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.ellipse(s, (206, 180, 236, 50), s.get_rect())
        pygame.draw.ellipse(s, (236, 220, 255, 170), s.get_rect(), 1)
        surface.blit(s, rect)


# --- interfaccia ---------------------------------------------------------------------------

def count_poisoned(world, p, now, visible=None) -> int:
    """Nemici visibili con 6 accumuli di veleno (HUD della passiva)."""
    n = 0
    for e in world.pokemons():
        if e.team == p.team or not e.alive:
            continue
        if visible is not None and not visible(e):
            continue
        if int(getattr(e, "venom_stacks", 0)) >= 6:
            n += 1
    return n


def draw_moth_icon(surface, cx, cy, s, tinted=False):
    """Icona della passiva: falena stilizzata (ali + corpo) con gocciolina."""
    for side in (-1, 1):
        draw_wing(surface, cx, cy + s * 0.2, side, s * 1.1, 1.0, 255,
                  (VEN_DK, (176, 120, 214), VEN_HI) if not tinted else (VEN_DK, (150, 170, 230), PSY_HI))
    pygame.draw.line(surface, VEN_DK, (cx, cy - s * 0.6), (cx, cy + s * 0.7), 3)
    pygame.draw.line(surface, (226, 200, 170), (cx, cy - s * 0.5), (cx, cy + s * 0.6), 1)
    surface.blit(_drop(tinted), (int(cx + s * 0.7), int(cy + s * 0.5)))


def draw_aim(surface, S, ts, ox, oy, nx, ny, dist, move) -> bool:
    """Mirino delle mosse della linea. Ritorna False se la forma non è sua."""
    shape = move.shape
    rng = move.range
    if shape == "mothbeam":
        ex, ey = ox + nx * rng, oy + ny * rng
        w = move.radius
        px, py = -ny * w, nx * w
        col = SCALE if move.fx == "mothsilver" else PSY
        for sg in (1, -1):
            pygame.draw.line(surface, col, S(ox + px * sg, oy + py * sg),
                             S(ex + px * sg, ey + py * sg), 1)
        pygame.draw.line(surface, (255, 255, 255), S(ox, oy), S(ex, ey), 1)
        return True
    if shape in ("powdercloud", "powderstorm"):
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        d = min(dist, rng)
        cx, cy = S(ox + nx * d, oy + ny * d)
        kind = move.effects.get("powder", "poison")
        col = (VEN_HI if shape == "powderstorm"
               else POWDER_COLS.get(kind, POWDER_COLS["poison"])[1])
        r = int(move.radius * ts)
        rect = pygame.Rect(0, 0, r * 2, int(r * 1.2))
        rect.center = (cx, cy)
        pygame.draw.ellipse(surface, col, rect, 1)
        return True
    if shape == "mothgust":
        # cono di respinta davanti, freccia dello scatto dietro
        half = math.radians(70)
        base = math.atan2(ny, nx)
        pts = [S(ox, oy)]
        for i in range(9):
            a = base - half + 2 * half * i / 8
            pts.append(S(ox + math.cos(a) * move.radius, oy + math.sin(a) * move.radius))
        pygame.draw.lines(surface, SCALE, True, pts, 1)
        bx, by = ox - nx * rng, oy - ny * rng
        pygame.draw.line(surface, VEN_HI, S(ox, oy), S(bx, by), 1)
        px, py = -ny * 0.35, nx * 0.35
        tip = S(bx, by)
        l = S(bx + nx * 0.5 + px, by + ny * 0.5 + py)
        r = S(bx + nx * 0.5 - px, by + ny * 0.5 - py)
        pygame.draw.lines(surface, (255, 255, 255), False, [l, tip, r], 1)
        return True
    if shape == "quiverdance":
        cx, cy = S(ox, oy)
        pygame.draw.circle(surface, VEN_HI, (cx, cy), int(0.9 * ts), 1)
        return True
    return False
