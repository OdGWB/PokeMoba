"""Visione e nebbia di guerra (puro, riusabile dal server in Fase 5).

Per ogni squadra calcola:
  - i tile attualmente visibili (unione dei raggi visivi di unità e strutture
    alleate vive);
  - i tile già esplorati (memoria persistente: terreno noto ma non più visibile);
  - gli ID delle UNITÀ nemiche attualmente visibili.

Regole:
  - Raggio visivo per entità (campo `vision`): Pokémon 9, torri 12, minion 6.
  - Cespugli (TILE_BUSH): un nemico dentro un cespuglio è invisibile ai nemici
    fuori, a meno che un alleato non sia vicino (ci "sbircia" dentro) o che sia
    AGITATO (passiva Quiete della linea Hatenna: lo agitano solo i nemici).
  - Le strutture non vengono nascoste (sono elementi fissi noti della mappa);
    la nebbia nasconde solo le unità nemiche.

Prestazioni: il calcolo viene rifatto SOLO quando una fonte di visione cambia
tile (o compare/sparisce); il disegno della nebbia è a parte, nel client.
I tile visibili ed esplorati sono MASCHERE numpy (righe = y, colonne = x): ogni
fonte "timbra" un disco precalcolato del suo raggio, invece di aggiungere a un
insieme Python tile per tile (in un 5v5 con le ondate era ~1/5 del frame).
"""
from __future__ import annotations

import numpy as np

from .entities import Structure, Unit
from .grid import TILE_BUSH

BUSH_REVEAL = 2.6   # tile: un alleato entro questa distanza rivela il nemico nel cespuglio

_DISCS: dict = {}


def _disc(r: int):
    """Disco di raggio r tile (dx*dx + dy*dy <= r*r), lato 2r+1, in cache."""
    d = _DISCS.get(r)
    if d is None:
        k = np.arange(-r, r + 1)
        d = _DISCS[r] = (k[None, :] ** 2 + k[:, None] ** 2) <= r * r
    return d


class TileMask:
    """Maschera booleana di tile (mask[y, x]) che si interroga come un insieme di
    coppie (x, y): `(x, y) in m`, `len(m)` (tile accesi), `bool(m)`."""
    __slots__ = ("mask",)

    def __init__(self, mask):
        self.mask = mask

    def __contains__(self, xy) -> bool:
        x, y = xy
        h, w = self.mask.shape
        return 0 <= x < w and 0 <= y < h and bool(self.mask[y, x])

    def __len__(self) -> int:
        return int(np.count_nonzero(self.mask))

    def __bool__(self) -> bool:
        return bool(self.mask.any())


class VisionSystem:
    def __init__(self, grid):
        self.grid = grid
        self.visible_tiles: dict[int, TileMask] = {}
        self.explored: dict[int, TileMask] = {}
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
        # Quiete (Hatenna): un nemico agitato in un cespuglio resta visibile, quindi
        # chi si agita/calma (o si muove agitato) cambia la visione.
        sig |= frozenset(("agi", u.id, int(u.pos.x), int(u.pos.y))
                         for u in world.entities.values()
                         if getattr(u, "agitated", False) and getattr(u, "team", team) != team)
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
        vm = np.zeros((h, w), dtype=bool)
        for e in sources:
            cx, cy = int(e.pos.x), int(e.pos.y)
            r = int(getattr(e, "vision", 0))
            x0, x1 = max(0, cx - r), min(w, cx + r + 1)
            y0, y1 = max(0, cy - r), min(h, cy + r + 1)
            if x0 >= x1 or y0 >= y1:
                continue
            d = _disc(r)
            vm[y0:y1, x0:x1] |= d[y0 - (cy - r):y1 - (cy - r), x0 - (cx - r):x1 - (cx - r)]
        self.visible_tiles[team] = TileMask(vm)
        exp = self.explored.get(team)
        if exp is None or exp.mask.shape != vm.shape:
            self.explored[team] = TileMask(vm.copy())
        else:
            exp.mask |= vm

        # Unità nemiche visibili (con la regola dei cespugli).
        enemies: set = set()
        for u in world.entities.values():
            if not isinstance(u, Unit) or u.team == team or not u.alive:
                continue
            tx, ty = int(u.pos.x), int(u.pos.y)
            if any((u.pos.x - x) ** 2 + (u.pos.y - y) ** 2 <= r * r for x, y, r in reveals):
                enemies.add(u.id)   # ping: visibile anche in nebbia, cespuglio o invisibile
                continue
            if not (0 <= tx < w and 0 <= ty < h) or not vm[ty, tx]:
                continue
            if getattr(u, "invisible", False):   # Memento: invisibile ai nemici
                continue
            if self.grid.tile_at(tx, ty) == TILE_BUSH and not getattr(u, "agitated", False):
                # Visibile solo se un alleato è vicino (ci sbircia dentro).
                if not any(e.pos.dist(u.pos) <= BUSH_REVEAL for e in sources):
                    continue
            enemies.add(u.id)
        self.visible_enemies[team] = enemies
        return True

    # --- interrogazioni ------------------------------------------------------
    def is_tile_visible(self, team: int, x: int, y: int) -> bool:
        v = self.visible_tiles.get(team)
        return v is not None and (x, y) in v

    def is_tile_explored(self, team: int, x: int, y: int) -> bool:
        e = self.explored.get(team)
        return e is not None and (x, y) in e

    def is_enemy_visible(self, team: int, unit_id: int) -> bool:
        return unit_id in self.visible_enemies.get(team, ())
