"""Opzioni (menu principale): per ora solo lo schermo intero.

Clic sul pulsante o Invio per attivare/disattivare; F11 funziona ovunque.
ESC torna al menu. La scelta viene salvata (%APPDATA%/PokeMoba/options.json).
"""
from __future__ import annotations

import pygame

from .online_lobby_scene import BG, DIM, GOLD, TEXT, font
from .menu_scene import PANEL, PANEL_HI, BORDER


class OptionsScene:
    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self._rects: list = []

    def _back(self):
        from .menu_scene import MenuScene
        self.next_scene = MenuScene(self.app)

    def _activate(self, key):
        if key == "fullscreen":
            self.app.set_fullscreen(not self.app.fullscreen)
        elif key == "back":
            self._back()

    def handle_events(self, events):
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for r, key in self._rects:
                    if r.collidepoint(ev.pos):
                        self._activate(key)
                        break
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self._back()
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self._activate("fullscreen")

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
        t = font(max(16, H // 38), True)
        small = font(max(13, H // 54))
        title = big.render("Opzioni", True, GOLD)
        surface.blit(title, (W // 2 - title.get_width() // 2, int(H * 0.08)))
        bw, bh = min(int(W * 0.5), 560), max(44, H // 13)
        self._rects = []
        mouse = pygame.mouse.get_pos()
        rows = [("fullscreen", f"Schermo intero:  {'SÌ' if self.app.fullscreen else 'NO'}"),
                ("back", "Indietro")]
        for i, (key, label) in enumerate(rows):
            r = pygame.Rect(W // 2 - bw // 2, int(H * 0.28) + i * (bh + 14), bw, bh)
            self._rects.append((r, key))
            on = r.collidepoint(mouse)
            pygame.draw.rect(surface, PANEL_HI if on else PANEL, r, border_radius=8)
            pygame.draw.rect(surface, GOLD if on else BORDER, r, 2, border_radius=8)
            txt = t.render(label, True, GOLD if on else TEXT)
            surface.blit(txt, (r.centerx - txt.get_width() // 2, r.centery - txt.get_height() // 2))
        hint = small.render("clic o Invio: cambia      F11: schermo intero      ESC: torna al menu",
                            True, DIM)
        surface.blit(hint, (W // 2 - hint.get_width() // 2, H - hint.get_height() - 12))
