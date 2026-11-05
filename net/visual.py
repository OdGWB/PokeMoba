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

SLOTS = ["Q", "W", "E", "R"]

# Liste del Match: nome -> (chiave della posizione, chiave della squadra).
LISTS = {
    "projectiles": ("pos", "team"), "avalanches": ("pos", "team"),
    "legion_waves": ("c", "team"), "spirit_beams": ("pos", "team"),
    "thunders": ("c", "team"), "blizzards": ("c", "team"),
    "future_sights": ("c", "team"), "swift_stars": ("pos", "team"),
    "item_clouds": ("center", "team"), "tailwinds": ("c", "team"),
    "shades": ("pos", "team"), "smogs": ("c", "team"), "cannon_charges": ("pos", "team"),
    "psy_zones": ("c", "team"), "flurries": ("pos", "team"),
    "sonar_pings": ("c", "team"), "hurricanes": ("c", "team"), "meteors": ("c", "team"),
    "honey_zones": ("c", "team"), "quakes": ("c", "team"),
    "claw_leaps": ("c", "team"), "beatups": ("pos", "team"), "sludge_lobs": ("c", "team"),
    "mien_leaps": ("c", "team"), "wave_zones": ("c", "team"), "thunder_marks": ("c", "team"),
    "hatt_marks": ("c", "team"), "moon_orbs": ("pos", "team"), "witch_waves": ("c", "team"),
    "mag_bolts": ("pos", "team"), "ion_trails": ("c", "team"), "mag_links": ("c", "team"),
    "ice_trails": ("c", "team"), "glacial_blocks": ("pos", "team"), "ice_storms": ("c", "team"),
    "powder_clouds": ("c", "team"), "octi_shots": ("pos", "team"),
}
# Campi solo di logica (oggetti del motore, insiemi di bersagli già colpiti).
SKIP = {"mv", "hit", "touched", "since", "rank", "explode", "first", "caught", "slept", "freed", "rel"}
# Stati sulle unità che non sono timer *_until (valore "spento" a destra).
UNIT_FLAGS = {"air_z": 0.0, "sand_radius": 0.0, "invisible": False, "submerged": False,
              "spirit_awaken": 0, "smoke_hidden": False, "armor_blocks": 0, "echo_count": 0,
              "honey": 0, "guts_active": False,
              "snatch_down": 0, "snatch_up": 0, "mien_regen": False,
              "arch_rain": False, "thunder_left": 0, "agitated": False, "mag_sign": 0,
              "frost_stacks": 0, "fat_shield": 0.0, "venom_stacks": 0, "octi_lock_by": -1}
# Il proprio Pokémon: passive e ricariche mostrate nell'interfaccia.
ME_FIELDS = ("passive_id", "soul_charges", "inversion_stacks", "muta_cd_until", "muta_cd_max",
             "form_until", "sandstorm_boost_until", "sand_radius", "spirit_charges",
             "wander_ready_at", "voltabsorb_ready_at", "flashfire_until", "recalling",
             "recall_until", "respawn_timer", "guard_ready_at", "climb_ready_at",
             "fakeout_ready", "dance_seq", "mien_calm_at", "ammo", "ammo_boost")

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
    # Taxi Volante: il punto d'atterraggio lo vede anche la squadra avversaria.
    taxis = [_clean(fl) for fl in getattr(match, "taxi_flights", ())]
    if taxis:
        out["taxi_flights"] = taxis
    # Carica di Elettroraggio: la vedono anche i nemici (anche fuori visione).
    charges = [_clean(ch) for ch in getattr(match, "beam_charges", ())]
    if charges:
        out["beam_charges"] = charges
    # Distortozona (Hatterene): l'area la vedono tutti (cambia la velocità di tutti).
    tricks = [_clean(z) for z in getattr(match, "trick_rooms", ())]
    if tricks:
        out["trick_rooms"] = tricks
    # Linea Magnemite: cariche sui muri, pilastro di Bombagnete (un ostacolo) e
    # Campo Elettrico li vedono tutti.
    for name in ("mag_walls", "mag_pillars", "mag_fields"):
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
