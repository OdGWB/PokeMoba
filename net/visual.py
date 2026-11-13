"""STATO VISIVO per squadra (lato host): ciò che la partita offline disegna
leggendo il Match e che lo snapshot non porta.

Lo snapshot (net/snapshot.py) basta per muovere e colpire; gli EVENTI FX
(S_FX) portano i lampi istantanei. Restano fuori le cose che DURANO e che la
scena offline ridisegna a ogni frame dallo stato del motore:
- stati sulle unità (sonno, veleno, radici, congelato, affascinato, in aria,
  invisibile, Acidarmatura, tempesta di sabbia...): tutti i campi *_until;
- effetti persistenti del Match (bolle in volo, valanghe di Frana, ondata
  della Legione, legami di Malcomune, raggi spiritici, Tuono, Bora,
  Divinazione, Desiderio, Comete, nubi della Palla Fumo);
- pilastri di Rocciotomba e spiriti di Spiritomb (world.pillars/spirits);
- Pokémon a terra (anello di respawn, animazione di morte);
- per il proprio Pokémon: ricarica degli oggetti attivabili, passive, cariche.

Lo stesso filtro di visione dello snapshot: della squadra avversaria passa
solo ciò che sta su un tile che la squadra vede (come `seen` in MatchScene).
Il pacchetto (R_VIS, canale reliable) parte solo quando cambia.
"""
from __future__ import annotations

import dataclasses

from engine.entities import Minion, Pokemon, Wild
from engine.lines import net_table

SLOTS = ["Q", "W", "E", "R"]

# Le tabelle qui sotto uniscono la parte COMUNE (mosse generiche del motore e
# linee scritte direttamente in engine/match.py) e quella dichiarata da ogni
# linea nel suo LINE["net"] (engine/lines.py). Una linea nuova NON si aggiunge qui.

# Liste del Match: nome -> (chiave della posizione, chiave della squadra).
LISTS = {
    "projectiles": ("pos", "team"), "avalanches": ("pos", "team"),
    "item_clouds": ("center", "team"),
    **{name: (pk, "team") for name, pk in net_table("lists").items()},
}
# Liste che vedono entrambe le squadre (aree d'effetto da evitare, ostacoli...).
SHARED = net_table("shared")
# Liste prese a mano in capture_visual (regole di visibilità particolari).
CUSTOM = ("pain_binds", "wishes", "bear_leaps", "swine_tracks")
# Tutte le liste che il client riceve (game/online_world.py le tiene in fxs).
ALL_LISTS = (*LISTS, *SHARED, *CUSTOM)
# Liste con pos/dir/speed che il client fa avanzare tra un pacchetto e l'altro.
MOVING = ("projectiles", "avalanches", *net_table("moving"))
# Campi solo di logica (oggetti del motore, insiemi di bersagli già colpiti).
SKIP = {"mv", "hit", "touched", "since", "rank", "explode", "first", "caught", "slept", "freed", "rel",
        "_pts"}
# Stati sulle unità che non sono timer *_until (valore "spento" a destra).
UNIT_FLAGS = {"air_z": 0.0, "sand_radius": 0.0, "invisible": False, "submerged": False,
              "smoke_hidden": False, **net_table("unit_flags")}
# Il proprio Pokémon: passive e ricariche mostrate nell'interfaccia.
ME_FIELDS = tuple(dict.fromkeys((
    "passive_id", "soul_charges", "inversion_stacks", "muta_cd_until", "muta_cd_max",
    "form_until", "sandstorm_boost_until", "sand_radius", "recalling", "recall_until",
    "respawn_timer", *net_table("me"))))

_timer_fields: dict = {}


def timer_fields(cls) -> tuple:
    """Campi float dell'entità che sono istanti di fine (…_until, …_ready_at)."""
    if cls not in _timer_fields:
        _timer_fields[cls] = tuple(
            f.name for f in dataclasses.fields(cls)
            if f.name.endswith(("_until", "_ready_at")) and isinstance(f.default, (int, float)))
    return _timer_fields[cls]


def _unit_state(e, now) -> dict:
    out = {}
    for name in timer_fields(type(e)):
        v = getattr(e, name, -1.0)
        if v > now:
            out[name] = float(v)
    for name, off in UNIT_FLAGS.items():
        v = getattr(e, name, off)
        if v != off:
            out[name] = v
    return out


def _clean(d) -> dict:
    return {k: v for k, v in d.items() if k not in SKIP}


def capture_visual(match, team: int, player=None) -> dict:
    world, vis, now = match.world, match.vision, match.time

    def seen(pos, t=None):
        return t == team or vis.is_tile_visible(team, int(pos.x), int(pos.y))

    units = {}
    for e in world.entities.values():
        if isinstance(e, (Pokemon, Minion, Wild)) and e.alive and (
                e.team == team or vis.is_enemy_visible(team, e.id)):
            st = _unit_state(e, now)
            if st:
                units[e.id] = st
    out = {"u": units}
    for name, (pk, tk) in LISTS.items():
        items = [_clean(d) for d in getattr(match, name, ())
                 if pk in d and seen(d[pk], d.get(tk))]
        if items:
            out[name] = items
    binds = []
    for bd in getattr(match, "pain_binds", ()):
        c = world.get(bd["caster_id"])
        if c is not None and seen(c.pos, c.team):
            binds.append(_clean(bd))
    if binds:
        out["pain_binds"] = binds
    wishes = []
    for w in getattr(match, "wishes", ()):
        t = world.get(w["target_id"])
        if t is not None and seen(t.pos, t.team):
            wishes.append(_clean(w))
    if wishes:
        out["wishes"] = wishes
    # Liste che vedono tutti (LINE["net"]["shared"]): Taxi Volante, carica di
    # Elettroraggio, Distortozona, cariche sui muri, fiori, schegge...
    for name in SHARED:
        items = [_clean(d) for d in getattr(match, name, ())]
        if items:
            out[name] = items
    # Fiuto (linea Swinub): le impronte dei nemici le vede SOLO la squadra che
    # fiuta, anche nella nebbia.
    tracks = [{"pos": d["pos"], "t": round(d["t"], 2), "dir": d["dir"], "side": d["side"],
               "big": d["big"], "viewer": d["viewer"]}
              for d in getattr(match, "swine_tracks", ()) if d.get("viewer") == team]
    if tracks:
        out["swine_tracks"] = tracks
    # Balzi della linea Teddiursa: l'atterraggio di Luna Piena lo vedono tutti.
    leaps = [_clean(lp) for lp in getattr(match, "bear_leaps", ())
             if lp.get("fx") == "fullmoon" or seen(lp["c"], lp["team"])]
    if leaps:
        out["bear_leaps"] = leaps
    pillars = [{"pos": pl.pos, "tx": pl.tx, "ty": pl.ty, "team": pl.team, "born": pl.born,
                "until": pl.until, "radius": pl.radius}
               for pl in getattr(world, "pillars", ())]
    if pillars:
        out["pillars"] = pillars
    spirits = [{"pos": sp.pos, "owner_id": sp.owner_id, "team": sp.team, "born": sp.born,
                "seed": sp.seed}
               for sp in getattr(world, "spirits", ()) if sp.team == team]
    if spirits:
        out["spirits"] = spirits
    dead = [p for p in world.pokemons() if not p.alive]
    if dead:
        out["dead"] = [p.id for p in dead]
        # Avanzamento arrotondato: il pacchetto parte solo quando cambia davvero.
        out["respawn"] = [(p.spawn_pos.x, p.spawn_pos.y, p.team,
                           round(1.0 - max(0.0, p.respawn_timer) / max(0.1, p.respawn_max), 2))
                          for p in dead]
    if isinstance(player, Pokemon):
        out["me"] = capture_me_visual(match, player)
    return out


def capture_me_visual(match, p) -> dict:
    me = {name: getattr(p, name) for name in ME_FIELDS if hasattr(p, name)}
    me["respawn_timer"] = round(max(0.0, p.respawn_timer))
    if p.passive_id == "armature":   # Charcadet: barre di Armature (arrotondate)
        me["fausta"], me["infausta"] = round(p.fausta), round(p.infausta)
    if p.passive_id == "soleluna":   # Sneasel: oro dai minion e dai neutrali
        me["gold_minion"], me["gold_wild"] = round(p.gold_minion), round(p.gold_wild)
    me["item_cd"] = {k: float(v) for k, v in p.item_cd.items() if v > match.time}
    charges = {}
    for s in SLOTS:
        ms = p.moveset.get(s)
        if ms is not None and ms.chosen is not None and ms.chosen.charges > 0:
            charges[s] = float(ms.charges_cur)
    if charges:
        me["charges"] = charges
    try:
        me["in_rain"] = bool(match._in_rain(p))
    except Exception:
        me["in_rain"] = False
    return me
