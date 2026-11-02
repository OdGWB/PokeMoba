"""Tier list dei Pokémon di PokéMoba, fatta da te.

Trascina un Pokémon dal gruppo "Da classificare" (o da un'altra riga) su una
riga S / A / B / C / D; trascinalo di nuovo nel gruppo in basso per toglierlo.
La classifica si salva sul PC (%APPDATA%/PokeMoba/tierlist.json), quindi la
ritrovi alla prossima apertura. "Azzera" rimette tutti in basso. ESC = menu.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pygame

import config
from engine.content import load_pokemon_def
from .char_select_scene import load_idle, scale_nearest
from .menu_scene import BG, BORDER, DIM, GOLD, PANEL, PANEL_HI, TEXT
from .online_lobby_scene import Buttons

TIERS = [("S", (230, 90, 80)), ("A", (236, 150, 70)), ("B", (232, 205, 80)),
         ("C", (130, 200, 100)), ("D", (90, 160, 210))]


def tier_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "PokeMoba" / "tierlist.json"


class TierChoiceScene:
    """Scelta della tier list: Developer (per ora vuota) o Personale (la tua)."""

    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self.buttons = Buttons()
        self._fonts = {}

    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = pygame.font.SysFont("consolas", size, bold=bold)
        return self._fonts[key]

    def _personal(self):
        self.next_scene = TierListScene(self.app)

    def _developer(self):
        pass        # da implementare

    def _back(self):
        from .menu_scene import MenuScene
        self.next_scene = MenuScene(self.app)

    def handle_events(self, events):
        for ev in events:
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self._back()
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                self.buttons.click(ev.pos)

    def fixed_update(self):
        pass

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def draw_fullres(self, surface, font):
        W, H = surface.get_size()
        surface.fill(BG)
        self.buttons.clear()
        title_f = self._font(max(30, H // 16), bold=True)
        big = self._font(max(22, H // 26), bold=True)
        small = self._font(max(13, H // 50))
        t = title_f.render("Tier list", True, GOLD)
        surface.blit(t, (W // 2 - t.get_width() // 2, H // 8))
        bw, bh = min(int(W * 0.34), 460), max(52, H // 11)
        y = int(H * 0.38)
        self.buttons.draw(surface, (W // 2 - bw // 2, y, bw, bh), "Developer",
                          self._developer, big)
        self.buttons.draw(surface, (W // 2 - bw // 2, y + bh + 16, bw, bh), "Personale",
                          self._personal, big)
        self.buttons.draw(surface, (W // 2 - bw // 2, y + 2 * (bh + 16) + 10, bw, bh),
                          "Indietro  (Esc)", self._back, small)


class TierListScene:
    def __init__(self, app):
        self.app = app
        self.next_scene = None
        defs = [load_pokemon_def(str(app.root / rel)) for rel in config.ROSTER]
        self.names = [d.name for d in defs]
        self.roles = {d.name: d.role for d in defs}
        self._frames = {}
        for d in defs:
            fr = load_idle(d.sprite_dir)
            self._frames[d.name] = fr[0][0] if fr else None
        self.colors = {d.name: tuple(d.color) for d in defs}
        self.rows = {t: [] for t, _ in TIERS}       # tier -> [nomi]
        self._load()
        self.drag = None                            # nome in trascinamento
        self.mouse = (0, 0)
        self.hover = None
        self._cells: list = []                      # (rect, nome)
        self._zones: dict = {}                      # tier|"pool" -> rect
        self.buttons = Buttons()
        self._fonts = {}
        self._icons = {}

    # --- salvataggio ----------------------------------------------------------------
    def _load(self):
        try:
            data = json.loads(tier_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        seen = set()
        for t, _ in TIERS:
            for n in data.get(t, []):
                if n in self.names and n not in seen:
                    self.rows[t].append(n)
                    seen.add(n)

    def _save(self):
        try:
            p = tier_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self.rows, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _pool(self):
        placed = {n for r in self.rows.values() for n in r}
        return [n for n in self.names if n not in placed]

    def _reset(self):
        self.rows = {t: [] for t, _ in TIERS}
        self._save()

    def _back(self):
        self.next_scene = TierChoiceScene(self.app)

    # --- input -------------------------------------------------------------------------
    def handle_events(self, events):
        for ev in events:
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self._back()
            elif ev.type == pygame.MOUSEMOTION:
                self.mouse = ev.pos
                self.hover = next((n for r, n in self._cells if r.collidepoint(ev.pos)), None)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self.buttons.click(ev.pos):
                    continue
                self.drag = next((n for r, n in self._cells if r.collidepoint(ev.pos)), None)
                self.mouse = ev.pos
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.drag:
                self._drop(self.drag, ev.pos)
                self.drag = None

    def _drop(self, name, pos):
        dest = next((z for z, r in self._zones.items() if r.collidepoint(pos)), None)
        if dest is None:
            return
        for r in self.rows.values():
            if name in r:
                r.remove(name)
        if dest != "pool":
            self.rows[dest].append(name)
        self._save()

    def fixed_update(self):
        pass

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    # --- disegno -------------------------------------------------------------------------
    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = pygame.font.SysFont("consolas", size, bold=bold)
        return self._fonts[key]

    def _icon(self, name, side):
        key = (name, side)
        if key not in self._icons:
            fr = self._frames.get(name)
            self._icons[key] = scale_nearest(fr, side - 8) if fr is not None else None
        return self._icons[key]

    def _draw_cell(self, surface, name, rect, lift=False):
        col = self.colors.get(name, (120, 120, 120))
        on = name == self.hover or lift
        pygame.draw.rect(surface, PANEL_HI if on else PANEL, rect, border_radius=6)
        pygame.draw.rect(surface, GOLD if on else col, rect, 2, border_radius=6)
        img = self._icon(name, rect.w)
        if img is not None:
            surface.blit(img, (rect.centerx - img.get_width() // 2,
                               rect.centery - img.get_height() // 2))

    def draw_fullres(self, surface, font):
        W, H = surface.get_size()
        surface.fill(BG)
        self.buttons.clear()
        title_f = self._font(max(28, H // 18), bold=True)
        mid = self._font(max(14, H // 46))
        small = self._font(max(12, H // 58))
        t = title_f.render("Tier list", True, GOLD)
        surface.blit(t, (W // 2 - t.get_width() // 2, int(H * 0.025)))
        h = small.render("Trascina i Pokémon sulle righe per classificarli; trascinali in basso "
                         "per toglierli. Si salva da sola.", True, DIM)
        surface.blit(h, (W // 2 - h.get_width() // 2, int(H * 0.025) + t.get_height() + 2))

        top = int(H * 0.025) + t.get_height() + h.get_height() + 14
        pool_h = int(H * 0.22)
        avail = H - top - pool_h - 70
        row_h = max(48, min(avail // len(TIERS), int(H * 0.13)))
        cell = row_h - 8
        lab_w = max(48, int(row_h * 0.9))
        x0 = int(W * 0.06)
        w = W - 2 * x0
        self._cells = []
        self._zones = {}
        for i, (tier, col) in enumerate(TIERS):
            y = top + i * row_h
            r = pygame.Rect(x0, y, w, row_h - 4)
            self._zones[tier] = r
            hot = self.drag and r.collidepoint(self.mouse)
            pygame.draw.rect(surface, PANEL_HI if hot else PANEL, r, border_radius=6)
            pygame.draw.rect(surface, GOLD if hot else BORDER, r, 1, border_radius=6)
            lab = pygame.Rect(r.x, r.y, lab_w, r.h)
            pygame.draw.rect(surface, col, lab, border_radius=6)
            lt = title_f.render(tier, True, (20, 24, 22))
            surface.blit(lt, (lab.centerx - lt.get_width() // 2, lab.centery - lt.get_height() // 2))
            self._place(surface, self.rows[tier], r.x + lab_w + 8, r.y + 2, r.right - 6, cell)

        py = top + len(TIERS) * row_h + 10
        pr = pygame.Rect(x0, py, w, pool_h)
        self._zones["pool"] = pr
        hot = self.drag and pr.collidepoint(self.mouse)
        pygame.draw.rect(surface, PANEL_HI if hot else PANEL, pr, border_radius=6)
        pygame.draw.rect(surface, GOLD if hot else BORDER, pr, 1, border_radius=6)
        surface.blit(small.render("Da classificare", True, DIM), (pr.x + 8, pr.y + 4))
        self._place(surface, self._pool(), pr.x + 8, pr.y + small.get_height() + 8, pr.right - 6,
                    cell)

        # Nome e ruolo del Pokémon sotto il mouse.
        info = self.drag or self.hover
        if info:
            txt = mid.render(f"{info}  -  {self.roles.get(info, '')}", True, TEXT)
            surface.blit(txt, (W // 2 - txt.get_width() // 2, H - txt.get_height() - 46))
        bh = mid.get_height() + 14
        self.buttons.draw(surface, (x0, H - bh - 10, 200, bh), "Indietro  (Esc)", self._back, mid)
        self.buttons.draw(surface, (x0 + 214, H - bh - 10, 160, bh), "Azzera", self._reset, mid)

        if self.drag:
            d = pygame.Rect(0, 0, cell, cell)
            d.center = self.mouse
            self._draw_cell(surface, self.drag, d, lift=True)

    def _place(self, surface, names, x, y, xmax, cell):
        """Disposizione a righe di icone; le celle entrano in self._cells (per il clic)."""
        gap = 4
        cx, cy = x, y
        for n in names:
            if cx + cell > xmax:
                cx, cy = x, cy + cell + gap
            r = pygame.Rect(cx, cy, cell, cell)
            cx += cell + gap
            if n == self.drag:
                continue
            self._cells.append((r, n))
            self._draw_cell(surface, n, r)
