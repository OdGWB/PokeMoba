"""Grafica della linea Charmander > Charmeleon > Charizard: effetti istantanei
(handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (palla di fuoco con la coda, getto del Lanciafiamme,
vortice di Turbofuoco, stella di Fuocobomba, mirino d'atterraggio di Volo),
la palla di Fuocobomba in volo (world_fx.draw_projectiles) e i disegni sulle
unità (Calore di Fiammacoda sotto la barra della vita, Scottatura).

Pixel art: forme piene a 3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config
from .charcadet_fx import draw_flame

FIRE = ((150, 32, 14), (246, 116, 36), (255, 214, 96))     # contorno, corpo, luce
CORE = (255, 246, 200)
SMOKE = (58, 50, 50)
DRAGON = ((40, 22, 96), (110, 84, 236), (214, 206, 255))    # Dragartigli
SCRATCH = ((70, 64, 60), (236, 232, 222), (255, 255, 255))  # Graffio
WING = (30, 22, 26)
WING_IN = (52, 120, 132)   # membrana delle ali di Charizard
WHITE = (255, 255, 255)


def _al(f, k=2.0):
    return max(0, min(255, int(255 * min(1.0, f * k))))


def _bits(fx, c, n, cols, speed=2.0, life=(0.25, 0.5), up=0.6):
    for _ in range(n):
        a = random.uniform(0, math.tau)
        sp = random.uniform(0.4, 1.0) * speed
        fx._add(c[0], c[1], math.cos(a) * sp, math.sin(a) * sp * 0.7 - up,
                random.uniform(*life), random.choice(cols), 1)


def _tongues(fx, c, n, spread, h=0.6, w=0.32, life=(0.3, 0.55), up=0.5, cols=FIRE, wait=0.0):
    for _ in range(n):
        a = random.uniform(0, math.tau)
        r = spread * math.sqrt(random.random())
        fx._shape(kind="flametongue", c=(c[0] + math.cos(a) * r, c[1] + math.sin(a) * r * 0.7),
                  v=(random.uniform(-0.15, 0.15), -up * random.uniform(0.5, 1.0)),
                  h=h * random.uniform(0.7, 1.25), w=w * random.uniform(0.8, 1.2),
                  ph=random.uniform(0, 6), cols=cols, col=cols[1],
                  life=random.uniform(*life), wait=wait)


def _shake(fx, ms):
    fx.shake_until_ms = max(getattr(fx, "shake_until_ms", 0), pygame.time.get_ticks() + ms)


# --- mattoni ---------------------------------------------------------------------------

def draw_fireball(surface, x, y, r, ang, alpha, flick=0.0, tail=1.0):
    """Palla di fuoco con la coda a goccia rivolta all'indietro (luce in alto a
    sinistra): contorno rosso scuro, corpo arancio, nucleo giallo e bianco."""
    r = max(2.0, r)
    bx, by = -math.cos(ang), -math.sin(ang)
    L = r * (2.2 + 0.4 * math.sin(flick)) * tail
    px, py = -by, bx
    for k, col in enumerate(FIRE):
        s = 1.0 - 0.28 * k
        rr = r * s
        ll = L * (1.0 - 0.25 * k)
        wob = math.sin(flick * 1.7 + k) * rr * 0.25
        tip = (x + bx * (rr + ll) + px * wob, y + by * (rr + ll) + py * wob)
        pts = [tip, (x + px * rr, y + py * rr), (x - px * rr, y - py * rr)]
        pygame.draw.polygon(surface, (*col, alpha), pts)
        pygame.draw.circle(surface, (*col, alpha), (int(x), int(y)), max(1, int(rr)))
    pygame.draw.circle(surface, (*CORE, alpha), (int(x - r * 0.18), int(y - r * 0.2)),
                       max(1, int(r * 0.38)))


def _star_pts(cx, cy, r, rot, n=5, inner=0.38, sq=0.8):
    pts = []
    for i in range(n * 2):
        a = rot + i * math.pi / n
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr * sq))
    return pts


def draw_blast_star(surface, cx, cy, r, rot, alpha, inner=0.55):
    """Stella di fuoco a cinque bracci TOZZI di Fuocobomba (tre strati pieni:
    con bracci sottili e contorno sembrava un pentagramma)."""
    for k, col in enumerate(FIRE):
        s = 1.0 - 0.24 * k
        pygame.draw.polygon(surface, (*col, alpha), _star_pts(cx, cy, r * s, rot, inner=inner))


def draw_flame_pip(surface, x, y, lit, now=0.0):
    """Fiammella 5x7 del Calore (accesa o spenta)."""
    x, y = int(x), int(y)
    if lit:
        h = 7 + (1 if math.sin(now * 14 + x) > 0.3 else 0)
        draw_flame(surface, x, y + 3, h, 6, 255, FIRE)
    else:
        pygame.draw.circle(surface, (40, 30, 28), (x, y + 1), 2)
        pygame.draw.circle(surface, (90, 60, 50), (x, y + 1), 2, 1)


# --- forme -------------------------------------------------------------------------------

SHAPES = ("charball", "charstream", "charspin", "charstar", "charflymark", "charwings")
AA_TRAVEL = {"charball": 0.85}


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    age = s["maxlife"] - s["life"]
    if kind == "charball":
        # Palla di fuoco da A a B (Braciere, attacco base): la testa arriva a 0,85.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.85)
        if u >= 1.0:
            return
        lift = s.get("lift", 0.38) * ts
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - lift
        ang = math.atan2(by - ay, bx - ax)
        r = s.get("sz", 0.16) * ts
        al = 255 if "hom" in s else _al(f, 4.0)
        # braci che restano indietro
        rnd = random.Random(s.get("seed", 1))
        for k in range(5):
            uk = max(0.0, u - 0.05 * (k + 1))
            qx = ax + (bx - ax) * uk + rnd.uniform(-2, 2)
            qy = ay + (by - ay) * uk - lift + rnd.uniform(-2, 2) - k
            c = FIRE[2] if k < 2 else FIRE[1]
            overlay.fill((*c, max(0, al - 40 * k)), pygame.Rect(int(qx), int(qy), 2, 2))
        draw_fireball(overlay, x, y, r, ang, al, flick=age * 30 + s.get("seed", 0), tail=1.0)
    elif kind == "charstream":
        # Getto del Lanciafiamme: sbuffi che escono dalla bocca e corrono lungo il
        # cono, gialli vicino alla bocca, poi arancio, rossi e fumo in fondo.
        ox, oy = S(*s["o"])
        oy -= int(0.35 * ts)
        ang = s.get("ang", 0.0)
        half = s.get("half", 0.26)
        rng = s.get("rng", 7.0) * ts
        n = s.get("n", 7)
        rnd = random.Random(s.get("seed", 2))
        fly = s.get("fly", 0.26)
        # alone che unisce gli sbuffi in un getto solo (cono tenue fino alla testa)
        head = min(1.0, age / fly)
        tail = max(0.0, (age - n * s.get("gap", 0.035)) / fly)
        if head > tail:
            pts_l, pts_r = [], []
            for i in range(7):
                u = tail + (head - tail) * i / 6
                d = rng * u
                wv = (0.12 + 0.5 * u) * ts * 0.55 + half * d * 0.5
                bx, by = ox + math.cos(ang) * d, oy + math.sin(ang) * d * 0.8 - u * u * 0.3 * ts
                px, py = -math.sin(ang) * wv, math.cos(ang) * wv * 0.8
                pts_l.append((bx + px, by + py))
                pts_r.append((bx - px, by - py))
            pygame.draw.polygon(overlay, (*FIRE[1], 70), pts_l + pts_r[::-1])
        for k in range(n):
            off = rnd.uniform(-1.0, 1.0)
            u = (age - k * s.get("gap", 0.035)) / fly
            if u <= 0.0 or u >= 1.0:
                continue
            d = rng * u
            an = ang + off * half * min(1.0, u * 1.6)
            x = ox + math.cos(an) * d
            y = oy + math.sin(an) * d * 0.8 - u * u * 0.3 * ts
            r = (0.13 + 0.42 * u) * ts * rnd.uniform(0.85, 1.15) * 0.62
            al = int(235 * (1.0 - max(0.0, u - 0.7) / 0.3))
            if u > 0.78:   # in fondo: fumo scuro
                pygame.draw.circle(overlay, (*SMOKE, al // 2), (int(x), int(y)), int(r * 1.1))
            pygame.draw.circle(overlay, (*FIRE[0], al), (int(x), int(y)), int(r))
            if u < 0.85:
                pygame.draw.circle(overlay, (*FIRE[1], al), (int(x - r * 0.12), int(y - r * 0.12)),
                                   max(1, int(r * 0.74)))
            if u < 0.5:
                pygame.draw.circle(overlay, (*FIRE[2], al), (int(x - r * 0.2), int(y - r * 0.22)),
                                   max(1, int(r * 0.45)))
            if u < 0.22:
                pygame.draw.circle(overlay, (*CORE, al), (int(x - r * 0.2), int(y - r * 0.25)),
                                   max(1, int(r * 0.22)))
    elif kind == "charspin":
        # Turbofuoco: anello di fiamme che gira attorno alla zona + spirale dentro.
        cx, cy = S(*s["c"])
        R = s.get("r", 1.5) * ts
        intro = min(1.0, age / 0.2)
        al = _al(f, 4.0)
        R *= 0.6 + 0.4 * intro
        rect = pygame.Rect(int(cx - R), int(cy - R * 0.55), int(2 * R), int(1.1 * R))
        glow = pygame.Rect(0, 0, int(2 * R * 0.95), int(1.1 * R * 0.95))
        glow.center = rect.center
        pygame.draw.ellipse(overlay, (*FIRE[0], al // 4), glow)
        pygame.draw.ellipse(overlay, (*FIRE[0], al), rect, 3)
        pygame.draw.ellipse(overlay, (*FIRE[1], al), rect.inflate(-4, -3), 1)
        rot = age * 6.0
        for arm in range(3):   # spirale di braci verso il centro
            pts = []
            for i in range(9):
                u = i / 8
                an = rot + arm * math.tau / 3 + u * 2.4
                rr = R * (1.0 - 0.85 * u)
                pts.append((cx + math.cos(an) * rr, cy + math.sin(an) * rr * 0.55))
            pygame.draw.lines(overlay, (*FIRE[1], al // 2), False, pts, 2)
        n = s.get("n", 10)
        flames = []
        for i in range(n):   # fiamme che girano sul bordo (dietro prima, davanti dopo)
            an = rot + i * math.tau / n
            fx_, fy_ = cx + math.cos(an) * R, cy + math.sin(an) * R * 0.55
            h = (0.55 + 0.25 * math.sin(age * 18 + i * 1.7)) * ts * (0.8 + 0.2 * math.sin(an))
            flames.append((fy_, fx_, h))
        for fy_, fx_, h in sorted(flames):
            draw_flame(overlay, fx_, fy_, h, h * 0.62, al, FIRE)
    elif kind == "charstar":
        # Stella a cinque bracci che si apre (Fuocobomba all'impatto).
        cx, cy = S(*s["c"])
        cy -= int(0.3 * ts)
        u = min(1.0, t / 0.3)
        R = s.get("r", 1.2) * ts
        al = _al(f, 1.6)
        pygame.draw.circle(overlay, (*FIRE[0], al), (int(cx), int(cy)), int(R * (0.35 + 0.35 * u)))
        draw_blast_star(overlay, cx, cy, R * (0.4 + 0.6 * u), s.get("rot", 0.0) + t * 0.8, al)
        pygame.draw.circle(overlay, (*FIRE[2], al), (int(cx), int(cy)), int(R * (0.25 + 0.15 * u)))
        pygame.draw.circle(overlay, (*CORE, al), (int(cx - R * 0.06), int(cy - R * 0.08)),
                           max(1, int(R * 0.12 * (1.0 - u * 0.5))))
    elif kind == "charflymark":
        # Volo: mirino d'atterraggio. Ellisse tratteggiata che gira, anello che si
        # chiude con la carica e l'ombra di Charizard che cresce dall'alto.
        cx, cy = S(*s["c"])
        R = s.get("r", 2.6) * ts
        p = max(0.0, min(1.0, s.get("p", 0.0)))
        al = _al(f, 6.0)
        rect = pygame.Rect(int(cx - R), int(cy - R * 0.55), int(2 * R), int(1.1 * R))
        pygame.draw.ellipse(overlay, (*FIRE[0], int(al * 0.18)), rect)
        segs = 22
        rot = age * 1.4
        for i in range(segs):
            if i % 2:
                continue
            a0 = rot + i * math.tau / segs
            a1 = a0 + math.tau / segs
            pygame.draw.arc(overlay, (*FIRE[1], al), rect, -a1, -a0, 2)
        inner = rect.inflate(-int(2 * R * (1.0 - p) * 0.9) - 2, -int(1.1 * R * (1.0 - p) * 0.9) - 2) \
            if p < 1.0 else rect
        if inner.w > 4 and inner.h > 2:
            pygame.draw.ellipse(overlay, (*FIRE[2], al), inner, 2)
        sw = R * (0.3 + 0.7 * p)   # ombra con le ali spiegate
        sh = sw * 0.32
        body = pygame.Rect(int(cx - sw * 0.25), int(cy - sh * 0.5), int(sw * 0.5), int(sh))
        a2 = int(al * (0.25 + 0.4 * p))
        pygame.draw.ellipse(overlay, (*WING, a2), body)
        flap = math.sin(age * 9) * sh * 0.4
        for sg in (-1, 1):
            pts = [(cx + sg * sw * 0.18, cy - sh * 0.2), (cx + sg * sw, cy - sh * 0.7 + flap),
                   (cx + sg * sw * 0.8, cy + sh * 0.1 + flap * 0.5),
                   (cx + sg * sw * 0.55, cy - sh * 0.05), (cx + sg * sw * 0.18, cy + sh * 0.3)]
            pygame.draw.polygon(overlay, (*WING, a2), pts)
    elif kind == "charwings":
        # Decollo/atterraggio: due ali scure che battono attorno al punto.
        cx, cy = S(*s["c"])
        cy -= int(0.55 * ts)
        w = s.get("w", 1.0) * ts
        lift = t * 0.6 * ts   # le ali salgono col decollo
        cy -= lift
        flap = math.sin(t * math.pi * 4)
        al = _al(f, 2.0)
        body = pygame.Rect(0, 0, int(w * 0.34), int(w * 0.5))   # sagoma scura del corpo
        body.center = (int(cx), int(cy + w * 0.05))
        pygame.draw.ellipse(overlay, (*WING, al), body)
        pygame.draw.ellipse(overlay, (*FIRE[0], al), body, 1)
        for sg in (-1, 1):
            tip = (cx + sg * w, cy - w * (0.5 + 0.25 * flap))
            sh = (cx + sg * w * 0.1, cy - w * 0.08)
            # bordo d'attacco (osso) e tre dita che scendono a festone
            f1 = (cx + sg * w * 0.72, cy - w * (0.05 + 0.1 * flap))
            f2 = (cx + sg * w * 0.45, cy + w * (0.08 - 0.05 * flap))
            n1 = (cx + sg * w * 0.78, cy - w * (0.22 + 0.15 * flap))
            n2 = (cx + sg * w * 0.5, cy - w * (0.08 + 0.06 * flap))
            mem = [sh, tip, n1, f1, n2, f2, (cx + sg * w * 0.18, cy + w * 0.1)]
            pygame.draw.polygon(overlay, (*WING, al), [(x + sg, y + 1) for x, y in mem])
            pygame.draw.polygon(overlay, (*WING_IN, al), mem)
            pygame.draw.line(overlay, (*FIRE[0], al), sh, tip, 3)
            pygame.draw.line(overlay, (*FIRE[1], al), sh, tip, 1)
            for fp in (f1, f2):
                pygame.draw.line(overlay, (*FIRE[0], al), sh, fp, 1)


# --- effetti istantanei ---------------------------------------------------------------

def fx_charember(fx, e, col):
    """Braciere e attacco base: palla di fuoco con la coda, scoppio di brace."""
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return
    big = e.get("kind") == "projectile"
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    life = 0.2 + L / 30.0
    fx._shape(kind="charball", a=tuple(a), b=tuple(b), col=FIRE[1], life=life,
              sz=0.2 if big else 0.15, seed=random.randrange(999))
    wait = life * 0.85
    top = (b[0], b[1] - 0.38)
    fx._shape(kind="flash", c=top, r=0.45 if big else 0.3, col=FIRE[2], life=0.14, wait=wait)
    if big:
        _tongues(fx, b, 4, 0.3, h=0.5, w=0.28, life=(0.25, 0.4), wait=wait)
        fx._shape(kind="ring", c=b, r0=0.15, r1=0.7, col=FIRE[1], life=0.22, wd=0.07, wait=wait)


def fx_charflamethrower(fx, e, col):
    """Lanciafiamme: un'ondata di sbuffi di fuoco a ogni tick (si sovrappongono
    in un getto continuo)."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    n = 22
    fx._shape(kind="charstream", o=tuple(o), ang=math.atan2(d[1], d[0]),
              half=math.radians(e.get("angle", 15)), rng=e.get("range", 7.0), n=n,
              gap=0.009, fly=0.3, seed=random.randrange(9999), col=FIRE[1],
              life=0.009 * n + 0.3)
    if random.random() < 0.5:
        m = (o[0] + d[0] * 0.55, o[1] + d[1] * 0.55 - 0.35)
        fx._shape(kind="flash", c=m, r=0.22, col=FIRE[2], life=0.1)


def fx_charheatwave(fx, e, col):
    """Ondacalda: tre archi caldi che si allargano nel cono + braci nell'aria."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    ang = math.atan2(d[1], d[0])
    half = math.radians(e.get("angle", 38))
    rng = e.get("range", 5.0)
    fx._shape(kind="incinroar", o=tuple(o), ang=ang, half=half, rng=rng,
              cols=(FIRE[0], FIRE[1], FIRE[2]), col=FIRE[1], life=0.55)
    for _ in range(10):
        an = ang + random.uniform(-half, half)
        r = random.uniform(0.8, rng)
        fx._add(o[0] + math.cos(an) * r, o[1] + math.sin(an) * r, math.cos(an) * 1.2,
                math.sin(an) * 1.2 - 0.6, random.uniform(0.3, 0.6),
                random.choice((FIRE[1], FIRE[2])), 1)


def _claws(fx, e, cols, r):
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    ang = math.atan2(d[1], d[0])
    c = (o[0] + d[0] * r * 0.5, o[1] + d[1] * r * 0.5 - 0.3)
    fx._shape(kind="claw3", c=(c[0] - d[0] * 0.5, c[1] - d[1] * 0.5), r=0.75 if r < 2.6 else 0.9,
              half=0.55, ang=ang, cols=cols, col=cols[1], life=0.3)
    return c


def fx_charscratch(fx, e, col):
    """Graffio: tre graffi chiari."""
    _claws(fx, e, SCRATCH, e.get("range", 2.3))


def fx_chardragonclaw(fx, e, col):
    """Dragartigli: tre artigliate viola-blu più grandi, con un lampo."""
    c = _claws(fx, e, DRAGON, e.get("range", 2.6) * 1.1)
    if c is not None:
        fx._shape(kind="impactstar", c=c, r=0.45, n=6, rot=random.uniform(0, 1), cols=DRAGON,
                  col=DRAGON[1], life=0.2, wait=0.1)


def fx_charfirespin(fx, e, col):
    """Turbofuoco: vortice di fiamme che resta per tutta la durata."""
    c = e.get("c")
    if c is None:
        return
    if e.get("kind") == "vortex":
        r = float(e.get("radius", 1.5))
        fx._shape(kind="charspin", c=tuple(c), r=r, n=10, col=FIRE[1],
                  life=float(e.get("dur", 1.5)))
        _tongues(fx, c, 5, r * 0.6, h=0.6, life=(0.3, 0.5))
    else:   # impulso della zona: qualche lingua dentro
        _tongues(fx, c, 2, float(e.get("radius", 1.5)) * 0.7, h=0.5, life=(0.25, 0.4))


def fx_charblast(fx, e, col):
    """Fuocobomba: braci dietro la palla in volo; all'impatto stella di fuoco a
    cinque bracci, onda a terra, lingue di fuoco e scossa."""
    kind = e.get("kind")
    if kind == "projectile":
        b = e.get("b")
        if b is None:
            return
        if random.random() < 0.45:
            _bits(fx, (b[0], b[1] - 0.4), 1, (FIRE[1], FIRE[2]), speed=0.6, life=(0.3, 0.5))
        return
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.0))
    fx._shape(kind="flash", c=(c[0], c[1] - 0.3), r=r * 0.55, col=FIRE[2], life=0.16)
    fx._shape(kind="charstar", c=tuple(c), r=min(1.1, r * 0.5), rot=random.uniform(0, math.tau),
              col=FIRE[1], life=0.38)
    fx._shape(kind="groundring", c=tuple(c), r0=0.3, r1=r * 1.05, cols=FIRE, w=0.08,
              speed=2.5, col=FIRE[1], life=0.4, wait=0.12)
    fx._shape(kind="groundcrack", c=tuple(c), r=r * 0.6, n=5, seed=random.randint(0, 9999),
              col=(60, 30, 20), life=0.9)
    _tongues(fx, c, 9, r * 0.8, h=0.7, life=(0.35, 0.6))
    _bits(fx, (c[0], c[1] - 0.3), 10, (FIRE[1], FIRE[2], CORE), speed=3.0, life=(0.3, 0.6))
    _shake(fx, 150)


def fx_charinferno(fx, e, col):
    """Incendio: eruzione attorno a Charizard (lingue alte su tutto il raggio)."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 3.2))
    fx._shape(kind="flash", c=(c[0], c[1] - 0.3), r=0.9, col=FIRE[2], life=0.18)
    for k in range(2):
        fx._shape(kind="groundring", c=tuple(c), r0=0.4, r1=r, cols=FIRE, w=0.1,
                  speed=2.2, col=FIRE[1], life=0.5, wait=k * 0.15)
    fx._shape(kind="groundcrack", c=tuple(c), r=r * 0.7, n=8, seed=random.randint(0, 9999),
              col=(60, 30, 20), life=1.1)
    for i in range(14):   # anello di colonne di fuoco
        an = i * math.tau / 14 + random.uniform(-0.15, 0.15)
        rr = r * random.uniform(0.55, 0.95)
        fx._shape(kind="flametongue", c=(c[0] + math.cos(an) * rr, c[1] + math.sin(an) * rr * 0.7),
                  v=(0.0, -0.7), h=random.uniform(0.9, 1.3), w=random.uniform(0.35, 0.5),
                  ph=i, cols=FIRE, col=FIRE[1], life=random.uniform(0.5, 0.75),
                  wait=0.04 * (i % 4))
    _tongues(fx, c, 8, r * 0.5, h=0.8, life=(0.4, 0.6))
    _bits(fx, (c[0], c[1] - 0.4), 14, (FIRE[1], FIRE[2], CORE), speed=3.4, life=(0.4, 0.7))
    _shake(fx, 220)


def fx_charfly(fx, e, col):
    """Volo: mirino d'atterraggio durante la carica (rinnovato a ogni tick),
    ali al decollo, schianto all'arrivo."""
    kind = e.get("kind")
    if kind == "zone":
        c = tuple(e.get("c") or ())
        if not c:
            return
        p = float(e.get("t", 0.0))
        for s in fx.shapes:
            if s["kind"] == "charflymark" and s["c"] == c:
                s["life"] = s["maxlife"] = 0.25
                s["p"] = p
                return
        fx._shape(kind="charflymark", c=c, r=float(e.get("radius", 2.6)), p=p, col=FIRE[1],
                  life=0.25)
        return
    if kind == "blink":
        a = e.get("a")
        if a is None:
            return
        fx._shape(kind="charwings", c=tuple(a), w=1.1, col=FIRE[1], life=0.35)
        fx._dust(a, 0.9, n=8, speed=(0.8, 2.0))
        for s in fx.shapes:   # il mirino lascia il posto all'impatto
            if s["kind"] == "charflymark":
                s["life"] = min(s["life"], 0.05)
        return
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.6))
    fx._shape(kind="impactstar", c=(c[0], c[1] - 0.3), r=0.7, n=8, rot=random.uniform(0, 1),
              cols=FIRE, col=FIRE[1], life=0.22)
    fx._shape(kind="groundring", c=tuple(c), r0=0.3, r1=r, cols=FIRE, w=0.09, speed=2.5,
              col=FIRE[1], life=0.45)
    fx._dust(c, r * 0.8, n=12, speed=(1.0, 2.8))
    _tongues(fx, c, 7, r * 0.7, h=0.6, life=(0.3, 0.5))
    _shake(fx, 180)


def fx_charburn(fx, e, col):
    """Scottatura (tre cariche di Calore): vampata sul bersaglio."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="flash", c=(c[0], c[1] - 0.4), r=0.4, col=FIRE[2], life=0.14)
    _tongues(fx, c, 5, 0.35, h=0.6, w=0.3, life=(0.3, 0.5), up=0.8)
    _bits(fx, (c[0], c[1] - 0.5), 6, (FIRE[1], FIRE[2]), speed=1.6)


STYLES = {
    "charember": fx_charember, "charflamethrower": fx_charflamethrower,
    "charheatwave": fx_charheatwave, "charscratch": fx_charscratch,
    "chardragonclaw": fx_chardragonclaw, "charfirespin": fx_charfirespin,
    "charblast": fx_charblast, "charinferno": fx_charinferno, "charfly": fx_charfly,
    "charburn": fx_charburn,
}


# --- disegni persistenti ---------------------------------------------------------------

def draw_blast(surface, camera, pr, now):
    """Palla di Fuocobomba in volo: sfera di fuoco con la stella a cinque bracci
    che gira, coda all'indietro e ombra a terra."""
    ts = config.TILE_SIZE
    p = pr["pos"]
    gx, gy = camera.world_to_screen(p.x * ts, p.y * ts)
    r = max(4.0, pr.get("radius", 0.55) * ts)
    lift = int(0.5 * ts)
    sh = pygame.Rect(0, 0, int(r * 1.6), int(r * 0.6))
    sh.center = (gx, gy + 2)
    pygame.draw.ellipse(surface, (20, 14, 12), sh)
    d = pr.get("dir")
    ang = math.atan2(d.y, d.x) if d is not None else 0.0
    layer = pygame.Surface((int(r * 8), int(r * 8)), pygame.SRCALPHA)
    cx = cy = r * 4
    pygame.draw.circle(layer, (*FIRE[1], 60), (int(cx), int(cy)), int(r * 1.7))
    draw_fireball(layer, cx, cy, r, ang, 255, flick=now * 26, tail=0.9)
    draw_blast_star(layer, cx, cy, r * 1.25, now * 5.0, 230)
    pygame.draw.circle(layer, (*CORE, 255), (int(cx - r * 0.15), int(cy - r * 0.18)), max(1, int(r * 0.3)))
    surface.blit(layer, (gx - cx, gy - lift - cy))


# --- sulle unità ---------------------------------------------------------------------------

def has_heat(u, now) -> bool:
    return getattr(u, "heat_stacks", 0) > 0 and getattr(u, "heat_until", -1.0) > now


def draw_heat_pips(surface, u, gx, top, w, row, now):
    """Calore di Fiammacoda: tre fiammelle sotto la barra della vita (accese
    quante le cariche; alla terza scatta la Scottatura)."""
    n = min(3, int(getattr(u, "heat_stacks", 0)))
    y = top + 7 + row * 7
    for i in range(3):
        draw_flame_pip(surface, gx - 7 + i * 7, y, i < n, now)


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Scottatura: due fiammelle che danzano sul corpo + fumo che sale."""
    if getattr(u, "burn_until", -1.0) <= now:
        return
    r = int(getattr(u, "radius", 0.5) * ts)
    for k, (dx, dy) in enumerate(((-0.45, -0.5), (0.4, -0.9))):
        h = 8 + 3 * math.sin(now * 13 + k * 2.1)
        draw_flame(surface, gx + dx * r, gy + dy * r, h, 6, 255, FIRE)
    ph = (now * 1.6) % 1.0
    for k in range(2):
        q = (ph + k * 0.5) % 1.0
        y = int(gy - r * 1.6 - q * 10)
        surface.fill((70, 64, 64) if q < 0.6 else (110, 104, 104),
                     pygame.Rect(gx - 2 + k * 4 + int(math.sin(q * 6) * 2), y, 2, 2))
