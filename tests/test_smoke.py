"""Test di FUMO: ogni linea del roster gioca una breve partita vera (ondate, bot,
torri, giungla) salendo di livello fino al 15, evolvendosi e lanciando tutte le
mosse appena pronte. Due varianti per linea (prima e seconda scelta di ogni
potenziamento/ramo). Ogni tanto lo stato passa dalla RETE: snapshot, stato visivo
ed eventi fx vengono codificati e decodificati come farebbe l'host online.

Non controlla i numeri: controlla che niente vada in crash e che i valori
restino sani (vita finita, posizioni dentro la mappa).
"""
import math
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.entities import Pokemon
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World
from net import protocol as P
from net.snapshot import capture_global, capture_hud, capture_me, capture_team, fx_visible
from net.visual import capture_visual

DT = 1 / 30
GAME_SECONDS = 16.0
NET_EVERY = 10                  # ticks tra due passaggi per la rete
LEVEL_PLAN = ((0.0, 3), (3.0, 6), (6.0, 9), (9.0, 15))   # (secondi, livello)
MAP = load_map(os.path.join(ROOT, config.DEFAULT_MAP))
DEFS = [load_pokemon_def(os.path.join(ROOT, rel)) for rel in config.ROSTER]


def _spawn(world, d, pos, team, bot):
    p = world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=d.color,
                            speed=d.base_speed, is_bot=bot, assigned_lane="mid",
                            types=d.types, base_stats=d.base_stats, growth=d.growth,
                            moves=d.moves, evolutions=d.evolutions, role=d.role,
                            passive=d.passive, attack_range=d.attack_range,
                            attack_cooldown=d.attack_cooldown, attack_fx=d.attack_fx,
                            rec_items=d.recommended_items)
    p.radius = d.radius
    p.spawn_pos = Vec2(pos.x, pos.y)
    return p


def _rank_all(p):
    for _ in range(20):
        for s in ("R", "Q", "W", "E"):
            if skills.can_rank_up(p, s):
                skills.rank_up(p, s)


def _branch_setup(match, p, variant):
    """Prepara il RAMO d'evoluzione della variante (le condizioni di
    engine/evolution._requires_met), così il test passa da tutte le forme."""
    if variant == 1:
        p.fausta, p.infausta = 1000.0, 0.0        # Charcadet -> Armarouge/Ceruledge
        p.gold_wild, p.gold_minion = 1000.0, 0.0  # Sneasel -> Sneasler
        p.items.append("king_rock")               # Poliwhirl -> Politoad
    # Scyther evolve SOLO con un oggetto: Metalcoperta o Augite Nera.
    p.items.append("metal_coat" if variant == 0 else "black_augurite")
    match._apply_items(p)


class _Game:
    def __init__(self, d, variant, seed):
        random.seed(seed)
        m = load_map(os.path.join(ROOT, config.DEFAULT_MAP))
        self.map = m
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        # Variante 0: partita completa coi minion (lenta, ~4 s); variante 1 senza
        # ondate (~0,6 s), per restare sotto i due minuti in tutto.
        self.match._wave_timer = 1.0 if variant == 0 else 1e9
        cx, cy = m.grid.width / 2, m.grid.height / 2
        mid = self.match.oriented_lane("mid", 0)
        c = min(mid, key=lambda v: (v.x - cx) ** 2 + (v.y - cy) ** 2)
        self.me = _spawn(self.world, d, Vec2(c.x - 1.5, c.y + 1.5), 0, bot=False)
        self.foe = _spawn(self.world, d, Vec2(c.x + 1.5, c.y - 1.5), 1, bot=True)
        self.foe2 = _spawn(self.world, DEFS[(DEFS.index(d) + 7) % len(DEFS)],
                           Vec2(c.x + 2.0, c.y - 0.5), 1, bot=True)
        self.variant = variant
        _branch_setup(self.match, self.me, variant)
        self.net_base = {0: None, 1: None}
        self.seq = {0: 0, 1: 0}

    def level_to(self, lv):
        p = self.me
        if p.level >= lv:
            return
        self.match._gain_xp(p, CUMULATIVE_XP[lv] - p.xp + 1.0)
        self.match._update_evolution(0)
        self.resolve_choices()

    def resolve_choices(self):
        p = self.me
        for slot in list(p.pending_choices):
            evolution.apply_choice(p, slot, self.variant)
        _rank_all(p)

    def act(self):
        """Il "giocatore": attacca e lancia ogni mossa pronta verso il nemico più vicino."""
        p, m = self.me, self.match
        if not p.alive:
            return
        enemies = [u for u in self.world.pokemons() if u.team != p.team and u.alive]
        if not enemies:
            return
        t = min(enemies, key=lambda u: (u.pos - p.pos).length())
        for slot in ("Q", "W", "E", "R"):
            ms = p.moveset.get(slot)
            if ms is not None and ms.chosen is not None and ms.ready and ms.rank > 0:
                m._cast(p, slot, t.pos.x, t.pos.y)
        if p.order == "idle":
            p.order = "attack"
            p.target_id = t.id

    def net_roundtrip(self):
        m = self.match
        glob = capture_global(m)
        for team in (0, 1):
            ents = capture_team(m, team)
            hero = self.me if team == 0 else self.foe
            hud = capture_hud(hero)
            me = capture_me(m, hero, 1, 1)
            base = self.net_base[team]
            self.seq[team] = P.seq_next(self.seq[team])
            data = P.enc_snapshot(self.seq[team], 1, ents, glob, hud, me, base)
            fr = P.dec_snapshot(data, {base.seq: base}.get if base else (lambda s: None))
            assert set(fr.ents) == set(ents), "entità perse nello snapshot"
            self.net_base[team] = P.Frame(self.seq[team], 1, ents, glob, hud, me)
            P.dec_vis(P.enc_vis(capture_visual(m, team, hero)))

    def fx_roundtrip(self):
        evs = self.match.fx_events
        if not evs:
            return
        for team in (0, 1):
            vis = [e for e in evs if fx_visible(self.match, team, e)]
            for pkt in P.enc_fx(1, vis):
                P.dec_fx(pkt)
        evs.clear()

    def check_sane(self):
        g = self.map.grid
        for u in self.world.pokemons():
            assert math.isfinite(u.hp) and math.isfinite(u.max_hp), f"{u.name}: vita non finita"
            assert math.isfinite(u.pos.x) and math.isfinite(u.pos.y), f"{u.name}: posizione NaN"
            assert -1 <= u.pos.x <= g.width + 1 and -1 <= u.pos.y <= g.height + 1, \
                f"{u.name}: fuori mappa {u.pos}"

    def run(self):
        plan = list(LEVEL_PLAN)
        n = int(GAME_SECONDS / DT)
        for i in range(n):
            t = i * DT
            while plan and t >= plan[0][0]:
                self.level_to(plan.pop(0)[1])
            if self.me.pending_choices:
                self.resolve_choices()
            self.act()
            self.match.update(DT, i)
            self.fx_roundtrip()
            if i % NET_EVERY == 0:
                self.net_roundtrip()
                self.check_sane()
        return self.me


class TestSmoke(unittest.TestCase):
    pass


def _make_test(k, d):
    def test(self):
        forms = set()
        for variant in (0, 1):
            with self.subTest(variant=variant):
                me = _Game(d, variant, seed=100 + k * 2 + variant).run()
                self.assertEqual(me.level, 15)
                forms.add(me.name)
                for s in ("Q", "W", "E", "R"):   # tutte le mosse con una variante
                    ms = me.moveset.get(s)
                    self.assertIsNotNone(ms, f"{me.name}: manca lo slot {s}")
                    self.assertIsNotNone(ms.chosen, f"{me.name}: {s} senza mossa")
        if d.name in BRANCHED:   # le due varianti finiscono in forme diverse
            self.assertEqual(len(forms), 2, f"{d.name}: stessi rami {forms}")
    return test


# Linee il cui ramo finale dipende dalla variante (vedi _branch_setup).
BRANCHED = {"Charcadet", "Sneasel", "Poliwag", "Scyther", "Eevee"}

for _k, _d in enumerate(DEFS):
    setattr(TestSmoke, f"test_{_d.name.lower().replace('é', 'e')}", _make_test(_k, _d))


if __name__ == "__main__":
    unittest.main()
