"""Statistiche, livelli ed esperienza.

Puro: nessun pygame. Il modello deriva TUTTE le statistiche di gioco (stile
MOBA/LoL) dalle 6 statistiche base REALI del Pokémon (HP, Att, Dif, Att.Sp,
Dif.Sp, Vel), uguali per ogni personaggio. La pipeline e':

    stat base reale --(normalizzazione sul BST)--> valore "efficace" (eff)
    eff --(conversioni + crescita per livello)--> HP, AD, armatura, RM, mana...

La normalizzazione (budget sul BST, amplificazione con pavimento morbido,
compressione) comprime la forbice tra Pokémon forti e deboli senza gonfiare i
BST bassissimi (Shedinja). Da li' in poi ogni statistica ha una conversione
diretta o una formula dedicata.

NOTE DI FASE (vedi CLAUDE.md "Stat"):
- Questa fase implementa il MOTORE delle statistiche (punti 1-5 della spec) e lo
  aggancia a HP / AD / armatura (defense) / RM (sp_defense) / livello / velocita'.
- Mana, AP, critico, penetrazione, letalita', tenacia, ability haste e le nuove
  formule di combattimento (STAB 1.15, tipi, ecc.) sono CALCOLATI e memorizzati
  ma NON ancora consumati dal combattimento: verranno collegati nel passo
  successivo. Per non rompere le abilita' esistenti, `Stats.sp_attack` porta
  ancora un "potere speciale" TRANSITORIO (vedi `_special_power`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Variante a 16 livelli (scelta di progetto): tutte le CRESCITE sono ×17/15
# rispetto alla variante a 18 livelli; i valori di partenza (livello 1) no.
MAX_LEVEL = 16
GROWTH_SCALE = 17.0 / 15.0

# STAB del combattimento (nuovo modello MOBA: +15%).
STAB_MULT = 1.15

# Critico ed efficacia dei tipi (modello MOBA compresso).
CRIT_MULT = 1.75          # danno × 1,75 su un critico
HIGH_CRIT_CHANCE = 0.25   # critico innato delle mosse "ad alto tasso di critico"
TYPE_SUPER = 1.25         # superefficace (per tipo)
TYPE_WEAK = 0.8           # poco efficace (per tipo)
TYPE_IMMUNE = 0.6         # "immunita'" ammorbidita (per tipo)
TYPE_MIN = 0.6            # tetti del moltiplicatore totale di tipo
TYPE_MAX = 1.5

# Tetti e conversioni della velocita'.
MS_CAP = 365.0            # movement speed massimo (unita' "LoL")
AS_CAP = 2.5              # attacchi al secondo massimo
# La movement speed e' espressa in unita' LoL (315-365); il gioco ragiona in
# tile/secondo. Fattore scelto per restare vicino alle velocita' attuali
# (~3.5-3.8 tile/s). Tarabile senza toccare le formule.
MS_TO_TILES = 1.0 / 95.0

# Statistiche considerate (nomi dei campi di Stats).
STAT_NAMES = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]


@dataclass
class Stats:
    """Bundle "vivo" consumato dal motore a un certo livello.

    Dopo la derivazione i campi NON sono piu' le stat Pokémon ma le stat di
    gioco: hp = Vita, attack = AD, defense = Armatura, sp_defense = Resistenza
    magica, speed = Movement Speed (tile/s), sp_attack = potere speciale
    transitorio (vedi nota di fase). Nei JSON invece `base_stats` sono le 6 stat
    base REALI del Pokémon, da cui tutto viene derivato.
    """
    hp: float = 100.0
    attack: float = 10.0
    defense: float = 10.0
    sp_attack: float = 10.0
    sp_defense: float = 10.0
    speed: float = 10.0

    @classmethod
    def from_dict(cls, d: dict) -> "Stats":
        return cls(**{k: float(d.get(k, 0.0)) for k in STAT_NAMES})


# --- 1) Normalizzazione sul BST ---------------------------------------------
def _normalize_one(base: float, bst: float) -> float:
    """Porta una stat base reale al suo valore "efficace".

    1. Budget:          n  = base × min(1,35, 600 / BST)
    2. Amplificazione:  n' = max(100 + (n − 100) × 1,6, 25 + n/2)   (pavimento morbido)
    3. Compressione:    eff = 100 × (n'/100)^0,6
    """
    if bst <= 0:
        bst = 1.0
    n = base * min(1.35, 600.0 / bst)
    n2 = max(100.0 + (n - 100.0) * 1.6, 25.0 + n / 2.0)
    return 100.0 * (n2 / 100.0) ** 0.6


@dataclass
class EffStats:
    """Le 6 stat base dopo la normalizzazione (valori "efficaci")."""
    hp: float
    attack: float
    defense: float
    sp_attack: float
    sp_defense: float
    speed: float


def bst(base: Stats) -> float:
    """Somma delle 6 statistiche base ORIGINALI."""
    return sum(getattr(base, k) for k in STAT_NAMES)


def normalize(base: Stats) -> EffStats:
    b = bst(base)
    return EffStats(
        hp=_normalize_one(base.hp, b),
        attack=_normalize_one(base.attack, b),
        defense=_normalize_one(base.defense, b),
        sp_attack=_normalize_one(base.sp_attack, b),
        sp_defense=_normalize_one(base.sp_defense, b),
        speed=_normalize_one(base.speed, b),
    )


# --- 2/3) Stat base e crescita per livello ----------------------------------
def _grow(level1: float, growth_per_level: float, level: int) -> float:
    """Valore al livello L = livello1 + crescita × (L − 1). Crescita gia' ×17/15."""
    return level1 + growth_per_level * GROWTH_SCALE * (level - 1)


# --- 5) Gittata: classificazione di design ----------------------------------
# r = SpA / (Atk + SpA) sulle stat ORIGINALI (non normalizzate).
RANGE_MELEE = 175.0
RANGE_MID = 350.0
RANGE_RANGED = 550.0


def range_class(base: Stats) -> str:
    denom = base.attack + base.sp_attack
    r = 0.5 if denom <= 0 else base.sp_attack / denom
    if r < 0.4:
        return "melee"
    if r > 0.6:
        return "ranged"
    return "mid"


def range_units(cls: str) -> float:
    return {"melee": RANGE_MELEE, "ranged": RANGE_RANGED}.get(cls, RANGE_MID)


# --- Potere speciale TRANSITORIO (vedi nota di fase) -------------------------
def _special_power(spa_eff: float, level: int) -> float:
    """Potere speciale per livello, in attesa del sistema AP + moltiplicatore.

    Specchia la formula dell'AD sul lato speciale (senza penalita' ranged), cosi'
    le abilita' magiche continuano a scalare col livello finche' il passo
    combattimento non introdurra' `(base + ratio×AP) × moltiplicatore SpA`.
    """
    return _grow(32.0 + 0.25 * spa_eff, 1.0 + 0.03 * spa_eff, level)


@dataclass
class Derived:
    """Tutte le statistiche di gioco derivate a un dato livello."""
    stats: Stats                 # bundle vivo (hp/AD/armatura/RM/speed/sp_attack)
    # Velocita'
    move_speed_tiles: float
    attack_speed: float          # attacchi/secondo
    attack_cooldown: float       # secondi tra un attacco (= 1/attack_speed)
    # Risorsa (non ancora consumata)
    max_mana: float
    mana_regen5: float           # rigenerazione mana ogni 5s
    # Combattimento futuro
    ap: float                    # potere magico (0 base + oggetti)
    crit: float                  # probabilita' critico (0 base)
    ability_mult: float          # 0,6 + 0,004×SpA (moltiplica il danno abilita')
    # Identita'
    ranged: bool
    range_cls: str
    range_val: float
    tenacity: float              # 0..0,25
    hp_regen5: float             # rigenerazione HP ogni 5s
    flat_reduction: float        # riduzione danni fissa per colpo (0..8)
    lethality: float             # letalita' innata (0..5)
    lethality_physical: bool     # True = fisica, False = magica
    heal_power: float            # potere cure/scudi (1..1,35)


def derive(base: Stats, level: int, *, ranged: bool | None = None,
           range_override: str | None = None) -> Derived:
    """Deriva tutte le stat di gioco al livello L dalle 6 stat base reali."""
    level = max(1, min(MAX_LEVEL, level))
    eff = normalize(base)

    cls = range_override or range_class(base)
    is_ranged = range_class(base) == "ranged" if ranged is None else bool(ranged)

    # Conversioni dirette + crescita (crescite ×17/15 dentro _grow).
    hp = _grow(450.0 + 2.0 * eff.hp, 70.0 + 0.4 * eff.hp, level)
    ad1 = 32.0 + 0.25 * eff.attack
    if is_ranged:
        ad1 *= 0.95
    ad = _grow(ad1, 1.0 + 0.03 * eff.attack, level)
    armor = _grow(15.0 + 0.15 * eff.defense, 2.0 + 0.03 * eff.defense, level)
    mr = _grow(22.0 + 0.1 * eff.sp_defense, 0.3 + 0.02 * eff.sp_defense, level)
    spsum = eff.sp_attack + eff.sp_defense
    mana = _grow(250.0 + spsum, 25.0 + 0.1 * spsum, level)
    mana_regen5 = 5.0 + 0.03 * eff.sp_defense       # senza crescita per livello

    # Velocita'.
    ms = min(MS_CAP, 315.0 + 0.3 * eff.speed)
    as1 = 0.55 + 0.0015 * eff.speed
    as_growth_pct = (1.0 + 0.02 * eff.speed) * GROWTH_SCALE
    atk_speed = min(AS_CAP, as1 * (1.0 + as_growth_pct * (level - 1) / 100.0))

    # Stat derivate d'identita' (non crescono con il livello).
    avg_def = (eff.defense + eff.sp_defense) / 2.0
    ability_mult = 0.6 + 0.004 * eff.sp_attack
    tenacity = min(0.25, max(0.0, (avg_def - 90.0) * 0.005))
    d = eff.hp - avg_def
    hp_regen5 = 4.0 + 0.04 * eff.hp + max(0.0, d) * 0.05
    flat_reduction = min(8.0, (-d - 30.0) * 0.1) if d < -30.0 else 0.0
    g = max(eff.attack, eff.sp_attack) - avg_def
    lethality = min(5.0, (g - 30.0) * 0.1) if g > 30.0 else 0.0
    heal_power = min(1.35, 1.0 + max(0.0, eff.sp_defense - 80.0) * 0.005)

    stats = Stats(
        hp=hp, attack=ad, defense=armor,
        sp_attack=_special_power(eff.sp_attack, level),
        sp_defense=mr, speed=ms * MS_TO_TILES,
    )
    return Derived(
        stats=stats,
        move_speed_tiles=ms * MS_TO_TILES,
        attack_speed=atk_speed,
        attack_cooldown=1.0 / atk_speed if atk_speed > 0 else 1.0,
        max_mana=mana, mana_regen5=mana_regen5,
        ap=0.0, crit=0.0, ability_mult=ability_mult,
        ranged=is_ranged, range_cls=cls, range_val=range_units(cls),
        tenacity=tenacity, hp_regen5=hp_regen5, flat_reduction=flat_reduction,
        lethality=lethality, lethality_physical=(eff.attack >= eff.sp_attack),
        heal_power=heal_power,
    )


# --- Esperienza e livelli ----------------------------------------------------
def _cumulative_xp() -> list[float]:
    """XP totale per raggiungere ogni livello (indice = livello).

    Variante a 16 livelli: XP da L a L+1 = 200 + 130 × L (totale 18.600).
    """
    cum = [0.0, 0.0]  # livelli 0 e 1 a 0 XP
    total = 0.0
    for lvl in range(1, MAX_LEVEL):
        need = 200.0 + 130.0 * lvl
        total += need
        cum.append(total)
    return cum


CUMULATIVE_XP = _cumulative_xp()


def level_from_xp(xp: float) -> int:
    lvl = 1
    for L in range(1, MAX_LEVEL + 1):
        if xp >= CUMULATIVE_XP[L]:
            lvl = L
        else:
            break
    return lvl


def respawn_time(level: int) -> float:
    """Tempo di respawn crescente col livello (stile LoL/Wild Rift)."""
    return 6.0 + level * 2.3


# --- Evoluzioni: moltiplicatore di potenza per stadio (punto 8) --------------
# M si applica a HP, AD, armatura, RM, mana e rigenerazione; NON a MS/AS,
# gittata e moltiplicatore abilita'. `n_stages` = numero di stadi della linea.
_EVO_MULT = {
    1: [1.00],                # non si evolve
    2: [0.87, 1.02],          # 2 stadi
    3: [0.82, 0.92, 1.03],    # 3 stadi
}


def evolution_mult(stage: int, n_stages: int) -> float:
    table = _EVO_MULT.get(max(1, min(3, n_stages)), _EVO_MULT[1])
    return table[max(0, min(len(table) - 1, stage))]


# --- Combattimento -----------------------------------------------------------
def ability_haste_factor(haste: float) -> float:
    """Fattore di ricarica: ricarica × 100/(100+haste) (riduzione haste/(100+haste))."""
    return 100.0 / (100.0 + max(0.0, haste))


def combine_tenacity(*sources: float) -> float:
    """Piu' fonti di tenacia si moltiplicano: 1 − Π(1 − t). Risultato in 0..1."""
    keep = 1.0
    for t in sources:
        keep *= (1.0 - max(0.0, min(1.0, t)))
    return 1.0 - keep


def penetrate(defense: float, pct_pen: float = 0.0, flat_pen: float = 0.0) -> float:
    """Applica penetrazione %% poi fissa. La penetrazione non porta mai sotto 0."""
    if defense <= 0.0:
        return defense
    defense *= (1.0 - max(0.0, pct_pen))
    return max(0.0, defense - max(0.0, flat_pen))


def mitigate(dmg: float, defense: float) -> float:
    """Danno dopo la difesa. Difesa >=0 riduce; difesa <0 amplifica (fino a ×2)."""
    if defense >= 0.0:
        return dmg * 100.0 / (100.0 + defense)
    return dmg * (2.0 - 100.0 / (100.0 - defense))


def damage(power: float, defense: float, effectiveness: float = 1.0,
           stab: float = 1.0) -> float:
    """Danno mitigato dalla difesa (per minion/strutture: niente penetrazione)."""
    return max(1.0, mitigate(power * effectiveness * stab, max(0.0, defense)))
