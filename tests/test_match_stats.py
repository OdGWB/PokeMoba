"""Statistiche della partita (tabellone/fine partita) e riepilogo della morte."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from engine.content import load_map, load_pokemon_def
from engine.match import RECAP_WINDOW, Match
from engine.vec import Vec2
from engine.world import World
from net import protocol as P
from net.visual import capture_visual

from tests.test_smoke import _spawn

DEFS = [load_pokemon_def(os.path.join(ROOT, rel)) for rel in config.ROSTER]


class StatsTest(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, config.DEFAULT_MAP))
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        c = Vec2(m.grid.width / 2, m.grid.height / 2)
        self.a = _spawn(self.world, DEFS[0], Vec2(c.x - 1, c.y), 0, bot=False)
        self.b = _spawn(self.world, DEFS[1], Vec2(c.x + 1, c.y), 1, bot=True)
        self.c = _spawn(self.world, DEFS[2], Vec2(c.x + 1, c.y + 1), 0, bot=True)

    def test_kda_and_recap(self):
        m, a, b, c = self.match, self.a, self.b, self.c
        mv = next(iter(a.moveset.values())).chosen
        m.time = 5.0
        m._deal_damage(c, b, 50.0)                          # c assiste
        m._dmg_label = mv.name
        m._deal_damage(a, b, 100.0, dmg_type=mv.type)
        m._dmg_label = None
        m._deal_damage(a, b, b.hp + 999.0)                   # colpo finale (con eccesso)
        self.assertEqual((a.stat_kills, b.stat_deaths, c.stat_assists), (1, 1, 1))
        self.assertGreater(a.stat_dmg, 100.0)
        rc = b.death_recap
        self.assertEqual(rc["killer"], a.id)
        top = rc["rows"][0]
        self.assertEqual(top["id"], a.id)
        # l'eccesso oltre gli HP non conta
        self.assertLessEqual(sum(r["total"] for r in rc["rows"]), round(b.max_hp) + 1)
        self.assertIn(mv.name, [s[0] for s in top["src"]])
        self.assertEqual(b.dmg_log, [])

    def test_recap_window(self):
        m, a, b = self.match, self.a, self.b
        m.time = 1.0
        m._deal_damage(a, b, 10.0)
        m.time = 1.0 + RECAP_WINDOW + 5.0
        m._deal_damage(a, b, b.hp + 1.0)
        total = sum(r["total"] for r in b.death_recap["rows"])
        self.assertLess(total, b.max_hp)                  # i 10 HP vecchi non ci sono

    def test_net_roundtrip(self):
        m, a, b = self.match, self.a, self.b
        m._deal_damage(a, b, b.hp + 1.0)
        vis = P.dec_vis(P.enc_vis(capture_visual(m, 1, b)))
        rows = {r[0]: r for r in vis["score"]}
        self.assertEqual(rows[a.id][4], 1)               # uccisioni
        self.assertEqual(rows[b.id][5], 1)               # morti
        self.assertEqual(vis["recap"]["killer"], a.id)
        from game.match_ui import rows_from_score
        sr = rows_from_score(vis["score"], b.id, {}, {b.id})
        me = [r for r in sr if r.me][0]
        self.assertFalse(me.alive)


if __name__ == "__main__":
    unittest.main()
