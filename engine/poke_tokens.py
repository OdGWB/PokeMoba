"""Token di identita' dei Pokémon per i bot (taratura CMA-ES oggi, Reinforcement
Learning domani). Puro: niente pygame, niente stato di partita, non cambia nulla
del gioco ne' del comportamento dei bot.

Due livelli di identita'
------------------------
- LINEA (`line_*`): la linea evolutiva scelta in selezione (Charmander, Eevee, ...).
  Chiave = numero del Pokédex nazionale della forma BASE (stadio 0 del JSON).
- FORMA (`form_*`): la forma attuale in partita (Charmeleon, Jolteon, Politoad...,
  piu' le forme temporanee Shedinja della passiva Muta e Ferrosacco della R di
  Delibird). Chiave = numero del Pokédex della forma.

Per ognuno ci sono:
- un INDICE INTERO fisso (`line_id`, `form_id`): per gli embedding appresi
  (nn.Embedding(LINE_VOCAB, d) / nn.Embedding(FORM_VOCAB, d)). 0 = UNKNOWN,
  riservato a "nessuno / sconosciuto" (slot vuoto, Pokémon non registrato).
- un VETTORE fisso (`line_vec`, `form_vec`): riga di una matrice di Hadamard
  (Sylvester) di ordine LINE_DIM=64 / FORM_DIM=128, scalata a norma 1
  (componenti ±1/8 per le linee, ±1/sqrt(128) per le forme). Righe diverse di una
  Hadamard sono ESATTAMENTE ortogonali: similarita' coseno 0 tra ogni coppia,
  distanza euclidea sqrt(2) ~ 1,414 tra ogni coppia (il massimo possibile per
  vettori unitari non opposti). Il vettore dipende solo dall'indice fisso.

Stabilita'
----------
Gli indici sono scritti A MANO nelle tabelle LINES e FORMS qui sotto, non derivati
dall'ordine di config.ROSTER ne' dal caricamento dei JSON. Regole:
  * mai cambiare o riusare un indice gia' assegnato (un modello addestrato lo
    interpreterebbe come un altro Pokémon);
  * un Pokémon nuovo prende il PRIMO INDICE LIBERO IN CODA (linee fino a 63,
    forme fino a 127: c'e' spazio per 37 linee e ~50 forme in piu');
  * una linea/forma tolta dal roster resta in tabella (il suo indice non torna
    libero).
tests/test_poke_tokens.py fotografa gli indici attuali e controlla che ogni linea
del roster e ogni forma dei JSON (evolutions + forme temporanee) sia registrata.

Feature descrittive (separate dal token puro)
---------------------------------------------
`descriptive_features(...)` / `player_features(p)`: vettore multi-hot in {0,1} di
dimensione fissa FEATURE_DIM = 6 categorie + 5 corsie + 18 tipi = 29:
  - categoria (CATEGORIES; "mago mobile" conta come mago),
  - corsie consigliate della linea (LANE_NAMES, dalla tabella LANES di
    game/scenes/char_select_scene.py, letta senza importare pygame),
  - tipi (TYPE_NAMES). Per un giocatore usa i tipi VIVI (Magipolvere li cambia).
Non sono identita': due Pokémon possono avere le stesse feature.

Uso
---
Dal giocatore in partita (engine.entities.Pokemon, anche dentro sim/ e nel
simulatore nativo, dove i Pokémon restano oggetti Python):

    from engine import poke_tokens as T
    T.line_id_of(p), T.form_id_of(p)      # interi per gli embedding
    T.line_vec_of(p), T.form_vec_of(p)    # tuple di float, norma 1
    T.observation(p)                      # linea + forma + feature, dim. OBS_DIM

CMA-ES (tools/cma_tune.py): oggi i parametri sono per GRUPPO (ruolo/jungler/
support), quindi non servono input; per parametri specifici di una linea basta
indicizzare con `line_id_of(p)` (o il nome `LINE_NAME[line_id]`) una tabella di
correzioni, oppure aggiungere al punteggio di utilita' un termine lineare
`dot(w, line_vec_of(p))` con w tra le dimensioni tarate (LINE_DIM pesi: per la
ortogonalita' ogni linea ha il suo "peso" senza interferenze).

RL: concatenare `observation(p)` di se', alleati e nemici (ordine fisso degli
slot; slot vuoto = `observation(None)`, che usa il token UNKNOWN e feature a 0),
oppure passare `line_id_of`/`form_id_of` a uno strato di embedding. Tutti i valori
sono in [-1, 1].
"""
from __future__ import annotations

import ast
import math
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

UNKNOWN = 0

# --- Linee: dex della forma base -> (indice fisso, nome) ----------------------
# NON riordinare, NON riusare indici: le nuove linee vanno in coda (27, 28, ...).
LINES: dict[int, tuple[int, str]] = {
    4:   (1, "Charmander"),
    92:  (2, "Gastly"),
    158: (3, "Totodile"),
    722: (4, "Rowlet"),
    495: (5, "Snivy"),
    290: (6, "Nincada"),
    60:  (7, "Poliwag"),
    524: (8, "Roggenrola"),
    442: (9, "Spiritomb"),
    133: (10, "Eevee"),
    821: (11, "Rookidee"),
    935: (12, "Charcadet"),
    714: (13, "Noibat"),
    216: (14, "Teddiursa"),
    215: (15, "Sneasel"),
    619: (16, "Mienfoo"),
    884: (17, "Duraludon"),
    856: (18, "Hatenna"),
    81:  (19, "Magnemite"),
    220: (20, "Swinub"),
    48:  (21, "Venonat"),
    223: (22, "Remoraid"),
    669: (23, "Flabébé"),
    123: (24, "Scyther"),
    725: (25, "Litten"),
    225: (26, "Delibird"),
}

# --- Forme: dex della forma -> (indice fisso, nome, dex della linea) ----------
# NON riordinare, NON riusare indici: le nuove forme vanno in coda (78, 79, ...).
FORMS: dict[int, tuple[int, str, int]] = {
    4:    (1, "Charmander", 4),
    5:    (2, "Charmeleon", 4),
    6:    (3, "Charizard", 4),
    92:   (4, "Gastly", 92),
    93:   (5, "Haunter", 92),
    94:   (6, "Gengar", 92),
    158:  (7, "Totodile", 158),
    159:  (8, "Croconaw", 158),
    160:  (9, "Feraligatr", 158),
    722:  (10, "Rowlet", 722),
    723:  (11, "Dartrix", 722),
    724:  (12, "Decidueye", 722),
    495:  (13, "Snivy", 495),
    496:  (14, "Servine", 495),
    497:  (15, "Serperior", 495),
    290:  (16, "Nincada", 290),
    291:  (17, "Ninjask", 290),
    292:  (18, "Shedinja", 290),      # forma temporanea (passiva Muta / R Rancore)
    60:   (19, "Poliwag", 60),
    61:   (20, "Poliwhirl", 60),
    62:   (21, "Poliwrath", 60),
    186:  (22, "Politoad", 60),
    524:  (23, "Roggenrola", 524),
    525:  (24, "Boldore", 524),
    526:  (25, "Gigalith", 524),
    442:  (26, "Spiritomb", 442),
    133:  (27, "Eevee", 133),
    135:  (28, "Jolteon", 133),
    136:  (29, "Flareon", 133),
    196:  (30, "Espeon", 133),
    471:  (31, "Glaceon", 133),
    470:  (32, "Leafeon", 133),
    197:  (33, "Umbreon", 133),
    700:  (34, "Sylveon", 133),
    134:  (35, "Vaporeon", 133),
    821:  (36, "Rookidee", 821),
    822:  (37, "Corvisquire", 821),
    823:  (38, "Corviknight", 821),
    935:  (39, "Charcadet", 935),
    936:  (40, "Armarouge", 935),
    937:  (41, "Ceruledge", 935),
    714:  (42, "Noibat", 714),
    715:  (43, "Noivern", 714),
    216:  (44, "Teddiursa", 216),
    217:  (45, "Ursaring", 216),
    901:  (46, "Ursaluna", 216),
    215:  (47, "Sneasel", 215),
    461:  (48, "Weavile", 215),
    903:  (49, "Sneasler", 215),
    619:  (50, "Mienfoo", 619),
    620:  (51, "Mienshao", 619),
    884:  (52, "Duraludon", 884),
    1018: (53, "Archaludon", 884),
    856:  (54, "Hatenna", 856),
    857:  (55, "Hattrem", 856),
    858:  (56, "Hatterene", 856),
    81:   (57, "Magnemite", 81),
    82:   (58, "Magneton", 81),
    462:  (59, "Magnezone", 81),
    220:  (60, "Swinub", 220),
    221:  (61, "Piloswine", 220),
    473:  (62, "Mamoswine", 220),
    48:   (63, "Venonat", 48),
    49:   (64, "Venomoth", 48),
    223:  (65, "Remoraid", 223),
    224:  (66, "Octillery", 223),
    669:  (67, "Flabébé", 669),
    670:  (68, "Floette", 669),
    671:  (69, "Florges", 669),
    123:  (70, "Scyther", 123),
    212:  (71, "Scizor", 123),
    900:  (72, "Kleavor", 123),
    725:  (73, "Litten", 725),
    726:  (74, "Torracat", 725),
    727:  (75, "Incineroar", 725),
    225:  (76, "Delibird", 225),
    991:  (77, "Ferrosacco", 225),    # forma temporanea (R Paradosso Futuro)
}

SHEDINJA_DEX = 292                    # p.form == "shedinja" non cambia p.dex

LINE_DIM = 64                         # ordine Hadamard: 63 linee + UNKNOWN
FORM_DIM = 128                        # ordine Hadamard: 127 forme + UNKNOWN
LINE_VOCAB = LINE_DIM                 # taglia dell'embedding (indici 0..63)
FORM_VOCAB = FORM_DIM                 # indici 0..127

LINE_NAME = {UNKNOWN: "?", **{i: n for i, n in LINES.values()}}
FORM_NAME = {UNKNOWN: "?", **{i: n for i, n, _ in FORMS.values()}}
_LINE_BY_NAME = {n: d for d, (_, n) in LINES.items()}
_FORM_BY_NAME = {n: d for d, (_, n, _) in FORMS.items()}

# --- Feature descrittive -------------------------------------------------------
CATEGORIES = ("combattente", "mago", "tiratore", "assassino", "tank", "supporto")
_CATEGORY_ALIAS = {"mago mobile": "mago"}
LANE_NAMES = ("top", "giungla", "mid", "bottom", "support")
TYPE_NAMES = ("Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting",
              "Poison", "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost",
              "Dragon", "Dark", "Steel", "Fairy")
FEATURE_DIM = len(CATEGORIES) + len(LANE_NAMES) + len(TYPE_NAMES)
OBS_DIM = LINE_DIM + FORM_DIM + FEATURE_DIM


# --- Vettori -------------------------------------------------------------------
def _hadamard_row(i: int, n: int) -> tuple[float, ...]:
    """Riga i della Hadamard di Sylvester di ordine n (potenza di 2), norma 1:
    H[i][j] = (-1)^popcount(i & j) / sqrt(n)."""
    s = 1.0 / math.sqrt(n)
    return tuple(-s if bin(i & j).count("1") & 1 else s for j in range(n))


@lru_cache(maxsize=None)
def line_vec(line_id: int) -> tuple[float, ...]:
    """Vettore fisso (norma 1, dim LINE_DIM) dell'indice di linea."""
    if not 0 <= line_id < LINE_DIM:
        line_id = UNKNOWN
    return _hadamard_row(line_id, LINE_DIM)


@lru_cache(maxsize=None)
def form_vec(form_id: int) -> tuple[float, ...]:
    """Vettore fisso (norma 1, dim FORM_DIM) dell'indice di forma."""
    if not 0 <= form_id < FORM_DIM:
        form_id = UNKNOWN
    return _hadamard_row(form_id, FORM_DIM)


# --- Ricerca per dex / nome ----------------------------------------------------
def line_id(dex_or_name) -> int:
    """Indice della linea dal dex della forma base, dal nome della linea, o da
    QUALSIASI forma della linea (dex o nome). UNKNOWN se non registrata."""
    d = _to_dex(dex_or_name)
    if d in LINES:
        return LINES[d][0]
    if d in FORMS:
        return LINES[FORMS[d][2]][0]
    return UNKNOWN


def form_id(dex_or_name) -> int:
    """Indice della forma dal suo dex o nome. UNKNOWN se non registrata."""
    f = FORMS.get(_to_dex(dex_or_name))
    return f[0] if f else UNKNOWN


def _to_dex(x) -> int | None:
    if isinstance(x, str):
        return _LINE_BY_NAME.get(x, _FORM_BY_NAME.get(x))
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


# --- Dal giocatore in partita (engine.entities.Pokemon) --------------------------
def _form_dex(p) -> int | None:
    if getattr(p, "form", "") == "shedinja":
        return SHEDINJA_DEX
    return getattr(p, "dex", None)


def _line_dex(p) -> int | None:
    evos = getattr(p, "evolutions", None) or ()
    if evos:
        base = min(evos, key=lambda st: st.get("stage", 0))
        if "dex" in base:
            return int(base["dex"])
    d = _form_dex(p)
    return FORMS[d][2] if d in FORMS else d


def line_id_of(p) -> int:
    """Indice della linea di un giocatore (None -> UNKNOWN)."""
    return UNKNOWN if p is None else line_id(_line_dex(p))


def form_id_of(p) -> int:
    """Indice della forma ATTUALE di un giocatore (None -> UNKNOWN)."""
    return UNKNOWN if p is None else form_id(_form_dex(p))


def line_vec_of(p) -> tuple[float, ...]:
    return line_vec(line_id_of(p))


def form_vec_of(p) -> tuple[float, ...]:
    return form_vec(form_id_of(p))


# --- Feature descrittive -------------------------------------------------------
@lru_cache(maxsize=1)
def lanes_table() -> dict[str, tuple[str, ...]]:
    """LANES di game/scenes/char_select_scene.py (nome linea -> corsie), letta
    dal sorgente con ast per non importare pygame."""
    src = (ROOT / "game" / "scenes" / "char_select_scene.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and getattr(node.targets[0], "id", None) == "LANES"):
            return {k: tuple(v) for k, v in ast.literal_eval(node.value).items()}
    return {}


def descriptive_features(role: str = "", lanes=(), types=()) -> tuple[float, ...]:
    """Multi-hot {0,1} di dimensione FEATURE_DIM: categoria | corsie | tipi."""
    role = _CATEGORY_ALIAS.get(role, role)
    lanes, types = set(lanes or ()), set(types or ())
    return (tuple(1.0 if c == role else 0.0 for c in CATEGORIES)
            + tuple(1.0 if l in lanes else 0.0 for l in LANE_NAMES)
            + tuple(1.0 if t in types else 0.0 for t in TYPE_NAMES))


def player_features(p) -> tuple[float, ...]:
    """Feature descrittive VIVE di un giocatore (ruolo e tipi della forma attuale,
    corsie della linea). None -> tutto 0."""
    if p is None:
        return (0.0,) * FEATURE_DIM
    lanes = lanes_table().get(LINE_NAME.get(line_id_of(p), ""), ())
    return descriptive_features(getattr(p, "role", ""), lanes, getattr(p, "types", ()))


def observation(p) -> tuple[float, ...]:
    """line_vec | form_vec | feature, dimensione OBS_DIM, valori in [-1, 1]."""
    return line_vec_of(p) + form_vec_of(p) + player_features(p)
