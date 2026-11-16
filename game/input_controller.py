"""Traduce l'input del giocatore in comandi per la simulazione.

Stile LoL / MOBA:
  - Tasto destro: muovi verso il punto.
  - Tasto sinistro: attacca (su un nemico lo insegue; a terra = attack-move).
  - Q/W/E/R: tieni premuto per mirare (compare l'indicatore), rilascia (o clic
    sinistro) per lanciare la mossa verso il punto del mouse; clic destro
    annulla la mira.
  - Ctrl + Q/W/E/R: assegna un punto grado alla mossa.
  - S: ferma (tiene la posizione: attacca solo chi è già a portata).
  - Maiusc tenuto: "solo Pokémon" (il clic sinistro ignora minion, neutrali e
    strutture, sia sul bersaglio sia nell'attacco-movimento).
  - Rotella o Tab mentre si mira una R a polarità (Magnezone): alterna + / -.

L'input non tocca lo stato: produce Command con numero di sequenza.
"""
from __future__ import annotations

import pygame

import config
from engine.entities import Pokemon, Structure, Unit
from game import keybinds, mag_fx
from sim.commands import (AttackCommand, AttackMoveCommand, CastMoveCommand,
                          MoveCommand, RankMoveCommand, StopCommand)

def champs_only_held() -> bool:
    """Tasto "solo Pokémon" (Maiusc) tenuto premuto."""
    return bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)


ABILITY_KEYS = {pygame.K_q: "Q", pygame.K_w: "W", pygame.K_e: "E", pygame.K_r: "R"}  # predefiniti


def needs_aim(mv) -> bool:
    """Mosse che usano la PRESSIONE tenuta (Tiro Lungo) o la polarità scelta
    mirando (Magnezone): restano a mira normale anche col lancio rapido."""
    if mv is None:
        return False
    return bool(mv.effects.get("hold")) or mag_fx.has_polarity(mv)
PICK_RADIUS = 1.4


class InputController:
    def __init__(self, controlled_id: int):
        self.controlled_id = controlled_id
        self._seq = 0
        self.aiming_slot: str | None = None   # slot in fase di mira (per l'indicatore)
        self.aim_start = 0                    # ms: inizio della mira (pressione tenuta)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def process(self, events, camera, world=None) -> list:
        commands = []
        me = world.get(self.controlled_id) if world is not None else None
        for ev in events:
            if ev.type == pygame.KEYDOWN and keybinds.slot_for(ev.key):
                slot = keybinds.slot_for(ev.key)
                if pygame.key.get_mods() & pygame.KMOD_CTRL:
                    commands.append(RankMoveCommand(seq=self._next_seq(),
                                                    entity_id=self.controlled_id, slot=slot))
                elif self._can_aim(me, slot):
                    self.aim_start = pygame.time.get_ticks()
                    if keybinds.smart_cast and not needs_aim(self._move(me, slot)):
                        # Lancio rapido: parte subito verso il mouse, senza mirino.
                        commands.append(self._cast_at_mouse(slot, camera,
                                                            pygame.mouse.get_pos(), me))
                        self.aiming_slot = None
                    else:
                        self.aiming_slot = slot
            elif ev.type == pygame.KEYUP and keybinds.slot_for(ev.key):
                slot = keybinds.slot_for(ev.key)
                if self.aiming_slot == slot:
                    commands.append(self._cast_at_mouse(slot, camera, pygame.mouse.get_pos(), me))
                    self.aiming_slot = None
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self.aiming_slot:
                    commands.append(self._cast_at_mouse(self.aiming_slot, camera, ev.pos, me))
                    self.aiming_slot = None
                else:
                    commands.append(self._left_click(ev.pos, camera, world, me))
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
                if self.aiming_slot:
                    self.aiming_slot = None   # annulla la mira
                else:
                    tx, ty = self._world_tile(camera, ev.pos)
                    commands.append(MoveCommand(seq=self._next_seq(),
                                                entity_id=self.controlled_id, x=tx, y=ty))
            elif ev.type == pygame.KEYDOWN and ev.key == keybinds.key("stop"):
                commands.append(StopCommand(seq=self._next_seq(), entity_id=self.controlled_id))
            elif ((ev.type == pygame.MOUSEWHEEL
                   or (ev.type == pygame.KEYDOWN and ev.key == keybinds.key("score")))
                  and self.aiming_slot and mag_fx.has_polarity(self._move(me, self.aiming_slot))):
                mag_fx.toggle_polarity()   # Bombagnete / Campo Elettrico: + <-> -
        return commands

    # --- aiuto ---------------------------------------------------------------
    def _can_aim(self, me, slot: str) -> bool:
        if me is None or not getattr(me, "moveset", None):
            return False
        ms = me.moveset.get(slot)
        return bool(ms and ms.chosen and ms.unlocked and ms.rank > 0)

    @staticmethod
    def _move(me, slot):
        ms = me.moveset.get(slot) if me is not None and getattr(me, "moveset", None) else None
        return ms.chosen if ms is not None else None

    def _cast_at_mouse(self, slot, camera, pos, me=None):
        tx, ty = self._world_tile(camera, pos)
        hold = min(1.5, max(0.0, (pygame.time.get_ticks() - self.aim_start) / 1000.0))
        hold = mag_fx.cast_hold(self._move(me, slot), hold)   # R a polarità: il segno
        return CastMoveCommand(seq=self._next_seq(), entity_id=self.controlled_id,
                               slot=slot, x=tx, y=ty, hold=hold)

    def _left_click(self, pos, camera, world, me):
        tx, ty = self._world_tile(camera, pos)
        champs = champs_only_held()
        target = self._pick_enemy(world, me, tx, ty, champs)
        if target is not None:
            return AttackCommand(seq=self._next_seq(), entity_id=self.controlled_id,
                                 target_id=target.id)
        return AttackMoveCommand(seq=self._next_seq(), entity_id=self.controlled_id,
                                 x=tx, y=ty, champs_only=champs)

    def _world_tile(self, camera, pos):
        wx, wy = camera.screen_window_to_world(*pos)
        return wx / config.TILE_SIZE, wy / config.TILE_SIZE

    def _pick_enemy(self, world, me, tx: float, ty: float, champs_only: bool = False):
        if world is None or me is None:
            return None
        best, best_d = None, 1e9
        for e in world.combatants():
            if e.team == me.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Unit, Structure)):
                continue
            if champs_only and not isinstance(e, Pokemon):
                continue
            d = ((e.pos.x - tx) ** 2 + (e.pos.y - ty) ** 2) ** 0.5
            if d <= PICK_RADIUS + getattr(e, "radius", 0.0) and d < best_d:
                best, best_d = e, d
        return best
