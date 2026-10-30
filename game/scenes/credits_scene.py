"""Crediti (menu, tasto C): da dove vengono sprite, ritratti e librerie.

Le stesse informazioni stanno in CREDITS.md; gli autori dei ritratti profilo
si leggono da assets/avatars/credits.json (scritto da tools/fetch_avatars.py).
Rotellina / frecce / PagSu-PagGiu per scorrere, ESC o INVIO per tornare.
"""
from __future__ import annotations

import pygame

from .. import avatars as A
from .online_lobby_scene import BG, DIM, GOLD, TEXT, font

# (stile, testo): "h" titolo di sezione, "t" testo, "d" testo tenue, "" riga vuota
INTRO = [
    ("h", "Sprite dei Pokémon in partita"),
    ("t", "PMD Sprite Collab - https://sprites.pmdcollab.org/"),
    ("d", "Repository: github.com/PMDCollab/SpriteCollab - licenza CC BY-NC 4.0"),
    ("d", "Opera degli artisti della community PMD Sprite Collab."),
    ("", ""),
    ("h", "Immagini profilo (ritratti \"Normal\" dei leggendari)"),
    ("t", "PMD Sprite Collab - https://sprites.pmdcollab.org/ - licenza CC BY-NC 4.0"),
    ("d", "CHUNSOFT = ritratti originali di Pokémon Mystery Dungeon (Spike Chunsoft)."),
]
OUTRO = [
    ("", ""),
    ("h", "Pokémon"),
    ("t", "Pokémon, nomi e personaggi (c) Nintendo / Game Freak / The Pokémon Company."),
    ("d", "Progetto amatoriale, gratuito e non ufficiale, senza scopo di lucro."),
    ("", ""),
    ("h", "Icone degli oggetti"),
    ("t", "Sprite degli strumenti dei giochi Pokémon (c) The Pokémon Company"),
    ("d", "(Nintendo / Game Freak / Creatures)."),
    ("t", "Raccolta PokeAPI/sprites - https://github.com/PokeAPI/sprites (sprites/items)"),
    ("d", "Repository CC0 1.0; i diritti sulle immagini restano di The Pokémon Company."),
    ("", ""),
    ("h", "Software"),
    ("t", "pygame (LGPL) - https://www.pygame.org/"),
    ("t", "aiortc (BSD) - https://github.com/aiortc/aiortc  (multiplayer online WebRTC)"),
]


def credit_lines():
    lines = list(INTRO)
    credits = A.load_credits()
    for dex, name in A.AVATARS:
        c = credits.get(f"{dex:04d}")
        if c:
            lines.append(("t", f"  #{dex:<4} {name:<12} {', '.join(c['authors'])}"))
    return lines + OUTRO


class CreditsScene:
    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self.lines = credit_lines()
        self.scroll = 0
        self._max = 0

    def handle_events(self, events):
        for ev in events:
            if ev.type == pygame.MOUSEWHEEL:
                self.scroll -= ev.y * 3
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_c):
                    from .menu_scene import MenuScene
                    self.next_scene = MenuScene(self.app)
                elif ev.key in (pygame.K_DOWN, pygame.K_s):
                    self.scroll += 1
                elif ev.key in (pygame.K_UP, pygame.K_w):
                    self.scroll -= 1
                elif ev.key == pygame.K_PAGEDOWN:
                    self.scroll += 15
                elif ev.key == pygame.K_PAGEUP:
                    self.scroll -= 15
            self.scroll = max(0, min(self.scroll, self._max))

    def fixed_update(self):
        pass

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def draw_fullres(self, surface, f):
        W, H = surface.get_size()
        surface.fill(BG)
        big = font(max(26, H // 22), True)
        h = font(max(16, H // 42), True)
        t = font(max(13, H // 54))
        title = big.render("Crediti", True, GOLD)
        surface.blit(title, (W // 2 - title.get_width() // 2, int(H * 0.04)))
        top = int(H * 0.04) + title.get_height() + 16
        bottom = H - 40
        step = t.get_height() + 4
        visible = max(1, (bottom - top) // step)
        self._max = max(0, len(self.lines) - visible)
        self.scroll = min(self.scroll, self._max)
        x = int(W * 0.08)
        y = top
        for style, text in self.lines[self.scroll:self.scroll + visible]:
            if style == "h":
                surface.blit(h.render(text, True, GOLD), (x, y))
            elif style:
                surface.blit(t.render(text, True, TEXT if style == "t" else DIM), (x, y))
            y += step
        hint = t.render("rotellina / frecce: scorri      ESC: torna al menu", True, DIM)
        surface.blit(hint, (W // 2 - hint.get_width() // 2, H - hint.get_height() - 12))
