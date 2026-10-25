"""Griglia di tile della mappa.

La griglia è una semplice matrice di interi (tipo di tile). Per la Fase 1 ci
bastano due tipi: pavimento calpestabile e muro. In futuro altri valori
(cespuglio, fiume, muro distruttibile...) si aggiungono qui senza toccare il
resto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Tipi di tile
TILE_FLOOR = 0        # erba / giungla
TILE_WALL = 1         # muro di bordo (bloccante, permanente)
TILE_LANE = 2         # corsia (strada) - calpestabile, cosmetico
TILE_RIVER = 3        # fiume - calpestabile, cosmetico
TILE_BUSH = 4         # cespuglio - calpestabile (invisibilita); sparisce col Sole
TILE_JUNGLE_WALL = 5  # muro di giungla (bloccante); si apre col Vento forte
TILE_PUDDLE = 6       # pozza (solo con la Pioggia) - calpestabile, rallenta i non-Acqua

# Insieme dei tile non calpestabili.
BLOCKING = {TILE_WALL, TILE_JUNGLE_WALL}


@dataclass
class Grid:
    width: int
    height: int
    tiles: list[list[int]]  # tiles[y][x]

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
        for i in range(steps + 1):
            t = i / steps
            if not self.is_walkable_point(ax + dx * t, ay + dy * t, block_bush):
                return False
        return True
