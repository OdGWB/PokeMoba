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
                          RankMoveCommand, RecallCommand, SellItemCommand, UseItemCommand)
from sim.simulation import Simulation

from ..camera import Camera
from ..fx import FXSystem
from ..input_controller import InputController
from ..minimap import Minimap
from .. import anim_tuning, arch_fx, eevee_fx, hatt_fx, mag_fx, spirit_fx, swine_fx
from ..particles import ParticleSystem
from ..renderer import Renderer
from ..shop_ui import ShopUI
from ..sprites.animator import FallbackAnimator, SpriteAnimator
from ..sprites.spritesheet import load_pokemon_animations, make_wild_animator
from .. import hud
from ..fx import type_color
from ..hud_passives import PassiveCtx, draw_passive
from ..world_fx import draw_projectiles, draw_world_effects, update_world_fx

ROOT = Path(__file__).resolve().parents[2]
LANE_SLOTS = ["top", "mid", "bot"]
# Tasti 1-6: oggetto attivabile dello slot corrispondente (1/2 scelgono il
# potenziamento quando c'e' una scelta in sospeso in base).
ITEM_KEYS = {k: i for i, k in enumerate((pygame.K_1, pygame.K_2, pygame.K_3,
                                         pygame.K_4, pygame.K_5, pygame.K_6))}
# Piccoli scostamenti per non far nascere i tre alleati esattamente sovrapposti.
SLOT_OFFSET = {"top": Vec2(-1.2, 0.0), "mid": Vec2(0.0, 0.0), "bot": Vec2(0.0, 1.2)}
DEATH_FADE = 1.5   # s: posa Hurt tenuta mentre l'unità si dissolve alla morte


class MatchScene:
    def __init__(self, map_path: str, pokemon_path: str, start_level: int = 1,
                 start_items=None, bot_paths=None, start_armature=None):
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

        # Charcadet (test): barra di Armature in vantaggio prima del livello, cosi'
        # al liv.8 evolve nella forma scelta (fausta -> Armarouge).
        if start_armature and self.player is not None:
            setattr(self.player, start_armature, 1.0)

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
        # Regolazioni visive dell'editor delle animazioni (partenza proiettili).
        self._fx_tuner = anim_tuning.FxTuner(config.TILE_SIZE)
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
                                     attack_cooldown=pdef.attack_cooldown,
                                     attack_fx=pdef.attack_fx,
                                     rec_items=pdef.recommended_items)
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
                                               attack_cooldown=self.pdef.attack_cooldown,
                                               attack_fx=self.pdef.attack_fx,
                                               rec_items=self.pdef.recommended_items)
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
        wild = make_wild_animator(unit, self._load_anim)
        if wild is not None:
            return wild
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
            elif (ev.type == pygame.KEYDOWN and ev.key in ITEM_KEYS
                  and self.match is not None):
                # Tasti 1-6: attiva l'oggetto dello slot (Mentalerba, Palla Fumo).
                self._menu_seq += 1
                self.sim.queue_command(UseItemCommand(seq=60_000 + self._menu_seq,
                                                      entity_id=self.player.id,
                                                      slot=ITEM_KEYS[ev.key]))
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
                # Addormentato (sonno, Riposo): posa Sleep finché dura.
                anim.pose = "Sleep" if getattr(u, "sleep_until", -1.0) > self.match.time else None
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
            self.fx.spawn_events(self._fx_tuner.process(
                self.match.fx_events, self.animators, self._unit_pos))
            self.match.fx_events.clear()
        # Proiettili che aspettano il loro fotogramma (editor delle animazioni).
        late = self._fx_tuner.due(dt)
        if late:
            self.fx.spawn_events(late)
        # Polvere delle valanghe e nube della Palla Fumo (anche online, world_fx).
        if self.match is not None:
            update_world_fx(self.fx, self.match, self.match.time)
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
            if eid is not None and "anim" in e:
                anim = self.animators.get(eid)
                if isinstance(anim, SpriteAnimator):
                    anim_tuning.trigger_anim(anim, e)

    def _unit_pos(self, uid):
        u = self.world.get(uid)
        return (u.pos.x, u.pos.y) if u is not None else None

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
        # Effetti che durano (sabbia, valanghe, Spiritomb, Eevee), dallo stato del
        # Match: stesso codice della partita online (game/world_fx.py).
        if self.match is not None:
            reach, pick = self._spirit_aim(surface)
            draw_world_effects(surface, self.camera, self.world, self.match, self.player.team,
                               self.vision, self.match.time, self.player.id, reach, pick)
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
            draw_projectiles(surface, self.camera, self.match, self.match.time)
        # Indicatore di mira (solo se la mossa è pronta: niente mirino in cooldown).
        if self.input.aiming_slot and self.player.alive:
            ms = self.player.moveset.get(self.input.aiming_slot)
            if ms and ms.chosen and ms.ready:
                mx, my = pygame.mouse.get_pos()
                wx, wy = self.camera.screen_window_to_world(mx, my)
                hold = (pygame.time.get_ticks() - self.input.aim_start) / 1000.0
                self.renderer.draw_aim(surface, self.camera, self.player.pos,
                                       (wx / config.TILE_SIZE, wy / config.TILE_SIZE),
                                       ms.chosen, hold=hold,
                                       rain=getattr(self.player, "arch_rain", False))
        # Particelle degli effetti.
        self.fx.draw(surface, self.camera)
        arch_fx.draw_shake(surface, self.fx)   # Elettroraggio: lo schermo trema

    def _spirit_aim(self, surface):
        """Mira di Richiamo degli Spiriti (Spiritomb): raggio e spirito che verrebbe
        scelto, col filo verso di lui. (None, None) se non si sta mirando."""
        reach = pick = None
        if self.input.aiming_slot and self.player.alive:
            ms = self.player.moveset.get(self.input.aiming_slot)
            if ms and ms.chosen and ms.ready and ms.chosen.shape == "spiritcall":
                reach = (self.player.pos, ms.chosen.range)
                mx, my = pygame.mouse.get_pos()
                wx, wy = self.camera.screen_window_to_world(mx, my)
                pick = self.match._spirit_call_target(
                    self.player, ms.chosen, Vec2(wx / config.TILE_SIZE, wy / config.TILE_SIZE))
                if pick is not None:   # filo verso lo spirito scelto
                    ts = config.TILE_SIZE
                    a = self.camera.world_to_screen(self.player.pos.x * ts, self.player.pos.y * ts)
                    b = self.camera.world_to_screen(pick.pos.x * ts, pick.pos.y * ts)
                    pygame.draw.line(surface, spirit_fx.LIME_HI, a, b, 1)
        return reach, pick

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

    def hud_lines(self) -> list[str]:
        # L'HUD vero e' in draw_fullres (game/hud.py); qui niente righe di testo.
        return []

    # --- UI a piena risoluzione (game/hud.py) --------------------------------
    def _player_view(self) -> hud.PlayerView:
        p = self.player
        sd = self._dex_sprite.get(p.dex) or self.pdef.sprite_dir
        atkm = "+" if p.atk_mult > 1.0 else ""
        difm = "+" if p.def_buff_active else ("-" if p.def_debuff_active else "")
        # L'Att. Speciale vero (AP) viene dagli oggetti; il moltiplicatore abilita'
        # (0,6 + 0,004 x SpA_eff) si mostra a parte cosi' lo speciale non sembra zero.
        stats = [("Attacco", int(p.eff_attack()), atkm),
                 ("Difesa", int(p.eff_defense()), difm),
                 ("Dif. Sp.", int(p.eff_sp_defense()), ""),
                 ("Att. Sp.", int(p.eff_sp_attack()), ""),
                 ("Abilità", f"x{p.ability_mult:.2f}", "")]
        return hud.PlayerView(
            name=p.name, level=p.level, xp=p.xp, hp=p.hp, max_hp=p.max_hp,
            portrait=self._portrait(sd, hud.PORT - 14) if sd else None,
            gold=int(p.gold), items=list(p.items), stats=stats, alive=p.alive,
            respawn_left=max(0.0, p.respawn_timer),
            points=skills.available_points(p), team=p.team)

    def _slot_views(self) -> list:
        p = self.player
        avail = skills.available_points(p)
        out = []
        for sl in ("Q", "W", "E", "R"):
            ms = p.moveset.get(sl)
            s = hud.SlotView(key=sl)
            if ms is not None:
                s.rank, s.max_rank = ms.rank, ms.max_rank
                s.can_rank = avail > 0 and skills.can_rank_up(p, sl)
                s.evolvable = sl in p.pending_choices and bool(ms.upgrades)
            if ms and ms.chosen and ms.unlocked:
                mv = ms.chosen
                s.name, s.mtype = mv.name, mv.type
                if mv.charges > 0 and ms.rank > 0:
                    cur = ms.charges_cur if ms.charges_cur >= 0 else float(mv.charges)
                    whole = max(0, min(mv.charges, int(cur + 1e-6)))
                    prog = 1.0 if whole >= mv.charges else (cur - int(cur))
                    s.charges = (whole, mv.charges, prog)
                elif ms.rank > 0 and ms.cooldown_remaining > 0:
                    s.cd_left = ms.cooldown_remaining
                    s.cd_frac = ms.cooldown_remaining / max(0.1, mv.cooldown_at(ms.rank))
            elif ms and (not ms.unlocked or ms.chosen is None):
                s.can_rank = False
                s.locked = "Liv. 8" if p.level < 8 else "Scegli"
            elif ms is None:
                # Eevee/rami: l'ultimate arriva con la forma (o col liv. 8)
                s.locked = "Liv. 8" if p.level < 8 else "Evolvi"
                s.max_rank = 0
            out.append(s)
        return out

    def _match_view(self) -> hud.MatchView:
        from engine.jungle import WEATHER_NAMES
        cores = {c.team: c for c in self.world.cores()}
        teams = tuple(tuple(0.0 if q.alive else max(0.1, q.respawn_timer)
                            for q in self.world.pokemons() if q.team == t) for t in (0, 1))
        return hud.MatchView(
            time=self.match.time,
            cores=tuple((cores[t].hp, cores[t].max_hp) if t in cores else (0.0, 1.0)
                        for t in (0, 1)),
            teams=teams, next_wave=max(0.0, self.match._wave_timer),
            weather=WEATHER_NAMES.get(self.match.jungle.weather, ""),
            winner=self.match.winner, player_team=self.player.team)

    def draw_fullres(self, surface, font) -> None:
        if self.match is None:
            return
        p = self.player
        near_base = p.pos.dist(p.spawn_pos) <= config.SHOP_RANGE
        right = None
        if self.minimap is not None:
            self.minimap.draw(surface, self.world, self.camera, self.vision,
                              self.player.team, self.map_data.dens, self.player)
            right = self.minimap.rect.x
        hud.draw_top(surface, self._match_view(), getattr(self, "fps", None))
        hud.text(surface, "Dx muovi  Sx attacca  Q/W/E/R mosse  Ctrl+tasto grado  "
                 "Y camera  ESC esci", (8, 6), 12, hud.DIM)
        icon = lambda iid, size: self.shop._icon(self.match.item_catalog, iid, size, font)
        lay = hud.draw_bar(surface, self._player_view(), self._slot_views(), type_color,
                           icon, right_limit=right)
        self._skill_rects = dict(lay.slot_rects)
        self._choice_rects = []
        # Passiva (anime, Inversione, Muta, Sabbia, Spiriti, Eevee): game/hud_passives.py,
        # stesso disegno della partita online.
        px, py, ph = lay.passive_at
        draw_passive(surface, hud.font(13), p, px, py, ph, PassiveCtx(
            now=self.match.time, portrait=self._portrait, in_rain=self.match._in_rain(p),
            weather=self.match.jungle.weather,
            agitated=hatt_fx.count_agitated(
                self.world, p, self.match.time,
                lambda e: self.match.vision.is_enemy_visible(p.team, e.id)),
            charged=mag_fx.count_charged(
                self.world, p, self.match.time,
                lambda e: self.match.vision.is_enemy_visible(p.team, e.id)),
            frost_ready=swine_fx.count_frozen_ready(
                self.world, p, self.match.time,
                lambda e: self.match.vision.is_enemy_visible(p.team, e.id))))
        # Popup delle evoluzioni: in fila sopra la barra, mai sovrapposti.
        evo = [sl for sl in ("Q", "W", "E", "R")
               if sl in p.pending_choices and p.moveset.get(sl) and p.moveset[sl].upgrades]
        if evo:
            sizes = [self._choice_size(sl) for sl in evo]
            anchors = [lay.slot_rects[sl].centerx for sl in evo]
            bottom = lay.rect.y - (30 if skills.available_points(p) > 0 else 8)
            rects = hud.layout_popups(sizes, anchors, bottom, right or surface.get_width())
            for sl, r in zip(evo, rects):
                self._draw_slot_choice(surface, sl, p.moveset[sl], r, near_base,
                                       first=(sl == p.pending_choices[0]))
        # Avvisi al centro
        if self.match.winner is not None:
            squad = "BLU" if self.match.winner == 0 else "ROSSA"
            win = self.match.winner == p.team
            hud.draw_banner(surface, "VITTORIA!" if win else "SCONFITTA",
                            f"Ha vinto la squadra {squad}",
                            (255, 230, 120) if win else (240, 120, 110),
                            y=surface.get_height() // 3)
        elif not p.alive:
            hud.draw_banner(surface, "ABBATTUTO", f"Rinasci tra {p.respawn_timer:.0f}s",
                            (240, 120, 110))
        elif p.recalling:
            left = max(0.0, p.recall_until - self.match.time)
            hud.draw_banner(surface, f"RICHIAMO  {left:.1f}s",
                            "muoviti o subisci danno per annullare", (150, 200, 255),
                            frac=1.0 - left / config.RECALL_TIME)

        if self.shop.open:
            self.shop.draw(surface, font, self.match.item_catalog, p.gold, p.items,
                           p.rec_items or self.pdef.role, near_base, p.item_cd, self.match.time)

    def _choice_size(self, sl) -> tuple:
        if self.player.passive_id == "adattabilita" and sl in CHOICE_SLOTS:
            return 340, 64 + 22 * 2
        return hud.choice_size(sl, self.player.moveset[sl].upgrades[:2])

    def _draw_slot_choice(self, surface, sl, ms, panel, near_base, first=False) -> None:
        """Scelta del potenziamento di una mossa, nel rettangolo dato da layout_popups."""
        if self.player.passive_id == "adattabilita" and sl in CHOICE_SLOTS:
            self._draw_eevee_choice(surface, sl, ms, panel, near_base)
            return
        if near_base:
            title = f"Evolvi {sl}" + (" - clic o 1/2" if first else " - clic")
        else:
            title = f"Evolvi {sl} - torna in BASE"
        rows = hud.draw_choice(surface, panel, title, ms.upgrades[:2], type_color, near_base,
                               hud.GOLD if near_base else (236, 170, 110))
        self._choice_rects += [(r, sl, i) for i, r in enumerate(rows)]

    def _draw_eevee_choice(self, surface, sl, ms, panel, near_base) -> None:
        """Scelta di Eevee: ogni opzione è un asse di ruolo; accanto, le forme a cui
        porta. In cima l'anteprima "Con queste scelte diventerai: [forma]",
        aggiornata a ogni scelta (e all'opzione sotto il mouse)."""
        p = self.player
        opts = ms.upgrades[:2]
        axis = eevee_fx.CHOICE_AXES.get(sl, ("", ""))
        lh = 22
        hud.panel(surface, panel, trim=hud.TRIM_HI)
        title = f"Evolvi {sl} - clic" if near_base else f"Evolvi {sl} - torna in BASE"
        hud.text(surface, title, (panel.x + 10, panel.y + 6), 14,
                 hud.GOLD if near_base else (236, 170, 110), bold=True)
        mouse = pygame.mouse.get_pos()
        hover = None
        rows = []
        for i, mv in enumerate(opts):
            oy = panel.y + 62 + i * lh
            r = pygame.Rect(panel.x + 6, oy, panel.w - 12, lh - 2)
            rows.append((i, mv, r, oy))
            if r.collidepoint(mouse):
                hover = i
        # Anteprima: forme raggiungibili con le scelte fatte (+ l'opzione sotto il mouse).
        cands = eevee_candidates(p, {sl: hover} if hover is not None else None)
        hud.text(surface, "Con queste scelte diventerai:", (panel.x + 10, panel.y + 25), 13,
                 (210, 205, 190))
        x, y = panel.x + 12, panel.y + 42
        if len(cands) == len(eevee_forms(p)):
            hud.text(surface, "?", (x, y), 14, (235, 225, 200), bold=True)
        else:
            for k, st in enumerate(cands):
                s = st["name"] + ("" if k == len(cands) - 1 else " /")
                w = hud.font(14, True).size(s)[0]
                if x + w > panel.right - 4:
                    break
                hud.text(surface, s, (x, y), 14, eevee_fx.readable(st["form_color"]), bold=True)
                x += w + 5
        for i, mv, r, oy in rows:
            if near_base:
                pygame.draw.rect(surface, (64, 70, 90) if i == hover else (38, 42, 54), r,
                                 border_radius=4)
                self._choice_rects.append((r, sl, i))
            hud.text(surface, f"{i + 1}. {mv.name} ({axis[i]})", (r.x + 6, oy + 2), 14,
                     hud.TEXT, bold=True)
            # pallini colorati delle forme a cui porta questa opzione
            dots = eevee_candidates(p, {sl: i})
            dx = r.right - 10
            for st in reversed(dots):
                cy = oy + lh // 2 - 1
                pygame.draw.circle(surface, eevee_fx.readable(st["form_color"]), (dx, cy), 5)
                pygame.draw.circle(surface, (15, 15, 20), (dx, cy), 5, 1)
                dx -= 12
