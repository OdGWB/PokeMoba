"""Versione del gioco e repository delle GitHub Releases.

BUILD a zero vuol dire "copia di sviluppo" (python run_client.py o exe fatto in
casa con crea_exe.bat): niente controllo degli aggiornamenti. La GitHub Action
(.github/workflows/release.yml) parte quando in cima a data/news.json c'e' una
versione SERIE.N non ancora pubblicata: riscrive BUILD = SERIES_BASE + N
(tools/release_info.py) prima di creare l'exe, e pubblica la Release col tag
"v<BUILD>" (numerico: l'updater confronta quello) e il nome "PokéMoba <name()>".

Versione mostrata: SERIE (decisa a mano, es. "3.0") + numero di patch:
patch = BUILD - SERIES_BASE. Per passare a una serie nuova
(es. 3.1 o 4.0) si cambiano SERIES e SERIES_BASE = numero dell'ultima build
della serie precedente.

RICOSTRUZIONI (REBUILDS): build in piu' della STESSA versione (es. un asset
dimenticato nella Release). L'updater confronta solo il numero di build, quindi
gli exe installati le scaricano, ma il nome resta quello della versione
precedente e le patch successive slittano di uno (build 8 = 3.1.0 ricostruita,
build 10 = 3.1.1). Per farne una: aggiungere qui la build nuova e fare push su
main (la Release parte anche per le modifiche a questo file).
"""

BUILD = 0
REPO = "OWNER/REPO"          # "utente/nome-repo" su github.com
ASSET = "PokeMoba.exe"       # nome del file allegato a ogni Release
# Chiave PUBBLICA Ed25519 (64 cifre esadecimali) con cui l'updater verifica la firma
# dell'exe nuovo (game/updater.py). Vuota = firma non richiesta. Si genera con
#   python tools/release_sign.py setup
# (la privata va SOLO nel secret UPDATE_SIGNING_KEY dell'environment "release"
# del repo, mai mostrata ne' salvata). ATTENZIONE: gli exe
# pubblicati con la chiave impostata rifiutano le Release non firmate.
UPDATE_PUBKEY = "db61360c46f3c55824e68701c6680c293ebde6ae6473518a327e9f40c8844c92"
SERIES = "3.2"
SERIES_BASE = 10             # build 10 = 3.2.0 (serie 3.1: build 7 = 3.1.0, ricostruita come 8 e 9)
REBUILDS = ()                # build in piu' della stessa versione (vedi sopra)


def name() -> str:
    """Versione leggibile, es. "3.1.0" ("3.1 dev" per le copie di sviluppo)."""
    return name_of(BUILD)


def name_of(build: int) -> str:
    """Nome leggibile di una build qualunque (es. quella appena scaricata)."""
    if not build:
        return f"{SERIES} dev"
    patch = build - SERIES_BASE - sum(1 for b in REBUILDS if SERIES_BASE < b <= build)
    return f"{SERIES}.{max(0, patch)}"


def label() -> str:
    return f"v{name()}" if BUILD else name()
