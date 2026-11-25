import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.basic_attack import is_melee
from engine.content import load_map, load_pokemon_def
from engine.delibird import KIND_MULT, QUEUE_LEN
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
DELI = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "delibird.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))


def spawn(world, d, pos, team):
    p = world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=d.color,
                            speed=d.base_speed, is_bot=False, types=d.types,
                            base_stats=d.base_stats, moves=d.moves, evolutions=d.evolutions,
                            role=d.role, passive=d.passive, attack_range=d.attack_range,
                            attack_cooldown=d.attack_cooldown, attack_fx=d.attack_fx)
    p.radius = d.radius
    p.spawn_pos = Vec2(2.0, 98.0)
    p.order = "idle"
    return p


class TestDelibird(unittest.TestCase):
    def setUp(self):
        random.seed(5)
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        self.match.time = 100.0
        self.u = spawn(self.world, DELI, Vec2(20.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(24.5, 47.5), 1)
        self.a = spawn(self.world, FOE, Vec2(20.5, 52.5), 0)   # alleato
        for x in (self.e, self.a):
            x.max_hp = x.hp = 50000.0
        for x in (self.u, self.e, self.a):
            x.crit = 0.0
        self.match._update_regen = lambda dt: None

    def level(self, lv):
        self.match._gain_xp(self.u, CUMULATIVE_XP[lv] - self.u.xp + 1.0)
        self.match._update_evolution(0)
        self.rank_all()

    def choose(self, slot, idx):
        if slot not in self.u.pending_choices:
            self.u.pending_choices.append(slot)
        evolution.apply_choice(self.u, slot, idx)
        self.rank_all()

    def rank_all(self):
        for _ in range(20):
            for s in ("R", "Q", "W", "E"):
                if skills.can_rank_up(self.u, s):
                    skills.rank_up(self.u, s)

    def cast(self, slot, x, y):
        ms = self.u.moveset[slot]
        ms.cooldown_remaining = 0.0
        ms.rank = max(1, ms.rank)
        if ms.charges_cur >= 0:
            ms.charges_cur = max(ms.charges_cur, 1.0)
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(self.u, slot, x, y)

    def tick(self, sec):
        for _ in range(int(round(sec / DT))):
            self.match.time += DT
            self.match._combat_hash.rebuild(self.world.combatants())
            self.match._update_deli(DT)
            self.match._update_status(DT)

    @staticmethod
    def lost(u):
        return u.max_hp - u.hp

    def gift(self, kind, tgt):
        self.u.deli_queue = [kind, "s", "s"]
        self.cast("Q", tgt.pos.x, tgt.pos.y)
        self.tick(1.0)

    # --- dati -------------------------------------------------------------------
    def test_data(self):
        self.assertEqual(self.u.types, ["Ice", "Flying"])
        self.assertEqual(self.u.passive_id, "paccoinarrivo")
        self.assertEqual(self.u.base_stats.sp_attack, 65)
        power, magic = self.match._aa_power(self.u)
        self.assertTrue(magic)
        self.assertFalse(is_melee(self.u))
        self.level(8)
        self.assertEqual(self.u.name, "Delibird")   # nessuna evoluzione
        for s in ("Q", "W", "E", "R"):
            self.assertIn(s, self.u.pending_choices)

    def test_item_attack_becomes_sp_attack(self):
        self.u.items = ["quick_claw"]
        self.match._apply_items(self.u)
        self.assertNotIn("attack", self.u.item_bonus)

    # --- Q: pacchi ------------------------------------------------------------------
    def test_queue_filled(self):
        self.tick(DT)
        self.assertEqual(len(self.u.deli_queue), QUEUE_LEN)

    def test_pack_damage_scales(self):
        hits = {}
        for kind in ("s", "m", "l"):
            self.e.hp = self.e.max_hp
            self.gift(kind, self.e)
            hits[kind] = self.lost(self.e)
        self.assertGreater(hits["s"], 0)
        self.assertAlmostEqual(hits["m"] / hits["s"], KIND_MULT["m"], delta=0.05)
        self.assertAlmostEqual(hits["l"] / hits["s"], KIND_MULT["l"], delta=0.05)

    def test_large_splash(self):
        f = spawn(self.world, FOE, Vec2(25.5, 48.5), 1)
        f.max_hp = f.hp = 50000.0
        f.crit = 0.0
        self.gift("l", self.e)
        self.assertGreater(self.lost(f), 0)
        self.assertLess(self.lost(f), self.lost(self.e))

    def test_gift_heals_ally_and_stops_there(self):
        self.a.hp = 1000.0
        self.e.pos = Vec2(20.5, 56.5)   # nemico dietro l'alleato
        self.gift("g", self.a)
        self.assertGreater(self.a.hp, 1000.0)
        self.assertEqual(self.lost(self.e), 0)

    def test_damage_pack_on_ally_harmless(self):
        self.gift("l", self.a)
        self.assertEqual(self.lost(self.a), 0)

    def test_gift_on_enemy_heals_self(self):
        self.u.hp = self.u.max_hp * 0.5
        hp0 = self.u.hp
        self.gift("g", self.e)
        self.assertGreater(self.u.hp, hp0)
        self.assertEqual(self.lost(self.e), 0)

    def test_express_two_charges(self):
        self.level(5)
        self.choose("Q", 1)
        ms = self.u.moveset["Q"]
        self.assertEqual(ms.chosen.charges, 2)
        ms.cooldown_remaining = 0.0
        self.match._cast(self.u, "Q", 30.0, 47.5)
        ms.cooldown_remaining = 0.0
        self.assertTrue(ms.ready)
        self.match._cast(self.u, "Q", 30.0, 47.5)
        ms.cooldown_remaining = 0.0
        self.assertFalse(ms.ready)

    # --- W -------------------------------------------------------------------------------
    def test_spikes_trigger_and_cap(self):
        self.level(6)
        self.choose("W", 0)
        self.e.pos = Vec2(40.5, 40.5)
        self.cast("W", 26.0, 47.5)
        self.assertEqual(len(self.match.deli_spikes), 3)
        self.cast("W", 26.0, 44.0)
        self.cast("W", 26.0, 51.0)
        self.assertEqual(len(self.match.deli_spikes), 6)
        sp = self.match.deli_spikes[-1]
        self.e.pos = Vec2(sp["c"].x, sp["c"].y)
        self.tick(DT * 2)
        self.assertGreater(self.lost(self.e), 0)
        self.assertGreater(self.e.slow_until, self.match.time)
        self.assertEqual(len(self.match.deli_spikes), 5)

    def test_freezedry_double_vs_water(self):
        self.level(6)
        self.choose("W", 1)
        self.e.types = ["Normal"]
        self.cast("W", 30.0, 47.5)
        normal = self.lost(self.e)
        self.e.hp = self.e.max_hp
        self.e.types = ["Water"]
        eff = self.match.types.moba_multiplier("Ice", ["Water"])
        self.cast("W", 30.0, 47.5)
        self.assertAlmostEqual(self.lost(self.e) / normal, 2.0 * eff, delta=0.05)

    # --- E -------------------------------------------------------------------------------
    def test_surprise_bomb(self):
        self.level(7)
        self.choose("E", 1)
        start = Vec2(self.u.pos.x, self.u.pos.y)
        self.e.pos = Vec2(start.x - 1.5, start.y - 0.8)
        self.cast("E", start.x, start.y + 10.0)
        self.assertGreater(start.dist(self.u.pos), 3.0)
        self.assertEqual(self.lost(self.e), 0)
        self.tick(1.1)
        self.assertGreater(self.lost(self.e), 0)

    # --- R -------------------------------------------------------------------------------
    def test_special_delivery(self):
        self.level(8)
        self.choose("R", 1)
        self.a.hp = 1000.0
        self.a.pos = Vec2(24.5, 49.0)
        self.cast("R", 24.5, 47.5)
        self.tick(0.5)
        self.assertEqual(self.lost(self.e), 0)
        self.tick(0.6)
        self.assertGreater(self.lost(self.e), 0)
        self.assertGreater(self.e.frozen_until, self.match.time)
        self.assertGreater(self.a.hp, 1000.0)

    def test_paradox_form_and_revert(self):
        self.level(8)
        self.choose("R", 0)
        self.u.deli_queue = ["l", "g", "m"]
        self.u.hp = self.u.max_hp * 0.5
        self.cast("R", 0, 0)
        self.assertEqual(self.u.name, "Ferrosacco")
        self.assertEqual(self.u.dex, 991)
        self.assertEqual(self.u.types, ["Water", "Ice"])
        self.assertAlmostEqual(self.u.hp / self.u.max_hp, 0.5, delta=0.01)
        self.assertEqual(self.u.moveset["Q"].chosen.name, "Idropompa")
        self.assertEqual(self.u.moveset["E"].chosen.name, "Inversione")
        self.assertGreater(self.match._eff_attack_speed(self.u), 0)
        self.cast("Q", 30.0, 47.5)
        self.assertGreater(self.lost(self.e), 0)
        self.tick(8.2)
        self.assertEqual(self.u.name, "Delibird")
        self.assertEqual(self.u.moveset["Q"].chosen.shape, "deligift")
        self.assertEqual(self.u.deli_queue, ["l", "g", "m"])

    def test_quark_in_electric_field(self):
        self.level(8)
        self.choose("R", 0)
        self.cast("R", 0, 0)
        self.match.mag_fields.append({"c": Vec2(self.u.pos.x, self.u.pos.y), "radius": 3.0})
        self.tick(DT * 2)
        self.assertTrue(self.u.quark_active)
        self.assertEqual(self.u.quark_stat, "speed")
        self.assertGreater(self.u.ferro_until, self.match.time + 11.0)
        self.match.mag_fields.clear()
        self.tick(9.0)
        self.assertEqual(self.u.name, "Ferrosacco")   # la forma dura di più
        self.tick(3.5)
        self.assertEqual(self.u.name, "Delibird")
        self.assertFalse(self.u.quark_active)


if __name__ == "__main__":
    unittest.main()
