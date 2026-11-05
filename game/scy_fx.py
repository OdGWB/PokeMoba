"""Grafica della linea Scyther > Scizor / Kleavor: effetti istantanei (handler
registrati in FXSystem._FX_STYLES), forme nuove per FXSystem._draw_shapes
(falce che taglia ad arco, chela che si chiude, pugno d'acciaio, ascia di
pietra, cono di Taglio d'Albero che si riempie, schegge che volano, fiamme
di Focalenergia), disegni persistenti letti dallo stato del Match (campi di
schegge, Taglio d'Albero in carica: visibili a TUTTI), sulle unità (aura di
Focalenergia, Chele d'Acciaio, Troppoforte, Cuordeciso, accumuli di
Spaccaroccia sotto la barra della vita), HUD della passiva (con l'avviso
dell'evoluzione tramite oggetto) e mirini.

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

SCY = ((34, 78, 30), (110, 184, 78), (214, 246, 168))       # falci di Scyther
STEEL = ((96, 20, 26), (206, 56, 56), (255, 178, 168))     # corazza di Scizor
METAL = ((70, 74, 90), (176, 182, 200), (244, 246, 255))   # acciaio
STONE = ((62, 48, 34), (150, 122, 86), (222, 198, 156))    # ascia di Kleavor
AUGITE = ((26, 22, 28), (78, 68, 76), (150, 138, 150))     # pietra scura (schegge)
FOCUS = ((140, 24, 10), (250, 96, 40), (255, 222, 140))    # Focalenergia
FIGHT = ((120, 40, 12), (232, 112, 48), (255, 214, 150))   # Troppoforte, Spaccaroccia
WIND = (226, 248, 236)
WHITE = (255, 255, 255)

SCY_DEX = (123, 212, 900)
FORM_OF_ITEM = {"metal_coat": "Scizor", "black_augurite": "Kleavor"}
PASSIVE_NAMES = {"cuordeciso": "Cuordeciso", "tecnico": "Tecnico",
                 "ascedipietra": "Asce di Pietra"}


def _al(f, k=2.0):
    return max(0, min(255, int(255 * min(1.0, f * k))))


def is_scy(u) -> bool:
    return (getattr(u, "passive_id", "") in PASSIVE_NAMES
            or getattr(u, "dex", 0) in SCY_DEX)


def evo_hint(p) -> dict:
    """Oggetti da evidenziare nel negozio (id -> forma): solo per Scyther."""
    if getattr(p, "dex", 0) == 123 or getattr(p, "passive_id", "") == "cuordeciso":
        return dict(FORM_OF_ITEM)
    return {}


# --- mattoni ---------------------------------------------------------------------------

def draw_blade(surface, cx, cy, a0, a1, r, w, cols, alpha=255):
    """Lama curva affusolata lungo l'arco (a0 -> a1) di raggio r: spessa al
    centro, a punta ai capi; tre strati (scuro, colore, filo chiaro)."""
    n = 14
    for k, (ww, col) in enumerate(((w, cols[0]), (w * 0.66, cols[1]), (w * 0.22, cols[2]))):
        if ww < 0.8:
            continue
        outer, inner = [], []
        for i in range(n + 1):
            u = i / n
            an = a0 + (a1 - a0) * u
            th = ww * math.sin(math.pi * u) ** 0.8
            ro = r + th * 0.5 + (0 if k else 0.5)
            ri = r - th * 0.5
            outer.append((cx + math.cos(an) * ro, cy + math.sin(an) * ro * 0.75))
            inner.append((cx + math.cos(an) * ri, cy + math.sin(an) * ri * 0.75))
        pts = outer + inner[::-1]
        if len(pts) >= 3:
            pygame.draw.polygon(surface, (*col, alpha), pts)


def draw_fist(surface, x, y, s, ang, cols, alpha=255):
    """Pugno/chela compatto pixel art puntato in `ang` (blocco con nocche)."""
    s = max(3, int(s))
    surf = pygame.Surface((s * 3, s * 3), pygame.SRCALPHA)
    o = s * 3 // 2
    body = pygame.Rect(o - s, o - s * 3 // 4, s * 2, s * 3 // 2)
    pygame.draw.rect(surf, (*cols[0], alpha), body.inflate(2, 2))
    pygame.draw.rect(surf, (*cols[1], alpha), body)
    for k in range(3):   # nocche
        kx = body.right - 2
        ky = body.y + 1 + k * max(1, body.h // 3)
        surf.fill((*cols[2], alpha), pygame.Rect(kx, ky, 2, max(1, body.h // 3 - 1)))
    surf.fill((*cols[2], alpha), pygame.Rect(body.x + 1, body.y + 1, body.w // 2, 1))
    rs = pygame.transform.rotate(surf, -math.degrees(ang))
    surface.blit(rs, rs.get_rect(center=(int(x), int(y))))


def draw_shard(surface, x, y, s, ang, cols, alpha=255):
    """Scheggia di pietra a punta (rombo stretto con il lato in luce)."""
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    tip = (x + ux * s * 1.4, y + uy * s * 1.4)
    tail = (x - ux * s * 0.8, y - uy * s * 0.8)
    l = (x + px * s * 0.45, y + py * s * 0.45)
    r = (x - px * s * 0.45, y - py * s * 0.45)
    pygame.draw.polygon(surface, (*cols[0], alpha), [(tip[0] + ux, tip[1] + uy), l, tail, r])
    pygame.draw.polygon(surface, (*cols[1], alpha), [tip, l, tail])
    pygame.draw.polygon(surface, (*cols[2], alpha), [tip, l, (x, y)])


def _cone_pts(S, o, d, rng, half, n=12):
    base = math.atan2(d[1], d[0])
    pts = [S(o[0], o[1])]
    for i in range(n + 1):
        an = base - half + 2 * half * i / n
        pts.append(S(o[0] + math.cos(an) * rng, o[1] + math.sin(an) * rng))
    return pts


# --- forme (FXSystem._draw_shapes) ------------------------------------------------------

SHAPES = ("scyblade", "scypincer", "scyfist", "scyshard", "scyflame", "scychop")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "scyblade":
        # Falce / ascia che taglia ad arco: la lama corre da un lato all'altro
        # dell'apertura lasciando una scia che sbiadisce dietro.
        cx, cy = S(*s["c"])
        cy -= int(0.3 * ts)
        half = s.get("half", 1.0)
        ang = s.get("ang", 0.0)
        side = s.get("side", 1)
        prog = min(1.0, t / 0.45)
        r = s.get("r", 1.5) * ts
        w = s.get("w", 0.22) * ts
        cols = s.get("cols", SCY)
        al = _al(f, 2.2)
        head = ang - side * half + side * 2 * half * prog
        tail = ang - side * half + side * 2 * half * max(0.0, prog - 0.55)
        a0, a1 = (tail, head) if side > 0 else (head, tail)
        draw_blade(overlay, cx, cy, a0, a1, r, w, cols, al)
        if s.get("echo"):   # scia più larga e tenue (accumuli di Tagliofuria)
            draw_blade(overlay, cx, cy, a0, a1, r * 0.78, w * 0.6, cols, al // 2)
    elif kind == "scypincer":
        # Chela che si apre e si chiude sul bersaglio (attacco base di Scizor).
        cx, cy = S(*s["c"])
        cy -= int(0.35 * ts)
        ang = s.get("ang", 0.0)
        snap = min(1.0, t / 0.4)
        gap = 0.9 * (1.0 - snap)
        r = s.get("r", 0.42) * ts
        al = _al(f, 2.5)
        for sg in (1, -1):
            a0 = ang + math.pi + sg * (0.25 + gap)
            a1 = ang + sg * (0.15 + gap * 0.4)
            lo, hi = (a0, a1) if sg < 0 else (a1, a0)
            draw_blade(overlay, cx - math.cos(ang) * r * 0.4, cy - math.sin(ang) * r * 0.3,
                       min(lo, hi), max(lo, hi) if abs(hi - lo) < math.pi * 1.5 else min(lo, hi) + 1.2,
                       r, 0.2 * ts, STEEL, al)
        if snap >= 1.0:
            for k in range(4):
                an = ang + (k - 1.5) * 0.6
                d0, d1 = r * 0.6, r * (0.9 + 0.5 * t)
                pygame.draw.line(overlay, (*METAL[2], al), (cx + math.cos(an) * d0, cy + math.sin(an) * d0),
                                 (cx + math.cos(an) * d1, cy + math.sin(an) * d1), 1)
    elif kind == "scyfist":
        # Pugno d'acciaio che scatta in avanti con le linee di velocità.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.3)
        lift = 0.35 * ts
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - lift
        ang = math.atan2(by - ay, bx - ax)
        al = _al(f, 2.5)
        cols = s.get("cols", METAL)
        for k in range(4):
            off = (k - 1.5) * 0.09 * ts
            px, py = -math.sin(ang) * off, math.cos(ang) * off
            ln = (0.5 + 0.25 * (k % 2)) * ts
            pygame.draw.line(overlay, (*cols[2], al // 2), (x + px - math.cos(ang) * ln, y + py - math.sin(ang) * ln),
                             (x + px - math.cos(ang) * 0.2 * ts, y + py - math.sin(ang) * 0.2 * ts), 1)
        draw_fist(overlay, x, y, s.get("sz", 0.16) * ts, ang, cols, al)
    elif kind == "scyshard":
        # Scheggia che vola a parabola e si pianta a terra.
        age = s["maxlife"] - s["life"]
        u = min(1.0, age / max(0.05, s["maxlife"] * 0.6))
        px, py = S(s["c"][0] + s["v"][0] * u, s["c"][1] + s["v"][1] * u)
        hop = 4.0 * u * (1.0 - u) * s.get("h", 0.5) * ts
        ang = math.atan2(s["v"][1] - (1.0 - 2 * u) * s.get("h", 0.5), s["v"][0])
        draw_shard(overlay, px, py - hop, s.get("sz", 0.1) * ts, ang, s.get("cols", AUGITE),
                   _al(f, 3.0))
    elif kind == "scyflame":
        # Lingua di energia rossa che sale (Focalenergia).
        cx, cy = S(*s["c"])
        age = s["maxlife"] - s["life"]
        h = s.get("h", 0.6) * ts
        rise = age * s.get("up", 1.4) * ts
        w = max(2, int(s.get("w", 0.16) * ts * f))
        al = _al(f, 2.0)
        x, y = cx + math.sin(age * 9 + s.get("ph", 0)) * 2, cy - rise
        pts = [(x, y - h * 0.5), (x + w, y), (x, y + w * 0.6), (x - w, y)]
        pygame.draw.polygon(overlay, (*FOCUS[0], al), [(px, py + 1) for px, py in pts])
        pygame.draw.polygon(overlay, (*FOCUS[1], al), pts)
        pygame.draw.line(overlay, (*FOCUS[2], al), (x, y - h * 0.35), (x, y), 1)
    elif kind == "scychop":
        # Taglio d'Albero: la grande ascia cala sul cono (lampo di pietra).
        o, d = s["o"], s["dir"]
        rng, half = s["range"], math.radians(s.get("angle", 30))
        al = _al(f, 1.6)
        pts = _cone_pts(S, o, d, rng, half)
        pygame.draw.polygon(overlay, (*STONE[2], al // 3), pts)
        pygame.draw.lines(overlay, (*STONE[0], al), True, pts, 2)
        base = math.atan2(d[1], d[0])
        cx, cy = S(*o)
        # Una sola grande lama che spazza il cono da un lato all'altro.
        prog = min(1.0, t / 0.3)
        head = base - half + 2 * half * prog
        tail = base - half + 2 * half * max(0.0, prog - 0.6)
        draw_blade(overlay, cx, cy - int(0.2 * ts), tail, head, rng * 0.8 * ts, 0.42 * ts,
                   STONE, al)


# --- handler degli eventi (FXSystem._FX_STYLES) ------------------------------------

def _sh(fx, **kw):
    """fx._shape con il colore di default (FXSystem lo legge per ogni forma)."""
    kw.setdefault("col", WHITE)
    fx._shape(**kw)


def _ab(e):
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return None
    return a, b


def _bits(fx, c, n, cols, speed=2.0, life=(0.2, 0.4), size=1, up=0.0):
    for _ in range(n):
        an = random.uniform(0, math.tau)
        v = random.uniform(0.4, 1.0) * speed
        fx._add(c[0], c[1], math.cos(an) * v, math.sin(an) * v * 0.5 - up,
                random.uniform(*life), random.choice(cols), size)


def _slash_aa(fx, e, cols, r=0.9, half=0.9, w=0.16):
    ab = _ab(e)
    if ab is None:
        return None
    a, b = ab
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    side = 1 if random.random() < 0.5 else -1
    _sh(fx, kind="scyblade", c=(b[0] - math.cos(ang) * r * 0.6, b[1] - math.sin(ang) * r * 0.6),
              ang=ang, half=half, r=r, w=w, side=side, cols=cols, life=0.22)
    return a, b, ang


def fx_scyslash(fx, e, col):
    """Attacco base di Scyther: una falciata verde (due se è il secondo colpo)."""
    got = _slash_aa(fx, e, SCY, r=0.8, half=0.85, w=0.15)
    if got:
        _bits(fx, got[1], 3, (SCY[2], WHITE), speed=1.2, life=(0.1, 0.25))


def fx_scypinch(fx, e, col):
    """Attacco base di Scizor: la chela rossa si chiude sul bersaglio."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    _sh(fx, kind="scypincer", c=b, ang=ang, r=0.42, col=STEEL[1], life=0.3)
    _bits(fx, b, 3, (METAL[2], STEEL[2]), speed=1.4, life=(0.1, 0.25))


def fx_kleacleave(fx, e, col):
    """Attacco base di Kleavor: colpo d'ascia di pietra largo (copre l'arco)."""
    got = _slash_aa(fx, e, STONE, r=1.0, half=1.0, w=0.24)
    if got:
        a, b, ang = got
        for _ in range(2):
            an = ang + random.uniform(-1.0, 1.0)
            _sh(fx, kind="scyshard", c=b, v=(math.cos(an) * 0.6, math.sin(an) * 0.4), h=0.4,
                      sz=0.06, life=0.4)


def fx_kleacleavearc(fx, e, col):
    """Asce di Pietra: l'arco dei colpi secondari (tenue, sotto il colpo)."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    ang = math.atan2(d[1], d[0])
    _sh(fx, kind="scyblade", c=o, ang=ang, half=math.radians(e.get("angle", 55)),
              r=e.get("range", 2.0) * 0.8, w=0.1, side=1, cols=STONE, life=0.2)


def fx_scyfury(fx, e, col):
    """Tagliofuria: falciata ad arco; più accumuli = lama più lunga e doppia,
    più verde-chiaro, con le schegge d'erba."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    n = int(e.get("stacks", 0))
    ang = math.atan2(d[1], d[0])
    half = math.radians(e.get("angle", 60))
    rng = e.get("range", 2.2)
    side = 1 if n % 2 == 0 else -1
    _sh(fx, kind="scyblade", c=o, ang=ang, half=half, r=rng * 0.75, w=0.2 + 0.03 * n,
              side=side, cols=SCY, life=0.28, echo=n >= 2)
    if n >= 3:   # seconda falce, a specchio
        _sh(fx, kind="scyblade", c=o, ang=ang, half=half * 0.8, r=rng * 0.55, w=0.16,
                  side=-side, cols=SCY, life=0.26, wait=0.06)
    for _ in range(3 + n * 2):
        an = ang + random.uniform(-half, half)
        dd = rng * random.uniform(0.5, 1.0)
        c = (o[0] + math.cos(an) * dd, o[1] + math.sin(an) * dd - 0.3)
        fx._add(c[0], c[1], math.cos(an) * 1.2, math.sin(an) * 0.6, random.uniform(0.15, 0.3),
                random.choice((SCY[1], SCY[2], WHITE)), 1)


def fx_scyfocus(fx, e, col):
    """Focalenergia: fiamme rosse che salgono attorno a Scyther + anello;
    con Doppiocolpo due falci si incrociano sopra la testa."""
    c = e.get("c")
    if c is None:
        return
    _sh(fx, kind="ring", c=c, r0=0.3, r1=1.0, col=FOCUS[1], life=0.35, wd=0.1)
    for k in range(6):   # fiammelle sul bordo (non sopra lo sprite)
        an = k * math.tau / 6 + 0.3
        _sh(fx, kind="scyflame", c=(c[0] + math.cos(an) * 0.75, c[1] + math.sin(an) * 0.4),
                  h=0.32, w=0.08, up=1.0, ph=k, col=FOCUS[1], life=0.5, wait=0.04 * k)
    if e.get("double"):
        top = (c[0], c[1] - 1.1)
        for side in (1, -1):
            _sh(fx, kind="scyblade", c=top, ang=-math.pi / 2, half=0.7, r=0.4, w=0.1,
                      side=side, cols=SCY, life=0.4)


def fx_scywing(fx, e, col):
    """Attacco d'Ala: scia di vento con le ali che fendono l'aria."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
    for off in (-0.35, 0.0, 0.35):
        _sh(fx, kind="windline", a=(a[0] + nx * off, a[1] + ny * off - 0.4),
                  b=(b[0] + nx * off, b[1] + ny * off - 0.4), col=WIND if off else SCY[2], life=0.3)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for side in (1, -1):
        _sh(fx, kind="scyblade", c=b, ang=ang + math.pi + side * 1.2, half=0.6, r=0.6, w=0.14,
                  side=side, cols=SCY, life=0.24)


def fx_scyuturn(fx, e, col):
    """Retromarcia: andata come Attacco d'Ala, ritorno con una scia ad arco."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    if e.get("back"):
        _sh(fx, kind="windline", a=(a[0], a[1] - 0.6), b=(b[0], b[1] - 0.2), col=SCY[2], life=0.35)
        _sh(fx, kind="ring", c=b, r0=0.2, r1=0.7, col=SCY[1], life=0.25, wd=0.08)
        return
    fx_scywing(fx, e, col)


def fx_scyheart(fx, e, col):
    """Cuordeciso: raffica di vento attorno a Scyther (riparte di slancio)."""
    c = e.get("c")
    if c is None:
        return
    for k in range(5):
        an = k * math.tau / 5 + random.uniform(-0.3, 0.3)
        a = (c[0] + math.cos(an) * 0.3, c[1] + math.sin(an) * 0.2 - 0.4)
        b = (c[0] + math.cos(an) * 1.1, c[1] + math.sin(an) * 0.6 - 0.4)
        _sh(fx, kind="windline", a=a, b=b, col=WIND, life=0.3)


def fx_scybullet(fx, e, col):
    """Pugnoscarica: scatto rosso-acciaio a tutta velocità (lo scatto) e il
    pugno che parte (l'impatto è "scypunch")."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    if e.get("kind") == "dash":
        _sh(fx, kind="windline", a=(a[0], a[1] - 0.4), b=(b[0], b[1] - 0.4), col=STEEL[2], life=0.2)
        _sh(fx, kind="windline", a=(a[0], a[1] - 0.2), b=(b[0], b[1] - 0.2), col=METAL[2], life=0.16)
        return
    fx_scypunch(fx, e, col)


def fx_scypunch(fx, e, col):
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    _sh(fx, kind="scyfist", a=a, b=b, sz=0.16, cols=METAL, col=METAL[1], life=0.32)
    top = (b[0], b[1] - 0.35)
    _sh(fx, kind="impactstar", c=top, r=0.45, n=6, rot=random.uniform(0, 1),
              cols=(STEEL[0], METAL[1], WHITE), col=METAL[1], life=0.22, wait=0.08)
    _bits(fx, top, 6, (METAL[2], STEEL[2], WHITE), speed=2.0, life=(0.12, 0.3))


def fx_scyinterrupt(fx, e, col):
    """Interruzione di Pugnoscarica: anello spezzato + scintille."""
    c = e.get("c")
    if c is None:
        return
    _sh(fx, kind="ring", c=(c[0], c[1] - 0.3), r0=0.9, r1=0.3, col=METAL[2], life=0.25, wd=0.06)
    _bits(fx, (c[0], c[1] - 0.6), 8, (WHITE, METAL[2]), speed=2.6, life=(0.15, 0.35))


def fx_scysuperpower(fx, e, col):
    """Troppoforte: pugno enorme arancione, onda d'urto e crepe."""
    c, a = e.get("c"), e.get("a")
    if c is None:
        return
    if a is not None:
        _sh(fx, kind="scyfist", a=a, b=c, sz=0.3, cols=FIGHT, col=FIGHT[1], life=0.35)
    _sh(fx, kind="impactstar", c=(c[0], c[1] - 0.35), r=0.9, n=8, rot=random.uniform(0, 1),
              cols=FIGHT, col=FIGHT[1], life=0.3, wait=0.08)
    _sh(fx, kind="groundring", c=c, r0=0.3, r1=1.6, col=FIGHT[2], life=0.4, wait=0.08)
    _sh(fx, kind="groundcrack", c=c, r=1.0, n=6, seed=random.randint(0, 9999), col=STONE[0],
              life=0.9, wait=0.08)
    for _ in range(5):
        an = random.uniform(0, math.tau)
        _sh(fx, kind="pebble", c=c, v=(math.cos(an) * 1.1, math.sin(an) * 0.6), h=0.5,
                  col=STONE[1], life=0.5, wait=0.08)
    fx.shake_until_ms = max(getattr(fx, "shake_until_ms", 0), pygame.time.get_ticks() + 180)


def fx_scyclaws(fx, e, col):
    """Chele d'Acciaio: lampo metallico e due chele che si incrociano."""
    c = e.get("c")
    if c is None:
        return
    _sh(fx, kind="flash", c=(c[0], c[1] - 0.4), r=0.8, col=METAL[2], life=0.2)
    _sh(fx, kind="ring", c=c, r0=0.3, r1=1.1, col=STEEL[1], life=0.35, wd=0.1)
    for side, ang in ((1, -0.4), (-1, math.pi + 0.4)):
        _sh(fx, kind="scypincer", c=(c[0] + math.cos(ang) * 0.5, c[1] - 0.2), ang=ang, r=0.38,
                  col=STEEL[1], life=0.35)
    _bits(fx, (c[0], c[1] - 0.5), 8, (WHITE, METAL[2], STEEL[2]), speed=1.6, life=(0.2, 0.4))


def fx_kleaaxe(fx, e, col):
    """Asciapietra: grande ascia ad arco, schegge che volano e si piantano nel
    punto colpito (dove nasce il campo)."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    ang = math.atan2(d[1], d[0])
    half = math.radians(e.get("angle", 55))
    rng = e.get("range", 2.4)
    _sh(fx, kind="scyblade", c=o, ang=ang, half=half, r=rng * 0.75, w=0.32, side=1,
              cols=STONE, life=0.32)
    c = e.get("c") or (o[0] + d[0] * 1.6, o[1] + d[1] * 1.6)
    for k in range(8):
        an = random.uniform(0, math.tau)
        dist = random.uniform(0.3, 1.6)
        _sh(fx, kind="scyshard", c=(c[0] - math.cos(an) * 0.2, c[1] - math.sin(an) * 0.1),
                  v=(math.cos(an) * dist, math.sin(an) * dist * 0.6), h=0.7, sz=0.09,
                  life=0.5, wait=0.05 + 0.02 * k)
    _sh(fx, kind="groundcrack", c=c, r=0.8, n=5, seed=random.randint(0, 9999), col=STONE[0],
              life=0.7, wait=0.1)


def fx_kleachop(fx, e, col):
    """Taglio d'Albero: l'avviso è il disegno persistente (scy_chops); qui solo
    la polvere della carica."""
    o = e.get("o")
    if o is None:
        return
    _bits(fx, (o[0], o[1] - 0.2), 6, (STONE[1], STONE[2]), speed=0.8, life=(0.3, 0.5), up=0.4)


def fx_kleachophit(fx, e, col):
    """Taglio d'Albero a segno: ascia gigante, crepe e schegge lungo il cono."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    rng = e.get("range", 5.0)
    _sh(fx, kind="scychop", o=o, dir=d, range=rng, angle=e.get("angle", 30), col=STONE[1],
              life=0.45)
    ang = math.atan2(d[1], d[0])
    half = math.radians(e.get("angle", 30))
    for k in range(4):
        dist = rng * (0.3 + 0.2 * k)
        c = (o[0] + d[0] * dist, o[1] + d[1] * dist)
        _sh(fx, kind="groundcrack", c=c, r=0.6 + 0.15 * k, n=5, seed=random.randint(0, 9999),
                  col=STONE[0], life=1.0, wait=0.04 * k)
    for k in range(14):
        an = ang + random.uniform(-half, half)
        dist = rng * random.uniform(0.2, 1.0)
        c = (o[0] + math.cos(an) * dist, o[1] + math.sin(an) * dist)
        _sh(fx, kind="scyshard", c=c, v=(random.uniform(-0.5, 0.5), random.uniform(-0.3, 0.3)),
                  h=0.9, sz=0.1, life=0.6, wait=0.02 * k)
    fx.shake_until_ms = max(getattr(fx, "shake_until_ms", 0), pygame.time.get_ticks() + 220)


def fx_kleasmash(fx, e, col):
    """Spaccaroccia: pugni arancioni che battono e la pietra che si incrina."""
    c = e.get("c")
    if c is None:
        return
    _sh(fx, kind="ring", c=c, r0=0.3, r1=1.0, col=FIGHT[1], life=0.35, wd=0.1)
    _sh(fx, kind="groundcrack", c=c, r=0.8, n=5, seed=random.randint(0, 9999), col=STONE[0],
              life=0.8)
    _bits(fx, (c[0], c[1] - 0.4), 8, (FIGHT[1], FIGHT[2], STONE[2]), speed=1.6, life=(0.2, 0.4))


def fx_kleashred(fx, e, col):
    """Spaccaroccia a segno: crepa sull'armatura del colpito."""
    c = e.get("c")
    if c is None:
        return
    top = (c[0], c[1] - 0.5)
    _sh(fx, kind="impactstar", c=top, r=0.3, n=5, rot=random.uniform(0, 1), cols=FIGHT,
              col=FIGHT[1], life=0.2)
    _bits(fx, top, 4, (STONE[1], STONE[2]), speed=1.4, life=(0.15, 0.3))


STYLES = {
    "scyslash": fx_scyslash, "scypinch": fx_scypinch, "kleacleave": fx_kleacleave,
    "kleacleavearc": fx_kleacleavearc, "scyfury": fx_scyfury, "scyfocus": fx_scyfocus,
    "scywing": fx_scywing, "scyuturn": fx_scyuturn, "scyheart": fx_scyheart,
    "scybullet": fx_scybullet, "scypunch": fx_scypunch, "scyinterrupt": fx_scyinterrupt,
    "scysuperpower": fx_scysuperpower, "scyclaws": fx_scyclaws, "kleaaxe": fx_kleaaxe,
    "kleachop": fx_kleachop, "kleachophit": fx_kleachophit, "kleasmash": fx_kleasmash,
    "kleashred": fx_kleashred,
}


# --- disegni persistenti (world_fx) ---------------------------------------------------

_SHARD_CACHE: dict = {}


def _shard_sprite(seed, ts):
    """Sprite di una scheggia piantata a terra (pixel art, in cache per variante)."""
    key = (seed % 6, ts)
    spr = _SHARD_CACHE.get(key)
    if spr is not None:
        return spr
    rnd = random.Random(seed % 6 + 11)
    h = max(5, int(ts * rnd.uniform(0.16, 0.26)))
    w = max(3, int(h * rnd.uniform(0.45, 0.65)))
    spr = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    lean = rnd.randint(-1, 1)
    tip = (w // 2 + 1 + lean, 0)
    pts = [tip, (w + 1, h + 1), (0, h + 1)]
    pygame.draw.polygon(spr, AUGITE[0], pts)
    inner = [(tip[0], 2), (w - 1, h), (1, h)]
    pygame.draw.polygon(spr, AUGITE[1], inner)
    pygame.draw.polygon(spr, AUGITE[2], [(tip[0], 2), (tip[0], h), (1, h)])   # lato in luce
    pygame.draw.line(spr, STONE[2], (tip[0], 2), (tip[0] - 1, h // 2), 1)
    _SHARD_CACHE[key] = spr
    return spr


def _field_points(fl):
    """Posizioni (mondo) delle schegge del campo: stabili per tutta la durata."""
    pts = fl.get("_pts")
    if pts is not None:
        return pts
    rnd = random.Random(int(fl.get("id", 7)))
    pts = []
    if fl.get("kind") == "circle":
        c, R = fl["c"], fl["r"]
        n = int(10 + R * 6)
        for _ in range(n):
            an = rnd.uniform(0, math.tau)
            rr = R * math.sqrt(rnd.uniform(0.02, 0.92))
            pts.append((c.x + math.cos(an) * rr, c.y + math.sin(an) * rr, rnd.randrange(999)))
    else:
        o, d, rng = fl["o"], fl["dir"], fl["range"]
        half = fl.get("half", math.radians(fl.get("angle", 30)))
        base = math.atan2(d.y, d.x)
        n = int(18 + rng * 5)
        for _ in range(n):
            an = base + rnd.uniform(-half, half) * 0.92
            rr = rng * math.sqrt(rnd.uniform(0.04, 0.95))
            pts.append((o.x + math.cos(an) * rr, o.y + math.sin(an) * rr, rnd.randrange(999)))
    pts.sort(key=lambda q: q[1])
    fl["_pts"] = pts
    return pts


def _vec(v):
    return (v.x, v.y) if hasattr(v, "x") else (v[0], v[1])


def draw_field(surface, camera, fl, now):
    """Campo di schegge (Asciapietra, Taglio d'Albero): terreno scurito con
    il bordo tratteggiato, schegge di pietra scura piantate a terra; sparisce
    sfumando nell'ultimo secondo. Visibile a tutti."""
    ts = config.TILE_SIZE
    left = fl["end"] - now
    born = now - fl.get("born", now - 1.0)
    al = max(0.0, min(1.0, left / 1.0, born / 0.2))
    if al <= 0.0:
        return
    for k in ("c", "o", "dir"):
        if k in fl and not hasattr(fl[k], "x"):
            from engine.vec import Vec2
            fl[k] = Vec2(*fl[k])

    def S(x, y):
        return camera.world_to_screen(x * ts, y * ts)

    if fl.get("kind") == "circle":
        c, R = fl["c"], fl["r"]
        cx, cy = S(c.x, c.y)
        rw = rh = int(R * ts)   # cerchio vero, come l'area in logica
        surf = pygame.Surface((rw * 2 + 4, rh * 2 + 4), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (*AUGITE[0], int(70 * al)), pygame.Rect(2, 2, rw * 2, rh * 2))
        surface.blit(surf, (cx - rw - 2, cy - rh - 2))
        n = max(16, int(R * 14))
        for i in range(0, n, 2):
            a0 = i * math.tau / n + now * 0.4
            a1 = a0 + math.tau / n
            pygame.draw.line(surface, STONE[1], (cx + math.cos(a0) * rw, cy + math.sin(a0) * rh),
                             (cx + math.cos(a1) * rw, cy + math.sin(a1) * rh), 1)
    else:
        o, d = fl["o"], fl["dir"]
        half = fl.get("half", math.radians(fl.get("angle", 30)))
        pts = _cone_pts(S, (o.x, o.y), (d.x, d.y), fl["range"], half)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0 = min(xs), min(ys)
        surf = pygame.Surface((max(xs) - x0 + 2, max(ys) - y0 + 2), pygame.SRCALPHA)
        pygame.draw.polygon(surf, (*AUGITE[0], int(70 * al)), [(x - x0, y - y0) for x, y in pts])
        surface.blit(surf, (x0, y0))
        for i in range(0, len(pts), 1):
            if i % 2 == 0:
                a, b = pts[i], pts[(i + 1) % len(pts)]
                pygame.draw.line(surface, STONE[1], a, b, 1)
    sink = int((1.0 - al) * 4)
    for x, y, sd in _field_points(fl):
        gx, gy = S(x, y)
        spr = _shard_sprite(sd, ts)
        if al < 1.0:
            spr = spr.copy()
            spr.set_alpha(int(255 * al))
        surface.blit(spr, (gx - spr.get_width() // 2, gy - spr.get_height() + sink))


def draw_chop(surface, camera, ch, now):
    """Taglio d'Albero in carica: cono rosso-pietra che si riempie dal
    lanciatore verso la punta (avviso visibile a TUTTI)."""
    ts = config.TILE_SIZE
    o, d = _vec(ch["o"]), _vec(ch["dir"])
    span = max(1e-3, ch["t"] - ch.get("start", ch["t"] - 0.5))
    u = max(0.0, min(1.0, 1.0 - (ch["t"] - now) / span))
    half = math.radians(ch.get("angle", 30))

    def S(x, y):
        return camera.world_to_screen(x * ts, y * ts)

    full = _cone_pts(S, o, d, ch["range"], half)
    xs = [p[0] for p in full]
    ys = [p[1] for p in full]
    x0, y0 = min(xs) - 2, min(ys) - 2
    surf = pygame.Surface((max(xs) - x0 + 4, max(ys) - y0 + 4), pygame.SRCALPHA)
    pygame.draw.polygon(surf, (190, 70, 40, 50), [(x - x0, y - y0) for x, y in full])
    part = _cone_pts(S, o, d, ch["range"] * u, half)
    if u > 0.02:
        pygame.draw.polygon(surf, (220, 110, 60, 90), [(x - x0, y - y0) for x, y in part])
    surface.blit(surf, (x0, y0))
    pygame.draw.lines(surface, (236, 140, 80), True, full, 1)
    # ascia alzata sopra il lanciatore
    cx, cy = S(*o)
    tilt = -math.pi / 2 - 0.9 * (1.0 - u)
    hx, hy = cx + math.cos(tilt) * ts * 0.9, cy - ts * 0.4 + math.sin(tilt) * ts * 0.9
    pygame.draw.line(surface, STONE[0], (cx, cy - ts * 0.4), (hx, hy), 3)
    draw_shard(surface, hx, hy, ts * 0.22, tilt + math.pi / 2, STONE)


# --- sulle unità ------------------------------------------------------------------------

def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Focalenergia (fiammelle rosse), Doppiocolpo pronto (due falci sopra),
    Chele d'Acciaio (riflessi d'acciaio), Troppoforte (frecce in giù),
    Cuordeciso (linee di vento), Spaccaroccia attiva (pugni arancioni),
    Kleavor nel suo campo (scaglie di pietra che girano)."""
    r = int(getattr(u, "radius", 0.5) * ts)
    if getattr(u, "scy_focus_until", -1.0) > now:
        for k in range(6):
            ph = (now * 1.8 + k / 6) % 1.0
            x = gx + (r + 2) * (1 if k % 2 else -1) + math.sin(k * 2.1 + now * 3) * 2
            y = gy - ph * r * 2.0
            s = max(1, int(2 * (1 - ph)) + 1)
            pts = [(x, y - s * 2), (x + s, y), (x - s, y)]
            pygame.draw.polygon(surface, FOCUS[1], pts)
            surface.set_at((int(x), int(y - s)), FOCUS[2])
    if getattr(u, "scy_double_ready", False):
        top = gy - 2 * r - 20
        for side in (-1, 1):
            x = gx + side * 4
            pygame.draw.line(surface, SCY[0], (x - side * 3, top + 5), (x + side * 2, top - 2), 3)
            pygame.draw.line(surface, SCY[2], (x - side * 3, top + 5), (x + side * 2, top - 2), 1)
    if getattr(u, "scy_claws_until", -1.0) > now:
        rnd = random.Random(int(now * 10) + getattr(u, "id", 0))
        for _ in range(3):
            an = rnd.uniform(0, math.tau)
            x = int(gx + math.cos(an) * r * 0.9)
            y = int(gy - r + math.sin(an) * r * 0.7)
            pygame.draw.line(surface, METAL[2], (x - 2, y), (x + 2, y))
            pygame.draw.line(surface, METAL[2], (x, y - 2), (x, y + 2))
        for side in (-1, 1):   # alone rosso sulle chele
            pygame.draw.circle(surface, STEEL[1], (gx + side * (r + 2), gy - r), 3, 1)
    if getattr(u, "scy_down_until", -1.0) > now:
        for k, side in enumerate((-1, 1)):
            x = gx + side * (r + 5)
            y = gy - r + int((now * 6 + k) % 2)
            pygame.draw.polygon(surface, (90, 120, 200), [(x - 3, y - 2), (x + 3, y - 2), (x, y + 2)])
    if getattr(u, "scy_heart_until", -1.0) > now:
        for k in range(3):
            ph = (now * 3 + k / 3) % 1.0
            y = gy - r * (0.4 + 0.5 * k)
            x0 = gx - r - 2 - ph * r
            pygame.draw.line(surface, WIND, (x0, y), (x0 - r * 0.6, y), 1)
    if getattr(u, "scy_smash_until", -1.0) > now:
        for k in range(2):
            an = now * 4 + k * math.pi
            x = gx + math.cos(an) * (r + 3)
            y = gy - r * 0.6 + math.sin(an) * 3
            draw_fist(surface, x, y, 3, an + math.pi / 2, FIGHT)
    if getattr(u, "scy_infield", False):
        for k in range(3):
            an = now * 2.2 + k * math.tau / 3
            x = gx + math.cos(an) * (r + 2)
            y = gy - r * 0.3 + math.sin(an) * r * 0.35
            draw_shard(surface, x, y, 3, an, AUGITE)


def draw_hp_extras(surface, u, gx, top, w, row):
    """Spaccaroccia subita: tacche di armatura incrinata sotto la barra della
    vita (una per accumulo, max 5, visibili a tutti)."""
    n = int(getattr(u, "scy_shred", 0))
    if n <= 0:
        return
    y = top + 6 + row * 6
    x0 = gx - w // 2
    x0 = gx - 15
    for i in range(5):
        r = pygame.Rect(x0 + i * 6, y, 6, 6)
        pygame.draw.rect(surface, (12, 10, 10), r)   # contorno scuro: si legge su ogni sprite
        inner = r.inflate(-2, -2)
        if i < n:   # piastra chiara incrinata
            pygame.draw.rect(surface, (236, 226, 210), inner)
            surface.set_at((inner.x + 1, inner.y), FIGHT[0])
            surface.set_at((inner.x + 2, inner.y + 1), FIGHT[0])
            surface.set_at((inner.x + 1, inner.y + 2), FIGHT[0])
            surface.set_at((inner.x + 2, inner.y + 3), FIGHT[0])
        else:
            pygame.draw.rect(surface, (58, 52, 48), inner)


# --- interfaccia ---------------------------------------------------------------------------

def _scythe_icon(surface, cx, cy, s, cols):
    draw_blade(surface, cx + s * 0.3, cy + s * 0.5, -math.pi * 0.95, -math.pi * 0.25, s, s * 0.45,
               cols)
    pygame.draw.line(surface, cols[0], (cx - s * 0.1, cy + s * 0.9), (cx + s * 0.4, cy - s * 0.1), 2)


def draw_hud(surface, font, p, bx, y0, bh, now, level=0, fury=0):
    """Passiva della linea: Cuordeciso (falce verde; dal liv.8 avviso
    dell'evoluzione tramite oggetto), Tecnico (chela rossa), Asce di Pietra
    (ascia di pietra). Accanto: accumuli di Tagliofuria o tempi attivi."""
    pid = getattr(p, "passive_id", "")
    box = pygame.Rect(bx, y0, bh, bh)
    pygame.draw.rect(surface, (26, 30, 26), box)
    cx, cy = box.centerx, box.centery
    s = bh * 0.32
    if pid == "tecnico":
        frame = STEEL[1]
        draw_fist(surface, cx, cy, s * 0.8, -0.6, STEEL)
    elif pid == "ascedipietra":
        frame = STONE[1]
        pygame.draw.line(surface, (90, 64, 40), (cx - s, cy + s), (cx + s * 0.6, cy - s * 0.6), 3)
        draw_shard(surface, cx + s * 0.4, cy - s * 0.4, s * 0.7, -0.4, STONE)
    else:
        frame = SCY[1]
        _scythe_icon(surface, cx, cy, s, SCY)
        if getattr(p, "scy_heart_until", -1.0) > now:
            frame = WIND
    pygame.draw.rect(surface, frame, box, 2)
    label = PASSIVE_NAMES.get(pid, "")
    col = frame
    if pid == "cuordeciso" and level >= 8:
        # Dal liv.8: può evolvere comprando uno dei due oggetti.
        blink = int(now * 2) % 2 == 0
        label = "Evolvi: Metalcoperta/Augite"
        col = (255, 220, 110) if blink else (230, 190, 90)
        pygame.draw.rect(surface, col, box.inflate(4, 4), 1)
    surface.blit(font.render(label, True, col), (bx - 4, y0 - 18))
    x = box.right + 6
    if fury > 0 and getattr(p, "scy_fury_until", -1.0) > now:
        for k in range(4):
            y = y0 + 4 + k * max(6, (bh - 8) // 4)
            c = SCY[2] if k < fury else (60, 70, 60)
            pygame.draw.line(surface, SCY[0], (x - 2, y + 3), (x + 4, y - 2), 3)
            pygame.draw.line(surface, c, (x - 2, y + 3), (x + 4, y - 2), 1)


def draw_aim(surface, S, ts, ox, oy, nx, ny, dist, move) -> bool:
    """Mirino delle mosse della linea. Ritorna False se la forma non è sua."""
    shape = move.shape
    rng = move.range
    if shape in ("scyfury", "kleaaxe", "scysuperpower", "kleachop"):
        half = math.radians(move.angle)
        col = {"scyfury": SCY[2], "kleaaxe": STONE[2], "scysuperpower": FIGHT[2],
               "kleachop": (236, 140, 80)}[shape]
        pygame.draw.lines(surface, col, True, _cone_pts(S, (ox, oy), (nx, ny), rng, half), 1)
        if shape == "kleaaxe":
            fd = move.effects.get("field", {})
            c = S(ox + nx * min(1.6, rng), oy + ny * min(1.6, rng))
            R = float(fd.get("radius", 2.0)) * ts
            pygame.draw.ellipse(surface, AUGITE[2], pygame.Rect(c[0] - R, c[1] - R * 0.8, R * 2, R * 1.6), 1)
        return True
    if shape in ("scywing", "scybullet"):
        ex, ey = ox + nx * rng, oy + ny * rng
        col = SCY[2] if shape == "scywing" else STEEL[2]
        w = move.radius
        px, py = -ny * w, nx * w
        for sg in (1, -1):
            pygame.draw.line(surface, col, S(ox + px * sg, oy + py * sg), S(ex + px * sg, ey + py * sg), 1)
        pygame.draw.line(surface, WHITE, S(ox, oy), S(ex, ey), 1)
        back = float(move.effects.get("back", 0.0))
        if back > 0.0:   # Retromarcia: freccia del ritorno
            bx, by = ex - nx * back, ey - ny * back
            pts = [S(ex + px * 1.6, ey + py * 1.6), S(bx + px * 1.6, by + py * 1.6)]
            pygame.draw.line(surface, SCY[1], pts[0], pts[1], 1)
            tip = pts[1]
            l = S(bx + px * 1.6 + nx * 0.4 + px * 0.6, by + py * 1.6 + ny * 0.4 + py * 0.6)
            r = S(bx + px * 1.6 + nx * 0.4 - px * 0.6, by + py * 1.6 + ny * 0.4 - py * 0.6)
            pygame.draw.lines(surface, SCY[2], False, [l, tip, r], 1)
        return True
    if shape in ("scyfocus", "scyclaws", "kleasmash"):
        return True
    return False
