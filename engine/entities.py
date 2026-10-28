"""Entità della simulazione.

Classi di dati "povere": contengono stato, non logica di rendering. Il client
legge questi campi (pos, facing, hp...) per disegnare, ma non li modifica.

Gerarchia:
    Entity                       id, posizione, raggio
      ├── Unit                   entità che si muove e combatte
      │     ├── Pokemon
      │     └── Minion
      └── Structure              entità fissa che combatte (torre, nucleo)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .stats import Stats
from .vec import Vec2


@dataclass
class Entity:
    # Valori di default necessari: con l'ereditarietà multipla dei dataclass
    # (Unit = Entity + Combatant) tutti i campi ereditati devono avere default.
    # In pratica le entità si creano sempre con argomenti nominali.
    id: int = 0
    pos: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    radius: float = 0.35  # in tile; usato per le collisioni a cerchio


@dataclass
class Combatant:
    """Campi comuni a chi ha punti vita e può attaccare."""
    team: int = 0
    hp: float = 100.0
    max_hp: float = 100.0
    alive: bool = True
    attack_damage: float = 0.0
    attack_range: float = 0.0        # in tile
    attack_cooldown: float = 1.0     # secondi tra un attacco e l'altro
    attack_timer: float = 0.0        # tempo rimasto prima di poter riattaccare
    target_id: int | None = None
    vision: float = 9.0
    # Chi ha inflitto danno di recente a questa unità (per il targeting torri).
    last_attacker_id: int | None = None
    last_damaged_at: float = -1e9

    def is_full_hp(self) -> bool:
        return self.hp >= self.max_hp


@dataclass
class Unit(Entity, Combatant):
    speed: float = 3.6               # tile/secondo
    path: list = field(default_factory=list)  # waypoint rimanenti (Vec2)
    moving: bool = False
    facing: int = 0                  # indice direzione 0..7 (vedi vec.DIR_NAMES)
    bush_blocks: bool = False        # True = non può entrare nei cespugli (minion)

    def set_path(self, points: list) -> None:
        self.path = list(points)
        self.moving = bool(self.path)

    def stop(self) -> None:
        self.path = []
        self.moving = False


@dataclass
class Pokemon(Unit):
    dex: int = 0
    name: str = "Pokemon"
    color: tuple = (230, 120, 60)
    role: str = ""
    attack_fx: str = ""              # stile effetto dell'auto-attacco (vedi game/fx.py)
    is_bot: bool = False
    is_jungler: bool = False
    assigned_lane: str = "mid"
    spawn_pos: Vec2 = field(default_factory=lambda: Vec2(0, 0))
    respawn_timer: float = 0.0       # >0 = morto, in attesa di respawn
    respawn_max: float = 1.0         # durata totale del respawn corrente (per la UI)
    # Statistiche / livelli (Fase 3)
    types: list = field(default_factory=list)
    level: int = 1
    xp: float = 0.0
    base_stats: Stats = field(default_factory=Stats)   # 6 stat base REALI del Pokémon
    stats: Stats = field(default_factory=Stats)         # bundle "vivo" derivato per livello
    ranged: bool = False                                # attacco a distanza (AD ×0,95)
    # Stat di gioco derivate (vedi engine/stats.derive). Mana/AP/critico sono
    # calcolate e memorizzate ma non ancora consumate dal combattimento.
    attack_speed: float = 1.0                           # attacchi/secondo
    max_mana: float = 0.0
    mana: float = 0.0
    mana_regen5: float = 0.0
    ap: float = 0.0
    crit: float = 0.0                 # probabilita' di critico (0..1)
    ability_mult: float = 1.0
    # Penetrazione e sostentamento (dagli oggetti; punto 6)
    armor_pen_pct: float = 0.0
    magic_pen_pct: float = 0.0
    magic_pen_flat: float = 0.0
    lifesteal: float = 0.0            # rubavita sugli attacchi base/fisici
    omnivamp: float = 0.0             # cura da ogni danno inflitto
    ability_haste: float = 0.0
    tenacity: float = 0.0
    hp_regen5: float = 0.0
    flat_reduction: float = 0.0
    lethality: float = 0.0
    lethality_physical: bool = True
    heal_power: float = 1.0
    range_cls: str = "mid"
    range_val: float = 350.0
    # Mosse / evoluzioni / gradi (Fase 3b)
    moveset: dict = field(default_factory=dict)       # {slot: MoveSlot}
    evolutions: list = field(default_factory=list)    # stadi (dict dal JSON)
    stage: int = 0
    stat_mult: float = 1.0
    skill_points_spent: int = 0
    pending_choices: list = field(default_factory=list)  # slot in attesa di scelta potenziamento
    offered_slots: set = field(default_factory=set)  # slot il cui potenziamento è già stato offerto
    pending_cast: tuple | None = None   # (slot, x, y) da eseguire al prossimo tick
    move_speed_base: float = 3.6
    # Stati temporanei
    slow_mult: float = 1.0
    slow_until: float = -1.0
    speed_mult: float = 1.0
    speed_until: float = -1.0
    atk_mult: float = 1.0
    atk_until: float = -1.0
    shield: float = 0.0
    shield_until: float = -1.0
    # Sollevamento visivo (salto/lancio in aria, es. Ribaltiro/Rimbalzo): il
    # client alza lo sprite di air_z tile e disegna un'ombra a terra. Cosmetico.
    air_z: float = 0.0
    passive_bonus: dict = field(default_factory=dict)   # {stat: valore} permanente (mosse)
    # Oro e oggetti (Fase 6)
    gold: float = 500.0
    kill_streak: int = 0                # uccisioni consecutive (serie di uccisioni)
    death_streak: int = 0               # morti consecutive (serie di morti)
    items: list = field(default_factory=list)           # id degli oggetti (max 6)
    item_bonus: dict = field(default_factory=dict)       # {stat: valore} dagli oggetti
    # Buff Giudizio di Arceus (Fase 7)
    judgment_until: float = -1.0
    judgment_plate: str = ""
    # Passiva e controlli (CC) / stati speciali
    passive_id: str = ""
    cc_active: bool = False            # True se sotto un qualunque CC (per ForzaBruta)
    stun_until: float = -1.0           # immobilizzato (stun / congelamento): niente movimento/azioni
    confuse_until: float = -1.0        # confuso: attacca gli alleati
    silence_until: float = -1.0        # silenziato: solo autoattacchi, niente mosse (Ripeti)
    untargetable_until: float = -1.0   # non bersagliabile (SUB)
    rampage_until: float = -1.0        # Oltraggio attivo
    cc_immune_until: float = -1.0      # immune ai CC (durante Oltraggio)
    def_debuff_until: float = -1.0
    def_debuff_active: bool = False
    def_debuff_amt: float = 0.0
    def_debuff_mult: float = 1.0       # Codacciaio: calo difesa in percentuale
    spdef_debuff_until: float = -1.0
    spdef_debuff_active: bool = False
    spdef_debuff_amt: float = 0.0
    atk_debuff_until: float = -1.0     # Danzadipiume: riduce l'Attacco
    atk_debuff_active: bool = False
    atk_debuff_amt: float = 0.0
    aa_stealth: bool = False           # auto-attacco furtivo in corso (passiva Distacco)
    sleep_arm_at: float = -1.0         # sonno ritardato (Ipnosi): quando scatta
    sleep_arm_dur: float = 0.0
    fear_until: float = -1.0           # spavento: fugge dalla fonte, rallentato
    fear_src: Vec2 | None = None
    dashlock_until: float = -1.0       # Cucitombra: niente scatti/teletrasporti
    # Passiva Distacco (linea Rowlet): primo colpo da invisibile/cespuglio
    stealth_shot_ready: bool = True
    reveal_block_until: float = -1.0   # resta nascosto per un po' dopo il colpo furtivo
    # Richiamo (recall) verso la base
    recalling: bool = False
    recall_until: float = -1.0
    recall_start: float = -1.0
    # SUB (sott'acqua): mentre è immerso è intargetabile ma si muove liberamente;
    # riemerge (a tempo o ri-lanciando la R) con un'onda d'urto che fa danno.
    submerged: bool = False
    submerge_until: float = -1.0
    # Auto-attacco con windup/recovery (stile LoL): il danno parte a fine windup;
    # muoversi o lanciare durante il windup annulla l'attacco.
    aa_active: bool = False            # True = windup in corso
    aa_until: float = -1.0             # istante in cui il danno è garantito
    aa_target_id: int | None = None
    # Stati alterati aggiuntivi (linea Gastly)
    root_until: float = -1.0           # paralisi: non si muove ma può agire (rooted)
    sleep_until: float = -1.0          # sonno: immobile, rotto dal primo danno
    poison_until: float = -1.0         # veleno: danno nel tempo
    poison_dps: float = 0.0
    poison_src: int | None = None
    # Passiva Corpofunesto (cariche d'anima)
    soul_charges: int = 0
    # Passiva Muta / forma Shedinja (linea Nincada): forma temporanea.
    #   form: "" normale, "shedinja" guscio temporaneo (HP fissi a 1, Coleottero/Spettro).
    form: str = ""
    form_until: float = -1.0           # istante in cui la forma Shedinja finisce
    rancore_form: bool = False         # True se la forma Shedinja viene dalla R Rancore
    muta_cd_until: float = -1.0        # ricarica condivisa Muta/Rancore (150s)
    muta_cd_max: float = 150.0
    ninjask_stats: dict = field(default_factory=dict)   # stat base reali salvate per il ritorno
    ninjask_types: list = field(default_factory=list)   # tipi salvati per il ritorno
    ninjask_dex: int = 0
    # Potenziamento difesa temporaneo (Indurimento)
    def_buff_until: float = -1.0
    def_buff_active: bool = False
    def_buff_mult: float = 1.0
    # Sfuriate (colpi consecutivi sullo stesso bersaglio)
    fury_target: int | None = None
    fury_stacks: int = 0
    fury_until: float = -1.0
    # Doppioteam (clone esca): unita' innocua che cammina e svanisce
    is_decoy: bool = False
    decoy_until: float = -1.0
    # Passiva Inversione (linea Snivy): ogni carica dà +1% ATT e +1% SPAT.
    inversion_stacks: int = 0
    inversion_oc_until: float = -1.0   # finestra "sovraccarico" (tetto 100 anziché 50)
    inversion_last_gain: float = -1.0  # ultimo istante in cui ha guadagnato cariche
    inversion_decay_next: float = 0.0  # prossimo tick di decadimento (dopo 10s d'inattività)
    # Maledizione (R): marchio ritardato
    curse_until: float = -1.0
    curse_src: int | None = None
    curse_power: float = 0.0
    # Spettrotuffo (R): ritorno automatico al punto di partenza
    blink_return_until: float = -1.0
    blink_return_pos: Vec2 | None = None

    def _bonus(self, stat: str) -> float:
        return self.passive_bonus.get(stat, 0.0) + self.item_bonus.get(stat, 0.0)

    def eff_attack(self) -> float:
        base = self.stats.attack + self._bonus("attack")
        if self.atk_debuff_active:
            base -= self.atk_debuff_amt
        atk = max(0.0, base) * self.atk_mult
        if self.passive_id == "forzabruta" and self.cc_active:
            atk *= 1.5   # ForzaBruta: +50% attacco fisico mentre è sotto CC
        if self.passive_id == "inversione" and self.inversion_stacks:
            atk *= 1.0 + 0.01 * self.inversion_stacks
        return atk

    def eff_sp_attack(self) -> float:
        # Nel modello MOBA la statistica speciale per livello e' sparita: le
        # abilita' speciali scalano sull'AP (0 base + oggetti), poi il danno
        # finale e' moltiplicato per ability_mult (vedi Match._ability_damage).
        ap = self.ap * self.atk_mult
        if self.passive_id == "inversione" and self.inversion_stacks:
            ap *= 1.0 + 0.01 * self.inversion_stacks
        return ap

    def _soul(self) -> int:
        # Corpofunesto: ogni carica dà +1 Difesa e +1 Dif.Sp.
        return self.soul_charges if self.passive_id == "corpofunesto" else 0

    def eff_defense(self) -> float:
        d = self.stats.defense + self._bonus("defense") + self._soul()
        if self.def_debuff_active:
            d = (d - self.def_debuff_amt) * self.def_debuff_mult
        if self.def_buff_active:        # Indurimento: +difesa temporanea
            d *= self.def_buff_mult
        return max(0.0, d)

    def eff_sp_defense(self) -> float:
        d = self.stats.sp_defense + self._bonus("sp_defense") + self._soul()
        if self.spdef_debuff_active:
            d -= self.spdef_debuff_amt
        return max(0.0, d)
    # Ordine corrente impartito dal giocatore (o dal controllo): guida l'IA.
    #   "idle" | "move" | "attack" | "attackmove" | "stop"
    order: str = "idle"
    order_target_id: int | None = None
    order_point: Vec2 | None = None


@dataclass
class Minion(Unit):
    lane: str = "mid"
    minion_type: str = "melee"       # "melee" | "caster" | "cannon"
    lane_points: list = field(default_factory=list)  # waypoint della lane (Vec2)
    lane_idx: int = 0                # prossimo waypoint da raggiungere
    aggro: float = 4.0               # raggio entro cui ingaggia un nemico
    gold: int = 20                   # ricompensa (usata in Fase 6)
    xp: int = 20
    chasing: bool = False            # True quando sta inseguendo (usa A*)
    bush_blocks: bool = True         # i minion non attraversano i cespugli


@dataclass
class Wild(Unit):
    """Pokémon neutrale della giungla (squadra 2): campo, leggendario o Arceus."""
    kind: str = "camp"              # "camp" | "meteo" | "arceus"
    weather: str = ""               # per il leggendario meteo: "sun"|"rain"|"wind"
    plate: str = ""                 # per Arceus: tipo della lastra
    reward_xp: float = 0.0
    reward_gold: int = 0
    color: tuple = (180, 180, 150)


@dataclass
class Structure(Entity, Combatant):
    kind: str = "tower"              # "tower" | "core"
    lane: str | None = None
    tier: int = 1


@dataclass
class Core(Structure):
    """Il nucleo della base: distruggerlo fa vincere la partita."""
    kind: str = "core"
