"""Partita ONLINE (WebRTC): estende NetMatchScene con predizione del proprio
personaggio, interpolazione degli altri, effetti visivi dall'host, HUD di
debug della rete (F3) e fine partita pulita se l'host cade.

Gli EFFETTI che durano (stati sulle unità, valanghe, spiriti, Tuono/Bora,
nube della Palla Fumo...), le morti che sfumano, gli anelli di respawn, le
passive e le ricariche degli oggetti arrivano con lo STATO VISIVO
(net/visual.py) e si disegnano con lo stesso codice della partita offline
(game/world_fx.py, game/hud_passives.py).

Lo stesso codice serve all'host (sessione collegata in memoria alla propria
HostSession) e agli amici (sessione su WebRTC). L'host ha in più il pannello
degli slot (F2) per far rientrare chi è caduto.
"""
from __future__ import annotations

import time

import pygame

import config
from net import client as C
from net.prediction import Predictor

from .. import anim_tuning, arch_fx, hatt_fx, hud, mag_fx, moth_fx, swine_fx
from ..fx import FXSystem
from ..hud_passives import PassiveCtx, draw_passive
from ..online_world import MovementModel, OnlineWorld
from ..sprites.animator import SpriteAnimator
from ..world_fx import draw_projectiles, draw_world_effects, update_world_fx
from .match_scene import DEATH_FADE
from .net_match_scene import NetMatchScene

DIM = (165, 170, 180)
GONE_WAIT = 0.4      # s: un Pokémon sparito è morto se lo stato visivo lo dà a terra


class OnlineMatchScene(NetMatchScene):
    def __init__(self, app, session, host=None):
        # NetMatchScene carica mappa, minimappa, negozio; la mappa grafica del
        # renderer si costruisce invece al PRIMO draw (10-20 s). R_LOADED parte
        # solo dopo quel primo draw: l'host non avvia la simulazione finché
        # tutti non sono davvero pronti (altrimenti chi carica si perde l'inizio).
        super().__init__(app, session, session.start_info)
        self.session = session
        self.host = host
        self.predictor = Predictor(MovementModel(self.map_data.grid), config.TICK_DT)
        self.world = OnlineWorld(self.map_data.grid, self.your_id, self.predictor, session)
        session.on_frame = self.world.push_frame
        session.on_command = self._on_command
        self.fx = FXSystem()
        self.fx.pos_of = self._unit_pos   # proiettili dell attacco base che seguono il bersaglio
        self.fx.me = self.your_id         # "+oro" dell'ultimo colpo: solo il proprio
        # Regolazioni visive dell'editor delle animazioni (partenza proiettili).
        self._fx_tuner = anim_tuning.FxTuner(config.TILE_SIZE)
        self.show_debug = True
        self.slot_panel = None
        self._acc = 0.0
        self._names = {p["entity_id"]: p["name"] for p in session.start_info["players"]}
        self._loaded_sent = False
        self._seen_poke: dict = {}     # eid -> (pos, facing) all'ultimo frame
        self._gone: dict = {}          # eid -> (pos, facing, animatore, istante)
        self._dying: dict = {}         # come MatchScene: posa Hurt che si dissolve
        self._portraits: dict = {}

    def _on_command(self, seq, kind, f):
        target = (f["x"], f["y"]) if "x" in f else None
        self.predictor.command(seq, kind, target)

    # --- input --------------------------------------------------------------------------
    def handle_events(self, events):
        rest = []
        for ev in events:
            if self.slot_panel is not None and self.slot_panel.handle_event(ev):
                continue
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                if self.slot_panel is not None:
                    self.slot_panel = None
                else:
                    self._leave()
                continue
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F3:
                self.show_debug = not self.show_debug
                continue
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F2 and self.host is not None:
                from .online_lobby_scene import SlotPanel
                self.slot_panel = None if self.slot_panel else SlotPanel(self.host, in_match=True)
                continue
            if self.session.phase in (C.ENDED, C.LOST):
                if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._leave()
                continue
            rest.append(ev)
        super().handle_events(rest)

    def _leave(self):
        """Torna al menu chiudendo tutto in modo pulito (host: avvisa gli amici)."""
        if self.host is not None:
            self.host.shutdown()
        else:
            self.session.close()
        from .menu_scene import MenuScene
        self.next_scene = MenuScene(self.app)

    def _unit_pos(self, uid):
        u = self.world.get(int(uid))
        return (u.pos.x, u.pos.y) if u is not None else None

    # --- aggiornamento --------------------------------------------------------------------
    def update(self, dt):
        # Predizione a tick fissi, come l'host (1/30 s), prima di ricevere gli
        # snapshot del frame: la riconciliazione confronta tick con tick.
        self._acc = min(self._acc + dt, 0.25)
        while self._acc >= config.TICK_DT:
            self.predictor.step()
            self._acc -= config.TICK_DT
        super().update(dt)          # poll della sessione + interpolazione + animatori
        if self.session.fx_queue:
            events, self.session.fx_queue = self.session.fx_queue, []
            try:   # minion e mostri morti: morte rapida (death_fx)
                self.fx.deaths.from_events(events, self.animators)
            except Exception:
                pass
            try:
                anim_tuning.apply_unit_events(self.animators, events)
            except Exception:       # evento cosmetico incompleto: si salta
                pass
            try:
                self.fx.spawn_events(self._fx_tuner.process(
                    events, self.animators, self._unit_pos))
            except Exception:       # evento cosmetico incompleto: si salta
                pass
        late = self._fx_tuner.due(dt)   # proiettili in attesa del loro fotogramma
        if late:
            try:
                self.fx.spawn_events(late)
            except Exception:
                pass
        update_world_fx(self.fx, self.world.fxs, self.world.match_time)
        self._update_deaths(dt)
        self.fx.update(dt)
        if self.slot_panel is not None:
            self.slot_panel.update()

    def _update_deaths(self, dt):
        """Morte: posa Hurt + dissolvenza come offline. Lo snapshot toglie il
        Pokémon morto; se lo stato visivo lo dà a terra (dead) parte la dissolvenza,
        altrimenti era solo uscito dalla visione."""
        from engine.entities import Pokemon
        from engine.vec import Vec2
        now = time.monotonic()
        alive = {}
        for u in self.world.units():
            if isinstance(u, Pokemon) and u.alive:
                alive[u.id] = (Vec2(u.pos.x, u.pos.y), u.facing)
        for eid, (pos, facing) in self._seen_poke.items():
            if eid not in alive and eid not in self._gone:
                self._gone[eid] = (pos, facing, self.animators.get(eid), now)
        self._seen_poke = alive
        for eid, (pos, facing, anim, t0) in list(self._gone.items()):
            if eid in alive:
                del self._gone[eid]
            elif eid in self.world.dead:
                del self._gone[eid]
                if isinstance(anim, SpriteAnimator):
                    death = SpriteAnimator(anim.anim_set, scale=anim.scale)
                    death.facing = facing
                    death.freeze("Hurt")
                    self._dying[eid] = {"anim": death, "pos": pos, "t": 0.0}
            elif now - t0 > GONE_WAIT:
                del self._gone[eid]
        for eid, d in list(self._dying.items()):
            d["t"] += dt
            if eid in alive or d["t"] >= DEATH_FADE:
                del self._dying[eid]

    def _draw_world_extras(self, surface):
        me = self.world.get(self.your_id)
        self.renderer.flower_source = lambda: self.world.fxs.flowers
        draw_world_effects(surface, self.camera, self.world, self.world.fxs, self.team,
                           self.vision, self.world.match_time,
                           me.id if me is not None else self.your_id)

    def _draw_after_particles(self, surface):
        ts = config.TILE_SIZE
        for d in self._dying.values():
            gx, gy = self.camera.world_to_screen(d["pos"].x * ts, d["pos"].y * ts)
            alpha = int(255 * max(0.0, 1.0 - d["t"] / DEATH_FADE))
            d["anim"].draw(surface, gx, gy, alpha=alpha)
        draw_projectiles(surface, self.camera, self.world.fxs, self.world.match_time)

    def draw(self, surface):
        super().draw(surface)
        self.fx.draw(surface, self.camera)
        arch_fx.draw_shake(surface, self.fx)   # Elettroraggio: lo schermo trema
        if not self._loaded_sent:
            self._loaded_sent = True
            self.session.send_loaded()

    # --- HUD --------------------------------------------------------------------------------
    def hud_lines(self):
        lines = super().hud_lines()
        s = self.session
        now = time.monotonic()
        for t, txt in list(s.events):
            if now - t < 6.0:
                lines.append(f"* {txt}")
        if self.show_debug:
            ping = f"{s.clock.rtt * 1000:.0f} ms" if s.clock.rtt is not None else "?"
            tick = s.latest.tick if s.latest else 0
            pr = self.predictor
            lines.append(f"RETE  ping {ping}   perdita {s.loss.loss * 100:.1f}%   tick {tick}   "
                         f"snapshot {s.snap_bytes.last} B (media {s.snap_bytes.value:.0f})   "
                         f"input {s.input_bytes.last} B   keyframe {s.keyframes}")
            lines.append(f"      predizione: replay {pr.replays}  scatti {pr.snaps}  "
                         f"ultimo errore {pr.last_error:.2f} tile  comandi in volo {len(s.unacked)}")
        return lines

    def draw_fullres(self, surface, font):
        super().draw_fullres(surface, font)
        self._draw_passive(surface, font)
        self._draw_disconnected(surface, font)
        if self.slot_panel is not None:
            self.slot_panel.draw(surface, font)
        if self.session.phase in (C.ENDED, C.LOST):
            self._draw_end(surface)

    @property
    def HELP(self):
        return ("ONLINE  Dx muovi  Sx attacca  Q/W/E/R mosse  Ctrl+tasto grado  F3 rete"
                + ("  F2 slot" if self.host else "") + "  ESC esci")

    def _portrait(self, sprite_dir, side):
        """Ritratto di una forma (primo fotogramma Idle), come MatchScene._portrait."""
        key = (sprite_dir, side)
        if key not in self._portraits:
            img = None
            aset = self._load(sprite_dir)
            idle = aset.get("Idle") if aset is not None else None
            if idle is not None and idle.frames and idle.frames[0]:
                fr = idle.frames[0][0]
                fr = fr.subsurface(fr.get_bounding_rect()).copy()
                k = side / max(fr.get_width(), fr.get_height())
                img = pygame.transform.scale(fr, (max(1, int(fr.get_width() * k)),
                                                  max(1, int(fr.get_height() * k))))
            self._portraits[key] = img
        return self._portraits[key]

    def _draw_passive(self, surface, font):
        """Passiva accanto alla barra delle mosse, come offline: i campi arrivano
        dallo stato visivo e si copiano sull'entità del proprio Pokémon."""
        me = self.world.get(self.your_id)
        mv = self.world.me_vis
        h = self.world.hud
        if me is None or not mv or h is None:
            return
        for k, v in mv.items():
            if k not in ("item_cd", "charges", "in_rain"):
                setattr(me, k, v)
        # Eevee: candidati e forma si leggono da evoluzioni e scelte fatte.
        me.evolutions = self.pdef.evolutions
        for sl, ms in self.disp_moveset.items():
            ms.chosen = self._variant_move(ms, h["slots"][sl]["variant"])
        me.moveset = self.disp_moveset
        bar = getattr(self, "_bar", None)
        if bar is None:
            return
        px, py, ph = bar.passive_at
        from engine.jungle import CODE_WEATHER
        draw_passive(surface, hud.font(13), me, px, py, ph, PassiveCtx(
            now=self.world.match_time, portrait=self._portrait,
            in_rain=bool(mv.get("in_rain")),
            weather=CODE_WEATHER.get(h.get("weather", 0), "clear"),
            agitated=hatt_fx.count_agitated(self.world, me, self.world.match_time),
            charged=mag_fx.count_charged(self.world, me, self.world.match_time),
            frost_ready=swine_fx.count_frozen_ready(self.world, me, self.world.match_time),
            poisoned=moth_fx.count_poisoned(self.world, me, self.world.match_time),
            flowers=tuple(f for f in self.world.fxs.flowers if f.get("owner") == me.id),
            level=int(h.get("level", 1))))

    def _draw_disconnected(self, surface, font):
        """Etichetta sopra i Pokémon dei giocatori caduti."""
        for eid in self.world.disconnected:
            e = self.world.get(eid)
            if e is None:
                continue
            cam = self.camera
            lx, ly = cam.world_to_screen(e.pos.x * config.TILE_SIZE, e.pos.y * config.TILE_SIZE)
            sx = cam.vp_ox + lx * cam.vp_scale
            sy = cam.vp_oy + ly * cam.vp_scale
            name = self._names.get(eid, "")
            t = font.render(f"{name} DISCONNESSO", True, (250, 120, 110))
            surface.blit(t, (sx - t.get_width() // 2, sy - 70))

    def _draw_end(self, surface):
        s = self.session
        W, H = surface.get_size()
        if s.phase == C.ENDED and s.end_info and s.end_info["winner"] is not None:
            w = s.end_info["winner"]
            title = "VITTORIA!" if w == self.team else "SCONFITTA"
            sub = f"Ha vinto la squadra {'BLU' if w == 0 else 'ROSSA'}."
        else:
            title = "PARTITA TERMINATA"
            sub = (s.end_info or {}).get("message") or s.lost_reason or "Connessione chiusa."
        panel = pygame.Rect(W // 2 - 330, H // 2 - 90, 660, 180)
        bg = pygame.Surface(panel.size, pygame.SRCALPHA)
        bg.fill((14, 16, 22, 235))
        surface.blit(bg, panel)
        pygame.draw.rect(surface, (210, 190, 110), panel, 2)
        big = pygame.font.SysFont("consolas", 30, bold=True)
        small = pygame.font.SysFont("consolas", 17)
        tt = big.render(title, True, (255, 230, 120))
        surface.blit(tt, (panel.centerx - tt.get_width() // 2, panel.y + 22))
        for i, line in enumerate(_wrap(sub, 70)[:3]):
            st = small.render(line, True, (230, 230, 230))
            surface.blit(st, (panel.centerx - st.get_width() // 2, panel.y + 74 + i * 22))
        hint = small.render("INVIO o ESC: torna al menu", True, DIM)
        surface.blit(hint, (panel.centerx - hint.get_width() // 2, panel.bottom - 30))


def _wrap(text, n):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines
