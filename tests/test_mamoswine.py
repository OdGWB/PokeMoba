import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.entities import Wild
from engine.grid import TILE_LANE
from engine.mamoswine import FAT_FRAC, FROST_LOCK, TRACK_LIFE
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
SWI = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "swinub.json"))
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


class TestMamoswine(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.grid = m.grid
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        self.match.time = 100.0
        self.u = spawn(self.world, SWI, Vec2(20.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(22.5, 47.5), 1)
        self.f = spawn(self.world, FOE, Vec2(26.5, 51.5), 1)
        self.a = spawn(self.world, FOE, Vec2(20.5, 40.5), 0)   # alleato
        for x in (self.e, self.f, self.a):
            x.max_hp = x.hp = 50000.0
        for x in (self.u, self.e, self.f, self.a):
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
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(self.u, slot, x, y)

    def tick(self, sec):
        for _ in range(int(round(sec / DT))):
            self.match.time += DT
            self.match._combat_hash.rebuild(self.world.combatants())
            self.match._update_swine(DT)
            self.match._update_quakes()
            self.match._update_swine_shoves(DT)
            self.match._update_status(DT)

    @staticmethod
    def lost(u):
        return u.max_hp - u.hp

    # --- dati -----------------------------------------------------------------
    def test_evolutions_types_and_stats(self):
        self.assertEqual(self.u.types, ["Ice", "Ground"])
        self.assertEqual(self.u.passive_id, "fiuto")
        self.level(4)
        self.assertEqual(self.u.name, "Piloswine")
        self.assertEqual(self.u.passive_id, "grassospesso")
        self.level(8)
        self.assertEqual(self.u.name, "Mamoswine")
        self.assertEqual(self.u.types, ["Ice", "Ground"])
        self.assertEqual(self.u.base_stats.attack, 130)
        self.assertEqual(self.u.base_stats.speed, 80)
        self.assertEqual(self.u.passive_id, "gelo")

    # --- Fiuto ----------------------------------------------------------------
    def test_fiuto_bonus_vs_wild(self):
        w = Wild()
        w.team = 2
        self.assertAlmostEqual(self.match._swine_wild_mult(self.u, w), 1.3)
        self.assertAlmostEqual(self.match._swine_wild_mult(self.u, self.e), 1.0)
        self.level(8)   # resta anche da Mamoswine
        self.assertAlmostEqual(self.match._swine_wild_mult(self.u, w), 1.3)

    def test_tracks_in_jungle_only_for_enemies(self):
        self.tick(0.1)
        for k in range(6):
            self.e.pos = Vec2(22.5 + k * 0.8, 47.5)
            self.a.pos = Vec2(20.5 + k * 0.8, 40.5)
            self.tick(0.1)
        prints = self.match.swine_tracks
        self.assertGreaterEqual(len(prints), 4)
        self.assertTrue(all(t["team"] == 1 and t["viewer"] == 0 for t in prints))
        # sulla lane niente impronte
        for y in range(44, 50):
            for x in range(30, 40):
                self.grid.tiles[y][x] = TILE_LANE
        n = len(prints)
        for k in range(5):
            self.e.pos = Vec2(31.5 + k * 0.8, 47.5)
            self.tick(0.1)
        self.assertEqual(len(self.match.swine_tracks), n)
        self.tick(TRACK_LIFE + 0.2)
        self.assertEqual(self.match.swine_tracks, [])

    def test_no_tracks_without_sniffer(self):
        self.u.alive = False
        for k in range(6):
            self.e.pos = Vec2(22.5 + k * 0.8, 47.5)
            self.tick(0.1)
        self.assertEqual(self.match.swine_tracks, [])

    # --- Grassospesso ---------------------------------------------------------
    def test_thick_fat_shield_and_type_reduction(self):
        self.level(4)
        self.tick(0.1)
        cap = self.u.max_hp * FAT_FRAC
        self.assertAlmostEqual(self.u.fat_shield, cap, places=3)
        self.assertAlmostEqual(self.match._swine_type_mult(self.u, "Fire"), 0.5)
        self.assertAlmostEqual(self.match._swine_type_mult(self.u, "Ice"), 0.5)
        self.assertAlmostEqual(self.match._swine_type_mult(self.u, "Water"), 1.0)
        hp0 = self.u.hp
        self.match._deal_damage(self.e, self.u, cap * 0.5)
        self.assertAlmostEqual(self.u.hp, hp0)          # assorbito dallo scudo
        self.match._deal_damage(self.e, self.u, cap)
        self.assertAlmostEqual(self.u.fat_shield, 0.0)
        self.assertAlmostEqual(self.u.hp, hp0 - cap * 0.5, places=3)
        self.tick(7.0)
        self.assertAlmostEqual(self.u.fat_shield, 0.0)
        self.tick(1.2)
        self.assertAlmostEqual(self.u.fat_shield, cap, places=3)

    def test_swinub_has_no_fat(self):
        self.tick(0.2)
        self.assertEqual(self.u.fat_shield, 0.0)
        self.assertAlmostEqual(self.match._swine_type_mult(self.u, "Fire"), 1.0)

    # --- Gelo -----------------------------------------------------------------
    def test_frost_stacks_and_freeze_on_aa(self):
        self.level(8)
        for _ in range(4):
            self.match._swine_after_aa(self.u, self.e)
        self.assertEqual(self.e.frost_stacks, 4)
        self.assertLessEqual(self.e.frozen_until, self.match.time)
        self.match._swine_after_aa(self.u, self.e)
        self.assertGreater(self.e.frozen_until, self.match.time + 0.9)
        self.assertEqual(self.e.frost_stacks, 0)
        # al massimo una volta ogni 8 s per nemico
        self.tick(1.2)
        for _ in range(5):
            self.match._swine_after_aa(self.u, self.e)
        self.assertEqual(self.e.frost_stacks, 4)
        self.assertLessEqual(self.e.frozen_until, self.match.time)
        self.tick(FROST_LOCK - 1.0)
        self.match._swine_after_aa(self.u, self.e)   # accumuli scaduti nel frattempo
        self.assertEqual(self.e.frost_stacks, 1)

    def test_frost_expires(self):
        self.level(8)
        self.match._swine_after_aa(self.u, self.e)
        self.tick(5.2)
        self.assertEqual(self.e.frost_stacks, 0)

    def test_no_frost_before_mamoswine(self):
        self.level(4)
        self.match._swine_after_aa(self.u, self.e)
        self.cast("Q", self.e.pos.x, self.e.pos.y)
        self.assertEqual(self.e.frost_stacks, 0)

    def test_move_hit_gives_frost(self):
        self.level(8)
        self.cast("Q", self.e.pos.x, self.e.pos.y)
        self.assertGreater(self.lost(self.e), 0)
        self.assertEqual(self.e.frost_stacks, 1)

    # --- Q ----------------------------------------------------------------------
    def test_icetrail_speeds_allies_and_slows_foes(self):
        self.level(5)
        self.choose("Q", 0)
        self.e.pos = Vec2(30.5, 47.5)
        self.cast("Q", 24.5, 47.5)
        self.assertAlmostEqual(self.u.pos.x, 24.5, places=1)
        self.assertEqual(len(self.match.ice_trails), 1)
        self.a.pos = Vec2(22.5, 47.5)
        self.f.pos = Vec2(23.0, 47.5)
        self.tick(0.1)
        self.assertGreater(self.a.speed, self.a.move_speed_base * 1.25)
        self.assertLess(self.f.speed, self.f.move_speed_base * 0.75)
        self.tick(4.0)
        self.assertEqual(self.match.ice_trails, [])

    def test_takedown_knockback_and_recoil(self):
        self.level(5)
        self.choose("Q", 1)
        self.e.pos = Vec2(25.5, 47.5)
        hp0 = self.u.hp
        self.cast("Q", 30.5, 47.5)
        dealt = self.lost(self.e)
        self.assertGreater(dealt, 0)
        self.assertLess(self.u.pos.x, 25.5)
        self.assertAlmostEqual(hp0 - self.u.hp, dealt * 0.1, places=2)
        self.tick(0.5)
        self.assertAlmostEqual(self.e.pos.x, 27.5, places=1)

    # --- W ----------------------------------------------------------------------
    def test_avalanche_double_on_recent_attacker(self):
        self.cast("W", self.e.pos.x, self.e.pos.y)
        base = self.lost(self.e)
        self.assertGreater(base, 0)
        self.e.hp = self.e.max_hp
        self.match._deal_damage(self.e, self.u, 1.0)
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.assertAlmostEqual(self.lost(self.e) / base, 2.0, places=2)
        self.e.hp = self.e.max_hp
        self.tick(3.2)
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.assertAlmostEqual(self.lost(self.e) / base, 1.0, places=2)

    def test_bora_slows(self):
        self.level(6)
        self.choose("W", 0)
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.assertGreater(self.e.slow_until, self.match.time + 1.8)
        self.assertAlmostEqual(self.e.slow_mult, 0.6)

    def test_icefang_single_target_two_stacks(self):
        self.level(8)
        self.choose("W", 1)
        self.f.pos = Vec2(22.6, 48.0)
        self.cast("W", self.e.pos.x, self.e.pos.y)
        hit = [x for x in (self.e, self.f) if self.lost(x) > 0]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0].frost_stacks, 2)

    # --- E ----------------------------------------------------------------------
    def test_ancientpower_buff_only_on_pokemon_hit(self):
        atk0 = self.u.eff_attack()
        self.cast("E", 24.5, 41.5)   # a vuoto
        self.assertFalse(self.u.ancient_active)
        self.cast("E", self.e.pos.x, self.e.pos.y)
        self.assertGreater(self.lost(self.e), 0)
        self.assertTrue(self.u.ancient_active)
        self.assertAlmostEqual(self.u.eff_attack(), atk0 * 1.1, places=3)
        self.tick(0.1)
        self.assertAlmostEqual(self.u.speed, self.u.move_speed_base * 1.1, places=3)
        self.tick(4.0)
        self.assertFalse(self.u.ancient_active)

    def test_rockslide_stun_chance(self):
        self.level(7)
        self.choose("E", 0)
        random.seed(1)
        stuns = 0
        for _ in range(60):
            self.e.stun_until = -1.0
            self.cast("E", self.e.pos.x, self.e.pos.y)
            stuns += self.e.stun_until > self.match.time
        self.assertTrue(8 <= stuns <= 32, stuns)

    def test_stealthrock_same_as_existing(self):
        self.level(7)
        self.choose("E", 1)
        mv = self.u.moveset["E"].chosen
        self.assertEqual(mv.shape, "spikes")
        self.cast("E", self.e.pos.x, self.e.pos.y)
        self.assertTrue(any(ae.get("spikes") for ae in self.match.area_effects))

    # --- R ----------------------------------------------------------------------
    def test_earthquake(self):
        self.level(8)
        self.choose("R", 0)
        self.assertEqual(self.u.moveset["R"].chosen.category, "special")
        self.cast("R", self.u.pos.x, self.u.pos.y)
        self.assertEqual(len(self.match.quakes), 1)
        self.tick(0.1)
        self.assertGreater(self.lost(self.e), 0)

    def test_iceage_freezes_and_storm(self):
        self.level(8)
        self.choose("R", 1)
        self.e.pos = Vec2(28.5, 47.5)
        self.f.pos = Vec2(29.5, 48.5)
        self.cast("R", 40.5, 47.5)
        self.tick(0.7)
        self.assertGreater(self.lost(self.e), 0)
        self.assertGreater(self.e.frozen_until, self.match.time + 0.5)
        self.assertEqual(len(self.match.ice_storms), 1)
        self.assertEqual(self.match.glacial_blocks, [])
        self.assertLess(self.f.slow_mult, 0.7)
        self.tick(3.0)
        self.assertGreaterEqual(self.f.frost_stacks, 3)
        self.assertEqual(self.match.ice_storms, [])

    def test_iceage_miss_explodes_at_end(self):
        self.level(8)
        self.choose("R", 1)
        self.e.pos = Vec2(20.5, 55.5)
        self.f.pos = Vec2(20.5, 56.5)
        self.cast("R", 40.5, 47.5)
        self.tick(1.0)
        self.assertEqual(len(self.match.ice_storms), 1)
        c = self.match.ice_storms[0]["c"]
        self.assertAlmostEqual(c.x, 32.5, places=0)


if __name__ == "__main__":
    unittest.main()
