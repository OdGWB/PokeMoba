"""Simulazione a tick fisso: applica i comandi e avanza il World.

Questo è l'oggetto che, in Fase 5, girerà identico sul server. In Fase 1 lo
usa direttamente il client.
"""
from __future__ import annotations

from engine.pathfinding import plan_move
from engine.vec import Vec2
from engine.world import World

import config
from engine import evolution, skills

from .commands import (AttackCommand, AttackMoveCommand, BuyItemCommand,
                       ChooseUpgradeCommand, Command, CastMoveCommand, MoveCommand,
                       RankMoveCommand, RecallCommand, SellItemCommand, SmiteCommand, StopCommand,
                       SurrenderVoteCommand,
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
            self._drop_lock(unit)
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
        elif isinstance(cmd, SmiteCommand):
            if self.match is not None:
                self.match.use_smite(unit)
        elif isinstance(cmd, SurrenderVoteCommand):
            if self.match is not None:
                self.match.surrender_vote(unit, cmd.yes)
        elif isinstance(cmd, StopCommand):
            self._set_order(unit, "stop")
            unit.stop()

    def _drop_lock(self, unit) -> None:
        """Ordine di movimento: il bersaglio agganciato si molla davvero. Da fermo
        non verra' reinseguito per un po' (solo attaccato se entra a portata)."""
        if self.match is None or not hasattr(unit, "order"):
            return
        tid = unit.order_target_id if unit.order == "attack" else unit.target_id
        if tid is not None:
            self.match.skip_chase(unit, tid)

    @staticmethod
    def _set_order(unit, order: str, target_id=None, point=None) -> None:
        # Solo i Pokémon hanno il concetto di "ordine"; per gli altri è innocuo.
        if hasattr(unit, "order"):
            unit.order = order
            unit.order_target_id = target_id
            unit.order_point = point
            unit.idle_anchor = None     # nuovo ordine: nuova ancora d'inseguimento
            unit.champs_only = False
            if hasattr(unit, "move_dest"):
                unit.move_dest = None   # lo imposta _apply_move per gli ordini di movimento

    def _apply_move(self, unit, tx: float, ty: float) -> None:
        if not getattr(unit, "alive", True):
            return
        # Punto esatto del clic (anche nel proprio tile); clic su un muro o in
        # una zona irraggiungibile -> tile raggiungibile piu' vicino al clic.
        pts = plan_move(self.world.grid, (unit.pos.x, unit.pos.y), (tx, ty))
        if not pts:
            return
        unit.set_path([Vec2(px, py) for (px, py) in pts])
        if hasattr(unit, "move_dest"):
            # Destinazione ricordata: dopo un CC o un richiamo l'ordine riprende.
            unit.move_dest = Vec2(*pts[-1])
