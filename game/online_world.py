"""Mondo lato client per la partita ONLINE (WebRTC).

Come NetWorld (stesse classi entità del motore, così renderer, minimappa e
animatori funzionano identici), ma:
- le ALTRE entità sono interpolate con un buffer di ~100 ms (net/interp.py);
- il PROPRIO Pokémon è predetto localmente e riconciliato con l'host
  (net/prediction.py), con il movimento vero del motore (MovementModel).
"""
from __future__ import annotations

import config
from engine import movement
from engine.entities import Core, Minion, Pokemon, Structure, Unit, Wild
from engine.pathfinding import find_path, smooth_path
from engine.vec import Vec2
from net import protocol as P
from net.interp import INTERP_DELAY, InterpBuffer
from sim.simulation import _nearest_walkable

from .networld import NetWorld

_WILD_COLORS = {"camp": (170, 160, 120), "meteo": (220, 180, 80), "arceus": (230, 220, 240)}


class MovementModel:
    """Il movimento del motore, usato dalla predizione.

    plan()    = A* + lisciatura, IDENTICO a Simulation._apply_move. Si chiama
                SOLO al momento del click, mai durante il replay.
    advance() = engine.movement.advance_unit su un'unità d'appoggio."""

    def __init__(self, grid):
        self.grid = grid
        self._u = Unit()

    def plan(self, pos, kind, target):
        if kind == P.CMD_STOP:
            return ()
        if kind not in (P.CMD_MOVE, P.CMD_ATTACKMOVE) or target is None:
            return None              # attacco/mossa/richiamo: lo decide l'host
        g = self.grid
        start = (int(pos[0]), int(pos[1]))
        goal = (int(target[0]), int(target[1]))
        if not g.is_walkable(*goal):
            goal = _nearest_walkable(g, goal)
            if goal is None:
                return ()
        tile_path = find_path(g, start, goal)
        if not tile_path:
            return ()
        return tuple(smooth_path(g, tile_path)[1:])

    def advance(self, pos, path, speed, dt):
        u = self._u
        u.pos = Vec2(pos[0], pos[1])
        u.path = [Vec2(x, y) for (x, y) in path]
        u.speed = speed
        movement.advance_unit(u, dt, self.grid)
        return (u.pos.x, u.pos.y), tuple((p.x, p.y) for p in u.path), u.facing


class OnlineWorld(NetWorld):
    def __init__(self, grid, your_id, predictor, session):
        super().__init__(grid)
        self.your_id = your_id
        self.pred = predictor
        self.session = session
        self.interp = InterpBuffer()
        self.disconnected: set = set()
        self._last_t = None

    # --- snapshot -> entità ------------------------------------------------------------
    def push_frame(self, frame, now):
        t = frame.tick * config.TICK_DT
        self.disconnected = set()
        for eid, e in frame.ents.items():
            obj = self._ensure_t(eid, e)
            obj.team = e[P.E_TEAM]
            obj.radius = e[P.E_RAD] / 100.0
            obj.hp = float(e[P.E_HP])
            obj.max_hp = max(1.0, float(e[P.E_MAXHP]))
            fl = e[P.E_FLAGS]
            obj.moving = bool(fl & P.EF_MOVING)
            obj.alive = bool(fl & P.EF_ALIVE)
            if fl & P.EF_DISCONNECTED:
                self.disconnected.add(eid)
            if isinstance(obj, Pokemon):
                obj.dex = e[P.E_EXTRA]
                obj.form = "shedinja" if e[P.E_EXTRA] == 292 else ""
            if not isinstance(obj, Wild):
                obj.color = config.TEAM_COLORS.get(obj.team, (200, 200, 200))
            x, y = P.dq_pos(e[P.E_X]), P.dq_pos(e[P.E_Y])
            if eid != self.your_id:
                obj.facing = P.angle_to_facing(e[P.E_ANG])
                self.interp.push(eid, t, x, y)
            if isinstance(obj, Core):
                self.core_hp[obj.team] = obj.hp
        for eid in [i for i in self.entities if i not in frame.ents]:
            del self.entities[eid]
        self.interp.forget(frame.ents)

        g = frame.glob
        self.winner = None if g[2] < 0 else g[2]
        self.match_time = t
        self.hud = self._hud_dict(frame)

        me = frame.me
        if me is not None:
            fl = me[3]
            own = frame.ents.get(self.your_id)
            self.pred.reconcile(
                (P.dq_pos(me[0]), P.dq_pos(me[1])), me[2] / 256.0,
                can_move=bool(fl & P.ME_CAN_MOVE) and bool(fl & P.ME_ALIVE),
                server_moving=bool(fl & P.ME_MOVING),
                ack_seq=me[4] if fl & P.ME_HAS_ACK else None, ack_tick=me[5],
                server_tick=frame.tick,
                server_facing=P.angle_to_facing(own[P.E_ANG]) if own else 0)

    def _ensure_t(self, eid, e):
        kind = e[P.E_KIND]
        want = {P.K_POKEMON: Pokemon, P.K_MINION: Minion, P.K_TOWER: Structure,
                P.K_CORE: Core, P.K_WILD: Wild}.get(kind, Minion)
        obj = self.entities.get(eid)
        if obj is not None and type(obj) is want:
            return obj
        pos = Vec2(P.dq_pos(e[P.E_X]), P.dq_pos(e[P.E_Y]))
        ex = e[P.E_EXTRA]
        if kind == P.K_POKEMON:
            obj = Pokemon(id=eid, pos=pos, dex=ex)
        elif kind == P.K_MINION:
            mt = P.MINION_TYPES[ex] if ex < len(P.MINION_TYPES) else "melee"
            obj = Minion(id=eid, pos=pos, minion_type=mt)
        elif kind == P.K_TOWER:
            obj = Structure(id=eid, pos=pos, kind="tower", tier=ex)
        elif kind == P.K_CORE:
            obj = Core(id=eid, pos=pos, kind="core")
        else:
            wk = P.WILD_KINDS[ex & 3] if (ex & 3) < len(P.WILD_KINDS) else "camp"
            ww = P.WILD_WEATHERS[(ex >> 2) & 3]
            obj = Wild(id=eid, pos=pos, kind=wk, weather=ww, team=2,
                       color=_WILD_COLORS.get(wk, (180, 180, 150)))
        self.entities[eid] = obj
        return obj

    @staticmethod
    def _hud_dict(frame):
        """Stesso formato del vecchio snapshot LAN: NetMatchScene lo legge così."""
        g, h = frame.glob, frame.hud
        out = {"seq": frame.seq, "time": frame.tick * config.TICK_DT, "winner": g[2],
               "core0": g[0], "core1": g[1], "weather": g[3], "arceus_open": g[4]}
        if h is None:
            h = (1, 0, 0, 0) + (-1, 0, 0) * 4 + (0, ())
        out.update({"level": h[0], "xp": h[1] / 100.0, "points": h[2], "pending": h[3],
                    "slots": {s: {"variant": h[4 + i * 3], "rank": h[5 + i * 3],
                                  "cd": h[6 + i * 3] / 100.0}
                              for i, s in enumerate(P.SLOTS_QWER)},
                    "gold": h[16], "items": list(h[17])})
        return out

    # --- posizioni da disegnare -----------------------------------------------------------
    def interpolate(self, local_time):
        dt = 0.0 if self._last_t is None else max(0.0, local_time - self._last_t)
        self._last_t = local_time
        render_t = self.session.clock.host_time(local_time) - INTERP_DELAY
        for eid, obj in self.entities.items():
            if eid == self.your_id:
                p = self.pred.display(dt)
                if p is not None:
                    obj.pos = Vec2(p[0], p[1])
                    obj.facing = self.pred.facing
                    if not self.pred.follow:
                        obj.moving = self.pred.moving
                continue
            s = self.interp.sample(eid, render_t)
            if s is not None:
                obj.pos = Vec2(s[0], s[1])

    # --- accessori: anche i neutrali (Wild) sono unità -------------------------------------
    def units(self):
        return [e for e in self.entities.values() if isinstance(e, Unit)]

    def alive_units(self):
        return [e for e in self.entities.values() if isinstance(e, Unit) and e.alive]

    def wilds(self):
        return [e for e in self.entities.values() if isinstance(e, Wild)]

    def combatants(self):
        return [e for e in self.entities.values()
                if isinstance(e, (Unit, Structure)) and getattr(e, "alive", True)]
