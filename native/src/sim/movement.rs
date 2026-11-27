//! World.tick (engine/world.py) on the Rust state: advance_unit for every live
//! unit in order, circle collisions, then the push out of the live towers.
//! Same arithmetic and order as engine/movement.py (wall-shape grid, as on the
//! match maps); the grid helpers are GridView's, shared with the live game.

use super::world::{Ent, World};
use crate::{hypot, GridView, TILE_BUSH, TILE_PILLAR, WALL_R_MAX};

/// config.TOWER_BLOCK_RADIUS
pub const TOWER_BLOCK_RADIUS: f64 = 0.85;

/// The grid as movement sees it: GridView + the tile-centre wall mask
/// (Grid._shape_cen_b) that grid.is_walkable uses.
pub struct MoveGrid<'a> {
    pub gv: &'a GridView,
    pub cen: &'a [u8],
}

impl MoveGrid<'_> {
    /// grid.is_walkable(tx, ty, block_bush) with the shape on.
    fn is_walkable(&self, tx: i64, ty: i64, bb: bool) -> bool {
        let g = self.gv;
        if !(0 <= tx && tx < g.w as i64 && 0 <= ty && ty < g.h as i64) {
            return false;
        }
        let t = g.tile(tx as usize, ty as usize);
        if bb && t == TILE_BUSH {
            return false;
        }
        if t == TILE_PILLAR {
            return false;
        }
        self.cen[ty as usize * g.w + tx as usize] == 0
    }

    /// movement._nearest_walkable
    fn nearest_walkable(&self, px: f64, py: f64, bb: bool) -> Option<(f64, f64)> {
        let (cx, cy) = (px.floor() as i64, py.floor() as i64);
        let mut best: Option<(f64, f64)> = None;
        let mut best_d = 1e18f64;
        for r in 1..8i64 {
            for ty in (cy - r)..=(cy + r) {
                for tx in (cx - r)..=(cx + r) {
                    if (tx - cx).abs().max((ty - cy).abs()) != r || !self.is_walkable(tx, ty, bb) {
                        continue;
                    }
                    // (tx + 0.5 - pos.x) ** 2 + (ty + 0.5 - pos.y) ** 2  (float pow, as CPython)
                    let d = (tx as f64 + 0.5 - px).powf(2.0) + (ty as f64 + 0.5 - py).powf(2.0);
                    if d < best_d {
                        best = Some((tx as f64 + 0.5, ty as f64 + 0.5));
                        best_d = d;
                    }
                }
            }
            if best.is_some() {
                return best;
            }
        }
        None
    }

    #[inline]
    fn keep_r(u: &Ent) -> f64 {
        if u.radius < WALL_R_MAX { u.radius } else { WALL_R_MAX }
    }

    /// movement.advance_unit (grid present, shape on).
    pub fn advance_unit(&self, u: &mut Ent, dt: f64) {
        let bb = u.bush_blocks;
        let ground = u.air_z <= 0.0;
        if ground && !self.gv.walkable_point(u.pos.0, u.pos.1, bb) {
            if let Some(fix) = self.nearest_walkable(u.pos.0, u.pos.1, bb) {
                u.pos = fix;
            }
        }
        let kr = Self::keep_r(u);
        if u.path.is_empty() {
            u.moving = false;
            if ground {
                u.pos = self.gv.keep_off(u.pos.0, u.pos.1, kr, bb);
            }
            return;
        }
        let airborne = u.air_z > 0.0;
        let path = &u.path;
        let (x, y, n, f) = self
            .gv
            .advance_with(u.pos.0, u.pos.1, path.len(), |i| Ok(path[i]), u.speed * dt, bb, airborne, kr)
            .expect("advance on owned waypoints cannot fail");
        if n > 0 {
            u.path.drain(..n);
        }
        if f >= 0 {
            u.facing = f;
        }
        u.pos = (x, y);
        u.moving = !u.path.is_empty();
    }

    /// movement._free_outside
    #[allow(clippy::too_many_arguments)]
    fn free_outside(&self, ox: f64, oy: f64, min_d: f64, ang: f64, bb: bool,
                    others: &[(f64, f64, f64)]) -> Option<(f64, f64)> {
        for extra in [0.0, 0.2, 0.45, 0.75, 1.1, 1.5] {
            let rr = min_d + extra;
            for k in 0..13i64 {
                let sgns: &[i64] = if k == 0 || k == 12 { &[1] } else { &[1, -1] };
                for &sgn in sgns {
                    let a = ang + (sgn * k) as f64 * (std::f64::consts::PI / 12.0);
                    let (x, y) = (ox + a.cos() * rr, oy + a.sin() * rr);
                    if !self.gv.walkable_point(x, y, bb) {
                        continue;
                    }
                    if others.iter().any(|&(qx, qy, qr)| (x - qx).powf(2.0) + (y - qy).powf(2.0) < qr * qr) {
                        continue;
                    }
                    return Some((x, y));
                }
            }
        }
        None
    }

    /// movement.resolve_obstacles on one unit (already known to touch one).
    fn push_out(&self, u: &mut Ent, obstacles: &[(f64, f64, f64)]) {
        if u.air_z > 0.0 {
            return;
        }
        let bb = u.bush_blocks;
        for &(ox, oy, r) in obstacles {
            let (dx, dy) = (u.pos.0 - ox, u.pos.1 - oy);
            let min_d = r + u.radius;
            let d2 = dx * dx + dy * dy;
            if d2 >= min_d * min_d {
                continue;
            }
            let d = d2.sqrt();
            let (nx, ny) = if d > 1e-6 { (dx / d, dy / d) } else { (0.0, 1.0) };
            let mut new = Some((ox + nx * min_d, oy + ny * min_d));
            if !u.path.is_empty() {
                let w = u.path[0];
                if (w.0 - ox).powf(2.0) + (w.1 - oy).powf(2.0) < min_d * min_d {
                    u.path.remove(0);
                }
                if !u.path.is_empty() {
                    let (tx, ty) = (u.path[0].0 - u.pos.0, u.path[0].1 - u.pos.1);
                    let tl = hypot(tx, ty);
                    let (px, py) = (-ny, nx);
                    let side = tx * px + ty * py;
                    if tl > 1e-6 && side.abs() < 0.3 * tl && tx * nx + ty * ny < 0.0 {
                        let sgn = if side > 0.0 || (side.abs() < 1e-6 && u.id % 2 != 0) { 1.0 } else { -1.0 };
                        let (qx, qy) = new.unwrap();
                        new = Some((qx + px * 0.04 * sgn, qy + py * 0.04 * sgn));
                    }
                }
            }
            let (qx, qy) = new.unwrap();
            if !self.gv.walkable_point(qx, qy, bb) {
                let others: Vec<(f64, f64, f64)> =
                    obstacles.iter().copied().filter(|o| o.0 != ox || o.1 != oy).collect();
                new = self.free_outside(ox, oy, min_d, ny.atan2(nx), bb, &others);
            }
            if let Some(p) = new {
                u.pos = p;
            }
        }
    }

    /// Live units (movers) and live towers as obstacles, in entity order.
    fn movers_towers(w: &World) -> (Vec<usize>, Vec<(f64, f64, f64)>) {
        let movers = (0..w.ents.len()).filter(|&i| w.ents[i].kind.is_unit() && w.ents[i].alive).collect();
        let towers = w
            .ents
            .iter()
            .filter(|e| e.kind.is_structure() && e.skind == "tower" && e.alive)
            .map(|e| (e.pos.0, e.pos.1, TOWER_BLOCK_RADIUS))
            .collect();
        (movers, towers)
    }

    /// movement.resolve_collisions on the ground movers; returns the ones that
    /// touch a tower afterwards (World.tick passes them to resolve_obstacles).
    fn collide(&self, w: &mut World, movers: &[usize], towers: &[(f64, f64, f64)]) -> Vec<usize> {
        let ground: Vec<usize> = movers.iter().copied().filter(|&i| w.ents[i].air_z <= 0.0).collect();
        let xs: Vec<f64> = ground.iter().map(|&i| w.ents[i].pos.0).collect();
        let ys: Vec<f64> = ground.iter().map(|&i| w.ents[i].pos.1).collect();
        let rs: Vec<f64> = ground.iter().map(|&i| w.ents[i].radius).collect();
        let ids: Vec<i64> = ground.iter().map(|&i| w.ents[i].id).collect();
        let bbs: Vec<bool> = ground.iter().map(|&i| w.ents[i].bush_blocks).collect();
        let (nx, ny) = self.gv.resolve_collisions(xs, ys, rs.clone(), ids, bbs, 2);
        let mut hits = Vec::new();
        for (j, &i) in ground.iter().enumerate() {
            w.ents[i].pos = (nx[j], ny[j]);
            for &(ox, oy, r) in towers {
                let (dx, dy) = (nx[j] - ox, ny[j] - oy);
                let min_d = r + rs[j];
                if dx * dx + dy * dy < min_d * min_d {
                    hits.push(i);
                    break;
                }
            }
        }
        hits
    }

    /// World.tick(dt).
    pub fn world_tick(&self, w: &mut World, dt: f64) {
        self.world_tick_timed(w, dt, None);
    }

    /// World.tick(dt); with `t` adds the ns of each phase (advance, collisions,
    /// towers) to it.
    pub fn world_tick_timed(&self, w: &mut World, dt: f64, mut t: Option<&mut [u128; 3]>) {
        let c0 = std::time::Instant::now();
        let (movers, towers) = Self::movers_towers(w);
        for &i in &movers {
            self.advance_unit(&mut w.ents[i], dt);
        }
        let c1 = std::time::Instant::now();
        let hits = self.collide(w, &movers, &towers);
        let c2 = std::time::Instant::now();
        if !towers.is_empty() {
            for i in hits {
                self.push_out(&mut w.ents[i], &towers);
            }
        }
        if let Some(t) = t.as_deref_mut() {
            t[0] += (c1 - c0).as_nanos();
            t[1] += (c2 - c1).as_nanos();
            t[2] += c2.elapsed().as_nanos();
        }
    }
}
