"""Loop principale del client: finestra, timestep fisso, scaling low-res, scene.

La finestra è ridimensionabile e supporta il fullscreen (F11). Il mondo viene
disegnato su una surface a risoluzione interna FISSA (config.LOWRES_*) e poi
scalato per riempire la finestra mantenendo le proporzioni (lettera-box): così
l'area di gioco visibile è la stessa a qualsiasi dimensione dello schermo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pygame

import config

MAX_FRAME_DT = 0.25
ROOT = Path(__file__).resolve().parents[1]


def _set_app_icon() -> None:
    """Icona della finestra e della barra applicazioni (prima di set_mode)."""
    if sys.platform == "win32":
        try:    # AppUserModelID proprio: la barra mostra la nostra icona, non quella di python.exe
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PokeMoba.Game")
        except Exception:
            pass
    try:
        pygame.display.set_icon(pygame.image.load(str(ROOT / "assets" / "ui" / "icon.png")))
    except (pygame.error, FileNotFoundError):
        pass


class App:
    def __init__(self, initial="menu", map_path=None, pokemon_path=None, start_level=1,
                 start_items=None, start_armature=None, flower_color=None):
        pygame.init()
        _set_app_icon()
        self.windowed_size = (config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        self.fullscreen = False
        self.window = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        pygame.display.set_caption(config.WINDOW_TITLE)
        self.lowres = pygame.Surface((config.LOWRES_WIDTH, config.LOWRES_HEIGHT)).convert()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 16)
        self.root = ROOT
        self.server = None
        self.profile = None                     # {"name", "avatar"} (game/avatars.py)
        self.running = True
        self.accumulator = 0.0
        # Trasformazione corrente lowres->finestra (scale + scostamento lettera-box).
        self._vp = (config.RENDER_SCALE, 0, 0)

        if initial == "match":
            from .scenes.match_scene import MatchScene
            self.scene = MatchScene(map_path, pokemon_path, start_level=start_level,
                                    start_items=start_items, start_armature=start_armature,
                                    flower_color=flower_color)
        else:
            from .avatars import load_profile
            self.profile = load_profile()       # nickname + immagine profilo salvati
            if self.profile is None:            # primo avvio: si chiede subito
                from .scenes.profile_scene import ProfileScene
                self.scene = ProfileScene(self, first=True)
            else:
                from .scenes.menu_scene import MenuScene
                self.scene = MenuScene(self)

    def _toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)

    def run(self):
        while self.running:
            dt = min(self.clock.tick(120) / 1000.0, MAX_FRAME_DT)
            events = pygame.event.get()
            for ev in events:
                if ev.type == pygame.QUIT:
                    self.running = False
                elif ev.type == pygame.VIDEORESIZE and not self.fullscreen:
                    self.windowed_size = (max(640, ev.w), max(360, ev.h))
                    self.window = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
                elif ev.type == pygame.KEYDOWN and ev.key in (pygame.K_F11, pygame.K_f):
                    self._toggle_fullscreen()
            self.scene.handle_events(events)

            self.accumulator += dt
            while self.accumulator >= config.TICK_DT:
                self.scene.fixed_update()
                self.accumulator -= config.TICK_DT
            self.scene.update(dt)

            self.scene.draw(self.lowres)
            self._present()

            if getattr(self.scene, "quit_app", False):
                self.running = False
            nxt = getattr(self.scene, "next_scene", None)
            if nxt is not None:
                self.scene.next_scene = None
                self.scene = nxt

        if self.server is not None:
            self.server.stop()
        pygame.quit()

    def _present(self):
        """Scala la lowres nella finestra (aspect-fit + lettera-box) e disegna la UI."""
        ww, wh = self.window.get_size()
        lw, lh = config.LOWRES_WIDTH, config.LOWRES_HEIGHT
        scale = min(ww / lw, wh / lh)
        dw, dh = int(lw * scale), int(lh * scale)
        ox, oy = (ww - dw) // 2, (wh - dh) // 2
        self._vp = (scale, ox, oy)
        # Comunica la trasformazione alla camera della scena (per il mouse).
        cam = getattr(self.scene, "camera", None)
        if cam is not None:
            cam.set_viewport_transform(scale, ox, oy)

        self.window.fill((0, 0, 0))
        self.window.blit(pygame.transform.scale(self.lowres, (dw, dh)), (ox, oy))
        self._draw_hud()
        fullres = getattr(self.scene, "draw_fullres", None)
        if fullres is not None:
            self.scene.fps = self.clock.get_fps()   # mostrato dall'HUD della partita
            fullres(self.window, self.font)
        pygame.display.flip()

    def _draw_hud(self):
        # Solo messaggi temporanei (eventi di rete, debug F3): l'HUD vero della
        # partita e' disegnato dalla scena in draw_fullres (game/hud.py).
        lines = list(self.scene.hud_lines()) if hasattr(self.scene, "hud_lines") else []
        y = 62
        for line in lines:
            self.window.blit(self.font.render(line, True, (0, 0, 0)), (9, y + 1))
            self.window.blit(self.font.render(line, True, (240, 240, 240)), (8, y))
            y += 20
