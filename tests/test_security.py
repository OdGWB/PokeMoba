"""Test delle difese di sicurezza: percorso della mappa dall'host, flood sul canale
reliable, robustezza del thread dell'host, nebbia di guerra negli FX, updater."""
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from net import protocol as P
from net import validation as V


class TestMapPath(unittest.TestCase):
    def test_only_known_maps(self):
        for _n, path in config.MAPS:
            self.assertEqual(V.allowed_map(path), path)
        for bad in ("//attacker.example/share/m.json", "\\\\attacker\\share\\m.json",
                    "C:/Windows/win.ini", "../../secret.json", "data/maps/../../x.json",
                    "data/maps/map_test.json", "", None, 3):
            self.assertIsNone(V.allowed_map(bad), bad)

    def test_client_refuses_malicious_start(self):
        from net import ClientSession, LoopbackTransport
        _a, b = LoopbackTransport.pair()
        c = ClientSession(b, "Amico")
        evil = P.enc_start("//attacker.example/share/m.json", 5,
                           [{"slot": 0, "entity_id": 5, "team": 0, "pokemon": 0, "name": "x"}])
        c._handle(P.CH_RELIABLE, evil, time.monotonic())
        self.assertIsNone(c.start_info)
        self.assertEqual(c.phase, "lost")

    def test_client_refuses_bad_roster_index(self):
        from net import ClientSession, LoopbackTransport
        _a, b = LoopbackTransport.pair()
        c = ClientSession(b, "Amico")
        evil = P.enc_start(config.MAPS[0][1], 5,
                           [{"slot": 0, "entity_id": 5, "team": 0, "pokemon": 250, "name": "x"}])
        c._handle(P.CH_RELIABLE, evil, time.monotonic())
        self.assertIsNone(c.start_info)

    def test_lan_client_ignores_other_senders(self):
        from net.lan import protocol as LP
        from net.lan.client import GameClient
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("127.0.0.1", 0))
        evil = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        evil.bind(("127.0.0.1", 0))
        try:
            gc = GameClient("127.0.0.1", srv.getsockname()[1])
            gc.send_hello("x")                       # assegna una porta al client
            _d, caddr = srv.recvfrom(4096)
            start = LP.enc_start(config.MAPS[0][1], 1, [])
            evil.sendto(start, caddr)                # finto server
            time.sleep(0.05)
            gc.poll()
            self.assertIsNone(gc.start_info)
            srv.sendto(LP.enc_start("//attacker.example/s/m.json", 1, []), caddr)
            time.sleep(0.05)
            gc.poll()
            self.assertIsNone(gc.start_info)         # mappa non ammessa
            srv.sendto(start, caddr)                 # il vero server
            time.sleep(0.05)
            gc.poll()
            self.assertIsNotNone(gc.start_info)
            gc.sock.close()
        finally:
            srv.close()
            evil.close()


def _pump(sessions, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for s in sessions:
            s.poll()
        time.sleep(0.005)


class TestHostHardening(unittest.TestCase):
    def test_reliable_flood_is_limited_and_kicked(self):
        from net import ClientSession, HostSession, LoopbackTransport
        h = HostSession(map_index=0, host_name="Host")
        h.start()
        try:
            a, b = LoopbackTransport.pair()
            h.attach_transport(1, a)
            c = ClientSession(b, "Amico")
            _pump([h.local, c], 0.4)
            self.assertEqual(c.phase, "lobby")
            for _ in range(400):                     # flood di scelte in lobby
                b.send_reliable(P.enc_choice(0, 1, False))
            _pump([h.local, c], 0.5)
            self.assertGreater(h.view[1]["rejected"], 0)
            self.assertTrue(h._thread.is_alive())
        finally:
            h.shutdown()

    def test_unexpected_exception_does_not_kill_host(self):
        from net import HostSession
        h = HostSession(map_index=0, host_name="Host")
        boom = {"n": 0}
        orig = h._advance

        def bad_advance(now):
            if boom["n"] < 3:
                boom["n"] += 1
                raise RuntimeError("bug del motore")
            return orig(now)
        h._advance = bad_advance
        h.start()
        try:
            time.sleep(0.2)
            self.assertEqual(boom["n"], 3)
            self.assertTrue(h._thread.is_alive())
            self.assertGreaterEqual(h.errors_total, 3)
        finally:
            h.shutdown()


class _Vis:
    def __init__(self, visible_tiles=(), visible_ids=()):
        self.tiles, self.ids = set(visible_tiles), set(visible_ids)

    def is_tile_visible(self, team, x, y):
        return (x, y) in self.tiles

    def is_enemy_visible(self, team, eid):
        return eid in self.ids


class TestFxFog(unittest.TestCase):
    def _match(self, vis):
        ents = {1: SimpleNamespace(team=0), 2: SimpleNamespace(team=1)}
        return SimpleNamespace(world=SimpleNamespace(get=ents.get), vision=vis)

    def test_cone_in_fog_is_hidden(self):
        from net.snapshot import fx_visible
        m = self._match(_Vis())
        cone = {"kind": "cone", "o": (10.0, 10.0), "dir": (1.0, 0.0), "range": 3}
        self.assertFalse(fx_visible(m, 0, cone))
        m = self._match(_Vis(visible_tiles=[(10, 10)]))
        self.assertTrue(fx_visible(m, 0, cone))

    def test_no_position_events(self):
        from net.snapshot import fx_visible
        m = self._match(_Vis())
        self.assertTrue(fx_visible(m, 0, {"kind": "shake", "dur": 0.6}))   # globale apposta
        self.assertFalse(fx_visible(m, 0, {"kind": "mistero"}))
        self.assertFalse(fx_visible(m, 0, {"kind": "x", "src": 2}))          # nemico in nebbia
        self.assertTrue(fx_visible(m, 0, {"kind": "x", "src": 1}))           # alleato
        m = self._match(_Vis(visible_ids=[2]))
        self.assertTrue(fx_visible(m, 0, {"kind": "x", "hit": 2}))

    def test_pts_list(self):
        from net.snapshot import fx_visible
        ev = {"kind": "painsplit", "pts": [(1.0, 1.0), (20.0, 20.0)]}
        self.assertFalse(fx_visible(self._match(_Vis()), 0, ev))
        self.assertTrue(fx_visible(self._match(_Vis(visible_tiles=[(20, 20)])), 0, ev))


class TestUpdater(unittest.TestCase):
    def setUp(self):
        from game import version
        self.version = version
        self._repo, self._key = version.REPO, version.UPDATE_PUBKEY
        version.REPO = "owner/game"

    def tearDown(self):
        self.version.REPO, self.version.UPDATE_PUBKEY = self._repo, self._key
        os.environ.pop("POKEMOBA_UPDATE_URL", None)

    def test_download_url_allowlist(self):
        from game.updater import download_allowed
        ok = "https://github.com/owner/game/releases/download/v9/PokeMoba.exe"
        self.assertTrue(download_allowed(ok))
        for bad in ("https://evil.example/PokeMoba.exe",
                    "https://github.com/evil/game/releases/download/v9/PokeMoba.exe",
                    "https://github.com.evil.example/owner/game/releases/download/x",
                    "http://github.com/owner/game/releases/download/v9/PokeMoba.exe",
                    "http://127.0.0.1:8000/PokeMoba.exe", None):
            self.assertFalse(download_allowed(bad), bad)
        self.assertTrue(download_allowed("http://127.0.0.1:8000/PokeMoba.exe", local=True))
        self.assertFalse(download_allowed("http://127.0.0.1.evil.example/x", local=True))

    def test_override_only_localhost(self):
        from game.updater import _local_override
        os.environ["POKEMOBA_UPDATE_URL"] = "https://evil.example/api"
        self.assertIsNone(_local_override())
        os.environ["POKEMOBA_UPDATE_URL"] = "http://localhost.evil.example/api"
        self.assertIsNone(_local_override())
        os.environ["POKEMOBA_UPDATE_URL"] = "http://127.0.0.1:8000/api"
        self.assertEqual(_local_override(), "http://127.0.0.1:8000/api")

    def test_signature(self):
        import hashlib
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from game.updater import verify_signature
        k = Ed25519PrivateKey.generate()
        pub = k.public_key().public_bytes(serialization.Encoding.Raw,
                                          serialization.PublicFormat.Raw).hex()
        from game.updater import signed_message
        d = hashlib.sha256(b"exe").digest()
        sig = k.sign(signed_message(d, 12))
        self.assertTrue(verify_signature(d, 12, sig, pub))
        self.assertFalse(verify_signature(hashlib.sha256(b"altro").digest(), 12, sig, pub))
        self.assertFalse(verify_signature(d, 12, b"x" * 64, pub))
        self.assertFalse(verify_signature(d, 12, sig, "zz"))
        # Downgrade: lo stesso exe firmato per il build 12 non vale come build 13.
        self.assertFalse(verify_signature(d, 13, sig, pub))
        # Una firma del solo sha256 (formato senza build) non e' accettata.
        self.assertFalse(verify_signature(d, 12, k.sign(d), pub))
        self.assertFalse(verify_signature(d, 0, sig, pub))

    def test_bad_file_is_deleted(self):
        import hashlib
        from game.updater import Updater
        u = Updater()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "PokeMoba.exe.part"
            tmp.write_bytes(b"exe")
            d = hashlib.sha256(b"exe").digest()
            with self.assertRaises(OSError):
                u._check_file(d, 12, "00" * 32, "", tmp)          # impronta sbagliata
            self.assertFalse(tmp.exists())
            tmp.write_bytes(b"exe")
            self.version.UPDATE_PUBKEY = "11" * 32
            with self.assertRaises(OSError):
                u._check_file(d, 12, d.hex(), "", tmp)        # firma richiesta e assente
            self.assertFalse(tmp.exists())
            tmp.write_bytes(b"exe")
            self.version.UPDATE_PUBKEY = ""
            u._check_file(d, 12, d.hex(), "", tmp)            # impronta giusta, niente firma
            self.assertTrue(tmp.exists())


if __name__ == "__main__":
    unittest.main()
