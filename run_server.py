"""Server LAN dedicato (headless, senza pygame).

    python run_server.py [--port 50007]

Gli altri giocatori si uniscono con `python run_client.py` -> "Unisciti" e
l'IP di questa macchina. In alternativa un giocatore può ospitare direttamente
dal menu del client ("Ospita"): in quel caso questo server dedicato non serve.
"""
from __future__ import annotations

import argparse
import socket
import time

import config


def main() -> None:
    parser = argparse.ArgumentParser(description="PokéMoba - server LAN dedicato")
    parser.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    args = parser.parse_args()

    from net.lan.server import GameServer
    server = GameServer(port=args.port)
    server.start()
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        ip = "?"
    print(f"Server in ascolto su {ip}:{args.port}  (Ctrl+C per fermare)")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nArresto del server.")
        server.stop()


if __name__ == "__main__":
    main()
