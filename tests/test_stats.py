import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.stats import (CRIT_MULT, CUMULATIVE_XP, GROWTH_SCALE, MAX_LEVEL,
                          STAB_MULT, Stats, ability_haste_factor, bst,
                          combine_tenacity, damage, derive, evolution_mult,
                          level_from_xp, mitigate, normalize, penetrate,
                          range_class, respawn_time)
from engine.types import TypeChart

S = GROWTH_SCALE  # 17/15


def flat(v):
    """Base con tutte le stat = v: BST = 6v (per v=100 -> BST=600, budget ×1,0)."""
    return Stats(hp=v, attack=v, defense=v, sp_attack=v, sp_defense=v, speed=v)


class TestNormalize(unittest.TestCase):
    def test_budget_1_identity(self):
        # BST = 600 -> budget ×1,0; base 100 -> n=100 -> n'=100 -> eff=100.
        eff = normalize(flat(100))
        for k in ("hp", "attack", "defense", "sp_attack", "sp_defense", "speed"):
            self.assertAlmostEqual(getattr(eff, k), 100.0, places=6)

    def test_cap_prevents_lowbst_inflation(self):
        # Shedinja-like: BST minuscolo non deve gonfiare oltre il tetto ×1,35.
        tiny = Stats(hp=1, attack=1, defense=1, sp_attack=1, sp_defense=1, speed=1)
        eff = normalize(tiny)
        # n = 1 × 1,35 = 1,35 -> pavimento 25 + 0,675 = 25,675 -> compresso.
        self.assertLess(eff.hp, 60.0)

    def test_bst_sum(self):
        self.assertEqual(bst(flat(50)), 300.0)


class TestDerive(unittest.TestCase):
    def test_level1_exact(self):
        d = derive(flat(100), 1)
        self.assertAlmostEqual(d.stats.hp, 650.0)          # 450 + 2×100
        self.assertAlmostEqual(d.stats.attack, 57.0)       # 32 + 0,25×100 (non ranged)
        self.assertAlmostEqual(d.stats.defense, 30.0)      # 15 + 0,15×100
        self.assertAlmostEqual(d.stats.sp_defense, 32.0)   # 22 + 0,1×100
        self.assertAlmostEqual(d.max_mana, 450.0)          # 250 + (100+100)
        self.assertAlmostEqual(d.ability_mult, 1.0)        # 0,6 + 0,004×100
        self.assertAlmostEqual(d.mana_regen5, 8.0)         # 5 + 0,03×100
        self.assertEqual(d.ap, 0.0)
        self.assertEqual(d.crit, 0.0)

    def test_growth_scaled_16levels(self):
        d1 = derive(flat(100), 1)
        d2 = derive(flat(100), 2)
        self.assertAlmostEqual(d2.stats.hp - d1.stats.hp, 110.0 * S)      # (70+40)×17/15
        self.assertAlmostEqual(d2.stats.attack - d1.stats.attack, 4.0 * S)
        self.assertAlmostEqual(d2.stats.defense - d1.stats.defense, 5.0 * S)
        self.assertAlmostEqual(d2.stats.sp_defense - d1.stats.sp_defense, 2.3 * S)

    def test_ranged_ad_penalty(self):
        base = flat(100)
        normal = derive(base, 1, ranged=False).stats.attack
        ranged = derive(base, 1, ranged=True).stats.attack
        self.assertAlmostEqual(ranged, normal * 0.95)

    def test_speed_and_caps(self):
        d = derive(flat(100), 1)
        self.assertAlmostEqual(d.move_speed_tiles, 345.0 / 95.0)  # (315+30)/95
        self.assertAlmostEqual(d.attack_speed, 0.70)              # 0,55 + 0,0015×100
        self.assertAlmostEqual(d.attack_cooldown, 1.0 / 0.70)
        # Tetti: MS<=365/95, AS<=2,5.
        fast = derive(Stats(hp=1, attack=1, defense=1, sp_attack=1,
                            sp_defense=1, speed=999), MAX_LEVEL)
        self.assertLessEqual(fast.move_speed_tiles, 365.0 / 95.0 + 1e-6)
        self.assertLessEqual(fast.attack_speed, 2.5 + 1e-6)

    def test_identity_stats(self):
        d = derive(flat(100), 1)
        self.assertAlmostEqual(d.tenacity, 0.05)      # (100-90)×0,005
        self.assertAlmostEqual(d.hp_regen5, 8.0)      # 4 + 0,04×100 + 0
        self.assertEqual(d.flat_reduction, 0.0)
        self.assertEqual(d.lethality, 0.0)
        self.assertAlmostEqual(d.heal_power, 1.1)     # 1 + (100-80)×0,005

    def test_tenacity_and_heal_caps(self):
        tank = flat(200)
        d = derive(tank, 1)
        self.assertLessEqual(d.tenacity, 0.25)
        self.assertLessEqual(d.heal_power, 1.35)

    def test_flat_reduction_squishy(self):
        # HP bassissimo, difese alte -> d molto negativo -> riduzione fissa > 0.
        d = derive(Stats(hp=1, attack=1, defense=250, sp_attack=1,
                         sp_defense=250, speed=1), 1)
        self.assertGreater(d.flat_reduction, 0.0)
        self.assertLessEqual(d.flat_reduction, 8.0)

    def test_lethality_bruiser(self):
        d = derive(Stats(hp=1, attack=250, defense=1, sp_attack=1,
                         sp_defense=1, speed=1), 1)
        self.assertGreater(d.lethality, 0.0)
        self.assertLessEqual(d.lethality, 5.0)
        self.assertTrue(d.lethality_physical)

    def test_range_class(self):
        self.assertEqual(range_class(Stats(attack=100, sp_attack=10)), "melee")
        self.assertEqual(range_class(Stats(attack=10, sp_attack=100)), "ranged")
        self.assertEqual(range_class(flat(100)), "mid")

    def test_level_capped(self):
        self.assertEqual(derive(flat(100), 999).stats.hp,
                         derive(flat(100), MAX_LEVEL).stats.hp)


class TestXpLevels(unittest.TestCase):
    def test_curve_16(self):
        self.assertEqual(MAX_LEVEL, 16)
        self.assertAlmostEqual(CUMULATIVE_XP[2], 330.0)     # 200 + 130×1
        self.assertAlmostEqual(CUMULATIVE_XP[MAX_LEVEL], 18600.0)

    def test_level_from_xp(self):
        self.assertEqual(level_from_xp(0), 1)
        self.assertEqual(level_from_xp(CUMULATIVE_XP[2] - 1), 1)
        self.assertEqual(level_from_xp(CUMULATIVE_XP[2]), 2)
        self.assertEqual(level_from_xp(CUMULATIVE_XP[MAX_LEVEL]), MAX_LEVEL)
        self.assertEqual(level_from_xp(10 ** 9), MAX_LEVEL)

    def test_respawn_grows(self):
        self.assertLess(respawn_time(1), respawn_time(MAX_LEVEL))


class TestDamage(unittest.TestCase):
    def test_defense_reduces(self):
        self.assertAlmostEqual(damage(100, 0), 100)
        self.assertAlmostEqual(damage(100, 100), 50)

    def test_effectiveness_and_stab(self):
        base = damage(100, 0)
        self.assertAlmostEqual(damage(100, 0, effectiveness=2.0), base * 2)
        self.assertAlmostEqual(STAB_MULT, 1.15)
        self.assertAlmostEqual(damage(100, 0, stab=STAB_MULT), base * 1.15)

    def test_minimum_one(self):
        self.assertEqual(damage(0, 9999), 1.0)


class TestCombat(unittest.TestCase):
    def test_mitigate_positive_negative(self):
        self.assertAlmostEqual(mitigate(100, 0), 100)
        self.assertAlmostEqual(mitigate(100, 100), 50)
        self.assertAlmostEqual(mitigate(100, -100), 100 * (2 - 100 / 200))  # 150
        self.assertLessEqual(mitigate(100, -1e9), 200)  # tetto ×2

    def test_penetration_never_below_zero(self):
        self.assertAlmostEqual(penetrate(100, 0.3, 10), 100 * 0.7 - 10)  # 60
        self.assertEqual(penetrate(5, 0.0, 50), 0.0)                      # non sotto 0
        self.assertEqual(penetrate(-20, 0.5, 10), -20)                    # difesa <0 intatta

    def test_evolution_mult(self):
        self.assertEqual(evolution_mult(0, 3), 0.82)
        self.assertEqual(evolution_mult(2, 3), 1.03)
        self.assertEqual(evolution_mult(0, 2), 0.87)
        self.assertEqual(evolution_mult(0, 1), 1.0)

    def test_tenacity_multiplies(self):
        self.assertAlmostEqual(combine_tenacity(0.2, 0.2), 1 - 0.8 * 0.8)  # 0.36
        self.assertAlmostEqual(combine_tenacity(0.0), 0.0)

    def test_ability_haste(self):
        self.assertAlmostEqual(ability_haste_factor(0), 1.0)
        self.assertAlmostEqual(ability_haste_factor(100), 0.5)   # -50% ricarica

    def test_crit_const(self):
        self.assertAlmostEqual(CRIT_MULT, 1.75)

    def test_type_moba_clamp(self):
        tc = TypeChart.load(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "data", "types.json"))
        # Superefficace su un tipo -> ×1,25; su due -> ×1,5 (tetto).
        m1 = tc.moba_multiplier("Fire", ["Grass"])
        self.assertAlmostEqual(m1, 1.25)
        self.assertLessEqual(tc.moba_multiplier("Fire", ["Grass", "Ice"]), 1.5)
        self.assertGreaterEqual(tc.moba_multiplier("Normal", ["Rock", "Steel"]), 0.6)


if __name__ == "__main__":
    unittest.main()
