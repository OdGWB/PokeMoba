"""Regole della linea Sneasel > Weavile / Sneasler.

Puro: nessun pygame. Mixin di Match (engine/match.py) come Charcadet e
Teddiursa: usa lo stesso stato (self.time, self.world, self.fx_events,
_combat_hash, gli _apply_*). Il client legge le liste del Match (claw_leaps,
beatups, sludge_lobs) e i campi delle unità (nightfall_until, healcut_until,
snatch_down/snatch_up, gold_minion/gold_wild) per disegnare.

Passive:
  - Sole e Luna (Sneasel): conta l'oro guadagnato dai minion (last-hit) e dai
    Pokémon neutrali (campi + oro di squadra del leggendario meteo e di
    Arceus). Al liv.8 decide la forma (evolution._requires_met, {"oro":
    "neutrali"}): neutrali più alto -> Sneasler, altrimenti (parità compresa)
    Weavile.
  - Arraffalesto (Weavile): ogni colpo (attacco base o mossa) su un Pokémon
    nemico isolato (nessun suo alleato entro 5 tile) gli ruba il 5% di
    Attacco e Att. Sp. per 4 s, cumulabile fino al 25%; Weavile guadagna lo
    stesso valore.
  - Scalaroccia (Sneasler): muovendosi contro un muro della giungla spesso al
    massimo 3 tile lo scavalca in 1 s (non bersagliabile), ricarica 6 s;
    +30% di danno ai neutrali.
Stato generico: cure ridotte (healcut_until/healcut_mult), letto da
_heal_in_mult per ogni cura che passa di lì.
"""
from __future__ import annotations

import random

from .entities import Minion, Pokemon, Wild
from .grid import TILE_JUNGLE_WALL, TILE_WALL
from .pathfinding import find_path, smooth_path
from .vec import Vec2

SUNMOON_ID = "soleluna"
SNATCH_ID = "arraffalesto"
CLIMB_ID = "scalaroccia"
SNEASEL_PASSIVES = {SUNMOON_ID, SNATCH_ID, CLIMB_ID}

ISOLATION_RANGE = 5.0         # isolato: nessun alleato Pokémon entro questa distanza
SNATCH_PER = 0.05             # Arraffalesto: 5% per carica
SNATCH_MAX = 5                # fino al 25%
SNATCH_DUR = 4.0
CLIMB_WILD_MULT = 1.30        # Scalaroccia: danno ai Pokémon neutrali
CLIMB_TIME = 1.0              # durata dello scavalcamento
CLIMB_CD = 6.0
CLIMB_MAX = 3.05              # spessore massimo del muro (tile)
CLIMB_REACH = 0.55            # il muro deve essere a questa distanza dal bordo dell'unità
CLIMB_PEAK = 1.1              # altezza del salto (tile, solo grafica)
PICK = 2.5                    # raggio di ricerca del bersaglio attorno al mirino
DIRECLAW_POISON = 0.03        # Dire Claw: veleno = 3% HP max al secondo


def is_sneasel_line(p) -> bool:
    return getattr(p, "passive_id", None) in SNEASEL_PASSIVES


class SneaselMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(SNEASEL_PASSIVES),
        "init": "_init_sneasel",
        "update": "_update_sneasel",
        "precheck": "_sneasel_precheck",
        "cast": "_sneasel_cast",
        "bot_cast": "_bot_sneasel_cast",
        # Rete (net/visual.py, game/online_world.py): cosa passa al client.
        "net": {
            "lists": {"claw_leaps": "c", "beatups": "pos", "sludge_lobs": "c"},
            "unit_flags": {"snatch_down": 0, "snatch_up": 0},
            "me": ("climb_ready_at",),
        },
    }

    def _init_sneasel(self) -> None:
        self.claw_leaps: list[dict] = []    # balzi: scavalcamento dei muri e Agguato dalla Rupe
        self.beatups: list[dict] = []       # Picchiaduro: raffica di colpi in corso
        self.sludge_lobs: list[dict] = []   # Sporcolancio: fango in volo e pozza a terra

    # --- dispatcher -----------------------------------------------------------
    def _sneasel_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"nightslash": self._cast_nightslash, "nightfall": self._cast_nightfall,
              "beatup": self._cast_beatup, "cliffambush": self._cast_cliffambush,
              "sludgelob": self._cast_sludgelob}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    def _sneasel_precheck(self, p, mv, tgt) -> bool:
        """Picchiaduro e Agguato senza un nemico valido (o lontano da un muro)
        non partono: la ricarica non si spende."""
        if mv.shape == "beatup":
            return self._claw_target(p, tgt, mv.range) is not None
        if mv.shape == "cliffambush":
            wr = float(mv.effects.get("wall_range", 2.0))
            return (self._near_wall(p.pos, wr + p.radius)
                    and self._claw_target(p, tgt, mv.range) is not None)
        return True

    def _sneasel_on_cast(self, p, mv) -> None:
        """Lanciare una mossa (tranne Notte Fonda stessa) dall'invisibilità la
        termina; il colpo d'agguato resta pronto per un istante, finché la
        mossa arriva a segno."""
        if p.nightfall_until > self.time and mv.shape != "nightfall":
            self._end_stealth(p, keep_ambush=True)

    def _claw_target(self, p, tgt, rng):
        """Il nemico vicino al mirino (Pokémon prima), entro la gittata."""
        best = None
        for pokemon_only in (True, False):
            best = self._foe_near(p, tgt, PICK, pokemon_only=pokemon_only)
            if best is not None and p.pos.dist(best.pos) <= rng + best.radius:
                return best
        return None

    # --- passiva: Sole e Luna ---------------------------------------------------
    def _track_gold(self, p, amount, source) -> None:
        """Oro guadagnato da `p`: dai minion o dai neutrali (Sole e Luna)."""
        if not isinstance(p, Pokemon) or p.passive_id != SUNMOON_ID or amount <= 0.0:
            return
        if source == "minion":
            p.gold_minion += amount
        else:
            p.gold_wild += amount

    # --- isolamento, critici, Arraffalesto, Notte Fonda -------------------------
    def _isolated(self, target) -> bool:
        """Isolato: nessun Pokémon alleato del bersaglio entro 5 tile. I neutrali
        non hanno alleati: sono sempre isolati."""
        if not isinstance(target, Pokemon):
            return isinstance(target, Wild)
        for q in self.world.pokemons():
            if (q is not target and q.team == target.team and q.alive and not q.is_decoy
                    and q.pos.dist(target.pos) <= ISOLATION_RANGE):
                return False
        return True

    def _ambush_on(self, p) -> bool:
        return isinstance(p, Pokemon) and (p.nightfall_until > self.time
                                           or p.ambush_until > self.time)

    def _sneasel_crit_bonus(self, caster) -> float:
        """Brutto colpo garantito: Nottesferza sugli isolati, primo colpo dalla
        Notte Fonda."""
        if getattr(caster, "_force_crit", False) or self._ambush_on(caster):
            return 1.0
        return 0.0

    def _sneasel_on_hit(self, caster, target) -> None:
        """Dopo un colpo a segno (attacco base o mossa) di un Pokémon nemico."""
        if (not isinstance(caster, Pokemon) or target.team == caster.team
                or getattr(caster, "_in_ambush", False)):
            return
        if self._ambush_on(caster) and caster.ambush_mv is not None:
            mv, rank = caster.ambush_mv
            self._end_stealth(caster)
            # Il colpo d'agguato: danno Buio fisico extra (brutto colpo garantito)
            # e rallentamento del 50% per 2 s (effects.slow della R).
            caster._force_crit = caster._in_ambush = True
            self._hit(caster, mv, rank, target)
            caster._force_crit = caster._in_ambush = False
            self.fx_events.append({"kind": "attack", "a": (caster.pos.x, caster.pos.y),
                                   "b": (target.pos.x, target.pos.y), "mtype": "Dark",
                                   "melee": True, "fx": "ambushhit"})
        if (caster.passive_id == SNATCH_ID and isinstance(target, Pokemon)
                and not target.is_decoy and self._isolated(target)):
            now = self.time
            target.snatch_down = min(SNATCH_MAX, target.snatch_down + 1)
            target.snatch_down_until = now + SNATCH_DUR
            caster.snatch_up = min(SNATCH_MAX, caster.snatch_up + 1)
            caster.snatch_up_until = now + SNATCH_DUR
            self.fx_events.append({"kind": "sync", "a": (target.pos.x, target.pos.y),
                                   "b": (caster.pos.x, caster.pos.y), "mtype": "Dark",
                                   "fx": "snatch"})

    def _sneasel_after_aa(self, u, tgt) -> None:
        self._sneasel_on_hit(u, tgt)

    def _end_stealth(self, p, keep_ambush=False) -> None:
        now = self.time
        if p.nightfall_until > now:
            if p.speed_until > now and p.speed_mult > 1.0:
                p.speed_until = now   # finisce anche il +30% di velocità
            p.nightfall_until = now
            p.invisible = p.memento_until > now
            self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "mtype": "Dark",
                                   "fx": "nightfallend", "radius": 0.9})
        p.ambush_until = now + 0.8 if keep_ambush else -1.0

    # --- W: Furto, Q di Sneasler: Dire Claw, cure ridotte ------------------------
    def _sneasel_hit_effects(self, caster, target, fx) -> None:
        if not fx:
            return
        sg = fx.get("steal_gold")
        if sg and isinstance(caster, Pokemon) and caster.team != target.team and not target.is_decoy:
            ready = caster.thief_cd.get(target.id, 0.0)
            amt = min(float(sg.get("amount", 10)), max(0.0, target.gold))
            if self.time >= ready and amt > 0.0:
                target.gold -= amt
                caster.gold += amt
                caster.thief_cd[target.id] = self.time + float(sg.get("cd", 10.0))
                self.fx_events.append({"kind": "sync", "a": (target.pos.x, target.pos.y),
                                       "b": (caster.pos.x, caster.pos.y), "mtype": "Dark",
                                       "fx": "goldsteal", "amount": int(round(amt))})
        dc = fx.get("direclaw")
        if dc and random.random() < float(dc.get("chance", 0.5)):
            dur = float(dc.get("duration", 2.0))
            kind = random.choice(("poison", "paralysis", "sleep"))
            if kind == "poison":
                self._apply_poison(target, caster, DIRECLAW_POISON * target.max_hp, dur)
            elif kind == "paralysis":
                self._apply_root(target, dur)
            else:
                self._apply_sleep(target, dur)
            self.fx_events.append({"kind": "area", "c": (target.pos.x, target.pos.y),
                                   "radius": 0.7, "mtype": "Poison", "fx": "direclaw_" + kind})
        hc = fx.get("healcut")
        if hc:
            self._apply_healcut(target, float(hc.get("mult", 0.5)), float(hc.get("duration", 6.0)))

    def _apply_healcut(self, p, mult, dur) -> None:
        """Cure ridotte: le cure ricevute sono moltiplicate per `mult`."""
        now = self.time
        p.healcut_mult = min(p.healcut_mult, mult) if p.healcut_until > now else mult
        p.healcut_until = max(p.healcut_until, now + dur)

    def _healcut_mult(self, p) -> float:
        return p.healcut_mult if getattr(p, "healcut_until", -1.0) > self.time else 1.0

    # --- Weavile: Nottesferza -----------------------------------------------------
    def _cast_nightslash(self, p, mv, rank, origin, tgt, dirv):
        """Fendente in linea retta: colpisce tutti i nemici sulla linea; sugli
        isolati è sempre un brutto colpo."""
        end = self._clamp_to_wall(origin, origin + dirv * mv.range)
        for e in self._combat_hash.query_radius((origin.x + end.x) / 2, (origin.y + end.y) / 2,
                                                mv.range / 2 + mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion, Wild)):
                continue
            if self._point_seg_dist(e.pos, origin, end) > mv.radius + e.radius:
                continue
            p._force_crit = self._isolated(e)
            self._hit(p, mv, rank, e)
            p._force_crit = False
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                               "b": (end.x, end.y), "mtype": mv.type})

    # --- Weavile: Notte Fonda -----------------------------------------------------
    def _cast_nightfall(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        dur = float(eff.get("duration", 4.0))
        p.nightfall_until = self.time + dur
        p.ambush_until = -1.0
        p.ambush_mv = (mv, rank)
        p.invisible = True
        p.aa_active = False
        p.target_id = None
        self._apply_speed(p, float(eff.get("speed", 1.3)), dur)
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "mtype": "Dark",
                               "radius": 1.0})

    # --- Weavile: Picchiaduro -----------------------------------------------------
    def _cast_beatup(self, p, mv, rank, origin, tgt, dirv):
        """Scatta sul nemico e lo colpisce 3 volte, +1 per ogni Pokémon alleato
        entro 8 tile."""
        e = self._claw_target(p, tgt, mv.range)
        if e is None:
            return
        eff = mv.effects
        allies = sum(1 for q in self.world.pokemons()
                     if q is not p and q.team == p.team and q.alive and not q.is_decoy
                     and q.pos.dist(p.pos) <= float(eff.get("ally_range", 8.0)))
        hits = int(eff.get("hits", 3)) + allies
        side = origin - e.pos
        side = side.normalized() if side.length() > 1e-6 else Vec2(-1.0, 0.0)
        off = side * (e.radius + p.radius + 0.1)
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                               "b": (e.pos.x + off.x, e.pos.y + off.y), "mtype": mv.type})
        p.pos = self._nearest_walkable(e.pos + off, e.pos)
        gap = float(eff.get("interval", 0.16))
        end = self.time + gap * hits
        self.beatups.append({"caster_id": p.id, "target_id": e.id, "team": p.team,
                             "mv": mv, "rank": rank, "start": self.time, "end": end,
                             "gap": gap, "hits": hits, "done": 0, "allies": allies,
                             "off": off, "pos": Vec2(e.pos.x, e.pos.y)})
        p.stop()
        p.aa_active = False
        p.channel_until = max(p.channel_until, end)
        p.root_until = max(p.root_until, end)

    def _update_beatups(self) -> None:
        now = self.time
        keep = []
        for bu in self.beatups:
            p = self.world.get(bu["caster_id"])
            t = self.world.get(bu["target_id"])
            ok_t = (t is not None and t.alive
                    and not (isinstance(t, Pokemon) and t.untargetable_until > now))
            if p is None or not p.alive or not ok_t or self._immobile(p):
                if p is not None:
                    p.channel_until = p.root_until = now
                continue
            p.pos = self._nearest_walkable(t.pos + bu["off"], t.pos)
            bu["pos"] = Vec2(t.pos.x, t.pos.y)
            while bu["done"] < bu["hits"] and now >= bu["start"] + bu["gap"] * bu["done"]:
                bu["done"] += 1
                self._hit(p, bu["mv"], bu["rank"], t)
                self.fx_events.append({"kind": "attack", "a": (p.pos.x, p.pos.y),
                                       "b": (t.pos.x, t.pos.y), "mtype": "Fighting",
                                       "melee": True, "fx": "beatuphit", "n": bu["done"],
                                       "ally": bu["done"] > bu["hits"] - bu["allies"]})
                if not t.alive:
                    break
            if bu["done"] < bu["hits"] and t.alive:
                keep.append(bu)
            else:
                p.channel_until = p.root_until = now
        self.beatups = keep

    # --- Sneasler: Agguato dalla Rupe ----------------------------------------------
    def _near_wall(self, c, r) -> bool:
        """Vero se un tile di muro (giungla o confine) è entro `r` da `c`."""
        g = self.world.grid
        ri = int(r) + 1
        for ty in range(int(c.y) - ri, int(c.y) + ri + 1):
            for tx in range(int(c.x) - ri, int(c.x) + ri + 1):
                if g.tile_at(tx, ty) not in (TILE_JUNGLE_WALL, TILE_WALL):
                    continue
                dx = max(tx - c.x, 0.0, c.x - (tx + 1))
                dy = max(ty - c.y, 0.0, c.y - (ty + 1))
                if dx * dx + dy * dy <= r * r:
                    return True
        return False

    def _near_border_wall(self, c) -> bool:
        """Vero se un tile del muro di CONFINE e' entro 2 tile da `c`: un punto
        della sagoma disegnata fuori dal suo tile puo' appartenere a lui."""
        g = self.world.grid
        for ty in range(int(c.y) - 1, int(c.y) + 3):
            for tx in range(int(c.x) - 2, int(c.x) + 3):
                if g.tile_at(tx, ty) == TILE_WALL:
                    return True
        return False

    def _cast_cliffambush(self, p, mv, rank, origin, tgt, dirv):
        """Balzo dalla parete su un nemico entro 10 tile: lo insegue in volo e
        all'atterraggio lo colpisce e lo stordisce."""
        e = self._claw_target(p, tgt, mv.range)
        if e is None:
            return
        dur = float(mv.effects.get("leap_time", 0.6))
        self._start_claw_leap(p, origin, self._ambush_spot(p, e, origin), dur, 1.5,
                              "ambush", mv=mv, rank=rank, target_id=e.id)

    def _ambush_spot(self, p, e, origin):
        side = origin - e.pos
        side = side.normalized() if side.length() > 1e-6 else Vec2(-1.0, 0.0)
        return self._nearest_walkable(e.pos + side * (e.radius + p.radius * 0.6), e.pos)

    def _land_ambush(self, p, lp) -> None:
        mv, rank = lp["mv"], lp["rank"]
        e = self.world.get(lp["target_id"]) if lp["target_id"] is not None else None
        c = p.pos
        if e is not None and e.alive and p.pos.dist(e.pos) <= e.radius + p.radius + 1.0:
            self._hit(p, mv, rank, e)   # danno + stordimento (effects.stun)
            c = e.pos
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": "cliffambushland"})

    # --- Sneasler: Sporcolancio ------------------------------------------------------
    def _cast_sludgelob(self, p, mv, rank, origin, tgt, dirv):
        to = tgt - origin
        c = (origin + to.normalized() * min(to.length(), mv.range)
             if to.length() > 1e-6 else Vec2(origin.x, origin.y))
        fl = float(mv.effects.get("flight", 0.6))
        self.sludge_lobs.append({"a": Vec2(origin.x, origin.y), "c": c, "radius": mv.radius,
                                 "team": p.team, "caster_id": p.id, "mv": mv, "rank": rank,
                                 "start": self.time, "land": self.time + fl,
                                 "end": self.time + fl + 1.6, "done": False})

    def _update_lobs(self) -> None:
        now = self.time
        keep = []
        for lb in self.sludge_lobs:
            if not lb["done"] and now >= lb["land"]:
                lb["done"] = True
                p = self.world.get(lb["caster_id"])
                c = lb["c"]
                if p is not None:
                    for e in self._combat_hash.query_radius(c.x, c.y, lb["radius"] + 1.0):
                        if e.team == lb["team"] or not getattr(e, "alive", False):
                            continue
                        if (isinstance(e, (Pokemon, Minion, Wild))
                                and c.dist(e.pos) <= lb["radius"] + e.radius):
                            self._hit(p, lb["mv"], lb["rank"], e)   # veleno + cure ridotte
                self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": lb["radius"],
                                       "mtype": "Poison", "fx": "sludgelobhit"})
            if now < lb["end"]:
                keep.append(lb)
        self.sludge_lobs = keep

    # --- Sneasler: Scalaroccia -------------------------------------------------------
    def _sneasel_wild_mult(self, attacker, target) -> float:
        if (isinstance(target, Wild) and isinstance(attacker, Pokemon)
                and attacker.passive_id == CLIMB_ID):
            return CLIMB_WILD_MULT
        return 1.0

    def _climb_plan(self, p, d, limit):
        """Se davanti a `p` (direzione `d`) c'è un muro della giungla spesso al
        massimo 3 tile con terreno libero dietro, il punto d'atterraggio."""
        g = self.world.grid
        pos = p.pos
        step = 0.1
        s = 0.0
        reach = p.radius + CLIMB_REACH
        d0 = None
        while s <= reach:
            pt = pos + d * s
            if not g.is_walkable_point(pt.x, pt.y):
                d0 = s
                break
            s += step
        if d0 is None:
            return None
        s = d0
        while True:
            pt = pos + d * s
            if g.is_walkable_point(pt.x, pt.y):
                break
            t = g.tile_at(int(pt.x), int(pt.y))
            if t != TILE_JUNGLE_WALL and not (t != TILE_WALL and g.shape_blocked(pt.x, pt.y)
                                              and not self._near_border_wall(pt)):
                return None   # muro di confine, fiume, pilastro...: niente
            s += step
            if s - d0 > CLIMB_MAX:
                return None   # troppo spesso
        if s >= limit:
            return None       # la destinazione è dentro il muro
        for extra in (0.3, 0.5, 0.7, 0.9):
            land = pos + d * (s + p.radius * 0.5 + extra)
            if g.is_walkable_point(land.x, land.y):
                return land
        return None

    def _update_climb(self, p) -> None:
        now = self.time
        if (now < p.climb_ready_at or not p.moving or not p.path or self._immobile(p)
                or p.root_until > now or p.channel_until > now or p.dashlock_until > now):
            return
        dest = p.path[-1]
        to = dest - p.pos
        L = to.length()
        if L < 1.0:
            return
        # Solo se il percorso aggira davvero un muro (molto più lungo della retta).
        route, prev = 0.0, p.pos
        for w in p.path:
            route += prev.dist(w)
            prev = w
        if route < L * 1.2 + 0.8:
            return
        land = self._climb_plan(p, to.normalized(), L)
        if land is None:
            return
        p.climb_ready_at = now + CLIMB_CD
        self._start_claw_leap(p, p.pos, land, CLIMB_TIME, CLIMB_PEAK, "climb", dest=dest)

    # --- balzi (scavalcamento e Agguato) ----------------------------------------------
    def _start_claw_leap(self, p, a, b, dur, peak, kind, mv=None, rank=0, target_id=None,
                         dest=None) -> None:
        p.stop()
        p.aa_active = False
        p.recalling = False
        p.stun_until = max(p.stun_until, self.time + dur)   # in volo: niente azioni
        if kind == "climb":
            self._apply_untargetable(p, dur)
        self.claw_leaps.append({"pid": p.id, "a": Vec2(a.x, a.y), "c": Vec2(b.x, b.y),
                                "start": self.time, "end": self.time + dur, "peak": peak,
                                "team": p.team, "kind": kind, "mv": mv, "rank": rank,
                                "target_id": target_id, "dest": dest})
        self.fx_events.append({"eid": p.id, "anim": "Hop", "anim_speed": 1.0 / max(0.2, dur)})
        self.fx_events.append({"kind": "dash", "a": (a.x, a.y), "b": (b.x, b.y),
                               "mtype": "Rock" if kind == "ambush" else "Fighting",
                               "fx": "cliffambushjump" if kind == "ambush" else "climbjump"})

    def _update_claw_leaps(self) -> None:
        now = self.time
        keep = []
        for lp in self.claw_leaps:
            p = self.world.get(lp["pid"])
            if p is None or not p.alive:
                continue
            if lp["kind"] == "ambush":   # insegue il bersaglio mentre è in volo
                e = self.world.get(lp["target_id"])
                if e is not None and e.alive:
                    lp["c"] = self._ambush_spot(p, e, lp["a"])
            span = max(1e-6, lp["end"] - lp["start"])
            t = min(1.0, (now - lp["start"]) / span)
            a, b = lp["a"], lp["c"]
            p.pos = Vec2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)
            p.air_z = lp["peak"] * 4.0 * t * (1.0 - t)
            p.stop()
            if t < 1.0:
                keep.append(lp)
                continue
            p.air_z = 0.0
            p.pos = Vec2(b.x, b.y)
            if lp["kind"] == "ambush":
                self._land_ambush(p, lp)
            else:
                self._resume_path(p, lp["dest"])
                self.fx_events.append({"kind": "area", "c": (b.x, b.y), "radius": 0.6,
                                       "mtype": "Rock", "fx": "climbland"})
        self.claw_leaps = keep

    def _resume_path(self, p, dest) -> None:
        """Dopo lo scavalcamento riprende verso la destinazione."""
        if dest is None:
            return
        g = self.world.grid
        if g.line_of_sight(p.pos.x, p.pos.y, dest.x, dest.y):
            p.set_path([Vec2(dest.x, dest.y)])
            return
        tiles = find_path(g, (int(p.pos.x), int(p.pos.y)), (int(dest.x), int(dest.y)))
        if tiles:
            p.set_path([Vec2(x, y) for (x, y) in smooth_path(g, tiles)[1:]] or [dest])

    # --- aggiornamento ------------------------------------------------------------------
    def _update_sneasel(self, dt: float) -> None:
        now = self.time
        if self.claw_leaps:
            self._update_claw_leaps()
        if self.beatups:
            self._update_beatups()
        if self.sludge_lobs:
            self._update_lobs()
        for p in self.world.pokemons():
            if p.snatch_down and now > p.snatch_down_until:
                p.snatch_down = 0
            if p.snatch_up and now > p.snatch_up_until:
                p.snatch_up = 0
            if p.nightfall_until > 0.0 and (now >= p.nightfall_until or not p.alive):
                p.nightfall_until = -1.0   # scaduta (o morto): torna visibile
                p.invisible = p.memento_until > now
            if p.passive_id == CLIMB_ID and p.alive:
                self._update_climb(p)

    # --- bot ------------------------------------------------------------------------------
    def _bot_sneasel_cast(self, p, target) -> bool:
        """I bot usano Notte Fonda quando sono vicini al bersaglio, Picchiaduro
        e Agguato quando è a tiro."""
        ms = p.moveset.get("R")
        if not (ms and ms.ready and ms.chosen):
            return False
        mv = ms.chosen
        d = p.pos.dist(target.pos)
        if mv.shape == "nightfall" and d <= 6.0 and isinstance(target, Pokemon):
            p.pending_cast = ("R", p.pos.x, p.pos.y)
            return True
        if mv.shape in ("beatup", "cliffambush", "sludgelob") and d <= mv.range:
            if mv.shape == "cliffambush" and not self._near_wall(p.pos, 2.0 + p.radius):
                return False
            p.pending_cast = ("R", target.pos.x, target.pos.y)
            return True
        return False
