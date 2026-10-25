"""Pathfinding A* su griglia, movimento a 8 direzioni con percorsi smussati.

Lo stesso sistema sarà usato da Pokémon, minion e bot (Fase 2+).
"""
from __future__ import annotations

import heapq
import math

from .grid import Grid

# Vicini a 8 direzioni: (dx, dy, costo)
_SQRT2 = math.sqrt(2.0)
_NEIGHBORS = [
    (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
    (1, 1, _SQRT2), (1, -1, _SQRT2), (-1, 1, _SQRT2), (-1, -1, _SQRT2),
]


def _heuristic(ax: int, ay: int, bx: int, by: int) -> float:
    """Distanza octile: coerente col movimento a 8 direzioni e ammissibile."""
    dx, dy = abs(ax - bx), abs(ay - by)
    return (dx + dy) + (_SQRT2 - 2.0) * min(dx, dy)


def find_path(grid: Grid, start: tuple[int, int], goal: tuple[int, int],
              block_bush: bool = False) -> list[tuple[int, int]]:
    """A* fra due tile. Ritorna la lista di tile (start..goal) o [] se irraggiungibile.

    Vieta il "corner cutting": per muoversi in diagonale entrambi i tile
    ortogonali adiacenti devono essere liberi, così l'unità non taglia gli
    angoli dei muri. Con `block_bush=True` i cespugli sono invalicabili (minion):
    il percorso li aggira. La partenza è sempre consentita (l'unità può uscire
    da un cespuglio in cui si trovasse già)."""
    sx, sy = start
    gx, gy = goal
    if not grid.is_walkable(gx, gy, block_bush) or not grid.is_walkable(sx, sy):
        return []
    if start == goal:
        return [start]

    open_heap: list[tuple[float, int, tuple[int, int]]] = []
    counter = 0  # tie-breaker stabile per l'heap
    heapq.heappush(open_heap, (0.0, counter, start))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], float] = {start: 0.0}
    closed: set[tuple[int, int]] = set()

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            return _reconstruct(came_from, current)
        if current in closed:
            continue
        closed.add(current)

        cx, cy = current
        for dx, dy, cost in _NEIGHBORS:
            nx, ny = cx + dx, cy + dy
            if not grid.is_walkable(nx, ny, block_bush):
                continue
            if dx != 0 and dy != 0:
                # No corner cutting attraverso i muri (o i cespugli, per i minion).
                if (not grid.is_walkable(cx + dx, cy, block_bush)
                        or not grid.is_walkable(cx, cy + dy, block_bush)):
                    continue
            neighbor = (nx, ny)
            if neighbor in closed:
                continue
            tentative = g_score[current] + cost
            if tentative < g_score.get(neighbor, math.inf):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                f = tentative + _heuristic(nx, ny, gx, gy)
                counter += 1
                heapq.heappush(open_heap, (f, counter, neighbor))

    return []


def _reconstruct(came_from: dict, current: tuple[int, int]) -> list[tuple[int, int]]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def smooth_path(grid: Grid, tile_path: list[tuple[int, int]],
                block_bush: bool = False) -> list[tuple[float, float]]:
    """Smussa un percorso di tile con string-pulling.

    Converte i tile al loro centro e rimuove i waypoint intermedi quando c'è
    linea di vista libera, così il movimento risulta più diretto e naturale.
    """
    if not tile_path:
        return []
    pts = [(tx + 0.5, ty + 0.5) for (tx, ty) in tile_path]
    if len(pts) <= 2:
        return pts

    result = [pts[0]]
    anchor = 0
    i = 1
    while i < len(pts) - 1:
        # Prova a saltare da anchor direttamente al punto successivo (i+1).
        ax, ay = pts[anchor]
        nx, ny = pts[i + 1]
        if grid.line_of_sight(ax, ay, nx, ny, block_bush):
            i += 1  # possiamo saltare pts[i]
        else:
            result.append(pts[i])
            anchor = i
            i += 1
    result.append(pts[-1])
    return result
