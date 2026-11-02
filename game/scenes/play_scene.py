"""Schermata GIOCA: da qui si sceglie come giocare.

- Offline: clic su una mappa (o 1 / 2, frecce + Invio) -> scelta del personaggio.
- Online (amici via Internet, codici scambiati a mano): ospita / unisciti.
- LAN: ospita / unisciti (IP).
ESC torna al menu principale.
"""
from __future__ import annotations

import socket

import pygame

import config
from .menu_scene import (BG, BORDER, DIM, GOLD, PANEL, PANEL_HI, TEXT, MAP_INFO,
                         map_thumbnail)
from .online_lobby_scene import Buttons


class PlayScene:
    def __init__(self, app, map_index=0):
        self.app = app
        self.next_scene = None
        self.mode = "menu"          # "menu" | "enter_ip"
        self.ip_text = "127.0.0.1"
        self.map_index = map_index  # 0 = 3v3, 1 = 5v5
        self._thumbs = [map_thumbnail(str(app.root / p)) for _, p in config.MAPS]
        self._cards: list = []
        self._fonts = {}
        self.buttons = Buttons()

    # --- input ----------------------------------------------------------------
    def handle_events(self, events):
        for ev in events:
            if self.mode == "menu":
                if ev.type == pygame.MOUSEMOTION:
                    for r, i in self._cards:
                        if r.collidepoint(ev.pos):
                            self.map_index = i
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if self.buttons.click(ev.pos):
                        continue
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
                elif ev.key == pygame.K_o:
                    self._online_host()
                elif ev.key == pygame.K_u:
                    self._online_join()
                elif ev.key == pygame.K_ESCAPE:
                    self._back()
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

    # --- costruzione scene ---------------------------------------------------------
    def _back(self):
        from .menu_scene import MenuScene
        self.next_scene = MenuScene(self.app)

    def _single(self):
        from .char_select_scene import CharSelectScene
        self.next_scene = CharSelectScene(self.app, self.map_index)

    def _online_host(self):
        from .online_lobby_scene import OnlineHostLobbyScene
        self.next_scene = OnlineHostLobbyScene(self.app, self.map_index)

    def _online_join(self):
        from .online_lobby_scene import OnlineJoinScene
        self.next_scene = OnlineJoinScene(self.app)

    def _ask_ip(self):
        self.mode = "enter_ip"

    def _host(self):
        from net.lan.server import GameServer
        from net.lan.client import GameClient
        from .lobby_scene import LobbyScene
        server = GameServer(port=config.DEFAULT_PORT)
        server.start()
        client = GameClient("127.0.0.1", config.DEFAULT_PORT)
        client.send_hello(self._nick("Host"))
        self.app.server = server
        self.next_scene = LobbyScene(self.app, client, server=server, is_host=True,
                                     init_map_index=self.map_index)

    def _join(self, ip):
        from net.lan.client import GameClient
        from .lobby_scene import LobbyScene
        client = GameClient(ip, config.DEFAULT_PORT)
        client.send_hello(self._nick("Ospite"))
        self.next_scene = LobbyScene(self.app, client, is_host=False)

    def _nick(self, default):
        prof = getattr(self.app, "profile", None)
        return prof["name"] if prof else (socket.gethostname()[:16] or default)

    # --- disegno -------------------------------------------------------------------------
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
        self.buttons.clear()
        title_f = self._font(max(30, H // 16), bold=True)
        big = self._font(max(22, H // 26), bold=True)
        small = self._font(max(13, H // 50))
        t = title_f.render("Gioca", True, GOLD)
        surface.blit(t, (W // 2 - t.get_width() // 2, H // 20))

        if self.mode == "enter_ip":
            cx = W // 2 - 170
            surface.blit(big.render("IP dell'host:", True, TEXT), (cx, H // 3))
            surface.blit(big.render(self.ip_text + "_", True, (255, 255, 255)),
                         (cx, H // 3 + 50))
            surface.blit(small.render("INVIO = unisciti    ESC = indietro", True, DIM),
                         (cx, H // 3 + 110))
            return

        s = small.render("PARTITA OFFLINE: scegli la mappa (clic, frecce + Invio, oppure 1 / 2)",
                         True, DIM)
        surface.blit(s, (W // 2 - s.get_width() // 2, H // 20 + t.get_height() + 6))

        n = len(config.MAPS)
        cw = min(int(W * 0.30), int(H * 0.44))
        gap = int(W * 0.05)
        x0 = W // 2 - (n * cw + (n - 1) * gap) // 2
        y0 = int(H * 0.20)
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

        # Online / LAN: pulsanti cliccabili (le scorciatoie da tastiera restano).
        by = y0 + ch + int(H * 0.04)
        bh = small.get_height() + 16
        bw = int(W * 0.20)
        g = int(W * 0.015)
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip = "?"
        rows = [("ONLINE", "Ospita  [O]", self._online_host, "Unisciti  [U]", self._online_join),
                ("LAN", "Ospita  [H]", self._host, "Unisciti (IP)  [J]", self._ask_ip)]
        for k, (lab, l1, a1, l2, a2) in enumerate(rows):
            y = by + k * (bh + 10)
            lt = small.render(lab, True, GOLD if k == 0 else DIM)
            lx = W // 2 - bw - g // 2 - lt.get_width() - g
            surface.blit(lt, (max(10, lx), y + (bh - lt.get_height()) // 2))
            self.buttons.draw(surface, (W // 2 - bw - g // 2, y, bw, bh), l1, a1, small)
            self.buttons.draw(surface, (W // 2 + g // 2, y, bw, bh), l2, a2, small)
        foot = small.render(f"online: amici via Internet, codici su Discord/WhatsApp      "
                            f"LAN: il tuo IP {ip}, porta {config.DEFAULT_PORT}", True, DIM)
        surface.blit(foot, (W // 2 - foot.get_width() // 2, by + 2 * (bh + 10) + 4))
        self.buttons.draw(surface, (20, H - bh - 16, int(W * 0.14), bh), "Indietro  (Esc)",
                          self._back, small)
