"""Menu iniziale: giocatore singolo, ospita (host) o unisciti (join via IP)."""
from __future__ import annotations

import socket

import pygame

import config


class MenuScene:
    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self.mode = "menu"          # "menu" | "enter_ip"
        self.ip_text = "127.0.0.1"
        self.map_index = 0          # 0 = 3v3, 1 = 5v5

    def handle_events(self, events):
        for ev in events:
            if ev.type != pygame.KEYDOWN:
                continue
            if self.mode == "menu":
                if ev.key == pygame.K_1:
                    self._single()
                elif ev.key == pygame.K_2:
                    self._host()
                elif ev.key == pygame.K_3:
                    self.mode = "enter_ip"
                elif ev.key == pygame.K_m:
                    self.map_index = (self.map_index + 1) % len(config.MAPS)
                elif ev.key == pygame.K_ESCAPE:
                    self.quit_app = True
            elif self.mode == "enter_ip":
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
        from .match_scene import MatchScene
        self.next_scene = MatchScene(str(self.app.root / config.MAPS[self.map_index][1]),
                                     str(self.app.root / "data/pokemon/charmander.json"))

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
        surface.fill((16, 18, 24))

    def hud_lines(self):
        return []

    def draw_fullres(self, surface, font):
        big = pygame.font.SysFont("consolas", 28, bold=True)
        W, _ = surface.get_size()
        cx = W // 2
        surface.blit(big.render("PokrLOL", True, (255, 230, 120)), (cx - 70, 120))
        if self.mode == "menu":
            mode_name = config.MAPS[self.map_index][0]
            surface.blit(font.render(f"Modalita: {mode_name}      [M] per cambiare (3v3 / 5v5)",
                                     True, (255, 230, 120)), (cx - 170, 185))
            opts = ["[1]  Giocatore singolo (vs bot)",
                    "[2]  Ospita partita LAN (host)",
                    "[3]  Unisciti a partita LAN (inserisci IP)"]
            for i, o in enumerate(opts):
                surface.blit(font.render(o, True, (230, 230, 235)), (cx - 170, 225 + i * 36))
            # Mostra il proprio IP locale per comodità dell'host.
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except OSError:
                ip = "?"
            surface.blit(font.render(f"Il tuo IP locale: {ip}   porta: {config.DEFAULT_PORT}",
                                     True, (150, 150, 160)), (cx - 170, 360))
        else:
            surface.blit(font.render("IP dell'host:", True, (230, 230, 235)), (cx - 170, 240))
            box = font.render(self.ip_text + "_", True, (255, 255, 255))
            surface.blit(box, (cx - 170, 270))
            surface.blit(font.render("INVIO = unisciti    ESC = indietro", True, (170, 170, 180)),
                         (cx - 170, 320))
