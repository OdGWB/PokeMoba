"""Evoluzioni e scelta dei potenziamenti.

Puro. L'evoluzione (cambio stadio: nome, dex, statistiche, dimensione) avviene
quando il livello raggiunge la soglia dello stadio. La scelta dei potenziamenti
(stile Pokémon Unite) e dell'ultimate R è gestita a parte dal Match.
"""
from __future__ import annotations

from . import skills


def _requires_met(p, st) -> bool:
    """Valuta la condizione di una ramificazione d'evoluzione.

    Senza `requires` è il ramo di DEFAULT (vero). Condizioni supportate:
      {"has_item": "<id>"}  -> vero se l'oggetto è nell'inventario.
    La decisione si congela al momento dell'evoluzione (lo stadio sale e non
    si rivaluta più): comprare/vendere l'oggetto dopo non cambia nulla.
    """
    req = st.get("requires")
    if not req:
        return True
    need = req.get("has_item")
    if need is not None and need not in getattr(p, "items", []):
        return False
    return True


def check_evolution(p) -> bool:
    """Porta il Pokémon allo stadio più alto consentito dal suo livello.

    Supporta le EVOLUZIONI RAMIFICATE: più voci possono condividere lo stesso
    `stage` (stesso livello) con una `requires` diversa; si sceglie il ramo con
    condizione soddisfatta, altrimenti il ramo senza `requires` (default).

    Ritorna True se lo stadio è cambiato (il Match ricalcola le statistiche).
    """
    if not p.evolutions:
        return False
    target = p.stage
    for st in p.evolutions:
        if p.level >= st.get("level", 1) and st.get("stage", 0) > target:
            target = st["stage"]
    if target == p.stage:
        return False
    # Tra le voci dello stadio bersaglio, scegli il ramo adatto: prima una
    # ramificazione con `requires` soddisfatta, altrimenti il default.
    cands = [st for st in p.evolutions if st.get("stage", 0) == target]
    st = next((c for c in cands if c.get("requires") and _requires_met(p, c)), None)
    if st is None:
        st = next((c for c in cands if _requires_met(p, c)), None)
    if st is None:
        return False
    p.stage = target
    p.name = st.get("name", p.name)
    p.dex = st.get("dex", p.dex)
    p.stat_mult = float(st.get("stat_mult", p.stat_mult))
    p.radius = float(st.get("radius", p.radius))
    # Campi d'identità che possono cambiare con la forma (ramo scelto).
    if "passive" in st:
        p.passive_id = st["passive"]
    if "role" in st:
        p.role = st["role"]
    if "color" in st:
        p.color = tuple(st["color"])
    if "attack_fx" in st:
        p.attack_fx = st["attack_fx"]
    if "attack_range" in st:
        p.attack_range = float(st["attack_range"])
    # Mosse specifiche della forma (ramo scelto): es. la R di Politoad è diversa
    # da quella di Poliwrath. Ricostruisce solo gli slot elencati, conservando il
    # grado/sblocco già raggiunti.
    if "moves" in st:
        from .moves import build_moveset
        for slot, slot_obj in build_moveset(st["moves"]).items():
            old = p.moveset.get(slot)
            if old is not None:
                slot_obj.rank = old.rank
                slot_obj.unlocked = old.unlocked
                slot_obj.cooldown_remaining = old.cooldown_remaining
            p.moveset[slot] = slot_obj
    # Il tipo può cambiare con l'evoluzione (es. Poliwhirl Acqua -> Poliwrath
    # Acqua/Lotta): aggiorna debolezze, STAB ed effetti del meteo.
    if "types" in st:
        p.types = list(st["types"])
    # Statistiche base REALI proprie della forma evoluta (se definite nel JSON):
    # il Match ricalcola tutte le stat derivate da queste. La classe di gittata
    # puo' cambiare con la forma (aggiorna la penalita' AD ranged).
    if "base_stats" in st:
        from .stats import Stats, range_class
        p.base_stats = Stats.from_dict(st["base_stats"])
        if "ranged" in st:
            p.ranged = bool(st["ranged"])
        else:
            p.ranged = range_class(p.base_stats) == "ranged"
    return True


def apply_choice(p, slot: str, index: int) -> bool:
    """Applica la scelta del potenziamento (o ultimate) per uno slot.

    Il grado della mossa si conserva (cambia solo la variante). Per la R,
    scegliere l'ultimate sblocca lo slot.
    """
    ms = p.moveset.get(slot)
    if ms is None or not ms.upgrades:
        return False
    if slot not in p.pending_choices:
        return False
    index = max(0, min(index, len(ms.upgrades) - 1))
    ms.chosen = ms.upgrades[index]
    if slot == "R":
        ms.unlocked = True
    p.pending_choices.remove(slot)
    skills._apply_passive(p)
    return True
