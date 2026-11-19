"""Novità e patch notes (data/news.json), mostrate dal pannello del menu.

Il file è una lista di voci, la PIÙ RECENTE PER PRIMA:
    {"version": "3.0.1", "date": "AAAA-MM-GG", "title": "...", "items": ["...", ...]}
Se ne tengono al massimo MAX_ENTRIES: add_entry() scarta la più vecchia e
load() ignora quelle in più (un file scritto a mano troppo lungo non pesa).

Ad ogni aggiornamento:
    python -m game.news 3.0.2 "Titolo" "prima novità" "seconda novità" ...

"Già lette": la versione più recente vista si salva in
%APPDATA%/PokeMoba/news_seen.txt; finché non si apre il pannello il pulsante
del menu ha un pallino d'oro.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "data" / "news.json"
MAX_ENTRIES = 10


def _clean(raw) -> list:
    out = []
    for e in raw if isinstance(raw, list) else []:
        if not isinstance(e, dict) or not e.get("version"):
            continue
        items = [str(i) for i in e.get("items", []) if str(i).strip()]
        out.append({"version": str(e["version"]), "date": str(e.get("date", "")),
                    "title": str(e.get("title", "")), "items": items})
    return out[:MAX_ENTRIES]


def load(path: Path = NEWS_FILE) -> list:
    try:
        return _clean(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def add_entry(version: str, title: str, items: list, date: str | None = None,
              path: Path = NEWS_FILE) -> list:
    """Mette la voce in cima (sostituisce quella della stessa versione) e tiene
    solo le ultime MAX_ENTRIES. Ritorna la lista scritta."""
    entry = {"version": version, "date": date or time.strftime("%Y-%m-%d"),
             "title": title, "items": list(items)}
    rest = [e for e in load(path) if e["version"] != version]
    news = _clean([entry] + rest)
    Path(path).write_text(json.dumps(news, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return news


# --- già lette --------------------------------------------------------------------
def _seen_file() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "PokeMoba" / "news_seen.txt"


def latest_version(news: list) -> str:
    return news[0]["version"] if news else ""


def is_unread(news: list) -> bool:
    v = latest_version(news)
    if not v:
        return False
    try:
        return _seen_file().read_text(encoding="utf-8").strip() != v
    except OSError:
        return True


def mark_read(news: list) -> None:
    v = latest_version(news)
    if not v:
        return
    try:
        f = _seen_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(v, encoding="utf-8")
    except OSError:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print('uso: python -m game.news VERSIONE "Titolo" "novita 1" ["novita 2" ...]')
        sys.exit(1)
    out = add_entry(sys.argv[1], sys.argv[2], sys.argv[3:])
    print(f"{len(out)} voci in {NEWS_FILE} (max {MAX_ENTRIES})")
