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

    # Nodi = indici in una lista piatta di calpestabilita' con un bordo non
    # calpestabile (niente controlli dei confini); stesso ordine dei vicini, stessi
    # costi e stesso spareggio di prima, quindi lo stesso percorso, ~3x piu' veloce.
    walk, stride = grid.walk_flags(block_bush)
    steps = [(dx, dy, cost, dy * stride + dx) for dx, dy, cost in _NEIGHBORS]
    sq2m2 = _SQRT2 - 2.0
    s_id = (sy + 1) * stride + sx + 1
    g_id = (gy + 1) * stride + gx + 1
    open_heap: list = [(0.0, 0, s_id, sx, sy)]
    counter = 0  # tie-breaker stabile per l'heap
    came_from: dict = {}
    g_score: dict = {s_id: 0.0}
    closed: set = set()
    push, pop, inf = heapq.heappush, heapq.heappop, math.inf

    while open_heap:
        _, _, cur, cx, cy = pop(open_heap)
        if cur == g_id:
            path = [(cx, cy)]
            while cur in came_from:
                cur = came_from[cur]
                y, x = divmod(cur, stride)
                path.append((x - 1, y - 1))
            path.reverse()
            return path
        if cur in closed:
            continue
        closed.add(cur)
        g_cur = g_score[cur]
        for dx, dy, cost, off in steps:
            nb = cur + off
            if not walk[nb]:
                continue
            if dx != 0 and dy != 0:
                # No corner cutting attraverso i muri (o i cespugli, per i minion).
                if not walk[cur + dx] or not walk[cur + dy * stride]:
                    continue
            if nb in closed:
                continue
            tentative = g_cur + cost
            if tentative < g_score.get(nb, inf):
                came_from[nb] = cur
                g_score[nb] = tentative
                nx, ny = cx + dx, cy + dy
                # Distanza octile: coerente col movimento a 8 direzioni e ammissibile.
                hx, hy = abs(nx - gx), abs(ny - gy)
                f = tentative + ((hx + hy) + sq2m2 * (hx if hx < hy else hy))
                counter += 1
                push(open_heap, (f, counter, nb, nx, ny))

    return []


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
