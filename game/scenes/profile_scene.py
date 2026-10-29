"""Profilo del giocatore: NICKNAME (come ti vedono gli altri) e IMMAGINE PROFILO.

Compare al PRIMO avvio (non c'è ancora un profilo salvato) e dal menu col
tasto P. L'immagine si sceglie fra i ritratti "Normal" dei leggendari di
PMD Sprite Collab (game/avatars.py); la si vede accanto al nome nella scelta
del personaggio e nelle lobby online. Il profilo resta salvato sul PC.

Comandi: scrivi il nome, clic o frecce per l'immagine, INVIO salva,
ESC annulla (non al primo avvio: lì il profilo serve).
"""
from __future__ import annotations

import random

import pygame

from .. import avatars as A
from .online_lobby_scene import BG, BORDER, DIM, GOLD, RED, TEXT, Buttons, TextField, font


class ProfileScene:
    def __init__(self, app, first=False):
        self.app = app
        self.first = first
        self.next_scene = None
        self.items = A.available()
        prof = getattr(app, "profile", None) or {}
        self.field = TextField("il tuo nickname", limit=A.NAME_MAX)
        self.field.text = prof.get("name", "")
        self.field.focused = True
        dexes = [d for d, _ in self.items]
        cur = prof.get("avatar", 0)
        if cur in dexes:
            self.index = dexes.index(cur)
        else:
            self.index = random.randrange(len(dexes)) if dexes else 0
        self.hover = None
        self.error = ""
        self.buttons = Buttons()
        self._cells: list = []
        self._credits = A.load_credits()

    # --- input ------------------------------------------------------------------------
    def handle_events(self, events):
        for ev in events:
            # Frecce ed ESC prima del campo: il campo, sempre a fuoco, li mangerebbe.
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                if not self.first:
                    self._back()
                continue
            if ev.type == pygame.KEYDOWN and self.items:
                cols = self._cols
                step = {pygame.K_LEFT: -1, pygame.K_RIGHT: 1,
                        pygame.K_UP: -cols, pygame.K_DOWN: cols}.get(ev.key)
                if step is not None:
                    self.index = max(0, min(len(self.items) - 1, self.index + step))
                    continue
            if self.field.handle_event(ev) == "submit":
                self._save()
                continue
            if ev.type == pygame.MOUSEMOTION:
                self.hover = next((i for c, i in self._cells if c.collidepoint(ev.pos)), None)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self.buttons.click(ev.pos):
                    continue
                for c, i in self._cells:
                    if c.collidepoint(ev.pos):
                        self.index = i
                # un clic fuori dal campo gli toglie il focus: lo si ridà, il
                # nome è l'unico testo della pagina
                self.field.focused = True

    def _save(self):
        name = A.clean_name(self.field.text)
        if not name:
            self.error = "Scrivi un nickname: è il nome che vedranno gli altri giocatori."
            return
        dex = self.items[self.index][0] if self.items else 0
        try:
            A.save_profile(name, dex)
        except OSError as e:
            self.error = f"Non riesco a salvare il profilo: {e}"
            return
        self.app.profile = {"name": name, "avatar": dex}
        self._back()

    def _back(self):
        from .menu_scene import MenuScene
        self.next_scene = MenuScene(self.app)

    def fixed_update(self):
        pass

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    # --- disegno ------------------------------------------------------------------------
    _cols = 12

    def draw_fullres(self, surface, f):
        W, H = surface.get_size()
        surface.fill(BG)
        self.buttons.clear()
        big, mid, sm = font(max(24, H // 26), True), font(max(15, H // 46)), font(max(13, H // 56))
        x = int(W * 0.06)
        t = big.render("Il tuo profilo" if not self.first else "Benvenuto! Crea il tuo profilo",
                       True, GOLD)
        surface.blit(t, (x, int(H * 0.05)))
        y = int(H * 0.05) + t.get_height() + 14
        surface.blit(mid.render("Nickname (lo vedranno gli altri giocatori):", True, TEXT), (x, y))
        y += mid.get_height() + 6
        self.field.draw(surface, (x, y, int(W * 0.34), mid.get_height() + 12), mid)
        y += mid.get_height() + 26

        # Griglia dei ritratti a sinistra, anteprima grande a destra.
        surface.blit(mid.render("Immagine profilo (la vedrai nella scelta del personaggio):",
                                True, TEXT), (x, y))
        y += mid.get_height() + 8
        grid_w = int(W * 0.60)
        rows_room = H - y - int(H * 0.16)
        n = max(1, len(self.items))
        self._cols = cols = 12
        rows = (n + cols - 1) // cols
        cell = max(24, min(grid_w // cols, rows_room // rows))
        side = cell - 6
        self._cells = []
        for i, (dex, _) in enumerate(self.items):
            r = pygame.Rect(x + (i % cols) * cell, y + (i // cols) * cell, side, side)
            self._cells.append((r, i))
            col = GOLD if i == self.index else ((200, 205, 198) if i == self.hover else BORDER)
            A.draw_avatar(surface, dex, r, col)
            if i == self.index:
                pygame.draw.rect(surface, GOLD, r.inflate(4, 4), 2)

        px = x + cols * cell + int(W * 0.03)
        py = y
        pside = min(W - px - x, int(H * 0.30))
        pside -= pside % 40                     # multiplo di 40: pixel netti (nearest)
        if self.items and pside >= 40:
            dex, pname = self.items[self.index if self.hover is None else self.hover]
            A.draw_avatar(surface, dex, (px, py, pside, pside), GOLD)
            yy = py + pside + 10
            surface.blit(mid.render(A.clean_name(self.field.text) or "?", True, GOLD), (px, yy))
            yy += mid.get_height() + 4
            surface.blit(sm.render(pname, True, TEXT), (px, yy))
            yy += sm.get_height() + 4
            who = ", ".join(self._credits.get(f"{dex:04d}", {}).get("authors", []))
            for line in _wrap(f"Ritratto: {who}", max(16, (W - px) // max(7, sm.size("x")[0]))):
                surface.blit(sm.render(line, True, DIM), (px, yy))
                yy += sm.get_height() + 2
        elif not self.items:
            surface.blit(mid.render("Ritratti mancanti: lancia  python tools/fetch_avatars.py",
                                    True, RED), (x, y))

        by = H - int(H * 0.12)
        bh = mid.get_height() + 14
        self.buttons.draw(surface, (x, by, 200, bh), "Salva  (INVIO)", self._save, mid)
        if not self.first:
            self.buttons.draw(surface, (x + 214, by, 200, bh), "Annulla  (ESC)", self._back, mid)
        if self.error:
            surface.blit(sm.render(self.error, True, RED), (x + 430, by + 8))
        cr = sm.render("Ritratti: PMD Sprite Collab (sprites.pmdcollab.org), CC BY-NC 4.0. "
                       "Autori nei Crediti del menu (C).", True, DIM)
        surface.blit(cr, (x, H - cr.get_height() - 10))


def _wrap(text, n):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + len(w) + 1 > n:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines
