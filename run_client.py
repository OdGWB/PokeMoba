"""Avvio del client di gioco.

    python run_client.py            # menu: singolo / ospita / unisciti (LAN)
    python run_client.py --single   # vai diretto a una partita vs bot
    python run_client.py --single --map data/maps/map_test.json   # demo Fase 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def check_engine() -> None:
    """Nell'exe il motore Rust e' obbligatorio (engine/backend.py).
    `--check-engine`: esce con 0 se c'e', 1 se no, senza aprire il gioco (lo usano
    release.yml e crea_exe.bat sull'exe appena creato)."""
    only_check = sys.argv[1:] == ["--check-engine"]
    if not only_check and not getattr(sys, "frozen", False):
        return
    from engine.backend import native_problem
    problem = native_problem()
    if only_check:
        if sys.stdout is not None:      # l'exe senza console non ha stdout
            print(problem or "motore Rust attivo")
        sys.exit(1 if problem else 0)
    if problem:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, f"PokéMoba non può partire: {problem}.\n\n"
                  "Reinstalla il gioco con l'ultimo PokeMoba-Setup.exe.",
            "PokéMoba", 0x10)
        sys.exit(1)


def main() -> None:
    check_engine()
    if len(sys.argv) >= 3 and sys.argv[1] == "--terrain-worker":
        # Processo delle varianti della mappa col meteo (game/terrain_variants.py).
        from game import terrain_variants
        sys.exit(terrain_variants.worker_main(sys.argv[2]))
    parser = argparse.ArgumentParser(description="PokéMoba - client")
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
    parser.add_argument("--oro", choices=("minion", "neutrali"), default=None,
                        help="Sneasel: oro in vantaggio (test: forma al liv.8)")
    parser.add_argument("--colore", choices=("rosso", "giallo", "arancione", "blu", "bianco"),
                        default=None, help="Flabébé: colore dei fiori")
    args = parser.parse_args()
    colore = {"rosso": "red", "giallo": "yellow", "arancione": "orange", "blu": "blue",
              "bianco": "white"}.get(args.colore)
    if args.oro:   # stesso meccanismo di --armature: un contatore in vantaggio
        args.armature = "gold_wild" if args.oro == "neutrali" else "gold_minion"

    from game.app import App
    if args.single:
        app = App(initial="match", map_path=str(ROOT / args.map),
                  pokemon_path=str(ROOT / args.pokemon), start_level=args.level,
                  start_items=args.items, start_armature=args.armature,
                  flower_color=colore)
    else:
        app = App(initial="menu")
    app.run()


if __name__ == "__main__":
    main()
