import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.archaludon import RAIN_SLOW
from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World
from net import protocol as P

DT = 1 / 30
ARCH = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "duraludon.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))


def spawn(world, d, pos, team):
    p = world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=d.color,
                            speed=d.base_speed, is_bot=False, types=d.types,
                            base_stats=d.base_stats, moves=d.moves, evolutions=d.evolutions,
                            role=d.role, passive=d.passive, attack_range=d.attack_range,
                            attack_cooldown=d.attack_cooldown, attack_fx=d.attack_fx)
    p.radius = d.radius
    p.spawn_pos = Vec2(2.0, 98.0)   # lontano dalla fontana: niente rigenerazione
    p.order = "idle"
    return p


class TestArchaludon(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        self.match.time = 100.0
        self.u = spawn(self.world, ARCH, Vec2(20.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(28.5, 47.5), 1)
        self.a = spawn(self.world, FOE, Vec2(22.5, 49.5), 0)
        self.e.max_hp = self.e.hp = 50000.0
        self.u.crit = self.e.crit = 0.0
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

    def cast(self, slot, x, y, hold=0.0):
        ms = self.u.moveset[slot]
        ms.cooldown_remaining = 0.0
        ms.rank = max(1, ms.rank)
        self.u.cast_hold = hold
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(self.u, slot, x, y)

    def tick(self, sec):
        for _ in range(int(round(sec / DT))):
            self.match.time += DT
            self.match._combat_hash.rebuild(self.world.combatants())
            self.match._update_arch(DT)

    def rain(self):
        self.match.jungle.weather = "rain"

    def lost(self):
        return self.e.max_hp - self.e.hp

    # --- dati ---------------------------------------------------------------------
    def test_evolves_at_8_with_real_stats(self):
        self.assertEqual(self.u.types, ["Steel", "Dragon"])
        self.assertEqual(self.u.base_stats.sp_attack, 120)
        self.level(8)
        self.assertEqual(self.u.dex, 1018)
        self.assertEqual(self.u.base_stats.hp, 90)
        self.assertEqual(self.u.base_stats.defense, 130)

    def test_upgrades_standard_levels(self):
        self.level(5)
        self.assertIn("Q", self.u.pending_choices)
        self.assertNotIn("W", self.u.pending_choices)

    # --- Q ------------------------------------------------------------------------
    def test_flashcannon_spdef_down(self):
        self.cast("Q", self.e.pos.x, self.e.pos.y)
        self.assertGreater(self.lost(), 0)
        self.assertGreater(self.e.spdef_debuff_until, self.match.time)
        self.assertAlmostEqual(self.e.spdef_debuff_mult, 0.85)

    def test_long_shot_charge(self):
        self.choose("Q", 0)
        far = Vec2(33.0, 47.5)                     # 12,5 tile: oltre i 10 base
        self.e.pos = far
        self.cast("Q", far.x, far.y, hold=0.0)
        self.assertEqual(self.lost(), 0)
        self.cast("Q", far.x, far.y, hold=1.0)
        self.assertGreater(self.lost(), 0)

    def test_long_shot_damage_scales(self):
        self.choose("Q", 0)
        self.cast("Q", self.e.pos.x, self.e.pos.y, hold=0.0)
        low = self.lost()
        self.e.hp = self.e.max_hp
        self.e.spdef_debuff_until = -1
        self.cast("Q", self.e.pos.x, self.e.pos.y, hold=1.0)
        self.assertAlmostEqual(self.lost() / low, 1.5, delta=0.05)

    def test_long_shot_rain_halves_charge(self):
        self.choose("Q", 0)
        self.rain()
        far = Vec2(33.0, 47.5)
        self.e.pos = far
        self.cast("Q", far.x, far.y, hold=0.5)     # sotto la pioggia 0,5 s = carica piena
        self.assertGreater(self.lost(), 0)

    def test_burst_two_charges(self):
        self.choose("Q", 1)
        ms = self.u.moveset["Q"]
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(self.u, "Q", self.e.pos.x, self.e.pos.y)
        ms.cooldown_remaining = 0.0
        self.match._cast(self.u, "Q", self.e.pos.x, self.e.pos.y)
        self.assertLess(ms.charges_cur, 0.5)
        ms.cooldown_remaining = 0.0
        self.assertFalse(ms.ready)

    # --- W ------------------------------------------------------------------------
    def test_thunderwave_delay_then_paralyze(self):
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.tick(0.5)
        self.assertLessEqual(self.e.root_until, self.match.time)
        self.tick(0.4)
        self.assertGreater(self.e.root_until, self.match.time)

    def test_thunderwave_rain_half_delay_and_slow(self):
        self.rain()
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.tick(0.42)
        self.assertGreater(self.e.root_until, self.match.time)
        self.assertGreater(self.e.slow_until, self.match.time)
        self.assertAlmostEqual(self.e.slow_mult, RAIN_SLOW)

    def test_bolt_upgrade_damages(self):
        self.choose("W", 0)
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.tick(0.9)
        self.assertGreater(self.lost(), 0)

    def test_plus_upgrade_bigger(self):
        self.choose("W", 1)
        self.cast("W", self.e.pos.x + 2.2, self.e.pos.y)
        self.tick(0.9)
        self.assertGreater(self.e.root_until, self.match.time)

    # --- E ------------------------------------------------------------------------
    def test_dragontail_push(self):
        self.e.pos = Vec2(22.0, 47.5)
        self.cast("E", 23.0, 47.5)
        self.assertGreater(self.lost(), 0)
        self.assertAlmostEqual(self.e.pos.x, 26.0, delta=0.05)

    def test_metalsound(self):
        self.choose("E", 0)
        self.e.pos = Vec2(22.5, 47.5)
        self.cast("E", 22.5, 47.5)
        self.assertAlmostEqual(self.e.spdef_debuff_mult, 0.7)
        self.assertEqual(self.lost(), 0)

    def test_irondefense_on_ally(self):
        self.choose("E", 1)
        self.cast("E", self.a.pos.x, self.a.pos.y)
        self.assertGreater(self.a.shield, 0)
        self.assertGreater(self.a.def_buff_until, self.match.time)
        self.assertAlmostEqual(self.a.def_buff_mult, 1.3)

    # --- R ------------------------------------------------------------------------
    def test_electroshot_charge_then_beam(self):
        self.level(8)
        self.choose("R", 0)
        far = spawn(self.world, FOE, Vec2(44.0, 47.5), 1)
        far.max_hp = far.hp = 50000.0
        self.cast("R", 30.0, 47.5)
        self.assertGreater(self.u.beam_charge_until, self.match.time)
        self.assertEqual(self.lost(), 0)
        self.tick(1.6)
        self.assertGreater(self.lost(), 0)
        self.assertLess(far.hp, far.max_hp)
        self.assertTrue(any(ev.get("kind") == "shake" for ev in self.match.fx_events))

    def test_electroshot_rain_instant(self):
        self.level(8)
        self.choose("R", 0)
        self.rain()
        self.cast("R", 30.0, 47.5)
        self.assertGreater(self.lost(), 0)
        self.assertGreater(self.u.arch_spa_until, self.match.time)

    def test_electroshot_interrupted(self):
        self.level(8)
        self.choose("R", 0)
        self.cast("R", 30.0, 47.5)
        self.u.stun_until = self.match.time + 1.0
        self.tick(1.6)
        self.assertEqual(self.lost(), 0)

    def test_thunder_three_bolts(self):
        self.level(8)
        self.choose("R", 1)
        ms = self.u.moveset["R"]
        for i in range(3):
            self.cast("R", self.e.pos.x, self.e.pos.y)
            if i < 2:
                self.assertLess(ms.cooldown_remaining, 1.0)
            self.tick(0.8)
        self.assertGreater(ms.cooldown_remaining, 30.0)
        self.assertEqual(self.u.thunder_left, 0)
        self.assertGreater(self.lost(), 0)

    def test_thunder_window_expires(self):
        self.level(8)
        self.choose("R", 1)
        ms = self.u.moveset["R"]
        self.cast("R", self.e.pos.x, self.e.pos.y)
        self.tick(5.2)
        self.assertEqual(self.u.thunder_left, 0)
        self.assertGreater(ms.cooldown_remaining, 30.0)

    def test_thunder_rain_bigger(self):
        self.level(8)
        self.choose("R", 1)
        self.rain()
        self.cast("R", self.e.pos.x, self.e.pos.y)
        self.assertAlmostEqual(self.match.thunder_marks[0]["radius"], 2.25)

    # --- rete -----------------------------------------------------------------------
    def test_hold_packed_in_slot_byte(self):
        data = P.enc_input(None, [{"seq": 1, "kind": P.CMD_CAST, "slot": 2, "x": 1.0,
                                   "y": 2.0, "hold": 0.8}])
        c = P.dec_input(data)["cmds"][0]
        self.assertEqual(c["slot"], 2)
        self.assertAlmostEqual(c["hold"], 0.8)


if __name__ == "__main__":
    unittest.main()
