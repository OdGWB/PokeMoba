"""Scelta dell'ALLENAMENTO (menu principale -> "Allenamento").

Stessa griglia e anteprima della selezione offline (CharSelectScene), con in
piu', a destra del titolo:
  - il LIVELLO di partenza (- / + o clic sulle frecce, 1..MAX_LEVEL);
  - il pulsante "Tutorial" (tasto F1): la guida passo passo con Charmander.
Invio / "Allenati" apre TrainingScene sulla mappa piccola; Esc torna al menu.
Da allenamento e tutorial Esc riporta qui.
"""
from __future__ import annotations

import pygame

import config
from engine.stats import MAX_LEVEL

from .. import ui_theme as UI
from .char_select_scene import CharSelectScene


def _back_here(app):
    return TrainingSelectScene(app)


class TrainingSelectScene(CharSelectScene):
    PLAY_LABEL = "Allenati"
    HINTS = [("frecce", "scegli"), ("Tab", "ruolo"), ("- +", "livello"), ("F1", "tutorial")]
    _last = {"sel": 0, "level": 1}      # ricordati tra un allenamento e l'altro

    def __init__(self, app):
        super().__init__(app, 0)
        self.sel = min(self._last["sel"], len(self.defs) - 1)
        self.level = self._last["level"]
        self.tutorial = False
        self._lvl_rects: list = []
        self._tut_rect = None

    def _header(self):
        return ("Menu", "Allenamento",
                "mappa piccola · tre manichini · ricariche, oro e livello a piacere")

    def _back(self):
        from .menu_scene import MenuScene
        self.next_scene = MenuScene(self.app)

    def _set_level(self, lv):
        self.level = max(1, min(MAX_LEVEL, lv))

    def _start_tutorial(self):
        self.tutorial = True
        self._start()

    def _build_scene(self):
        TrainingSelectScene._last.update(sel=self.sel, level=self.level)
        if self.tutorial:
            from .tutorial_scene import TutorialScene
            return TutorialScene(back=_back_here)
        from .training_scene import TrainingScene
        return TrainingScene(str(self.app.root / config.ROSTER[self.sel]),
                             start_level=self.level,
                             flower_color=self.flower_color if self._has_colors() else None,
                             back=_back_here)

    # --- input ---------------------------------------------------------------
    def _extra_key(self, ev) -> bool:
        if ev.key in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS, pygame.K_PAGEUP):
            self._set_level(self.level + 1)
        elif ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_PAGEDOWN):
            self._set_level(self.level - 1)
        elif ev.key == pygame.K_F1:
            self._start_tutorial()
        else:
            return False
        return True

    def _extra_click(self, pos) -> bool:
        for r, d in self._lvl_rects:
            if r.collidepoint(pos):
                self._set_level(self.level + d)
                return True
        if self._tut_rect and self._tut_rect.collidepoint(pos):
            self._start_tutorial()
            return True
        return False

    # --- disegno -------------------------------------------------------------
    def _draw_extra(self, surface, ox, S, mouse):
        # Tutorial a destra, sopra il pannello d'anteprima (x 780..1232).
        right = ox + S(1232)
        tut = pygame.Rect(0, S(26), S(176), S(40))
        tut.right = right
        hov = tut.collidepoint(mouse)
        pygame.draw.rect(surface, UI.SEL if hov else UI.CARD, tut, border_radius=S(9))
        pygame.draw.rect(surface, UI.GOLD, tut, 1, border_radius=S(9))
        f = UI.font(max(12, S(15)), bold=True)
        t = f.render("Tutorial", True, UI.GOLD)
        kw = UI.font(max(10, S(11))).size("F1")[0] + 12
        x = tut.x + (tut.w - t.get_width() - S(8) - kw) // 2
        surface.blit(t, (x, tut.centery - t.get_height() // 2))
        UI.keycap(surface, "F1", x + t.get_width() + S(8), tut.centery - 11)
        self._tut_rect = tut

        # Livello di partenza: [-] Liv. N [+]
        bh = S(40)
        bw = S(34)
        plus = pygame.Rect(0, tut.y, bw, bh)
        plus.right = tut.x - S(18)
        val_w = S(92)
        val = pygame.Rect(plus.x - S(6) - val_w, tut.y, val_w, bh)
        minus = pygame.Rect(val.x - S(6) - bw, tut.y, bw, bh)
        self._lvl_rects = [(minus, -1), (plus, +1)]
        for r, sign in self._lvl_rects:
            off = (sign < 0 and self.level <= 1) or (sign > 0 and self.level >= MAX_LEVEL)
            on = r.collidepoint(mouse) and not off
            pygame.draw.rect(surface, UI.SEL if on else UI.CARD, r, border_radius=S(8))
            pygame.draw.rect(surface, UI.CARD_LINE, r, 1, border_radius=S(8))
            col = UI.FAINT if off else (UI.GOLD if on else UI.TEXT)
            cx, cy, s = r.centerx, r.centery, max(4, S(6))
            pygame.draw.rect(surface, col, (cx - s, cy - 1, 2 * s, 3))
            if sign > 0:
                pygame.draw.rect(surface, col, (cx - 1, cy - s, 3, 2 * s))
        pygame.draw.rect(surface, UI.CARD, val, border_radius=S(8))
        pygame.draw.rect(surface, UI.CARD_LINE, val, 1, border_radius=S(8))
        cap = UI.font(max(10, S(11))).render("livello", True, UI.DIM)
        num = UI.font(max(14, S(19)), bold=True).render(str(self.level), True, UI.GOLD)
        h = cap.get_height() + num.get_height() - S(4)
        y = val.centery - h // 2
        surface.blit(cap, (val.centerx - cap.get_width() // 2, y))
        surface.blit(num, (val.centerx - num.get_width() // 2, y + cap.get_height() - S(4)))
