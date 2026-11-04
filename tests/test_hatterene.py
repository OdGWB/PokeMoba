import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.grid import TILE_BUSH
from engine.hatterene import AGITATE_DUR, TRICK_FAST, TRICK_SLOW
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
HATT = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "hatenna.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))
FAST = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "sneasel.json"))


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


class TestHatterene(unittest.TestCase):
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
        self.u = spawn(self.world, HATT, Vec2(20.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(26.5, 47.5), 1)
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

    def cast(self, slot, x, y, who=None):
        who = who or self.u
        ms = who.moveset[slot]
        ms.cooldown_remaining = 0.0
        ms.rank = max(1, ms.rank)
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(who, slot, x, y)

    def tick(self, sec):
        for _ in range(int(round(sec / DT))):
            self.match.time += DT
            self.match._combat_hash.rebuild(self.world.combatants())
            self.match._update_hatt(DT)

    def lost(self):
        return self.e.max_hp - self.e.hp

    # --- dati ---------------------------------------------------------------------
    def test_evolutions_and_types(self):
        self.assertEqual(self.u.types, ["Psychic"])
        self.level(4)
        self.assertEqual(self.u.name, "Hattrem")
        self.assertEqual(self.u.types, ["Psychic"])
        self.level(8)
        self.assertEqual(self.u.name, "Hatterene")
        self.assertEqual(self.u.types, ["Psychic", "Fairy"])
        self.assertEqual(self.u.base_stats.sp_attack, 136)
        self.assertEqual(self.u.base_stats.speed, 29)

    # --- passiva Quiete -------------------------------------------------------------
    def test_enemy_cast_nearby_agitates(self):
        self.cast("Q", 20.5, 47.5, who=self.e)
        self.assertGreater(self.e.agitated_until, self.match.time)
        self.tick(0.1)
        self.assertTrue(self.e.agitated)
        self.tick(AGITATE_DUR)
        self.assertFalse(self.e.agitated)

    def test_far_cast_does_not_agitate(self):
        self.e.pos = Vec2(40.5, 47.5)   # 20 tile
        self.cast("Q", 41.5, 47.5, who=self.e)
        self.assertLess(self.e.agitated_until, self.match.time)

    def test_agitated_takes_more_damage(self):
        self.cast("Q", 26.5, 47.5)
        self.tick(0.6)
        base = self.lost()
        self.e.hp = self.e.max_hp
        self.e.confuse_until = -1.0
        self.e.agitated_until = self.match.time + 3.0
        self.cast("Q", 26.5, 47.5)
        self.tick(0.6)
        self.assertAlmostEqual(self.lost() / base, 1.10, places=2)

    def test_agitated_visible_in_bush(self):
        self.grid.tiles[47][26] = TILE_BUSH
        self.match.vision.update(self.world, 0)
        self.assertNotIn(self.e.id, self.match.vision.visible_enemies[0])
        self.e.agitated_until = self.match.time + 3.0
        self.tick(DT)
        self.match.vision.update(self.world, 0)
        self.assertIn(self.e.id, self.match.vision.visible_enemies[0])

    # --- Q -------------------------------------------------------------------------
    def test_confusion_delayed_and_confuses(self):
        self.cast("Q", 26.5, 47.5)
        self.tick(0.3)
        self.assertEqual(self.lost(), 0)
        self.tick(0.3)
        self.assertGreater(self.lost(), 0)
        self.assertGreater(self.e.confuse_until, self.match.time + 1.0)

    def test_psyshock_uses_defense(self):
        self.level(5)
        self.choose("Q", 0)
        self.e.stats.defense = 0.0
        self.e.stats.sp_defense = 400.0
        self.cast("Q", 26.5, 47.5)
        self.tick(0.6)
        shock = self.lost()
        self.e.hp = self.e.max_hp
        self.u.moveset["Q"].chosen = self.u.moveset["Q"].base
        self.cast("Q", 26.5, 47.5)
        self.tick(0.6)
        self.assertGreater(shock, self.lost() * 1.5)

    def test_psybeam_line(self):
        self.level(5)
        self.choose("Q", 1)
        e2 = spawn(self.world, FOE, Vec2(29.5, 47.5), 1)
        self.cast("Q", 30.5, 47.5)
        self.assertGreater(self.lost(), 0)
        self.assertLess(e2.hp, e2.max_hp)
        self.assertGreater(e2.confuse_until, self.match.time)

    # --- W -------------------------------------------------------------------------
    def test_voice_pushes(self):
        self.e.pos = Vec2(22.5, 47.5)
        self.cast("W", 22.5, 47.5)
        self.assertGreater(self.lost(), 0)
        self.assertAlmostEqual(self.e.pos.x, 25.5, places=1)

    def test_magic_powder_psychic_type(self):
        self.level(6)
        self.choose("W", 0)
        self.e.pos = Vec2(22.5, 47.5)
        self.cast("W", 22.5, 47.5)
        self.assertEqual(self.e.types, ["Psychic"])
        self.assertAlmostEqual(self.e.pos.x, 22.5, places=3)   # niente respinta
        self.tick(4.1)
        self.assertEqual(self.e.types, ["Water"])

    def test_draining_kiss_heals(self):
        self.level(6)
        self.choose("W", 1)
        self.u.hp = self.u.max_hp * 0.5
        hp0 = self.u.hp
        self.e.pos = Vec2(22.5, 47.5)
        self.cast("W", 22.5, 47.5)
        self.assertAlmostEqual(self.u.hp - hp0, self.lost() * 0.5, delta=1.0)

    # --- E -------------------------------------------------------------------------
    def test_moonblast_slow_orb_stuns_first(self):
        self.cast("E", 26.5, 47.5)
        self.tick(0.3)
        self.assertEqual(self.lost(), 0)        # sfera lenta: non ancora arrivata
        self.tick(1.0)
        self.assertGreater(self.lost(), 0)
        self.assertGreater(self.e.stun_until, self.match.time)
        self.assertFalse(self.match.moon_orbs)

    def test_mystical_fire_lowers_spa(self):
        self.level(7)
        self.choose("E", 0)
        self.cast("E", 26.5, 47.5)
        self.tick(1.3)
        self.assertAlmostEqual(self.e.spa_down_mult, 0.75)
        self.assertGreater(self.e.spa_down_until, self.match.time + 3.0)

    def test_moonblast_plus_area(self):
        self.level(7)
        self.choose("E", 1)
        e2 = spawn(self.world, FOE, Vec2(26.5, 49.0), 1)
        self.cast("E", 26.5, 47.5)
        self.tick(1.3)
        self.assertLess(e2.hp, e2.max_hp)
        self.assertGreater(e2.stun_until, self.match.time)

    # --- R -------------------------------------------------------------------------
    def test_trick_room_speeds(self):
        self.level(8)
        self.choose("R", 0)
        f = spawn(self.world, FAST, Vec2(21.5, 47.5), 1)   # Sneasel: Velocità 115
        self.cast("R", 21.0, 47.5)
        self.assertAlmostEqual(self.match._hatt_speed_mult(self.u), TRICK_FAST)
        self.assertAlmostEqual(self.match._hatt_speed_mult(f), TRICK_SLOW)
        self.tick(6.1)
        self.assertAlmostEqual(self.match._hatt_speed_mult(self.u), 1.0)

    def test_forest_witch_stuns_agitated(self):
        self.level(8)
        self.choose("R", 1)
        e2 = spawn(self.world, FOE, Vec2(24.5, 49.5), 1)
        e2.max_hp = e2.hp = 50000.0
        self.e.agitated_until = self.match.time + 5.0
        self.cast("R", 20.5, 47.5)
        self.tick(0.5)
        self.assertEqual(self.lost(), 0)
        self.tick(0.4)
        self.assertGreater(self.lost(), (e2.max_hp - e2.hp) * 1.5)
        self.assertGreater(self.e.stun_until, self.match.time + 1.0)
        self.assertLess(e2.stun_until, self.match.time)


if __name__ == "__main__":
    unittest.main()
