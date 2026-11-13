"""Regole della linea Rookidee > Corvisquire > Corviknight (tank di supporto).

Puro: nessun pygame. È un mixin di Match (engine/match.py) come Eevee e
Spiritomb: usa lo stesso stato (self.time, self.world, self.fx_events,
_combat_hash, gli _apply_*). Il client legge match.tailwinds (correnti di
Ventoincoda) e match.taxi_flights (Taxi Volante) per disegnare.

Passive:
  - Sguardofermo (Rookidee, Corvisquire): +30% raggio visivo.
  - Specchiarmatura (Corviknight): un rallentamento o un calo di statistiche
    lanciato da un Pokémon nemico non lo colpisce e torna su chi l'ha lanciato
    (12 s di ricarica per lo stesso nemico; durante la ricarica lo subisce).

Stato nuovo "provocato" (Provocazione): il Pokémon deve attaccare con gli
attacchi base chi l'ha provocato e non può lanciare mosse.
"""
from __future__ import annotations

from .entities import Minion, Pokemon, Structure, Wild
from .vec import Vec2

SGUARDO_ID = "sguardofermo"
MIRROR_ID = "specchiarmatura"
CORVI_PASSIVES = {SGUARDO_ID, MIRROR_ID}

SGUARDO_VISION = 1.3          # Sguardofermo: +30% raggio visivo
MIRROR_CD = 12.0              # Specchiarmatura: ricarica per lo stesso nemico
# Effetti che Specchiarmatura rimanda: rallentamento e cali di statistiche.
MIRROR_KEYS = ("slow", "def_debuff", "spdef_debuff", "atk_debuff")
TAXI_MIN_FLIGHT = 0.6         # Taxi Volante: durata minima del volo (s)
TAXI_PEAK = 1.3               # altezza visiva del volo (tile)


class CorviknightMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(CORVI_PASSIVES),
        "init": "_init_corvi",
        "update": "_update_corvi",
        "cast": "_corvi_cast",
        "bot_cast": "_bot_corvi_cast",
    }

    def _init_corvi(self) -> None:
        self.tailwinds: list[dict] = []     # Ventoincoda: correnti di vento a tempo
        self.taxi_flights: list[dict] = []  # Taxi Volante: canalizzazione e volo

    # --- dispatcher -----------------------------------------------------------
    def _corvi_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"defog": self._cast_defog, "tailwind": self._cast_tailwind,
              "roost": self._cast_roost, "taxi": self._cast_taxi}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    def _corvi_point(self, origin, tgt, rng):
        to = tgt - origin
        if to.length() <= rng or to.length() < 1e-6:
            return Vec2(tgt.x, tgt.y)
        return origin + to.normalized() * rng

    # --- W: Scacciabruma ------------------------------------------------------
    def _cast_defog(self, p, mv, rank, origin, tgt, dirv):
        """Soffio su un'area: spazza via le zone e le trappole NEMICHE che la
        toccano (Muro di Fumo, Levitoroccia, vortici, nubi di Palla Fumo, zone di
        Abbattimento, pilastri di Rocciotomba)."""
        c = self._corvi_point(origin, tgt, mv.range)
        r = mv.radius
        foe = p.team

        def hit(center, rad):
            return center.dist(c) <= r + rad

        before = (len(self.area_effects) + len(self.item_clouds)
                  + len(self.smackdown_zones) + len(self.world.pillars))
        self.area_effects = [z for z in self.area_effects
                             if z.get("team") == foe or not hit(z["center"], z.get("radius", 0.0))]
        self.item_clouds = [z for z in self.item_clouds
                            if z.get("team") == foe or not hit(z["center"], z.get("radius", 0.0))]
        self.smackdown_zones = [z for z in self.smackdown_zones
                                if z.get("team") == foe
                                or not hit(z.get("c", z.get("center", Vec2(-99, -99))),
                                           z.get("radius", 0.0))]
        for pl in list(self.world.pillars):
            if pl.team != foe and hit(pl.pos, 0.5):
                self._remove_pillar(pl)
        # Chi era nel fumo nemico torna subito a vederci.
        for a in self.world.pokemons():
            if a.team == foe and a.alive and a.pos.dist(c) <= r:
                a.smoke_until = -1.0
        after = (len(self.area_effects) + len(self.item_clouds)
                 + len(self.smackdown_zones) + len(self.world.pillars))
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": r,
                               "mtype": mv.type, "o": (origin.x, origin.y),
                               "cleared": before - after})

    # --- E: Ventoincoda / Trespolo --------------------------------------------
    def _cast_tailwind(self, p, mv, rank, origin, tgt, dirv):
        """Corrente di vento in linea retta che resta per `duration`: gli alleati
        che la attraversano corrono di più per qualche secondo."""
        a = Vec2(origin.x, origin.y)
        b = self._clamp_to_wall(a, a + dirv * mv.range)
        if a.dist(b) < 1.5:   # muro subito davanti: la corrente passa comunque sopra
            b = a + dirv * mv.range
        dur = float(mv.effects.get("duration", 4.0))
        spd = mv.effects.get("speed", {})
        self.tailwinds.append({
            "a": a, "b": b, "c": (a + b) * 0.5, "width": mv.radius, "team": p.team,
            "start": self.time, "end": self.time + dur, "caster_id": p.id,
            "mult": float(spd.get("mult", 1.3)), "buff": float(spd.get("duration", 3.0))})
        self.fx_events.append({"kind": "dash", "a": (a.x, a.y), "b": (b.x, b.y),
                               "mtype": mv.type})

    def _update_tailwinds(self) -> None:
        now = self.time
        self.tailwinds = [w for w in self.tailwinds if w["end"] > now]
        for w in self.tailwinds:
            for q in self.world.pokemons():
                if q.team != w["team"] or not q.alive or q.is_decoy:
                    continue
                if self._point_seg_dist(q.pos, w["a"], w["b"]) > w["width"] + q.radius:
                    continue
                # Non toglie un bonus di velocità più forte già attivo.
                if q.speed_until > now and q.speed_mult > w["mult"]:
                    continue
                if q.speed_until - now < w["buff"] - 0.05:
                    if q.speed_until <= now:
                        self.fx_events.append({"kind": "buff", "c": (q.pos.x, q.pos.y),
                                               "mtype": "Flying", "fx": "tailwindbuff"})
                    self._apply_speed(q, w["mult"], w["buff"])

    def _cast_roost(self, p, mv, rank, origin, tgt, dirv):
        """Trespolo: si posa (fermo) e si cura una parte degli HP mancanti; per
        qualche secondo perde il tipo Volante (non è più debole a Roccia/Elettro
        né resistente a Lotta/Coleottero/Erba)."""
        eff = mv.effects
        p.stop()
        p.root_until = max(p.root_until, self.time + float(eff.get("root", 1.0)))
        heal = (p.max_hp - p.hp) * float(eff.get("heal_missing", 0.25)) * p.heal_power
        self._give_heal(p, p, heal)
        p.roost_until = self.time + float(eff.get("lose_flying", 3.0))
        if "Flying" in p.types:
            p.types = [t for t in p.types if t != "Flying"] or ["Normal"]
        self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "mtype": mv.type,
                               "radius": 1.0})

    def _stage_types(self, p) -> list:
        for st in p.evolutions:
            if st.get("stage", 0) == p.stage and "types" in st:
                return list(st["types"])
        return list(p.types)

    def _update_roost(self) -> None:
        for p in self.world.pokemons():
            if p.roost_until < 0.0:
                continue
            if p.roost_until > self.time and p.alive:
                if "Flying" in p.types:   # evoluto durante Trespolo: resta "posato"
                    p.types = [t for t in p.types if t != "Flying"] or ["Normal"]
                continue
            p.roost_until = -1.0
            p.types = self._stage_types(p)

    # --- R: Taxi Volante ------------------------------------------------------
    def _cast_taxi(self, p, mv, rank, origin, tgt, dirv):
        """Sceglie l'alleato più vicino entro `ally_range` (o nessuno) e un punto
        d'arrivo lontano; canalizza, poi vola con lui. Durante il volo nessuno dei
        due è bersagliabile; i nemici vedono dove atterreranno."""
        eff = mv.effects
        dest = self._nearest_walkable(self._corvi_point(origin, tgt, mv.range), origin)
        reach = float(eff.get("ally_range", 3.0))
        ally, best = None, 1e9
        for q in self.world.pokemons():
            if q is p or q.team != p.team or not q.alive or q.is_decoy:
                continue
            d = q.pos.dist(p.pos)
            if d <= reach + q.radius and d < best:
                ally, best = q, d
        channel = float(eff.get("channel", 1.5))
        p.stop()
        p.channel_until = self.time + channel
        p.root_until = max(p.root_until, self.time + channel)
        self.taxi_flights.append({
            "caster_id": p.id, "ally_id": ally.id if ally is not None else None,
            "team": p.team, "mv": mv, "rank": rank, "phase": "channel",
            "start": self.time, "end": self.time + channel,
            "dest": Vec2(dest.x, dest.y), "c": Vec2(dest.x, dest.y),
            "radius": mv.radius, "origin": Vec2(origin.x, origin.y),
            "speed": float(eff.get("speed", 18.0))})
        self.fx_events.append({"kind": "zone", "c": (dest.x, dest.y), "radius": mv.radius,
                               "mtype": mv.type})

    def _taxi_stopped(self, p) -> bool:
        """La canalizzazione si interrompe con i controlli (non con il suo root)."""
        t = self.time
        return (self._immobile(p) or p.fear_until > t or p.charm_until > t
                or p.taunt_until > t or p.silence_until > t)

    def _taxi_hold(self, u, until) -> None:
        u.stop()
        u.aa_active = False
        u.recalling = False
        u.target_id = None
        u.channel_until = max(u.channel_until, until)
        u.root_until = max(u.root_until, until)
        u.untargetable_until = max(u.untargetable_until, until + 0.05)

    def _update_taxi(self) -> None:
        now = self.time
        keep = []
        for fl in self.taxi_flights:
            p = self.world.get(fl["caster_id"])
            ally = self.world.get(fl["ally_id"]) if fl["ally_id"] is not None else None
            if p is None or not p.alive:
                if fl["phase"] == "flight" and ally is not None and ally.alive:
                    # Il trasportatore muore in volo: l'alleato scende dov'è.
                    ally.air_z = 0.0
                    ally.channel_until = ally.root_until = ally.untargetable_until = now
                    ally.pos = self._nearest_walkable(ally.pos, fl["src"])
                continue
            if ally is not None and not ally.alive:
                ally, fl["ally_id"] = None, None
            if fl["phase"] == "channel":
                if self._taxi_stopped(p):
                    p.channel_until = now
                    p.root_until = now
                    continue   # interrotto: la ricarica resta spesa
                if now < fl["end"]:
                    keep.append(fl)
                    continue
                # Decollo: l'alleato deve essere ancora vicino.
                if ally is not None and ally.pos.dist(p.pos) > 5.0:
                    ally, fl["ally_id"] = None, None
                src = Vec2(p.pos.x, p.pos.y)
                dist = src.dist(fl["dest"])
                fl.update(phase="flight", src=src, t0=now,
                          t1=now + max(TAXI_MIN_FLIGHT, dist / fl["speed"]),
                          pos=Vec2(src.x, src.y))
                if ally is not None:
                    fl["ally_off"] = ally.pos - p.pos
                self.fx_events.append({"kind": "blink", "a": (src.x, src.y),
                                       "b": (src.x, src.y), "mtype": "Flying",
                                       "fx": "taxitakeoff"})
            # In volo: lanciatore (e alleato) seguono la traiettoria.
            span = max(1e-6, fl["t1"] - fl["t0"])
            u = min(1.0, (now - fl["t0"]) / span)
            pos = fl["src"] + (fl["dest"] - fl["src"]) * u
            fl["pos"] = pos
            z = TAXI_PEAK * min(1.0, 4.0 * u * (1.0 - u) + (0.6 if 0.1 < u < 0.9 else 0.0))
            riders = [p] + ([ally] if ally is not None else [])
            for r in riders:
                self._taxi_hold(r, fl["t1"])
                off = fl.get("ally_off", Vec2(0.0, 0.0)) * 0.3 if r is ally else Vec2(0.0, 0.0)
                r.pos = pos + off
                r.air_z = z
            if u < 1.0:
                keep.append(fl)
                continue
            self._taxi_land(p, ally, fl)
        self.taxi_flights = keep

    def _taxi_land(self, p, ally, fl) -> None:
        dest = fl["dest"]
        now = self.time
        for r in (p, ally):
            if r is None:
                continue
            r.air_z = 0.0
            r.channel_until = now
            r.root_until = now
            r.untargetable_until = now
            r.stop()
        p.pos = Vec2(dest.x, dest.y)
        if ally is not None:
            off = fl.get("ally_off", Vec2(0.6, 0.0))
            off = off.normalized() * 0.8 if off.length() > 1e-6 else Vec2(0.8, 0.0)
            ally.pos = self._nearest_walkable(dest + off, dest)
        mv, rank = fl["mv"], fl["rank"]
        for e in self._combat_hash.query_radius(dest.x, dest.y, mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if isinstance(e, (Pokemon, Minion, Wild)) and dest.dist(e.pos) <= mv.radius + e.radius:
                self._hit(p, mv, rank, e)
                if not isinstance(e, Pokemon):   # i minion non passano da _apply_hit_effects
                    sl = mv.effects.get("slow")
                    if sl:
                        self._apply_slow(e, float(sl.get("mult", 0.6)),
                                         float(sl.get("duration", 1.5)))
        self.fx_events.append({"kind": "area", "c": (dest.x, dest.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": "taxiland"})

    # --- stato provocato ------------------------------------------------------
    def _apply_taunt(self, p, src, dur) -> None:
        """Provocato: per `dur` attacca solo `src` con attacchi base, niente mosse."""
        if not isinstance(p, Pokemon) or not isinstance(src, Pokemon) or self._cc_immune(p):
            return
        dur = self._tenacity_dur(p, dur)
        p.taunt_until = max(p.taunt_until, self.time + dur)
        p.taunt_src = src.id
        p.order = "idle"
        p.pending_cast = None
        self.fx_events.append({"kind": "charm", "c": (p.pos.x, p.pos.y), "mtype": "Dark",
                               "fx": "taunted"})

    def _taunted(self, p, dt) -> None:
        src = self.world.get(p.taunt_src) if p.taunt_src is not None else None
        if (src is None or not getattr(src, "alive", False)
                or src.untargetable_until > self.time or p.pos.dist(src.pos) > 12.0):
            p.taunt_until = -1.0
            p.target_id = None
            p.stop()
            return
        p.target_id = src.id
        if self._immobile(p) or p.root_until > self.time:
            p.stop()
            if self._within_attack(p, src):
                self._face(p, src)
            return
        if self._within_attack(p, src):
            p.stop()
            self._face(p, src)
        else:
            self._chase(p, src, dt)

    # --- Spennata: ruba il potenziamento --------------------------------------
    def _steal_buff(self, caster, target) -> None:
        """Se il bersaglio ha un bonus temporaneo da una mossa di potenziamento
        (Attacco, Difesa, Velocità), glielo toglie e il lanciatore lo ottiene per
        la durata rimanente."""
        if not isinstance(caster, Pokemon) or not isinstance(target, Pokemon):
            return
        now = self.time
        stolen = False
        if target.atk_until > now and target.atk_mult > 1.0:
            self._apply_atk(caster, target.atk_mult, target.atk_until - now)
            target.atk_mult, target.atk_until = 1.0, now
            stolen = True
        if target.def_buff_until > now and target.def_buff_mult > 1.0:
            self._apply_def_buff(caster, target.def_buff_mult, target.def_buff_until - now)
            caster.def_buff_active = True
            target.def_buff_mult, target.def_buff_until = 1.0, now
            target.def_buff_active = False
            stolen = True
        if target.speed_until > now and target.speed_mult > 1.0:
            self._apply_speed(caster, target.speed_mult, target.speed_until - now)
            target.speed_mult, target.speed_until = 1.0, now
            stolen = True
        if stolen:
            self.fx_events.append({"kind": "sync", "a": (target.pos.x, target.pos.y),
                                   "b": (caster.pos.x, caster.pos.y), "mtype": "Flying",
                                   "fx": "steal"})

    # --- passive --------------------------------------------------------------
    def _mirror_armor(self, caster, target, fx) -> dict:
        """Specchiarmatura: toglie da `fx` rallentamenti e cali di statistiche
        lanciati da un Pokémon nemico e li applica a lui. Ritorna gli effetti che
        Corviknight subisce davvero."""
        if (not isinstance(target, Pokemon) or target.passive_id != MIRROR_ID
                or not isinstance(caster, Pokemon) or caster.team == target.team
                or not caster.alive):
            return fx
        refl = {k: fx[k] for k in MIRROR_KEYS if fx.get(k)}
        if not refl or target.mirror_cd.get(caster.id, -1.0) > self.time:
            return fx
        target.mirror_cd[caster.id] = self.time + MIRROR_CD
        self._apply_hit_effects(target, caster, refl)
        self.fx_events.append({"kind": "sync", "a": (target.pos.x, target.pos.y),
                               "b": (caster.pos.x, caster.pos.y), "mtype": "Steel",
                               "fx": "mirror"})
        return {k: v for k, v in fx.items() if k not in refl}

    def _corvi_vision(self, p, base: float) -> float:
        if p.passive_id == SGUARDO_ID:
            return float(round(base * SGUARDO_VISION))
        return base

    def _update_corvi(self, dt: float) -> None:
        if self.tailwinds:
            self._update_tailwinds()
        if self.taxi_flights:
            self._update_taxi()
        self._update_roost()

    # --- bot ------------------------------------------------------------------
    def _bot_corvi_cast(self, p, target) -> bool:
        """I bot usano le mosse senza danno: Provocazione/Fulmisguardo sul
        nemico vicino, Trespolo e Granfisico in combattimento, Ventoincoda verso
        il bersaglio. Il Taxi Volante no (serve una scelta del giocatore)."""
        d = p.pos.dist(target.pos)
        for slot in ("W", "E"):
            ms = p.moveset.get(slot)
            if not (ms and ms.ready and ms.chosen):
                continue
            mv = ms.chosen
            if mv.shape == "cone" and mv.power_at(ms.rank) <= 0 and d <= mv.range:
                p.pending_cast = (slot, target.pos.x, target.pos.y)
                return True
            if mv.shape == "roost" and p.hp < 0.5 * p.max_hp:
                p.pending_cast = (slot, p.pos.x, p.pos.y)
                return True
            if mv.shape == "buff" and d <= 3.0:
                p.pending_cast = (slot, p.pos.x, p.pos.y)
                return True
            if mv.shape == "tailwind" and 3.0 <= d <= 9.0:
                p.pending_cast = (slot, target.pos.x, target.pos.y)
                return True
        return False
