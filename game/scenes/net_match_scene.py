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
from engine.entities import Structure, Unit
from engine.grid import TILE_FLOOR, TILE_WALL
from engine.items import ItemCatalog
from engine.jungle import CODE_WEATHER, WEATHER_NAMES, apply_weather, ring_tiles
from engine.vec import Vec2
from engine.vision import VisionSystem

from ..camera import Camera
from ..minimap import Minimap
from ..networld import NetWorld
from ..particles import ParticleSystem
from ..renderer import Renderer
from ..shop_ui import ShopUI
from ..sprites.animator import FallbackAnimator, SpriteAnimator
from ..sprites.spritesheet import load_pokemon_animations, make_wild_animator

ROOT = Path(__file__).resolve().parents[2]
ABILITY_KEYS = {pygame.K_q: 0, pygame.K_w: 1, pygame.K_e: 2, pygame.K_r: 3}
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
            elif (self.minimap is not None and ev.type == pygame.MOUSEBUTTONDOWN
                  and self.minimap.contains(ev.pos)):
                self._minimap_click(ev)
            elif ev.type == pygame.KEYDOWN and ev.key in ABILITY_KEYS:
                slot = ABILITY_KEYS[ev.key]
                if pygame.key.get_mods() & pygame.KMOD_CTRL:
                    self.client.send_rank(slot)
                elif self._slot_castable(slot):
                    self.aiming_slot = slot
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

    def _tile(self, pos):
        wx, wy = self.camera.screen_window_to_world(*pos)
        return wx / config.TILE_SIZE, wy / config.TILE_SIZE

    def _cast(self, slot, pos):
        tx, ty = self._tile(pos)
        self.client.send_cast(slot, tx, ty)

    def _left_click(self, pos):
        tx, ty = self._tile(pos)
        tgt = self._pick_enemy(tx, ty)
        if tgt is not None:
            self.client.send_attack(tgt.id)
        else:
            self.client.send_attackmove(tx, ty)

    def _pick_enemy(self, tx, ty):
        best, bd = None, 1e9
        for e in self.world.combatants():
            if e.team == self.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Unit, Structure)):
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
            self.animators[u.id].update(dt, u.moving, u.facing)
        # Particelle d'atmosfera: aggiornate solo nel rettangolo visibile.
        self.particles.update(dt, self.camera, self.map_data.grid)
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
                           vision=self.vision, player_team=self.team,
                           now=self.world.match_time)
        # Gittata delle torri nemiche: cerchio di pericolo quando ti avvicini.
        self.renderer.draw_tower_ranges(surface, self.camera, self.world, self.team,
                                        now=self.world.match_time,
                                        player_pos=me.pos if me else None, near=6.0)
        # Particelle d'atmosfera della giungla (sopra mappa e unita, sotto la UI).
        self.particles.draw(surface, self.camera)
        if self.aiming_slot is not None and me is not None:
            s = self.world.hud["slots"][["Q", "W", "E", "R"][self.aiming_slot]]
            ms = self.disp_moveset.get(["Q", "W", "E", "R"][self.aiming_slot])
            mv = self._variant_move(ms, s["variant"])
            ready = mv is not None and s["rank"] > 0 and s["cd"] <= 0 and s["variant"] != -2
            if mv is not None and ready:   # niente mirino se in cooldown o non pronta
                mx, my = pygame.mouse.get_pos()
                wx, wy = self.camera.screen_window_to_world(mx, my)
                self.renderer.draw_aim(surface, self.camera, me.pos,
                                       (wx / config.TILE_SIZE, wy / config.TILE_SIZE), mv)

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
        h = self.world.hud
        lines = []
        if h is not None:
            t = int(h["time"])
            lines.append(f"Tempo {t // 60:02d}:{t % 60:02d}   Nucleo BLU {int(h['core0'])}   "
                         f"Nucleo ROSSO {int(h['core1'])}   Lv.{h['level']}   "
                         f"Oro {int(h.get('gold', 0))}   "
                         f"Meteo: {WEATHER_NAMES.get(CODE_WEATHER.get(h.get('weather', 0), 'clear'), '?')}"
                         f"  (P: negozio)")
            if self.world.winner is not None:
                squad = "BLU" if self.world.winner == 0 else "ROSSO"
                lines.append(f">>> VITTORIA squadra {squad}! <<<")
        lines.append("ONLINE  Dx: muovi  Sx: attacca  Q/W/E/R: mosse  Ctrl+tasto: grado  ESC: esci")
        return lines

    def draw_fullres(self, surface, font):
        h = self.world.hud
        if h is None:
            return
        slots = ["Q", "W", "E", "R"]
        bw, bh, gap = 72, 56, 10
        total = len(slots) * bw + (len(slots) - 1) * gap
        W, H = surface.get_size()
        x0 = (W - total) // 2
        y0 = H - bh - 12
        avail = h["points"]
        for i, sl in enumerate(slots):
            bx = x0 + i * (bw + gap)
            rect = pygame.Rect(bx, y0, bw, bh)
            pygame.draw.rect(surface, (28, 30, 36), rect)
            pygame.draw.rect(surface, (95, 95, 108), rect, 1)
            s = h["slots"][sl]
            ms = self.disp_moveset.get(sl)
            mv = self._variant_move(ms, s["variant"])
            name = mv.name if mv is not None else ("R: lv.8" if s["variant"] == -2 else "—")
            on_cd = mv is not None and s["rank"] > 0 and s["cd"] > 0
            if on_cd:
                frac = max(0.0, min(1.0, s["cd"] / max(0.1, mv.cooldown_at(s["rank"]))))
                ov = pygame.Surface((bw, int(bh * frac)), pygame.SRCALPHA)
                ov.fill((10, 12, 20, 180)); surface.blit(ov, (bx, y0))
            surface.blit(font.render(sl, True, (255, 230, 120)), (bx + 5, y0 + 3))
            ncol = (140, 140, 150) if on_cd else (230, 230, 230)
            surface.blit(font.render(name[:10], True, ncol), (bx + 5, y0 + bh - 20))
            if on_cd:
                txt = f"{s['cd']:.0f}" if s["cd"] >= 1.0 else f"{s['cd']:.1f}"
                num = font.render(txt, True, (255, 255, 255))
                surface.blit(num, (bx + bw // 2 - num.get_width() // 2,
                                   y0 + bh // 2 - num.get_height() // 2 - 2))
            maxr = 3 if sl == "R" else 4
            pip_w = (bw - 12) // maxr
            for r in range(maxr):
                col = (120, 210, 120) if r < s["rank"] else (70, 70, 82)
                pygame.draw.rect(surface, col, pygame.Rect(bx + 6 + r * pip_w, y0 + 21, pip_w - 2, 5))
        if avail > 0:
            surface.blit(font.render(f"Punti mossa: {avail} (Ctrl+Q/W/E/R)", True,
                                     (120, 220, 120)), (x0, y0 - 22))
        me = self.world.get(self.your_id)
        self.minimap.draw(surface, self.world, self.camera, self.vision, self.team,
                          self.map_data.dens, me)
        if self._pending():
            self._draw_choice_menu(surface, font)

        if self.shop.open:
            near = me is not None and me.pos.dist(self.base) <= config.SHOP_RANGE
            self.shop.draw(surface, font, self.item_catalog, h.get("gold", 0),
                           h.get("items", []), self.pdef.role, near)

    def _draw_choice_menu(self, surface, font):
        slot = ["Q", "W", "E", "R"][self._pending()[0]]
        ms = self.disp_moveset.get(slot)
        if not ms or not ms.upgrades:
            return
        W, H = surface.get_size()
        panel = pygame.Rect(W // 2 - 230, H // 2 - 80, 460, 150)
        bg = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA); bg.fill((18, 18, 26, 235))
        surface.blit(bg, panel)
        pygame.draw.rect(surface, (210, 200, 120), panel, 2)
        title = "EVOLUZIONE - scegli l'ultimate (R)" if slot == "R" else f"EVOLUZIONE - potenziamento {slot}"
        surface.blit(font.render(title, True, (255, 230, 120)), (panel.x + 14, panel.y + 10))
        for i, mv in enumerate(ms.upgrades[:2]):
            surface.blit(font.render(f"[{i + 1}]  {mv.name}", True, (235, 235, 235)),
                         (panel.x + 18, panel.y + 40 + i * 40))
            surface.blit(font.render(f"{mv.type} · {mv.shape} · {mv.category}", True,
                                     (165, 165, 180)), (panel.x + 46, panel.y + 58 + i * 40))
        near = self._near_base()
        hint = "Premi 1 / 2 per scegliere" if near else "Torna in BASE per scegliere"
        surface.blit(font.render(hint, True, (150, 220, 150) if near else (230, 170, 120)),
                     (panel.x + 14, panel.bottom - 22))
