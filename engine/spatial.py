"""Griglia spaziale (spatial hash) per query di vicinato efficienti.

Serve a non confrontare ogni unità con tutte le altre (O(n^2)) durante le
collisioni e la ricerca di bersagli: le unità vengono messe in celle e si
guardano solo le celle adiacenti.
"""
from __future__ import annotations

import math
from collections import defaultdict


class SpatialHash:
    def __init__(self, cell_size: float = 2.0):
        self.cell_size = cell_size
        self._cells: dict[tuple[int, int], list] = defaultdict(list)

    def _key(self, x: float, y: float) -> tuple[int, int]:
        inv = 1.0 / self.cell_size
        return (int(math.floor(x * inv)), int(math.floor(y * inv)))

    def rebuild(self, entities: list) -> None:
        self._cells.clear()
        for e in entities:
            self._cells[self._key(e.pos.x, e.pos.y)].append(e)

    def query_radius(self, x: float, y: float, radius: float) -> list:
        """Entità in tutte le celle che intersecano il cerchio (x,y,radius)."""
        inv = 1.0 / self.cell_size
        floor = math.floor
        cx0 = int(floor((x - radius) * inv))
        cy0 = int(floor((y - radius) * inv))
        cx1 = int(floor((x + radius) * inv))
        cy1 = int(floor((y + radius) * inv))
        out = []
        get, ext = self._cells.get, out.extend
        xs = range(cx0, cx1 + 1)
        for cy in range(cy0, cy1 + 1):
            for cx in xs:
                bucket = get((cx, cy))
                if bucket:
                    ext(bucket)
        return out

    def neighbors(self, entity) -> list:
        """Entità nella cella dell'entità e nelle 8 adiacenti."""
        kx, ky = self._key(entity.pos.x, entity.pos.y)
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                bucket = self._cells.get((kx + dx, ky + dy))
                if bucket:
                    out.extend(bucket)
        return out
