"""Movimento e collisioni con i muri: clic al punto esatto, clic su un muro,
ordine che riprende dopo un CC, torre accanto a un muro, unita' in volo e hitbox
dei muri sulla sagoma disegnata (engine/wall_shape)."""
import math
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.content import load_map
from engine.entities import Unit
from engine.grid import TILE_JUNGLE_WALL, TILE_WALL, Grid
from engine.match import Match
from engine.movement import advance_unit, resolve_collisions, resolve_obstacles
from engine.pathfinding import plan_move
from engine.vec import Vec2
from engine.world import World
from sim.commands import AttackMoveCommand
from sim.simulation import Simulation

from tests.test_match_rules import DT, spawn

_MAP = None


def map3():
    global _MAP
    if _MAP is None:
        _MAP = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
    return _MAP


def unit(x, y, r=0.35):
    u = Unit(pos=Vec2(x, y))
    u.radius = r
    return u


class TestPlanMove(unittest.TestCase):
    def test_exact_point_not_tile_center(self):
        g = Grid.empty(10, 10)
        pts = plan_move(g, (1.5, 1.5), (7.2, 3.8))
        self.assertTrue(pts)
        self.assertAlmostEqual(pts[-1][0], 7.2)
        self.assertAlmostEqual(pts[-1][1], 3.8)

    def test_exact_point_inside_own_tile(self):
        g = Grid.empty(5, 5)
        self.assertEqual(plan_move(g, (2.1, 2.1), (2.8, 2.9)), [(2.8, 2.9)])

    def test_click_on_wall_goes_to_reachable_side(self):
        # Muro spesso al centro: il clic dentro il muro porta al bordo raggiungibile
        # piu' vicino, non a un tile chiuso dall'altra parte.
        rows = [[0] * 9 for _ in range(9)]
        for y in range(9):
            for x in range(3, 6):
                rows[y][x] = 1
        g = Grid.from_rows(rows)
        pts = plan_move(g, (1.5, 4.5), (4.9, 4.5))
        self.assertTrue(pts)
        ex, ey = pts[-1]
        self.assertTrue(g.is_walkable(int(ex), int(ey)))
        self.assertLess(ex, 3.0)          # resta dal lato dell'unita'

    def test_click_on_wall_never_walks_around_for_little(self):
        # Muro lungo con un solo varco in fondo: il clic nel muro, un po' piu'
        # vicino all'altro lato, non deve far fare tutto il giro.
        rows = [[0] * 12 for _ in range(30)]
        for y in range(28):
            for x in range(4, 8):
                rows[y][x] = 1
        g = Grid.from_rows(rows)
        for ty in (4.5, 5.5, 6.5):     # clic ripetuti mentre ci si sposta
            ex, ey = plan_move(g, (2.5, 3.5), (6.4, ty))[-1]
            self.assertLess(ex, 4.0)
            self.assertAlmostEqual(ey, ty, delta=1.0)

    def test_click_on_thin_wall_can_use_the_other_side(self):
        # Se il giro e' corto, vince ancora il lato vicino al punto cliccato.
        rows = [[0] * 9 for _ in range(9)]
        for y in range(1, 8):
            for x in range(3, 6):
                rows[y][x] = 1
        g = Grid.from_rows(rows)       # varco in cima, accanto all'unita'
        ex, ey = plan_move(g, (2.5, 0.5), (5.8, 4.5))[-1]
        self.assertEqual((int(ex), int(ey)), (6, 4))

    def test_click_in_closed_pocket(self):
        rows = [[0] * 7 for _ in range(7)]
        for i in range(2, 5):
            rows[2][i] = rows[4][i] = rows[i][2] = rows[i][4] = 1
        g = Grid.from_rows(rows)       # (3, 3) chiuso da ogni lato
        pts = plan_move(g, (0.5, 0.5), (3.5, 3.5))
        self.assertTrue(pts)
        ex, ey = pts[-1]
        self.assertNotEqual((int(ex), int(ey)), (3, 3))


class TestResumeAfterCC(unittest.TestCase):
    def test_move_order_resumes_after_stun(self):
        random.seed(1)
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        world = World(m.grid)
        match = Match(world, m)
        sx, sy = m.spawns["team0"]
        p = spawn(world, Vec2(sx + 0.5, sy + 0.5), 0)
        dest = None
        for dx, dy in ((6, -6), (6, 0), (0, -6), (4, -4)):
            if m.grid.is_walkable_point(sx + dx + 0.3, sy + dy + 0.3):
                dest = Vec2(sx + dx + 0.3, sy + dy + 0.3)
                break
        self.assertIsNotNone(dest)
        pts = plan_move(m.grid, (p.pos.x, p.pos.y), (dest.x, dest.y))
        p.set_path([Vec2(x, y) for x, y in pts])
        p.order = "move"
        p.move_dest = dest
        for i in range(6):
            match.update(DT, i)
        p.stun_until = match.time + 0.5
        for i in range(6, 30):
            match.update(DT, i)
        for i in range(30, 400):
            match.update(DT, i)
            if p.pos.dist(dest) < 0.3:
                break
        self.assertLess(p.pos.dist(dest), 0.3)


class TestAttackMoveOnWall(unittest.TestCase):
    def setUp(self):
        # Mappa 3v3 vera, ma con un muro di prova su griglia vuota: via diretta chiusa.
        random.seed(1)
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        rows = [[0] * m.grid.width for _ in range(m.grid.height)]
        for y in range(42, 70):
            rows[y][50] = 1
        self.grid = Grid.from_rows(rows)
        self.world = World(self.grid)
        self.match = Match(self.world, m)
        self.sim = Simulation(self.world, DT, self.match)
        self.p = spawn(self.world, Vec2(46.5, 55.5), 0)

    def order(self, x, y):
        self.sim.queue_command(AttackMoveCommand(seq=1, entity_id=self.p.id, x=x, y=y))

    def test_click_on_wall_replaces_previous_destination(self):
        self.order(54.5, 55.5)          # oltre il muro
        for _ in range(3):
            self.sim.step()
        self.order(50.5, 65.5)          # subito dopo, SUL muro
        for _ in range(300):
            self.sim.step()
            self.assertLess(self.p.pos.x, 50.0)     # non va piu' dall'altra parte
        self.assertLess(self.p.pos.dist(Vec2(49.5, 65.5)), 0.6)
        self.assertEqual(self.p.order, "idle")      # arrivato: l'ordine finisce

    def test_blocked_goal_never_follows_old_path(self):
        u = self.p
        self.match._move_towards(u, Vec2(54.5, 55.5), 1.0, use_astar=True)
        self.match._move_towards(u, Vec2(50.5, 65.5), 1.0, use_astar=True)
        self.assertLess(u.path[-1].x, 50.0)
        self.assertGreater(u.path[-1].y, 63.0)


class TestObstaclesAndAir(unittest.TestCase):
    def test_tower_next_to_wall_pushes_out(self):
        # Torre accanto a un muro: la spinta radiale verso il muro non basta, ma
        # l'unita' deve comunque finire fuori dalla torre e fuori dal muro.
        rows = [[0] * 10 for _ in range(10)]
        for y in range(10):
            rows[y][6] = 1
        g = Grid.from_rows(rows)
        u = unit(5.6, 5.0)
        tower = (5.0, 5.0, 0.85)
        resolve_obstacles([u], [tower], g)
        self.assertTrue(g.is_walkable_point(u.pos.x, u.pos.y))
        self.assertGreaterEqual(math.hypot(u.pos.x - 5.0, u.pos.y - 5.0),
                                0.85 + u.radius - 1e-6)

    def test_airborne_ignores_tower_and_units(self):
        g = Grid.empty(10, 10)
        a, b = unit(5.0, 5.0), unit(5.2, 5.0)
        a.air_z = 1.0
        resolve_collisions([a, b], g)
        self.assertEqual((a.pos.x, b.pos.x), (5.0, 5.2))
        resolve_obstacles([a], [(5.0, 5.0, 0.85)], g)
        self.assertEqual((a.pos.x, a.pos.y), (5.0, 5.0))
        a.air_z = 0.0
        resolve_collisions([a, b], g)
        self.assertGreater(b.pos.x - a.pos.x, 0.2)


class TestWallShape(unittest.TestCase):
    def test_shape_active_on_match_maps(self):
        self.assertTrue(map3().grid._shape_on)
        self.assertFalse(Grid.empty(4, 4)._shape_on)

    def test_drawn_protrusions_block_and_cut_corners_pass(self):
        g = map3().grid
        H, W = g.height, g.width
        protrude = cut = 0
        for y in range(H):
            for x in range(W):
                t = g.tiles[y][x]
                for fx in (0.15, 0.5, 0.85):
                    for fy in (0.15, 0.5, 0.85):
                        px, py = x + fx, y + fy
                        wall = t in (TILE_WALL, TILE_JUNGLE_WALL)
                        free = g.is_walkable_point(px, py)
                        if not wall and not free and g.tiles[y][x] != 7:
                            protrude += 1
                        if wall and free:
                            cut += 1
                        # Punto bloccato <=> dentro la sagoma (per i muri).
                        if t not in (4, 7):
                            self.assertEqual(free, not g.shape_blocked(px, py))
        # La sagoma disegnata sporge oltre i tile e arrotonda gli spigoli.
        self.assertGreater(protrude, 0)
        self.assertGreater(cut, 0)

    def test_body_stays_off_drawn_wall(self):
        g = map3().grid
        rng = random.Random(3)
        free_tiles = [(x, y) for y in range(g.height) for x in range(g.width)
                      if g.is_walkable(x, y) and g.shape_near(x + 0.5, y + 0.5, 0.6)]
        self.assertTrue(free_tiles)
        worst = 0.0
        for _ in range(60):
            x, y = rng.choice(free_tiles)
            u = unit(x + 0.5, y + 0.5, 0.35)
            if not g.is_walkable_point(u.pos.x, u.pos.y):
                continue
            ang = rng.random() * math.tau
            u.speed = 3.0
            u.set_path([Vec2(u.pos.x + math.cos(ang) * 4, u.pos.y + math.sin(ang) * 4)])
            for _ in range(60):
                advance_unit(u, DT, g)
                self.assertTrue(g.is_walkable_point(u.pos.x, u.pos.y))
            # Profondita' con cui il corpo entra nella sagoma (campionata).
            for k in range(32):
                a = k * math.tau / 32
                for f in (0.5, 0.7):
                    if g.shape_blocked(u.pos.x + math.cos(a) * 0.35 * f,
                                       u.pos.y + math.sin(a) * 0.35 * f):
                        worst = max(worst, 0.35 * (1 - f))
        self.assertLessEqual(worst, 0.35 * 0.5 + 1e-9)

    def test_waypoints_next_to_drawn_walls_are_reached(self):
        # Il centro di questi tile e' libero ma piu' vicino al muro del raggio del
        # corpo: l'unita' restava incastrata li' per sempre.
        g = map3().grid
        for start, click in (((9.1, 29.3), (6.0, 37.1)), ((42.6, 27.9), (35.9, 32.4)),
                             ((49.9, 96.8), (57.3, 95.2))):
            u = unit(*start)
            u.speed = 3.0
            pts = plan_move(g, start, click)
            u.set_path([Vec2(x, y) for x, y in pts])
            for _ in range(600):
                advance_unit(u, DT, g)
            self.assertFalse(u.path, (start, click, u.pos))
            self.assertLess(u.pos.dist(Vec2(*pts[-1])), 0.05)

    def test_random_moves_almost_never_get_stuck(self):
        g = map3().grid
        rng = random.Random(7)
        total = stuck = 0
        while total < 300:
            p = (rng.uniform(2, g.width - 2), rng.uniform(2, g.height - 2))
            t = (p[0] + rng.uniform(-14, 14), p[1] + rng.uniform(-10, 10))
            if not (0 < t[0] < g.width and 0 < t[1] < g.height) or not g.is_walkable_point(*p):
                continue
            u = unit(*p)
            u.speed = 4.0
            advance_unit(u, 0.0, g)             # parte gia' staccato dai muri
            pts = plan_move(g, (u.pos.x, u.pos.y), t)
            if not pts:
                continue
            total += 1
            u.set_path([Vec2(x, y) for x, y in pts])
            for _ in range(900):
                advance_unit(u, DT, g)
                if not u.path:
                    break
            stuck += bool(u.path)
        self.assertLess(stuck / total, 0.02)   # prima della correzione: oltre il 15%

    def test_no_camp_or_structure_blocked(self):
        m = map3()
        for c in m.camps:
            self.assertTrue(m.grid.is_walkable_point(c["pos"][0] + 0.5, c["pos"][1] + 0.5))
        for s in m.structures:
            self.assertTrue(m.grid.is_walkable(int(s["pos"][0]), int(s["pos"][1])))

    def test_weather_resync_matches_full_rebuild(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        g = m.grid
        ys = [(x, y) for y in range(g.height) for x in range(g.width)
              if g.tiles[y][x] == TILE_JUNGLE_WALL]
        x, y = ys[len(ys) // 2]
        g.tiles[y][x] = 0
        g.is_walkable_point(0.5, 0.5)      # risincronizza (solo la zona cambiata)
        inc = g._shape_np.copy()
        g2 = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json")).grid
        keep = g2._shape_keep
        g2.tiles[y][x] = 0
        object.__setattr__(g2, "_shape_walls", None)
        object.__setattr__(g2, "_shape_bush", None)
        object.__setattr__(g2, "_shape_ver", None)
        g2._shape_sync()
        self.assertIs(g2._shape_keep, keep)
        self.assertTrue((inc == g2._shape_np).all())


if __name__ == "__main__":
    unittest.main()
