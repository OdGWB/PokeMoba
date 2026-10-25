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
