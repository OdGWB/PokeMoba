"""Partita ONLINE (WebRTC): estende NetMatchScene con predizione del proprio
personaggio, interpolazione degli altri, effetti visivi dall'host, HUD di
debug della rete (F3) e fine partita pulita se l'host cade.

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

from ..fx import FXSystem
from ..online_world import MovementModel, OnlineWorld
from ..sprites.animator import SpriteAnimator
from .net_match_scene import NetMatchScene

DIM = (165, 170, 180)


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
        self.show_debug = True
        self.slot_panel = None
        self._acc = 0.0
        self._names = {p["entity_id"]: p["name"] for p in session.start_info["players"]}
        self._loaded_sent = False

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
            for e in events:
                eid, name = e.get("eid"), e.get("anim")
                if eid is not None and name:
                    anim = self.animators.get(int(eid))
                    if isinstance(anim, SpriteAnimator):
                        anim.play_once(name, float(e.get("anim_speed", 1.0)))
            try:
                self.fx.spawn_events(events)
            except Exception:       # evento cosmetico incompleto: si salta
                pass
        self.fx.update(dt)
        if self.slot_panel is not None:
            self.slot_panel.update()

    def draw(self, surface):
        super().draw(surface)
        self.fx.draw(surface, self.camera)
        if not self._loaded_sent:
            self._loaded_sent = True
            self.session.send_loaded()

    # --- HUD --------------------------------------------------------------------------------
    def hud_lines(self):
        lines = super().hud_lines()
        lines[-1] = ("ONLINE  Dx: muovi  Sx: attacca  Q/W/E/R  Ctrl+tasto: grado  "
                     "F3: rete" + ("  F2: slot" if self.host else "") + "  ESC: esci")
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
        self._draw_disconnected(surface, font)
        if self.slot_panel is not None:
            self.slot_panel.draw(surface, font)
        if self.session.phase in (C.ENDED, C.LOST):
            self._draw_end(surface)

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
