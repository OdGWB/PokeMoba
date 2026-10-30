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
        self.assertEqual(len(self.cat.intermediate_ids), 7)
        self.assertEqual(len(self.cat.completed_ids), 26)
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
        self.assertEqual(self.cat.effective_price("choice_band", ["muscle_band", "scope_lens"]), 900)

    def test_components_consumed(self):
        comps = self.cat.components_in("choice_band", ["muscle_band", "scope_lens", "hp_up"])
        self.assertEqual(set(comps), {"muscle_band", "scope_lens"})

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


if __name__ == "__main__":
    unittest.main()
