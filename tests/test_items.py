import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.items import ITEM_SLOTS, ItemCatalog


class TestItems(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = ItemCatalog.load(os.path.join(ROOT, "data", "items.json"))

    def test_slots_cap(self):
        self.assertEqual(ITEM_SLOTS, 6)

    def test_full_price_no_components(self):
        self.assertEqual(self.cat.effective_price("choice_band", []), 1100)

    def test_discount_one_component(self):
        self.assertEqual(self.cat.effective_price("choice_band", ["muscle_band"]), 800)

    def test_discount_all_components(self):
        self.assertEqual(self.cat.effective_price("choice_band", ["muscle_band", "scope_lens"]), 500)

    def test_components_consumed(self):
        comps = self.cat.components_in("choice_band", ["muscle_band", "scope_lens", "berry"])
        self.assertEqual(set(comps), {"muscle_band", "scope_lens"})

    def test_total_bonus(self):
        b = self.cat.total_bonus(["muscle_band", "wise_glasses"])
        self.assertEqual(b["attack"], 15)
        self.assertEqual(b["sp_attack"], 18)

    def test_sell_value(self):
        self.assertEqual(self.cat.sell_value("choice_band"), int(1100 * 0.6))


if __name__ == "__main__":
    unittest.main()
