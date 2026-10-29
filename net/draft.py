"""DRAFT della partita online: chi sceglie il Pokémon, in che ordine.

Solo logica pura (niente rete, niente pygame): la usa l'host (net/host.py) e la
testano i test. In giocatore singolo non c'è draft: il Pokémon si sceglie prima
(game/scenes/char_select_scene.py).

ORDINE
- 3v3: uno a testa, comincia il primo BLU      B1 R1 B2 R2 B3 R3
- 5v5: stile LoL, uno-due-due-due-due-uno     B1 R1 R2 B2 B3 R3 R4 B4 B5 R5
In ogni squadra le posizioni 1..k vanno ai k giocatori umani (in ordine di
slot), le altre ai BOT: i turni dei bot si saltano e, quando tutti gli umani
hanno scelto, i bot prendono TUTTI INSIEME un Pokémon a caso fra quelli rimasti.
Un Pokémon si può prendere una volta sola in tutta la partita.
"""
from __future__ import annotations

import random

PICK_TIME = 30.0          # s per scegliere; scaduto si prende l'anteprima o uno a caso
DONE_TIME = 3.0           # s in cui si mostra il draft completo prima di caricare

ORDERS = {
    3: [0, 1, 0, 1, 0, 1],
    5: [0, 1, 1, 0, 0, 1, 1, 0, 0, 1],
}


def pick_order(team_size: int) -> list:
    """[(squadra, posizione nella squadra)] nell'ordine di scelta."""
    teams = ORDERS.get(team_size) or [k % 2 for k in range(2 * team_size)]
    seen = [0, 0]
    out = []
    for t in teams:
        out.append((t, seen[t]))
        seen[t] += 1
    return out


class Draft:
    """entries: una per posizione, nell'ordine di scelta:
    {"team", "pos", "slot" (indice slot dell'umano o None = bot), "poke" (o None)}."""

    def __init__(self, team_size, humans, roster_size, now=0.0, rng=None):
        """humans: {squadra: [indici di slot in ordine]}."""
        self.roster_size = roster_size
        self.rng = rng or random.Random()
        self.entries = []
        for team, pos in pick_order(team_size):
            mine = humans.get(team, [])
            self.entries.append({"team": team, "pos": pos,
                                 "slot": mine[pos] if pos < len(mine) else None,
                                 "poke": None})
        self.turn = None          # indice in entries di chi sceglie ora (None = umani finiti)
        self.hover = None         # anteprima di chi sceglie
        self.deadline = 0.0
        self.done = False
        self._next(now)

    # --- stato -------------------------------------------------------------------
    def taken(self) -> set:
        return {e["poke"] for e in self.entries if e["poke"] is not None}

    def free(self) -> list:
        t = self.taken()
        return [i for i in range(self.roster_size) if i not in t]

    def current_slot(self):
        return None if self.turn is None else self.entries[self.turn]["slot"]

    def time_left(self, now) -> float:
        return max(0.0, self.deadline - now) if self.turn is not None else 0.0

    # --- azioni ------------------------------------------------------------------
    def hover_pick(self, slot, poke) -> bool:
        if slot is None or slot != self.current_slot() or poke not in self.free():
            return False
        self.hover = poke
        return True

    def lock(self, slot, poke, now) -> bool:
        if not self.hover_pick(slot, poke):
            return False
        self.entries[self.turn]["poke"] = poke
        self._next(now)
        return True

    def tick(self, now) -> bool:
        """Tempo scaduto: si prende l'anteprima (se libera) o uno a caso. True se cambia."""
        if self.turn is None or now < self.deadline:
            return False
        free = self.free()
        poke = self.hover if self.hover in free else self.rng.choice(free)
        self.entries[self.turn]["poke"] = poke
        self._next(now)
        return True

    def drop_slot(self, slot, now) -> bool:
        """Il giocatore dello slot se n'è andato: la sua posizione diventa un bot
        (tiene il Pokémon se l'aveva già scelto). True se cambia."""
        changed = False
        for k, e in enumerate(self.entries):
            if e["slot"] == slot:
                e["slot"] = None
                changed = True
                if k == self.turn:
                    self._next(now)
        return changed

    def _next(self, now) -> None:
        self.hover = None
        for k, e in enumerate(self.entries):
            if e["slot"] is not None and e["poke"] is None:
                self.turn = k
                self.deadline = now + PICK_TIME
                return
        self.turn = None
        # Umani finiti: i bot prendono tutti insieme un Pokémon a caso fra i rimasti.
        free = self.free()
        self.rng.shuffle(free)
        for e in self.entries:
            if e["poke"] is None:
                e["poke"] = free.pop() if free else self.rng.randrange(self.roster_size)
        self.done = True
