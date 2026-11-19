"""Pulsante "Novità" (in alto a sinistra nel menu) e pannello delle patch notes.

Solo interfaccia: legge game/news.py (data/news.json, max 10 voci). Il testo
delle voci si impagina UNA volta su una tela in cache (rifatta solo se cambia
la dimensione della finestra): a ogni frame un blit della parte visibile.
"""
from __future__ import annotations

import pygame

from .. import news as N
from .. import ui_theme as UI

# Stellina pixel art (9x9) dell'icona: X = oro, o = ombra.
_STAR = [
    "....X....",
    "....X....",
    "...XXX...",
    "XXXXXXXXo",
    ".oXXXXXo.",
    "..XXXXX..",
    "..XXoXX..",
    ".XXo.oXX.",
    ".Xo...oX.",
]
_icons: dict = {}


def star_icon(px: int) -> pygame.Surface:
    if px not in _icons:
        s = pygame.Surface((9, 9), pygame.SRCALPHA)
        for y, row in enumerate(_STAR):
            for x, ch in enumerate(row):
                if ch == "X":
                    s.set_at((x, y), UI.GOLD)
                elif ch == "o":
                    s.set_at((x, y), (150, 110, 30))
        _icons[px] = pygame.transform.scale(s, (9 * px, 9 * px))
    return _icons[px]


def news_button(surface, x, y, news, unread, hover=False):
    """Pulsante in alto a sinistra (gemello del profilo a destra). Ritorna il rect."""
    nm = UI.font(14, bold=True).render("Novità", True, UI.GOLD if hover else UI.TEXT)
    v = N.latest_version(news)
    st = UI.font(11).render(f"patch notes {v}" if v else "patch notes", True, UI.DIM)
    side = 40
    tw = max(nm.get_width(), st.get_width())
    r = pygame.Rect(x, y, 6 + side + 12 + tw + 16, side + 12)
    UI.alpha_rect(surface, (*UI.BG, 184), r, radius=10)
    pygame.draw.rect(surface, UI.LINE if hover else UI.CARD_LINE, r, 1, border_radius=10)
    box = pygame.Rect(r.x + 6, r.y + 6, side, side)
    pygame.draw.rect(surface, UI.CARD, box, border_radius=8)
    pygame.draw.rect(surface, UI.GOLD if hover else UI.CARD_LINE, box, 1, border_radius=8)
    ic = star_icon(4)
    surface.blit(ic, ic.get_rect(center=box.center))
    tx = box.right + 12
    surface.blit(nm, (tx, r.centery - nm.get_height() - 1))
    surface.blit(st, (tx, r.centery + 1))
    if unread:          # pallino d'oro finché il pannello non è stato aperto
        c = (box.right - 2, box.y + 2)
        pygame.draw.circle(surface, UI.GOLD_SHADOW, c, 6)
        pygame.draw.circle(surface, UI.GOLD, c, 5)
        pygame.draw.circle(surface, (255, 246, 200), (c[0] - 1, c[1] - 1), 2)
    return r


def _wrap(text, f, width):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if f.size(t)[0] <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


class NewsPanel:
    """Finestra modale sopra il menu. close() / .open per sapere se è aperta."""

    def __init__(self, news):
        self.news = news
        self.open = False
        self.scroll = 0
        self._canvas = None
        self._canvas_key = None
        self._rect = pygame.Rect(0, 0, 0, 0)
        self._body = pygame.Rect(0, 0, 0, 0)
        self._close = pygame.Rect(0, 0, 0, 0)
        self._hover_close = False

    def show(self):
        self.open = True
        self.scroll = 0
        N.mark_read(self.news)

    def close(self):
        self.open = False

    # --- input --------------------------------------------------------------
    def handle(self, ev) -> None:
        """Consuma l'evento (il menu sotto non lo vede finché il pannello è aperto)."""
        step = 40
        if ev.type == pygame.MOUSEMOTION:
            self._hover_close = self._close.collidepoint(ev.pos)
        elif ev.type == pygame.MOUSEWHEEL:
            self.scroll -= ev.y * step
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self._close.collidepoint(ev.pos) or not self._rect.collidepoint(ev.pos):
                self.close()
        elif ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_n):
                self.close()
            elif ev.key in (pygame.K_DOWN, pygame.K_s):
                self.scroll += step
            elif ev.key in (pygame.K_UP, pygame.K_w):
                self.scroll -= step
            elif ev.key == pygame.K_PAGEDOWN:
                self.scroll += self._body.h - step
            elif ev.key == pygame.K_PAGEUP:
                self.scroll -= self._body.h - step

    # --- disegno -------------------------------------------------------------
    def _build(self, w, k=1.0):
        """Tela con tutte le voci, larga w (solo testo e badge, sfondo trasparente).
        k = scala della finestra (720p = 1): i caratteri crescono con lei."""
        def fs(n):
            return max(n, int(n * k))
        f_ver = UI.font(fs(15), bold=True)
        f_date = UI.font(fs(12))
        f_title = UI.font(fs(16), bold=True)
        f_item = UI.font(fs(14))
        blocks = []          # (surface, x, y)
        y = 4
        if not self.news:
            t = f_item.render("Nessuna novità per ora.", True, UI.DIM)
            blocks.append((t, 0, y))
            y += t.get_height()
        for i, e in enumerate(self.news):
            if i:
                y += 14
                blocks.append(("line", 0, y))
                y += 18
            v = f_ver.render(e["version"], True, UI.BG)
            badge = pygame.Surface((v.get_width() + 16, v.get_height() + 6), pygame.SRCALPHA)
            pygame.draw.rect(badge, UI.GOLD if i == 0 else UI.SOFT, badge.get_rect(), border_radius=6)
            badge.blit(v, (8, 3))
            blocks.append((badge, 0, y))
            bx = badge.get_width() + 10
            if i == 0:
                nw = UI.font(fs(11), bold=True).render("NUOVO", True, UI.GREEN_HI)
                blocks.append((nw, bx, y + (badge.get_height() - nw.get_height()) // 2))
                bx += nw.get_width() + 10
            if e["date"]:
                d = f_date.render(e["date"], True, UI.DIM)
                blocks.append((d, bx, y + (badge.get_height() - d.get_height()) // 2))
            y += badge.get_height() + 8
            if e["title"]:
                for ln in _wrap(e["title"], f_title, w):
                    t = f_title.render(ln, True, UI.TEXT)
                    blocks.append((t, 0, y))
                    y += t.get_height() + 2
                y += 6
            for item in e["items"]:
                first = True
                for ln in _wrap(item, f_item, w - 22):
                    if first:
                        blocks.append(("dot", 6, y + f_item.get_height() // 2))
                        first = False
                    t = f_item.render(ln, True, UI.SOFT)
                    blocks.append((t, 22, y))
                    y += t.get_height() + 2
                y += 6
        canvas = pygame.Surface((w, y + 8), pygame.SRCALPHA)
        for s, x, yy in blocks:
            if s == "line":
                pygame.draw.line(canvas, UI.LINE, (0, yy), (w, yy))
            elif s == "dot":
                pygame.draw.rect(canvas, UI.GOLD, (x, yy - 2, 4, 4))
            else:
                canvas.blit(s, (x, yy))
        return canvas

    def draw(self, surface):
        if not self.open:
            return
        W, H = surface.get_size()
        k = H / 720
        UI.alpha_rect(surface, (0, 0, 0, 150), (0, 0, W, H))
        pw, ph = min(W - 32, int(680 * k)), min(H - 32, int(540 * k))
        r = pygame.Rect(0, 0, pw, ph)
        r.center = (W // 2, H // 2)
        self._rect = r
        pygame.draw.rect(surface, UI.PANEL, r, border_radius=14)
        pygame.draw.rect(surface, UI.BORDER, r, 1, border_radius=14)
        pad = int(28 * k)
        # intestazione
        ic = star_icon(max(3, int(4 * k)))
        surface.blit(ic, (r.x + pad, r.y + pad + 4))
        tr = UI.title(surface, "Novità", r.x + pad + ic.get_width() + 14, r.y + pad - 4,
                      max(30, int(38 * k)), shadow=3)
        sub = UI.font(max(11, int(12 * k))).render(
            f"novità e patch notes · ultime {N.MAX_ENTRIES} versioni", True, UI.DIM)
        surface.blit(sub, (tr.x, tr.bottom + 4))
        # chiudi
        cs = 32
        self._close = pygame.Rect(r.right - pad - cs + 8, r.y + pad - 8, cs, cs)
        pygame.draw.rect(surface, UI.LINE if self._hover_close else UI.CARD_LINE,
                         self._close, 1, border_radius=8)
        c = self._close.center
        col = UI.TEXT if self._hover_close else UI.DIM
        pygame.draw.line(surface, col, (c[0] - 6, c[1] - 6), (c[0] + 6, c[1] + 6), 2)
        pygame.draw.line(surface, col, (c[0] - 6, c[1] + 6), (c[0] + 6, c[1] - 6), 2)
        top = sub.get_rect(topleft=(tr.x, tr.bottom + 4)).bottom + int(16 * k)
        pygame.draw.line(surface, UI.LINE, (r.x + pad, top), (r.right - pad, top))
        # corpo scorrevole
        body = pygame.Rect(r.x + pad, top + 14, r.w - 2 * pad - 14, r.bottom - pad - 34 - (top + 14))
        self._body = body
        key = (body.w, len(self.news), round(k, 2))
        if self._canvas_key != key:
            self._canvas = self._build(body.w, k)
            self._canvas_key = key
        ch = self._canvas.get_height()
        self.scroll = max(0, min(self.scroll, max(0, ch - body.h)))
        surface.blit(self._canvas, body.topleft, pygame.Rect(0, self.scroll, body.w, body.h))
        if ch > body.h:          # barra di scorrimento
            tr_ = pygame.Rect(body.right + 8, body.y, 4, body.h)
            pygame.draw.rect(surface, UI.CARD_LINE, tr_, border_radius=2)
            th = max(24, body.h * body.h // ch)
            ty = body.y + (body.h - th) * self.scroll // max(1, ch - body.h)
            pygame.draw.rect(surface, UI.GOLD, (tr_.x, ty, 4, th), border_radius=2)
        UI.hints(surface, [("Esc", "chiudi"), ("↑↓", "scorri")], r.x + pad, r.bottom - pad - 22)
