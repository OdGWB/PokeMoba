"""Vettore 2D e utilità sulle 8 direzioni.

Le coordinate di gioco sono in "tile" (float): (0, 0) è l'angolo in alto a
sinistra della mappa, +x va verso destra, +y verso il basso (come lo schermo).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Vec2:
    x: float = 0.0
    y: float = 0.0

    def __add__(self, o: "Vec2") -> "Vec2":
        return Vec2(self.x + o.x, self.y + o.y)

    def __sub__(self, o: "Vec2") -> "Vec2":
        return Vec2(self.x - o.x, self.y - o.y)

    def __mul__(self, s: float) -> "Vec2":
        return Vec2(self.x * s, self.y * s)

    __rmul__ = __mul__

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def length_sq(self) -> float:
        return self.x * self.x + self.y * self.y

    def normalized(self) -> "Vec2":
        l = self.length()
        if l < 1e-9:
            return Vec2(0.0, 0.0)
        return Vec2(self.x / l, self.y / l)

    def dist(self, o: "Vec2") -> float:
        return math.hypot(self.x - o.x, self.y - o.y)

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


# --- 8 direzioni -------------------------------------------------------------
# Ordine dei fogli sprite PMD / SpriteCollab: le righe del foglio seguono questo
# ordine (0 in alto). (dx, dy) con +y verso il basso.
#   0 Down, 1 DownRight, 2 Right, 3 UpRight, 4 Up, 5 UpLeft, 6 Left, 7 DownLeft
DIR_NAMES = ["Down", "DownRight", "Right", "UpRight", "Up", "UpLeft", "Left", "DownLeft"]
DIR_VECTORS = [
    Vec2(0, 1),
    Vec2(1, 1),
    Vec2(1, 0),
    Vec2(1, -1),
    Vec2(0, -1),
    Vec2(-1, -1),
    Vec2(-1, 0),
    Vec2(-1, 1),
]
# Versioni normalizzate, pre-calcolate (per il prodotto scalare).
_DIR_UNIT = [v.normalized() for v in DIR_VECTORS]


def direction_index(dx: float, dy: float) -> int:
    """Indice 0..7 della direzione più vicina al vettore (dx, dy).

    Sceglie la direzione con prodotto scalare massimo, robusto a qualsiasi
    angolo. Se il vettore è nullo ritorna 0 (Down), direzione di riposo di
    default negli sprite PMD.
    """
    if dx == 0 and dy == 0:
        return 0
    inv = 1.0 / math.hypot(dx, dy)
    nx, ny = dx * inv, dy * inv
    best_i, best_dot = 0, -2.0
    for i, u in enumerate(_DIR_UNIT):
        d = nx * u.x + ny * u.y
        if d > best_dot:
            best_dot, best_i = d, i
    return best_i
