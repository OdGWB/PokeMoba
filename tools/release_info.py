"""Dati della prossima Release, ricavati dalla voce piu' recente di data/news.json.

Usato da .github/workflows/release.yml: la Release si fa SOLO quando in cima alle
novita' c'e' una versione che non e' ancora stata pubblicata. La versione "SERIE.N"
decide il numero della build (BUILD = SERIES_BASE + N, vedi game/version.py) e
quindi il tag "v<BUILD>" che l'updater confronta.

    python tools/release_info.py            # stampa i dati
    python tools/release_info.py --notes    # scrive le note in notes.md
    python tools/release_info.py --github   # notes.md + version/build/tag in $GITHUB_OUTPUT
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game import version  # noqa: E402


def build_of(ver: str) -> int:
    """'3.1.2' -> 9 con SERIES "3.1" e SERIES_BASE 7 (la patch parte da 0: 3.1.0 = 7).
    Errore se la serie non e' quella
    di game/version.py (per una serie nuova si cambiano SERIES e SERIES_BASE)."""
    series, _, patch = ver.rpartition(".")
    if series != version.SERIES or not patch.isdigit():
        raise ValueError(f"versione {ver!r} fuori dalla serie {version.SERIES}.N "
                         "(aggiorna SERIES/SERIES_BASE in game/version.py)")
    build = version.SERIES_BASE + int(patch)
    assert version.name_of(build) == ver
    return build


def notes(entry: dict) -> str:
    lines = [f"**{entry.get('title', '')}**", ""]
    lines += [f"- {it}" for it in entry.get("items", [])]
    lines += ["", "**Download:** scarica ed esegui **PokeMoba-Setup.exe**. Chi ha già "
              "il gioco riceve l'aggiornamento da solo all'avvio.", "",
              "<sub>PokeMoba.exe è il file usato dall'aggiornamento automatico.</sub>"]
    return "\n".join(lines) + "\n"


def info(path: pathlib.Path = ROOT / "data" / "news.json") -> dict:
    news = json.loads(path.read_text(encoding="utf-8"))
    if not news:
        raise ValueError("data/news.json e' vuoto")
    top = news[0]
    build = build_of(top["version"])
    return {"version": top["version"], "build": build, "tag": f"v{build}",
            "notes": notes(top)}


def main() -> None:
    d = info()
    if "--github" in sys.argv or "--notes" in sys.argv:
        (ROOT / "notes.md").write_text(d["notes"], encoding="utf-8")
    if "--github" in sys.argv:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            for k in ("version", "build", "tag"):
                print(f"{k}={d[k]}", file=fh)
    print(f"versione {d['version']}  build {d['build']}  tag {d['tag']}")
    print(d["notes"])


if __name__ == "__main__":
    main()
