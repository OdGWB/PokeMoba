"""Modalita' ALLENAMENTO: la partita normale (MatchScene) sulla mappa piccola
data/maps/map_training.json, con le regole di engine/training.TrainingMatch.

  - il giocatore (squadra blu) e tre MANICHINI (Pokemon della squadra rossa che
    non attaccano e tornano al loro posto) nella radura a nord;
  - pannello a sinistra (clic o tasti): livello -/+ (PagGiu/PagSu), ricariche
    azzerate (F7), oro infinito (F8), ondate di minion (F9), cura dei manichini e
    misuratore azzerato (F10), torna in base (Home), F4 nasconde il pannello;
  - misuratore del danno ai manichini: totale, ultimo colpo, DPS sugli ultimi 5 s.

Nessuna logica nuova nel motore oltre a TrainingMatch (sottoclasse di Match).
ESC apre le opzioni (game/ingame_menu.py): da li' si esce.
Il Tutorial (tutorial_scene.py) e' una sottoclasse di questa scena.
"""
from __future__ import annotations

import json
from pathlib import Path

import pygame

import config
from engine.stats import CUMULATIVE_XP, MAX_LEVEL
from engine.training import TrainingMatch
from engine.vec import Vec2
from sim.commands import MoveCommand
from sim.simulation import Simulation

from .. import hud, sfx
from .match_scene import MatchScene

ROOT = Path(__file__).resolve().parents[2]
TRAINING_MAP = ROOT / "data" / "maps" / "map_training.json"

PANEL_W = 236
ROW_H = 24
ON = (120, 214, 120)
OFF = (150, 152, 162)


class TrainingScene(MatchScene):
    def __init__(self, pokemon_path, start_level=1, flower_color=None, back=None):
        self._pokemon_path = str(pokemon_path)
        self._flower_color = flower_color
        self._back_factory = back          # callable(app) -> scena a cui tornare uscendo
        self._dummy_spots = json.loads(TRAINING_MAP.read_text(encoding="utf-8")).get(
            "dummies", [])
        self._dummies: list = []
        self._home_seq = 0
        self.panel_open = True
        self._btns: list = []              # (rect, azione) dell'ultimo frame
        super().__init__(str(TRAINING_MAP), self._pokemon_path, start_level=start_level,
                         flower_color=flower_color)
        self._sync_dummy_levels()
        # La visione iniziale tiene conto dei manichini appena allineati.
        self.match.vision.update(self.world, 0)

    # --- allestimento --------------------------------------------------------
    def _setup_moba(self):
        self.match = TrainingMatch(self.world, self.map_data)
        self.player = self._spawn_pokemon(0, "mid", is_bot=False)
        for (x, y), pdef in zip(self._dummy_spots, self._bot_defs(len(self._dummy_spots))):
            d = self._spawn_pokemon(1, "mid", is_bot=False, pdef=pdef)
            d.pos = Vec2(x + 0.5, y + 0.5)
            d.spawn_pos = Vec2(x + 0.5, y + 0.5)
            self._dummies.append(d)
        self.match.player_id = self.player.id
        self.match.dummy_ids = {d.id for d in self._dummies}
        self.match.assign_junglers()
        self.sim = Simulation(self.world, config.TICK_DT, match=self.match)
        self.match.vision.update(self.world, 0)
        self.match.vision.update(self.world, 1)

    def _sync_dummy_levels(self):
        """I manichini salgono fino al livello del giocatore (scendere ricostruisce)."""
        for d in self._dummies:
            if d.level < self.player.level:
                self.match._gain_xp(d, CUMULATIVE_XP[self.player.level] + 1.0 - d.xp)

    # --- comandi del pannello ------------------------------------------------
    def _action(self, act):
        m = self.match
        sfx.play("ui_click")
        if act == "lvl+":
            lv = self.player.level
            if lv < MAX_LEVEL:
                m._gain_xp(self.player, CUMULATIVE_XP[lv + 1] + 1.0 - self.player.xp)
                self._sync_dummy_levels()
        elif act == "lvl-":
            if self.player.level > 1:
                self._rebuild(self.player.level - 1)
        elif act == "cd":
            m.no_cd = not m.no_cd
        elif act == "gold":
            m.inf_gold = not m.inf_gold
        elif act == "waves":
            m.waves_on = not m.waves_on
            if not m.waves_on:
                m.clear_minions()
        elif act == "reset":
            m.heal_dummies()
            m.reset_meter()
        elif act == "home":
            p = self.player
            if p.alive:
                p.stop()
                p.pos = Vec2(p.spawn_pos.x, p.spawn_pos.y)
                self.camera.center_on(p.pos.x * config.TILE_SIZE, p.pos.y * config.TILE_SIZE)

    def _rebuild(self, level):
        """Livello piu' basso: si riparte da capo (il motore non toglie livelli)."""
        nxt = type(self)(self._pokemon_path, start_level=level,
                         flower_color=self._flower_color, back=self._back_factory)
        nxt.app = getattr(self, "app", None)
        nxt.panel_open = self.panel_open
        self.next_scene = nxt

    def _leave_match(self) -> None:
        self._leave()

    def _leave(self):
        app = getattr(self, "app", None)
        if app is None:
            self.quit_app = True
        elif self._back_factory is not None:
            self.next_scene = self._back_factory(app)
        else:
            from .menu_scene import MenuScene
            self.next_scene = MenuScene(app)

    KEYS = {pygame.K_PAGEUP: "lvl+", pygame.K_PAGEDOWN: "lvl-", pygame.K_F7: "cd",
            pygame.K_F8: "gold", pygame.K_F9: "waves", pygame.K_F10: "reset",
            pygame.K_HOME: "home"}

    # --- ciclo ---------------------------------------------------------------
    def handle_events(self, events) -> None:
        rest = []
        for ev in events:
            if self.match_menu is not None:     # opzioni aperte: le gestisce MatchScene
                rest.append(ev)
                continue
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F4:
                self.panel_open = not self.panel_open
                continue
            if ev.type == pygame.KEYDOWN and ev.key in self.KEYS:
                self._action(self.KEYS[ev.key])
                continue
            if (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.panel_open
                    and not self.shop.open):
                hit = next((a for r, a in self._btns if r.collidepoint(ev.pos)), None)
                if hit is not None:
                    if hit != "-":
                        self._action(hit)
                    continue
            rest.append(ev)
        super().handle_events(rest)

    def update(self, dt: float) -> None:
        super().update(dt)
        # Manichini spinti via (respinte, trascinamenti): tornano al loro posto.
        for d in self._dummies:
            if (d.alive and not self.match._immobile(d) and not d.moving
                    and d.pos.dist(d.spawn_pos) > 0.6):
                self._home_seq += 1
                self.sim.queue_command(MoveCommand(seq=90_000 + self._home_seq, entity_id=d.id,
                                                   x=d.spawn_pos.x, y=d.spawn_pos.y))

    # --- disegno -------------------------------------------------------------
    def draw_fullres(self, surface, font) -> None:
        super().draw_fullres(surface, font)
        if self.match is None or self.match.winner is not None or self.shop.open:
            return
        self._draw_panel(surface)

    def _panel_rows(self):
        m, p = self.match, self.player
        return [
            ("lvl", f"Livello  {p.level}", "PagGiu/Su"),
            ("cd", "Ricariche azzerate", "F7", m.no_cd),
            ("gold", "Oro infinito", "F8", m.inf_gold),
            ("waves", "Ondate di minion", "F9", m.waves_on),
            ("reset", "Cura manichini", "F10"),
            ("home", "Torna in base", "Home"),
        ]

    def _draw_panel(self, surface):
        self._btns = []
        x, y = 10, 62
        if not self.panel_open:
            r = pygame.Rect(x, y, 150, 24)
            hud.panel(surface, r)
            hud.text(surface, "ALLENAMENTO  [F4]", (r.x + 8, r.y + 5), 12, hud.GOLD, bold=True)
            self._btns.append((r, "-"))
            return
        rows = self._panel_rows()
        h = 30 + len(rows) * ROW_H + 92
        R = pygame.Rect(x, y, PANEL_W, h)
        hud.panel(surface, R)
        self._btns.append((R, "-"))                 # il pannello consuma i clic
        hud.text(surface, "ALLENAMENTO", (R.x + 10, R.y + 7), 14, hud.GOLD, bold=True)
        hud.text(surface, "F4 nascondi", (R.right - 8, R.y + 9), 11, hud.DIM, right=True)
        mouse = pygame.mouse.get_pos()
        yy = R.y + 30
        for row in rows:
            act, label, key = row[0], row[1], row[2]
            rr = pygame.Rect(R.x + 6, yy, R.w - 12, ROW_H - 3)
            if act == "lvl":
                minus = pygame.Rect(rr.x + 2, rr.y + 2, 18, rr.h - 4)
                plus = pygame.Rect(rr.x + 112, rr.y + 2, 18, rr.h - 4)
                for b, s, a in ((minus, "-", "lvl-"), (plus, "+", "lvl+")):
                    hov = b.collidepoint(mouse)
                    pygame.draw.rect(surface, (44, 50, 62) if hov else (30, 34, 44), b,
                                     border_radius=3)
                    pygame.draw.rect(surface, hud.TRIM, b, 1, border_radius=3)
                    hud.text(surface, s, (b.centerx, b.y + 1), 14, hud.TEXT, bold=True,
                             center=True)
                    self._btns.append((b, a))
                hud.text(surface, label, (minus.right + 8, rr.y + 4), 13, hud.TEXT)
            else:
                hov = rr.collidepoint(mouse)
                if hov:
                    pygame.draw.rect(surface, (34, 40, 52), rr, border_radius=3)
                if len(row) > 3:                     # interruttore acceso/spento
                    on = row[3]
                    box = pygame.Rect(rr.x + 4, rr.y + 5, 12, 12)
                    pygame.draw.rect(surface, (18, 20, 26), box)
                    if on:
                        pygame.draw.rect(surface, ON, box.inflate(-4, -4))
                    pygame.draw.rect(surface, ON if on else OFF, box, 1)
                    hud.text(surface, label, (box.right + 8, rr.y + 4), 13,
                             hud.TEXT if on else OFF)
                else:
                    hud.text(surface, "> " + label, (rr.x + 4, rr.y + 4), 13, hud.TEXT)
                self._btns.append((rr, act))
            hud.text(surface, key, (rr.right - 4, rr.y + 5), 11, hud.DIM, right=True)
            yy += ROW_H
        # Misuratore del danno.
        pygame.draw.line(surface, (60, 56, 40), (R.x + 8, yy + 2), (R.right - 8, yy + 2))
        m = self.match
        hud.text(surface, "DANNO AI MANICHINI", (R.x + 10, yy + 8), 12, hud.GOLD, bold=True)
        cols = (("Totale", f"{m.dmg_total:,.0f}".replace(",", ".")),
                ("Ultimo colpo", f"{m.dmg_last:,.0f}".replace(",", ".")),
                ("DPS (5 s)", f"{m.dps():,.0f}".replace(",", ".")))
        for i, (k, v) in enumerate(cols):
            ly = yy + 26 + i * 18
            hud.text(surface, k, (R.x + 12, ly), 13, hud.DIM)
            hud.text(surface, v, (R.right - 12, ly), 13, (255, 236, 190), bold=True, right=True)
