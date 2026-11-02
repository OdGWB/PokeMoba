"""Grafica della linea Duraludon > Archaludon: effetti istantanei (handler
registrati in FXSystem._FX_STYLES), forme nuove per FXSystem._draw_shapes
(palla d'acciaio in volo, fulmine dal cielo, anello elettrico che crepita,
raggio di Elettroraggio), disegni persistenti letti dallo stato del Match a
ogni frame (area di Tuononda in arrivo, carica di Elettroraggio con la mira,
bersagli di Tuono), sulle unità (scintille di Conduzione, carica di Att.
Sp., fulmini rimasti) e mirino (Tiro Lungo che si allunga).

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra. Lo schermo che trema è il blit della
scena spostato di 1-2 px (draw_shake), non uno scaling.
"""
from __future__ import annotations

import math
import random

import pygame

import config

STEEL = (196, 206, 222)        # acciaio di Duraludon
STEEL_HI = (255, 255, 255)
STEEL_DK = (54, 62, 84)
ELEC = (255, 222, 72)          # Elettro
ELEC_HI = (255, 255, 214)
ELEC_DK = (120, 84, 10)
DRAGON = (92, 120, 232)        # coda (Drago)
DRAGON_HI = (190, 214, 255)
DRAGON_DK = (24, 34, 96)
RAIN = (120, 190, 255)

ARCH_DEX = (884, 1018)


def _al(f, k=2.0):
    return int(255 * max(0.0, min(1.0, f * k)))


def is_arch(u) -> bool:
    return getattr(u, "dex", 0) in ARCH_DEX


def _zigzag(a, b, seg_len, jag, rnd=random):
    """Polilinea spezzata da a a b (schermo), punti interni spostati di ±jag."""
    ax, ay = a
    bx, by = b
    L = math.hypot(bx - ax, by - ay)
    if L < 1:
        return [a, b]
    px, py = -(by - ay) / L, (bx - ax) / L
    n = max(2, int(L / max(2.0, seg_len)) + 1)
    pts = []
    for i in range(n + 1):
        u = i / n
        j = 0.0 if i in (0, n) else rnd.uniform(-jag, jag)
        pts.append((ax + (bx - ax) * u + px * j, ay + (by - ay) * u + py * j))
    return pts


def _bolt_lines(overlay, pts, w, al, cols=(ELEC_DK, ELEC, ELEC_HI)):
    """Saetta a tre strati: alone scuro, corpo giallo, nucleo chiaro."""
    pygame.draw.lines(overlay, (*cols[0], al // 2), False, pts, max(3, int(w * 2.2)))
    pygame.draw.lines(overlay, (*cols[1], al), False, pts, max(2, int(w)))
    pygame.draw.lines(overlay, (*cols[2], al), False, pts, max(1, int(w * 0.4)))


# --- forme per FXSystem._draw_shapes --------------------------------------------

SHAPES = ("steelball", "zigbolt", "sparkring", "railbeam")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "steelball":
        # Palla d'acciaio da A a B: vola nel primo tratto di vita con una scia
        # argentata a tre strati, poi sparisce (l'impatto lo disegna lo stile).
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        fly = s.get("fly", 0.7)
        u = min(1.0, t / fly)
        if u >= 1.0:
            return
        hx, hy = ax + (bx - ax) * u, ay + (by - ay) * u
        tail = max(0.0, u - s.get("trail", 0.25))
        tx, ty = ax + (bx - ax) * tail, ay + (by - ay) * tail
        r = max(2, int(s.get("r", 0.2) * ts))
        cols = s.get("cols", (STEEL_DK, STEEL, STEEL_HI))
        pygame.draw.line(overlay, (*cols[0], 150), (tx, ty), (hx, hy), r * 2)
        pygame.draw.line(overlay, (*cols[1], 200), (tx, ty), (hx, hy), max(1, r))
        pygame.draw.line(overlay, (*cols[2], 230), ((tx + hx) / 2, (ty + hy) / 2), (hx, hy),
                         max(1, r // 2))
        pygame.draw.circle(overlay, (*cols[0], 255), (int(hx), int(hy)), r + 1)
        pygame.draw.circle(overlay, (*cols[1], 255), (int(hx), int(hy)), r)
        pygame.draw.circle(overlay, (*cols[2], 255), (int(hx - r * 0.35), int(hy - r * 0.35)),
                           max(1, r // 2))
        if s.get("spark"):   # Tiro Lungo carico: scintille gialle attorno alla testa
            for k in range(3):
                an = random.uniform(0, math.tau)
                pygame.draw.line(overlay, (*ELEC, 230), (hx, hy),
                                 (hx + math.cos(an) * r * 2.2, hy + math.sin(an) * r * 2.2), 1)
    elif kind == "zigbolt":
        # Fulmine dal cielo: da un punto alto (spostato di lato) fino a terra; si
        # rifà a ogni frame (crepita), si assottiglia mentre svanisce.
        cx, cy = S(*s["c"])
        h = s.get("h", 6.0) * ts
        top = (cx + s.get("dx", 0.4) * ts, cy - h)
        pts = _zigzag(top, (cx, cy), 0.5 * ts, 0.28 * ts)
        w = s.get("w", 0.22) * ts * (0.4 + 0.6 * f)
        _bolt_lines(overlay, pts, w, _al(f, 2.0), s.get("cols", (ELEC_DK, ELEC, ELEC_HI)))
        if s.get("branch", True) and len(pts) > 4:   # un ramo laterale
            i = len(pts) // 3
            p0 = pts[i]
            side = 1 if (i % 2) else -1
            br = _zigzag(p0, (p0[0] + side * 0.9 * ts, p0[1] + 1.1 * ts), 0.4 * ts, 0.18 * ts)
            _bolt_lines(overlay, br, w * 0.5, _al(f, 1.6))
    elif kind == "sparkring":
        # Anello elettrico che crepita: bordo a zig-zag rifatto a ogni frame.
        cx, cy = S(*s["c"])
        r0, r1 = s.get("r0", s.get("r", 1.0)), s.get("r", 1.0)
        r = (r0 + (r1 - r0) * min(1.0, t / 0.35)) * ts
        n = max(16, int(r / 1.5))
        jag = s.get("jag", 0.08) * ts
        pts = []
        for i in range(n):
            an = i / n * math.tau
            rr = r + (jag if i % 2 else -jag) * random.uniform(0.4, 1.0)
            pts.append((cx + math.cos(an) * rr, cy + math.sin(an) * rr * 0.6))
        al = _al(f, 2.0)
        cols = s.get("cols", (ELEC_DK, ELEC, ELEC_HI))
        if s.get("fill"):
            pygame.draw.polygon(overlay, (*cols[1], al // 5), pts)
        pygame.draw.polygon(overlay, (*cols[0], al // 2), pts, 4)
        pygame.draw.polygon(overlay, (*cols[1], al), pts, 2)
        pygame.draw.lines(overlay, (*cols[2], al), False, pts[n // 2:], 1)
    elif kind == "railbeam":
        # Elettroraggio: raggio dritto che si accende di colpo e si assottiglia;
        # sul corpo corrono archi elettrici rifatti a ogni frame.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        L = math.hypot(bx - ax, by - ay)
        if L < 2:
            return
        ux, uy = (bx - ax) / L, (by - ay) / L
        px, py = -uy, ux
        grow = min(1.0, t / 0.08)
        w = s.get("w", 0.8) * ts * grow * (0.35 + 0.65 * f)
        al = _al(f, 1.8)
        pygame.draw.line(overlay, (*ELEC_DK, al // 3), (ax, ay), (bx, by), max(4, int(w * 2.6)))
        pygame.draw.line(overlay, (*ELEC, al), (ax, ay), (bx, by), max(3, int(w * 1.3)))
        pygame.draw.line(overlay, (*ELEC_HI, al), (ax, ay), (bx, by), max(2, int(w * 0.55)))
        pygame.draw.line(overlay, (*STEEL_HI, al), (ax, ay), (bx, by), max(1, int(w * 0.2)))
        for side in (-1, 1):   # archi che crepitano lungo i bordi
            off = w * 0.9 * side
            pts = _zigzag((ax + px * off, ay + py * off), (bx + px * off, by + py * off),
                          0.7 * ts, 0.25 * ts)
            pygame.draw.lines(overlay, (*ELEC_HI, al), False, pts, 1)
        # anelli che scorrono lungo il raggio
        step = 1.6 * ts
        d = (t * 40.0 * ts) % step
        rr = max(2, int(w * 1.1))
        while d < L:
            cx, cy = ax + ux * d, ay + uy * d
            pygame.draw.ellipse(overlay, (*ELEC_HI, al // 2),
                                pygame.Rect(cx - rr // 3, cy - rr, max(2, rr * 2 // 3), rr * 2), 1)
            d += step


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


def _impact(fx, c, size, cols=(STEEL_DK, STEEL, STEEL_HI), wait=0.0):
    fx._shape(kind="flash", c=c, r=0.25 * size, col=cols[2], life=0.08, wait=wait)
    fx._shape(kind="ring", c=c, r0=0.15, r1=0.6 * size, col=cols[1], life=0.22, wd=0.06,
              wait=wait)
    fx._shape(kind="impactstar", c=c, r=0.45 * size, rot=random.uniform(0, 1), n=6, col=cols[1],
              life=0.2, cols=cols, wait=wait)


def fx_steelshot(fx, e, col):
    """Attacco base: pallottola d'acciaio dalla bocca del cannone."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    a = (a[0], a[1] - 0.45)
    b = (b[0], b[1] - 0.3)
    fx._shape(kind="steelball", a=a, b=b, r=0.11, trail=0.3, fly=0.75, col=STEEL, life=0.2)
    fx._shape(kind="flash", c=b, r=0.14, col=STEEL_HI, life=0.07, wait=0.15)


def fx_flashcannon(fx, e, col):
    """Cannonflash: grossa palla d'acciaio (più grossa e scintillante se Tiro
    Lungo è carico); al bersaglio lampo, stella e schegge."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    ch = float(e.get("charge", 0.0))
    a = (a[0], a[1] - 0.45)
    b = (b[0], b[1] - 0.3)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    fly_t = 0.08 + L / 34.0
    life = fly_t / 0.8
    fx._shape(kind="steelball", a=a, b=b, r=0.2 + 0.14 * ch, trail=0.3 + 0.15 * ch, fly=0.8,
              spark=ch > 0.3, col=STEEL, life=life)
    fx._shape(kind="flash", c=a, r=0.3 + 0.15 * ch, col=STEEL_HI, life=0.08)
    _bits(fx, a, 5, (STEEL, STEEL_HI), speed=1.6)
    if ch > 0.3:   # carica: lampo giallo alla bocca
        fx._shape(kind="sparkring", c=a, r0=0.2, r=0.5 + 0.3 * ch, jag=0.05, col=ELEC, life=0.18)
    if e.get("hit"):
        _impact(fx, b, 1.0 + 0.6 * ch, wait=fly_t)
        fx._shape(kind="ring", c=b, r0=0.2, r1=0.85, col=(150, 120, 230), life=0.3, wd=0.04,
                  wait=fly_t)   # Dif. Sp. ridotta: anello viola tenue


def fx_wavecast(fx, e, col):
    """Tuononda lanciata: piccola scarica sul punto (il resto è persistente)."""
    c = e.get("c")
    if c is not None:
        fx._shape(kind="sparkring", c=c, r0=0.2, r=0.6, jag=0.06, col=ELEC, life=0.2)


def fx_waveburst(fx, e, col):
    """Tuononda scatta: anello che crepita, scariche interne; con Fulmine un
    vero fulmine dal cielo."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 1.6))
    fx._shape(kind="sparkring", c=c, r0=r * 0.6, r=r, jag=0.1, fill=True, col=ELEC, life=0.4)
    for k in range(4):
        an = random.uniform(0, math.tau)
        d = random.uniform(0.2, r * 0.8)
        p = (c[0] + math.cos(an) * d, c[1] + math.sin(an) * d * 0.6)
        fx._shape(kind="zigbolt", c=p, h=0.9, dx=random.uniform(-0.3, 0.3), w=0.07,
                  branch=False, col=ELEC, life=0.18, wait=0.03 * k)
    if e.get("dmg"):
        fx._shape(kind="zigbolt", c=c, h=6.5, dx=0.8, w=0.24, col=ELEC, life=0.28)
        fx._shape(kind="flash", c=c, r=r * 0.5, col=ELEC_HI, life=0.1)
    _bits(fx, c, 12, (ELEC, ELEC_HI), speed=2.4, up=0.5)


def fx_tailswipe(fx, e, col):
    """Codadrago: mezzaluna blu acciaio che spazza davanti a sé."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    ang = math.atan2(d[1], d[0])
    rng = float(e.get("range", 2.6))
    fx._shape(kind="crescent", c=(o[0], o[1] - 0.3), ang=ang, r=rng * 0.65, thick=0.32,
              sweep=1.0, col=DRAGON, life=0.3, cols=(DRAGON_DK, DRAGON, DRAGON_HI))
    fx._shape(kind="crescent", c=(o[0], o[1] - 0.3), ang=ang, r=rng * 0.45, thick=0.16,
              sweep=1.0, col=STEEL, life=0.24, cols=(STEEL_DK, STEEL, STEEL_HI), wait=0.03)


def fx_tailpush(fx, e, col):
    """Respinta di Codadrago: stella d'impatto, scie di vento, polvere."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    _impact(fx, (a[0], a[1] - 0.35), 1.2, cols=(DRAGON_DK, DRAGON, DRAGON_HI))
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L > 1e-6:
        nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
        for k in (-1, 0, 1):
            off = k * 0.2
            fx._shape(kind="windline", a=(a[0] + nx * off, a[1] + ny * off - 0.4),
                      b=(b[0] + nx * off, b[1] + ny * off - 0.4), col=DRAGON_HI,
                      life=0.32 + 0.03 * abs(k))
    fx._dust(b, 0.5, n=8)


def fx_metalsound(fx, e, col):
    """Ferrosuono: onde metalliche stridenti che si allargano da Duraludon."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 3.2))
    for k in range(3):
        fx._shape(kind="soundarc", c=(c[0], c[1] - 0.3), r0=0.4, r1=r, half=math.pi,
                  ang=0.0, w=0.09, jag=0.07, speed=1.4, col=STEEL, life=0.42,
                  cols=(STEEL_DK, (170, 150, 220), STEEL_HI), wait=0.09 * k)
    fx._shape(kind="ring", c=c, r0=r, r1=r * 0.9, col=(150, 120, 230), life=0.4, wd=0.05)


def fx_irondefense(fx, e, col):
    """Ferroscudo: esagono d'acciaio che si stringe sull'alleato, filo di
    luce da Duraludon."""
    c = e.get("c")
    if c is None:
        return
    ab = _ab(e)
    if ab is not None and math.hypot(ab[1][0] - ab[0][0], ab[1][1] - ab[0][1]) > 0.3:
        a, b = ab
        fx._shape(kind="windline", a=(a[0], a[1] - 0.5), b=(b[0], b[1] - 0.5), col=STEEL_HI,
                  life=0.25)
    fx._shape(kind="hexshell", c=c, r=0.8, col=STEEL, life=0.75)
    fx._shape(kind="flash", c=(c[0], c[1] - 0.3), r=0.3, col=STEEL_HI, life=0.1, wait=0.1)
    _bits(fx, (c[0], c[1] - 0.4), 8, (STEEL, STEEL_HI), speed=1.6, up=0.6)


def fx_electroshot(fx, e, col):
    """Elettroraggio: raggio giallo-bianco lunghissimo, lampo alla bocca,
    scintille lungo la linea."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    a = (a[0], a[1] - 0.45)
    b = (b[0], b[1] - 0.45)
    fx._shape(kind="railbeam", a=a, b=b, w=float(e.get("radius", 0.8)), col=ELEC, life=0.55)
    fx._shape(kind="flash", c=a, r=0.7, col=ELEC_HI, life=0.12)
    fx._shape(kind="sparkring", c=a, r0=0.3, r=1.2, jag=0.1, col=ELEC, life=0.3)
    for k in range(10):
        u = random.random()
        p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        _bits(fx, p, 2, (ELEC, ELEC_HI, STEEL_HI), speed=3.0, life=(0.2, 0.5))


def fx_shake(fx, e, col):
    """Lo schermo trema per tutti (Elettroraggio): lo legge draw_shake."""
    until = pygame.time.get_ticks() + int(float(e.get("dur", 0.6)) * 1000)
    fx.shake_until_ms = max(getattr(fx, "shake_until_ms", 0), until)


def fx_paralyzed(fx, e, col):
    """Paralisi di Tuono: scintille gialle sul bersaglio."""
    c = e.get("c")
    if c is None:
        return
    for k in range(3):
        an = k / 3 * math.tau + random.uniform(-0.3, 0.3)
        p = (c[0] + math.cos(an) * 0.35, c[1] - 0.5 + math.sin(an) * 0.25)
        fx._shape(kind="zigbolt", c=p, h=0.45, dx=random.uniform(-0.2, 0.2), w=0.05,
                  branch=False, col=ELEC, life=0.3, wait=0.05 * k)


def fx_thunderstrike(fx, e, col):
    """Fulmine di Tuono: saetta dal cielo, lampo, anello a terra e bruciatura."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 1.5))
    fx._shape(kind="zigbolt", c=c, h=8.0, dx=random.uniform(-1.0, 1.0), w=0.32, col=ELEC,
              life=0.32)
    fx._shape(kind="zigbolt", c=(c[0] + 0.3, c[1]), h=7.0, dx=random.uniform(-1.4, 1.4),
              w=0.14, branch=False, col=ELEC, life=0.22, wait=0.06)
    fx._shape(kind="flash", c=c, r=r * 0.6, col=ELEC_HI, life=0.12)
    fx._shape(kind="sparkring", c=c, r0=r * 0.4, r=r, jag=0.1, fill=True, col=ELEC, life=0.35)
    _bits(fx, (c[0], c[1] - 0.2), 16, (ELEC, ELEC_HI, STEEL_HI), speed=3.2, up=0.8)


STYLES = {
    "steelshot": fx_steelshot, "flashcannon": fx_flashcannon, "wavecast": fx_wavecast,
    "waveburst": fx_waveburst, "tailswipe": fx_tailswipe, "tailpush": fx_tailpush,
    "metalsound": fx_metalsound, "irondefense": fx_irondefense,
    "electroshot": fx_electroshot, "shake": fx_shake, "paralyzed": fx_paralyzed,
    "thunderstrike": fx_thunderstrike,
}


def draw_shake(surface, fx) -> None:
    """Se Elettroraggio sta facendo tremare lo schermo, sposta il fotogramma di
    1-2 px (a bassa risoluzione: resta pixel art)."""
    left = getattr(fx, "shake_until_ms", 0) - pygame.time.get_ticks()
    if left <= 0:
        return
    k = 2 if left > 250 else 1
    surface.scroll(random.randint(-k, k), random.randint(-k, k))


# --- disegni persistenti (stato del Match) ---------------------------------------


def _ellipse_layer(R):
    g = pygame.Surface((R * 2 + 8, R + 8), pygame.SRCALPHA)
    o = (R + 4, R // 2 + 4)
    return g, o


def draw_wave_zone(surface, camera, z, now):
    """Tuononda in arrivo: area che si riempie, cerchio che si allarga verso
    il bordo, bordo che crepita."""
    ts = config.TILE_SIZE
    c = z["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    span = max(1e-6, z["at"] - z["start"])
    u = max(0.0, min(1.0, (now - z["start"]) / span))
    R = int(z["radius"] * ts)
    g, o = _ellipse_layer(R)
    rect = pygame.Rect(o[0] - R, o[1] - R // 2, R * 2, R)
    pygame.draw.ellipse(g, (*ELEC_DK, int(40 + 60 * u)), rect)
    pygame.draw.ellipse(g, (*ELEC, 220), rect, 2)
    ir = max(2, int(R * u))
    pygame.draw.ellipse(g, (*ELEC_HI, 200), pygame.Rect(o[0] - ir, o[1] - ir // 2, ir * 2, ir), 1)
    rnd = random.Random(int(now * 14) + int(c.x * 7))
    for _ in range(2 + int(3 * u)):   # scariche che corrono dentro
        an = rnd.uniform(0, math.tau)
        d = rnd.uniform(0.1, 0.9) * R
        p0 = (o[0] + math.cos(an) * d, o[1] + math.sin(an) * d * 0.5)
        an2 = an + rnd.uniform(-1.2, 1.2)
        p1 = (o[0] + math.cos(an2) * d * 0.6, o[1] + math.sin(an2) * d * 0.3)
        pygame.draw.lines(g, (*ELEC_HI, 230), False, _zigzag(p0, p1, 4, 2, rnd), 1)
    surface.blit(g, (cx - o[0], cy - o[1]))


def draw_beam_charge(surface, camera, ch, now):
    """Elettroraggio in carica (visibile anche ai nemici): linea tratteggiata
    della mira che si accende, energia risucchiata dal cannone."""
    ts = config.TILE_SIZE
    p, d = ch["pos"], ch["dir"]
    span = max(1e-6, ch["at"] - ch["start"])
    u = max(0.0, min(1.0, (now - ch["start"]) / span))
    ax, ay = camera.world_to_screen(p.x * ts, p.y * ts)
    L = 25.0 * ts
    ux, uy = d.x, d.y
    px, py = -uy, ux
    w = (0.8 * ts) * (0.3 + 0.7 * u)
    # corsia tratteggiata (si accende verso la fine)
    dash = 0.6 * ts
    off = (now * 6.0 * ts) % (dash * 2)
    dd = off
    col = (*ELEC, int(90 + 140 * u))
    g = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    while dd < L:
        x0, y0 = ax + ux * dd, ay + uy * dd
        x1, y1 = ax + ux * min(L, dd + dash), ay + uy * min(L, dd + dash)
        for s in (-1, 1):
            pygame.draw.line(g, col, (x0 + px * w * s, y0 + py * w * s),
                             (x1 + px * w * s, y1 + py * w * s), 1)
        dd += dash * 2
    pygame.draw.line(g, (*ELEC_HI, int(60 + 120 * u)), (ax, ay), (ax + ux * L, ay + uy * L), 1)
    # globo d'energia sulla bocca del cannone
    hx, hy = ax + ux * 0.4 * ts, ay + uy * 0.4 * ts - 0.45 * ts
    pulse = 0.5 + 0.5 * math.sin(now * 30.0)
    rr = max(2, int((0.18 + 0.32 * u + 0.05 * pulse) * ts))
    pygame.draw.circle(g, (*ELEC_DK, 120), (int(hx), int(hy)), rr + 3)
    pygame.draw.circle(g, (*ELEC, 230), (int(hx), int(hy)), rr)
    pygame.draw.circle(g, (*ELEC_HI, 255), (int(hx - rr * 0.3), int(hy - rr * 0.3)), max(1, rr // 2))
    rnd = random.Random(int(now * 20))
    for _ in range(5):   # scintille risucchiate
        an = rnd.uniform(0, math.tau)
        d0 = rnd.uniform(0.8, 1.6) * ts
        pygame.draw.lines(g, (*ELEC_HI, 220), False,
                          _zigzag((hx + math.cos(an) * d0, hy + math.sin(an) * d0),
                                  (hx + math.cos(an) * rr, hy + math.sin(an) * rr), 4, 2, rnd), 1)
    surface.blit(g, (0, 0))


def draw_thunder_mark(surface, camera, tm, now):
    """Fulmine di Tuono in arrivo: ombra della nube, cerchio che si chiude."""
    ts = config.TILE_SIZE
    c = tm["c"]
    cx, cy = camera.world_to_screen(c.x * ts, c.y * ts)
    span = max(1e-6, tm["at"] - tm["start"])
    u = max(0.0, min(1.0, (now - tm["start"]) / span))
    R = int(tm["radius"] * ts)
    g, o = _ellipse_layer(R)
    rect = pygame.Rect(o[0] - R, o[1] - R // 2, R * 2, R)
    pygame.draw.ellipse(g, (14, 16, 30, int(70 + 70 * u)), rect)
    pygame.draw.ellipse(g, (*ELEC, 230), rect, 2)
    ir = max(2, int(R * (1.0 - u)))
    pygame.draw.ellipse(g, (*ELEC_HI, 230), pygame.Rect(o[0] - ir, o[1] - ir // 2, ir * 2, ir), 1)
    for k in range(4):   # tacche
        aa = k * math.pi / 2
        x0, y0 = o[0] + math.cos(aa) * R * 0.75, o[1] + math.sin(aa) * R * 0.375
        x1, y1 = o[0] + math.cos(aa) * R, o[1] + math.sin(aa) * R * 0.5
        pygame.draw.line(g, (*ELEC_HI, 230), (x0, y0), (x1, y1), 2)
    if tm.get("rain"):   # gocce: area allargata dalla pioggia
        for k in range(6):
            aa = k / 6 * math.tau + now
            x, y = o[0] + math.cos(aa) * R * 0.5, o[1] + math.sin(aa) * R * 0.25
            pygame.draw.line(g, (*RAIN, 200), (x, y - 2), (x, y + 1), 1)
    surface.blit(g, (cx - o[0], cy - o[1]))


# --- sulle unità --------------------------------------------------------------


def draw_bolt_icon(surface, x, y, s, col=ELEC, dark=ELEC_DK):
    """Saetta pixel art (interfaccia, fulmini rimasti)."""
    pts = [(x + s // 3, y - s), (x - s // 2, y + s // 6), (x, y + s // 6),
           (x - s // 3, y + s), (x + s // 2, y - s // 6), (x, y - s // 6)]
    pygame.draw.polygon(surface, dark, pts)
    pygame.draw.polygon(surface, col, pts, 0)
    pygame.draw.polygon(surface, dark, pts, 1)


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Sopra lo sprite: scintille di Conduzione (sotto la pioggia), alone di
    Att. Sp. di Elettroraggio, saette dei fulmini di Tuono ancora da lanciare
    (a destra della barra della vita). Visibili a tutti."""
    r = int(getattr(u, "radius", 0.5) * ts)
    if getattr(u, "arch_rain", False):
        rnd = random.Random(int(now * 9) + u.id * 31)
        for _ in range(2):
            an = rnd.uniform(0, math.tau)
            x0 = gx + math.cos(an) * r * 0.9
            y0 = gy - r + math.sin(an) * r * 0.9
            pts = _zigzag((x0, y0), (x0 + rnd.uniform(-5, 5), y0 + rnd.uniform(-5, 5)), 2, 1.5, rnd)
            pygame.draw.lines(surface, ELEC_DK, False, [(p[0] + 1, p[1] + 1) for p in pts], 1)
            pygame.draw.lines(surface, ELEC_HI, False, pts, 1)
    if getattr(u, "arch_spa_until", -1.0) > now:
        pulse = 0.5 + 0.5 * math.sin(now * 10.0)
        g = pygame.Surface((r * 2 + 10, r + 8), pygame.SRCALPHA)
        o = (r + 5, r // 2 + 4)
        pygame.draw.ellipse(g, (*ELEC, int(60 + 50 * pulse)),
                            pygame.Rect(o[0] - r - 3, o[1] - r // 2 - 2, r * 2 + 6, r + 4), 2)
        surface.blit(g, (gx - o[0], gy - o[1]))
    left = getattr(u, "thunder_left", 0)
    if left > 0 and getattr(u, "thunder_until", -1.0) > now:
        top = gy - 2 * r - 8
        w = max(14, r * 2)
        for k in range(left):
            draw_bolt_icon(surface, gx + w // 2 + 6 + k * 7, top + 1, 4)


# --- mirino ---------------------------------------------------------------------


def draw_aim(surface, S, ts, ox, oy, nx, ny, dist, move, hold=0.0, rain=False) -> bool:
    """Mirino delle mosse della linea. Ritorna False se la forma non è sua."""
    shape = move.shape
    col = ELEC if move.type == "Electric" else (STEEL if move.type == "Steel" else DRAGON)
    rng = move.range
    if shape == "flashcannon":
        hd = move.effects.get("hold")
        frac = 0.0
        if hd:
            full = float(hd.get("time", 1.0)) * (0.5 if rain else 1.0)
            frac = max(0.0, min(1.0, hold / max(0.05, full)))
            pygame.draw.circle(surface, (70, 70, 70), S(ox, oy),
                               int(rng * (1.0 + float(hd.get("range", 0.4))) * ts), 1)
            rng *= 1.0 + float(hd.get("range", 0.4)) * frac
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        ex, ey = ox + nx * rng, oy + ny * rng
        w = move.radius * (1.0 + 0.5 * frac)   # corsia: due bordi + linea centrale
        px, py = -ny * w, nx * w
        for sg in (1, -1):
            pygame.draw.line(surface, col, S(ox + px * sg, oy + py * sg),
                             S(ex + px * sg, ey + py * sg), 1)
        pygame.draw.line(surface, (255, 255, 255) if frac >= 1.0 else col, S(ox, oy), S(ex, ey), 1)
        pygame.draw.circle(surface, col, S(ex, ey), max(3, int(w * ts)), 1)
        if hd:   # barra di carica sopra la linea
            bx, by = S(ox, oy - 1.4)
            bw = int(1.4 * ts)
            pygame.draw.rect(surface, (20, 20, 26), pygame.Rect(bx - bw // 2 - 1, by - 1, bw + 2, 5))
            pygame.draw.rect(surface, ELEC if frac >= 1.0 else STEEL,
                             pygame.Rect(bx - bw // 2, by, int(bw * frac), 3))
        return True
    if shape in ("thunderwave", "thunderstorm"):
        r = move.radius * (float(move.effects.get("rain_mult", 1.0)) if rain else 1.0)
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        d = min(dist, rng)
        cx, cy = S(ox + nx * d, oy + ny * d)
        pygame.draw.circle(surface, col, (cx, cy), int(r * ts), 2)
        pygame.draw.circle(surface, (255, 255, 255), (cx, cy), max(3, int(0.25 * ts)), 1)
        return True
    if shape == "dragontail":
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        ex, ey = ox + nx * rng, oy + ny * rng
        pygame.draw.line(surface, col, S(ox, oy), S(ex, ey), max(2, int(move.radius * ts)))
        push = float(move.effects.get("push", 4.0))
        pygame.draw.line(surface, (255, 255, 255), S(ex, ey),
                         S(ex + nx * push, ey + ny * push), 1)
        return True
    if shape == "metalsound":
        pygame.draw.circle(surface, col, S(ox, oy), int(move.radius * ts), 2)
        return True
    if shape == "irondefense":
        pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)
        d = min(dist, rng)
        pygame.draw.circle(surface, STEEL_HI, S(ox + nx * d, oy + ny * d), max(4, int(0.7 * ts)), 1)
        return True
    if shape == "electroshot":
        ex, ey = ox + nx * rng, oy + ny * rng
        pygame.draw.line(surface, col, S(ox, oy), S(ex, ey), max(2, int(move.radius * ts * 2)))
        pygame.draw.line(surface, (255, 255, 255), S(ox, oy), S(ex, ey), 1)
        return True
    return False
