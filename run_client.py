"""Avvio del client di gioco.

    python run_client.py            # menu: singolo / ospita / unisciti (LAN)
    python run_client.py --single   # vai diretto a una partita vs bot
    python run_client.py --single --map data/maps/map_test.json   # demo Fase 1
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="PokrLOL - client")
    parser.add_argument("--single", action="store_true",
                        help="avvia subito una partita in locale contro i bot")
    parser.add_argument("--map", default="data/maps/map_3v3.json")
    parser.add_argument("--pokemon", default="data/pokemon/charmander.json")
    parser.add_argument("--level", type=int, default=1,
                        help="livello di partenza del giocatore (test: es. 8 per Ninjask)")
    parser.add_argument("--item", action="append", default=[], dest="items",
                        help="oggetto di partenza (ripetibile; es. --item king_rock per Politoad)")
    parser.add_argument("--armature", choices=("fausta", "infausta"), default=None,
                        help="Charcadet: barra di Armature in vantaggio (test: forma al liv.8)")
    args = parser.parse_args()

    from game.app import App
    if args.single:
        app = App(initial="match", map_path=str(ROOT / args.map),
                  pokemon_path=str(ROOT / args.pokemon), start_level=args.level,
                  start_items=args.items, start_armature=args.armature)
    else:
        app = App(initial="menu")
    app.run()


if __name__ == "__main__":
    main()
