"""Punti mossa: il punto del liv.8 va alla ultimate (nessun punto in più) e il
grado in più si offre solo quando il livello lo consente."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_pokemon_def
from engine.grid import TILE_FLOOR, Grid
from engine.vec import Vec2
from engine.world import World


def pokemon(name):
    d = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", name + ".json"))
    world = World(Grid(8, 8, [[TILE_FLOOR] * 8 for _ in range(8)]))
    return world.spawn_pokemon(pos=Vec2(2, 2), team=0, dex=d.dex, name=d.name,
                               types=d.types, base_stats=d.base_stats, growth=d.growth,
                               color=d.color, speed=d.base_speed,
                               moves=d.moves, evolutions=d.evolutions, passive=d.passive)


def spend_all(p):
    while any(skills.rank_up(p, s) for s in "RQWE"):
        pass


class TestUltimatePoint(unittest.TestCase):
    def test_level_8_point_is_reserved_for_ultimate(self):
        p = pokemon("charmander")
        p.level = 7
        spend_all(p)
        p.level = 8
        self.assertEqual(skills.available_points(p), 0)
        self.assertFalse(any(skills.can_rank_up(p, s) for s in "QWER"))

    def test_choosing_ultimate_spends_that_point(self):
        p = pokemon("charmander")
        p.level = 8                       # 8 punti mai spesi: 7 liberi + quello della R
        self.assertEqual(skills.available_points(p), 7)
        p.pending_choices.append("R")
        self.assertTrue(evolution.apply_choice(p, "R", 0))
        self.assertEqual(p.moveset["R"].rank, 1)
        self.assertEqual(p.skill_points_spent, 1)
        self.assertEqual(skills.available_points(p), 7)

    def test_one_rank_per_level_up_to_15(self):
        p = pokemon("charmander")
        for level in range(1, 16):
            p.level = level
            if level == 8:
                p.pending_choices.append("R")
                evolution.apply_choice(p, "R", 0)
            spend_all(p)
            self.assertEqual(sum(m.rank for m in p.moveset.values()), level, level)

    def test_form_without_r_slot_also_reserves(self):
        p = pokemon("charcadet")          # la R arriva solo con la forma del liv.8
        p.level = 8
        self.assertEqual(skills.available_points(p), 7)


class TestRankAllowed(unittest.TestCase):
    def test_basic_cap_is_half_level(self):
        self.assertTrue(skills.rank_allowed("Q", 0, 4, 1))
        self.assertFalse(skills.rank_allowed("Q", 1, 4, 2))
        self.assertTrue(skills.rank_allowed("Q", 1, 4, 3))
        self.assertFalse(skills.rank_allowed("Q", 4, 4, 15))

    def test_ultimate_only_at_8_11_14(self):
        self.assertFalse(skills.rank_allowed("R", 1, 3, 10))
        self.assertTrue(skills.rank_allowed("R", 1, 3, 11))
        self.assertFalse(skills.rank_allowed("R", 2, 3, 13))
        self.assertTrue(skills.rank_allowed("R", 2, 3, 14))
        self.assertFalse(skills.rank_allowed("R", 3, 3, 15))


if __name__ == "__main__":
    unittest.main()
