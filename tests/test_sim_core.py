"""Fondamenta del motore di allenamento in Rust (docs/RUST_ENGINE.md, fase 0):
RNG, funzioni matematiche e hash delle tuple devono dare ESATTAMENTE i risultati
di CPython, bit per bit, perche' le partite in Rust restino identiche a quelle
in Python."""
import math
import random
import struct
import unittest

try:
    import pokemoba_native as nat
except ImportError:  # estensione non compilata: niente da controllare
    nat = None

HAS_SIM = nat is not None and hasattr(nat, "SimRandom")


def bits(x: float) -> int:
    return struct.unpack("<q", struct.pack("<d", x))[0]


@unittest.skipUnless(HAS_SIM, "pokemoba_native senza il motore di allenamento")
class TestSimRandom(unittest.TestCase):
    SEEDS = (0, 1, 7, 500, 12345, 2**31 - 1, 2**32, 2**40 + 3, -99, 2**100 + 17)

    def test_random_stream(self):
        for s in self.SEEDS:
            py, rs = random.Random(s), nat.SimRandom(s)
            for _ in range(2000):        # oltre i 624 numeri: passa per la rigenerazione
                self.assertEqual(py.random(), rs.random(), s)

    def test_int_draws(self):
        for s in self.SEEDS:
            py, rs = random.Random(s), nat.SimRandom(s)
            for n in (1, 2, 3, 5, 7, 10, 26, 100, 1 << 16, 1 << 30, (1 << 31) + 5, 1 << 40):
                for _ in range(50):
                    self.assertEqual(py._randbelow(n), rs.randbelow(n))
                    self.assertEqual(py.randrange(n), rs.randrange(n))
                    self.assertEqual(py.randrange(-4, n), rs.randrange(-4, n))
            for k in (0, 1, 5, 31, 32, 33, 53, 64):
                for _ in range(20):
                    self.assertEqual(py.getrandbits(k), rs.getrandbits(k))

    def test_choice_shuffle_uniform(self):
        for s in self.SEEDS:
            py, rs = random.Random(s), nat.SimRandom(s)
            seq = ("poison", "paralysis", "sleep")
            for n in (1, 3, 9, 100):
                lst = list(range(n))
                py.shuffle(lst)
                self.assertEqual(lst, rs.shuffled_range(n))
                self.assertEqual(py.choice(seq), seq[rs.choice_index(len(seq))])
            for a, b in ((0.0, math.tau), (-3.5, 2.25), (5.0, 5.0)):
                self.assertEqual(bits(py.uniform(a, b)), bits(rs.uniform(a, b)))

    def test_state_handoff(self):
        # Il Python consuma qualche numero nel preparare la partita, poi passa lo
        # stato al Rust: da li' i due flussi devono coincidere.
        py = random.Random(777)
        for _ in range(1000):
            py.random()
        rs = nat.SimRandom.from_state(py.getstate())
        self.assertEqual(rs.getstate(), py.getstate())
        for _ in range(1500):
            self.assertEqual(py.random(), rs.random())
        self.assertEqual(rs.getstate(), py.getstate())


@unittest.skipUnless(HAS_SIM, "pokemoba_native senza il motore di allenamento")
class TestSimMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = random.Random(3)
        xs = [r.uniform(-50, 50) for _ in range(20000)]
        xs += [r.uniform(-1e-3, 1e-3) for _ in range(2000)]
        xs += [r.uniform(-1e6, 1e6) for _ in range(2000)]
        xs += [0.0, -0.0, 0.5, -0.5, 1.5, 2.5, -2.5, 1e-310, math.pi, -math.pi, 1.0, -1.0]
        cls.xs = xs
        cls.ys = [r.uniform(-50, 50) for _ in xs]

    def check(self, name, f, xs, ys=None):
        got = nat.sim_math(name, xs, ys)
        exp = [f(x) for x in xs] if ys is None else [f(x, y) for x, y in zip(xs, ys)]
        bad = [(x, e, g) for x, e, g in zip(xs, exp, got) if bits(e) != bits(g)]
        self.assertEqual(bad[:3], [], "%s: %d/%d differ" % (name, len(bad), len(xs)))

    def test_unary(self):
        unit = [math.sin(x) for x in self.xs]   # dominio di acos
        for name, f, xs in (("sin", math.sin, self.xs), ("cos", math.cos, self.xs),
                            ("exp", math.exp, [x / 10 for x in self.xs if abs(x) < 7000]),
                            ("sqrt", math.sqrt, [abs(x) for x in self.xs]),
                            ("acos", math.acos, unit),
                            ("floor", lambda x: float(math.floor(x)), self.xs),
                            ("ceil", lambda x: float(math.ceil(x)), self.xs),
                            ("radians", math.radians, self.xs), ("degrees", math.degrees, self.xs),
                            ("round", lambda x: float(round(x)), self.xs)):
            self.check(name, f, xs)

    def test_binary(self):
        ys = [y if y != 0.0 else 1.0 for y in self.ys]
        for name, f in (("atan2", math.atan2), ("hypot", math.hypot),
                        ("mod", lambda a, b: a % b), ("floordiv", lambda a, b: a // b)):
            self.check(name, f, self.xs, ys)
        pos = [abs(x) for x in self.xs]
        self.check("pow", lambda a, b: a ** b, pos, [0.5] * len(pos))
        self.check("pow", lambda a, b: a ** b, pos, [2.0] * len(pos))

    def test_tuple_hash(self):
        r = random.Random(5)
        for _ in range(3000):
            t = [r.randrange(-10**6, 10**6) for _ in range(r.randrange(0, 6))]
            self.assertEqual(nat.sim_tuple_hash(t), hash(tuple(t)), t)
        for t in ([-1], [-2, -1], [2**61 - 1], [2**61], [2**62, -(2**62)]):
            self.assertEqual(nat.sim_tuple_hash(t), hash(tuple(t)), t)


@unittest.skipUnless(HAS_SIM, "pokemoba_native senza il motore di allenamento")
class TestFloatHex(unittest.TestCase):
    def test_roundtrip(self):
        r = random.Random(11)
        xs = [r.uniform(-1e3, 1e3) for _ in range(5000)] + [r.uniform(-1, 1) * 10 ** r.randrange(-320, 308)
                                                            for _ in range(5000)]
        xs += [0.0, -0.0, 1.0, -2.5, 5e-324, -5e-324, 2.2250738585072014e-308, 1.7976931348623157e308,
               math.inf, -math.inf]
        hx = nat.sim_float_hex(xs)
        self.assertEqual(hx, [x.hex() for x in xs])
        back = nat.sim_parse_hex([x.hex() for x in xs])
        self.assertEqual([bits(x) for x in back], [bits(x) for x in xs])
        self.assertTrue(math.isnan(nat.sim_parse_hex([math.nan.hex()])[0]))


@unittest.skipUnless(HAS_SIM and hasattr(nat, "sim_world_tick"), "pokemoba_native senza World.tick in Rust")
class TestWorldTickParity(unittest.TestCase):
    def test_short_match(self):
        # World.tick in Rust sullo stato proprio == World.tick del motore, tick per tick.
        import contextlib
        import io
        import os
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
        import sim_step_parity
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sim_step_parity.run("world_tick", 1, 25.0, 7, 0, 3)
        self.assertEqual(code, 0, out.getvalue())


@unittest.skipUnless(HAS_SIM, "pokemoba_native senza il motore di allenamento")
class TestMatchSpec(unittest.TestCase):
    def test_spec_handoff(self):
        import os
        import sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(root, "tools"))
        import sim_spec
        import tier_sim
        tier_sim._init_worker(False, 10.0, True)
        job = tier_sim.make_jobs(1, 7)[0]
        spec = sim_spec.build_spec(job)
        self.assertEqual(spec["version"], nat.SIM_SPEC_VERSION)
        expected = random.Random()
        expected.setstate(spec["rng_state"])
        res = nat.run_match(spec)
        self.assertEqual(res["rng_next"], expected.random())   # RNG passato esatto
        self.assertEqual(res["ticks"], 300)
        self.assertEqual(sorted(res["team_sizes"]), [5, 5])
        # La cattura non gioca tick: lo stato iniziale e' quello di prima del primo update.
        self.assertEqual(spec["initial"]["time"], (0.0).hex())
        bad = dict(spec, version=spec["version"] + 1)
        with self.assertRaises(ValueError):
            nat.run_match(bad)


if __name__ == "__main__":
    unittest.main()
