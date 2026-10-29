"""Scarica le immagini PROFILO (ritratti "Normal" dei Pokémon leggendari) da
PMD Sprite Collab e ne salva i crediti.

    python tools/fetch_avatars.py

Risultato:
  assets/avatars/<dex>.png   ritratto 40x40 "Normal"
  assets/avatars/credits.json  {dex: {"name", "authors": [...]}}  (letto dai crediti
                               nel menu e da CREDITS.md)

Fonte: https://sprites.pmdcollab.org/ (repository PMDCollab/SpriteCollab),
licenza CC BY-NC 4.0. Gli autori per ritratto vengono da portrait/<dex>/credits.txt
(solo le righe che riguardano l'emozione Normal) e i nomi da credit_names.txt.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game.avatars import AVATARS  # noqa: E402

RAW = "https://raw.githubusercontent.com/PMDCollab/SpriteCollab/master"
OUT = ROOT / "assets" / "avatars"


def get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.read()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    names = {}
    for line in get(f"{RAW}/credit_names.txt").decode("utf-8").splitlines()[1:]:
        cols = line.split("\t")
        if cols and cols[0]:
            # credits.txt cita l'autore col nome o con l'id Discord: entrambi -> nome.
            names[cols[0]] = cols[0]
            if len(cols) > 1 and cols[1]:
                names[cols[1]] = cols[0]
    credits = {}
    for dex, name in AVATARS:
        d = f"{dex:04d}"
        try:
            png = get(f"{RAW}/portrait/{d}/Normal.png")
        except Exception as e:                  # ritratto mancante: si salta
            print(f"  {d} {name}: manca ({e})")
            continue
        (OUT / f"{d}.png").write_bytes(png)
        authors = []
        try:
            for line in get(f"{RAW}/portrait/{d}/credits.txt").decode("utf-8").splitlines():
                cols = line.split("\t")
                if len(cols) >= 5 and "Normal" in cols[4].split(","):
                    who = names.get(cols[1], cols[1])
                    if who.startswith("<@"):    # autore senza nome registrato
                        who = "utente Discord " + who.strip("<@!>")
                    if who not in authors:
                        authors.append(who)
        except Exception:
            pass
        credits[d] = {"name": name, "authors": authors or ["sconosciuto"]}
        print(f"  {d} {name}: {', '.join(credits[d]['authors'])}")
    (OUT / "credits.json").write_text(json.dumps(credits, indent=1, ensure_ascii=False),
                                      encoding="utf-8")
    (OUT / "CREDITS.md").write_text(credits_md(credits), encoding="utf-8")
    print(f"{len(credits)}/{len(AVATARS)} ritratti in {OUT}")


def credits_md(credits) -> str:
    """Tabella dei crediti dei ritratti (anche incollata in CREDITS.md)."""
    rows = ["# Crediti delle immagini profilo", "",
            'Ritratti "Normal" da **PMD Sprite Collab** - https://sprites.pmdcollab.org/',
            "(repository https://github.com/PMDCollab/SpriteCollab), licenza",
            "**CC BY-NC 4.0** - https://creativecommons.org/licenses/by-nc/4.0/.",
            "CHUNSOFT = ritratti originali di Pokémon Mystery Dungeon (Spike Chunsoft).", "",
            "| N. | Pokémon | Autori del ritratto |", "|---|---|---|"]
    for d, c in sorted(credits.items()):
        rows.append(f"| {int(d)} | {c['name']} | {', '.join(c['authors'])} |")
    return "\n".join(rows) + "\n"


if __name__ == "__main__":
    main()
