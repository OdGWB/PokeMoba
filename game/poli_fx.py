"""Grafica della linea Poliwag > Poliwhirl > Poliwrath / Politoad: effetti
istantanei (handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (bolla a spirale, bolla ad arco col mirino, pioggia,
spirale della pancia, Acquanello, fango, mulinello, arco del lancio, mirino
del Rimbalzo, Ultimocanto col conto alla rovescia, specchio di Ripeti), il
Bollaraggio in volo (world_fx.draw_projectiles) e il disegno sulle unità
(Panciamburo: battiti rossi della pancia finché dura il +Attacco).

Pixel art: forme piene a 3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config
from .incin_fx import draw_arrow

WATER = ((16, 44, 96), (58, 132, 222), (196, 236, 255))     # contorno, corpo, luce
FOAM = ((70, 120, 170), (178, 222, 248), (255, 255, 255))
SPIRAL = ((22, 30, 60), (40, 52, 96), (236, 240, 255))      # pancia di Poliwag
FIST = ((24, 30, 70), (70, 96, 196), (170, 196, 255))       # guanti blu di Poliwrath
DYN = ((90, 30, 10), (240, 120, 40), (255, 220, 140))       # Dinamipugno
DRUM = ((70, 10, 16), (220, 50, 56), (255, 170, 150))       # Panciamburo
MUD = ((40, 26, 14), (112, 78, 44), (176, 138, 92))
TOAD = ((20, 70, 30), (80, 180, 90), (200, 250, 180))       # Politoad
PERISH = ((30, 14, 50), (120, 70, 190), (226, 200, 255))    # Ultimocanto
MIRROR = ((60, 70, 100), (200, 214, 240), (255, 255, 255))
STAR = ((120, 90, 20), (250, 220, 80), (255, 250, 200))
SHADE = (8, 18, 30)
WHITE = (255, 255, 255)

POLI_DEX = (60, 61, 62, 186)

# Cifre 3x5 per il conto alla rovescia di Ultimocanto.
_DIGITS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "011", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
}
_digit_cache: dict = {}


def _al(f, k=2.0):
    return max(0, min(255, int(255 * min(1.0, f * k))))


def _bits(fx, c, n, cols, speed=1.6, life=(0.3, 0.6), up=0.7):
    for _ in range(n):
        a = random.uniform(0, math.tau)
        sp = random.uniform(0.3, 1.0) * speed
        fx._add(c[0], c[1], math.cos(a) * sp, math.sin(a) * sp * 0.6 - up,
                random.uniform(*life), random.choice(cols), 1)


def _shake(fx, ms):
    fx.shake_until_ms = max(getattr(fx, "shake_until_ms", 0), pygame.time.get_ticks() + ms)


def _ab(e):
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return None
    return tuple(a), tuple(b)


def _track(s, key="tid"):
    tr = s.get("track")
    if tr is None or s.get(key) is None:
        return None
    try:
        return tr(s[key])
    except Exception:
        return None


def _center(s, S):
    p = _track(s)
    return S(*(p if p is not None else s["c"]))


def _sh(fx, **kw):
    fx._shape(**kw)


def _hit_points(e):
    h = e.get("hits")
    if not h:
        return []
    return [(h[i], h[i + 1]) for i in range(0, len(h) - 1, 2)]


# --- mattoni ---------------------------------------------------------------------------

def draw_bubble(surface, x, y, r, alpha, spiral=False):
    """Bolla: velo azzurro, bordo chiaro e contorno scuro, riflesso in alto a
    sinistra; con `spiral` la spirale bianca della pancia di Poliwag."""
    r = max(1.5, r)
    ir = int(r)
    if ir <= 1:
        surface.fill((*FOAM[1], alpha), pygame.Rect(int(x), int(y), 2, 2))
        return
    pygame.draw.circle(surface, (*WATER[1], alpha // 3), (int(x), int(y)), ir)
    pygame.draw.circle(surface, (*WATER[0], alpha), (int(x), int(y)), ir + 1, 1)
    pygame.draw.circle(surface, (*FOAM[1], alpha), (int(x), int(y)), ir, 1)
    if spiral and ir >= 4:
        pts = []
        for i in range(14):
            an = i * 0.55
            rr = r * 0.12 + r * 0.6 * i / 13
            pts.append((x + math.cos(an) * rr, y + math.sin(an) * rr))
        pygame.draw.lines(surface, (*WHITE, alpha), False, pts, 1)
    hx, hy = int(x - r * 0.45), int(y - r * 0.45)
    surface.fill((*WHITE, alpha), pygame.Rect(hx, hy, max(1, ir // 3), max(1, ir // 3)))


def draw_drop(surface, x, y, s, alpha, cols=WATER):
    """Goccia (punta in alto): contorno, corpo, puntino di luce."""
    pts = [(x, y - s * 1.5), (x + s, y), (x, y + s), (x - s, y)]
    pygame.draw.polygon(surface, (*cols[0], alpha), [(px + (px - x) * 0.3, py + (py - y) * 0.3) for px, py in pts])
    pygame.draw.polygon(surface, (*cols[1], alpha), pts)
    surface.fill((*cols[2], alpha), pygame.Rect(int(x - s * 0.4), int(y - s * 0.3), 1, 1))


def draw_note(surface, x, y, s, alpha, cols=PERISH):
    """Croma pixel art: testa ovale, gambo e bandierina (contorno scuro)."""
    s = max(3, int(s))
    head = pygame.Rect(0, 0, s + 2, int(s * 0.8) + 1)
    head.center = (int(x), int(y))
    gx = head.right - 1
    for dx, dy, c in ((1, 1, cols[0]), (0, 0, cols[1])):
        pygame.draw.ellipse(surface, (*c, alpha), head.move(dx, dy))
        pygame.draw.line(surface, (*c, alpha), (gx + dx, head.centery + dy), (gx + dx, head.top - s * 2 + dy), 2)
        pygame.draw.line(surface, (*c, alpha), (gx + dx, head.top - s * 2 + dy),
                         (gx + s * 0.8 + dx, head.top - s * 1.3 + dy), 2)
    surface.fill((*cols[2], alpha), pygame.Rect(head.left + 1, head.top + 1, 1, 1))


def _digit(ch, px):
    key = (ch, px)
    spr = _digit_cache.get(key)
    if spr is None:
        rows = _DIGITS.get(ch, _DIGITS["0"])
        spr = pygame.Surface((5 * px, 7 * px), pygame.SRCALPHA)
        for y, row in enumerate(rows):   # contorno a 8 vicini
            for x, b in enumerate(row):
                if b == "1":
                    spr.fill((*PERISH[0], 255), pygame.Rect(x * px, y * px, 3 * px, 3 * px))
        for y, row in enumerate(rows):
            for x, b in enumerate(row):
                if b == "1":
                    col = PERISH[2] if y < 2 else (236, 222, 255)
                    spr.fill((*col, 255), pygame.Rect((x + 1) * px, (y + 1) * px, px, px))
        _digit_cache[key] = spr
    return spr


def _dashed_ellipse(overlay, cx, cy, rx, ry, col, al, n, rot=0.0, w=2, fill=0.55):
    for i in range(n):
        a0 = rot + i * math.tau / n
        a1 = a0 + math.tau / n * fill
        p0 = (cx + math.cos(a0) * rx, cy + math.sin(a0) * ry)
        p1 = (cx + math.cos(a1) * rx, cy + math.sin(a1) * ry)
        pygame.draw.line(overlay, (*col, al), p0, p1, w)


# --- forme -------------------------------------------------------------------------------

SHAPES = ("polibubble", "poliarc", "politarget", "polirain", "polispiral", "poliring", "poliplus",
          "polimud", "polisplat", "poliswirl", "poliarcline", "polimark", "poliperish", "polimirror",
          "polimute")
AA_TRAVEL = {"polibubble": 0.85}


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    age = s["maxlife"] - s["life"]
    if kind == "polibubble":
        # Attacco base: bolla con la spirale che vola (a ricerca) e ondeggia.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.85)
        lift = 0.4 * ts
        x = ax + (bx - ax) * u
        y = ay + (by - ay) * u - lift - math.sin(u * math.pi) * 0.25 * ts
        r = s.get("sz", 0.15) * ts * (1.0 + 0.08 * math.sin(age * 30))
        al = 255 if "hom" in s else _al(f, 4)
        for k in (1, 2):   # bollicine dietro
            v = max(0.0, u - 0.12 * k)
            draw_bubble(overlay, ax + (bx - ax) * v, ay + (by - ay) * v - lift - math.sin(v * math.pi) * 0.25 * ts,
                        r * (0.4 - 0.1 * k), al)
        draw_bubble(overlay, x, y, r, al, spiral=True)
    elif kind == "poliarc":
        # Bolla: grossa bolla a spirale che vola in ARCO verso il punto mirato,
        # con l'ombra a terra che la segue.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t)
        x = ax + (bx - ax) * u
        y = ay + (by - ay) * u
        h = 4.0 * u * (1.0 - u) * s.get("arc", 1.6) * ts + 0.35 * ts * (1.0 - u)
        r = s.get("sz", 0.28) * ts
        sh = pygame.Rect(0, 0, int(r * 1.8), max(2, int(r * 0.5)))
        sh.center = (int(x), int(y))
        pygame.draw.ellipse(overlay, (*SHADE, 90), sh)
        wob = math.sin(age * 16) * 0.08
        draw_bubble(overlay, x, y - h, r * (1 + wob), 255, spiral=True)
    elif kind == "politarget":
        # Mirino d'atterraggio: ellisse tratteggiata che gira e un anello che
        # si stringe fino al bordo interno quando la bolla arriva.
        cx, cy = S(*s["c"])
        r = s.get("r", 1.6) * ts
        cols = s.get("cols", WATER)
        al = _al(f, 6)
        pygame.draw.ellipse(overlay, (*cols[1], 30), pygame.Rect(cx - r, cy - r * 0.5, r * 2, r))
        _dashed_ellipse(overlay, cx, cy, r, r * 0.5, cols[2], al, max(10, int(r / 4)), rot=age * 1.5)
        k = 1.0 - min(1.0, t) * 0.75
        pygame.draw.ellipse(overlay, (*cols[1], al), pygame.Rect(cx - r * k, cy - r * k * 0.5, r * k * 2, r * k), 1)
    elif kind == "polirain":
        # Pioggiadanza: velo azzurro tenue, bordo tratteggiato, gocce che
        # cadono a strisce oblique e schizzi a terra; per tutta la durata.
        cx, cy = S(*s["c"])
        r = s.get("r", 3.0) * ts
        al = int(_al(f, 6) * min(1.0, age / 0.2))
        pygame.draw.ellipse(overlay, (*WATER[1], al // 7), pygame.Rect(cx - r, cy - r * 0.5, r * 2, r))
        _dashed_ellipse(overlay, cx, cy, r, r * 0.5, FOAM[1], al * 2 // 3, max(14, int(r / 5)), rot=-age * 0.4,
                        w=1)
        rng = random.Random(s.get("seed", 0))
        n = s.get("n", 28)
        fall = 1.4 * ts
        for i in range(n):
            ph = rng.random()
            an = rng.uniform(0, math.tau)
            d = math.sqrt(rng.random()) * 0.95
            gx = cx + math.cos(an) * d * r
            gy = cy + math.sin(an) * d * r * 0.5
            v = (age * 1.8 + ph) % 1.0
            if v < 0.8:   # goccia che cade (striscia obliqua)
                y = gy - fall * (1.0 - v / 0.8)
                x = gx + fall * 0.25 * (1.0 - v / 0.8)
                pygame.draw.line(overlay, (*WATER[0], al // 2), (x + 1, y + 1), (x - 2, y + 6), 1)
                pygame.draw.line(overlay, (*FOAM[1], al), (x, y), (x - 2, y + 6), 1)
            else:         # schizzo a terra
                w = (v - 0.8) / 0.2
                rr = int(1 + w * 3)
                pygame.draw.ellipse(overlay, (*FOAM[1], int(al * (1 - w))),
                                    pygame.Rect(gx - rr, gy - rr // 2, rr * 2 + 1, rr + 1), 1)
    elif kind == "polispiral":
        # Spirale della pancia di Poliwag che gira (Panciamburo in rosso).
        cx, cy = _center(s, S)
        cy -= s.get("lift", 0.45) * ts
        r = s.get("r", 0.5) * ts * (0.6 + 0.4 * min(1.0, t * 4))
        cols = s.get("cols", DRUM)
        al = _al(f, 2.5)
        rot = age * s.get("spin", 9.0)
        if s.get("soft"):
            al = al * 3 // 5
        for pas, (dx, col, w) in enumerate(((1, cols[0], 2), (0, cols[1], 1), (0, cols[2], 1))):
            pts = []
            for i in range(22):
                an = rot + i * 0.42
                rr = r * (0.1 + 0.9 * i / 21)
                pts.append((cx + math.cos(an) * rr + dx, cy + math.sin(an) * rr * 0.6 + dx))
            pygame.draw.lines(overlay, (*col, al), False, pts, w)
    elif kind == "poliring":
        # Acquanello: anello d'acqua schiacciato attorno ai piedi che segue
        # chi lo lancia, con tre gocce che ci girano sopra.
        cx, cy = _center(s, S)
        r = s.get("r", 0.6) * ts
        al = int(_al(f, 5) * min(1.0, age / 0.2))
        rect = pygame.Rect(cx - r, cy - r * 0.45, r * 2, r * 0.9)
        pygame.draw.ellipse(overlay, (*WATER[0], al), rect.inflate(2, 2), 3)
        pygame.draw.ellipse(overlay, (*WATER[1], al), rect, 2)
        pygame.draw.arc(overlay, (*FOAM[2], al), rect, math.pi * 0.55, math.pi * 0.95, 1)
        drops = []
        for k in range(3):
            an = age * 3.0 + k * math.tau / 3
            drops.append((math.sin(an), cx + math.cos(an) * r, cy + math.sin(an) * r * 0.45))
        for _, x, y in sorted(drops):
            draw_drop(overlay, x, y - 0.25 * ts, max(2.0, 0.07 * ts), al)
    elif kind == "poliplus":
        # Crocetta di cura che sale e svanisce.
        cx, cy = _center(s, S)
        y = cy - (0.6 + age * 1.2) * ts + s.get("dy", 0) * ts
        x = cx + s.get("dx", 0) * ts
        al = _al(f, 2.5)
        k = max(2, int(0.06 * ts))
        for dx, dy, c in ((1, 1, WATER[0]), (0, 0, FOAM[2] if s.get("hi") else FOAM[1])):
            overlay.fill((*c, al), pygame.Rect(int(x - k * 1.5) + dx, int(y - k * 0.5) + dy, k * 3, k))
            overlay.fill((*c, al), pygame.Rect(int(x - k * 0.5) + dx, int(y - k * 1.5) + dy, k, k * 3))
    elif kind == "polimud":
        # Colpo di Fango: palla di fango che vola tesa con schizzi dietro.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.8)
        lift = 0.38 * ts
        x = ax + (bx - ax) * u
        y = ay + (by - ay) * u - lift - math.sin(u * math.pi) * 0.2 * ts
        if t > 0.8:
            return
        r = s.get("sz", 0.13) * ts
        rng = random.Random(s.get("seed", 0))
        for k in range(4):   # gocce di fango dietro
            v = max(0.0, u - 0.07 * (k + 1))
            px = ax + (bx - ax) * v + rng.uniform(-3, 3)
            py = ay + (by - ay) * v - lift - math.sin(v * math.pi) * 0.2 * ts + rng.uniform(-3, 3)
            pygame.draw.circle(overlay, (*MUD[1], 220), (int(px), int(py)), max(1, int(r * (0.5 - 0.09 * k))))
        pts = [(x + math.cos(an) * r * (1 + 0.18 * math.sin(an * 3 + age * 20)),
                y + math.sin(an) * r * (1 + 0.18 * math.sin(an * 3 + age * 20))) for an in
               (i * math.tau / 10 for i in range(10))]
        pygame.draw.polygon(overlay, (*MUD[0], 255), [(px + 1, py + 1) for px, py in pts])
        pygame.draw.polygon(overlay, (*MUD[1], 255), pts)
        pygame.draw.circle(overlay, (*MUD[2], 255), (int(x - r * 0.35), int(y - r * 0.35)), max(1, int(r * 0.3)))
    elif kind == "polisplat":
        # Macchia di fango che si spiaccica sul bersaglio e cola giù.
        cx, cy = _center(s, S)
        cy -= s.get("lift", 0.35) * ts
        r = s.get("r", 0.24) * ts * (0.5 + 0.5 * min(1.0, t * 6))
        al = _al(f, 2.0)
        rng = random.Random(s.get("seed", 0))
        for _ in range(6):   # lobi
            an = rng.uniform(0, math.tau)
            d = rng.uniform(0.4, 0.9) * r
            rr = max(1, int(r * rng.uniform(0.3, 0.5)))
            px, py = cx + math.cos(an) * d, cy + math.sin(an) * d * 0.7
            pygame.draw.circle(overlay, (*MUD[0], al), (int(px) + 1, int(py) + 1), rr)
            pygame.draw.circle(overlay, (*MUD[1], al), (int(px), int(py)), rr)
        pygame.draw.circle(overlay, (*MUD[1], al), (int(cx), int(cy)), max(1, int(r * 0.55)))
        for k in range(2):   # colature
            x = cx + (k - 0.5) * r * 0.8
            pygame.draw.line(overlay, (*MUD[1], al), (x, cy), (x, cy + r * (0.6 + t * 0.8 + 0.3 * k)), 2)
        pygame.draw.circle(overlay, (*MUD[2], al), (int(cx - r * 0.25), int(cy - r * 0.25)), max(1, int(r * 0.15)))
    elif kind == "poliswirl":
        # Mulinello: vortice d'acqua schiacciato con bracci a spirale che
        # girano verso il centro e schiuma sul bordo, per tutta la durata.
        cx, cy = S(*s["c"])
        r = s.get("r", 2.2) * ts
        al = int(_al(f, 5) * min(1.0, age / 0.2))
        pygame.draw.ellipse(overlay, (*WATER[0], al // 3), pygame.Rect(cx - r, cy - r * 0.5, r * 2, r))
        pygame.draw.ellipse(overlay, (*WATER[1], al // 4),
                            pygame.Rect(cx - r * 0.6, cy - r * 0.3, r * 1.2, r * 0.6))
        rot = age * 5.0
        for arm in range(4):
            for pas, (col, w) in enumerate(((WATER[1], 3), (FOAM[1], 1))):
                pts = []
                for i in range(16):
                    v = i / 15
                    an = rot + arm * math.tau / 4 + v * 2.6
                    rr = r * (0.95 - 0.85 * v)
                    pts.append((cx + math.cos(an) * rr, cy + math.sin(an) * rr * 0.5))
                pygame.draw.lines(overlay, (*col, al if pas else al * 2 // 3), False, pts, w)
        _dashed_ellipse(overlay, cx, cy, r, r * 0.5, FOAM[2], al, max(12, int(r / 5)), rot=rot * 0.5, w=1)
        pygame.draw.ellipse(overlay, (*WATER[0], al), pygame.Rect(cx - r * 0.12, cy - r * 0.06, r * 0.24, r * 0.12))
    elif kind == "poliarcline":
        # Ribaltiro: arco tratteggiato della presa e del lancio dietro le spalle.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        h = s.get("h", 1.6) * ts
        al = _al(f, 2.0)
        n = 18
        pts = []
        for i in range(n + 1):
            v = i / n
            pts.append((ax + (bx - ax) * v, ay + (by - ay) * v - 4 * v * (1 - v) * h - 0.4 * ts))
        head = min(n, int(n * min(1.0, t / 0.5)) + 1)
        for i in range(0, head - 1):
            if i % 2:
                continue
            pygame.draw.line(overlay, (*FIST[0], al), (pts[i][0] + 1, pts[i][1] + 1),
                             (pts[i + 1][0] + 1, pts[i + 1][1] + 1), 3)
            pygame.draw.line(overlay, (*FIST[2], al), pts[i], pts[i + 1], 2)
        if head <= n:
            x, y = pts[head - 1]
            pygame.draw.circle(overlay, (*WHITE, al), (int(x), int(y)), 2)
    elif kind == "polimark":
        # Rimbalzo: ombra di Politoad che cresce al punto d'arrivo + anello
        # tratteggiato che si chiude finché atterra.
        cx, cy = S(*s["c"])
        r = s.get("r", 2.6) * ts
        al = _al(f, 8)
        pygame.draw.ellipse(overlay, (*TOAD[1], 26), pygame.Rect(cx - r, cy - r * 0.5, r * 2, r))
        _dashed_ellipse(overlay, cx, cy, r, r * 0.5, TOAD[2], al, max(12, int(r / 4)), rot=age * 1.2)
        k = 1.0 - min(1.0, t)
        pygame.draw.ellipse(overlay, (*TOAD[1], al),
                            pygame.Rect(cx - r * (0.25 + 0.75 * k), cy - r * (0.25 + 0.75 * k) * 0.5,
                                        r * (0.25 + 0.75 * k) * 2, r * (0.25 + 0.75 * k)), 2)
        sr = (0.2 + 0.4 * min(1.0, t)) * ts
        pygame.draw.ellipse(overlay, (*SHADE, int(70 + 80 * t)),
                            pygame.Rect(cx - sr, cy - sr * 0.4, sr * 2, sr * 0.8))
    elif kind == "poliperish":
        # Ultimocanto: area viola col bordo tratteggiato, note che girano sul
        # bordo e la cifra del conto alla rovescia sopra il centro.
        cx, cy = S(*s["c"])
        r = s.get("r", 3.0) * ts
        left = max(0.0, s["life"])
        al = int(255 * min(1.0, age / 0.25))
        pulse = 0.5 + 0.5 * math.sin(age * (6 + 6 * (1 - left / max(0.1, s["maxlife"]))))
        pygame.draw.ellipse(overlay, (*PERISH[1], int(20 + 24 * pulse)),
                            pygame.Rect(cx - r, cy - r * 0.5, r * 2, r))
        _dashed_ellipse(overlay, cx, cy, r, r * 0.5, PERISH[0], al, max(14, int(r / 4)), rot=age * 0.8, w=3)
        _dashed_ellipse(overlay, cx, cy, r, r * 0.5, PERISH[2], al, max(14, int(r / 4)), rot=age * 0.8, w=1)
        for k in range(5):
            an = -age * 1.2 + k * math.tau / 5
            x = cx + math.cos(an) * r * 0.85
            y = cy + math.sin(an) * r * 0.42 - 0.3 * ts - math.sin(age * 5 + k) * 3
            draw_note(overlay, x, y, 0.09 * ts, al)
        n = max(1, math.ceil(left - 1e-3))
        px = max(2, int(0.07 * ts))
        spr = _digit(str(min(5, n)), px)
        overlay.blit(spr, (int(cx - spr.get_width() / 2), int(cy - 1.4 * ts - spr.get_height() / 2)))
    elif kind == "polimirror":
        # Ripeti: scheggia di specchio che vola e brilla.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.7)
        if t > 0.7:
            return
        lift = 0.4 * ts
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - lift
        ang = math.atan2(by - ay, bx - ax) + age * 14
        r = 0.16 * ts
        pts = [(x + math.cos(ang + k * math.pi / 2) * r * (1.0 if k % 2 == 0 else 0.5),
                y + math.sin(ang + k * math.pi / 2) * r * (1.0 if k % 2 == 0 else 0.5)) for k in range(4)]
        tx, ty = ax + (bx - ax) * max(0.0, u - 0.25), ay + (by - ay) * max(0.0, u - 0.25) - lift
        pygame.draw.line(overlay, (*MIRROR[1], 120), (tx, ty), (x, y), 2)
        pygame.draw.polygon(overlay, (*MIRROR[0], 255), [(px + 1, py + 1) for px, py in pts])
        pygame.draw.polygon(overlay, (*MIRROR[1], 255), pts)
        pygame.draw.line(overlay, (*WHITE, 255), pts[0], pts[2], 1)
    elif kind == "polimute":
        # Silenzio di Ripeti: nota sbarrata sopra la testa del colpito.
        cx, cy = _center(s, S)
        y = cy - 1.15 * ts - min(1.0, t * 4) * 0.1 * ts
        al = _al(f, 3.0)
        s_ = 0.12 * ts
        draw_note(overlay, cx - s_ * 0.3, y, s_, al, cols=MIRROR)
        R = int(s_ * 2.0)
        pygame.draw.circle(overlay, (*DRUM[0], al), (int(cx) + 1, int(y - s_ * 0.6) + 1), R, 3)
        pygame.draw.circle(overlay, (*DRUM[1], al), (int(cx), int(y - s_ * 0.6)), R, 2)
        d = R * 0.7
        pygame.draw.line(overlay, (*DRUM[1], al), (cx - d, y - s_ * 0.6 - d), (cx + d, y - s_ * 0.6 + d), 2)


# --- effetti istantanei --------------------------------------------------------------------

def _bubbles(fx, c, n, wait=0.0, r=(0.06, 0.12), spread=0.35, rise=(0.4, 0.9)):
    for _ in range(n):
        p = (c[0] + random.uniform(-spread, spread), c[1] + random.uniform(-spread, spread) * 0.6)
        _sh(fx, kind="totobubble", c=p, r=random.uniform(*r), rise=random.uniform(*rise),
            seed=random.uniform(0, 6), col=FOAM[1], life=random.uniform(0.4, 0.7),
            wait=wait + random.uniform(0.0, 0.1))


def _spray(fx, c, wait=0.0, n=8, r=0.6):
    """Spruzzo d'arrivo: anello sottile + gocce."""
    _sh(fx, kind="ring", c=c, r0=0.12, r1=r, col=FOAM[1], life=0.22, wd=0.05, wait=wait)
    _sh(fx, kind="totosplash", c=(c[0], c[1] + 0.4), h=0.0, w=0.12, drops=n, seed=random.randrange(999),
        col=WATER[1], life=0.45, wait=wait)


def fx_polibubble(fx, e, col):
    """Attacco base a distanza (Poliwag, Poliwhirl, Politoad): bolla con la
    spirale; a ricerca (fx._aa_ranged tiene solo la testa)."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    _sh(fx, kind="polibubble", a=a, b=b, sz=0.17 if e.get("big") else 0.14, col=FOAM[1],
        life=0.15 + L / 14.0)


def fx_polipunch(fx, e, col):
    """Attacco base di Poliwrath (in mischia): guantone blu che scatta sul
    bersaglio."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    st = (b[0] - (b[0] - a[0]) / L * 0.7, b[1] - (b[1] - a[1]) / L * 0.7)
    _sh(fx, kind="scyfist", a=st, b=b, sz=0.14, cols=FIST, col=FIST[1], life=0.26)
    _bits(fx, (b[0], b[1] - 0.4), 3, (WATER[1], FOAM[1]), speed=1.2, life=(0.15, 0.3))


def fx_poliarc(fx, e, col):
    """Bolla (Q): la bolla vola in arco col mirino che si stringe; all'arrivo
    (evento 'area' dell'impatto) scoppia: anello, gocce e bollicine."""
    if e.get("kind") == "arcbubble":
        ab = _ab(e)
        if ab is None:
            return
        a, b = ab
        r = float(e.get("radius", 1.6))
        d = float(e.get("delay", 0.55))
        _sh(fx, kind="politarget", c=b, r=r, col=WATER[1], life=d)
        _sh(fx, kind="poliarc", a=a, b=b, sz=0.3, arc=1.3, col=FOAM[1], life=d)
        return
    if e.get("kind") != "area":
        return
    c = e.get("c")
    if c is None:
        return
    c = tuple(c)
    r = float(e.get("radius", 0.8)) * 2.0
    _sh(fx, kind="ring", c=c, r0=0.2, r1=r * 0.9, col=FOAM[1], life=0.3, wd=0.05)
    _sh(fx, kind="totosplash", c=c, h=0.7, w=0.22, drops=10, seed=random.randrange(999),
        col=WATER[1], life=0.5)
    for _ in range(5):
        an = random.uniform(0, math.tau)
        dd = random.uniform(0.3, r * 0.8)
        _bubbles(fx, (c[0] + math.cos(an) * dd, c[1] + math.sin(an) * dd * 0.6), 1)


def fx_polibeam(fx, e, col):
    """Bollaraggio al lancio: bollicine alla bocca (la raffica in volo la
    disegna world_fx.draw_projectiles -> draw_projectile)."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    _bubbles(fx, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 0.35), 4, r=(0.05, 0.1), spread=0.25)


def fx_polibeamhit(fx, e, col):
    """Bollaraggio a segno: le bolle scoppiano sul colpito."""
    c = e.get("c")
    if c is None:
        return
    c = tuple(c)
    top = (c[0], c[1] - 0.4)
    _spray(fx, top, n=6, r=0.55)
    _bubbles(fx, top, 5, r=(0.05, 0.1), spread=0.3)


def fx_polimirror(fx, e, col):
    """Ripeti: scheggia di specchio che vola sul bersaglio, lampo e nota
    sbarrata (silenzio) sopra la testa."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    fly = 0.08 + L / 16.0
    _sh(fx, kind="polimirror", a=a, b=b, col=MIRROR[1], life=fly / 0.7)
    _sh(fx, kind="twinkle", c=(b[0], b[1] - 0.45), r=0.3, col=WHITE, cols=MIRROR, life=0.3, wait=fly)
    _sh(fx, kind="polimute", c=b, track=fx.pos_of, tid=e.get("hit_id"), col=DRUM[1], life=1.1, wait=fly)
    _bits(fx, (b[0], b[1] - 0.45), 6, (MIRROR[1], WHITE), speed=1.6, life=(0.2, 0.35))


def fx_polirain(fx, e, col):
    """Pioggiadanza: zona di pioggia che dura quanto la mossa (evento al lancio)."""
    c = e.get("c")
    if c is None or e.get("kind") != "zone":
        return
    c = tuple(c)
    r = float(e.get("radius", 3.0))
    dur = float(e.get("dur", 3.0))
    _sh(fx, kind="polirain", c=c, r=r, n=int(10 + r * r * 2.5), seed=random.randrange(9999),
        col=WATER[1], life=dur)
    _sh(fx, kind="polispiral", c=c, track=fx.pos_of, tid=e.get("src"), r=0.45, cols=WATER, spin=12.0,
        col=WATER[1], life=0.5)


def fx_polidrum(fx, e, col):
    """Panciamburo: la spirale della pancia gira in rosso, colpi di tamburo
    (anelli) e scintille; poi l'overlay sull'unità per la durata."""
    c = e.get("c")
    if c is None or e.get("kind") != "buff":
        return
    c = tuple(c)
    _sh(fx, kind="polispiral", c=c, track=fx.pos_of, tid=e.get("src"), r=0.26, lift=0.32, soft=True,
        cols=DRUM, col=DRUM[1], life=0.6)
    for k in range(3):
        _sh(fx, kind="ring", c=c, r0=0.45, r1=0.8, col=DRUM[1], life=0.18, wd=0.03, wait=k * 0.18)
    _sh(fx, kind="impactstar", c=(c[0] + 0.35, c[1] - 0.75), r=0.16, n=8, rot=random.uniform(0, 1), cols=DRUM,
        col=DRUM[1], life=0.16, wait=0.36)
    _bits(fx, (c[0], c[1] - 0.5), 6, (DRUM[1], DRUM[2]), speed=1.8, life=(0.3, 0.5))


def fx_poliaquaring(fx, e, col):
    """Acquanello: al lancio l'anello d'acqua attorno ai piedi per la durata;
    a ogni battito della cura crocette che salgono."""
    c = e.get("c")
    if c is None or e.get("kind") != "zone":
        return
    c = tuple(c)
    if e.get("src") is not None:   # lancio
        dur = float(e.get("dur", 4.0))
        r = float(e.get("radius", 3.0))
        _sh(fx, kind="poliring", c=c, track=fx.pos_of, tid=e.get("src"), r=0.6, col=WATER[1], life=dur)
        _sh(fx, kind="ring", c=c, r0=0.3, r1=r, col=FOAM[1], life=0.35, wd=0.05)
        return
    for k in range(3):   # battito: crocette di cura
        _sh(fx, kind="poliplus", c=(c[0] + random.uniform(-0.5, 0.5), c[1] + random.uniform(-0.2, 0.2)),
            hi=k == 0, col=FOAM[1], life=0.6, wait=k * 0.1)


def fx_polimud(fx, e, col):
    """Colpo di Fango: palla di fango tesa; a segno si spiaccica e cola."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    fly = 0.05 + L / 11.0
    _sh(fx, kind="polimud", a=a, b=b, sz=0.14, seed=random.randrange(999), col=MUD[1], life=fly / 0.8)
    if e.get("hit"):
        _sh(fx, kind="polisplat", c=b, track=fx.pos_of, tid=e.get("hit_id"), seed=random.randrange(999),
            col=MUD[1], life=0.7, wait=fly)
        for _ in range(6):
            an = random.uniform(0, math.tau)
            fx._add(b[0], b[1] - 0.4, math.cos(an) * 1.5, math.sin(an) * 0.8 - 0.6,
                    random.uniform(0.2, 0.4), random.choice((MUD[1], MUD[2])), 1)


def fx_polithrow(fx, e, col):
    """Ribaltiro: presa (stella) e arco tratteggiato fin dietro le spalle,
    poi tonfo all'atterraggio."""
    if e.get("kind") != "dash":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    _sh(fx, kind="impactstar", c=(a[0], a[1] - 0.45), r=0.28, n=6, rot=random.uniform(0, 1), cols=FIST,
        col=FIST[1], life=0.14)
    _sh(fx, kind="poliarcline", a=a, b=b, h=2.0, col=FIST[2], life=0.5)
    _sh(fx, kind="ring", c=b, r0=0.2, r1=0.8, col=FOAM[1], life=0.25, wd=0.05, wait=0.4)
    _sh(fx, kind="dizzy", c=(b[0], b[1] - 1.05), r=0.3, cols=((140, 200, 255), WHITE), col=FOAM[1],
        life=0.9, wait=0.4)
    _shake(fx, 80)


def fx_poliswirl(fx, e, col):
    """Mulinello: vortice d'acqua a terra per tutta la durata + spruzzi."""
    c = e.get("c")
    if c is None or e.get("kind") != "vortex":
        return
    c = tuple(c)
    r = float(e.get("radius", 2.2))
    dur = float(e.get("dur", 1.5))
    _sh(fx, kind="poliswirl", c=c, r=r, col=WATER[1], life=dur)
    _bubbles(fx, c, 6, r=(0.06, 0.12), spread=r * 0.5)


def fx_polidynamic(fx, e, col):
    """Dinamipugno: un grosso pugno arancione nel cono e, su ogni colpito,
    stella d'impatto + stelline della confusione."""
    if e.get("kind") != "cone":
        return
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    L = math.hypot(d[0], d[1]) or 1.0
    ux, uy = d[0] / L, d[1] / L
    rng = float(e.get("range", 2.6))
    a = (o[0] + ux * 0.3, o[1] + uy * 0.3)
    b = (o[0] + ux * rng * 0.8, o[1] + uy * rng * 0.8)
    _sh(fx, kind="scyfist", a=a, b=b, sz=0.26, cols=DYN, col=DYN[1], life=0.35)
    _sh(fx, kind="incinroar", o=o, ang=math.atan2(uy, ux), half=math.radians(e.get("angle", 45)) * 0.6,
        rng=rng * 0.7, cols=DYN, col=DYN[1], life=0.3, wait=0.08)
    for p in _hit_points(e):
        top = (p[0], p[1] - 0.45)
        _sh(fx, kind="impactstar", c=top, r=0.34, n=8, rot=random.uniform(0, 1), cols=DYN, col=DYN[1],
            life=0.18, wait=0.1)
        _sh(fx, kind="dizzy", c=(p[0], p[1] - 1.05), r=0.3, cols=(DYN[2], WHITE), col=DYN[1], life=1.3,
            wait=0.12)
    _shake(fx, 110)


def fx_poliflurry(fx, e, col):
    """Zuffa: raffica di pugni blu in tutte le direzioni attorno a Poliwrath,
    stelle d'impatto sparse e un anello."""
    c = e.get("c")
    if c is None or e.get("kind") != "area":
        return
    c = tuple(c)
    r = float(e.get("radius", 2.4))
    for k in range(7):
        an = k * math.tau / 7 + random.uniform(-0.3, 0.3)
        d = random.uniform(0.55, 0.85) * r
        a = (c[0] + math.cos(an) * 0.3, c[1] + math.sin(an) * 0.2)
        b = (c[0] + math.cos(an) * d, c[1] + math.sin(an) * d * 0.7)
        _sh(fx, kind="scyfist", a=a, b=b, sz=0.15, cols=FIST, col=FIST[1], life=0.26, wait=k * 0.045)
        _sh(fx, kind="impactstar", c=(b[0], b[1] - 0.35), r=0.22, n=6, rot=random.uniform(0, 1), cols=FIST,
            col=FIST[1], life=0.13, wait=k * 0.045 + 0.08)
    _sh(fx, kind="ring", c=c, r0=0.4, r1=r, col=FIST[2], life=0.3, wd=0.05, wait=0.1)
    _shake(fx, 130)


def fx_polibounce(fx, e, col):
    """Rimbalzo: al salto l'ombra e il mirino d'arrivo; all'atterraggio
    (evento con 'land') onda d'acqua, colonna di schizzi e scossa."""
    c = e.get("c")
    if c is None or e.get("kind") != "area":
        return
    c = tuple(c)
    r = float(e.get("radius", 2.6))
    if not e.get("land"):
        _sh(fx, kind="polimark", c=c, r=r, col=TOAD[1], life=float(e.get("dur", 1.0)))
        return
    _sh(fx, kind="totosplash", c=c, h=1.1, w=0.3, drops=12, seed=random.randrange(999), col=WATER[1], life=0.6)
    _sh(fx, kind="ring", c=c, r0=0.4, r1=r, col=TOAD[2], life=0.4, wd=0.06)
    _sh(fx, kind="ring", c=c, r0=0.2, r1=r * 0.6, col=FOAM[1], life=0.32, wd=0.05, wait=0.08)
    for _ in range(4):
        _sh(fx, kind="poliplus", c=(c[0] + random.uniform(-0.6, 0.6), c[1] + random.uniform(-0.3, 0.3)),
            col=FOAM[1], life=0.6, wait=random.uniform(0.1, 0.3))
    _shake(fx, 160)


def fx_poliperish(fx, e, col):
    """Ultimocanto: al lancio l'area col conto alla rovescia (dura quanto il
    conto, 'left'); ai battiti una nota sale; alla fine lampo viola, note che
    schizzano via e scossa."""
    c = e.get("c")
    if c is None:
        return
    c = tuple(c)
    r = float(e.get("radius", 3.0))
    kind = e.get("kind")
    if kind == "zone":
        if e.get("src") is not None:   # lancio
            _sh(fx, kind="poliperish", c=c, r=r, col=PERISH[1], life=float(e.get("left", 3.0)))
            _sh(fx, kind="ring", c=c, r0=0.3, r1=r, col=PERISH[2], life=0.35, wd=0.05)
            return
        an = random.uniform(0, math.tau)
        p = (c[0] + math.cos(an) * r * 0.5, c[1] + math.sin(an) * r * 0.3)
        _sh(fx, kind="note", c=p, ang=-math.pi / 2, d0=0.0, dist=0.6, cols=PERISH, col=PERISH[1], life=0.8)
        return
    if kind != "area":
        return
    _sh(fx, kind="impactstar", c=(c[0], c[1] - 0.4), r=0.35, n=8, rot=random.uniform(0, 1), cols=PERISH,
        col=PERISH[1], life=0.18)
    _sh(fx, kind="ring", c=c, r0=0.5, r1=r, col=PERISH[1], life=0.4, wd=0.03)
    for k in range(5):
        _sh(fx, kind="note", c=c, ang=k * math.tau / 5 + random.uniform(-0.2, 0.2), d0=0.8, dist=r * 0.7,
            cols=PERISH, col=PERISH[1], life=0.6)
    _shake(fx, 200)


STYLES = {
    "polibubble": fx_polibubble, "polipunch": fx_polipunch, "poliarc": fx_poliarc,
    "polibeam": fx_polibeam, "polibeamhit": fx_polibeamhit, "polimirror": fx_polimirror,
    "polirain": fx_polirain, "polidrum": fx_polidrum, "poliaquaring": fx_poliaquaring,
    "polimud": fx_polimud, "polithrow": fx_polithrow, "poliswirl": fx_poliswirl,
    "polidynamic": fx_polidynamic, "poliflurry": fx_poliflurry, "polibounce": fx_polibounce,
    "poliperish": fx_poliperish,
}


# --- Bollaraggio in volo ---------------------------------------------------------------------

def draw_projectile(surface, camera, pr, now):
    """Bollaraggio in volo (world_fx.draw_projectiles): grappolo di bolle che
    ondeggiano attorno alla testa, scia di bollicine e ombra a terra."""
    ts = config.TILE_SIZE
    p = pr["pos"]
    gx, gy = camera.world_to_screen(p.x * ts, p.y * ts)
    r = max(3.0, pr.get("radius", 0.6) * ts * 0.4)
    lift = int(0.42 * ts)
    sw, shh = max(4, int(r * 1.6)), max(2, int(r * 0.45))
    shl = pygame.Surface((sw, shh), pygame.SRCALPHA)
    pygame.draw.ellipse(shl, (*SHADE, 70), shl.get_rect())
    surface.blit(shl, (gx - sw // 2, gy + 2 - shh // 2))
    d = pr.get("dir")
    dx, dy = (d.x, d.y) if d is not None else (1.0, 0.0)
    size = int(r * 10)
    layer = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size / 2
    for k in range(1, 6):   # scia
        bx = cx - dx * r * (0.9 + 0.7 * k) + math.sin(now * 11 + k * 2.1) * r * 0.4
        by = cy - dy * r * (0.9 + 0.7 * k) + math.cos(now * 9 + k * 1.7) * r * 0.4
        draw_bubble(layer, bx, by, r * (0.5 - 0.07 * k), 230)
    for k in range(3):      # grappolo in testa
        an = now * 8 + k * math.tau / 3
        draw_bubble(layer, cx + math.cos(an) * r * 0.55, cy + math.sin(an) * r * 0.55, r * 0.55, 255)
    draw_bubble(layer, cx, cy, r * 0.75, 255)
    surface.blit(layer, (gx - cx, gy - lift - cy))


# --- sulle unità ---------------------------------------------------------------------------

def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Panciamburo: battiti rossi della pancia (un piccolo anello che pulsa
    sul corpo + due note di tamburo che salgono) finché dura il +Attacco."""
    if getattr(u, "atk_until", -1.0) <= now or getattr(u, "dex", 0) not in POLI_DEX:
        return
    r = getattr(u, "radius", 0.5) * ts
    left = getattr(u, "atk_until", now) - now
    al = 255 if left > 1.0 else int(255 * max(0.0, left))
    beat = (now * 2.2) % 1.0
    cy = gy - r * 0.9
    rr = int(r * (0.35 + 0.35 * beat))
    if rr > 1:
        pygame.draw.ellipse(surface, DRUM[0], pygame.Rect(gx - rr + 1, cy - rr // 2 + 1, rr * 2, rr), 2)
        lay = pygame.Surface((rr * 2 + 4, rr + 4), pygame.SRCALPHA)
        pygame.draw.ellipse(lay, (*DRUM[1], int(al * (1 - beat))), pygame.Rect(2, 2, rr * 2, rr), 2)
        surface.blit(lay, (gx - rr - 2, cy - rr // 2 - 2))
    for k in range(2):   # freccine rosse che salgono ai lati (+Attacco)
        v = (now * 0.9 + k * 0.5) % 1.0
        if v > 0.8 or al < 120:
            continue
        x = gx + (k * 2 - 1) * r * 1.5
        y = gy - r * 0.5 - v * r * 0.9
        draw_arrow(surface, x, y, True, DRUM[1])
