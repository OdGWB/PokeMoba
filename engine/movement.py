"""Avanzamento lungo il percorso e collisioni a cerchio fra unità.

Funzioni pure che operano su Unit + Grid. Nessuno stato globale.
"""
from __future__ import annotations

import math

from .entities import Unit
from .grid import TILE_PILLAR, Grid
from .spatial import SpatialHash
from .vec import Vec2, direction_index

# Distanza entro cui un waypoint si considera raggiunto.
_ARRIVE_EPS = 0.02
# Aggiramento dei pilastri temporanei: angoli provati (gradi) attorno alla
# direzione di marcia quando il passo entrerebbe in un pilastro.
_STEER_ANGLES = (35, -35, 70, -70, 100, -100)


def _in_pillar(grid: Grid | None, p: Vec2) -> bool:
    return grid is not None and grid.tile_at(math.floor(p.x), math.floor(p.y)) == TILE_PILLAR


def _steer(grid: Grid, pos: Vec2, step: Vec2) -> Vec2 | None:
    """Passo deviato per aggirare un pilastro (che compare dopo il calcolo del
    percorso, o sulla traiettoria diretta di minion/bot): prova direzioni
    ruotate e prende la prima libera. None = bloccato."""
    for deg in _STEER_ANGLES:
        a = math.radians(deg)
        ca, sa = math.cos(a), math.sin(a)
        alt = pos + Vec2(step.x * ca - step.y * sa, step.x * sa + step.y * ca)
        if not _in_pillar(grid, alt) and grid.is_walkable_point(alt.x, alt.y):
            return alt
    return None


def _nearest_walkable(grid: Grid, pos: Vec2, block_bush: bool) -> Vec2 | None:
    """Centro del tile calpestabile piu' vicino a pos (ricerca ad anelli)."""
    cx, cy = math.floor(pos.x), math.floor(pos.y)
    best, best_d = None, 1e18
    for r in range(1, 8):
        for ty in range(cy - r, cy + r + 1):
            for tx in range(cx - r, cx + r + 1):
                if max(abs(tx - cx), abs(ty - cy)) != r or not grid.is_walkable(tx, ty, block_bush):
                    continue
                d = (tx + 0.5 - pos.x) ** 2 + (ty + 0.5 - pos.y) ** 2
                if d < best_d:
                    best, best_d = Vec2(tx + 0.5, ty + 0.5), d
        if best is not None:
            return best
    return None


def _slide(grid: Grid, pos: Vec2, nxt: Vec2, block_bush: bool) -> Vec2 | None:
    """Passo pos->nxt senza entrare nei tile bloccanti: se il passo diretto e'
    bloccato prova a scivolare lungo un solo asse (spigoli e pareti). Anche il
    passo libero e' verificato a meta' per non tagliare gli angoli."""
    ok = grid.is_walkable_point
    if ok(nxt.x, nxt.y, block_bush):
        # Diagonale fra due tile bloccanti: passa solo se almeno un lato e' libero.
        if (int(math.floor(pos.x)) == int(math.floor(nxt.x))
                or int(math.floor(pos.y)) == int(math.floor(nxt.y))
                or ok(nxt.x, pos.y, block_bush) or ok(pos.x, nxt.y, block_bush)):
            return nxt
    ax, ay = Vec2(nxt.x, pos.y), Vec2(pos.x, nxt.y)
    # prima l'asse col movimento maggiore
    cand = (ax, ay) if abs(nxt.x - pos.x) >= abs(nxt.y - pos.y) else (ay, ax)
    for c in cand:
        if (c.x != pos.x or c.y != pos.y) and ok(c.x, c.y, block_bush):
            return c
    return None


def advance_unit(unit: Unit, dt: float, grid: Grid | None = None) -> None:
    """Muove l'unità lungo i suoi waypoint per un intervallo dt.

    Consuma più waypoint se dt è grande. Aggiorna `facing` e `moving`. Se
    l'unità ha `bush_blocks` (minion) e il prossimo passo entrerebbe in un
    cespuglio, il movimento si ferma al bordo invece di attraversarlo.
    """
    block_bush = grid is not None and getattr(unit, "bush_blocks", False)
    # Anti-incastro: chi si ritrova col centro dentro un muro (scatto, spinta,
    # cambio di meteo) viene riportato sul tile calpestabile piu' vicino.
    # In volo (air_z > 0) i muri si scavalcano.
    if (grid is not None and getattr(unit, "air_z", 0.0) <= 0.0
            and not grid.is_walkable_point(unit.pos.x, unit.pos.y, block_bush)):
        fix = _nearest_walkable(grid, unit.pos, block_bush)
        if fix is not None:
            unit.pos = fix

    if not unit.path:
        unit.moving = False
        if grid is not None and getattr(unit, "air_z", 0.0) <= 0.0:
            _keep_off_walls(unit, grid, block_bush)
        return

    airborne = getattr(unit, "air_z", 0.0) > 0.0

    def _blocked(p) -> bool:
        return (grid is not None and not airborne
                and not grid.is_walkable_point(p.x, p.y, block_bush=block_bush))

    budget = unit.speed * dt
    pos = unit.pos
    while budget > 1e-9 and unit.path:
        target = unit.path[0]
        to = target - pos
        d = to.length()
        # Pilastro di roccia sulla traiettoria: lo aggira deviando il passo (o si
        # ferma se non c'è spazio). Un waypoint dentro il pilastro non si raggiunge.
        if d > _ARRIVE_EPS and grid is not None:
            step = to.normalized() * min(budget, d)
            if _in_pillar(grid, pos + step) or _in_pillar(grid, target):
                alt = _steer(grid, pos, step) if _in_pillar(grid, pos + step) else pos + step
                if alt is None or _blocked(alt):
                    unit.facing = direction_index(to.x, to.y)
                    break
                pos = alt
                unit.facing = direction_index(to.x, to.y)
                budget = 0.0
                break
        if d <= _ARRIVE_EPS:
            if _blocked(target):
                break
            pos = target
            unit.path.pop(0)
            continue
        if d <= budget:
            if _blocked(target):
                break
            if grid is not None and not airborne:
                moved = _slide(grid, pos, target, block_bush)
                if moved is None:
                    break
                if moved is not target:      # scivolato: waypoint non raggiunto
                    pos = moved
                    unit.facing = direction_index(to.x, to.y)
                    budget = 0.0
                    break
            pos = target
            budget -= d
            unit.facing = direction_index(to.x, to.y)
            unit.path.pop(0)
        else:
            step = to.normalized() * budget
            nxt = pos + step
            if grid is not None and not airborne:
                nxt = _slide(grid, pos, nxt, block_bush)
            if nxt is None:
                unit.facing = direction_index(to.x, to.y)
                budget = 0.0
                break
            pos = nxt
            unit.facing = direction_index(to.x, to.y)
            budget = 0.0

    unit.pos = pos
    if grid is not None and not airborne:
        _keep_off_walls(unit, grid, block_bush)
    unit.moving = bool(unit.path)


# Raggio massimo con cui il corpo di un'unita' tiene le distanze dai muri: sotto
# 0.5 per poter passare nei varchi larghi un tile.
_WALL_R_MAX = 0.42


def _keep_off_walls(unit: Unit, grid: Grid, block_bush: bool) -> None:
    """Il corpo (cerchio) non entra nei tile bloccanti: la collisione col solo
    centro faceva sporgere lo sprite dentro i muri e incastrare negli spigoli.
    Spinge il centro fuori dai tile bloccanti adiacenti (cerchio contro
    rettangolo), accettando solo posizioni calpestabili."""
    r = min(getattr(unit, "radius", 0.35), _WALL_R_MAX)
    px, py = unit.pos.x, unit.pos.y
    cx, cy = math.floor(px), math.floor(py)
    for _ in range(2):
        moved = False
        for ty in range(cy - 1, cy + 2):
            for tx in range(cx - 1, cx + 2):
                if grid.is_walkable(tx, ty, block_bush):
                    continue
                qx = min(max(px, tx), tx + 1)
                qy = min(max(py, ty), ty + 1)
                dx, dy = px - qx, py - qy
                d2 = dx * dx + dy * dy
                if d2 >= r * r or d2 < 1e-12:
                    continue
                d = math.sqrt(d2)
                k = (r - d) / d
                nx, ny = px + dx * k, py + dy * k
                if grid.is_walkable_point(nx, ny, block_bush):
                    px, py = nx, ny
                    moved = True
        if not moved:
            break
    if px != unit.pos.x or py != unit.pos.y:
        unit.pos = Vec2(px, py)


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


def resolve_obstacles(units: list[Unit], obstacles: list, grid: Grid) -> None:
    """Spinge fuori le unità dai cerchi statici (x, y, raggio), es. le torri.

    La spinta è radiale, quindi chi cammina contro l'ostacolo scivola lungo il
    bordo con la componente tangenziale del passo. Se punta dritto al centro
    (componente tangenziale ~0) riceve una piccola spinta laterale verso il lato
    del waypoint, così non resta incastrato. Un waypoint DENTRO l'ostacolo si
    considera raggiunto appena lo si tocca.
    """
    for u in units:
        for ox, oy, r in obstacles:
            dx, dy = u.pos.x - ox, u.pos.y - oy
            min_d = r + u.radius
            d2 = dx * dx + dy * dy
            if d2 >= min_d * min_d:
                continue
            d = math.sqrt(d2)
            nx, ny = (dx / d, dy / d) if d > 1e-6 else (0.0, 1.0)
            new = Vec2(ox + nx * min_d, oy + ny * min_d)
            if u.path:
                w = u.path[0]
                if (w.x - ox) ** 2 + (w.y - oy) ** 2 < min_d * min_d:
                    u.path.pop(0)
                if u.path:
                    tx, ty = u.path[0].x - u.pos.x, u.path[0].y - u.pos.y
                    tl = math.hypot(tx, ty)
                    px, py = -ny, nx
                    side = tx * px + ty * py
                    if tl > 1e-6 and abs(side) < 0.3 * tl and tx * nx + ty * ny < 0:
                        sgn = 1.0 if side > 0 or (abs(side) < 1e-6 and u.id % 2) else -1.0
                        new = Vec2(new.x + px * 0.04 * sgn, new.y + py * 0.04 * sgn)
            if grid.is_walkable_point(new.x, new.y,
                                      block_bush=getattr(u, "bush_blocks", False)):
                u.pos = new


def _move_out(unit: Unit, offset: Vec2, grid: Grid) -> None:
    """Applica uno spostamento di separazione se la destinazione è calpestabile."""
    new_pos = unit.pos + offset
    bb = getattr(unit, "bush_blocks", False)
    if grid.is_walkable_point(new_pos.x, new_pos.y, block_bush=bb):
        unit.pos = new_pos
        if getattr(unit, "air_z", 0.0) <= 0.0:
            _keep_off_walls(unit, grid, bb)
