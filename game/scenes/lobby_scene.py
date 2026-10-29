"""Lobby di rete: mostra i giocatori connessi e la propria scelta.

Comandi: T = cambia squadra, , / . = cambia Pokémon, SPAZIO = pronto/non pronto.
Quando tutti sono pronti il server avvia la partita (le lane libere sono
riempite da bot). I Pokémon mancanti sono riempiti da bot.
"""
from __future__ import annotations

import pygame

import config
from .net_match_scene import NetMatchScene

def _roster_names() -> list[str]:
    """Nomi del roster letti dai JSON (stesso ordine di config.ROSTER)."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    out = []
    for rel in config.ROSTER:
        try:
            out.append(json.loads((root / rel).read_text(encoding="utf-8")).get("name", "?"))
        except (OSError, ValueError):
            out.append("?")
    return out


ROSTER_NAMES = _roster_names()


class LobbyScene:
    def __init__(self, app, client, server=None, is_host=False, init_map_index=0):
        self.app = app
        self.client = client
        self.server = server
        self.is_host = is_host
        self.next_scene = None
        self.team = 0
        self.pokemon = 0
        self.ready = False
        self.map_index = init_map_index
        self._sent = False

    def _send(self):
        self.client.send_lobby(self.team, self.pokemon, self.ready, self.map_index)

    def handle_events(self, events):
        for ev in events:
            if ev.type != pygame.KEYDOWN:
                continue
            if ev.key == pygame.K_ESCAPE:
                self.client.close()
                if self.server is not None:
                    self.server.stop()
                from .menu_scene import MenuScene
                self.next_scene = MenuScene(self.app)
            elif ev.key == pygame.K_t:
                self.team ^= 1; self._send()
            elif ev.key == pygame.K_COMMA:
                self.pokemon = (self.pokemon - 1) % len(config.ROSTER); self._send()
            elif ev.key == pygame.K_PERIOD:
                self.pokemon = (self.pokemon + 1) % len(config.ROSTER); self._send()
            elif ev.key == pygame.K_m and self.is_host:
                self.map_index = (self.map_index + 1) % len(config.MAPS); self._send()
            elif ev.key == pygame.K_SPACE:
                self.ready = not self.ready; self._send()

    def fixed_update(self):
        pass

    def update(self, dt):
        self.client.poll()
        if not self._sent:
            self._send(); self._sent = True
        if self.client.start_info is not None:
            self.next_scene = NetMatchScene(self.app, self.client, self.client.start_info)

    def draw(self, surface):
        surface.fill((20, 24, 30))

    def hud_lines(self):
        return []

    def draw_fullres(self, surface, font):
        big = pygame.font.SysFont("consolas", 22, bold=True)
        x, y = 40, 40
        surface.blit(big.render("LOBBY", True, (255, 230, 120)), (x, y)); y += 40
        role = "HOST" if self.is_host else "OSPITE"
        mapname = config.MAPS[self.client.lobby_map][0] if self.client.lobby_map < len(config.MAPS) else "?"
        hint = "  (M = cambia mappa)" if self.is_host else ""
        surface.blit(font.render(f"[{role}]  id: {self.client.client_id}   Mappa: {mapname}{hint}",
                                 True, (200, 200, 210)), (x, y)); y += 30
        surface.blit(font.render("Giocatori connessi:", True, (220, 220, 230)), (x, y)); y += 26
        for p in self.client.lobby:
            col = config.TEAM_COLORS[p["team"]]
            tag = "PRONTO" if p["ready"] else "..."
            poke = ROSTER_NAMES[p["pokemon"]] if p["pokemon"] < len(ROSTER_NAMES) else "?"
            line = f"  {p['name']}  -  squadra {'BLU' if p['team']==0 else 'ROSSO'}  -  {poke}  [{tag}]"
            surface.blit(font.render(line, True, col), (x, y)); y += 24
        y += 20
        surface.blit(font.render("La tua scelta:", True, (220, 220, 230)), (x, y)); y += 26
        mine = (f"  Squadra: {'BLU' if self.team==0 else 'ROSSO'}   "
                f"Pokemon: {ROSTER_NAMES[self.pokemon]}   "
                f"Stato: {'PRONTO' if self.ready else 'non pronto'}")
        surface.blit(font.render(mine, True, (240, 240, 240)), (x, y)); y += 40
        surface.blit(font.render("T = squadra    , / . = Pokemon    SPAZIO = pronto", True, (170, 170, 180)), (x, y)); y += 24
        surface.blit(font.render("La partita parte quando tutti sono pronti.", True, (170, 170, 180)), (x, y))
