"""Menu principale di PokéMoba: titolo e cinque voci.

Gioca (mappa, offline / online / LAN: play_scene.py), Personalizzazione
(nickname e immagine profilo), Crediti, Tier list ed Esci. Frecce + Invio o
clic. In alto a destra il profilo. Qui restano anche i colori e la miniatura
delle mappe, usati dalla schermata Gioca.
"""
from __future__ import annotations

import math

import pygame

import config
from engine import grid as G
from .. import avatars as A
from engine.content import load_map

BG = (14, 20, 17)
PANEL = (24, 34, 29)
PANEL_HI = (38, 56, 44)
BORDER = (60, 84, 66)
GOLD = (235, 210, 90)
TEXT = (230, 232, 225)
DIM = (150, 160, 150)

# Colori della miniatura della mappa (stessa palette cupa della giungla).
THUMB = {
    G.TILE_FLOOR: (46, 74, 51), G.TILE_WALL: (18, 40, 26), G.TILE_LANE: (122, 108, 84),
    G.TILE_RIVER: (52, 98, 120), G.TILE_BUSH: (47, 125, 91),
    G.TILE_JUNGLE_WALL: (24, 52, 32),
}
MAP_INFO = {"3v3": "3 lane, squadre da 3", "5v5": "3 lane, squadre da 5, mappa più grande"}


def map_thumbnail(path):
    """Miniatura pixel-art della mappa (1 px per tile) con le basi delle squadre."""
    md = load_map(path)
    g = md.grid
    img = pygame.Surface((g.width, g.height))
    img.fill(THUMB[G.TILE_FLOOR])
    for y in range(g.height):
        row = g.tiles[y]
        for x in range(g.width):
            c = THUMB.get(row[x])
            if c is not None and row[x] != G.TILE_FLOOR:
                img.set_at((x, y), c)
    for team in (0, 1):
        sp = md.spawns.get(f"team{team}")
        if sp:
            pygame.draw.circle(img, config.TEAM_COLORS[team], (int(sp[0]), int(sp[1])),
                               max(2, g.width // 30))
    return img


ENTRIES = [("Gioca", "play"), ("Personalizzazione", "profile"), ("Crediti", "credits"),
           ("Tier list", "tier"), ("Esci", "quit")]


class MenuScene:
    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self.sel = 0
        self.t = 0.0
        self._rects: list = []
        self._fonts = {}

    # --- input -----------------------------------------------------------------
    def handle_events(self, events):
        for ev in events:
            if ev.type == pygame.MOUSEMOTION:
                for r, i in self._rects:
                    if r.collidepoint(ev.pos):
                        self.sel = i
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for r, i in self._rects:
                    if r.collidepoint(ev.pos):
                        self.sel = i
                        self._activate(ENTRIES[i][1])
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_DOWN, pygame.K_s):
                    self.sel = (self.sel + 1) % len(ENTRIES)
                elif ev.key in (pygame.K_UP, pygame.K_w):
                    self.sel = (self.sel - 1) % len(ENTRIES)
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self._activate(ENTRIES[self.sel][1])
                elif ev.key == pygame.K_ESCAPE:
                    self.quit_app = True

    def _activate(self, key):
        if key == "play":
            from .play_scene import PlayScene
            self.next_scene = PlayScene(self.app)
        elif key == "profile":
            from .profile_scene import ProfileScene
            self.next_scene = ProfileScene(self.app)
        elif key == "credits":
            from .credits_scene import CreditsScene
            self.next_scene = CreditsScene(self.app)
        elif key == "tier":
            from .tier_scene import TierChoiceScene
            self.next_scene = TierChoiceScene(self.app)
        elif key == "quit":
            self.quit_app = True

    def fixed_update(self):
        pass

    def update(self, dt):
        self.t += dt

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = pygame.font.SysFont("consolas", size, bold=bold)
        return self._fonts[key]

    # --- disegno ------------------------------------------------------------------
    def draw_fullres(self, surface, font):
        W, H = surface.get_size()
        surface.fill(BG)
        # Fascia di luce calda dietro il titolo (luce alto-sinistra, giungla cupa).
        glow = pygame.Surface((W, int(H * 0.42)), pygame.SRCALPHA)
        for i in range(glow.get_height()):
            a = int(60 * (1 - i / glow.get_height()) ** 2)
            pygame.draw.line(glow, (60, 90, 60, a), (0, i), (W, i))
        surface.blit(glow, (0, 0))

        title_f = self._font(max(48, H // 7), bold=True)
        tx = W // 2
        ty = int(H * 0.10)
        title = "PokéMoba"
        sh = title_f.render(title, True, (8, 12, 10))
        for dx, dy in ((6, 6), (4, 4), (2, 2)):
            surface.blit(sh, (tx - sh.get_width() // 2 + dx, ty + dy))
        out = title_f.render(title, True, (60, 46, 10))
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            surface.blit(out, (tx - out.get_width() // 2 + dx, ty + dy))
        surface.blit(title_f.render(title, True, GOLD), (tx - sh.get_width() // 2, ty))
        sub = self._font(max(14, H // 48)).render(
            "il MOBA dei Pokémon  -  giungla, lane e campi neutrali", True, DIM)
        surface.blit(sub, (tx - sub.get_width() // 2, ty + sh.get_height() + 4))

        bf = self._font(max(22, H // 26), bold=True)
        bw, bh = min(int(W * 0.34), 460), max(44, H // 12)
        gap = max(10, H // 70)
        y0 = int(H * 0.38)
        self._rects = []
        for i, (label, key) in enumerate(ENTRIES):
            r = pygame.Rect(tx - bw // 2, y0 + i * (bh + gap), bw, bh)
            self._rects.append((r, i))
            on = i == self.sel
            pygame.draw.rect(surface, PANEL_HI if on else PANEL, r, border_radius=8)
            pygame.draw.rect(surface, GOLD if on else BORDER, r, 3 if on else 1, border_radius=8)
            txt = bf.render(label, True, GOLD if on else TEXT)
            surface.blit(txt, (r.centerx - txt.get_width() // 2,
                               r.centery - txt.get_height() // 2))
            if on:      # frecce che pulsano ai lati
                k = 4 + int(3 * (1 + math.sin(self.t * 5)))
                cy = r.centery
                lx, rx = r.x - 24 - k, r.right + 24 + k
                pygame.draw.polygon(surface, GOLD, [(lx, cy - 8), (lx + 12, cy), (lx, cy + 8)])
                pygame.draw.polygon(surface, GOLD, [(rx, cy - 8), (rx - 12, cy), (rx, cy + 8)])
        small = self._font(max(13, H // 56))
        self._draw_profile(surface, W, H, small)
        hint = small.render("frecce + Invio, oppure clic        F11: schermo intero", True, DIM)
        surface.blit(hint, (W // 2 - hint.get_width() // 2, H - hint.get_height() - 12))

    def _draw_profile(self, surface, W, H, small):
        """In alto a destra: immagine profilo + nickname."""
        prof = getattr(self.app, "profile", None) or {}
        side = max(40, (H // 12) // 40 * 40)
        r = pygame.Rect(W - side - 24, 20, side, side)
        A.draw_avatar(surface, prof.get("avatar", 0), r, GOLD)
        nm = small.render(prof.get("name", "?"), True, TEXT)
        surface.blit(nm, (r.x - nm.get_width() - 12, r.centery - nm.get_height() // 2))
