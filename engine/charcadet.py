"""Regole della linea Charcadet > Armarouge / Ceruledge.

Puro: nessun pygame. Mixin di Match (engine/match.py) come Eevee, Spiritomb e
Corviknight: usa lo stesso stato (self.time, self.world, self.fx_events,
_combat_hash, gli _apply_*). Il client legge le liste del Match (shades,
smogs, cannon_charges, psy_zones, flurries) e i campi delle unità
(floatarmor_until, armor_blocks, shadowclaw_until, calm_until) per disegnare.

Passive:
  - Armature (Charcadet): Armatura Fausta si riempie col danno SUBITO dai
    Pokémon nemici, Armatura Infausta col danno INFLITTO ai Pokémon nemici
    (minion, neutrali e torri non contano). Al liv.8 decide la forma
    (evolution._requires_met, {"armature": "fausta"}): Fausta più alta ->
    Armarouge, altrimenti (parità compresa) Ceruledge.
  - Guardia (Armarouge): quando un alleato entro 6 tile scende sotto il 30%
    degli HP riceve uno scudo (30 s di ricarica).
  - Doppia Lama (Ceruledge): ogni attacco base colpisce due volte; il secondo
    colpo fa metà danno ed è di tipo Spettro.
"""
from __future__ import annotations

import random

from .entities import Minion, Pokemon, Structure, Wild
from .vec import Vec2

ARMATURE_ID = "armature"
GUARD_ID = "guardia"
DOUBLE_ID = "doppialama"
CHARCADET_PASSIVES = {ARMATURE_ID, GUARD_ID, DOUBLE_ID}

GUARD_RANGE = 6.0             # Guardia: raggio degli alleati protetti
GUARD_HP_FRAC = 0.30          # sotto questa frazione di HP scatta lo scudo
GUARD_CD = 30.0
GUARD_DUR = 3.0
DOUBLE_DELAY = 0.15           # Doppia Lama: il secondo colpo arriva poco dopo
DOUBLE_MULT = 0.5
SHADE_PICK = 2.0              # Ombra Notturna: raggio di ricerca attorno al mirino
BURN_HP_FRAC = 0.025          # scottatura: 2,5% degli HP max al secondo


class CharcadetMixin:
    def _init_charcadet(self) -> None:
        self.shades: list[dict] = []          # Ombra Notturna: ombre in viaggio a terra
        self.smogs: list[dict] = []           # Pulifumo: nubi a tempo
        self.cannon_charges: list[dict] = []  # Armor Cannon: carica di 0,5 s
        self.psy_zones: list[dict] = []       # Psichico: area che scatta dopo 0,5 s
        self.flurries: list[dict] = []        # Lama dei Rancori: raffica di fendenti
        self.double_hits: list[dict] = []     # Doppia Lama: secondi colpi in arrivo

    # --- dispatcher -----------------------------------------------------------
    def _charcadet_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"nightshade": self._cast_nightshade, "clearsmog": self._cast_clearsmog,
              "armorcannon": self._cast_armorcannon, "floatarmor": self._cast_floatarmor,
              "psychic": self._cast_psychic, "grudgeblade": self._cast_grudgeblade,
              "shadowclaw": self._cast_shadowclaw}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    def _charcadet_precheck(self, p, mv, tgt) -> bool:
        """Ombra Notturna e Lama dei Rancori senza un nemico valido non partono
        (la ricarica non si spende)."""
        if mv.shape == "nightshade":
            return self._shade_target(p, mv, tgt) is not None
        if mv.shape == "grudgeblade":
            return self._flurry_target(p, mv, tgt) is not None
        return True

    def _charc_point(self, origin, tgt, rng):
        to = tgt - origin
        if to.length() <= rng or to.length() < 1e-6:
            return Vec2(tgt.x, tgt.y)
        return origin + to.normalized() * rng

    def _foe_near(self, p, c, reach, pokemon_only=False):
        """Il nemico vivo e bersagliabile più vicino a `c` entro `reach`."""
        best, bd = None, 1e9
        kinds = (Pokemon,) if pokemon_only else (Pokemon, Minion, Wild)
        for e in self._combat_hash.query_radius(c.x, c.y, reach + 1.0):
            if e.team == p.team or not getattr(e, "alive", False) or not isinstance(e, kinds):
                continue
            if isinstance(e, Pokemon) and (e.untargetable_until > self.time or e.is_decoy
                                           or e.invisible):
                continue
            d = c.dist(e.pos) - getattr(e, "radius", 0.0)
            if d <= reach and d < bd:
                best, bd = e, d
        return best

    # --- W: Ombra Notturna ----------------------------------------------------
    def _shade_target(self, p, mv, tgt):
        c = self._charc_point(p.pos, tgt, mv.range)
        e = self._foe_near(p, c, SHADE_PICK)
        if e is None or p.pos.dist(e.pos) > mv.range + 1.5:
            return None
        return e

    def _cast_nightshade(self, p, mv, rank, origin, tgt, dirv):
        """Un'ombra scivola a terra fino al bersaglio e lo colpisce con danno
        PURO (base + livello × grado): ignora Difesa e Dif. Sp."""
        e = self._shade_target(p, mv, tgt)
        if e is None:
            return
        per = self._rank_val(mv.effects.get("per_level", [10]), rank)
        dmg = mv.power_at(rank) + per * p.level
        self.shades.append({"pos": Vec2(origin.x, origin.y), "target_id": e.id,
                            "team": p.team, "caster_id": p.id, "dmg": dmg,
                            "speed": mv.speed, "start": self.time, "mtype": mv.type})
        self.fx_events.append({"kind": "area", "c": (origin.x, origin.y), "radius": 0.8,
                               "mtype": mv.type})

    def _update_shades(self, dt: float) -> None:
        keep = []
        for sh in self.shades:
            t = self.world.get(sh["target_id"])
            if (t is None or not getattr(t, "alive", False)
                    or (isinstance(t, Pokemon) and t.untargetable_until > self.time)):
                continue   # bersaglio sparito: l'ombra si dissolve
            to = t.pos - sh["pos"]
            step = sh["speed"] * dt
            if to.length() > step + 0.3:
                sh["dir"] = to.normalized()
                sh["pos"] = sh["pos"] + sh["dir"] * step
                keep.append(sh)
                continue
            caster = self.world.get(sh["caster_id"])
            if caster is not None:
                self._deal_damage(caster, t, sh["dmg"], dmg_type=sh["mtype"])
            self.fx_events.append({"kind": "area", "c": (t.pos.x, t.pos.y), "radius": 0.9,
                                   "mtype": sh["mtype"], "fx": "nightshadehit"})
        self.shades = keep

    # --- W: Pulifumo ----------------------------------------------------------
    def _cast_clearsmog(self, p, mv, rank, origin, tgt, dirv):
        """Nube a distanza: per `duration` i nemici dentro perdono ogni bonus
        temporaneo alle statistiche (Attacco, Difesa, Velocità, Calmamente)."""
        c = self._charc_point(origin, tgt, mv.range)
        dur = float(mv.effects.get("duration", 3.0))
        self.smogs.append({"c": c, "radius": mv.radius, "team": p.team,
                           "start": self.time, "end": self.time + dur})
        self.fx_events.append({"kind": "zone", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type})

    def _purge_buffs(self, q) -> bool:
        now = self.time
        out = False
        if q.atk_until > now and q.atk_mult > 1.0:
            q.atk_mult, q.atk_until = 1.0, now
            out = True
        if q.def_buff_until > now and q.def_buff_mult > 1.0:
            q.def_buff_mult, q.def_buff_until = 1.0, now
            q.def_buff_active = False
            out = True
        if q.speed_until > now and q.speed_mult > 1.0:
            q.speed_mult, q.speed_until = 1.0, now
            out = True
        if q.fc_stacks > 0 and q.fc_until > now:   # cariche di Nitrocarica
            q.fc_stacks, q.fc_until = 0, now
            out = True
        if q.calm_until > now:
            q.calm_until = now
            q.calm_active = False
            out = True
        return out

    def _update_smogs(self) -> None:
        now = self.time
        self.smogs = [s for s in self.smogs if s["end"] > now]
        for s in self.smogs:
            for q in self.world.pokemons():
                if q.team == s["team"] or not q.alive:
                    continue
                if q.pos.dist(s["c"]) <= s["radius"] + q.radius and self._purge_buffs(q):
                    self.fx_events.append({"kind": "buff", "c": (q.pos.x, q.pos.y),
                                           "mtype": "Poison", "fx": "purged"})

    # --- E: Calmamente --------------------------------------------------------
    def _apply_calm(self, p, mult, dur) -> None:
        p.calm_mult = mult
        p.calm_until = self.time + dur
        p.calm_active = True

    def _calm_mult(self, p) -> float:
        return p.calm_mult if getattr(p, "calm_until", -1.0) > self.time else 1.0

    # --- Q: Bruciatutto (rompe gli scudi) e scottatura di Lavasbuffo ----------
    def _shield_break(self, target, fx) -> None:
        frac = fx.get("shield_break")
        if (frac and isinstance(target, Pokemon) and target.shield > 0.0
                and target.shield_until > self.time):
            target.shield *= max(0.0, 1.0 - float(frac))
            self.fx_events.append({"kind": "area", "c": (target.pos.x, target.pos.y),
                                   "radius": 0.8, "mtype": "Fire", "fx": "shieldbreak"})

    def _apply_burn(self, caster, target, dur) -> None:
        if self._cc_immune(target) or self._flor_status_immune(target):
            return
        target.burn_until = max(target.burn_until, self.time + dur)
        target.burn_dps = max(target.burn_dps, BURN_HP_FRAC * target.max_hp)
        target.burn_src = caster.id
        self.fx_events.append({"kind": "area", "c": (target.pos.x, target.pos.y),
                               "radius": 0.7, "mtype": "Fire", "fx": "burned"})

    def _charcadet_hit_effects(self, caster, target, fx) -> None:
        bu = fx.get("burn")
        if bu and isinstance(caster, Pokemon) and random.random() < float(bu.get("chance", 1.0)):
            self._apply_burn(caster, target, float(bu.get("duration", 3.0)))

    # --- Armarouge: Armor Cannon ----------------------------------------------
    def _cast_armorcannon(self, p, mv, rank, origin, tgt, dirv):
        """Breve carica (0,5 s, fermo), poi una palla di fuoco a lunga gittata.
        Al tiro Armarouge resta scoperto: Difesa e Dif. Sp. -20% per 4 s."""
        ch = float(mv.effects.get("charge", 0.5))
        p.stop()
        p.channel_until = self.time + ch
        p.root_until = max(p.root_until, self.time + ch)
        self.cannon_charges.append({"pos": Vec2(origin.x, origin.y), "dir": Vec2(dirv.x, dirv.y),
                                    "caster_id": p.id, "team": p.team, "mv": mv, "rank": rank,
                                    "range": mv.range, "start": self.time, "end": self.time + ch})

    def _update_cannons(self) -> None:
        keep = []
        for cc in self.cannon_charges:
            p = self.world.get(cc["caster_id"])
            if p is None or not p.alive or self._immobile(p) or p.silence_until > self.time:
                if p is not None:
                    p.channel_until = p.root_until = self.time
                continue   # interrotto
            cc["pos"] = Vec2(p.pos.x, p.pos.y)
            if self.time < cc["end"]:
                keep.append(cc)
                continue
            mv, d = cc["mv"], cc["dir"]
            start = p.pos + d * 0.5
            self.projectiles.append({
                "pos": start, "dir": Vec2(d.x, d.y), "speed": mv.speed, "left": mv.range,
                "radius": mv.radius, "team": p.team, "caster_id": p.id, "mv": mv,
                "rank": cc["rank"], "mtype": mv.type, "burst": 0.0, "fx": mv.fx})
            sd = mv.effects.get("self_down", {})
            m, dur = float(sd.get("mult", 0.8)), float(sd.get("duration", 4.0))
            self._apply_def_debuff(p, 0.0, dur, m)
            self._apply_spdef_debuff(p, 0.0, dur, m)
            self.fx_events.append({"kind": "projectile", "a": (p.pos.x, p.pos.y),
                                   "b": (start.x + d.x, start.y + d.y), "mtype": mv.type,
                                   "fx": "armorcannonfire"})
        self.cannon_charges = keep

    # --- Armarouge: Armatura Fluttuante ---------------------------------------
    def _cast_floatarmor(self, p, mv, rank, origin, tgt, dirv):
        """Per `duration` gli spallacci orbitano e intercettano fino a `blocks`
        proiettili nemici; alla fine esplodono attorno ad Armarouge."""
        eff = mv.effects
        p.floatarmor_until = self.time + float(eff.get("duration", 5.0))
        p.armor_blocks = int(eff.get("blocks", 3))
        p.floatarmor_mv = (mv, rank)
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "mtype": mv.type,
                               "radius": 1.2})

    def _update_floatarmor(self) -> None:
        now = self.time
        for p in self.world.pokemons():
            if p.floatarmor_until < 0.0:
                continue
            if not p.alive:
                p.floatarmor_until, p.armor_blocks = -1.0, 0
                continue
            mv, rank = p.floatarmor_mv
            if now < p.floatarmor_until:
                if p.armor_blocks > 0:
                    self._armor_intercept(p, float(mv.effects.get("guard_radius", 1.7)))
                continue
            # Fine: gli spallacci esplodono.
            p.floatarmor_until, p.armor_blocks = -1.0, 0
            for e in self._combat_hash.query_radius(p.pos.x, p.pos.y, mv.radius + 1.0):
                if e.team == p.team or not getattr(e, "alive", False):
                    continue
                if (isinstance(e, (Pokemon, Minion, Wild))
                        and p.pos.dist(e.pos) <= mv.radius + e.radius):
                    self._hit(p, mv, rank, e)
            self.fx_events.append({"kind": "area", "c": (p.pos.x, p.pos.y), "radius": mv.radius,
                                   "mtype": mv.type, "fx": "floatarmorboom"})

    def _armor_intercept(self, p, rad) -> None:
        """Proiettili nemici (mosse in volo e Ombre Notturne) che arrivano su di lui."""
        def stop(pos):
            p.armor_blocks -= 1
            self.fx_events.append({"kind": "sync", "a": (p.pos.x, p.pos.y),
                                   "b": (pos.x, pos.y), "mtype": "Fire", "fx": "armorblock"})

        keep = []
        for pr in self.projectiles:
            if (p.armor_blocks > 0 and pr["team"] != p.team
                    and pr["pos"].dist(p.pos) <= rad + p.radius):
                stop(pr["pos"])
                continue
            keep.append(pr)
        self.projectiles = keep
        keep = []
        for sh in self.shades:
            if (p.armor_blocks > 0 and sh["team"] != p.team and sh["target_id"] == p.id
                    and sh["pos"].dist(p.pos) <= rad + p.radius):
                stop(sh["pos"])
                continue
            keep.append(sh)
        self.shades = keep

    # --- Armarouge: Psichico --------------------------------------------------
    def _cast_psychic(self, p, mv, rank, origin, tgt, dirv):
        c = self._charc_point(origin, tgt, mv.range)
        delay = float(mv.effects.get("delay", 0.5))
        self.psy_zones.append({"c": c, "radius": mv.radius, "team": p.team, "caster_id": p.id,
                               "mv": mv, "rank": rank, "start": self.time,
                               "end": self.time + delay})

    def _update_psy_zones(self) -> None:
        keep = []
        for z in self.psy_zones:
            if self.time < z["end"]:
                keep.append(z)
                continue
            p = self.world.get(z["caster_id"])
            c = z["c"]
            if p is not None:
                for e in self._combat_hash.query_radius(c.x, c.y, z["radius"] + 1.0):
                    if e.team == z["team"] or not getattr(e, "alive", False):
                        continue
                    if (isinstance(e, (Pokemon, Minion, Wild))
                            and c.dist(e.pos) <= z["radius"] + e.radius):
                        self._hit(p, z["mv"], z["rank"], e)
            self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": z["radius"],
                                   "mtype": "Psychic", "fx": "psychicburst"})
        self.psy_zones = keep

    # --- Ceruledge: Lama dei Rancori ------------------------------------------
    def _flurry_target(self, p, mv, tgt):
        c = self._charc_point(p.pos, tgt, mv.range)
        e = self._foe_near(p, c, SHADE_PICK, pokemon_only=True)
        if e is None or p.pos.dist(e.pos) > mv.range + e.radius:
            e = self._foe_near(p, c, SHADE_PICK)
        if e is None or p.pos.dist(e.pos) > mv.range + e.radius:
            return None
        return e

    def _cast_grudgeblade(self, p, mv, rank, origin, tgt, dirv):
        """Scatta sul nemico e lo colpisce con `hits` fendenti in `duration`;
        intanto non è bersagliabile e ogni fendente lo cura."""
        e = self._flurry_target(p, mv, tgt)
        if e is None:
            return
        dur = float(mv.effects.get("duration", 1.5))
        side = (origin - e.pos)
        side = side.normalized() if side.length() > 1e-6 else Vec2(-1.0, 0.0)
        off = side * (e.radius + p.radius + 0.15)
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                               "b": (e.pos.x + off.x, e.pos.y + off.y), "mtype": mv.type})
        p.pos = self._nearest_walkable(e.pos + off, e.pos)
        hits = int(mv.effects.get("hits", 6))
        self.flurries.append({"caster_id": p.id, "target_id": e.id, "team": p.team,
                              "mv": mv, "rank": rank, "start": self.time,
                              "end": self.time + dur, "hits": hits, "done": 0,
                              "off": off, "pos": Vec2(e.pos.x, e.pos.y)})
        self._flurry_hold(p, self.time + dur)

    def _flurry_hold(self, p, until) -> None:
        p.stop()
        p.aa_active = False
        p.channel_until = max(p.channel_until, until)
        p.root_until = max(p.root_until, until)
        p.untargetable_until = max(p.untargetable_until, until)

    def _update_flurries(self) -> None:
        now = self.time
        keep = []
        for fl in self.flurries:
            p = self.world.get(fl["caster_id"])
            t = self.world.get(fl["target_id"])
            ok_t = (t is not None and t.alive
                    and not (isinstance(t, Pokemon) and t.untargetable_until > now))
            if p is None or not p.alive or not ok_t:
                if p is not None:   # finisce prima: torna bersagliabile
                    p.channel_until = p.root_until = p.untargetable_until = now
                continue
            p.pos = self._nearest_walkable(t.pos + fl["off"], t.pos)   # gli resta addosso
            fl["pos"] = Vec2(t.pos.x, t.pos.y)
            span = fl["end"] - fl["start"]
            while fl["done"] < fl["hits"] and now >= fl["start"] + span * (fl["done"] + 0.5) / fl["hits"]:
                fl["done"] += 1
                before = t.hp + (t.shield if getattr(t, "shield_until", -1.0) > now else 0.0)
                self._hit(p, fl["mv"], fl["rank"], t)   # danno in JSON PER COLPO
                dealt = max(0.0, before - t.hp - (t.shield if getattr(t, "shield_until", -1.0) > now
                                                  else 0.0))
                heal = dealt * float(fl["mv"].effects.get("heal_ratio", 0.2))
                if heal > 0.0:
                    p.hp = min(p.max_hp, p.hp + heal * self._heal_in_mult(p))
                self.fx_events.append({"kind": "attack", "a": (p.pos.x, p.pos.y),
                                       "b": (t.pos.x, t.pos.y), "mtype": "Ghost",
                                       "melee": True, "fx": "grudgehit", "n": fl["done"]})
                if not t.alive:
                    break
            if now < fl["end"] and t.alive:
                keep.append(fl)
            else:
                p.channel_until = p.root_until = p.untargetable_until = now
        self.flurries = keep

    # --- Ceruledge: Ombrartigli e Doppia Lama ---------------------------------
    def _cast_shadowclaw(self, p, mv, rank, origin, tgt, dirv):
        p.shadowclaw_until = self.time + float(mv.effects.get("duration", 6.0))
        p.shadowclaw_mult = float(mv.effects.get("range_mult", 1.5))
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "mtype": mv.type,
                               "radius": 1.0})

    def _claws_on(self, u) -> bool:
        return isinstance(u, Pokemon) and u.shadowclaw_until > self.time

    def _claw_reach(self, u, r) -> float:
        return r * u.shadowclaw_mult if self._claws_on(u) else r

    def _aa_ghost_damage(self, u, tgt, mult=1.0, power=None) -> float:
        """Colpo base di tipo Spettro (secondo colpo di Doppia Lama, Ombrartigli):
        fisico, con efficacia del tipo; con Ombrartigli è sempre brutto colpo.
        `power`: Attacco fotografato al rilascio dell'attacco base."""
        power = (u.eff_attack() if power is None else power) * mult
        if isinstance(tgt, Pokemon):
            power *= self.types.moba_multiplier("Ghost", tgt.types)
            if tgt.passive_id == "mantelneve":
                power *= 0.9
        return self._mitigate_hit(u, tgt, power, magic=False, can_crit=True,
                                  crit_bonus=1.0 if self._claws_on(u) else 0.0)

    def _after_aa(self, u, tgt) -> None:
        """Dopo un attacco base a segno: Doppia Lama prepara il secondo colpo."""
        if u.passive_id == DOUBLE_ID:
            self.double_hits.append({"t": self.time + DOUBLE_DELAY, "caster_id": u.id,
                                     "target_id": tgt.id})

    def _update_double_hits(self) -> None:
        keep = []
        for dh in self.double_hits:
            if self.time < dh["t"]:
                keep.append(dh)
                continue
            u = self.world.get(dh["caster_id"])
            t = self.world.get(dh["target_id"])
            if (u is None or t is None or not u.alive or not getattr(t, "alive", False)
                    or u.pos.dist(t.pos) > self._auto_reach(u) + u.radius + getattr(t, "radius", 0.0) + 0.8):
                continue
            dmg = self._aa_ghost_damage(u, t, DOUBLE_MULT)
            self._deal_damage(u, t, dmg, dmg_type="Ghost")
            self._vamp(u, dmg, physical=True)
            self.fx_events.append({"kind": "attack", "a": (u.pos.x, u.pos.y),
                                   "b": (t.pos.x, t.pos.y), "mtype": "Ghost", "melee": True,
                                   "fx": "ghostslash"})
        self.double_hits = keep

    # --- passive --------------------------------------------------------------
    def _armature_track(self, attacker, target, amount) -> None:
        """Armature: conta il danno tra Charcadet e i Pokémon NEMICI."""
        if amount <= 0.0 or not isinstance(attacker, Pokemon) or not isinstance(target, Pokemon):
            return
        if attacker.team == target.team or target.is_decoy:
            return
        if target.passive_id == ARMATURE_ID:
            target.fausta += amount
        if attacker.passive_id == ARMATURE_ID:
            attacker.infausta += amount

    def _update_guard(self) -> None:
        now = self.time
        for p in self.world.pokemons():
            if p.passive_id != GUARD_ID or not p.alive or now < p.guard_ready_at:
                continue
            best = None
            for q in self.world.pokemons():
                if (q is p or q.team != p.team or not q.alive or q.is_decoy
                        or q.hp >= GUARD_HP_FRAC * q.max_hp or q.pos.dist(p.pos) > GUARD_RANGE):
                    continue
                if best is None or q.hp / q.max_hp < best.hp / best.max_hp:
                    best = q
            if best is None:
                continue
            amt = (60.0 + 12.0 * p.level + 0.3 * p.eff_sp_attack()) * p.heal_power
            self._give_shield(p, best, amt, GUARD_DUR)
            p.guard_ready_at = now + GUARD_CD
            self.fx_events.append({"kind": "sync", "a": (p.pos.x, p.pos.y),
                                   "b": (best.pos.x, best.pos.y), "mtype": "Fire",
                                   "fx": "guardshield"})

    def _update_charcadet(self, dt: float) -> None:
        now = self.time
        for p in self.world.pokemons():
            p.calm_active = p.calm_until > now
        if self.cannon_charges:
            self._update_cannons()
        if self.shades:
            self._update_shades(dt)
        if self.smogs:
            self._update_smogs()
        if self.psy_zones:
            self._update_psy_zones()
        if self.flurries:
            self._update_flurries()
        if self.double_hits:
            self._update_double_hits()
        self._update_floatarmor()
        self._update_guard()

    # --- bot ------------------------------------------------------------------
    def _bot_charcadet_cast(self, p, target) -> bool:
        """I bot usano anche le mosse senza danno: Calmamente/Danzaspada e
        Ombrartigli vicino al bersaglio, Pulifumo su di lui, Armatura Fluttuante
        quando sono in pericolo."""
        d = p.pos.dist(target.pos)
        for slot in ("R", "W", "E"):
            ms = p.moveset.get(slot)
            if not (ms and ms.ready and ms.chosen):
                continue
            mv = ms.chosen
            if mv.shape in ("buff", "shadowclaw") and d <= 3.0:
                p.pending_cast = (slot, p.pos.x, p.pos.y)
                return True
            if mv.shape == "clearsmog" and d <= mv.range:
                p.pending_cast = (slot, target.pos.x, target.pos.y)
                return True
            if mv.shape == "floatarmor" and d <= 4.0:
                p.pending_cast = (slot, p.pos.x, p.pos.y)
                return True
        return False
