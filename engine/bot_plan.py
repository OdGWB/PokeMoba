"""IA dei bot a PIANI (opzionale): shopping, assedio, aiuto alle torri, roam del support.

E' ATTIVO di default su tutti i bot (`match.bot_plan = False` lo spegne). Il piano gira PRIMA dell'IA di base: se prende il comando del
bot ritorna True, altrimenti (False) il bot si comporta come sempre (lane, combattimento,
farm del jungler). Ordine di priorita':
  1. tornare in base a COMPRARE (oro sufficiente per il prossimo pezzo) e curarsi;
  2. NEXUS scoperto: tutti vanno a distruggerlo (se non sono feriti);
  3. AIUTARE a buttare giu' una torre nemica quando e' fattibile (poco vita, o minion
     alleati vicini e non siamo in inferiorita');
  4. SUPPORT che gira per la mappa a dare una mano agli alleati nei guai.
Il gank del jungler resta in engine/smite.py (soglie piu' larghe se bot_gank_hp > 0.6).
"""
from __future__ import annotations

import config
from .items import ITEM_SLOTS
from .vec import Vec2

RECALL_GOLD = 850           # oro minimo per tornare a comprare
RECALL_COOLDOWN = 110.0     # s tra due ritorni in base
RECALL_MAX = 110.0          # s: oltre, il ritorno viene annullato
SHOP_STAY = 14.0            # s massimi fermi in base (acquisti + cura)
SIEGE_FROM = 300.0          # s: da qui si aiutano le torri
CORE_FROM = 240.0
ROAM_FROM = 180.0
ROAM_TIME = 26.0
ROAM_COOLDOWN = 70.0
TOWER_NEAR = 28.0           # tile: torre raggiungibile
TOWER_NEAR_LOW = 45.0       # tile: se e' quasi caduta si viene da piu' lontano


class BotPlanMixin:
    bot_plan = True
    bot_gank_hp = 0.6

    # --- statistiche (solo osservazione) ------------------------------------
    def _bps(self, p) -> dict:
        d = self.__dict__.setdefault("bot_stat", {})
        return d.setdefault(p.id, {"recalls": 0, "roams": 0, "tower_t": 0.0, "core_t": 0.0,
                                   "bought": 0})

    # --- passo principale ----------------------------------------------------
    def _bot_plan_step(self, p, dt: float) -> bool:
        if self._immobile(p):
            return False
        st = self._ai.setdefault(p.id, {})
        if p.hp < p.max_hp * 0.28 and not st.get("recall"):
            return False                      # ritirata di base
        if self._plan_shop(p, st, dt):
            return True
        if self._acquire_enemy_champ(p, 4.5) is not None:
            return False                      # scontro in corso: combatte l'IA di base
        if self._plan_core(p, st, dt):
            return True
        if self._plan_tower(p, st, dt):
            return True
        if getattr(p, "bot_support", False) and self._plan_roam(p, st, dt):
            return True
        return False

    # --- 1. shopping ---------------------------------------------------------
    def _bot_next_buy(self, p):
        """Lo stesso criterio di _bot_buy, ma senza comprare: id del prossimo acquisto."""
        cat = self.item_catalog

        def can_buy(iid):
            it = cat.get(iid)
            if it is None or not cat.group_ok(iid, p.items):
                return False
            if it.group == "exp_share" and self._team_has_item(p.team, iid):
                return False
            slots_after = len(p.items) - len(cat.components_in(iid, p.items)) + 1
            return p.gold >= cat.effective_price(iid, p.items) and slots_after <= ITEM_SLOTS

        def pick(iid, need=1):
            if p.items.count(iid) >= need:
                return None
            if can_buy(iid):
                return iid
            comps = cat.get(iid).build_from
            for comp in dict.fromkeys(comps):
                got = pick(comp, comps.count(comp))
                if got is not None:
                    return got
            return None

        for target in (p.rec_items or cat.recommended_for(p.role)):
            it = cat.get(target)
            if it is None or target in p.items:
                continue
            if not cat.group_ok(target, p.items) or (
                    it.group == "exp_share" and self._team_has_item(p.team, target)):
                continue
            return pick(target)
        return None

    def _plan_shop(self, p, st, dt) -> bool:
        home = p.spawn_pos
        if st.get("recall"):
            ps = self._bps(p)
            at_home = p.pos.dist(home) <= config.SHOP_RANGE
            if at_home:
                st.setdefault("shop_at", self.time)
                done = (self._bot_next_buy(p) is None and p.hp >= p.max_hp * 0.85)
                if done or self.time - st["shop_at"] > SHOP_STAY:
                    st["recall"] = False
                    st.pop("shop_at", None)
                    st["last_recall"] = self.time
                    return False
                p.target_id = None
                p.stop()
                return True
            if self.time - st["recall_t0"] > RECALL_MAX:
                st["recall"] = False
                st["last_recall"] = self.time
                return False
            p.target_id = None
            self._move_towards(p, home, dt, use_astar=True)
            return True
        if (self.time < 150.0 or self.time - st.get("last_recall", -999.0) < RECALL_COOLDOWN
                or p.gold < RECALL_GOLD or p.pos.dist(home) <= config.SHOP_RANGE):
            return False
        if self._acquire_enemy_champ(p, 9.0) is not None:
            return False                      # non mollare un combattimento
        if self._bot_next_buy(p) is None:
            return False
        st["recall"] = True
        st["recall_t0"] = self.time
        self._bps(p)["recalls"] += 1
        return False

    # --- 2. nexus scoperto ---------------------------------------------------
    def _plan_core(self, p, st, dt) -> bool:
        if self.time < CORE_FROM or p.hp < p.max_hp * 0.4:
            return False
        enemy = 1 - p.team
        if self._alive_towers(enemy) > config.CORE_EXPOSE_TOWERS_LEFT:
            return False
        core = next((c for c in self.world.cores() if c.team == enemy and c.alive), None)
        if core is None:
            return False
        p.target_id = core.id
        self._bps(p)["core_t"] += dt
        if self._within_attack(p, core):
            p.stop()
            self._face(p, core)
            self._bot_try_cast(p, core)
        else:
            self._move_towards(p, core.pos, dt, use_astar=True)
        return True

    # --- 3. aiuto alle torri -------------------------------------------------
    def _plan_tower(self, p, st, dt) -> bool:
        t = self.time
        if t < SIEGE_FROM or p.hp < p.max_hp * 0.55:
            return False
        if (p.is_jungler and t < 480.0) or (getattr(p, "bot_support", False) and t < 480.0):
            return False
        best, bs = None, None
        for tw in self.world.structures():
            if tw.kind != "tower" or not tw.alive or tw.team == p.team:
                continue
            d = p.pos.dist(tw.pos)
            frac = tw.hp / max(1.0, tw.max_hp)
            if d > (TOWER_NEAR_LOW if frac <= 0.5 else TOWER_NEAR):
                continue
            minions = self._has_allied_minion_near(p, tw.pos, 4.5)
            if not minions and frac > 0.3:
                continue
            allies = self._count_champs(tw.pos, 12.0, p.team) + (0 if d <= 12.0 else 1)
            foes = sum(1 for e in self.world.pokemons()
                       if e.team != p.team and e.alive and tw.pos.dist(e.pos) <= 12.0
                       and self.vision.is_enemy_visible(p.team, e.id))
            if foes > allies:
                continue
            score = d * 0.5 + frac * 30.0 - (10.0 if minions else 0.0)
            if bs is None or score < bs:
                best, bs = tw, score
        if best is None:
            return False
        p.target_id = best.id
        self._bps(p)["tower_t"] += dt
        if self._within_attack(p, best):
            p.stop()
            self._face(p, best)
            self._bot_try_cast(p, best)
        else:
            self._chase(p, best, dt)
        return True

    # --- 4. roam del support -------------------------------------------------
    def _plan_roam(self, p, st, dt) -> bool:
        from .spiritomb import PASSIVE_ID as SPIRIT
        if self.time < ROAM_FROM or p.passive_id == SPIRIT:
            return False
        if p.hp < p.max_hp * 0.5:
            st["roam_until"] = 0.0
        if st.get("roam_until", 0.0) > self.time:
            ally = self.world.get(st.get("roam_id"))
            if ally is None or not getattr(ally, "alive", False):
                st["roam_until"] = 0.0
                st["roaming"] = False
                return False
            st["roaming"] = True
            if p.pos.dist(ally.pos) > 3.5:
                p.target_id = None
                self._move_towards(p, ally.pos, dt, use_astar=True)
                return True
            return False                      # vicino all'alleato: l'IA di base combatte
        st["roaming"] = False
        if self.time < st.get("roam_cd", 0.0):
            return False
        best, bs = None, None
        for a in self.world.pokemons():
            if a is p or a.team != p.team or not a.alive or getattr(a, "bot_support", False):
                continue
            foes = sum(1 for e in self.world.pokemons()
                       if e.team != p.team and e.alive and a.pos.dist(e.pos) <= 10.0
                       and self.vision.is_enemy_visible(p.team, e.id))
            frac = a.hp / max(1.0, a.max_hp)
            other_lane = 1.0 if a.assigned_lane != p.assigned_lane else 0.0
            score = foes * 4.0 + (1.0 - frac) * 3.0 + other_lane * 2.0 - p.pos.dist(a.pos) * 0.05
            if foes == 0 and frac > 0.7 and not other_lane:
                continue
            if bs is None or score > bs:
                best, bs = a, score
        st["roam_cd"] = self.time + 15.0
        if best is None:
            return False
        st["roam_id"] = best.id
        st["roam_until"] = self.time + ROAM_TIME
        st["roam_cd"] = self.time + ROAM_COOLDOWN
        self._bps(p)["roams"] += 1
        return False
