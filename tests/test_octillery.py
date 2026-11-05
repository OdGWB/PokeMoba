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
from engine.octillery import LOCK_CD, LOCK_DUR, SNIPER_CRIT
from engine.stats import CRIT_MULT, CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
REM = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "remoraid.json"))
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


class TestOctillery(unittest.TestCase):
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
        self.u = spawn(self.world, REM, Vec2(20.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(24.5, 47.5), 1)
        self.f = spawn(self.world, FOE, Vec2(25.5, 47.5), 1)
        for x in (self.e, self.f):
            x.max_hp = x.hp = 50000.0
        for x in (self.u, self.e, self.f):
            x.crit = 0.0
        self.u.octi_lock_ready_at = 1e9   # Prendimira spenta salvo nei test dedicati
        self.match._update_regen = lambda dt: None

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
        if ms.charges_cur >= 0:
            ms.charges_cur = max(ms.charges_cur, 1.0)
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(self.u, slot, x, y)

    def tick(self, sec):
        for _ in range(int(round(sec / DT))):
            self.match.time += DT
            self.match._combat_hash.rebuild(self.world.combatants())
            self.match._update_octi(DT)
            self.match._update_status(DT)

    def aa(self, tgt):
        snap = self.match._aa_snapshot(self.u, tgt)
        self.match._octi_snap(self.u, tgt, snap)
        self.match._aa_land(self.u, tgt, snap)

    @staticmethod
    def lost(u):
        return u.max_hp - u.hp

    def reset_hp(self):
        for x in (self.e, self.f):
            x.hp = x.max_hp

    # --- dati ------------------------------------------------------------------
    def test_evolution_types_and_stats(self):
        self.assertEqual(self.u.types, ["Water"])
        self.assertEqual(self.u.passive_id, "cecchino")
        self.level(4)
        self.assertEqual(self.u.name, "Remoraid")   # al liv.4 nessuna evoluzione
        self.level(8)
        self.assertEqual(self.u.name, "Octillery")
        self.assertEqual(self.u.types, ["Water"])
        self.assertEqual(self.u.passive_id, "ventose")
        self.assertEqual(self.u.base_stats.attack, 105)
        self.assertEqual(self.u.base_stats.speed, 45)

    def test_move_ids_are_own_and_physical(self):
        for slot, sd in REM.moves.items():
            for mv in ([sd.get("base")] if sd.get("base") else []) + list(sd.get("upgrades", [])):
                self.assertTrue(mv["id"].startswith("octillery_"), mv["id"])
                self.assertIn(mv["category"], ("physical", "none"), mv["id"])

    def test_aa_physical_ranged_and_spa_items_become_attack(self):
        _, magic = self.match._aa_power(self.u)
        self.assertFalse(magic)
        self.assertFalse(is_melee(self.u))
        self.u.items = ["choice_specs"]
        self.match._apply_items(self.u)
        self.assertNotIn("sp_attack", self.u.item_bonus)
        self.assertGreater(self.u.item_bonus.get("attack", 0.0), 0.0)

    def test_ammo_swap_usable_at_level_1(self):
        self.assertEqual(self.u.level, 1)
        self.assertEqual(self.u.moveset["W"].rank, 1)   # grado gratuito
        self.assertTrue(self.u.moveset["W"].ready)
        self.assertEqual(self.u.ammo, "Water")
        self.match._cast(self.u, "W", 0, 0)
        self.assertEqual(self.u.ammo, "Ice")
        self.u.moveset["W"].cooldown_remaining = 0
        self.match._cast(self.u, "W", 0, 0)
        self.assertEqual(self.u.ammo, "Water")

    def test_third_ammo_at_level_6(self):
        self.level(6)
        self.choose("W", 0)   # Munizioni Fuoco
        seen = []
        for _ in range(3):
            self.cast("W", 0, 0)
            seen.append(self.u.ammo)
        self.assertEqual(seen, ["Ice", "Fire", "Water"])

    # --- munizioni ----------------------------------------------------------------
    def test_aa_uses_ammo_type(self):
        # Il bersaglio di prova e' Acqua: Erba superefficace, Acqua poco efficace (+STAB).
        self.aa(self.e)
        water = self.lost(self.e)
        self.reset_hp()
        self.u.ammo = "Grass"
        self.u.moveset["W"].chosen = self.u.moveset["W"].upgrades[1]   # Erba
        self.aa(self.e)
        grass = self.lost(self.e)
        self.assertGreater(grass, water)

    def test_ice_slows_and_hits_less(self):
        self.aa(self.e)
        water = self.lost(self.e)
        self.reset_hp()
        self.u.ammo = "Ice"
        self.aa(self.e)
        self.assertGreater(self.e.slow_until, self.match.time)
        self.assertAlmostEqual(self.e.slow_mult, 0.8, places=3)
        self.assertGreater(self.lost(self.e), 0.0)

    def test_fire_can_burn(self):
        self.u.moveset["W"].chosen = self.u.moveset["W"].upgrades[0]
        self.u.ammo = "Fire"
        random.seed(5)
        for _ in range(60):
            self.aa(self.e)
        self.assertGreater(self.e.burn_until, self.match.time)

    def test_grass_splashes_nearby(self):
        self.u.moveset["W"].chosen = self.u.moveset["W"].upgrades[1]
        self.u.ammo = "Grass"
        self.match._combat_hash.rebuild(self.world.combatants())
        self.aa(self.e)
        self.assertGreater(self.lost(self.f), 0.0)
        self.assertLess(self.lost(self.f), self.lost(self.e))

    def test_octillery_swap_bonus_first_hit(self):
        self.level(8)
        self.aa(self.e)
        base = self.lost(self.e)
        self.reset_hp()
        self.cast("W", 0, 0)
        self.cast("W", 0, 0)   # di nuovo Acqua, con il bonus
        self.assertTrue(self.u.ammo_boost)
        self.aa(self.e)
        self.assertAlmostEqual(self.lost(self.e) / base, 1.3, delta=0.02)
        self.assertFalse(self.u.ammo_boost)
        self.reset_hp()
        self.aa(self.e)
        self.assertAlmostEqual(self.lost(self.e), base, delta=1.0)

    # --- Cecchino / Prendimira -------------------------------------------------------
    def test_sniper_crit_multiplier(self):
        self.assertEqual(self.match._crit_mult(self.u, CRIT_MULT), SNIPER_CRIT)
        self.assertEqual(self.match._crit_mult(self.e, CRIT_MULT), CRIT_MULT)

    def test_lock_on_and_forced_crit(self):
        self.aa(self.e)
        plain = self.lost(self.e)
        self.reset_hp()
        self.u.octi_lock_ready_at = 0.0
        self.aa(self.e)
        self.assertGreater(self.e.octi_lock_until, self.match.time)
        self.assertEqual(self.e.octi_lock_by, self.u.id)
        self.assertAlmostEqual(self.u.octi_lock_ready_at, self.match.time + LOCK_CD)
        self.assertAlmostEqual(self.lost(self.e) / plain, SNIPER_CRIT, delta=0.03)
        # anche le mosse sono brutti colpi sul bersaglio agganciato
        self.assertEqual(self.match._octi_crit_bonus(self.u, self.e), 1.0)
        self.assertEqual(self.match._octi_crit_bonus(self.u, self.f), 0.0)
        self.match.time += LOCK_DUR + 0.1
        self.assertEqual(self.match._octi_crit_bonus(self.u, self.e), 0.0)

    def test_lock_ignores_bright_powder(self):
        self.e.items = ["bright_powder"]
        self.match._apply_items(self.e)
        self.e.octi_lock_until = self.match.time + 4
        self.e.octi_lock_by = self.u.id
        random.seed(1)
        for _ in range(30):
            self.aa(self.e)
        self.assertFalse(any(ev.get("kind") == "miss" for ev in self.match.fx_events))

    # --- Q -----------------------------------------------------------------------------
    def test_watergun_travels_and_hits_first(self):
        self.cast("Q", 30.5, 47.5)
        self.assertEqual(len(self.match.octi_shots), 1)
        self.tick(0.5)
        self.assertGreater(self.lost(self.e), 0.0)
        self.assertEqual(self.lost(self.f), 0.0)
        self.assertEqual(self.match.octi_shots, [])

    def test_watergun_takes_ammo_type(self):
        self.cast("Q", 30.5, 47.5)
        self.tick(0.5)
        water = self.lost(self.e)
        self.reset_hp()
        self.u.moveset["W"].chosen = self.u.moveset["W"].upgrades[1]
        self.u.ammo = "Grass"
        self.cast("Q", 30.5, 47.5)
        self.tick(0.5)
        self.assertGreater(self.lost(self.e), water)

    def test_burst_three_shots(self):
        self.cast("Q", 30.5, 47.5)
        self.tick(0.5)
        single = self.lost(self.e)
        self.reset_hp()
        self.u.moveset["Q"].chosen = self.u.moveset["Q"].upgrades[0]
        self.cast("Q", 30.5, 47.5)
        self.tick(0.8)
        self.assertAlmostEqual(self.lost(self.e) / single, 3 * 0.45, delta=0.05)

    def test_pierce_hits_all_in_line(self):
        self.u.moveset["Q"].chosen = self.u.moveset["Q"].upgrades[1]
        self.cast("Q", 30.5, 47.5)
        self.tick(1.0)
        self.assertGreater(self.lost(self.e), 0.0)
        self.assertGreater(self.lost(self.f), 0.0)

    # --- E -----------------------------------------------------------------------------
    def test_octazooka_blinds_and_jets_back(self):
        x0 = self.u.pos.x
        self.cast("E", 24.5, 47.5)
        self.assertGreater(self.e.blind_until, self.match.time)
        self.assertAlmostEqual(x0 - self.u.pos.x, 3.0, delta=0.1)
        self.assertGreater(self.lost(self.e), 0.0)

    def test_dense_ink_and_jet(self):
        self.u.moveset["E"].chosen = self.u.moveset["E"].upgrades[0]
        self.cast("E", 24.5, 47.5)
        self.assertGreater(self.e.blind_until, self.match.time + 2.5)
        self.assertGreater(self.e.slow_until, self.match.time)
        self.u.moveset["E"].chosen = self.u.moveset["E"].upgrades[1]
        self.u.pos = Vec2(30.5, 47.5)
        self.cast("E", 40.5, 47.5)
        self.assertAlmostEqual(30.5 - self.u.pos.x, 5.0, delta=0.1)

    # --- Ventose -------------------------------------------------------------------------
    def test_suction_halves_displacement(self):
        self.match._item_push(self.u, Vec2(1, 0), 2.0)
        self.assertAlmostEqual(self.u.pos.x, 22.5, delta=0.05)
        self.level(8)
        x = self.u.pos.x
        self.match._item_push(self.u, Vec2(1, 0), 2.0)
        self.assertAlmostEqual(self.u.pos.x - x, 1.0, delta=0.05)
        self.match._apply_airborne(self.u, 1.0)
        self.assertAlmostEqual(self.u.airborne_until - self.match.time, 0.5, delta=1e-6)

    # --- R -------------------------------------------------------------------------------
    def test_hyperbeam_pierces_and_recharges(self):
        self.level(8)
        self.choose("R", 0)
        self.cast("R", 40.5, 47.5)
        self.assertGreater(self.lost(self.e), 0.0)
        self.assertGreater(self.lost(self.f), 0.0)
        self.assertGreater(self.u.stun_until, self.match.time + 1.4)

    def test_grab_roots_both_and_fast_attacks(self):
        self.level(8)
        self.choose("R", 1)
        self.e.pos = Vec2(22.5, 47.5)
        self.cast("R", 22.5, 47.5)
        self.assertGreater(self.u.octi_grab_until, self.match.time)
        self.assertGreater(self.e.root_until, self.match.time + 1.9)
        self.assertGreater(self.u.root_until, self.match.time + 1.9)
        self.assertEqual(self.match._octi_as_bonus(self.u), 0.5)
        self.assertEqual(self.match._octi_crit_bonus(self.u, self.e), 1.0)
        # IA: attacca da solo l'afferrato
        self.match._update_ai(DT)
        self.assertEqual(self.u.target_id, self.e.id)

    def test_grab_needs_target_in_range(self):
        self.level(8)
        self.choose("R", 1)
        self.e.pos = Vec2(28.5, 47.5)
        self.f.pos = Vec2(29.5, 47.5)
        self.cast("R", 28.5, 47.5)
        self.assertLessEqual(self.u.octi_grab_until, self.match.time)
        self.assertEqual(self.u.moveset["R"].cooldown_remaining, 0.0)   # non spesa


if __name__ == "__main__":
    unittest.main()
