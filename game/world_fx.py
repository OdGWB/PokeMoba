"""Effetti che DURANO, disegnati dallo stato della partita a ogni frame.

Stesso codice per la partita offline (MatchScene: `m` è il Match vero) e per
quella online (OnlineMatchScene: `m` è OnlineWorld.fxs, ricostruito dallo
stato visivo che manda l'host, net/visual.py). Le liste hanno gli stessi nomi
e gli stessi campi, quindi online si vede quello che si vede offline.

- draw_world_effects: tempesta di sabbia, valanghe, spiriti e mosse di
  Spiritomb, mosse di Eevee (sopra mappa e unità, sotto le particelle);
- draw_projectiles:   bolle in volo (Idropulsar), sopra le particelle;
- update_world_fx:    polvere delle valanghe e nube della Palla Fumo per tutta
  la sua durata (l'evento arriva una volta sola, la nube dura 3 s).
"""
from __future__ import annotations

import random

import pygame

import config

from . import eevee_fx, spirit_fx
from .fx import draw_avalanche, draw_sandstorm, type_color


def draw_world_effects(surface, camera, world, m, team, vision, now, player_id,
                       reach=None, pick=None) -> None:
    def enemy_seen(p):
        return p.team == team or vision is None or vision.is_enemy_visible(team, p.id)

    def seen(pos, t=None):
        return (t == team or vision is None
                or vision.is_tile_visible(team, int(pos.x), int(pos.y)))

    # Linea Roggenrola: tempesta di Sabbiafiume (aura) e valanghe di Frana.
    for p in world.pokemons():
        if p.alive and p.sand_radius > 0.0 and enemy_seen(p):
            draw_sandstorm(surface, camera, p.pos, p.sand_radius, now)
    for av in m.avalanches:
        if now >= av["start"]:
            draw_avalanche(surface, camera, av, now)
    # Spiritomb: solo i PROPRI spiriti (quelli di un altro Spiritomb alleato non
    # si possono raccogliere), ondata della Legione, Malcomune, Stordiraggio.
    mine = [s for s in getattr(world, "spirits", ()) if s.owner_id == player_id]
    spirit_fx.draw_spirits(surface, camera, mine, team, now, reach=reach, pick=pick)
    for w in m.legion_waves:
        spirit_fx.draw_legion_wave(surface, camera, w, now)
    for bd in m.pain_binds:
        c = world.get(bd["caster_id"])
        if c is not None and seen(c.pos, c.team):
            spirit_fx.draw_pain_bind(surface, camera, bd, world, now)
    for b in m.spirit_beams:
        if seen(b["pos"], b["team"]):
            spirit_fx.draw_spirit_beam(surface, camera, b, now)
    # Linea Eevee: Tuono, Bora, Divinazione, Desiderio, Comete.
    for th in m.thunders:
        if seen(th["c"], th["team"]):
            eevee_fx.draw_thunder(surface, camera, th, now)
    for bz in m.blizzards:
        if seen(bz["c"], bz["team"]):
            eevee_fx.draw_blizzard(surface, camera, bz, now)
    for fs in m.future_sights:
        if seen(fs["c"], fs["team"]):
            eevee_fx.draw_future_sight(surface, camera, fs, now)
    for w in m.wishes:
        tgt = world.get(w["target_id"])
        if tgt is not None and seen(tgt.pos, tgt.team):
            eevee_fx.draw_wish(surface, camera, w, world, now)
    for st in m.swift_stars:
        if seen(st["pos"], st["team"]):
            eevee_fx.draw_swift_star(surface, camera, st, now)


def draw_projectiles(surface, camera, m) -> None:
    """Proiettili che viaggiano (bolla Idropulsar)."""
    ts = config.TILE_SIZE
    for pr in m.projectiles:
        gx, gy = camera.world_to_screen(pr["pos"].x * ts, pr["pos"].y * ts)
        col = type_color(pr["mtype"])
        r = max(3, int(pr["radius"] * ts))
        glow = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*col, 70), (r * 2, r * 2), r * 2)
        surface.blit(glow, (gx - r * 2, gy - r * 2))
        pygame.draw.circle(surface, col, (gx, gy), r)
        pygame.draw.circle(surface, (255, 255, 255), (gx, gy), r, 1)


def update_world_fx(fx, m, now) -> None:
    # Frana: polvere sollevata dietro la valanga che rotola.
    for av in m.avalanches:
        if now >= av["start"] and random.random() < 0.6:
            d, r = av["dir"], av["radius"]
            fx._dust((av["pos"].x - d.x * r, av["pos"].y - d.y * r), r * 0.7,
                     n=2, speed=(0.3, 1.2))
    # Palla Fumo: la nube si rinnova finché esiste (fx._fx_smoke non ne crea
    # una nuova finché la precedente è ancora fitta).
    clouds = getattr(m, "item_clouds", ())
    if clouds:
        fx.spawn_events([{"kind": "zone", "c": (c["center"].x, c["center"].y),
                          "radius": c["radius"], "mtype": "Normal", "fx": "smoke"}
                         for c in clouds])
