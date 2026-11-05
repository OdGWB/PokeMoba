"""Grafica della linea Litten > Torracat > Incineroar: effetti istantanei
(handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (calcio di fuoco ad arco, fauci di fuoco, croce di
Incrocolpo, ruggito di Bullo, corde del ring che si tendono al rimbalzo,
scia di fuoco della corsa, anello del Darkest Lariat), disegni sulle unità
(Lariat che gira, pugni accesi dal rimbalzo, frecce dell'Attacco per Bullo e
Prepotenza), HUD della passiva e mirini.

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

from .charcadet_fx import draw_flame
from .scy_fx import draw_blade, draw_fist

FIRE = ((140, 30, 16), (246, 112, 40), (255, 222, 120))       # fiamme della cintura
HEEL = ((70, 14, 18), (196, 40, 44), (255, 150, 120))        # rosso di Incineroar
DARK = ((22, 14, 26), (74, 40, 84), (170, 120, 190))         # Buio (Lariat, Prepotenza)
FIGHT = ((110, 40, 14), (226, 120, 52), (255, 214, 150))     # Lotta (impatti)
ROPE = ((40, 20, 20), (216, 52, 52), (255, 236, 220))        # corde del ring
GOLD = (255, 214, 96)
WHITE = (255, 255, 255)

INCIN_DEX = (725, 726, 727)
PASSIVE_NAMES = {"prepotenza": "Prepotenza", "cattivodelring": "Cattivo del Ring"}


def _al(f, k=2.0):
    return max(0, min(255, int(255 * min(1.0, f * k))))


def is_incin(u) -> bool:
    return (getattr(u, "passive_id", "") in PASSIVE_NAMES
            or getattr(u, "dex", 0) in INCIN_DEX)


# --- mattoni ---------------------------------------------------------------------------

def draw_arrow(surface, x, y, up, col, dk=(12, 8, 10)):
    """Freccina pixel art 5x5 (su = Attacco aumentato, giù = diminuito)."""
    x, y = int(x), int(y)
    pts = ([(x, y - 3), (x + 3, y), (x + 1, y), (x + 1, y + 3), (x - 1, y + 3), (x - 1, y), (x - 3, y)]
           if up else
           [(x, y + 3), (x + 3, y), (x + 1, y), (x + 1, y - 3), (x - 1, y - 3), (x - 1, y), (x - 3, y)])
    pygame.draw.polygon(surface, dk, [(px + 1, py + 1) for px, py in pts])
    pygame.draw.polygon(surface, dk, pts, 0)
    inner = [(px + (0 if px == x else (-1 if px > x else 1)), py) for px, py in pts]
    pygame.draw.polygon(surface, col, inner)


def draw_ropes(surface, cx, cy, ang, L, bulge, alpha, ts):
    """Tre corde del ring perpendicolari alla direzione `ang`, tese verso
    l'esterno di `bulge` (px) al centro: rossa, bianca, rossa."""
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    for k, col in enumerate((ROPE[1], ROPE[2], ROPE[1])):
        off = (k - 1) * 0.16 * ts
        pts = []
        n = 10
        for i in range(n + 1):
            u = i / n * 2 - 1
            b = bulge * (1.0 - u * u)
            x = cx + px * u * L + ux * b
            y = cy + py * u * L * 0.8 + uy * b * 0.8 - off
            pts.append((x, y))
        pygame.draw.lines(surface, (*ROPE[0], alpha), False, [(x, y + 1) for x, y in pts], 3)
        pygame.draw.lines(surface, (*col, alpha), False, pts, 2)
    for sg in (-1, 1):   # paletti agli angoli
        x, y = cx + px * L * sg, cy + py * L * 0.8 * sg
        r = pygame.Rect(int(x) - 2, int(y - 0.5 * ts), 4, int(0.5 * ts) + 2)
        pygame.draw.rect(surface, (*ROPE[0], alpha), r.inflate(2, 2))
        pygame.draw.rect(surface, (*GOLD, alpha), r)


def draw_jaw(surface, cx, cy, ang, r, gap, alpha):
    """Fauci di fuoco: due mascelle curve (sopra e sotto rispetto alla
    direzione del morso) con tre zanne a punta ciascuna, che si chiudono."""
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    for sg in (1, -1):
        # mascella: arco che si apre verso il centro del morso
        arc = []
        n = 8
        for i in range(n + 1):
            u = i / n * 2 - 1
            off = gap + r * (0.18 + 0.32 * u * u)
            arc.append((cx + ux * u * r * 0.8 + px * sg * off,
                        cy + uy * u * r * 0.8 + py * sg * off))
        pygame.draw.lines(surface, (*FIRE[0], alpha), False, arc, 5)
        pygame.draw.lines(surface, (*FIRE[1], alpha), False, arc, 3)
        pygame.draw.lines(surface, (*FIRE[2], alpha), False, arc[2:7], 1)
        for u in (-0.38, 0.38):   # due zanne grandi verso il centro
            off = gap + r * (0.18 + 0.32 * u * u)
            bx = cx + ux * u * r * 0.8 + px * sg * off
            by = cy + uy * u * r * 0.8 + py * sg * off
            ln = r * 0.5
            tip = (bx - px * sg * ln + ux * u * r * 0.2, by - py * sg * ln + uy * u * r * 0.2)
            hw = r * 0.2
            l = (bx - ux * hw, by - uy * hw)
            rr = (bx + ux * hw, by + uy * hw)
            pygame.draw.polygon(surface, (*FIRE[0], alpha), [tip, l, rr])
            pygame.draw.polygon(surface, (250, 244, 230, alpha),
                                [(tip[0] + px * sg, tip[1] + py * sg),
                                 (l[0] + ux - px * sg, l[1] + uy - py * sg),
                                 (rr[0] - ux - px * sg, rr[1] - uy - py * sg)])


def _stroke(surface, a, b, w, cols, alpha, prog=1.0):
    """Tratto affusolato a, b (spesso al centro) che si traccia fino a `prog`."""
    n = 10
    m = max(1, int(n * prog))
    pts = [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(m + 1)]
    for k, col in enumerate(cols):
        for i in range(len(pts) - 1):
            u = (i + 0.5) / n
            ww = max(1, int(round(w * math.sin(math.pi * u) * (1.0 - 0.4 * k))))
            if k == 0:
                ww += 2
            pygame.draw.line(surface, (*col, alpha), pts[i], pts[i + 1], ww)


# --- forme (FXSystem._draw_shapes) ------------------------------------------------------

SHAPES = ("incinjaw", "incinx", "incinroar", "incinropes", "incinstreak", "incinspin")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "incinjaw":
        cx, cy = S(*s["c"])
        cy -= int(0.35 * ts)
        snap = min(1.0, t / 0.3)
        gap = (1.0 - snap) * 0.35 * ts
        al = _al(f, 2.5)
        if snap >= 1.0:   # morso chiuso: lampo di brace
            pygame.draw.circle(overlay, (*FIRE[1], al // 2), (int(cx), int(cy)), int(0.3 * ts))
        draw_jaw(overlay, cx, cy, s.get("ang", 0.0), s.get("r", 0.45) * ts, gap, al)
    elif kind == "incinx":
        # Incrocolpo: due tagli che si incrociano (uno dopo l'altro) e lampo al centro.
        cx, cy = S(*s["c"])
        cy -= int(0.3 * ts)
        arm = s.get("arm", 1.0) * ts
        base = s.get("ang", 0.0)
        al = _al(f, 2.0)
        w = s.get("w", 0.22) * ts
        for k, sg in enumerate((1, -1)):
            prog = min(1.0, max(0.0, (t - 0.12 * k) / 0.22))
            if prog <= 0:
                continue
            an = base + sg * math.pi / 4
            ux, uy = math.cos(an), math.sin(an) * 0.8
            a0 = (cx - ux * arm, cy - uy * arm)
            b0 = (cx + ux * arm, cy + uy * arm)
            if sg < 0:
                a0, b0 = b0, a0
            _stroke(overlay, a0, b0, w, (FIGHT[0], FIGHT[1], WHITE), al, prog)
        if t > 0.3:
            r = int(0.35 * ts * (1.0 + (t - 0.3)))
            pygame.draw.circle(overlay, (*FIGHT[2], al // 2), (int(cx), int(cy)), r, 2)
    elif kind == "incinroar":
        # Bullo: tre archi spessi che escono nel cono (rosso scuro / viola).
        cx, cy = S(*s["o"])
        cy -= int(0.3 * ts)
        ang = s.get("ang", 0.0)
        half = s.get("half", 0.7)
        rng = s.get("rng", 3.0) * ts
        al = _al(f, 2.0)
        cols = s.get("cols", (DARK[0], HEEL[1], HEEL[2]))
        for k in range(3):
            u = ((t * 1.6) + k / 3.0) % 1.0
            r = rng * (0.25 + 0.75 * u)
            aa = int(al * (1.0 - u))
            if aa <= 0:
                continue
            pts = []
            for i in range(13):
                an = ang - half + 2 * half * i / 12
                pts.append((cx + math.cos(an) * r, cy + math.sin(an) * r * 0.8))
            pygame.draw.lines(overlay, (*cols[0], aa), False, pts, 6)
            pygame.draw.lines(overlay, (*cols[1], aa), False, pts, 3)
            pygame.draw.lines(overlay, (*cols[2], aa), False, pts[3:10], 1)
    elif kind == "incinropes":
        # Corde del ring che si tendono contro il muro e scattano indietro.
        cx, cy = S(*s["c"])
        u = min(1.0, t / 0.25)
        bulge = math.sin(u * math.pi) * s.get("b", 0.5) * ts * (1.0 if u < 1.0 else 0.0)
        bulge += math.sin(t * 40) * 2 * f if u >= 1.0 else 0.0   # vibrano
        draw_ropes(overlay, cx, cy, s.get("ang", 0.0), s.get("L", 0.9) * ts, bulge, _al(f, 2.0), ts)
    elif kind == "incinstreak":
        # Scia di fuoco della corsa / del nemico scagliato (si ritira verso la punta).
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        lift = s.get("lift", 0.3) * ts
        u0 = min(1.0, t * 0.9)
        sx, sy = ax + (bx - ax) * u0, ay + (by - ay) * u0
        al = _al(f, 2.0)
        cols = s.get("cols", FIRE)
        pygame.draw.line(overlay, (*cols[0], al), (sx, sy - lift), (bx, by - lift), 5)
        pygame.draw.line(overlay, (*cols[1], al), (sx, sy - lift), (bx, by - lift), 3)
        pygame.draw.line(overlay, (*cols[2], al), (sx, sy - lift - 1), (bx, by - lift - 1), 1)
    elif kind == "incinspin":
        # Darkest Lariat: anello schiacciato viola-rosso che si allarga a ogni colpo.
        cx, cy = S(*s["c"])
        R = s.get("r", 2.5) * ts
        r = R * (0.55 + 0.45 * min(1.0, t * 3.0))
        al = _al(f, 2.0)
        rect = pygame.Rect(int(cx - r), int(cy - r * 0.55), int(r * 2), int(r * 1.1))
        pygame.draw.ellipse(overlay, (*DARK[0], al), rect.inflate(4, 4), 5)
        pygame.draw.ellipse(overlay, (*HEEL[1], al), rect, 3)
        pygame.draw.arc(overlay, (*FIRE[2], al), rect, math.pi * 0.55, math.pi * 1.05, 1)
        rot = s.get("rot", 0.0) + t * 6.0
        for k in range(3):   # fiammate sul bordo che girano
            an = rot + k * math.tau / 3
            x, y = cx + math.cos(an) * r, cy + math.sin(an) * r * 0.55
            draw_flame(overlay, x, y, 0.35 * ts * f, 0.2 * ts, al, (DARK[0], HEEL[1], FIRE[2]))


# --- handler degli eventi (FXSystem._FX_STYLES) ------------------------------------

def _sh(fx, **kw):
    kw.setdefault("col", WHITE)
    fx._shape(**kw)


def _bits(fx, c, n, cols, speed=2.0, life=(0.2, 0.4), size=1, up=0.0):
    for _ in range(n):
        an = random.uniform(0, math.tau)
        v = random.uniform(0.4, 1.0) * speed
        fx._add(c[0], c[1], math.cos(an) * v, math.sin(an) * v * 0.5 - up,
                random.uniform(*life), random.choice(cols), size)


def _tongues(fx, c, n, spread, h=0.45, w=0.25, life=(0.25, 0.45), up=0.5, cols=FIRE, wait=0.0):
    for k in range(n):
        an = random.uniform(0, math.tau)
        r = spread * random.uniform(0.2, 1.0)
        _sh(fx, kind="flametongue", c=(c[0] + math.cos(an) * r, c[1] + math.sin(an) * r * 0.7),
            v=(random.uniform(-0.2, 0.2), -up * random.uniform(0.5, 1.0)),
            h=h * random.uniform(0.7, 1.2), w=w * random.uniform(0.8, 1.2),
            ph=random.uniform(0, 6), cols=cols, col=cols[1], life=random.uniform(*life),
            wait=wait)


def _ab(e):
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return None
    return a, b


def fx_incinclaw(fx, e, col):
    """Attacco base di Litten/Torracat: tre graffi infuocati."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    _sh(fx, kind="claw3", c=(b[0], b[1] - 0.35), r=0.32, half=0.7, ang=ang + math.pi / 2,
        cols=FIRE, life=0.26)
    _bits(fx, (b[0], b[1] - 0.4), 3, (FIRE[1], FIRE[2]), speed=1.2, life=(0.1, 0.25))


def fx_incinpunch(fx, e, col):
    """Attacco base di Incineroar: pugno rosso con le linee di velocità."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    _sh(fx, kind="scyfist", a=a, b=b, sz=0.17, cols=HEEL, col=HEEL[1], life=0.3)
    top = (b[0], b[1] - 0.35)
    _sh(fx, kind="impactstar", c=top, r=0.32, n=6, rot=random.uniform(0, 1), cols=FIRE,
        col=FIRE[1], life=0.2, wait=0.08)
    _bits(fx, top, 4, (FIRE[1], FIRE[2]), speed=1.5, life=(0.1, 0.25))


def fx_incinkick(fx, e, col):
    """Doppiocalcio: arco del calcio (destro poi sinistro) con la scia di fuoco."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    n = int(e.get("n", 0))
    ang = math.atan2(d[1], d[0])
    rng = e.get("range", 1.9)
    side = 1 if n % 2 == 0 else -1
    _sh(fx, kind="scyblade", c=o, ang=ang, half=math.radians(e.get("angle", 40)) * 1.1,
        r=rng * 0.7, w=0.26, side=side, cols=FIGHT, life=0.24)
    tip = (o[0] + d[0] * rng * 0.75, o[1] + d[1] * rng * 0.75)
    _sh(fx, kind="impactstar", c=(tip[0], tip[1] - 0.3), r=0.3, n=5, rot=random.uniform(0, 1),
        cols=FIGHT, col=FIGHT[1], life=0.18, wait=0.1)
    _tongues(fx, tip, 2, 0.3, h=0.35, w=0.2, life=(0.2, 0.35), wait=0.05)
    if e.get("emp"):
        fx_incinempower(fx, {"c": tip}, col)


def fx_incinfang(fx, e, col):
    """Fuocodenti: fauci di fuoco che si chiudono sul bersaglio."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    _sh(fx, kind="incinjaw", c=b, ang=ang, r=0.7, col=FIRE[1], life=0.45)
    if e.get("hit", True):
        _tongues(fx, b, 3, 0.45, h=0.4, w=0.22, wait=0.25)
        _bits(fx, (b[0], b[1] - 0.4), 6, (FIRE[1], FIRE[2], WHITE), speed=1.8, life=(0.15, 0.3))


def fx_incincross(fx, e, col):
    """Incrocolpo: X arancio-bianca davanti a sé; stella d'impatto se a segno."""
    c, d = e.get("c"), e.get("dir")
    if c is None:
        return
    ang = math.atan2(d[1], d[0]) if d else 0.0
    _sh(fx, kind="incinx", c=c, ang=ang, arm=e.get("radius", 1.05), w=0.24, col=FIGHT[1],
        life=0.42)
    if e.get("hit"):
        _sh(fx, kind="impactstar", c=(c[0], c[1] - 0.3), r=0.55, n=8, rot=random.uniform(0, 1),
            cols=FIGHT, col=FIGHT[1], life=0.24, wait=0.3)
        _bits(fx, (c[0], c[1] - 0.3), 8, (FIGHT[2], WHITE), speed=2.4, life=(0.15, 0.3))


def _roar(fx, e, cols):
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return None
    ang = math.atan2(d[1], d[0])
    _sh(fx, kind="incinroar", o=o, ang=ang, half=math.radians(e.get("angle", 45)),
        rng=e.get("range", 3.5), cols=cols, col=cols[1], life=0.55)
    return ang


def fx_incinbully(fx, e, col):
    """Bullo: ruggito rosso nel cono + fiammata della cintura."""
    o = e.get("o")
    if _roar(fx, e, (DARK[0], HEEL[1], HEEL[2])) is None:
        return
    _tongues(fx, o, 5, 0.6, h=0.5, w=0.3, cols=FIRE)


def fx_incinbulkup(fx, e, col):
    """Granfisico: ruggito + muscoli gonfi (anello arancio che si stringe)."""
    o = e.get("o")
    if _roar(fx, e, (FIGHT[0], FIGHT[1], FIGHT[2])) is None:
        return
    _sh(fx, kind="ring", c=o, r0=1.2, r1=0.3, col=FIGHT[1], life=0.4, wd=0.12)
    _bits(fx, (o[0], o[1] - 0.5), 8, (FIGHT[1], FIGHT[2]), speed=1.4, life=(0.25, 0.45), up=0.8)


def fx_incintaunt(fx, e, col):
    """Provocazione: ruggito viola scuro, più lungo."""
    if _roar(fx, e, (DARK[0], DARK[1], DARK[2])) is None:
        return


def fx_incinrun(fx, e, col):
    """Corsa alle Corde: scia di fuoco dietro Incineroar (più chiara dopo i rimbalzi)."""
    ab = _ab(e)
    if ab is None:
        return
    cols = FIRE if not e.get("n") else (FIRE[0], FIRE[2], WHITE)
    a, b = ab
    a = (b[0] + (a[0] - b[0]) * 1.6, b[1] + (a[1] - b[1]) * 1.6)   # si sovrappone alla scia prima
    _sh(fx, kind="incinstreak", a=a, b=b, cols=cols, col=cols[1], life=0.3, lift=0.25)
    if random.random() < 0.5:
        fx._add(ab[0][0], ab[0][1], 0.0, -0.6, 0.3, random.choice((FIRE[1], FIRE[2])), 1)


def fx_incinbounce(fx, e, col):
    """Rimbalzo: le corde si tendono contro il muro e lo rilanciano."""
    c, d = e.get("c"), e.get("dir")
    if c is None or d is None:
        return
    back = (c[0] - d[0] * 0.3, c[1] - d[1] * 0.3)   # le corde stanno dal lato del muro
    _sh(fx, kind="incinropes", c=back, ang=math.atan2(d[1], d[0]), L=0.9, b=0.45,
        col=ROPE[1], life=0.7)
    _bits(fx, (c[0], c[1] - 0.3), 6, (FIRE[2], WHITE), speed=1.8, life=(0.15, 0.3))
    if e.get("cdr"):   # Slancio: lampo azzurro della ricarica
        _sh(fx, kind="ring", c=c, r0=0.2, r1=0.8, col=(140, 210, 255), life=0.3, wd=0.08)


def fx_incinslam(fx, e, col):
    """Schianto contro il muro: stella d'impatto, crepe, sassi e scossa."""
    c = e.get("c")
    if c is None:
        return
    big = bool(e.get("big"))
    top = (c[0], c[1] - 0.4)
    _sh(fx, kind="impactstar", c=top, r=0.9 if big else 0.7, n=8, rot=random.uniform(0, 1),
        cols=FIGHT, col=FIGHT[1], life=0.3)
    _sh(fx, kind="groundcrack", c=c, r=1.0 if big else 0.8, n=6, seed=random.randint(0, 9999),
        col=FIGHT[0], life=0.9)
    for _ in range(6 if big else 4):
        an = random.uniform(0, math.tau)
        _sh(fx, kind="pebble", c=c, v=(math.cos(an) * 1.0, math.sin(an) * 0.6), h=0.5,
            col=(130, 110, 90), life=0.5)
    _bits(fx, top, 8, (FIGHT[2], WHITE, FIRE[1]), speed=2.6, life=(0.15, 0.35))
    fx.shake_until_ms = max(getattr(fx, "shake_until_ms", 0),
                            pygame.time.get_ticks() + (260 if big else 160))


def fx_incingrabbed(fx, e, col):
    """Il nemico viene afferrato durante la corsa."""
    c = e.get("c")
    if c is None:
        return
    _sh(fx, kind="impactstar", c=(c[0], c[1] - 0.35), r=0.35, n=5, rot=random.uniform(0, 1),
        cols=HEEL, col=HEEL[1], life=0.18)


def fx_incinempower(fx, e, col):
    """Colpo potenziato dal rimbalzo: esplosione di brace + stordimento."""
    c = e.get("c")
    if c is None:
        return
    top = (c[0], c[1] - 0.4)
    _sh(fx, kind="impactstar", c=top, r=0.5, n=7, rot=random.uniform(0, 1), cols=FIRE,
        col=FIRE[1], life=0.25)
    _tongues(fx, c, 3, 0.35, h=0.4, w=0.22)


def fx_incinintim(fx, e, col):
    """Prepotenza: onda d'urto scura che parte da Incineroar (raggio 4)."""
    c = e.get("c")
    if c is None:
        return
    r = e.get("radius", 4.0)
    _sh(fx, kind="groundring", c=c, r0=0.4, r1=r, cols=(DARK[0], DARK[1], HEEL[2]), w=0.06,
        speed=3.0, col=DARK[1], life=0.45)
    for k in range(5):   # fiammate scure attorno a Incineroar
        an = k * math.tau / 5
        _sh(fx, kind="flametongue", c=(c[0] + math.cos(an) * 0.7, c[1] + math.sin(an) * 0.4),
            v=(0.0, -0.6), h=0.5, w=0.26, ph=k, cols=(DARK[0], HEEL[1], FIRE[2]),
            col=HEEL[1], life=0.4)


def fx_incinintimhit(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    _bits(fx, (c[0], c[1] - 0.6), 4, (DARK[2], (140, 160, 230)), speed=1.0, life=(0.2, 0.4))


def fx_incinlariat(fx, e, col):
    """Darkest Lariat: parte la rotazione (lampo scuro + fiamme)."""
    c = e.get("c")
    if c is None:
        return
    _sh(fx, kind="incinspin", c=c, r=e.get("radius", 2.5), rot=0.0, col=HEEL[1], life=0.4)
    _tongues(fx, c, 6, 1.0, h=0.5, w=0.28, cols=(DARK[0], HEEL[1], FIRE[2]))


def fx_incinlariattick(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    _sh(fx, kind="incinspin", c=c, r=e.get("radius", 2.5), rot=random.uniform(0, math.tau),
        col=HEEL[1], life=0.35)


def fx_incingrab(fx, e, col):
    c = e.get("c") or e.get("b")
    if c is not None:
        _bits(fx, c, 4, (HEEL[1], FIGHT[2]), speed=1.2)


def fx_incingrabhold(fx, e, col):
    """Presa del Campione: le braccia si chiudono sul bersaglio."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for sg in (1, -1):
        _sh(fx, kind="scyblade", c=(b[0], b[1]), ang=ang + math.pi + sg * 1.4, half=0.7, r=0.55,
            w=0.2, side=sg, cols=HEEL, life=0.3)
    _sh(fx, kind="impactstar", c=(b[0], b[1] - 0.35), r=0.45, n=6, rot=random.uniform(0, 1),
        cols=FIGHT, col=FIGHT[1], life=0.22, wait=0.1)


def fx_incinthrown(fx, e, col):
    """Il nemico scagliato: scia rossa (sollevata come lui)."""
    ab = _ab(e)
    if ab is None:
        return
    z = float(e.get("z", 0.0))
    _sh(fx, kind="incinstreak", a=ab[0], b=ab[1], cols=(HEEL[0], HEEL[1], HEEL[2]),
        col=HEEL[1], life=0.22, lift=0.3 + z)


def fx_incinland(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    _sh(fx, kind="groundring", c=c, r0=0.2, r1=1.0, col=(150, 120, 90), life=0.35)
    for _ in range(3):
        an = random.uniform(0, math.tau)
        _sh(fx, kind="pebble", c=c, v=(math.cos(an) * 0.6, math.sin(an) * 0.4), h=0.35,
            col=(130, 110, 90), life=0.4)


STYLES = {
    "incinclaw": fx_incinclaw, "incinpunch": fx_incinpunch, "incinkick": fx_incinkick,
    "incinfang": fx_incinfang, "incincross": fx_incincross, "incinbully": fx_incinbully,
    "incinbulkup": fx_incinbulkup, "incintaunt": fx_incintaunt, "incinrun": fx_incinrun,
    "incinropes": fx_incinrun, "incinbounce": fx_incinbounce, "incinslam": fx_incinslam,
    "incingrabbed": fx_incingrabbed, "incinempower": fx_incinempower,
    "incinintim": fx_incinintim, "incinintimhit": fx_incinintimhit,
    "incinlariat": fx_incinlariat, "incinlariattick": fx_incinlariattick,
    "incingrab": fx_incingrab, "incingrabhold": fx_incingrabhold,
    "incinthrown": fx_incinthrown, "incinland": fx_incinland,
}


# --- sulle unità ------------------------------------------------------------------------

def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Darkest Lariat (braccia che girano + fiamme scure), pugni accesi dal
    rimbalzo, frecce dell'Attacco (Bullo su, Prepotenza giù: visibili a tutti)."""
    r = int(getattr(u, "radius", 0.5) * ts)
    if getattr(u, "incin_lariat_until", -1.0) > now:
        ang = now * 14.0
        cy = gy - r * 0.8
        # anello d'ombra a terra
        rect = pygame.Rect(gx - r - 6, gy - (r + 6) // 3, (r + 6) * 2, (r + 6) * 2 // 3)
        pygame.draw.ellipse(surface, DARK[1], rect, 2)
        for sg in (0, math.pi):   # due braccia tese che girano (prospettiva)
            an = ang + sg
            ex = gx + math.cos(an) * (r + 8)
            ey = cy + math.sin(an) * (r + 8) * 0.4
            pygame.draw.line(surface, DARK[0], (gx, cy), (ex, ey), 5)
            pygame.draw.line(surface, HEEL[1], (gx, cy), (ex, ey), 3)
            draw_flame(surface, ex, ey + 2, 9, 7, 255, (DARK[0], HEEL[1], FIRE[2]))
    if getattr(u, "incin_rope_until", -1.0) > now:
        ph = (now * 6.0) % 1.0
        for sg in (-1, 1):   # pugni accesi
            x = gx + sg * (r + 3)
            y = gy - r * 0.7
            draw_flame(surface, x, y, 8 + 3 * math.sin(now * 12 + sg), 6, 255, FIRE)
        pygame.draw.circle(surface, FIRE[2], (gx, int(gy - r * 2 - 4 - ph * 3)), 1)
    up = getattr(u, "incin_bully_until", -1.0) > now
    down = getattr(u, "incin_intim_until", -1.0) > now
    if up or down:
        x = gx + r + 6
        y = gy - r * 2 + 2
        if up:
            draw_arrow(surface, x, y + int(math.sin(now * 6) * 1), True, (240, 70, 60))
            x += 8
        if down:
            draw_arrow(surface, x, y + int(math.sin(now * 6 + 1) * 1), False, (130, 150, 240))


# --- interfaccia ---------------------------------------------------------------------------

def _belt_icon(surface, cx, cy, s, lit):
    """Cintura di fuoco di Incineroar: fascia scura con la fibbia d'oro."""
    w, h = int(s * 2.2), max(4, int(s * 0.7))
    band = pygame.Rect(int(cx - w / 2), int(cy - h / 2), w, h)
    pygame.draw.rect(surface, (20, 14, 14), band.inflate(2, 2))
    pygame.draw.rect(surface, HEEL[1] if lit else (90, 40, 40), band)
    pygame.draw.line(surface, HEEL[2] if lit else (130, 80, 80), band.topleft,
                     (band.right - 1, band.top), 1)
    buckle = pygame.Rect(0, 0, int(s * 0.8), int(h + 4))
    buckle.center = (int(cx), int(cy))
    pygame.draw.rect(surface, (40, 30, 10), buckle.inflate(2, 2))
    pygame.draw.rect(surface, GOLD if lit else (140, 120, 70), buckle)
    pygame.draw.rect(surface, (40, 30, 10), buckle.inflate(-4, -4))
    if lit:
        for k in (-1, 1):
            draw_flame(surface, cx + k * s * 0.6, band.top, s * 0.7, s * 0.4, 255, FIRE)


def draw_hud(surface, font, p, bx, y0, bh, now):
    """Passiva della linea: cintura di fuoco (accesa = Prepotenza pronta),
    barra del tempo di calma (5 s), e con Incineroar 3 tacche di Cattivo del
    Ring (nemici entro 5 tile)."""
    pid = getattr(p, "passive_id", "")
    box = pygame.Rect(bx, y0, bh, bh)
    pygame.draw.rect(surface, (30, 22, 22), box)
    calm = now - float(getattr(p, "incin_calm_at", -1e9))
    frac = max(0.0, min(1.0, calm / 5.0))
    ready = frac >= 1.0
    _belt_icon(surface, box.centerx, box.centery + 2, bh * 0.3, ready)
    frame = GOLD if ready else HEEL[1]
    pygame.draw.rect(surface, frame, box, 2)
    # barra della calma sotto l'icona
    bar = pygame.Rect(box.x + 3, box.bottom - 6, box.w - 6, 3)
    pygame.draw.rect(surface, (10, 8, 8), bar.inflate(2, 2))
    pygame.draw.rect(surface, GOLD if ready else (150, 110, 60),
                     pygame.Rect(bar.x, bar.y, int(bar.w * frac), bar.h))
    label = "Prepotenza pronta" if (ready and pid == "prepotenza") else PASSIVE_NAMES.get(pid, "")
    n = int(getattr(p, "incin_ring_n", 0)) if pid == "cattivodelring" else 0
    if n:
        label += f" +{5 * n}%"
    surface.blit(font.render(label, True, frame), (bx - 4, y0 - 18))
    if pid == "cattivodelring":
        x = box.right + 4
        for k in range(3):
            y = y0 + 4 + k * max(7, (bh - 8) // 3)
            r = pygame.Rect(x, y, 7, 7)
            pygame.draw.rect(surface, (12, 8, 8), r)
            pygame.draw.rect(surface, HEEL[2] if (2 - k) < n else (60, 40, 40), r.inflate(-2, -2))


def _cone_pts(S, o, d, rng, half, n=12):
    base = math.atan2(d[1], d[0])
    pts = [S(o[0], o[1])]
    for i in range(n + 1):
        an = base - half + 2 * half * i / n
        pts.append(S(o[0] + math.cos(an) * rng, o[1] + math.sin(an) * rng))
    return pts


def draw_aim(surface, S, ts, ox, oy, nx, ny, dist, move) -> bool:
    """Mirino delle mosse della linea. Ritorna False se la forma non è sua."""
    shape = move.shape
    rng = move.range
    if shape in ("incinkick", "incinbully"):
        col = FIGHT[2] if shape == "incinkick" else HEEL[2]
        pygame.draw.lines(surface, col, True,
                          _cone_pts(S, (ox, oy), (nx, ny), rng, math.radians(move.angle)), 1)
        return True
    if shape == "incinfang":
        cx, cy = S(ox + nx * min(rng, 1.3), oy + ny * min(rng, 1.3))
        R = int(move.radius * ts)
        pygame.draw.circle(surface, FIRE[2], (int(cx), int(cy)), R, 1)
        pygame.draw.line(surface, FIRE[1], S(ox, oy), (cx, cy), 1)
        return True
    if shape == "incincross":
        c = float(move.effects.get("center", 1.25))
        arm = float(move.effects.get("arm", 1.05))
        cx, cy = ox + nx * c, oy + ny * c
        base = math.atan2(ny, nx)
        for sg in (1, -1):
            an = base + sg * math.pi / 4
            ux, uy = math.cos(an) * arm, math.sin(an) * arm
            pygame.draw.line(surface, FIGHT[0], S(cx - ux, cy - uy), S(cx + ux, cy + uy), 5)
            pygame.draw.line(surface, FIGHT[2], S(cx - ux, cy - uy), S(cx + ux, cy + uy), 1)
        return True
    if shape == "incinropes":
        ex, ey = ox + nx * rng, oy + ny * rng
        w = move.radius
        px, py = -ny * w, nx * w
        for sg in (1, -1):
            pygame.draw.line(surface, FIRE[1], S(ox + px * sg, oy + py * sg),
                             S(ex + px * sg, ey + py * sg), 1)
        pygame.draw.line(surface, WHITE, S(ox, oy), S(ex, ey), 1)
        # punta: corde del ring (il rimbalzo)
        tx, ty = S(ex, ey)
        draw_ropes(surface, tx, ty, math.atan2(ny, nx), 0.55 * ts, 0, 200, ts * 0.6)
        n = int(move.effects.get("bounces", 1))
        for k in range(n):   # frecce del ritorno
            bx, by = S(ex - nx * (1.0 + 0.6 * k) + px * 1.8, ey - ny * (1.0 + 0.6 * k) + py * 1.8)
            l = S(ex - nx * (0.6 + 0.6 * k) + px * 2.3, ey - ny * (0.6 + 0.6 * k) + py * 2.3)
            r = S(ex - nx * (0.6 + 0.6 * k) + px * 1.3, ey - ny * (0.6 + 0.6 * k) + py * 1.3)
            pygame.draw.lines(surface, FIRE[2], False, [l, (bx, by), r], 1)
        return True
    if shape == "incinlariat":
        cx, cy = S(ox, oy)
        R = int(move.radius * ts)
        pygame.draw.circle(surface, HEEL[2], (int(cx), int(cy)), R, 1)
        return True
    if shape == "incingrab":
        cx, cy = S(ox, oy)
        g = float(move.effects.get("grab_range", 2.0))
        pygame.draw.circle(surface, HEEL[2], (int(cx), int(cy)), int(g * ts), 1)
        ex, ey = ox + nx * (g + rng), oy + ny * (g + rng)
        pygame.draw.line(surface, FIGHT[1], S(ox + nx * g, oy + ny * g), S(ex, ey), 2)
        tip = S(ex, ey)
        l = S(ex - nx * 0.5 - ny * 0.35, ey - ny * 0.5 + nx * 0.35)
        r = S(ex - nx * 0.5 + ny * 0.35, ey - ny * 0.5 - nx * 0.35)
        pygame.draw.polygon(surface, FIGHT[1], [tip, l, r])
        return True
    return False
