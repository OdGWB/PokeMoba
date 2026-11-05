"""Minimappa cliccabile in basso a destra.

Mostra terreno, strutture, tane, alleati e nemici VISIBILI, la nebbia di guerra
e il riquadro della camera. Disegnata a piena risoluzione (finestra). Clic
sinistro = sposta lì la camera; clic destro = ordina al Pokémon di andare lì.
"""
from __future__ import annotations

import numpy as np
import pygame

import config
from engine.entities import Core, Minion, Pokemon, Structure
from engine.grid import (TILE_BUSH, TILE_JUNGLE_WALL, TILE_LANE, TILE_PUDDLE,
                         TILE_RIVER, TILE_WALL)

SIZE = 190
MARGIN = 12
_TILE_COL = {0: (52, 80, 56), TILE_LANE: (150, 134, 92), TILE_RIVER: (64, 110, 160),
             TILE_BUSH: (34, 70, 44), TILE_WALL: (40, 42, 48),
             TILE_JUNGLE_WALL: (52, 60, 50), TILE_PUDDLE: (70, 120, 150)}
_FOG_UNSEEN = (5, 6, 11, 240)     # tile mai visto
_FOG_SEEN = (8, 10, 16, 150)      # tile esplorato ma non visibile ora
DEN_COL = {"low": (240, 150, 60), "high": (180, 120, 230)}


class Minimap:
    def __init__(self, grid, map_data):
        self.grid = grid
        self.map = map_data
        w, h = grid.width, grid.height
        self.scale = SIZE / max(w, h)
        self.mw = int(w * self.scale)
        self.mh = int(h * self.scale)
        self.base = self._render_base()
        self._fog = None
        self._exp_mask = None
        self._exp_len = -1
        self.rect = pygame.Rect(0, 0, self.mw, self.mh)  # aggiornato al draw

    def _render_base(self):
        surf = pygame.Surface((self.mw, self.mh))
        surf.fill((18, 20, 24))
        s = self.scale
        cell = max(1, int(s + 0.999))
        for ty in range(self.grid.height):
            row = self.grid.tiles[ty]
            for tx in range(self.grid.width):
                col = _TILE_COL.get(row[tx], _TILE_COL[0])
                surf.fill(col, pygame.Rect(int(tx * s), int(ty * s), cell, cell))
        return surf

    def rebuild_fog(self, vision, team):
        """Ricostruisce l'overlay di nebbia (solo quando la visione cambia).

        Una immagine RGBA a risoluzione di TILE costruita con numpy (visibile =
        trasparente, esplorato = velo leggero, mai visto = velo scuro) e poi scalata
        NEAREST alla dimensione della minimappa: un'operazione sola invece di un
        `fill` per ogni tile (prima ~40 ms a chiamata, ora ~1 ms)."""
        w, h = self.grid.width, self.grid.height
        exp = vision.explored.get(team) or ()
        if len(exp) != self._exp_len or self._exp_mask is None:
            # L'esplorato cresce soltanto: la maschera si rifa solo quando cambia.
            self._exp_len = len(exp)
            m = np.zeros((h, w), dtype=bool)
            if exp:
                pts = np.array(list(exp), dtype=np.intp)
                m[pts[:, 1], pts[:, 0]] = True
            self._exp_mask = m
        img = np.empty((h, w, 4), dtype=np.uint8)
        img[:] = _FOG_UNSEEN
        img[self._exp_mask] = _FOG_SEEN
        vis = vision.visible_tiles.get(team)
        if vis:
            pts = np.array(list(vis), dtype=np.intp)
            img[pts[:, 1], pts[:, 0]] = 0
        small = pygame.image.frombuffer(img.tobytes(), (w, h), "RGBA")
        self._fog = pygame.transform.scale(small, (self.mw, self.mh))

    # --- conversioni ---------------------------------------------------------
    def _m(self, wx, wy):
        return (self.rect.x + int(wx * self.scale), self.rect.y + int(wy * self.scale))

    def contains(self, pos) -> bool:
        return self.rect.collidepoint(pos)

    def to_world_tile(self, pos):
        lx = (pos[0] - self.rect.x) / self.scale
        ly = (pos[1] - self.rect.y) / self.scale
        return lx, ly

    # --- disegno -------------------------------------------------------------
    def draw(self, surface, world, camera, vision, player_team, dens, player=None):
        W, H = surface.get_size()
        self.rect.topleft = (W - self.mw - MARGIN, H - self.mh - MARGIN)
        surface.blit(self.base, self.rect)
        if self._fog is not None:
            surface.blit(self._fog, self.rect)
        explored = vision.explored.get(player_team, set()) if vision is not None else None

        # Tane (se esplorate).
        for name, (dx, dy) in (dens or {}).items():
            if explored is None or (int(dx), int(dy)) in explored:
                pygame.draw.circle(surface, DEN_COL.get(name, (220, 220, 220)),
                                   self._m(dx, dy), 3)
        # Strutture.
        for s in world.structures():
            if not s.alive:
                continue
            if explored is not None and (int(s.pos.x), int(s.pos.y)) not in explored:
                continue
            col = config.TEAM_COLORS.get(s.team, (200, 200, 200))
            r = 4 if isinstance(s, Core) else 2
            pygame.draw.rect(surface, col, pygame.Rect(self._m(s.pos.x, s.pos.y), (r, r)))
        # Spiriti di Spiritomb: li vede (e raccoglie) solo il proprietario.
        for sp in getattr(world, "spirits", ()):
            if sp.team == player_team and (player is None or sp.owner_id == player.id):
                x, y = self._m(sp.pos.x, sp.pos.y)
                pygame.draw.circle(surface, (40, 80, 20), (x, y), 3)
                pygame.draw.circle(surface, (170, 245, 60), (x, y), 2)
        # Unità: alleati sempre, nemici solo se visibili.
        for u in world.alive_units():
            if u.team != player_team:
                if vision is not None and not vision.is_enemy_visible(player_team, u.id):
                    continue
            col = config.TEAM_COLORS.get(u.team, (220, 220, 220))
            r = 3 if isinstance(u, Pokemon) else 1
            pygame.draw.circle(surface, col, self._m(u.pos.x, u.pos.y), r)
        # Giocatore evidenziato.
        if player is not None and player.alive:
            pygame.draw.circle(surface, (255, 255, 255), self._m(player.pos.x, player.pos.y), 3, 1)
        # Riquadro della camera.
        ts = config.TILE_SIZE
        vx = camera.x / ts
        vy = camera.y / ts
        vw = camera.view_w / ts
        vh = camera.view_h / ts
        cam_rect = pygame.Rect(self._m(vx, vy), (int(vw * self.scale), int(vh * self.scale)))
        pygame.draw.rect(surface, (235, 235, 235), cam_rect, 1)
        pygame.draw.rect(surface, (120, 120, 130), self.rect, 1)
