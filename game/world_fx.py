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

from . import (arch_fx, char_fx, charcadet_fx, corvi_fx, eevee_fx, gastly_fx, hatt_fx, mag_fx, mien_fx, noivern_fx,
               flor_fx, moth_fx, octi_fx, scy_fx, sneasel_fx, spirit_fx, swine_fx, ursa_fx)
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
    # Linea Rookidee: correnti di Ventoincoda e Taxi Volante (il punto
    # d'atterraggio lo vedono anche i nemici).
    for tw in getattr(m, "tailwinds", ()):
        if seen(tw["c"], tw["team"]):
            corvi_fx.draw_tailwind(surface, camera, tw, now)
    for fl in getattr(m, "taxi_flights", ()):
        corvi_fx.draw_taxi(surface, camera, fl, now)
    # Linea Charcadet: Pulifumo, Psichico, Ombra Notturna, carica di Armor
    # Cannon, raffica della Lama dei Rancori.
    for s in getattr(m, "smogs", ()):
        if seen(s["c"], s["team"]):
            charcadet_fx.draw_smog(surface, camera, s, now)
    for z in getattr(m, "psy_zones", ()):
        if seen(z["c"], z["team"]):
            charcadet_fx.draw_psy_zone(surface, camera, z, now)
    for sh in getattr(m, "shades", ()):
        if seen(sh["pos"], sh["team"]):
            charcadet_fx.draw_shade(surface, camera, sh, now)
    for cc in getattr(m, "cannon_charges", ()):
        if seen(cc["pos"], cc["team"]):
            charcadet_fx.draw_cannon_charge(surface, camera, cc, now)
    for fl in getattr(m, "flurries", ()):
        if seen(fl["pos"], fl["team"]):
            charcadet_fx.draw_flurry(surface, camera, fl, now)
    # Linea Noibat: ping di Ecolocalizzazione, Tifone, Dragobolide in arrivo.
    for pg in getattr(m, "sonar_pings", ()):
        if seen(pg["c"], pg["team"]):
            noivern_fx.draw_ping(surface, camera, pg, now)
    for h in getattr(m, "hurricanes", ()):
        if seen(h["c"], h["team"]):
            noivern_fx.draw_hurricane(surface, camera, h, now)
    for mt in getattr(m, "meteors", ()):
        if seen(mt["c"], mt["team"]):
            noivern_fx.draw_meteor_warn(surface, camera, mt, now)
    # Linea Teddiursa: nuvola di Profumino, balzi (Luna Piena in arrivo), Terremoto.
    for z in getattr(m, "honey_zones", ()):
        if seen(z["c"], z["team"]):
            ursa_fx.draw_honey_zone(surface, camera, z, now)
    for q in getattr(m, "quakes", ()):
        if seen(q["c"], q["team"]):
            ursa_fx.draw_quake(surface, camera, q, now)
    for lp in getattr(m, "bear_leaps", ()):
        if seen(lp["c"], lp["team"]) or lp.get("fx") == "fullmoon":   # l'atterraggio lo vedono tutti
            ursa_fx.draw_leap(surface, camera, lp, now)
    # Linea Sneasel: fango di Sporcolancio, balzi (scavalcamento, Agguato dalla Rupe).
    for lb in getattr(m, "sludge_lobs", ()):
        if seen(lb["c"], lb["team"]):
            sneasel_fx.draw_lob(surface, camera, lb, now)
    for lp in getattr(m, "claw_leaps", ()):
        if seen(lp["c"], lp["team"]):
            sneasel_fx.draw_claw_leap(surface, camera, lp, now)
    # Linea Mienfoo: mirino d'atterraggio di Calcinvolo.
    for lp in getattr(m, "mien_leaps", ()):
        if seen(lp["c"], lp["team"]):
            mien_fx.draw_jump(surface, camera, lp, now)
    # Linea Duraludon: Tuononda in arrivo, fulmini di Tuono, carica di Elettroraggio
    # (la carica la vedono tutti, anche la squadra avversaria).
    for z in getattr(m, "wave_zones", ()):
        if seen(z["c"], z["team"]):
            arch_fx.draw_wave_zone(surface, camera, z, now)
    for tm in getattr(m, "thunder_marks", ()):
        if seen(tm["c"], tm["team"]):
            arch_fx.draw_thunder_mark(surface, camera, tm, now)
    for ch in getattr(m, "beam_charges", ()):
        arch_fx.draw_beam_charge(surface, camera, ch, now)
    # Linea Hatenna: Distortozona (visibile a tutti), Confusione in arrivo,
    # carica della Strega della Foresta, sfere di Forza Lunare in volo.
    for z in getattr(m, "trick_rooms", ()):
        hatt_fx.draw_trick_room(surface, camera, z, now)
    for z in getattr(m, "hatt_marks", ()):
        if seen(z["c"], z["team"]):
            hatt_fx.draw_mark(surface, camera, z, now)
    for w in getattr(m, "witch_waves", ()):
        if seen(w["c"], w["team"]):
            hatt_fx.draw_witch_charge(surface, camera, w, now)
    for o in getattr(m, "moon_orbs", ()):
        if seen(o["pos"], o["team"]):
            hatt_fx.draw_moon_orb(surface, camera, o, now)
    # Linea Magnemite: Campo Elettrico, pilastro di Bombagnete e cariche sui muri
    # (visibili a tutti), Scia Ionica, interazioni in corso, Tuonoshock in volo.
    for z in getattr(m, "mag_fields", ()):
        mag_fx.draw_mag_field(surface, camera, z, now)
    for tr in getattr(m, "ion_trails", ()):
        if seen(tr["c"], tr["team"]):
            mag_fx.draw_ion_trail(surface, camera, tr, now)
    for pl in getattr(m, "mag_pillars", ()):
        mag_fx.draw_mag_pillar(surface, camera, pl, now)
    for w in getattr(m, "mag_walls", ()):
        mag_fx.draw_wall_charge(surface, camera, w, now)
    for ln in getattr(m, "mag_links", ()):
        if seen(ln["c"], ln["team"]):
            mag_fx.draw_mag_link(surface, camera, ln, now)
    for o in getattr(m, "mag_bolts", ()):
        if seen(o["pos"], o["team"]):
            mag_fx.draw_bolt(surface, camera, o, now)
    # Linea Swinub: Scia Ghiacciata, bufera e blocco di Era Glaciale, impronte
    # del Fiuto (solo per la squadra che fiuta, anche nella nebbia).
    for tr in getattr(m, "ice_trails", ()):
        if seen(tr["c"], tr["team"]):
            swine_fx.draw_ice_trail(surface, camera, tr, now)
    for z in getattr(m, "ice_storms", ()):
        if seen(z["c"], z["team"]):
            swine_fx.draw_ice_storm(surface, camera, z, now)
    for o in getattr(m, "glacial_blocks", ()):
        if seen(o["pos"], o["team"]):
            swine_fx.draw_glacial_block(surface, camera, o, now)
    # Linea Venonat: nubi di polvere e Tempesta di Polveri.
    for cl in getattr(m, "powder_clouds", ()):
        if seen(cl["c"], cl["team"]):
            moth_fx.draw_powder_cloud(surface, camera, cl, now)
    # Linea Flabébé: Radici e Campo Nebbioso (visibili a tutti; i fiori li
    # disegna il renderer a terra, ordinati con le unità).
    for z in getattr(m, "flor_roots", ()):
        flor_fx.draw_roots(surface, camera, z, now)
    for z in getattr(m, "flor_mists", ()):
        flor_fx.draw_mist(surface, camera, z, now)
    # Linea Scyther: campi di schegge e Taglio d'Albero in carica (visibili a tutti).
    for fl in getattr(m, "scy_fields", ()):
        scy_fx.draw_field(surface, camera, fl, now)
    for ch in getattr(m, "scy_chops", ()):
        scy_fx.draw_chop(surface, camera, ch, now)
    # Linea Remoraid: proiettili di Pistolacqua / Raffica / Colpo Perforante.
    for o in getattr(m, "octi_shots", ()):
        if seen(o["pos"], o["team"]):
            octi_fx.draw_shot(surface, camera, o, now)
    tracks = getattr(m, "swine_tracks", ())
    if tracks:
        swine_fx.draw_tracks(surface, camera, tracks, team, now)


def draw_projectiles(surface, camera, m, now=0.0) -> None:
    """Proiettili che viaggiano (bolla Idropulsar, palla di Armor Cannon)."""
    ts = config.TILE_SIZE
    for pr in m.projectiles:
        if pr.get("fx") == "armorcannon":
            charcadet_fx.draw_cannonball(surface, camera, pr, now)
            continue
        if pr.get("fx") == "charblast":   # Fuocobomba
            char_fx.draw_blast(surface, camera, pr, now)
            continue
        if pr.get("fx") in ("gastshadowball", "gasthypnosis"):   # Palla Ombra, Ipnosi
            gastly_fx.draw_projectile(surface, camera, pr, now)
            continue
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
