"""Scarica le ICONE degli oggetti del negozio dal repository PokeAPI/sprites.

    python tools/fetch_items.py            # scarica solo le icone che mancano
    python tools/fetch_items.py --force    # riscarica tutto

Risultato:
  assets/items/<nome>.png   sprite dell'oggetto (es. choice-band.png)
  data/items.json           campo "icon" = <nome> per ogni oggetto del catalogo
  alla fine, l'elenco delle icone NON trovate (da recuperare a mano: il gioco
  usa il segnaposto con l'iniziale finché il file manca).

Fonte: https://github.com/PokeAPI/sprites, cartella sprites/items.
Le immagini sono gli sprite originali dei giochi Pokémon, (c) The Pokémon
Company (Nintendo / Game Freak / Creatures); il repository PokeAPI le raccoglie
sotto CC0 1.0 (la licenza copre la raccolta, non i diritti sulle immagini).
Crediti in CREDITS.md e nella schermata Crediti del menu.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items"
OUT = ROOT / "assets" / "items"
ITEMS_JSON = ROOT / "data" / "items.json"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# id dell'oggetto in items.json -> nome del file su PokeAPI (senza .png).
# Gli ultimi (consumabili e visione) non sono ancora nel catalogo: le icone si
# scaricano lo stesso, così sono pronte quando arriveranno.
ICONS = {
    "hp_up": "hp-up", "protein": "protein", "iron": "iron", "calcium": "calcium",
    "zinc": "zinc", "carbos": "carbos", "running_shoes": "running-shoes",
    "bicycle": "bicycle", "muscle_band": "muscle-band", "wise_glasses": "wise-glasses",
    "scope_lens": "scope-lens", "shell_bell": "shell-bell", "hard_stone": "hard-stone",
    "eviolite": "eviolite", "choice_band": "choice-band", "quick_claw": "quick-claw",
    "choice_scarf": "choice-scarf", "zoom_lens": "zoom-lens", "choice_specs": "choice-specs",
    "metronome": "metronome", "wide_lens": "wide-lens", "big_root": "big-root",
    "life_orb": "life-orb", "expert_belt": "expert-belt", "weakness_policy": "weakness-policy",
    "black_sludge": "black-sludge", "assault_vest": "assault-vest",
    "rocky_helmet": "rocky-helmet", "leftovers": "leftovers", "red_card": "red-card",
    "iron_ball": "iron-ball", "bright_powder": "bright-powder", "king_rock": "kings-rock",
    "light_clay": "light-clay", "soothe_bell": "soothe-bell", "exp_share": "exp-share",
    "focus_sash": "focus-sash", "mental_herb": "mental-herb", "smoke_ball": "smoke-ball",
    "eject_button": "eject-button",
    # rework oggetti (36 completi, 13 intermedi)
    "silk_scarf": "silk-scarf", "twisted_spoon": "twisted-spoon", "sharp_beak": "sharp-beak",
    "black_belt": "black-belt", "miracle_seed": "miracle-seed", "thick_club": "thick-club",
    "dragon_fang": "dragon-fang", "poison_barb": "poison-barb", "magnet": "magnet",
    "charcoal": "charcoal", "spell_tag": "spell-tag", "focus_band": "focus-band",
    "rusted_sword": "rusted-sword", "never_melt_ice": "never-melt-ice",
    "mystic_water": "mystic-water", "poke_flute": "poke-flute",
    # consumabili / visione (non ancora in items.json)
    "potion": "potion", "full_heal": "full-heal", "escape_rope": "escape-rope",
    "poke_ball": "poke-ball", "silph_scope": "silph-scope",
}


def download(name: str) -> bytes | None:
    """PNG dell'oggetto, o None se non esiste (404) o non è un PNG valido."""
    try:
        with urllib.request.urlopen(f"{RAW}/{name}.png", timeout=20) as r:
            data = r.read(512 * 1024)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return data if data.startswith(PNG_MAGIC) else None


def set_icons_in_json() -> list:
    """Scrive "icon" in items.json per ogni oggetto del catalogo. Modifica il
    testo riga per riga (niente riformattazione del file). Ritorna gli id del
    catalogo senza una corrispondenza in ICONS."""
    text = ITEMS_JSON.read_text(encoding="utf-8")
    data = json.loads(text)
    ids = [d["id"] for k in ("base", "intermediate", "completed") for d in data.get(k, [])]
    for iid in ids:
        name = ICONS.get(iid)
        if name is None:
            continue
        head = re.compile(r'("id":\s*"' + re.escape(iid) + r'",\s*"name":\s*"[^"]*",\s*)')
        m = head.search(text)
        if m is None:
            raise SystemExit(f"items.json: oggetto {iid} non riconosciuto")
        rest = text[m.end():]
        cur = re.match(r'"icon":\s*"[^"]*"', rest)
        if cur:
            rest = f'"icon": "{name}"' + rest[cur.end():]
        else:
            rest = f'"icon": "{name}", ' + rest
        text = text[:m.end()] + rest
    json.loads(text)   # deve restare JSON valido
    ITEMS_JSON.write_text(text, encoding="utf-8")
    return [i for i in ids if i not in ICONS]


def main() -> None:
    force = "--force" in sys.argv[1:]
    OUT.mkdir(parents=True, exist_ok=True)
    missing, saved, kept = [], 0, 0
    for iid, name in ICONS.items():
        dest = OUT / f"{name}.png"
        if dest.exists() and not force:
            kept += 1
            continue
        try:
            png = download(name)
        except Exception as e:   # rete/server: lo si segnala tra i mancanti
            print(f"  {name}: errore ({e})")
            png = None
        if png is None:
            missing.append((iid, name))
            continue
        dest.write_bytes(png)
        saved += 1
        print(f"  {name}.png")
    no_map = set_icons_in_json()
    print(f"\n{saved} icone scaricate, {kept} gia' presenti, in {OUT}")
    print("Campo \"icon\" aggiornato in data/items.json.")
    if no_map:
        print("Oggetti del catalogo senza nome di file in ICONS: " + ", ".join(no_map))
    if missing:
        print(f"\nIcone NON trovate ({len(missing)}) - da recuperare a mano in assets/items/:")
        for iid, name in missing:
            print(f"  {iid:<16} {name}.png   ({RAW}/{name}.png)")
    else:
        print("\nTutte le icone sono state trovate.")


if __name__ == "__main__":
    main()
