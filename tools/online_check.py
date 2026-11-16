"""Collaudo dell'ONLINE contro l'OFFLINE, mossa per mossa, per tutto il roster.

    python tools/online_check.py              # tutti i Pokémon, scelte 1 e 2
    python tools/online_check.py 8            # solo Spiritomb (indice in config.ROSTER)

Per ogni Pokémon e per ciascuna delle due scelte di potenziamento:
- ONLINE: host + client veri (tubo in memoria con 30 ms di latenza), il client
  sceglie il Pokémon nel draft, sale di grado e sceglie i potenziamenti coi
  pacchetti veri, poi lancia Q/W/E/R e l'auto-attacco contro un bersaglio
  fermo. La scena online del client (OnlineMatchScene) gira e si DISEGNA a ogni
  passo: un errore negli effetti grafici o nell'interfaccia esce qui.
- OFFLINE: la stessa scena sul motore puro (stessi livelli, gradi, scelte,
  posizioni), con i comandi messi direttamente nella simulazione come fa
  MatchScene.
Confronta: danno al bersaglio (hitbox), stati applicati al bersaglio e a chi
lancia (effetti secondari), effetti grafici arrivati al client e rispecchiati
sulle entità. L'orologio è virtuale: niente attese reali.
"""
from __future__ import annotations

import os
import random
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

# --- orologio virtuale (rete, host, client e scena lo leggono da time.monotonic) ----------
_clock = [1000.0]
time.monotonic = lambda: _clock[0]
FRAME = 1.0 / 60

import pygame  # noqa: E402

pygame.init()
SCREEN = pygame.display.set_mode((1280, 720))

import config  # noqa: E402
from engine import evolution, skills  # noqa: E402
from engine.stats import CUMULATIVE_XP  # noqa: E402
from engine.vec import Vec2  # noqa: E402
from net import protocol as P  # noqa: E402
from net.client import ClientSession  # noqa: E402
from net.host import HostSession  # noqa: E402
from net.transport import LoopbackTransport  # noqa: E402
from net.visual import LISTS, UNIT_FLAGS, timer_fields  # noqa: E402

SLOTS = ["Q", "W", "E", "R"]
CAST_TIME = 2.8          # s di partita osservati dopo ogni lancio (non un multiplo
                         # del ciclo d'attacco: un colpo sul bordo esatto della finestra
                         # entrerebbe offline e uscirebbe online per 30 ms di latenza)
DUMMY_DIST = 3.0         # tile tra chi lancia e il bersaglio
DUMMY_HP = 50000.0
LOWRES = None
_shared_renderer = [None]


# Il draft dell'host usa un random.Random() suo: qui con un seme, così i bot
# scelgono sempre gli stessi Pokémon (e il bersaglio è lo stesso a ogni collaudo).
import net.draft as _draft  # noqa: E402

_DRAFT_SEED = [0]
_draft_init = _draft.Draft.__init__


def _seeded_draft_init(self, *a, rng=None, **k):
    _draft_init(self, *a, rng=rng or random.Random(_DRAFT_SEED[0]), **k)


_draft.Draft.__init__ = _seeded_draft_init


class App:
    root = ROOT
    profile = {"name": "Collaudo", "avatar": 0}


# =====================================================================================
# Host pilotato a mano (stesso corpo del giro di HostSession._run, senza thread)
# =====================================================================================
def host_step(h):
    now = time.monotonic()
    h._process_cmds(now)
    h._poll_futures()
    for s in h.slots:
        if s.transport is None:
            continue
        for ch, data in s.transport.recv():
            try:
                h._on_message(s, ch, data, now)
            except (P.ProtocolError, ValueError, KeyError, IndexError):
                h._strike(s)
    h._check_links(now)
    h._advance(now)
    h._publish()


class Online:
    def __init__(self, idx, choice, errors):
        from game.scenes.online_match_scene import OnlineMatchScene
        self.errors = errors
        self.h = HostSession(map_index=0, host_name="Host", host_plays=False)
        self.h._running = True
        a, b = LoopbackTransport.pair(latency=0.03)
        self.h.attach_transport(1, a)
        self.c = ClientSession(b, "Amico")
        self.scene = None
        self.client_rng = random.Random(12345).getstate()
        self.fx_kinds = set()
        self.frame = 0
        self.pump(0.3)
        self.c.send_choice(0, 0, True)
        self.pump(0.2)
        self.h.request_start()
        while self.c.phase != "loading":
            if self.c.phase == "draft" and self.c.draft_my_turn():
                self.c.send_pick(idx, lock=True)
            self.pump(0.05)
        self.scene = OnlineMatchScene(App(), self.c)
        if _shared_renderer[0] is not None:            # la mappa grafica si costruisce una volta
            self.scene.renderer = _shared_renderer[0]
        orig = self.scene.fx.spawn_events

        def spawn(events):                              # la scena ingoia gli errori: qui no
            for e in events:
                self.fx_kinds.add(e.get("fx") or e.get("kind") or e.get("anim"))
            try:
                orig(events)
            except Exception:
                self.errors.append(("fx", traceback.format_exc(limit=3)))
        self.scene.fx.spawn_events = spawn
        self.pump(0.5)
        _shared_renderer[0] = self.scene.renderer
        self.eid = self.c.start_info["your_entity_id"]

    def pump(self, sec, draw_every=2):
        end = _clock[0] + sec
        while _clock[0] < end:
            _clock[0] += FRAME
            host_step(self.h)
            # Il client (effetti grafici, particelle) usa il suo generatore casuale:
            # così i numeri del MOTORE restano gli stessi della partita offline.
            engine_rng = random.getstate()
            random.setstate(self.client_rng)
            try:
                self._client_step(draw_every)
            finally:
                self.client_rng = random.getstate()
                random.setstate(engine_rng)

    def _client_step(self, draw_every):
        if True:
            self.c.poll()
            if self.scene is not None:
                try:
                    self.scene.update(FRAME)
                    self.frame += 1
                    if self.frame % draw_every == 0:
                        self.scene.draw(LOWRES)
                        self.scene.draw_fullres(SCREEN, pygame.font.SysFont("consolas", 14))
                except Exception:
                    self.errors.append(("scena", traceback.format_exc(limit=4)))
                    if len(self.errors) > 20:
                        raise RuntimeError("troppi errori nella scena")

    @property
    def match(self):
        return self.h.match

    def player(self):
        return self.h.world.get(self.eid)

    def level_and_build(self, choice):
        m, p = self.match, self.player()
        m._gain_xp(p, CUMULATIVE_XP[15] + 1.0)
        self.pump(0.3)
        for _ in range(30):                             # scelte e gradi coi PACCHETTI veri
            hud = self.c.latest.hud if self.c.latest else None
            for i, sl in enumerate(SLOTS):
                if sl in p.pending_choices:
                    ms = p.moveset.get(sl)
                    self.c.send_choose(i, min(choice, len(ms.upgrades) - 1))
            if hud is not None and hud[2] > 0:
                for i, sl in enumerate(SLOTS):
                    if skills.can_rank_up(p, sl):
                        self.c.send_rank(i)
                        break
            self.pump(0.1)
            if not p.pending_choices and skills.available_points(p) == 0:
                break

    def cast(self, slot_i, target):
        self.c.send_cast(slot_i, target.x, target.y)

    def attack(self, dummy_id):
        self.c.send_attack(dummy_id)


class Offline:
    """Stessa partita sul motore puro: i comandi vanno dritti nella simulazione."""

    def __init__(self, idx, entries):
        """entries: le posizioni del draft online (stesse squadre, stessi Pokémon)."""
        from engine.content import load_map
        from engine.match import Match
        from engine.world import World
        from sim.simulation import Simulation
        self.h = HostSession(map_index=0, host_plays=False)    # solo per _spawn/_get_def
        md = load_map(str(ROOT / config.MAPS[0][1]))
        self.h.world = World(md.grid)
        self.h.match = Match(self.h.world, md)
        from net.host import LANES
        self.eid = None
        for e in sorted(entries, key=lambda e: (e["team"], e["pos"])):     # come _start_match
            human = e["slot"] is not None
            q = self.h._spawn(md, e["team"], LANES[e["pos"] % 3], e["poke"], not human)
            if human:
                self.eid = q.id
        self.h.match.assign_junglers()
        self.sim = Simulation(self.h.world, config.TICK_DT, match=self.h.match)
        self.seq = 0

    @property
    def match(self):
        return self.h.match

    def player(self):
        return self.h.world.get(self.eid)

    def pump(self, sec, draw_every=0):
        for _ in range(int(round(sec / config.TICK_DT))):
            self.sim.step()
            self.match.fx_events.clear()

    def level_and_build(self, choice):
        m, p = self.match, self.player()
        m._gain_xp(p, CUMULATIVE_XP[15] + 1.0)
        self.pump(0.1)
        for _ in range(30):
            for sl in list(p.pending_choices):
                ms = p.moveset.get(sl)
                evolution.apply_choice(p, sl, min(choice, len(ms.upgrades) - 1))
            for sl in SLOTS:
                if skills.can_rank_up(p, sl):
                    skills.rank_up(p, sl)
            self.pump(0.1)
            if not p.pending_choices and skills.available_points(p) == 0:
                break

    def cast(self, slot_i, target):
        from sim.commands import CastMoveCommand
        self.seq += 1
        self.sim.queue_command(CastMoveCommand(seq=self.seq, entity_id=self.eid,
                                               slot=SLOTS[slot_i], x=target.x, y=target.y))

    def attack(self, dummy_id):
        from sim.commands import AttackCommand
        self.seq += 1
        self.sim.queue_command(AttackCommand(seq=self.seq, entity_id=self.eid, target_id=dummy_id))


# =====================================================================================
# Scenario comune: arena in mezzo alla mappa, bersaglio fermo, niente ondate
# =====================================================================================
def arena(grid):
    """Un punto calpestabile con DUMMY_DIST tile liberi a destra (mid, vicino al centro)."""
    cx, cy = grid.width // 2, grid.height // 2
    for r in range(0, 20):
        for dx in range(-r, r + 1):
            for dy in (-r, r):
                x, y = cx + dx, cy + dy
                if all(grid.is_walkable(x + k, y) for k in range(-1, int(DUMMY_DIST) + 3)) and \
                        all(grid.is_walkable(x + k, y + j) for k in range(0, 4) for j in (-1, 1)):
                    return Vec2(x + 0.5, y + 0.5)
    return Vec2(cx + 0.5, cy + 0.5)


def prepare(side):
    m, w = side.match, side.match.world
    m._wave_timer = 1e9
    for e in list(w.minions()):
        w.remove(e.id) if hasattr(w, "remove") else None
    p = side.player()
    pos = arena(w.grid)
    foes = [q for q in w.pokemons() if q.team != p.team]
    dummy = foes[0]
    # Danno contato dove il motore lo applica (i PS non bastano: c'è la rigenerazione).
    side.dmg_log = []
    orig = m._deal_damage

    def deal(attacker, target, amount, *a, **k):
        if target is dummy and amount > 0:
            side.dmg_log.append(amount)
        return orig(attacker, target, amount, *a, **k)
    m._deal_damage = deal
    random.seed(77)                                    # il bot sceglie le stesse evoluzioni
    m._gain_xp(dummy, CUMULATIVE_XP[15] + 1.0)        # bersaglio di pari livello
    # Bersaglio INERTE: non attacca e non ha passiva. Altrimenti risponde al fuoco
    # (stati e danni su chi lancia) e la sua passiva cambia i risultati.
    orig_aa = m._pokemon_auto_attack

    def auto_attack(u):
        if u is dummy:
            u.target_id = None
            return None
        # Chi lancia non attacca finché la mossa del giro non è partita: online il
        # comando arriva qualche tick dopo (latenza) e un attacco base "di attesa"
        # finirebbe nel conto solo da una parte.
        slot = getattr(side, "aa_block_slot", None)
        if slot is not None and u.id == side.eid:
            ms = u.moveset.get(slot)
            if ms is not None and ms.cooldown_remaining <= 0.0:
                return None
            side.aa_block_slot = None
        return orig_aa(u)
    m._pokemon_auto_attack = auto_attack
    for _ in range(6):                                 # stadi e scelte del bot, subito
        m._update_evolution(0)
    dummy.passive_id = ""
    for q in w.pokemons():
        q.is_bot = False
        q.order, q.path = "stop", []
        if q is not p and q is not dummy:
            q.pos = Vec2(q.spawn_pos.x, q.spawn_pos.y)
    p.pos = Vec2(pos.x, pos.y)
    dummy.pos = Vec2(pos.x + DUMMY_DIST, pos.y)
    p.path, dummy.path = [], []
    return dummy


def reset_round(side, dummy, pos):
    m, p, now = side.match, side.player(), side.match.time
    for u in (p, dummy):
        for name in timer_fields(type(u)):
            if getattr(u, name) > now and not name.startswith(("voltabsorb", "wander")):
                setattr(u, name, -1.0)
        u.alive = True
    dummy.max_hp = dummy.hp = DUMMY_HP                 # resiste a tutto: si misura il danno pieno
    p.hp = p.max_hp
    for u in (p, dummy):
        u.path = []
        u.air_z = 0.0
    p.pos = Vec2(pos.x, pos.y)
    dummy.pos = Vec2(pos.x + DUMMY_DIST, pos.y)
    for sl in SLOTS:
        ms = p.moveset.get(sl)
        if ms is not None:
            ms.cooldown_remaining = 0.0
            if ms.chosen is not None and ms.chosen.charges > 0:
                ms.charges_cur = float(ms.chosen.charges)
    # Ricariche delle passive (Spirito Vagante, Scalaroccia...): pronte a ogni giro.
    # Il giro prima, online, è finito qualche tick dopo (latenza), e una passiva che
    # torna pronta proprio in quel margine scatterebbe solo da una parte.
    for name in list(vars(p)):
        if name.endswith("_ready_at") and isinstance(getattr(p, name), (int, float)):
            setattr(p, name, 0.0)
    # Effetti rimasti dal giro prima (bufere, nubi, proiettili...): tutte le liste
    # del registro (net/visual.LISTS), più le speciali. Restano le condivise
    # (fiori, schegge...), che sono risorse di chi lancia.
    for lst in (*LISTS, "pain_binds", "wishes", "area_effects", "rain_zones", "rock_waves",
                "rock_charges", "smackdown_zones", "channels"):
        v = getattr(m, lst, None)
        if isinstance(v, list):
            v.clear()
    # Accumuli e marchi sul BERSAGLIO (Gelo, veleno, cariche...) tornano a zero.
    for name, off in UNIT_FLAGS.items():
        if name != "flower_color" and hasattr(dummy, name):
            setattr(dummy, name, off)
    # Spiriti di Spiritomb: compaiono a caso nel tempo, quindi online e offline ne
    # avrebbero di diversi. Si riparte da UNO solo, nello stesso punto (lo spot
    # libero più vicino), così Richiamo/Accompagnatore/Inseguimento si confrontano.
    if hasattr(m.world, "spirits"):
        m.world.spirits.clear()
        if hasattr(m, "_spirit_candidates") and p.passive_id == "108spiriti":
            from engine.entities import Spirit
            spots = m._spirit_candidates()
            if spots:
                c = min(spots, key=lambda v: (v.dist(pos), v.x, v.y))
                m.world.spirits.append(Spirit(pos=Vec2(c.x, c.y), owner_id=p.id, team=p.team,
                                              born=m.time, seed=7))


def statuses(u, now):
    return {n for n in timer_fields(type(u)) if getattr(u, n) > now + 0.05
            and not n.startswith(("voltabsorb", "wander", "muta_cd", "last_", "aa_"))}


def run_pair(idx, choice):
    errors = []
    random.seed(idx * 10 + choice)
    _DRAFT_SEED[0] = idx * 10 + choice                 # stesso avversario a ogni collaudo
    on = Online(idx, choice, errors)
    off = Offline(idx, on.h.draft.entries)
    rows = []
    for side in (on, off):
        side.level_and_build(choice)
    dums = {}
    for side in (on, off):
        dums[side] = prepare(side)
    pos = {s: s.player().pos for s in (on, off)}
    pos = {s: Vec2(v.x, v.y) for s, v in pos.items()}
    on.pump(0.6)                                       # il client vede il teletrasporto
    off.pump(0.6)                                      # (e anche il bersaglio offline evolve)
    p_on = on.player()
    assert dums[on].name == dums[off].name, (dums[on].name, dums[off].name)
    name = f"{p_on.name} contro {dums[on].name}"
    for k, sl in enumerate(SLOTS + ["AA"]):
        res = {}
        for side in (on, off):
            d = dums[side]
            side.aa_block_slot = None if sl == "AA" else sl
            reset_round(side, d, pos[side])
            side.pump(0.3)
            reset_round(side, d, pos[side])
            side.dmg_log.clear()
            if os.environ.get("CHECK_DEBUG"):
                pp = side.player()
                print(f"    [{type(side).__name__} {sl}] caster alive={pp.alive} hp={pp.hp:.0f} "
                      f"pos=({pp.pos.x:.1f},{pp.pos.y:.1f}) dummy alive={d.alive} hp={d.hp:.0f} "
                      f"pos=({d.pos.x:.1f},{d.pos.y:.1f}) dist={pp.pos.dist(d.pos):.2f} "
                      f"t={side.match.time:.1f} resp={d.respawn_timer:.1f}")
            if isinstance(side, Online):
                side.fx_kinds.clear()
                seen_vis = set()
                mirrored = set()
            random.seed(1000 + k)                      # stessi numeri casuali online e offline
            if sl == "AA":
                side.attack(d.id)
            else:
                side.cast(k, d.pos)
            caster_st, dummy_st = set(), set()
            t_end = side.match.time + CAST_TIME
            while side.match.time < t_end:
                side.pump(0.1)
                now = side.match.time
                caster_st |= statuses(side.player(), now)
                dummy_st |= statuses(d, now)
                if isinstance(side, Online):
                    seen_vis |= {kk for kk, vv in side.c.visual.items()
                                 if kk not in ("u", "me") and vv}
                    pe = side.scene.world.get(d.id)
                    if pe is not None:
                        mirrored |= statuses(pe, side.scene.world.match_time)
            res[side] = {"dmg": sum(side.dmg_log), "caster": caster_st, "dummy": dummy_st}
            if isinstance(side, Online):
                # Dove il client VEDE il proprio Pokémon (predizione) rispetto all'host.
                side.pump(0.4)
                me_c = side.scene.world.get(side.eid)
                gap = me_c.pos.dist(side.player().pos) if me_c is not None else -1.0
                res[side].update(fx=set(side.fx_kinds) - {None}, vis=seen_vis, mirror=mirrored,
                                 gap=gap)
        ms = p_on.moveset.get(sl) if sl != "AA" else None
        mvname = ms.chosen.name if ms and ms.chosen else ("auto-attacco" if sl == "AA" else "-")
        rows.append((sl, mvname, res[on], res[off]))
    return name, rows, errors, on


def verdict(r_on, r_off):
    probs = []
    a, b = r_on["dmg"], r_off["dmg"]
    if (a > 1) != (b > 1):
        probs.append(f"danno online {a:.0f} vs offline {b:.0f}")
    elif max(a, b) > 1 and abs(a - b) / max(a, b) > 0.40:
        probs.append(f"danno diverso: online {a:.0f} vs offline {b:.0f}")
    for key, lab in (("dummy", "stati bersaglio"), ("caster", "stati di chi lancia")):
        if r_on[key] != r_off[key]:
            probs.append(f"{lab}: online {sorted(r_on[key])} offline {sorted(r_off[key])}")
    miss = {s for s in r_on["dummy"] if s in ("frozen_until", "charm_until", "blind_until",
                                              "sleep_until", "poison_until", "root_until",
                                              "curse_until", "slow_until", "airborne_until",
                                              "endure_until", "puddle_until")} - r_on["mirror"]
    if miss:
        probs.append(f"stati non visti dal client: {sorted(miss)}")
    if r_on.get("gap", 0.0) > 0.5:
        probs.append(f"il client vede il proprio Pokémon a {r_on['gap']:.2f} tile da dove è davvero")
    return probs


def main():
    global LOWRES
    LOWRES = pygame.Surface((config.LOWRES_WIDTH, config.LOWRES_HEIGHT))
    only = [int(a) for a in sys.argv[1:]] or list(range(len(config.ROSTER)))
    total_probs = 0
    for idx in only:
        for choice in (0, 1):
            try:
                name, rows, errors, on = run_pair(idx, choice)
            except Exception:
                print(f"\n### {config.ROSTER[idx]} scelta {choice + 1}: CRASH")
                traceback.print_exc()
                total_probs += 1
                continue
            print(f"\n### {name} (roster {idx}), scelte n.{choice + 1}")
            for sl, mv, r_on, r_off in rows:
                probs = verdict(r_on, r_off)
                total_probs += len(probs)
                flag = "OK " if not probs else "!! "
                print(f"  {flag}{sl} {mv:<18} danno on/off {r_on['dmg']:6.0f}/{r_off['dmg']:6.0f}"
                      f"  stati bersaglio {sorted(s.replace('_until', '') for s in r_on['dummy'])}"
                      f"  fx {sorted(map(str, r_on['fx']))[:6]}  vis {sorted(r_on['vis'])}"
                      f"  scarto {r_on['gap']:.2f}")
                for pr in probs:
                    print(f"       -> {pr}")
            for kind, tb in errors[:5]:
                total_probs += 1
                print(f"  !! errore {kind}:\n{tb}")
            print(f"  rifiutati dall'host: {on.h.view[1]['rejected']}")
    print(f"\nPROBLEMI: {total_probs}")


if __name__ == "__main__":
    main()
