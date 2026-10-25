"""Costanti globali del gioco.

Questo modulo contiene solo valori: può essere importato sia dalla simulazione
pura (engine/sim) sia dal client (game) senza creare dipendenze da pygame.
"""

# --- Mondo / griglia ---------------------------------------------------------
TILE_SIZE = 24          # dimensione di un tile in pixel (risoluzione nativa)
RENDER_SCALE = 3        # fattore di scaling della surface low-res sulla finestra

# --- Timing ------------------------------------------------------------------
TICK_RATE = 30          # tick di simulazione al secondo (server autoritativo)
TICK_DT = 1.0 / TICK_RATE
SNAPSHOT_RATE = 20      # snapshot di rete al secondo (usato dalla Fase 5)

# --- Finestra ----------------------------------------------------------------
WINDOW_WIDTH = 1280     # dimensione INIZIALE della finestra (ridimensionabile)
WINDOW_HEIGHT = 720
WINDOW_TITLE = "PokrLOL"

# Risoluzione interna FISSA su cui si disegna il mondo (648x360 = 27x15 tile da
# 24 px, 16:9). Viene scalata per riempire la finestra mantenendo le proporzioni
# (lettera-box): così l'area di gioco visibile è la STESSA per tutti, a qualsiasi
# risoluzione o in fullscreen ("zoom fisso e uguale per tutti").
LOWRES_WIDTH = 648
LOWRES_HEIGHT = 360

# --- Movimento ---------------------------------------------------------------
# Velocità base in tile/secondo. La taratura precisa (lane base-base in 30-40s)
# arriva in Fase 2 con la mappa vera.
BASE_MOVE_SPEED = 3.6

# --- Camera ------------------------------------------------------------------
EDGE_SCROLL_MARGIN = 20     # px (in coordinate finestra) dai bordi per lo scroll
EDGE_SCROLL_SPEED = 400.0   # px/secondo di scorrimento camera

# --- Multiplayer (Fase 5) ----------------------------------------------------
DEFAULT_PORT = 50007
# Roster selezionabile in lobby (indice condiviso tra server e client).
ROSTER = [
    "data/pokemon/charmander.json",
    "data/pokemon/squirtle.json",
    "data/pokemon/gastly.json",
    "data/pokemon/bulbasaur.json",
    "data/pokemon/totodile.json",
    "data/pokemon/rowlet.json",
    "data/pokemon/snivy.json",
]
DEFAULT_MAP = "data/maps/map_3v3.json"
# Mappe selezionabili dalla lobby (nome, percorso).
MAPS = [("3v3", "data/maps/map_3v3.json"), ("5v5", "data/maps/map_5v5.json")]

# --- Squadre -----------------------------------------------------------------
TEAM_COLORS = {
    0: (74, 136, 235),   # blu (base in basso a sinistra)
    1: (231, 86, 76),    # rosso (base in alto a destra)
}

# --- Partita (Fase 2, valori greybox da bilanciare) --------------------------
# Riferimento LoL (wiki ufficiale): prima ondata 0:30, poi ogni 30s (25s dai 14',
# 20s dai 30'); 3 melee + 3 caster per ondata, cannone ogni 3a ondata (dall'1:30).
# Qui accorciamo l'intervallo per partite LAN più ritmate.
FIRST_WAVE_TIME = 20.0      # quando parte la prima ondata
WAVE_INTERVAL = 25.0        # secondi tra un'ondata e l'altra
CANNON_EVERY = 3            # un minion cannone ogni N ondate
MELEE_PER_WAVE = 3          # minion corpo-a-corpo per lane per ondata
CASTER_PER_WAVE = 3         # minion caster (dalla distanza) per lane per ondata
MINION_SPAWN_GAP = 0.5      # ritardo tra un minion e il successivo nell'ondata

POKEMON_RESPAWN_TIME = 8.0  # respawn fisso in Fase 2 (cresce col livello in Fase 3)

# --- Oro e negozio (Fase 6) --------------------------------------------------
STARTING_GOLD = 500
GOLD_PASSIVE_PER_SEC = 3.0   # guadagno passivo nel tempo
GOLD_KILL_BASE = 120
GOLD_KILL_PER_LEVEL = 15
GOLD_ASSIST = 60
GOLD_TOWER = 250
ASSIST_WINDOW = 8.0          # s: finestra per contare un assist
SHOP_RANGE = 6.0             # tile dalla base per poter usare il negozio
RECALL_TIME = 5.0            # secondi di canalizzazione del richiamo
RECALL_HEAL = 0.25           # cura all'arrivo in base (frazione degli HP max)

# --- Giungla, leggendari e meteo (Fase 7) ------------------------------------
WEATHER_FIRST_SPAWN = 300.0  # 5:00 - prima comparsa del leggendario meteo
WEATHER_RESPAWN = 300.0      # ricompare 5 min dopo (meteo diverso)
ARCEUS_OPEN_3V3 = 900.0      # 15:00 - si apre la tana di Arceus (3v3)
ARCEUS_OPEN_5V5 = 1200.0     # 20:00 - si apre la tana di Arceus (5v5)
ARCEUS_RESPAWN = 360.0       # 6 min dopo la sconfitta
CAMP_RESPAWN = 70.0          # ricrescita dei campi neutrali
JUDGMENT_DURATION = 180.0    # buff Giudizio (3 min)

LEGENDARY_HP = 4200
LEGENDARY_DMG = 95
LEGENDARY_XP = 450
LEGENDARY_GOLD = 250
ARCEUS_HP = 11000
ARCEUS_DMG = 150
ARCEUS_XP = 750
ARCEUS_GOLD = 420
CAMP_HP = 900
CAMP_DMG = 42
CAMP_XP = 220
CAMP_GOLD = 90
# Campi "grandi" (buff), più tosti e redditizi dei piccoli.
CAMP_BIG_MULT = 1.8         # hp/danno dei campi grandi
CAMP_BIG_REWARD_MULT = 2.0  # xp/oro dei campi grandi
# Passiva Corpofunesto (linea Gastly): cariche d'anima.
SOUL_PER_KILL = 10
SOUL_PER_ASSIST = 5
SOUL_MAX = 100
# Passiva Distacco (linea Rowlet): colpo furtivo da nascosto.
DISTACCO_RANGE_BONUS = 2.5    # gittata extra dell'auto-attacco se nascosto
DISTACCO_BONUS_MULT = 1.6     # danno del primo colpo furtivo
DISTACCO_REVEAL_BLOCK = 1.0   # resta nascosto per 1s dopo il colpo

ARCEUS_PLATES = ["Fire", "Water", "Grass", "Electric", "Psychic", "Ghost", "Dragon", "Steel"]
# Moltiplicatori del meteo sui danni delle mosse.
WEATHER_DMG = {
    "sun":  {"Fire": 1.5, "Water": 0.5},
    "rain": {"Water": 1.5, "Fire": 0.5},
    "wind": {},
    "clear": {},
}
PUDDLE_SLOW = 0.65           # rallentamento nelle pozze per i non-Acqua
WIND_FLYING_SPEED = 1.35     # bonus velocità ai Volanti col Vento forte

# --- Ritmo partita / strutture (per partite da ~15-25 min, stile Wild Rift) --
# Il nucleo è invulnerabile finché la squadra ha più di questo numero di torri.
CORE_EXPOSE_TOWERS_LEFT = 0
TOWER_HP_OUTER = 2900       # torre esterna (tier 1)
TOWER_HP_INNER = 3900       # torre interna (tier 2), più vicina al nucleo
TOWER_DAMAGE = 110
CORE_HP = 9500
# I minion grattano le strutture (pressione lenta) ma cresce col tempo.
STRUCT_MINION_DMG_MULT = 0.5
# Le torri "scaldano": ogni colpo sullo stesso bersaglio aumenta il danno,
# così fare dive senza minion davanti è molto pericoloso.
TOWER_RAMP_PER_HIT = 0.28
TOWER_RAMP_MAX = 3.0
# I minion crescono col tempo: rompono gli stalli e fanno finire le partite
# (verso i 18-24 min diventano forti abbastanza da sfondare).
MINION_SCALE_PER_MIN = 0.22

# Visione (usata davvero in Fase 4 per la nebbia; qui solo come dato).
VISION_POKEMON = 9.0
VISION_TOWER = 12.0
VISION_MINION = 6.0

# --- Debug -------------------------------------------------------------------
SHOW_GRID_LINES = False
SHOW_PATH = True
SHOW_HP_BARS = True
