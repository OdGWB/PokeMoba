"""Simulazione a tick fisso: applica i comandi e avanza il World.

Questo è l'oggetto che, in Fase 5, girerà identico sul server. In Fase 1 lo
usa direttamente il client.
"""
from __future__ import annotations

from engine.pathfinding import find_path, smooth_path
from engine.vec import Vec2
from engine.world import World

import config
from engine import evolution, skills

from .commands import (AttackCommand, AttackMoveCommand, BuyItemCommand,
                       ChooseUpgradeCommand, Command, CastMoveCommand, MoveCommand,
                       RankMoveCommand, RecallCommand, SellItemCommand, StopCommand,
                       UseItemCommand)


class Simulation:
    def __init__(self, world: World, tick_dt: float, match=None):
        self.world = world
        self.tick_dt = tick_dt
        self.match = match          # engine.match.Match, opzionale (None = demo libera)
        self.tick_count = 0
        self._pending: list[Command] = []

    def queue_command(self, cmd: Command) -> None:
        """Accoda un comando da applicare all'inizio del prossimo tick."""
        self._pending.append(cmd)

    def step(self) -> None:
        """Esegue un singolo tick di simulazione."""
        for cmd in self._pending:
            self._apply(cmd)
        self._pending.clear()
        if self.match is not None:
            # Il Match applica le regole e, al suo interno, avanza il movimento.
            self.match.update(self.tick_dt, self.tick_count)
        else:
            self.world.tick(self.tick_dt)
        self.tick_count += 1

    # --- applicazione comandi ------------------------------------------------
    def _apply(self, cmd: Command) -> None:
        unit = self.world.get(cmd.entity_id)
        if unit is None or not getattr(unit, "alive", True):
            return
        if isinstance(cmd, MoveCommand):
            self._set_order(unit, "move", point=Vec2(cmd.x, cmd.y))
            self._apply_move(unit, cmd.x, cmd.y)
        elif isinstance(cmd, AttackCommand):
            # Attacca un bersaglio: il movimento (inseguimento) lo guida il Match.
            self._set_order(unit, "attack", target_id=cmd.target_id)
            unit.stop()
        elif isinstance(cmd, AttackMoveCommand):
            self._set_order(unit, "attackmove", point=Vec2(cmd.x, cmd.y))
            if hasattr(unit, "champs_only"):
                unit.champs_only = bool(getattr(cmd, "champs_only", False))
                unit.target_id = None   # nuovo attacco-movimento: si sceglie da capo
        elif isinstance(cmd, CastMoveCommand):
            # Il lancio vero lo esegue il Match al prossimo tick (autoritativo).
            if hasattr(unit, "pending_cast"):
                unit.pending_cast = (cmd.slot, cmd.x, cmd.y)
                unit.cast_hold = max(0.0, min(2.0, float(getattr(cmd, "hold", 0.0))))
        elif isinstance(cmd, RankMoveCommand):
            if hasattr(unit, "moveset"):
                skills.rank_up(unit, cmd.slot)
        elif isinstance(cmd, ChooseUpgradeCommand):
            # La scelta del potenziamento si fa solo in base.
            if (hasattr(unit, "moveset") and getattr(unit, "spawn_pos", None) is not None
                    and unit.pos.dist(unit.spawn_pos) <= config.SHOP_RANGE):
                evolution.apply_choice(unit, cmd.slot, cmd.index)
        elif isinstance(cmd, BuyItemCommand):
            if self.match is not None:
                self.match.shop_buy(unit, cmd.item_id)
        elif isinstance(cmd, SellItemCommand):
            if self.match is not None:
                self.match.shop_sell(unit, cmd.slot)
        elif isinstance(cmd, UseItemCommand):
            if self.match is not None:
                self.match.use_item(unit, cmd.slot)
        elif isinstance(cmd, RecallCommand):
            # Avvia o annulla il richiamo verso la base.
            if self.match is not None and hasattr(unit, "recalling"):
                if unit.recalling:
                    unit.recalling = False
                else:
                    unit.recalling = True
                    unit.recall_start = self.match.time
                    unit.recall_until = self.match.time + config.RECALL_TIME
                    unit.order = "stop"
                    unit.stop()
        elif isinstance(cmd, StopCommand):
            self._set_order(unit, "stop")
            unit.stop()

    @staticmethod
    def _set_order(unit, order: str, target_id=None, point=None) -> None:
        # Solo i Pokémon hanno il concetto di "ordine"; per gli altri è innocuo.
        if hasattr(unit, "order"):
            unit.order = order
            unit.order_target_id = target_id
            unit.order_point = point
            unit.idle_anchor = None     # nuovo ordine: nuova ancora d'inseguimento
            unit.champs_only = False

    def _apply_move(self, unit, tx: float, ty: float) -> None:
        if not getattr(unit, "alive", True):
            return
        grid = self.world.grid
        start = (int(unit.pos.x), int(unit.pos.y))
        goal = (int(tx), int(ty))
        # Se il tile cliccato è un muro, prova a trovare il tile libero più
        # vicino (semplice ricerca a spirale) per non ignorare il click.
        if not grid.is_walkable(*goal):
            goal = _nearest_walkable(grid, goal)
            if goal is None:
                return
        tile_path = find_path(grid, start, goal)
        if not tile_path:
            return
        points = smooth_path(grid, tile_path)
        # I waypoint dopo il primo (il centro del tile di partenza) sono il
        # percorso vero. Se non ce ne sono, il click era nel tile corrente.
        waypoints = [Vec2(px, py) for (px, py) in points[1:]]
        if not waypoints:
            unit.stop()
            return
        unit.set_path(waypoints)


def _nearest_walkable(grid, goal: tuple[int, int], max_r: int = 6):
    gx, gy = goal
    for r in range(1, max_r + 1):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                if grid.is_walkable(gx + dx, gy + dy):
                    return (gx + dx, gy + dy)
    return None
