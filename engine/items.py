"""Catalogo oggetti e logica del negozio (puro).

Gli oggetti sono data-driven (data/items.json). I bonus sono placeholder: qui
conta la MECCANICA (prezzo, combinazione dei componenti con sconto, somma dei
bonus). Gli effetti unici (rigen, scudo-letale, danno di ritorno...) arriveranno
dopo, item per item.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ITEM_SLOTS = 6   # tetto di oggetti per Pokémon


@dataclass
class ItemDef:
    id: str
    name: str
    price: int
    build_from: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    note: str = ""
    is_base: bool = True


class ItemCatalog:
    def __init__(self, items: dict, base_ids, completed_ids, recommended):
        self.items = items
        self.base_ids = base_ids
        self.completed_ids = completed_ids
        self.recommended = recommended

    @classmethod
    def load(cls, path: str | Path) -> "ItemCatalog":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        items = {}
        base_ids, comp_ids = [], []
        for d in data.get("base", []):
            items[d["id"]] = ItemDef(d["id"], d["name"], int(d["price"]),
                                     list(d.get("build_from", [])), dict(d.get("stats", {})),
                                     d.get("note", ""), is_base=True)
            base_ids.append(d["id"])
        for d in data.get("completed", []):
            items[d["id"]] = ItemDef(d["id"], d["name"], int(d["price"]),
                                     list(d.get("build_from", [])), dict(d.get("stats", {})),
                                     d.get("note", ""), is_base=False)
            comp_ids.append(d["id"])
        return cls(items, base_ids, comp_ids, dict(data.get("recommended", {})))

    def get(self, item_id):
        return self.items.get(item_id)

    def components_in(self, item_id, owned_ids):
        """Componenti posseduti che verrebbero consumati (ognuno una volta)."""
        it = self.items.get(item_id)
        if it is None:
            return []
        owned = list(owned_ids)
        consumed = []
        for comp in it.build_from:
            if comp in owned:
                owned.remove(comp)
                consumed.append(comp)
        return consumed

    def effective_price(self, item_id, owned_ids) -> int:
        """Prezzo da pagare scontando i componenti già posseduti."""
        it = self.items.get(item_id)
        if it is None:
            return 0
        discount = sum(self.items[c].price for c in self.components_in(item_id, owned_ids)
                       if c in self.items)
        return max(0, it.price - discount)

    def total_bonus(self, owned_ids) -> dict:
        """Somma dei bonus statistici di tutti gli oggetti posseduti."""
        bonus: dict[str, float] = {}
        for oid in owned_ids:
            it = self.items.get(oid)
            if it is None:
                continue
            for k, v in it.stats.items():
                bonus[k] = bonus.get(k, 0.0) + float(v)
        return bonus

    def sell_value(self, item_id) -> int:
        it = self.items.get(item_id)
        return int(it.price * 0.6) if it else 0   # rivendita al 60%

    def recommended_for(self, role: str):
        return self.recommended.get(role, self.recommended.get("default", []))
