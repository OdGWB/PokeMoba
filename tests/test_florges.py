import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.florges import BLOOM_AT, LIFE, flower_phase
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
FLA = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "flabebe.json"))
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


class TestFlorges(unittest.TestCase):
    def setUp(self):
        random.seed(3)
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        self.match.time = 100.0
        self.u = spawn(self.world, FLA, Vec2(20.5, 47.5), 0)
        self.a = spawn(self.world, FOE, Vec2(24.5, 44.5), 0)   # alleato
        self.e = spawn(self.world, FOE, Vec2(26.5, 48.5), 1)
        for x in (self.a, self.e):
            x.max_hp = x.hp = 5000.0
        self.match._update_regen = lambda dt: None
        self.rank_all()

    # --- aiuti -----------------------------------------------------------------
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
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(self.u, slot, x, y)

    def tick(self, sec):
        for _ in range(int(round(sec / DT))):
            self.match.time += DT
            self.match._combat_hash.rebuild(self.world.combatants())
            self.match._update_flor(DT)
            self.match._update_status(DT)

    def mine(self):
        return [f for f in self.match.flowers if f["owner"] == self.u.id]

    def plant_at(self, x, y):
        self.cast("Q", x, y)
        return self.mine()[-1]

    # --- dati ------------------------------------------------------------------
    def test_line_types_and_evolutions(self):
        self.assertEqual(self.u.types, ["Fairy"])
        self.assertEqual(self.u.passive_id, "giardino")
        self.level(4)
        self.assertEqual(self.u.name, "Floette")
        self.level(8)
        self.assertEqual(self.u.name, "Florges")
        self.assertEqual(self.u.base_stats.sp_defense, 154)

    def test_move_ids_are_own(self):
        for slot, sd in FLA.moves.items():
            for mv in ([sd.get("base")] if sd.get("base") else []) + list(sd.get("upgrades", [])):
                self.assertTrue(mv["id"].startswith("florges_"), mv["id"])

    # --- passiva ---------------------------------------------------------------
    def test_flower_phases_and_life(self):
        fl = self.plant_at(24.5, 47.5)
        now = self.match.time
        self.assertEqual(flower_phase(fl, now + 1.0), 0)
        self.assertEqual(flower_phase(fl, now + 3.0), 1)
        self.assertEqual(flower_phase(fl, now + BLOOM_AT + 0.01), 2)
        self.tick(LIFE + 0.2)
        self.assertEqual(self.mine(), [])

    def test_limit_per_stage_removes_oldest(self):
        first = self.plant_at(22.5, 44.5)
        self.plant_at(22.5, 45.5)
        self.plant_at(22.5, 46.5)
        self.assertEqual(len(self.mine()), 2)   # Flabébé: 2
        self.assertNotIn(first, self.mine())
        self.level(8)
        for y in (40.5, 41.5, 42.5, 43.5, 44.5):
            self.plant_at(26.5, y)
        self.assertEqual(len(self.mine()), 4)   # Florges: 4

    def test_ally_picks_only_bloomed(self):
        self.a.hp = 1000.0
        fl = self.plant_at(24.5, 44.5)   # sotto l'alleato: germoglio, nulla
        self.tick(0.5)
        self.assertIn(fl, self.mine())
        self.assertEqual(self.a.hp, 1000.0)
        self.tick(BLOOM_AT)
        self.assertNotIn(fl, self.mine())
        self.assertGreater(self.a.hp, 1000.0)

    def test_enemy_tramples_any_phase(self):
        self.e.hp = 1000.0
        fl = self.plant_at(26.5, 48.5)
        self.tick(0.1)
        self.assertNotIn(fl, self.mine())
        self.assertEqual(self.e.hp, 1000.0)

    def pick_color(self, color):
        self.u.flower_color = color
        fl = self.match._plant_flower(self.u, self.a.pos, bloom=0.0)
        self.tick(DT)
        self.assertNotIn(fl, self.match.flowers)

    def test_color_red_yellow(self):
        self.pick_color("red")
        self.assertGreater(self.a.flor_red_until, self.match.time)
        self.assertAlmostEqual(self.match._flor_dmg_mult(self.a), 1.15)
        self.pick_color("yellow")
        self.assertAlmostEqual(self.match._flor_speed_mult(self.a), 1.25)

    def test_color_orange_shield(self):
        self.pick_color("orange")
        self.assertAlmostEqual(self.a.shield, self.a.max_hp * 0.10, delta=1.0)

    def test_color_blue_cooldowns(self):
        self.a.moveset["Q"].cooldown_remaining = 5.0
        self.pick_color("blue")
        self.assertAlmostEqual(self.a.moveset["Q"].cooldown_remaining, 3.5, delta=0.05)

    def test_color_white_cleanse(self):
        self.a.stun_until = self.match.time + 5.0
        self.a.slow_until = self.match.time + 5.0
        self.pick_color("white")
        self.assertLess(self.a.stun_until, self.match.time)
        self.assertLess(self.a.slow_until, self.match.time)

    def test_quick_bloom(self):
        self.level(5)
        self.choose("Q", 0)
        fl = self.plant_at(24.5, 47.5)
        self.assertAlmostEqual(fl["bloom"] - fl["born"], 2.0)

    def test_roots_area_heals(self):
        self.level(5)
        self.choose("Q", 1)
        self.a.hp = 1000.0
        fl = self.match._plant_flower(self.u, self.a.pos, bloom=0.0)
        self.tick(DT)
        self.assertEqual(len(self.match.flor_roots), 1)
        after_pick = self.a.hp
        self.tick(1.0)
        self.assertGreater(self.a.hp, after_pick)
        self.tick(3.0)
        self.assertEqual(self.match.flor_roots, [])

    # --- W ------------------------------------------------------------------------
    def test_floral_healing_doubles_near_flower_and_blooms(self):
        self.a.hp = 1000.0
        self.cast("W", self.a.pos.x, self.a.pos.y)
        single = self.a.hp - 1000.0
        self.assertGreater(single, 0.0)
        self.a.hp = 1000.0
        fl = self.plant_at(24.5, 42.5)   # entro 3 tile dall'alleato
        self.cast("W", self.a.pos.x, self.a.pos.y)
        self.assertAlmostEqual(self.a.hp - 1000.0, single * 2.0, delta=1.0)
        self.assertEqual(flower_phase(fl, self.match.time), 2)

    def test_floral_healing_self_when_no_ally(self):
        self.u.hp = self.u.max_hp * 0.3
        hp = self.u.hp
        self.cast("W", 15.5, 52.5)
        self.assertGreater(self.u.hp, hp)

    def test_aromatherapy_cleanses_area(self):
        self.level(6)
        self.choose("W", 0)
        self.a.stun_until = self.match.time + 5.0
        self.cast("W", self.a.pos.x, self.a.pos.y)
        self.assertLess(self.a.stun_until, self.match.time)

    def test_symbiosis_shares_item_stats(self):
        self.level(6)
        self.choose("W", 1)
        self.u.items = ["choice_specs"]
        self.match._apply_items(self.u)
        spa = self.u.item_bonus.get("sp_attack", 0.0)
        self.assertGreater(spa, 0.0)
        self.cast("W", self.a.pos.x, self.a.pos.y)
        self.assertAlmostEqual(self.a.item_bonus.get("sp_attack", 0.0), spa * 0.3, delta=0.01)
        self.tick(4.2)
        self.assertEqual(self.a.item_bonus.get("sp_attack", 0.0), 0.0)

    # --- E ------------------------------------------------------------------------
    def test_petal_blizzard_self_and_flowers(self):
        self.e.pos = Vec2(22.5, 47.5)
        self.cast("E", 0, 0)
        self.assertLess(self.e.hp, self.e.max_hp)
        self.assertGreater(self.e.pos.dist(self.u.pos), 3.0)   # respinto
        # fiore lontano da Florges ma vicino al nemico: vortice al 50%
        self.e.hp = self.e.max_hp
        self.e.pos = Vec2(26.5, 52.5)
        self.u.pos = Vec2(20.5, 47.5)
        fl = self.match._plant_flower(self.u, Vec2(26.5, 51.5), bloom=60.0)
        self.cast("E", 0, 0)
        self.assertLess(self.e.hp, self.e.max_hp)
        self.assertIn(fl, self.match.flowers)   # non si consuma

    def test_petal_dance(self):
        self.level(7)
        self.choose("E", 0)
        self.e.pos = Vec2(21.5, 47.5)
        self.cast("E", 0, 0)
        self.assertGreater(self.match._flor_speed_mult(self.u), 1.29)
        self.tick(1.0)
        self.assertLess(self.e.hp, self.e.max_hp)
        self.tick(2.2)
        self.assertGreater(self.u.confuse_until, self.match.time)

    def test_misty_terrain_blocks_status(self):
        self.level(7)
        self.choose("E", 1)
        self.e.pos = Vec2(23.0, 47.5)
        self.cast("E", 0, 0)
        self.assertEqual(self.e.hp, self.e.max_hp)   # niente vortice intorno a Florges
        self.tick(0.1)
        self.match._apply_stun(self.u, 2.0)
        self.match._apply_poison(self.u, self.e, 10.0, 3.0)
        self.assertLess(self.u.stun_until, self.match.time)
        self.assertLess(self.u.poison_until, self.match.time)
        self.tick(5.2)
        self.match._apply_stun(self.u, 2.0)
        self.assertGreater(self.u.stun_until, self.match.time)

    # --- R ------------------------------------------------------------------------
    def test_royal_garden(self):
        self.level(8)
        self.choose("R", 0)
        self.plant_at(22.5, 44.5)
        self.cast("R", 27.5, 52.5)
        extra = [f for f in self.mine() if f["extra"]]
        self.assertEqual(len(extra), 6)
        self.assertTrue(all(flower_phase(f, self.match.time) == 2 for f in extra))
        self.assertAlmostEqual(extra[0]["end"] - self.match.time, 20.0)
        base = self.match._flor_pick_heal(self.u)
        self.tick(6.2)
        self.assertAlmostEqual(self.match._flor_pick_heal(self.u), base / 2.0, delta=0.5)

    def test_solar_beam_consumes_and_needs_flowers(self):
        self.level(8)
        self.choose("R", 1)
        self.cast("R", 0, 0)   # nessun fiore: non parte
        self.assertEqual(self.u.moveset["R"].cooldown_remaining, 0.0)
        self.plant_at(24.5, 47.5)
        self.plant_at(24.5, 46.5)
        self.cast("R", 0, 0)
        self.assertLess(self.e.hp, self.e.max_hp)
        self.assertEqual(self.mine(), [])

    def test_bot_picks_random_color(self):
        self.u.is_bot = True
        random.seed(1)
        self.match._update_flor(DT)
        self.assertIn(self.u.flower_color, ("red", "yellow", "orange", "blue", "white"))


if __name__ == "__main__":
    unittest.main()
