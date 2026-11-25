"""Oggetti dell'aggiornamento 3.1 (data/items.json, engine/item_effects.py)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution
from engine.content import load_map, load_pokemon_def
from engine.entities import Wild
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

TOTO = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "totodile.json"))
DELI = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "delibird.json"))


class TestItems31(unittest.TestCase):
    def setUp(self):
        md = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        self.world = World(md.grid)
        self.match = Match(self.world, md)
        self.match._wave_timer = 1e9
        self.match.time = 100.0
        sp = md.spawns["team0"]
        self.base = Vec2(sp[0] + 0.5, sp[1] + 0.5)
        self.a = self.mk(TOTO, 0, self.base)
        self.b = self.mk(TOTO, 1, self.base + Vec2(1.0, 0.0))
        for p in (self.a, self.b):
            p.crit = 0.0

    def mk(self, d, team, pos):
        p = self.world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=(0, 0, 0),
                                     speed=3.5, types=d.types, base_stats=d.base_stats,
                                     moves=d.moves, evolutions=d.evolutions,
                                     attack_range=d.attack_range, passive=d.passive)
        p.spawn_pos = Vec2(self.base.x, self.base.y)
        return p

    def give(self, p, *ids):
        p.items = list(ids)
        self.match._apply_items(p)

    def buy(self, p, iid):
        p.gold = 99999
        return self.match.shop_buy(p, iid)

    # --- regole d'acquisto ------------------------------------------------------------
    def test_one_starter_item(self):
        self.assertTrue(self.buy(self.a, "oran_berry"))
        self.assertFalse(self.buy(self.a, "honey"))
        self.assertFalse(self.buy(self.a, "exp_share"))

    def test_one_pair_of_boots(self):
        self.assertTrue(self.buy(self.a, "mach_bike"))
        self.assertFalse(self.buy(self.a, "acro_bike"))
        self.assertFalse(self.buy(self.a, "running_shoes"))

    def test_consumables_max_two(self):
        self.assertTrue(self.buy(self.a, "sitrus_berry"))
        self.assertTrue(self.buy(self.a, "sitrus_berry"))
        self.assertFalse(self.buy(self.a, "sitrus_berry"))
        self.assertTrue(self.buy(self.a, "ether"))

    def test_everstone_only_if_can_evolve(self):
        self.assertTrue(self.buy(self.a, "everstone"))
        self.assertFalse(self.buy(self.a, "everstone"))   # una sola
        d = self.mk(DELI, 0, self.base)
        self.assertFalse(self.buy(d, "everstone"))        # Delibird non si evolve

    # --- Pietrastante / Evolcondensa --------------------------------------------------
    def test_everstone_blocks_evolution_and_r_then_sell_evolves(self):
        self.give(self.a, "everstone")
        xp0 = self.a.xp
        self.match._gain_xp(self.a, 100.0)
        self.assertAlmostEqual(self.a.xp - xp0, 150.0)   # +50% di esperienza
        self.match._gain_xp(self.a, CUMULATIVE_XP[9] - self.a.xp + 1.0)
        self.match._update_evolution(0)
        self.assertEqual(self.a.stage, 0)
        self.assertNotIn("R", self.a.pending_choices)
        self.assertTrue(self.match.shop_sell(self.a, 0))
        self.match._update_evolution(0)
        self.assertEqual(self.a.stage, 2)                 # salta fino allo stadio del livello
        self.assertIn("R", self.a.pending_choices)

    def test_eviolite_percent_only_if_not_final(self):
        self.match._recompute_stats(self.a)
        d0, s0 = self.a.eff_defense(), self.a.eff_sp_defense()
        self.give(self.a, "eviolite")
        self.assertAlmostEqual(self.a.eff_defense(), d0 * 1.25, places=4)
        self.assertAlmostEqual(self.a.eff_sp_defense(), s0 * 1.25, places=4)
        d = self.mk(DELI, 0, self.base)
        self.match._recompute_stats(d)
        dd = d.eff_defense()
        self.give(d, "eviolite")
        self.assertAlmostEqual(d.eff_defense(), dd, places=4)

    # --- consumabili --------------------------------------------------------------------
    def test_sitrus_heals_once_below_30(self):
        self.give(self.b, "sitrus_berry")
        self.match._deal_damage(self.a, self.b, self.b.max_hp * 0.75)
        self.assertNotIn("sitrus_berry", self.b.items)
        self.assertAlmostEqual(self.b.hp, self.b.max_hp * 0.45, delta=1.0)

    def test_lum_cleanses_first_status(self):
        self.give(self.b, "lum_berry")
        self.match._apply_stun(self.b, 2.0)
        self.match._update_items(0.033)
        self.assertLessEqual(self.b.stun_until, self.match.time)
        self.assertNotIn("lum_berry", self.b.items)

    def test_ether_cuts_cooldowns_not_r(self):
        self.give(self.a, "ether")
        self.a.moveset["Q"].cooldown_remaining = 6.0
        self.a.moveset["R"].cooldown_remaining = 6.0
        self.assertTrue(self.match.use_item(self.a, 0))
        self.assertAlmostEqual(self.a.moveset["Q"].cooldown_remaining, 2.0)
        self.assertAlmostEqual(self.a.moveset["R"].cooldown_remaining, 6.0)
        self.assertEqual(self.a.items, [])

    # --- danno ----------------------------------------------------------------------------
    def test_light_ball_takes_more(self):
        self.b.max_hp = self.b.hp = 10000.0
        self.match._deal_damage(self.a, self.b, 100.0)
        base = 10000.0 - self.b.hp
        self.b.hp = 10000.0
        self.give(self.b, "light_ball")
        self.b.max_hp = self.b.hp = 10000.0
        self.match._deal_damage(self.a, self.b, 100.0)
        self.assertAlmostEqual(10000.0 - self.b.hp, base * 1.1, places=3)

    def test_black_glasses_low_hp_bonus_and_takedown_speed(self):
        self.give(self.a, "black_glasses")
        self.b.max_hp = 10000.0
        self.b.hp = 9000.0
        self.match._deal_damage(self.a, self.b, 100.0)
        hi = 9000.0 - self.b.hp
        self.b.hp = 3000.0
        self.match._deal_damage(self.a, self.b, 100.0)
        self.assertAlmostEqual(3000.0 - self.b.hp, hi * 1.2, places=3)
        self.match._item_on_takedown(self.a, [])
        self.assertGreater(self.a.speed_until, self.match.time)

    def test_honey_wild_bonus_and_heal(self):
        w = Wild(pos=self.base + Vec2(2, 0), team=2)
        w.max_hp = w.hp = 5000.0
        self.world.add(w)
        self.match._deal_damage(self.a, w, 100.0)
        base = 5000.0 - w.hp
        self.give(self.a, "honey")
        w.hp = 5000.0
        self.match._deal_damage(self.a, w, 100.0)
        self.assertAlmostEqual(5000.0 - w.hp, base * 1.3, places=3)
        self.a.hp = self.a.max_hp * 0.5
        self.match._item_on_wild_kill(self.a)
        self.assertAlmostEqual(self.a.hp, self.a.max_hp * 0.56, delta=0.5)
        self.match.time = 16 * 60.0   # dopo il minuto 15: niente bonus
        w.hp = 5000.0
        self.match._deal_damage(self.a, w, 100.0)
        self.assertAlmostEqual(5000.0 - w.hp, base, places=3)

    def test_iron_plate_and_silver_powder_extra(self):
        self.b.max_hp = self.b.hp = 20000.0
        self.give(self.a, "iron_plate")
        self.match._item_aa_extra(self.a, self.b)
        self.assertGreater(20000.0 - self.b.hp, 0.0)
        self.b.hp = 20000.0
        self.give(self.a, "silver_powder")
        self.match._item_aa_extra(self.a, self.b)
        self.assertGreater(20000.0 - self.b.hp, 0.0)

    def test_soft_sand_slows(self):
        self.give(self.a, "soft_sand")
        self.match._item_aa_extra(self.a, self.b)
        self.assertGreater(self.b.slow_until, self.match.time)
        self.assertAlmostEqual(self.b.slow_mult, 0.8)

    # --- controlli ---------------------------------------------------------------------------
    def test_snowball_shorter_cc_and_attack_after(self):
        self.give(self.b, "snowball")
        self.match._apply_stun(self.b, 2.0)
        self.assertAlmostEqual(self.b.stun_until - self.match.time, 1.5, places=3)
        self.match._update_items(0.033)
        self.match.time += 2.0
        self.match._update_items(0.033)
        self.assertTrue(self.b.snow_atk_active or self.b.snow_atk_until > self.match.time)

    def test_acro_bike_slow_and_jump(self):
        self.give(self.a, "acro_bike")
        self.match._apply_slow(self.a, 0.5, 2.0)
        self.assertAlmostEqual(self.a.slow_until - self.match.time, 1.4, places=3)
        self.a.facing = 0
        p0 = Vec2(self.a.pos.x, self.a.pos.y)
        self.assertTrue(self.match.use_item(self.a, 0))
        self.assertGreater(p0.dist(self.a.pos), 0.0)
        self.assertLessEqual(p0.dist(self.a.pos), 3.0 + 1e-6)
        self.assertFalse(self.match.use_item(self.a, 0))   # in ricarica

    # --- supporto -------------------------------------------------------------------------------
    def test_rusted_shield_shields_allies(self):
        ally = self.mk(TOTO, 0, self.base + Vec2(2.0, 0.0))
        self.give(self.a, "rusted_shield")
        self.assertTrue(self.match.use_item(self.a, 0))
        self.assertGreater(self.a.shield, 0.0)
        self.assertGreater(ally.shield, 0.0)
        self.assertEqual(self.b.shield, 0.0)

    def test_amulet_coin_gold(self):
        self.give(self.a, "amulet_coin")
        g = self.a.gold
        self.match._update_items(1.0)
        self.assertAlmostEqual(self.a.gold - g, 1.0)
        self.match._item_on_takedown(None, [self.a])
        self.assertAlmostEqual(self.a.gold - g, 31.0)

    def test_prism_scale_heal_buff(self):
        ally = self.mk(TOTO, 0, self.base + Vec2(2.0, 0.0))
        self.give(self.a, "prism_scale")
        ally.hp = ally.max_hp * 0.5
        h0 = ally.hp
        self.match._give_heal(self.a, ally, 100.0)
        self.assertAlmostEqual(ally.hp - h0, 110.0 * self.match._heal_in_mult(ally), places=3)
        self.assertGreater(ally.prism_until, self.match.time)
        self.assertGreater(self.match._item_as_bonus(ally), 0.0)

    # --- meteo locale ------------------------------------------------------------------------------
    def test_damp_rock_rain_on_ult(self):
        self.give(self.a, "damp_rock")
        self.match._item_on_ult(self.a)
        self.assertTrue(any(z["end"] > self.match.time for z in self.match.rain_zones))

    def test_heat_rock_sun_zone(self):
        self.give(self.a, "heat_rock")
        self.match._item_on_ult(self.a)
        self.assertEqual(len(self.match.sun_zones), 1)
        fire = type("M", (), {"type": "Fire"})()
        water = type("M", (), {"type": "Water"})()
        self.assertAlmostEqual(self.match._sun_mult(self.a, fire), 1.3)
        self.assertAlmostEqual(self.match._sun_mult(self.a, water), 0.7)
        self.match.time += 7.0
        self.match._update_items(0.033)
        self.assertEqual(self.match.sun_zones, [])


if __name__ == "__main__":
    unittest.main()
