"""Interfaccia del negozio (overlay). Usabile solo in base.

Mostra oro, i 6 slot oggetto (clic per vendere), gli oggetti consigliati e la
lista acquistabile (base + completi) con prezzo scontato dai componenti già
posseduti. Ritorna le azioni di acquisto/vendita come ('buy', id) / ('sell', n).
Icone: segnaposto colorati (le icone vere PokeAPI vanno in assets/items/).
"""
from __future__ import annotations

import pygame

from engine.items import ITEM_SLOTS

_PANEL_W, _PANEL_H = 600, 440


def _icon_color(item_id: str):
    h = abs(hash(item_id))
    return (80 + h % 150, 80 + (h // 7) % 150, 80 + (h // 53) % 150)


class ShopUI:
    def __init__(self):
        self.open = False
        self._buy_rects = []    # (rect, item_id)
        self._sell_rects = []   # (rect, slot)
        self._panel = pygame.Rect(0, 0, _PANEL_W, _PANEL_H)

    def toggle(self):
        self.open = not self.open

    def handle_event(self, ev):
        if not self.open or ev.type != pygame.MOUSEBUTTONDOWN:
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

    def draw(self, surface, font, catalog, gold, owned, role, near_base):
        self._buy_rects.clear()
        self._sell_rects.clear()
        W, H = surface.get_size()
        self._panel = pygame.Rect((W - _PANEL_W) // 2, (H - _PANEL_H) // 2, _PANEL_W, _PANEL_H)
        p = self._panel
        bg = pygame.Surface((p.w, p.h), pygame.SRCALPHA); bg.fill((16, 18, 26, 240))
        surface.blit(bg, p)
        pygame.draw.rect(surface, (210, 200, 120), p, 2)

        head = f"NEGOZIO   Oro: {int(gold)}" + ("" if near_base else "   (vai in BASE per comprare)")
        surface.blit(font.render(head, True, (255, 230, 120) if near_base else (230, 150, 150)),
                     (p.x + 14, p.y + 10))

        # Slot posseduti (clic = vendi).
        surface.blit(font.render(f"Oggetti ({len(owned)}/{ITEM_SLOTS})  - clic per vendere:",
                                 True, (210, 210, 220)), (p.x + 14, p.y + 38))
        for i in range(ITEM_SLOTS):
            r = pygame.Rect(p.x + 14 + i * 56, p.y + 60, 50, 50)
            pygame.draw.rect(surface, (40, 42, 50), r)
            pygame.draw.rect(surface, (90, 90, 105), r, 1)
            if i < len(owned):
                it = catalog.get(owned[i])
                pygame.draw.rect(surface, _icon_color(owned[i]), r.inflate(-10, -10))
                if it:
                    surface.blit(font.render(it.name[:6], True, (235, 235, 235)), (r.x + 2, r.bottom - 16))
                self._sell_rects.append((r, i))

        # Consigliati.
        rec = catalog.recommended_for(role)
        surface.blit(font.render("Consigliati: " + ", ".join(
            catalog.get(x).name for x in rec if catalog.get(x)), True, (150, 200, 150)),
            (p.x + 14, p.y + 120))

        # Lista acquistabile.
        y0 = p.y + 150
        surface.blit(font.render("Base:", True, (200, 200, 210)), (p.x + 14, y0))
        self._draw_list(surface, font, catalog, catalog.base_ids, owned, gold, near_base,
                        p.x + 14, y0 + 22, cols=5)
        y1 = y0 + 100
        surface.blit(font.render("Completi (scontano i componenti):", True, (200, 200, 210)),
                     (p.x + 14, y1))
        self._draw_list(surface, font, catalog, catalog.completed_ids, owned, gold, near_base,
                        p.x + 14, y1 + 22, cols=4)

        surface.blit(font.render("P = chiudi", True, (170, 170, 180)), (p.x + 14, p.bottom - 22))

    def _draw_list(self, surface, font, catalog, ids, owned, gold, near_base, x, y, cols):
        bw, bh, gap = 108, 54, 8
        for i, iid in enumerate(ids):
            it = catalog.get(iid)
            if it is None:
                continue
            r = pygame.Rect(x + (i % cols) * (bw + gap), y + (i // cols) * (bh + gap), bw, bh)
            price = catalog.effective_price(iid, owned)
            slots_after = len(owned) - len(catalog.components_in(iid, owned)) + 1
            afford = near_base and gold >= price and slots_after <= ITEM_SLOTS
            pygame.draw.rect(surface, (34, 38, 48) if afford else (26, 26, 32), r)
            pygame.draw.rect(surface, (100, 150, 100) if afford else (80, 80, 90), r, 1)
            pygame.draw.rect(surface, _icon_color(iid), pygame.Rect(r.x + 4, r.y + 4, 14, 14))
            surface.blit(font.render(it.name[:11], True, (235, 235, 235)), (r.x + 22, r.y + 4))
            col = (120, 220, 120) if afford else (200, 180, 120)
            surface.blit(font.render(f"{price}", True, col), (r.x + 6, r.bottom - 18))
            self._buy_rects.append((r, iid))
