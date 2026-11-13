"""Regole della linea Litten > Torracat > Incineroar (combattente LOTTATORE
da top lane: provoca, afferra, usa i muri come le corde del ring).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Scizor: usa lo
stesso stato (self.time, self.world, self.fx_events, _combat_hash, gli
_apply_*). Il client legge i campi `incin_*` delle unità (i timer *_until
passano da soli anche online) e gli eventi fx.

Passive:
  - Prepotenza (tutta la linea): quando infligge danno a un Pokémon nemico
    dopo almeno 5 s senza infliggere né subire danni, i Pokémon nemici entro
    4 tile hanno -20% Attacco per 4 s.
  - Cattivo del Ring (in più con Incineroar): +5% danno inflitto per ogni
    Pokémon nemico entro 5 tile, fino a +15%.

Mosse: Q Doppiocalcio (due calci in un piccolo cono, metà danno l'uno;
Fuocodenti: morso su un solo bersaglio, 30% scottatura; Incrocolpo: colpo a
croce, +40% brutto colpo), W Bullo (cono: provoca 1,5 s; i provocati E
Incineroar +10% Attacco per 4 s; Granfisico: Incineroar +20% Attacco e
Difesa per 2,5 s; Provocazione: provoca 2,5 s, niente bonus ai nemici),
E Corsa alle Corde (scatto di 5 tile: trascina il primo Pokémon nemico e lo
schianta contro il muro = danno + stordimento 1 s; a vuoto contro il muro
rimbalza indietro al +50% di velocità e potenzia il prossimo attacco base
o Q: +50% danno e stordimento 0,5 s; Doppio Rimbalzo: fino a 2 rimbalzi;
Slancio: ogni rimbalzo dimezza la ricarica rimanente), R Darkest Lariat
(3 s di rotazione inarrestabile, colpi ogni 0,5 s entro 2,5 tile, ignora i
bonus temporanei alla Difesa) / Presa del Campione (afferra entro 2 tile e
scaglia fino a 6 tile: contro il muro danno extra e stordimento 1,5 s; i
Pokémon nemici sul percorso subiscono danno e volano in aria 1 s).
"""
from __future__ import annotations

import math

from .entities import Minion, Pokemon, Structure, Wild
from .vec import Vec2

INTIM_ID = "prepotenza"
RING_ID = "cattivodelring"
INCIN_PASSIVES = {INTIM_ID, RING_ID}
INCIN_DEX = (725, 726, 727)

INTIM_IDLE = 5.0            # Prepotenza: secondi senza combattere
INTIM_RANGE = 4.0
INTIM_MULT = 0.80           #   -20% Attacco
INTIM_DUR = 4.0
RING_RANGE = 5.0            # Cattivo del Ring: +5% per nemico entro 5 tile
RING_PER = 0.05
RING_MAX = 3
DRAG_STUN = 0.12            # chi è trascinato/scagliato non agisce (rinnovato ogni tick)


def has_incin(p) -> bool:
    return getattr(p, "passive_id", "") in INCIN_PASSIVES


def _in_cone(pos, origin, dirv, rng, half, extra=0.0) -> bool:
    rel = pos - origin
    d = rel.length()
    if d > rng + extra:
        return False
    if d < 1e-6:
        return True
    cosang = (rel.x * dirv.x + rel.y * dirv.y) / d
    return math.acos(max(-1.0, min(1.0, cosang))) <= half


class IncineroarMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(INCIN_PASSIVES),
        "init": "_init_incin",
        "update": "_update_incin",
        "precheck": "_incin_precheck",
        "cast": "_incin_cast",
        "bot_cast": "_bot_incin_cast",
        "speed_mult": "_incin_speed_mult",
    }

    def _init_incin(self) -> None:
        self.incin_runs: list[dict] = []     # Corsa alle Corde in corso
        self.incin_throws: list[dict] = []   # Presa del Campione: nemici in volo
        self._incin_kicks: list[dict] = []   # secondo calcio di Doppiocalcio

    # --- dispatcher --------------------------------------------------------------
    def _incin_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"incinkick": self._cast_incinkick, "incinfang": self._cast_incinfang,
              "incincross": self._cast_incincross, "incinbully": self._cast_incinbully,
              "incinropes": self._cast_incinropes, "incinlariat": self._cast_incinlariat,
              "incingrab": self._cast_incingrab}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    def _incin_precheck(self, p, mv, tgt) -> bool:
        """Presa del Campione senza un Pokémon nemico a portata: non parte e la
        ricarica non si spende. Corsa alle Corde bloccata da Cucitombra."""
        if mv.shape == "incingrab":
            return self._incin_grab_target(p, mv) is not None
        if mv.shape == "incinropes":
            return p.dashlock_until <= self.time
        return True

    def _incin_foe_ok(self, p, e, pokemon_only=False) -> bool:
        if e.team == p.team or not getattr(e, "alive", False):
            return False
        if pokemon_only and not isinstance(e, Pokemon):
            return False
        if not isinstance(e, (Pokemon, Minion, Wild, Structure)):
            return False
        if isinstance(e, Pokemon) and (e.untargetable_until > self.time or e.is_decoy
                                       and pokemon_only):
            return False
        return True

    def _incin_foes_in_cone(self, p, origin, dirv, rng, half, pokemon_only=False):
        out = []
        for e in self._combat_hash.query_radius(origin.x, origin.y, rng + 1.5):
            if not self._incin_foe_ok(p, e, pokemon_only):
                continue
            if _in_cone(e.pos, origin, dirv, rng, half, getattr(e, "radius", 0.0)):
                out.append(e)
        return out

    # --- Prepotenza / Cattivo del Ring ----------------------------------------------
    def _incin_on_dealt(self, attacker, target, amount) -> None:
        """Chiamata da _deal_damage prima di togliere gli HP."""
        if not isinstance(attacker, Pokemon) or not has_incin(attacker) or amount <= 0.0:
            return
        now = self.time
        calm = max(attacker.incin_last_dealt, attacker.last_damaged_at)
        if (isinstance(target, Pokemon) and target.team != attacker.team
                and not target.is_decoy and now - calm >= INTIM_IDLE):
            self._incin_intimidate(attacker)
        attacker.incin_last_dealt = now
        attacker.incin_calm_at = max(attacker.incin_last_dealt, attacker.last_damaged_at)

    def _incin_intimidate(self, p) -> None:
        hit = 0
        for e in self.world.pokemons():
            if (e.team == p.team or not e.alive or e.is_decoy
                    or e.pos.dist(p.pos) > INTIM_RANGE + e.radius):
                continue
            e.incin_intim_until = self.time + INTIM_DUR
            hit += 1
            self.fx_events.append({"kind": "area", "c": (e.pos.x, e.pos.y), "radius": 0.6,
                                   "mtype": "Dark", "fx": "incinintimhit"})
        self.fx_events.append({"kind": "area", "c": (p.pos.x, p.pos.y), "radius": INTIM_RANGE,
                               "mtype": "Dark", "fx": "incinintim", "n": hit})

    def _incin_dmg_mult(self, attacker) -> float:
        """Cattivo del Ring: +5% per Pokémon nemico entro 5 tile (max +15%)."""
        if getattr(attacker, "passive_id", "") != RING_ID:
            return 1.0
        return 1.0 + RING_PER * attacker.incin_ring_n

    def _incin_ring_count(self, p) -> int:
        n = 0
        for e in self.world.pokemons():
            if (e.team != p.team and e.alive and not e.is_decoy
                    and e.pos.dist(p.pos) <= RING_RANGE + e.radius):
                n += 1
        return min(RING_MAX, n)

    # --- Corsa alle Corde: potenziamento del rimbalzo -----------------------------------
    def _incin_emp(self, p) -> dict | None:
        """Effetti del colpo potenziato (prossimo attacco base o Q), se attivo."""
        if getattr(p, "incin_rope_until", -1.0) <= self.time:
            return None
        ms = p.moveset.get("E")
        mv = ms.chosen if ms is not None else None
        emp = mv.effects.get("empower") if mv is not None else None
        return emp or {"mult": 1.5, "stun": 0.5}

    def _incin_aa_mult(self, u) -> float:
        emp = self._incin_emp(u) if isinstance(u, Pokemon) else None
        return float(emp.get("mult", 1.5)) if emp else 1.0

    def _incin_after_aa(self, u, tgt) -> None:
        if not isinstance(u, Pokemon):
            return
        emp = self._incin_emp(u)
        if emp is None:
            return
        u.incin_rope_until = -1.0
        if isinstance(tgt, Pokemon) and tgt.alive and tgt.team != u.team:
            self._apply_stun(tgt, float(emp.get("stun", 0.5)))
        self.fx_events.append({"kind": "area", "c": (tgt.pos.x, tgt.pos.y), "radius": 0.7,
                               "mtype": "Fighting", "fx": "incinempower"})

    def _incin_q_emp(self, p):
        """Q potenziata: (moltiplicatore, durata dello stordimento) e consuma."""
        emp = self._incin_emp(p)
        if emp is None:
            return 1.0, 0.0
        p.incin_rope_until = -1.0
        return float(emp.get("mult", 1.5)), float(emp.get("stun", 0.5))

    def _incin_stun_hit(self, p, targets, stun) -> None:
        if stun <= 0.0:
            return
        for e in targets:
            if isinstance(e, Pokemon) and e.alive and e.team != p.team:
                self._apply_stun(e, stun)
                self.fx_events.append({"kind": "area", "c": (e.pos.x, e.pos.y), "radius": 0.7,
                                       "mtype": "Fighting", "fx": "incinempower"})

    # --- Q Doppiocalcio / Fuocodenti / Incrocolpo -----------------------------------------
    def _cast_incinkick(self, p, mv, rank, origin, tgt, dirv):
        fx = mv.effects
        mult, stun = self._incin_q_emp(p)
        half = math.radians(mv.angle)
        km = float(fx.get("kick_mult", 0.5))
        foes = self._incin_foes_in_cone(p, origin, dirv, mv.range, half)
        for e in foes:
            self._hit(p, mv, rank, e, mult=km * mult)
        self._incin_stun_hit(p, foes, stun)
        for k in range(1, int(fx.get("kicks", 2))):
            self._incin_kicks.append({"t": self.time + float(fx.get("kick_gap", 0.18)) * k,
                                      "pid": p.id, "mv": mv, "rank": rank,
                                      "dir": Vec2(dirv.x, dirv.y), "mult": km * mult, "n": k})
        self.fx_events.append({"kind": "cone", "o": (origin.x, origin.y), "dir": (dirv.x, dirv.y),
                               "range": mv.range, "angle": mv.angle, "mtype": mv.type,
                               "n": 0, "emp": stun > 0.0})

    def _update_incin_kicks(self) -> None:
        keep = []
        for k in self._incin_kicks:
            if self.time < k["t"]:
                keep.append(k)
                continue
            p = self.world.get(k["pid"])
            if p is None or not p.alive or self._immobile(p):
                continue
            mv = k["mv"]
            o, d = Vec2(p.pos.x, p.pos.y), k["dir"]
            for e in self._incin_foes_in_cone(p, o, d, mv.range, math.radians(mv.angle)):
                self._hit(p, mv, k["rank"], e, mult=k["mult"])
            self.fx_events.append({"kind": "cone", "o": (o.x, o.y), "dir": (d.x, d.y),
                                   "range": mv.range, "angle": mv.angle, "mtype": mv.type,
                                   "fx": mv.fx, "n": k["n"], "src": p.id, "move": mv.id})
        self._incin_kicks = keep

    def _cast_incinfang(self, p, mv, rank, origin, tgt, dirv):
        mult, stun = self._incin_q_emp(p)
        best, bd = None, 1e9
        for e in self._incin_foes_in_cone(p, origin, dirv, mv.range, math.radians(50)):
            d = origin.dist(e.pos)
            # Preferisce i Pokémon; tra pari, il più vicino.
            key = d - (10.0 if isinstance(e, Pokemon) else 0.0)
            if key < bd:
                best, bd = e, key
        tip = origin + dirv * min(mv.range, 1.2)
        if best is not None:
            self._hit(p, mv, rank, best, mult=mult)   # scottatura al 30% (effects.burn)
            self._incin_stun_hit(p, [best], stun)
            tip = Vec2(best.pos.x, best.pos.y)
        self.fx_events.append({"kind": "attack", "a": (origin.x, origin.y), "b": (tip.x, tip.y),
                               "mtype": mv.type, "melee": True, "hit": best is not None})

    def _cross_hit(self, pos, c, dirv, arm, w) -> bool:
        """Dentro la X centrata in c (due bracci a ±45° dalla direzione)."""
        for sg in (1, -1):
            a = math.atan2(dirv.y, dirv.x) + sg * math.pi / 4
            u = Vec2(math.cos(a), math.sin(a))
            if self._point_seg_dist(pos, c - u * arm, c + u * arm) <= w:
                return True
        return False

    def _cast_incincross(self, p, mv, rank, origin, tgt, dirv):
        fx = mv.effects
        mult, stun = self._incin_q_emp(p)
        c = origin + dirv * float(fx.get("center", 1.25))
        arm = float(fx.get("arm", 1.05))
        foes = []
        for e in self._combat_hash.query_radius(c.x, c.y, arm + 1.5):
            if not self._incin_foe_ok(p, e):
                continue
            if self._cross_hit(e.pos, c, dirv, arm, mv.radius + getattr(e, "radius", 0.0)):
                foes.append(e)
        for e in foes:
            self._hit(p, mv, rank, e, mult=mult)   # +40% brutto colpo (crit_bonus)
        self._incin_stun_hit(p, foes, stun)
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "dir": (dirv.x, dirv.y),
                               "radius": arm, "mtype": mv.type, "hit": bool(foes)})

    # --- W Bullo / Granfisico / Provocazione -----------------------------------------------
    def _cast_incinbully(self, p, mv, rank, origin, tgt, dirv):
        fx = mv.effects
        half = math.radians(mv.angle)
        dur = float(fx.get("atk_dur", 4.0))
        foes = self._incin_foes_in_cone(p, origin, dirv, mv.range, half, pokemon_only=True)
        for e in foes:
            self._apply_taunt(e, p, float(fx.get("taunt", 1.5)))
            if fx.get("foe_atk"):   # i provocati si arrabbiano: +10% Attacco
                e.incin_bully_until = self.time + dur
        if fx.get("self_atk"):
            p.incin_bully_until = self.time + dur
        bulk = fx.get("bulk")
        if bulk:   # Granfisico: +20% Attacco e Difesa
            self._apply_atk(p, float(bulk.get("atk", 1.2)), float(bulk.get("duration", 2.5)))
            self._apply_def_buff(p, float(bulk.get("def", 1.2)), float(bulk.get("duration", 2.5)))
        self.fx_events.append({"kind": "cone", "o": (origin.x, origin.y), "dir": (dirv.x, dirv.y),
                               "range": mv.range, "angle": mv.angle, "mtype": mv.type,
                               "n": len(foes), "bulk": bool(bulk)})

    # --- E Corsa alle Corde ---------------------------------------------------------------
    def _cast_incinropes(self, p, mv, rank, origin, tgt, dirv):
        if p.dashlock_until > self.time:
            return
        p.stop()
        p.aa_active = False
        p.channel_until = self.time + mv.range / max(0.1, mv.speed) + 0.2
        self.incin_runs.append({"pid": p.id, "dir": Vec2(dirv.x, dirv.y), "left": mv.range,
                                "speed": mv.speed, "mv": mv, "rank": rank, "drag": None,
                                "bounces": int(mv.effects.get("bounces", 1)), "n": 0,
                                "fx_next": 0.0})

    def _incin_wall_ahead(self, pos, dirv, dist) -> bool:
        pt = pos + dirv * dist
        return not self.world.grid.is_walkable_point(pt.x, pt.y)

    def _end_run(self, p, run) -> None:
        p.channel_until = self.time
        p.stop()
        e = self.world.get(run["drag"]) if run["drag"] is not None else None
        if e is not None:
            e.stop()

    def _update_incin_runs(self, dt: float) -> None:
        alive = []
        for run in self.incin_runs:
            p = self.world.get(run["pid"])
            if p is None or not p.alive or self._immobile(p):
                if p is not None:
                    p.channel_until = self.time
                continue
            mv, dirv = run["mv"], run["dir"]
            if any(z["team"] != p.team and p.pos.dist(z["c"]) <= z["radius"] + p.radius
                   for z in self.smackdown_zones):   # Abbattimento nemico: si ferma
                self._intercept_dash(p, p.pos, p.pos)
                self._end_run(p, run)
                continue
            drag = self.world.get(run["drag"]) if run["drag"] is not None else None
            if drag is not None and (not drag.alive or drag.untargetable_until > self.time):
                drag, run["drag"] = None, None
            step = min(run["speed"] * dt, max(0.0, run["left"]))
            newpos = p.pos + dirv * step
            # Sbatte contro le corde: muro/pilastro davanti a lui o davanti al
            # nemico trascinato.
            lead = p.radius * 0.8 if drag is None else p.radius + 2.0 * drag.radius + 0.05
            if self._incin_wall_ahead(newpos, dirv, lead):
                if drag is not None:
                    self._incin_slam(p, run, drag)
                    self._end_run(p, run)
                    continue
                if run["bounces"] > 0:
                    self._incin_bounce(p, run)
                    alive.append(run)
                    continue
                self._end_run(p, run)
                continue
            p.pos = newpos
            p.stop()
            run["left"] -= step
            if drag is None:   # afferra il primo Pokémon nemico sul percorso
                for e in self._combat_hash.query_radius(p.pos.x, p.pos.y, p.radius + 1.5):
                    if (not isinstance(e, Pokemon) or not self._incin_foe_ok(p, e, True)
                            or e.pos.dist(p.pos) > p.radius + e.radius + mv.radius * 0.5):
                        continue
                    if self._cc_immune(e):
                        continue
                    run["drag"] = e.id
                    drag = e
                    self.fx_events.append({"kind": "area", "c": (e.pos.x, e.pos.y),
                                           "radius": 0.7, "mtype": "Fighting",
                                           "fx": "incingrabbed"})
                    break
            if drag is not None:
                pt = p.pos + dirv * (p.radius + drag.radius + 0.05)
                if self.world.grid.is_walkable_point(pt.x, pt.y):
                    drag.pos = pt
                drag.stop()
                drag.stun_until = max(drag.stun_until, self.time + DRAG_STUN)
            if self.time >= run["fx_next"]:
                run["fx_next"] = self.time + 0.05
                self.fx_events.append({"kind": "dash", "a": (p.pos.x - dirv.x * 0.6,
                                                             p.pos.y - dirv.y * 0.6),
                                       "b": (p.pos.x, p.pos.y), "mtype": "Fire",
                                       "fx": "incinrun", "n": run["n"]})
            if run["left"] <= 0.0:
                self._end_run(p, run)
                continue
            alive.append(run)
        self.incin_runs = alive

    def _incin_slam(self, p, run, e) -> None:
        """Il nemico trascinato sbatte contro il muro: danno + stordimento."""
        mv = run["mv"]
        self._hit(p, mv, run["rank"], e)
        if e.alive:
            self._apply_stun(e, float(mv.effects.get("slam_stun", 1.0)))
        wall = e.pos + run["dir"] * (e.radius + 0.2)
        self.fx_events.append({"kind": "area", "c": (wall.x, wall.y), "radius": 1.0,
                               "dir": (run["dir"].x, run["dir"].y), "mtype": "Fighting",
                               "fx": "incinslam"})
        self.fx_events.append({"eid": e.id, "anim": "Hurt"})

    def _incin_bounce(self, p, run) -> None:
        """Rimbalzo sulle corde: torna indietro più veloce e potenzia il colpo."""
        mv = run["mv"]
        fx = mv.effects
        run["bounces"] -= 1
        run["n"] += 1
        run["dir"] = Vec2(-run["dir"].x, -run["dir"].y)
        run["left"] = mv.range
        run["speed"] = mv.speed * float(fx.get("bounce_speed", 1.5))
        p.channel_until = self.time + run["left"] / max(0.1, run["speed"]) + 0.2
        emp = fx.get("empower", {})
        p.incin_rope_until = self.time + float(emp.get("window", 3.0))
        cdr = float(fx.get("bounce_cdr", 0.0))
        if cdr > 0.0:   # Slancio: ogni rimbalzo dimezza la ricarica rimanente
            ms = p.moveset.get("E")
            if ms is not None:
                ms.cooldown_remaining *= (1.0 - cdr)
        self.fx_events.append({"kind": "area", "c": (p.pos.x, p.pos.y), "radius": 0.9,
                               "dir": (run["dir"].x, run["dir"].y), "mtype": "Fighting",
                               "fx": "incinbounce", "n": run["n"], "cdr": cdr > 0.0})

    # --- R Darkest Lariat -------------------------------------------------------------------
    def _cast_incinlariat(self, p, mv, rank, origin, tgt, dirv):
        fx = mv.effects
        dur = float(fx.get("duration", 3.0))
        p.incin_lariat_until = self.time + dur
        p.incin_lariat_next = self.time   # il primo colpo parte subito
        p.cc_immune_until = max(p.cc_immune_until, self.time + dur)   # inarrestabile
        p.channel_until = self.time + dur   # niente attacchi base né altre mosse
        p.aa_active = False
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "radius": mv.radius,
                               "mtype": mv.type})

    def _incin_lariat_tick(self, p) -> None:
        ms = p.moveset.get("R")
        mv = ms.chosen if ms is not None else None
        if mv is None or mv.shape != "incinlariat":
            p.incin_lariat_until = -1.0
            return
        if p.incin_lariat_next > self.time:
            return
        p.incin_lariat_next = self.time + float(mv.effects.get("interval", 0.5))
        R = mv.radius
        hit = 0
        for e in self._combat_hash.query_radius(p.pos.x, p.pos.y, R + 1.0):
            if not self._incin_foe_ok(p, e) or isinstance(e, Structure):
                continue
            if e.pos.dist(p.pos) > R + getattr(e, "radius", 0.0):
                continue
            self._hit(p, mv, ms.rank, e)   # ignore_def_buffs: la Difesa potenziata non conta
            hit += 1
        self.fx_events.append({"kind": "area", "c": (p.pos.x, p.pos.y), "radius": R,
                               "mtype": mv.type, "fx": "incinlariattick", "hit": hit})

    def _incin_speed_mult(self, p) -> float:
        if p.incin_lariat_until > self.time:
            ms = p.moveset.get("R")
            mv = ms.chosen if ms is not None else None
            return float(mv.effects.get("move_mult", 0.7)) if mv is not None else 0.7
        return 1.0

    # --- R Presa del Campione -------------------------------------------------------------
    def _incin_grab_target(self, p, mv):
        rng = float(mv.effects.get("grab_range", 2.0))
        best, bd = None, 1e9
        for e in self._combat_hash.query_radius(p.pos.x, p.pos.y, rng + 1.5):
            if not isinstance(e, Pokemon) or not self._incin_foe_ok(p, e, True):
                continue
            d = p.pos.dist(e.pos)
            if d <= rng + e.radius + p.radius and d < bd:
                best, bd = e, d
        return best

    def _cast_incingrab(self, p, mv, rank, origin, tgt, dirv):
        fx = mv.effects
        e = self._incin_grab_target(p, mv)
        if e is None:
            return
        self._hit(p, mv, rank, e)
        self.fx_events.append({"kind": "attack", "a": (origin.x, origin.y), "b": (e.pos.x, e.pos.y),
                               "mtype": mv.type, "melee": True, "fx": "incingrabhold"})
        if not e.alive or self._cc_immune(e) or e.untargetable_until > self.time:
            return
        p.stop()
        start = Vec2(e.pos.x, e.pos.y)
        # Lo solleva e lo scaglia nella direzione scelta (da Incineroar verso il mirino).
        self.incin_throws.append({"pid": e.id, "src": p.id, "team": p.team, "dir": Vec2(dirv.x, dirv.y),
                                  "left": mv.range, "total": mv.range, "speed": mv.speed,
                                  "mv": mv, "rank": rank, "hit": set(), "start": start,
                                  "fx_next": 0.0})
        e.stop()
        e.aa_active = False
        e.stun_until = max(e.stun_until, self.time + DRAG_STUN)
        self.fx_events.append({"eid": e.id, "anim": "Hurt"})

    def _update_incin_throws(self, dt: float) -> None:
        g = self.world.grid
        keep = []
        for th in self.incin_throws:
            e = self.world.get(th["pid"])
            src = self.world.get(th["src"])
            if e is None or not e.alive:
                continue
            mv, d = th["mv"], th["dir"]
            fx = mv.effects
            step = min(th["speed"] * dt, max(0.0, th["left"]))
            nxt = e.pos + d * step
            front = nxt + d * (e.radius * 0.8)
            if not g.is_walkable_point(front.x, front.y):
                # Contro il muro: danno extra e stordimento lungo.
                e.air_z = 0.0
                if src is not None:
                    self._hit(src, mv, th["rank"], e, mult=float(fx.get("wall_mult", 0.5)))
                if e.alive:
                    self._apply_stun(e, float(fx.get("wall_stun", 1.5)))
                wall = e.pos + d * (e.radius + 0.2)
                self.fx_events.append({"kind": "area", "c": (wall.x, wall.y), "radius": 1.2,
                                       "dir": (d.x, d.y), "mtype": "Fighting",
                                       "fx": "incinslam", "big": True})
                self.fx_events.append({"eid": e.id, "anim": "Hurt"})
                continue
            e.pos = nxt
            e.stop()
            th["left"] -= step
            u = 1.0 - th["left"] / max(1e-6, th["total"])
            e.air_z = 1.4 * 4.0 * u * (1.0 - u)
            e.stun_until = max(e.stun_until, self.time + DRAG_STUN)
            # Chi sta sul percorso viene travolto (danno + in aria).
            pr = float(fx.get("path_radius", 0.8))
            if src is not None:
                for o in self._combat_hash.query_radius(e.pos.x, e.pos.y, pr + 1.0):
                    if (o is e or not isinstance(o, Pokemon) or o.id in th["hit"]
                            or not self._incin_foe_ok(src, o, True)
                            or o.pos.dist(e.pos) > pr + o.radius):
                        continue
                    th["hit"].add(o.id)
                    self._hit(src, mv, th["rank"], o, mult=float(fx.get("path_mult", 0.5)))
                    self._apply_airborne(o, float(fx.get("path_air", 1.0)), 1.0)
            if self.time >= th["fx_next"]:
                th["fx_next"] = self.time + 0.05
                self.fx_events.append({"kind": "dash", "a": (e.pos.x - d.x * 0.5, e.pos.y - d.y * 0.5),
                                       "b": (e.pos.x, e.pos.y), "mtype": "Fighting",
                                       "fx": "incinthrown", "z": e.air_z})
            if th["left"] <= 0.0:
                e.air_z = 0.0
                self.fx_events.append({"kind": "area", "c": (e.pos.x, e.pos.y), "radius": 0.9,
                                       "mtype": "Fighting", "fx": "incinland"})
                continue
            keep.append(th)
        self.incin_throws = keep

    # --- stato per tick --------------------------------------------------------------------
    def _incin_stat_mults(self, p) -> None:
        now = self.time
        m = 1.0
        if p.incin_intim_until > now:
            m *= INTIM_MULT
        if p.incin_bully_until > now:
            m *= 1.10
        p.incin_atk_mult = m

    def _update_incin(self, dt: float) -> None:
        self._update_incin_kicks()
        self._update_incin_runs(dt)
        self._update_incin_throws(dt)
        now = self.time
        for p in self.world.pokemons():
            if p.incin_intim_until > -1.0 or p.incin_bully_until > -1.0 or p.incin_atk_mult != 1.0:
                self._incin_stat_mults(p)
            if not has_incin(p):
                continue
            p.incin_calm_at = max(p.incin_last_dealt, p.last_damaged_at)
            p.incin_ring_n = self._incin_ring_count(p) if (p.passive_id == RING_ID and p.alive) else 0
            if p.incin_lariat_until > now and p.alive:
                self._incin_lariat_tick(p)
            elif p.incin_lariat_until > -1.0 and (p.incin_lariat_until <= now or not p.alive):
                p.incin_lariat_until = -1.0

    # --- bot --------------------------------------------------------------------------------
    def _bot_incin_cast(self, p, target) -> bool:
        """Bullo (potenza 0) non lo lancerebbe il ciclo generico: lo usa sui
        Pokémon vicini. Presa del Campione solo con un nemico a portata."""
        if not isinstance(target, Pokemon):
            return False
        d = p.pos.dist(target.pos)
        ms = p.moveset.get("W")
        mv = ms.chosen if ms is not None else None
        if (mv is not None and ms.ready and ms.rank > 0 and mv.shape == "incinbully"
                and d <= mv.range * 0.8):
            p.pending_cast = ("W", target.pos.x, target.pos.y)
            return True
        ms = p.moveset.get("R")
        mv = ms.chosen if ms is not None else None
        if mv is not None and ms.ready and ms.rank > 0 and ms.unlocked:
            if mv.shape == "incinlariat" and d <= mv.radius:
                p.pending_cast = ("R", p.pos.x, p.pos.y)
                return True
            if mv.shape == "incingrab" and self._incin_grab_target(p, mv) is not None:
                p.pending_cast = ("R", target.pos.x, target.pos.y)
                return True
        return False
