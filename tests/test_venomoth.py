import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.basic_attack import is_melee
from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.moves import Move
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.venomoth import VENOM_DUR, VENOM_MAX
from engine.world import World

DT = 1 / 30
VEN = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "venonat.json"))
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


class TestVenomoth(unittest.TestCase):
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
        self.u = spawn(self.world, VEN, Vec2(20.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(24.5, 47.5), 1)
        self.f = spawn(self.world, FOE, Vec2(30.5, 52.5), 1)
        for x in (self.e, self.f):
            x.max_hp = x.hp = 50000.0
        for x in (self.u, self.e, self.f):
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
            self.match._update_moth(DT)
            self.match._update_status(DT)

    def aa(self, tgt):
        snap = self.match._aa_snapshot(self.u, tgt)
        self.match._aa_land(self.u, tgt, snap)

    @staticmethod
    def lost(u):
        return u.max_hp - u.hp

    def make_steel(self, p):
        p.types = ["Steel"]

    # --- dati -----------------------------------------------------------------
    def test_evolution_types_and_stats(self):
        self.assertEqual(self.u.types, ["Bug", "Poison"])
        self.assertEqual(self.u.passive_id, "scaglievelenose")
        self.level(4)
        self.assertEqual(self.u.name, "Venonat")   # al liv.4 nessuna evoluzione
        self.level(8)
        self.assertEqual(self.u.name, "Venomoth")
        self.assertEqual(self.u.types, ["Bug", "Poison"])
        self.assertEqual(self.u.passive_id, "lentifume")
        self.assertEqual(self.u.base_stats.sp_attack, 90)
        self.assertEqual(self.u.base_stats.speed, 90)

    def test_move_ids_are_own(self):
        ids = []
        for slot, sd in VEN.moves.items():
            for mv in ([sd.get("base")] if sd.get("base") else []) + list(sd.get("upgrades", [])):
                ids.append(mv["id"] if isinstance(mv, dict) else mv.id)
        self.assertTrue(all(i.startswith("venomoth_") for i in ids), ids)

    # --- Scaglie Velenose -----------------------------------------------------------
    def test_aa_is_special_and_ranged(self):
        power, magic = self.match._aa_power(self.u)
        self.assertTrue(magic)
        self.assertFalse(is_melee(self.u))
        self.assertGreaterEqual(self.u.attack_range, 4.5)

    def test_item_attack_becomes_sp_attack(self):
        self.u.items = ["poison_barb"]
        self.match._apply_items(self.u)
        self.assertNotIn("attack", self.u.item_bonus)
        self.assertGreater(self.u.item_bonus.get("sp_attack", 0.0), 0.0)
        self.assertGreater(self.u.as_bonus, 0.0)   # la velocità d'attacco resta

    def test_aa_stacks_cap_refresh_and_expire(self):
        for _ in range(8):
            self.aa(self.e)
        self.assertEqual(self.e.venom_stacks, VENOM_MAX)
        hp0 = self.e.hp
        self.tick(1.0)
        self.assertLess(self.e.hp, hp0)              # danno nel tempo
        self.tick(VENOM_DUR - 2.0)
        self.aa(self.e)                              # si rinnovano a ogni colpo
        self.tick(2.5)
        self.assertEqual(self.e.venom_stacks, VENOM_MAX)
        self.tick(VENOM_DUR)
        self.assertEqual(self.e.venom_stacks, 0)

    def test_dot_scales_with_stacks(self):
        self.aa(self.e)
        h = self.e.hp
        self.tick(1.0)
        one = h - self.e.hp
        for _ in range(5):
            self.aa(self.e)
        h = self.e.hp
        self.tick(1.0)
        six = h - self.e.hp
        self.assertAlmostEqual(six / one, 6.0, delta=0.3)

    def test_stacks_on_minions_too(self):
        mn = self.world.spawn_minion(Vec2(23.5, 49.5), 1, "mid", [], (200, 60, 60))
        self.aa(mn)
        self.assertEqual(mn.venom_stacks, 1)

    def test_steel_immune_to_stacks_and_poison(self):
        self.make_steel(self.e)
        for _ in range(3):
            self.aa(self.e)
        self.assertEqual(self.e.venom_stacks, 0)
        self.match._apply_poison(self.e, self.u, 50.0, 3.0)
        self.assertLess(self.e.poison_until, self.match.time)

    def test_steel_immune_to_poison_moves(self):
        mv = Move("Q", 4, {"id": "t_sludge", "name": "Fango", "type": "Poison", "category": "special",
                   "shape": "projectile", "power": [100, 100, 100, 100], "ratio": 0.5,
                   "cooldown": [5, 5, 5, 5], "range": 6, "radius": 0.5,
                   "effects": {"slow": {"mult": 0.5, "duration": 2.0}}})
        self.make_steel(self.e)
        self.match._hit(self.u, mv, 1, self.e)
        self.assertEqual(self.lost(self.e), 0.0)
        self.assertLess(self.e.slow_until, self.match.time)
        self.match._hit(self.u, mv, 1, self.f)       # gli altri tipi la subiscono
        self.assertGreater(self.lost(self.f), 0.0)

    def test_venom_does_not_wake(self):
        for _ in range(3):
            self.aa(self.e)
        self.match._apply_sleep(self.e, 2.0)
        self.tick(1.0)
        self.assertGreater(self.e.sleep_until, self.match.time)

    # --- Lentifume' -------------------------------------------------------------------
    def test_tinted_lens(self):
        self.assertAlmostEqual(self.match._moth_eff(self.u, 0.8), 0.8)
        self.level(8)
        self.assertAlmostEqual(self.match._moth_eff(self.u, 0.8), 1.0)
        self.assertAlmostEqual(self.match._moth_eff(self.u, 0.64), 1.0)
        self.assertAlmostEqual(self.match._moth_eff(self.u, 1.25), 1.25)

    # --- Q ---------------------------------------------------------------------------------
    def test_psybeam_line_hits_all(self):
        self.f.pos = Vec2(27.5, 47.5)
        self.cast("Q", 30.5, 47.5)
        self.assertGreater(self.lost(self.e), 0)
        self.assertGreater(self.lost(self.f), 0)

    def test_psybeam_confuse_chance(self):
        n = 0
        for _ in range(60):
            self.e.confuse_until = -1.0
            self.cast("Q", 30.5, 47.5)
            n += self.e.confuse_until > self.match.time
        self.assertTrue(8 <= n <= 30, n)

    def test_bugbuzz_spdef_down(self):
        self.level(5)
        self.choose("Q", 0)
        self.assertEqual(self.u.moveset["Q"].chosen.id, "venomoth_bugbuzz")
        self.assertEqual(self.u.moveset["Q"].chosen.type, "Bug")
        sd = self.e.eff_sp_defense()
        self.cast("Q", 30.5, 47.5)
        self.assertGreater(self.lost(self.e), 0)
        self.tick(0.1)
        self.assertAlmostEqual(self.e.eff_sp_defense(), sd * 0.8, delta=0.5)
        self.tick(4.1)
        self.assertAlmostEqual(self.e.eff_sp_defense(), sd, delta=0.5)

    def test_silverwind_buff_only_on_pokemon(self):
        self.level(5)
        self.choose("Q", 1)
        self.e.pos = Vec2(40.5, 30.5)   # fuori dalla linea
        spa = self.u.eff_sp_defense()
        self.cast("Q", 28.5, 47.5)
        self.assertFalse(self.u.silver_active)
        self.e.pos = Vec2(24.5, 47.5)
        self.cast("Q", 28.5, 47.5)
        self.assertTrue(self.u.silver_active)
        self.assertAlmostEqual(self.u.eff_sp_defense(), spa * 1.1, delta=0.5)
        self.tick(2.6)
        self.assertFalse(self.u.silver_active)

    # --- W ---------------------------------------------------------------------------------
    def test_poisonpowder_cloud_stacks(self):
        self.cast("W", 24.5, 47.5)
        self.assertEqual(len(self.match.powder_clouds), 1)
        self.tick(0.05)
        self.assertEqual(self.e.venom_stacks, 1)
        self.tick(2.1)
        self.assertEqual(self.e.venom_stacks, 3)
        self.tick(1.2)
        self.assertEqual(self.match.powder_clouds, [])
        self.assertEqual(self.e.venom_stacks, 3)   # gli accumuli restano

    def test_stunspore_roots_on_spawn(self):
        self.level(6)
        self.choose("W", 0)
        self.cast("W", 24.5, 47.5)
        self.assertGreater(self.e.root_until, self.match.time + 0.9)
        self.tick(0.05)
        self.assertEqual(self.e.venom_stacks, 1)

    def test_sleeppowder_after_one_second_once(self):
        self.level(6)
        self.choose("W", 1)
        self.cast("W", 24.5, 47.5)
        self.tick(0.5)
        self.assertLess(self.e.sleep_until, self.match.time)
        self.tick(0.6)
        self.assertGreater(self.e.sleep_until, self.match.time)
        self.e.sleep_until = -1.0
        self.tick(1.0)
        self.assertLess(self.e.sleep_until, self.match.time)   # una volta per nube

    # --- E ---------------------------------------------------------------------------------
    def test_gust_dashes_back_and_pushes(self):
        self.e.pos = Vec2(22.0, 47.5)
        self.cast("E", 30.5, 47.5)
        self.assertAlmostEqual(self.u.pos.x, 16.5, delta=0.2)
        self.assertAlmostEqual(self.e.pos.x, 24.0, delta=0.2)
        self.assertAlmostEqual(self.f.pos.x, 30.5)   # lontano: resta

    def test_doublegust_two_charges(self):
        self.level(7)
        self.choose("E", 0)
        ms = self.u.moveset["E"]
        self.assertEqual(ms.chosen.charges, 2)
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(self.u, "E", 30.5, 47.5)
        ms.cooldown_remaining = 0.0
        x1 = self.u.pos.x
        self.match._cast(self.u, "E", 30.5, 47.5)
        self.assertLess(self.u.pos.x, x1 - 3.0)
        self.assertLess(ms.charges_cur, 0.5)

    def test_powdershield(self):
        self.level(7)
        self.choose("E", 1)
        self.cast("E", 30.5, 47.5)
        self.assertGreater(self.u.shield, self.u.max_hp * 0.14)
        self.match._apply_stun(self.u, 1.0)
        self.assertLess(self.u.stun_until, self.match.time)
        self.tick(1.6)
        self.match._apply_stun(self.u, 1.0)
        self.assertGreater(self.u.stun_until, self.match.time)

    # --- R ---------------------------------------------------------------------------------
    def test_quiverdance(self):
        self.level(8)
        self.choose("R", 0)
        spd = self.u.eff_sp_defense()
        aps = self.match._eff_attack_speed(self.u)
        self.cast("R", self.u.pos.x, self.u.pos.y)
        self.tick(0.1)
        self.assertAlmostEqual(self.u.eff_sp_defense(), spd * 1.3, delta=0.5)
        self.assertGreater(self.match._eff_attack_speed(self.u), aps * 1.2)
        self.aa(self.e)
        self.assertEqual(self.e.venom_stacks, 2)
        self.tick(6.0)
        self.assertFalse(self.u.quiver_active)
        self.aa(self.f)
        self.assertEqual(self.f.venom_stacks, 1)

    def test_powderstorm(self):
        self.level(8)
        self.choose("R", 1)
        self.f.pos = Vec2(25.5, 49.5)
        self.cast("R", 24.5, 47.5)
        slept = {self.e.id: 0, self.f.id: 0}
        for _ in range(5 * 30 + 5):
            for t in (self.e, self.f):
                if t.sleep_until > self.match.time + 0.95:
                    slept[t.id] += 1
                    t.sleep_until = -1.0
            self.tick(DT)
        self.assertEqual(self.match.powder_clouds, [])
        self.assertTrue(all(v <= 1 for v in slept.values()), slept)
        affected = sum(1 for t in (self.e, self.f)
                       if t.venom_stacks or slept[t.id] or t.root_until > 0)
        self.assertEqual(affected, 2)


if __name__ == "__main__":
    unittest.main()
