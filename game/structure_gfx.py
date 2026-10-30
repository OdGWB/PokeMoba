"""Grafica delle STRUTTURE: torri (2.5D, gemma di squadra) e base di spawn.

Tutto pixel-art disegnato UNA volta a risoluzione nativa (tile_size) e messo in
cache; a ogni frame solo blit + piccoli ritocchi animati (gemma che fluttua,
bagliore che pulsa). Luce da alto-sinistra: facce sinistre chiare, destre in
ombra, ombre a terra verso basso-destra (come i pilastri di Gigalith).

- Torre: plinto ottagonale estruso, fusto di blocchi di pietra rastremato,
  capitello con tre punte e una GEMMA sfaccettata che fluttua sopra (BLU per la
  squadra 0, ROSSA per la 1). Da distrutta resta un moncone di macerie.
- Base (nucleo): piattaforma di pietra PIATTA con anello di lastre, anello di
  rune e la gemma del nucleo incastonata al centro. Si disegna SOTTO le unità
  (chi rinasce ci sta sopra), quindi non ha parti alte.
"""
from __future__ import annotations

import math
import random

import numpy as np
import pygame

# Pietra (stessa famiglia dei pilastri di Gigalith).
ST_HI = (160, 146, 118)
ST_MID = (114, 101, 83)
ST_SH = (72, 63, 53)
ST_TOP = (192, 178, 146)
ST_OUT = (38, 32, 28)
ST_DEEP = (50, 44, 38)
ST_JOINT_HI = (128, 115, 92)
ST_JOINT = (88, 77, 64)
ST_JOINT_SH = (54, 47, 40)
MOSS = (58, 84, 44)
MOSS_DK = (40, 60, 34)
GOLD = (196, 160, 82)
GOLD_HI = (238, 210, 128)
GOLD_SH = (120, 92, 46)

# Gemme per squadra: (contorno, scuro, medio, chiaro, riflesso).
GEMS = {
    0: ((14, 30, 74), (30, 74, 168), (58, 132, 238), (130, 196, 255), (232, 246, 255)),
    1: ((70, 12, 18), (138, 26, 36), (214, 52, 60), (255, 128, 112), (255, 232, 220)),
}
DEAD_GEM = ((26, 26, 30), (54, 54, 60), (78, 78, 86), (104, 104, 112), (136, 136, 144))

_cache: dict = {}


def _gem(team):
    return GEMS.get(team, GEMS[0])


def _outline(surf, col):
    """Contorno di 1 px ATTORNO alla sagoma (dilatazione della maschera)."""
    a = pygame.surfarray.pixels_alpha(surf)
    solid = a > 0
    dil = solid.copy()
    dil[1:, :] |= solid[:-1, :]
    dil[:-1, :] |= solid[1:, :]
    dil[:, 1:] |= solid[:, :-1]
    dil[:, :-1] |= solid[:, 1:]
    ring = dil & ~solid
    del a
    rgb = pygame.surfarray.pixels3d(surf)
    rgb[ring] = col
    del rgb
    a = pygame.surfarray.pixels_alpha(surf)
    a[ring] = 255
    del a


def _banded(surf, poly, x_lit, x_sh, cols):
    """Poligono diviso in 3 bande verticali (luce | medio | ombra)."""
    lit, mid, sh = cols
    W, H = surf.get_size()
    for col, clip in ((lit, (0, 0, x_lit, H)), (mid, (x_lit, 0, x_sh - x_lit, H)),
                      (sh, (x_sh, 0, W - x_sh, H))):
        surf.set_clip(pygame.Rect(clip))
        pygame.draw.polygon(surf, col, poly)
    surf.set_clip(None)


def _octagon(cx, cy, rx, ry):
    return [(cx + rx * math.cos(math.radians(22.5 + 45 * i)),
             cy + ry * math.sin(math.radians(22.5 + 45 * i))) for i in range(8)]


def _prism(surf, cx, cy, rx, ry, depth, top_col, face_cols):
    """Ottagono ESTRUSO verso il basso (2.5D): faccia frontale a bande, cima."""
    for d in range(depth, 0, -1):
        _banded(surf, _octagon(cx, cy + d, rx, ry), int(cx - rx * 0.35),
                int(cx + rx * 0.3), face_cols)
    pygame.draw.polygon(surf, top_col, _octagon(cx, cy, rx, ry))
    # bordo della cima: luce sul lato alto-sinistro
    pts = _octagon(cx, cy, rx, ry)
    pygame.draw.lines(surf, ST_TOP, False, [pts[3], pts[4], pts[5], pts[6]], 1)


# --- torre ---------------------------------------------------------------
def tower_sprite(ts: int, team: int, broken: bool = False):
    """Sprite statico della torre (senza la gemma, che fluttua a parte).
    Ritorna (surface, foot_x, foot_y, gem_y): foot = punto a terra (pos della
    torre), gem_y = centro della gemma nello sprite."""
    key = ("tower", ts, team, broken)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    k = ts / 24.0
    W, H = int(46 * k), int(90 * k)
    spr = pygame.Surface((W, H), pygame.SRCALPHA)
    cx = W // 2
    foot = int(H - 9 * k)
    rng = random.Random(41 + team)
    gem = _gem(team)
    faces = (ST_HI, ST_MID, ST_SH)
    low_faces = (ST_MID, ST_SH, ST_DEEP)    # facce frontali di plinto/capitello

    # 1) plinto ottagonale estruso
    _prism(spr, cx, foot - 3 * k, 19 * k, 8 * k, int(7 * k), ST_HI, low_faces)
    # 2) fusto rastremato a blocchi
    s_bot = foot - 6 * k
    s_top = (foot - 34 * k) if broken else (foot - 58 * k)
    wb, wt = 12 * k, 8.5 * k
    if broken:
        # cima spezzata: profilo frastagliato
        shaft = [(cx - wb, s_bot), (cx - wt, s_top + 5 * k), (cx - wt * 0.6, s_top),
                 (cx - wt * 0.1, s_top + 4 * k), (cx + wt * 0.4, s_top - 2 * k),
                 (cx + wt, s_top + 3 * k), (cx + wb, s_bot)]
    else:
        shaft = [(cx - wb, s_bot), (cx - wt, s_top), (cx + wt, s_top), (cx + wb, s_bot)]
    _banded(spr, shaft, int(cx - 3 * k), int(cx + 3 * k), faces)
    # riga di luce sul bordo sinistro
    pygame.draw.line(spr, ST_TOP, (int(cx - wb + 1), int(s_bot - 1)),
                     (int(cx - wt + 1), int(s_top + 1)), 1)
    # giunti dei blocchi: orizzontali + verticali sfalsati
    row_h = 8 * k
    y = s_bot - row_h
    r = 0
    while y > s_top + 2 * k:
        f = (s_bot - y) / max(1.0, s_bot - s_top)
        half = wb + (wt - wb) * f
        x0, x1 = int(cx - half + 1), int(cx + half - 1)
        for x in range(x0, x1 + 1):
            jc = ST_JOINT_HI if x < cx - 3 * k else ST_JOINT if x < cx + 3 * k else ST_JOINT_SH
            spr.set_at((x, int(y)), jc)
        for vx in ((-0.45, 0.35) if r % 2 == 0 else (-0.05, 0.7)):
            xx = int(cx + vx * half)
            jc = ST_JOINT_HI if xx < cx - 3 * k else ST_JOINT if xx < cx + 3 * k else ST_JOINT_SH
            pygame.draw.line(spr, jc, (xx, int(y + 1)), (xx, int(y + row_h - 1)), 1)
        y -= row_h
        r += 1
    # crepe corte
    for _ in range(3 if broken else 2):
        x = rng.randint(int(cx - wt), int(cx + wt))
        yy = rng.randint(int(s_top + 6 * k), int(s_bot - 6 * k))
        pts = [(x, yy)]
        for _s in range(3):
            x += rng.choice((-1, 0, 1))
            yy += rng.randint(1, 3)
            pts.append((x, yy))
        pygame.draw.lines(spr, ST_OUT, False, pts, 1)
    # muschio alla base del fusto e sul plinto
    for _ in range(int(14 * k)):
        mx = rng.randint(int(cx - wb), int(cx + wb))
        my = int(s_bot - rng.random() ** 2 * 7 * k)
        spr.set_at((mx, my), MOSS if mx < cx else MOSS_DK)
    for _ in range(int(10 * k)):
        a = rng.uniform(math.pi * 0.9, math.pi * 2.1)
        mx = int(cx + math.cos(a) * 17 * k)
        my = int(foot - 3 * k + math.sin(a) * 7 * k)
        spr.set_at((mx, my), MOSS if mx < cx else MOSS_DK)

    gem_y = s_top
    if not broken:
        # 3) runa di squadra incastonata nel fusto
        ry = int(s_bot - 0.5 * (s_bot - s_top))
        rp = [(cx, ry - 4 * k), (cx + 3 * k, ry), (cx, ry + 4 * k), (cx - 3 * k, ry)]
        pygame.draw.polygon(spr, gem[0], [(x, y) for x, y in _grow(rp, cx, ry, 1.0)])
        pygame.draw.polygon(spr, gem[2], rp)
        pygame.draw.polygon(spr, gem[3], [rp[0], rp[3], (cx, ry)])
        spr.set_at((int(cx - 1), int(ry - 2 * k)), gem[4])
        # 4) capitello: anello ottagonale estruso
        cap_y = s_top - 1 * k
        _prism(spr, cx, cap_y, 13 * k, 5 * k, int(5 * k), ST_HI, low_faces)
        # fascia d'oro sul capitello
        for x in range(int(cx - 12 * k), int(cx + 12 * k) + 1):
            yy = int(cap_y + 5 * k * math.sqrt(max(0.0, 1 - ((x - cx) / (13 * k)) ** 2)) + 2 * k)
            spr.set_at((x, yy), GOLD_HI if x < cx - 3 * k else GOLD if x < cx + 3 * k else GOLD_SH)
        # 5) tre punte che reggono la gemma (le laterali si aprono verso l'esterno)
        for px, lean, hgt in ((-9, -3, 14), (9, 3, 14), (0, 0, 10)):
            bx = cx + px * k
            tip = (bx + lean * k, cap_y - hgt * k)
            left = (bx - 3 * k, cap_y + 1 * k)
            right = (bx + 3 * k, cap_y + 1 * k)
            mid = (bx, cap_y + 1 * k)
            pygame.draw.polygon(spr, ST_HI, [left, tip, mid])
            pygame.draw.polygon(spr, ST_SH, [mid, tip, right])
            spr.set_at((int(tip[0]), int(tip[1])), GOLD_HI)
        gem_y = cap_y - 15 * k
    else:
        # macerie attorno al moncone
        for _ in range(7):
            a = rng.uniform(0, math.tau)
            d = rng.uniform(12, 19) * k
            sx = int(cx + math.cos(a) * d)
            sy = int(foot - 3 * k + math.sin(a) * d * 0.45)
            sr = max(1, int(rng.uniform(1.5, 3.2) * k))
            pygame.draw.circle(spr, ST_SH, (sx, sy + 1), sr)
            pygame.draw.circle(spr, ST_MID, (sx, sy), sr)
            spr.set_at((sx - 1, sy - 1), ST_HI)
    _outline(spr, ST_OUT)
    hit = (spr, cx, foot, int(gem_y))
    _cache[key] = hit
    return hit


def _grow(pts, cx, cy, d):
    out = []
    for x, y in pts:
        dx, dy = x - cx, y - cy
        n = math.hypot(dx, dy) or 1.0
        out.append((x + dx / n * d, y + dy / n * d))
    return out


def gem_sprite(ts: int, team: int, dead: bool = False):
    """Gemma sfaccettata (rombo allungato), luce da alto-sinistra."""
    key = ("gem", ts, team, dead)
    spr = _cache.get(key)
    if spr is not None:
        return spr
    k = ts / 24.0
    out, dk, md, lt, wh = DEAD_GEM if dead else _gem(team)
    W, H = int(16 * k) + 2, int(24 * k) + 2
    spr = pygame.Surface((W, H), pygame.SRCALPHA)
    cx = W / 2
    top, gir, bot = 1, 1 + 8 * k, H - 2
    hw = 6.5 * k
    T, L, R, B = (cx, top), (cx - hw, gir), (cx + hw, gir), (cx, bot)
    C = (cx - 1 * k, gir + 1 * k)              # centro della faccia (spostato verso la luce)
    pygame.draw.polygon(spr, out, _grow([T, R, B, L], cx, gir, 1.2))
    pygame.draw.polygon(spr, lt, [T, L, C])            # alto-sx: luce
    pygame.draw.polygon(spr, md, [T, C, R])            # alto-dx
    pygame.draw.polygon(spr, md, [L, C, B])            # basso-sx
    pygame.draw.polygon(spr, dk, [C, R, B])            # basso-dx: ombra
    # cintura (girdle) e spigolo centrale
    pygame.draw.line(spr, wh if not dead else lt, (int(L[0] + 1), int(gir)), (int(C[0]), int(C[1])), 1)
    pygame.draw.line(spr, dk, (int(C[0]), int(C[1])), (int(R[0] - 1), int(gir)), 1)
    pygame.draw.line(spr, lt, (int(C[0]), int(C[1] + 1)), (int(cx), int(bot - 2)), 1)
    # riflessi
    if not dead:
        spr.fill(wh, pygame.Rect(int(cx - 3 * k), int(top + 3 * k), max(1, int(2 * k)), max(1, int(2 * k))))
        spr.set_at((int(cx - 1 * k), int(top + 2 * k)), wh)
    _cache[key] = spr
    return spr


def _glow_disc(r: int, col, alpha_max: int, steps: int = 4):
    """Alone a gradini (pixel-art, niente sfumatura continua) - cache."""
    key = ("glow", r, col, alpha_max, steps)
    s = _cache.get(key)
    if s is None:
        s = pygame.Surface((2 * r + 1, 2 * r + 1), pygame.SRCALPHA)
        for i in range(steps):
            rr = int(r * (1 - i / steps))
            a = int(alpha_max * (i + 1) / steps)
            pygame.draw.circle(s, (*col, a), (r, r), max(1, rr))
        _cache[key] = s
    return s


def _ground_shadow(w: int, h: int, alpha: int):
    key = ("shadow", w, h, alpha)
    s = _cache.get(key)
    if s is None:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, alpha // 2), s.get_rect())
        pygame.draw.ellipse(s, (0, 0, 0, alpha), s.get_rect().inflate(-w // 4, -h // 3))
        _cache[key] = s
    return s


def _cast_shadow(ts: int):
    """Ombra lunga del fusto a terra, verso basso-destra (luce da alto-sx)."""
    key = ("cast", ts)
    s = _cache.get(key)
    if s is None:
        k = ts / 24.0
        s = pygame.Surface((int(52 * k), int(30 * k)), pygame.SRCALPHA)
        poly = [(0, 4 * k), (16 * k, 0), (50 * k, 20 * k), (40 * k, 28 * k)]
        pygame.draw.polygon(s, (0, 0, 0, 38), poly)
        pygame.draw.polygon(s, (0, 0, 0, 62), _grow(poly, 22 * k, 12 * k, -3 * k))
        _cache[key] = s
    return s


def tower_top_y(ts: int, gy: int) -> int:
    """Y schermo della cima della torre (per la barra della vita)."""
    spr, _fx, foot, gem_y = tower_sprite(ts, 0)
    return gy - (foot - gem_y) - int(14 * ts / 24)


def gem_height_tiles(ts: int = 24) -> float:
    """Altezza (in tile) della gemma sopra il piede: da qui partono i colpi."""
    spr, _fx, foot, gem_y = tower_sprite(ts, 0)
    return (foot - gem_y) / ts


def draw_tower(surface, s, gx: int, gy: int, now: float, ts: int) -> None:
    team = getattr(s, "team", 0)
    alive = getattr(s, "alive", True)
    spr, fx, foot, gem_y = tower_sprite(ts, team, broken=not alive)
    k = ts / 24.0
    sh = _ground_shadow(int(48 * k), int(16 * k), 110)
    surface.blit(sh, (gx - int(18 * k), gy - int(6 * k)))
    if alive:
        surface.blit(_cast_shadow(ts), (gx - int(10 * k), gy - int(4 * k)))
    surface.blit(spr, (gx - fx, gy - foot))
    if not alive:
        return
    g = _gem(team)
    seed = (int(s.pos.x * 7) + int(s.pos.y * 13)) % 17
    bob = round(math.sin(now * 2.2 + seed) * 1.6 * k)
    pulse = 0.5 + 0.5 * math.sin(now * 3.1 + seed)
    gyc = gy - foot + gem_y + bob
    # alone che pulsa + bagliore sulle punte del capitello
    gr = int((13 + 3 * pulse) * k)
    surface.blit(_glow_disc(gr, g[3], int(70 + 60 * pulse)), (gx - gr, gyc - gr))
    gs = gem_sprite(ts, team)
    surface.blit(gs, (gx - gs.get_width() // 2, gyc - gs.get_height() // 2))
    # scintilla che orbita attorno alla gemma (piu' chiara quando passa davanti)
    a = now * 2.6 + seed
    sx = gx + int(math.cos(a) * 10 * k)
    sy = gyc + int(math.sin(a) * 4 * k)
    px = max(1, int(k))
    surface.fill(g[4] if math.sin(a) > 0 else g[3], pygame.Rect(sx, sy, px, px))


# --- base di spawn (nucleo) -------------------------------------------------
def base_radius_px(ts: int) -> int:
    return int(2.2 * ts)


def base_sprite(ts: int, team: int, dead: bool = False):
    """Piattaforma piatta della base. Ritorna (surface, cx, cy)."""
    key = ("base", ts, team, dead)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    k = ts / 24.0
    R = base_radius_px(ts)
    lip = max(3, int(5 * k))
    W, H = 2 * R + 10, 2 * R + lip + 10
    cx, cy = W // 2 - 2, R + 3
    gem = DEAD_GEM if dead else _gem(team)

    # campi per pixel: raggio, angolo
    xs = np.arange(W)[:, None] - cx
    ys = np.arange(H)[None, :] - cy
    rad = np.sqrt(xs * xs + ys * ys)
    ang = np.arctan2(ys, xs)
    rgb = np.zeros((W, H, 3), np.uint8)
    alpha = np.zeros((W, H), np.uint8)

    def put(mask, col, a=255):
        rgb[mask] = col
        alpha[mask] = a

    # ombra a basso-destra + bordo frontale (spessore della lastra)
    ys_l = ys - lip
    rad_lip = np.sqrt(xs * xs + ys_l * ys_l)
    sx_, sy_ = xs - 4 * k, ys - lip - 3 * k
    put(np.sqrt(sx_ * sx_ + sy_ * sy_) <= R, (0, 0, 0), 70)
    lipmask = np.zeros_like(rad, bool)
    for d in range(1, lip + 1):
        yy = ys - d
        lipmask |= np.sqrt(xs * xs + yy * yy) <= R
    lit_side = xs < -R * 0.25
    put(lipmask & lit_side, (98, 87, 71))
    put(lipmask & ~lit_side, (66, 58, 49))
    put(lipmask & (rad_lip > R - 1.2) & (ys > 0), ST_OUT)

    # cima: anello di lastre (2 corone) + disco interno
    top = rad <= R
    r_in = 0.60 * R
    r_mid = 0.80 * R
    seg_n = np.where(rad > r_mid, 28, 20)
    seg = np.floor((ang + math.pi) / math.tau * seg_n).astype(np.int32)
    ring_id = (rad > r_mid).astype(np.int32)
    h = (seg * 73856093 ^ ring_id * 19349663 ^ team * 83492791) & 0xFF
    tone = (h.astype(np.float32) / 255.0 - 0.5) * 16.0
    base_col = np.array(ST_MID, np.float32)
    stone = np.clip(base_col[None, None, :] + tone[..., None], 0, 255).astype(np.uint8)
    flag = top & (rad > r_in)
    rgb[flag] = stone[flag]
    alpha[flag] = 255
    # giunti: concentrici e radiali
    frac = (ang + math.pi) / math.tau * seg_n
    radial_joint = np.abs(frac - np.round(frac)) * (math.tau / seg_n) * rad < 0.7
    joint = flag & (radial_joint | (np.abs(rad - r_mid) < 0.7))
    put(joint, ST_JOINT_SH)
    # smusso del bordo: luce in alto-sinistra, ombra in basso-destra (3 livelli)
    light = -(np.cos(ang) + np.sin(ang)) / math.sqrt(2)   # 1 = verso alto-sinistra
    bevel = top & (rad > R - 2.2 * k)
    put(bevel & (light > 0.35), ST_TOP)
    put(bevel & (light <= 0.35) & (light > -0.35), ST_HI)
    put(bevel & (light <= -0.35), ST_SH)
    put(top & (rad > R - 0.9), ST_OUT)

    # disco interno: pietra scura levigata con leggera tinta di squadra
    inner = rad <= r_in
    tint = np.array(gem[1], np.float32) * 0.18 + np.array((52, 48, 46), np.float32) * 0.82
    put(inner, tuple(int(c) for c in tint))
    # cornice d'oro del disco interno
    put((rad <= r_in) & (rad > r_in - 2.0 * k) & (light > 0.2), GOLD_HI)
    put((rad <= r_in) & (rad > r_in - 2.0 * k) & (light <= 0.2) & (light > -0.4), GOLD)
    put((rad <= r_in) & (rad > r_in - 2.0 * k) & (light <= -0.4), GOLD_SH)
    put(np.abs(rad - r_in) < 0.6, ST_OUT)
    # anello di rune (spento: il bagliore si aggiunge per frame)
    r_rune = 0.43 * R
    put(np.abs(rad - r_rune) < 0.75 * k + 0.2, gem[1])

    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = rgb
    pygame.surfarray.pixels_alpha(surf)[:] = alpha

    # glifi sull'anello di rune (8 rombetti)
    for i in range(8):
        a = i * math.tau / 8 + math.pi / 8
        gx_, gy_ = cx + math.cos(a) * r_rune, cy + math.sin(a) * r_rune
        d = 2.2 * k
        pygame.draw.polygon(surf, gem[2], [(gx_, gy_ - d), (gx_ + d, gy_), (gx_, gy_ + d), (gx_ - d, gy_)])
        surf.set_at((int(gx_), int(gy_ - 1)), gem[3])
    # 4 cristalli incastonati sulla corona esterna (diagonali)
    for i in range(4):
        a = i * math.tau / 4 + math.pi / 4
        px_, py_ = cx + math.cos(a) * (r_mid + 0.1 * R), cy + math.sin(a) * (r_mid + 0.1 * R)
        d = 3.0 * k
        pts = [(px_, py_ - d), (px_ + d, py_), (px_, py_ + d), (px_ - d, py_)]
        pygame.draw.polygon(surf, gem[0], _grow(pts, px_, py_, 1.0))
        pygame.draw.polygon(surf, gem[2], pts)
        pygame.draw.polygon(surf, gem[3], [pts[0], pts[3], (px_, py_)])
    # gemma del nucleo: ottagono sfaccettato incastonato al centro
    gr = 0.27 * R
    oc = _octagon(cx, cy, gr, gr)
    pygame.draw.polygon(surf, gem[0], _grow(oc, cx, cy, 1.5))
    for i in range(8):
        a0, a1 = oc[i], oc[(i + 1) % 8]
        mx, my = (a0[0] + a1[0]) / 2 - cx, (a0[1] + a1[1]) / 2 - cy
        lv = -(mx + my) / (gr * math.sqrt(2))
        col = gem[3] if lv > 0.45 else gem[2] if lv > -0.45 else gem[1]
        pygame.draw.polygon(surf, col, [a0, a1, (cx, cy)])
    tab = _octagon(cx, cy, gr * 0.48, gr * 0.48)        # tavola centrale
    pygame.draw.polygon(surf, gem[2], tab)
    pygame.draw.polygon(surf, gem[3], [tab[4], tab[5], tab[6], (cx, cy)])
    pygame.draw.lines(surf, gem[0], True, tab, 1)
    if not dead:
        surf.fill(gem[4], pygame.Rect(int(cx - gr * 0.55), int(cy - gr * 0.6),
                                      max(1, int(2 * k)), max(1, int(2 * k))))
    else:
        # crepe sulla gemma spenta
        pygame.draw.lines(surf, ST_OUT, False, [(cx - gr * 0.7, cy - gr * 0.2), (cx - 2, cy + 1),
                                                (cx + gr * 0.3, cy - gr * 0.4), (cx + gr * 0.8, cy + gr * 0.3)], 1)
    # muschio qua e là sulla corona
    rng = random.Random(7 + team)
    for _ in range(int(40 * k)):
        a = rng.uniform(0, math.tau)
        rr = rng.uniform(r_mid, R - 2.5 * k)
        surf.set_at((int(cx + math.cos(a) * rr), int(cy + math.sin(a) * rr)),
                    MOSS if rng.random() < 0.5 else MOSS_DK)
    hit = (surf, cx, cy)
    _cache[key] = hit
    return hit


def _rune_glow(ts: int, team: int):
    """Strato luminoso (anello di rune + gemma) da sovrapporre con alpha che pulsa."""
    key = ("baseglow", ts, team)
    s = _cache.get(key)
    if s is None:
        k = ts / 24.0
        R = base_radius_px(ts)
        gem = _gem(team)
        size = 2 * R + 2
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        c = (size // 2, size // 2)
        r_rune = int(0.43 * R)
        pygame.draw.circle(s, (*gem[2], 70), c, r_rune + int(2 * k), max(1, int(4 * k)))
        pygame.draw.circle(s, (*gem[3], 200), c, r_rune, max(1, int(k)))
        gr = int(0.27 * R)
        pygame.draw.circle(s, (*gem[2], 60), c, int(gr * 1.7))
        pygame.draw.circle(s, (*gem[3], 50), c, int(gr * 1.25))
        _cache[key] = s
    return s


def draw_base(surface, core, gx: int, gy: int, now: float, ts: int) -> None:
    """Piattaforma della base (sotto le unità) + bagliore che pulsa."""
    team = getattr(core, "team", 0)
    alive = getattr(core, "alive", True)
    spr, cx, cy = base_sprite(ts, team, dead=not alive)
    surface.blit(spr, (gx - cx, gy - cy))
    if not alive:
        return
    glow = _rune_glow(ts, team)
    glow.set_alpha(int(110 + 110 * (0.5 + 0.5 * math.sin(now * 1.8))))
    surface.blit(glow, (gx - glow.get_width() // 2, gy - glow.get_height() // 2))
