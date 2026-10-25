"""Evoluzioni e scelta dei potenziamenti.

Puro. L'evoluzione (cambio stadio: nome, dex, statistiche, dimensione) avviene
quando il livello raggiunge la soglia dello stadio. La scelta dei potenziamenti
(stile Pokémon Unite) e dell'ultimate R è gestita a parte dal Match.
"""
from __future__ import annotations

from . import skills


def check_evolution(p) -> bool:
    """Porta il Pokémon allo stadio più alto consentito dal suo livello.

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
    st = p.evolutions[target]
    p.stage = target
    p.name = st.get("name", p.name)
    p.dex = st.get("dex", p.dex)
    p.stat_mult = float(st.get("stat_mult", p.stat_mult))
    p.radius = float(st.get("radius", p.radius))
    # Il tipo può cambiare con l'evoluzione (es. Dartrix Erba/Volante -> Decidueye
    # Erba/Spettro): aggiorna debolezze, STAB ed effetti del meteo.
    if "types" in st:
        p.types = list(st["types"])
    # Statistiche proprie della forma evoluta (se definite nel JSON).
    if "base_stats" in st:
        from .stats import Stats
        p.base_stats = Stats.from_dict(st["base_stats"])
        if "growth" in st:
            p.growth = Stats.from_dict(st["growth"])
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
