"""Cattura dello stato del Match in tuple QUANTIZZATE, per squadra (lato host).

È l'unico file di net/ che legge le entità del gioco. Produce i valori che
net/protocol.enc_snapshot mette in delta. Tutto è già quantizzato (interi),
così il confronto "è cambiato?" del delta è un semplice ==.

FILTRO DI VISIONE: lo snapshot di una squadra contiene solo alleati,
strutture e nemici/neutrali attualmente VISIBILI a quella squadra. Un client
non può leggere dai pacchetti dove si nasconde il nemico.
"""
from __future__ import annotations

from engine.entities import Core, Minion, Pokemon, Structure, Wild
from engine.jungle import WEATHER_CODE

from .protocol import (EF_ALIVE, EF_DISCONNECTED, EF_MOVING, K_CORE, K_MINION,
                       K_POKEMON, K_TOWER, K_WILD, ME_ALIVE, ME_CAN_MOVE, ME_HAS_ACK,
                       ME_MOVING, MINION_TYPES, WILD_KINDS, WILD_WEATHERS,
                       facing_to_angle, q_pos)

SLOTS = ["Q", "W", "E", "R"]


def _hp(v) -> int:
    return max(0, min(65535, round(v)))


def _rad(v) -> int:
    return max(0, min(255, round(v * 100)))


def _entity(e, flags_extra=0):
    if isinstance(e, Core):
        kind, extra = K_CORE, 0
    elif isinstance(e, Structure):
        kind, extra = K_TOWER, int(getattr(e, "tier", 1))
    elif isinstance(e, Pokemon):
        kind = K_POKEMON
        extra = 292 if getattr(e, "form", "") == "shedinja" else int(e.dex)
    elif isinstance(e, Wild):
        kind = K_WILD
        k = WILD_KINDS.index(e.kind) if e.kind in WILD_KINDS else 0
        wt = WILD_WEATHERS.index(e.weather) if e.weather in WILD_WEATHERS else 0
        extra = k | (wt << 2)
    else:
        kind = K_MINION
        mt = getattr(e, "minion_type", "melee")
        extra = MINION_TYPES.index(mt) if mt in MINION_TYPES else 0
    flags = flags_extra
    if getattr(e, "moving", False):
        flags |= EF_MOVING
    if getattr(e, "alive", True):
        flags |= EF_ALIVE
    return (kind, int(e.team) & 0xFF, q_pos(e.pos.x), q_pos(e.pos.y),
            facing_to_angle(getattr(e, "facing", 0)), flags,
            _hp(e.hp), _hp(e.max_hp), _rad(e.radius), extra & 0xFFFF)


def capture_team(match, team: int, disconnected=frozenset()) -> dict:
    """{id: tupla} di ciò che la squadra `team` può vedere."""
    vis = match.vision
    out = {}
    for e in match.world.entities.values():
        if isinstance(e, Structure):
            out[e.id] = _entity(e)          # anche distrutte: resta il moncone
        elif isinstance(e, (Pokemon, Minion, Wild)) and e.alive:
            if e.team == team or vis.is_enemy_visible(team, e.id):
                out[e.id] = _entity(e, EF_DISCONNECTED if e.id in disconnected else 0)
    return out


def capture_global(match) -> tuple:
    cores = {c.team: c for c in match.world.cores()}
    return (_hp(cores[0].hp) if 0 in cores else 0,
            _hp(cores[1].hp) if 1 in cores else 0,
            -1 if match.winner is None else int(match.winner),
            WEATHER_CODE.get(match.jungle.weather, 0),
            1 if match.jungle._arceus_opened else 0)


def _slot_variant(ms) -> int:
    if ms is None:
        return -1
    if not ms.unlocked or ms.chosen is None:
        return -2
    if ms.chosen is ms.base:
        return 0
    try:
        return ms.upgrades.index(ms.chosen) + 1
    except ValueError:
        return 0


def capture_hud(p) -> tuple | None:
    if not isinstance(p, Pokemon):
        return None
    from engine import skills
    out = [p.level, max(0, round(p.xp * 100)), skills.available_points(p),
           sum((1 << i) for i, s in enumerate(SLOTS) if s in p.pending_choices)]
    for s in SLOTS:
        ms = p.moveset.get(s)
        out += [_slot_variant(ms), ms.rank if ms else 0,
                min(65535, round((ms.cooldown_remaining if ms else 0.0) * 100))]
    out.append(max(0, round(p.gold)))
    out.append(tuple(p.items[:6]))
    return tuple(out)


def can_move(match, p) -> bool:
    """L'host lascerebbe muovere il Pokémon adesso? (per fermare la predizione)"""
    t = match.time
    return (p.alive and not match._immobile(p) and p.root_until <= t
            and p.fear_until <= t and not p.recalling
            and getattr(p, "channel_until", -1.0) <= t)


def capture_me(match, p, ack_seq, ack_tick) -> tuple | None:
    """Blocco "io": posizione esatta e cosa serve alla riconciliazione."""
    if not isinstance(p, Pokemon):
        return None
    f = 0
    if p.alive:
        f |= ME_ALIVE
    if can_move(match, p):
        f |= ME_CAN_MOVE
    if p.moving:
        f |= ME_MOVING
    if ack_seq is not None:
        f |= ME_HAS_ACK
    return (q_pos(p.pos.x), q_pos(p.pos.y), min(65535, round(p.speed * 256)), f,
            (ack_seq or 0) & 0xFFFF, ack_tick)


def fx_visible(match, team: int, ev: dict) -> bool:
    """Un evento visivo si manda solo se la squadra può vederlo."""
    world, vis = match.world, match.vision
    eid = ev.get("eid")
    if eid is not None:
        e = world.get(eid)
        if e is None:
            return False
        return getattr(e, "team", team) == team or vis.is_enemy_visible(team, eid)
    pts = [ev[k] for k in FX_POINT_KEYS if isinstance(ev.get(k), (tuple, list))]
    pts += [p for p in ev.get("pts") or () if isinstance(p, (tuple, list))]
    pts = [p for p in pts if len(p) >= 2 and all(isinstance(x, (int, float)) for x in p[:2])]
    if pts:
        return any(vis.is_tile_visible(team, int(p[0]), int(p[1])) for p in pts)
    # Niente posizione: si manda solo se e' globale per scelta di design, oppure se
    # riguarda un'unita' che la squadra vede. Prima passava TUTTO (coni con "o",
    # colpi con "src"/"hit"): un client modificato li leggeva nella nebbia.
    if ev.get("kind") in FX_GLOBAL_KINDS:
        return True
    for k in FX_ID_KEYS:
        oid = ev.get(k)
        if isinstance(oid, int) and not isinstance(oid, bool):
            e = world.get(oid)
            if e is not None and (getattr(e, "team", team) == team
                                  or vis.is_enemy_visible(team, oid)):
                return True
    return False


# Chiavi degli eventi FX che portano un punto (x, y) della mappa.
FX_POINT_KEYS = ("a", "b", "c", "o")
# Chiavi con l'id di un'unita' coinvolta (oltre a "eid", gestito sopra).
FX_ID_KEYS = ("eid2", "src", "hit", "tgt", "who")
# Eventi senza posizione che vedono tutti (Elettroraggio: tremolio "per tutti").
FX_GLOBAL_KINDS = frozenset({"shake"})
