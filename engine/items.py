"""Catalogo oggetti e logica del negozio (puro).

Gli oggetti sono data-driven (data/items.json) su 3 livelli: vitamine ->
intermedi -> completi. Qui ci sono prezzo, combinazione dei componenti (anche
annidati: chi possiede una Proteina la sconta da una Fascia Scelta), somma dei
bonus statistici e le regole di possesso (gruppi Scelta/scarpe/Condividi Esp.).
Gli effetti unici degli oggetti sono in engine/item_effects.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ITEM_SLOTS = 6   # tetto di oggetti per Pokémon

# Gruppi a possesso limitato: al massimo un oggetto del gruppo per Pokémon
# (exp_share: al massimo uno per SQUADRA, controllato dal Match).
LIMITED_GROUPS = ("choice", "boots", "exp_share")


@dataclass
class ItemDef:
    id: str
    name: str
    price: int
    build_from: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    note: str = ""
    is_base: bool = True
    tier: int = 1
    category: str = ""
    group: str = ""
    icon: str = ""
    active: bool = False


class ItemCatalog:
    def __init__(self, items: dict, base_ids, completed_ids, recommended,
                 intermediate_ids=None, categories=None):
        self.items = items
        self.base_ids = base_ids
        self.intermediate_ids = list(intermediate_ids or [])
        self.completed_ids = completed_ids
        self.recommended = recommended
        self.categories = list(categories or [])   # [(id, etichetta)] = schede del negozio

    @classmethod
    def load(cls, path: str | Path) -> "ItemCatalog":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        items = {}
        lists = {"base": [], "intermediate": [], "completed": []}
        for tier, key in enumerate(("base", "intermediate", "completed"), start=1):
            for d in data.get(key, []):
                items[d["id"]] = ItemDef(d["id"], d["name"], int(d["price"]),
                                         list(d.get("build_from", [])),
                                         dict(d.get("stats", {})), d.get("note", ""),
                                         is_base=(tier == 1), tier=tier,
                                         category=d.get("category", key),
                                         group=d.get("group", ""), icon=d.get("icon", ""),
                                         active=bool(d.get("active", False)))
                lists[key].append(d["id"])
        cats = [tuple(c) for c in data.get("categories", [])]
        return cls(items, lists["base"], lists["completed"],
                   dict(data.get("recommended", {})), lists["intermediate"], cats)

    def get(self, item_id):
        return self.items.get(item_id)

    def in_category(self, cat: str) -> list:
        return [i for i in self.base_ids + self.intermediate_ids + self.completed_ids
                if self.items[i].category == cat]

    def components_in(self, item_id, owned_ids):
        """Componenti posseduti che verrebbero consumati (ognuno una volta).

        Si scende nell'albero: un componente non posseduto viene cercato nei
        SUOI componenti (es. Fascia Scelta <- Muscolbanda <- Proteina)."""
        it = self.items.get(item_id)
        if it is None:
            return []
        owned = list(owned_ids)
        consumed = []

        def take(cid):
            if cid in owned:
                owned.remove(cid)
                consumed.append(cid)
                return
            sub = self.items.get(cid)
            if sub is not None:
                for c in sub.build_from:
                    take(c)

        for comp in it.build_from:
            take(comp)
        return consumed

    def effective_price(self, item_id, owned_ids) -> int:
        """Prezzo da pagare scontando i componenti già posseduti."""
        it = self.items.get(item_id)
        if it is None:
            return 0
        discount = sum(self.items[c].price for c in self.components_in(item_id, owned_ids)
                       if c in self.items)
        return max(0, it.price - discount)

    def group_ok(self, item_id, owned_ids) -> bool:
        """Regola "al massimo uno" del gruppo (Scelta, scarpe, Condividi Esp.),
        contando che i componenti consumati dall'acquisto spariscono."""
        it = self.items.get(item_id)
        if it is None or not it.group:
            return True
        left = list(owned_ids)
        for c in self.components_in(item_id, owned_ids):
            left.remove(c)
        return not any(self.items[o].group == it.group for o in left if o in self.items)

    def total_bonus(self, owned_ids, skip=()) -> dict:
        """Somma dei bonus statistici degli oggetti posseduti (tranne `skip`)."""
        bonus: dict[str, float] = {}
        for oid in owned_ids:
            it = self.items.get(oid)
            if it is None or oid in skip:
                continue
            for k, v in it.stats.items():
                bonus[k] = bonus.get(k, 0.0) + float(v)
        return bonus

    def sell_value(self, item_id) -> int:
        it = self.items.get(item_id)
        return int(it.price * 0.6) if it else 0   # rivendita al 60%

    def recommended_for(self, role: str):
        return self.recommended.get(role, self.recommended.get("default", []))
