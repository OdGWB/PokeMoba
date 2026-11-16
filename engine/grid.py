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
        """(bloccanti, bloccanti + cespugli) come maschere numpy [y, x], in cache."""
        if getattr(self, "_mask_ver", None) != self._ver:
            arr = np.array(self.tiles, dtype=np.int16).reshape(self.height, self.width)
            blk = np.isin(arr, list(BLOCKING))
            self._masks = (blk, blk | (arr == TILE_BUSH))
            self._mask_ver = self._ver
        return self._masks

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
        if t in BLOCKING:
            return False
        if block_bush and t == TILE_BUSH:
            return False
        return True

    def is_walkable_point(self, px: float, py: float, block_bush: bool = False) -> bool:
        """Come is_walkable ma su coordinate float (converte a tile)."""
        return self.is_walkable(int(math.floor(px)), int(math.floor(py)), block_bush)

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
