"""Client di rete UDP.

Manda input (con numero di sequenza) e riceve: welcome, stato lobby, start,
snapshot, fine. Non simula nulla: gli snapshot decodificati vengono passati al
NetWorld per il rendering interpolato.
"""
from __future__ import annotations

import socket
import time

import config
from . import protocol as P
from .snapshot import decode_snapshot


class GameClient:
    def __init__(self, server_ip, port=config.DEFAULT_PORT):
        self.server = (server_ip, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self._seq = 0
        self.client_id = None
        self.lobby = []          # ultimo stato lobby ricevuto
        self.lobby_map = 0       # indice mappa scelta (in config.MAPS)
        self.start_info = None   # dict da S_START quando la partita parte
        self.winner = None
        self.on_snapshot = None  # callback(snapshot_dict, local_time)
        self._last_ping = 0.0

    # --- invio ---------------------------------------------------------------
    def _send(self, data):
        try:
            self.sock.sendto(data, self.server)
        except OSError:
            pass

    def send_hello(self, name):
        self._send(P.enc_hello(name))

    def send_lobby(self, team, pokemon, ready, map_index=0):
        self._send(P.enc_lobby_choice(team, pokemon, ready, map_index))

    def send_bye(self):
        self._send(P.enc_bye())

    def _input(self, kind, **f):
        self._seq += 1
        self._send(P.enc_input(self._seq, kind, **f))

    def send_move(self, x, y): self._input(P.CMD_MOVE, x=x, y=y)
    def send_attack(self, target_id): self._input(P.CMD_ATTACK, target_id=target_id)
    def send_attackmove(self, x, y): self._input(P.CMD_ATTACKMOVE, x=x, y=y)
    def send_cast(self, slot, x, y): self._input(P.CMD_CAST, slot=slot, x=x, y=y)
    def send_rank(self, slot): self._input(P.CMD_RANK, slot=slot)
    def send_choose(self, slot, index): self._input(P.CMD_CHOOSE, slot=slot, index=index)
    def send_stop(self): self._input(P.CMD_STOP)
    def send_buy(self, item_id): self._input(P.CMD_BUY, item_id=item_id)
    def send_sell(self, slot): self._input(P.CMD_SELL, slot=slot)
    def send_recall(self): self._input(P.CMD_RECALL)

    # --- ricezione -----------------------------------------------------------
    def poll(self):
        now = time.monotonic()
        if now - self._last_ping > 1.0:
            self._last_ping = now
            self._send(P.enc_ping())
        while True:
            try:
                data, _addr = self.sock.recvfrom(8192)
            except (BlockingIOError, OSError):
                break
            try:
                self._handle(data, now)
            except Exception:
                pass  # pacchetto malformato: ignora

    def _handle(self, data, now):
        t = P.msg_type(data)
        if t == P.S_WELCOME:
            r = P.Reader(data); r.u8(); self.client_id = r.u8()
        elif t == P.S_LOBBY:
            d = P.dec_lobby_state(data)
            self.lobby = d["players"]
            self.lobby_map = d["map_index"]
        elif t == P.S_START:
            self.start_info = P.dec_start(data)
            self.winner = None
        elif t == P.S_SNAPSHOT:
            snap = decode_snapshot(data)
            if self.on_snapshot is not None:
                self.on_snapshot(snap, now)
        elif t == P.S_END:
            r = P.Reader(data); r.u8(); w = r.i8()
            self.winner = None if w < 0 else w

    def close(self):
        try:
            self.send_bye()
            self.sock.close()
        except OSError:
            pass
