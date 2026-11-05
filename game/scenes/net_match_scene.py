"""Partita in rete (client): rende dagli snapshot interpolati e invia input.

Non simula: lo stato autoritativo è sul server. Riusa renderer, minimappa,
animatori e la visione (per la nebbia) girandoli sul NetWorld ricostruito.
"""
from __future__ import annotations

from pathlib import Path

import pygame

import config
from engine import moves as moves_mod
from engine.content import load_map, load_pokemon_def
from engine.entities import Pokemon, Structure, Unit
from engine.grid import TILE_FLOOR, TILE_WALL
from engine.items import ItemCatalog
from engine.jungle import CODE_WEATHER, WEATHER_NAMES, apply_weather, ring_tiles
from engine.vec import Vec2
from engine.vision import VisionSystem

from .. import hud, mag_fx, scy_fx
from ..camera import Camera
from ..fx import type_color
from ..input_controller import champs_only_held
from ..minimap import Minimap
from ..networld import NetWorld
from ..particles import ParticleSystem
from ..renderer import Renderer
from ..shop_ui import ShopUI
from ..sprites.animator import FallbackAnimator, SpriteAnimator
from ..sprites.spritesheet import load_pokemon_animations, make_wild_animator

ROOT = Path(__file__).resolve().parents[2]
ABILITY_KEYS = {pygame.K_q: 0, pygame.K_w: 1, pygame.K_e: 2, pygame.K_r: 3}
ITEM_KEYS = {k: i for i, k in enumerate((pygame.K_1, pygame.K_2, pygame.K_3,
                                         pygame.K_4, pygame.K_5, pygame.K_6))}
PICK_RADIUS = 1.4


class NetMatchScene:
    def __init__(self, app, client, start_info):
        self.app = app
        self.client = client
        self.next_scene = None
        self.your_id = start_info["your_entity_id"]
        self.team = 0
        self.pokemon_index = 0
        for p in start_info["players"]:
            if p["client_id"] == client.client_id:
                self.team = p["team"]
                self.pokemon_index = p["pokemon"]
        self.pdef = load_pokemon_def(str(ROOT / config.ROSTER[self.pokemon_index]))
        self.disp_moveset = moves_mod.build_moveset(self.pdef.moves)

        self.map_data = load_map(str(ROOT / start_info.get("map", config.DEFAULT_MAP)))
        self.world = NetWorld(self.map_data.grid)
        self.vision = VisionSystem(self.map_data.grid)
        self.minimap = Minimap(self.map_data.grid, self.map_data)
        self._mm_version = -1

        mw = self.map_data.grid.width * config.TILE_SIZE
        mh = self.map_data.grid.height * config.TILE_SIZE
        self.camera = Camera(config.LOWRES_WIDTH, config.LOWRES_HEIGHT, mw, mh)
        self.renderer = Renderer()
        self.renderer.map.set_camps(self.map_data.camps)   # sentieri di terra verso le lane
        # Particelle d'atmosfera (lucciole/polline/foglie): cosmetiche, aggiornate
        # solo dentro la camera, al massimo ~60 a schermo. Stesse della partita
        # locale: la grafica della giungla e' identica anche online.
        self.particles = ParticleSystem()
        self.animators = {}
        self._unit_dex = {}   # dex per unità (per ricreare lo sprite al cambio forma)
        self.camera_locked = True
        self.aiming_slot = None
        self.aim_start = 0             # ms: inizio della mira (pressione tenuta)
        self._sprite_cache = {}
        self.item_catalog = ItemCatalog.load(str(ROOT / "data/items.json"))
        self.shop = ShopUI()
        self.base = Vec2(*self.map_data.spawns[f"team{self.team}"]) + Vec2(0.5, 0.5)
        # Terreno giungla sincronizzato col meteo del server (stessa logica).
        g = self.map_data.grid
        hx, hy = self.map_data.dens.get("high", (50, 50))
        self._seal = ring_tiles(g, int(hx), int(hy), 2)
        for (x, y) in self._seal:
            g.tiles[y][x] = TILE_WALL
        self._base_tiles = [row[:] for row in g.tiles]
        self._applied_weather = None
        self._applied_open = False
        client.on_snapshot = self._on_snapshot

    def _sync_terrain(self):
        h = self.world.hud
        if not h:
            return
        weather = CODE_WEATHER.get(h.get("weather", 0), "clear")
        opened = bool(h.get("arceus_open", 0))
        if weather == self._applied_weather and opened == self._applied_open:
            return
        if opened and not self._applied_open:
            for (x, y) in self._seal:
                self._base_tiles[y][x] = TILE_FLOOR
        apply_weather(self.map_data.grid, self._base_tiles, weather,
                      puddles=self.map_data.puddles,
                      puddle_spots=self.map_data.puddle_spots,
                      wind_passages=self.map_data.wind_passages)
        self._applied_weather = weather
        self._applied_open = opened
        self._mm_version = -1   # forza il ridisegno della nebbia sulla minimappa

    def _on_snapshot(self, snap, local_time):
        self.world.push(snap, local_time)

    # --- ciclo ---------------------------------------------------------------
    def handle_events(self, events):
        for ev in events:
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.client.close()
                self.quit_app = True
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_p:
                self.shop.toggle()
            elif (self.shop.open and ev.type == pygame.MOUSEBUTTONDOWN
                  and self.shop.consumes(ev.pos)):
                action = self.shop.handle_event(ev)
                if action is not None:
                    kind, val = action
                    if kind == "buy":
                        self.client.send_buy(val)
                    else:
                        self.client.send_sell(val)
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_y:
                self.camera_locked = not self.camera_locked
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_b:
                self.client.send_recall()
            elif ev.type == pygame.KEYDOWN and ev.key in (pygame.K_1, pygame.K_2) \
                    and self._pending() and self._near_base():
                slot = self._pending()[0]
                self.client.send_choose(slot, 0 if ev.key == pygame.K_1 else 1)
            elif ev.type == pygame.KEYDOWN and ev.key in ITEM_KEYS:
                self.client.send_use_item(ITEM_KEYS[ev.key])   # oggetto attivabile dello slot
            elif (self.minimap is not None and ev.type == pygame.MOUSEBUTTONDOWN
                  and self.minimap.contains(ev.pos)):
                self._minimap_click(ev)
            elif ev.type == pygame.KEYDOWN and ev.key in ABILITY_KEYS:
                slot = ABILITY_KEYS[ev.key]
                if pygame.key.get_mods() & pygame.KMOD_CTRL:
                    self.client.send_rank(slot)
                elif self._slot_castable(slot):
                    self.aiming_slot = slot
                    self.aim_start = pygame.time.get_ticks()
            elif ev.type == pygame.KEYUP and ev.key in ABILITY_KEYS:
                if self.aiming_slot == ABILITY_KEYS[ev.key]:
                    self._cast(self.aiming_slot, pygame.mouse.get_pos())
                    self.aiming_slot = None
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self.aiming_slot is not None:
                    self._cast(self.aiming_slot, ev.pos); self.aiming_slot = None
                else:
                    self._left_click(ev.pos)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
                if self.aiming_slot is not None:
                    self.aiming_slot = None
                else:
                    tx, ty = self._tile(ev.pos)
                    self.client.send_move(tx, ty)
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_s:
                self.client.send_stop()
            elif ((ev.type == pygame.MOUSEWHEEL
                   or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_TAB))
                  and self.aiming_slot is not None
                  and mag_fx.has_polarity(self._aim_move(self.aiming_slot))):
                mag_fx.toggle_polarity()   # Bombagnete / Campo Elettrico: + <-> -

    def _tile(self, pos):
        wx, wy = self.camera.screen_window_to_world(*pos)
        return wx / config.TILE_SIZE, wy / config.TILE_SIZE

    def _aim_move(self, slot):
        """Variante attiva della mossa dello slot (indice 0-3), o None."""
        h = self.world.hud
        if not h:
            return None
        name = ["Q", "W", "E", "R"][slot]
        return self._variant_move(self.disp_moveset.get(name), h["slots"][name]["variant"])

    def _cast(self, slot, pos):
        tx, ty = self._tile(pos)
        hold = min(1.5, max(0.0, (pygame.time.get_ticks() - self.aim_start) / 1000.0))
        hold = mag_fx.cast_hold(self._aim_move(slot), hold)   # R a polarità: il segno
        self.client.send_cast(slot, tx, ty, hold=hold)

    def _left_click(self, pos):
        tx, ty = self._tile(pos)
        champs = champs_only_held()   # Maiusc: "solo Pokémon"
        tgt = self._pick_enemy(tx, ty, champs)
        if tgt is not None:
            self.client.send_attack(tgt.id)
        else:
            self.client.send_attackmove(tx, ty, champs_only=champs)

    def _pick_enemy(self, tx, ty, champs_only=False):
        best, bd = None, 1e9
        for e in self.world.combatants():
            if e.team == self.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Unit, Structure)):
                continue
            if champs_only and not isinstance(e, Pokemon):
                continue
            d = ((e.pos.x - tx) ** 2 + (e.pos.y - ty) ** 2) ** 0.5
            if d <= PICK_RADIUS + getattr(e, "radius", 0.0) and d < bd:
                best, bd = e, d
        return best

    def _minimap_click(self, ev):
        tx, ty = self.minimap.to_world_tile(ev.pos)
        if ev.button == 3:
            self.client.send_move(tx, ty)
        elif ev.button == 1:
            self.camera_locked = False
            self.camera.center_on(tx * config.TILE_SIZE, ty * config.TILE_SIZE)

    def _load(self, sprite_dir):
        if sprite_dir not in self._sprite_cache:
            self._sprite_cache[sprite_dir] = load_pokemon_animations(sprite_dir)
        return self._sprite_cache[sprite_dir]

    def _net_animator(self, u):
        from engine.entities import Minion, Pokemon
        if isinstance(u, Pokemon):
            aset = self._load(f"assets/pokemon/{u.dex:04d}")
            if aset is not None:
                return SpriteAnimator(aset)
        if isinstance(u, Minion):
            aset = self._load(f"assets/minions/{u.team}_{u.minion_type}")
            if aset is not None:
                wf = aset.get("Walk") or aset.get("Idle")
                fh = wf.frames[0][0].get_height() if (wf and wf.frames and wf.frames[0]) else 48
                return SpriteAnimator(aset, scale=max(16, int(u.radius * config.TILE_SIZE * 4.5)) / max(1, fh))
        wild = make_wild_animator(u, self._load)
        if wild is not None:
            return wild
        return FallbackAnimator(getattr(u, "color", (200, 200, 200)),
                                int(u.radius * config.TILE_SIZE))

    def _near_base(self):
        me = self.world.get(self.your_id)
        return me is not None and me.pos.dist(self.base) <= config.SHOP_RANGE

    def _pending(self):
        h = self.world.hud
        if not h:
            return []
        bits = h["pending"]
        return [i for i in range(4) if bits & (1 << i)]

    def _slot_castable(self, slot):
        h = self.world.hud
        if not h:
            return False
        s = h["slots"][["Q", "W", "E", "R"][slot]]
        return s["variant"] >= 0 and s["rank"] > 0

    def fixed_update(self):
        pass  # niente simulazione lato client

    def update(self, dt):
        import time
        self.client.poll()
        now = time.monotonic()
        self.world.interpolate(now)
        self._sync_terrain()
        me = self.world.get(self.your_id)
        if me is not None:
            self.camera.update(dt, self.camera_locked, me.pos.x * config.TILE_SIZE,
                               me.pos.y * config.TILE_SIZE, pygame.mouse.get_pos(),
                               pygame.key.get_pressed()[pygame.K_SPACE])
        for u in self.world.units():
            from engine.entities import Pokemon
            # Ricrea l'animatore se il dex cambia (es. forma Shedinja: 291 -> 292).
            if (u.id in self.animators and isinstance(u, Pokemon)
                    and self._unit_dex.get(u.id) != u.dex):
                self.animators.pop(u.id, None)
            if u.id not in self.animators:
                self.animators[u.id] = self._net_animator(u)
                if isinstance(u, Pokemon):
                    self._unit_dex[u.id] = u.dex
            anim = self.animators[u.id]
            anim.pose = ("Sleep" if getattr(u, "sleep_until", -1.0) > self.world.match_time
                         else None)   # addormentato (sonno, Riposo)
            anim.update(dt, u.moving, u.facing)
        # Particelle d'atmosfera: aggiornate solo nel rettangolo visibile.
        self.particles.update(dt, self.camera, self.map_data.grid)
        # Ping di Ecolocalizzazione (Noibat): l'host li manda nello stato visivo;
        # i nemici che rivelano arrivano nello snapshot, qui non vanno rinascosti.
        fxs = getattr(self.world, "fxs", None)
        self.vision.reveals[self.team] = [
            (pg["c"].x, pg["c"].y, pg["radius"]) for pg in getattr(fxs, "sonar_pings", ())
            if pg.get("team") == self.team and pg.get("end", 0.0) > self.world.match_time]
        # Profumino (Teddiursa): i nemici nella nuvola restano visibili.
        self.vision.reveals[self.team] += [
            (z["c"].x, z["c"].y, z["radius"]) for z in getattr(fxs, "honey_zones", ())
            if z.get("team") == self.team and z.get("end", 0.0) > self.world.match_time]
        self.vision.update(self.world, self.team)
        v = self.vision.version.get(self.team, 0)
        if v != self._mm_version:
            self._mm_version = v
            self.minimap.rebuild_fog(self.vision, self.team)

    def draw(self, surface):
        me = self.world.get(self.your_id)
        self.renderer.draw(surface, self.world, self.camera, self.animators,
                           selected_id=me.id if me else None,
                           dens=self.map_data.dens or None,
                           respawning=getattr(self.world, "respawning", None) or None,
                           vision=self.vision, player_team=self.team,
                           now=self.world.match_time)
        # Gittata delle torri nemiche: cerchio di pericolo quando ti avvicini.
        self.renderer.draw_tower_ranges(surface, self.camera, self.world, self.team,
                                        now=self.world.match_time,
                                        player_pos=me.pos if me else None, near=6.0)
        self._draw_world_extras(surface)
        # Particelle d'atmosfera della giungla (sopra mappa e unita, sotto la UI).
        self.particles.draw(surface, self.camera)
        self._draw_after_particles(surface)
        if self.aiming_slot is not None and me is not None:
            s = self.world.hud["slots"][["Q", "W", "E", "R"][self.aiming_slot]]
            ms = self.disp_moveset.get(["Q", "W", "E", "R"][self.aiming_slot])
            mv = self._variant_move(ms, s["variant"])
            ready = mv is not None and s["rank"] > 0 and s["cd"] <= 0 and s["variant"] != -2
            if mv is not None and ready:   # niente mirino se in cooldown o non pronta
                mx, my = pygame.mouse.get_pos()
                wx, wy = self.camera.screen_window_to_world(mx, my)
                hold = (pygame.time.get_ticks() - self.aim_start) / 1000.0
                self.renderer.draw_aim(surface, self.camera, me.pos,
                                       (wx / config.TILE_SIZE, wy / config.TILE_SIZE), mv,
                                       hold=hold, rain=getattr(me, "arch_rain", False),
                                       ammo=getattr(me, "ammo", "Water"))

    def _draw_world_extras(self, surface):
        """Effetti che durano, sopra mappa e unità (la scena online li ha)."""

    def _draw_after_particles(self, surface):
        """Morti che sfumano e proiettili in volo (la scena online li ha)."""

    def _me_vis(self) -> dict:
        """Ricariche e passive del proprio Pokémon (stato visivo online; LAN: vuoto)."""
        return getattr(self.world, "me_vis", None) or {}

    @staticmethod
    def _variant_move(ms, variant):
        if ms is None or variant < 0:
            return None
        if variant == 0:
            return ms.base
        if 1 <= variant <= len(ms.upgrades):
            return ms.upgrades[variant - 1]
        return ms.base

    def hud_lines(self):
        # L'HUD vero e' in draw_fullres (game/hud.py); qui solo messaggi temporanei.
        return []

    HELP = "ONLINE  Dx muovi  Sx attacca  Q/W/E/R mosse  Ctrl+tasto grado  ESC esci"

    # --- HUD a piena risoluzione (game/hud.py, uguale alla partita locale) -------------
    def _my_form(self, me):
        """(nome, sprite_dir) della forma attuale, dal dex dell'entità."""
        dex = getattr(me, "dex", None) if me is not None else None
        for e in self.pdef.evolutions or ():
            if e.get("dex") is not None and int(e["dex"]) == dex:
                return e.get("name") or self.pdef.name, e.get("sprite_dir") or self.pdef.sprite_dir
        return self.pdef.name, self.pdef.sprite_dir

    def _player_view(self, h, me) -> hud.PlayerView:
        name, sd = self._my_form(me)
        port = getattr(self, "_portrait", None)
        dead = me is None or me.id in getattr(self.world, "dead", ())
        return hud.PlayerView(
            name=name, level=h["level"], xp=h["xp"],
            hp=me.hp if me is not None else 0.0,
            max_hp=me.max_hp if me is not None else 1.0,
            portrait=port(sd, hud.PORT - 14) if (port and sd) else None,
            gold=int(h.get("gold", 0)), items=list(h.get("items", [])),
            stats=self._info_rows(h, me), alive=not dead, points=h["points"],
            rank_hint="Ctrl+Q/W/E/R", team=self.team)

    def _info_rows(self, h, me) -> list:
        """Online le statistiche non viaggiano nello snapshot: al loro posto ruolo,
        tipi e oggetti (righe senza etichetta: ("", testo, colore))."""
        role, types = self.pdef.role, self.pdef.types
        dex = getattr(me, "dex", None)
        for e in self.pdef.evolutions or ():   # ruolo e tipi della forma attuale
            if e.get("dex") is not None and int(e["dex"]) == dex:
                role, types = e.get("role") or role, e.get("types") or types
        rows = [("", (role or "").capitalize(), hud.TRIM_HI)]
        rows += [("", t, type_color(t)) for t in types[:2]]
        rows.append(("Oggetti", f"{len(h.get('items', []))}/6", ""))
        return rows

    def _slot_views(self, h) -> list:
        pend = {["Q", "W", "E", "R"][i] for i in self._pending()}
        charges = self._me_vis().get("charges", {})
        out = []
        for sl in ("Q", "W", "E", "R"):
            s = h["slots"][sl]
            ms = self.disp_moveset.get(sl)
            mv = self._variant_move(ms, s["variant"])
            maxr = ms.max_rank if ms is not None else (3 if sl == "R" else 4)
            v = hud.SlotView(key=sl, rank=s["rank"], max_rank=maxr,
                             can_rank=h["points"] > 0 and s["rank"] < maxr,
                             evolvable=sl in pend and ms is not None and bool(ms.upgrades))
            if mv is not None:
                v.name, v.mtype = mv.name, mv.type
                ch = charges.get(sl)
                if ch is not None and s["rank"] > 0 and mv.charges > 0:
                    whole = max(0, min(mv.charges, int(ch + 1e-6)))
                    v.charges = (whole, mv.charges, 1.0 if whole >= mv.charges else ch - int(ch))
                elif s["rank"] > 0 and s["cd"] > 0:
                    v.cd_left = s["cd"]
                    v.cd_frac = s["cd"] / max(0.1, mv.cooldown_at(s["rank"]))
            else:
                v.can_rank = False
                v.locked = "Liv. 8" if (s["variant"] == -2 or h["level"] < 8) else "Evolvi"
                if ms is None:
                    v.max_rank = 0
            out.append(v)
        return out

    def _match_view(self, h) -> hud.MatchView:
        cores = {c.team: c for c in self.world.cores()}
        dead = getattr(self.world, "dead", set())
        teams = tuple(tuple(-1.0 if (q.id in dead or not getattr(q, "alive", True)) else 0.0
                            for q in self.world.pokemons() if q.team == t) for t in (0, 1))
        return hud.MatchView(
            time=h["time"],
            cores=tuple((cores[t].hp, cores[t].max_hp) if t in cores
                        else (float(h.get(f"core{t}", 0)), float(config.CORE_HP))
                        for t in (0, 1)),
            teams=teams, next_wave=None,
            weather=WEATHER_NAMES.get(CODE_WEATHER.get(h.get("weather", 0), "clear"), ""),
            winner=self.world.winner, player_team=self.team)

    def draw_fullres(self, surface, font):
        h = self.world.hud
        if h is None:
            return
        me = self.world.get(self.your_id)
        self.minimap.draw(surface, self.world, self.camera, self.vision, self.team,
                          self.map_data.dens, me)
        right = self.minimap.rect.x
        hud.draw_top(surface, self._match_view(h), getattr(self, "fps", None))
        hud.text(surface, self.HELP, (8, 6), 12, hud.DIM)
        icon = lambda iid, size: self.shop._icon(self.item_catalog, iid, size, font)
        self._bar = hud.draw_bar(surface, self._player_view(h, me), self._slot_views(h),
                                 type_color, icon, right_limit=right)
        # Popup delle evoluzioni (online si sceglie con 1/2 la prima in coda).
        pend = [["Q", "W", "E", "R"][i] for i in self._pending()]
        pend = [sl for sl in pend if self.disp_moveset.get(sl) and self.disp_moveset[sl].upgrades]
        if pend:
            near = self._near_base()
            sizes = [hud.choice_size(sl, self.disp_moveset[sl].upgrades[:2]) for sl in pend]
            anchors = [self._bar.slot_rects[sl].centerx for sl in pend]
            bottom = self._bar.rect.y - (30 if h["points"] > 0 else 8)
            for k, (sl, r) in enumerate(zip(pend, hud.layout_popups(sizes, anchors, bottom,
                                                                      right))):
                if not near:
                    title, col = f"Evolvi {sl} - torna in BASE", (236, 170, 110)
                elif k == 0:
                    title, col = f"Evolvi {sl} - premi 1 / 2", hud.GOLD
                else:
                    title, col = f"Evolvi {sl} - dopo {pend[0]}", hud.DIM
                hud.draw_choice(surface, r, title, self.disp_moveset[sl].upgrades[:2],
                                type_color, False, col)
        if self.world.winner is not None:
            win = self.world.winner == self.team
            hud.draw_banner(surface, "VITTORIA!" if win else "SCONFITTA",
                            f"Ha vinto la squadra {'BLU' if self.world.winner == 0 else 'ROSSA'}",
                            (255, 230, 120) if win else (240, 120, 110),
                            y=surface.get_height() // 3)
        elif me is None or me.id in getattr(self.world, "dead", ()):
            hud.draw_banner(surface, "ABBATTUTO", "Rinasci in base tra poco", (240, 120, 110))

        if self.shop.open:
            near = me is not None and me.pos.dist(self.base) <= config.SHOP_RANGE
            self.shop.draw(surface, font, self.item_catalog, h.get("gold", 0),
                           h.get("items", []), self.pdef.recommended_items or self.pdef.role,
                           near, self._me_vis().get("item_cd", {}), self.world.match_time,
                           evo=scy_fx.evo_hint(self.world.get(self.your_id)))   # Scyther
