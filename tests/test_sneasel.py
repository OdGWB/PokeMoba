import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.grid import TILE_JUNGLE_WALL
from engine.match import Match
from engine.pathfinding import find_path, smooth_path
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
SNE = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "sneasel.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "squirtle.json"))


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


class TestSneasel(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.grid = m.grid
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        self.u = spawn(self.world, SNE, Vec2(26.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(30.0, 47.5), 1)
        self.e.max_hp = self.e.hp = 50000.0
        self.match._update_regen = lambda dt: None

    def level(self, lv):
        self.match._gain_xp(self.u, CUMULATIVE_XP[lv] - self.u.xp + 1.0)
        self.match._update_evolution(0)

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

    def step(self, sec):
        for i in range(int(round(sec / DT))):
            self.match.update(DT, i)

    def wild(self, pos, kind="camp"):
        return self.world.spawn_wild(pos, kind, 3000.0, 10.0, 1.6, 1.2, 50.0, 30)

    def to_sneasler(self):
        self.u.gold_wild = 10.0
        self.level(8)
        self.assertEqual(self.u.name, "Sneasler")
        self.rank_all()

    # --- Sole e Luna ---------------------------------------------------------------
    def test_gold_counters(self):
        w = self.wild(Vec2(28.0, 45.0))
        g0 = self.u.gold
        self.match._deal_damage(self.u, w, w.hp + 1.0)
        self.assertGreater(self.u.gold_wild, 0.0)
        self.assertAlmostEqual(self.u.gold - g0, self.u.gold_wild, delta=0.01)
        mn = self.world.spawn_minion(Vec2(28.0, 49.0), 1, "mid", [], (200, 60, 60), gold=20)
        self.match._deal_damage(self.u, mn, mn.hp + 1.0)
        self.assertAlmostEqual(self.u.gold_minion, 20.0)

    def test_tie_evolves_weavile(self):
        self.level(8)
        self.assertEqual(self.u.name, "Weavile")
        self.assertEqual(self.u.passive_id, "arraffalesto")
        self.assertEqual(self.u.moveset["Q"].chosen.id, "nightslash")

    def test_wild_gold_evolves_sneasler(self):
        self.u.gold_minion, self.u.gold_wild = 100.0, 140.0
        self.level(8)
        self.assertEqual(self.u.name, "Sneasler")
        self.assertEqual(self.u.types, ["Fighting", "Poison"])
        self.assertEqual(self.u.moveset["Q"].chosen.id, "direclaw")

    def test_q_upgrade_without_choice(self):
        self.level(5)
        self.assertEqual(self.u.moveset["Q"].chosen.id, "iceshardplus")

    # --- W ---------------------------------------------------------------------------
    def test_thief_steals_gold_once_per_10s(self):
        self.level(3)
        self.rank_all()
        self.e.gold = 100.0
        self.e.pos = Vec2(27.8, 47.5)
        g0 = self.u.gold
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.assertAlmostEqual(self.u.gold - g0, 10.0)
        self.assertAlmostEqual(self.e.gold, 90.0)
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.assertAlmostEqual(self.e.gold, 90.0)      # stesso bersaglio entro 10 s
        self.match.time += 10.1
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.assertAlmostEqual(self.e.gold, 80.0)

    def test_poison_jab(self):
        self.level(6)
        self.choose("W", 1)
        self.e.pos = Vec2(27.8, 47.5)
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.assertGreater(self.e.poison_until, self.match.time + 2.5)

    # --- E ---------------------------------------------------------------------------
    def test_double_dash_charges(self):
        self.level(7)
        self.choose("E", 0)
        ms = self.u.moveset["E"]
        self.cast("E", 30.0, 47.5)
        self.assertTrue(ms.ready or ms.cooldown_remaining <= 0.6)
        self.step(0.7)
        self.assertTrue(ms.ready)                       # seconda carica
        self.match._cast(self.u, "E", 34.0, 47.5)
        self.step(0.7)
        self.assertFalse(ms.ready)                      # cariche finite

    def test_quick_dance_attack_boost(self):
        self.level(7)
        self.choose("E", 1)
        atk = self.u.eff_attack()
        self.cast("E", 30.0, 45.0)
        self.assertAlmostEqual(self.u.eff_attack(), atk * 1.25, delta=0.5)
        self.step(2.7)
        self.assertAlmostEqual(self.u.eff_attack(), atk, delta=0.5)

    # --- Weavile ---------------------------------------------------------------------
    def test_night_slash_crits_isolated(self):
        self.level(8)
        self.u.crit = 0.0
        self.e.pos = Vec2(28.5, 47.5)
        hp0 = self.e.hp
        self.cast("Q", 30.0, 47.5)
        lone = hp0 - self.e.hp
        ally = spawn(self.world, FOE, Vec2(31.0, 49.0), 1)   # ora non è più isolato
        hp1 = self.e.hp
        self.cast("Q", 30.0, 47.5)
        crowd = hp1 - self.e.hp
        self.assertGreater(lone, crowd * 1.3)

    def test_snatch_stacks(self):
        self.level(8)
        self.rank_all()
        self.e.pos = Vec2(28.0, 47.5)
        atk_e = self.e.eff_attack()
        for _ in range(7):
            self.cast("Q", 30.0, 47.5)
        self.assertEqual(self.e.snatch_down, 5)
        self.assertEqual(self.u.snatch_up, 5)
        self.assertAlmostEqual(self.e.eff_attack(), atk_e * 0.75, delta=0.5)
        self.e.pos = Vec2(40.0, 47.5)   # fuori portata: niente altri attacchi base
        self.step(4.2)
        self.assertEqual(self.e.snatch_down, 0)
        self.assertEqual(self.u.snatch_up, 0)

    def test_nightfall_stealth_and_ambush(self):
        self.level(8)
        self.choose("R", 0)
        self.cast("R", self.u.pos.x, self.u.pos.y)
        self.step(0.1)
        self.assertTrue(self.u.invisible)
        self.assertGreater(self.u.speed_mult, 1.2)
        self.e.pos = Vec2(28.0, 47.5)
        self.cast("Q", 30.0, 47.5)
        self.assertFalse(self.u.invisible)
        self.assertLess(self.e.slow_mult, 0.6)
        self.assertGreater(self.e.slow_until, self.match.time + 1.5)
        self.step(0.1)
        self.assertLessEqual(self.u.speed_mult, 1.0)

    def test_nightfall_expires(self):
        self.level(8)
        self.choose("R", 0)
        self.cast("R", self.u.pos.x, self.u.pos.y)
        self.step(4.2)
        self.assertFalse(self.u.invisible)

    def test_beat_up_hits_with_allies(self):
        self.level(8)
        self.choose("R", 1)
        spawn(self.world, SNE, Vec2(24.0, 47.5), 0)
        spawn(self.world, SNE, Vec2(24.0, 46.0), 0)
        self.e.pos = Vec2(29.5, 47.5)
        self.cast("R", 29.5, 47.5)
        self.assertEqual(self.match.beatups[0]["hits"], 5)
        self.step(1.2)
        self.assertFalse(self.match.beatups)
        self.assertLess(self.u.pos.dist(self.e.pos), 1.5)

    # --- Sneasler --------------------------------------------------------------------
    def test_sneasler_wild_bonus(self):
        self.to_sneasler()
        w = self.wild(Vec2(28.0, 45.0))
        hp0 = w.hp
        self.match._deal_damage(self.u, w, 100.0)
        self.assertAlmostEqual(hp0 - w.hp, 130.0)

    def _wall(self, x0, x1, y0=38, y1=57):
        for y in range(y0, y1):
            for x in range(x0, x1):
                self.grid.tiles[y][x] = TILE_JUNGLE_WALL

    def _walk_to(self, dest):
        tiles = find_path(self.grid, (int(self.u.pos.x), int(self.u.pos.y)),
                          (int(dest.x), int(dest.y)))
        self.u.set_path([Vec2(x, y) for (x, y) in smooth_path(self.grid, tiles)[1:]])

    def test_climb_thin_wall(self):
        self._wall(28, 30)              # muro spesso 2 tile
        self.to_sneasler()
        self.u.pos = Vec2(27.4, 47.5)
        self._walk_to(Vec2(33.5, 47.5))
        self.step(0.2)
        self.assertTrue(self.match.claw_leaps)
        self.assertGreater(self.u.untargetable_until, self.match.time)
        self.step(1.1)
        self.assertGreater(self.u.pos.x, 30.0)
        self.assertGreater(self.u.climb_ready_at, self.match.time + 4.0)

    def test_no_climb_thick_wall(self):
        self._wall(28, 32)              # spesso 4 tile: niente
        self.to_sneasler()
        self.u.pos = Vec2(27.4, 47.5)
        self._walk_to(Vec2(35.5, 47.5))
        self.step(0.3)
        self.assertFalse(self.match.claw_leaps)

    def test_dire_claw_status(self):
        self.to_sneasler()
        self.e.pos = Vec2(28.0, 47.5)
        got = 0
        for _ in range(20):
            self.e.poison_until = self.e.root_until = self.e.sleep_until = -1.0
            self.cast("Q", 30.0, 47.5)
            t = self.match.time
            if self.e.poison_until > t or self.e.root_until > t or self.e.sleep_until > t:
                got += 1
        self.assertTrue(3 <= got <= 17)

    def test_cliff_ambush_needs_wall(self):
        self.to_sneasler()
        self.choose("R", 0)
        self.e.pos = Vec2(33.0, 47.5)
        self.cast("R", 33.0, 47.5)
        self.assertFalse(self.match.claw_leaps)          # nessun muro vicino
        self._wall(24, 26)
        self.cast("R", 33.0, 47.5)
        self.assertTrue(self.match.claw_leaps)
        self.step(0.8)
        self.assertGreater(self.e.stun_until, self.match.time)
        self.assertLess(self.u.pos.dist(self.e.pos), 1.5)

    def test_sludge_lob_poison_and_healcut(self):
        self.to_sneasler()
        self.choose("R", 1)
        self.e.pos = Vec2(31.0, 47.5)
        self.cast("R", 31.0, 47.5)
        self.step(0.7)
        self.assertGreater(self.e.poison_until, self.match.time + 3.0)
        self.assertGreater(self.e.healcut_until, self.match.time + 5.0)
        self.e.hp = 1000.0
        self.match._give_heal(self.e, self.e, 100.0)
        self.assertAlmostEqual(self.e.hp, 1050.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
