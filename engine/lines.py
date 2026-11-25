"""Registro delle LINEE di Pokémon con logica propria nel motore.

Ogni linea vive nel suo modulo (engine/<pokemon>.py) come mixin di Match e
dichiara nell'attributo di classe `LINE` quali metodi agganciare:

    LINE = {
        "passives": frozenset({...}),   # passive della linea (per l'IA dei bot)
        "init": "_init_xxx",            # Match.__init__: crea le proprie liste
        "update": "_update_xxx",        # ogni tick, prima delle mosse generiche
        "precheck": "_xxx_precheck",    # (p, mv, tgt) -> False = la mossa non parte
        "cast": "_xxx_cast",            # (p, mv, rank, origin, tgt, dirv) -> True se gestita
        "bot_cast": "_bot_xxx_cast",    # (p, target) -> True se il bot ha lanciato
        "speed_mult": "_xxx_speed_mult",  # (p) -> moltiplicatore della velocità
        "net": {                        # cosa passa al client online (net/visual.py)
            "lists": {"xxx_zones": "c"},    # liste del Match filtrate dalla visione:
                                            # nome -> chiave della posizione
            "shared": ("xxx_walls",),       # liste che vedono TUTTE e due le squadre
            "moving": ("xxx_bolts",),       # liste con pos/dir/speed: il client le fa avanzare
            "unit_flags": {"xxx_stacks": 0},  # campi dell'unità (non timer) + valore "spento"
            "me": ("xxx_ready",),           # campi del proprio Pokémon per l'HUD
        },
    }

I timer *_until / *_ready_at delle unità passano da soli (net/visual.timer_fields).

Tutti i campi tranne "passives" sono facoltativi. Match chiama gli agganci
nell'ordine di LINE_MIXINS.

PER AGGIUNGERE UNA LINEA: scrivi il mixin con il suo `LINE` e aggiungilo a
LINE_MIXINS. Non serve toccare engine/match.py, net/visual.py né
game/online_world.py: Match chiama gli agganci e la rete legge "net" da qui.
Resta da fare a mano la GRAFICA (game/<linea>_fx.py, registrato in game/fx.py).
tests/test_lines.py controlla che ogni metodo dichiarato esista e che due mixin
non definiscano lo stesso nome di metodo (si coprirebbero a vicenda in silenzio).
"""
from __future__ import annotations

from .archaludon import ArchaludonMixin
from .charcadet import CharcadetMixin
from .corviknight import CorviknightMixin
from .delibird import DelibirdMixin
from .eevee import EeveeMixin
from .florges import FlorgesMixin
from .hatterene import HattereneMixin
from .incineroar import IncineroarMixin
from .magnezone import MagnezoneMixin
from .mamoswine import MamoswineMixin
from .mienshao import MienshaoMixin
from .noivern import NoivernMixin
from .octillery import OctilleryMixin
from .scizor import ScizorMixin
from .sneasel import SneaselMixin
from .spiritomb import SpiritombMixin
from .ursaring import UrsaringMixin
from .venomoth import VenomothMixin

# L'ORDINE conta: è quello in cui si chiamano init/update/precheck/cast/bot_cast.
LINE_MIXINS: tuple = (
    SpiritombMixin, EeveeMixin, CorviknightMixin, CharcadetMixin, NoivernMixin,
    UrsaringMixin, SneaselMixin, MienshaoMixin, ArchaludonMixin, HattereneMixin,
    MagnezoneMixin, MamoswineMixin, VenomothMixin, OctilleryMixin, FlorgesMixin,
    ScizorMixin, IncineroarMixin, DelibirdMixin,
)

HOOK_KINDS = ("init", "update", "precheck", "cast", "bot_cast", "speed_mult")
NET_KINDS = ("lists", "shared", "moving", "unit_flags", "me")


_HOOK_CACHE: dict = {}


def hook_names(kind: str) -> tuple:
    """Nomi dei metodi agganciati a `kind`, nell'ordine del registro (in cache:
    LINE_MIXINS e i loro LINE non cambiano a partita in corso)."""
    r = _HOOK_CACHE.get(kind)
    if r is None:
        r = _HOOK_CACHE[kind] = tuple(m.LINE[kind] for m in LINE_MIXINS if m.LINE.get(kind))
    return r


def bot_cast_table() -> tuple:
    """((passive della linea, nome del metodo), ...) per l'IA dei bot (in cache)."""
    r = _HOOK_CACHE.get("_bot_cast_table")
    if r is None:
        r = _HOOK_CACHE["_bot_cast_table"] = tuple(
            (m.LINE["passives"], m.LINE["bot_cast"])
            for m in LINE_MIXINS if m.LINE.get("bot_cast"))
    return r


_BOT_CAST_BY_PASSIVE: dict = {}


def bot_cast_names(passive_id) -> tuple:
    """Metodi di bot_cast_table() la cui linea ha `passive_id`, nello stesso ordine."""
    r = _BOT_CAST_BY_PASSIVE.get(passive_id)
    if r is None:
        r = _BOT_CAST_BY_PASSIVE[passive_id] = tuple(
            name for passives, name in bot_cast_table() if passive_id in passives)
    return r


def net_table(kind: str):
    """Unione delle dichiarazioni "net" delle linee per `kind` (vedi NET_KINDS):
    dict per "lists"/"unit_flags", tupla (senza doppioni) per gli altri."""
    if kind in ("lists", "unit_flags"):
        out: dict = {}
        for m in LINE_MIXINS:
            out.update(m.LINE.get("net", {}).get(kind, {}))
        return out
    seen: dict = {}
    for m in LINE_MIXINS:
        for name in m.LINE.get("net", {}).get(kind, ()):
            seen.setdefault(name, None)
    return tuple(seen)
