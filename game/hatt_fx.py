"""Grafica della linea Hatenna > Hattrem > Hatterene: effetti istantanei
(handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (increspatura psichica, raggio di Psicoraggio a fili
intrecciati, note di Incantavoce, cuoricino di Assorbibacio, onda con le
ciocche della Strega della Foresta), disegni persistenti letti dallo stato del
Match a ogni frame (area di Confusione in arrivo, sfera di Forza Lunare in
volo, Distortozona visibile a tutti, carica della Strega), sulle unità
(segno di rabbia degli AGITATI, brillantini di Magipolvere) e mirino.

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

PSY = (236, 104, 190)          # Psico (rosa-magenta)
PSY_HI = (255, 214, 240)
PSY_DK = (92, 28, 88)
SHOCK = (150, 120, 255)        # Psicoshock: viola-blu (colpisce il "fisico")
SHOCK_HI = (226, 218, 255)
SHOCK_DK = (40, 30, 110)
FAIRY = (255, 160, 210)        # Folletto
FAIRY_HI = (255, 242, 250)
FAIRY_DK = (128, 46, 100)
MOON = (255, 206, 236)         # Forza Lunare
MOON_HI = (255, 255, 255)
MOON_DK = (110, 54, 120)
MFIRE = (255, 110, 120)        # Magifiamma: fiamma magenta-arancio
MFIRE_HI = (255, 226, 150)
MFIRE_DK = (110, 24, 70)
TRICK = (196, 132, 255)        # Distortozona
TRICK_HI = (240, 222, 255)
TRICK_DK = (52, 26, 96)
ANGER = (238, 52, 64)          # agitato
ANGER_DK = (80, 10, 20)
HEAL = (255, 120, 170)

HATT_DEX = (856, 857, 858)


def _al(f, k=2.0):
    return int(255 * max(0.0, min(1.0, f * k)))


def is_hatt(u) -> bool:
    return getattr(u, "dex", 0) in HATT_DEX


def _ellipse_pts(cx, cy, r, n=40, wob=0.0, phase=0.0, k=5):
    """Contorno schiacciato in prospettiva (y × 0,5) con un'onda di `k` lobi."""
    pts = []
    for i in range(n):
        a = i / n * math.tau
        rr = r * (1.0 + wob * math.sin(a * k + phase))
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.5))
    return pts


def _heart(surface, x, y, s, col, dark):
    """Cuoricino pixel art (s = mezza larghezza)."""
    pts = [(x, y + s), (x - s, y), (x - s, y - s // 2), (x - s // 2, y - s),
           (x, y - s // 2), (x + s // 2, y - s), (x + s, y - s // 2), (x + s, y)]
    pygame.draw.polygon(surface, dark, [(px + (1 if px > x else -1 if px < x else 0), py)
                                        for px, py in pts])
    pygame.draw.polygon(surface, col, pts)


def _note(surface, x, y, s, col, dark, al=255):
    """Nota musicale (croma): testa ovale + gambo + bandierina."""
    x, y = int(x), int(y)
    head = pygame.Rect(x - s, y - s // 2, s * 2, s + 1)
    pygame.draw.ellipse(surface, (*dark, al), head.inflate(2, 2))
    pygame.draw.ellipse(surface, (*col, al), head)
    pygame.draw.line(surface, (*dark, al), (x + s, y), (x + s, y - s * 3), 3)
    pygame.draw.line(surface, (*col, al), (x + s, y), (x + s, y - s * 3), 1)
    pygame.draw.line(surface, (*col, al), (x + s, y - s * 3), (x + s * 2, y - s * 2), 2)


# --- forme per FXSystem._draw_shapes --------------------------------------------

SHAPES = ("psywave", "psyband", "note", "heartfly", "witchring", "moonarc")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "psywave":
        # Increspatura psichica: anello schiacciato che si allarga ondeggiando
        # (5 lobi che ruotano), a tre strati.
        cx, cy = S(*s["c"])
        r = (s["r0"] + (s["r1"] - s["r0"]) * min(1.0, t * s.get("speed", 1.6))) * ts
        cols = s.get("cols", (PSY_DK, PSY, PSY_HI))
        al = _al(f, 2.2)
        pts = _ellipse_pts(cx, cy, r, n=max(24, int(r / 2)), wob=s.get("wob", 0.06),
                           phase=t * 9.0 + s.get("ph", 0.0))
        if s.get("fill"):
            pygame.draw.polygon(overlay, (*cols[0], al // 3), pts)
        pygame.draw.polygon(overlay, (*cols[0], al), pts, 5)
        pygame.draw.polygon(overlay, (*cols[1], al), pts, 3)
        pygame.draw.lines(overlay, (*cols[2], al), False, pts[len(pts) // 2:], 1)
    elif kind == "psyband":
        # Psicoraggio: tre fili sinusoidali intrecciati (rosa, viola, azzurro)
        # attorno a un nucleo chiaro; la luce corre lungo il raggio.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        L = math.hypot(bx - ax, by - ay)
        if L < 2:
            return
        ux, uy = (bx - ax) / L, (by - ay) / L
        px, py = -uy, ux
        w = s.get("w", 0.5) * ts * (0.5 + 0.5 * f)
        al = _al(f, 2.0)
        pygame.draw.line(overlay, (*PSY_DK, al // 2), (ax, ay), (bx, by), max(3, int(w * 1.4)))
        pygame.draw.line(overlay, (*PSY, al), (ax, ay), (bx, by), max(2, int(w * 0.8)))
        n = max(8, int(L / 3))
        for k, col in enumerate(((255, 150, 215), (190, 150, 255), (150, 225, 255))):
            pts = []
            for i in range(n + 1):
                d = L * i / n
                o = math.sin(d / (1.8 * ts) * math.tau - t * 18.0 + k * 2.1) * w * 0.45
                pts.append((ax + ux * d + px * o, ay + uy * d + py * o))
            pygame.draw.lines(overlay, (*col, al), False, pts, 1)
        pygame.draw.line(overlay, (*PSY_HI, al), (ax, ay), (bx, by), 1)
        for k in range(3):   # anelli che scorrono lungo il raggio
            d = ((t * 2.2 + k / 3) % 1.0) * L
            x, y = ax + ux * d, ay + uy * d
            rr = max(2, int(w))
            pygame.draw.ellipse(overlay, (*PSY_HI, al),
                                pygame.Rect(int(x - rr * 0.5), int(y - rr), rr, rr * 2), 1)
    elif kind == "note":
        # Nota che vola via dal centro (Incantavoce) e svanisce.
        cx, cy = S(*s["c"])
        d = (s.get("d0", 0.3) + s.get("dist", 2.5) * min(1.0, t * 1.4)) * ts
        an = s.get("ang", 0.0)
        x = cx + math.cos(an) * d
        y = cy + math.sin(an) * d * 0.5 - math.sin(t * math.pi) * 0.4 * ts
        cols = s.get("cols", (FAIRY_DK, FAIRY, FAIRY_HI))
        _note(overlay, x, y, max(3, int(0.15 * ts)), cols[2], cols[0], _al(f, 2.5))
    elif kind == "heartfly":
        # Cuoricino che vola dal bersaglio a chi cura (Assorbibacio).
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.85)
        x = ax + (bx - ax) * u
        y = ay + (by - ay) * u - math.sin(u * math.pi) * 0.8 * ts
        g = pygame.Surface((14, 14), pygame.SRCALPHA)
        _heart(g, 7, 7, 4, (*HEAL, _al(f, 3)), (*FAIRY_DK, _al(f, 3)))
        overlay.blit(g, (int(x) - 7, int(y) - 7))
    elif kind == "witchring":
        # Strega della Foresta: onda larghissima con le "ciocche" di Hatterene
        # (tentacoli a uncino) che puntano verso l'esterno sul bordo.
        cx, cy = S(*s["c"])
        r = (s.get("r0", 0.5) + (s["r"] - s.get("r0", 0.5)) * min(1.0, t * 2.4)) * ts
        al = _al(f * f, 2.2)
        pts = _ellipse_pts(cx, cy, r, n=72, wob=0.03, phase=t * 6.0, k=9)
        pygame.draw.polygon(overlay, (*PSY, al // 6), pts)
        pygame.draw.polygon(overlay, (*PSY_DK, al // 2), pts, 6)
        pygame.draw.polygon(overlay, (*PSY, al), pts, 3)
        pygame.draw.polygon(overlay, (*PSY_HI, al), pts, 1)
        n = 10
        for i in range(n):
            a0 = i / n * math.tau + 0.2
            x0, y0 = cx + math.cos(a0) * r, cy + math.sin(a0) * r * 0.5
            hook = []
            for j in range(6):   # ciocca che si arriccia
                uu = j / 5
                aa = a0 + 0.35 * uu * uu
                rr = r + 0.6 * ts * uu
                hook.append((cx + math.cos(aa) * rr, cy + math.sin(aa) * rr * 0.5 - 0.25 * ts * uu))
            pygame.draw.lines(overlay, (*PSY_DK, al), False, hook, 4)
            pygame.draw.lines(overlay, (*PSY, al), False, hook, 2)
            pygame.draw.circle(overlay, (*PSY_HI, al), (int(hook[-1][0]), int(hook[-1][1])), 1)
    elif kind == "moonarc":
        # Falce di luna che si apre sul punto d'impatto (Forza Lunare).
        cx, cy = S(*s["c"])
        R = s.get("r", 0.6) * ts * (0.6 + 0.6 * min(1.0, t * 3))
        al = _al(f, 2.5)
        cols = s.get("cols", (MOON_DK, MOON, MOON_HI))
        g = pygame.Surface((int(R * 2 + 6), int(R * 2 + 6)), pygame.SRCALPHA)
        o = int(R + 3)
        pygame.draw.circle(g, (*cols[0], al), (o, o), int(R) + 1)
        pygame.draw.circle(g, (*cols[1], al), (o, o), int(R))
        pygame.draw.circle(g, (*cols[2], al), (o - int(R * 0.3), o - int(R * 0.3)), max(1, int(R * 0.35)))
        pygame.draw.circle(g, (0, 0, 0, 0), (o + int(R * 0.45), o - int(R * 0.25)), int(R * 0.85))
        overlay.blit(g, (int(cx) - o, int(cy - 0.4 * ts) - o))


# --- handler degli eventi (FXSystem._FX_STYLES) --------------------------------


def _ab(e):
    a, b = e.get("a"), e.get("b")
    return (a, b) if a is not None and b is not None else None


def _bits(fx, c, n, cols, speed=2.0, life=(0.2, 0.4), size=1, up=0.0, spread=0.0):
    for _ in range(n):
        a = random.uniform(0, math.tau)
        v = random.uniform(0.4, 1.0) * speed
        x = c[0] + random.uniform(-spread, spread)
        y = c[1] + random.uniform(-spread, spread) * 0.5
        fx._add(x, y, math.cos(a) * v, math.sin(a) * v * 0.5 - up, random.uniform(*life),
                random.choice(cols), size)


def fx_psyshot(fx, e, col):
    """Attacco base: sferetta psichica rosa con un anellino attorno."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    a = (a[0], a[1] - 0.45)
    b = (b[0], b[1] - 0.3)
    fx._shape(kind="energy", a=a, b=b, col=PSY, life=0.24, sz=0.13)
    fx._shape(kind="psywave", c=b, r0=0.1, r1=0.45, wob=0.12, col=PSY, life=0.2, wait=0.17)


def fx_psycast(fx, e, col):
    """Confusione lanciata: piccolo lampo sul punto (il resto è persistente)."""
    c = e.get("c")
    if c is not None:
        fx._shape(kind="psywave", c=c, r0=0.15, r1=0.6, wob=0.1, col=PSY, life=0.22)


def fx_psyburst(fx, e, col):
    """Confusione scatta: due increspature che si allargano + spirali di luce
    (Psicoshock: viola-blu con schegge squadrate)."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 1.7))
    cols = (SHOCK_DK, SHOCK, SHOCK_HI) if e.get("shock") else (PSY_DK, PSY, PSY_HI)
    fx._shape(kind="psywave", c=c, r0=r * 0.3, r1=r, wob=0.08, fill=True, cols=cols,
              col=cols[1], life=0.45)
    fx._shape(kind="psywave", c=c, r0=0.1, r1=r * 0.6, wob=0.14, cols=cols, col=cols[1],
              life=0.35, ph=1.7)
    for k in range(4):   # stelline psichiche dentro l'area
        an = k / 4 * math.tau + random.uniform(-0.4, 0.4)
        fx._shape(kind="twinkle", c=(c[0] + math.cos(an) * r * 0.5, c[1] + math.sin(an) * r * 0.25 - 0.3),
                  r=0.28, rot=an, cols=cols, col=cols[1], life=0.4, wait=0.03 * k)
    _bits(fx, c, 18, cols[1:], speed=2.4, size=2 if e.get("shock") else 1, spread=r * 0.5)


def fx_psybeam(fx, e, col):
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    a = (a[0], a[1] - 0.4)
    b = (b[0], b[1] - 0.4)
    fx._shape(kind="psyband", a=a, b=b, w=float(e.get("radius", 0.55)), col=PSY, life=0.45)
    fx._shape(kind="flash", c=a, r=0.35, col=PSY_HI, life=0.1)
    fx._shape(kind="psywave", c=b, r0=0.2, r1=0.8, wob=0.1, col=PSY, life=0.3)


def _voice(fx, e, cols, notes=True):
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 3.0))
    fx._shape(kind="psywave", c=c, r0=0.4, r1=r, wob=0.04, cols=cols, col=cols[1],
              life=0.4, speed=2.4)
    fx._shape(kind="psywave", c=c, r0=0.2, r1=r * 0.7, wob=0.05, cols=cols, col=cols[1],
              life=0.35, speed=2.4, ph=2.0, wait=0.06)
    if notes:
        for i in range(7):
            fx._shape(kind="note", c=(c[0], c[1] - 0.4), ang=i / 7 * math.tau + random.uniform(-0.2, 0.2),
                      d0=0.8, dist=r * 0.8, cols=cols, col=cols[1], life=0.55, wait=0.02 * i)


def fx_hattvoice(fx, e, col):
    """Incantavoce: onda rosa con note che volano via."""
    _voice(fx, e, (FAIRY_DK, FAIRY, FAIRY_HI))


def fx_magicpowder(fx, e, col):
    """Magipolvere: onda viola e nuvola di brillantini."""
    c = e.get("c")
    if c is None:
        return
    _voice(fx, e, (PSY_DK, (210, 140, 255), PSY_HI), notes=False)
    r = float(e.get("radius", 3.0))
    _bits(fx, c, 40, ((220, 170, 255), PSY_HI, (255, 240, 160)), speed=1.0,
          life=(0.5, 0.9), up=0.5, spread=r * 0.7)
    for k in range(6):
        an = k / 6 * math.tau
        fx._shape(kind="twinkle", c=(c[0] + math.cos(an) * r * 0.6, c[1] + math.sin(an) * r * 0.3),
                  r=0.25, rot=an, cols=(PSY_DK, (220, 170, 255), PSY_HI), col=PSY,
                  life=0.5, wait=0.04 * k)


def fx_drainingkiss(fx, e, col):
    """Assorbibacio: onda rosa + cuori."""
    _voice(fx, e, (FAIRY_DK, HEAL, FAIRY_HI))


def fx_kissheal(fx, e, col):
    """Assorbibacio cura: cuoricini dal colpito a Hatterene."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    for k in range(2):
        fx._shape(kind="heartfly", a=(a[0], a[1] - 0.4), b=(b[0], b[1] - 0.6), col=HEAL,
                  life=0.6, wait=0.1 + 0.08 * k)


def fx_voicepush(fx, e, col):
    """Respinta di Incantavoce: due scie d'aria rosa dietro al respinto."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L < 0.2:
        return
    nx, ny = -dy / L * 0.25, dx / L * 0.25
    for s in (-1, 1):
        fx._shape(kind="windline", a=(a[0] + nx * s, a[1] + ny * s - 0.4),
                  b=(b[0] + nx * s, b[1] + ny * s - 0.4), col=FAIRY_HI, life=0.3)
    fx._dust(b, 0.4, n=6)


def fx_moonhit(fx, e, col):
    """Forza Lunare a segno: falce di luna, lampo e brillantini (Magifiamma:
    vampata magenta; Forza Lunare +: esplosione larga)."""
    c = e.get("c")
    if c is None:
        return
    fire = e.get("fire")
    cols = (MFIRE_DK, MFIRE, MFIRE_HI) if fire else (MOON_DK, MOON, MOON_HI)
    r = float(e.get("radius", 0.5))
    if e.get("burst"):
        fx._shape(kind="psywave", c=c, r0=0.3, r1=r, wob=0.05, fill=True, cols=cols,
                  col=cols[1], life=0.45, speed=2.0)
        for k in range(5):
            an = k / 5 * math.tau
            fx._shape(kind="twinkle", c=(c[0] + math.cos(an) * r * 0.6,
                                         c[1] + math.sin(an) * r * 0.3 - 0.3),
                      r=0.3, rot=an, cols=cols, col=cols[1], life=0.45, wait=0.03 * k)
    if not fire:
        fx._shape(kind="moonarc", c=c, r=0.55, cols=cols, col=cols[1], life=0.4)
    fx._shape(kind="flash", c=(c[0], c[1] - 0.3), r=0.5, col=cols[2], life=0.12)
    fx._shape(kind="ring", c=(c[0], c[1] - 0.3), r0=0.2, r1=0.9, col=cols[1], life=0.3, wd=0.06)
    _bits(fx, (c[0], c[1] - 0.3), 16, cols[1:], speed=2.6, up=0.8 if fire else 0.0)


def fx_moonfizzle(fx, e, col):
    c = e.get("c")
    if c is not None:
        _bits(fx, c, 8, (MOON, MOON_HI), speed=1.2)


def fx_trickroom(fx, e, col):
    """Distortozona aperta: lampo viola sul centro (l'area è persistente)."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 5.0))
    fx._shape(kind="psywave", c=c, r0=0.2, r1=r, wob=0.02, cols=(TRICK_DK, TRICK, TRICK_HI),
              col=TRICK, life=0.5, speed=2.0)
    fx._shape(kind="flash", c=c, r=0.8, col=TRICK_HI, life=0.15)


def fx_witchwave(fx, e, col):
    """Strega della Foresta: onda psichica larghissima con le ciocche."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 7.0))
    fx._shape(kind="witchring", c=c, r=r, r0=0.6, col=PSY, life=0.6)
    fx._shape(kind="psywave", c=c, r0=0.3, r1=r * 0.6, wob=0.08, col=PSY, life=0.4, ph=1.0)
    fx._shape(kind="flash", c=(c[0], c[1] - 0.5), r=0.6, col=PSY, life=0.12)


def fx_witchstun(fx, e, col):
    """Agitato colpito dalla Strega: stelline che girano."""
    c = e.get("c")
    if c is None:
        return
    for k in range(3):
        an = k / 3 * math.tau
        fx._shape(kind="twinkle", c=(c[0] + math.cos(an) * 0.4, c[1] - 1.0 + math.sin(an) * 0.15),
                  r=0.22, rot=an, cols=(PSY_DK, PSY, PSY_HI), col=PSY, life=0.6, wait=0.05 * k)


def fx_agitate(fx, e, col):
    """Un nemico si agita: piccolo scoppio rosso sopra la testa."""
    c = e.get("c")
    if c is None:
        return
    top = (c[0], c[1] - 1.2)
    fx._shape(kind="ring", c=top, r0=0.1, r1=0.45, col=ANGER, life=0.25, wd=0.05)
    _bits(fx, top, 6, (ANGER, (255, 160, 160)), speed=1.6)


STYLES = {
    "psyshot": fx_psyshot, "psycast": fx_psycast, "psyburst": fx_psyburst,
    "psybeam": fx_psybeam, "hattvoice": fx_hattvoice, "magicpowder": fx_magicpowder,
    "drainingkiss": fx_drainingkiss, "kissheal": fx_kissheal, "voicepush": fx_voicepush, "moonhit": fx_moonhit,
    "moonfizzle": fx_moonfizzle, "trickroom": fx_trickroom, "witchwave": fx_witchwave,
    "witchstun": fx_witchstun, "agitate": fx_agitate,
}


# --- disegni persistenti (stato del Match) ---------------------------------------


def _layer(R):
    g = pygame.Surface((R * 2 + 12, R + 12), pygame.SRCALPHA)
    return g, (R + 6, R // 2 + 6)


def draw_mark(surface, camera, z, now):
    """Confusione in arrivo: area che si riempie, spirale psichica che gira
    e cerchio interno che si allarga verso il bordo."""
    ts = config.TILE_SIZE
    c = z["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    span = max(1e-6, z["at"] - z["start"])
    u = max(0.0, min(1.0, (now - z["start"]) / span))
    R = int(z["radius"] * ts)
    shock = z.get("shock")
    dk, md, hi = (SHOCK_DK, SHOCK, SHOCK_HI) if shock else (PSY_DK, PSY, PSY_HI)
    g, o = _layer(R)
    rect = pygame.Rect(o[0] - R, o[1] - R // 2, R * 2, R)
    pygame.draw.ellipse(g, (*dk, int(50 + 70 * u)), rect)
    pygame.draw.ellipse(g, (*md, 230), rect, 2)
    ir = max(2, int(R * u))
    pygame.draw.ellipse(g, (*hi, 210), pygame.Rect(o[0] - ir, o[1] - ir // 2, ir * 2, ir), 1)
    for arm in range(3):   # spirale a tre bracci che gira
        pts = []
        for i in range(10):
            k = i / 9
            an = arm * math.tau / 3 + k * 2.6 + now * 7.0
            rr = R * 0.9 * k
            pts.append((o[0] + math.cos(an) * rr, o[1] + math.sin(an) * rr * 0.5))
        pygame.draw.lines(g, (*md, int(120 + 100 * u)), False, pts, 1)
    surface.blit(g, (cx - o[0], cy - o[1]))


def draw_moon_orb(surface, camera, orb, now):
    """Sfera di Forza Lunare (lenta): globo rosa-bianco con l'ombra di una
    falce, alone che pulsa e scia di brillantini; Magifiamma = palla di fiamma
    magenta."""
    ts = config.TILE_SIZE
    p = orb["pos"]
    d = orb["dir"]
    x, y = camera.world_to_screen(p.x * ts, (p.y - 0.45) * ts)
    fire = orb.get("mtype") == "Fire"
    dk, md, hi = (MFIRE_DK, MFIRE, MFIRE_HI) if fire else (MOON_DK, MOON, MOON_HI)
    R = max(4, int(orb.get("radius", 0.5) * ts * 0.8))
    pulse = 0.5 + 0.5 * math.sin(now * 12.0)
    g = pygame.Surface((R * 8, R * 8), pygame.SRCALPHA)
    o = R * 4
    # scia
    for k in range(1, 6):
        tx = o - d.x * R * 0.9 * k
        ty = o - d.y * R * 0.9 * k
        rr = max(1, int(R * (1.0 - k / 6.5)))
        pygame.draw.circle(g, (*md, int(150 * (1 - k / 6))), (int(tx), int(ty)), rr)
    pygame.draw.circle(g, (*md, int(50 + 40 * pulse)), (o, o), int(R * 1.8))
    pygame.draw.circle(g, (*dk, 255), (o, o), R + 1)
    pygame.draw.circle(g, (*md, 255), (o, o), R)
    if fire:   # lingue di fiamma che salgono
        rnd = random.Random(int(now * 18) + orb.get("caster_id", 0))
        for _ in range(4):
            fxo = rnd.uniform(-R * 0.7, R * 0.7)
            h = rnd.uniform(R * 0.8, R * 1.6)
            pygame.draw.polygon(g, (*md, 230), [(o + fxo - 2, o - R * 0.4), (o + fxo + 2, o - R * 0.4),
                                                (o + fxo + rnd.uniform(-2, 2), o - R * 0.4 - h)])
        pygame.draw.circle(g, (*hi, 255), (o, o + 1), max(1, R // 2))
    else:      # falce di luna: ombra a destra in basso, luce in alto a sinistra
        pygame.draw.circle(g, (*hi, 255), (o - R // 3, o - R // 3), max(1, R // 2))
        pygame.draw.arc(g, (*dk, 255), pygame.Rect(o - R, o - R, R * 2, R * 2),
                        -math.pi * 0.6, math.pi * 0.15, 2)
    rnd = random.Random(int(now * 10) + int(p.x * 13))
    for _ in range(3):   # brillantini dietro
        bx = o - d.x * rnd.uniform(R, R * 4) + rnd.uniform(-R, R)
        by = o - d.y * rnd.uniform(R, R * 4) + rnd.uniform(-R, R)
        pygame.draw.rect(g, (*hi, 220), pygame.Rect(int(bx), int(by), 2, 2))
    surface.blit(g, (x - o, y - o))
    # ombra a terra
    sx, sy = camera.world_to_screen(p.x * ts, p.y * ts)
    sh = pygame.Surface((R * 2, R), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 70), sh.get_rect())
    surface.blit(sh, (sx - R, sy - R // 2))


def draw_trick_room(surface, camera, z, now):
    """Distortozona (visibile a tutti): pavimento a scacchi deformato che
    ondeggia, bordo viola tratteggiato che gira; svanisce negli ultimi istanti."""
    ts = config.TILE_SIZE
    c = z["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    R = int(z["radius"] * ts)
    left = z["end"] - now
    fade = max(0.0, min(1.0, left / 0.6)) * max(0.0, min(1.0, (now - z["start"]) / 0.3))
    if fade <= 0.0:
        return
    g, o = _layer(R)
    # scacchiera deformata (celle di 0,8 tile) dentro l'ellisse
    cell = max(4, int(0.8 * ts))
    sw = math.sin(now * 2.0) * 0.12
    for gy in range(-R // 2, R // 2 + 1, cell // 2):
        for gx in range(-R, R + 1, cell):
            nx, ny = gx / R, gy / (R * 0.5)
            if nx * nx + ny * ny > 1.0:
                continue
            k = ((gx // cell) + (gy // (cell // 2))) & 1
            if not k:
                continue
            tw = sw * (1.0 - nx * nx - ny * ny)   # torsione più forte al centro
            px = o[0] + gx * (1.0 + tw) - gy * tw * 2
            py = o[1] + gy
            pygame.draw.rect(g, (*TRICK, int(62 * fade)),
                             pygame.Rect(int(px), int(py), cell, cell // 2))
    rect = pygame.Rect(o[0] - R, o[1] - R // 2, R * 2, R)
    base = pygame.Surface(g.get_size(), pygame.SRCALPHA)   # fondo sotto la scacchiera
    pygame.draw.ellipse(base, (*TRICK_DK, int(70 * fade)), rect)
    base.blit(g, (0, 0))
    g = base
    pygame.draw.ellipse(g, (*TRICK_DK, int(200 * fade)), rect, 4)
    n = 28
    for i in range(n):   # bordo tratteggiato che gira
        if i % 2:
            continue
        a0 = i / n * math.tau + now * 0.6
        a1 = a0 + math.tau / n
        p0 = (o[0] + math.cos(a0) * R, o[1] + math.sin(a0) * R * 0.5)
        p1 = (o[0] + math.cos(a1) * R, o[1] + math.sin(a1) * R * 0.5)
        pygame.draw.line(g, (*TRICK_HI, int(230 * fade)), p0, p1, 2)
    # tre frecce: chi è lento accelera, chi è veloce frena (simbolo invertito)
    for k in range(3):
        an = k / 3 * math.tau - now * 0.9
        ax, ay = o[0] + math.cos(an) * R * 0.55, o[1] + math.sin(an) * R * 0.27
        tx, ty = -math.sin(an), math.cos(an) * 0.5
        L = 0.5 * ts
        tl = math.hypot(tx, ty) or 1.0
        tx, ty = tx / tl, ty / tl
        hx, hy = ax + tx * L, ay + ty * L
        pygame.draw.line(g, (*TRICK_HI, int(190 * fade)), (ax - tx * L, ay - ty * L), (hx, hy), 2)
        pygame.draw.polygon(g, (*TRICK_HI, int(190 * fade)),
                            [(hx + tx * 4, hy + ty * 4), (hx - ty * 3, hy + tx * 3),
                             (hx + ty * 3, hy - tx * 3)])
    surface.blit(g, (cx - o[0], cy - o[1]))
    # secondi rimasti in alto (piccolo, pixel)
    if left > 0.0:
        bar_w = int(R * 0.6)
        bx, by = cx - bar_w // 2, cy - R // 2 - 6
        pygame.draw.rect(surface, (20, 14, 30), pygame.Rect(bx - 1, by - 1, bar_w + 2, 4))
        pygame.draw.rect(surface, TRICK, pygame.Rect(bx, by, int(bar_w * min(1.0, left / 6.0)), 2))


def draw_witch_charge(surface, camera, w, now):
    """Strega della Foresta in carica: anello che si allarga fino al raggio
    vero e ciocche che si sollevano attorno a Hatterene."""
    ts = config.TILE_SIZE
    c = w["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    span = max(1e-6, w["at"] - w["start"])
    u = max(0.0, min(1.0, (now - w["start"]) / span))
    R = int(w["radius"] * ts)
    g, o = _layer(R)
    rect = pygame.Rect(o[0] - R, o[1] - R // 2, R * 2, R)
    pygame.draw.ellipse(g, (*PSY_DK, int(30 + 50 * u)), rect)
    pygame.draw.ellipse(g, (*PSY, 200), rect, 1)
    ir = max(2, int(R * u))
    pygame.draw.ellipse(g, (*PSY_HI, 230), pygame.Rect(o[0] - ir, o[1] - ir // 2, ir * 2, ir), 2)
    for i in range(6):   # ciocche che si sollevano e si arricciano verso l'esterno
        an = i / 6 * math.tau + 0.4
        side = 1 if math.cos(an) >= 0 else -1
        x0 = o[0] + math.cos(an) * 0.45 * ts
        y0 = o[1] + math.sin(an) * 0.22 * ts - 0.5 * ts
        L = (0.5 + 1.0 * u) * ts
        pts = []
        for k in range(7):
            q = k / 6
            ang = an + side * q * q * 1.6 + math.sin(now * 6 + i) * 0.08
            pts.append((x0 + math.cos(ang) * L * q,
                        y0 + math.sin(ang) * L * q * 0.5 - L * 0.35 * q))
        pygame.draw.lines(g, (*PSY_DK, 230), False, pts, 3)
        pygame.draw.lines(g, (*PSY, 255), False, pts, 1)
        pygame.draw.circle(g, (*PSY_HI, 255), (int(pts[-1][0]), int(pts[-1][1])), 1)
    surface.blit(g, (cx - o[0], cy - o[1]))


# --- sulle unità --------------------------------------------------------------


_ANGER_BMP = (
    ".XX...XX.",
    "X.X...X.X",
    "XX.....XX",
    ".........",
    ".........",
    ".........",
    "XX.....XX",
    "X.X...X.X",
    ".XX...XX.",
)
_anger_cache: dict = {}


def draw_anger(surface, x, y, s=1, col=ANGER, dark=ANGER_DK):
    """Vena di rabbia pixel art (quattro uncini agli angoli, 9x9 px con il
    contorno scuro): icona dello stato AGITATO. `s` = scala intera."""
    key = (s, col, dark)
    img = _anger_cache.get(key)
    if img is None:
        n = len(_ANGER_BMP)
        img = pygame.Surface((n + 2, n + 2), pygame.SRCALPHA)
        on = [(c, r) for r, row in enumerate(_ANGER_BMP) for c, ch in enumerate(row) if ch == "X"]
        for c, r in on:   # contorno = dilatazione di 1 px
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    img.set_at((c + 1 + dx, r + 1 + dy), dark)
        for c, r in on:
            img.set_at((c + 1, r + 1), col)
        for c, r in on[:2]:   # luce in alto a sinistra
            img.set_at((c + 1, r + 1), (255, 170, 170))
        if s > 1:
            img = pygame.transform.scale(img, (img.get_width() * s, img.get_height() * s))
        _anger_cache[key] = img
    surface.blit(img, (int(x) - img.get_width() // 2, int(y) - img.get_height() // 2))


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Sopra lo sprite: segno di rabbia degli AGITATI (sopra i pallini di
    stato, pulsa) e brillantini viola di Magipolvere (tipo Psico). Visibili a
    tutti."""
    r = int(getattr(u, "radius", 0.5) * ts)
    if getattr(u, "agitated_until", -1.0) > now:
        pulse = 1 if (now * 6.0) % 1.0 < 0.5 else 0
        draw_anger(surface, gx, gy - 2 * r - 16 - pulse)
    if getattr(u, "powder_until", -1.0) > now:
        for k in range(3):
            an = now * 2.5 + k / 3 * math.tau
            x = gx + int(math.cos(an) * (r + 3))
            y = gy - r + int(math.sin(an) * r * 0.5)
            tw = (now * 5 + k) % 1.0 < 0.5
            col = (230, 180, 255) if tw else PSY_HI
            pygame.draw.line(surface, PSY_DK, (x - 2, y + 1), (x + 2, y + 1))
            pygame.draw.line(surface, col, (x - 2, y), (x + 2, y))
            pygame.draw.line(surface, col, (x, y - 2), (x, y + 2))


# --- interfaccia ---------------------------------------------------------------


def count_agitated(world, p, now, visible=None) -> int:
    """Nemici agitati entro 10 tile da `p` (per l'icona della passiva); solo
    per la linea Hatenna, altrimenti 0. `visible(e)` filtra quelli visti."""
    if getattr(p, "passive_id", None) != "quiete":
        return 0
    n = 0
    for e in world.pokemons():
        if (e.team != p.team and e.alive and getattr(e, "agitated_until", -1.0) > now
                and e.pos.dist(p.pos) <= 10.0 and (visible is None or visible(e))):
            n += 1
    return n


def draw_hat_icon(surface, cx, cy, s, col=PSY, dark=PSY_DK, hi=PSY_HI):
    """Cappello della linea Hatenna (cupola con la treccia): icona della passiva."""
    dome = pygame.Rect(cx - s, cy - s, s * 2, int(s * 1.6))
    pygame.draw.ellipse(surface, dark, dome.inflate(2, 2))
    pygame.draw.ellipse(surface, col, dome)
    pygame.draw.ellipse(surface, hi, pygame.Rect(cx - s + 2, cy - s + 2, s, s // 2))
    pygame.draw.rect(surface, (30, 14, 40), pygame.Rect(cx - s + 2, cy + s // 4, s * 2 - 4, s // 2))
    tail = [(cx + s - 1, cy - s // 3), (cx + s + s // 2, cy + s // 3), (cx + s + 2, cy + s)]
    pygame.draw.lines(surface, dark, False, tail, 4)
    pygame.draw.lines(surface, col, False, tail, 2)


# --- mirino ---------------------------------------------------------------------


def draw_aim(surface, S, ts, ox, oy, nx, ny, dist, move) -> bool:
    """Mirino delle mosse della linea. Ritorna False se la forma non è sua."""
    shape = move.shape
    col = {"Fairy": FAIRY, "Fire": MFIRE}.get(move.type, PSY)
    rng = move.range
    if shape in ("psyburst", "trickroom"):
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        d = min(dist, rng)
        cx, cy = S(ox + nx * d, oy + ny * d)
        c2 = TRICK if shape == "trickroom" else col
        pygame.draw.circle(surface, c2, (cx, cy), int(move.radius * ts), 2)
        pygame.draw.circle(surface, (255, 255, 255), (cx, cy), max(3, int(0.25 * ts)), 1)
        return True
    if shape in ("psybeam", "moonorb"):
        ex, ey = ox + nx * rng, oy + ny * rng
        w = move.radius
        px, py = -ny * w, nx * w
        for sg in (1, -1):
            pygame.draw.line(surface, col, S(ox + px * sg, oy + py * sg),
                             S(ex + px * sg, ey + py * sg), 1)
        pygame.draw.line(surface, (255, 255, 255), S(ox, oy), S(ex, ey), 1)
        br = float(move.effects.get("burst", 0.0))
        if br > 0.0:   # Forza Lunare +: area d'esplosione in fondo
            pygame.draw.circle(surface, col, S(ex, ey), int(br * ts), 1)
        return True
    if shape in ("hattvoice", "witchwave"):
        pygame.draw.circle(surface, col, S(ox, oy), int(move.radius * ts), 2)
        push = float(move.effects.get("push", 0.0))
        if push > 0.0:   # frecce della respinta
            for k in range(6):
                an = k / 6 * math.tau
                r0 = move.radius * 0.6
                a = (ox + math.cos(an) * r0, oy + math.sin(an) * r0)
                b = (ox + math.cos(an) * (r0 + 0.9), oy + math.sin(an) * (r0 + 0.9))
                pygame.draw.line(surface, (255, 255, 255), S(*a), S(*b), 1)
        return True
    return False
