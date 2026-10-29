"""Costruzione e lettura degli snapshot di stato.

Il server costruisce, per ciascuna squadra, uno snapshot che contiene solo ciò
che quella squadra può vedere (alleati, strutture, e nemici attualmente
visibili): così un client non può "barare" leggendo i pacchetti.

Il client decodifica lo snapshot in dati grezzi; la ricostruzione delle entità
per il rendering e l'interpolazione stanno in game/networld.py.
"""
from __future__ import annotations

from engine.entities import Core, Minion, Pokemon, Structure
from engine.jungle import WEATHER_CODE
from .protocol import (K_CORE, K_MINION, K_POKEMON, K_TOWER, Reader, S_SNAPSHOT,
                       Writer)

_SLOTS = ["Q", "W", "E", "R"]


def _slot_variant(ms) -> int:
    if ms is None:
        return -1
    if not ms.unlocked:
        return -2
    if ms.chosen is None:
        return -2
    if ms.chosen is ms.base:
        return 0
    try:
        return ms.upgrades.index(ms.chosen) + 1
    except ValueError:
        return 0


def build_snapshot(match, team: int, your_entity_id: int, snap_seq: int) -> bytes:
    world = match.world
    w = Writer().u8(S_SNAPSHOT).u32(snap_seq).f32(match.time)
    w.i8(-1 if match.winner is None else match.winner)

    cores = {c.team: c for c in world.cores()}
    w.hp(cores[0].hp if 0 in cores else 0).hp(cores[1].hp if 1 in cores else 0)
    w.u8(WEATHER_CODE.get(match.jungle.weather, 0))
    w.u8(1 if match.jungle._arceus_opened else 0)

    # Blocco HUD del giocatore destinatario.
    me = world.get(your_entity_id)
    if isinstance(me, Pokemon):
        w.u8(me.level).f32(me.xp)
        from engine import skills
        w.u8(skills.available_points(me))
        pend = sum((1 << i) for i, s in enumerate(_SLOTS) if s in me.pending_choices)
        w.u8(pend)
        for s in _SLOTS:
            ms = me.moveset.get(s)
            w.i8(_slot_variant(ms))
            w.u8(ms.rank if ms else 0)
            w.u16(round((ms.cooldown_remaining if ms else 0.0) * 100))
        w.u32(round(me.gold)).u8(len(me.items))
        for iid in me.items:
            w.s(iid)
    else:
        w.u8(0).f32(0.0).u8(0).u8(0)
        for _ in _SLOTS:
            w.i8(-1).u8(0).u16(0)
        w.u32(0).u8(0)

    # Entità visibili alla squadra.
    ents = []
    for e in world.entities.values():
        if isinstance(e, Structure):
            if e.alive:
                ents.append(e)
        elif isinstance(e, (Pokemon, Minion)) and e.alive:
            if e.team == team or match.vision.is_enemy_visible(team, e.id):
                ents.append(e)
    w.u16(len(ents))
    for e in ents:
        if isinstance(e, Core):
            kind, extra = K_CORE, 0
        elif isinstance(e, Structure):
            kind, extra = K_TOWER, int(getattr(e, "tier", 1))
        elif isinstance(e, Pokemon):
            kind, extra = K_POKEMON, int(e.dex)
        else:
            kind = K_MINION
            extra = {"melee": 0, "caster": 1, "cannon": 2}.get(e.minion_type, 0)
        flags = (1 if getattr(e, "moving", False) else 0) | (2 if e.alive else 0)
        w.u16(e.id).u8(kind).u8(e.team).fx(e.pos.x).fx(e.pos.y)
        w.u8(getattr(e, "facing", 0)).rad(e.radius).hp(e.hp).hp(e.max_hp)
        w.u8(flags).u16(extra)
    return w.bytes()


def decode_snapshot(data) -> dict:
    r = Reader(data); r.u8()
    snap = {"seq": r.u32(), "time": r.f32(), "winner": r.i8()}
    snap["core0"] = r.hp(); snap["core1"] = r.hp()
    snap["weather"] = r.u8(); snap["arceus_open"] = r.u8()
    snap["level"] = r.u8(); snap["xp"] = r.f32()
    snap["points"] = r.u8(); snap["pending"] = r.u8()
    slots = {}
    for s in _SLOTS:
        slots[s] = {"variant": r.i8(), "rank": r.u8(), "cd": r.u16() / 100.0}
    snap["slots"] = slots
    snap["gold"] = r.u32()
    snap["items"] = [r.s() for _ in range(r.u8())]
    n = r.u16()
    ents = []
    for _ in range(n):
        e = {"id": r.u16(), "kind": r.u8(), "team": r.u8(),
             "x": r.fx(), "y": r.fx(), "facing": r.u8(), "radius": r.rad(),
             "hp": r.hp(), "max_hp": r.hp()}
        flags = r.u8(); e["moving"] = bool(flags & 1); e["alive"] = bool(flags & 2)
        e["extra"] = r.u16()
        ents.append(e)
    snap["entities"] = ents
    return snap
