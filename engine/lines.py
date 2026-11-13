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
    }

Tutti i campi tranne "passives" sono facoltativi. Match chiama gli agganci
nell'ordine di LINE_MIXINS.

PER AGGIUNGERE UNA LINEA: scrivi il mixin con il suo `LINE` e aggiungilo a
LINE_MIXINS. Non serve toccare engine/match.py per questi agganci.
tests/test_lines.py controlla che ogni metodo dichiarato esista e che due mixin
non definiscano lo stesso nome di metodo (si coprirebbero a vicenda in silenzio).
"""
from __future__ import annotations

from .archaludon import ArchaludonMixin
from .charcadet import CharcadetMixin
from .corviknight import CorviknightMixin
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
    ScizorMixin, IncineroarMixin,
)

HOOK_KINDS = ("init", "update", "precheck", "cast", "bot_cast", "speed_mult")


def hook_names(kind: str) -> tuple:
    """Nomi dei metodi agganciati a `kind`, nell'ordine del registro."""
    return tuple(m.LINE[kind] for m in LINE_MIXINS if m.LINE.get(kind))


def bot_cast_table() -> tuple:
    """((passive della linea, nome del metodo), ...) per l'IA dei bot."""
    return tuple((m.LINE["passives"], m.LINE["bot_cast"])
                 for m in LINE_MIXINS if m.LINE.get("bot_cast"))
