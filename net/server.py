"""Server autoritativo UDP.

Gira la stessa simulazione pura (engine + sim) a 30 tick/s in un thread, accetta
i client in lobby, poi avvia la partita. Ogni 1/20 s invia a ciascun client uno
snapshot filtrato per la sua squadra. Gestisce pacchetti persi (UDP), input
fuori ordine (numero di sequenza) e disconnessioni (timeout -> il Pokémon
diventa un bot, la partita continua).

Nessun pygame qui dentro.
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import config
from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.vec import Vec2
from engine.world import World
from sim.commands import (AttackCommand, AttackMoveCommand, BuyItemCommand,
                          ChooseUpgradeCommand, CastMoveCommand, MoveCommand,
                          RankMoveCommand, RecallCommand, SellItemCommand, StopCommand)
from sim.simulation import Simulation
from . import protocol as P

ROOT = Path(__file__).resolve().parent.parent
LANES = ["top", "mid", "bot"]
SLOT_OFFSET = {"top": Vec2(-1.2, 0.0), "mid": Vec2(0.0, 0.0), "bot": Vec2(0.0, 1.2)}
CLIENT_TIMEOUT = 8.0


class ClientConn:
    def __init__(self, addr, cid, name):
        self.addr = addr
        self.cid = cid
        self.name = name or f"Giocatore {cid}"
        self.team = 0
        self.pokemon = 0
        self.ready = False
        self.entity_id = 0
        self.last_seen = time.monotonic()
        self.last_seq = 0


class GameServer:
    def __init__(self, host="0.0.0.0", port=config.DEFAULT_PORT, map_path=None):
        self.selected_map = map_path or config.DEFAULT_MAP   # percorso relativo
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        self.sock.setblocking(False)
        self.clients: dict = {}          # addr -> ClientConn
        self._next_cid = 0
        self.state = "lobby"
        self.world = None
        self.match = None
        self.sim = None
        self.snap_seq = 0
        self.running = False
        self._thread = None
        self._defs = {}                  # cache PokemonDef per indice roster

    # --- ciclo di vita -------------------------------------------------------
    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass

    def _loop(self):
        last = time.monotonic()
        acc = 0.0
        snap_acc = 0.0
        snap_dt = 1.0 / config.SNAPSHOT_RATE
        while self.running:
            self._pump_packets()
            now = time.monotonic()
            dt = now - last
            last = now
            self._prune(now)

            if self.state == "match" and self.sim is not None:
                acc += dt
                # Limita per non entrare in spirale dopo un rallentamento.
                acc = min(acc, 0.25)
                while acc >= config.TICK_DT:
                    self.sim.step()
                    acc -= config.TICK_DT
                snap_acc += dt
                if snap_acc >= snap_dt:
                    snap_acc = 0.0
                    self._send_snapshots()

            time.sleep(0.002)

    # --- rete ----------------------------------------------------------------
    def _pump_packets(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(4096)
            except (BlockingIOError, OSError):
                break
            try:
                self._handle(data, addr)
            except Exception:
                pass  # pacchetto malformato: ignora, non far crashare il server

    def _send(self, addr, data):
        try:
            self.sock.sendto(data, addr)
        except OSError:
            pass

    def _broadcast(self, data):
        for c in self.clients.values():
            self._send(c.addr, data)

    def _handle(self, data, addr):
        t = P.msg_type(data)
        c = self.clients.get(addr)
        if c:
            c.last_seen = time.monotonic()

        if t == P.C_HELLO:
            if c is None and self.state == "lobby" and len(self.clients) < 6:
                rr = P.Reader(data); rr.u8()
                c = ClientConn(addr, self._next_cid, rr.s())
                self._next_cid += 1
                # Bilancia le squadre.
                t0 = sum(1 for x in self.clients.values() if x.team == 0)
                t1 = sum(1 for x in self.clients.values() if x.team == 1)
                c.team = 0 if t0 <= t1 else 1
                self.clients[addr] = c
                self._send(addr, P.enc_welcome(c.cid))
                self._broadcast_lobby()
        elif t == P.C_LOBBY and c is not None and self.state == "lobby":
            rr = P.Reader(data); rr.u8()
            c.team = rr.u8() % 2
            c.pokemon = rr.u8() % len(config.ROSTER)
            c.ready = bool(rr.u8())
            if rr.remaining() >= 1:
                mi = rr.u8()
                if c.cid == 0 and 0 <= mi < len(config.MAPS):   # solo l'host sceglie la mappa
                    self.selected_map = config.MAPS[mi][1]
            self._broadcast_lobby()
            self._maybe_start()
        elif t == P.C_INPUT and c is not None and self.state == "match":
            self._handle_input(c, data)
        elif t == P.C_PING and c is not None:
            self._send(addr, P.enc_pong())
        elif t == P.C_BYE and c is not None:
            self._drop(c)

    def _broadcast_lobby(self):
        players = [{"client_id": c.cid, "team": c.team, "pokemon": c.pokemon,
                    "ready": c.ready, "name": c.name} for c in self.clients.values()]
        mi = next((i for i, (_n, p) in enumerate(config.MAPS) if p == self.selected_map), 0)
        self._broadcast(P.enc_lobby_state(players, mi))

    def _maybe_start(self):
        if self.state != "lobby" or not self.clients:
            return
        if all(c.ready for c in self.clients.values()):
            self._start_match()

    def _prune(self, now):
        gone = [c for c in self.clients.values() if now - c.last_seen > CLIENT_TIMEOUT]
        for c in gone:
            self._drop(c)

    def _drop(self, c):
        # Se la partita è in corso, il suo Pokémon diventa un bot.
        if self.state == "match" and self.world is not None:
            ent = self.world.get(c.entity_id)
            if ent is not None:
                ent.is_bot = True
        self.clients.pop(c.addr, None)
        if self.state == "lobby":
            self._broadcast_lobby()

    # --- partita -------------------------------------------------------------
    def _get_def(self, idx):
        if idx not in self._defs:
            self._defs[idx] = load_pokemon_def(str(ROOT / config.ROSTER[idx]))
        return self._defs[idx]

    def _start_match(self):
        map_data = load_map(str(ROOT / self.selected_map))
        self.world = World(map_data.grid)
        self.match = Match(self.world, map_data)
        team_size = map_data.team_size

        # Assegna i client agli slot della squadra (lane a rotazione); i restanti bot.
        by_team = {0: [], 1: []}
        for c in self.clients.values():
            by_team[c.team].append(c)
        players_info = []
        for team in (0, 1):
            clients = by_team[team]
            for slot in range(team_size):
                lane = LANES[slot % 3]
                if slot < len(clients):
                    c = clients[slot]
                    p = self._spawn(map_data, team, lane, self._get_def(c.pokemon), is_bot=False)
                    c.entity_id = p.id
                    players_info.append({"client_id": c.cid, "entity_id": p.id,
                                         "team": team, "pokemon": c.pokemon, "name": c.name})
                else:
                    self._spawn(map_data, team, lane, self._get_def(0), is_bot=True)

        self.match.assign_junglers()
        self.match.vision.update(self.world, 0)
        self.match.vision.update(self.world, 1)
        self.sim = Simulation(self.world, config.TICK_DT, match=self.match)
        self.state = "match"
        for c in self.clients.values():
            self._send(c.addr, P.enc_start(self.selected_map, c.entity_id, players_info))

    def _spawn(self, map_data, team, lane, pdef, is_bot):
        base = Vec2(*map_data.spawns[f"team{team}"]) + Vec2(0.5, 0.5)
        pos = base + SLOT_OFFSET[lane]
        p = self.world.spawn_pokemon(pos=pos, team=team, dex=pdef.dex, name=pdef.name,
                                     color=config.TEAM_COLORS[team], speed=pdef.base_speed,
                                     is_bot=is_bot, assigned_lane=lane, types=pdef.types,
                                     base_stats=pdef.base_stats, growth=pdef.growth,
                                     moves=pdef.moves, evolutions=pdef.evolutions,
                                     role=pdef.role, passive=pdef.passive,
                                     attack_range=pdef.attack_range,
                                     attack_cooldown=pdef.attack_cooldown,
                                     attack_fx=pdef.attack_fx)
        p.radius = pdef.radius
        return p

    def _handle_input(self, c, data):
        m = P.dec_input(data)
        if m["seq"] <= c.last_seq:        # scarta input vecchi/fuori ordine
            return
        c.last_seq = m["seq"]
        eid = c.entity_id
        k = m["kind"]
        cmd = None
        if k == P.CMD_MOVE:
            cmd = MoveCommand(seq=m["seq"], entity_id=eid, x=m["x"], y=m["y"])
        elif k == P.CMD_ATTACK:
            cmd = AttackCommand(seq=m["seq"], entity_id=eid, target_id=m["target_id"])
        elif k == P.CMD_ATTACKMOVE:
            cmd = AttackMoveCommand(seq=m["seq"], entity_id=eid, x=m["x"], y=m["y"])
        elif k == P.CMD_CAST:
            cmd = CastMoveCommand(seq=m["seq"], entity_id=eid, slot=P.SLOTS[m["slot"]],
                                  x=m["x"], y=m["y"])
        elif k == P.CMD_RANK:
            cmd = RankMoveCommand(seq=m["seq"], entity_id=eid, slot=P.SLOTS[m["slot"]])
        elif k == P.CMD_CHOOSE:
            cmd = ChooseUpgradeCommand(seq=m["seq"], entity_id=eid,
                                       slot=P.SLOTS[m["slot"]], index=m["index"])
        elif k == P.CMD_STOP:
            cmd = StopCommand(seq=m["seq"], entity_id=eid)
        elif k == P.CMD_BUY:
            cmd = BuyItemCommand(seq=m["seq"], entity_id=eid, item_id=m["item_id"])
        elif k == P.CMD_SELL:
            cmd = SellItemCommand(seq=m["seq"], entity_id=eid, slot=m["slot"])
        elif k == P.CMD_RECALL:
            cmd = RecallCommand(seq=m["seq"], entity_id=eid)
        if cmd is not None:
            self.sim.queue_command(cmd)

    def _send_snapshots(self):
        from .snapshot import build_snapshot
        self.snap_seq += 1
        for c in self.clients.values():
            self._send(c.addr, build_snapshot(self.match, c.team, c.entity_id, self.snap_seq))
        if self.match.winner is not None:
            self._broadcast(P.enc_end(self.match.winner))
