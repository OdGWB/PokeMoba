import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.stats import (CUMULATIVE_XP, MAX_LEVEL, STAB_MULT, Stats, damage,
                          level_from_xp, respawn_time, stats_at_level)


class TestStats(unittest.TestCase):
    def test_stats_at_level(self):
        base = Stats(hp=500, attack=50, defense=40, sp_attack=60, sp_defense=40, speed=50)
        growth = Stats(hp=60, attack=5, defense=4, sp_attack=6, sp_defense=4, speed=0)
        lv1 = stats_at_level(base, growth, 1)
        self.assertEqual(lv1.hp, 500)
        self.assertEqual(lv1.attack, 50)
        lv5 = stats_at_level(base, growth, 5)
        self.assertEqual(lv5.hp, 500 + 60 * 4)
        self.assertEqual(lv5.attack, 50 + 5 * 4)

    def test_level_capped(self):
        high = stats_at_level(Stats(), Stats(hp=10), 999)
        same = stats_at_level(Stats(), Stats(hp=10), MAX_LEVEL)
        self.assertEqual(high.hp, same.hp)

    def test_level_from_xp(self):
        self.assertEqual(level_from_xp(0), 1)
        self.assertEqual(level_from_xp(CUMULATIVE_XP[2] - 1), 1)
        self.assertEqual(level_from_xp(CUMULATIVE_XP[2]), 2)
        self.assertEqual(level_from_xp(CUMULATIVE_XP[MAX_LEVEL]), MAX_LEVEL)
        self.assertEqual(level_from_xp(10 ** 9), MAX_LEVEL)

    def test_respawn_grows(self):
        self.assertLess(respawn_time(1), respawn_time(15))

    def test_damage_defense_reduces(self):
        d0 = damage(100, 0)
        d100 = damage(100, 100)
        self.assertAlmostEqual(d0, 100)
        self.assertAlmostEqual(d100, 50)  # 100 * 100/200

    def test_damage_effectiveness_and_stab(self):
        base = damage(100, 0)
        self.assertAlmostEqual(damage(100, 0, effectiveness=2.0), base * 2)
        self.assertAlmostEqual(damage(100, 0, stab=STAB_MULT), base * 1.5)

    def test_damage_minimum_one(self):
        self.assertEqual(damage(0, 9999), 1.0)


if __name__ == "__main__":
    unittest.main()
