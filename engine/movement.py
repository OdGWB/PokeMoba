"""Avanzamento lungo il percorso e collisioni a cerchio fra unità.

Funzioni pure che operano su Unit + Grid. Nessuno stato globale.
"""
from __future__ import annotations

from .entities import Unit
from .grid import Grid
from .spatial import SpatialHash
from .vec import Vec2, direction_index

# Distanza entro cui un waypoint si considera raggiunto.
_ARRIVE_EPS = 0.02


def advance_unit(unit: Unit, dt: float, grid: Grid | None = None) -> None:
    """Muove l'unità lungo i suoi waypoint per un intervallo dt.

    Consuma più waypoint se dt è grande. Aggiorna `facing` e `moving`. Se
    l'unità ha `bush_blocks` (minion) e il prossimo passo entrerebbe in un
    cespuglio, il movimento si ferma al bordo invece di attraversarlo.
    """
    if not unit.path:
        unit.moving = False
        return

    block_bush = grid is not None and getattr(unit, "bush_blocks", False)

    def _blocked(p) -> bool:
        return block_bush and not grid.is_walkable_point(p.x, p.y, block_bush=True)

    budget = unit.speed * dt
    pos = unit.pos
    while budget > 1e-9 and unit.path:
        target = unit.path[0]
        to = target - pos
        d = to.length()
        if d <= _ARRIVE_EPS:
            if _blocked(target):
                break
            pos = target
            unit.path.pop(0)
            continue
        if d <= budget:
            if _blocked(target):
                break
            pos = target
            budget -= d
            unit.facing = direction_index(to.x, to.y)
            unit.path.pop(0)
        else:
            step = to.normalized() * budget
            nxt = pos + step
            if _blocked(nxt):
                unit.facing = direction_index(to.x, to.y)
                budget = 0.0
                break
            pos = nxt
            unit.facing = direction_index(to.x, to.y)
            budget = 0.0

    unit.pos = pos
    unit.moving = bool(unit.path)


def resolve_collisions(units: list[Unit], grid: Grid, iterations: int = 2,
                       spatial: SpatialHash | None = None) -> None:
    """Separa le unità che si sovrappongono (collisione a cerchio).

    Usa una griglia spaziale per confrontare solo le unità vicine invece di
    tutte le coppie. Per ogni coppia troppo vicina le spinge via a metà strada,
    senza farle finire dentro i muri.
    """
    if spatial is None:
        spatial = SpatialHash(cell_size=2.0)
    for _ in range(iterations):
        spatial.rebuild(units)
        seen: set[tuple[int, int]] = set()
        for a in units:
            for b in spatial.neighbors(a):
                if b is a:
                    continue
                pair = (a.id, b.id) if a.id < b.id else (b.id, a.id)
                if pair in seen:
                    continue
                seen.add(pair)
                delta = b.pos - a.pos
                dist = delta.length()
                min_dist = a.radius + b.radius
                if dist >= min_dist:
                    continue
                if dist < 1e-6:
                    # Sovrapposizione perfetta: spingi su un asse arbitrario.
                    push = Vec2(min_dist * 0.5, 0.0)
                    _move_out(a, Vec2(-push.x, -push.y), grid)
                    _move_out(b, push, grid)
                    continue
                overlap = (min_dist - dist) * 0.5
                dir_ = delta.normalized()
                _move_out(a, dir_ * (-overlap), grid)
                _move_out(b, dir_ * overlap, grid)


def _move_out(unit: Unit, offset: Vec2, grid: Grid) -> None:
    """Applica uno spostamento di separazione se la destinazione è calpestabile."""
    new_pos = unit.pos + offset
    if grid.is_walkable_point(new_pos.x, new_pos.y,
                              block_bush=getattr(unit, "bush_blocks", False)):
        unit.pos = new_pos
