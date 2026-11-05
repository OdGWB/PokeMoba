import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
SCY = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "scyther.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))


def spawn(world, d, pos, team):
    p = world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=d.color,
                            speed=d.base_speed, is_bot=False, types=d.types,
                            base_stats=d.base_stats, moves=d.moves, evolutions=d.evolutions,
                            role=d.role, passive=d.passive, attack_range=d.attack_range,
                            attack_cooldown=d.attack_cooldown, attack_fx=d.attack_fx)
    p.radius = d.radius
    p.spawn_pos = Vec2(pos.x, pos.y)   # negozio a portata
    p.order = "idle"
    return p


class TestScyther(unittest.TestCase):
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
        self.u = spawn(self.world, SCY, Vec2(20.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(22.0, 47.5), 1)
        self.e.max_hp = self.e.hp = 50000.0
        self.match._update_regen = lambda dt: None
        self.u.gold = 99999
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
            self.match._update_scy(DT)
            self.match._update_status(DT)

    def lost(self, before):
        return before - self.e.hp

    def buy(self, iid):
        self.assertTrue(self.match.shop_buy(self.u, iid), iid)
        self.match._update_evolution(0)
        self.rank_all()

    # --- dati e evoluzione -------------------------------------------------------
    def test_types_and_ids(self):
        self.assertEqual(self.u.types, ["Bug", "Flying"])
        self.assertEqual(self.u.passive_id, "cuordeciso")
        ids = []
        for sd in SCY.moves.values():
            ids += [m["id"] for m in ([sd["base"]] if sd.get("base") else []) + sd.get("upgrades", [])]
        for st in SCY.evolutions:
            for sd in st.get("moves", {}).values():
                ids += [m["id"] for m in ([sd["base"]] if sd.get("base") else []) + sd.get("upgrades", [])]
        for i in ids:
            self.assertTrue(i.split("_")[0] in ("scyther", "scizor", "kleavor"), i)
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_evolution_without_item(self):
        self.level(4)
        self.assertEqual(self.u.name, "Scyther")
        self.level(9)
        self.assertEqual(self.u.name, "Scyther")
        self.assertIsNone(self.u.moveset.get("R"))

    def test_metal_coat_gives_scizor_at_8(self):
        self.buy("metal_coat")
        self.assertEqual(self.u.name, "Scyther")   # liv.1: aspetta il liv.8
        self.level(8)
        self.assertEqual(self.u.name, "Scizor")
        self.assertEqual(self.u.types, ["Bug", "Steel"])
        self.assertEqual(self.u.passive_id, "tecnico")
        self.assertEqual(self.u.moveset["Q"].chosen.id, "scizor_bulletpunch")
        self.assertIn("R", self.u.pending_choices)

    def test_buy_after_level_8_evolves_at_once(self):
        self.level(8)
        self.assertEqual(self.u.name, "Scyther")
        self.buy("black_augurite")
        self.assertEqual(self.u.name, "Kleavor")
        self.assertEqual(self.u.types, ["Bug", "Rock"])
        self.assertEqual(self.u.moveset["Q"].chosen.id, "kleavor_stoneaxe")

    def test_first_bought_wins_and_selling_after_is_harmless(self):
        self.buy("black_augurite")
        self.buy("metal_coat")
        self.level(8)
        self.assertEqual(self.u.name, "Kleavor")
        self.assertTrue(self.match.shop_sell(self.u, self.u.items.index("black_augurite")))
        self.match._update_evolution(0)
        self.assertEqual(self.u.name, "Kleavor")

    def test_upgrades_kept_and_q_rank_kept(self):
        self.level(7)
        self.assertEqual(self.u.moveset["Q"].chosen.id, "scyther_furycutter2")   # auto al liv.5
        self.choose("W", 1)
        self.choose("E", 0)
        self.level(8)
        qrank = self.u.moveset["Q"].rank
        self.buy("metal_coat")
        self.assertEqual(self.u.moveset["W"].chosen.id, "scyther_doublehit")
        self.assertEqual(self.u.moveset["E"].chosen.id, "scyther_uturn")
        self.assertEqual(self.u.moveset["Q"].rank, qrank)

    def test_item_stats(self):
        cat = self.match.item_catalog
        mc, ba = cat.get("metal_coat"), cat.get("black_augurite")
        self.assertEqual((mc.price, sorted(mc.build_from)), (1000, ["carbos", "iron"]))
        self.assertEqual(mc.stats, {"attack": 10, "defense": 20, "attack_speed": 0.10})
        self.assertEqual((ba.price, sorted(ba.build_from)), (1000, ["hp_up", "protein"]))
        self.assertEqual(ba.stats, {"attack": 15, "hp": 150})
        for it in cat.items.values():
            self.assertNotIn("metal_coat", it.build_from)
            self.assertNotIn("black_augurite", it.build_from)

    def test_augurite_tower_bonus(self):
        tower = next(s for s in self.world.structures() if s.kind == "tower" and s.team == 1)
        m = self.match
        self.assertEqual(m._item_struct_mult(self.u, tower), 1.0)
        self.u.items.append("black_augurite")
        self.assertAlmostEqual(m._item_struct_mult(self.u, tower), 1.2)
        self.assertEqual(m._item_struct_mult(self.u, self.e), 1.0)

    # --- Scyther -------------------------------------------------------------------
    def test_fury_cutter_ramps(self):
        dmg = []
        for _ in range(6):
            hp = self.e.hp
            random.seed(1)
            self.u.crit = 0.0
            self.cast("Q", 22.0, 47.5)
            dmg.append(self.lost(hp))
            self.match.time += 1.0
        self.assertAlmostEqual(dmg[1] / dmg[0], 1.25, delta=0.02)
        self.assertAlmostEqual(dmg[4] / dmg[0], 1.25 ** 4, delta=0.05)
        self.assertAlmostEqual(dmg[5] / dmg[0], 1.25 ** 4, delta=0.05)   # tetto 4
        self.match.time += 3.5   # finestra scaduta
        hp = self.e.hp
        self.cast("Q", 22.0, 47.5)
        self.assertAlmostEqual(self.lost(hp), dmg[0], delta=dmg[0] * 0.02)

    def test_fury_miss_resets(self):
        self.cast("Q", 22.0, 47.5)
        self.assertEqual(self.u.scy_fury_stacks, 1)
        self.cast("Q", 18.0, 47.5)   # dalla parte opposta: a vuoto
        self.assertEqual(self.u.scy_fury_stacks, 0)

    def test_focus_energy_crit(self):
        self.cast("W", 0, 0)
        self.assertAlmostEqual(self.match._scy_crit_bonus(self.u), 0.4)
        self.tick(4.1)
        self.assertEqual(self.match._scy_crit_bonus(self.u), 0.0)

    def test_double_hit_next_aa(self):
        self.level(6)
        self.choose("W", 1)
        self.cast("W", 0, 0)
        self.assertTrue(self.u.scy_double_ready)
        self.match._combat_hash.rebuild(self.world.combatants())
        hp = self.e.hp
        self.match._aa_land(self.u, self.e, self.match._aa_snapshot(self.u, self.e))
        one = self.lost(hp)
        self.tick(0.3)
        self.assertGreater(self.lost(hp), one * 1.5)
        self.assertFalse(self.u.scy_double_ready)

    def test_wing_attack_stops_on_first_foe(self):
        self.e.pos = Vec2(23.0, 47.5)
        hp = self.e.hp
        self.cast("E", 30.0, 47.5)
        self.assertLess(self.u.pos.x, 23.0)
        self.assertGreater(self.lost(hp), 0)

    def test_uturn_goes_back(self):
        self.level(7)
        self.choose("E", 0)
        self.e.pos = Vec2(23.0, 47.5)
        self.cast("E", 30.0, 47.5)
        self.assertLess(self.u.pos.x, 20.0)   # ~22.4 - 3

    def test_double_dash_has_two_charges(self):
        self.level(7)
        self.choose("E", 1)
        self.assertEqual(self.u.moveset["E"].chosen.charges, 2)

    def test_resolve_speed_after_stun(self):
        self.match._apply_stun(self.u, 0.5)
        self.tick(0.2)
        base = self.u.speed
        self.assertEqual(base, 0.0)
        self.tick(0.5)
        self.assertGreater(self.u.scy_heart_until, self.match.time)
        self.assertAlmostEqual(self.match._scy_speed_mult(self.u), 1.3)
        self.tick(2.1)
        self.assertEqual(self.match._scy_speed_mult(self.u), 1.0)

    # --- Scizor --------------------------------------------------------------------
    def to_scizor(self):
        self.level(8)
        self.buy("metal_coat")
        self.assertEqual(self.u.name, "Scizor")

    def test_technician_bullet_punch(self):
        self.to_scizor()
        q = self.u.moveset["Q"]
        self.assertAlmostEqual(self.match._scy_move_mult(self.u, q.chosen, q.rank), 1.4)
        w = self.u.moveset["W"]
        self.assertEqual(self.match._scy_move_mult(self.u, w.chosen, max(1, w.rank)), 1.0)

    def test_bullet_punch_dashes_and_interrupts(self):
        self.to_scizor()
        self.e.pos = Vec2(23.5, 47.5)
        self.e.channel_until = self.match.time + 2.0
        self.match.channels.append({"type": "flame", "caster_id": self.e.id,
                                    "end": self.match.time + 2.0})
        hp = self.e.hp
        self.cast("Q", 30.0, 47.5)
        self.assertGreater(self.u.pos.x, 21.5)
        self.assertGreater(self.lost(hp), 0)
        self.assertFalse([c for c in self.match.channels if c["caster_id"] == self.e.id])
        self.assertLessEqual(self.e.channel_until, self.match.time)
        self.assertGreater(self.u.cc_immune_until, self.match.time)   # non interrompibile

    def test_superpower_self_debuff(self):
        self.to_scizor()
        self.choose("R", 0)
        atk, df = self.u.eff_attack(), self.u.eff_defense()
        hp = self.e.hp
        self.cast("R", 22.0, 47.5)
        self.assertGreater(self.lost(hp), 0)
        self.tick(0.1)
        self.assertAlmostEqual(self.u.eff_attack(), atk * 0.8, delta=1.0)
        self.assertAlmostEqual(self.u.eff_defense(), df * 0.8, delta=1.0)
        self.tick(4.1)
        self.assertAlmostEqual(self.u.eff_attack(), atk, delta=1.0)

    def test_steel_claws(self):
        self.to_scizor()
        self.choose("R", 1)
        as0 = self.match._eff_attack_speed(self.u)
        self.cast("R", 0, 0)
        self.assertGreater(self.match._eff_attack_speed(self.u), as0)
        self.u.hp = self.u.max_hp * 0.5
        h0 = self.u.hp
        self.match._combat_hash.rebuild(self.world.combatants())
        hp = self.e.hp
        self.match._aa_land(self.u, self.e, self.match._aa_snapshot(self.u, self.e))
        one = self.lost(hp)
        self.tick(0.3)
        two = self.lost(hp) - one
        self.assertAlmostEqual(two / one, 0.6, delta=0.15)
        self.assertGreater(self.u.hp, h0)

    # --- Kleavor -------------------------------------------------------------------
    def to_kleavor(self):
        self.level(8)
        self.buy("black_augurite")
        self.assertEqual(self.u.name, "Kleavor")

    def test_stone_axes_aa(self):
        self.to_kleavor()
        self.assertAlmostEqual(self.match._scy_as_mult(self.u), 0.8)
        self.assertAlmostEqual(self.match._scy_aa_mult(self.u), 1.4)
        e2 = spawn(self.world, FOE, Vec2(22.0, 48.3), 1)
        e2.max_hp = e2.hp = 50000.0
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._aa_land(self.u, self.e, self.match._aa_snapshot(self.u, self.e))
        self.assertLess(e2.hp, e2.max_hp)   # arco davanti

    def test_stone_axe_field(self):
        self.to_kleavor()
        df = self.u.eff_defense()
        self.cast("Q", 22.0, 47.5)
        self.assertEqual(len(self.match.scy_fields), 1)
        hp = self.e.hp
        self.tick(1.1)
        self.assertGreater(self.lost(hp), 0)
        self.assertLess(self.e.slow_mult, 1.0)
        self.assertTrue(self.u.scy_infield)
        self.assertAlmostEqual(self.u.eff_defense(), df * 1.2, delta=1.0)
        self.tick(5.5)
        self.assertEqual(self.match.scy_fields, [])

    def test_tree_cut_delay_airborne_field(self):
        self.to_kleavor()
        self.choose("R", 0)
        hp = self.e.hp
        self.cast("R", 24.0, 47.5)
        self.assertEqual(self.lost(hp), 0)
        self.tick(0.6)
        self.assertGreater(self.lost(hp), 0)
        self.assertGreater(self.e.airborne_until, self.match.time)
        f = self.match.scy_fields[-1]
        self.assertEqual(f["kind"], "cone")
        self.tick(1.2)   # i tick del campo fanno danno ma non rilanciano in aria
        self.e.airborne_until = -1.0
        hp = self.e.hp
        self.tick(1.1)
        self.assertGreater(self.lost(hp), 0)
        self.assertLess(self.e.airborne_until, self.match.time)

    def test_rock_smash_shred(self):
        self.to_kleavor()
        self.choose("R", 1)
        df = self.e.eff_defense()
        self.cast("R", 0, 0)
        self.match._combat_hash.rebuild(self.world.combatants())
        for _ in range(7):
            self.match._aa_land(self.u, self.e, self.match._aa_snapshot(self.u, self.e))
        self.assertEqual(self.e.scy_shred, 5)
        self.assertAlmostEqual(self.e.eff_defense(), df * 0.6, delta=1.0)
        self.tick(4.2)
        self.assertAlmostEqual(self.e.eff_defense(), df, delta=1.0)

    # --- rete ----------------------------------------------------------------------
    def test_fields_and_chops_reach_both_teams(self):
        from net import protocol
        from net.visual import capture_visual
        self.level(8)
        self.buy("black_augurite")
        self.choose("R", 0)
        self.cast("Q", 22.0, 47.5)
        self.cast("R", 24.0, 47.5)
        for team in (0, 1):
            st = protocol.dec_vis(protocol.enc_vis(capture_visual(self.match, team)))
            self.assertEqual(len(st["scy_fields"]), 1)
            self.assertEqual(len(st["scy_chops"]), 1)
            self.assertNotIn("mv", st["scy_fields"][0])


if __name__ == "__main__":
    unittest.main()
