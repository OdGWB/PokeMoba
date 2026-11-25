"""Smite (come in League of Legends) e IA piu' prudente dei bot.

SMITE: danno VERO ai soli neutrali (campi, leggendari), 2 cariche, una carica si
ricarica in 90 s, 15 s tra un uso e l'altro, gittata 4 tile (500 unita' LoL).
Il danno sale con il livello: 600 al liv.1 fino a 1200 al liv.16. Serve a
"rubare" i mostri nel momento in cui hanno meno vita del danno dello Smite.

IA DEI BOT (solo decisioni, nessuna regola di gioco cambia):
  - niente inseguimento di un campione sotto una torre nemica se non ci sono buone
    possibilita' di ucciderlo;
  - i bot di lane non si allontanano dalla lane (leash piu' stretto nei primi
    minuti) per inseguire;
  - il jungler fa il giro dei campi e va a fare gank solo se e' probabile che
    fruttino (nemico ferito, fuori torre, senza troppi rinforzi).
"""
from __future__ import annotations

SMITE_RANGE = 4.0          # tile
SMITE_CHARGES = 2
SMITE_RECHARGE = 90.0      # s per ricaricare UNA carica
SMITE_LOCK = 15.0          # s minimi tra due Smite
# Linee da jungler (dex di tutte le forme): un GIOCATORE che ne sceglie una fa il
# jungler della squadra (Smite); altrimenti il jungler e' un bot.
JUNGLE_DEX = frozenset({
    290, 291, 292,          # Nincada > Ninjask / Shedinja
    215, 461, 903,          # Sneasel > Weavile / Sneasler
    216, 217, 901,          # Teddiursa > Ursaring > Ursaluna
    220, 221, 473,          # Swinub > Piloswine > Mamoswine
    158, 159, 160,          # Totodile > Croconaw > Feraligatr
})

# Le soglie dell'IA dei bot (guinzaglio, gank...) sono in engine/bot_params.py.


def smite_damage(level: int) -> float:
    return 600.0 + 40.0 * (max(1, level) - 1)


class SmiteMixin:
    # --- Smite ---------------------------------------------------------------
    def _update_smite(self, dt: float) -> None:
        for p in self.world.pokemons():
            if p.smite_charges < SMITE_CHARGES and p.smite_regen_at >= 0.0 \
                    and self.time >= p.smite_regen_at:
                p.smite_charges += 1
                p.smite_regen_at = (self.time + SMITE_RECHARGE
                                    if p.smite_charges < SMITE_CHARGES else -1.0)

    def smite_target(self, p):
        """Neutrale vivo piu' conveniente entro la gittata (leggendari prima)."""
        best, bk = None, None
        for w in self.world.wilds():
            if not w.alive:
                continue
            d = p.pos.dist(w.pos)
            if d > SMITE_RANGE + w.radius:
                continue
            key = (w.kind == "camp", d)
            if bk is None or key < bk:
                best, bk = w, key
        return best

    def use_smite(self, p, target=None) -> bool:
        """Usa lo Smite su `target` (o sul neutrale migliore a portata).
        Solo il jungler della squadra ha la Punizione."""
        if (not p.is_jungler or not p.alive or p.smite_charges <= 0 or self.time < p.smite_ready_at
                or self._immobile(p)):
            return False
        w = target if target is not None else self.smite_target(p)
        if w is None or not w.alive or p.pos.dist(w.pos) > SMITE_RANGE + w.radius:
            return False
        p.smite_charges -= 1
        p.smite_ready_at = self.time + SMITE_LOCK
        if p.smite_regen_at < 0.0:
            p.smite_regen_at = self.time + SMITE_RECHARGE
        self._deal_damage(p, w, smite_damage(p.level), ignore_shield=True)
        return True

    def _bot_smite(self, p, wild) -> None:
        """Smite "da LoL": solo per portare a zero un neutrale che ha meno vita
        del danno. Con una sola carica la tiene per i grandi e per i leggendari."""
        if wild is None or not wild.alive or wild.hp > smite_damage(p.level):
            return
        import config
        big = wild.kind != "camp" or wild.max_hp >= config.CAMP_HP * config.CAMP_BIG_MULT * 0.9
        if p.smite_charges >= SMITE_CHARGES or big:
            self.use_smite(p, wild)

    # --- aiutanti per l'IA dei bot ------------------------------------------
    def _under_enemy_tower(self, p, pos) -> bool:
        nat = getattr(self, "_bot_nat", None)
        if nat is not None:
            return nat.under_tower(self.world.structures(), p.team, pos.x, pos.y,
                                   self._bp(p).tower_margin)
        for e in self.world.structures():
            if e.kind == "tower" and e.alive and e.team != p.team \
                    and pos.dist(e.pos) <= e.attack_range + self._bp(p).tower_margin:
                return True
        return False

    def _count_champs(self, pos, r: float, team: int, exclude=None) -> int:
        nat = getattr(self, "_bot_nat", None)
        if nat is not None:
            return nat.count_champs(self.world.pokemons(), pos.x, pos.y, r, team, exclude)
        n = 0
        for e in self.world.pokemons():
            if e is exclude or not e.alive or e.team != team:
                continue
            if pos.dist(e.pos) <= r:
                n += 1
        return n

    def _good_kill_chance(self, p, t) -> bool:
        """Ha senso inseguire `t` anche sotto torre? Solo se e' quasi morto e io sto
        bene, oppure se in zona siamo piu' numerosi e lui e' gia' ferito."""
        bp = self._bp(p)
        if p.hp < p.max_hp * bp.kill_my_hp:
            return False
        hp_frac = t.hp / max(1.0, t.max_hp)
        if hp_frac <= bp.kill_low_hp:
            return True
        allies = self._count_champs(t.pos, bp.kill_count_r, p.team, exclude=p)
        foes = self._count_champs(t.pos, bp.kill_count_r, t.team)
        return hp_frac <= bp.kill_mid_hp and (allies + 1) - foes >= bp.kill_adv

    def _dist_to_lane(self, lane: str, team: int, pos) -> float:
        pts = self.oriented_lane(lane, team)
        if not pts:
            return 0.0
        return min(pos.dist(q) for q in pts)

    def _bot_filter_target(self, p, t):
        """Scarta i bersagli che un bot prudente non dovrebbe inseguire."""
        from .entities import Pokemon
        if t is None or not isinstance(t, Pokemon):
            return t
        bp = self._bp(p)
        if bp.utility and self._ai.get(p.id, {}).get("u_nofight"):
            return None           # IA a punteggio: combattere ora non conviene
        if self._under_enemy_tower(p, t.pos) and not self._good_kill_chance(p, t):
            return None
        limit = bp.lane_leash_early if self.time < bp.early_time else bp.lane_leash
        if (not p.is_jungler and not self._ai.get(p.id, {}).get("roaming")
                and self._dist_to_lane(p.assigned_lane, p.team, t.pos) > limit
                and not self._good_kill_chance(p, t)):
            return None
        return t

    def _jungler_gank_target(self, p, st):
        """Nemico ferito da andare a prendere, solo se il gank sembra fruttuoso."""
        bp = self._bp(p)
        if (self.time < bp.gank_min_time or p.level < bp.gank_min_level
                or self.time < st.get("gank_cd", 0.0) or p.hp < p.max_hp * bp.gank_my_hp):
            return None
        best, bs = None, None
        for e in self.world.pokemons():
            if e.team == p.team or not e.alive or not self.vision.is_enemy_visible(p.team, e.id):
                continue
            d = p.pos.dist(e.pos)
            if d > bp.gank_max_dist:
                continue
            hp_frac = e.hp / max(1.0, e.max_hp)
            if hp_frac > bp.gank_hp:
                continue
            if self._under_enemy_tower(p, e.pos) and not self._good_kill_chance(p, e):
                continue
            allies = self._count_champs(e.pos, bp.gank_count_r, p.team, exclude=p)
            foes = self._count_champs(e.pos, bp.gank_count_r, e.team)
            if foes - (allies + 1) >= bp.gank_max_disadv:
                continue
            score = (1.0 - hp_frac) * bp.gank_w_hp + allies * bp.gank_w_ally - d * bp.gank_w_dist
            if bs is None or score > bs:
                best, bs = e, score
        return best
