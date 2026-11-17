"""Griglia di tile della mappa.

La griglia è una semplice matrice di interi (tipo di tile). Per la Fase 1 ci
bastano due tipi: pavimento calpestabile e muro. In futuro altri valori
(cespuglio, fiume, muro distruttibile...) si aggiungono qui senza toccare il
resto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Tipi di tile
TILE_FLOOR = 0        # erba / giungla
TILE_WALL = 1         # muro di bordo (bloccante, permanente)
TILE_LANE = 2         # corsia (strada) - calpestabile, cosmetico
TILE_RIVER = 3        # fiume - calpestabile, cosmetico
TILE_BUSH = 4         # cespuglio - calpestabile (invisibilita); sparisce col Sole
TILE_JUNGLE_WALL = 5  # muro di giungla (bloccante); si apre col Vento forte
TILE_PUDDLE = 6       # pozza (solo con la Pioggia) - calpestabile, rallenta i non-Acqua
TILE_PILLAR = 7       # pilastro di roccia temporaneo (Rocciotomba): bloccante, dura pochi secondi

# Insieme dei tile non calpestabili.
BLOCKING = {TILE_WALL, TILE_JUNGLE_WALL, TILE_PILLAR}

# Da quanti campioni line_of_sight passa a numpy (sotto, il ciclo Python costa meno).
_LOS_NUMPY_MIN = 24


class _Row(list):
    """Riga della griglia: una lista normale che, a ogni scrittura di un tile,
    fa avanzare la versione della griglia (le maschere numpy si rifanno da sole)."""
    __slots__ = ("_grid",)

    def __setitem__(self, i, v):
        list.__setitem__(self, i, v)
        self._grid._ver += 1


class _Rows(list):
    """Elenco delle righe: anche sostituire una riga intera cambia la versione."""
    __slots__ = ("_grid",)

    def __setitem__(self, i, v):
        list.__setitem__(self, i, _wrap_row(self._grid, v))
        self._grid._ver += 1


def _wrap_row(grid, row) -> _Row:
    r = _Row(row)
    r._grid = grid
    return r


@dataclass
class Grid:
    width: int
    height: int
    tiles: list[list[int]]  # tiles[y][x]

    # Sagoma dei muri (enable_wall_shape): spenta di default (test, mappe semplici).
    _shape_on = False
    _shape_ver = None

    # Ogni scrittura nella griglia (tiles[y][x] = ..., una riga o tutta la matrice)
    # passa da qui o da _Row/_Rows e fa avanzare `_ver`: le maschere numpy usate da
    # line_of_sight si ricostruiscono solo quando la versione e' cambiata.
    def __setattr__(self, name, value):
        if name == "tiles":
            rows = _Rows(_wrap_row(self, r) for r in value)
            rows._grid = self
            value = rows
            object.__setattr__(self, "_ver", getattr(self, "_ver", 0) + 1)
        object.__setattr__(self, name, value)

    def _block_masks(self):
        """(bloccanti, bloccanti + cespugli) come maschere numpy [y, x], in cache.
        Con la sagoma dei muri attiva: tile bloccante = CENTRO dentro il muro
        disegnato (o pilastro); un tile-muro col centro fuori dal disegno e'
        calpestabile."""
        if getattr(self, "_mask_ver", None) != self._ver:
            arr = np.array(self.tiles, dtype=np.int16).reshape(self.height, self.width)
            if self._shape_on:
                self._shape_sync(arr)
                blk = (arr == TILE_PILLAR) | self._shape_cen
            else:
                blk = np.isin(arr, list(BLOCKING))
            self._masks = (blk, blk | (arr == TILE_BUSH))
            self._mask_ver = self._ver
        return self._masks

    # --- hitbox dei muri sulla sagoma disegnata --------------------------------
    def enable_wall_shape(self, keep_points=()):
        """Collisione dei muri (TILE_WALL/TILE_JUNGLE_WALL) sulla SAGOMA DISEGNATA
        (engine/wall_shape: stesso calcolo della grafica, RES celle per tile)
        invece che sui tile: si sbatte dove il muro si vede, non contro l'aria, e
        non si cammina sulla cima estrusa. Pilastri e cespugli restano per tile.
        `keep_points` = [(x, y, r)] in tile: zone sempre libere (campi, tane,
        strutture, basi) anche se la sagoma ci sporge sopra. Quando il meteo
        apre/chiude i muri si rifà solo la zona cambiata."""
        from . import wall_shape as ws
        R = ws.RES
        fh, fw = self.height * R, self.width * R
        keep = np.zeros((fh, fw), bool)
        fy = (np.arange(fh, dtype=np.float32) + 0.5) / R
        fx = (np.arange(fw, dtype=np.float32) + 0.5) / R
        for (kx, ky, kr) in keep_points:
            y0 = max(0, int((ky - kr) * R)); y1 = min(fh, int((ky + kr) * R) + 2)
            x0 = max(0, int((kx - kr) * R)); x1 = min(fw, int((kx + kr) * R) + 2)
            if y1 <= y0 or x1 <= x0:
                continue
            d2 = (fx[None, x0:x1] - kx) ** 2 + (fy[y0:y1, None] - ky) ** 2
            keep[y0:y1, x0:x1] |= d2 <= kr * kr
        for k, v in (("_shape_keep", keep), ("_shape_walls", None),
                     ("_shape_bush", None), ("_shape_on", True),
                     ("_shape_ver", None), ("_mask_ver", None)):
            object.__setattr__(self, k, v)
        self._shape_sync()

    def _shape_sync(self, arr=None):
        """Rifà la maschera fine se i muri (o i cespugli mai visti) sono cambiati."""
        if self._shape_ver == self._ver:
            return
        from . import wall_shape as ws
        R, M = ws.RES, ws.MARGIN
        if arr is None:
            arr = np.array(self.tiles, dtype=np.int16).reshape(self.height, self.width)
        walls = (arr == TILE_WALL) | (arr == TILE_JUNGLE_WALL)
        # Cespugli: l'UNIONE di quelli mai visti (la grafica e' pre-renderizzata coi
        # cespugli d'inizio partita: se il Sole li toglie, il muro disegnato resta
        # scavato attorno a loro).
        bush = arr == TILE_BUSH
        if self._shape_bush is not None:
            bush = bush | self._shape_bush
        H, W = self.height, self.width
        if self._shape_walls is None:
            foot = ws.footprint(walls, bush)
            fine = np.zeros((H * R, W * R), bool)
            box = (0, 0, W, H)
        else:
            foot, fine = self._shape_foot, self._shape_np
            ch = (walls != self._shape_walls) | (bush != self._shape_bush)
            box = None
            if ch.any():
                ys, xs = np.where(ch)
                # Zona che puo' cambiare: dischi + blur (~3 tile), piu' la cima
                # estrusa verso l'alto (~1,2 tile).
                box = (max(0, int(xs.min()) - 3), max(0, int(ys.min()) - 5),
                       min(W, int(xs.max()) + 4), min(H, int(ys.max()) + 4))
                bx0, by0, bx1, by1 = box
                wx0, wy0 = max(0, bx0 - M), max(0, by0 - M)
                wx1, wy1 = min(W, bx1 + M), min(H, by1 + M)
                sub = ws.footprint(walls[wy0:wy1, wx0:wx1], bush[wy0:wy1, wx0:wx1],
                                   wx0, wy0)
                foot[by0 * R:by1 * R, bx0 * R:bx1 * R] = sub[
                    (by0 - wy0) * R:(by1 - wy0) * R, (bx0 - wx0) * R:(bx1 - wx0) * R]
        if box is not None:
            bx0, by0, bx1, by1 = box
            # Sagoma vista = impronta + cima estrusa verso l'alto.
            ey1 = min(H * R, by1 * R + ws.RELIEF)
            vis = ws.extrude(foot[by0 * R:ey1, bx0 * R:bx1 * R])[:(by1 - by0) * R]
            vis &= ~self._shape_keep[by0 * R:by1 * R, bx0 * R:bx1 * R]
            fine[by0 * R:by1 * R, bx0 * R:bx1 * R] = vis
            cen = fine[R // 2::R, R // 2::R].copy()
            # Tile toccati dalla sagoma (anche solo in parte): uscita rapida per
            # chi e' lontano dai muri (movement._keep_off_walls).
            anyt = fine.reshape(H, R, W, R).any(axis=(1, 3))
            for k, v in (("_shape_foot", foot), ("_shape_np", fine),
                         ("_shape_b", fine.tobytes()), ("_shape_cen", cen),
                         ("_shape_cen_b", cen.tobytes()),
                         ("_shape_any_b", anyt.tobytes())):
                object.__setattr__(self, k, v)
        object.__setattr__(self, "_shape_walls", walls)
        object.__setattr__(self, "_shape_bush", bush)
        object.__setattr__(self, "_shape_ver", self._ver)

    def shape_blocked(self, px: float, py: float) -> bool:
        """True se il punto sta dentro la sagoma disegnata di un muro (False se la
        sagoma non e' attiva o se il punto e' fuori mappa)."""
        if not self._shape_on or not (0.0 <= px < self.width and 0.0 <= py < self.height):
            return False
        if self._shape_ver != self._ver:
            self._shape_sync()
        return bool(self._shape_b[int(py * 8) * self.width * 8 + int(px * 8)])

    def shape_near(self, px: float, py: float, r: float) -> bool:
        """True se la sagoma disegnata tocca uno dei tile coperti dal quadrato di
        lato 2r attorno al punto (test rapido prima di campionare la sagoma)."""
        if not self._shape_on:
            return False
        if self._shape_ver != self._ver:
            self._shape_sync()
        W, H = self.width, self.height
        x0 = max(0, int(math.floor(px - r))); x1 = min(W - 1, int(math.floor(px + r)))
        y0 = max(0, int(math.floor(py - r))); y1 = min(H - 1, int(math.floor(py + r)))
        b = self._shape_any_b
        for ty in range(y0, y1 + 1):
            row = ty * W
            for tx in range(x0, x1 + 1):
                if b[row + tx]:
                    return True
        return False

    def walk_flags(self, block_bush: bool = False):
        """Calpestabilita' per il pathfinding: (lista piatta di bool con un bordo
        di un tile NON calpestabile tutt'intorno, larghezza della riga). Il tile
        (x, y) e' all'indice (y + 1) * stride + x + 1. In cache per versione."""
        key = (self._ver, block_bush)
        cache = getattr(self, "_walk_cache", None)
        if cache is None or cache[0] != key:
            blk = self._block_masks()[1 if block_bush else 0]
            pad = np.zeros((self.height + 2, self.width + 2), dtype=bool)
            pad[1:-1, 1:-1] = ~blk
            cache = self._walk_cache = (key, pad.ravel().tolist(), self.width + 2)
        return cache[1], cache[2]

    @classmethod
    def from_rows(cls, rows: list[list[int]]) -> "Grid":
        h = len(rows)
        w = len(rows[0]) if h else 0
        for r in rows:
            if len(r) != w:
                raise ValueError("Tutte le righe della griglia devono avere la stessa larghezza")
        return cls(width=w, height=h, tiles=[list(r) for r in rows])

    @classmethod
    def empty(cls, width: int, height: int, fill: int = TILE_FLOOR) -> "Grid":
        return cls(width, height, [[fill] * width for _ in range(height)])

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def tile_at(self, x: int, y: int) -> int:
        if not self.in_bounds(x, y):
            return TILE_WALL
        return self.tiles[y][x]

    def is_walkable(self, x: int, y: int, block_bush: bool = False) -> bool:
        """Un tile è calpestabile se è dentro i confini e non è bloccante.

        Con `block_bush=True` anche i cespugli contano come bloccanti: lo usano
        i minion, che non possono entrare nei cespugli (ci passano solo i
        campioni).
        """
        if not self.in_bounds(x, y):
            return False
        t = self.tiles[y][x]
        if block_bush and t == TILE_BUSH:
            return False
        if self._shape_on:
            if t == TILE_PILLAR:
                return False
            # Muri: conta il CENTRO del tile rispetto al muro disegnato.
            if self._shape_ver != self._ver:
                self._shape_sync()
            return not self._shape_cen_b[y * self.width + x]
        return t not in BLOCKING

    def is_walkable_point(self, px: float, py: float, block_bush: bool = False) -> bool:
        """Come is_walkable ma su coordinate float. Con la sagoma dei muri attiva
        il muro blocca dove e' DISEGNATO (anche oltre il suo tile) e lascia
        passare dove il tile-muro non e' disegnato; pilastri e cespugli per tile."""
        if not self._shape_on:
            return self.is_walkable(int(math.floor(px)), int(math.floor(py)), block_bush)
        if not (0.0 <= px < self.width and 0.0 <= py < self.height):
            return False
        t = self.tiles[int(py)][int(px)]
        if t == TILE_PILLAR or (block_bush and t == TILE_BUSH):
            return False
        if self._shape_ver != self._ver:
            self._shape_sync()
        return not self._shape_b[int(py * 8) * self.width * 8 + int(px * 8)]

    def line_of_sight(self, ax: float, ay: float, bx: float, by: float,
                      block_bush: bool = False) -> bool:
        """True se il segmento A->B non attraversa tile bloccanti.

        Campiona il segmento a passi fini; sufficiente per lo smoothing dei
        percorsi su una griglia (string-pulling). Con `block_bush=True` anche i
        cespugli bloccano la vista (i minion ci "sbattono" contro).
        """
        dx, dy = bx - ax, by - ay
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            return self.is_walkable_point(ax, ay, block_bush)
        if self._shape_on:
            return self._los_shape(ax, ay, dx, dy, dist, block_bush)
        steps = int(dist * 4) + 1  # ~4 campioni per tile
        w, h = self.width, self.height
        if steps >= _LOS_NUMPY_MIN:
            # Segmenti lunghi (minion verso il prossimo punto della lane: ~200
            # campioni): stessi campioni, stessa aritmetica in virgola mobile, ma in
            # numpy. Fuori mappa o un tile bloccante in qualunque campione = False,
            # come nel ciclo qui sotto.
            t = np.arange(steps + 1) / steps
            xs = np.floor(ax + dx * t).astype(np.intp)
            ys = np.floor(ay + dy * t).astype(np.intp)
            # I campioni avanzano in linea retta (floor e arrotondamenti sono
            # monotoni): gli estremi sono il primo e l'ultimo.
            if (min(xs[0], xs[-1]) < 0 or min(ys[0], ys[-1]) < 0
                    or max(xs[0], xs[-1]) >= w or max(ys[0], ys[-1]) >= h):
                return False
            mask = self._block_masks()[1 if block_bush else 0]
            return not mask[ys, xs].any()
        # Stessa logica di is_walkable_point, inlineata: e' il punto piu' caldo della
        # simulazione (migliaia di chiamate per tick con i minion in lane).
        tiles, blocking, floor = self.tiles, BLOCKING, math.floor
        for i in range(steps + 1):
            t = i / steps
            x = floor(ax + dx * t)
            y = floor(ay + dy * t)
            if not (0 <= x < w and 0 <= y < h):
                return False
            tt = tiles[y][x]
            if tt in blocking or (block_bush and tt == TILE_BUSH):
                return False
        return True

    def _los_shape(self, ax, ay, dx, dy, dist, block_bush):
        """line_of_sight con la sagoma dei muri: stessi campioni (~4 per tile: il
        muro disegnato non ha parti piu' sottili di ~mezzo tile); pilastri e
        cespugli per tile, muri sulla maschera fine."""
        if self._shape_ver != self._ver:
            self._shape_sync()
        steps = int(dist * 4) + 1
        w, h = self.width, self.height
        if steps >= _LOS_NUMPY_MIN:
            t = np.arange(steps + 1) / steps
            xf = ax + dx * t
            yf = ay + dy * t
            if (min(xf[0], xf[-1]) < 0 or min(yf[0], yf[-1]) < 0
                    or max(xf[0], xf[-1]) >= w or max(yf[0], yf[-1]) >= h):
                return False
            if self._shape_np[(yf * 8).astype(np.intp), (xf * 8).astype(np.intp)].any():
                return False
            kind = self._kind_mask(block_bush)
            return not kind[yf.astype(np.intp), xf.astype(np.intp)].any()
        tiles, fb, fw = self.tiles, self._shape_b, w * 8
        for i in range(steps + 1):
            t = i / steps
            x = ax + dx * t
            y = ay + dy * t
            if not (0.0 <= x < w and 0.0 <= y < h):
                return False
            if fb[int(y * 8) * fw + int(x * 8)]:
                return False
            tt = tiles[int(y)][int(x)]
            if tt == TILE_PILLAR or (block_bush and tt == TILE_BUSH):
                return False
        return True

    def _kind_mask(self, block_bush):
        """Pilastri (+ cespugli) per tile come maschera numpy, in cache per versione."""
        key = (self._ver, block_bush)
        c = getattr(self, "_kind_cache", None)
        if c is None or c[0] != key:
            arr = np.array(self.tiles, dtype=np.int16).reshape(self.height, self.width)
            m = arr == TILE_PILLAR
            if block_bush:
                m = m | (arr == TILE_BUSH)
            c = (key, m)
            object.__setattr__(self, "_kind_cache", c)
        return c[1]
