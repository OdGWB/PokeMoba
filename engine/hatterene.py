"""Regole della linea Hatenna > Hattrem > Hatterene (mago di controllo da mid
lane: lento, senza scatti, forte contro chi lo attacca).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Archaludon e
Mienshao. Il client legge le liste del Match (hatt_marks, moon_orbs,
trick_rooms, witch_waves) e i campi delle unità (agitated_until, agitated,
powder_until) per disegnare.

Passiva Quiete (stesso id per le tre forme):
  - un Pokémon nemico che lancia una mossa entro 10 tile da un Pokémon della
    linea diventa AGITATO per 3 s (icona sopra la barra della vita);
  - i nemici agitati sono visibili alla squadra della linea anche nei
    cespugli (VisionSystem: campo `agitated` dell'unità) e subiscono +10% di
    danno dalle mosse della linea.
Mosse: Confusione (area a distanza che scatta dopo 0,5 s e confonde;
Psicoshock = mitigata dalla Difesa, Psicoraggio = raggio dritto di 10 tile),
Incantavoce (onda attorno a sé che respinge di 3 tile; Magipolvere = niente
respinta, i nemici colpiti diventano di tipo Psico per 4 s; Assorbibacio =
cura del 50% del danno), Forza Lunare (sfera lenta che stordisce il primo
colpito; Magifiamma = Fuoco e -25% Att. Sp.; Forza Lunare + = esplode in
un'area di 2 tile), R Distortozona (area di 6 s: Velocità base < 70 -> +40%
velocità, > 70 -> -40%, per tutti) o Strega della Foresta (onda di 7 tile dopo
0,75 s; gli agitati subiscono più danno e sono storditi).
"""
from __future__ import annotations

from .entities import Minion, Pokemon, Structure, Wild
from .vec import Vec2

QUIET_ID = "quiete"
HATT_PASSIVES = {QUIET_ID}

AGITATE_RANGE = 10.0          # tile: un nemico che lancia una mossa entro questa distanza...
AGITATE_DUR = 3.0             # ...resta agitato per 3 s
AGITATED_MULT = 1.10          # +10% di danno dalle mosse della linea
TRICK_SPEED_LINE = 70.0       # Distortozona: soglia della Velocità base
TRICK_FAST = 1.4              # sotto la soglia: +40%
TRICK_SLOW = 0.6              # sopra la soglia: -40%


def is_hatt_line(p) -> bool:
    return getattr(p, "passive_id", None) in HATT_PASSIVES


class HattereneMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(HATT_PASSIVES),
        "init": "_init_hatt",
        "update": "_update_hatt",
        "cast": "_hatt_cast",
        "bot_cast": "_bot_hatt_cast",
        "speed_mult": "_hatt_speed_mult",
        # Rete (net/visual.py, game/online_world.py): cosa passa al client.
        "net": {
            "lists": {"hatt_marks": "c", "moon_orbs": "pos", "witch_waves": "c"},
            "shared": ("trick_rooms",),
            "moving": ("moon_orbs",),
            "unit_flags": {"agitated": False},
        },
    }

    def _init_hatt(self) -> None:
        self.hatt_marks: list[dict] = []    # Confusione: aree che scattano dopo il ritardo
        self.moon_orbs: list[dict] = []     # Forza Lunare: sfere lente in volo
        self.trick_rooms: list[dict] = []   # Distortozona: aree attive (visibili a tutti)
        self.witch_waves: list[dict] = []   # Strega della Foresta: onda in carica

    # --- dispatcher -------------------------------------------------------------
    def _hatt_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"psyburst": self._cast_psyburst, "psybeam": self._cast_psybeam,
              "hattvoice": self._cast_hattvoice, "moonorb": self._cast_moonorb,
              "trickroom": self._cast_trickroom,
              "witchwave": self._cast_witchwave}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    # --- passiva: Quiete ----------------------------------------------------------
    def _hatt_on_cast(self, p) -> None:
        """Un Pokémon ha appena lanciato una mossa: se è entro 10 tile da un
        Pokémon nemico della linea, diventa agitato."""
        for h in self.world.pokemons():
            if (h.team != p.team and h.alive and is_hatt_line(h)
                    and h.pos.dist(p.pos) <= AGITATE_RANGE):
                if p.agitated_until <= self.time:
                    self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y),
                                           "radius": 0.6, "mtype": "Psychic",
                                           "fx": "agitate", "eid2": p.id})
                p.agitated_until = self.time + AGITATE_DUR
                p.agitated = True
                return

    def _hatt_dmg_mult(self, caster, target, mv) -> float:
        """+10% sugli agitati (mosse della linea) e danno extra di Strega della
        Foresta sugli agitati."""
        if (not isinstance(caster, Pokemon) or not is_hatt_line(caster)
                or not isinstance(target, Pokemon) or target.agitated_until <= self.time):
            return 1.0
        return AGITATED_MULT * float(mv.effects.get("agitated_bonus", 1.0))

    def _hatt_hit_effects(self, caster, target, fx) -> None:
        """Magifiamma: Att. Sp. del bersaglio ridotta (stesso stato di Dragobolide)."""
        sd = fx.get("spa_down_target")
        if sd and caster.team != target.team:
            mult = float(sd.get("mult", 0.75))
            if target.spa_down_until > self.time:
                mult = min(mult, target.spa_down_mult)
            target.spa_down_mult = mult
            target.spa_down_until = max(target.spa_down_until,
                                        self.time + float(sd.get("duration", 4.0)))

    def _hatt_speed_mult(self, p) -> float:
        """Distortozona: chi sta dentro un'area cambia velocità secondo la sua
        Velocità base (sotto 70 più veloce, sopra 70 più lento)."""
        if not self.trick_rooms:
            return 1.0
        spd = float(p.base_stats.speed)
        if spd == TRICK_SPEED_LINE:
            return 1.0
        for z in self.trick_rooms:
            if z["c"].dist(p.pos) <= z["radius"]:
                return TRICK_FAST if spd < TRICK_SPEED_LINE else TRICK_SLOW
        return 1.0

    # --- utilità ------------------------------------------------------------------
    def _hatt_enemies(self, p, c, r):
        """Nemici colpibili (campioni, minion, neutrali, strutture) entro r da c."""
        out = []
        for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if c.dist(e.pos) > r + getattr(e, "radius", 0.0):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            out.append(e)
        return out

    def _hatt_clamp(self, origin, tgt, rng):
        to = tgt - origin
        if to.length() > rng:
            return origin + to.normalized() * rng
        return Vec2(tgt.x, tgt.y)

    def _hatt_push(self, origin, e, dist) -> None:
        """Respinge `e` lontano da `origin` di `dist` tile (fermato dai muri)."""
        if (not e.alive or not isinstance(e, (Pokemon, Minion))
                or (isinstance(e, Pokemon) and self._cc_immune(e))):
            return
        away = e.pos - origin
        if away.length() < 1e-6:
            away = Vec2(1.0, 0.0)
        if isinstance(e, Pokemon) and "iron_ball" in self._fx_items(e):
            from .item_effects import IRONBALL_MULT
            dist *= IRONBALL_MULT
        dist *= self._octi_disp_mult(e)   # Ventose
        a = Vec2(e.pos.x, e.pos.y)
        dest = self._clamp_to_wall(a, a + away.normalized() * dist)
        e.pos = dest
        e.stop()
        if isinstance(e, Pokemon):
            e.aa_active = False
            e.recalling = False
        self.fx_events.append({"kind": "dash", "a": (a.x, a.y), "b": (dest.x, dest.y),
                               "mtype": "Fairy", "fx": "voicepush"})

    # --- Q: Confusione / Psicoshock ---------------------------------------------------
    def _cast_psyburst(self, p, mv, rank, origin, tgt, dirv):
        """Area a distanza: dopo 0,5 s danneggia e confonde chi è dentro."""
        c = self._hatt_clamp(origin, tgt, mv.range)
        delay = float(mv.effects.get("delay", 0.5))
        self.hatt_marks.append({"c": c, "radius": mv.radius, "team": p.team,
                                "caster_id": p.id, "start": self.time,
                                "at": self.time + delay, "mv": mv, "rank": rank,
                                "shock": bool(mv.d.get("vs_defense"))})
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": "psycast"})

    def _update_hatt_marks(self) -> None:
        now = self.time
        keep = []
        for z in self.hatt_marks:
            if now < z["at"]:
                keep.append(z)
                continue
            p = self.world.get(z["caster_id"])
            if p is None:
                continue
            for e in self._hatt_enemies(p, z["c"], z["radius"]):
                self._hit(p, z["mv"], z["rank"], e)
            self.fx_events.append({"kind": "area", "c": (z["c"].x, z["c"].y),
                                   "radius": z["radius"], "mtype": "Psychic",
                                   "fx": "psyburst", "shock": z["shock"]})
        self.hatt_marks = keep

    # --- Q: Psicoraggio --------------------------------------------------------------
    def _cast_psybeam(self, p, mv, rank, origin, tgt, dirv):
        """Raggio dritto di 10 tile: danneggia e confonde tutti i nemici
        attraversati (si ferma contro un muro)."""
        end = self._clamp_to_wall(origin, origin + dirv * mv.range)
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
                if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                    continue
                self._hit(p, mv, rank, e)
        self.fx_events.append({"kind": "beam", "a": (origin.x, origin.y), "b": (end.x, end.y),
                               "c": (mid.x, mid.y), "mtype": mv.type, "fx": "psybeam",
                               "radius": mv.radius})

    # --- W: Incantavoce / Magipolvere / Assorbibacio -----------------------------------
    def _cast_hattvoice(self, p, mv, rank, origin, tgt, dirv):
        """Onda attorno a sé: danno e respinta di 3 tile (Magipolvere: niente
        respinta, i nemici colpiti diventano di tipo Psico per 4 s)."""
        eff = mv.effects
        push = float(eff.get("push", 0.0))
        powder = float(eff.get("psychic_type", 0.0))
        heal = "heal_self_ratio" in eff
        hit = self._hatt_enemies(p, origin, mv.radius)
        for e in hit:
            self._hit(p, mv, rank, e)
            if heal:   # Assorbibacio: cuoricini dal colpito a chi si cura
                self.fx_events.append({"kind": "buff", "a": (e.pos.x, e.pos.y),
                                       "b": (p.pos.x, p.pos.y), "c": (p.pos.x, p.pos.y),
                                       "mtype": "Fairy", "fx": "kissheal"})
            if not e.alive:
                continue
            if powder > 0.0 and isinstance(e, Pokemon):
                self._hatt_powder(e, powder)
            if push > 0.0:
                self._hatt_push(origin, e, push)
        self.fx_events.append({"kind": "area", "c": (origin.x, origin.y),
                               "radius": mv.radius, "mtype": mv.type,
                               "fx": mv.fx or "hattvoice"})

    def _hatt_powder(self, e, dur) -> None:
        """Magipolvere: i tipi del bersaglio diventano solo Psico (debolezze,
        resistenze e STAB) fino alla fine; poi tornano quelli di prima."""
        if e.powder_until <= self.time:
            e.powder_types = list(e.types)
            e.powder_dex = e.dex
        e.types = ["Psychic"]
        e.powder_until = self.time + dur

    def _update_powder(self) -> None:
        now = self.time
        for e in self.world.pokemons():
            if e.powder_types is not None and e.powder_until <= now:
                # Se nel frattempo si è evoluto il tipo l'ha già scritto l'evoluzione.
                if e.dex == e.powder_dex and e.types == ["Psychic"]:
                    e.types = list(e.powder_types)
                e.powder_types = None

    # --- E: Forza Lunare / Magifiamma / Forza Lunare + ------------------------------------
    def _cast_moonorb(self, p, mv, rank, origin, tgt, dirv):
        """Sfera lenta a lunga distanza: stordisce il primo nemico colpito (o
        esplode in un'area con Forza Lunare +)."""
        eff = mv.effects
        self.moon_orbs.append({"pos": Vec2(origin.x, origin.y), "origin": Vec2(origin.x, origin.y),
                               "dir": Vec2(dirv.x, dirv.y), "left": mv.range,
                               "speed": float(eff.get("orb_speed", 7.0)), "radius": mv.radius,
                               "team": p.team, "caster_id": p.id, "mv": mv, "rank": rank,
                               "mtype": mv.type, "burst": float(eff.get("burst", 0.0)),
                               "born": self.time})

    def _update_moon_orbs(self, dt: float) -> None:
        keep = []
        grid = self.world.grid
        for o in self.moon_orbs:
            step = o["speed"] * dt
            o["pos"] = o["pos"] + o["dir"] * step
            o["left"] -= step
            pos = o["pos"]
            if not grid.is_walkable_point(pos.x, pos.y):
                self._moon_pop(o, None)          # contro un muro: si spegne / esplode
                continue
            hit = None
            for e in self._combat_hash.query_radius(pos.x, pos.y, o["radius"] + 1.0):
                if e.team == o["team"] or not getattr(e, "alive", False):
                    continue
                if not isinstance(e, (Pokemon, Minion, Structure, Wild)):
                    continue
                if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                    continue
                if pos.dist(e.pos) <= o["radius"] + getattr(e, "radius", 0.0):
                    hit = e
                    break
            if hit is not None:
                self._moon_pop(o, hit)
                continue
            if o["left"] > 0:
                keep.append(o)
            elif o["burst"] > 0.0:
                self._moon_pop(o, None)          # Forza Lunare +: esplode a fine corsa
        self.moon_orbs = keep

    def _moon_pop(self, o, hit) -> None:
        p = self.world.get(o["caster_id"])
        c = o["pos"]
        mv = o["mv"]
        br = o["burst"]
        if p is not None:
            if br > 0.0:
                for e in self._hatt_enemies(p, c, br):
                    self._hit(p, mv, o["rank"], e)
            elif hit is not None:
                self._hit(p, mv, o["rank"], hit)
        if hit is not None and br <= 0.0:
            c = Vec2(hit.pos.x, hit.pos.y)      # l'impatto si disegna sul colpito
        if hit is None and br <= 0.0:
            self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": 0.5,
                                   "mtype": o["mtype"], "fx": "moonfizzle"})
            return
        self.fx_events.append({"kind": "area", "c": (c.x, c.y),
                               "radius": br if br > 0.0 else o["radius"],
                               "mtype": o["mtype"], "fx": "moonhit", "burst": br > 0.0,
                               "fire": mv.type == "Fire"})

    # --- R: Distortozona ---------------------------------------------------------------
    def _cast_trickroom(self, p, mv, rank, origin, tgt, dirv):
        """Grande area per 6 s (visibile a tutti): dentro, chi ha Velocità base
        sotto 70 va più veloce del 40%, chi l'ha sopra più lento del 40%."""
        c = self._hatt_clamp(origin, tgt, mv.range)
        dur = float(mv.effects.get("duration", 6.0))
        self.trick_rooms.append({"c": c, "radius": mv.radius, "team": p.team,
                                 "caster_id": p.id, "start": self.time,
                                 "end": self.time + dur})
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": "trickroom"})

    # --- R: Strega della Foresta -------------------------------------------------------
    def _cast_witchwave(self, p, mv, rank, origin, tgt, dirv):
        """Dopo 0,75 s onda psichica attorno a sé (dove si trova in quel
        momento): danno a tutti i nemici, extra e stordimento sugli agitati."""
        delay = float(mv.effects.get("delay", 0.75))
        self.witch_waves.append({"c": Vec2(p.pos.x, p.pos.y), "radius": mv.radius,
                                 "team": p.team, "caster_id": p.id, "start": self.time,
                                 "at": self.time + delay, "mv": mv, "rank": rank})

    def _update_witch_waves(self) -> None:
        now = self.time
        keep = []
        for w in self.witch_waves:
            p = self.world.get(w["caster_id"])
            if p is None or not p.alive:
                continue                          # abbattuta prima dell'onda: annullata
            w["c"] = Vec2(p.pos.x, p.pos.y)       # l'onda parte da dove si trova
            if now < w["at"]:
                keep.append(w)
                continue
            mv = w["mv"]
            stun = float(mv.effects.get("agitated_stun", 1.5))
            for e in self._hatt_enemies(p, w["c"], w["radius"]):
                agit = isinstance(e, Pokemon) and e.agitated_until > now
                self._hit(p, mv, w["rank"], e)
                if agit and e.alive:
                    self._apply_stun(e, stun)
                    self.fx_events.append({"kind": "buff", "c": (e.pos.x, e.pos.y),
                                           "radius": 0.6, "mtype": "Psychic",
                                           "fx": "witchstun"})
            self.fx_events.append({"kind": "area", "c": (w["c"].x, w["c"].y),
                                   "radius": w["radius"], "mtype": "Psychic",
                                   "fx": "witchwave"})
            self.fx_events.append({"eid": p.id, "anim": "Strike"})
        self.witch_waves = keep

    # --- aggiornamento ------------------------------------------------------------------
    def _update_hatt(self, dt: float) -> None:
        now = self.time
        if self.hatt_marks:
            self._update_hatt_marks()
        if self.moon_orbs:
            self._update_moon_orbs(dt)
        if self.witch_waves:
            self._update_witch_waves()
        if self.trick_rooms:
            self.trick_rooms = [z for z in self.trick_rooms if z["end"] > now]
        self._update_powder()
        for e in self.world.pokemons():
            e.agitated = e.alive and e.agitated_until > now

    # --- IA (bot) ---------------------------------------------------------------------
    def _bot_hatt_cast(self, p, target) -> bool:
        """Bot della linea: controllo dalla distanza, Incantavoce per staccarsi."""
        d = p.pos.dist(target.pos)
        tp = (target.pos.x, target.pos.y)
        champ = isinstance(target, Pokemon)
        ms = p.moveset.get("R")
        if ms is not None and ms.ready and ms.chosen is not None and champ:
            sh = ms.chosen.shape
            if sh == "witchwave" and d <= ms.chosen.radius * 0.8:
                p.pending_cast = ("R", *tp)
                return True
            if sh == "trickroom" and d <= 7.0:
                # Hatterene è lenta: la zona la aiuta se il nemico è più veloce.
                mid = Vec2((p.pos.x + target.pos.x) * 0.5, (p.pos.y + target.pos.y) * 0.5)
                p.pending_cast = ("R", mid.x, mid.y)
                return True
        ms = p.moveset.get("W")
        if ms is not None and ms.ready and ms.chosen is not None and d <= ms.chosen.radius:
            p.pending_cast = ("W", *tp)
            return True
        ms = p.moveset.get("E")
        if ms is not None and ms.ready and ms.chosen is not None and d <= ms.chosen.range * 0.9:
            p.pending_cast = ("E", *tp)
            return True
        ms = p.moveset.get("Q")
        if ms is not None and ms.ready and ms.chosen is not None and d <= ms.chosen.range:
            p.pending_cast = ("Q", *tp)
            return True
        return False
