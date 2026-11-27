"""Opzioni DENTRO la partita (offline, allenamento, LAN e online) e ordine di ESC.

ESC in partita: 1) chiude l'interfaccia aperta (il negozio); 2) se non c'è nulla
di aperto, apre le opzioni; 3) ESC di nuovo le chiude. Dalla partita si esce
solo da qui ("Esci dalla partita").

Le opzioni sono le stesse del menu principale (scenes/options_scene.py),
disegnate sopra la partita su un velo scuro. La partita NON si ferma: mentre
sono aperte l'input non arriva al gioco.
"""
from __future__ import annotations

import pygame

from . import sfx
from .scenes.options_scene import KeybindScene, OptionsScene

VEIL = (10, 12, 18, 238)


_veils: dict = {}        # misura della finestra -> velo (costruito una volta)


def _veil(surface) -> None:
    size = surface.get_size()
    v = _veils.get(size)
    if v is None:
        _veils.clear()
        v = _veils[size] = pygame.Surface(size, pygame.SRCALPHA)
        v.fill(VEIL)
    surface.blit(v, (0, 0))


class _MatchOptions(OptionsScene):
    ROWS = OptionsScene.ROWS + ("leave",)
    BACK_LABEL = "Torna alla partita"
    ESC_HINT = "ESC: torna alla partita"

    def __init__(self, app, menu):
        super().__init__(app)
        # Invio / Spazio appena aperte: si torna alla partita (non schermo intero).
        self.sel = self.ROWS.index("back")
        self.menu = menu
        self.leave_note = menu.leave_note

    def _backdrop(self, surface):
        _veil(surface)

    def _back(self):
        self.menu.closed = True

    def _change(self, key, delta):
        if key == "leave":
            if delta == 0:
                self.menu.leave()
        elif key == "keys":
            self.menu.show_keys()
        else:
            super()._change(key, delta)


class _MatchKeys(KeybindScene):
    def __init__(self, app, menu):
        super().__init__(app)
        self.menu = menu

    def _backdrop(self, surface):
        _veil(surface)

    def _activate(self, item):
        if item == "back":
            self.menu.show_options("keys")
        else:
            super()._activate(item)


class InGameMenu:
    def __init__(self, app, on_leave, leave_note=""):
        self.app = app
        self.on_leave = on_leave
        self.leave_note = leave_note
        self.closed = False
        self.page = _MatchOptions(app, self)

    def show_options(self, row=None):
        self.page = _MatchOptions(self.app, self)
        if row is not None:
            self.page.sel = self.page.ROWS.index(row)

    def show_keys(self):
        self.page = _MatchKeys(self.app, self)

    def leave(self):
        self.closed = True
        self.on_leave()

    def handle_event(self, ev) -> None:
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
            sfx.play("ui_click")
        elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            sfx.play("ui_back")
        self.page.handle_events([ev])

    def draw(self, surface, font=None) -> None:
        self.page.draw_fullres(surface, font)


class MatchMenuMixin:
    """Per le scene di partita (con `shop`, `comm` e `camera`). La finestra la
    disegna App sopra tutta l'interfaccia (`match_menu`)."""

    match_menu: InGameMenu | None = None

    def _escape(self) -> None:
        """ESC in partita: prima chiude il negozio, poi apre le opzioni."""
        if self.shop.open:
            self.shop.toggle()
        else:
            self._open_menu()

    def _open_menu(self) -> None:
        self._cancel_aim()
        # Un tasto dei ping tenuto premuto non deve restare "incastrato".
        self.comm.key_held = False
        self.comm.wheel = None
        app = getattr(self, "app", None) or getattr(self, "options_app", None)
        self.match_menu = InGameMenu(app, self._leave_match, self._leave_note())
        sfx.play("ui_confirm")

    def _menu_event(self, ev) -> None:
        menu = self.match_menu
        menu.handle_event(ev)
        if menu.closed:
            self.match_menu = None

    def _cancel_aim(self) -> None:
        raise NotImplementedError

    def _leave_match(self) -> None:
        raise NotImplementedError

    def _leave_note(self) -> str:
        return ""
