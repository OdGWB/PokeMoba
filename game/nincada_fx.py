"""Grafica della linea Nincada > Ninjask (+ forma Shedinja): effetti istantanei
(handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (graffi affusolati, X di Forbice X, buca nel terreno,
vortice di sabbia, sbuffi di Doppioteam, linee di velocità, aureola e fiammelle
spettrali) e il disegno sulle unità (Shedinja: aureola che fluttua sopra la
testa e fiammelle spettrali, più rosse e fitte nella forma di Rancore).

Pixel art: forme piene a 3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

CLAW = ((30, 24, 10), (236, 200, 96), (255, 255, 236))     # contorno, corpo, luce
FURY = ((60, 30, 14), (236, 168, 84), (255, 236, 190))
XS = ((16, 56, 22), (112, 222, 92), (232, 255, 214))
EARTH = ((44, 30, 18), (128, 94, 56), (190, 156, 106))
SAND = ((96, 74, 36), (214, 186, 120), (250, 236, 186))
SHELL = ((70, 58, 30), (214, 196, 136), (255, 250, 226))
WIND = ((70, 92, 100), (214, 238, 242))
GHOST = ((30, 16, 52), (136, 96, 210), (222, 204, 255))
GRUDGE = ((54, 8, 32), (196, 52, 112), (255, 176, 214))
HALO = ((116, 96, 46), (246, 232, 166), (255, 255, 240))
PUFF = ((104, 98, 96), (226, 222, 214), (255, 255, 255))
SWORD = (220, 230, 250)
WHITE = (255, 255, 255)


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


def _hit_points(e):
    h = e.get("hits")
    if not h:
        return []
    return [(h[i], h[i + 1]) for i in range(0, len(h) - 1, 2)]


# --- mattoni ---------------------------------------------------------------------------

def _taper(surface, a, b, prog, w, bow, cols, al):
    """Tratto AFFUSOLATO da a verso b (spesso al centro, a punta ai capi),
    disegnato fino a `prog` (0..1), un filo incurvato (bow, frazione della
    lunghezza): contorno scuro, corpo, filo di luce sul lato in alto a sinistra."""
    if prog <= 0.02:
        return
    ax, ay = a
    bx, by = b
    L = math.hypot(bx - ax, by - ay)
    if L < 2:
        return
    ux, uy = (bx - ax) / L, (by - ay) / L
    px, py = -uy, ux
    N = 10
    cen = []
    for i in range(N + 1):
        v = prog * i / N
        bo = math.sin(math.pi * v) * bow * L
        cen.append((ax + (bx - ax) * v + px * bo, ay + (by - ay) * v + py * bo, v))
    for layer, extra in ((0, 1.8), (1, 0.0)):
        left, right = [], []
        for x, y, v in cen:
            hw = w * math.sin(math.pi * v) + extra
            left.append((x + px * hw, y + py * hw))
            right.append((x - px * hw, y - py * hw))
        poly = left + right[::-1]
        if len(poly) >= 3:
            pygame.draw.polygon(surface, (*cols[layer], al), poly)
    side = -1.0 if (px + py) > 0 else 1.0   # verso l'alto a sinistra
    hl = [(x + side * px * w * 0.35 * math.sin(math.pi * v), y + side * py * w * 0.35 * math.sin(math.pi * v))
          for x, y, v in cen[2:-2]]
    if len(hl) >= 2:
        pygame.draw.lines(surface, (*cols[2], al), False, hl, 1)


def _flame(surface, x, y, h, w, alpha, cols, lean=0.0):
    """Fiammella a goccia (punta in alto, che si piega)."""
    pts = [(x - w, y), (x - w * 0.6, y - h * 0.45), (x + lean, y - h), (x + w * 0.6, y - h * 0.45), (x + w, y),
           (x, y + w * 0.5)]
    pygame.draw.polygon(surface, (*cols[0], alpha), [(px + (px - x) * 0.3, py + (py - y + h * 0.4) * 0.12)
                                                      for px, py in pts])
    pygame.draw.polygon(surface, (*cols[1], alpha), pts)
    inner = [(x - w * 0.45, y), (x + lean * 0.6, y - h * 0.6), (x + w * 0.45, y)]
    pygame.draw.polygon(surface, (*cols[2], alpha), inner)


def _halo(surface, x, y, w, alpha, glow=True):
    """Aureola di Shedinja: anello schiacciato dorato, luce in alto a sinistra."""
    rect = pygame.Rect(0, 0, max(4, int(w * 2)), max(2, int(w * 0.62)))
    rect.center = (int(x), int(y))
    if glow:
        pygame.draw.ellipse(surface, (*HALO[1], alpha // 5), rect.inflate(6, 4))
    pygame.draw.ellipse(surface, (*HALO[0], alpha), rect.inflate(2, 2), 3)
    pygame.draw.ellipse(surface, (*HALO[1], alpha), rect, 2)
    pygame.draw.arc(surface, (*HALO[2], alpha), rect, math.pi * 0.55, math.pi * 1.05, 1)


# --- forme -------------------------------------------------------------------------------

SHAPES = ("ninscratch", "ninx", "ninhole", "ninsand", "ninpuff", "ninspeed", "ninhalo", "ninwisp")
AA_TRAVEL = {}


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    age = s["maxlife"] - s["life"]
    if kind == "ninscratch":
        # Graffi: n tratti affusolati paralleli che corrono uno dopo l'altro
        # sul colpito (dall'alto a sinistra verso il basso a destra).
        p = _track(s)
        cx, cy = S(*(p if p is not None else s["c"]))
        cy -= s.get("lift", 0.45) * ts
        ang = s.get("ang", 0.9)
        n = s.get("n", 3)
        L = s.get("L", 0.6) * ts
        sep = s.get("sep", 0.15) * ts
        w = s.get("w", 0.06) * ts
        cols = s.get("cols", CLAW)
        ux, uy = math.cos(ang), math.sin(ang)
        px, py = -uy, ux
        al = 255 if f > 0.3 else int(255 * f / 0.3)
        stg = s.get("stagger", 0.1)
        for i in range(n):
            prog = (t - i * stg) / 0.22
            if prog <= 0:
                continue
            off = (i - (n - 1) / 2) * sep
            ln = L * (0.8 + 0.2 * math.sin(math.pi * (i + 0.5) / n))
            a0 = (cx - ux * ln / 2 + px * off, cy - uy * ln / 2 + py * off)
            b0 = (cx + ux * ln / 2 + px * off, cy + uy * ln / 2 + py * off)
            _taper(overlay, a0, b0, min(1.0, prog), w, 0.1, cols, al)
    elif kind == "ninx":
        # Forbice X: due lame affusolate e incurvate che si incrociano una dopo
        # l'altra attorno a chi lancia, poi un lampo all'incrocio.
        p = _track(s)
        cx, cy = S(*(p if p is not None else s["c"]))
        cy -= s.get("lift", 0.4) * ts
        R = s.get("r", 0.9) * ts
        w = s.get("w", 0.1) * ts
        cols = s.get("cols", XS)
        al = 255 if f > 0.3 else int(255 * f / 0.3)
        for j, sg in enumerate((1, -1)):
            prog = (t - j * 0.16) / 0.2
            if prog <= 0:
                continue
            a0 = (cx - R * sg, cy - R * 0.62)
            b0 = (cx + R * sg, cy + R * 0.62)
            _taper(overlay, a0, b0, min(1.0, prog), w, 0.12 * sg, cols, al)
        if 0.36 < t < 0.62:   # lampo all'incrocio: stella a 4 raggi
            k = 1.0 - abs(t - 0.49) / 0.13
            rr = R * 0.32 * k
            for an in (0.0, math.pi / 2):
                dx, dy = math.cos(an) * rr, math.sin(an) * rr
                pygame.draw.line(overlay, (*cols[1], al), (cx - dx, cy - dy), (cx + dx, cy + dy), 3)
                pygame.draw.line(overlay, (*WHITE, al), (cx - dx, cy - dy), (cx + dx, cy + dy), 1)
    elif kind == "ninhole":
        # Buca: si apre in fretta, resta e si richiude; zolle che saltano fuori.
        cx, cy = S(*s["c"])
        r = s.get("r", 0.45) * ts
        cols = s.get("cols", EARTH)
        k = min(1.0, t / 0.15) * min(1.0, f / 0.35)
        rx, ry = r * k, r * 0.42 * k
        if rx >= 2:
            rim = pygame.Rect(0, 0, int(rx * 2 + 6), int(ry * 2 + 4))
            rim.center = (int(cx), int(cy))
            pygame.draw.ellipse(overlay, (*cols[0], 255), rim.inflate(2, 2))
            pygame.draw.ellipse(overlay, (*cols[1], 255), rim)
            pygame.draw.arc(overlay, (*cols[2], 255), rim, math.pi * 0.25, math.pi * 0.95, 1)
            hole = pygame.Rect(0, 0, int(rx * 2), max(2, int(ry * 2)))
            hole.center = (int(cx), int(cy + 1))
            if s.get("rimonly"):
                # riemersione: solo il bordo di terra smossa (chi esce sta
                # al centro: la buca scura gli finirebbe sopra)
                pygame.draw.ellipse(overlay, (0, 0, 0, 0), hole)
                pygame.draw.ellipse(overlay, (*cols[0], 200), hole, 1)
            else:
                pygame.draw.ellipse(overlay, (24, 16, 10, 255), hole)
        rng = random.Random(s.get("seed", 0))
        al = _al(f, 3.0)
        for i in range(s.get("clods", 6)):   # zolle a parabola dal bordo
            an = rng.uniform(0, math.tau)
            v = rng.uniform(0.6, 1.3) * r * 2.2
            x = cx + math.cos(an) * (r * 0.5 + v * t)
            y = cy + math.sin(an) * r * 0.25 - v * 1.6 * t + 3.2 * ts * t * t
            if y < cy + r * 0.4:
                sz = 3 if i % 2 else 2
                overlay.fill((*cols[0], al), pygame.Rect(int(x) - 1, int(y) - 1, sz + 1, sz + 1))
                overlay.fill((*cols[1 + i % 2], al), pygame.Rect(int(x) - 1, int(y) - 1, sz, sz))
    elif kind == "ninsand":
        # Sabbiotomba: vortice di sabbia a terra che gira e risucchia granelli
        # verso il centro per tutta la durata della radice.
        cx, cy = S(*s["c"])
        r = s.get("r", 2.0) * ts
        al = int(255 * min(1.0, t / 0.12) * min(1.0, f / 0.25))
        rect = pygame.Rect(0, 0, int(r * 2), int(r))
        rect.center = (int(cx), int(cy))
        pygame.draw.ellipse(overlay, (*SAND[1], al // 6), rect)
        n = max(12, int(r / 5))
        for i in range(n):   # trattini del bordo che girano
            a0 = i / n * math.tau + age * 1.6
            a1 = a0 + math.tau / n * 0.5
            p0 = (cx + math.cos(a0) * r, cy + math.sin(a0) * r * 0.5)
            p1 = (cx + math.cos(a1) * r, cy + math.sin(a1) * r * 0.5)
            pygame.draw.line(overlay, (*SAND[0], al), p0, p1, 3)
            pygame.draw.line(overlay, (*SAND[1], al), p0, p1, 1)
        rng = random.Random(s.get("seed", 0))
        for i in range(36):   # granelli che spiraleggiano verso il centro
            a0 = rng.uniform(0, math.tau)
            ph = rng.random()
            u = (age * 0.8 + ph) % 1.0
            rad = r * (1.0 - u) * 0.95
            an = a0 + age * 2.6 + u * 3.5
            x = cx + math.cos(an) * rad
            y = cy + math.sin(an) * rad * 0.5 - u * 0.15 * ts
            g = int(al * min(1.0, (1.0 - u) * 3))
            c = SAND[2] if i % 3 == 0 else SAND[1]
            overlay.fill((*c, g), pygame.Rect(int(x), int(y), 2 if i % 4 else 1, 2 if i % 4 else 1))
        for j in range(2):   # spirale sottile al centro
            pts = []
            for k in range(14):
                v = k / 13
                an = age * 3.2 + j * math.pi + v * 4.0
                pts.append((cx + math.cos(an) * r * 0.45 * v, cy + math.sin(an) * r * 0.22 * v))
            pygame.draw.lines(overlay, (*SAND[0], al // 2), False, pts, 1)
    elif kind == "ninpuff":
        # Sbuffi di fumo chiaro che si gonfiano e svaniscono (Doppioteam).
        cx, cy = S(*s["c"])
        r = s.get("r", 0.4) * ts
        rng = random.Random(s.get("seed", 0))
        al = _al(f, 2.0)
        puffs = []
        for i in range(s.get("n", 6)):
            an = rng.uniform(0, math.tau)
            d = rng.uniform(0.2, 1.0) * r
            rr = r * rng.uniform(0.35, 0.6) * (0.5 + 0.6 * min(1.0, t * 2.5))
            puffs.append((cx + math.cos(an) * d * (0.6 + t), cy + math.sin(an) * d * 0.5 - t * r * 0.6
                          - s.get("lift", 0.3) * ts, rr))
        for x, y, rr in puffs:
            pygame.draw.circle(overlay, (*PUFF[0], al), (int(x), int(y)), int(rr) + 1)
        for x, y, rr in puffs:
            pygame.draw.circle(overlay, (*PUFF[1], al), (int(x), int(y)), int(rr))
        for x, y, rr in puffs:
            pygame.draw.circle(overlay, (*PUFF[2], al), (int(x - rr * 0.35), int(y - rr * 0.35)),
                               max(1, int(rr * 0.3)))
    elif kind == "ninspeed":
        # Agilità: linee di velocità che scorrono ai lati di chi corre.
        p = _track(s)
        cx, cy = S(*(p if p is not None else s["c"]))
        al = _al(f, 3.0)
        rng = random.Random(s.get("seed", 0))
        for i in range(6):
            h = rng.uniform(0.1, 0.95) * ts
            ph = rng.random()
            u = (ph + age * 2.2) % 1.0
            sg = -1 if i % 2 else 1
            x = cx + sg * (0.35 + u * 0.5) * ts
            ln = 0.35 * ts * (1.0 - u)
            a = int(al * (1.0 - u))
            pygame.draw.line(overlay, (*WIND[0], a), (x, cy - h + 1), (x + sg * ln, cy - h + 1), 2)
            pygame.draw.line(overlay, (*WIND[1], a), (x, cy - h), (x + sg * ln, cy - h), 1)
    elif kind == "ninhalo":
        # L'aureola di Shedinja che scende dall'alto sulla testa.
        p = _track(s)
        cx, cy = S(*(p if p is not None else s["c"]))
        drop = 1.0 - min(1.0, t / 0.4)
        drop = drop * drop
        y = cy - s.get("lift", 1.0) * ts - drop * 0.8 * ts
        _halo(overlay, cx, y, s.get("w", 0.22) * ts, _al(f, 3.0))
    elif kind == "ninwisp":
        # Fiammella spettrale che sale ondeggiando e si spegne.
        cx, cy = S(*s["c"])
        cols = s.get("cols", GHOST)
        h = s.get("h", 0.3) * ts * (1.0 - 0.5 * t)
        x = cx + math.sin(age * 6 + s.get("seed", 0)) * 0.08 * ts
        y = cy - s.get("lift", 0.3) * ts - s.get("rise", 0.8) * ts * t
        _flame(overlay, x, y, h, max(2.0, h * 0.28), _al(f, 2.5), cols,
               lean=math.sin(age * 9 + s.get("seed", 0)) * h * 0.25)


# --- effetti istantanei --------------------------------------------------------------------

def _sh(fx, **kw):
    fx._shape(**kw)


def _wisps(fx, c, n, cols, spread=0.4, wait=0.0, life=(0.5, 0.9)):
    for _ in range(n):
        an = random.uniform(0, math.tau)
        d = random.uniform(0.1, spread)
        _sh(fx, kind="ninwisp", c=(c[0] + math.cos(an) * d, c[1] + math.sin(an) * d * 0.5),
            h=random.uniform(0.2, 0.34), rise=random.uniform(0.6, 1.1), seed=random.uniform(0, 6),
            cols=cols, col=cols[1], life=random.uniform(*life), wait=wait + random.uniform(0, 0.15))


def _front(e, frac=0.6, default=2.0):
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return None
    L = math.hypot(d[0], d[1]) or 1.0
    rng = float(e.get("range", default)) * frac
    return (o[0] + d[0] / L * rng, o[1] + d[1] / L * rng)


def fx_ninclaw(fx, e, col):
    """Attacco base (in mischia): due graffi chiari sul bersaglio."""
    ab = _ab(e)
    if ab is None:
        return
    _, b = ab
    _sh(fx, kind="ninscratch", c=b, n=2, L=0.56, sep=0.15, w=0.07, ang=random.uniform(0.7, 1.1),
        track=fx.pos_of, tid=e.get("tgt"), col=CLAW[1], life=0.3)


def fx_ninscratch(fx, e, col):
    """Graffio: tre graffi affusolati su ogni colpito."""
    if e.get("kind") != "cone":
        return
    pts = _hit_points(e)
    hit = bool(pts)
    if not pts:
        p = _front(e)
        pts = [p] if p else []
    for p in pts:
        _sh(fx, kind="ninscratch", c=p, n=3, L=0.62, ang=random.uniform(0.7, 1.1), col=CLAW[1], life=0.38)
        if hit:
            _bits(fx, (p[0], p[1] - 0.45), 4, (CLAW[1], CLAW[2]), speed=1.4, life=(0.15, 0.3))


def fx_ninfury(fx, e, col):
    """Sfuriate: raffica di graffi incrociati, uno sull'altro, arancioni."""
    if e.get("kind") != "cone":
        return
    pts = _hit_points(e)
    hit = bool(pts)
    if not pts:
        p = _front(e)
        pts = [p] if p else []
    for p in pts:
        base = random.uniform(0.7, 1.0)
        for k, ang in enumerate((base, base + 1.55, base + 0.25)):
            _sh(fx, kind="ninscratch", c=p, n=2, L=0.5, sep=0.12, w=0.05, ang=ang, stagger=0.15,
                col=FURY[1], cols=FURY, life=0.3, wait=k * 0.08)
        if hit:
            _sh(fx, kind="impactstar", c=(p[0], p[1] - 0.45), r=0.16, n=6, rot=random.uniform(0, 1),
                cols=FURY, col=FURY[1], life=0.14, wait=0.16)


def fx_ninxscissor(fx, e, col):
    """Forbice X: X verde di lame attorno a Nincada + anello sottile."""
    c = e.get("c")
    if c is None or e.get("kind") != "area":
        return
    c = tuple(c)
    r = float(e.get("radius", 2.0))
    _sh(fx, kind="ninx", c=c, r=min(0.62, r * 0.32), w=0.06, track=fx.pos_of, tid=e.get("src"),
        col=XS[1], life=0.5)
    _sh(fx, kind="ring", c=c, r0=0.4, r1=r, col=XS[1], life=0.28, wd=0.05, wait=0.12)
    _bits(fx, (c[0], c[1] - 0.4), 8, (XS[1], XS[2]), speed=2.2, life=(0.2, 0.4))


def _dive(fx, c, cols, wait=0.0):
    _sh(fx, kind="ninhole", c=c, r=0.42, cols=cols, clods=7, seed=random.randrange(999),
        col=cols[1], life=0.6, wait=wait)
    _bits(fx, (c[0], c[1] - 0.1), 6, (cols[1], cols[2]), speed=1.2, life=(0.25, 0.45), up=1.0)


def _burst(fx, c, r, cols):
    _sh(fx, kind="ninhole", c=(c[0], c[1] + 0.12), r=0.5, cols=cols, clods=12, seed=random.randrange(999),
        rimonly=True, col=cols[1], life=0.7)
    _sh(fx, kind="ring", c=c, r0=0.4, r1=r, col=cols[1], life=0.35, wd=0.05)
    _bits(fx, (c[0], c[1] - 0.2), 12, (cols[1], cols[2]), speed=2.4, life=(0.3, 0.55), up=1.4)
    _shake(fx, 120)


def fx_nindig(fx, e, col):
    """Fossa: buca con le zolle al tuffo, esplosione di terra in riemersione."""
    c = e.get("c")
    if c is None:
        return
    c = tuple(c)
    if e.get("kind") == "dive":
        _dive(fx, c, EARTH)
    elif e.get("kind") == "area":
        _burst(fx, c, float(e.get("radius", 2.0)), EARTH)


def fx_ninsandtomb(fx, e, col):
    """Sabbiotomba: buca di sabbia al tuffo; in riemersione vortice di sabbia
    per la durata della radice."""
    c = e.get("c")
    if c is None:
        return
    c = tuple(c)
    if e.get("kind") == "dive":
        _dive(fx, c, SAND)
    elif e.get("kind") == "area":
        r = float(e.get("radius", 2.2))
        _burst(fx, c, r, SAND)
        _sh(fx, kind="ninsand", c=c, r=r, seed=random.randrange(999), col=SAND[1], life=1.6)


def fx_nindouble(fx, e, col):
    """Doppioteam: sbuffo al tuffo; in riemersione (col clone) un altro sbuffo."""
    c = e.get("c")
    if c is None:
        return
    c = tuple(c)
    if e.get("kind") == "dive":
        _dive(fx, c, EARTH)
        _sh(fx, kind="ninpuff", c=c, r=0.45, n=6, seed=random.randrange(999), col=PUFF[1], life=0.5)
    elif e.get("kind") == "area":
        _sh(fx, kind="ninpuff", c=c, r=0.6, n=8, seed=random.randrange(999), col=PUFF[1], life=0.6)
        _sh(fx, kind="twinkle", c=(c[0] + 0.3, c[1] - 0.9), r=0.18, col=WHITE, life=0.4, wait=0.1)


def fx_ninharden(fx, e, col):
    """Indurimento: guscio esagonale color corazza che si stringe + scintilla."""
    c = e.get("c")
    if c is None or e.get("kind") != "buff":
        return
    c = tuple(c)
    _sh(fx, kind="hexshell", c=c, r=0.7, col=SHELL[1], life=0.7)
    _sh(fx, kind="twinkle", c=(c[0] - 0.3, c[1] - 0.8), r=0.2, col=SHELL[2], life=0.4, wait=0.25)
    _bits(fx, (c[0], c[1] - 0.4), 5, (SHELL[1], SHELL[2]), speed=1.0, life=(0.2, 0.4))


def fx_ninagility(fx, e, col):
    """Agilità: linee di velocità ai lati per un attimo + folate."""
    c = e.get("c")
    if c is None or e.get("kind") != "buff":
        return
    c = tuple(c)
    _sh(fx, kind="ninspeed", c=c, track=fx.pos_of, tid=e.get("src"), seed=random.randrange(999),
        col=WIND[1], life=1.2)
    _sh(fx, kind="ring", c=c, r0=0.2, r1=0.9, col=WIND[1], life=0.25, wd=0.04)


def fx_ninswords(fx, e, col):
    """Danzaspada: quattro spadine che girano attorno + anello rosso."""
    c = e.get("c")
    if c is None or e.get("kind") != "buff":
        return
    c = tuple(c)
    for k in range(4):
        _sh(fx, kind="sword", c=c, a0=k * math.pi / 2, spin=7.0, orbit=0.8, size=0.34, col=SWORD, life=0.75)
    _sh(fx, kind="ring", c=c, r0=0.3, r1=1.1, col=(236, 120, 96), life=0.35, wd=0.05)


def fx_ninaerial(fx, e, col):
    """Aeroassalto: una scia di vento per ogni balzo (uno dopo l'altro) e tre
    graffi su ogni bersaglio raggiunto."""
    if e.get("kind") != "dash":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    w = int(e.get("i", 0)) * 0.12
    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    px, py = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
    for off in (-0.12, 0.0, 0.12):
        lift = 0.45 + off
        _sh(fx, kind="windline", a=(a[0] + px * off, a[1] - lift), b=(b[0] + px * off, b[1] - lift),
            col=WIND[1], life=0.28, wait=w + abs(off))
    if e.get("hit"):
        _sh(fx, kind="ninscratch", c=b, n=3, L=0.7, ang=random.uniform(0.6, 1.2), track=fx.pos_of,
            tid=e.get("tgt"), col=CLAW[1], life=0.36, wait=w + 0.05)
        _bits(fx, (b[0], b[1] - 0.45), 5, (CLAW[1], WIND[1]), speed=1.6, life=(0.15, 0.3))
    else:
        _bits(fx, b, 5, (EARTH[1], EARTH[2]), speed=1.0, life=(0.2, 0.4))


def _molt(fx, e, cols, grudge):
    c = e.get("c")
    if c is None or e.get("kind") != "area":
        return
    c = tuple(c)
    _sh(fx, kind="ninhalo", c=c, track=fx.pos_of, tid=e.get("src", e.get("eid")), lift=1.05,
        col=HALO[1], life=0.9)
    _wisps(fx, c, 8 if grudge else 5, cols, spread=0.5)
    _sh(fx, kind="ring", c=c, r0=0.3, r1=1.4, col=cols[1], life=0.4, wd=0.05)
    if grudge:
        _sh(fx, kind="impactstar", c=(c[0], c[1] - 0.5), r=0.35, n=8, rot=random.uniform(0, 1),
            cols=cols, col=cols[1], life=0.18)
        _shake(fx, 140)
    _bits(fx, (c[0], c[1] - 0.5), 8, (cols[1], cols[2]), speed=1.2, life=(0.4, 0.7), up=1.2)


def fx_ninmolt(fx, e, col):
    """Muta: aureola che scende e fiammelle spettrali viola."""
    _molt(fx, e, GHOST, False)


def fx_ningrudge(fx, e, col):
    """Rancore: come la Muta ma cremisi, con un colpo d'urto e la scossa."""
    _molt(fx, e, GRUDGE, True)


def fx_ninrevert(fx, e, col):
    """Fine della forma Shedinja: il guscio si rompe, schegge chiare."""
    c = e.get("c")
    if c is None:
        return
    c = tuple(c)
    _sh(fx, kind="ring", c=c, r0=0.2, r1=1.0, col=SHELL[1], life=0.3, wd=0.05)
    _bits(fx, (c[0], c[1] - 0.5), 10, (SHELL[1], SHELL[2], GHOST[2]), speed=1.8, life=(0.3, 0.5))


STYLES = {
    "ninclaw": fx_ninclaw, "ninscratch": fx_ninscratch, "ninfury": fx_ninfury,
    "ninxscissor": fx_ninxscissor, "nindig": fx_nindig, "ninsandtomb": fx_ninsandtomb,
    "nindouble": fx_nindouble, "ninharden": fx_ninharden, "ninagility": fx_ninagility,
    "ninswords": fx_ninswords, "ninaerial": fx_ninaerial, "ninmolt": fx_ninmolt,
    "ningrudge": fx_ningrudge, "ninrevert": fx_ninrevert,
}


# --- sulle unità ---------------------------------------------------------------------------

_HALO_CACHE: dict = {}


def _halo_sprite(w):
    spr = _HALO_CACHE.get(w)
    if spr is None:
        spr = pygame.Surface((w * 2 + 12, w + 12), pygame.SRCALPHA)
        _halo(spr, spr.get_width() / 2, spr.get_height() / 2, w, 255)
        _HALO_CACHE[w] = spr
    return spr


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Forma Shedinja (dex 292): aureola che fluttua sopra la testa e due
    fiammelle spettrali dietro; con Rancore (solo offline: il campo non passa
    online) fiammelle cremisi più fitte. Visibile a tutti."""
    if getattr(u, "dex", 0) != 292 or not getattr(u, "alive", True):
        return
    r = getattr(u, "radius", 0.5) * ts
    grudge = bool(getattr(u, "rancore_form", False))
    cols = GRUDGE if grudge else GHOST
    alpha_ok = bool(surface.get_flags() & pygame.SRCALPHA)
    n = 4 if grudge else 2
    for i in range(n):   # fiammelle spettrali che salgono ai lati
        ph = (now * 0.9 + i / n) % 1.0
        sg = -1 if i % 2 else 1
        x = gx + sg * r * (0.75 + 0.15 * math.sin(now * 3 + i))
        y = gy - r * 0.4 - ph * r * 1.1
        h = r * 0.5 * (1.0 - 0.6 * ph)
        al = int(200 * (1.0 - ph))
        if not alpha_ok and al < 90:
            continue
        _flame(surface, x, y, h, max(2.0, h * 0.28), al, cols, lean=math.sin(now * 7 + i) * h * 0.3)
    w = max(4, int(r * 0.55))
    spr = _halo_sprite(w)
    bob = math.sin(now * 3.0) * 2
    surface.blit(spr, (gx - spr.get_width() // 2, int(gy - r * 2.3 + bob) - spr.get_height() // 2))
