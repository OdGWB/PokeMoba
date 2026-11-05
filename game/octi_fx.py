"""Grafica della linea Remoraid > Octillery: effetti istantanei (handler
registrati in FXSystem._FX_STYLES), forme nuove per FXSystem._draw_shapes
(pallottola della munizione in volo, schizzi d'inchiostro, Iper Raggio,
tentacolo con le ventose, mirino che si chiude), disegni persistenti letti
dallo stato del Match a ogni frame (proiettili di Pistolacqua / Raffica /
Colpo Perforante), il mirino di Prendimira sulle unità agganciate, i tentacoli
della Presa a Ventosa, la ricarica dell'Iper Raggio, l'icona delle munizioni
nell'HUD della passiva e il mirino delle mosse.

Le MUNIZIONI hanno ognuna un colore e una sagoma: Acqua = goccia blu,
Ghiaccio = scheggia azzurra, Fuoco = palla di brace, Erba = seme verde.

Pixel art: tratti pieni a 2-3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

# munizioni: (scuro, colore, luce)
AMMO_COLS = {
    "Water": ((22, 58, 140), (72, 150, 240), (206, 236, 255)),
    "Ice": ((52, 112, 150), (150, 222, 246), (244, 253, 255)),
    "Fire": ((132, 36, 10), (250, 122, 40), (255, 232, 140)),
    "Grass": ((30, 82, 22), (112, 194, 62), (222, 250, 160)),
}
AMMO_NAMES = {"Water": "Acqua", "Ice": "Ghiaccio", "Fire": "Fuoco", "Grass": "Erba"}
INK = ((18, 14, 26), (52, 44, 72), (124, 114, 158))
BEAM = ((150, 70, 20), (255, 176, 64), (255, 246, 210))
OCTO = ((110, 26, 22), (222, 82, 60), (255, 176, 150))     # tentacoli di Octillery
SUCKER = (255, 214, 190)
LOCK = (255, 70, 60)
LOCK_HI = (255, 214, 200)
LOCK_DK = (90, 10, 10)
WHITE = (255, 255, 255)

OCTI_DEX = (223, 224)
# Munizioni disponibili per la W scelta (anche sul client, dove non c'è il motore).
AMMO_BY_MOVE = {"octillery_ammoswap": ("Water", "Ice"),
                "octillery_fireammo": ("Water", "Ice", "Fire"),
                "octillery_grassammo": ("Water", "Ice", "Grass")}


def _al(f, k=2.0):
    return max(0, min(255, int(255 * min(1.0, f * k))))


def is_octi(u) -> bool:
    return (getattr(u, "passive_id", "") in ("cecchino", "ventose")
            or getattr(u, "dex", 0) in OCTI_DEX)


def ammo_cols(t):
    return AMMO_COLS.get(t, AMMO_COLS["Water"])


def ammo_list(p) -> tuple:
    ms = getattr(p, "moveset", {}).get("W") if hasattr(p, "moveset") else None
    mv = getattr(ms, "chosen", None) if ms is not None else None
    if mv is not None:
        return AMMO_BY_MOVE.get(mv.id, tuple(mv.effects.get("ammo", ("Water", "Ice"))))
    return ("Water", "Ice")


# --- mattoni ---------------------------------------------------------------------------

def draw_pellet(surface, x, y, r, ammo, ang, alpha=255):
    """Pallottola della munizione, puntata nella direzione `ang`.
    Acqua: goccia; Ghiaccio: scheggia a rombo; Fuoco: palla con fiammella;
    Erba: seme ovale con una fogliolina."""
    dk, c, hi = ammo_cols(ammo)
    r = max(2.0, r)
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    if ammo == "Ice":
        pts = [(x + ux * r * 1.6, y + uy * r * 1.6), (x + px * r * 0.7, y + py * r * 0.7),
               (x - ux * r * 1.2, y - uy * r * 1.2), (x - px * r * 0.7, y - py * r * 0.7)]
        pygame.draw.polygon(surface, (*dk, alpha), [(a + (a - x) * 0.25, b + (b - y) * 0.25)
                                                     for a, b in pts])
        pygame.draw.polygon(surface, (*c, alpha), pts)
        pygame.draw.line(surface, (*hi, alpha), pts[0], pts[2], 1)
        return
    if ammo == "Fire":
        for k in range(3):   # fiammella dietro
            q = 1.0 + k * 0.7
            pygame.draw.circle(surface, (*(c if k else hi), alpha // (k + 1)),
                               (int(x - ux * r * q), int(y - uy * r * q - k)), max(1, int(r * (0.8 - k * 0.2))))
        pygame.draw.circle(surface, (*dk, alpha), (int(x), int(y)), int(r + 1))
        pygame.draw.circle(surface, (*c, alpha), (int(x), int(y)), int(r))
        pygame.draw.circle(surface, (*hi, alpha), (int(x - r * 0.3), int(y - r * 0.3)), max(1, int(r * 0.45)))
        return
    if ammo == "Grass":
        rect = pygame.Rect(0, 0, int(r * 3.0), int(r * 2.0))
        surf = pygame.Surface((rect.w + 4, rect.h + 4), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (*dk, alpha), surf.get_rect())
        pygame.draw.ellipse(surf, (*c, alpha), surf.get_rect().inflate(-2, -2))
        pygame.draw.ellipse(surf, (*hi, alpha), pygame.Rect(3, 2, max(2, rect.w // 3), max(1, rect.h // 3)))
        rs = pygame.transform.rotate(surf, -math.degrees(ang))
        surface.blit(rs, rs.get_rect(center=(int(x), int(y))))
        lx, ly = x - ux * r * 1.3, y - uy * r * 1.3
        pygame.draw.line(surface, (*dk, alpha), (lx, ly), (lx - ux * r + px * r * 0.8, ly - uy * r + py * r * 0.8), 2)
        return
    # Acqua: goccia (coda a punta all'indietro)
    tail = [(x - ux * r * 2.4, y - uy * r * 2.4), (x + px * r, y + py * r), (x - px * r, y - py * r)]
    pygame.draw.polygon(surface, (*c, alpha), tail)
    pygame.draw.circle(surface, (*dk, alpha), (int(x), int(y)), int(r + 1))
    pygame.draw.circle(surface, (*c, alpha), (int(x), int(y)), int(r))
    pygame.draw.circle(surface, (*hi, alpha), (int(x - r * 0.35), int(y - r * 0.35)), max(1, int(r * 0.4)))


def draw_reticle(surface, cx, cy, r, now, alpha=255, col=LOCK):
    """Mirino pixel art: quattro angolari che pulsano verso il centro, croce
    centrale con il punto; ombra scura spostata in basso a destra (luce da
    in alto a sinistra). Leggibile anche piccolo (r ~ 6 px)."""
    r = max(4, int(r))
    w = 1 if r < 10 else 2
    pulse = int(round(math.sin(now * 6.0) * (1 if r < 10 else 2)))
    rr = r + pulse
    size = rr * 2 + 6
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    o = size // 2
    arm = max(2, int(rr * 0.5))
    tick = max(2, int(r * 0.35))

    def shape(dx, dy, c):
        for sx in (-1, 1):
            for sy in (-1, 1):
                x0, y0 = o + sx * rr + dx, o + sy * rr + dy
                pygame.draw.line(s, c, (x0, y0), (x0 - sx * arm, y0), w)
                pygame.draw.line(s, c, (x0, y0), (x0, y0 - sy * arm), w)
        for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            pygame.draw.line(s, c, (o + ax * 2 + dx, o + ay * 2 + dy),
                             (o + ax * (2 + tick) + dx, o + ay * (2 + tick) + dy), w)
        s.fill(c, pygame.Rect(o + dx, o + dy, 1, 1))

    shape(1, 1, (*LOCK_DK, alpha))
    shape(0, 0, (*col, alpha))
    for sx, sy in ((-1, -1),):   # riflesso sull'angolare in alto a sinistra
        s.fill((*LOCK_HI, alpha), pygame.Rect(o + sx * rr, o + sy * rr, w, w))
    surface.blit(s, (int(cx) - o, int(cy) - o))


def draw_tentacle(surface, ax, ay, bx, by, w, t, alpha=255, curl=1.0):
    """Tentacolo da A a B: corpo affusolato rosso che ondeggia, ventose chiare
    sul lato in luce."""
    L = math.hypot(bx - ax, by - ay) or 1.0
    ux, uy = (bx - ax) / L, (by - ay) / L
    px, py = -uy, ux
    n = max(6, int(L / 4))
    mid = []
    for i in range(n + 1):
        u = i / n
        wob = math.sin(u * 5.0 - t * 9.0) * 0.12 * L * curl * u * (1 - u * 0.4)
        mid.append((ax + ux * L * u + px * wob, ay + uy * L * u + py * wob))
    left, right = [], []
    for i, (x, y) in enumerate(mid):
        ww = w * (1.0 - 0.7 * i / n)
        left.append((x + px * ww, y + py * ww))
        right.append((x - px * ww, y - py * ww))
    pygame.draw.polygon(surface, (*OCTO[0], alpha), left + right[::-1])
    inner_l = [((x + m[0]) / 2, (y + m[1]) / 2) for (x, y), m in zip(left, mid)]
    pygame.draw.polygon(surface, (*OCTO[1], alpha), inner_l + mid[::-1])
    for i in range(1, n, 2):   # ventose
        x, y = right[i]
        mx, my = mid[i]
        sx, sy = (x + mx) / 2, (y + my) / 2
        pygame.draw.circle(surface, (*SUCKER, alpha), (int(sx), int(sy)), max(1, int(w * 0.35 * (1 - i / n) + 1)))


# --- forme per FXSystem._draw_shapes -------------------------------------------------

SHAPES = ("octipellet", "inksplat", "octibeam", "octitentacle", "octireticle")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if kind == "octipellet":
        # Pallottola da A a B (attacco base): piccola scia, poi spruzzo all'arrivo.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.8)
        lift = 0.32 * ts
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - lift
        ang = math.atan2(by - ay, bx - ax)
        al = _al(f, 3.0)
        ammo = s.get("ammo", "Water")
        cols = ammo_cols(ammo)
        if u < 1.0:
            for k in (1, 2, 3):
                uk = max(0.0, u - 0.07 * k)
                qx, qy = ax + (bx - ax) * uk, ay + (by - ay) * uk - lift
                overlay.fill((*cols[1], al // (k + 1)), pygame.Rect(int(qx), int(qy), 2, 2))
            draw_pellet(overlay, x, y, s.get("sz", 0.09) * ts, ammo, ang, al)
        else:
            rnd = random.Random(s.get("seed", 3))
            for k in range(6):
                an = rnd.uniform(0, math.tau)
                d = (t - 0.8) / 0.2 * 0.3 * ts * rnd.uniform(0.6, 1.0)
                overlay.fill((*cols[k % 3 and 1 or 2], al),
                             pygame.Rect(int(bx + math.cos(an) * d), int(by - lift + math.sin(an) * d * 0.6), 2, 2))
    elif kind == "inksplat":
        # Macchia d'inchiostro che vola da A e si spiaccica in B.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.45)
        arc = math.sin(u * math.pi) * 0.4 * ts
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - 0.3 * ts - arc
        al = _al(f, 2.0)
        r = s.get("r", 0.16) * ts
        if u < 1.0:
            pygame.draw.circle(overlay, (*INK[0], al), (int(x), int(y)), int(r + 1))
            pygame.draw.circle(overlay, (*INK[1], al), (int(x), int(y)), int(r))
            pygame.draw.circle(overlay, (*INK[2], al), (int(x - r * 0.3), int(y - r * 0.3)), max(1, int(r * 0.35)))
        else:
            rnd = random.Random(s.get("seed", 1))
            grow = min(1.0, (t - 0.45) / 0.15)
            for k in range(5):
                an = rnd.uniform(0, math.tau)
                d = rnd.uniform(0.0, 1.4) * r * grow
                rr = r * rnd.uniform(0.4, 0.9)
                pygame.draw.ellipse(overlay, (*INK[0], int(al * 0.75)),
                                    pygame.Rect(int(bx + math.cos(an) * d - rr), int(by + math.sin(an) * d * 0.5 - rr * 0.5),
                                                int(rr * 2), int(rr)))
    elif kind == "octibeam":
        # Iper Raggio: fascia arancio spessa, nucleo bianco, anelli che scorrono,
        # bordo che crepita; si allarga in fretta e si assottiglia sparendo.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        L = math.hypot(bx - ax, by - ay) or 1.0
        ux, uy = (bx - ax) / L, (by - ay) / L
        px, py = -uy, ux
        lift = 0.35 * ts
        grow = min(1.0, t / 0.12)
        thin = 1.0 if t < 0.55 else max(0.0, 1.0 - (t - 0.55) / 0.45)
        al = _al(f, 2.5)
        w = s.get("w", 0.62) * ts * thin
        age = s["maxlife"] - s["life"]
        ex, ey = ax + ux * L * grow, ay + uy * L * grow
        a0, b0 = (ax, ay - lift), (ex, ey - lift)
        for ww, col, aa in ((w, BEAM[0], al // 2), (w * 0.72, BEAM[1], al), (w * 0.32, BEAM[2], al)):
            if ww < 1:
                continue
            pts = [(a0[0] + px * ww, a0[1] + py * ww), (b0[0] + px * ww, b0[1] + py * ww),
                   (b0[0] - px * ww, b0[1] - py * ww), (a0[0] - px * ww, a0[1] - py * ww)]
            pygame.draw.polygon(overlay, (*col, aa), pts)
        pygame.draw.circle(overlay, (*BEAM[1], al), (int(a0[0]), int(a0[1])), int(w * 0.9) + 1)
        pygame.draw.circle(overlay, (*BEAM[2], al), (int(a0[0]), int(a0[1])), int(w * 0.5) + 1)
        for k in range(7):   # anelli che corrono verso la punta
            d = (age * 22.0 * ts + k * L / 7) % max(1.0, L * grow)
            cx, cy = ax + ux * d, ay + uy * d - lift
            hh = w * 1.15
            pygame.draw.line(overlay, (*BEAM[2], al), (cx + px * hh, cy + py * hh), (cx - px * hh, cy - py * hh), 2)
        rnd = random.Random(int(age * 30))
        for k in range(10):   # crepitio sui bordi
            d = rnd.uniform(0, L * grow)
            sg = rnd.choice((-1, 1))
            cx, cy = ax + ux * d + px * w * sg * 1.1, ay + uy * d + py * w * sg * 1.1 - lift
            overlay.fill((*BEAM[2], al), pygame.Rect(int(cx), int(cy), 2, 2))
    elif kind == "octitentacle":
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        ext = min(1.0, t / 0.35)
        al = _al(f, 3.0)
        lift = 0.3 * ts
        ex, ey = ax + (bx - ax) * ext, ay + (by - ay) * ext
        age = s["maxlife"] - s["life"]
        draw_tentacle(overlay, ax, ay - lift, ex, ey - lift, max(2, 0.12 * ts), age, al,
                      curl=s.get("curl", 1.0))
    elif kind == "octireticle":
        # Mirino che si chiude sul bersaglio (aggancio di Prendimira).
        cx, cy = S(*s["c"])
        r = (1.8 - 1.2 * min(1.0, t / 0.35)) * 0.45 * ts
        age = s["maxlife"] - s["life"]
        draw_reticle(overlay, int(cx), int(cy - 0.35 * ts), r, age, _al(f, 3.0))


# --- handler degli eventi (FXSystem._FX_STYLES) ------------------------------------

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


def fx_octishot(fx, e, col):
    """Attacco base: pallottola del tipo della munizione (colore e sagoma)."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    ammo = e.get("mtype", "Water")
    if ammo not in AMMO_COLS:
        ammo = "Water"
    fx._shape(kind="octipellet", a=a, b=b, ammo=ammo, col=ammo_cols(ammo)[1], life=0.26, sz=0.11,
              seed=random.randrange(999))


def fx_octimuzzle(fx, e, col):
    """Bocca di fuoco della Q: sbuffo del colore della munizione."""
    c, d = e.get("c"), e.get("dir")
    if c is None or d is None:
        return
    cols = ammo_cols(e.get("mtype", "Water"))
    m = (c[0] + d[0] * 0.5, c[1] + d[1] * 0.5 - 0.3)
    fx._shape(kind="flash", c=m, r=0.28, col=cols[1], life=0.14)
    _bits(fx, m, 6, cols[1:], speed=2.4, life=(0.1, 0.25))


def fx_octihit(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    cols = ammo_cols(e.get("mtype", "Water"))
    top = (c[0], c[1] - 0.3)
    fx._shape(kind="ring", c=c, r0=0.1, r1=0.55, col=cols[1], life=0.22, wd=0.07)
    _bits(fx, top, 9, cols, speed=2.6, life=(0.15, 0.35), up=0.6)


def fx_octisplash(fx, e, col):
    """Munizioni Erba: schegge di foglie verso i vicini."""
    c = e.get("c")
    if c is None:
        return
    r = e.get("radius", 1.5)
    cols = AMMO_COLS["Grass"]
    fx._shape(kind="ring", c=c, r0=0.3, r1=r, col=cols[1], life=0.3, wd=0.06)
    _bits(fx, (c[0], c[1] - 0.3), 14, cols, speed=r * 2.4, life=(0.2, 0.4), size=2)


def fx_ammoswap(fx, e, col):
    """Cambio Munizioni: tamburo che gira (anello del colore nuovo + granelli)."""
    c = e.get("c")
    if c is None:
        return
    cols = ammo_cols(e.get("mtype", "Water"))
    fx._shape(kind="ring", c=c, r0=0.9, r1=0.35, col=cols[1], life=0.3, wd=0.08)
    for k in range(4):
        an = k * math.tau / 4
        p = (c[0] + math.cos(an) * 0.6, c[1] + math.sin(an) * 0.35 - 0.4)
        q = (c[0] + math.cos(an + 1.2) * 0.25, c[1] + math.sin(an + 1.2) * 0.15 - 0.4)
        fx._shape(kind="octipellet", a=p, b=q, ammo=e.get("mtype", "Water"), col=cols[1],
                  life=0.3, seed=k)


def fx_octazooka(fx, e, col):
    """Octazooka: getto d'inchiostro nel cono (macchie che volano e si spiaccicano)."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    rng = e.get("range", 4.0)
    half = math.radians(e.get("angle", 35))
    ang = math.atan2(d[1], d[0])
    fx._shape(kind="flash", c=(o[0] + d[0] * 0.6, o[1] + d[1] * 0.6 - 0.3), r=0.4, col=INK[1],
              life=0.18)
    for k in range(9):
        an = ang + random.uniform(-half, half)
        dist = rng * random.uniform(0.45, 1.0)
        b = (o[0] + math.cos(an) * dist, o[1] + math.sin(an) * dist)
        fx._shape(kind="inksplat", a=(o[0], o[1]), b=b, r=random.uniform(0.12, 0.22), col=INK[1],
                  life=0.9, wait=0.02 * k, seed=random.randrange(999))


def fx_octijet(fx, e, col):
    """Spinta all'indietro: scia d'acqua e inchiostro lungo lo scatto."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    for k in range(6):
        u = k / 5
        c = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u - 0.2)
        _bits(fx, c, 3, (AMMO_COLS["Water"][1], AMMO_COLS["Water"][2], INK[2]), speed=1.4,
              life=(0.2, 0.45))
    fx._shape(kind="windline", a=(a[0], a[1] - 0.3), b=(b[0], b[1] - 0.3), col=AMMO_COLS["Water"][2],
              life=0.25)


def fx_octibeam(fx, e, col):
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="octibeam", a=a, b=b, col=BEAM[1], life=0.75, w=0.62)
    fx._shape(kind="flash", c=(a[0], a[1] - 0.35), r=0.7, col=BEAM[2], life=0.25)
    fx._shape(kind="flash", c=(b[0], b[1] - 0.35), r=0.6, col=BEAM[1], life=0.3, wait=0.1)
    if e.get("kind") == "projectile":
        fx.shake_until_ms = max(getattr(fx, "shake_until_ms", 0), pygame.time.get_ticks() + 250)


def fx_octigrab(fx, e, col):
    """Presa a Ventosa: due tentacoli che partono da Octillery e avvolgono il bersaglio."""
    c, a = e.get("c"), e.get("a")
    if c is None:
        return
    if a is not None:
        for k, curl in enumerate((1.0, -1.0)):
            fx._shape(kind="octitentacle", a=a, b=c, curl=curl, col=OCTO[1], life=0.45,
                      wait=0.04 * k)
    fx._shape(kind="ring", c=c, r0=1.0, r1=0.4, col=OCTO[1], life=0.3, wd=0.08)


def fx_octilock(fx, e, col):
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="octireticle", c=c, col=LOCK, life=0.45)


STYLES = {
    "octishot": fx_octishot, "octimuzzle": fx_octimuzzle, "octihit": fx_octihit,
    "octisplash": fx_octisplash, "ammoswap": fx_ammoswap, "octazooka": fx_octazooka,
    "octijet": fx_octijet, "octibeam": fx_octibeam, "octigrab": fx_octigrab,
    "octilock": fx_octilock,
}


# --- disegni persistenti (world_fx) ---------------------------------------------------

def draw_shot(surface, camera, o, now):
    """Proiettile di Pistolacqua / Raffica / Colpo Perforante in volo, con scia
    del colore della munizione e ombra a terra. Il Colpo Perforante è più
    grosso e lascia una scia più lunga."""
    ts = config.TILE_SIZE
    p, d = o["pos"], o["dir"]
    big = bool(o.get("big"))
    ammo = o.get("ammo", "Water")
    cols = ammo_cols(ammo)
    lift = 0.32
    gx, gy = camera.world_to_screen(p.x * ts, p.y * ts)
    sh = pygame.Surface((int(0.36 * ts), int(0.14 * ts)), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 70), sh.get_rect())
    surface.blit(sh, (gx - sh.get_width() // 2, gy - sh.get_height() // 2))
    n = 8 if big else 5
    for k in range(n, 0, -1):
        back = k * (0.16 if big else 0.13)
        tx, ty = camera.world_to_screen((p.x - d.x * back) * ts, (p.y - d.y * back - lift) * ts)
        r = max(1, int((0.14 if big else 0.1) * ts * (1 - k / (n + 1))))
        pygame.draw.circle(surface, cols[1] if k % 2 else cols[2], (tx, ty), r)
    x, y = camera.world_to_screen(p.x * ts, (p.y - lift) * ts)
    draw_pellet(surface, x, y, (0.2 if big else 0.15) * ts, ammo, math.atan2(d.y, d.x))
    if big:
        rnd = random.Random(int(now * 25) + int(o.get("seed", 0)))
        for _ in range(3):
            an = rnd.uniform(0, math.tau)
            surface.set_at((int(x + math.cos(an) * 0.3 * ts), int(y + math.sin(an) * 0.2 * ts)), cols[2])


# --- sulle unità ------------------------------------------------------------------------

def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Presa a Ventosa (tentacoli tesi in avanti / avvolti attorno all'afferrato),
    ricarica dell'Iper Raggio (vapore e scintille)."""
    r = int(getattr(u, "radius", 0.5) * ts)
    if getattr(u, "octi_held_until", -1.0) > now:
        # Avvolto: due fasce di tentacolo che gli girano attorno (davanti allo
        # sprite), contorno scuro, ventose chiare; stringono a ritmo.
        squeeze = 1.0 + 0.08 * math.sin(now * 10.0)
        for k, hy in enumerate((0.45, 1.05)):
            cy = gy - r * hy
            rx = (r + 3) * squeeze
            ry = max(3, r * 0.32)
            pts = []
            for i in range(13):
                an = math.pi * i / 12   # meta' davanti dell'ellisse
                pts.append((gx + math.cos(an) * rx * (1 if k else -1), cy + math.sin(an) * ry))
            pygame.draw.lines(surface, OCTO[0], False, pts, 6)
            pygame.draw.lines(surface, OCTO[1], False, pts, 4)
            pygame.draw.lines(surface, OCTO[2], False, [(x, y - 1) for x, y in pts[2:-2]], 1)
            for i in range(2, 12, 3):
                x, y = pts[i]
                pygame.draw.circle(surface, SUCKER, (int(x), int(y + 1)), 1)
            ex, ey = pts[-1]   # punta arricciata
            pygame.draw.circle(surface, OCTO[0], (int(ex), int(ey - 2)), 3)
            pygame.draw.circle(surface, OCTO[1], (int(ex), int(ey - 2)), 2)
    if getattr(u, "octi_grab_until", -1.0) > now:
        for k in range(2):
            an = now * 2.0 + k * math.pi
            x = gx + math.cos(an) * (r + 4)
            y = gy - r * 0.2 + math.sin(an) * 3
            pygame.draw.circle(surface, OCTO[1], (int(x), int(y)), 3)
            pygame.draw.circle(surface, SUCKER, (int(x), int(y)), 1)
    if getattr(u, "octi_recharge_until", -1.0) > now:
        rnd = random.Random(int(now * 12) + getattr(u, "id", 0))
        for k in range(5):   # vapore che sale
            ph = (now * 1.6 + k / 5) % 1.0
            x = gx + math.sin(k * 2.3) * r * 0.7
            y = gy - r - ph * r * 1.6
            pygame.draw.circle(surface, (200, 200, 210), (int(x), int(y)), max(1, int(3 * (1 - ph)) + 1))
        for _ in range(2):
            an = rnd.uniform(0, math.tau)
            surface.set_at((int(gx + math.cos(an) * r), int(gy - r * 0.5 + math.sin(an) * r * 0.5)), BEAM[2])


def draw_lock(surface, u, gx, top, now):
    """Mirino di Prendimira sopra la barra della vita dell'agganciato (visibile a tutti)."""
    if getattr(u, "octi_lock_until", -1.0) <= now:
        return False
    left = u.octi_lock_until - now
    if left < 1.0 and int(now * 8) % 2:   # lampeggia nell'ultimo secondo
        return True
    draw_reticle(surface, gx, top - 13, 7, now)
    return True


# --- interfaccia ---------------------------------------------------------------------------

def draw_ammo_icon(surface, cx, cy, s, ammo, active=True):
    dk, c, hi = ammo_cols(ammo)
    r = max(3, int(s))
    pygame.draw.circle(surface, dk if active else (44, 46, 54), (cx, cy), r + 2)
    pygame.draw.circle(surface, (16, 18, 24), (cx, cy), r + 1)
    surf = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
    draw_pellet(surf, r * 2, r * 2, r * 0.6, ammo, -math.pi / 4, 255 if active else 120)
    surface.blit(surf, (cx - r * 2, cy - r * 2))


def draw_aim(surface, S, ts, ox, oy, nx, ny, dist, move, ammo="Water") -> bool:
    """Mirino delle mosse della linea. Ritorna False se la forma non è sua."""
    shape = move.shape
    rng = move.range
    if shape == "octishot":
        col = ammo_cols(ammo)[1]
        ex, ey = ox + nx * rng, oy + ny * rng
        w = move.radius
        px, py = -ny * w, nx * w
        for sg in (1, -1):
            pygame.draw.line(surface, col, S(ox + px * sg, oy + py * sg), S(ex + px * sg, ey + py * sg), 1)
        pygame.draw.line(surface, WHITE, S(ox, oy), S(ex, ey), 1)
        draw_pellet(surface, *S(ex, ey), 0.12 * ts, ammo, math.atan2(ny, nx))
        return True
    if shape == "octazooka":
        half = math.radians(move.angle)
        base = math.atan2(ny, nx)
        pts = [S(ox, oy)]
        for i in range(9):
            a = base - half + 2 * half * i / 8
            pts.append(S(ox + math.cos(a) * rng, oy + math.sin(a) * rng))
        pygame.draw.lines(surface, INK[2], True, pts, 1)
        back = float(move.effects.get("backjet", 3.0))
        bx, by = ox - nx * back, oy - ny * back
        pygame.draw.line(surface, AMMO_COLS["Water"][2], S(ox, oy), S(bx, by), 1)
        px, py = -ny * 0.35, nx * 0.35
        tip = S(bx, by)
        l = S(bx + nx * 0.5 + px, by + ny * 0.5 + py)
        r = S(bx + nx * 0.5 - px, by + ny * 0.5 - py)
        pygame.draw.lines(surface, WHITE, False, [l, tip, r], 1)
        return True
    if shape == "octibeam":
        ex, ey = ox + nx * rng, oy + ny * rng
        w = move.radius
        px, py = -ny * w, nx * w
        for sg in (1, -1):
            pygame.draw.line(surface, BEAM[1], S(ox + px * sg, oy + py * sg), S(ex + px * sg, ey + py * sg), 2)
        pygame.draw.line(surface, BEAM[2], S(ox, oy), S(ex, ey), 1)
        return True
    if shape == "octigrab":
        pygame.draw.circle(surface, OCTO[1], S(ox, oy), int(rng * ts), 1)
        d = min(dist, rng)
        cx, cy = S(ox + nx * d, oy + ny * d)
        pygame.draw.circle(surface, SUCKER, (cx, cy), int(0.5 * ts), 1)
        return True
    if shape == "ammoswap":
        return True
    return False
