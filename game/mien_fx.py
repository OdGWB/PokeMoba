"""Grafica della linea Mienfoo > Mienshao: effetti istantanei (handler
registrati in FXSystem._FX_STYLES), forme nuove per FXSystem._draw_shapes
(manica a frusta che schiocca, palmo di Bruciapelo, occhio di Individua,
stellina del punto dolce, nastri che girano, lucchetto) e disegni persistenti
letti dallo stato del Match a ogni frame (mirino d'atterraggio di
Calcinvolo), sulle unità (guardia di Individua, nastri della Danza, oggetti
disattivati, Rigenergia, brutto colpo pronto), attorno al proprio Pokémon
(fascia del punto dolce) e nell'interfaccia.

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

SLEEVE = (196, 160, 232)       # maniche di Mienshao (lavanda)
SLEEVE_HI = (250, 242, 255)
SLEEVE_DK = (64, 34, 104)
PINK = (236, 120, 180)         # bordi delle maniche
GOLD = (255, 212, 84)          # punto dolce
GOLD_HI = (255, 250, 200)
GOLD_DK = (150, 92, 20)
FIGHT = (240, 132, 60)
FIGHT_HI = (255, 230, 160)
FIGHT_DK = (110, 40, 14)
PARRY = (170, 226, 255)
PARRY_HI = (255, 255, 255)
PARRY_DK = (30, 70, 120)
DARK = (110, 76, 160)
DARK_HI = (214, 190, 255)
DARK_DK = (26, 16, 44)
HEAL = (110, 230, 130)
RED = (236, 70, 60)
WHITE = (255, 255, 255)
DUST = (176, 160, 130)

MIEN_DEX = (619, 620)


def _al(f, k=2.0):
    return int(255 * max(0.0, min(1.0, f * k)))


def _rot(px, py, ca, sa):
    return px * ca - py * sa, px * sa + py * ca


def is_mien(u) -> bool:
    return getattr(u, "dex", 0) in MIEN_DEX


# --- forme per FXSystem._draw_shapes --------------------------------------------

SHAPES = ("sleeve", "palm", "eye", "twinkle", "ribbons", "padlock")


def _ribbon(overlay, pts, w0, cols, al):
    """Nastro affusolato lungo `pts` (largo w0 alla base, a punta in cima)."""
    n = len(pts)
    if n < 2:
        return
    for layer, (col, extra) in enumerate(((cols[0], 1.6), (cols[1], 0.0))):
        for i in range(n - 1):
            k = 1.0 - i / (n - 1)
            w = max(1, int(w0 * (0.35 + 0.65 * k) + extra))
            pygame.draw.line(overlay, (*col, al), pts[i], pts[i + 1], w)
    for i in range(0, n - 2, 2):   # filo di luce in alto
        pygame.draw.line(overlay, (*cols[2], al), (pts[i][0], pts[i][1] - 1),
                         (pts[i + 1][0], pts[i + 1][1] - 1), 1)


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "sleeve":
        # Manica che schiocca da A verso B: la punta corre in fretta, il nastro
        # ondeggia (sinusoide che si smorza verso la punta), poi sbiadisce.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        L = math.hypot(bx - ax, by - ay)
        if L < 2:
            return
        ux, uy = (bx - ax) / L, (by - ay) / L
        nx, ny = uy, -ux
        reach = min(1.0, t / 0.35)
        amp = s.get("amp", 0.3) * ts * (1.0 - 0.35 * reach)
        side = s.get("side", 1)
        cols = s.get("cols", (SLEEVE_DK, SLEEVE, SLEEVE_HI))
        n = 16
        pts = []
        for i in range(n + 1):
            u = i / n * reach
            wv = math.sin(u * math.pi * 3.0 - t * 14.0) * amp * math.sin(math.pi * min(1.0, u * 1.4)) * side
            pts.append((ax + ux * L * u + nx * wv, ay + uy * L * u + ny * wv))
        _ribbon(overlay, pts, s.get("w", 0.11) * ts, cols, _al(f, 2.4))
        cuff = s.get("cuff", PINK)   # bordo della manica sulla punta
        if cuff is not None and len(pts) > 3:
            pygame.draw.lines(overlay, (*cuff, _al(f, 2.4)), False, pts[-3:], max(2, int(0.07 * ts)))
        if reach >= 1.0 and t < 0.5:   # schiocco: tre trattini sulla punta
            tip = pts[-1]
            for k in (-1, 0, 1):
                aa = math.atan2(uy, ux) + k * 0.7
                pygame.draw.line(overlay, (*cols[2], _al(f, 2.4)), tip,
                                 (tip[0] + math.cos(aa) * ts * 0.22, tip[1] + math.sin(aa) * ts * 0.22), 1)
    elif kind == "palm":
        # Palmo aperto (Bruciapelo) che scatta in avanti e si schiaccia sul bersaglio.
        cx, cy = S(*s["c"])
        ang = s.get("ang", 0.0)
        ca, sa = math.cos(ang), math.sin(ang)
        sc = s.get("size", 0.42) * ts * (0.7 + 0.5 * min(1.0, t / 0.25))
        cols = s.get("cols", (FIGHT_DK, (255, 226, 190), WHITE))
        al = _al(f, 2.4)

        def P(px, py):
            x, y = _rot(px * sc, py * sc, ca, sa)
            return (cx + x, cy + y)

        palm = [P(-0.5, -0.45), P(0.15, -0.5), P(0.25, 0.45), P(-0.5, 0.45)]
        fingers = [((0.15, -0.4), (0.75, -0.42)), ((0.2, -0.13), (0.88, -0.13)),
                   ((0.2, 0.13), (0.84, 0.15)), ((0.15, 0.38), (0.66, 0.42))]
        thumb = ((-0.3, -0.45), (0.05, -0.85))
        fw = max(2, int(sc * 0.24))
        for (p0, p1) in fingers + [thumb]:
            pygame.draw.line(overlay, (*cols[0], al), P(*p0), P(*p1), fw + 3)
        pygame.draw.polygon(overlay, (*cols[0], al), palm)
        pygame.draw.polygon(overlay, (*cols[0], al), palm, 3)
        for (p0, p1) in fingers + [thumb]:
            pygame.draw.line(overlay, (*cols[1], al), P(*p0), P(*p1), fw)
        pygame.draw.polygon(overlay, (*cols[1], al), palm)
        pygame.draw.line(overlay, (*cols[2], al), P(-0.4, -0.35), P(0.05, -0.38), 1)
    elif kind == "eye":
        # Occhio di Individua: si apre di scatto, la pupilla brilla, si richiude.
        cx, cy = S(*s["c"])
        R = s.get("r", 0.4) * ts
        open_ = math.sin(math.pi * min(1.0, t)) ** 0.5
        h = max(1.0, R * 0.55 * open_)
        cols = s.get("cols", (PARRY_DK, PARRY, PARRY_HI))
        al = _al(f, 3.0)
        top = [(cx - R + 2 * R * i / 10, cy - math.sin(math.pi * i / 10) * h) for i in range(11)]
        bot = [(cx + R - 2 * R * i / 10, cy + math.sin(math.pi * i / 10) * h) for i in range(11)]
        pygame.draw.polygon(overlay, (*cols[2], al), top + bot)
        pygame.draw.polygon(overlay, (*cols[0], al), top + bot, 2)
        if h > 2:
            pr = max(1, int(min(h, R * 0.4)))
            pygame.draw.circle(overlay, (*cols[1], al), (int(cx), int(cy)), pr)
            pygame.draw.circle(overlay, (*cols[0], al), (int(cx), int(cy)), max(1, pr // 2))
            pygame.draw.rect(overlay, (*WHITE, al), pygame.Rect(int(cx - pr * 0.6), int(cy - pr * 0.6), 2, 2))
    elif kind == "twinkle":
        # Stellina a 4 punte del punto dolce (si allarga e ruota un poco).
        cx, cy = S(*s["c"])
        r = s.get("r", 0.3) * ts * (0.5 + 0.7 * min(1.0, t * 4))
        rot = s.get("rot", 0.0) + t * 1.5
        cols = s.get("cols", (GOLD_DK, GOLD, GOLD_HI))
        al = _al(f, 2.5)
        pts = []
        for i in range(8):
            rr = r if i % 2 == 0 else r * 0.28
            aa = rot + i * math.pi / 4
            pts.append((cx + math.cos(aa) * rr, cy + math.sin(aa) * rr))
        pygame.draw.polygon(overlay, (*cols[0], al), pts)
        inner = [(cx + (x - cx) * 0.72, cy + (y - cy) * 0.72) for x, y in pts]
        pygame.draw.polygon(overlay, (*cols[1], al), inner)
        pygame.draw.circle(overlay, (*cols[2], al), (int(cx), int(cy)), max(1, int(r * 0.18)))
    elif kind == "ribbons":
        # Nastri che girano attorno a un centro (Danza delle Maniche): archi
        # schiacciati in prospettiva che si allargano.
        cx, cy = S(*s["c"])
        R = (s["r0"] + (s["r1"] - s["r0"]) * min(1.0, t * s.get("speed", 1.6))) * ts
        n = s.get("n", 3)
        spin = s.get("spin", 6.0)
        cols = s.get("cols", (SLEEVE_DK, SLEEVE, SLEEVE_HI))
        al = _al(f, 2.0)
        for k in range(n):
            a0 = k * math.tau / n + t * spin
            pts = []
            for i in range(9):
                aa = a0 + i * 0.16
                rr = R * (0.75 + 0.25 * i / 8)
                pts.append((cx + math.cos(aa) * rr, cy + math.sin(aa) * rr * 0.5 - s.get("lift", 0.3) * ts))
            _ribbon(overlay, pts[::-1], s.get("w", 0.12) * ts, cols, al)
    elif kind == "padlock":
        # Lucchetto sopra il bersaglio (Privazione: oggetti spenti).
        cx, cy = S(*s["c"])
        sc = max(2, int(s.get("size", 0.12) * ts))
        al = _al(f, 2.5)
        cy -= int(t * 0.3 * ts)
        body = pygame.Rect(int(cx - sc * 1.6), int(cy - sc), sc * 3 + 1, int(sc * 2.4))
        pygame.draw.circle(overlay, (*DARK_DK, al), (int(cx), int(cy - sc)), sc * 1 + 2, 3)
        pygame.draw.circle(overlay, (*DARK_HI, al), (int(cx), int(cy - sc)), sc, 1)
        pygame.draw.rect(overlay, (*DARK_DK, al), body.inflate(3, 3))
        pygame.draw.rect(overlay, (*DARK, al), body)
        pygame.draw.line(overlay, (*DARK_HI, al), body.topleft, body.topright, 1)
        pygame.draw.rect(overlay, (*DARK_DK, al), pygame.Rect(int(cx - 1), int(cy), 2, max(2, sc)))


# --- handler degli eventi (FXSystem._FX_STYLES) --------------------------------


def _ab(e):
    a, b = e.get("a"), e.get("b")
    return (a, b) if a is not None and b is not None else None


def _bits(fx, c, n, cols, speed=2.0, life=(0.2, 0.4), size=1, up=0.0):
    for _ in range(n):
        a = random.uniform(0, math.tau)
        v = random.uniform(0.4, 1.0) * speed
        fx._add(c[0], c[1], math.cos(a) * v, math.sin(a) * v - up, random.uniform(*life),
                random.choice(cols), size)


def fx_sleevewhip(fx, e, col):
    """Attacco base: una manica schiocca dal busto al bersaglio."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="sleeve", a=(a[0], a[1] - 0.35), b=(b[0], b[1] - 0.3),
              side=random.choice((-1, 1)), col=SLEEVE, life=0.26)
    fx._shape(kind="flash", c=(b[0], b[1] - 0.3), r=0.12, col=SLEEVE_HI, life=0.07, wait=0.08)


def fx_sweetspot(fx, e, col):
    """Punto dolce: stellina d'oro che brilla sul bersaglio + scintille."""
    ab = _ab(e)
    if ab is None:
        return
    _, b = ab
    c = (b[0] + 0.35, b[1] - 1.05)
    fx._shape(kind="twinkle", c=c, r=0.32, rot=random.uniform(0, 0.8), col=GOLD, life=0.38)
    fx._shape(kind="ring", c=(b[0], b[1] - 0.3), r0=0.15, r1=0.6, col=GOLD, life=0.22, wd=0.05)
    _bits(fx, c, 6, (GOLD, GOLD_HI), speed=1.8)


def fx_detectcrit(fx, e, col):
    """Brutto colpo garantito dopo una parata: grande stella arancio."""
    ab = _ab(e)
    if ab is None:
        return
    _, b = ab
    c = (b[0], b[1] - 0.35)
    fx._shape(kind="impactstar", c=c, r=0.55, rot=random.uniform(0, 1), n=8, col=FIGHT,
              life=0.26, cols=(FIGHT_DK, RED, FIGHT_HI))
    fx._shape(kind="flash", c=c, r=0.35, col=FIGHT_HI, life=0.1)
    _bits(fx, c, 10, (FIGHT, FIGHT_HI, RED), speed=2.6)


def fx_jumpkick(fx, e, col):
    """Calcinvolo (stacco): polvere ai piedi e linee di velocità verso l'arrivo."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._dust(a, 0.5, n=8)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 1e-6:
        return
    nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
    for k in range(3):
        off = (k - 1) * 0.18
        fx._shape(kind="windline", a=(a[0] + nx * off, a[1] + ny * off - 0.6),
                  b=(b[0] + nx * off, b[1] + ny * off - 0.6), col=SLEEVE_HI, life=0.3 + 0.04 * k)


def fx_jumpkickhit(fx, e, col):
    """Calcinvolo a segno: stella d'impatto, onda a terra, sassi, lampo."""
    c = e.get("c")
    if c is None:
        return
    tg = e.get("t") or c
    top = ((c[0] + tg[0]) / 2, (c[1] + tg[1]) / 2 - 0.45)
    fx._shape(kind="impactstar", c=top, r=0.6, rot=random.uniform(0, 1), n=7, col=FIGHT,
              life=0.28, cols=(FIGHT_DK, FIGHT, FIGHT_HI))
    fx._shape(kind="flash", c=top, r=0.45, col=FIGHT_HI, life=0.1)
    fx._shape(kind="groundring", c=c, r0=0.3, r1=float(e.get("radius", 1.0)) + 0.4, col=FIGHT,
              life=0.4)
    for k in range(5):
        an = k / 5 * math.tau + random.uniform(-0.3, 0.3)
        fx._shape(kind="pebble", c=c, v=(math.cos(an) * 1.0, math.sin(an) * 0.5), h=0.4,
                  sz=0.06, col=DUST, life=0.42)
    _bits(fx, top, 10, (FIGHT, FIGHT_HI, WHITE), speed=3.0)


def fx_jumpkickcrash(fx, e, col):
    """Calcinvolo a vuoto: si schianta. Crepe, nube di polvere, stelline di dolore."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="groundcrack", c=c, r=0.9, n=5, seed=random.randint(0, 9999), col=DUST,
              life=0.8)
    fx._dust(c, 0.8, n=14)
    for k in range(3):
        an = k / 3 * math.tau
        fx._shape(kind="twinkle", c=(c[0] + math.cos(an) * 0.35, c[1] - 0.9 + math.sin(an) * 0.15),
                  r=0.16, rot=an, col=(255, 236, 120), life=0.5, wait=0.05 * k,
                  cols=((120, 90, 20), (255, 236, 120), WHITE))
    fx._shape(kind="flash", c=(c[0], c[1] - 0.3), r=0.3, col=RED, life=0.12)


def fx_jumpkickmiss(fx, e, col):
    """Calcio Controllato a vuoto: atterraggio pulito, solo un po' di polvere."""
    c = e.get("c")
    if c is not None:
        fx._dust(c, 0.4, n=6)


def fx_detect(fx, e, col):
    """Individua: occhio che si apre sopra Mienshao + anello di guardia
    (largo come la Guardia Rapida, se c'è)."""
    c = e.get("c")
    if c is None:
        return
    life = max(0.18, float(e.get("win", 0.5)))
    fx._shape(kind="eye", c=(c[0], c[1] - 1.3), r=0.36, col=PARRY, life=life + 0.15)
    r = float(e.get("radius", 0.8))
    fx._shape(kind="ring", c=c, r0=r, r1=r * 0.85, col=PARRY, life=life, wd=0.05)
    if r > 1.5:   # Guardia Rapida: seconda corona più tenue
        fx._shape(kind="ring", c=c, r0=0.6, r1=r, col=PARRY_HI, life=life, wd=0.04)


def fx_parry(fx, e, col):
    """Parata riuscita: scintilla di metallo bianco-azzurra tra i due."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(a[0] - b[0], a[1] - b[1]) or 1.0
    c = (b[0] + (a[0] - b[0]) / L * 0.45, b[1] + (a[1] - b[1]) / L * 0.45 - 0.4)
    fx._shape(kind="impactstar", c=c, r=0.45, rot=random.uniform(0, 1), n=4, col=PARRY,
              life=0.24, cols=(PARRY_DK, PARRY, PARRY_HI))
    fx._shape(kind="flash", c=c, r=0.3, col=PARRY_HI, life=0.08)
    fx._shape(kind="eye", c=(b[0], b[1] - 1.3), r=0.3, col=PARRY, life=0.3,
              cols=(FIGHT_DK, FIGHT, FIGHT_HI))
    _bits(fx, c, 10, (PARRY, PARRY_HI, WHITE), speed=3.2, life=(0.12, 0.3))


def fx_counter(fx, e, col):
    """Contrattacco: l'attaccante viene respinto (scia + polvere all'arrivo)."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="windline", a=(a[0], a[1] - 0.3), b=(b[0], b[1] - 0.3), col=FIGHT_HI, life=0.3)
    fx._shape(kind="sleeve", a=(a[0], a[1] - 0.3), b=(b[0], b[1] - 0.3), side=1,
              col=SLEEVE, life=0.3, amp=0.12)
    fx._dust(b, 0.5, n=8)


def fx_quickguard(fx, e, col):
    """Guardia Rapida: scudo esagonale che compare sull'alleato protetto."""
    ab = _ab(e)
    if ab is None:
        return
    _, b = ab
    fx._shape(kind="hexshell", c=(b[0], b[1] - 0.35), r=0.55, col=PARRY, life=0.32)
    fx._shape(kind="flash", c=(b[0], b[1] - 0.35), r=0.25, col=PARRY_HI, life=0.08)


def _fakeout(fx, e, cols, dark=False):
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    if e.get("miss"):   # a vuoto: solo lo spostamento d'aria
        fx._shape(kind="windline", a=(a[0], a[1] - 0.3), b=(b[0], b[1] - 0.3), col=cols[2],
                  life=0.2)
        return
    c = (b[0] - math.cos(ang) * 0.25, b[1] - math.sin(ang) * 0.25 - 0.4)
    fx._shape(kind="sleeve", a=(a[0], a[1] - 0.35), b=c, side=1, col=SLEEVE, life=0.2, amp=0.12)
    if e.get("stun"):   # stordimento: scoppio giallo + anello (sotto il palmo)
        fx._shape(kind="impactstar", c=(b[0], b[1] - 0.45), r=0.5, rot=ang, n=6, col=GOLD,
                  life=0.3, cols=(GOLD_DK, GOLD, GOLD_HI))
        fx._shape(kind="ring", c=(b[0], b[1] - 0.2), r0=0.2, r1=0.9, col=GOLD, life=0.3, wd=0.06)
        _bits(fx, (b[0], b[1] - 0.45), 12, (GOLD, GOLD_HI, WHITE), speed=3.0)
    else:
        fx._shape(kind="flash", c=(b[0], b[1] - 0.4), r=0.2, col=cols[2], life=0.08)
    fx._shape(kind="palm", c=c, ang=ang, size=0.42 if e.get("stun") else 0.34, col=cols[1],
              life=0.3, cols=cols)
    if dark:
        _bits(fx, (b[0], b[1] - 0.45), 8, (DARK, DARK_HI), speed=2.0)


def fx_fakeout(fx, e, col):
    _fakeout(fx, e, (FIGHT_DK, (255, 226, 190), WHITE))


def fx_fakeoutdark(fx, e, col):
    """Privazione: palmo buio e lucchetto sugli oggetti del bersaglio."""
    _fakeout(fx, e, (DARK_DK, (160, 118, 220), DARK_HI), dark=True)


def fx_sleevedance(fx, e, col):
    """Danza delle Maniche (inizio): nastri che si aprono a spirale."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ribbons", c=c, r0=0.3, r1=1.2, n=3, spin=7.0, col=SLEEVE, life=0.6)
    fx._shape(kind="ribbons", c=c, r0=0.2, r1=0.9, n=2, spin=-6.0, col=PINK, life=0.5,
              cols=((110, 30, 70), PINK, (255, 220, 236)), lift=0.6)


def fx_dancestep(fx, e, col):
    """Un passo della danza: nastri brevi, più numerosi al secondo passo."""
    c = e.get("c")
    if c is None:
        return
    n = int(e.get("n", 1))
    fx._shape(kind="ribbons", c=c, r0=0.4, r1=0.9, n=n + 1, spin=9.0, col=SLEEVE, life=0.35)


def fx_dancebreak(fx, e, col):
    """Danza interrotta: pezzi di nastro grigi che cadono."""
    c = e.get("c")
    if c is None:
        return
    _bits(fx, (c[0], c[1] - 0.6), 12, ((150, 140, 160), (110, 100, 120)), speed=1.6, up=-0.5,
          size=2)


def fx_dancefinale(fx, e, col):
    """Colpo finale della danza: vortice di nastri, onda a terra, stelle d'impatto."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.6))
    fx._shape(kind="ribbons", c=c, r0=0.4, r1=r, n=6, spin=10.0, col=SLEEVE, life=0.6, w=0.16)
    fx._shape(kind="ribbons", c=c, r0=0.3, r1=r * 0.7, n=4, spin=-8.0, col=PINK, life=0.5,
              cols=((110, 30, 70), PINK, (255, 220, 236)), lift=0.7)
    fx._shape(kind="groundring", c=c, r0=0.4, r1=r, col=FIGHT, life=0.5)
    for k in range(5):
        an = k / 5 * math.tau + random.uniform(-0.2, 0.2)
        p = (c[0] + math.cos(an) * r * 0.65, c[1] + math.sin(an) * r * 0.4 - 0.35)
        fx._shape(kind="impactstar", c=p, r=0.4, rot=an, n=6, col=FIGHT, life=0.3,
                  wait=0.05 * k, cols=(FIGHT_DK, FIGHT, FIGHT_HI))
    fx._shape(kind="flash", c=(c[0], c[1] - 0.4), r=0.8, col=SLEEVE_HI, life=0.12)


def fx_reversal(fx, e, col):
    """Contropiede: calcio rotante; più è disperato, più è rosso e grande."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    k = max(0.0, min(1.0, (float(e.get("mult", 1.0)) - 1.0) / 2.0))
    hot = tuple(int(FIGHT[i] + (RED[i] - FIGHT[i]) * k) for i in range(3))
    hcols = (FIGHT_DK, hot, FIGHT_HI)
    c = (b[0], b[1] - 0.4)
    for side in (-1, 1):   # le due maniche frustano insieme
        fx._shape(kind="sleeve", a=(a[0], a[1] - 0.4), b=c, side=side, col=hot, life=0.28,
                  amp=0.35, w=0.12 + 0.04 * k, cols=hcols, cuff=WHITE)
    if e.get("miss"):
        return
    fx._shape(kind="flash", c=c, r=0.25 + 0.15 * k, col=FIGHT_HI, life=0.08, wait=0.06)
    fx._shape(kind="impactstar", c=c, r=0.5 + 0.35 * k, rot=random.uniform(0, 1), n=7, col=hot,
              life=0.32, wait=0.06, cols=hcols)
    fx._shape(kind="groundring", c=b, r0=0.2, r1=0.8 + 0.6 * k, col=hot, life=0.35, wait=0.06)
    _bits(fx, c, int(8 + 10 * k), (hot, FIGHT_HI, WHITE), speed=2.4 + 1.6 * k)


STYLES = {
    "sleevewhip": fx_sleevewhip, "sweetspot": fx_sweetspot, "detectcrit": fx_detectcrit,
    "jumpkick": fx_jumpkick, "jumpkickhit": fx_jumpkickhit, "jumpkickcrash": fx_jumpkickcrash,
    "jumpkickmiss": fx_jumpkickmiss, "detect": fx_detect, "parry": fx_parry,
    "counter": fx_counter, "quickguard": fx_quickguard, "fakeout": fx_fakeout,
    "fakeoutdark": fx_fakeoutdark, "sleevedance": fx_sleevedance, "dancestep": fx_dancestep,
    "dancebreak": fx_dancebreak, "dancefinale": fx_dancefinale, "reversal": fx_reversal,
}


# --- disegni persistenti (stato del Match) -------------------------------------


def draw_jump(surface, camera, lp, now):
    """Calcinvolo in volo: mirino d'atterraggio (area d'impatto) che si chiude."""
    ts = config.TILE_SIZE
    c = lp["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    span = max(1e-6, lp["end"] - lp["start"])
    prog = max(0.0, min(1.0, (now - lp["start"]) / span))
    R = int(lp.get("radius", 1.0) * ts)
    g = pygame.Surface((R * 2 + 6, R + 6), pygame.SRCALPHA)
    o = (R + 3, R // 2 + 3)
    rect = pygame.Rect(o[0] - R, o[1] - R // 2, R * 2, R)
    pygame.draw.ellipse(g, (*FIGHT_DK, int(50 + 70 * prog)), rect)
    pygame.draw.ellipse(g, (*FIGHT, 230), rect, 2)
    ir = max(2, int(R * (1.0 - prog)))
    pygame.draw.ellipse(g, (*FIGHT_HI, 230), pygame.Rect(o[0] - ir, o[1] - ir // 2, ir * 2, ir), 1)
    for k in range(4):   # quattro tacche
        aa = k * math.pi / 2 + math.pi / 4
        x0, y0 = o[0] + math.cos(aa) * R * 0.7, o[1] + math.sin(aa) * R * 0.35
        x1, y1 = o[0] + math.cos(aa) * R * 1.0, o[1] + math.sin(aa) * R * 0.5
        pygame.draw.line(g, (*FIGHT_HI, 230), (x0, y0), (x1, y1), 2)
    surface.blit(g, (cx - o[0], cy - o[1]))


# --- attorno al proprio Pokémon: fascia del punto dolce -------------------------

_ring_cache: dict = {}


def draw_sweet_ring(surface, u, gx, gy, ts):
    """Fascia del punto dolce attorno al proprio Mienfoo/Mienshao: dal 70% al
    100% della portata degli attacchi base (misurata dal bordo del bersaglio,
    quindi qui un filo più larga del cerchio di gittata)."""
    if not is_mien(u) or not getattr(u, "alive", True):
        return
    # dalla forma (online l'entità non porta la portata vera)
    reach = 1.5 if u.dex == 619 else 2.1
    if "zoom_lens" in getattr(u, "items", ()):
        reach *= 1.15
    own = getattr(u, "radius", 0.35)   # portata da bordo a bordo: + il proprio raggio
    reach += own
    key = int(reach * ts)
    surf = _ring_cache.get(key)
    if surf is None:
        R = int((reach + 0.35) * ts)
        r = int(((reach - own) * 0.7 + own + 0.35) * ts)
        surf = pygame.Surface((R * 2 + 4, R * 2 + 4), pygame.SRCALPHA)
        o = (R + 2, R + 2)
        pygame.draw.circle(surf, (*GOLD, 34), o, R)
        pygame.draw.circle(surf, (0, 0, 0, 0), o, r)
        pygame.draw.circle(surf, (*GOLD, 150), o, R, 1)
        for i in range(0, 48, 2):   # bordo interno tratteggiato
            a0, a1 = i / 48 * math.tau, (i + 1) / 48 * math.tau
            pygame.draw.line(surf, (*GOLD_HI, 110),
                             (o[0] + math.cos(a0) * r, o[1] + math.sin(a0) * r),
                             (o[0] + math.cos(a1) * r, o[1] + math.sin(a1) * r), 1)
        _ring_cache[key] = surf
    surface.blit(surf, (gx - surf.get_width() // 2, gy - surf.get_height() // 2))


# --- sulle unità --------------------------------------------------------------


def draw_unit_under(surface, u, gx, gy, now, ts):
    """Sotto lo sprite: guardia di Individua (anello chiaro con raggi) e nastri
    della Danza delle Maniche. Visibili a tutti: si vede quando para."""
    if getattr(u, "parry_until", -1.0) > now:
        r = int(0.75 * ts)
        g = pygame.Surface((r * 2 + 6, r + 6), pygame.SRCALPHA)
        o = (r + 3, r // 2 + 3)
        pygame.draw.ellipse(g, (*PARRY, 70), pygame.Rect(o[0] - r, o[1] - r // 2, r * 2, r))
        pygame.draw.ellipse(g, (*PARRY_HI, 230), pygame.Rect(o[0] - r, o[1] - r // 2, r * 2, r), 2)
        for k in range(4):
            aa = now * 6.0 + k * math.pi / 2
            x0, y0 = o[0] + math.cos(aa) * r, o[1] + math.sin(aa) * r / 2
            pygame.draw.line(g, (*PARRY_HI, 230), (x0, y0),
                             (o[0] + math.cos(aa) * (r + 3), o[1] + math.sin(aa) * (r + 3) / 2 - 3), 2)
        surface.blit(g, (gx - o[0], gy - o[1]))
    if getattr(u, "dance_until", -1.0) > now:
        R = 0.8 * ts
        for k in range(2):   # due nastri in orbita, davanti e dietro
            pts = []
            for i in range(8):
                aa = now * 5.0 + k * math.pi + i * 0.18
                pts.append((gx + math.cos(aa) * R, gy - 0.5 * ts + math.sin(aa) * R * 0.45))
            col = SLEEVE if k == 0 else PINK
            pygame.draw.lines(surface, SLEEVE_DK, False, pts, 4)
            pygame.draw.lines(surface, col, False, pts, 2)


def draw_padlock(surface, x, y):
    """Oggetti disattivati: lucchetto pixel art 7x8."""
    pygame.draw.rect(surface, DARK_DK, pygame.Rect(x - 4, y - 1, 9, 7))
    pygame.draw.rect(surface, DARK, pygame.Rect(x - 3, y, 7, 5))
    pygame.draw.line(surface, DARK_HI, (x - 3, y), (x + 3, y))
    pygame.draw.rect(surface, DARK_DK, pygame.Rect(x - 3, y - 5, 7, 5), 2)
    pygame.draw.rect(surface, DARK_HI, pygame.Rect(x - 2, y - 4, 5, 4), 1)
    pygame.draw.rect(surface, DARK_DK, pygame.Rect(x, y + 1, 1, 3))


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Sopra lo sprite: lucchetto (oggetti disattivati) a destra della barra
    della vita, crocette verdi di Rigenergia, scintilla del brutto colpo pronto."""
    r = int(getattr(u, "radius", 0.5) * ts)
    top = gy - 2 * r - 8
    w = max(14, r * 2)
    if getattr(u, "itemlock_until", -1.0) > now:
        draw_padlock(surface, gx + w // 2 + 6, top + 1)
    if getattr(u, "mien_regen", False) and u.hp < u.max_hp:
        for k in range(3):   # crocette che salgono
            ph = (now * 0.8 + k / 3) % 1.0
            x = gx + (r + 3) * (1 if k % 2 else -1) + int(math.sin(k * 2.1 + now) * 2)
            y = gy - int(0.3 * ts + ph * 1.1 * ts)
            c = HEAL if ph < 0.7 else (70, 150, 90)
            pygame.draw.rect(surface, (20, 60, 30), pygame.Rect(x - 2, y - 1, 5, 3))
            pygame.draw.rect(surface, (20, 60, 30), pygame.Rect(x - 1, y - 2, 3, 5))
            pygame.draw.line(surface, c, (x - 1, y), (x + 1, y))
            pygame.draw.line(surface, c, (x, y - 1), (x, y + 1))
    if getattr(u, "mien_crit_until", -1.0) > now:
        pulse = 0.5 + 0.5 * math.sin(now * 12.0)
        x, y = gx + r, gy - int(r * 1.3)
        s = 3 + int(2 * pulse)
        pygame.draw.line(surface, FIGHT_DK, (x - s - 1, y), (x + s + 1, y), 3)
        pygame.draw.line(surface, FIGHT_DK, (x, y - s - 1), (x, y + s + 1), 3)
        pygame.draw.line(surface, FIGHT_HI, (x - s, y), (x + s, y), 1)
        pygame.draw.line(surface, FIGHT_HI, (x, y - s), (x, y + s), 1)


# --- interfaccia ------------------------------------------------------------------


def draw_hand_icon(surface, cx, cy, s, col, dark):
    """Palmo aperto (Bruciapelo) per l'interfaccia."""
    palm = pygame.Rect(cx - s // 2, cy - s // 4, s, s // 2 + s // 4)
    for k in range(4):
        x = cx - s // 2 + 1 + k * (s // 4)
        pygame.draw.line(surface, dark, (x, cy - s // 4), (x, cy - s + (k in (1, 2)) * -2), 4)
    pygame.draw.line(surface, dark, (cx - s // 2, cy), (cx - s, cy - s // 3), 4)
    pygame.draw.rect(surface, dark, palm.inflate(2, 2))
    for k in range(4):
        x = cx - s // 2 + 1 + k * (s // 4)
        pygame.draw.line(surface, col, (x, cy - s // 4), (x, cy - s + (k in (1, 2)) * -2), 2)
    pygame.draw.line(surface, col, (cx - s // 2, cy), (cx - s, cy - s // 3), 2)
    pygame.draw.rect(surface, col, palm)
