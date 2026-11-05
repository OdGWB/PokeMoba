import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.grid import TILE_WALL
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
LIT = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "litten.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))


def spawn(world, d, pos, team):
    p = world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=d.color,
                            speed=d.base_speed, is_bot=False, types=d.types,
                            base_stats=d.base_stats, moves=d.moves, evolutions=d.evolutions,
                            role=d.role, passive=d.passive, attack_range=d.attack_range,
                            attack_cooldown=d.attack_cooldown, attack_fx=d.attack_fx)
    p.radius = d.radius
    p.spawn_pos = Vec2(pos.x, pos.y)
    p.order = "idle"
    return p


class TestIncineroar(unittest.TestCase):
    def setUp(self):
        random.seed(5)
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.grid = m.grid
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        self.match.time = 100.0
        self.u = spawn(self.world, LIT, Vec2(20.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(22.0, 47.5), 1)
        self.e.max_hp = self.e.hp = 50000.0
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
            self.match._update_incin(DT)
            self.match._update_status(DT)

    def wall_col(self, x):
        for y in range(30, 60):
            self.grid.tiles[y][x] = TILE_WALL

    # --- evoluzioni e passive ---------------------------------------------------
    def test_evolutions(self):
        self.assertEqual(self.u.name, "Litten")
        self.assertEqual(self.u.types, ["Fire"])
        self.level(4)
        self.assertEqual(self.u.name, "Torracat")
        self.level(8)
        self.assertEqual(self.u.name, "Incineroar")
        self.assertEqual(set(self.u.types), {"Fire", "Dark"})
        self.assertEqual(self.u.passive_id, "cattivodelring")

    def test_intimidate_after_idle(self):
        self.u.incin_last_dealt = -1e9
        self.u.last_damaged_at = -1e9
        before = self.e.eff_attack()
        self.match._deal_damage(self.u, self.e, 10.0)
        self.tick(DT)
        self.assertGreater(self.e.incin_intim_until, self.match.time)
        self.assertAlmostEqual(self.e.eff_attack(), before * 0.8, delta=0.5)
        # Subito dopo non riscatta (non è passato il tempo di calma).
        self.e.incin_intim_until = -1.0
        self.match._deal_damage(self.u, self.e, 10.0)
        self.assertLess(self.e.incin_intim_until, self.match.time)

    def test_ring_bonus(self):
        self.level(8)
        self.u.incin_last_dealt = self.match.time   # niente Prepotenza
        self.tick(DT)
        self.assertEqual(self.u.incin_ring_n, 1)
        hp = self.e.hp
        self.match._deal_damage(self.u, self.e, 100.0)
        self.assertAlmostEqual(hp - self.e.hp, 105.0, delta=0.01)
        for k in range(4):
            spawn(self.world, FOE, Vec2(21.0 + k * 0.5, 49.0), 1)
        self.tick(DT)
        self.assertEqual(self.u.incin_ring_n, 3)

    # --- Q -----------------------------------------------------------------------
    def test_double_kick_two_hits(self):
        hp = self.e.hp
        self.cast("Q", 23.0, 47.5)
        first = hp - self.e.hp
        self.assertGreater(first, 0)
        self.tick(0.3)
        self.assertGreater(hp - self.e.hp, first * 1.6)

    def test_cross_chop_and_fang(self):
        self.level(5)
        self.choose("Q", 1)   # Incrocolpo
        hp = self.e.hp
        self.cast("Q", 23.0, 47.5)
        self.assertGreater(hp - self.e.hp, 0)
        self.choose("Q", 0)   # Fuocodenti
        hp = self.e.hp
        self.cast("Q", 23.0, 47.5)
        self.assertGreater(hp - self.e.hp, 0)

    # --- W -----------------------------------------------------------------------
    def test_bully_taunts_and_buffs(self):
        a0 = self.e.eff_attack()
        self.cast("W", 23.0, 47.5)
        self.tick(DT)
        self.assertGreater(self.e.taunt_until, self.match.time)
        self.assertEqual(self.e.taunt_src, self.u.id)
        self.assertAlmostEqual(self.e.eff_attack(), a0 * 1.1, delta=0.5)
        self.assertGreater(self.u.incin_bully_until, self.match.time)

    def test_taunt_upgrade_no_foe_bonus(self):
        self.level(6)
        self.choose("W", 1)   # Provocazione
        self.cast("W", 23.0, 47.5)
        self.assertGreater(self.e.taunt_until, self.match.time + 2.0)
        self.assertLess(self.e.incin_bully_until, self.match.time)

    def test_bulkup(self):
        self.level(6)
        self.choose("W", 0)   # Granfisico
        self.cast("W", 23.0, 47.5)
        self.assertAlmostEqual(self.u.atk_mult, 1.2)
        self.assertGreater(self.u.def_buff_until, self.match.time)
        self.assertGreater(self.e.taunt_until, self.match.time)

    # --- E -----------------------------------------------------------------------
    def test_ropes_drag_and_slam(self):
        self.wall_col(25)
        hp = self.e.hp
        self.cast("E", 30.0, 47.5)
        self.tick(0.5)
        self.assertGreater(hp - self.e.hp, 0)
        self.assertGreater(self.e.stun_until, self.match.time + 0.3)
        self.assertLess(self.e.pos.x, 25.0)

    def test_ropes_bounce_empowers(self):
        self.e.pos = Vec2(20.5, 40.0)   # fuori dal percorso
        self.wall_col(23)
        self.cast("E", 30.0, 47.5)
        self.tick(0.25)
        self.assertGreater(self.u.incin_rope_until, self.match.time)
        self.tick(0.6)
        self.assertLess(self.u.pos.x, 20.0)   # tornato indietro
        self.assertFalse(self.match.incin_runs)
        # Prossimo Q potenziato: stordisce.
        self.e.pos = Vec2(self.u.pos.x + 1.2, self.u.pos.y)
        self.cast("Q", self.e.pos.x + 1, self.e.pos.y)
        self.assertGreater(self.e.stun_until, self.match.time)
        self.assertLess(self.u.incin_rope_until, self.match.time)

    def test_momentum_halves_cooldown(self):
        self.level(7)
        self.choose("E", 1)   # Slancio
        self.e.pos = Vec2(20.5, 40.0)
        self.wall_col(23)
        self.cast("E", 30.0, 47.5)
        cd0 = self.u.moveset["E"].cooldown_remaining
        self.tick(0.25)
        self.assertLess(self.u.moveset["E"].cooldown_remaining, cd0 * 0.55)

    def test_double_bounce(self):
        self.level(7)
        self.choose("E", 0)   # Doppio Rimbalzo
        self.e.pos = Vec2(20.5, 40.0)
        self.wall_col(23)
        self.wall_col(17)
        self.cast("E", 30.0, 47.5)
        self.tick(1.2)
        self.assertGreater(self.u.pos.x, 19.0)   # secondo rimbalzo verso destra

    # --- R -----------------------------------------------------------------------
    def test_lariat(self):
        self.level(8)
        self.choose("R", 0)
        hp = self.e.hp
        self.cast("R", 20.5, 47.5)
        self.tick(DT)
        self.assertTrue(self.match._cc_immune(self.u))
        self.tick(3.1)
        self.assertGreater(hp - self.e.hp, 0)
        self.assertLess(self.u.incin_lariat_until, self.match.time)

    def test_lariat_ignores_def_buff(self):
        self.level(8)
        self.choose("R", 0)
        mv = self.u.moveset["R"].chosen
        random.seed(1)
        hp = self.e.hp
        self.match._hit(self.u, mv, 1, self.e)
        plain = hp - self.e.hp
        self.match._apply_def_buff(self.e, 2.0, 5.0)
        self.match._update_status(0)
        hp = self.e.hp
        self.match._hit(self.u, mv, 1, self.e)
        self.assertAlmostEqual(hp - self.e.hp, plain, delta=plain * 0.02)

    def test_champion_grab_wall(self):
        self.level(8)
        self.choose("R", 1)
        self.wall_col(26)
        other = spawn(self.world, FOE, Vec2(24.0, 47.5), 1)
        other.max_hp = other.hp = 50000.0
        hp = self.e.hp
        self.cast("R", 30.0, 47.5)
        self.tick(1.0)
        self.assertGreater(hp - self.e.hp, 0)
        self.assertGreater(self.e.stun_until, self.match.time + 0.4)
        self.assertLess(other.hp, other.max_hp)
        self.assertGreater(other.airborne_until, 0)

    def test_champion_grab_needs_target(self):
        self.level(8)
        self.choose("R", 1)
        self.e.pos = Vec2(30.0, 47.5)
        self.cast("R", 30.0, 47.5)
        self.assertEqual(self.u.moveset["R"].cooldown_remaining, 0.0)


if __name__ == "__main__":
    unittest.main()
