"""Meccaniche chiave delle linee senza un file di test dedicato: Muta di
Nincada, pilastri di Roggenrola, Roccia di Re di Poliwag e le 8 forme di Eevee.
(Il danno di ogni mossa è in test_moves_hit.py, le partite in test_smoke.py.)"""
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.grid import TILE_PILLAR
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World


def _def(name):
    return load_pokemon_def(os.path.join(ROOT, "data", "pokemon", f"{name}.json"))


FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))


class Base(unittest.TestCase):
    def setUp(self):
        random.seed(2)
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.grid = m.grid
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        self.match.time = 100.0

    def spawn(self, d, pos, team=0):
        p = self.world.spawn_pokemon(
            pos=pos, team=team, dex=d.dex, name=d.name, color=d.color, speed=d.base_speed,
            types=d.types, base_stats=d.base_stats, moves=d.moves, evolutions=d.evolutions,
            role=d.role, passive=d.passive, attack_range=d.attack_range,
            attack_cooldown=d.attack_cooldown, attack_fx=d.attack_fx)
        p.radius = d.radius
        p.spawn_pos = Vec2(pos.x, pos.y)
        return p

    def level(self, p, lv, variant=0):
        self.match._gain_xp(p, CUMULATIVE_XP[lv] - p.xp + 1.0)
        self.match._update_evolution(0)
        for _ in range(3):
            for slot in list(p.pending_choices):
                evolution.apply_choice(p, slot, variant if isinstance(variant, int)
                                       else variant.get(slot, 0))
            for _ in range(20):
                for s in ("R", "Q", "W", "E"):
                    if skills.can_rank_up(p, s):
                        skills.rank_up(p, s)
            self.match._update_evolution(0)   # Eevee evolve dopo le scelte


class TestNincada(Base):
    def test_muta_cheats_death_once_then_cooldown(self):
        p = self.spawn(_def("nincada"), Vec2(30.5, 45.5))
        foe = self.spawn(FOE, Vec2(31.5, 45.5), team=1)
        self.assertFalse(self.match._muta_ready(p))      # Nincada: Muta non ancora attiva
        self.level(p, 8)
        self.assertTrue(self.match._muta_ready(p))       # Ninjask
        self.match._deal_damage(foe, p, 1e9)
        self.assertTrue(p.alive)
        self.assertEqual(p.form, "shedinja")
        self.assertFalse(self.match._muta_ready(p))
        self.match._deal_damage(foe, p, 1e9)             # Shedinja da Muta: muore davvero
        self.assertFalse(p.alive)

    def test_nincada_dies_normally(self):
        p = self.spawn(_def("nincada"), Vec2(30.5, 45.5))
        foe = self.spawn(FOE, Vec2(31.5, 45.5), team=1)
        self.match._deal_damage(foe, p, 1e9)
        self.assertFalse(p.alive)


class TestRoggenrola(Base):
    def test_pillar_blocks_tile_then_crumbles(self):
        p = self.spawn(_def("roggenrola"), Vec2(30.5, 45.5))
        foe = self.spawn(FOE, Vec2(33.5, 45.5), team=1)
        pl = self.match._place_pillar(p, Vec2(33.5, 45.5))
        self.assertIsNotNone(pl)
        self.assertEqual(self.grid.tiles[45][33], TILE_PILLAR)
        self.assertFalse(self.grid.is_walkable(33, 45))
        self.assertNotEqual((int(foe.pos.x), int(foe.pos.y)), (33, 45))   # spinto fuori
        self.assertIsNone(self.match._place_pillar(p, Vec2(33.5, 45.5)))  # già occupato
        self.match.time = pl.until + 0.1
        self.match._update_pillars(0.0)
        self.assertNotEqual(self.grid.tiles[45][33], TILE_PILLAR)
        self.assertTrue(self.grid.is_walkable(33, 45))


class TestPoliwag(Base):
    def test_kings_rock_picks_politoad(self):
        for items, form in (([], "Poliwrath"), (["king_rock"], "Politoad")):
            p = self.spawn(_def("poliwag"), Vec2(30.5, 45.5))
            p.items.extend(items)
            self.level(p, 8)
            self.assertEqual(p.name, form)


class TestEevee(Base):
    def test_each_choice_combination_gives_its_own_form(self):
        d = _def("eevee")
        forms = set()
        for q in (0, 1):
            for w in (0, 1):
                for e in (0, 1):
                    p = self.spawn(d, Vec2(30.5, 45.5))
                    self.level(p, 8, {"Q": q, "W": w, "E": e, "R": 0})
                    self.assertNotEqual(p.name, "Eevee", f"Q{q} W{w} E{e}: non evolve")
                    forms.add(p.name)
        self.assertEqual(len(forms), 8, forms)


if __name__ == "__main__":
    unittest.main()
