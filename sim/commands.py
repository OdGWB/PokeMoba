"""Comandi di input del giocatore.

Punto chiave dell'architettura: l'input NON modifica direttamente lo stato, ma
produce comandi con un numero di sequenza. In single-player (Fase 1) vengono
applicati localmente; in Fase 5 gli stessi comandi viaggeranno via rete senza
cambiare nulla qui.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Command:
    seq: int          # numero di sequenza crescente per client
    entity_id: int    # unità che il comando controlla


@dataclass
class MoveCommand(Command):
    """Ordine di muoversi verso una posizione (in coordinate tile, float)."""
    x: float = 0.0
    y: float = 0.0


@dataclass
class StopCommand(Command):
    """Ferma l'unità dove si trova."""


@dataclass
class AttackCommand(Command):
    """Attacca (e insegue) un bersaglio specifico."""
    target_id: int = 0


@dataclass
class AttackMoveCommand(Command):
    """Vai verso un punto attaccando i nemici incontrati (attack-move).
    champs_only: tasto "solo Pokémon" tenuto (ignora minion, neutrali, strutture)."""
    x: float = 0.0
    y: float = 0.0
    champs_only: bool = False


@dataclass
class CastMoveCommand(Command):
    """Lancia la mossa di uno slot (Q/W/E/R) verso un punto/direzione."""
    slot: str = "Q"
    x: float = 0.0
    y: float = 0.0
    hold: float = 0.0   # secondi di pressione del tasto (mosse a carica: Tiro Lungo)


@dataclass
class RankMoveCommand(Command):
    """Assegna un punto mossa a uno slot (Ctrl+Q/W/E/R)."""
    slot: str = "Q"


@dataclass
class ChooseUpgradeCommand(Command):
    """Sceglie un potenziamento/ultimate per uno slot (menu evoluzione)."""
    slot: str = "Q"
    index: int = 0


@dataclass
class BuyItemCommand(Command):
    """Compra un oggetto dal negozio (solo in base)."""
    item_id: str = ""


@dataclass
class SellItemCommand(Command):
    """Vende l'oggetto nello slot indicato."""
    slot: int = 0


@dataclass
class UseItemCommand(Command):
    """Attiva l'oggetto nello slot indicato (Mentalerba, Palla Fumo)."""
    slot: int = 0


@dataclass
class RecallCommand(Command):
    """Avvia (o annulla) il richiamo verso la base."""


@dataclass
class SmiteCommand(Command):
    """Usa lo Smite sul neutrale piu' vicino a portata (tasto D, solo partita locale)."""
