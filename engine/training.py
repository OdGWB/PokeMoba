"""Regole della modalita' ALLENAMENTO (e del Tutorial), sopra il Match normale.

Sottoclasse di Match: la logica di gioco vera resta intatta, qui si cambiano solo
le regole della partita di prova sulla mappa piccola (data/maps/map_training.json):

  - ondate di minion ACCENDIBILI (spente di default), leggendari spenti;
  - torri e nuclei INDISTRUTTIBILI (tornano pieni invece di morire: niente vittoria);
  - MANICHINI = Pokemon della squadra 1 che non attaccano e non si muovono da soli
    (la scena li riporta al loro posto), rinascono subito e si rigenerano se nessuno
    li colpisce per qualche secondo;
  - ricariche AZZERATE e ORO INFINITO per il giocatore (accendibili/spegnibili);
  - misuratore del danno inflitto ai manichini (totale, ultimo colpo, DPS).

Puro: nessun pygame.
"""
from __future__ import annotations

import math

from .entities import Pokemon, Structure
from .match import Match

DUMMY_RESPAWN = 2.5        # s: un manichino abbattuto rinasce quasi subito
DUMMY_REGEN_AFTER = 4.0    # s senza danno -> torna a vita piena
DPS_WINDOW = 5.0           # s: finestra del DPS ("danno negli ultimi 5 s / 5")
INF_GOLD = 99999


class TrainingMatch(Match):
    def __init__(self, world, map_data):
        super().__init__(world, map_data)
        self.waves_on = False
        self.no_cd = True
        self.inf_gold = True
        self.player_id: int | None = None
        self.dummy_ids: set[int] = set()
        self._dummy_hit_at: dict[int, float] = {}
        # Misuratore del danno ai manichini.
        self.dmg_total = 0.0
        self.dmg_last = 0.0
        self.dmg_hits: list[tuple[float, float]] = []   # (istante, danno)
        # Leggendari spenti: la giungla non apre mai le tane.
        self.jungle._next_meteo = math.inf
        self.jungle._arceus_open_time = math.inf

    # --- regole --------------------------------------------------------------
    def _update_waves(self, dt: float) -> None:
        if self.waves_on:
            super()._update_waves(dt)
        elif self._spawn_queue:      # spegnendo: nessuna nuova ondata in coda
            self._spawn_queue.clear()

    def _update_ai(self, dt: float) -> None:
        super()._update_ai(dt)
        for did in self.dummy_ids:   # i manichini non attaccano mai da soli
            d = self.world.get(did)
            if d is not None:
                d.target_id = None

    def _on_death(self, victim, killer) -> None:
        if isinstance(victim, Structure):    # torri e nucleo: indistruttibili
            victim.hp = victim.max_hp
            victim.alive = True
            return
        super()._on_death(victim, killer)
        if isinstance(victim, Pokemon) and victim.id in self.dummy_ids:
            victim.respawn_timer = victim.respawn_max = DUMMY_RESPAWN

    def _track_damage(self, attacker, target, amount, dmg_type) -> None:
        super()._track_damage(attacker, target, amount, dmg_type)
        tid = getattr(target, "id", None)
        if tid in self.dummy_ids:
            self._dummy_hit_at[tid] = self.time
            if getattr(attacker, "id", None) == self.player_id and amount > 0:
                self.dmg_total += amount
                self.dmg_last = amount
                self.dmg_hits.append((self.time, amount))

    def update(self, dt: float, tick: int) -> None:
        super().update(dt, tick)
        self.winner = None            # la prova non finisce mai
        p = self.world.get(self.player_id) if self.player_id is not None else None
        if p is not None:
            if self.no_cd:
                self.reset_cooldowns(p)
            if self.inf_gold:
                p.gold = INF_GOLD
        for did in self.dummy_ids:
            d = self.world.get(did)
            if (d is not None and d.alive and d.hp < d.max_hp
                    and self.time - self._dummy_hit_at.get(did, -99.0) > DUMMY_REGEN_AFTER):
                d.hp = d.max_hp
        cut = self.time - DPS_WINDOW
        if self.dmg_hits and self.dmg_hits[0][0] < cut:
            self.dmg_hits = [h for h in self.dmg_hits if h[0] >= cut]

    # --- comandi del pannello ------------------------------------------------
    def reset_cooldowns(self, p) -> None:
        for ms in p.moveset.values():
            ms.cooldown_remaining = 0.0
            mv = ms.chosen
            if mv is not None and mv.charges > 0:
                ms.charges_cur = float(mv.charges)
        if getattr(p, "is_jungler", False):
            p.smite_charges = 2
            p.smite_ready_at = 0.0
            p.smite_regen_at = -1.0

    def dps(self) -> float:
        return sum(a for _, a in self.dmg_hits) / DPS_WINDOW

    def reset_meter(self) -> None:
        self.dmg_total = self.dmg_last = 0.0
        self.dmg_hits.clear()

    def heal_dummies(self) -> None:
        for did in self.dummy_ids:
            d = self.world.get(did)
            if d is not None and d.alive:
                d.hp = d.max_hp

    def clear_minions(self) -> None:
        for m in self.world.minions():
            self.world.remove(m.id)
            self._ai.pop(m.id, None)
        self._spawn_queue.clear()
