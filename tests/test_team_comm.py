"""Ping, chat rapida e resa: protocollo, logica della resa (engine/surrender.py) e input della
ruota/limite anti-spam (game/team_comm.py)."""
import os
import sys
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.surrender import SURRENDER_COOLDOWN, SURRENDER_MIN_TIME, SURRENDER_VOTE_TIME
from engine.vec import Vec2
from engine.world import World
from game import team_comm as T
from net import protocol as P

FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))


def spawn(world, team, bot):
    d = FOE
    return world.spawn_pokemon(pos=Vec2(20.5 + team * 40, 47.5), team=team, dex=d.dex,
                               name=d.name, color=d.color, speed=d.base_speed, is_bot=bot,
                               types=d.types, base_stats=d.base_stats, moves=d.moves,
                               evolutions=d.evolutions, role=d.role, passive=d.passive,
                               attack_range=d.attack_range,
                               attack_cooldown=d.attack_cooldown, attack_fx=d.attack_fx)


class TestProtocol(unittest.TestCase):
    def test_team_roundtrip(self):
        m = P.dec_team(P.enc_team(3, P.TEAM_PING, 4, 12.5, 40.25))
        self.assertEqual((m["slot"], m["kind"], m["code"]), (3, P.TEAM_PING, 4))
        self.assertAlmostEqual(m["x"], 12.5, places=1)
        self.assertAlmostEqual(m["y"], 40.25, places=1)

    def test_team_bad_code(self):
        with self.assertRaises(P.ProtocolError):
            P.dec_team(P.enc_team(0, P.TEAM_CHAT, P.TEAM_CODES))

    def test_surrender_roundtrip(self):
        for yes in (True, False):
            a = P.dec_action(P.enc_action(7, P.ACT_SURRENDER, yes=yes))
            self.assertEqual((a["seq"], a["kind"], a["yes"]), (7, P.ACT_SURRENDER, yes))


class TestSurrender(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        self.world = World(m.grid)
        self.match = Match(self.world, m)

    def humans(self, n, bots=1):
        hs = [spawn(self.world, 0, False) for _ in range(n)]
        for _ in range(bots):
            spawn(self.world, 0, True)
        spawn(self.world, 1, True)
        return hs

    def test_needed(self):
        self.assertEqual([Match.surrender_needed(n) for n in (1, 2, 3, 4, 5)], [1, 2, 3, 3, 4])

    def test_too_early(self):
        h = self.humans(1)[0]
        self.match.time = SURRENDER_MIN_TIME - 5
        self.assertIsNotNone(self.match.surrender_vote(h, True))
        self.assertIsNone(self.match.winner)

    def test_solo_passes(self):
        h = self.humans(1)[0]
        self.match.time = SURRENDER_MIN_TIME
        self.assertIsNone(self.match.surrender_vote(h, True))
        self.assertEqual(self.match.winner, 1)

    def test_bots_excluded_and_pass(self):
        a, b = self.humans(2, bots=3)
        self.match.time = SURRENDER_MIN_TIME + 1
        self.match.surrender_vote(a, True)
        st = self.match.surrender_state(0)
        self.assertEqual((st["n"], st["need"], st["yes"]), (2, 2, [a.id]))
        self.assertIsNone(self.match.winner)
        self.assertIsNotNone(self.match.surrender_vote(a, True))   # gia' votato
        self.match.surrender_vote(b, True)
        self.assertEqual(self.match.winner, 1)

    def test_no_fails_with_cooldown(self):
        a, b = self.humans(2)
        self.match.time = SURRENDER_MIN_TIME
        self.match.surrender_vote(a, True)
        self.match.surrender_vote(b, False)
        self.assertIsNone(self.match.winner)
        st = self.match.surrender_state(0)
        self.assertNotIn("end_at", st)
        self.assertAlmostEqual(st["next_at"], SURRENDER_MIN_TIME + SURRENDER_COOLDOWN)
        self.assertIsNotNone(self.match.surrender_vote(a, True))   # in attesa

    def test_timeout(self):
        a, _b = self.humans(2)
        self.match.time = SURRENDER_MIN_TIME
        self.match.surrender_vote(a, True)
        self.match.time += SURRENDER_VOTE_TIME
        self.match._surrender_tick()
        self.assertNotIn("end_at", self.match.surrender_state(0))
        self.assertIsNone(self.match.winner)

    def test_bot_cannot_vote(self):
        self.humans(1, bots=0)
        bot = spawn(self.world, 0, True)
        self.match.time = SURRENDER_MIN_TIME
        self.assertIsNotNone(self.match.surrender_vote(bot, True))


class TestTeamComm(unittest.TestCase):
    def test_wheel_pick(self):
        w = {"c": (100, 100), "alt": False}
        self.assertEqual(T.TeamComm._wheel_pick(w, (102, 101)), T.P_ALERT)
        self.assertEqual(T.TeamComm._wheel_pick(dict(w, alt=True), (100, 100)), T.P_DANGER)
        self.assertEqual(T.TeamComm._wheel_pick(w, (100, 40)), T.WHEEL[0])     # alto
        self.assertEqual(T.TeamComm._wheel_pick(w, (160, 90)), T.WHEEL[1])     # destra
        self.assertEqual(T.TeamComm._wheel_pick(w, (40, 90)), T.WHEEL[4])      # sinistra

    def test_spam_limit(self):
        sent = []
        c = T.TeamComm(lambda *a: sent.append(a))
        c.update(10.0)
        for _ in range(T.SPAM_N + 3):
            c._emit(T.KIND_PING, 0, 1, 1)
        self.assertEqual(len(sent), T.SPAM_N)
        c.update(10.0 + T.SPAM_T + 0.1)
        c._emit(T.KIND_PING, 0, 1, 1)
        self.assertEqual(len(sent), T.SPAM_N + 1)

    def test_surrender_ui(self):
        votes = []
        c = T.TeamComm()
        c.on_surrender = votes.append
        c.update(1.0)
        c.set_vote({"next_at": 600.0}, 500.0, 7)
        c._surrender(True)                       # troppo presto: solo avviso
        self.assertEqual(votes, [])
        self.assertIn("Resa possibile", c.notice[1])
        c.set_vote({"next_at": 600.0}, 600.0, 7)
        c._surrender(True)
        self.assertEqual(votes, [True])
        c.set_vote({"next_at": 600.0, "by": 3, "yes": [3], "no": [], "need": 2, "n": 2,
                    "end_at": 630.0}, 601.0, 7)
        self.assertFalse(c._voted())
        c._surrender(False)
        self.assertEqual(votes, [True, False])
        c.set_vote({"next_at": 600.0, "by": 3, "yes": [3], "no": [7], "need": 2, "n": 2,
                    "end_at": 630.0}, 602.0, 7)
        self.assertTrue(c._voted())


if __name__ == "__main__":
    unittest.main()
