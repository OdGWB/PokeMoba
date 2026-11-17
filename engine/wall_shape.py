"""Hitbox dei muri sulla SAGOMA DISEGNATA (non sui tile).

La grafica (game/map_renderer.py, MapRenderer._jungle_solid + l'estrusione di
_build_jungle_walls) disegna i muri come una silhouette organica: dischi sui
centri dei tile-muro -> blur -> soglia + rumore al bordo, con un clamp di ~mezzo
tile, poi la cima estrusa verso l'alto di ~1,12 tile (la parete frontale copre
l'impronta). Qui si rifà lo STESSO calcolo in numpy (niente pygame), a una
risoluzione fissa di RES celle per tile, cosi' la collisione coincide con quello
che si vede: si sbatte dove il muro e' disegnato, non contro l'aria, e non si
cammina sopra la cima.

Il calcolo e' riproducibile su una FINESTRA della mappa (stessi valori della
mappa intera nella parte interna, il rumore e' in coordinate assolute): quando il
meteo apre/chiude un muro si rifà solo la zona attorno.
"""
from __future__ import annotations

import math

import numpy as np

# Celle della maschera per tile (la grafica usa 24 px per tile; a 8 lo scarto e'
# sotto 1/8 di tile e il calcolo costa poco).
RES = 8
# Estrusione verso l'alto della cima del muro (RELIEF = int(ts * 1.12) nella
# grafica), in celle a RES per tile.
RELIEF = round(int(24 * 1.12) * RES / 24)
# Margine (tile) attorno a una finestra: blur (3 passate da ~0,5 tile) + dischi
# (1,25 tile) + scavo dei cespugli: oltre 3 tile la parte interna e' esatta.
MARGIN = 4


def _hash01(xi, yi):
    h = (xi * 374761393 + yi * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFF).astype(np.float32) / 65535.0


def _vnoise(X, Y):
    x0 = np.floor(X).astype(np.int64); y0 = np.floor(Y).astype(np.int64)
    fx = (X - x0).astype(np.float32); fy = (Y - y0).astype(np.float32)
    sx = fx * fx * (3 - 2 * fx); sy = fy * fy * (3 - 2 * fy)
    a = _hash01(x0, y0); b = _hash01(x0 + 1, y0)
    c = _hash01(x0, y0 + 1); d = _hash01(x0 + 1, y0 + 1)
    top = a + (b - a) * sx; bot = c + (d - c) * sx
    return top + (bot - top) * sy


def _box1d(a, r, axis):
    if axis == 0:
        a = a.T
    H, W = a.shape
    c = np.zeros((H, W + 1), np.float32)
    np.cumsum(a, axis=1, out=c[:, 1:])
    idx = np.arange(W)
    lo = np.clip(idx - r, 0, W); hi = np.clip(idx + r + 1, 0, W)
    out = (c[:, hi] - c[:, lo]) / (hi - lo)[None, :].astype(np.float32)
    return out.T if axis == 0 else out


def _sep_blur(a, r, passes=3):
    a = a.astype(np.float32)
    for _ in range(passes):
        a = _box1d(a, r, 1)
        a = _box1d(a, r, 0)
    return a


def _dist_lo(mask, Rc):
    hl, wl = mask.shape
    big = Rc + 2.0
    d = np.full((hl, wl), big, np.float32); d[mask] = 0.0
    for dy in range(-Rc, Rc + 1):
        for dx in range(-Rc, Rc + 1):
            e = math.hypot(dx, dy)
            if e == 0.0 or e > Rc:
                continue
            dy0 = max(0, -dy); dy1 = hl - max(0, dy)
            dx0 = max(0, -dx); dx1 = wl - max(0, dx)
            if dy1 <= dy0 or dx1 <= dx0:
                continue
            src = mask[dy0 + dy:dy1 + dy, dx0 + dx:dx1 + dx]
            sub = d[dy0:dy1, dx0:dx1]
            np.minimum(sub, np.where(src, np.float32(e), big), out=sub)
    return d


def _upscale(lo, W, H, step):
    hl, wl = lo.shape
    fx = np.minimum(np.arange(W, dtype=np.float32) / step, wl - 1.0)
    x0 = np.floor(fx).astype(np.int64); x1 = np.minimum(x0 + 1, wl - 1)
    wx = (fx - x0)[None, :]
    colx = lo[:, x0] * (1 - wx) + lo[:, x1] * wx
    fy = np.minimum(np.arange(H, dtype=np.float32) / step, hl - 1.0)
    y0 = np.floor(fy).astype(np.int64); y1 = np.minimum(y0 + 1, hl - 1)
    wy = (fy - y0)[:, None]
    return colx[y0] * (1 - wy) + colx[y1] * wy


def footprint(walls: np.ndarray, bushes: np.ndarray, ox: int = 0, oy: int = 0,
              ts: int = RES) -> np.ndarray:
    """Impronta (sagoma a terra) dei muri, (Ht*ts, Wt*ts) bool: stesso algoritmo
    di MapRenderer._jungle_solid. `walls`/`bushes` = maschere a risoluzione tile
    di una finestra che parte dal tile (ox, oy) della mappa (per il rumore)."""
    Ht, Wt = walls.shape
    W, H = Wt * ts, Ht * ts
    if not walls.any():
        return np.zeros((H, W), bool)
    s = max(2, ts // 4)
    hl = (H + s - 1) // s; wl = (W + s - 1) // s
    ys, xs = np.where(walls)
    cmask = np.zeros((hl, wl), bool)
    ccx = np.clip(((xs + 0.5) * ts / s).astype(int), 0, wl - 1)
    ccy = np.clip(((ys + 0.5) * ts / s).astype(int), 0, hl - 1)
    cmask[ccy, ccx] = True
    dist = _dist_lo(cmask, int(math.ceil(ts * 1.25 / s)))
    disc = (dist <= (ts * 0.72 / s)).astype(np.float32)
    core = dist <= (ts * 0.42 / s)
    allowed = dist <= (ts * 1.0 / s)
    if bushes.any():
        bys, bxs = np.where(bushes)
        bmask = np.zeros((hl, wl), bool)
        bbx = np.clip(((bxs + 0.5) * ts / s).astype(int), 0, wl - 1)
        bby = np.clip(((bys + 0.5) * ts / s).astype(int), 0, hl - 1)
        bmask[bby, bbx] = True
        bdist = _dist_lo(bmask, int(math.ceil(ts * 0.9 / s)))
        carve = bdist <= (ts * 0.5 / s)
        disc[carve] = 0.0; core[carve] = False; allowed[carve] = False
    bf = _sep_blur(disc, max(1, int(ts * 0.55 / s)), passes=3)
    bf_full = _upscale(bf, W, H, s)
    iy = np.minimum(np.arange(H) // s, hl - 1)
    ix = np.minimum(np.arange(W) // s, wl - 1)
    core_full = core[iy][:, ix]
    allow_full = allowed[iy][:, ix]
    TXf = (np.arange(W, dtype=np.float32) / ts + ox)[None, :]
    TYf = (np.arange(H, dtype=np.float32) / ts + oy)[:, None]
    nz = _vnoise(TXf / 1.5 + 11.0, TYf / 1.5 + 7.0) - 0.5
    thr = np.where(bf_full >= 0.80, True,
                   np.where(bf_full <= 0.22, False, (bf_full + nz * 0.33) > 0.5))
    return (thr | core_full) & allow_full


def extrude(sol: np.ndarray, relief: int = RELIEF) -> np.ndarray:
    """Sagoma VISTA: l'impronta piu' la cima estrusa verso l'alto di `relief`
    celle (la parete frontale riempie lo spazio tra cima e impronta)."""
    v = sol.copy()
    for k in range(1, relief + 1):
        v[:-k] |= sol[k:]
    return v
