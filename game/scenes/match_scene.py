"""Scena di partita.

- Se la mappa ha le strutture MOBA (lane, torri, nucleo), avvia una partita
  3v3 contro/insieme a bot: il giocatore controlla un Pokémon della squadra 0.
- Altrimenti ripiega sulla demo della Fase 1 (un solo Pokémon su mappa libera).

La logica di gioco sta in engine/sim; qui c'è solo l'orchestrazione lato client.
"""
from __future__ import annotations

import random
from pathlib import Path

import pygame

import config
from engine import skills
from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.vec import Vec2
from engine.eevee import CHOICE_SLOTS, chosen_index, eevee_candidates, eevee_forms
from engine.world import World
from sim.commands import (BuyItemCommand, ChooseUpgradeCommand, MoveCommand,
                          RankMoveCommand, RecallCommand, SellItemCommand)
from sim.simulation import Simulation

from ..camera import Camera
from ..fx import FXSystem, draw_avalanche, draw_sandstorm, type_color
from ..input_controller import InputController
from ..minimap import Minimap
from .. import eevee_fx, spirit_fx
from ..particles import ParticleSystem
from ..renderer import Renderer
from ..shop_ui import ShopUI
from ..sprites.animator import FallbackAnimator, SpriteAnimator
from ..sprites.spritesheet import load_pokemon_animations

ROOT = Path(__file__).resolve().parents[2]
LANE_SLOTS = ["top", "mid", "bot"]
# Piccoli scostamenti per non far nascere i tre alleati esattamente sovrapposti.
SLOT_OFFSET = {"top": Vec2(-1.2, 0.0), "mid": Vec2(0.0, 0.0), "bot": Vec2(0.0, 1.2)}
DEATH_FADE = 1.5   # s: posa Hurt tenuta mentre l'unità si dissolve alla morte


class MatchScene:
    def __init__(self, map_path: str, pokemon_path: str, start_level: int = 1,
                 start_items=None, bot_paths=None):
        map_data = load_map(map_path)
        self.map_data = map_data
        self.world = World(map_data.grid)
        self.pdef = load_pokemon_def(pokemon_path)
        self._bot_paths = bot_paths
        # Definizione di ogni Pokémon in campo (id -> PokemonDef) e, per gli sprite,
        # dex -> cartella sprite di TUTTE le forme dei Pokémon in partita.
        self._unit_defs: dict = {}
        self._dex_sprite: dict = {}
        self._sprite_key: dict = {}   # id -> (dex, stadio, forma) dello sprite attuale
        self._register_def(self.pdef)

        self.animators: dict[int, object] = {}
        self._dying: dict = {}      # unità morte: anim Hurt + dissolvenza breve
        self._sprite_cache: dict = {}
        self._portraits: dict = {}   # (sprite_dir, lato) -> ritratto (icona passiva Eevee)

        self.camera_locked = True
        self.match: Match | None = None

        if map_data.is_moba_map:
            self._setup_moba()
        else:
            self._setup_demo()

        # Oggetti di partenza (test): es. --item king_rock per far evolvere
        # Poliwhirl in Politoad all'arrivo al liv.8. Vanno dati PRIMA del livello,
        # così la condizione di ramo è soddisfatta quando scatta l'evoluzione.
        if start_items and self.match is not None and self.player is not None:
            for iid in start_items:
                if self.match.item_catalog.get(iid) is not None:
                    self.player.items.append(iid)
            self.match._apply_items(self.player)

        # Livello di partenza (test): porta il giocatore al livello richiesto.
        if start_level > 1 and self.match is not None and self.player is not None:
            from engine.stats import CUMULATIVE_XP
            lvl = max(1, min(start_level, len(CUMULATIVE_XP) - 1))
            self.match._gain_xp(self.player, CUMULATIVE_XP[lvl] + 1.0)

        # Camera.
        map_w_px = map_data.grid.width * config.TILE_SIZE
        map_h_px = map_data.grid.height * config.TILE_SIZE
        self.camera = Camera(config.LOWRES_WIDTH, config.LOWRES_HEIGHT, map_w_px, map_h_px)
        self.camera.center_on(self.player.pos.x * config.TILE_SIZE,
                              self.player.pos.y * config.TILE_SIZE)
        self.input = InputController(self.player.id)
        self.renderer = Renderer()
        self.renderer.map.set_camps(map_data.camps)   # sentieri di terra verso le lane
        self.fx = FXSystem()
        # Particelle d'atmosfera (lucciole/polline/foglie): cosmetiche, aggiornate
        # solo dentro la camera, al massimo ~60 a schermo.
        self.particles = ParticleSystem()
        self._menu_seq = 0
        # Nebbia di guerra + minimappa solo nelle mappe MOBA. La visione è
        # calcolata dal Match (motore), così la condividono bot e client.
        self.vision = self.match.vision if self.match is not None else None
        self.minimap = Minimap(map_data.grid, map_data) if map_data.is_moba_map else None
        self._mm_version = -1
        self.shop = ShopUI()
        self._skill_rects = {}      # slot -> rect (click per salire di grado)
        self._choice_rects = []     # (rect, slot, idx) per scegliere il potenziamento

    # --- allestimento --------------------------------------------------------
    def _register_def(self, pdef) -> None:
        """Annota le cartelle sprite di tutte le forme di `pdef` (per dex)."""
        if pdef.sprite_dir:
            self._dex_sprite.setdefault(pdef.dex, pdef.sprite_dir)
        for e in pdef.evolutions:
            if e.get("dex") is not None and e.get("sprite_dir"):
                self._dex_sprite.setdefault(int(e["dex"]), e["sprite_dir"])

    def _bot_defs(self, n):
        """Definizioni dei `n` bot: quelle passate (bot_paths) oppure Pokémon CASUALI
        dal roster, SENZA ripetizioni (né tra loro né col giocatore). Si ripete solo
        se il roster non basta a coprire tutti gli slot."""
        if self._bot_paths:
            paths = list(self._bot_paths)
        else:
            pool = [rel for rel in config.ROSTER
                    if load_pokemon_def(str(ROOT / rel)).dex != self.pdef.dex]
            random.shuffle(pool)
            paths = pool[:n]
            while len(paths) < n and pool:
                paths.append(random.choice(pool))
        defs = [load_pokemon_def(str(ROOT / p)) for p in paths]
        while len(defs) < n:
            defs.append(self.pdef)
        return defs[:n]

    def _spawn_pokemon(self, team, lane, is_bot, pdef=None):
        pdef = pdef or self.pdef
        self._register_def(pdef)
        base = Vec2(*self.map_data.spawns[f"team{team}"]) + Vec2(0.5, 0.5)
        pos = base + SLOT_OFFSET[lane]
        color = config.TEAM_COLORS[team]
        p = self.world.spawn_pokemon(pos=pos, team=team, dex=pdef.dex,
                                     name=pdef.name, color=color,
                                     speed=pdef.base_speed, is_bot=is_bot,
                                     assigned_lane=lane, types=pdef.types,
                                     base_stats=pdef.base_stats,
                                     growth=pdef.growth, moves=pdef.moves,
                                     evolutions=pdef.evolutions, role=pdef.role,
                                     passive=pdef.passive,
                                     attack_range=pdef.attack_range,
                                     attack_cooldown=pdef.attack_cooldown)
        p.radius = pdef.radius
        self._unit_defs[p.id] = pdef
        return p

    def _setup_moba(self):
        self.match = Match(self.world, self.map_data)
        # team_size Pokémon per squadra (3v3 o 5v5), lane a rotazione. Il giocatore
        # prende il primo slot in mid; il resto della squadra 0 e tutta la 1 sono bot.
        self.player = None
        ts = self.map_data.team_size
        bots = iter(self._bot_defs(2 * ts - 1))
        for slot in range(ts):
            lane = LANE_SLOTS[slot % 3]
            is_player = self.player is None and lane == "mid"
            p0 = self._spawn_pokemon(0, lane, is_bot=not is_player,
                                     pdef=None if is_player else next(bots))
            if is_player:
                self.player = p0
            self._spawn_pokemon(1, lane, is_bot=True, pdef=next(bots))
        if self.player is None:   # fallback (team molto piccoli)
            self.player = self.world.pokemons()[0]
            self.player.is_bot = False
        self.match.assign_junglers()
        self.sim = Simulation(self.world, config.TICK_DT, match=self.match)
        # Calcola subito la visione iniziale (evita un frame tutto in nebbia).
        self.match.vision.update(self.world, 0)
        self.match.vision.update(self.world, 1)

    def _setup_demo(self):
        spawn = self.map_data.spawns.get("team0", (self.map_data.grid.width // 2,
                                                   self.map_data.grid.height // 2))
        pos = Vec2(spawn[0] + 0.5, spawn[1] + 0.5)
        self.player = self.world.spawn_pokemon(pos=pos, team=0, dex=self.pdef.dex,
                                               name=self.pdef.name, color=self.pdef.color,
                                               speed=self.pdef.base_speed,
                                               types=self.pdef.types,
                                               base_stats=self.pdef.base_stats,
                                               growth=self.pdef.growth,
                                               moves=self.pdef.moves,
                                               evolutions=self.pdef.evolutions,
                                               role=self.pdef.role, passive=self.pdef.passive,
                                               attack_range=self.pdef.attack_range,
                                               attack_cooldown=self.pdef.attack_cooldown)
        self.player.radius = self.pdef.radius
        self._unit_defs[self.player.id] = self.pdef
        self.sim = Simulation(self.world, config.TICK_DT)

    def _load_anim(self, sprite_dir):
        if not sprite_dir:
            return None
        if sprite_dir not in self._sprite_cache:
            self._sprite_cache[sprite_dir] = load_pokemon_animations(sprite_dir)
        return self._sprite_cache[sprite_dir]

    def _unit_sprite_dir(self, unit):
        """Cartella sprite della forma ATTUALE di un Pokémon. Si risolve per DEX
        (così funzionano anche i rami, es. Poliwrath/Politoad allo stesso stadio,
        e il clone esca che copia il dex del lanciatore); forma Shedinja a parte."""
        if getattr(unit, "form", "") == "shedinja":
            return "assets/pokemon/0292"
        sd = self._dex_sprite.get(unit.dex)
        if sd:
            return sd
        pdef = self._unit_defs.get(unit.id)
        return pdef.sprite_dir if pdef is not None else None

    @staticmethod
    def _sprite_state(unit):
        return (unit.dex, unit.stage, getattr(unit, "form", ""))

    def _make_animator(self, unit):
        from engine.entities import Minion, Pokemon
        # Tutti i Pokémon (giocatore, bot, cloni esca) usano gli sprite reali.
        if isinstance(unit, Pokemon):
            self._sprite_key[unit.id] = self._sprite_state(unit)
            aset = self._load_anim(self._unit_sprite_dir(unit))
            if aset is not None:
                return SpriteAnimator(aset)
        # I minion usano la skin per squadra+tipo (ridimensionata piccola).
        if isinstance(unit, Minion):
            aset = self._load_anim(f"assets/minions/{unit.team}_{unit.minion_type}")
            if aset is not None:
                return SpriteAnimator(aset, scale=self._minion_scale(unit, aset))
        radius_px = int(unit.radius * config.TILE_SIZE)
        color = getattr(unit, "color", (200, 200, 200))
        return FallbackAnimator(color, radius_px)

    @staticmethod
    def _minion_scale(unit, aset):
        wf = aset.get("Walk") or aset.get("Idle")
        fh = wf.frames[0][0].get_height() if (wf and wf.frames and wf.frames[0]) else 48
        target = max(16, int(unit.radius * config.TILE_SIZE * 4.5))
        return target / max(1, fh)

    # --- ciclo ---------------------------------------------------------------
    def handle_events(self, events) -> None:
        passthrough = []
        for ev in events:
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.quit_app = True
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_p and self.match is not None:
                self.shop.toggle()
            elif (self.shop.open and ev.type == pygame.MOUSEBUTTONDOWN
                  and self.shop.consumes(ev.pos)):
                action = self.shop.handle_event(ev)
                if action is not None:
                    self._shop_action(action)
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_y:
                self.camera_locked = not self.camera_locked
            elif (ev.type == pygame.KEYDOWN and ev.key == pygame.K_h
                  and self.match is not None):
                # Test (solo locale): entra subito nella forma Shedinja.
                self.match.force_shedinja(self.player)
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_b:
                self._menu_seq += 1
                self.sim.queue_command(RecallCommand(seq=50_000 + self._menu_seq,
                                                     entity_id=self.player.id))
            # Menu evoluzione (nessuna pausa): tasti 1/2 scelgono il potenziamento.
            elif (ev.type == pygame.KEYDOWN and ev.key in (pygame.K_1, pygame.K_2)
                  and self.player.pending_choices
                  and self.player.pos.dist(self.player.spawn_pos) <= config.SHOP_RANGE):
                slot = self.player.pending_choices[0]
                idx = 0 if ev.key == pygame.K_1 else 1
                self._menu_seq += 1
                self.sim.queue_command(ChooseUpgradeCommand(
                    seq=10_000 + self._menu_seq, entity_id=self.player.id,
                    slot=slot, index=idx))
            elif (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1
                  and self._skillbar_click(ev.pos)):
                pass   # clic consumato dalla barra abilità (grado o scelta)
            elif (self.minimap is not None and ev.type == pygame.MOUSEBUTTONDOWN
                  and self.minimap.contains(ev.pos)):
                self._minimap_click(ev)
            else:
                passthrough.append(ev)
        for cmd in self.input.process(passthrough, self.camera, self.world):
            self.sim.queue_command(cmd)

    def _skillbar_click(self, pos) -> bool:
        for r, sl, idx in self._choice_rects:         # scelta del potenziamento (in base)
            if r.collidepoint(pos):
                self._menu_seq += 1
                self.sim.queue_command(ChooseUpgradeCommand(
                    seq=10_000 + self._menu_seq, entity_id=self.player.id, slot=sl, index=idx))
                return True
        for sl, r in self._skill_rects.items():        # clic sulla casella -> assegna grado
            if r.collidepoint(pos):
                self._menu_seq += 1
                self.sim.queue_command(RankMoveCommand(
                    seq=40_000 + self._menu_seq, entity_id=self.player.id, slot=sl))
                return True
        return False

    def _shop_action(self, action) -> None:
        kind, val = action
        self._menu_seq += 1
        if kind == "buy":
            self.sim.queue_command(BuyItemCommand(seq=30_000 + self._menu_seq,
                                                  entity_id=self.player.id, item_id=val))
        elif kind == "sell":
            self.sim.queue_command(SellItemCommand(seq=30_000 + self._menu_seq,
                                                   entity_id=self.player.id, slot=val))

    def _minimap_click(self, ev) -> None:
        tx, ty = self.minimap.to_world_tile(ev.pos)
        if ev.button == 3:   # destro: ordina di spostarsi lì
            self._menu_seq += 1
            self.sim.queue_command(MoveCommand(seq=20_000 + self._menu_seq,
                                               entity_id=self.player.id, x=tx, y=ty))
        elif ev.button == 1:  # sinistro: sposta la camera lì
            self.camera_locked = False
            self.camera.center_on(tx * config.TILE_SIZE, ty * config.TILE_SIZE)

    def fixed_update(self) -> None:
        self.sim.step()

    def update(self, dt: float) -> None:
        for u in self.world.units():
            if u.id not in self.animators:
                self.animators[u.id] = self._make_animator(u)
        # Cambio sprite quando un Pokémon (giocatore o bot) si evolve, anche di
        # RAMO (stesso stadio, dex diverso), o entra/esce dalla forma Shedinja.
        for p in self.world.pokemons():
            key = self._sprite_state(p)
            if self._sprite_key.get(p.id, key) != key:
                self._sprite_key[p.id] = key
                aset = self._load_anim(self._unit_sprite_dir(p))
                if aset is not None:
                    self.animators[p.id] = SpriteAnimator(aset)

        keys = pygame.key.get_pressed()
        space_held = keys[pygame.K_SPACE]
        mouse_win = pygame.mouse.get_pos()
        tx = self.player.pos.x * config.TILE_SIZE
        ty = self.player.pos.y * config.TILE_SIZE
        self.camera.update(dt, self.camera_locked, tx, ty, mouse_win, space_held)

        alive_ids = {u.id for u in self.world.alive_units()}
        for u in self.world.alive_units():
            anim = self.animators.get(u.id)
            if anim is not None:
                anim.update(dt, u.moving, u.facing)

        # Morte: avvia l'animazione Hurt + dissolvenza (così si capisce che sei morto).
        for uid in list(self.animators.keys()):
            if uid in alive_ids or uid in self._dying:
                continue
            u = self.world.get(uid)
            anim = self.animators.get(uid)
            if u is not None and isinstance(anim, SpriteAnimator):
                # Animatore separato bloccato sulla posa Hurt (il condiviso resta
                # pulito per il respawn); si dissolve senza tornare a Idle.
                death = SpriteAnimator(anim.anim_set, scale=anim.scale)
                death.facing = u.facing
                death.freeze("Hurt")
                self._dying[uid] = {"anim": death, "pos": Vec2(u.pos.x, u.pos.y),
                                    "t": 0.0}
        for uid, d in list(self._dying.items()):
            if uid in alive_ids:               # risorto: interrompi la dissolvenza
                del self._dying[uid]; continue
            d["t"] += dt
            if d["t"] >= DEATH_FADE:
                del self._dying[uid]
        # Pulizia animatori di unità rimosse (es. minion) non in dissolvenza.
        for uid in list(self.animators.keys()):
            if uid not in alive_ids and uid not in self._dying and self.world.get(uid) is None:
                del self.animators[uid]

        # Effetti visivi delle mosse (cosmetici): consuma gli eventi della sim.
        if self.match is not None and self.match.fx_events:
            self._trigger_anims(self.match.fx_events)
            self.fx.spawn_events(self.match.fx_events)
            self.match.fx_events.clear()
        # Frana: polvere sollevata dietro la valanga che rotola.
        if self.match is not None:
            for av in self.match.avalanches:
                if self.match.time >= av["start"] and random.random() < 0.6:
                    d, r = av["dir"], av["radius"]
                    self.fx._dust((av["pos"].x - d.x * r, av["pos"].y - d.y * r), r * 0.7,
                                  n=2, speed=(0.3, 1.2))
        self.fx.update(dt)
        # Particelle d'atmosfera: aggiornate solo nel rettangolo visibile.
        self.particles.update(dt, self.camera, self.map_data.grid)

        # La visione la calcola il Match; qui rigenero la nebbia della minimappa
        # solo quando è davvero cambiata (versione).
        if self.vision is not None and self.minimap is not None:
            v = self.vision.version.get(self.player.team, 0)
            if v != self._mm_version:
                self._mm_version = v
                self.minimap.rebuild_fog(self.vision, self.player.team)

    def _trigger_anims(self, events) -> None:
        """Avvia le animazioni una-tantum (Attack/Shoot) dagli eventi FX."""
        for e in events:
            eid = e.get("eid")
            name = e.get("anim")
            if eid is not None and name:
                anim = self.animators.get(eid)
                if isinstance(anim, SpriteAnimator):
                    anim.play_once(name, float(e.get("anim_speed", 1.0)))

    def draw(self, surface) -> None:
        path_pts = [self.player.pos] + self.player.path if self.player.alive else []
        sel = self.player.id if self.player.alive else None
        respawning = None
        if self.match is not None:
            respawning = [(p.spawn_pos, p.team,
                           1.0 - max(0.0, p.respawn_timer) / max(0.1, p.respawn_max))
                          for p in self.world.pokemons() if not p.alive]
        self.renderer.draw(surface, self.world, self.camera, self.animators,
                           selected_path=path_pts, selected_id=sel,
                           dens=self.map_data.dens or None, respawning=respawning,
                           vision=self.vision, player_team=self.player.team,
                           now=self.match.time if self.match else 1e9)
        # Gittata delle torri nemiche: cerchio di pericolo quando ti avvicini.
        if self.match is not None:
            self.renderer.draw_tower_ranges(surface, self.camera, self.world,
                                             self.player.team, now=self.match.time,
                                             player_pos=self.player.pos, near=6.0)
        # Linea Roggenrola: tempesta di Sabbiafiume (aura permanente) e valanghe
        # di Frana, disegnate dallo stato del Match (sopra mappa e unità).
        if self.match is not None:
            now = self.match.time
            for p in self.world.pokemons():
                if p.alive and p.sand_radius > 0.0 and (
                        p.team == self.player.team or self.vision is None
                        or self.vision.is_enemy_visible(self.player.team, p.id)):
                    draw_sandstorm(surface, self.camera, p.pos, p.sand_radius, now)
            for av in self.match.avalanches:
                if now >= av["start"]:
                    draw_avalanche(surface, self.camera, av, now)
            self._draw_spiritomb(surface, now)
            self._draw_eevee(surface, now)
        # Particelle d'atmosfera della giungla (ambientali, sopra mappa e unita,
        # sotto gli effetti delle mosse e la UI).
        self.particles.draw(surface, self.camera)
        # Unità in morte: Hurt che svanisce (sopra la mappa).
        ts = config.TILE_SIZE
        for d in self._dying.values():
            gx, gy = self.camera.world_to_screen(d["pos"].x * ts, d["pos"].y * ts)
            alpha = int(255 * max(0.0, 1.0 - d["t"] / DEATH_FADE))
            d["anim"].draw(surface, gx, gy, alpha=alpha)
        # Proiettili che viaggiano (bolla Idropulsar).
        if self.match is not None:
            for pr in self.match.projectiles:
                gx, gy = self.camera.world_to_screen(pr["pos"].x * ts, pr["pos"].y * ts)
                col = type_color(pr["mtype"])
                r = max(3, int(pr["radius"] * ts))
                glow = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
                pygame.draw.circle(glow, (*col, 70), (r * 2, r * 2), r * 2)
                surface.blit(glow, (gx - r * 2, gy - r * 2))
                pygame.draw.circle(surface, col, (gx, gy), r)
                pygame.draw.circle(surface, (255, 255, 255), (gx, gy), r, 1)
        # Indicatore di mira (solo se la mossa è pronta: niente mirino in cooldown).
        if self.input.aiming_slot and self.player.alive:
            ms = self.player.moveset.get(self.input.aiming_slot)
            if ms and ms.chosen and ms.ready:
                mx, my = pygame.mouse.get_pos()
                wx, wy = self.camera.screen_window_to_world(mx, my)
                self.renderer.draw_aim(surface, self.camera, self.player.pos,
                                       (wx / config.TILE_SIZE, wy / config.TILE_SIZE),
                                       ms.chosen)
        # Particelle degli effetti.
        self.fx.draw(surface, self.camera)

    def _draw_spiritomb(self, surface, now) -> None:
        """Spiritomb: spiriti (solo quelli della propria squadra), ondata della
        Legione, legami di Malcomune e proiettili di Stordiraggio."""
        m = self.match
        team = self.player.team

        def seen(pos):
            return (self.vision is None
                    or self.vision.is_tile_visible(team, int(pos.x), int(pos.y)))

        reach = pick = None
        if self.input.aiming_slot and self.player.alive:
            ms = self.player.moveset.get(self.input.aiming_slot)
            if ms and ms.chosen and ms.ready and ms.chosen.shape == "spiritcall":
                reach = (self.player.pos, ms.chosen.range)
                mx, my = pygame.mouse.get_pos()
                wx, wy = self.camera.screen_window_to_world(mx, my)
                pick = m._spirit_call_target(self.player, ms.chosen,
                                             Vec2(wx / config.TILE_SIZE, wy / config.TILE_SIZE))
                if pick is not None:   # filo verso lo spirito scelto
                    ts = config.TILE_SIZE
                    a = self.camera.world_to_screen(self.player.pos.x * ts, self.player.pos.y * ts)
                    b = self.camera.world_to_screen(pick.pos.x * ts, pick.pos.y * ts)
                    pygame.draw.line(surface, spirit_fx.LIME_HI, a, b, 1)
        # Solo i PROPRI spiriti: quelli di un altro Spiritomb alleato non si
        # possono raccogliere, quindi non vanno mostrati.
        mine = [s for s in self.world.spirits if s.owner_id == self.player.id]
        spirit_fx.draw_spirits(surface, self.camera, mine, team, now,
                               reach=reach, pick=pick)
        for w in m.legion_waves:
            spirit_fx.draw_legion_wave(surface, self.camera, w, now)
        for bd in m.pain_binds:
            c = self.world.get(bd["caster_id"])
            if c is not None and (c.team == team or seen(c.pos)):
                spirit_fx.draw_pain_bind(surface, self.camera, bd, self.world, now)
        for b in m.spirit_beams:
            if b["team"] == team or seen(b["pos"]):
                spirit_fx.draw_spirit_beam(surface, self.camera, b, now)

    def _draw_eevee(self, surface, now) -> None:
        """Linea Eevee: stelle di Comete, Desiderio, nube del Tuono, Bora e
        Divinazione (le proprie sempre, le nemiche solo se nella visione)."""
        m = self.match
        team = self.player.team

        def seen(pos, t):
            return (t == team or self.vision is None
                    or self.vision.is_tile_visible(team, int(pos.x), int(pos.y)))

        for th in m.thunders:
            if seen(th["c"], th["team"]):
                eevee_fx.draw_thunder(surface, self.camera, th, now)
        for bz in m.blizzards:
            if seen(bz["c"], bz["team"]):
                eevee_fx.draw_blizzard(surface, self.camera, bz, now)
        for fs in m.future_sights:
            if seen(fs["c"], fs["team"]):
                eevee_fx.draw_future_sight(surface, self.camera, fs, now)
        for w in m.wishes:
            tgt = self.world.get(w["target_id"])
            if tgt is not None and seen(tgt.pos, tgt.team):
                eevee_fx.draw_wish(surface, self.camera, w, self.world, now)
        for st in m.swift_stars:
            if seen(st["pos"], st["team"]):
                eevee_fx.draw_swift_star(surface, self.camera, st, now)

    def _portrait(self, sprite_dir, side):
        """Ritratto di una forma (primo fotogramma Idle verso il basso), ritagliato
        e scalato NEAREST a `side` px. In cache."""
        key = (sprite_dir, side)
        if key not in self._portraits:
            img = None
            aset = self._load_anim(sprite_dir)
            idle = aset.get("Idle") if aset is not None else None
            if idle is not None and idle.frames and idle.frames[0]:
                fr = idle.frames[0][0]
                fr = fr.subsurface(fr.get_bounding_rect()).copy()
                k = side / max(fr.get_width(), fr.get_height())
                img = pygame.transform.scale(fr, (max(1, int(fr.get_width() * k)),
                                                  max(1, int(fr.get_height() * k))))
            self._portraits[key] = img
        return self._portraits[key]

    def _draw_adaptability(self, surface, font, p, bx, y0, bh) -> None:
        """Passiva Adattabilità (Eevee): icona della forma verso cui vanno le scelte
        ("?" senza scelte; con più forme possibili scorre tra quelle) e barra con
        gli 8 colori delle forme (accese quelle ancora raggiungibili)."""
        forms = eevee_forms(p)
        cands = eevee_candidates(p)
        now = self.match.time if self.match is not None else 0.0
        box = pygame.Rect(bx, y0, bh, bh)
        pygame.draw.rect(surface, (24, 22, 30), box)
        one = cands[0] if len(cands) == 1 else None
        if len(cands) == len(forms):
            q = font.render("?", True, (235, 225, 200))
            q = pygame.transform.scale(q, (q.get_width() * 2, q.get_height() * 2))
            surface.blit(q, (box.centerx - q.get_width() // 2, box.centery - q.get_height() // 2))
            frame = (120, 112, 100)
        else:
            show = one or cands[int(now / 0.8) % len(cands)]
            img = self._portrait(show["sprite_dir"], bh - 10)
            if img is not None:
                if one is None:
                    img = img.copy()
                    img.set_alpha(150)   # ancora incerto: ritratto attenuato
                surface.blit(img, (box.centerx - img.get_width() // 2,
                                   box.centery - img.get_height() // 2))
            frame = tuple(show["form_color"])
        pygame.draw.rect(surface, frame, box, 2 if one else 1)
        # Barra degli 8 colori (verticale, accanto all'icona).
        seg_h = bh // len(forms)
        bar_x = box.right + 4
        for i, st in enumerate(forms):
            col = tuple(st["form_color"])
            on = st in cands
            if not on:
                col = tuple(int(c * 0.22 + 20) for c in col)
            r = pygame.Rect(bar_x, y0 + i * seg_h, 10, seg_h - 1)
            pygame.draw.rect(surface, col, r)
            if on and one is not None:
                pygame.draw.rect(surface, (255, 255, 255), r.inflate(2, 2), 1)
        pygame.draw.rect(surface, (90, 86, 96), pygame.Rect(bar_x - 1, y0 - 1, 12, seg_h * len(forms) + 1), 1)
        title = one["name"] if one else ("Adattabilità" if len(cands) == len(forms)
                                         else f"{len(cands)} forme")
        tcol = tuple(one["form_color"]) if one else (225, 215, 190)
        if one and sum(tcol) < 200:   # Umbreon (nero): testo leggibile
            tcol = (200, 200, 215)
        surface.blit(font.render(title, True, tcol), (bx - 4, y0 - 18))

    def _draw_form_passive(self, surface, font, p, bx, y0, bh) -> None:
        """Passiva della forma evoluta di Eevee: ritratto + nome + stato."""
        st = next((e for e in p.evolutions if e.get("dex") == p.dex), None)
        if st is None:
            return
        now = self.match.time if self.match is not None else 0.0
        col = tuple(st.get("form_color", (200, 200, 200)))
        box = pygame.Rect(bx, y0, bh, bh)
        pygame.draw.rect(surface, (24, 22, 30), box)
        img = self._portrait(st["sprite_dir"], bh - 10)
        if img is not None:
            surface.blit(img, (box.centerx - img.get_width() // 2, box.centery - img.get_height() // 2))
        info = ""
        lit = True
        if p.passive_id == "assorbivolt":
            left = p.voltabsorb_ready_at - now
            lit = left <= 0
            info = "pronto" if lit else f"{left:0.0f}s"
        elif p.passive_id == "fuocardore":
            left = p.flashfire_until - now
            lit = left > 0
            info = f"+30% {left:0.1f}s" if lit else ""
        elif p.passive_id == "idratazione":
            lit = self.match is not None and self.match._in_rain(p)
            info = "pioggia" if lit else ""
        elif p.passive_id == "fogliamanto":
            lit = self.match is not None and self.match.jungle.weather == "sun"
            info = "sole" if lit else ""
        frame = col if lit else tuple(int(c * 0.5) for c in col)
        if sum(frame) < 200:
            frame = (150, 150, 170)
        pygame.draw.rect(surface, frame, box, 2 if lit else 1)
        name = eevee_fx.PASSIVE_NAMES.get(p.passive_id, p.passive_id)
        if info:
            name += f" {info}"
        surface.blit(font.render(name, True, frame), (bx - 4, y0 - 18))

    def _respawn_status(self, team: int) -> str:
        name = "BLU" if team == 0 else "ROSSO"
        pk = [p for p in self.world.pokemons() if p.team == team]
        alive = sum(p.alive for p in pk)
        dead = [p for p in pk if not p.alive]
        if dead:
            soon = min(p.respawn_timer for p in dead)
            return f"{name} {alive}/{len(pk)} vivi (prossimo {soon:.0f}s)"
        return f"{name} {alive}/{len(pk)} vivi"

    def hud_lines(self) -> list[str]:
        cam = "AGGANCIATA" if self.camera_locked else "LIBERA"
        lines = []
        if self.match is not None:
            t = int(self.match.time)
            cores = {c.team: c for c in self.world.cores()}
            c0 = int(cores[0].hp) if 0 in cores else 0
            c1 = int(cores[1].hp) if 1 in cores else 0
            next_wave = max(0, int(self.match._wave_timer))
            lines.append(f"Tempo {t // 60:02d}:{t % 60:02d}   Nucleo BLU {c0}   "
                         f"Nucleo ROSSO {c1}   Prossima ondata: {next_wave}s")
            from engine.jungle import WEATHER_NAMES
            lines.append(f"Respawn - {self._respawn_status(0)}   {self._respawn_status(1)}   "
                         f"Meteo: {WEATHER_NAMES.get(self.match.jungle.weather, '?')}")
            p = self.player
            atkm = "+" if p.atk_mult > 1.0 else ""
            difm = "+" if p.def_buff_active else ("-" if p.def_debuff_active else "")
            # L'Att. Speciale non e' un valore di danno ma il MOLTIPLICATORE abilita'
            # (0,6 + 0,004 x SpA_eff); l'AP vero viene dagli oggetti. Mostro entrambi
            # cosi' lo "speciale" non sembra zero.
            lines.append(
                f"{p.name} Lv.{p.level}  HP {int(p.hp)}/{int(p.max_hp)}  "
                f"Atk {int(p.eff_attack())}{atkm}  Dif {int(p.eff_defense())}{difm}  "
                f"DifSp {int(p.eff_sp_defense())}  MoltAbil x{p.ability_mult:.2f}  "
                f"AP {int(p.eff_sp_attack())}  Oro {int(p.gold)}  (P: negozio)")
            if self.player.recalling:
                left = max(0.0, self.player.recall_until - self.match.time)
                lines.append(f"RICHIAMO in corso... {left:.1f}s (muoviti o subisci danno per annullare)")
            if not self.player.alive:
                lines.append(f"ABBATTUTO - respawn tra {self.player.respawn_timer:.0f}s")
            if self.match.winner is not None:
                squad = "BLU" if self.match.winner == 0 else "ROSSO"
                lines.append(f">>> VITTORIA squadra {squad}! <<<")
        lines.append(f"camera: {cam}   Dx: muovi  Sx: attacca  Q/W/E/R: mosse  "
                     f"Ctrl/clic: grado  B: richiamo  P: negozio  Y: camera  ESC: esci")
        return lines

    # --- UI a piena risoluzione (barra mosse + menu evoluzione) --------------
    def draw_fullres(self, surface, font) -> None:
        if self.match is None:
            return
        p = self.player
        W, H = surface.get_size()
        slots = ["Q", "W", "E", "R"]
        bw, bh, gap = 72, 56, 10
        total = len(slots) * bw + (len(slots) - 1) * gap
        x0 = (W - total) // 2
        y0 = H - bh - 12
        avail = skills.available_points(p)

        self._skill_rects = {}
        self._choice_rects = []
        near_base = p.pos.dist(p.spawn_pos) <= config.SHOP_RANGE
        for i, sl in enumerate(slots):
            bx = x0 + i * (bw + gap)
            rect = pygame.Rect(bx, y0, bw, bh)
            self._skill_rects[sl] = rect
            ms = p.moveset.get(sl)
            pygame.draw.rect(surface, (28, 30, 36), rect)
            evolvable = ms is not None and sl in p.pending_choices and ms.upgrades
            if evolvable:
                pygame.draw.rect(surface, (235, 210, 90), rect, 2)   # bordo: evolvibile
            else:
                pygame.draw.rect(surface, (95, 95, 108), rect, 1)
            name = "—"
            on_cd = False
            cd_left = 0.0
            charge_count = None
            if ms and ms.chosen and ms.unlocked:
                mv = ms.chosen
                name = mv.name
                if mv.charges > 0 and ms.rank > 0:
                    # Mossa a cariche (Erboscivolata): riempimento + numero di cariche.
                    cur = ms.charges_cur if ms.charges_cur >= 0 else float(mv.charges)
                    whole = max(0, min(mv.charges, int(cur + 1e-6)))
                    charge_count = whole
                    prog = 1.0 if whole >= mv.charges else (cur - int(cur))
                    if whole == 0:
                        on_cd = True
                        # velo scuro che si svuota dal basso col caricarsi della carica
                        empty_h = int(bh * (1.0 - prog))
                        ov = pygame.Surface((bw, empty_h), pygame.SRCALPHA)
                        ov.fill((10, 12, 20, 180))
                        surface.blit(ov, (bx, y0))
                    elif whole < mv.charges:
                        # barra sottile: ricarica della prossima carica
                        pw = int((bw - 10) * prog)
                        pygame.draw.rect(surface, (40, 44, 54), pygame.Rect(bx + 5, y0 + bh - 6, bw - 10, 4))
                        pygame.draw.rect(surface, (120, 200, 140), pygame.Rect(bx + 5, y0 + bh - 6, pw, 4))
                elif ms.rank > 0 and ms.cooldown_remaining > 0:
                    on_cd = True
                    cd_left = ms.cooldown_remaining
                    frac = max(0.0, min(1.0, ms.cooldown_remaining / max(0.1, mv.cooldown_at(ms.rank))))
                    # Velo scuro che "cala" dall'alto man mano che la ricarica scende.
                    ov = pygame.Surface((bw, int(bh * frac)), pygame.SRCALPHA)
                    ov.fill((10, 12, 20, 180))
                    surface.blit(ov, (bx, y0))
            elif ms and not ms.unlocked:
                name = "R: lv.8"
            elif ms is None and sl == "R" and p.passive_id == "adattabilita":
                name = "R: evolvi"   # Eevee: l'ultimate arriva con la forma
            surface.blit(font.render(sl, True, (255, 230, 120)), (bx + 5, y0 + 3))
            ncol = (140, 140, 150) if on_cd else (230, 230, 230)
            surface.blit(font.render(name[:10], True, ncol), (bx + 5, y0 + bh - 20))
            if on_cd and cd_left > 0:                     # secondi mancanti (solo mosse a cooldown)
                txt = f"{cd_left:.0f}" if cd_left >= 1.0 else f"{cd_left:.1f}"
                num = font.render(txt, True, (255, 255, 255))
                surface.blit(num, (bx + bw // 2 - num.get_width() // 2,
                                   y0 + bh // 2 - num.get_height() // 2 - 2))
            if charge_count is not None:                  # badge col numero di cariche
                badge = (120, 220, 140) if charge_count > 0 else (160, 160, 170)
                cxp, cyp = bx + bw - 12, y0 + bh - 13
                pygame.draw.circle(surface, (16, 20, 26), (cxp, cyp), 9)
                pygame.draw.circle(surface, badge, (cxp, cyp), 9, 1)
                nn = font.render(str(charge_count), True, badge)
                surface.blit(nn, (cxp - nn.get_width() // 2, cyp - nn.get_height() // 2))
            if ms:
                pip_w = (bw - 12) // ms.max_rank
                for r in range(ms.max_rank):
                    col = (120, 210, 120) if r < ms.rank else (70, 70, 82)
                    pygame.draw.rect(surface, col,
                                     pygame.Rect(bx + 6 + r * pip_w, y0 + 21, pip_w - 2, 5))
                if avail > 0 and skills.can_rank_up(p, sl):   # pallino "+": clic per il grado
                    pygame.draw.circle(surface, (120, 220, 120), (bx + bw - 9, y0 + 10), 6)
                    surface.blit(font.render("+", True, (10, 30, 10)), (bx + bw - 13, y0 + 1))
            if evolvable:
                self._draw_slot_choice(surface, font, sl, ms, bx, y0, bw, near_base)

        if avail > 0:
            surface.blit(font.render(f"Punti mossa: {avail}  (clic sul + o Ctrl+tasto)",
                                     True, (120, 220, 120)), (x0, y0 - 22))
        # Cariche d'anima (passiva Corpofunesto): visibili in interfaccia.
        if p.passive_id == "corpofunesto":
            cz = p.soul_charges
            bx = x0 + total + 14
            pygame.draw.rect(surface, (40, 28, 56), pygame.Rect(bx, y0, 16, bh))
            fill = int(bh * min(1.0, cz / 100.0))
            pygame.draw.rect(surface, (170, 90, 230), pygame.Rect(bx, y0 + bh - fill, 16, fill))
            pygame.draw.rect(surface, (210, 170, 240), pygame.Rect(bx, y0, 16, bh), 1)
            surface.blit(font.render(f"Anime {cz}", True, (210, 170, 240)), (bx - 6, y0 - 18))
        # Cariche d'Inversione (passiva linea Snivy).
        if p.passive_id == "inversione":
            iz = p.inversion_stacks
            bx = x0 + total + 14
            pygame.draw.rect(surface, (24, 40, 28), pygame.Rect(bx, y0, 16, bh))
            fill = int(bh * min(1.0, iz / 100.0))
            pygame.draw.rect(surface, (110, 215, 130), pygame.Rect(bx, y0 + bh - fill, 16, fill))
            pygame.draw.rect(surface, (170, 230, 180), pygame.Rect(bx, y0, 16, bh), 1)
            surface.blit(font.render(f"Inv {iz}", True, (170, 230, 180)), (bx - 6, y0 - 18))
        # Passiva Muta (linea Nincada): ricarica e stato della forma Shedinja.
        if p.passive_id == "muta":
            bx = x0 + total + 14
            now = self.match.time if self.match is not None else 0.0
            in_form = getattr(p, "form", "") == "shedinja"
            cd_left = max(0.0, p.muta_cd_until - now)
            ready = cd_left <= 0.0 and not in_form
            frame = (230, 200, 120) if ready else (120, 110, 90)
            pygame.draw.rect(surface, (40, 36, 24), pygame.Rect(bx, y0, 16, bh))
            frac = 1.0 - min(1.0, cd_left / max(1.0, p.muta_cd_max))
            fill = int(bh * (1.0 if ready else frac))
            col = (235, 210, 110) if ready else (150, 140, 70)
            pygame.draw.rect(surface, col, pygame.Rect(bx, y0 + bh - fill, 16, fill))
            pygame.draw.rect(surface, frame, pygame.Rect(bx, y0, 16, bh), 1)
            surface.blit(font.render("Muta", True, frame), (bx - 6, y0 - 18))
            if in_form:
                left = max(0.0, p.form_until - now)
                tag = font.render(f"SHEDINJA {left:0.1f}s", True, (210, 180, 240))
                surface.blit(tag, (bx - tag.get_width() // 2 + 8, y0 + bh + 2))
            elif not ready:
                t = font.render(f"{cd_left:0.0f}s", True, frame)
                surface.blit(t, (bx - t.get_width() // 2 + 8, y0 + bh + 2))

        # Passiva Sabbiafiume (linea Roggenrola): tempesta attiva da Gigalith,
        # raddoppiata da Terrempesta (barra = tempo rimasto del raddoppio).
        if p.passive_id == "sabbiafiume":
            bx = x0 + total + 14
            now = self.match.time if self.match is not None else 0.0
            boost = max(0.0, p.sandstorm_boost_until - now)
            on = p.sand_radius > 0.0
            frame = (226, 196, 130) if on else (120, 108, 86)
            pygame.draw.rect(surface, (44, 36, 24), pygame.Rect(bx, y0, 16, bh))
            fill = int(bh * (min(1.0, boost / 4.0) if boost > 0 else (1.0 if on else 0.0)))
            col = (250, 200, 110) if boost > 0 else (200, 168, 104)
            pygame.draw.rect(surface, col, pygame.Rect(bx, y0 + bh - fill, 16, fill))
            pygame.draw.rect(surface, frame, pygame.Rect(bx, y0, 16, bh), 1)
            surface.blit(font.render("Sabbia", True, frame), (bx - 10, y0 - 18))
            if boost > 0:
                t = font.render(f"x2 {boost:0.1f}s", True, (250, 210, 130))
                surface.blit(t, (bx - t.get_width() // 2 + 8, y0 + bh + 2))
            elif not on:
                t = font.render("liv.8", True, frame)
                surface.blit(t, (bx - t.get_width() // 2 + 8, y0 + bh + 2))

        # Passiva I 108 Spiriti (Spiritomb): cariche raccolte (max 108), tacche dei
        # risvegli a 36/72 e Spirito Vagante pronto (riquadro acceso).
        if p.passive_id == "108spiriti":
            bx = x0 + total + 14
            now = self.match.time if self.match is not None else 0.0
            ready = now >= p.wander_ready_at
            frame = (214, 255, 128) if ready else (110, 150, 70)
            pygame.draw.rect(surface, (22, 34, 18), pygame.Rect(bx, y0, 16, bh))
            fill = int(bh * min(1.0, p.spirit_charges / 108.0))
            pygame.draw.rect(surface, (150, 230, 50), pygame.Rect(bx, y0 + bh - fill, 16, fill))
            for n in (36, 72):
                ty = y0 + bh - int(bh * n / 108.0)
                pygame.draw.line(surface, (240, 255, 200), (bx, ty), (bx + 15, ty))
            pygame.draw.rect(surface, frame, pygame.Rect(bx, y0, 16, bh), 2 if ready else 1)
            surface.blit(font.render(f"Spiriti {p.spirit_charges}", True, frame), (bx - 14, y0 - 18))
            if not ready:
                t = font.render(f"{p.wander_ready_at - now:0.0f}s", True, frame)
                surface.blit(t, (bx - t.get_width() // 2 + 8, y0 + bh + 2))

        # Linea Eevee: Adattabilità (prima dell'evoluzione) o passiva della forma.
        if p.passive_id == "adattabilita":
            self._draw_adaptability(surface, font, p, x0 + total + 14, y0, bh)
        elif p.passive_id in eevee_fx.PASSIVE_NAMES:
            self._draw_form_passive(surface, font, p, x0 + total + 14, y0, bh)

        if self.minimap is not None:
            self.minimap.draw(surface, self.world, self.camera, self.vision,
                              self.player.team, self.map_data.dens, self.player)

        if self.shop.open and self.match is not None:
            near = p.pos.dist(p.spawn_pos) <= config.SHOP_RANGE
            self.shop.draw(surface, font, self.match.item_catalog, p.gold, p.items,
                           self.pdef.role, near)

    def _draw_slot_choice(self, surface, font, sl, ms, bx, y0, bw, near_base) -> None:
        """Piccola scelta del potenziamento sopra lo slot (al posto del pop-up)."""
        if self.player.passive_id == "adattabilita" and sl in CHOICE_SLOTS:
            self._draw_eevee_choice(surface, font, sl, ms, bx, y0, bw, near_base)
            return
        opts = ms.upgrades[:2]
        ph = 22 + 18 * len(opts)
        panel = pygame.Rect(bx - 44, y0 - ph - 6, bw + 88, ph)
        bg = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        bg.fill((20, 20, 28, 235))
        surface.blit(bg, panel)
        pygame.draw.rect(surface, (235, 210, 90), panel, 1)
        title = f"Evolvi {sl} (clic):" if near_base else f"Evolvi {sl} - vai in BASE"
        surface.blit(font.render(title, True, (235, 210, 90)), (panel.x + 6, panel.y + 3))
        for i, mv in enumerate(opts):
            oy = panel.y + 20 + i * 18
            r = pygame.Rect(panel.x + 5, oy, panel.w - 10, 17)
            if near_base:
                pygame.draw.rect(surface, (44, 48, 60), r)
                self._choice_rects.append((r, sl, i))
            surface.blit(font.render(f"{i + 1}. {mv.name}", True, (230, 230, 235)), (r.x + 4, oy + 1))

    def _draw_eevee_choice(self, surface, font, sl, ms, bx, y0, bw, near_base) -> None:
        """Scelta di Eevee: ogni opzione è un asse di ruolo; accanto, le forme a cui
        porta. In cima l'anteprima "Con queste scelte diventerai: [forma]",
        aggiornata a ogni scelta (e all'opzione sotto il mouse)."""
        p = self.player
        opts = ms.upgrades[:2]
        axis = eevee_fx.CHOICE_AXES.get(sl, ("", ""))
        lh = 18
        pw = 330
        ph = 60 + lh * len(opts)
        # sopra la riga "Punti mossa" (y0 - 22), così non si sovrappongono
        panel = pygame.Rect(bx + bw // 2 - pw // 2, y0 - ph - 26, pw, ph)
        W = surface.get_width()
        panel.x = max(4, min(panel.x, W - pw - 4))
        bg = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        bg.fill((20, 20, 28, 235))
        surface.blit(bg, panel)
        pygame.draw.rect(surface, (235, 210, 90), panel, 1)
        title = f"Evolvi {sl} (clic):" if near_base else f"Evolvi {sl} - vai in BASE"
        surface.blit(font.render(title, True, (235, 210, 90)), (panel.x + 6, panel.y + 3))
        mouse = pygame.mouse.get_pos()
        hover = None
        rows = []
        for i, mv in enumerate(opts):
            oy = panel.y + 58 + i * lh
            r = pygame.Rect(panel.x + 5, oy, panel.w - 10, lh - 1)
            rows.append((i, mv, r, oy))
            if r.collidepoint(mouse):
                hover = i
        # Anteprima: forme raggiungibili con le scelte fatte (+ l'opzione sotto il mouse).
        cands = eevee_candidates(p, {sl: hover} if hover is not None else None)
        x = panel.x + 6
        y = panel.y + 21
        lab = font.render("Con queste scelte diventerai:", True, (210, 205, 190))
        surface.blit(lab, (x, y))
        x = panel.x + 10
        y += 18
        if len(cands) == len(eevee_forms(p)):
            surface.blit(font.render("?", True, (235, 225, 200)), (x, y))
        else:
            for k, st in enumerate(cands):
                col = eevee_fx.readable(st["form_color"])
                t = font.render(st["name"] + ("" if k == len(cands) - 1 else " /"), True, col)
                if x + t.get_width() > panel.right - 4:
                    break
                surface.blit(t, (x, y))
                x += t.get_width() + 4
        for i, mv, r, oy in rows:
            if near_base:
                pygame.draw.rect(surface, (60, 64, 80) if i == hover else (44, 48, 60), r)
                self._choice_rects.append((r, sl, i))
            txt = f"{i + 1}. {mv.name} ({axis[i]})"
            surface.blit(font.render(txt, True, (230, 230, 235)), (r.x + 4, oy + 1))
            # pallini colorati delle forme a cui porta questa opzione
            dots = eevee_candidates(p, {sl: i})
            dx = r.right - 8
            for st in reversed(dots):
                pygame.draw.circle(surface, eevee_fx.readable(st["form_color"]), (dx, oy + lh // 2), 5)
                pygame.draw.circle(surface, (15, 15, 20), (dx, oy + lh // 2), 5, 1)
                dx -= 12
