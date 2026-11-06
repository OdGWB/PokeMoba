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

LANE_LEASH_EARLY = 7.0     # tile dalla lane: primi minuti
LANE_LEASH = 14.0
EARLY_TIME = 150.0         # s: fino a qui i bot di lane restano stretti sulla lane
GANK_MIN_TIME = 150.0      # s: prima i jungler farmano soltanto
GANK_MIN_LEVEL = 3
GANK_COOLDOWN = 75.0
GANK_DURATION = 14.0
GANK_MAX_DIST = 40.0


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
        """Usa lo Smite su `target` (o sul neutrale migliore a portata)."""
        if (not p.alive or p.smite_charges <= 0 or self.time < p.smite_ready_at
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
        for e in self.world.structures():
            if e.kind == "tower" and e.alive and e.team != p.team \
                    and pos.dist(e.pos) <= e.attack_range + 0.8:
                return True
        return False

    def _count_champs(self, pos, r: float, team: int, exclude=None) -> int:
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
        if p.hp < p.max_hp * 0.5:
            return False
        hp_frac = t.hp / max(1.0, t.max_hp)
        if hp_frac <= 0.25:
            return True
        allies = self._count_champs(t.pos, 8.0, p.team, exclude=p)
        foes = self._count_champs(t.pos, 8.0, t.team)
        return hp_frac <= 0.5 and (allies + 1) - foes >= 2

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
        if self._under_enemy_tower(p, t.pos) and not self._good_kill_chance(p, t):
            return None
        limit = LANE_LEASH_EARLY if self.time < EARLY_TIME else LANE_LEASH
        if (not p.is_jungler and not self._ai.get(p.id, {}).get("roaming")
                and self._dist_to_lane(p.assigned_lane, p.team, t.pos) > limit
                and not self._good_kill_chance(p, t)):
            return None
        return t

    def _jungler_gank_target(self, p, st):
        """Nemico ferito da andare a prendere, solo se il gank sembra fruttuoso."""
        if (self.time < GANK_MIN_TIME or p.level < GANK_MIN_LEVEL
                or self.time < st.get("gank_cd", 0.0) or p.hp < p.max_hp * 0.7):
            return None
        best, bs = None, None
        for e in self.world.pokemons():
            if e.team == p.team or not e.alive or not self.vision.is_enemy_visible(p.team, e.id):
                continue
            d = p.pos.dist(e.pos)
            if d > GANK_MAX_DIST:
                continue
            hp_frac = e.hp / max(1.0, e.max_hp)
            if hp_frac > self.bot_gank_hp:
                continue
            if self._under_enemy_tower(p, e.pos) and not self._good_kill_chance(p, e):
                continue
            allies = self._count_champs(e.pos, 9.0, p.team, exclude=p)
            foes = self._count_champs(e.pos, 9.0, e.team)
            if foes - (allies + 1) >= 2:
                continue
            score = (1.0 - hp_frac) * 10.0 + allies * 2.0 - d * 0.1
            if bs is None or score > bs:
                best, bs = e, score
        return best
