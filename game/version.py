"""Versione del gioco e repository delle GitHub Releases.

BUILD a zero vuol dire "copia di sviluppo" (python run_client.py o exe fatto in
casa con crea_exe.bat): niente controllo degli aggiornamenti. La GitHub Action
(.github/workflows/release.yml) parte quando in cima a data/news.json c'e' una
versione 3.0.N non ancora pubblicata: riscrive BUILD = SERIES_BASE + N
(tools/release_info.py) prima di creare l'exe, e pubblica la Release col tag
"v<BUILD>" (numerico: l'updater confronta quello) e il nome "PokéMoba <name()>".

Versione mostrata: SERIE (decisa a mano, es. "3.0") + numero di patch:
patch = BUILD - SERIES_BASE. Per passare a una serie nuova
(es. 3.1 o 4.0) si cambiano SERIES e SERIES_BASE = numero dell'ultima build
della serie precedente.
"""

BUILD = 0
REPO = "OWNER/REPO"          # "utente/nome-repo" su github.com
ASSET = "PokeMoba.exe"       # nome del file allegato a ogni Release
SERIES = "3.0"
SERIES_BASE = 4              # build 4 = 3.0.1 (max 1), build 6 = 3.0.2: la run 5 e' fallita


def name() -> str:
    """Versione leggibile, es. "3.0.1" ("3.0 dev" per le copie di sviluppo)."""
    return name_of(BUILD)


def name_of(build: int) -> str:
    """Nome leggibile di una build qualunque (es. quella appena scaricata)."""
    return f"{SERIES}.{max(1, build - SERIES_BASE)}" if build else f"{SERIES} dev"


def label() -> str:
    return f"v{name()}" if BUILD else name()
