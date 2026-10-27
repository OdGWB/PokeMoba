"""Scena di partita.

- Se la mappa ha le strutture MOBA (lane, torri, nucleo), avvia una partita
  3v3 contro/insieme a bot: il giocatore controlla un Pokémon della squadra 0.
- Altrimenti ripiega sulla demo della Fase 1 (un solo Pokémon su mappa libera).

La logica di gioco sta in engine/sim; qui c'è solo l'orchestrazione lato client.
"""
from __future__ import annotations

import pygame

import config
from engine import skills
from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.vec import Vec2
from engine.world import World
from sim.commands import (BuyItemCommand, ChooseUpgradeCommand, MoveCommand,
                          RankMoveCommand, RecallCommand, SellItemCommand)
from sim.simulation import Simulation

from ..camera import Camera
from ..fx import FXSystem, type_color
from ..input_controller import InputController
from ..minimap import Minimap
from ..particles import ParticleSystem
from ..renderer import Renderer
from ..shop_ui import ShopUI
from ..sprites.animator import FallbackAnimator, SpriteAnimator
from ..sprites.spritesheet import load_pokemon_animations

LANE_SLOTS = ["top", "mid", "bot"]
# Piccoli scostamenti per non far nascere i tre alleati esattamente sovrapposti.
SLOT_OFFSET = {"top": Vec2(-1.2, 0.0), "mid": Vec2(0.0, 0.0), "bot": Vec2(0.0, 1.2)}
DEATH_FADE = 1.5   # s: posa Hurt tenuta mentre l'unità si dissolve alla morte


class MatchScene:
    def __init__(self, map_path: str, pokemon_path: str):
        map_data = load_map(map_path)
        self.map_data = map_data
        self.world = World(map_data.grid)
        self.pdef = load_pokemon_def(pokemon_path)

        self.animators: dict[int, object] = {}
        self._dying: dict = {}      # unità morte: anim Hurt + dissolvenza breve
        self._sprite_cache: dict = {}
        self._player_stage = 0
        self.anim_set = self._load_anim(self.pdef.sprite_dir)
        self._using_sprites = self.anim_set is not None

        self.camera_locked = True
        self.match: Match | None = None

        if map_data.is_moba_map:
            self._setup_moba()
        else:
            self._setup_demo()

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
    def _spawn_pokemon(self, team, lane, is_bot):
        base = Vec2(*self.map_data.spawns[f"team{team}"]) + Vec2(0.5, 0.5)
        pos = base + SLOT_OFFSET[lane]
        color = config.TEAM_COLORS[team]
        p = self.world.spawn_pokemon(pos=pos, team=team, dex=self.pdef.dex,
                                     name=self.pdef.name, color=color,
                                     speed=self.pdef.base_speed, is_bot=is_bot,
                                     assigned_lane=lane, types=self.pdef.types,
                                     base_stats=self.pdef.base_stats,
                                     growth=self.pdef.growth, moves=self.pdef.moves,
                                     evolutions=self.pdef.evolutions, role=self.pdef.role,
                                     passive=self.pdef.passive,
                                     attack_range=self.pdef.attack_range,
                                     attack_cooldown=self.pdef.attack_cooldown)
        p.radius = self.pdef.radius
        return p

    def _setup_moba(self):
        self.match = Match(self.world, self.map_data)
        # team_size Pokémon per squadra (3v3 o 5v5), lane a rotazione. Il giocatore
        # prende il primo slot in mid; il resto della squadra 0 e tutta la 1 sono bot.
        self.player = None
        ts = self.map_data.team_size
        for slot in range(ts):
            lane = LANE_SLOTS[slot % 3]
            is_player = self.player is None and lane == "mid"
            p0 = self._spawn_pokemon(0, lane, is_bot=not is_player)
            if is_player:
                self.player = p0
            self._spawn_pokemon(1, lane, is_bot=True)
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
        self.sim = Simulation(self.world, config.TICK_DT)

    def _load_anim(self, sprite_dir):
        if not sprite_dir:
            return None
        if sprite_dir not in self._sprite_cache:
            self._sprite_cache[sprite_dir] = load_pokemon_animations(sprite_dir)
        return self._sprite_cache[sprite_dir]

    def _stage_sprite_dir(self, stage):
        evs = self.pdef.evolutions
        if evs and 0 <= stage < len(evs) and evs[stage].get("sprite_dir"):
            return evs[stage]["sprite_dir"]
        return self.pdef.sprite_dir

    def _make_animator(self, unit):
        from engine.entities import Minion, Pokemon
        # Il giocatore usa gli sprite reali (se presenti).
        if isinstance(unit, Pokemon) and not unit.is_bot:
            aset = self._load_anim(self._stage_sprite_dir(unit.stage))
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
        # Cambio sprite quando il giocatore si evolve.
        if self.player.stage != self._player_stage:
            self._player_stage = self.player.stage
            aset = self._load_anim(self._stage_sprite_dir(self.player.stage))
            if aset is not None:
                self.animators[self.player.id] = SpriteAnimator(aset)

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
            lines.append(
                f"{p.name} Lv.{p.level}  HP {int(p.hp)}/{int(p.max_hp)}  "
                f"Atk {int(p.eff_attack())}  Dif {int(p.eff_defense())}  "
                f"AttSp {int(p.eff_sp_attack())}  Oro {int(p.gold)}  (P: negozio)")
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

        if self.minimap is not None:
            self.minimap.draw(surface, self.world, self.camera, self.vision,
                              self.player.team, self.map_data.dens, self.player)

        if self.shop.open and self.match is not None:
            near = p.pos.dist(p.spawn_pos) <= config.SHOP_RANGE
            self.shop.draw(surface, font, self.match.item_catalog, p.gold, p.items,
                           self.pdef.role, near)

    def _draw_slot_choice(self, surface, font, sl, ms, bx, y0, bw, near_base) -> None:
        """Piccola scelta del potenziamento sopra lo slot (al posto del pop-up)."""
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
