"""Regole della linea Eevee: passiva Adattabilità (evoluzione al liv.8 decisa
dalla combinazione dei potenziamenti Q/W/E), mosse di Eevee e passive/ultimate
delle 8 forme evolute.

Puro: nessun pygame. È un mixin di Match (engine/match.py): usa lo stesso stato
(self.time, self.world, self.fx_events, _combat_hash, gli _apply_*). Il client
legge match.wishes, match.swift_stars, match.thunders, match.blizzards e
match.future_sights per disegnare.

Assi delle scelte (indice del potenziamento nel JSON):
  Q: 0 Offensivo (Sdoppiatore)  / 1 Protettivo (Desiderio)
  W: 0 Ravvicinato (Morso)      / 1 A distanza (Comete)
  E: 0 Rapido (Rapidattacco)    / 1 Solido (Resistenza)
"""
from __future__ import annotations

import math
import random

from .entities import Minion, Pokemon, Structure, Wild
from .vec import Vec2

PASSIVE_ID = "adattabilita"
CHOICE_SLOTS = ("Q", "W", "E")
# Passive delle forme evolute (per gli hook del Match e dei bot).
FORM_PASSIVES = {"assorbivolt", "fuocardore", "sincronismo", "mantelneve",
                 "fogliamanto", "forzainteriore", "incantevole", "idratazione"}
EEVEE_PASSIVES = FORM_PASSIVES | {PASSIVE_ID}

VOLTABSORB_CD = 40.0         # Assorbivolt: un assorbimento ogni 40s
FLASHFIRE_MULT = 1.3         # Fuocardore: +30% alle mosse Fuoco...
FLASHFIRE_DUR = 4.0          # ...per 4s dopo aver subito una mossa Fuoco nemica
SNOWCLOAK_MULT = 0.9         # Mantelneve: -10% agli attacchi base nemici
LEAFGUARD_MULT = 0.9         # Fogliamanto: stati -10% col Sole
INNERFOCUS_MULT = 0.7        # Forza Interiore: controlli -30%
CUTECHARM_CHANCE = 0.25      # Incantevole: 25% su chi colpisce in corpo a corpo
CUTECHARM_DUR = 1.0
MELEE_REACH = 2.2            # gittata d'attacco base sotto cui si è "in corpo a corpo"
HYDRATION_EVERY = 3.0        # Idratazione: pulizia degli stati ogni 3s sotto la pioggia
FREEZE_HOLD = 1.5            # Bora: congela chi è dentro da almeno 1,5s alla fine


# --- helper puri (usati anche dall'interfaccia) -------------------------------
def chosen_index(p, slot):
    """Indice del potenziamento scelto per lo slot (None = non ancora scelto)."""
    ms = p.moveset.get(slot)
    if ms is None or ms.chosen is None or ms.chosen is ms.base:
        return None
    try:
        return ms.upgrades.index(ms.chosen)
    except ValueError:
        return None


def eevee_forms(p) -> list:
    """Le 8 forme evolute (voci di evoluzione con requires.choices)."""
    return [st for st in p.evolutions if st.get("requires", {}).get("choices")]


def eevee_candidates(p, extra: dict | None = None) -> list:
    """Forme ancora raggiungibili con le scelte fatte; `extra` = {slot: indice}
    ipotetico (anteprima di un'opzione nel menu di scelta)."""
    picks = {sl: chosen_index(p, sl) for sl in CHOICE_SLOTS}
    if extra:
        picks.update(extra)
    out = []
    for st in eevee_forms(p):
        need = st["requires"]["choices"]
        if all(picks[sl] is None or picks[sl] == need.get(sl) for sl in CHOICE_SLOTS):
            out.append(st)
    return out


class EeveeMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(EEVEE_PASSIVES),
        "init": "_init_eevee",
        "update": "_update_eevee",
        "precheck": "_eevee_precheck",
        "cast": "_eevee_cast",
        "bot_cast": "_bot_eevee_cast",
        # Rete (net/visual.py, game/online_world.py): cosa passa al client.
        "net": {
            "lists": {"thunders": "c", "blizzards": "c", "future_sights": "c", "swift_stars": "pos"},
            "moving": ("swift_stars",),
            "me": ("voltabsorb_ready_at", "flashfire_until"),
        },
    }

    def _init_eevee(self) -> None:
        self.wishes: list[dict] = []        # Desiderio: cura ritardata
        self.swift_stars: list[dict] = []   # Comete: stelle che inseguono
        self.thunders: list[dict] = []      # Tuono: fulmini in sequenza
        self.blizzards: list[dict] = []     # Bora: zona di gelo crescente
        self.future_sights: list[dict] = [] # Divinazione: esplosione ritardata

    # --- bersagli -------------------------------------------------------------
    def _eevee_foes(self, team, c, r, structures=True):
        kinds = (Pokemon, Minion, Wild, Structure) if structures else (Pokemon, Minion, Wild)
        for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
            if e.team == team or not getattr(e, "alive", False) or not isinstance(e, kinds):
                continue
            if isinstance(e, Pokemon) and (e.is_decoy or e.untargetable_until > self.time):
                continue
            if c.dist(e.pos) <= r + getattr(e, "radius", 0.0):
                yield e

    def _swift_target(self, p, mv, near=None):
        """Comete: il nemico VISIBILE più vicino entro la gittata."""
        c = near or p.pos
        best, bd = None, 1e9
        for e in self._eevee_foes(p.team, c, mv.range, structures=False):
            if isinstance(e, Pokemon) and not self.vision.is_enemy_visible(p.team, e.id):
                continue
            d = c.dist(e.pos)
            if d < bd:
                best, bd = e, d
        return best

    def _eevee_precheck(self, p, mv, tgt) -> bool:
        """Comete senza nessun nemico a tiro: la mossa non parte e la ricarica
        non si spende."""
        if mv.shape == "swift":
            return self._swift_target(p, mv) is not None
        return True

    # --- dispatcher -----------------------------------------------------------
    def _eevee_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"wish": self._cast_wish, "swift": self._cast_swift,
              "endure": self._cast_endure, "thunder": self._cast_thunder,
              "blizzard": self._cast_blizzard, "moonlight": self._cast_moonlight,
              "gleam": self._cast_gleam, "acidarmor": self._cast_acidarmor,
              "futuresight": self._cast_futuresight}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    def _aim_point(self, origin, tgt, rng):
        to = tgt - origin
        if to.length() <= rng or to.length() < 1e-6:
            return Vec2(tgt.x, tgt.y)
        return origin + to.normalized() * rng

    # --- Q: Desiderio ---------------------------------------------------------
    def _cast_wish(self, p, mv, rank, origin, tgt, dirv):
        """Desiderio: dopo 2s cura l'alleato più vicino al punto mirato (entro
        gittata), altrimenti Eevee stesso."""
        who, bd = p, float(mv.effects.get("pick", 2.0))
        for a in self.world.pokemons():
            if (a is p or a.team != p.team or not a.alive or a.is_decoy
                    or origin.dist(a.pos) > mv.range + a.radius):
                continue
            d = tgt.dist(a.pos)
            if d < bd:
                who, bd = a, d
        delay = float(mv.effects.get("delay", 2.0))
        base_heal = self._rank_val(mv.effects.get("heal", []), rank)
        stat = (max(p.eff_attack(), p.eff_sp_attack()) if mv.effects.get("heal_stat") == "best"
                else p.eff_sp_attack())
        base_heal += float(mv.effects.get("heal_scaling", 0.0)) * stat
        amt = base_heal * p.heal_power
        amt += p.max_hp * float(mv.effects.get("heal_maxhp", 0.0))
        self.wishes.append({"caster_id": p.id, "target_id": who.id, "start": self.time,
                            "at": self.time + delay, "amount": amt})
        self.fx_events.append({"kind": "wishcast", "c": (who.pos.x, who.pos.y),
                               "mtype": mv.type, "fx": "wishcast"})

    # --- W: Comete ------------------------------------------------------------
    def _cast_swift(self, p, mv, rank, origin, tgt, dirv):
        """Comete: 3 stelle che partono a ventaglio e inseguono il nemico più
        vicino entro la gittata (non mancano mai; i muri non le fermano)."""
        target = self._swift_target(p, mv)
        if target is None:
            return
        n = int(mv.effects.get("count", 3))
        base = math.atan2(target.pos.y - origin.y, target.pos.x - origin.x)
        for k in range(n):
            a = base + (k - (n - 1) / 2) * 0.7
            self.swift_stars.append({
                "pos": Vec2(origin.x, origin.y), "dir": Vec2(math.cos(a), math.sin(a)),
                "start": self.time + k * 0.09, "born": self.time, "speed": mv.speed,
                "target_id": target.id, "caster_id": p.id, "team": p.team,
                "mv": mv, "rank": rank, "mtype": mv.type, "spin": random.random() * math.tau})
        self.fx_events.append({"eid": p.id, "anim": "Shoot"})

    def _update_swift(self, dt):
        alive = []
        for st in self.swift_stars:
            caster = self.world.get(st["caster_id"])
            if caster is None:
                continue
            if self.time < st["start"]:          # non ancora partita: segue Eevee
                st["pos"] = Vec2(caster.pos.x, caster.pos.y)
                alive.append(st)
                continue
            if self.time - st["born"] > 2.5:      # vita massima
                continue
            tgt = self.world.get(st["target_id"])
            if tgt is None or not getattr(tgt, "alive", False):
                tgt = self._swift_target(caster, st["mv"], near=st["pos"])
                if tgt is None:
                    continue
                st["target_id"] = tgt.id
            to = tgt.pos - st["pos"]
            dist = to.length()
            if dist <= getattr(tgt, "radius", 0.3) + 0.25:
                self._hit(caster, st["mv"], st["rank"], tgt)
                self.fx_events.append({"kind": "starhit", "c": (tgt.pos.x, tgt.pos.y),
                                       "mtype": st["mtype"], "fx": "starhit"})
                continue
            # Sterzata: il vettore direzione ruota verso il bersaglio.
            want = to * (1.0 / max(dist, 1e-6))
            k = min(1.0, 9.0 * dt)
            nd = st["dir"] * (1.0 - k) + want * k
            st["dir"] = nd.normalized() if nd.length() > 1e-6 else want
            step = min(dist, st["speed"] * dt)
            st["pos"] = st["pos"] + st["dir"] * step
            st["spin"] += dt * 12.0
            alive.append(st)
        self.swift_stars = alive

    # --- E: Resistenza --------------------------------------------------------
    def _cast_endure(self, p, mv, rank, origin, tgt, dirv):
        dur = float(mv.effects.get("duration", 2.0))
        p.endure_until = self.time + dur
        self.fx_events.append({"kind": "endure", "c": (p.pos.x, p.pos.y), "eid": p.id,
                               "mtype": mv.type, "fx": "endure", "dur": dur})

    # --- R Jolteon: Tuono -----------------------------------------------------
    def _cast_thunder(self, p, mv, rank, origin, tgt, dirv):
        c = self._aim_point(origin, tgt, mv.range)
        e = mv.effects
        self.thunders.append({
            "c": c, "radius": mv.radius, "end": self.time + float(e.get("duration", 2.0)),
            "next": self.time + 0.15, "interval": float(e.get("interval", 0.16)),
            "strike": float(e.get("strike_radius", 1.1)), "caster_id": p.id,
            "team": p.team, "mv": mv, "rank": rank, "mtype": mv.type, "start": self.time})
        self.fx_events.append({"kind": "zone", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": "thundercloud"})

    def _update_thunders(self, dt):
        alive = []
        for th in self.thunders:
            caster = self.world.get(th["caster_id"])
            if caster is None or self.time >= th["end"]:
                continue
            while self.time >= th["next"] and th["next"] < th["end"]:
                th["next"] += th["interval"]
                a = random.uniform(0, math.tau)
                r = th["radius"] * math.sqrt(random.random())
                pt = th["c"] + Vec2(math.cos(a) * r, math.sin(a) * r)
                for e in list(self._eevee_foes(th["team"], pt, th["strike"])):
                    self._hit(caster, th["mv"], th["rank"], e)
                self.fx_events.append({"kind": "thunderstrike", "c": (pt.x, pt.y),
                                       "radius": th["strike"], "mtype": th["mtype"],
                                       "fx": "thunderstrike"})
            alive.append(th)
        self.thunders = alive

    # --- R Glaceon: Bora ------------------------------------------------------
    def _cast_blizzard(self, p, mv, rank, origin, tgt, dirv):
        c = self._aim_point(origin, tgt, mv.range)
        e = mv.effects
        dur = float(e.get("duration", 3.0))
        self.blizzards.append({
            "c": c, "radius": mv.radius, "start": self.time, "end": self.time + dur,
            "next": self.time, "interval": float(e.get("interval", 0.25)),
            "caster_id": p.id, "team": p.team, "mv": mv, "rank": rank,
            "mtype": mv.type, "since": {}, "freeze": float(e.get("freeze_time", 1.0)),
            "ticks": max(1, int(dur / float(e.get("interval", 0.25))))})
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": "blizzardcast"})

    def _update_blizzards(self, dt):
        alive = []
        for bz in self.blizzards:
            caster = self.world.get(bz["caster_id"])
            if caster is None:
                continue
            span = max(1e-6, bz["end"] - bz["start"])
            if self.time >= bz["end"]:
                # Fine: chi è rimasto dentro abbastanza a lungo viene congelato.
                inside = {e.id: e for e in self._eevee_foes(bz["team"], bz["c"], bz["radius"],
                                                            structures=False)}
                for eid, t0 in bz["since"].items():
                    e = inside.get(eid)
                    if isinstance(e, Pokemon) and bz["end"] - t0 >= FREEZE_HOLD:
                        self._apply_freeze(e, bz["freeze"])
                        self.fx_events.append({"kind": "freeze", "c": (e.pos.x, e.pos.y),
                                               "mtype": "Ice", "fx": "freeze"})
                continue
            if self.time >= bz["next"]:
                bz["next"] += bz["interval"]
                prog = (self.time - bz["start"]) / span
                slow = max(0.15, 0.8 - 0.65 * prog)      # rallenta sempre di più
                seen = set()
                for e in self._eevee_foes(bz["team"], bz["c"], bz["radius"], structures=False):
                    seen.add(e.id)
                    bz["since"].setdefault(e.id, self.time)
                    self._hit(caster, bz["mv"], bz["rank"], e)   # danno in JSON PER COLPO
                    if isinstance(e, Pokemon):
                        self._apply_slow(e, slow, bz["interval"] + 0.15)
                for eid in [k for k in bz["since"] if k not in seen]:
                    del bz["since"][eid]                 # uscito: si riparte da zero
            alive.append(bz)
        self.blizzards = alive

    # --- R Espeon: Divinazione ------------------------------------------------
    def _cast_futuresight(self, p, mv, rank, origin, tgt, dirv):
        c = self._aim_point(origin, tgt, mv.range)
        delay = float(mv.effects.get("delay", 2.0))
        self.future_sights.append({"c": c, "radius": mv.radius, "start": self.time,
                                   "at": self.time + delay, "caster_id": p.id,
                                   "team": p.team, "mv": mv, "rank": rank})
        self.fx_events.append({"kind": "futuremark", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": "futuremark"})

    def _update_future_sights(self, dt):
        alive = []
        for fs in self.future_sights:
            if self.time < fs["at"]:
                alive.append(fs)
                continue
            caster = self.world.get(fs["caster_id"])
            if caster is not None:
                for e in list(self._eevee_foes(fs["team"], fs["c"], fs["radius"])):
                    self._hit(caster, fs["mv"], fs["rank"], e)
            self.fx_events.append({"kind": "area", "c": (fs["c"].x, fs["c"].y),
                                   "radius": fs["radius"], "mtype": "Psychic",
                                   "fx": "futureblast"})
        self.future_sights = alive

    # --- R Umbreon: Lucelunare ------------------------------------------------
    def _cast_moonlight(self, p, mv, rank, origin, tgt, dirv):
        frac = self._rank_val(mv.effects.get("missing_frac", [0.4]), rank)
        self._give_heal(p, p, (p.max_hp - p.hp) * frac * p.heal_power)
        self._cleanse(p)
        self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "radius": 1.6,
                               "mtype": mv.type, "fx": "moonlight"})

    # --- R Sylveon: Magibrillio -----------------------------------------------
    def _cast_gleam(self, p, mv, rank, origin, tgt, dirv):
        for e in list(self._eevee_foes(p.team, origin, mv.radius)):
            self._hit(p, mv, rank, e)
        heal = (self._rank_val(mv.effects.get("heal", []), rank)
                + float(mv.effects.get("heal_scaling", 0.0)) * p.eff_sp_attack()) * p.heal_power
        for a in self.world.pokemons():
            if (a.team == p.team and a.alive and not a.is_decoy
                    and origin.dist(a.pos) <= mv.radius + a.radius):
                self._give_heal(p, a, heal)
        self.fx_events.append({"kind": "area", "c": (origin.x, origin.y),
                               "radius": mv.radius, "mtype": mv.type, "fx": "gleam"})

    # --- R Vaporeon: Acidarmatura ---------------------------------------------
    def _cast_acidarmor(self, p, mv, rank, origin, tgt, dirv):
        e = mv.effects
        dur = float(e.get("duration", 2.0))
        p.puddle_until = self.time + dur
        p.puddle_heal = (self._rank_val(e.get("heal_frac", [0.2]), rank)
                         * p.max_hp * p.heal_power / dur)
        p.aa_active = False
        p.target_id = None
        self._apply_untargetable(p, dur)
        self._apply_speed(p, float(e.get("speed", 0.55)), dur)   # si muove lentamente
        self.fx_events.append({"kind": "area", "c": (p.pos.x, p.pos.y), "radius": 1.2,
                               "mtype": mv.type, "fx": "acidarmor"})

    # --- stati ----------------------------------------------------------------
    def _apply_freeze(self, p, dur):
        """Congelato: come lo stordimento (né movimento né azioni) ma con il suo
        stato e il blocco di ghiaccio visibile."""
        if self._cc_immune(p):
            return
        dur = self._tenacity_dur(p, dur)
        p.frozen_until = max(p.frozen_until, self.time + dur)
        p.stop()

    def _apply_charm(self, p, src, dur):
        """Affascinato: cammina verso `src` senza poter attaccare né lanciare."""
        if self._cc_immune(p) or not isinstance(p, Pokemon):
            return
        dur = self._tenacity_dur(p, dur)
        p.charm_until = max(p.charm_until, self.time + dur)
        p.charm_src = src.id
        p.aa_active = False
        self.fx_events.append({"kind": "charm", "c": (p.pos.x, p.pos.y), "mtype": "Fairy",
                               "fx": "charm"})

    def _apply_blind(self, p, dur):
        """Turbosabbia: gli attacchi base del bersaglio mancano."""
        if self._cc_immune(p):
            return
        p.blind_until = max(p.blind_until, self.time + self._tenacity_dur(p, dur))

    def _charmed(self, p, dt) -> None:
        src = self.world.get(p.charm_src) if p.charm_src is not None else None
        p.target_id = None
        p.aa_active = False
        if src is None or not getattr(src, "alive", False):
            p.charm_until = -1.0
            p.stop()
            return
        if p.pos.dist(src.pos) > p.radius + src.radius + 0.3:
            self._move_towards(p, src.pos, dt, use_astar=False)
        else:
            p.stop()

    def _cleanse(self, p) -> None:
        """Rimuove tutti gli stati alterati (Lucelunare, Idratazione)."""
        for attr in ("slow_until", "stun_until", "frozen_until", "sleep_until", "root_until",
                     "poison_until", "confuse_until", "silence_until", "fear_until",
                     "charm_until", "blind_until", "def_debuff_until", "spdef_debuff_until",
                     "atk_debuff_until", "burn_until", "dashlock_until",
                     "memento_weak_until", "spite_until", "curse_until", "taunt_until",
                     "ember_until", "aspd_slow_until"):
            setattr(p, attr, -1.0)
        p.sleep_arm_at = -1.0
        p.slow_mult = 1.0
        p.heat_stacks = 0

    def _eevee_status_count(self, p) -> bool:
        t = self.time
        return (p.slow_until > t or p.stun_until > t or p.frozen_until > t
                or p.sleep_until > t or p.root_until > t or p.poison_until > t
                or p.confuse_until > t or p.silence_until > t or p.fear_until > t
                or p.charm_until > t or p.blind_until > t or p.burn_until > t
                or p.def_debuff_until > t or p.spdef_debuff_until > t
                or p.atk_debuff_until > t or p.taunt_until > t)

    # --- hook del Match --------------------------------------------------------
    def _eevee_absorb(self, attacker, target, amount, dmg_type) -> bool:
        """Prima del danno. Assorbivolt: la mossa Elettro nemica cura (poi 40s di
        ricarica). Fuocardore: una mossa Fuoco nemica accende il potenziamento.
        Ritorna True se il danno è stato assorbito."""
        if not isinstance(target, Pokemon) or amount <= 0.0 or attacker is None:
            return False
        if getattr(attacker, "team", target.team) == target.team:
            return False
        if (target.passive_id == "assorbivolt" and dmg_type == "Electric"
                and self.time >= target.voltabsorb_ready_at):
            target.hp = min(target.max_hp, target.hp + amount)
            target.voltabsorb_ready_at = self.time + VOLTABSORB_CD
            self.fx_events.append({"kind": "absorb", "c": (target.pos.x, target.pos.y),
                                   "mtype": "Electric", "fx": "voltabsorb"})
            return True
        if target.passive_id == "fuocardore" and dmg_type == "Fire":
            if target.flashfire_until <= self.time:
                self.fx_events.append({"kind": "absorb", "c": (target.pos.x, target.pos.y),
                                       "mtype": "Fire", "fx": "flashfire"})
            target.flashfire_until = self.time + FLASHFIRE_DUR
        return False

    def _eevee_cc_mult(self, p) -> float:
        """Durata dei controlli: Forza Interiore -30%, Fogliamanto -10% col Sole."""
        if not isinstance(p, Pokemon):
            return 1.0
        if p.passive_id == "forzainteriore":
            return INNERFOCUS_MULT
        if p.passive_id == "fogliamanto" and self.jungle.weather == "sun":
            return LEAFGUARD_MULT
        return 1.0

    def _cute_charm(self, attacker, target) -> None:
        """Incantevole: chi colpisce Sylveon in corpo a corpo può restare affascinato."""
        if (isinstance(target, Pokemon) and target.passive_id == "incantevole"
                and isinstance(attacker, Pokemon) and attacker.team != target.team
                and attacker.attack_range <= MELEE_REACH and attacker.alive
                and random.random() < CUTECHARM_CHANCE):
            self._apply_charm(attacker, target, CUTECHARM_DUR)

    # --- aggiornamento --------------------------------------------------------
    def _update_eevee(self, dt: float) -> None:
        # Desiderio: la stella cade e cura.
        pend = []
        for w in self.wishes:
            if self.time < w["at"]:
                pend.append(w)
                continue
            tgt = self.world.get(w["target_id"])
            caster = self.world.get(w["caster_id"])
            if tgt is not None and tgt.alive:
                self._give_heal(caster or tgt, tgt, w["amount"])
                self.fx_events.append({"kind": "wishheal", "c": (tgt.pos.x, tgt.pos.y),
                                       "mtype": "Normal", "fx": "wishheal"})
        self.wishes = pend
        self._update_swift(dt)
        self._update_thunders(dt)
        self._update_blizzards(dt)
        self._update_future_sights(dt)
        for p in self.world.pokemons():
            if not p.alive:
                continue
            if p.puddle_until > self.time:               # Acidarmatura: cura nel tempo
                p.hp = min(p.max_hp, p.hp + p.puddle_heal * dt)
            if (p.passive_id == "idratazione" and self.time >= p.hydration_next
                    and self._in_rain(p) and self._eevee_status_count(p)):
                self._cleanse(p)
                p.hydration_next = self.time + HYDRATION_EVERY
                self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y),
                                       "radius": 1.0, "mtype": "Water", "fx": "hydration"})

    # --- bot ------------------------------------------------------------------
    def _bot_eevee_cast(self, p, target) -> bool:
        """Mosse di supporto/area che il bot generico non userebbe (potenza 0 o
        centrate su di sé)."""
        hp = p.hp / max(1.0, p.max_hp)
        d = p.pos.dist(target.pos)
        for slot in ("R", "Q", "W", "E"):
            ms = p.moveset.get(slot)
            if not (ms and ms.ready and ms.chosen):
                continue
            mv = ms.chosen
            sh = mv.shape
            at = (p.pos.x, p.pos.y)
            if sh in ("wish", "moonlight") and hp < 0.6:
                pass
            elif sh == "endure" and hp < 0.35:
                pass
            elif sh == "acidarmor" and hp < 0.4:
                pass
            elif sh == "gleam" and d <= mv.radius:
                pass
            elif sh == "area" and mv.power_at(ms.rank) <= 0 and d <= mv.radius:
                pass   # Colpocoda
            elif sh == "swift" and d <= mv.range:
                at = (target.pos.x, target.pos.y)
            elif sh in ("thunder", "blizzard", "futuresight") and d <= mv.range:
                at = (target.pos.x, target.pos.y)
            else:
                continue
            p.pending_cast = (slot, at[0], at[1])
            return True
        return False
