"""Pannelli della partita a piena risoluzione: tabellone (TAB), schermata di fine
partita e riepilogo della morte. Condivisi da MatchScene e OnlineMatchScene.

Solo disegno: le scene passano le righe (ScoreRow) e il riepilogo (dict del
motore, Match._make_death_recap). PRESTAZIONI: ogni pannello si disegna su una
Surface in cache e si rifa SOLO quando cambiano i dati (chiave = tupla delle
righe + dimensioni); a frame resta un solo blit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from . import hud
from .fx import type_color

BLUE_BG = (24, 40, 70)
RED_BG = (66, 26, 28)
ME_HI = (246, 206, 92)


@dataclass
class ScoreRow:
    eid: int
    name: str                 # nome del Pokémon (forma attuale)
    team: int
    dex: int = 0
    k: int = 0
    d: int = 0
    a: int = 0
    cs: int = 0
    level: int = 1
    dmg: int = 0
    items: list = field(default_factory=list)
    player: str = ""          # nickname del giocatore (online) o "" (bot/offline)
    alive: bool = True
    me: bool = False

    def key(self):
        return (self.eid, self.name, self.team, self.dex, self.k, self.d, self.a, self.cs,
                self.level, self.dmg, tuple(self.items), self.player, self.alive, self.me)


def rows_from_world(world, me_id) -> list:
    """Righe dal motore (partita offline)."""
    out = []
    for p in world.pokemons():
        if getattr(p, "is_decoy", False):
            continue
        out.append(ScoreRow(p.id, p.name, p.team, p.dex, p.stat_kills, p.stat_deaths,
                            p.stat_assists, p.stat_cs, p.level, int(round(p.stat_dmg)),
                            list(p.items), "" if p.id != me_id else "Tu", p.alive,
                            p.id == me_id))
    return out


def rows_from_score(score, me_id, names=None, dead=()) -> list:
    """Righe dallo stato visivo online (net/visual.capture_score)."""
    out = []
    names = names or {}
    for r in score or ():
        try:
            eid, name, team, dex, k, d, a, cs, lvl, dmg, items = r
        except (TypeError, ValueError):
            continue
        out.append(ScoreRow(int(eid), str(name), int(team), int(dex), int(k), int(d), int(a),
                            int(cs), int(lvl), int(dmg), list(items or ()),
                            names.get(int(eid), ""), int(eid) not in dead, int(eid) == me_id))
    return out


# --- tabella -----------------------------------------------------------------------------
ROW_H = 38
HEAD_H = 26
PORT = 30
ICON = 24


def _cols(width: int, dmg: bool):
    """Ascisse delle colonne (dal bordo del pannello)."""
    c = {"port": 10, "name": 50, "lvl": 0, "kda": 0, "cs": 0, "items": 0, "dmg": 0}
    right = width - 12
    if dmg:
        c["dmg"] = right - 110
        right = c["dmg"] - 14
    c["items"] = right - 6 * (ICON + 3)
    c["cs"] = c["items"] - 56
    c["kda"] = c["cs"] - 110
    c["lvl"] = c["kda"] - 44
    return c


def _team_table(rows, team, width, icon, portrait, dmg_max, show_dmg, my_team):
    rs = [r for r in rows if r.team == team]
    h = HEAD_H + ROW_H * max(1, len(rs))
    surf = pygame.Surface((width, h), pygame.SRCALPHA)
    c = _cols(width, show_dmg)
    col = hud.BLUE if team == 0 else hud.RED
    bg = BLUE_BG if team == 0 else RED_BG
    pygame.draw.rect(surf, (*bg, 210), (0, 0, width, HEAD_H), border_radius=4)
    side = "BLU" if team == 0 else "ROSSA"
    who = " (la tua squadra)" if team == my_team else ""
    hud.text(surf, f"SQUADRA {side}{who}", (10, 5), 14, col, bold=True)
    k = sum(r.k for r in rs)
    d = sum(r.d for r in rs)
    a = sum(r.a for r in rs)
    hud.text(surf, f"{k} / {d} / {a}", (c["kda"] + 50, 5), 14, hud.TEXT, bold=True, center=True)
    for lbl, x in (("Liv", c["lvl"] + 16), ("CS", c["cs"] + 22)):
        hud.text(surf, lbl, (x, 6), 12, hud.DIM, center=True)
    hud.text(surf, "Oggetti", (c["items"], 6), 12, hud.DIM)
    if show_dmg:
        hud.text(surf, "Danno ai campioni", (width - 10, 6), 12, hud.DIM, right=True)
    for i, r in enumerate(rs):
        y = HEAD_H + i * ROW_H
        rr = pygame.Rect(0, y + 1, width, ROW_H - 2)
        pygame.draw.rect(surf, (36, 40, 52, 200) if i % 2 == 0 else (28, 31, 40, 200), rr)
        if r.me:
            pygame.draw.rect(surf, ME_HI, rr, 1)
        img = portrait(r.dex) if portrait is not None else None
        pr = pygame.Rect(c["port"], y + (ROW_H - PORT) // 2, PORT, PORT)
        pygame.draw.rect(surf, (14, 16, 20), pr)
        if img is not None:
            if not r.alive:
                img = img.copy()
                img.fill((90, 90, 90, 255), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(img, img.get_rect(center=pr.center))
        pygame.draw.rect(surf, col, pr, 1)
        name_col = ME_HI if r.me else (hud.TEXT if r.alive else hud.DIM)
        if r.player:
            hud.text(surf, r.name, (c["name"], y + 3), 15, name_col, bold=True)
            hud.text(surf, r.player, (c["name"], y + 20), 12, hud.DIM)
        else:
            hud.text(surf, r.name, (c["name"], y + 10), 15, name_col, bold=True)
        if not r.alive:
            hud.text(surf, "caduto", (c["lvl"] - 8, y + 12), 11, (240, 120, 110), right=True)
        hud.text(surf, str(r.level), (c["lvl"] + 16, y + 10), 15, hud.TEXT, bold=True, center=True)
        hud.text(surf, f"{r.k} / {r.d} / {r.a}", (c["kda"] + 50, y + 10), 15, hud.TEXT,
                 center=True)
        hud.text(surf, str(r.cs), (c["cs"] + 22, y + 10), 15, hud.TEXT, center=True)
        for j in range(6):
            ir = pygame.Rect(c["items"] + j * (ICON + 3), y + (ROW_H - ICON) // 2, ICON, ICON)
            pygame.draw.rect(surf, (16, 18, 24), ir)
            iid = r.items[j] if j < len(r.items) else None
            if iid and icon is not None:
                ic = icon(iid, ICON - 2)
                if ic is not None:
                    surf.blit(ic, ic.get_rect(center=ir.center))
            pygame.draw.rect(surf, (58, 62, 74), ir, 1)
        if show_dmg:
            bw = width - 12 - c["dmg"]
            frac = r.dmg / dmg_max if dmg_max > 0 else 0.0
            hud.text(surf, f"{r.dmg:,}".replace(",", "."), (c["dmg"], y + 5), 13, hud.TEXT)
            hud.bar(surf, pygame.Rect(c["dmg"], y + 23, bw, 6), frac, (236, 120, 96),
                    (170, 64, 52))
    return surf


class _Cache:
    def __init__(self):
        self.key = None
        self.surf = None


_board = _Cache()
_end = _Cache()
_recap = _Cache()


def draw_scoreboard(surface, rows, my_team, time_s, icon=None, portrait=None) -> None:
    """Tabellone tenuto premuto TAB: K/D/A, CS, livello e oggetti di tutti."""
    if not rows:
        return
    W, H = surface.get_size()
    width = min(W - 40, 900)
    key = (tuple(r.key() for r in rows), width, my_team, int(time_s))
    if _board.key != key:
        _board.key = key
        dmg_max = max((r.dmg for r in rows), default=0)
        show_dmg = width >= 820
        t0 = _team_table(rows, 0, width, icon, portrait, dmg_max, show_dmg, my_team)
        t1 = _team_table(rows, 1, width, icon, portrait, dmg_max, show_dmg, my_team)
        top = 34
        h = top + t0.get_height() + 10 + t1.get_height() + 10
        s = pygame.Surface((width + 20, h), pygame.SRCALPHA)
        hud.panel(s, s.get_rect(), alpha=228)
        m, sec = divmod(int(time_s), 60)
        hud.text(s, "TABELLONE", (14, 8), 17, hud.GOLD, bold=True)
        hud.text(s, f"{m:02d}:{sec:02d}", (s.get_width() - 14, 9), 15, hud.TEXT, right=True)
        s.blit(t0, (10, top))
        s.blit(t1, (10, top + t0.get_height() + 10))
        _board.surf = s
    s = _board.surf
    surface.blit(s, (W // 2 - s.get_width() // 2, max(40, H // 2 - s.get_height() // 2 - 30)))


def draw_end_screen(surface, rows, winner, my_team, time_s, icon=None, portrait=None):
    """Schermata di fine partita: esito, durata e statistiche di tutti, con il
    danno ai campioni. Ritorna il rettangolo del pulsante "Torna al menu"."""
    W, H = surface.get_size()
    veil = pygame.Surface((W, H), pygame.SRCALPHA)
    veil.fill((6, 8, 12, 150))
    surface.blit(veil, (0, 0))
    width = min(W - 40, 940)
    key = (tuple(r.key() for r in rows), width, winner, my_team, int(time_s))
    if _end.key != key:
        _end.key = key
        dmg_max = max((r.dmg for r in rows), default=0)
        t0 = _team_table(rows, 0, width, icon, portrait, dmg_max, True, my_team)
        t1 = _team_table(rows, 1, width, icon, portrait, dmg_max, True, my_team)
        top = 92
        h = top + t0.get_height() + 10 + t1.get_height() + 70
        s = pygame.Surface((width + 20, h), pygame.SRCALPHA)
        win = winner == my_team
        col = (255, 230, 120) if win else (240, 120, 110)
        hud.panel(s, s.get_rect(), alpha=240, trim=col)
        if winner is None:
            title, sub = "PARTITA TERMINATA", ""
        else:
            title = "VITTORIA!" if win else "SCONFITTA"
            sub = f"Ha vinto la squadra {'BLU' if winner == 0 else 'ROSSA'}"
        m, sec = divmod(int(time_s), 60)
        hud.text(s, title, (s.get_width() // 2, 14), 34, col, bold=True, center=True)
        hud.text(s, f"{sub}   -   durata {m:02d}:{sec:02d}" if sub else f"durata {m:02d}:{sec:02d}",
                 (s.get_width() // 2, 58), 15, hud.TEXT, center=True)
        # Migliori della partita (piccoli riconoscimenti, solo se c'e' qualcosa).
        best = []
        if rows:
            r = max(rows, key=lambda r: (r.dmg, r.k))
            if r.dmg > 0:
                best.append(f"Più danno: {r.name}")
            r = max(rows, key=lambda r: (r.k + r.a, -r.d))
            if r.k + r.a > 0:
                best.append(f"Più partecipazioni: {r.name}")
            r = max(rows, key=lambda r: r.cs)
            if r.cs > 0:
                best.append(f"Più CS: {r.name}")
        if best:
            hud.text(s, "     ".join(best), (s.get_width() // 2, h - 58), 13, hud.GOLD,
                     center=True)
        s.blit(t0, (10, top))
        s.blit(t1, (10, top + t0.get_height() + 10))
        _end.surf = s
    s = _end.surf
    x, y = W // 2 - s.get_width() // 2, max(10, H // 2 - s.get_height() // 2)
    surface.blit(s, (x, y))
    btn = pygame.Rect(0, 0, 240, 34)
    btn.midbottom = (W // 2, y + s.get_height() - 10)
    hover = btn.collidepoint(pygame.mouse.get_pos())
    pygame.draw.rect(surface, (64, 58, 36) if hover else (38, 36, 30), btn, border_radius=6)
    pygame.draw.rect(surface, hud.GOLD if hover else hud.TRIM, btn, 2, border_radius=6)
    hud.text(surface, "Torna al menu  (Invio)", (btn.centerx, btn.y + 8), 15,
             hud.GOLD if hover else hud.TEXT, bold=True, center=True)
    return btn


def draw_death_recap(surface, recap, bottom: int, x: int = 16) -> None:
    """Riepilogo della morte: chi ti ha ucciso e il danno subito negli ultimi
    10 s, per attaccante (barra) e per mossa/fonte (colore del tipo)."""
    if not recap or not recap.get("rows"):
        return
    key = (recap.get("t"), recap.get("killer"), len(recap.get("rows", ())))
    if _recap.key != key:
        _recap.key = key
        rows = recap["rows"]
        total = sum(r["total"] for r in rows) or 1
        width = 330
        def srcs(r):   # niente riga "Torre / Torre": la fonte ripete il nome
            return [x for x in r["src"][:3] if not (len(r["src"]) == 1 and x[0] == r["name"])]
        lines = sum(1 + len(srcs(r)) for r in rows)
        h = 54 + lines * 17 + len(rows) * 8 + 8
        s = pygame.Surface((width, h), pygame.SRCALPHA)
        hud.panel(s, s.get_rect(), alpha=232, trim=(200, 96, 86))
        hud.text(s, "RIEPILOGO DELLA MORTE", (10, 6), 13, (240, 130, 115), bold=True)
        hud.text(s, f"Abbattuto da {recap.get('killer_name', '?')}", (10, 24), 15, hud.TEXT,
                 bold=True)
        hud.text(s, f"{total} danni in 10 s", (width - 10, 8), 12, hud.DIM, right=True)
        y = 48
        for r in rows:
            name_col = (240, 120, 110) if r.get("champ") else (210, 200, 180)
            if r.get("id") == recap.get("killer"):
                name_col = (255, 150, 120)
            hud.text(s, r["name"], (10, y), 14, name_col, bold=True)
            hud.text(s, str(r["total"]), (width - 10, y), 14, hud.TEXT, bold=True, right=True)
            bw = width - 20
            hud.bar(s, pygame.Rect(10, y + 16, bw, 4), r["total"] / total, (236, 120, 96),
                    (150, 56, 46))
            y += 25
            for lbl, dmg, ty in srcs(r):
                c = type_color(ty) if ty else (170, 170, 176)
                pygame.draw.rect(s, c, (18, y + 4, 8, 8))
                pygame.draw.rect(s, (0, 0, 0), (18, y + 4, 8, 8), 1)
                hud.text(s, str(lbl), (32, y), 13, (214, 214, 220))
                hud.text(s, str(dmg), (width - 10, y), 13, hud.DIM, right=True)
                y += 17
        _recap.surf = s
    s = _recap.surf
    surface.blit(s, (x, bottom - s.get_height()))
