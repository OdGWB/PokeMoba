import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.mienshao import CALM, SWEET_MULT
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
MIEN = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "mienfoo.json"))
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


class TestMienshao(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        self.match.time = 100.0
        self.u = spawn(self.world, MIEN, Vec2(26.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(31.5, 47.5), 1)
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
        p = who or self.u
        ms = p.moveset[slot]
        ms.cooldown_remaining = 0.0
        ms.rank = max(1, ms.rank)
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(p, slot, x, y)

    def land(self):
        """Fa atterrare il balzo di Calcinvolo."""
        for _ in range(30):
            self.match.time += DT
            self.match._combat_hash.rebuild(self.world.combatants())
            self.match._update_mien(DT)
            if not self.match.mien_leaps:
                return

    def calm(self):
        """Nessun danno né azione da più di 4 s."""
        self.u.last_dealt_at = self.u.last_damaged_at = self.u.mien_act_at = -1e9

    def aa_once(self, tgt):
        """Un attacco base completo di Mienfoo su `tgt`; ritorna il danno."""
        u, m = self.u, self.match
        u.attack_timer = 0.0
        u.moving = False
        u.target_id = tgt.id
        m._pokemon_auto_attack(u)
        self.assertTrue(u.aa_active)
        m.time = u.aa_until + 0.001
        hp0 = tgt.hp
        m._pokemon_auto_attack(u)
        return hp0 - tgt.hp

    # --- evoluzione ------------------------------------------------------------------
    def test_evolves_and_gains_reach(self):
        self.assertAlmostEqual(self.u.attack_range, 1.5)
        self.level(8)
        self.assertEqual(self.u.name, "Mienshao")
        self.assertAlmostEqual(self.u.attack_range, 1.5 * 1.4, places=2)
        self.assertEqual(len(self.u.moveset["R"].upgrades), 2)

    # --- Maniche a Frusta: punto dolce ---------------------------------------------------
    def test_sweet_spot_aa(self):
        self.level(2)
        er = self.e.radius
        self.e.pos = Vec2(26.5 + er + 1.4, 47.5)      # bordo a 1,4 tile: punto dolce
        sweet = self.aa_once(self.e)
        self.e.pos = Vec2(26.5 + er + 0.55, 47.5)     # troppo vicino
        near = self.aa_once(self.e)
        self.assertAlmostEqual(sweet / near, SWEET_MULT, places=2)

    def test_sweet_spot_cuts_jumpkick_cd(self):
        self.level(2)
        ms = self.u.moveset["Q"]
        ms.cooldown_remaining = 5.0
        self.e.pos = Vec2(26.5 + self.e.radius + 1.4, 47.5)
        self.aa_once(self.e)
        self.assertAlmostEqual(ms.cooldown_remaining, 4.0)

    # --- Rigenergia ------------------------------------------------------------------------
    def test_regen_after_calm_stops_on_damage(self):
        self.u.hp = self.u.max_hp * 0.5
        self.calm()
        self.match._update_mien(1.0)
        self.assertTrue(self.u.mien_regen)
        self.assertAlmostEqual(self.u.hp, self.u.max_hp * 0.53, places=3)
        self.u.last_dealt_at = self.match.time      # infligge danno: si ferma
        hp = self.u.hp
        self.match._update_mien(1.0)
        self.assertFalse(self.u.mien_regen)
        self.assertEqual(self.u.hp, hp)

    # --- Q: Calcinvolo ---------------------------------------------------------------------
    def test_jumpkick_fixed_distance_hits(self):
        self.level(2)
        hp0 = self.e.hp
        self.cast("Q", 27.5, 47.5)          # mira vicino: il balzo è comunque di 5 tile
        self.land()
        self.assertAlmostEqual(self.u.pos.x, 31.5, places=1)
        self.assertLess(self.e.hp, hp0)
        self.assertAlmostEqual(self.u.hp, self.u.max_hp)

    def test_jumpkick_miss_crashes(self):
        self.level(2)
        self.cast("Q", 26.5, 40.0)          # verso l'alto: nessuno all'atterraggio
        self.land()
        self.assertAlmostEqual(self.u.hp, self.u.max_hp * 0.85, places=3)
        self.assertGreater(self.u.stun_until, self.match.time + 0.4)

    def test_reckless_and_controlled(self):
        self.level(5)
        self.choose("Q", 0)                 # Temerarietà: 30%
        self.cast("Q", 26.5, 40.0)
        self.land()
        self.assertAlmostEqual(self.u.hp, self.u.max_hp * 0.70, places=3)
        self.u.hp = self.u.max_hp
        self.u.pos = Vec2(26.5, 47.5)
        self.u.stun_until = -1.0
        self.u.moveset["Q"].upgrade_index = None
        self.choose("Q", 1)                 # Calcio Controllato: niente autodanno, ricarica ×2
        self.cast("Q", 26.5, 40.0)
        cd = self.u.moveset["Q"].cooldown_remaining
        self.land()
        self.assertAlmostEqual(self.u.hp, self.u.max_hp)
        self.assertLessEqual(self.u.stun_until, self.match.time)
        self.assertGreater(self.u.moveset["Q"].cooldown_remaining, cd * 1.8)

    # --- W: Individua ----------------------------------------------------------------------
    def test_detect_parries_and_rewards(self):
        self.level(3)
        self.u.moveset["Q"].cooldown_remaining = 6.0
        self.cast("W", 26.5, 47.5)
        fmv = self.e.moveset["Q"].chosen
        self.match._hit(self.e, fmv, 1, self.u)
        self.assertAlmostEqual(self.u.hp, self.u.max_hp)
        self.assertEqual(self.u.moveset["Q"].cooldown_remaining, 0.0)
        self.assertGreater(self.u.mien_crit_until, self.match.time)
        self.match._hit(self.e, fmv, 1, self.u)      # la parata è già spesa
        self.assertLess(self.u.hp, self.u.max_hp)
        # attacco base: brutto colpo garantito
        self.e.pos = Vec2(26.5 + self.e.radius + 0.55, 47.5)
        crit = self.aa_once(self.e)
        self.assertLess(self.u.mien_crit_until, self.match.time)
        normal = self.aa_once(self.e)
        self.assertGreater(crit, normal * 1.3)

    def test_detect_window_halves(self):
        self.level(3)
        self.cast("W", 26.5, 47.5)
        self.assertAlmostEqual(self.u.parry_until - self.match.time, 0.5)
        self.match.time += 4.0
        self.cast("W", 26.5, 47.5)
        self.assertAlmostEqual(self.u.parry_until - self.match.time, 0.25)
        self.match.time += 4.0
        self.cast("W", 26.5, 47.5)
        self.assertAlmostEqual(self.u.parry_until - self.match.time, 0.15)
        self.match.time += 6.5
        self.cast("W", 26.5, 47.5)
        self.assertAlmostEqual(self.u.parry_until - self.match.time, 0.5)

    def test_counter_pushes_melee(self):
        self.level(6)
        self.choose("W", 0)
        self.e.pos = Vec2(27.6, 47.5)
        self.cast("W", 26.5, 47.5)
        self.match._hit(self.e, self.e.moveset["Q"].chosen, 1, self.u)
        self.assertAlmostEqual(self.e.pos.x, 30.6, places=1)

    def test_quick_guard_blocks_projectiles_on_allies(self):
        self.level(6)
        self.choose("W", 1)
        ally = spawn(self.world, FOE, Vec2(28.5, 47.5), 0)
        self.cast("W", 26.5, 47.5)
        self.match._update_mien(0.0)
        self.match._hit(self.e, self.e.moveset["Q"].chosen, 1, ally)   # Pistolacqua
        self.assertAlmostEqual(ally.hp, ally.max_hp)
        hb = self.e.moveset["E"].chosen                                   # Bottintesta (scatto)
        self.match._hit(self.e, hb, 1, ally)
        self.assertLess(ally.hp, ally.max_hp)

    # --- E: Bruciapelo ---------------------------------------------------------------------
    def test_fakeout_stuns_only_after_calm(self):
        self.level(3)
        self.e.pos = Vec2(28.0, 47.5)
        self.calm()
        self.match._update_mien(0.0)
        self.assertTrue(self.u.fakeout_ready)
        hp0 = self.e.hp
        self.cast("E", 28.0, 47.5)
        full = hp0 - self.e.hp
        self.assertGreater(self.e.stun_until, self.match.time + 0.9)
        self.e.stun_until = -1.0
        self.match.time += 1.0
        hp0 = self.e.hp
        self.cast("E", 28.0, 47.5)
        weak = hp0 - self.e.hp
        self.assertLessEqual(self.e.stun_until, self.match.time)
        self.assertAlmostEqual(weak / full, 0.4, places=2)

    def test_fakeout_sweet_spot(self):
        self.level(3)
        self.calm()
        self.e.pos = Vec2(26.5 + self.e.radius + 2.0, 47.5)   # bordo a 2 tile su 2,2
        hp0 = self.e.hp
        self.cast("E", self.e.pos.x, 47.5)
        far = hp0 - self.e.hp
        self.calm()
        self.e.pos = Vec2(26.5 + self.e.radius + 0.5, 47.5)
        hp0 = self.e.hp
        self.cast("E", self.e.pos.x, 47.5)
        near = hp0 - self.e.hp
        self.assertAlmostEqual(far / near, SWEET_MULT, places=2)

    def test_feint_locks_items(self):
        self.level(7)
        self.choose("E", 0)
        self.e.items = ["leftovers"]
        self.e.pos = Vec2(28.0, 47.5)
        hp0 = self.e.hp
        self.cast("E", 28.0, 47.5)
        self.assertLess(self.e.hp, hp0)
        self.assertLessEqual(self.e.stun_until, self.match.time)
        self.assertEqual(self.match._fx_items(self.e), ())
        self.assertEqual(self.e.items, ["leftovers"])
        self.match.time += 3.1
        self.assertEqual(self.match._fx_items(self.e), ["leftovers"])

    def test_double_fakeout(self):
        self.level(7)
        self.choose("E", 1)
        self.e.pos = Vec2(28.0, 47.5)
        self.calm()
        self.cast("E", 28.0, 47.5)
        ms = self.u.moveset["E"]
        self.assertTrue(ms.ready)
        self.e.stun_until = -1.0
        self.match.time += 0.5
        self.match._cast(self.u, "E", 28.0, 47.5)    # rilancio: stordimento pieno
        self.assertGreater(self.e.stun_until, self.match.time + 0.9)
        self.assertFalse(ms.ready)

    # --- R ---------------------------------------------------------------------------------
    def test_sleeve_dance_finale(self):
        self.level(8)
        self.choose("R", 0)
        self.e.pos = Vec2(31.5, 47.5)
        self.cast("R", 26.5, 47.5)
        self.cast("Q", 31.5, 47.5)
        self.land()
        self.assertEqual(self.u.dance_seq, "Q")
        self.assertTrue(self.u.moveset["E"].ready)
        self.calm()
        self.match._cast(self.u, "E", 33.0, 47.5)
        self.assertEqual(self.u.dance_seq, "QE")
        hp0 = self.e.hp
        self.match._cast(self.u, "W", 31.5, 47.5)     # terza mossa: colpo finale
        self.assertLess(self.e.hp, hp0)
        self.assertLess(self.u.dance_until, self.match.time)

    def test_sleeve_dance_breaks_on_repeat(self):
        self.level(8)
        self.choose("R", 0)
        self.cast("R", 26.5, 47.5)
        self.cast("W", 26.5, 47.5)
        self.cast("W", 26.5, 47.5)
        self.assertLess(self.u.dance_until, self.match.time)

    def test_reversal_scales_with_missing_hp(self):
        self.level(8)
        self.choose("R", 1)
        mv = self.u.moveset["R"].chosen
        self.assertAlmostEqual(self.match._reversal_mult(self.u, mv), 1.0)
        self.u.hp = self.u.max_hp * 0.10
        self.assertAlmostEqual(self.match._reversal_mult(self.u, mv), 3.0)
        self.u.hp = self.u.max_hp * 0.575
        self.assertAlmostEqual(self.match._reversal_mult(self.u, mv), 2.0)
        self.e.pos = Vec2(28.0, 47.5)
        hp0 = self.e.hp
        self.cast("R", 28.0, 47.5)
        self.assertLess(self.e.hp, hp0)


if __name__ == "__main__":
    unittest.main()
