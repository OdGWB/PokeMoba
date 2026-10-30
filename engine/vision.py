"""Visione e nebbia di guerra (puro, riusabile dal server in Fase 5).

Per ogni squadra calcola:
  - i tile attualmente visibili (unione dei raggi visivi di unità e strutture
    alleate vive);
  - i tile già esplorati (memoria persistente: terreno noto ma non più visibile);
  - gli ID delle UNITÀ nemiche attualmente visibili.

Regole:
  - Raggio visivo per entità (campo `vision`): Pokémon 9, torri 12, minion 6.
  - Cespugli (TILE_BUSH): un nemico dentro un cespuglio è invisibile ai nemici
    fuori, a meno che un alleato non sia vicino (ci "sbircia" dentro).
  - Le strutture non vengono nascoste (sono elementi fissi noti della mappa);
    la nebbia nasconde solo le unità nemiche.

Prestazioni: il calcolo (costoso) viene rifatto SOLO quando una fonte di visione
cambia tile (o compare/sparisce); il disegno della nebbia è a parte, nel client.
"""
from __future__ import annotations

from .entities import Structure, Unit
from .grid import TILE_BUSH

BUSH_REVEAL = 2.6   # tile: un alleato entro questa distanza rivela il nemico nel cespuglio


class VisionSystem:
    def __init__(self, grid):
        self.grid = grid
        self.visible_tiles: dict[int, set] = {}
        self.explored: dict[int, set] = {}
        self.visible_enemies: dict[int, set] = {}
        self.version: dict[int, int] = {}   # incrementa a ogni ricalcolo (per cache UI)
        self._sig: dict[int, frozenset] = {}
        # Zone che rivelano i nemici nascosti (ping di Ecolocalizzazione):
        # squadra -> lista di (x, y, raggio). Le imposta chi possiede la visione
        # (Match o scena online) prima di update().
        self.reveals: dict[int, list] = {}

    def _sources(self, world, team):
        out = []
        for e in world.entities.values():
            if getattr(e, "team", None) != team or not getattr(e, "alive", False):
                continue
            if isinstance(e, (Unit, Structure)) and getattr(e, "vision", 0) > 0:
                out.append(e)
        return out

    def update(self, world, team: int) -> bool:
        """Ricalcola la visione della squadra se qualcosa è cambiato.

        Ritorna True se ha ricalcolato (una fonte ha cambiato tile / è
        comparsa o sparita), False se nulla è cambiato.
        """
        sources = self._sources(world, team)
        sig = frozenset((e.id, int(e.pos.x), int(e.pos.y), int(getattr(e, "vision", 0)))
                        for e in sources)
        # Memento (Spiritomb): chi diventa/smette di essere invisibile cambia la
        # visione nemica anche senza muoversi di tile.
        sig |= frozenset(("inv", e.id) for e in world.entities.values()
                         if getattr(e, "invisible", False) and getattr(e, "team", team) != team)
        # Ping attivi: i nemici dentro si muovono senza cambiare la firma delle
        # fonti, quindi finché ce n'è uno si ricalcola a ogni aggiornamento.
        reveals = self.reveals.get(team) or ()
        if reveals:
            sig |= frozenset(("ping", round(x, 1), round(y, 1), r) for x, y, r in reveals)
            sig |= frozenset(("pos", u.id, int(u.pos.x), int(u.pos.y))
                             for u in world.entities.values()
                             if isinstance(u, Unit) and u.team != team and u.alive)
        if sig == self._sig.get(team):
            return False
        self._sig[team] = sig
        self.version[team] = self.version.get(team, 0) + 1

        w, h = self.grid.width, self.grid.height
        vis: set = set()
        for e in sources:
            cx, cy = int(e.pos.x), int(e.pos.y)
            r = int(getattr(e, "vision", 0))
            r2 = r * r
            for y in range(max(0, cy - r), min(h, cy + r + 1)):
                dy = y - cy
                for x in range(max(0, cx - r), min(w, cx + r + 1)):
                    dx = x - cx
                    if dx * dx + dy * dy <= r2:
                        vis.add((x, y))
        self.visible_tiles[team] = vis
        exp = self.explored.setdefault(team, set())
        exp |= vis

        # Unità nemiche visibili (con la regola dei cespugli).
        enemies: set = set()
        for u in world.entities.values():
            if not isinstance(u, Unit) or u.team == team or not u.alive:
                continue
            tx, ty = int(u.pos.x), int(u.pos.y)
            if any((u.pos.x - x) ** 2 + (u.pos.y - y) ** 2 <= r * r for x, y, r in reveals):
                enemies.add(u.id)   # ping: visibile anche in nebbia, cespuglio o invisibile
                continue
            if (tx, ty) not in vis:
                continue
            if getattr(u, "invisible", False):   # Memento: invisibile ai nemici
                continue
            if self.grid.tile_at(tx, ty) == TILE_BUSH:
                # Visibile solo se un alleato è vicino (ci sbircia dentro).
                if not any(e.pos.dist(u.pos) <= BUSH_REVEAL for e in sources):
                    continue
            enemies.add(u.id)
        self.visible_enemies[team] = enemies
        return True

    # --- interrogazioni ------------------------------------------------------
    def is_tile_visible(self, team: int, x: int, y: int) -> bool:
        return (x, y) in self.visible_tiles.get(team, ())

    def is_tile_explored(self, team: int, x: int, y: int) -> bool:
        return (x, y) in self.explored.get(team, ())

    def is_enemy_visible(self, team: int, unit_id: int) -> bool:
        return unit_id in self.visible_enemies.get(team, ())
