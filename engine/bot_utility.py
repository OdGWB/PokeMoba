"""IA dei bot a PUNTEGGIO (utility AI): sostituisce le scelte on/off con punteggi continui.

Attiva per squadra con Match.bot_params[team].utility = True (spenta di default: con
utility=False il gioco non cambia di un bit). Al posto della catena di "se X allora Y"
di engine/bot_plan.py e della ritirata a soglia fissa, ogni u_period secondi il bot
valuta un punteggio per ogni INTENZIONE e sceglie la piu' alta:

  retreat  tornare in base (poca vita, peggio se in inferiorita')
  fight    attaccare il campione nemico piu' vicino (vantaggio di forza, vite, torri)
  home     tornare a comprare / curarsi (oro, tempo dall'ultimo ritorno, calma)
  core     buttare giu' il nexus scoperto
  siege    aiutare a buttare giu' una torre nemica
  roam     (support) andare da un alleato nei guai
  lane     tutto il resto: l'IA di base (lane per i laner, farm/gank per il jungler)

Le soglie dei piani diventano il CENTRO di rampe morbide (u_band) e i "salta se"
diventano malus. ISTERESI: l'intenzione in corso ha un bonus (u_stick) e non si cambia
prima di u_min_hold secondi, a meno che la nuova non la superi di u_override.
Le azioni riusano gli stessi aiutanti dell'IA di base (stesso movimento, stesse mosse).

TRACCIA: Match.bot_trace[id] = secondi per intenzione, numero di cambi e gli ultimi
cambi (istante, da, a, punteggi) per capire cosa decide il bot.
Leggero: solo aritmetica in Python su poche unita' (gira anche sull'host online).
"""
from __future__ import annotations

import math

import config
from .entities import Pokemon
from .vec import Vec2

INTENTS = ("retreat", "fight", "home", "core", "siege", "roam", "lane")
TRACE_LOG = 60                   # ultimi cambi tenuti per bot


def _ramp(x: float, lo: float, hi: float) -> float:
    """0 sotto lo, 1 sopra hi, lineare in mezzo."""
    if hi <= lo:
        return 1.0 if x >= hi else 0.0
    return 0.0 if x <= lo else 1.0 if x >= hi else (x - lo) / (hi - lo)


def _sig(x: float) -> float:
    if x < -30.0:
        return 0.0
    if x > 30.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


class BotUtilityMixin:

    # --- traccia -------------------------------------------------------------
    def _u_trace(self, p) -> dict:
        d = self.__dict__.setdefault("bot_trace", {})
        tr = d.get(p.id)
        if tr is None:
            tr = d[p.id] = {"time": dict.fromkeys(INTENTS, 0.0), "switches": 0, "log": []}
        return tr

    # --- passo principale ----------------------------------------------------
    def _bot_utility_step(self, p, dt: float) -> None:
        if self._immobile(p):
            p.stop()
            return
        st = self._ai.setdefault(p.id, {})
        bp = self._bp(p)
        cur = st.get("u_int")
        if cur is None or self.time >= st.get("u_next", 0.0):
            st["u_next"] = self.time + bp.u_period
            scores = self._u_scores(p, st, bp)
            best = max(scores, key=scores.get)
            if cur is not None and best != cur and cur in scores:
                held = self.time - st.get("u_since", 0.0)
                if held < bp.u_min_hold and scores[best] < scores[cur] + bp.u_override:
                    best = cur
            if best != cur:
                self._u_leave(p, st, cur)
                tr = self._u_trace(p)
                tr["switches"] += 1
                tr["log"].append((round(self.time, 1), cur, best,
                                  {k: round(v, 2) for k, v in scores.items()}))
                if len(tr["log"]) > TRACE_LOG:
                    del tr["log"][0]
                st["u_int"] = cur = best
                st["u_since"] = self.time
        self._u_trace(p)["time"][cur] += dt
        getattr(self, "_u_do_" + cur)(p, st, bp, dt)

    def _u_leave(self, p, st, cur) -> None:
        """Pulizia quando si abbandona un'intenzione."""
        if cur == "home" and st.get("recall"):
            st["recall"] = False
            st.pop("shop_at", None)
            st["last_recall"] = self.time

    # --- punteggi ------------------------------------------------------------
    def _u_scores(self, p, st, bp) -> dict:
        t = self.time
        hpf = p.hp / max(1.0, p.max_hp)
        band = bp.u_band
        # Forza in zona: somma della vita attuale dei campioni (alleati compreso me,
        # nemici solo se visibili). adv in [-1, 1].
        ally_pow = foe_pow = 0.0
        r = bp.u_threat_r
        for e in self.world.pokemons():
            if not e.alive or p.pos.dist(e.pos) > r:
                continue
            if e.team == p.team:
                ally_pow += e.hp
            elif self.vision.is_enemy_visible(p.team, e.id):
                foe_pow += e.hp
        adv = (ally_pow - foe_pow) / max(1.0, ally_pow + foe_pow) if foe_pow > 0 else 1.0
        sc = {"lane": bp.u_w_lane}

        # ritirata
        low = 1.0 - _ramp(hpf, bp.retreat_hp - band, bp.retreat_hp + band)
        if low > 0.0:
            danger = (1.0 - adv) * 0.5 if foe_pow > 0 else 0.0
            sc["retreat"] = bp.u_w_retreat * low * (1.0 + bp.u_ret_danger * (danger - 0.5))

        # combattimento
        enemy = self._acquire_enemy_champ(p, bp.aggro)
        st["u_enemy"] = enemy.id if enemy is not None else None
        if enemy is not None:
            ehpf = enemy.hp / max(1.0, enemy.max_hp)
            x = bp.u_fight_adv * adv + bp.u_fight_hp * (hpf - ehpf) + bp.u_fight_bias
            if self._under_enemy_tower(p, enemy.pos):
                x -= bp.u_fight_tower
            sc["fight"] = bp.u_w_fight * _sig(bp.u_fight_k * x)
        # In "lane" l'IA di base non sceglie campioni se combattere non conviene.
        st["u_nofight"] = enemy is not None and sc.get("fight", 0.0) < sc["lane"]

        # ritorno in base: comprare e/o curarsi
        home_s = 0.0
        quiet = 1.0 if foe_pow <= 0 else 0.2
        if st.get("recall") or (not p.bot_standin and t >= bp.shop_from
                                and self._bot_next_buy(p) is not None):
            gold = _ramp(p.gold, bp.recall_gold - bp.u_shop_gold_band,
                         bp.recall_gold + bp.u_shop_gold_band)
            cool = _ramp(t - st.get("last_recall", -999.0), bp.recall_cooldown * 0.5,
                         bp.recall_cooldown)
            home_s = bp.u_w_shop * gold * cool * quiet
            if st.get("recall"):
                home_s = max(home_s, bp.u_w_shop * quiet)     # gia' in viaggio: si finisce
        heal = _ramp(bp.shop_done_hp - hpf, 0.0, bp.shop_done_hp - bp.retreat_hp)
        home_s = max(home_s, bp.u_w_heal * heal * quiet)
        if home_s > 0.0:
            sc["home"] = home_s

        # nexus scoperto
        enemy_team = 1 - p.team
        if self._alive_towers(enemy_team) <= config.CORE_EXPOSE_TOWERS_LEFT:
            core = next((c for c in self.world.cores() if c.team == enemy_team and c.alive), None)
            if core is not None:
                st["u_core"] = core.id
                sc["core"] = (bp.u_w_core * _ramp(hpf, bp.core_my_hp - band, bp.core_my_hp + band)
                              * _ramp(t, bp.core_from - 30.0, bp.core_from + 30.0))

        # assedio
        tgate = _ramp(t, bp.siege_from - 60.0, bp.siege_from + 60.0) * _ramp(
            hpf, bp.siege_my_hp - band, bp.siege_my_hp + band)
        if (p.is_jungler or getattr(p, "bot_support", False)) and tgate > 0.0:
            tgate *= _ramp(t, bp.siege_late_roles - 60.0, bp.siege_late_roles + 60.0)
        if tgate > 0.0:
            best, bs = None, None
            cr = bp.tower_count_r
            for tw in self.world.structures():
                if tw.kind != "tower" or not tw.alive or tw.team == p.team:
                    continue
                d = p.pos.dist(tw.pos)
                if d > bp.tower_near_low:
                    continue
                frac = tw.hp / max(1.0, tw.max_hp)
                minions = self._has_allied_minion_near(p, tw.pos, bp.tower_minion_r)
                allies = self._count_champs(tw.pos, cr, p.team) + (0 if d <= cr else 1)
                foes = sum(1 for e in self.world.pokemons()
                           if e.team != p.team and e.alive and tw.pos.dist(e.pos) <= cr
                           and self.vision.is_enemy_visible(p.team, e.id))
                good = (bp.tower_w_frac * (1.0 - frac)
                        + (bp.tower_w_minion if minions else -bp.tower_w_minion)
                        + 3.0 * (allies - foes) - d * bp.tower_w_dist)
                if bs is None or good > bs:
                    best, bs = tw, good
            if best is not None:
                st["u_tower"] = best.id
                sc["siege"] = bp.u_w_siege * tgate * _sig(bp.u_siege_k * bs + bp.u_siege_bias)

        # roam del support
        if getattr(p, "bot_support", False):
            from .spiritomb import PASSIVE_ID as SPIRIT
            if p.passive_id != SPIRIT:
                rgate = _ramp(t, bp.roam_from - 30.0, bp.roam_from + 30.0) * _ramp(
                    hpf, bp.roam_my_hp - band, bp.roam_my_hp + band)
                if rgate > 0.0:
                    best, bs = None, None
                    for a in self.world.pokemons():
                        if a is p or a.team != p.team or not a.alive or getattr(a, "bot_support", False):
                            continue
                        foes = sum(1 for e in self.world.pokemons()
                                   if e.team != p.team and e.alive and a.pos.dist(e.pos) <= bp.roam_foe_r
                                   and self.vision.is_enemy_visible(p.team, e.id))
                        frac = a.hp / max(1.0, a.max_hp)
                        other = 1.0 if a.assigned_lane != p.assigned_lane else 0.0
                        u = (foes * bp.roam_w_foe + (1.0 - frac) * bp.roam_w_hp
                             + other * bp.roam_w_lane - p.pos.dist(a.pos) * bp.roam_w_dist)
                        if bs is None or u > bs:
                            best, bs = a, u
                    if best is not None:
                        st["u_ally"] = best.id
                        sc["roam"] = bp.u_w_roam * rgate * _sig(bs - bp.u_roam_bias)
        return sc

    # --- azioni --------------------------------------------------------------
    def _u_do_lane(self, p, st, bp, dt) -> None:
        if p.is_jungler:
            self._ai_jungler(p, dt)
        else:
            self._ai_bot(p, dt)

    def _u_do_retreat(self, p, st, bp, dt) -> None:
        p.target_id = None
        st["gank_id"] = None
        self._move_towards(p, p.spawn_pos, dt, use_astar=True)

    def _u_do_fight(self, p, st, bp, dt) -> None:
        t = self.world.get(st.get("u_enemy"))
        if (t is None or not t.alive or not isinstance(t, Pokemon)
                or not self.vision.is_enemy_visible(p.team, t.id)):
            st["u_next"] = 0.0                # bersaglio perso: si rivaluta subito
            self._u_do_lane(p, st, bp, dt)
            return
        self._u_attack(p, t, dt, chase=True)

    def _u_do_home(self, p, st, bp, dt) -> None:
        home = p.spawn_pos
        if not st.get("recall"):
            st["recall"] = True
            st["recall_t0"] = self.time
            self._bps(p)["recalls"] += 1
        p.target_id = None
        if p.pos.dist(home) <= config.SHOP_RANGE:
            st.setdefault("shop_at", self.time)
            done = (self._bot_next_buy(p) is None and p.hp >= p.max_hp * bp.shop_done_hp)
            if done or self.time - st["shop_at"] > bp.shop_stay:
                self._u_leave(p, st, "home")
                st["u_next"] = 0.0
            p.stop()
            return
        if self.time - st["recall_t0"] > bp.recall_max:
            self._u_leave(p, st, "home")
            st["u_next"] = 0.0
        self._move_towards(p, home, dt, use_astar=True)

    def _u_do_core(self, p, st, bp, dt) -> None:
        core = self.world.get(st.get("u_core"))
        if core is None or not core.alive:
            st["u_next"] = 0.0
            self._u_do_lane(p, st, bp, dt)
            return
        self._bps(p)["core_t"] += dt
        self._u_attack(p, core, dt, chase=False)

    def _u_do_siege(self, p, st, bp, dt) -> None:
        tw = self.world.get(st.get("u_tower"))
        if tw is None or not tw.alive:
            st["u_next"] = 0.0
            self._u_do_lane(p, st, bp, dt)
            return
        self._bps(p)["tower_t"] += dt
        self._u_attack(p, tw, dt, chase=True)

    def _u_do_roam(self, p, st, bp, dt) -> None:
        ally = self.world.get(st.get("u_ally"))
        if ally is None or not getattr(ally, "alive", False):
            st["u_next"] = 0.0
            self._u_do_lane(p, st, bp, dt)
            return
        if p.pos.dist(ally.pos) > bp.roam_follow_r:
            p.target_id = None
            self._move_towards(p, ally.pos, dt, use_astar=True)
        else:
            self._ai_bot(p, dt)                # vicino all'alleato: combatte l'IA di base

    def _u_attack(self, p, t, dt, chase: bool) -> None:
        p.target_id = t.id
        if self._within_attack(p, t):
            p.stop()
            self._face(p, t)
            self._bot_try_cast(p, t)
        else:
            self._bot_try_cast(p, t)
            if chase:
                self._chase(p, t, dt)
            else:
                self._move_towards(p, t.pos, dt, use_astar=True)
