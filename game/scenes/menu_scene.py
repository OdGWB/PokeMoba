"""Menu principale di PokéMoba: titolo e otto voci (redesign).

Gioca (mappa, offline / online / LAN: play_scene.py), Allenamento (mappa
piccola coi manichini + Tutorial: training_select_scene.py), Enciclopedia
(mosse e passive di ogni linea: encyclopedia_scene.py), Personalizzazione
(nickname e immagine profilo), Crediti, Tier list, Opzioni ed Esci. L'editor delle animazioni
(anim_editor_scene.py) non e' piu' nel menu: data/anim_overrides.json resta. Frecce + Invio o
clic. In alto a destra il profilo (clic = Personalizzazione). Sfondo:
assets/ui/menu_bg.png con un velo scuro a sinistra, dove sta il menu.
Qui restano anche i colori e la miniatura delle mappe, usati dalla
schermata Gioca.
"""
from __future__ import annotations

import pygame

import config
from engine import grid as G
from engine.content import load_map
from .. import ui_theme as UI

# Colori storici: li importano anche le altre schermate.
BG = UI.BG
PANEL = UI.PANEL
PANEL_HI = UI.PANEL_HI
BORDER = UI.BORDER
GOLD = UI.GOLD
TEXT = UI.TEXT
DIM = UI.DIM

MENU_BG = "assets/ui/menu_bg.png"

# Colori della miniatura della mappa (stessa palette cupa della giungla).
THUMB = {
    G.TILE_FLOOR: (46, 74, 51), G.TILE_WALL: (18, 40, 26), G.TILE_LANE: (122, 108, 84),
    G.TILE_RIVER: (52, 98, 120), G.TILE_BUSH: (47, 125, 91),
    G.TILE_JUNGLE_WALL: (24, 52, 32),
}
MAP_INFO = {"3v3": "3 lane · squadre da 3", "5v5": "3 lane · squadre da 5 · mappa grande"}


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


ENTRIES = [("Gioca", "play"), ("Allenamento", "train"), ("Enciclopedia", "encyclopedia"),
           ("Personalizzazione", "profile"), ("Crediti", "credits"),
           ("Tier list", "tier"), ("Opzioni", "options"),
           ("Esci", "quit")]
NOTES = {"train": "e tutorial", "encyclopedia": "mosse e passive"}


class MenuScene:
    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self.sel = 0
        self.t = 0.0
        self._rects: list = []
        self._profile_rect = None

    # --- input -----------------------------------------------------------------
    def handle_events(self, events):
        for ev in events:
            if ev.type == pygame.MOUSEMOTION:
                for r, i in self._rects:
                    if r.collidepoint(ev.pos):
                        self.sel = i
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self._profile_rect and self._profile_rect.collidepoint(ev.pos):
                    self._activate("profile")
                    continue
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
        elif key == "train":
            from .training_select_scene import TrainingSelectScene
            self.next_scene = TrainingSelectScene(self.app)
        elif key == "encyclopedia":
            from .encyclopedia_scene import EncyclopediaScene
            self.next_scene = EncyclopediaScene(self.app)
        elif key == "profile":
            from .profile_scene import ProfileScene
            self.next_scene = ProfileScene(self.app)
        elif key == "credits":
            from .credits_scene import CreditsScene
            self.next_scene = CreditsScene(self.app)
        elif key == "tier":
            from .tier_scene import TierChoiceScene
            self.next_scene = TierChoiceScene(self.app)
        elif key == "options":
            from .options_scene import OptionsScene
            self.next_scene = OptionsScene(self.app)
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

    # --- disegno ------------------------------------------------------------------
    def draw_fullres(self, surface, font):
        W, H = surface.get_size()
        k = H / 720                       # tutto è pensato a 1280x720 e scalato
        if not UI.menu_backdrop(surface, MENU_BG, W, H, 0.6, 0.72):
            surface.fill(BG)
            UI.top_glow(surface, W, H)

        x0 = int(96 * k)
        r = UI.title(surface, "PokéMoba", x0, int(92 * k), max(48, int(80 * k)), shadow=max(2, int(4 * k)))
        sub = UI.font(max(12, int(14 * k))).render(
            "il MOBA dei Pokémon · giungla, lane e campi neutrali", True, DIM)
        surface.blit(sub, (x0 + 4, r.bottom + int(8 * k)))

        # Voci: "Gioca" più grande, poi le altre; Esci separata da una linea.
        bw = int(340 * k)
        y = int(236 * k)
        mx = int(92 * k)
        self._rects = []
        for i, (label, key) in enumerate(ENTRIES):
            if key == "quit":
                y += int(10 * k)
                pygame.draw.line(surface, UI.LINE, (mx + int(18 * k), y), (mx + bw - int(18 * k), y))
                y += int(11 * k)
            bh = int((56 if i == 0 else 38) * k)
            rr = pygame.Rect(mx, y, bw, bh)
            self._rects.append((rr, i))
            on = i == self.sel
            if on:
                UI.alpha_rect(surface, (*GOLD, 26), rr, radius=8)
            size = 22 if i == 0 else 15 if key == "quit" else 16
            col = GOLD if on else (DIM if key == "quit" else TEXT if i == 0 else UI.SOFT)
            t = UI.font(max(13, int(size * k)), bold=True).render(label, True, col)
            tx = rr.x + int(40 * k)
            surface.blit(t, (tx, rr.centery - t.get_height() // 2))
            if on:      # piccolo triangolo fermo, niente animazione
                cy = rr.centery
                ax = rr.x + int(18 * k)
                s = max(4, int(5 * k))
                pygame.draw.polygon(surface, GOLD, [(ax, cy - s), (ax + s + 1, cy), (ax, cy + s)])
            note = NOTES.get(key)
            if note:
                n = UI.font(max(10, int(11 * k))).render(note, True, DIM)
                surface.blit(n, (rr.right - int(18 * k) - n.get_width(), rr.centery - n.get_height() // 2))
            y += bh + int(4 * k)

        self._profile_rect = UI.profile_chip(surface, self.app, W, y=int(28 * k), right=int(40 * k))
        UI.hints(surface, [("↑↓", "scegli"), ("Invio", "apri"), ("F11", "schermo intero")],
                 x0, H - int(32 * k) - 22)
