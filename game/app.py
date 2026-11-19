"""Loop principale del client: finestra, timestep fisso, scaling low-res, scene.

La finestra è ridimensionabile e supporta il fullscreen (F11). Il mondo viene
disegnato su una surface a risoluzione interna FISSA (config.LOWRES_*) e poi
scalato per riempire la finestra mantenendo le proporzioni (lettera-box): così
l'area di gioco visibile è la stessa a qualsiasi dimensione dello schermo.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pygame

import config

MAX_FRAME_DT = 0.25
ROOT = Path(__file__).resolve().parents[1]


def _set_dpi_aware() -> None:
    """Windows con scala >100%: senza DPI-awareness la finestra a schermo intero viene
    ingrandita dal sistema e la barra delle applicazioni resta visibile/zoomata."""
    if sys.platform == "win32":
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


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


def _options_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "PokeMoba" / "options.json"


def load_options() -> dict:
    try:
        data = json.loads(_options_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_options(update: dict) -> None:
    data = load_options()
    data.update(update)
    try:
        p = _options_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


class App:
    def __init__(self, initial="menu", map_path=None, pokemon_path=None, start_level=1,
                 start_items=None, start_armature=None, flower_color=None):
        _set_dpi_aware()
        pygame.init()
        _set_app_icon()
        opts = load_options()
        from . import audio, keybinds
        audio.init(opts)
        keybinds.load(opts)
        self.fps_cap = int(opts.get("fps_cap", 120) or 0)   # 0 = senza limite
        self.windowed_size = (config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        self.fullscreen = False
        self.window = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        if opts.get("fullscreen"):
            self.set_fullscreen(True)
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
        # Aggiornamento automatico dalle GitHub Releases (solo exe pubblicato).
        from .updater import Updater
        self.updater = Updater()
        self.updater.start()
        self._restart_at = 0

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

    def set_fullscreen(self, on: bool) -> None:
        """Schermo intero senza bordi sull'intero monitor (niente barra del titolo
        né barra delle applicazioni); lo stato viene salvato tra una sessione e l'altra."""
        self.fullscreen = bool(on)
        if self.fullscreen:
            try:
                size = pygame.display.get_desktop_sizes()[0]
            except (pygame.error, IndexError, AttributeError):
                size = (0, 0)
            self.window = pygame.display.set_mode(size, pygame.FULLSCREEN | pygame.NOFRAME)
        else:
            self.window = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        _save_options({"fullscreen": self.fullscreen})

    def _toggle_fullscreen(self):
        self.set_fullscreen(not self.fullscreen)

    def _sync_music(self):
        from . import audio
        if audio.scene_wants_menu_music(self.scene):
            audio.play_music()
        else:
            audio.stop_music()

    _NAV_KEYS = (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB)

    def _ui_sounds(self, events):
        """Suoni generici dei menu (scene senza camera): clic, frecce, Invio, Esc.
        Nelle partite i suoni li gestisce la scena (game/sfx.py)."""
        if getattr(self.scene, "camera", None) is not None:
            return
        from . import sfx
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
                sfx.play("ui_click")
            elif ev.type == pygame.KEYDOWN:
                if ev.key in self._NAV_KEYS:
                    sfx.play("ui_move")
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    sfx.play("ui_confirm")
                elif ev.key == pygame.K_ESCAPE:
                    sfx.play("ui_back")

    def run(self):
        self._sync_music()
        while self.running:
            dt = min(self.clock.tick(self.fps_cap) / 1000.0, MAX_FRAME_DT)
            events = pygame.event.get()
            for ev in events:
                if ev.type == pygame.QUIT:
                    self.running = False
                elif ev.type == pygame.VIDEORESIZE and not self.fullscreen:
                    self.windowed_size = (max(640, ev.w), max(360, ev.h))
                    self.window = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
                elif ev.type == pygame.KEYDOWN and ev.key in (pygame.K_F11, pygame.K_f):
                    self._toggle_fullscreen()
            self._ui_sounds(events)
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
                self._sync_music()
            self._check_update()

        # Aggiornamento scaricato durante una partita: si installa ora (senza riavvio).
        self.updater.apply(relaunch=False)
        if self.server is not None:
            self.server.stop()
        pygame.quit()

    def _check_update(self):
        """Aggiornamento pronto e si e' nel menu principale: avviso per ~2 s, poi
        lo script sostituisce l'exe e lo riavvia. Altrove (partita, draft online,
        selezione) si aspetta: verra' installato alla chiusura del gioco."""
        if self.updater.state != "ready":
            return
        now = pygame.time.get_ticks()
        if self._restart_at == 0:
            if type(self.scene).__name__ == "MenuScene":
                self._restart_at = now + 2000
            return
        if now >= self._restart_at and self.updater.apply(relaunch=True):
            self.running = False

    def _draw_update(self):
        """Riga dell'aggiornamento in alto al centro e versione in basso a destra (menu)."""
        from . import version
        up = self.updater
        text = up.banner()
        if text and self._restart_at:
            text = f"Aggiornamento v{up.new_build} pronto: riavvio..."
        ww, wh = self.window.get_size()
        if getattr(self.scene, "camera", None) is not None:
            return          # in partita niente scritte sopra l'HUD
        if text:
            img = self.font.render(text, True, (240, 220, 150))
            r = img.get_rect(midtop=(ww // 2, 8))
            bg = r.inflate(20, 10)
            pygame.draw.rect(self.window, (20, 24, 22), bg, border_radius=6)
            pygame.draw.rect(self.window, (200, 165, 80), bg, 1, border_radius=6)
            if up.state == "downloading":
                bar = pygame.Rect(bg.x + 4, bg.bottom - 4, int((bg.w - 8) * up.progress), 2)
                pygame.draw.rect(self.window, (200, 165, 80), bar)
            self.window.blit(img, r)
        img = self.font.render(version.label(), True, (120, 120, 110))
        self.window.blit(img, img.get_rect(bottomright=(ww - 8, wh - 6)))

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
        self._draw_update()
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
