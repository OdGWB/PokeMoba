"""Punizione (engine/smite.py): solo il jungler della squadra puo' usarla."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.vec import Vec2
from engine.world import World

SNEASEL = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "sneasel.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))


def spawn(world, d, pos, team, bot):
    return world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=d.color,
                               speed=d.base_speed, is_bot=bot, types=d.types,
                               base_stats=d.base_stats, moves=d.moves,
                               evolutions=d.evolutions, role=d.role, passive=d.passive,
                               attack_range=d.attack_range,
                               attack_cooldown=d.attack_cooldown, attack_fx=d.attack_fx)


class TestSmite(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match.time = 100.0

    def wild_near(self, p):
        return self.world.spawn_wild(Vec2(p.pos.x + 1.0, p.pos.y), "camp", 5000.0, 0.0,
                                     1.0, 1.0, 0.0, 0)

    def test_human_jungle_line_is_jungler(self):
        h = spawn(self.world, SNEASEL, Vec2(20.5, 47.5), 0, False)
        b = [spawn(self.world, FOE, Vec2(22.5, 47.5), 0, True) for _ in range(2)]
        self.match.assign_junglers()
        self.assertTrue(h.is_jungler)
        self.assertFalse(any(x.is_jungler for x in b))

    def test_human_other_line_bot_jungles(self):
        h = spawn(self.world, FOE, Vec2(20.5, 47.5), 0, False)
        b = [spawn(self.world, FOE, Vec2(22.5, 47.5), 0, True) for _ in range(2)]
        self.match.assign_junglers()
        self.assertFalse(h.is_jungler)
        self.assertEqual(sum(x.is_jungler for x in b), 1)

    def test_only_jungler_can_smite(self):
        h = spawn(self.world, FOE, Vec2(20.5, 47.5), 0, False)
        w = self.wild_near(h)
        self.assertFalse(self.match.use_smite(h, w))
        self.assertEqual(h.smite_charges, 2)
        self.assertEqual(w.hp, 5000.0)
        h.is_jungler = True
        self.assertTrue(self.match.use_smite(h, w))
        self.assertEqual(h.smite_charges, 1)
        self.assertLess(w.hp, 5000.0)


if __name__ == "__main__":
    unittest.main()
