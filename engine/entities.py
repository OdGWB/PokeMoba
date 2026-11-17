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
    venom_stacks: int = 0            # accumuli di veleno di Scaglie Velenose (visibili a tutti)
    octi_lock_until: float = -1.0    # Prendimira (linea Remoraid): agganciato fino a qui
    octi_lock_by: int = -1           #   da questo Octillery/Remoraid
    octi_held_until: float = -1.0    # Presa a Ventosa: afferrato (solo grafica)

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
    bot_standin: bool = False        # bot che guida un giocatore caduto (online): niente acquisti/evoluzioni
    is_jungler: bool = False
    smite_charges: int = 2           # Smite (engine/smite.py): cariche, blocco e ricarica
    smite_ready_at: float = 0.0
    smite_regen_at: float = -1.0
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
    # Statistiche della partita (solo conteggi: tabellone TAB e fine partita).
    stat_kills: int = 0
    stat_deaths: int = 0
    stat_assists: int = 0
    stat_cs: int = 0                    # minion + mostri dei campi (ultimo colpo)
    stat_dmg: float = 0.0               # danno inflitto ai campioni nemici
    stat_taken: float = 0.0             # danno subito
    # Riepilogo della morte: colpi subiti negli ultimi RECAP_WINDOW secondi
    # (t, id attaccante, etichetta, danno, tipo) e il riassunto dell'ultima morte.
    dmg_log: list = field(default_factory=list)
    death_recap: dict | None = None
    items: list = field(default_factory=list)           # id degli oggetti (max 6)
    item_bonus: dict = field(default_factory=dict)       # {stat: valore} dagli oggetti
    rec_items: list = field(default_factory=list)        # oggetti consigliati (JSON del Pokémon)
    # Effetti unici degli oggetti (engine/item_effects.py)
    item_cd: dict = field(default_factory=dict)          # {id oggetto: istante in cui torna pronto}
    last_dealt_at: float = -1e9        # ultimo danno inflitto a un nemico (Bicicletta)
    last_aa_at: float = -1e9           # ultimo attacco base (Rapidartigli)
    aa_quick: bool = False             # attacco base istantaneo di Rapidartigli in corso
    choice_key: tuple | None = None    # ultima mossa lanciata (slot, id) per gli oggetti Scelta
    choice_at: float = -1e9
    choice_boost: str = ""             # id della mossa potenziata da Scelta (+25%)
    cast_seq: int = 0                  # contatore dei lanci (Assorbisfera: costo una volta a lancio)
    orb_paid_seq: int = -1
    metro: dict = field(default_factory=dict)            # Metronomo: {id bersaglio: (mossa, colpi, t)}
    wp_until: float = -1.0             # Vulnerassicurazione attiva fino a qui
    wp_active: bool = False            # aggiornato in _update_items (per eff_attack)
    smoke_hidden: bool = False         # dentro la propria Palla Fumo (invisibile)
    ember_until: float = -1.0          # Carbonella: bruciatura (1% HP max/s, senza tipo)
    ember_src: int | None = None
    aspd_slow_until: float = -1.0      # Gelomai: -20% velocita' d'attacco
    rust_stacks: int = 0               # Spada Arrugginita: cariche (+3% Attacco l'una)
    rust_until: float = -1.0
    rust_n: int = 0                    # cariche attive (aggiornato in _update_items)
    aura_spdef: float = 0.0            # Acqua Mistica: Dif. Sp. dall'aura di un alleato
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
    spdef_debuff_mult: float = 1.0     # Armor Cannon: Dif. Sp. ridotta in percentuale
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
    # Velocità d'attacco (engine/basic_attack.py): base del livello + bonus SOMMATI
    # (oggetti/passive); il tetto e i moltiplicatori temporanei si applicano al lancio.
    as_base: float = 0.0               # attacchi/s del livello senza bonus (0 = usa attack_speed)
    as_bonus: float = 0.0              # somma dei bonus % (0.2 + 0.3 = +50%)
    # Scelta del bersaglio: punto d'ancoraggio dell'auto-acquisizione da fermo
    # (limite d'inseguimento) e tasto "solo Pokémon" dell'attacco-movimento.
    idle_anchor: Vec2 | None = None
    champs_only: bool = False
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
    # Passiva Fiammacoda (linea Charmander): cariche di Calore e Scottatura.
    #   A 3 cariche di Calore (ognuna dura 4s, rinnovate a ogni colpo Fuoco) il
    #   nemico va in SCOTTATURA: danno nel tempo + Attacco ridotto del 25%.
    heat_stacks: int = 0
    heat_until: float = -1.0           # scadenza delle cariche di Calore
    burn_until: float = -1.0           # scottatura attiva: danno nel tempo
    burn_active: bool = False          # aggiornato in _update_status (per eff_attack)
    burn_dps: float = 0.0
    burn_src: int | None = None
    # Muro di Fumo: raggio visivo ridotto finché si resta nel fumo nemico.
    smoke_until: float = -1.0
    # Canalizzazione (Lanciafiamme continuo / Volo): mentre è attiva non si
    # possono lanciare altre mosse né fare auto-attacchi (gestita in match.py).
    channel_until: float = -1.0
    # Nitrocarica: cariche di velocità cumulabili (fino a 3) a ogni scatto.
    fc_stacks: int = 0
    fc_until: float = -1.0
    fc_per: float = 0.0                # bonus velocità per carica (impostato al lancio)
    # Lanciato in aria (knock-up: Pesobomba, Frana, Esplosione): non si muove né
    # lancia mosse; non viene accorciato/annullato da altri CC (né dalla tenacia).
    airborne_until: float = -1.0
    airborne_start: float = -1.0
    airborne_peak: float = 1.0         # altezza visiva del lancio (tile)
    # Linea Roggenrola: Terrempesta (Sabbiafiume x2) e cadenza del danno della tempesta.
    sandstorm_boost_until: float = -1.0
    sand_next: float = 0.0
    sand_radius: float = 0.0           # raggio attuale della tempesta (0 = spenta; per il client)
    # Passiva I 108 Spiriti (Spiritomb): cariche permanenti dagli spiriti raccolti,
    # risvegli a 36/72/108 (bonus HP/Dif/DifSp in spirit_bonus), Spirito Vagante
    # (attacco base potenziato ogni 6s) e prossima comparsa di uno spirito.
    spirit_charges: int = 0
    spirit_awaken: int = 0             # 0..3 risvegli raggiunti (aura visiva)
    spirit_next: float = 0.0           # istante della prossima comparsa di uno spirito
    wander_ready_at: float = 0.0       # Spirito Vagante pronto da questo istante
    spirit_bonus: dict = field(default_factory=dict)   # {stat: valore} dai risvegli
    # Dispetto: ricariche del nemico allungate (moltiplicatore sulle nuove ricariche).
    spite_until: float = -1.0
    spite_mult: float = 1.0
    # Memento: Spiritomb invisibile/non bersagliabile; i nemici colpiti hanno
    # Attacco e Att. Sp. dimezzati.
    memento_until: float = -1.0
    memento_weak_until: float = -1.0
    invisible: bool = False            # aggiornato in _update_status (per la visione)
    memento_weak: bool = False         # aggiornato in _update_status (per eff_attack)
    # Linea Eevee: stati nuovi (congelato, affascinato, accecato) e passive delle forme.
    frozen_until: float = -1.0         # congelato: immobile e inattivo (blocco di ghiaccio)
    charm_until: float = -1.0          # affascinato: cammina verso la fonte, niente azioni
    charm_src: int | None = None
    blind_until: float = -1.0          # Turbosabbia: gli attacchi base mancano
    endure_until: float = -1.0         # Resistenza: non scende sotto 1 HP
    puddle_until: float = -1.0         # Acidarmatura: pozza non bersagliabile, lenta
    puddle_heal: float = 0.0           # cura al secondo mentre è una pozza
    voltabsorb_ready_at: float = 0.0   # Assorbivolt: pronto da questo istante
    flashfire_until: float = -1.0      # Fuocardore: mosse Fuoco potenziate fino a qui
    hydration_next: float = 0.0        # Idratazione: prossima pulizia sotto la pioggia
    # Linea Rookidee: stato provocato (Provocazione), Trespolo, Specchiarmatura.
    taunt_until: float = -1.0          # provocato: deve attaccare taunt_src con attacchi base
    taunt_src: int | None = None
    roost_until: float = -1.0          # Trespolo: senza il tipo Volante fino a qui
    mirror_cd: dict = field(default_factory=dict)   # Specchiarmatura: id nemico -> pronto da
    # Linea Charcadet: barre di Armature, Calmamente, Guardia, Armatura
    # Fluttuante, Ombrartigli.
    fausta: float = 0.0                # Armatura Fausta: danno subito da Pokémon nemici
    infausta: float = 0.0              # Armatura Infausta: danno inflitto a Pokémon nemici
    calm_until: float = -1.0           # Calmamente: +Att. Sp. e +Dif. Sp. temporanei
    calm_mult: float = 1.0
    calm_active: bool = False          # aggiornato dal Match (per eff_sp_defense)
    guard_ready_at: float = 0.0        # Guardia: pronta da questo istante
    floatarmor_until: float = -1.0     # Armatura Fluttuante: spallacci in orbita fino a qui
    armor_blocks: int = 0              # proiettili che può ancora intercettare
    floatarmor_mv: tuple | None = None
    shadowclaw_until: float = -1.0     # Ombrartigli: attacchi base potenziati fino a qui
    shadowclaw_mult: float = 1.0
    # Linea Noibat: cariche del ping di Ecolocalizzazione, calo d'Att. Sp. di
    # Dragobolide.
    echo_count: int = 0                # attacchi base verso il prossimo ping (0..2)
    spa_down_until: float = -1.0       # Dragobolide: Att. Sp. ridotta fino a qui
    spa_down_mult: float = 1.0
    # Linea Teddiursa: vasetti di Miele, Dentistretti, Riposo, Luna Piena.
    honey: int = 0                     # vasetti di miele (0..3, visibili a tutti)
    honey_ready_at: float = 0.0        # prossimo vasetto consumabile da qui
    guts_until: float = -1.0           # Dentistretti attivo dopo il risveglio da Riposo
    guts_active: bool = False          # aggiornato dal Match (per eff_attack)
    rest_until: float = -1.0           # Riposo: sonno che il danno non rompe
    moon_until: float = -1.0           # Luna Piena: forma ingrandita fino a qui
    moon_hp_mult: float = 1.0
    moon_cleave: float = 0.0           # raggio degli attacchi base ad area
    # Linea Sneasel: Sole e Luna, Furto, Arraffalesto, Notte Fonda, Scalaroccia,
    # cure ridotte (stato generico).
    gold_minion: float = 0.0           # Sole e Luna: oro dai minion (-> Weavile)
    gold_wild: float = 0.0             # Sole e Luna: oro dai neutrali (-> Sneasler)
    thief_cd: dict = field(default_factory=dict)   # Furto: id vittima -> pronto da
    snatch_down: int = 0               # Arraffalesto: cariche rubate a questo Pokémon (5% l'una)
    snatch_down_until: float = -1.0
    snatch_up: int = 0                 # Arraffalesto: cariche guadagnate da Weavile
    snatch_up_until: float = -1.0
    nightfall_until: float = -1.0      # Notte Fonda: invisibile fino a qui
    ambush_until: float = -1.0         # Notte Fonda: colpo d'agguato pronto fino a qui
    ambush_mv: tuple | None = None
    climb_ready_at: float = 0.0        # Scalaroccia: prossimo scavalcamento da qui
    healcut_until: float = -1.0        # cure ridotte (Sporcolancio)
    healcut_mult: float = 1.0
    # Linea Mienfoo: Maniche a Frusta, Rigenergia, Individua, Bruciapelo,
    # Danza delle Maniche; oggetti disattivati (stato generico, Privazione).
    mien_act_at: float = -1e9          # ultima azione offensiva (attacco base, Q, E, R)
    mien_regen: bool = False           # Rigenergia attiva (aggiornato dal Match)
    mien_calm_at: float = -1e9         # da qui conta la calma (interfaccia)
    fakeout_ready: bool = False        # Bruciapelo: stordimento pronto (interfaccia)
    mien_crit_until: float = -1.0      # Individua: prossimo attacco base brutto colpo
    parry_until: float = -1.0          # Individua: finestra di parata aperta fino a qui
    parry_window: float = 0.5          # ultima finestra (si dimezza se ripetuta entro 6 s)
    parry_cast_at: float = -1e9
    parry_eff: dict | None = None
    double_until: float = -1.0         # Doppio Bruciapelo: rilancio pronto fino a qui
    double_cd: float = 0.0
    dance_until: float = -1.0          # Danza delle Maniche in corso fino a qui
    dance_seq: str = ""                # mosse già usate nella danza ("QE"...)
    dance_mv: tuple | None = None
    itemlock_until: float = -1.0       # oggetti disattivati (Privazione)
    # Linea Duraludon: Conduzione, Tiro Lungo, Elettroraggio, Tuono.
    cast_hold: float = 0.0             # secondi di pressione del tasto (Tiro Lungo)
    arch_rain: bool = False            # Conduzione attiva: sotto la pioggia (interfaccia)
    arch_spa_until: float = -1.0       # Elettroraggio: +Att. Sp. fino a qui
    arch_spa_mult: float = 1.0
    beam_charge_until: float = -1.0    # Elettroraggio: in carica fino a qui
    thunder_left: int = 0              # Tuono: fulmini ancora da lanciare
    thunder_until: float = -1.0        # Tuono: finestra dei rilanci
    thunder_cd: float = 0.0
    # Linea Hatenna: Quiete (agitato), Magipolvere (tipo Psico temporaneo).
    agitated_until: float = -1.0       # agitato (Quiete) fino a qui: visibile nei cespugli
    agitated: bool = False             # aggiornato dal Match (per la visione)
    powder_until: float = -1.0         # Magipolvere: tipo Psico fino a qui
    powder_types: list | None = None   # tipi da rimettere a fine Magipolvere
    powder_dex: int = 0
    mag_sign: int = 0                  # carica magnetica (Magnetismo): +1, -1, 0 = nessuna
    mag_until: float = -1.0            # la carica scade qui
    mag_src: int = 0                   # id del Magnemite che l'ha applicata
    mag_team: int = -1                 # squadra del Magnemite (per lui: nemico o ancora)
    # Linea Swinub: Gelo (accumuli sul nemico), Grassospesso (scudo), Forzantica.
    frost_stacks: int = 0              # accumuli di Gelo (0..4, visibili a tutti)
    frost_until: float = -1.0          # gli accumuli scadono qui
    frost_src: int = 0                 # id del Mamoswine che li ha dati
    frost_lock_until: float = -1.0     # niente congelamento da Gelo fino a qui
    fat_shield: float = 0.0            # Grassospesso: scudo che si rigenera
    ancient_until: float = -1.0        # Forzantica: statistiche +10% fino a qui
    ancient_mult: float = 1.0
    ancient_active: bool = False       # aggiornato dal Match
    # Linea Venonat: Eledanza, Ventargenteo, Polvoscudo (accumuli di veleno in Unit).
    quiver_until: float = -1.0         # Eledanza: fino a qui
    quiver_spa: float = 1.0
    quiver_spd: float = 1.0
    quiver_speed: float = 1.0
    quiver_as: float = 0.0
    quiver_active: bool = False        # aggiornato dal Match
    silver_until: float = -1.0         # Ventargenteo: tutte le statistiche +10%
    silver_mult: float = 1.0
    silver_active: bool = False
    powdershield_until: float = -1.0   # Polvoscudo (solo grafica)
    # Linea Remoraid: munizioni, Prendimira, Presa a Ventosa, Iper Raggio.
    ammo: str = "Water"                # munizione attiva (tipo di attacchi base e Q)
    ammo_boost: bool = False           # Octillery: primo colpo dopo il cambio +30%
    octi_lock_ready_at: float = 0.0    # Prendimira: pronta da qui
    octi_grab_until: float = -1.0      # Presa a Ventosa: sta afferrando fino a qui
    octi_grab_id: int | None = None
    octi_grab_as: float = 0.0
    octi_grab_root: float = -1.0       # fine del proprio blocco della Presa
    octi_recharge_until: float = -1.0  # Iper Raggio: ricarica (solo grafica)
    # Linea Flabébé (engine/florges.py): colore dei fiori scelto nella selezione
    # e bonus dei fiori raccolti (valgono su chiunque raccolga).
    flower_color: str = "red"          # red | yellow | orange | blue | white
    flor_red_until: float = -1.0       # Rosso: +15% danno inflitto
    flor_yellow_until: float = -1.0    # Giallo: +25% velocità
    flor_sym_until: float = -1.0       # Simbiosi: 30% dei bonus oggetti di Florges
    flor_sym_bonus: dict = field(default_factory=dict)
    flor_dance_until: float = -1.0     # Petalodanza in corso
    flor_dance_next: float = -1.0
    flor_mist_until: float = -1.0      # dentro Campo Nebbioso (immune ai nuovi stati)
    flor_pick_at: float = -1.0         # ultimo fiore raccolto (solo grafica)
    flor_pick_color: str = ""
    # Linea Scyther (engine/scizor.py)
    scy_was_cc: bool = False           # Cuordeciso: era sotto controllo al tick prima
    scy_heart_until: float = -1.0      # Cuordeciso: +30% velocità
    scy_fury_stacks: int = 0           # Tagliofuria: usi a segno consecutivi
    scy_fury_last: float = -1e9
    scy_fury_until: float = -1.0       # fine della finestra di Tagliofuria (solo grafica/HUD)
    scy_focus_until: float = -1.0      # Focalenergia: +40% brutto colpo
    scy_double_ready: bool = False     # Doppiocolpo: il prossimo attacco base colpisce due volte
    scy_claws_until: float = -1.0      # Chele d'Acciaio
    scy_down_until: float = -1.0       # Troppoforte: -20% Attacco e Difesa
    scy_smash_until: float = -1.0      # Spaccaroccia attiva (su Kleavor)
    scy_shred: int = 0                 # Spaccaroccia subita: accumuli (-8% Difesa l'uno)
    scy_shred_until: float = -1.0
    scy_infield: bool = False          # Kleavor dentro un suo campo di schegge
    scy_atk_mult: float = 1.0          # moltiplicatori ricalcolati a ogni tick
    scy_def_mult: float = 1.0
    scy_spdef_mult: float = 1.0
    # Linea Litten (engine/incineroar.py)
    incin_last_dealt: float = -1e9     # Prepotenza: ultimo danno inflitto
    incin_calm_at: float = -1e9        #   ultimo danno inflitto o subito (HUD)
    incin_intim_until: float = -1.0    # Prepotenza subita: -20% Attacco
    incin_bully_until: float = -1.0    # Bullo: +10% Attacco (provocati e Incineroar)
    incin_rope_until: float = -1.0     # Corsa alle Corde: prossimo attacco base o Q potenziato
    incin_lariat_until: float = -1.0   # Darkest Lariat in corso
    incin_lariat_next: float = -1.0
    incin_ring_n: int = 0              # Cattivo del Ring: nemici entro 5 tile (max 3)
    incin_atk_mult: float = 1.0        # ricalcolato a ogni tick

    def _bonus(self, stat: str) -> float:
        return (self.passive_bonus.get(stat, 0.0) + self.item_bonus.get(stat, 0.0)
                + self.spirit_bonus.get(stat, 0.0))

    def eff_attack(self) -> float:
        base = self.stats.attack + self._bonus("attack")
        if self.atk_debuff_active:
            base -= self.atk_debuff_amt
        atk = max(0.0, base) * self.atk_mult
        if self.rust_n:
            atk *= 1.0 + 0.03 * self.rust_n   # Spada Arrugginita
        if self.burn_active and self.passive_id != "dentistretti":
            atk *= 0.75   # Scottatura (Fiammacoda): -25% Attacco mentre brucia
        if self.guts_active:
            atk *= 1.5    # Dentistretti (Ursaring/Ursaluna): +50% con uno stato alterato
        if self.passive_id == "forzabruta" and self.cc_active:
            atk *= 1.5   # ForzaBruta: +50% attacco fisico mentre è sotto CC
        if self.passive_id == "inversione" and self.inversion_stacks:
            atk *= 1.0 + 0.01 * self.inversion_stacks
        if self.memento_weak:
            atk *= 0.5   # Memento: Attacco dimezzato
        if self.wp_active:
            atk *= 1.25  # Vulnerassicurazione: +25% Attacco
        if self.snatch_down or self.snatch_up:
            atk *= self.snatch_mult()   # Arraffalesto (Weavile): Attacco rubato
        if self.ancient_active:
            atk *= self.ancient_mult    # Forzantica (Mamoswine): tutte le statistiche
        if self.silver_active:
            atk *= self.silver_mult     # Ventargenteo (Venomoth): tutte le statistiche
        return atk * self.scy_atk_mult * self.incin_atk_mult   # Troppoforte; Prepotenza/Bullo

    def eff_sp_attack(self) -> float:
        # Nel modello MOBA la statistica speciale per livello e' sparita: le
        # abilita' speciali scalano sull'AP (0 base + oggetti), poi il danno
        # finale e' moltiplicato per ability_mult (vedi Match._ability_damage).
        ap = self.ap * self.atk_mult
        if self.passive_id == "inversione" and self.inversion_stacks:
            ap *= 1.0 + 0.01 * self.inversion_stacks
        if self.memento_weak:
            ap *= 0.5    # Memento: Att. Sp. dimezzato
        if self.wp_active:
            ap *= 1.25   # Vulnerassicurazione: +25% Att. Sp.
        if self.calm_active:
            ap *= self.calm_mult   # Calmamente: +Att. Sp. temporaneo
        if self.snatch_down or self.snatch_up:
            ap *= self.snatch_mult()   # Arraffalesto (Weavile): Att. Sp. rubato
        if self.ancient_active:
            ap *= self.ancient_mult    # Forzantica
        if self.silver_active:
            ap *= self.silver_mult     # Ventargenteo
        if self.quiver_active:
            ap *= self.quiver_spa      # Eledanza: +30% Att. Sp.
        return ap

    def snatch_mult(self) -> float:
        """Arraffalesto: -5% per carica rubata, +5% per carica guadagnata."""
        return (1.0 - 0.05 * self.snatch_down) * (1.0 + 0.05 * self.snatch_up)

    def _soul(self) -> int:
        # Corpofunesto: ogni carica dà +1 Difesa e +1 Dif.Sp.
        return self.soul_charges if self.passive_id == "corpofunesto" else 0

    def eff_defense(self) -> float:
        d = self.stats.defense + self._bonus("defense") + self._soul()
        if self.def_debuff_active:
            d = (d - self.def_debuff_amt) * self.def_debuff_mult
        if self.def_buff_active:        # Indurimento: +difesa temporanea
            d *= self.def_buff_mult
        if self.ancient_active:
            d *= self.ancient_mult      # Forzantica
        if self.silver_active:
            d *= self.silver_mult       # Ventargenteo
        return max(0.0, d * self.scy_def_mult)   # Troppoforte, Spaccaroccia, campo di schegge

    def eff_sp_defense(self) -> float:
        d = (self.stats.sp_defense + self._bonus("sp_defense") + self._soul()
             + self.aura_spdef)
        if self.spdef_debuff_active:
            d = (d - self.spdef_debuff_amt) * self.spdef_debuff_mult
        if self.calm_active:            # Calmamente: +Dif. Sp. temporanea
            d *= self.calm_mult
        if self.passive_id == "sabbiafiume" and self.stage >= 2:
            d *= 1.3   # Sabbiafiume (Gigalith): +30% Dif. Sp.
        if self.ancient_active:
            d *= self.ancient_mult      # Forzantica
        if self.silver_active:
            d *= self.silver_mult       # Ventargenteo
        if self.quiver_active:
            d *= self.quiver_spd        # Eledanza: +30% Dif. Sp.
        return max(0.0, d * self.scy_spdef_mult)   # campo di schegge (Kleavor)
    # Ordine corrente impartito dal giocatore (o dal controllo): guida l'IA.
    #   "idle" | "move" | "attack" | "attackmove" | "stop" (stop = tieni la posizione)
    order: str = "idle"
    order_target_id: int | None = None
    order_point: Vec2 | None = None
    # Destinazione dell'ultimo ordine di movimento (punto esatto o tile vicino):
    # se un CC o un richiamo svuotano il percorso, l'IA lo ricalcola fin li'.
    move_dest: Vec2 | None = None


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
class Pillar:
    """Pilastro di roccia temporaneo (Rocciotomba, linea Roggenrola).

    NON è un'entità del World (non combatte, non si bersaglia): occupa un tile
    che diventa TILE_PILLAR finché esiste, quindi blocca movimento, proiettili e
    pathfinding come un muro e vale come muro per Pesobomba. Il client lo legge
    da world.pillars per disegnarlo (spunta dal terreno, poi si sbriciola)."""
    pos: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    tx: int = 0
    ty: int = 0
    team: int = 0
    born: float = 0.0
    until: float = 0.0
    prev_tile: int = 0
    # Pietrataglio: esplode se un nemico ci viene schiantato contro.
    explode: tuple | None = None       # (Move dell'esplosione, grado, id lanciatore, raggio)
    radius: float = 0.5


@dataclass
class Spirit:
    """Spirito della passiva I 108 Spiriti (Spiritomb): fiammella verde lime in
    giungla o nel fiume. Lo vede solo la squadra del proprietario e lo raccoglie
    solo il proprietario passandoci sopra (o con Richiamo degli Spiriti). Non è
    un'entità del World: il client lo legge da world.spirits."""
    pos: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    owner_id: int = 0
    team: int = 0
    born: float = 0.0
    seed: int = 0


@dataclass
class Structure(Entity, Combatant):
    kind: str = "tower"              # "tower" | "core"
    lane: str | None = None
    tier: int = 1


@dataclass
class Core(Structure):
    """Il nucleo della base: distruggerlo fa vincere la partita."""
    kind: str = "core"
