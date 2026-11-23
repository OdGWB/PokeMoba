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
    il percorso li aggira. La partenza è sempre consentita se dentro la mappa
    (l'unità può uscire da un cespuglio, o da un bordo di muro, in cui si trovasse
    già)."""
    sx, sy = start
    gx, gy = goal
    if not grid.is_walkable(gx, gy, block_bush) or not grid.in_bounds(sx, sy):
        return []
    if start == goal:
        return [start]

    # Nodi = indici in una lista piatta di calpestabilita' con un bordo non
    # calpestabile (niente controlli dei confini); stesso ordine dei vicini, stessi
    # costi e stesso spareggio di prima, quindi lo stesso percorso, ~3x piu' veloce.
    nw = grid.native_walk(block_bush)
    if nw is not None:                       # stesso A*, in Rust (pokemoba_native)
        return nw.find_path(sx, sy, gx, gy) or []
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
                block_bush: bool = False, start: tuple[float, float] | None = None,
                end: tuple[float, float] | None = None) -> list[tuple[float, float]]:
    """Smussa un percorso di tile con string-pulling.

    Converte i tile al loro centro e rimuove i waypoint intermedi quando c'è
    linea di vista libera, così il movimento risulta più diretto e naturale.
    `start`/`end` (opzionali) sostituiscono il centro del primo/ultimo tile col
    punto esatto (posizione dell'unità, punto cliccato).
    """
    if not tile_path:
        return []
    pts = [(tx + 0.5, ty + 0.5) for (tx, ty) in tile_path]
    if start is not None:
        pts[0] = (float(start[0]), float(start[1]))
    if end is not None:
        pts[-1] = (float(end[0]), float(end[1]))
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


def _components(grid: Grid, block_bush: bool) -> list[int]:
    """Etichette delle componenti connesse dei tile calpestabili (lista piatta
    con bordo, come walk_flags; 0 = non calpestabile). La 4-connessione equivale
    al movimento a 8 direzioni senza corner cutting di find_path. In cache per
    versione della griglia."""
    cache = getattr(grid, "_comp_cache", None)
    key = (grid._ver, block_bush)
    if cache is not None and cache[0] == key:
        return cache[1]
    walk, stride = grid.walk_flags(block_bush)
    lab = [0] * len(walk)
    nxt = 0
    offs = (1, -1, stride, -stride)
    for i, w in enumerate(walk):
        if not w or lab[i]:
            continue
        nxt += 1
        lab[i] = nxt
        stack = [i]
        pop, push = stack.pop, stack.append
        while stack:
            c = pop()
            for o in offs:
                n = c + o
                if walk[n] and not lab[n]:
                    lab[n] = nxt
                    push(n)
    object.__setattr__(grid, "_comp_cache", (key, lab))
    return lab


def nearest_reachable_tile(grid: Grid, start: tuple[int, int],
                           target: tuple[float, float], block_bush: bool = False,
                           max_r: int = 24) -> tuple[int, int] | None:
    """Tile calpestabile col centro piu' VICINO (distanza euclidea) al punto
    `target`, tra quelli raggiungibili da `start` (stessa componente connessa).
    Se `start` non e' su un tile calpestabile, qualunque tile calpestabile."""
    lab = _components(grid, block_bush)
    stride = grid.width + 2
    sx, sy = start
    want = lab[(sy + 1) * stride + sx + 1] if grid.in_bounds(sx, sy) else 0
    tx, ty = target
    cx, cy = math.floor(tx), math.floor(ty)
    best, best_d = None, math.inf
    w, h = grid.width, grid.height
    for r in range(max_r + 1):
        for y in range(cy - r, cy + r + 1):
            if y < 0 or y >= h:
                continue
            edge = y == cy - r or y == cy + r
            xs = range(cx - r, cx + r + 1) if edge else (cx - r, cx + r)
            row = (y + 1) * stride + 1
            for x in xs:
                if x < 0 or x >= w:
                    continue
                l = lab[row + x]
                if not l or (want and l != want):
                    continue
                d = (x + 0.5 - tx) ** 2 + (y + 0.5 - ty) ** 2
                if d < best_d:
                    best, best_d = (x, y), d
        # Dall'anello r+1 in poi i centri distano almeno r+0.5: inutile cercare.
        if best is not None and math.sqrt(best_d) <= r + 0.5:
            break
    return best


def plan_move(grid: Grid, pos: tuple[float, float], target: tuple[float, float],
              block_bush: bool = False) -> list[tuple[float, float]]:
    """Waypoint di un ordine di movimento verso il punto `target`.

    - Se il punto cliccato e' calpestabile e raggiungibile, l'ultimo waypoint e'
      il punto ESATTO (non il centro del tile), anche dentro il tile dell'unita'.
    - Altrimenti (muro, zona irraggiungibile) si va al centro del tile
      raggiungibile piu' vicino al punto cliccato.
    - Il percorso parte dalla posizione vera dell'unita'.
    Ritorna [] se non c'e' modo di muoversi. Usata dall'host (Simulation) e dalla
    predizione online (MovementModel.plan): deve restare l'unica implementazione.
    """
    px, py = float(pos[0]), float(pos[1])
    tx, ty = float(target[0]), float(target[1])
    start = (math.floor(px), math.floor(py))
    if not grid.in_bounds(*start):
        return []
    goal = (math.floor(tx), math.floor(ty))
    lab = _components(grid, block_bush)
    stride = grid.width + 2

    def comp(t):
        return lab[(t[1] + 1) * stride + t[0] + 1] if grid.in_bounds(*t) else 0

    end = (tx, ty)
    sc = comp(start)
    gc = comp(goal)
    if (not gc or (sc and gc != sc)
            or not grid.is_walkable_point(tx, ty, block_bush)):
        goal = nearest_reachable_tile(grid, start, (tx, ty), block_bush)
        if goal is None:
            return []
        end = (goal[0] + 0.5, goal[1] + 0.5)
    if goal == start:
        return [end]
    tile_path = find_path(grid, start, goal, block_bush)
    if not tile_path:
        return []
    return smooth_path(grid, tile_path, block_bush, start=(px, py), end=end)[1:]
