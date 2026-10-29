"""Profilo del giocatore (nickname + immagine profilo) e avatar nel protocollo."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from game import avatars as A
from net import protocol as P
from net import validation as V


class ProfileTest(unittest.TestCase):
    def test_save_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "profile.json"
            self.assertIsNone(A.load_profile(path))           # primo avvio
            A.save_profile("  Ash   Ketchum  ", 384, path)
            self.assertEqual(A.load_profile(path), {"name": "Ash Ketchum", "avatar": 384})

    def test_bad_profile(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "profile.json"
            path.write_text("{non json", encoding="utf-8")
            self.assertIsNone(A.load_profile(path))
            path.write_text('{"name": "", "avatar": 150}', encoding="utf-8")
            self.assertIsNone(A.load_profile(path))           # nome vuoto = va richiesto
            path.write_text('{"name": "Red", "avatar": 25}', encoding="utf-8")
            self.assertEqual(A.load_profile(path)["avatar"], 0)  # non leggendario

    def test_clean_name(self):
        self.assertEqual(A.clean_name("a\x00b\nc" + "x" * 30), ("abc" + "x" * 30)[:A.NAME_MAX])

    def test_avatar_list(self):
        dexes = [d for d, _ in A.AVATARS]
        self.assertEqual(len(dexes), len(set(dexes)))
        self.assertTrue(all(0 < d <= 1025 for d in dexes))


class ProtocolAvatarTest(unittest.TestCase):
    def test_hello(self):
        h = P.dec_hello(P.enc_hello("Misty", 245))
        self.assertEqual((h["version"], h["name"], h["avatar"]), (P.PROTO_VERSION, "Misty", 245))

    def test_old_hello(self):
        old = P.Writer().u8(P.R_HELLO).u8(1).s("Vecchio", 24).bytes()
        self.assertEqual(P.dec_hello(old)["version"], 1)      # rifiutato dall'host, non crasha

    def test_lobby_start(self):
        pl = [{"slot": 0, "team": 0, "pokemon": 2, "ready": True, "conn": 1,
               "name": "Host", "avatar": 150}]
        self.assertEqual(P.dec_lobby(P.enc_lobby(0, 6, pl))["players"][0]["avatar"], 150)
        st = [{"slot": 1, "entity_id": 7, "team": 1, "pokemon": 0, "name": "Bob", "avatar": 1024}]
        self.assertEqual(P.dec_start(P.enc_start("m.json", 7, st))["players"][0]["avatar"], 1024)

    def test_valid_avatar(self):
        self.assertEqual(V.valid_avatar(384), 384)
        self.assertEqual(V.valid_avatar(70000), 0)
        self.assertEqual(V.valid_avatar("384"), 0)


if __name__ == "__main__":
    unittest.main()
