"""Grafica di Spiritomb (passiva I 108 Spiriti e mosse), disegnata dallo stato
del Match a ogni frame: spiriti (fiammelle verde lime), aura dei risvegli,
proiettili di Stordiraggio/Neropulsar/Finta, legami di Malcomune e ondata della
Legione dei 108.

Pixel art: le fiammelle sono sprite piccoli disegnati a risoluzione nativa (senza
antialias) e messi in cache per fotogramma; ogni frame solo blit.
"""
from __future__ import annotations

import math

import pygame

import config

# Fiammella verde lime: contorno scuro -> corpo -> interno chiaro -> cuore quasi bianco.
LIME_OUT = (34, 74, 18)
LIME_DK = (86, 168, 30)
LIME = (160, 236, 52)
LIME_HI = (214, 255, 128)
LIME_CORE = (246, 255, 214)
GLOW = (150, 240, 60)
VIOLET = (120, 80, 170)
VIOLET_DK = (52, 30, 78)

FLAME_FRAMES = 4
_FLAME_CACHE: dict = {}

BEAM_PAL = {   # fx della mossa -> (contorno, corpo, chiaro)
    "spiritbeam": (LIME_OUT, LIME, LIME_CORE),
    "darkbeam": (VIOLET_DK, (110, 64, 168), (214, 176, 255)),
    "feintbeam": ((22, 16, 30), (70, 52, 92), (176, 150, 206)),
}


def _flame(h: int, frame: int) -> pygame.Surface:
    """Fiammella alta `h` px: bulbo tondo in basso e punta che ondeggia in alto
    (4 fotogrammi). Strati netti, niente sfumature."""
    key = (h, frame)
    s = _FLAME_CACHE.get(key)
    if s is not None:
        return s
    r = max(2, h // 3)
    w = 2 * r + 5
    s = pygame.Surface((w, h + 3), pygame.SRCALPHA)
    cx = w // 2
    by = h + 1 - r                       # centro del bulbo
    sway = (-1, 0, 1, 0)[frame % 4]
    tip = (cx + sway, 0)

    def body(grow, dy, shrink_tip):
        rr = r + grow
        pygame.draw.circle(s, col, (cx, by + dy), rr)
        pygame.draw.polygon(s, col, [(cx - rr, by + dy), (cx + rr, by + dy),
                                     (tip[0] - sway * shrink_tip // 2, tip[1] + shrink_tip)])

    col = LIME_OUT
    body(1, 0, 0)
    col = LIME_DK
    body(0, 0, 1)
    col = LIME
    body(-1, 1, max(2, h // 4))
    col = LIME_HI
    pygame.draw.circle(s, col, (cx, by + 1), max(1, r - 2))
    pygame.draw.circle(s, LIME_CORE, (cx - (1 if r > 2 else 0), by + 1), max(1, r // 2 - 1))
    _FLAME_CACHE[key] = s
    return s


def _glow(surface, x, y, r, col, a):
    g = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
    pygame.draw.circle(g, (*col, a), (r, r), r)
    pygame.draw.circle(g, (*col, min(255, a + 30)), (r, r), max(1, r * 2 // 3))
    surface.blit(g, (x - r, y - r))


def draw_flame(surface, x, y, h, now, phase=0.0, alpha=255):
    """Fiammella con la base in (x, y) dello schermo."""
    fr = int(now * 8.0 + phase * 4.0) % FLAME_FRAMES
    img = _flame(h, fr)
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    surface.blit(img, (x - img.get_width() // 2, y - img.get_height()))


def draw_spirits(surface, camera, spirits, team, now, reach=None, pick=None):
    """Spiriti della squadra `team` (gli altri sono invisibili). `reach` =
    (centro, raggio) di Richiamo degli Spiriti mentre si mira: gli spiriti
    raggiungibili pulsano, `pick` è quello che verrebbe scelto."""
    ts = config.TILE_SIZE
    W, H = surface.get_size()
    for sp in spirits:
        if sp.team != team:
            continue
        gx, gy = camera.world_to_screen(sp.pos.x * ts, sp.pos.y * ts)
        if gx < -20 or gx > W + 20 or gy < -30 or gy > H + 20:
            continue
        ph = (sp.seed % 997) / 997.0
        bob = int(round(2.0 * math.sin(now * 2.4 + ph * 6.28)))
        # ombra a terra (verso basso-destra, luce da alto-sinistra)
        sh = pygame.Surface((12, 4), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 70), sh.get_rect())
        surface.blit(sh, (gx - 5, gy))
        age = now - sp.born
        grow = min(1.0, max(0.0, age / 0.6))       # compare crescendo
        h = max(5, int(14 * grow))
        pulse = 0.5 + 0.5 * math.sin(now * 3.0 + ph * 6.28)
        _glow(surface, gx, gy - 6 + bob, 9, GLOW, int(26 + 22 * pulse))
        if reach is not None and sp.pos.dist(reach[0]) <= reach[1]:
            ring = 7 + int(2 * pulse)
            col = (255, 255, 255) if sp is pick else LIME_HI
            pygame.draw.circle(surface, col, (gx, gy - 6 + bob), ring, 1)
        draw_flame(surface, gx, gy - 1 + bob, h, now, ph)
        # scintille che salgono
        for k in range(2):
            t = (now * 0.9 + ph + k * 0.5) % 1.0
            sx = gx + int(math.sin((t + k) * 9.0) * 3)
            sy = gy - 8 + bob - int(t * 10)
            if t < 0.8:
                surface.fill(LIME_HI if k else LIME, pygame.Rect(sx, sy, 1, 1))


def draw_aura(surface, camera, p, now, alpha=255):
    """Aura dei risvegli: fiammelle che orbitano attorno a Spiritomb, più numerose
    e più larghe a ogni risveglio (36/72/108 cariche)."""
    lvl = getattr(p, "spirit_awaken", 0)
    if lvl <= 0:
        return
    ts = config.TILE_SIZE
    gx, gy = camera.world_to_screen(p.pos.x * ts, p.pos.y * ts)
    n = (0, 3, 6, 10)[min(3, lvl)]
    rad = (0.55 + 0.28 * lvl + p.radius * 0.5) * ts
    h = (0, 6, 7, 9)[min(3, lvl)]
    if lvl >= 3:
        _glow(surface, gx, gy - 4, int(rad * 0.9), GLOW, 18)
    for i in range(n):
        a = now * (1.1 + 0.15 * lvl) + i * math.tau / n
        x = gx + int(math.cos(a) * rad)
        y = gy - 4 + int(math.sin(a) * rad * 0.45) - int(2 * math.sin(now * 3 + i))
        draw_flame(surface, x, y, h, now, i * 0.37, alpha)


def draw_spirit_beam(surface, camera, b, now):
    """Proiettile di Stordiraggio / Neropulsar / Finta: sfera con una scia di
    sbuffi che si assottiglia."""
    ts = config.TILE_SIZE
    out, body, hi = BEAM_PAL.get(b.get("fx"), BEAM_PAL["spiritbeam"])
    x, y = b["pos"].x, b["pos"].y
    dx, dy = b["dir"].x, b["dir"].y
    trail = min(1.6, max(0.0, (now - b["born"]) * b["speed"]))
    for k in range(6, 0, -1):
        d = trail * k / 6
        sx, sy = camera.world_to_screen((x - dx * d) * ts, (y - dy * d) * ts)
        rr = max(1, int(4 - k * 0.5))
        pygame.draw.circle(surface, body if k < 3 else out, (sx, sy), rr)
    sx, sy = camera.world_to_screen(x * ts, y * ts)
    r = max(3, int(b["radius"] * ts * 0.5))
    _glow(surface, sx, sy, r + 5, body, 40)
    pygame.draw.circle(surface, out, (sx, sy), r + 1)
    pygame.draw.circle(surface, body, (sx, sy), r)
    if b.get("fx") == "darkbeam":   # Neropulsar: anelli che pulsano
        rr = r + 2 + int((now * 14) % 4)
        pygame.draw.circle(surface, hi, (sx, sy), rr, 1)
    a = now * 9.0                   # vortice interno (Stordiraggio confonde)
    for k in range(3):
        aa = a + k * math.tau / 3
        surface.fill(hi, pygame.Rect(sx + int(math.cos(aa) * (r - 2)) - 1,
                                     sy + int(math.sin(aa) * (r - 2)) - 1, 2, 2))
    pygame.draw.circle(surface, hi, (sx - 1, sy - 1), max(1, r // 3))


def draw_pain_bind(surface, camera, bd, world, now):
    """Malcomune: catena di spiriti che lega Spiritomb ai bersagli, con un
    anello che si chiude allo scadere del secondo di legame."""
    ts = config.TILE_SIZE
    p = world.get(bd["caster_id"])
    if p is None:
        return
    ax, ay = camera.world_to_screen(p.pos.x * ts, p.pos.y * ts - 8)
    span = max(1e-6, bd["until"] - bd["start"])
    prog = max(0.0, min(1.0, (now - bd["start"]) / span))
    for i in bd["ids"]:
        e = world.get(i)
        if e is None:
            continue
        bx, by = camera.world_to_screen(e.pos.x * ts, e.pos.y * ts - 8)
        dist = math.hypot(bx - ax, by - ay)
        n = max(3, int(dist / 5))
        ang = math.atan2(by - ay, bx - ax)
        px, py = -math.sin(ang), math.cos(ang)
        enemy = e.team != p.team
        col = (200, 90, 230) if enemy else LIME
        for k in range(n + 1):
            u = k / n
            wob = math.sin(u * 9.0 - now * 10.0) * 2.0 * math.sin(u * math.pi)
            x = ax + (bx - ax) * u + px * wob
            y = ay + (by - ay) * u + py * wob
            lit = (k + int(now * 20)) % 4 == 0
            surface.fill(LIME_CORE if lit else col, pygame.Rect(int(x), int(y), 2, 2))
        pygame.draw.circle(surface, col, (bx, by), 7, 1)
        arc_r = pygame.Rect(bx - 9, by - 9, 18, 18)
        pygame.draw.arc(surface, LIME_CORE, arc_r, math.pi / 2, math.pi / 2 + prog * math.tau, 2)
    pygame.draw.circle(surface, LIME, (ax, ay), 6, 1)


def draw_legion_wave(surface, camera, w, now):
    """Legione dei 108: ondata circolare di spiriti che si espande da Spiritomb.
    Più cariche = più fiammelle sul fronte."""
    ts = config.TILE_SIZE
    r = w["r"] * ts
    if r < 2:
        return
    cx, cy = camera.world_to_screen(w["c"].x * ts, w["c"].y * ts)
    W, H = surface.get_size()
    if cx + r < 0 or cx - r > W or cy + r < 0 or cy - r > H:
        return
    t = min(1.0, (now - w["start"]) / max(1e-6, w["dur"]))
    fade = 1.0 - max(0.0, (t - 0.75) / 0.25)
    size = int(r * 2) + 8
    ov = pygame.Surface((size, size), pygame.SRCALPHA)
    o = size // 2
    pygame.draw.circle(ov, (*GLOW, int(22 * fade)), (o, o), int(r))
    pygame.draw.circle(ov, (*LIME, int(150 * fade)), (o, o), int(r), 2)
    pygame.draw.circle(ov, (*LIME_HI, int(90 * fade)), (o, o), max(1, int(r) - 4), 1)
    surface.blit(ov, (cx - o, cy - o))
    n = min(44, 14 + w.get("charges", 0) // 4)
    for i in range(n):
        a = i * math.tau / n + now * 0.6
        x = cx + int(math.cos(a) * r)
        y = cy + int(math.sin(a) * r)
        draw_flame(surface, x, y + 4, 8, now, i * 0.29, int(255 * fade))
