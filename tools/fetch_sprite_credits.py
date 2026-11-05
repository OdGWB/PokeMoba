"""Scarica i crediti degli sprite in assets/pokemon/ da PMD Sprite Collab.

Per ogni cartella assets/pokemon/<dex> legge sprite/<dex>/credits.txt dal
repository PMDCollab/SpriteCollab (lo stesso file linkato in ogni pagina di
https://sprites.pmdcollab.org/) e risolve gli id Discord con credit_names.txt.
Come richiede il "Proper Crediting" del progetto, gli autori sono elencati
SEPARATAMENTE per ogni sprite.

Scrive:
  assets/pokemon/credits.json   {dex: {"name", "authors": [...]}} (letto dalla
                                schermata Crediti del menu)
  CREDITS.md                    sezione tra i marcatori SPRITE-CREDITS

Uso: python tools/fetch_sprite_credits.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POKE = ROOT / "assets" / "pokemon"
RAW = "https://raw.githubusercontent.com/PMDCollab/SpriteCollab/master"
# Minion (assets/minions/<squadra>_<tipo>): sprite identici a quelli di SpriteCollab.
MINIONS = {"0010": "minion blu mischia", "0016": "minion blu a distanza",
           "0021": "minion blu cannone", "0399": "minion rosso mischia",
           "0396": "minion rosso a distanza", "0415": "minion rosso cannone"}
BEGIN, END = "<!-- SPRITE-CREDITS:BEGIN -->", "<!-- SPRITE-CREDITS:END -->"


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def who_name(raw: str, names: dict[str, str]) -> str:
    who = names.get(raw, raw)
    if who.startswith("<@"):                 # autore senza nome registrato
        who = "utente Discord " + who.strip("<@!>")
    return who


def main() -> int:
    names: dict[str, str] = {}
    for line in get(f"{RAW}/credit_names.txt").decode("utf-8").splitlines()[1:]:
        cols = line.split("\t")
        if cols and cols[0]:
            names[cols[0]] = cols[0]
            if len(cols) > 1 and cols[1]:
                names[cols[1]] = cols[0]
    tracker = json.loads(get(f"{RAW}/tracker.json").decode("utf-8"))
    credits: dict[str, dict] = {}
    folders = {p.name for p in POKE.iterdir() if p.is_dir() and p.name.isdigit()}
    for folder in sorted(folders | set(MINIONS)):
        authors: list[str] = []
        try:
            text = get(f"{RAW}/sprite/{folder}/credits.txt").decode("utf-8")
        except Exception as e:
            print(f"  {folder}: credits.txt mancante ({e})")
            text = ""
        for line in text.splitlines():
            cols = line.split("\t")
            if len(cols) >= 2 and cols[1].strip():
                who = who_name(cols[1].strip(), names)
                if who not in authors:
                    authors.append(who)
        name = tracker.get(folder, {}).get("name", folder)
        credits[folder] = {"name": name, "authors": authors or ["sconosciuto"]}
        if folder in MINIONS:
            credits[folder]["role"] = MINIONS[folder]
        print(f"  {folder} {name}: {', '.join(credits[folder]['authors'])}")
    (POKE / "credits.json").write_text(
        json.dumps(credits, indent=1, ensure_ascii=False), encoding="utf-8")
    update_credits_md(credits)
    print(f"{len(credits)} sprite con crediti")
    return 0


def update_credits_md(credits: dict) -> None:
    rows = [BEGIN, "",
            "Gli autori di ciascuno sprite sono elencati separatamente, come richiesto dal",
            "\"Proper Crediting\" di PMD Sprite Collab (fonte: `sprite/<dex>/credits.txt`",
            "del repository, generato con `python tools/fetch_sprite_credits.py`).",
            "CHUNSOFT = sprite originali di Pokémon Mystery Dungeon (Spike Chunsoft).", "",
            "| N. | Pokémon | Autori dello sprite |", "|---|---|---|"]
    for d, c in sorted(credits.items()):
        role = f" ({c['role']})" if c.get("role") else ""
        rows.append(f"| {int(d)} | {c['name']}{role} | {', '.join(c['authors'])} |")
    rows += ["", END]
    block = "\n".join(rows)
    path = ROOT / "CREDITS.md"
    md = path.read_text(encoding="utf-8")
    if BEGIN in md:
        md = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda m: block, md,
                    flags=re.S)
    else:
        marker = "> Nota: gli sprite non sono inclusi"
        i = md.index(marker)
        j = md.index("\n\n", i) + 2
        md = md[:j] + block + "\n\n" + md[j:]
    path.write_text(md, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
