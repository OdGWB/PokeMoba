"""Interfaccia del negozio (overlay). Comprare/vendere solo in base.

Mostra oro, i 6 slot oggetto (clic per vendere; tasti 1-6 attivano gli oggetti
attivabili), le SCHEDE per categoria (Consigliati, Vitamine, Intermedi, Fisici,
Speciali, Ibridi, Combattenti, Tank, Supporto, Utilità) e la griglia degli
oggetti della scheda con il prezzo scontato dai componenti già posseduti.
Passando sopra un oggetto si vedono statistiche, ricetta ed effetto.
Ritorna le azioni come ('buy', id) / ('sell', n).

Icone: assets/items/<icon>.png (tools/fetch_items.py, da PokeAPI/sprites),
scalate nearest; se il file manca, segnaposto colorato con l'iniziale.
"""
from __future__ import annotations

from pathlib import Path

import pygame

from engine.items import ITEM_SLOTS

_PANEL_W, _PANEL_H = 640, 500
_ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "items"
_REC_TAB = ("rec", "Consigliati")

# Etichette delle statistiche (chiavi di items.json -> testo, percentuale?).
_STAT_LABELS = [
    ("hp", "HP", False), ("attack", "Att.", False), ("defense", "Dif.", False),
    ("sp_attack", "Att.Sp.", False), ("sp_defense", "Dif.Sp.", False),
    ("attack_speed", "vel.att.", True), ("move_speed_pct", "vel.mov.", True),
    ("crit", "brutto colpo", True), ("lifesteal", "rubavita", True),
    ("omnivamp", "rubavita (anche mosse)", True), ("cdr", "rid. ricariche", True),
    ("heal_power", "cure/scudi", True),
]


def _icon_color(item_id: str):
    h = sum((i + 1) * ord(c) for i, c in enumerate(item_id))   # stabile tra un avvio e l'altro
    return (70 + h % 120, 70 + (h // 7) % 120, 70 + (h // 53) % 120)


def stats_text(it) -> str:
    parts = []
    for key, label, pct in _STAT_LABELS:
        v = it.stats.get(key)
        if not v:
            continue
        if pct:
            parts.append(f"{v * 100:+.0f}% {label}")
        else:
            parts.append(f"{v:+.0f} {label}")
    return ", ".join(parts)


class ShopUI:
    def __init__(self):
        self.open = False
        self.tab = _REC_TAB[0]
        self._buy_rects = []    # (rect, item_id)
        self._sell_rects = []   # (rect, slot)
        self._tab_rects = []    # (rect, tab_id)
        self._panel = pygame.Rect(0, 0, _PANEL_W, _PANEL_H)
        self._icons: dict = {}  # (item_id, size) -> Surface

    def toggle(self):
        self.open = not self.open

    def handle_event(self, ev):
        if not self.open or ev.type != pygame.MOUSEBUTTONDOWN:
            return None
        for rect, tab in self._tab_rects:
            if rect.collidepoint(ev.pos):
                self.tab = tab
                return None
        for rect, slot in self._sell_rects:
            if rect.collidepoint(ev.pos):
                return ("sell", slot)
        for rect, iid in self._buy_rects:
            if rect.collidepoint(ev.pos):
                return ("buy", iid)
        return None  # clic dentro il pannello ma non su un bottone

    def consumes(self, pos):
        return self.open and self._panel.collidepoint(pos)

    # --- icone ----------------------------------------------------------------
    def _icon(self, catalog, iid, size, font):
        key = (iid, size)
        surf = self._icons.get(key)
        if surf is not None:
            return surf
        it = catalog.get(iid)
        path = _ICON_DIR / f"{it.icon}.png" if it is not None and it.icon else None
        surf = None
        if path is not None and path.exists():
            try:
                img = pygame.image.load(str(path))
                img = img.convert_alpha() if pygame.display.get_surface() else img
                # crop del bordo trasparente, poi scala intera NEAREST (pixel art)
                bb = img.get_bounding_rect()
                if bb.w and bb.h:
                    img = img.subsurface(bb).copy()
                k = max(1, size // max(bb.w, bb.h, 1))
                img = pygame.transform.scale(img, (bb.w * k, bb.h * k))
                surf = pygame.Surface((size, size), pygame.SRCALPHA)
                surf.blit(img, ((size - img.get_width()) // 2, (size - img.get_height()) // 2))
            except (pygame.error, ValueError):
                surf = None
        if surf is None:   # segnaposto: quadrato colorato con l'iniziale
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            col = _icon_color(iid)
            pygame.draw.rect(surf, col, surf.get_rect(), border_radius=4)
            pygame.draw.rect(surf, tuple(max(0, c - 50) for c in col), surf.get_rect(), 2,
                             border_radius=4)
            letter = (it.name[:1] if it is not None else iid[:1]).upper()
            t = font.render(letter, True, (245, 245, 245))
            surf.blit(t, ((size - t.get_width()) // 2, (size - t.get_height()) // 2))
        self._icons[key] = surf
        return surf

    # --- disegno --------------------------------------------------------------
    def draw(self, surface, font, catalog, gold, owned, recommended, near_base,
             cooldowns=None, now=0.0):
        """`recommended` = lista di id (o un ruolo: si usano i consigliati del ruolo)."""
        if isinstance(recommended, str):
            recommended = catalog.recommended_for(recommended)
        self._buy_rects.clear()
        self._sell_rects.clear()
        self._tab_rects.clear()
        W, H = surface.get_size()
        self._panel = pygame.Rect((W - _PANEL_W) // 2, (H - _PANEL_H) // 2, _PANEL_W, _PANEL_H)
        p = self._panel
        bg = pygame.Surface((p.w, p.h), pygame.SRCALPHA); bg.fill((16, 18, 26, 240))
        surface.blit(bg, p)
        pygame.draw.rect(surface, (210, 200, 120), p, 2)

        head = f"NEGOZIO   Oro: {int(gold)}" + ("" if near_base else "   (vai in BASE per comprare)")
        surface.blit(font.render(head, True, (255, 230, 120) if near_base else (230, 150, 150)),
                     (p.x + 14, p.y + 10))

        # Slot posseduti (clic = vendi; 1-6 = attiva).
        surface.blit(font.render(f"Oggetti ({len(owned)}/{ITEM_SLOTS}) - clic: vendi, 1-6: attiva",
                                 True, (210, 210, 220)), (p.x + 14, p.y + 34))
        for i in range(ITEM_SLOTS):
            r = pygame.Rect(p.x + 14 + i * 54, p.y + 54, 50, 50)
            pygame.draw.rect(surface, (40, 42, 50), r)
            pygame.draw.rect(surface, (90, 90, 105), r, 1)
            if i < len(owned):
                surface.blit(self._icon(catalog, owned[i], 44, font), (r.x + 3, r.y + 3))
                left = (cooldowns or {}).get(owned[i], 0.0) - now
                if left > 0.0:
                    veil = pygame.Surface((r.w, r.h), pygame.SRCALPHA); veil.fill((0, 0, 0, 150))
                    surface.blit(veil, r)
                    t = font.render(str(int(left) + 1), True, (240, 240, 240))
                    surface.blit(t, t.get_rect(center=r.center))
                self._sell_rects.append((r, i))
            surface.blit(font.render(str(i + 1), True, (130, 130, 145)), (r.x + 2, r.y + 1))

        # Schede: Consigliati + categorie (due righe).
        tabs = [_REC_TAB] + list(catalog.categories)
        per_row = (len(tabs) + 1) // 2
        tw = (p.w - 28 - (per_row - 1) * 4) // per_row
        for i, (tid, label) in enumerate(tabs):
            r = pygame.Rect(p.x + 14 + (i % per_row) * (tw + 4), p.y + 112 + (i // per_row) * 26,
                            tw, 22)
            sel = tid == self.tab
            pygame.draw.rect(surface, (70, 64, 34) if sel else (32, 34, 44), r)
            pygame.draw.rect(surface, (210, 200, 120) if sel else (80, 80, 92), r, 1)
            t = font.render(self._fit(font, label, tw - 6), True,
                            (255, 235, 150) if sel else (190, 190, 200))
            surface.blit(t, t.get_rect(center=r.center))
            self._tab_rects.append((r, tid))

        ids = list(recommended) if self.tab == _REC_TAB[0] else catalog.in_category(self.tab)
        self._draw_list(surface, font, catalog, [i for i in ids if catalog.get(i)], owned,
                        gold, near_base, p.x + 14, p.y + 170, cols=3)

        # Dettagli dell'oggetto sotto il cursore.
        mx, my = pygame.mouse.get_pos()
        hover = None
        for rect, iid in self._buy_rects:
            if rect.collidepoint((mx, my)):
                hover = iid
                break
        if hover is None:
            for rect, slot in self._sell_rects:
                if rect.collidepoint((mx, my)):
                    hover = owned[slot]
                    break
        if hover is not None:
            self._draw_details(surface, font, catalog, hover, p.x + 14, p.bottom - 100, p.w - 28)

        t = font.render("P = chiudi", True, (170, 170, 180))
        surface.blit(t, (p.right - 14 - t.get_width(), p.y + 10))

    def _draw_details(self, surface, font, catalog, iid, x, y, w):
        it = catalog.get(iid)
        if it is None:
            return
        pygame.draw.line(surface, (80, 80, 92), (x, y - 6), (x + w, y - 6))
        surface.blit(self._icon(catalog, iid, 32, font), (x, y))
        surface.blit(font.render(f"{it.name}  ({it.price})", True, (255, 230, 150)), (x + 40, y))
        surface.blit(font.render(self._fit(font, stats_text(it), w - 40), True, (170, 220, 170)),
                     (x + 40, y + 17))
        yy = y + 38
        if it.build_from:
            recipe = "Ricetta: " + " + ".join(catalog.get(c).name if catalog.get(c) else c
                                              for c in it.build_from)
            surface.blit(font.render(self._fit(font, recipe, w), True, (180, 190, 220)), (x, yy))
            yy += 17
        if it.note:
            self._blit_wrapped(surface, font, it.note, x, yy, w, (215, 210, 150), max_lines=3)

    @staticmethod
    def _fit(font, text, max_w):
        if font.size(text)[0] <= max_w:
            return text
        while text and font.size(text + "…")[0] > max_w:
            text = text[:-1]
        return text + "…"

    @staticmethod
    def _blit_wrapped(surface, font, text, x, y, max_w, color, max_lines=99):
        words = text.split(" ")
        line, yy, n = "", y, 0
        for w in words:
            trial = (line + " " + w).strip()
            if font.size(trial)[0] > max_w and line:
                surface.blit(font.render(line, True, color), (x, yy))
                line, yy, n = w, yy + 16, n + 1
                if n >= max_lines:
                    return
            else:
                line = trial
        if line:
            surface.blit(font.render(line, True, color), (x, yy))

    def _draw_list(self, surface, font, catalog, ids, owned, gold, near_base, x, y, cols):
        gap = 5
        bw, bh = (_PANEL_W - 28 - (cols - 1) * gap) // cols, 52
        for i, iid in enumerate(ids):
            it = catalog.get(iid)
            r = pygame.Rect(x + (i % cols) * (bw + gap), y + (i // cols) * (bh + gap), bw, bh)
            price = catalog.effective_price(iid, owned)
            slots_after = len(owned) - len(catalog.components_in(iid, owned)) + 1
            afford = (near_base and gold >= price and slots_after <= ITEM_SLOTS
                      and catalog.group_ok(iid, owned))
            pygame.draw.rect(surface, (34, 38, 48) if afford else (26, 26, 32), r)
            pygame.draw.rect(surface, (100, 150, 100) if afford else (80, 80, 90), r, 1)
            surface.blit(self._icon(catalog, iid, 44, font), (r.x + 4, r.y + 4))
            surface.blit(font.render(self._fit(font, it.name, bw - 54), True, (235, 235, 235)),
                         (r.x + 54, r.y + 7))
            col = (120, 220, 120) if afford else (200, 180, 120)
            surface.blit(font.render(f"{price}", True, col), (r.x + 54, r.bottom - 22))
            self._buy_rects.append((r, iid))
