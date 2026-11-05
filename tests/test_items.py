import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.content import load_map, load_pokemon_def
from engine.items import ITEM_SLOTS, ItemCatalog
from engine.match import Match
from engine.vec import Vec2
from engine.world import World


class TestItems(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = ItemCatalog.load(os.path.join(ROOT, "data", "items.json"))

    def test_slots_cap(self):
        self.assertEqual(ITEM_SLOTS, 6)

    def test_catalog_shape(self):
        self.assertEqual(len(self.cat.base_ids), 7)
        self.assertEqual(len(self.cat.intermediate_ids), 15)   # + Metalcoperta, Augite Nera
        self.assertEqual(len(self.cat.completed_ids), 36)
        for it in self.cat.items.values():
            self.assertTrue(it.icon, it.id)
            for c in it.build_from:
                self.assertIn(c, self.cat.items, (it.id, c))
        self.assertIn("fighter", [c[0] for c in self.cat.categories])

    def test_full_price_no_components(self):
        self.assertEqual(self.cat.effective_price("choice_band", []), 3000)

    def test_discount_one_component(self):
        self.assertEqual(self.cat.effective_price("choice_band", ["muscle_band"]), 1900)

    def test_discount_nested_component(self):
        # Proteina -> Muscolbanda -> Fascia Scelta: il componente annidato si sconta.
        self.assertEqual(self.cat.effective_price("choice_band", ["protein"]), 2650)
        self.assertEqual(self.cat.effective_price("choice_band", ["protein", "protein", "carbos"]),
                         3000 - 350 - 350 - 300)

    def test_discount_all_components(self):
        self.assertEqual(self.cat.effective_price("choice_band", ["muscle_band", "scope_lens", "protein"]), 550)

    def test_components_consumed(self):
        comps = self.cat.components_in("choice_band", ["muscle_band", "scope_lens", "hp_up"])
        self.assertEqual(set(comps), {"muscle_band", "scope_lens"})

    def test_recipes_two_intermediates_plus_vitamin(self):
        # Regola: completo = 2 intermedi + 1 vitamina (eccezioni: Roccia di Re, Condividi Esp.).
        for iid in self.cat.completed_ids:
            if iid in ("king_rock", "exp_share"):
                continue
            kinds = [self.cat.items[c].tier for c in self.cat.items[iid].build_from]
            self.assertEqual(sorted(kinds), [1, 2, 2], iid)

    def test_group_rules(self):
        self.assertFalse(self.cat.group_ok("choice_specs", ["choice_band"]))
        self.assertFalse(self.cat.group_ok("running_shoes", ["bicycle"]))
        self.assertTrue(self.cat.group_ok("bicycle", ["running_shoes"]))   # le scarpe si consumano
        self.assertTrue(self.cat.group_ok("choice_band", ["quick_claw"]))

    def test_total_bonus(self):
        b = self.cat.total_bonus(["muscle_band", "wise_glasses", "protein", "protein"])
        self.assertEqual(b["attack"], 45)
        self.assertEqual(b["sp_attack"], 45)

    def test_sell_value(self):
        self.assertEqual(self.cat.sell_value("choice_band"), int(3000 * 0.6))

    def test_pokemon_recommended_exist(self):
        for f in os.listdir(os.path.join(ROOT, "data", "pokemon")):
            d = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", f))
            self.assertTrue(d.recommended_items, f)
            for iid in d.recommended_items:
                self.assertIn(iid, self.cat.items, (f, iid))
            groups = [self.cat.get(i).group for i in d.recommended_items if self.cat.get(i).group]
            self.assertEqual(len(groups), len(set(groups)), f)


class TestItemEffects(unittest.TestCase):
    def setUp(self):
        md = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        self.world = World(md.grid)
        self.match = Match(self.world, md)
        pdef = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "totodile.json"))
        sp = md.spawns["team0"]
        self.base = Vec2(sp[0] + 0.5, sp[1] + 0.5)

        def mk(team, pos):
            return self.world.spawn_pokemon(pos=pos, team=team, dex=pdef.dex, name=pdef.name,
                                            color=(0, 0, 0), speed=3.5, types=pdef.types,
                                            base_stats=pdef.base_stats, moves=pdef.moves,
                                            evolutions=pdef.evolutions,
                                            attack_range=pdef.attack_range)
        self.a = mk(0, self.base)
        self.b = mk(1, self.base + Vec2(1.0, 0.0))

    def give(self, p, *ids):
        p.items = list(ids)
        self.match._apply_items(p)

    def test_buy_respects_choice_limit(self):
        self.a.gold = 99999
        self.assertTrue(self.match.shop_buy(self.a, "choice_band"))
        self.assertFalse(self.match.shop_buy(self.a, "choice_specs"))

    def test_exp_share_one_per_team(self):
        ally = self.world.spawn_pokemon(pos=self.base, team=0, dex=1, name="X", color=(0, 0, 0),
                                        speed=3.5, base_stats=self.a.base_stats.__dict__)
        self.a.gold = ally.gold = 99999
        self.assertTrue(self.match.shop_buy(self.a, "exp_share"))
        self.assertFalse(self.match.shop_buy(ally, "exp_share"))

    def test_move_speed_pct(self):
        before = self.a.move_speed_base
        self.give(self.a, "running_shoes")
        self.assertAlmostEqual(self.a.move_speed_base, before * 1.10, places=5)

    def test_eviolite_only_before_final_form(self):
        self.match._recompute_stats(self.a)
        base_def = self.a.eff_defense()
        self.give(self.a, "eviolite")
        self.assertAlmostEqual(self.a.eff_defense(), base_def + 45, places=5)
        self.a.stage = self.match._n_stages(self.a) - 1   # forma finale
        self.match._recompute_stats(self.a)
        self.assertAlmostEqual(self.a.eff_defense(),
                               self.a.stats.defense, places=5)

    def test_focus_sash_survives(self):
        self.give(self.b, "focus_sash")
        self.match._deal_damage(self.a, self.b, self.b.max_hp * 5)
        self.assertTrue(self.b.alive)
        self.assertEqual(self.b.hp, 1.0)
        self.match._deal_damage(self.a, self.b, 10.0)   # in ricarica: muore
        self.assertFalse(self.b.alive)

    def test_red_card_pushes_attacker(self):
        self.give(self.b, "red_card")
        start = Vec2(self.a.pos.x, self.a.pos.y)
        self.match._deal_damage(self.a, self.b, self.b.max_hp * 0.2)
        self.assertGreater(self.a.pos.dist(start), 0.5)

    def test_leftovers_regen(self):
        self.give(self.b, "leftovers")
        self.b.hp = self.b.max_hp * 0.5
        self.b.last_damaged_at = -100.0
        self.match.time = 10.0
        hp0 = self.b.hp
        self.match._update_items(1.0)
        self.assertAlmostEqual(self.b.hp - hp0, self.b.max_hp * 0.02, places=3)

    def test_mental_herb_cleanses(self):
        self.give(self.a, "mental_herb")
        self.match._apply_stun(self.a, 3.0)
        self.assertTrue(self.match.use_item(self.a, 0))
        self.assertFalse(self.match._immobile(self.a))
        self.assertFalse(self.match.use_item(self.a, 0))   # in ricarica

    def test_cdr_to_haste(self):
        self.give(self.a, "soothe_bell")
        self.assertAlmostEqual(100.0 / (100.0 + self.a.ability_haste), 0.85, places=5)

    def test_penetration_stats(self):
        self.give(self.a, "dragon_fang", "magnet")
        self.assertAlmostEqual(self.a.armor_pen_pct, 0.20)
        self.assertAlmostEqual(self.a.magic_pen_pct, 0.20)

    def test_healcut_from_poison_barb(self):
        self.give(self.a, "poison_barb")
        self.match._item_after_aa(self.a, self.b)
        self.assertAlmostEqual(self.match._healcut_mult(self.b), 0.6)

    def test_charcoal_burns_on_move_only(self):
        self.give(self.a, "charcoal")
        self.match._item_after_aa(self.a, self.b)
        self.assertLess(self.b.ember_until, self.match.time)
        self.match._item_after_move_hit(self.a, None, self.b, 1.0)
        hp0 = self.b.hp
        self.match._update_items(1.0)
        self.assertAlmostEqual(hp0 - self.b.hp, self.b.max_hp * 0.01, places=3)

    def test_focus_band_shield(self):
        self.give(self.b, "focus_band")
        self.match._deal_damage(self.a, self.b, self.b.max_hp * 0.75)
        self.assertGreater(self.b.shield, 0.0)
        self.assertAlmostEqual(self.b.shield, self.b.max_hp * 0.30, places=3)

    def test_rusted_sword_stacks(self):
        self.give(self.a, "rusted_sword")
        base = self.a.eff_attack()
        for _ in range(5):
            self.match._item_after_aa(self.a, self.b)
        self.assertEqual(self.a.rust_n, 5)
        self.assertAlmostEqual(self.a.eff_attack(), base * 1.15, places=3)
        self.match.time += 10.0
        self.match._update_items(0.1)
        self.assertEqual(self.a.rust_n, 0)

    def test_never_melt_ice_slows_attacker(self):
        self.give(self.b, "never_melt_ice")
        self.match._item_after_aa(self.a, self.b)
        self.assertAlmostEqual(self.match._item_aa_cd_mult(self.a), 1.25)

    def test_mystic_water_aura(self):
        self.give(self.b, "mystic_water")
        ally = self.world.spawn_pokemon(pos=self.b.pos + Vec2(2.0, 0.0), team=1, dex=1, name="X",
                                        color=(0, 0, 0), speed=3.5,
                                        base_stats=self.a.base_stats.__dict__)
        d0 = ally.eff_sp_defense()
        self.match._update_items(0.1)
        self.assertAlmostEqual(ally.eff_sp_defense(), d0 + 20.0)
        self.assertEqual(self.b.aura_spdef, 0.0)   # il possessore non conta
        self.assertEqual(self.a.aura_spdef, 0.0)   # squadra diversa

    def test_poke_flute_cleanses_and_hastes(self):
        self.give(self.a, "poke_flute")
        self.match._apply_sleep(self.a, 5.0)
        self.assertTrue(self.match.use_item(self.a, 0))
        self.assertFalse(self.match._immobile(self.a))
        self.assertAlmostEqual(self.a.speed_mult, 1.2)


if __name__ == "__main__":
    unittest.main()
