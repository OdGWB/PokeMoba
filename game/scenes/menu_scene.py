"""Menu iniziale: scelta della MAPPA (3v3 / 5v5), poi selezione del personaggio.

In basso restano le partite LAN: [H] ospita (host), [J] unisciti (IP).
"""
from __future__ import annotations

import socket

import pygame

import config
from engine import grid as G
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


class MenuScene:
    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self.mode = "menu"          # "menu" | "enter_ip"
        self.ip_text = "127.0.0.1"
        self.map_index = 0          # 0 = 3v3, 1 = 5v5
        self._thumbs = [map_thumbnail(str(app.root / p)) for _, p in config.MAPS]
        self._cards: list = []
        self._fonts = {}

    def handle_events(self, events):
        for ev in events:
            if self.mode == "menu":
                if ev.type == pygame.MOUSEMOTION:
                    for r, i in self._cards:
                        if r.collidepoint(ev.pos):
                            self.map_index = i
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    for r, i in self._cards:
                        if r.collidepoint(ev.pos):
                            self.map_index = i
                            self._single()
                if ev.type != pygame.KEYDOWN:
                    continue
                if ev.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d,
                              pygame.K_m):
                    step = -1 if ev.key in (pygame.K_LEFT, pygame.K_a) else 1
                    self.map_index = (self.map_index + step) % len(config.MAPS)
                elif ev.key in (pygame.K_1, pygame.K_2) and ev.key - pygame.K_1 < len(config.MAPS):
                    self.map_index = ev.key - pygame.K_1
                    self._single()
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self._single()
                elif ev.key == pygame.K_h:
                    self._host()
                elif ev.key == pygame.K_j:
                    self.mode = "enter_ip"
                elif ev.key == pygame.K_ESCAPE:
                    self.quit_app = True
            elif self.mode == "enter_ip" and ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_RETURN:
                    self._join(self.ip_text.strip())
                elif ev.key == pygame.K_ESCAPE:
                    self.mode = "menu"
                elif ev.key == pygame.K_BACKSPACE:
                    self.ip_text = self.ip_text[:-1]
                elif ev.unicode and (ev.unicode.isdigit() or ev.unicode in ".:"):
                    self.ip_text += ev.unicode

    def fixed_update(self):
        pass

    def update(self, dt):
        pass

    # --- costruzione scene ---------------------------------------------------
    def _single(self):
        from .char_select_scene import CharSelectScene
        self.next_scene = CharSelectScene(self.app, self.map_index)

    def _host(self):
        from net.server import GameServer
        from net.client import GameClient
        from .lobby_scene import LobbyScene
        server = GameServer(port=config.DEFAULT_PORT)
        server.start()
        client = GameClient("127.0.0.1", config.DEFAULT_PORT)
        client.send_hello(socket.gethostname()[:16] or "Host")
        self.app.server = server
        self.next_scene = LobbyScene(self.app, client, server=server, is_host=True,
                                     init_map_index=self.map_index)

    def _join(self, ip):
        from net.client import GameClient
        from .lobby_scene import LobbyScene
        client = GameClient(ip, config.DEFAULT_PORT)
        client.send_hello(socket.gethostname()[:16] or "Ospite")
        self.next_scene = LobbyScene(self.app, client, is_host=False)

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = pygame.font.SysFont("consolas", size, bold=bold)
        return self._fonts[key]

    def draw_fullres(self, surface, font):
        W, H = surface.get_size()
        surface.fill(BG)
        title_f = self._font(max(30, H // 14), bold=True)
        big = self._font(max(22, H // 26), bold=True)
        small = self._font(max(13, H // 50))
        t = title_f.render("PokrLOL", True, GOLD)
        surface.blit(t, (W // 2 - t.get_width() // 2, H // 14))

        if self.mode == "enter_ip":
            cx = W // 2 - 170
            surface.blit(big.render("IP dell'host:", True, TEXT), (cx, H // 3))
            surface.blit(big.render(self.ip_text + "_", True, (255, 255, 255)),
                         (cx, H // 3 + 50))
            surface.blit(small.render("INVIO = unisciti    ESC = indietro", True, DIM),
                         (cx, H // 3 + 110))
            return

        s = small.render("Scegli la mappa  (clic, frecce + Invio, oppure 1 / 2)", True, DIM)
        surface.blit(s, (W // 2 - s.get_width() // 2, H // 14 + t.get_height() + 8))

        n = len(config.MAPS)
        cw = min(int(W * 0.36), int(H * 0.52))
        gap = int(W * 0.05)
        x0 = W // 2 - (n * cw + (n - 1) * gap) // 2
        y0 = int(H * 0.26)
        ch = int(cw * 1.12)
        self._cards = []
        for i, (name, _) in enumerate(config.MAPS):
            r = pygame.Rect(x0 + i * (cw + gap), y0, cw, ch)
            self._cards.append((r, i))
            on = i == self.map_index
            pygame.draw.rect(surface, PANEL_HI if on else PANEL, r, border_radius=8)
            pygame.draw.rect(surface, GOLD if on else BORDER, r, 3 if on else 1, border_radius=8)
            side = int(cw * 0.8)
            th = pygame.transform.scale(self._thumbs[i], (side, side))
            surface.blit(th, (r.centerx - side // 2, r.y + int(cw * 0.08)))
            nm = big.render(name, True, TEXT if on else (200, 205, 198))
            surface.blit(nm, (r.centerx - nm.get_width() // 2, r.y + int(cw * 0.08) + side + 8))
            info = small.render(MAP_INFO.get(name, ""), True, DIM)
            surface.blit(info, (r.centerx - info.get_width() // 2,
                                r.y + int(cw * 0.08) + side + 12 + nm.get_height()))

        try:
            ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip = "?"
        lan = small.render(f"LAN:  [H] ospita partita   [J] unisciti (IP)      "
                           f"il tuo IP: {ip}  porta {config.DEFAULT_PORT}      [Esc] esci",
                           True, DIM)
        surface.blit(lan, (W // 2 - lan.get_width() // 2, H - lan.get_height() - H // 24))
