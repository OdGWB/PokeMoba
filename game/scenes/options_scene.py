"""Opzioni (menu principale): schermo, audio, controlli.

Righe: schermo intero, volume della musica, limite FPS, velocità della camera,
lancio rapido (smart cast) e la pagina dei tasti. Frecce su/giù per scegliere,
sinistra/destra (o clic sulle frecce) per cambiare il valore, Invio/clic per
attivare. Tutto si salva subito in %APPDATA%/PokeMoba/options.json.
"""
from __future__ import annotations

import pygame

from .. import audio, keybinds
from ..app import _save_options
from .online_lobby_scene import BG, DIM, GOLD, TEXT, font
from .menu_scene import PANEL, PANEL_HI, BORDER

VOL_STEP = 0.1


def _row_box(surface, r, on, label, value=None, arrows=False, t=None):
    pygame.draw.rect(surface, PANEL_HI if on else PANEL, r, border_radius=8)
    pygame.draw.rect(surface, GOLD if on else BORDER, r, 2, border_radius=8)
    txt = t.render(label, True, GOLD if on else TEXT)
    if value is None:
        surface.blit(txt, (r.centerx - txt.get_width() // 2, r.centery - txt.get_height() // 2))
        return None, None
    surface.blit(txt, (r.x + 18, r.centery - txt.get_height() // 2))
    val = t.render(value, True, GOLD if on else TEXT)
    left = right = None
    if arrows:
        aw = 30
        right = pygame.Rect(r.right - 12 - aw, r.y + 6, aw, r.h - 12)
        vx = right.x - 10 - val.get_width()
        left = pygame.Rect(vx - 10 - aw, r.y + 6, aw, r.h - 12)
        for a, ch in ((left, "<"), (right, ">")):
            pygame.draw.rect(surface, (40, 44, 56), a, border_radius=5)
            g = t.render(ch, True, TEXT)
            surface.blit(g, (a.centerx - g.get_width() // 2, a.centery - g.get_height() // 2))
        surface.blit(val, (vx, r.centery - val.get_height() // 2))
    else:
        surface.blit(val, (r.right - 18 - val.get_width(), r.centery - val.get_height() // 2))
    return left, right


class OptionsScene:
    ROWS = ("fullscreen", "music", "fps", "camera", "smart", "keys", "back")

    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self.sel = 0
        self._rects: list = []       # (rect, key, delta) delta 0 = attiva

    def _back(self):
        from .menu_scene import MenuScene
        self.next_scene = MenuScene(self.app)

    # --- valori ----------------------------------------------------------------------
    def _value(self, key):
        if key == "fullscreen":
            return "SÌ" if self.app.fullscreen else "NO"
        if key == "music":
            return f"{round(audio.music_volume() * 100)}%"
        if key == "fps":
            cap = getattr(self.app, "fps_cap", 120)
            return "senza limite" if not cap else f"{cap}"
        if key == "camera":
            return f"x{keybinds.camera_speed:.2f}".rstrip("0").rstrip(".")
        if key == "smart":
            return "SÌ" if keybinds.smart_cast else "NO"
        return None

    def _change(self, key, delta):
        if key == "fullscreen":
            self.app.set_fullscreen(not self.app.fullscreen)
        elif key == "music":
            d = delta or 1
            v = round(audio.music_volume() + d * VOL_STEP, 2)
            if delta == 0 and v > 1.0:
                v = 0.0                                   # Invio: giro completo
            audio.set_music_volume(v)
            _save_options({"music_volume": audio.music_volume()})
        elif key == "fps":
            caps = keybinds.FPS_CAPS
            cur = getattr(self.app, "fps_cap", 120)
            i = caps.index(cur) if cur in caps else 2
            self.app.fps_cap = caps[(i + (delta or 1)) % len(caps)]
            _save_options({"fps_cap": self.app.fps_cap})
        elif key == "camera":
            sp = keybinds.CAM_SPEEDS
            cur = keybinds.camera_speed
            i = min(range(len(sp)), key=lambda k: abs(sp[k] - cur))
            keybinds.camera_speed = sp[(i + (delta or 1)) % len(sp)]
            _save_options(keybinds.to_options())
        elif key == "smart":
            keybinds.smart_cast = not keybinds.smart_cast
            _save_options(keybinds.to_options())
        elif key == "keys":
            self.next_scene = KeybindScene(self.app)
        elif key == "back":
            self._back()

    # --- ciclo -----------------------------------------------------------------------
    def handle_events(self, events):
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
                for r, key, delta in self._rects:
                    if r.collidepoint(ev.pos):
                        if delta == 0 and ev.button == 3:
                            delta = -1
                        self._change(key, delta)
                        break
            elif ev.type == pygame.KEYDOWN:
                key = self.ROWS[self.sel]
                if ev.key == pygame.K_ESCAPE:
                    self._back()
                elif ev.key in (pygame.K_DOWN, pygame.K_s):
                    self.sel = (self.sel + 1) % len(self.ROWS)
                elif ev.key in (pygame.K_UP, pygame.K_w):
                    self.sel = (self.sel - 1) % len(self.ROWS)
                elif ev.key in (pygame.K_LEFT, pygame.K_a) and self._value(key) is not None:
                    self._change(key, -1)
                elif ev.key in (pygame.K_RIGHT, pygame.K_d) and self._value(key) is not None:
                    self._change(key, 1)
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self._change(key, 0)
            elif ev.type == pygame.MOUSEMOTION:
                for i, k in enumerate(self.ROWS):
                    for r, key, _d in self._rects:
                        if key == k and r.collidepoint(ev.pos):
                            self.sel = i

    def fixed_update(self):
        pass

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def draw_fullres(self, surface, f):
        W, H = surface.get_size()
        surface.fill(BG)
        big = font(max(26, H // 22), True)
        t = font(max(15, H // 42), True)
        small = font(max(13, H // 54))
        title = big.render("Opzioni", True, GOLD)
        surface.blit(title, (W // 2 - title.get_width() // 2, int(H * 0.06)))
        labels = {"fullscreen": "Schermo intero", "music": "Volume musica",
                  "fps": "Limite FPS", "camera": "Velocità camera (bordi)",
                  "smart": "Lancio rapido (smart cast)", "keys": "Tasti...",
                  "back": "Indietro"}
        bw, bh = min(int(W * 0.6), 640), max(40, H // 15)
        self._rects = []
        y0 = int(H * 0.18)
        for i, key in enumerate(self.ROWS):
            r = pygame.Rect(W // 2 - bw // 2, y0 + i * (bh + 10), bw, bh)
            on = i == self.sel
            val = self._value(key)
            arrows = key in ("music", "fps", "camera")
            left, right = _row_box(surface, r, on, labels[key], val, arrows, t)
            if left is not None:
                self._rects += [(left, key, -1), (right, key, 1)]
            self._rects.append((r, key, 0))
        notes = {"smart": "Lancio rapido: la mossa parte appena premi il tasto, verso il mouse "
                          "(Tiro Lungo e la R di Magnezone restano a mira).",
                 "fps": "Limite FPS: più basso = meno lavoro per la CPU (portatili).",
                 "camera": "Velocità dello scorrimento quando il mouse tocca il bordo.",
                 "music": "Musica del menu (in partita non suona)."}
        note = notes.get(self.ROWS[self.sel])
        if note:
            n = small.render(note, True, DIM)
            surface.blit(n, (W // 2 - n.get_width() // 2, y0 + len(self.ROWS) * (bh + 10) + 6))
        hint = small.render("frecce: scegli e cambia     Invio/clic: attiva     "
                            "clic destro: indietro di un valore     ESC: menu", True, DIM)
        surface.blit(hint, (W // 2 - hint.get_width() // 2, H - hint.get_height() - 12))


class KeybindScene:
    """Tasti: clic (o Invio) su un'azione, poi premi il nuovo tasto. Se il tasto
    era già usato, le due azioni si scambiano. ESC annulla l'attesa o torna."""

    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self.sel = 0
        self.waiting = None          # azione in attesa del nuovo tasto
        self.msg = ""
        self._rects: list = []

    def _items(self):
        return [a for a, _l, _k in keybinds.ACTIONS] + ["reset", "back"]

    def _activate(self, item):
        if item == "back":
            self.next_scene = OptionsScene(self.app)
            self.next_scene.sel = OptionsScene.ROWS.index("keys")
        elif item == "reset":
            keybinds.reset()
            _save_options(keybinds.to_options())
            self.msg = "Tasti predefiniti ripristinati."
        else:
            self.waiting = item
            self.msg = ""

    def handle_events(self, events):
        for ev in events:
            if self.waiting is not None:
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        self.waiting = None
                    else:
                        err = keybinds.assign(self.waiting, ev.key)
                        if err:
                            self.msg = err
                        else:
                            _save_options(keybinds.to_options())
                            self.msg = ""
                        self.waiting = None
                continue
            items = self._items()
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for r, item in self._rects:
                    if r.collidepoint(ev.pos):
                        self._activate(item)
                        break
            elif ev.type == pygame.MOUSEMOTION:
                for r, item in self._rects:
                    if r.collidepoint(ev.pos):
                        self.sel = items.index(item)
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self._activate("back")
                elif ev.key == pygame.K_DOWN:
                    self.sel = (self.sel + 1) % len(items)
                elif ev.key == pygame.K_UP:
                    self.sel = (self.sel - 1) % len(items)
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._activate(items[self.sel])

    def fixed_update(self):
        pass

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def draw_fullres(self, surface, f):
        W, H = surface.get_size()
        surface.fill(BG)
        big = font(max(26, H // 22), True)
        t = font(max(14, H // 46), True)
        small = font(max(13, H // 54))
        title = big.render("Tasti", True, GOLD)
        surface.blit(title, (W // 2 - title.get_width() // 2, int(H * 0.04)))
        items = self._items()
        bw = min(int(W * 0.6), 640)
        bh = max(30, min(44, (H - int(H * 0.16) - 90) // len(items) - 6))
        y0 = int(H * 0.13)
        self._rects = []
        for i, item in enumerate(items):
            r = pygame.Rect(W // 2 - bw // 2, y0 + i * (bh + 6), bw, bh)
            on = i == self.sel
            self._rects.append((r, item))
            if item == "reset":
                _row_box(surface, r, on, "Ripristina predefiniti", t=t)
            elif item == "back":
                _row_box(surface, r, on, "Indietro", t=t)
            else:
                val = "premi un tasto..." if self.waiting == item else keybinds.key_name(item)
                _row_box(surface, r, on or self.waiting == item, keybinds.LABELS[item], val, t=t)
        if self.msg:
            m = small.render(self.msg, True, GOLD)
            surface.blit(m, (W // 2 - m.get_width() // 2, H - 64))
        hint = small.render("clic/Invio: cambia tasto (poi premi il nuovo)     Ctrl + tasto mossa: "
                            "sale di grado     1-6 oggetti     ESC: indietro", True, DIM)
        surface.blit(hint, (W // 2 - hint.get_width() // 2, H - hint.get_height() - 12))
