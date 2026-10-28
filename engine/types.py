"""Tipi ed efficacia dei tipi.

Puro: carica la tabella da data/types.json e calcola il moltiplicatore di danno
di un tipo attaccante contro uno o più tipi difensori.
"""
from __future__ import annotations

import json
from pathlib import Path


class TypeChart:
    def __init__(self, table: dict[str, dict[str, float]]):
        self.table = table

    @classmethod
    def load(cls, path: str | Path) -> "TypeChart":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        table = {k: v for k, v in data.items() if not k.startswith("_")}
        return cls(table)

    def multiplier(self, attack_type: str, defender_types) -> float:
        """Moltiplicatore totale del tipo attaccante contro i tipi del difensore.

        Es: Fuoco contro [Erba, Veleno] = 2 (super vs Erba) * 1 (vs Veleno) = 2.
        Un tipo attaccante assente in tabella (o None) vale 1 (neutro).
        """
        if not attack_type:
            return 1.0
        row = self.table.get(attack_type, {})
        mult = 1.0
        for d in (defender_types or []):
            mult *= row.get(d, 1.0)
        return mult

    def moba_multiplier(self, attack_type: str, defender_types) -> float:
        """Efficacia compressa stile MOBA (punto 7): per ciascun tipo difensore
        superefficace ×1,25, poco efficace ×0,8, immunita' ×0,6; con doppio tipo
        i valori si moltiplicano, ma il totale resta tra ×0,6 e ×1,5.
        """
        from .stats import (TYPE_IMMUNE, TYPE_MAX, TYPE_MIN, TYPE_SUPER,
                            TYPE_WEAK)
        if not attack_type:
            return 1.0
        row = self.table.get(attack_type, {})
        mult = 1.0
        for d in (defender_types or []):
            raw = row.get(d, 1.0)
            if raw == 0.0:
                mult *= TYPE_IMMUNE
            elif raw > 1.0:
                mult *= TYPE_SUPER
            elif raw < 1.0:
                mult *= TYPE_WEAK
        return max(TYPE_MIN, min(TYPE_MAX, mult))
