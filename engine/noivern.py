"""Regole della linea Noibat > Noivern (tiratore mobile, danno speciale,
controllo della visione).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Charcadet e
Corviknight: usa lo stesso stato (self.time, self.world, self.fx_events,
_combat_hash, gli _apply_*). Il client legge le liste del Match
(sonar_pings, hurricanes, meteors) e il campo `echo_count` delle unità per
disegnare.

Passiva Ecolocalizzazione (Noibat e Noivern):
  - gli attacchi base sono onde sonore a distanza che fanno danno SPECIALE:
    potere speciale per livello (stats.sp_attack, con la penalità da tiratore)
    + Att. Sp. (AP), mitigato dalla Dif. Sp.; possono fare brutto colpo;
  - l'Attacco bonus degli oggetti si converte in Att. Sp. (gli altri bonus,
    velocità d'attacco e brutto colpo compresi, restano com'erano);
  - ogni terzo attacco base emette un ping: per 2 s la squadra vede i nemici
    nascosti (cespugli, nebbia, invisibili) entro 6 tile dal bersaglio
    (VisionSystem.reveals).
"""
from __future__ import annotations

import math

from .entities import Minion, Pokemon
from .vec import Vec2

ECHO_ID = "ecolocalizzazione"
NOIVERN_PASSIVES = {ECHO_ID}

ECHO_EVERY = 3                # ogni terzo attacco base parte il ping
PING_RADIUS = 6.0             # tile attorno al bersaglio
PING_DUR = 2.0
ECHO_AA_MULT = 0.95           # penalità da tiratore (come l'AD dei ranged)
HURRICANE_STEP = 0.2          # s tra due richieste dell'animazione "Hurt"


class NoivernMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(NOIVERN_PASSIVES),
        "init": "_init_noivern",
        "update": "_update_noivern",
        "cast": "_noivern_cast",
        "bot_cast": "_bot_noivern_cast",
    }

    def _init_noivern(self) -> None:
        self.sonar_pings: list[dict] = []    # Ecolocalizzazione: zone rivelate
        self.hurricanes: list[dict] = []     # Tifone: tornado che avanza
        self.meteors: list[dict] = []        # Dragobolide: pioggia di meteore in arrivo

    # --- dispatcher -----------------------------------------------------------
    def _noivern_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"dragonpulse": self._cast_dragonpulse, "whirlwind": self._cast_whirlwind,
              "hurricane": self._cast_hurricane,
              "dracometeor": self._cast_dracometeor}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    # --- passiva: Ecolocalizzazione ---------------------------------------------
    def _echo_convert(self, p) -> None:
        """L'Attacco bonus degli oggetti diventa Att. Sp. (sui bonus degli oggetti)."""
        if p.passive_id != ECHO_ID:
            return
        atk = p.item_bonus.pop("attack", 0.0)
        if atk:
            p.item_bonus["sp_attack"] = p.item_bonus.get("sp_attack", 0.0) + atk

    def _echo_power(self, u) -> float:
        """Potenza grezza dell'attacco base sonoro (prima della mitigazione)."""
        return (u.stats.sp_attack * ECHO_AA_MULT + u.eff_sp_attack()) * self._spa_down_mult(u)

    def _spa_down_mult(self, p) -> float:
        """Dragobolide: Att. Sp. ridotta per qualche secondo dopo l'impatto."""
        if isinstance(p, Pokemon) and p.spa_down_until > self.time:
            return p.spa_down_mult
        return 1.0

    def _echo_after_aa(self, u, tgt) -> None:
        """Ogni terzo attacco base: ping che rivela i nemici attorno al bersaglio."""
        if u.passive_id != ECHO_ID:
            return
        u.echo_count += 1
        if u.echo_count < ECHO_EVERY:
            return
        u.echo_count = 0
        c = Vec2(tgt.pos.x, tgt.pos.y)
        self.sonar_pings.append({"c": c, "radius": PING_RADIUS, "team": u.team,
                                 "start": self.time, "end": self.time + PING_DUR,
                                 "owner_id": u.id})
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": PING_RADIUS,
                               "mtype": "Normal", "fx": "echoping", "team": u.team})

    def _update_pings(self) -> None:
        now = self.time
        self.sonar_pings = [pg for pg in self.sonar_pings if pg["end"] > now]
        for team in (0, 1):
            self.vision.reveals[team] = [(pg["c"].x, pg["c"].y, pg["radius"])
                                         for pg in self.sonar_pings if pg["team"] == team]

    # --- Q: Dragopulsar -----------------------------------------------------------
    def _beam_end(self, origin, dirv, rng):
        """Fin dove arriva un raggio prima di sbattere su un muro."""
        grid = self.world.grid
        steps = int(rng * 4) + 1
        last = origin
        for i in range(1, steps + 1):
            pt = origin + dirv * (rng * i / steps)
            if not grid.line_of_sight(origin.x, origin.y, pt.x, pt.y):
                return last
            last = pt
        return last

    def _cast_dragonpulse(self, p, mv, rank, origin, tgt, dirv):
        """Raggio lungo di tipo Drago: colpisce TUTTI i nemici sulla linea."""
        end = self._beam_end(origin, dirv, mv.range)
        L = origin.dist(end)
        mid = (origin + end) * 0.5
        for e in self._combat_hash.query_radius(mid.x, mid.y, L * 0.5 + mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            rel = e.pos - origin
            proj = rel.x * dirv.x + rel.y * dirv.y
            if proj < -0.3 or proj > L + 0.3:
                continue
            perp = abs(rel.x * (-dirv.y) + rel.y * dirv.x)
            if perp <= mv.radius + getattr(e, "radius", 0.0):
                self._hit(p, mv, rank, e)
        self.fx_events.append({"kind": "projectile", "a": (origin.x, origin.y),
                               "b": (end.x, end.y), "mtype": mv.type})

    # --- W: Turbine ----------------------------------------------------------------
    def _cast_whirlwind(self, p, mv, rank, origin, tgt, dirv):
        """Raffica attorno a sé: piccolo danno e tutti i nemici vicini respinti
        di `push` tile (fermati dai muri). Campi neutrali e strutture restano."""
        push = float(mv.effects.get("push", 4.0))
        self.fx_events.append({"kind": "area", "c": (origin.x, origin.y),
                               "radius": mv.radius, "mtype": mv.type})
        for e in self._combat_hash.query_radius(origin.x, origin.y, mv.radius + 1.0):
            if (e.team == p.team or not getattr(e, "alive", False)
                    or not isinstance(e, (Pokemon, Minion))):
                continue
            if origin.dist(e.pos) > mv.radius + getattr(e, "radius", 0.0):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            self._hit(p, mv, rank, e)
            if not e.alive or (isinstance(e, Pokemon) and self._cc_immune(e)):
                continue
            away = e.pos - origin
            if away.length() < 1e-6:
                away = dirv
            self._item_push(e, away, push)

    # --- R: Tifone -----------------------------------------------------------------
    def _raining_at(self, pos) -> bool:
        """Pioggia globale (meteo) o locale (Pioggiadanza, aura di Politoad)."""
        if self.jungle.weather == "rain":
            return True
        if any(pos.dist(rz["center"]) <= rz["radius"] for rz in self.rain_zones):
            return True
        from .match import PIOVISCHIO_RADIUS
        return any(pt.pos.dist(pos) <= PIOVISCHIO_RADIUS for pt in self._iter_politoads())

    def _cast_hurricane(self, p, mv, rank, origin, tgt, dirv):
        """Grande tornado che avanza piano nella direzione scelta: chi tocca viene
        trascinato con sé, danneggiato nel tempo e, al rilascio, confuso. Con la
        Pioggia (globale o locale) è più grande del 50%."""
        eff = mv.effects
        dur = float(eff.get("duration", 4.0))
        start = origin + dirv * 1.0
        rain = self._raining_at(start)
        radius = mv.radius * (float(eff.get("rain_mult", 1.5)) if rain else 1.0)
        self.hurricanes.append({
            "c": Vec2(start.x, start.y), "dir": Vec2(dirv.x, dirv.y),
            "speed": mv.range / max(0.1, dur), "radius": radius, "rain": rain,
            "team": p.team, "caster_id": p.id, "start": self.time,
            "end": self.time + dur, "next": self.time + float(eff.get("interval", 0.5)),
            "interval": float(eff.get("interval", 0.5)), "mv": mv, "rank": rank,
            "caught": {}, "hurt_at": 0.0, "mtype": mv.type})
        self.fx_events.append({"kind": "area", "c": (start.x, start.y), "radius": radius,
                               "mtype": mv.type})

    def _catchable(self, h, e) -> bool:
        if e.team == h["team"] or not getattr(e, "alive", False):
            return False
        if not isinstance(e, (Pokemon, Minion)):
            return False   # niente campi neutrali né strutture
        if isinstance(e, Pokemon):
            if e.untargetable_until > self.time or self._cc_immune(e):
                return False
        return True

    def _update_hurricanes(self, dt: float) -> None:
        now = self.time
        grid = self.world.grid
        keep = []
        for h in self.hurricanes:
            c = h["c"]
            if now >= h["end"]:
                self._release_hurricane(h)
                continue
            nxt = c + h["dir"] * (h["speed"] * dt)
            if grid.is_walkable_point(nxt.x, nxt.y):   # contro un muro si ferma
                h["c"] = c = nxt
            r = h["radius"]
            for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
                if e.id in h["caught"] or not self._catchable(h, e):
                    continue
                if e.id in h.get("freed", ()):
                    continue   # Ventose: già liberato, non si riprende
                if c.dist(e.pos) <= r + getattr(e, "radius", 0.0):
                    h["caught"][e.id] = math.atan2(e.pos.y - c.y, e.pos.x - c.x)
                    if self._octi_disp_mult(e) < 1.0:   # Ventose: trascinato la metà
                        h.setdefault("rel", {})[e.id] = now + (h["end"] - now) * 0.5
                    if isinstance(e, Pokemon):
                        e.aa_active = False
                        e.recalling = False
            hurt = now >= h["hurt_at"]
            if hurt:
                h["hurt_at"] = now + HURRICANE_STEP
            orbit = 0.35 * r
            for eid, ang in list(h["caught"].items()):
                e = self.world.get(eid)
                if e is None or not e.alive:
                    h["caught"].pop(eid, None)
                    continue
                if now >= h.get("rel", {}).get(eid, 1e18):   # Ventose: liberato a metà
                    h["caught"].pop(eid, None)
                    h.setdefault("freed", set()).add(eid)
                    self._release_one(h, e)
                    continue
                ang += 5.0 * dt
                h["caught"][eid] = ang
                pos = Vec2(c.x + math.cos(ang) * orbit, c.y + math.sin(ang) * orbit * 0.6)
                e.pos = pos if grid.is_walkable_point(pos.x, pos.y) else Vec2(c.x, c.y)
                e.stop()
                if isinstance(e, Pokemon):   # trascinato: niente azioni
                    e.stun_until = max(e.stun_until, now + 0.15)
                else:                        # i minion non hanno stordimento: niente colpi
                    e.attack_timer = max(e.attack_timer, 0.15)
                if hurt:
                    self.fx_events.append({"eid": e.id, "anim": "Hurt"})
            if now >= h["next"]:
                h["next"] += h["interval"]
                caster = self.world.get(h["caster_id"])
                if caster is not None:
                    mult = 1.0   # il danno in JSON e' PER COLPO (bilanciamento v2)
                    for eid in list(h["caught"]):
                        e = self.world.get(eid)
                        if e is not None and e.alive:
                            self._hit(caster, h["mv"], h["rank"], e, mult=mult)
            keep.append(h)
        self.hurricanes = keep

    def _release_one(self, h, e) -> None:
        if e is None or not e.alive or not isinstance(e, Pokemon):
            return
        conf = float(h["mv"].effects.get("release_confuse", 1.0))
        if e.stun_until <= self.time + 0.16:   # torna subito normale (stordimenti
            e.stun_until = self.time           # di altre mosse restano)
        if conf > 0:
            self._apply_confuse(e, conf)

    def _release_hurricane(self, h) -> None:
        for eid in h["caught"]:
            self._release_one(h, self.world.get(eid))
        self.fx_events.append({"kind": "area", "c": (h["c"].x, h["c"].y),
                               "radius": h["radius"], "mtype": h["mtype"],
                               "fx": "hurricaneend"})

    # --- R: Dragobolide ------------------------------------------------------------
    def _cast_dracometeor(self, p, mv, rank, origin, tgt, dirv):
        """Dopo `delay` una pioggia di meteore colpisce una grande area lontana con
        danno altissimo; poi l'Att. Sp. di chi la lancia cala per qualche secondo."""
        to = tgt - origin
        c = (Vec2(tgt.x, tgt.y) if to.length() <= mv.range
             else origin + to.normalized() * mv.range)
        delay = float(mv.effects.get("delay", 1.0))
        self.meteors.append({"c": c, "radius": mv.radius, "team": p.team, "caster_id": p.id,
                             "start": self.time, "hit_at": self.time + delay,
                             "mv": mv, "rank": rank, "mtype": mv.type})

    def _update_meteors(self) -> None:
        keep = []
        for m in self.meteors:
            if self.time < m["hit_at"]:
                keep.append(m)
                continue
            p = self.world.get(m["caster_id"])
            c, mv = m["c"], m["mv"]
            if p is not None:
                for e in self._combat_hash.query_radius(c.x, c.y, m["radius"] + 1.0):
                    if e.team == p.team or not getattr(e, "alive", False):
                        continue
                    if c.dist(e.pos) <= m["radius"] + getattr(e, "radius", 0.0):
                        self._hit(p, mv, m["rank"], e)
                sd = mv.effects.get("spa_down")
                if sd and isinstance(p, Pokemon):
                    p.spa_down_mult = float(sd.get("mult", 0.6))
                    p.spa_down_until = self.time + float(sd.get("duration", 6.0))
            self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": m["radius"],
                                   "mtype": m["mtype"], "fx": "dracometeorhit"})
        self.meteors = keep

    # --- ciclo -------------------------------------------------------------------
    def _update_noivern(self, dt: float) -> None:
        if self.hurricanes:
            self._update_hurricanes(dt)
        if self.meteors:
            self._update_meteors()
        self._update_pings()

    # --- bot -------------------------------------------------------------------
    def _bot_noivern_cast(self, p, target) -> bool:
        """I bot usano anche Agilità (in combattimento) e Turbine (nemico addosso)."""
        d = p.pos.dist(target.pos)
        for slot in ("W", "E"):
            ms = p.moveset.get(slot)
            if not (ms and ms.ready and ms.chosen):
                continue
            mv = ms.chosen
            if mv.shape == "whirlwind" and d <= mv.radius:
                p.pending_cast = (slot, p.pos.x, p.pos.y)
                return True
            if mv.shape == "buff" and d <= 6.0:
                p.pending_cast = (slot, p.pos.x, p.pos.y)
                return True
        return False
