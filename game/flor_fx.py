"""Grafica della linea Flabébé > Floette > Florges: i FIORI sul terreno (tre
fasi: germoglio, bocciolo, sbocciato, nel colore scelto nella selezione),
effetti istantanei (handler registrati in FXSystem._FX_STYLES), forme nuove
per FXSystem._draw_shapes (petalo in volo, vortice di petali, Solarraggio,
seme lanciato, croci di cura), aree persistenti (Radici, Campo Nebbioso),
sovrapposizioni sulle unità (Petalodanza, bonus dei fiori raccolti), HUD della
passiva Giardino, mirino delle mosse e la tavolozza dei colori della
selezione del Pokémon.

Pixel art a risoluzione nativa: contorno scuro, colore, luce in alto a
sinistra; sprite in cache, a ogni frame solo blit.
"""
from __future__ import annotations

import math
import random

import pygame

import config

COLORS = ("red", "yellow", "orange", "blue", "white")
COLOR_NAMES = {"red": "Rosso", "yellow": "Giallo", "orange": "Arancione",
               "blue": "Blu", "white": "Bianco"}
COLOR_EFFECT = {"red": "+15% danno", "yellow": "+25% velocità", "orange": "scudo 10% HP",
                "blue": "ricariche -1,5 s", "white": "toglie gli stati"}
# petali: (contorno, scuro, colore, luce); centro del fiore
FLOWER_COLS = {
    "red": ((70, 12, 22), (168, 32, 46), (230, 66, 74), (255, 162, 160)),
    "yellow": ((86, 62, 8), (196, 150, 24), (246, 210, 56), (255, 246, 170)),
    "orange": ((88, 36, 8), (196, 92, 24), (246, 146, 52), (255, 210, 150)),
    "blue": ((18, 30, 86), (46, 82, 176), (92, 144, 236), (190, 214, 255)),
    "white": ((70, 70, 86), (176, 176, 190), (236, 236, 242), (255, 255, 255)),
}
CENTER = {"red": (250, 210, 80), "yellow": (232, 120, 40), "orange": (252, 226, 96),
          "blue": (252, 232, 120), "white": (248, 206, 70)}
STEM = ((22, 52, 22), (54, 116, 44), (110, 176, 70))
FAIRY = ((92, 30, 70), (226, 110, 170), (255, 196, 228))
HEAL = ((30, 100, 40), (110, 220, 110), (220, 255, 210))
SOLAR = ((170, 120, 20), (255, 214, 70), (255, 252, 220))
MIST = (246, 214, 240)
ROOT = ((52, 32, 16), (110, 74, 40), (160, 116, 70))
ALLY_RING = (120, 220, 255)
FOE_RING = (255, 96, 86)
FLOR_DEX = (669, 670, 671)
MAX_BY_DEX = {669: 2, 670: 3, 671: 4}


def cols_of(color):
    return FLOWER_COLS.get(color, FLOWER_COLS["red"])


def _al(f, k=2.0):
    return max(0, min(255, int(255 * min(1.0, f * k))))


def is_flor(u) -> bool:
    return getattr(u, "passive_id", "") == "giardino" or getattr(u, "dex", 0) in FLOR_DEX


# --- sprite dei fiori (cache) -------------------------------------------------------------

_SPR: dict = {}


def _petal_poly(cx, cy, r, ang, w=0.55):
    """Petalo a goccia: punta verso il centro del fiore, largo all'esterno."""
    ca, sa = math.cos(ang), math.sin(ang)
    px, py = -sa, ca
    pts = [(cx, cy)]
    for t, ww in ((0.45, w * 0.9), (0.8, w), (1.0, w * 0.55)):
        pts.append((cx + ca * r * t + px * r * ww * 0.5, cy + sa * r * t + py * r * ww * 0.5))
    pts.append((cx + ca * r * 1.08, cy + sa * r * 1.08))
    for t, ww in ((1.0, w * 0.55), (0.8, w), (0.45, w * 0.9)):
        pts.append((cx + ca * r * t - px * r * ww * 0.5, cy + sa * r * t - py * r * ww * 0.5))
    return [(round(x), round(y)) for x, y in pts]


def _leaf(s, x, y, dx, col_out, col, col_hi):
    """Fogliolina di 3-4 px che parte dallo stelo verso dx (±1)."""
    pts = [(x, y), (x + dx * 2, y - 2), (x + dx * 4, y - 2), (x + dx * 3, y)]
    pygame.draw.polygon(s, col_out, [(px + (1 if dx > 0 else -1) * 0, py + 1) for px, py in pts])
    pygame.draw.polygon(s, col, pts)
    s.set_at((x + dx * 2, y - 2), col_hi)


def flower_sprite(color, phase, big=False):
    """Sprite del fiore (origine = in basso al centro). phase 0/1/2."""
    key = (color, phase, big)
    spr = _SPR.get(key)
    if spr is not None:
        return spr
    W, H = (21, 24) if big else (17, 20)
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    out, dk, c, hi = cols_of(color)
    so, sc, sh = STEM
    cx = W // 2
    base = H - 1
    if phase == 0:   # germoglio: stelo corto e due foglioline a V
        pygame.draw.line(s, so, (cx + 1, base), (cx + 1, base - 5))
        pygame.draw.line(s, sc, (cx, base), (cx, base - 5))
        _leaf(s, cx, base - 4, -1, so, sc, sh)
        _leaf(s, cx, base - 5, 1, so, sc, sh)
        s.set_at((cx, base - 6), sh)
    else:
        top = base - (9 if phase == 1 else 10) - (2 if big else 0)
        # stelo leggermente curvo
        for y in range(top, base + 1):
            dx = int(round(math.sin((y - top) / max(1, base - top) * math.pi) * 0.8))
            s.set_at((cx + dx + 1, y), so)
            s.set_at((cx + dx, y), sc)
        _leaf(s, cx, base - 3, -1, so, sc, sh)
        _leaf(s, cx, base - 5, 1, so, sc, sh)
        if phase == 1:   # bocciolo: goccia chiusa del colore, sepali verdi
            r = 3
            hy = top - 2
            pygame.draw.ellipse(s, out, pygame.Rect(cx - r - 1, hy - r - 2, 2 * r + 3, 2 * r + 5))
            pygame.draw.ellipse(s, dk, pygame.Rect(cx - r, hy - r - 1, 2 * r + 1, 2 * r + 3))
            pygame.draw.ellipse(s, c, pygame.Rect(cx - r, hy - r - 1, 2 * r, 2 * r + 1))
            s.set_at((cx - 1, hy - r), hi)
            s.set_at((cx - 2, hy - r + 1), hi)
            pygame.draw.line(s, sc, (cx - 2, hy + r), (cx, hy + 1))
            pygame.draw.line(s, sc, (cx + 2, hy + r), (cx, hy + 1))
        else:            # sbocciato: 5 petali + centro
            R = 6 if big else 5
            hy = top - R + 2
            angs = [-math.pi / 2 + k * math.tau / 5 for k in range(5)]
            for a in angs:   # contorno
                pygame.draw.polygon(s, out, _petal_poly(cx, hy, R + 1, a, 0.95))
            for a in angs:
                pygame.draw.polygon(s, dk, _petal_poly(cx, hy, R, a, 0.85))
            for a in angs:   # luce: meta' alta-sinistra dei petali piu' chiara
                pygame.draw.polygon(s, c, _petal_poly(cx - 0.5, hy - 0.5, R - 1, a, 0.7))
            for a in angs:
                if math.cos(a) < 0.3 and math.sin(a) < 0.3:
                    x = cx + math.cos(a) * (R - 2) - 0.5
                    y = hy + math.sin(a) * (R - 2) - 0.5
                    s.set_at((round(x), round(y)), hi)
            cc = CENTER.get(color, (250, 210, 80))
            pygame.draw.circle(s, out, (cx, hy), 2)
            pygame.draw.circle(s, cc, (cx, hy), 1)
            s.set_at((cx - 1, hy - 1), (255, 255, 230))
    _SPR[key] = s
    return s


def _phase(fl, now):
    if now >= fl["bloom"] - 1e-6:
        return 2
    if now >= fl["bud"] - 1e-6:
        return 1
    return 0


def draw_flower(surface, camera, fl, now, my_team=None):
    """Fiore sul terreno: ombra, anello della squadra (azzurro alleato, rosso
    nemico), alone del colore quando è sbocciato, sprite della fase. Negli
    ultimi 3 s lampeggia."""
    ts = config.TILE_SIZE
    p = fl["pos"]
    gx, gy = camera.world_to_screen(p.x * ts, p.y * ts)
    left = fl["end"] - now
    if left < 3.0 and int(now * 6) % 2 == 0:
        alpha = 110
    else:
        alpha = 255
    ph = _phase(fl, now)
    col = fl.get("color", "red")
    cols = cols_of(col)
    ring = ALLY_RING if my_team is None or fl.get("team") == my_team else FOE_RING
    rw, rh = int(0.62 * ts), int(0.3 * ts)
    sh = pygame.Surface((rw + 4, rh + 4), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 70), pygame.Rect(2, 2, rw, rh))
    if ph == 2:
        pulse = 0.5 + 0.5 * math.sin(now * 4.0 + fl.get("seed", 0))
        pygame.draw.ellipse(sh, (*cols[2], int(40 + 40 * pulse)), pygame.Rect(0, 0, rw + 4, rh + 4))
    pygame.draw.ellipse(sh, (*ring, 150), pygame.Rect(1, 1, rw + 2, rh + 2), 1)
    surface.blit(sh, (gx - sh.get_width() // 2, gy - sh.get_height() // 2))
    spr = flower_sprite(col, ph, bool(fl.get("extra")))
    if alpha < 255:
        spr = spr.copy()
        spr.set_alpha(alpha)
    # ondeggia appena (1 px) quando è sbocciato
    dx = int(round(math.sin(now * 2.2 + fl.get("seed", 0)) * 0.7)) if ph == 2 else 0
    surface.blit(spr, (gx - spr.get_width() // 2 + dx, gy - spr.get_height() + 2))
    if fl.get("extra") and ph == 2:   # Giardino Reale: scintille dorate
        rnd = random.Random(int(now * 8) + fl.get("seed", 0))
        for _ in range(2):
            x = gx + rnd.randint(-8, 8)
            y = gy - rnd.randint(6, 22)
            surface.set_at((x, y), SOLAR[2])
            surface.set_at((x + 1, y), SOLAR[1])
    # germoglio/bocciolo: tacche della crescita sotto (quanto manca a sbocciare)
    if ph < 2 and fl["bloom"] > fl["born"]:
        k = (now - fl["born"]) / max(0.1, fl["bloom"] - fl["born"])
        w = int(0.5 * ts)
        x0, y0 = gx - w // 2, gy + rh // 2 + 2
        bar = pygame.Surface((w + 2, 3), pygame.SRCALPHA)
        bar.fill((16, 20, 16, 120))
        bar.fill((*STEM[2], 230), pygame.Rect(1, 1, int(w * max(0.0, min(1.0, k))), 1))
        surface.blit(bar, (x0 - 1, y0 - 1))


def draw_flowers(surface, camera, m, now, my_team=None):
    fls = getattr(m, "flowers", ())
    for fl in sorted(fls, key=lambda f: f["pos"].y):
        draw_flower(surface, camera, fl, now, my_team)


def draw_roots(surface, camera, z, now):
    """Radici: area di cura (radici che si allargano + croci verdi che salgono)."""
    ts = config.TILE_SIZE
    c = z["c"]
    gx, gy = camera.world_to_screen(c.x * ts, c.y * ts)
    r = z["radius"] * ts
    dur = max(0.1, z["end"] - z["start"])
    k = (now - z["start"]) / dur
    fade = max(0.0, min(1.0, (1.0 - k) * 4.0, k * 8.0))
    w, h = int(2 * r) + 4, int(r) + 4
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (*HEAL[1], int(46 * fade)), pygame.Rect(2, 2, w - 4, h - 4))
    pygame.draw.ellipse(s, (*HEAL[2], int(150 * fade)), pygame.Rect(2, 2, w - 4, h - 4), 1)
    rnd = random.Random(int(z["start"] * 10))
    grow = min(1.0, k * 3.0)
    for i in range(7):
        a = i * math.tau / 7 + rnd.uniform(-0.3, 0.3)
        x, y = w / 2, h / 2
        L = r * rnd.uniform(0.5, 0.95) * grow
        steps = 6
        for j in range(steps):
            a2 = a + rnd.uniform(-0.4, 0.4)
            nx = x + math.cos(a2) * L / steps
            ny = y + math.sin(a2) * L / steps * 0.5
            pygame.draw.line(s, (*ROOT[1], int(220 * fade)), (int(x), int(y)), (int(nx), int(ny)), 1)
            x, y = nx, ny
    surface.blit(s, (gx - w // 2, gy - h // 2))
    rnd = random.Random(int(now * 4) + int(z["start"] * 10))
    for _ in range(3):
        a = rnd.uniform(0, math.tau)
        d = rnd.uniform(0, r * 0.8)
        t = (now * 1.5 + rnd.random()) % 1.0
        x = gx + math.cos(a) * d
        y = gy + math.sin(a) * d * 0.5 - t * 0.6 * ts
        _plus(surface, int(x), int(y), HEAL, int(230 * fade * (1 - t)))


def _plus(surface, x, y, cols, alpha=255):
    if alpha <= 0:
        return
    s = pygame.Surface((5, 5), pygame.SRCALPHA)
    pygame.draw.line(s, (*cols[0], alpha), (2, 0), (2, 4))
    pygame.draw.line(s, (*cols[0], alpha), (0, 2), (4, 2))
    s.set_at((2, 1), (*cols[1], alpha))
    s.set_at((2, 3), (*cols[1], alpha))
    s.set_at((1, 2), (*cols[1], alpha))
    s.set_at((3, 2), (*cols[1], alpha))
    s.set_at((2, 2), (*cols[2], alpha))
    surface.blit(s, (x - 2, y - 2))


def draw_mist(surface, camera, z, now):
    """Campo Nebbioso: velo rosa chiaro con chiazze che respirano, bordo a
    trattini che gira e scintille che salgono."""
    ts = config.TILE_SIZE
    c = z["c"]
    gx, gy = camera.world_to_screen(c.x * ts, c.y * ts)
    r = z["radius"] * ts
    dur = max(0.1, z["end"] - z["start"])
    k = (now - z["start"]) / dur
    fade = max(0.0, min(1.0, (1.0 - k) * 5.0, k * 10.0))
    w, h = int(2 * r) + 4, int(r) + 4
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (*MIST, int(44 * fade)), pygame.Rect(2, 2, w - 4, h - 4))
    rnd = random.Random(int(z["start"] * 7))
    for i in range(6):
        a = rnd.uniform(0, math.tau) + now * 0.3 * (1 if i % 2 else -1)
        d = rnd.uniform(0.2, 0.6) * r
        rr = r * rnd.uniform(0.22, 0.34) * (1 + 0.1 * math.sin(now * 2 + i))
        x = w / 2 + math.cos(a) * d
        y = h / 2 + math.sin(a) * d * 0.5
        pygame.draw.ellipse(s, (255, 236, 250, int(34 * fade)),
                            pygame.Rect(int(x - rr), int(y - rr * 0.5), int(2 * rr), int(rr)))
    n = max(12, int(r * 0.7))
    for i in range(n):
        if i % 2:
            continue
        a0 = i * math.tau / n + now * 0.5
        a1 = a0 + math.tau / n * 0.8
        p0 = (w / 2 + math.cos(a0) * (w / 2 - 3), h / 2 + math.sin(a0) * (h / 2 - 3))
        p1 = (w / 2 + math.cos(a1) * (w / 2 - 3), h / 2 + math.sin(a1) * (h / 2 - 3))
        pygame.draw.line(s, (*FAIRY[2], int(210 * fade)), p0, p1, 1)
    surface.blit(s, (gx - w // 2, gy - h // 2))
    rnd = random.Random(int(now * 5) + int(z["start"] * 7))
    for _ in range(5):
        a = rnd.uniform(0, math.tau)
        d = rnd.uniform(0, r * 0.9)
        t = (now + rnd.random()) % 1.0
        x = int(gx + math.cos(a) * d)
        y = int(gy + math.sin(a) * d * 0.5 - t * 0.8 * ts)
        surface.set_at((x, y), (255, 240, 252))


# --- petali e forme ----------------------------------------------------------------------------

def draw_petal(surface, x, y, r, ang, color, alpha=255):
    """Petalo singolo in volo (goccia con contorno e luce)."""
    out, dk, c, hi = cols_of(color) if color in FLOWER_COLS else (FAIRY[0], FAIRY[0], FAIRY[1], FAIRY[2])
    sz = int(r * 2 + 6)
    s = pygame.Surface((sz, sz), pygame.SRCALPHA)
    cx = cy = sz / 2
    tip = (cx - math.cos(ang) * r, cy - math.sin(ang) * r)
    pygame.draw.polygon(s, (*out, alpha), _petal_poly(tip[0], tip[1], 2 * r + 1, ang, 0.95))
    pygame.draw.polygon(s, (*c, alpha), _petal_poly(tip[0], tip[1], 2 * r, ang, 0.8))
    s.set_at((int(cx - 1), int(cy - 1)), (*hi, alpha))
    surface.blit(s, (int(x - sz / 2), int(y - sz / 2)))


SHAPES = ("florpetal", "florswirl", "florsolar", "florseedarc", "florplus")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    if t < 0:
        return
    color = s.get("color", "fairy")
    if kind == "florpetal":
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t)
        lift = s.get("lift", 0.35) * ts + math.sin(u * math.pi) * s.get("arc", 0.0) * ts
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - lift
        ang = s.get("ang0", 0.0) + t * s.get("spin", 9.0)
        draw_petal(overlay, x, y, s.get("r", 0.09) * ts, ang, color, _al(f, 3.0))
    elif kind == "florswirl":
        cx, cy = S(*s["c"])
        r = (s.get("r0", 0.3) + (s.get("r1", 2.0) - s.get("r0", 0.3)) * min(1.0, t * 1.4)) * ts
        n = s.get("n", 12)
        rot = s.get("rot0", 0.0) + t * s.get("spin", 7.0)
        al = _al(f, 2.5)
        for k in range(n):
            an = rot + k * math.tau / n
            rr = r * (0.75 + 0.25 * ((k * 37) % 7) / 6)
            x = cx + math.cos(an) * rr
            y = cy + math.sin(an) * rr * 0.5 - s.get("lift", 0.3) * ts - ((k % 3) * 0.08 * ts)
            col = color if k % 3 else "white" if color != "white" else "red"
            if s.get("mono"):
                col = color
            draw_petal(overlay, x, y, s.get("pr", 0.08) * ts, an + math.pi / 2, col, al)
    elif kind == "florsolar":
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        lift = 0.3 * ts
        ay -= lift
        by -= lift
        w = max(1, int(s.get("w", 0.35) * ts * min(1.0, f * 2.0)))
        al = _al(f, 2.0)
        pygame.draw.line(overlay, (*SOLAR[0], al), (ax, ay), (bx, by), w + 2)
        pygame.draw.line(overlay, (*SOLAR[1], al), (ax, ay), (bx, by), w)
        pygame.draw.line(overlay, (*SOLAR[2], al), (ax, ay), (bx, by), max(1, w // 3))
        rnd = random.Random(s.get("seed", 1) + int(t * 20))
        L = math.hypot(bx - ax, by - ay) or 1.0
        nx, ny = (bx - ax) / L, (by - ay) / L
        for _ in range(5):
            u = rnd.random()
            off = rnd.uniform(-1, 1) * w
            x = ax + (bx - ax) * u - ny * off
            y = ay + (by - ay) * u + nx * off
            overlay.fill((*SOLAR[2], al), pygame.Rect(int(x), int(y), 2, 2))
        pygame.draw.circle(overlay, (*SOLAR[2], al), (int(bx), int(by)), max(2, int(w * 0.9)))
    elif kind == "florseedarc":
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.7)
        h = 1.4 * ts * math.sin(u * math.pi)
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - 0.3 * ts - h
        if u < 1.0:
            pygame.draw.circle(overlay, (60, 36, 16, 255), (int(x), int(y)), 3)
            pygame.draw.circle(overlay, (160, 110, 60, 255), (int(x), int(y)), 2)
            overlay.set_at((int(x) - 1, int(y) - 1), (230, 200, 150, 255))
            for k in (1, 2):
                uk = max(0.0, u - 0.08 * k)
                hk = 1.4 * ts * math.sin(uk * math.pi)
                qx = ax + (bx - ax) * uk
                qy = ay + (by - ay) * uk - 0.3 * ts - hk
                overlay.fill((*cols_of(color)[2], 140 // k), pygame.Rect(int(qx), int(qy), 2, 2))
        else:
            k = (t - 0.7) / 0.3
            rnd = random.Random(s.get("seed", 2))
            for _ in range(7):
                an = rnd.uniform(math.pi, math.tau)
                d = k * 0.4 * ts * rnd.uniform(0.5, 1.0)
                overlay.fill((*ROOT[2], _al(f, 3.0)),
                             pygame.Rect(int(bx + math.cos(an) * d), int(by + math.sin(an) * d * 0.6), 2, 2))
    elif kind == "florplus":
        cx, cy = S(*s["c"])
        _plus(overlay, int(cx), int(cy - t * s.get("rise", 0.8) * ts), s.get("cols", HEAL), _al(f, 2.5))


# --- handler degli eventi (FXSystem._FX_STYLES) ------------------------------------------------

def _sh(fx, **kw):
    kw.setdefault("col", FAIRY[1])
    fx._shape(**kw)


def _bits(fx, c, n, cols, speed=2.0, life=(0.2, 0.4), size=1, up=0.0):
    for _ in range(n):
        an = random.uniform(0, math.tau)
        v = random.uniform(0.4, 1.0) * speed
        fx._add(c[0], c[1], math.cos(an) * v, math.sin(an) * v * 0.5 - up,
                random.uniform(*life), random.choice(cols), size)


def _pluses(fx, c, n, spread=0.6, cols=HEAL, life=0.8):
    for k in range(n):
        _sh(fx, kind="florplus", c=(c[0] + random.uniform(-spread, spread),
                                      c[1] + random.uniform(-spread, spread) * 0.5 - 0.3),
                  cols=cols, life=life, wait=0.06 * k, rise=random.uniform(0.6, 1.0))


def _petal_burst(fx, c, color, n=8, r=0.9, life=0.5):
    for k in range(n):
        an = k * math.tau / n + random.uniform(-0.3, 0.3)
        b = (c[0] + math.cos(an) * r, c[1] + math.sin(an) * r * 0.6)
        _sh(fx, kind="florpetal", a=c, b=b, color=color, life=life, r=0.08, lift=0.4,
                  arc=0.3, ang0=an, spin=random.uniform(-8, 8))


def fx_florshot(fx, e, col):
    """Attacco base: petalo rosa che rotea fino al bersaglio."""
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return
    _sh(fx, kind="florpetal", a=a, b=b, color="fairy", life=0.24, r=0.1, lift=0.4,
              ang0=random.uniform(0, math.tau), spin=14.0)
    _sh(fx, kind="florpetal", a=a, b=b, color="fairy", life=0.26, r=0.07, lift=0.32,
              ang0=random.uniform(0, math.tau), spin=-12.0, wait=0.03)
    _bits(fx, (b[0], b[1] - 0.35), 5, FAIRY[1:], speed=1.6, life=(0.15, 0.3))


def fx_florseed(fx, e, col):
    if e.get("kind") != "projectile":
        return
    _sh(fx, kind="florseedarc", a=e["a"], b=e["b"], color=e.get("color", "red"), life=0.55,
              seed=random.randrange(999))


def fx_florheal(fx, e, col):
    if e.get("kind") != "buff":
        return
    c = e["c"]
    dbl = bool(e.get("double"))
    a = e.get("a")
    if a is not None and (abs(a[0] - c[0]) + abs(a[1] - c[1])) > 0.5:
        for k in range(5):
            _sh(fx, kind="florpetal", a=a, b=c, color="fairy", life=0.32, r=0.07, lift=0.45,
                      arc=0.4 + 0.1 * k, ang0=k, spin=10.0, wait=0.03 * k)
    fx._shape(kind="ring", c=c, r0=0.2, r1=1.1 if dbl else 0.8,
              col=SOLAR[1] if dbl else HEAL[1], life=0.4, wd=0.08)
    _pluses(fx, c, 7 if dbl else 4, cols=HEAL)
    _sh(fx, kind="florswirl", c=c, r0=0.9, r1=0.3, n=8, color="fairy", mono=True,
              life=0.5, spin=6.0, pr=0.06)


def fx_florstorm(fx, e, col):
    kind = e.get("kind")
    if kind == "area":
        r = e.get("radius", 3.0)
        color = e.get("color", "red")
        _sh(fx, kind="florswirl", c=e["c"], r0=0.4, r1=r, n=16, color=color, life=0.7,
                  spin=9.0, rot0=random.uniform(0, math.tau), pr=0.1)
        _sh(fx, kind="florswirl", c=e["c"], r0=0.2, r1=r * 0.6, n=10, color="white",
                  life=0.6, spin=-11.0, rot0=random.uniform(0, math.tau), pr=0.07, wait=0.05)
        fx._shape(kind="ring", c=e["c"], r0=r * 0.3, r1=r, col=(110, 200, 90), life=0.35, wd=0.06)
    elif kind == "dash":
        a, b = e.get("a"), e.get("b")
        if a is not None and b is not None:
            fx._shape(kind="windline", a=(a[0], a[1] - 0.3), b=(b[0], b[1] - 0.3),
                      col=(220, 250, 200), life=0.25)


def fx_florpick(fx, e, col):
    c = e["c"]
    color = e.get("color", "red")
    fx._shape(kind="ring", c=c, r0=0.15, r1=0.9, col=cols_of(color)[2], life=0.35, wd=0.08)
    _petal_burst(fx, c, color, 9, 0.9, 0.55)
    _pluses(fx, c, 3)


def fx_florwilt(fx, e, col):
    c = e["c"]
    color = e.get("color", "red")
    for k in range(5):
        a = (c[0] + random.uniform(-0.15, 0.15), c[1] - 0.1)
        b = (a[0] + random.uniform(-0.5, 0.5), c[1] + random.uniform(0.0, 0.2))
        _sh(fx, kind="florpetal", a=a, b=b, color=color, life=0.9, r=0.06, lift=0.45 - 0.05 * k,
                  arc=-0.2, ang0=k, spin=3.0, wait=0.05 * k)


def fx_florcrush(fx, e, col):
    c = e["c"]
    color = e.get("color", "red")
    cc = cols_of(color)
    _bits(fx, (c[0], c[1] - 0.15), 10, (cc[1], cc[2], STEM[1], ROOT[1]), speed=2.2,
          life=(0.2, 0.45), size=2)
    fx._shape(kind="ring", c=c, r0=0.1, r1=0.6, col=ROOT[2], life=0.25, wd=0.06)


def fx_florbloom(fx, e, col):
    c = e["c"]
    color = e.get("color", "red")
    fx._shape(kind="ring", c=c, r0=0.5, r1=0.1, col=cols_of(color)[3], life=0.3, wd=0.07)
    _bits(fx, (c[0], c[1] - 0.45), 6, (cols_of(color)[3], (255, 255, 230)), speed=1.6,
          life=(0.2, 0.4), up=0.4)


def fx_floraroma(fx, e, col):
    c = e["c"]
    _sh(fx, kind="florswirl", c=c, r0=0.8, r1=0.2, n=6, color="white", mono=True, life=0.6,
              spin=8.0, pr=0.06, lift=0.6)
    _bits(fx, (c[0], c[1] - 0.6), 8, ((255, 236, 250), (200, 250, 200), (255, 255, 255)),
          speed=1.2, life=(0.4, 0.7), up=0.9)


def fx_florsym(fx, e, col):
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return
    for k in range(6):
        _sh(fx, kind="florpetal", a=a, b=b, color="fairy", life=0.45, r=0.06, lift=0.5,
                  arc=0.25 * (1 if k % 2 else -1), ang0=k, spin=6.0, wait=0.05 * k)
    fx._shape(kind="ring", c=b, r0=0.2, r1=0.9, col=(150, 230, 120), life=0.4, wd=0.07)


def fx_flordance(fx, e, col):
    c = e["c"]
    _sh(fx, kind="florswirl", c=c, r0=0.3, r1=2.0, n=12, color="fairy", mono=True, life=0.5,
              spin=10.0, pr=0.08)


def fx_flormist(fx, e, col):
    c = e["c"]
    r = e.get("radius", 4.0)
    fx._shape(kind="ring", c=c, r0=0.5, r1=r, col=MIST, life=0.5, wd=0.1)
    _bits(fx, (c[0], c[1] - 0.4), 16, (MIST, (255, 255, 255), FAIRY[2]), speed=r * 1.2,
          life=(0.3, 0.6))


def fx_florgarden(fx, e, col):
    c = e["c"]
    r = e.get("radius", 3.0)
    color = e.get("color", "red")
    fx._shape(kind="ring", c=c, r0=0.3, r1=r, col=SOLAR[1], life=0.6, wd=0.08)
    _sh(fx, kind="florswirl", c=c, r0=r, r1=0.5, n=18, color=color, life=0.8, spin=5.0, pr=0.09)
    _bits(fx, (c[0], c[1] - 0.4), 20, (SOLAR[1], SOLAR[2], cols_of(color)[2]), speed=r * 1.4,
          life=(0.3, 0.7), up=0.5)


def fx_florsolar(fx, e, col):
    if e.get("kind") != "projectile":
        return
    _sh(fx, kind="florsolar", a=e["a"], b=e["b"], life=0.5, w=0.22, seed=random.randrange(999))
    b = e["b"]
    fx._shape(kind="flash", c=(b[0], b[1] - 0.3), r=0.55, col=SOLAR[2], life=0.25)
    _bits(fx, (b[0], b[1] - 0.3), 8, SOLAR, speed=2.4, life=(0.15, 0.35))


def fx_florsolarflower(fx, e, col):
    c = e["c"]
    color = e.get("color", "red")
    fx._shape(kind="flash", c=(c[0], c[1] - 0.45), r=0.6, col=SOLAR[2], life=0.3)
    fx._shape(kind="ring", c=c, r0=0.3, r1=e.get("radius", 3.0), col=HEAL[1], life=0.45, wd=0.06)
    _petal_burst(fx, c, color, 6, 0.7, 0.5)
    _pluses(fx, c, 3)


STYLES = {
    "florshot": fx_florshot, "florseed": fx_florseed, "florheal": fx_florheal,
    "florstorm": fx_florstorm, "florpick": fx_florpick, "florwilt": fx_florwilt,
    "florcrush": fx_florcrush, "florbloom": fx_florbloom, "floraroma": fx_floraroma,
    "florsym": fx_florsym, "flordance": fx_flordance, "flormist": fx_flormist,
    "florgarden": fx_florgarden, "florsolar": fx_florsolar,
    "florsolarflower": fx_florsolarflower,
}


# --- sulle unità ----------------------------------------------------------------------------------

def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Petalodanza (petali che girano attorno), bonus dei fiori raccolti
    (petali del colore ai piedi), Campo Nebbioso (scintille rosa)."""
    r = getattr(u, "radius", 0.5) * ts
    if getattr(u, "flor_dance_until", -1.0) > now:
        color = getattr(u, "flower_color", "red")
        for k in range(8):
            an = now * 7.0 + k * math.tau / 8
            x = gx + math.cos(an) * r * 2.2
            y = gy - r * 0.6 + math.sin(an) * r * 1.0
            draw_petal(surface, x, y, 3.2, an + math.pi / 2, color if k % 2 else "white", 230)
    buffs = []
    if getattr(u, "flor_red_until", -1.0) > now:
        buffs.append("red")
    if getattr(u, "flor_yellow_until", -1.0) > now:
        buffs.append("yellow")
    for i, color in enumerate(buffs):
        for k in range(3):
            an = now * 3.0 + k * math.tau / 3 + i * 0.9
            x = gx + math.cos(an) * r * 1.3
            y = gy + math.sin(an) * r * 0.45
            draw_petal(surface, x, y, 2.0, an, color, 220)
    if getattr(u, "flor_mist_until", -1.0) > now:
        rnd = random.Random(int(now * 6) + getattr(u, "id", 0))
        for _ in range(3):
            x = gx + rnd.randint(-int(r), int(r))
            y = gy - rnd.randint(0, int(r * 2.2))
            surface.set_at((x, y), (255, 236, 250))
    if getattr(u, "flor_sym_until", -1.0) > now:
        w, h = int(r * 2.6), int(r * 1.0)
        s = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (150, 230, 120, 170), pygame.Rect(1, 1, w, h), 1)
        surface.blit(s, (gx - w // 2 - 1, gy - h // 2 - 1))


# --- interfaccia ----------------------------------------------------------------------------------

def icon(color, phase=2, scale=2):
    key = ("icon", color, phase, scale)
    spr = _SPR.get(key)
    if spr is None:
        base = flower_sprite(color, phase)
        spr = pygame.transform.scale(base, (base.get_width() * scale, base.get_height() * scale))
        _SPR[key] = spr
    return spr


def draw_color_picker(surface, x, y, w, sel, font, small=None, label=True):
    """Cinque caselle col fiore del colore; ritorna [(rect, colore)]."""
    out = []
    if label:
        t = font.render("Colore dei fiori (tasti 1-5)", True, (210, 210, 220))
        surface.blit(t, (x, y))
        y += t.get_height() + 4
    n = len(COLORS)
    side = max(26, min(48, (w - 6 * (n - 1)) // n if small is None else (w - 150) // n - 6))
    for i, c in enumerate(COLORS):
        r = pygame.Rect(x + i * (side + 6), y, side, side)
        on = c == sel
        pygame.draw.rect(surface, (52, 46, 60) if on else (30, 30, 38), r, border_radius=6)
        pygame.draw.rect(surface, (240, 200, 90) if on else (80, 80, 92), r, 2, border_radius=6)
        sc = 2 if side >= 40 else 1
        img = icon(c, 2, sc)
        surface.blit(img, (r.centerx - img.get_width() // 2, r.bottom - img.get_height() - 2))
        out.append((r, c))
    if small is not None:   # effetto del colore a destra delle caselle
        col = cols_of(sel)[3] if sel != "white" else (240, 240, 245)
        tx = x + n * (side + 6) + 6
        t1 = small.render(COLOR_NAMES.get(sel, sel), True, col)
        t2 = small.render(COLOR_EFFECT.get(sel, ""), True, (210, 210, 220))
        top = y + (side - t1.get_height() - t2.get_height()) // 2
        surface.blit(t1, (tx, top))
        surface.blit(t2, (tx, top + t1.get_height()))
    return out


COLOR_KEYS = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3, pygame.K_5: 4,
              pygame.K_KP1: 0, pygame.K_KP2: 1, pygame.K_KP3: 2, pygame.K_KP4: 3, pygame.K_KP5: 4}


def draw_hud(surface, font, p, bx, y0, bh, flowers, now):
    """Passiva Giardino: fiore del colore scelto e i fiori piantati (pallini
    pieni = sbocciati), con il nome dell'effetto sopra."""
    color = getattr(p, "flower_color", "red")
    box = pygame.Rect(bx, y0, bh, bh)
    pygame.draw.rect(surface, (34, 30, 40), box)
    img = icon(color, 2, 2 if bh >= 40 else 1)
    surface.blit(img, (box.centerx - img.get_width() // 2, box.bottom - img.get_height() - 1))
    pygame.draw.rect(surface, cols_of(color)[2], box, 2)
    mx = MAX_BY_DEX.get(getattr(p, "dex", 671), 4)
    regular = [f for f in flowers if not f.get("extra")]
    extra = [f for f in flowers if f.get("extra")]
    x = box.right + 6
    step = max(7, bh // max(4, mx))
    for k in range(mx):
        y = y0 + step // 2 + k * step
        if k < len(regular):
            ph = _phase(regular[k], now)
            c = cols_of(regular[k].get("color", color))
            pygame.draw.circle(surface, c[0], (x, y), 4)
            pygame.draw.circle(surface, c[2] if ph == 2 else STEM[1], (x, y), 3)
            if ph == 2:
                surface.set_at((x - 1, y - 1), c[3])
        else:
            pygame.draw.circle(surface, (70, 70, 80), (x, y), 3, 1)
    if extra:
        t = font.render(f"+{len(extra)}", True, SOLAR[1])
        surface.blit(t, (x + 6, y0))
    surface.blit(font.render(f"{COLOR_NAMES.get(color, color)}: {COLOR_EFFECT.get(color, '')}",
                             True, cols_of(color)[3] if color != "white" else (240, 240, 245)),
                 (bx - 4, y0 - 18))


def draw_aim(surface, S, ts, ox, oy, nx, ny, dist, move) -> bool:
    """Mirino delle mosse della linea. Ritorna False se la forma non è sua."""
    shape = move.shape
    rng = move.range
    if shape not in ("florseed", "florheal", "florstorm", "florgarden", "florsolar"):
        return False
    if shape in ("florseed", "florheal", "florgarden"):
        pygame.draw.circle(surface, (150, 210, 130), S(ox, oy), int(rng * ts), 1)
        d = min(dist, rng)
        cx, cy = S(ox + nx * d, oy + ny * d)
        if shape == "florseed":
            img = flower_sprite("red", 0)
            surface.blit(img, (cx - img.get_width() // 2, cy - img.get_height() + 2))
            pygame.draw.circle(surface, (220, 250, 200), (cx, cy), int(0.45 * ts), 1)
        elif shape == "florheal":
            pygame.draw.circle(surface, HEAL[1], (cx, cy), int(1.0 * ts), 1)
            fr = float(move.effects.get("flower_radius", 3.0))
            pygame.draw.circle(surface, FAIRY[2], (cx, cy), int(fr * ts), 1)
            _plus(surface, cx, cy - int(0.4 * ts), HEAL)
        else:
            pygame.draw.circle(surface, SOLAR[1], (cx, cy), int(move.radius * ts), 2)
        return True
    if shape == "florstorm":
        mist = move.effects.get("mist")
        r = float(mist.get("radius", 4.0)) if mist else move.radius
        pygame.draw.circle(surface, MIST if mist else (150, 220, 120), S(ox, oy), int(r * ts), 2)
        fr = float(move.effects.get("flower_range", 8.0))
        _dashed_circle(surface, S(ox, oy), fr * ts, FAIRY[2])
        return True
    if shape == "florsolar":
        _dashed_circle(surface, S(ox, oy), rng * ts, SOLAR[1])
        return True
    return False


def _dashed_circle(surface, c, r, col, n=40):
    for i in range(0, n, 2):
        a0 = i * math.tau / n
        a1 = (i + 1) * math.tau / n
        pygame.draw.line(surface, col, (c[0] + math.cos(a0) * r, c[1] + math.sin(a0) * r),
                         (c[0] + math.cos(a1) * r, c[1] + math.sin(a1) * r), 1)
