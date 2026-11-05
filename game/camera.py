"""Camera 2D: un semplice offset applicato al rendering.

Lavora nello spazio pixel della surface a bassa risoluzione (LOWRES_*). Tutto
ciò che si disegna viene traslato di -offset.

Comandi (gestiti qui, stato deciso dallo scene/input):
  - agganciata al proprio Pokémon (default)
  - Y: sblocca/riaggancia; da sbloccata, scorre avvicinando il mouse ai bordi
  - Spazio tenuto premuto: ricentra sul proprio Pokémon
"""
from __future__ import annotations

import pygame

import config


class Camera:
    def __init__(self, view_w: int, view_h: int, map_w_px: int, map_h_px: int):
        self.view_w = view_w
        self.view_h = view_h
        self.map_w_px = map_w_px
        self.map_h_px = map_h_px
        self.x = 0.0  # pixel world dell'angolo in alto a sinistra della vista
        self.y = 0.0
        # Offset di rendering INTERO, arrotondato una volta per frame (snap()):
        # mappa e unita lo condividono, cosi non "tremolano" di 1px tra loro.
        self.ox = 0
        self.oy = 0
        # Trasformazione finestra->lowres (impostata dall'App a ogni frame per il
        # mapping del mouse; tiene conto di scaling e lettera-box del fullscreen).
        self.vp_scale = config.RENDER_SCALE
        self.vp_ox = 0.0
        self.vp_oy = 0.0

    def set_viewport_transform(self, scale, ox, oy):
        self.vp_scale = scale if scale > 1e-6 else 1.0
        self.vp_ox = ox
        self.vp_oy = oy

    # --- controllo -----------------------------------------------------------
    def center_on(self, wx: float, wy: float) -> None:
        self.x = wx - self.view_w / 2
        self.y = wy - self.view_h / 2
        self._clamp()

    def update(self, dt: float, locked: bool, target_wx: float, target_wy: float,
               mouse_win: tuple[int, int], space_held: bool,
               edge_ok: bool = True) -> None:
        if space_held or locked:
            self.center_on(target_wx, target_wy)
            return
        # Sbloccata: edge-scrolling in base alla posizione del mouse nella finestra
        # REALE (non quella di default: in schermo intero o ridimensionata no).
        # edge_ok=False (mouse sopra la minimappa) sospende lo scorrimento.
        if edge_ok:
            mx, my = mouse_win
            surf = pygame.display.get_surface()
            ww, wh = surf.get_size() if surf is not None else (config.WINDOW_WIDTH,
                                                               config.WINDOW_HEIGHT)
            m = config.EDGE_SCROLL_MARGIN
            speed = config.EDGE_SCROLL_SPEED * dt
            if mx < m:
                self.x -= speed
            elif mx > ww - m:
                self.x += speed
            if my < m:
                self.y -= speed
            elif my > wh - m:
                self.y += speed
        self._clamp()

    def _clamp(self) -> None:
        # Non mostrare oltre i bordi mappa (se la mappa è più piccola, centra).
        if self.map_w_px <= self.view_w:
            self.x = (self.map_w_px - self.view_w) / 2
        else:
            self.x = max(0.0, min(self.x, self.map_w_px - self.view_w))
        if self.map_h_px <= self.view_h:
            self.y = (self.map_h_px - self.view_h) / 2
        else:
            self.y = max(0.0, min(self.y, self.map_h_px - self.view_h))

    # --- trasformazioni ------------------------------------------------------
    def snap(self) -> None:
        """Fissa l'offset di rendering intero per il frame corrente. Da chiamare
        una sola volta per frame, prima di disegnare mappa e unita."""
        self.ox = round(self.x)
        self.oy = round(self.y)

    def world_to_screen(self, wx: float, wy: float) -> tuple[int, int]:
        # Stesso offset intero (ox/oy) usato dai layer della mappa: un punto del
        # mondo cade sullo stesso pixel sia per il terreno che per le unita.
        return (round(wx) - self.ox, round(wy) - self.oy)

    def screen_window_to_world(self, mx: int, my: int) -> tuple[float, float]:
        """Da coordinate finestra (mouse) a coordinate pixel-world.

        Tiene conto dello scaling e dello scostamento (lettera-box) con cui la
        surface low-res viene disegnata nella finestra.
        """
        lx = (mx - self.vp_ox) / self.vp_scale
        ly = (my - self.vp_oy) / self.vp_scale
        return (lx + self.x, ly + self.y)

    def visible_tile_bounds(self, tile_size: int, grid_w: int, grid_h: int):
        """Intervallo di tile visibili (per il culling), con un tile di margine."""
        x0 = max(0, int(self.x // tile_size) - 1)
        y0 = max(0, int(self.y // tile_size) - 1)
        x1 = min(grid_w, int((self.x + self.view_w) // tile_size) + 2)
        y1 = min(grid_h, int((self.y + self.view_h) // tile_size) + 2)
        return x0, y0, x1, y1
