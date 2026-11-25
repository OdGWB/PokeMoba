"""Validazione lato host di tutto ciò che arriva dai client.

Regola d'oro: il client NON dichiara mai posizioni, danni, kill o l'entità
che controlla. Manda solo intenzioni ("voglio andare lì"); l'host ricava
l'entità dallo slot del mittente e controlla ogni campo:
- coordinate: tagliate dentro la mappa (clamp);
- slot mossa 0..3, scelta 0..1, slot oggetto 0..5, oggetto nel catalogo;
- bersaglio: deve esistere, essere vivo, nemico e VISIBILE alla squadra
  (niente attacchi a chi è nella nebbia: sarebbe un'informazione rubata);
- rate limiting a secchiello (token bucket) per pacchetti, comandi, azioni,
  chat; chi sfora troppe volte viene espulso.
"""
from __future__ import annotations

import math
import time


class TokenBucket:
    """`rate` gettoni al secondo, al massimo `burst` accumulati."""

    __slots__ = ("rate", "burst", "tokens", "t")

    def __init__(self, rate: float, burst: float):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.t = time.monotonic()

    def take(self, n: float = 1.0, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        self.tokens = min(self.burst, self.tokens + (now - self.t) * self.rate)
        self.t = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


# Limiti per client (generosi per un giocatore vero, stretti per un flood).
INPUT_PACKETS = (120.0, 40.0)    # pacchetti C_INPUT/s (il client ne manda ~60)
COMMANDS = (20.0, 12.0)          # comandi NUOVI/s (click, mosse)
ACTIONS = (10.0, 10.0)           # acquisti, gradi, scelte
CHAT = (2.0, 5.0)
TEAM = (3.0, 8.0)                # ping e chat rapida (oltre: scartati in silenzio)
RELIABLE = (60.0, 60.0)          # TUTTI i messaggi del canale reliable (ping 1/s, il resto a click)
LOBBY = (15.0, 15.0)             # scelte di lobby e anteprime del draft: ognuna fa un broadcast
                                 # a tutti, quindi un flood si moltiplicherebbe per 9
KICK_STRIKES = 200               # violazioni prima dell'espulsione


class ClientGuard:
    """Secchielli e contatore di violazioni di un client."""

    def __init__(self):
        self.packets = TokenBucket(*INPUT_PACKETS)
        self.commands = TokenBucket(*COMMANDS)
        self.actions = TokenBucket(*ACTIONS)
        self.chat = TokenBucket(*CHAT)
        self.team = TokenBucket(*TEAM)
        self.reliable = TokenBucket(*RELIABLE)
        self.lobby = TokenBucket(*LOBBY)
        self.strikes = 0
        self.rejected = 0

    def strike(self, n: int = 1) -> bool:
        """Registra una violazione. True = da espellere."""
        self.strikes += n
        self.rejected += 1
        return self.strikes >= KICK_STRIKES


def clamp_point(x: float, y: float, width: int, height: int):
    """Punto dentro la mappa, o None se non è un numero."""
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return (min(max(x, 0.0), width - 0.01), min(max(y, 0.0), height - 0.01))


def valid_move_slot(slot) -> bool:
    return isinstance(slot, int) and 0 <= slot <= 3


def valid_choice(index) -> bool:
    return isinstance(index, int) and 0 <= index <= 1


def valid_item_slot(slot) -> bool:
    return isinstance(slot, int) and 0 <= slot <= 5


def valid_avatar(dex) -> int:
    """Immagine profilo = numero di Pokédex; fuori intervallo diventa 0 (nessuna).
    Se il ritratto non c'è in assets/avatars il gioco mostra un riquadro vuoto."""
    return dex if isinstance(dex, int) and 0 <= dex <= 1025 else 0


def allowed_map(path) -> str | None:
    """Percorso della mappa mandato dall'host, solo se e' una delle mappe di
    config.MAPS. Mai unire alla cartella del gioco un percorso arbitrario: su
    Windows "//pc/condivisa/x.json" diventa un percorso UNC e il gioco si
    collegherebbe a un server SMB altrui (furto dell'hash NTLM); anche "C:/..."
    e "../" uscirebbero dalla cartella."""
    import config
    allowed = {p for _name, p in config.MAPS} | {config.DEFAULT_MAP}
    return path if isinstance(path, str) and path in allowed else None


def valid_roster_index(i) -> bool:
    import config
    return isinstance(i, int) and 0 <= i < len(config.ROSTER)


def clean_text(text: str, limit: int = 120) -> str:
    """Testo di chat/nome senza caratteri di controllo."""
    return "".join(ch for ch in (text or "") if ch.isprintable())[:limit].strip()
