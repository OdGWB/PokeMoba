"""Versione del gioco e repository delle GitHub Releases.

BUILD a zero vuol dire "copia di sviluppo" (python run_client.py o exe fatto in
casa con crea_exe.bat): niente controllo degli aggiornamenti. La GitHub Action
(.github/workflows/release.yml) riscrive BUILD col numero della build prima di
creare l'exe, e pubblica la Release col tag "v<BUILD>".
"""

BUILD = 0
REPO = "OWNER/REPO"          # "utente/nome-repo" su github.com
ASSET = "PokeMoba.exe"       # nome del file allegato a ogni Release


def label() -> str:
    return f"v{BUILD}" if BUILD else "dev"
