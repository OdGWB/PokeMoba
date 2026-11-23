//! Optional Rust acceleration for the PokeMoba engine.
//!
//! Every function here reproduces, bit for bit, the pure-Python code it replaces
//! (engine/grid.py, engine/movement.py, engine/spatial.py): same samples, same
//! visiting order, same floating-point operations. The engine falls back to the
//! Python code when this module is missing, so it must never change a result.

use pyo3::intern;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::{HashMap, HashSet};

const TILE_BUSH: u8 = 4;
const TILE_PILLAR: u8 = 7;
const RES: usize = 8; // fine cells per tile (engine/wall_shape.RES)
const WALL_R_MAX: f64 = 0.42; // movement._WALL_R_MAX
const SHAPE_FRACS: [f64; 5] = [0.2, 0.4, 0.6, 0.8, 1.0];
const ARRIVE_EPS: f64 = 0.02; // movement._ARRIVE_EPS

// ---------------------------------------------------------------------------
// math.hypot, exactly as CPython's vector_norm (Modules/mathmodule.c, 3.10+).

#[inline]
fn dl_mul(x: f64, y: f64) -> (f64, f64) {
    let z = x * y;
    (z, x.mul_add(y, -z))
}

#[inline]
fn dl_fast_sum(a: f64, b: f64) -> (f64, f64) {
    let x = a + b;
    let z = x - a;
    (x, b - z)
}

fn vector_norm(vec: &mut [f64], max: f64) -> f64 {
    if max.is_infinite() {
        return max;
    }
    if vec.iter().any(|v| v.is_nan()) {
        return f64::NAN;
    }
    if max == 0.0 || vec.len() <= 1 {
        return max;
    }
    let max_e = frexp_exp(max);
    if max_e < -1023 {
        for v in vec.iter_mut() {
            *v /= f64::MIN_POSITIVE;
        }
        return f64::MIN_POSITIVE * vector_norm(vec, max / f64::MIN_POSITIVE);
    }
    let scale = ldexp1(-max_e);
    let (mut csum, mut frac1, mut frac2) = (1.0f64, 0.0f64, 0.0f64);
    for &v in vec.iter() {
        let x = v * scale;
        let pr = dl_mul(x, x);
        let sm = dl_fast_sum(csum, pr.0);
        csum = sm.0;
        frac1 += pr.1;
        frac2 += sm.1;
    }
    let mut h = (csum - 1.0 + (frac1 + frac2)).sqrt();
    let pr = dl_mul(-h, h);
    let sm = dl_fast_sum(csum, pr.0);
    csum = sm.0;
    frac1 += pr.1;
    frac2 += sm.1;
    let x = csum - 1.0 + (frac1 + frac2);
    h += x / (2.0 * h);
    h / scale
}

/// Exponent e of frexp(v) (v = m * 2^e, 0.5 <= m < 1), v finite and > 0.
fn frexp_exp(v: f64) -> i32 {
    let bits = v.to_bits();
    let exp = ((bits >> 52) & 0x7ff) as i32;
    if exp == 0 {
        // subnormal
        let mant = bits & ((1u64 << 52) - 1);
        let lz = mant.leading_zeros() as i32 - 12; // zeros inside the 52-bit field
        -1022 - lz
    } else {
        exp - 1022
    }
}

/// 2^e as f64 (exact, subnormal results included).
fn ldexp1(e: i32) -> f64 {
    if e >= -1022 {
        f64::from_bits(((e + 1023) as u64) << 52)
    } else {
        f64::from_bits(1u64 << (e + 1074))
    }
}

#[inline]
fn hypot(x: f64, y: f64) -> f64 {
    let (ax, ay) = (x.abs(), y.abs());
    let mut v = [ax, ay];
    // CPython: max over the abs values; NaN handled inside.
    let m = if ay > ax { ay } else { ax };
    vector_norm(&mut v, m)
}

#[pyfunction]
fn py_hypot(x: f64, y: f64) -> f64 {
    hypot(x, y)
}

// ---------------------------------------------------------------------------

/// Read-only snapshot of a Grid with the wall shape on (Grid._shape_on True).
#[pyclass(frozen)]
struct GridView {
    w: usize,
    h: usize,
    tiles: Vec<u8>,     // row-major [y * w + x]
    fine: Vec<u8>,      // _shape_b: (h*8) x (w*8)
    any_t: Vec<u8>,     // _shape_any_b: per tile
    dirs: Vec<(f64, f64)>, // movement._SHAPE_DIRS (computed in Python: same libm)
    steer: Vec<(f64, f64)>, // cos/sin of movement._STEER_ANGLES (computed in Python)
    dir_unit: [(f64, f64); 8], // vec._DIR_UNIT
}

/// Result of movement._slide.
enum Slide {
    Same,           // returned nxt itself (`moved is target`)
    Axis(f64, f64), // slid along one axis
    Blocked,        // None
}

impl GridView {
    #[inline]
    fn tile(&self, x: usize, y: usize) -> u8 {
        self.tiles[y * self.w + x]
    }

    #[inline]
    fn in_bounds_f(&self, px: f64, py: f64) -> bool {
        0.0 <= px && px < self.w as f64 && 0.0 <= py && py < self.h as f64
    }

    #[inline]
    fn fine_at(&self, px: f64, py: f64) -> bool {
        let fy = (py * 8.0) as usize;
        let fx = (px * 8.0) as usize;
        self.fine[fy * self.w * RES + fx] != 0
    }

    #[inline]
    fn walkable_point(&self, px: f64, py: f64, bb: bool) -> bool {
        if !self.in_bounds_f(px, py) {
            return false;
        }
        let t = self.tile(px as usize, py as usize);
        if t == TILE_PILLAR || (bb && t == TILE_BUSH) {
            return false;
        }
        !self.fine_at(px, py)
    }

    #[inline]
    fn blocked(&self, px: f64, py: f64) -> bool {
        self.in_bounds_f(px, py) && self.fine_at(px, py)
    }

    fn near(&self, px: f64, py: f64, r: f64) -> bool {
        let (w, h) = (self.w as i64, self.h as i64);
        let x0 = ((px - r).floor() as i64).max(0);
        let x1 = ((px + r).floor() as i64).min(w - 1);
        let y0 = ((py - r).floor() as i64).max(0);
        let y1 = ((py + r).floor() as i64).min(h - 1);
        let mut ty = y0;
        while ty <= y1 {
            let mut tx = x0;
            while tx <= x1 {
                if self.any_t[(ty * w + tx) as usize] != 0 {
                    return true;
                }
                tx += 1;
            }
            ty += 1;
        }
        false
    }

    fn los(&self, ax: f64, ay: f64, bx: f64, by: f64, bb: bool) -> bool {
        let (dx, dy) = (bx - ax, by - ay);
        let dist = hypot(dx, dy);
        if dist < 1e-9 {
            return self.walkable_point(ax, ay, bb);
        }
        let steps = (dist * 4.0) as i64 + 1;
        let sf = steps as f64;
        let fw = self.w * RES;
        for i in 0..=steps {
            let t = i as f64 / sf;
            let x = ax + dx * t;
            let y = ay + dy * t;
            if !self.in_bounds_f(x, y) {
                return false;
            }
            if self.fine[(y * 8.0) as usize * fw + (x * 8.0) as usize] != 0 {
                return false;
            }
            let tt = self.tile(x as usize, y as usize);
            if tt == TILE_PILLAR || (bb && tt == TILE_BUSH) {
                return false;
            }
        }
        true
    }

    fn shape_push(&self, px: f64, py: f64, r: f64) -> Option<(f64, f64)> {
        if self.blocked(px, py) {
            return None;
        }
        let (mut sx, mut sy, mut deep) = (0.0f64, 0.0f64, 0.0f64);
        for &(c, s) in self.dirs.iter() {
            for &f in SHAPE_FRACS.iter() {
                if self.blocked(px + c * r * f, py + s * r * f) {
                    let d = r * (1.0 - f) + 0.2 * r;
                    sx -= c * d;
                    sy -= s * d;
                    if d > deep {
                        deep = d;
                    }
                    break;
                }
            }
        }
        if deep <= 0.0 {
            return None;
        }
        let n = hypot(sx, sy);
        if n < 1e-9 {
            return None;
        }
        Some((px + sx / n * deep, py + sy / n * deep))
    }

    /// movement._keep_off_walls with the shape on; r already = min(radius, 0.42).
    fn keep_off(&self, px0: f64, py0: f64, r: f64, bb: bool) -> (f64, f64) {
        let (mut px, mut py) = (px0, py0);
        let cx = px.floor() as i64;
        let cy = py.floor() as i64;
        let (w, h) = (self.w as i64, self.h as i64);
        for _ in 0..2 {
            let mut moved = false;
            for ty in (cy - 1)..(cy + 2) {
                for tx in (cx - 1)..(cx + 2) {
                    if 0 <= tx && tx < w && 0 <= ty && ty < h {
                        let t = self.tile(tx as usize, ty as usize);
                        if !(t == TILE_PILLAR || (bb && t == TILE_BUSH)) {
                            continue;
                        }
                    }
                    let (txf, tyf) = (tx as f64, ty as f64);
                    // min(max(px, tx), tx + 1): equal values whichever side wins.
                    let qx = px.max(txf).min(txf + 1.0);
                    let qy = py.max(tyf).min(tyf + 1.0);
                    let (dx, dy) = (px - qx, py - qy);
                    let d2 = dx * dx + dy * dy;
                    if d2 >= r * r || d2 < 1e-12 {
                        continue;
                    }
                    let d = d2.sqrt();
                    let k = (r - d) / d;
                    let (nx, ny) = (px + dx * k, py + dy * k);
                    if self.walkable_point(nx, ny, bb) {
                        px = nx;
                        py = ny;
                        moved = true;
                    }
                }
            }
            if self.near(px, py, r) {
                if let Some((nx, ny)) = self.shape_push(px, py, r) {
                    if self.walkable_point(nx, ny, bb) {
                        px = nx;
                        py = ny;
                        moved = true;
                    }
                }
            }
            if !moved {
                break;
            }
        }
        (px, py)
    }

    /// movement._in_pillar (tile_at is TILE_WALL out of bounds).
    #[inline]
    fn in_pillar(&self, px: f64, py: f64) -> bool {
        let (x, y) = (px.floor(), py.floor());
        if !(x >= 0.0 && y >= 0.0 && x < self.w as f64 && y < self.h as f64) {
            return false;
        }
        self.tile(x as usize, y as usize) == TILE_PILLAR
    }

    /// vec.direction_index.
    fn direction_index(&self, dx: f64, dy: f64) -> i64 {
        if dx == 0.0 && dy == 0.0 {
            return 0;
        }
        let inv = 1.0 / hypot(dx, dy);
        let (nx, ny) = (dx * inv, dy * inv);
        let (mut best_i, mut best_dot) = (0i64, -2.0f64);
        for (i, &(ux, uy)) in self.dir_unit.iter().enumerate() {
            let d = nx * ux + ny * uy;
            if d > best_dot {
                best_dot = d;
                best_i = i as i64;
            }
        }
        best_i
    }

    /// movement._steer.
    fn steer(&self, px: f64, py: f64, sx: f64, sy: f64) -> Option<(f64, f64)> {
        for &(ca, sa) in self.steer.iter() {
            let ax = px + (sx * ca - sy * sa);
            let ay = py + (sx * sa + sy * ca);
            if !self.in_pillar(ax, ay) && self.walkable_point(ax, ay, false) {
                return Some((ax, ay));
            }
        }
        None
    }

    /// movement._slide.
    fn slide(&self, px: f64, py: f64, nx: f64, ny: f64, bb: bool) -> Slide {
        if self.walkable_point(nx, ny, bb)
            && (px.floor() == nx.floor() || py.floor() == ny.floor()
                || self.walkable_point(nx, py, bb) || self.walkable_point(px, ny, bb)) {
            return Slide::Same;
        }
        let (ax, ay) = ((nx, py), (px, ny));
        let cand = if (nx - px).abs() >= (ny - py).abs() { [ax, ay] } else { [ay, ax] };
        for (cx, cy) in cand {
            if (cx != px || cy != py) && self.walkable_point(cx, cy, bb) {
                return Slide::Axis(cx, cy);
            }
        }
        Slide::Blocked
    }

    /// movement._move_out (+ _keep_off_walls) on index i.
    #[inline]
    fn move_out(&self, xs: &mut [f64], ys: &mut [f64], i: usize, ox: f64, oy: f64,
                kr: f64, bb: bool) {
        let nx = xs[i] + ox;
        let ny = ys[i] + oy;
        if self.walkable_point(nx, ny, bb) {
            let (px, py) = self.keep_off(nx, ny, kr, bb);
            xs[i] = px;
            ys[i] = py;
        }
    }
}

#[inline]
fn cell_key(x: f64, y: f64) -> (i64, i64) {
    // SpatialHash._key with cell_size 2.0 (inv = 0.5, exact).
    ((x * 0.5).floor() as i64, (y * 0.5).floor() as i64)
}

#[pymethods]
impl GridView {
    #[new]
    fn new(w: usize, h: usize, tiles: Vec<u8>, fine: Vec<u8>, any_t: Vec<u8>,
           dirs: Vec<(f64, f64)>, steer: Vec<(f64, f64)>) -> PyResult<Self> {
        if tiles.len() != w * h || any_t.len() != w * h || fine.len() != w * h * RES * RES {
            return Err(pyo3::exceptions::PyValueError::new_err("GridView: bad buffer sizes"));
        }
        // vec._DIR_UNIT = [Vec2(dx, dy).normalized() for DIR_VECTORS]
        let raw: [(f64, f64); 8] = [(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (1.0, -1.0),
                                    (0.0, -1.0), (-1.0, -1.0), (-1.0, 0.0), (-1.0, 1.0)];
        let mut dir_unit = [(0.0, 0.0); 8];
        for (i, &(x, y)) in raw.iter().enumerate() {
            let l = hypot(x, y);
            dir_unit[i] = (x / l, y / l);
        }
        Ok(GridView { w, h, tiles, fine, any_t, dirs, steer, dir_unit })
    }

    /// direction_index (for tests against vec.direction_index).
    fn direction_index_py(&self, dx: f64, dy: f64) -> i64 {
        self.direction_index(dx, dy)
    }

    /// The waypoint loop of movement.advance_unit (grid present, shape on).
    /// path: list of Vec2 (read, not modified). Returns (x, y, waypoints
    /// consumed, last facing or -1). keep_r = min(radius, 0.42) for the final
    /// _keep_off_walls (skipped in the air).
    #[allow(clippy::too_many_arguments)]
    fn advance(&self, px0: f64, py0: f64, path: &Bound<'_, PyList>, budget0: f64,
               bb: bool, airborne: bool, keep_r: f64) -> PyResult<(f64, f64, usize, i64)> {
        let pyh = path.py();
        let (kx, ky) = (intern!(pyh, "x"), intern!(pyh, "y"));
        let n = path.len();
        let (mut px, mut py) = (px0, py0);
        let mut budget = budget0;
        let mut i = 0usize;
        let mut facing = -1i64;
        let blocked = |x: f64, y: f64| !airborne && !self.walkable_point(x, y, bb);
        while budget > 1e-9 && i < n {
            let t = path.get_item(i)?;
            let tx: f64 = t.getattr(kx)?.extract()?;
            let ty: f64 = t.getattr(ky)?.extract()?;
            let (tox, toy) = (tx - px, ty - py);
            let d = hypot(tox, toy);
            // Vec2.normalized
            let (ux, uy) = if d < 1e-9 { (0.0, 0.0) } else { (tox / d, toy / d) };
            if d > ARRIVE_EPS {
                let m = if d < budget { d } else { budget };
                let (sx, sy) = (ux * m, uy * m);
                let (qx, qy) = (px + sx, py + sy);
                let step_in = self.in_pillar(qx, qy);
                if step_in || self.in_pillar(tx, ty) {
                    let alt = if step_in { self.steer(px, py, sx, sy) } else { Some((qx, qy)) };
                    if let Some((ax, ay)) = alt {
                        if !blocked(ax, ay) {
                            px = ax;
                            py = ay;
                        }
                    }
                    facing = self.direction_index(tox, toy);
                    break;
                }
            }
            if d <= ARRIVE_EPS {
                if blocked(tx, ty) {
                    break;
                }
                px = tx;
                py = ty;
                i += 1;
                continue;
            }
            if d <= budget {
                if blocked(tx, ty) {
                    break;
                }
                if !airborne {
                    match self.slide(px, py, tx, ty, bb) {
                        Slide::Blocked => break,
                        Slide::Axis(mx, my) => {
                            px = mx;
                            py = my;
                            facing = self.direction_index(tox, toy);
                            break;
                        }
                        Slide::Same => {}
                    }
                }
                px = tx;
                py = ty;
                budget -= d;
                facing = self.direction_index(tox, toy);
                i += 1;
            } else {
                let (mut nx, mut ny) = (px + ux * budget, py + uy * budget);
                if !airborne {
                    match self.slide(px, py, nx, ny, bb) {
                        Slide::Blocked => {
                            facing = self.direction_index(tox, toy);
                            break;
                        }
                        Slide::Axis(mx, my) => {
                            nx = mx;
                            ny = my;
                        }
                        Slide::Same => {}
                    }
                }
                px = nx;
                py = ny;
                facing = self.direction_index(tox, toy);
                break;
            }
        }
        if !airborne {
            let (qx, qy) = self.keep_off(px, py, keep_r, bb);
            px = qx;
            py = qy;
        }
        Ok((px, py, i, facing))
    }

    /// The whole movement.advance_unit (grid present, shape on), reading and
    /// writing the unit's attributes. Returns False (nothing changed) when the
    /// unit stands inside a wall on the ground: Python then runs its own path
    /// (anti-stuck search + loop).
    fn step_unit(&self, unit: &Bound<'_, PyAny>, dt: f64, vec2: &Bound<'_, PyAny>) -> PyResult<bool> {
        let py = unit.py();
        let bb = attr_truthy(unit, intern!(py, "bush_blocks"));
        let air_z: f64 = match unit.getattr(intern!(py, "air_z")) {
            Ok(v) => v.extract()?,
            Err(_) => 0.0,
        };
        let (px, py0) = pos_of(unit)?;
        let ground = air_z <= 0.0;
        if ground && !self.walkable_point(px, py0, bb) {
            return Ok(false);
        }
        let path_any = unit.getattr(intern!(py, "path"))?;
        let path = match path_any.cast::<PyList>() {
            Ok(l) => l.clone(),
            Err(_) => return Ok(false),
        };
        let keep_r: f64 = match unit.getattr(intern!(py, "radius")) {
            Ok(v) => {
                let r: f64 = v.extract()?;
                if r < WALL_R_MAX { r } else { WALL_R_MAX }
            }
            Err(_) => 0.35,
        };
        let kpos = intern!(py, "pos");
        if path.len() == 0 {
            unit.setattr(intern!(py, "moving"), false)?;
            if ground {
                let (qx, qy) = self.keep_off(px, py0, keep_r, bb);
                if qx != px || qy != py0 {
                    unit.setattr(kpos, vec2.call1((qx, qy))?)?;
                }
            }
            return Ok(true);
        }
        let airborne = air_z > 0.0;
        let speed: f64 = unit.getattr(intern!(py, "speed"))?.extract()?;
        let (x, y, n, f) = self.advance(px, py0, &path, speed * dt, bb, airborne, keep_r)?;
        if n > 0 {
            path.del_slice(0, n)?;
        }
        if f >= 0 {
            unit.setattr(intern!(py, "facing"), f)?;
        }
        if x != px || y != py0 {
            unit.setattr(kpos, vec2.call1((x, y))?)?;
        }
        unit.setattr(intern!(py, "moving"), path.len() > 0)?;
        Ok(true)
    }

    #[pyo3(signature = (px, py, bb=false))]
    fn is_walkable_point(&self, px: f64, py: f64, bb: bool) -> bool {
        self.walkable_point(px, py, bb)
    }

    fn shape_blocked(&self, px: f64, py: f64) -> bool {
        self.blocked(px, py)
    }

    fn shape_near(&self, px: f64, py: f64, r: f64) -> bool {
        self.near(px, py, r)
    }

    #[pyo3(signature = (ax, ay, bx, by, bb=false))]
    fn line_of_sight(&self, ax: f64, ay: f64, bx: f64, by: f64, bb: bool) -> bool {
        self.los(ax, ay, bx, by, bb)
    }

    fn keep_off_walls(&self, px: f64, py: f64, r: f64, bb: bool) -> (f64, f64) {
        self.keep_off(px, py, r, bb)
    }

    /// movement.resolve_collisions (units already filtered: not in the air).
    /// Returns the new positions; the caller writes back the changed ones.
    fn resolve_collisions(&self, mut xs: Vec<f64>, mut ys: Vec<f64>, rs: Vec<f64>,
                          ids: Vec<i64>, bbs: Vec<bool>, iterations: usize)
                          -> (Vec<f64>, Vec<f64>) {
        let n = xs.len();
        let kr: Vec<f64> = rs.iter().map(|&r| if WALL_R_MAX < r { WALL_R_MAX } else { r }).collect();
        let mut cells: HashMap<(i64, i64), Vec<usize>> = HashMap::new();
        let mut nb: Vec<usize> = Vec::with_capacity(64);
        let mut seen: HashSet<(i64, i64)> = HashSet::new();
        for _ in 0..iterations {
            for v in cells.values_mut() {
                v.clear();
            }
            for i in 0..n {
                cells.entry(cell_key(xs[i], ys[i])).or_default().push(i);
            }
            seen.clear();
            for a in 0..n {
                let (kx, ky) = cell_key(xs[a], ys[a]);
                nb.clear();
                for dy in -1..=1i64 {
                    for dx in -1..=1i64 {
                        if let Some(b) = cells.get(&(kx + dx, ky + dy)) {
                            nb.extend_from_slice(b);
                        }
                    }
                }
                for j in 0..nb.len() {
                    let b = nb[j];
                    if b == a {
                        continue;
                    }
                    let pair = if ids[a] < ids[b] { (ids[a], ids[b]) } else { (ids[b], ids[a]) };
                    if !seen.insert(pair) {
                        continue;
                    }
                    let ddx = xs[b] - xs[a];
                    let ddy = ys[b] - ys[a];
                    let dist = hypot(ddx, ddy);
                    let min_dist = rs[a] + rs[b];
                    if dist >= min_dist {
                        continue;
                    }
                    if dist < 1e-6 {
                        let px = min_dist * 0.5;
                        self.move_out(&mut xs, &mut ys, a, -px, -0.0, kr[a], bbs[a]);
                        self.move_out(&mut xs, &mut ys, b, px, 0.0, kr[b], bbs[b]);
                        continue;
                    }
                    let overlap = (min_dist - dist) * 0.5;
                    // Vec2.normalized (dist >= 1e-6 > 1e-9 here).
                    let (nx, ny) = (ddx / dist, ddy / dist);
                    let neg = -overlap;
                    self.move_out(&mut xs, &mut ys, a, nx * neg, ny * neg, kr[a], bbs[a]);
                    self.move_out(&mut xs, &mut ys, b, nx * overlap, ny * overlap, kr[b], bbs[b]);
                }
            }
        }
        (xs, ys)
    }
}

// ---------------------------------------------------------------------------

/// engine/spatial.SpatialHash: same cells, same bucket and visiting order.
#[pyclass(module = "pokemoba_native")]
struct SpatialHash {
    #[pyo3(get)]
    cell_size: f64,
    cells: HashMap<(i64, i64), Vec<Py<PyAny>>>,
}

impl SpatialHash {
    #[inline]
    fn key(&self, x: f64, y: f64) -> (i64, i64) {
        let inv = 1.0 / self.cell_size;
        ((x * inv).floor() as i64, (y * inv).floor() as i64)
    }
}

fn pos_of(e: &Bound<'_, PyAny>) -> PyResult<(f64, f64)> {
    let py = e.py();
    let p = e.getattr(intern!(py, "pos"))?;
    Ok((p.getattr(intern!(py, "x"))?.extract()?, p.getattr(intern!(py, "y"))?.extract()?))
}

#[pymethods]
impl SpatialHash {
    #[new]
    #[pyo3(signature = (cell_size=2.0))]
    fn new(cell_size: f64) -> Self {
        SpatialHash { cell_size, cells: HashMap::new() }
    }

    fn _key(&self, x: f64, y: f64) -> (i64, i64) {
        self.key(x, y)
    }

    fn rebuild(&mut self, entities: &Bound<'_, PyAny>) -> PyResult<()> {
        for v in self.cells.values_mut() {
            v.clear();
        }
        for e in entities.try_iter()? {
            let e = e?;
            let (x, y) = pos_of(&e)?;
            let k = self.key(x, y);
            self.cells.entry(k).or_default().push(e.unbind());
        }
        Ok(())
    }

    fn query_radius<'py>(&self, py: Python<'py>, x: f64, y: f64, radius: f64)
                         -> PyResult<Bound<'py, PyList>> {
        let inv = 1.0 / self.cell_size;
        let cx0 = ((x - radius) * inv).floor() as i64;
        let cy0 = ((y - radius) * inv).floor() as i64;
        let cx1 = ((x + radius) * inv).floor() as i64;
        let cy1 = ((y + radius) * inv).floor() as i64;
        let out = PyList::empty(py);
        for cy in cy0..=cy1 {
            for cx in cx0..=cx1 {
                if let Some(b) = self.cells.get(&(cx, cy)) {
                    for e in b {
                        out.append(e.bind(py))?;
                    }
                }
            }
        }
        Ok(out)
    }

    fn neighbors<'py>(&self, entity: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyList>> {
        let py = entity.py();
        let (x, y) = pos_of(entity)?;
        let (kx, ky) = self.key(x, y);
        let out = PyList::empty(py);
        for dy in -1..=1i64 {
            for dx in -1..=1i64 {
                if let Some(b) = self.cells.get(&(kx + dx, ky + dy)) {
                    for e in b {
                        out.append(e.bind(py))?;
                    }
                }
            }
        }
        Ok(out)
    }
}

/// Prefilter of movement.resolve_obstacles: indices of the (non-flying) units whose
/// body overlaps at least one obstacle circle, with the same float operations.
/// Units not listed are left untouched by the Python loop, so it can skip them.
#[pyfunction]
fn obstacle_hits(units: &Bound<'_, PyList>, obstacles: Vec<(f64, f64, f64)>) -> PyResult<Vec<usize>> {
    let py = units.py();
    let mut out = Vec::new();
    for (i, u) in units.iter().enumerate() {
        if let Ok(z) = u.getattr(intern!(py, "air_z")) {
            let z: f64 = z.extract().unwrap_or(0.0);
            if z > 0.0 {
                continue;
            }
        }
        let (x, y) = pos_of(&u)?;
        let rad: f64 = u.getattr(intern!(py, "radius"))?.extract()?;
        for &(ox, oy, r) in &obstacles {
            let dx = x - ox;
            let dy = y - oy;
            let min_d = r + rad;
            let d2 = dx * dx + dy * dy;
            if d2 < min_d * min_d {
                out.push(i);
                break;
            }
        }
    }
    Ok(out)
}

/// Walkability grid of pathfinding.find_path (flat, with a non-walkable border).
#[pyclass(module = "pokemoba_native")]
struct WalkGrid {
    walk: Vec<u8>,
    stride: i64,
}

#[derive(PartialEq)]
struct OpenNode {
    f: f64,
    counter: u64,
    id: i64,
    x: i64,
    y: i64,
}
impl Eq for OpenNode {}
impl PartialOrd for OpenNode {
    fn partial_cmp(&self, o: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for OpenNode {
    // Reversed: BinaryHeap is a max-heap, heapq a min-heap on (f, counter).
    fn cmp(&self, o: &Self) -> std::cmp::Ordering {
        o.f.partial_cmp(&self.f).unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| o.counter.cmp(&self.counter))
    }
}

#[pymethods]
impl WalkGrid {
    #[new]
    fn new(walk: Vec<u8>, stride: i64) -> Self {
        WalkGrid { walk, stride }
    }

    /// Same A* as pathfinding.find_path (neighbour order, costs, octile
    /// heuristic, (f, counter) tie-break, no corner cutting). None = unreachable.
    fn find_path(&self, sx: i64, sy: i64, gx: i64, gy: i64) -> Option<Vec<(i64, i64)>> {
        let stride = self.stride;
        let walk = &self.walk;
        let n = walk.len();
        let sq2 = 2.0f64.sqrt();
        let sq2m2 = sq2 - 2.0;
        let nbrs: [(i64, i64, f64); 8] = [
            (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
            (1, 1, sq2), (1, -1, sq2), (-1, 1, sq2), (-1, -1, sq2),
        ];
        let s_id = (sy + 1) * stride + sx + 1;
        let g_id = (gy + 1) * stride + gx + 1;
        let mut g_score = vec![f64::INFINITY; n];
        let mut came = vec![-1i64; n];
        let mut closed = vec![false; n];
        let mut heap = std::collections::BinaryHeap::new();
        g_score[s_id as usize] = 0.0;
        heap.push(OpenNode { f: 0.0, counter: 0, id: s_id, x: sx, y: sy });
        let mut counter: u64 = 0;
        while let Some(OpenNode { id: cur, x: cx, y: cy, .. }) = heap.pop() {
            if cur == g_id {
                let mut path = vec![(cx, cy)];
                let mut c = cur;
                while came[c as usize] >= 0 {
                    c = came[c as usize];
                    let (yy, xx) = (c.div_euclid(stride), c.rem_euclid(stride));
                    path.push((xx - 1, yy - 1));
                }
                path.reverse();
                return Some(path);
            }
            let cu = cur as usize;
            if closed[cu] {
                continue;
            }
            closed[cu] = true;
            let g_cur = g_score[cu];
            for &(dx, dy, cost) in &nbrs {
                let nb = cur + dy * stride + dx;
                let nbu = nb as usize;
                if walk[nbu] == 0 {
                    continue;
                }
                if dx != 0 && dy != 0
                    && (walk[(cur + dx) as usize] == 0 || walk[(cur + dy * stride) as usize] == 0) {
                    continue;
                }
                if closed[nbu] {
                    continue;
                }
                let tentative = g_cur + cost;
                if tentative < g_score[nbu] {
                    came[nbu] = cur;
                    g_score[nbu] = tentative;
                    let nx = cx + dx;
                    let ny = cy + dy;
                    let hx = (nx - gx).abs();
                    let hy = (ny - gy).abs();
                    let m = if hx < hy { hx } else { hy };
                    let f = tentative + (((hx + hy) as f64) + sq2m2 * (m as f64));
                    counter += 1;
                    heap.push(OpenNode { f, counter, id: nb, x: nx, y: ny });
                }
            }
        }
        None
    }
}

/// Entity scan of tier_sim.FastVision.update (no reveals): builds the same
/// signature (sources' (id, x, y, vision), invisible / agitated foes), compares
/// it with the previous one of the team and, if changed, returns the sources and
/// the foes that stand inside a source's vision circle and are not invisible
/// (the bush rule stays in Python). None = signature unchanged.
#[pyclass(module = "pokemoba_native")]
struct VisionScan {
    prev: HashMap<i64, Vec<(u8, i64, i64, i64, i64)>>,
}

fn attr_truthy(e: &Bound<'_, PyAny>, name: &Bound<'_, pyo3::types::PyString>) -> bool {
    match e.getattr(name) {
        Ok(v) => v.is_truthy().unwrap_or(false),
        Err(_) => false,
    }
}

#[pymethods]
impl VisionScan {
    #[new]
    fn new() -> Self {
        VisionScan { prev: HashMap::new() }
    }

    fn reset(&mut self, team: i64) {
        self.prev.remove(&team);
    }

    fn scan<'py>(&mut self, entities: &Bound<'py, PyAny>, team: &Bound<'py, PyAny>,
                 unit_cls: &Bound<'py, PyAny>, struct_cls: &Bound<'py, PyAny>)
                 -> PyResult<Option<(Vec<Bound<'py, PyAny>>, Vec<Bound<'py, PyAny>>)>> {
        let py = entities.py();
        let team_i: i64 = team.extract()?;
        let (k_team, k_alive, k_vision, k_id) =
            (intern!(py, "team"), intern!(py, "alive"), intern!(py, "vision"), intern!(py, "id"));
        let (k_inv, k_agi) = (intern!(py, "invisible"), intern!(py, "agitated"));
        let mut sig: Vec<(u8, i64, i64, i64, i64)> = Vec::new();
        let mut sources = Vec::new();
        let mut keys: Vec<(i64, i64, i64)> = Vec::new();
        let mut foes = Vec::new();
        let mut foe_xy: Vec<(i64, i64)> = Vec::new();
        for e in entities.try_iter()? {
            let e = e?;
            let t = e.getattr(k_team).ok();
            let own = match &t {
                None => true,
                Some(t) => t.eq(team)?,
            };
            if own {
                if t.is_some() && attr_truthy(&e, k_alive)
                    && (e.is_instance(unit_cls)? || e.is_instance(struct_cls)?) {
                    let v: f64 = match e.getattr(k_vision) {
                        Ok(v) => v.extract()?,
                        Err(_) => 0.0,
                    };
                    if v > 0.0 {
                        let id: i64 = e.getattr(k_id)?.extract()?;
                        let (x, y) = pos_of(&e)?;
                        let key = (x.trunc() as i64, y.trunc() as i64, v.trunc() as i64);
                        sig.push((0, id, key.0, key.1, key.2));
                        keys.push(key);
                        sources.push(e);
                    }
                }
                continue;
            }
            if attr_truthy(&e, k_inv) {
                let id: i64 = e.getattr(k_id)?.extract()?;
                sig.push((1, id, 0, 0, 0));
            }
            if attr_truthy(&e, k_agi) {
                let id: i64 = e.getattr(k_id)?.extract()?;
                let (x, y) = pos_of(&e)?;
                sig.push((2, id, x.trunc() as i64, y.trunc() as i64, 0));
            }
            if e.is_instance(unit_cls)? && attr_truthy(&e, k_alive) {
                let (x, y) = pos_of(&e)?;
                foe_xy.push((x.trunc() as i64, y.trunc() as i64));
                foes.push(e);
            }
        }
        sig.sort_unstable();
        sig.dedup();
        if self.prev.get(&team_i) == Some(&sig) {
            return Ok(None);
        }
        self.prev.insert(team_i, sig);
        let mut seen = Vec::new();
        if !keys.is_empty() {
            for (u, &(ux, uy)) in foes.into_iter().zip(foe_xy.iter()) {
                let inside = keys.iter().any(|&(kx, ky, kv)| {
                    (ux - kx) * (ux - kx) + (uy - ky) * (uy - ky) <= kv * kv
                });
                if inside && !attr_truthy(&u, k_inv) {
                    seen.push(u);
                }
            }
        }
        Ok(Some((sources, seen)))
    }
}

// ---------------------------------------------------------------------------
// IA dei minion (engine/match.py: _ai_minion, _valid_minion_target,
// _acquire_minion_target, _within_attack, _chase, _follow_lane, _move_towards).
// Stesse letture, stesse scritture, stesso ordine; il ramo A* di _move_towards
// resta in Python (passato come `astar_move`).

fn xy_of(v: &Bound<'_, PyAny>) -> PyResult<(f64, f64)> {
    let py = v.py();
    Ok((v.getattr(intern!(py, "x"))?.extract()?, v.getattr(intern!(py, "y"))?.extract()?))
}

fn attr_f64_or(e: &Bound<'_, PyAny>, name: &Bound<'_, pyo3::types::PyString>, d: f64) -> PyResult<f64> {
    match e.getattr(name) {
        Ok(v) => v.extract(),
        Err(_) => Ok(d),
    }
}

#[pyclass(module = "pokemoba_native")]
struct MinionAI {
    poke_cls: Py<PyAny>,
    minion_cls: Py<PyAny>,
    struct_cls: Py<PyAny>,
    vec2: Py<PyAny>,
    waypoint: f64,
    leash: f64,
    aggro_window: f64,
    retaliate: f64,
    tick_dt: f64,
}

struct MinionCtx<'a, 'py> {
    ai: &'a Bound<'py, PyDict>,
    entities: &'a Bound<'py, PyDict>,
    astar_move: &'a Bound<'py, PyAny>,
    hash: &'a SpatialHash,
    gv: &'a GridView,
    time: f64,
}

impl MinionAI {
    fn move_towards(&self, c: &MinionCtx, u: &Bound<'_, PyAny>, dest: &Bound<'_, PyAny>,
                    dt: f64) -> PyResult<()> {
        let py = u.py();
        let bb = attr_truthy(u, intern!(py, "bush_blocks"));
        let (ux, uy) = pos_of(u)?;
        let (dx, dy) = xy_of(dest)?;
        if c.gv.los(ux, uy, dx, dy, bb) {
            u.setattr(intern!(py, "path"), PyList::new(py, [dest])?)?;
            u.setattr(intern!(py, "moving"), true)?;
            return Ok(());
        }
        c.astar_move.call1((u, dest, dt, bb))?;
        Ok(())
    }

    fn face(&self, c: &MinionCtx, u: &Bound<'_, PyAny>, tx: f64, ty: f64) -> PyResult<()> {
        let (ux, uy) = pos_of(u)?;
        u.setattr(intern!(u.py(), "facing"), c.gv.direction_index(tx - ux, ty - uy))
    }

    fn follow_lane(&self, c: &MinionCtx, m: &Bound<'_, PyAny>) -> PyResult<()> {
        let py = m.py();
        let lp = m.getattr(intern!(py, "lane_points"))?;
        let n = lp.len()? as i64;
        if n == 0 {
            m.setattr(intern!(py, "path"), PyList::empty(py))?;
            m.setattr(intern!(py, "moving"), false)?;
            return Ok(());
        }
        let k_idx = intern!(py, "lane_idx");
        let mut idx: i64 = m.getattr(k_idx)?.extract()?;
        if idx >= n {
            idx = n - 1;
            m.setattr(k_idx, idx)?;
        }
        let mut wp = lp.get_item(idx)?;
        let (mx, my) = pos_of(m)?;
        let (wx, wy) = xy_of(&wp)?;
        if hypot(mx - wx, my - wy) <= self.waypoint && idx < n - 1 {
            idx += 1;
            m.setattr(k_idx, idx)?;
            wp = lp.get_item(idx)?;
        }
        self.move_towards(c, m, &wp, self.tick_dt)?;
        let (wx, wy) = xy_of(&wp)?;
        self.face(c, m, wx, wy)
    }

    fn acquire<'py>(&self, c: &MinionCtx<'_, 'py>, m: &Bound<'py, PyAny>, team: i64)
                    -> PyResult<Option<Bound<'py, PyAny>>> {
        let py = m.py();
        let (k_team, k_alive, k_rad) = (intern!(py, "team"), intern!(py, "alive"), intern!(py, "radius"));
        let aggro: f64 = m.getattr(intern!(py, "aggro"))?.extract()?;
        let (mx, my) = pos_of(m)?;
        let inv = 1.0 / c.hash.cell_size;
        let cx0 = ((mx - aggro) * inv).floor() as i64;
        let cy0 = ((my - aggro) * inv).floor() as i64;
        let cx1 = ((mx + aggro) * inv).floor() as i64;
        let cy1 = ((my + aggro) * inv).floor() as i64;
        let mut cands: Vec<(Bound<'py, PyAny>, f64)> = Vec::new();
        for cy in cy0..=cy1 {
            for cx in cx0..=cx1 {
                if let Some(b) = c.hash.cells.get(&(cx, cy)) {
                    for e in b {
                        let e = e.bind(py);
                        if e.is(m) {
                            continue;
                        }
                        let et: i64 = e.getattr(k_team)?.extract()?;
                        if et == team || !attr_truthy(e, k_alive) {
                            continue;
                        }
                        let (ex, ey) = pos_of(e)?;
                        let d = hypot(mx - ex, my - ey);
                        if d <= aggro + attr_f64_or(e, k_rad, 0.0)? {
                            cands.push((e.clone(), d));
                        }
                    }
                }
            }
        }
        if cands.is_empty() {
            return Ok(None);
        }
        let nearest = |pick: &dyn Fn(&Bound<'py, PyAny>) -> PyResult<bool>|
                       -> PyResult<Option<Bound<'py, PyAny>>> {
            let mut best: Option<(&Bound<'py, PyAny>, f64)> = None;
            for (e, d) in cands.iter() {
                if pick(e)? && best.map_or(true, |(_, bd)| *d < bd) {
                    best = Some((e, *d));
                }
            }
            Ok(best.map(|(e, _)| e.clone()))
        };
        let poke = self.poke_cls.bind(py);
        let k_agg = intern!(py, "_minion_aggro_at");
        let time = c.time;
        let win = self.aggro_window;
        if let Some(e) = nearest(&|e| Ok(e.is_instance(poke)?
                                     && time - attr_f64_or(e, k_agg, -1e9)? <= win))? {
            return Ok(Some(e));
        }
        let la = m.getattr(intern!(py, "last_attacker_id"))?;
        if !la.is_none() {
            let ld: f64 = m.getattr(intern!(py, "last_damaged_at"))?.extract()?;
            if time - ld <= self.retaliate {
                if let Some(a) = c.entities.get_item(&la)? {
                    if cands.iter().any(|(e, _)| e.is(&a)) {
                        return Ok(Some(a));
                    }
                }
            }
        }
        for cls in [self.minion_cls.bind(py), poke] {
            if let Some(e) = nearest(&|e| e.is_instance(cls))? {
                return Ok(Some(e));
            }
        }
        let st = self.struct_cls.bind(py);
        nearest(&|e| e.is_instance(st))
    }

    fn ai_minion(&self, c: &MinionCtx, m: &Bound<'_, PyAny>, dt: f64) -> PyResult<()> {
        let py = m.py();
        let (k_tid, k_chasing, k_leash) =
            (intern!(py, "target_id"), intern!(py, "chasing"), intern!(py, "leash"));
        let id = m.getattr(intern!(py, "id"))?;
        let state = match c.ai.get_item(&id)? {
            Some(s) => s.cast_into::<PyDict>()?,
            None => {
                let s = PyDict::new(py);
                c.ai.set_item(&id, &s)?;
                s
            }
        };
        let team: i64 = m.getattr(intern!(py, "team"))?.extract()?;
        let (mx, my) = pos_of(m)?;
        let aggro: f64 = m.getattr(intern!(py, "aggro"))?.extract()?;
        let origin_xy = |state: &Bound<'_, PyDict>| -> PyResult<(f64, f64)> {
            match state.get_item(k_leash)? {
                Some(v) => xy_of(&v),
                None => Ok((mx, my)),
            }
        };
        // _valid_minion_target
        let mut target = None;
        let tid = m.getattr(k_tid)?;
        if !tid.is_none() {
            if let Some(t) = c.entities.get_item(&tid)? {
                if attr_truthy(&t, intern!(py, "alive")) {
                    let tt: i64 = t.getattr(intern!(py, "team"))?.extract()?;
                    if tt != team {
                        let (tx, ty) = pos_of(&t)?;
                        let (ox, oy) = origin_xy(&state)?;
                        if !(hypot(mx - tx, my - ty) > aggro * 1.6
                             || hypot(mx - ox, my - oy) > self.leash) {
                            target = Some(t);
                        }
                    }
                }
            }
        }
        if target.is_none() {
            target = self.acquire(c, m, team)?;
            match &target {
                Some(t) => {
                    m.setattr(k_tid, t.getattr(intern!(py, "id"))?)?;
                    state.set_item(k_leash, self.vec2.bind(py).call1((mx, my))?)?;
                }
                None => {
                    m.setattr(k_tid, py.None())?;
                    if state.contains(k_leash)? {
                        state.del_item(k_leash)?;
                    }
                }
            }
        }
        if let Some(t) = target {
            let (tx, ty) = pos_of(&t)?;
            let reach = attr_f64_or(m, intern!(py, "attack_range"), 0.0)?
                + attr_f64_or(&t, intern!(py, "radius"), 0.0)?;
            if hypot(mx - tx, my - ty) <= reach {
                m.setattr(intern!(py, "path"), PyList::empty(py))?;
                m.setattr(intern!(py, "moving"), false)?;
                self.face(c, m, tx, ty)?;
                m.setattr(k_chasing, false)?;
            } else {
                let (ox, oy) = origin_xy(&state)?;
                if hypot(mx - ox, my - oy) <= self.leash {
                    m.setattr(k_chasing, true)?;
                    let tpos = t.getattr(intern!(py, "pos"))?;
                    self.move_towards(c, m, &tpos, dt)?;
                    self.face(c, m, tx, ty)?;
                } else {
                    m.setattr(k_tid, py.None())?;
                    if state.contains(k_leash)? {
                        state.del_item(k_leash)?;
                    }
                    m.setattr(k_chasing, false)?;
                    self.follow_lane(c, m)?;
                }
            }
            return Ok(());
        }
        m.setattr(k_chasing, false)?;
        self.follow_lane(c, m)
    }
}

#[pymethods]
impl MinionAI {
    #[new]
    #[allow(clippy::too_many_arguments)]
    fn new(poke_cls: Py<PyAny>, minion_cls: Py<PyAny>, struct_cls: Py<PyAny>, vec2: Py<PyAny>,
           waypoint: f64, leash: f64, aggro_window: f64, retaliate: f64, tick_dt: f64) -> Self {
        MinionAI { poke_cls, minion_cls, struct_cls, vec2, waypoint, leash, aggro_window,
                   retaliate, tick_dt }
    }

    /// Match._update_ai, parte dei minion (stride compreso).
    #[allow(clippy::too_many_arguments)]
    fn run(&self, minions: &Bound<'_, PyAny>, ai: &Bound<'_, PyDict>, entities: &Bound<'_, PyDict>,
           astar_move: &Bound<'_, PyAny>, hash: PyRef<'_, SpatialHash>, gv: PyRef<'_, GridView>,
           time: f64, dt: f64, stride: i64, tick: i64) -> PyResult<()> {
        let py = ai.py();
        let c = MinionCtx { ai, entities, astar_move, hash: &hash, gv: &gv, time };
        let (k_alive, k_id) = (intern!(py, "alive"), intern!(py, "id"));
        let mdt = if stride > 1 { dt * stride as f64 } else { dt };
        for m in minions.try_iter()? {
            let m = m?;
            if !m.getattr(k_alive)?.is_truthy()? {
                continue;
            }
            if stride > 1 {
                let id: i64 = m.getattr(k_id)?.extract()?;
                if (id + tick).rem_euclid(stride) != 0 {
                    continue;
                }
            }
            self.ai_minion(&c, &m, mdt)?;
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Aiutanti dell'IA dei bot (engine/match.py: _has_allied_minion_near,
// _unsafe_dive, _threatened_structure; engine/smite.py: _under_enemy_tower,
// _count_champs). Stesse letture e stesso risultato; nessuna scrittura.

#[pyclass(module = "pokemoba_native")]
struct BotHelpers {
    poke_cls: Py<PyAny>,
    minion_cls: Py<PyAny>,
}

impl BotHelpers {
    fn minion_near_impl(&self, py: Python<'_>, hash: &SpatialHash, team: i64, x: f64, y: f64,
                        r: f64) -> PyResult<bool> {
        let (k_team, k_alive) = (intern!(py, "team"), intern!(py, "alive"));
        let mcls = self.minion_cls.bind(py);
        let inv = 1.0 / hash.cell_size;
        let cx0 = ((x - r) * inv).floor() as i64;
        let cy0 = ((y - r) * inv).floor() as i64;
        let cx1 = ((x + r) * inv).floor() as i64;
        let cy1 = ((y + r) * inv).floor() as i64;
        for cy in cy0..=cy1 {
            for cx in cx0..=cx1 {
                if let Some(b) = hash.cells.get(&(cx, cy)) {
                    for e in b {
                        let e = e.bind(py);
                        if !e.is_instance(mcls)? {
                            continue;
                        }
                        let et: i64 = e.getattr(k_team)?.extract()?;
                        if et != team || !e.getattr(k_alive)?.is_truthy()? {
                            continue;
                        }
                        let (ex, ey) = pos_of(e)?;
                        if hypot(x - ex, y - ey) <= r {
                            return Ok(true);
                        }
                    }
                }
            }
        }
        Ok(false)
    }
}

#[pymethods]
impl BotHelpers {
    #[new]
    fn new(poke_cls: Py<PyAny>, minion_cls: Py<PyAny>) -> Self {
        BotHelpers { poke_cls, minion_cls }
    }

    /// _has_allied_minion_near(p, pos, r) con team = p.team.
    fn minion_near(&self, hash: PyRef<'_, SpatialHash>, team: i64, x: f64, y: f64, r: f64)
                   -> PyResult<bool> {
        self.minion_near_impl(hash.py(), &hash, team, x, y, r)
    }

    /// _unsafe_dive(p, point).
    #[allow(clippy::too_many_arguments)]
    fn unsafe_dive(&self, structures: &Bound<'_, PyList>, hash: PyRef<'_, SpatialHash>, team: i64,
                   x: f64, y: f64, margin: f64, smr: f64) -> PyResult<bool> {
        let py = structures.py();
        let (k_kind, k_alive, k_team, k_range) =
            (intern!(py, "kind"), intern!(py, "alive"), intern!(py, "team"), intern!(py, "attack_range"));
        for e in structures.iter() {
            if e.getattr(k_kind)?.extract::<&str>()? != "tower" || !e.getattr(k_alive)?.is_truthy()? {
                continue;
            }
            let et: i64 = e.getattr(k_team)?.extract()?;
            if et == team {
                continue;
            }
            let (ex, ey) = pos_of(&e)?;
            let ar: f64 = e.getattr(k_range)?.extract()?;
            if hypot(x - ex, y - ey) <= ar + margin && !self.minion_near_impl(py, &hash, team, ex, ey, smr)? {
                return Ok(true);
            }
        }
        Ok(false)
    }

    /// _under_enemy_tower(p, pos).
    fn under_tower(&self, structures: &Bound<'_, PyList>, team: i64, x: f64, y: f64, margin: f64)
                   -> PyResult<bool> {
        let py = structures.py();
        let (k_kind, k_alive, k_team, k_range) =
            (intern!(py, "kind"), intern!(py, "alive"), intern!(py, "team"), intern!(py, "attack_range"));
        for e in structures.iter() {
            if e.getattr(k_kind)?.extract::<&str>()? != "tower" || !e.getattr(k_alive)?.is_truthy()? {
                continue;
            }
            let et: i64 = e.getattr(k_team)?.extract()?;
            if et == team {
                continue;
            }
            let (ex, ey) = pos_of(&e)?;
            let ar: f64 = e.getattr(k_range)?.extract()?;
            if hypot(x - ex, y - ey) <= ar + margin {
                return Ok(true);
            }
        }
        Ok(false)
    }

    /// _threatened_structure(p).
    #[allow(clippy::too_many_arguments)]
    fn threatened<'py>(&self, structures: &Bound<'py, PyList>, hash: PyRef<'_, SpatialHash>,
                       team: i64, px: f64, py_: f64, r: f64, maxd: f64)
                       -> PyResult<Option<Bound<'py, PyAny>>> {
        let py = structures.py();
        let (k_alive, k_team) = (intern!(py, "alive"), intern!(py, "team"));
        let (pcls, mcls) = (self.poke_cls.bind(py), self.minion_cls.bind(py));
        let inv = 1.0 / hash.cell_size;
        let mut best: Option<Bound<'py, PyAny>> = None;
        let mut bestd = 1e9_f64;
        for e in structures.iter() {
            let et: i64 = e.getattr(k_team)?.extract()?;
            if et != team || !e.getattr(k_alive)?.is_truthy()? {
                continue;
            }
            let (ex, ey) = pos_of(&e)?;
            let cx0 = ((ex - r) * inv).floor() as i64;
            let cy0 = ((ey - r) * inv).floor() as i64;
            let cx1 = ((ex + r) * inv).floor() as i64;
            let cy1 = ((ey + r) * inv).floor() as i64;
            let mut found = false;
            'scan: for cy in cy0..=cy1 {
                for cx in cx0..=cx1 {
                    if let Some(b) = hash.cells.get(&(cx, cy)) {
                        for x in b {
                            let x = x.bind(py);
                            let xt: i64 = x.getattr(k_team)?.extract()?;
                            if xt == team || !attr_truthy(x, k_alive) {
                                continue;
                            }
                            if x.is_instance(pcls)? || x.is_instance(mcls)? {
                                found = true;
                                break 'scan;
                            }
                        }
                    }
                }
            }
            if !found {
                continue;
            }
            let d = hypot(px - ex, py_ - ey);
            if d < bestd {
                bestd = d;
                best = Some(e);
            }
        }
        Ok(if best.is_some() && bestd < maxd { best } else { None })
    }

    /// _count_champs(pos, r, team, exclude).
    #[pyo3(signature = (pokemons, x, y, r, team, exclude=None))]
    fn count_champs(&self, pokemons: &Bound<'_, PyList>, x: f64, y: f64, r: f64, team: i64,
                    exclude: Option<&Bound<'_, PyAny>>) -> PyResult<i64> {
        let py = pokemons.py();
        let (k_alive, k_team) = (intern!(py, "alive"), intern!(py, "team"));
        let mut n = 0;
        for e in pokemons.iter() {
            if let Some(ex) = exclude {
                if e.is(ex) {
                    continue;
                }
            }
            if !e.getattr(k_alive)?.is_truthy()? {
                continue;
            }
            let et: i64 = e.getattr(k_team)?.extract()?;
            if et != team {
                continue;
            }
            let (ex, ey) = pos_of(&e)?;
            if hypot(x - ex, y - ey) <= r {
                n += 1;
            }
        }
        Ok(n)
    }
}

#[pymodule]
fn pokemoba_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(py_hypot, m)?)?;
    m.add_class::<GridView>()?;
    m.add_class::<SpatialHash>()?;
    m.add_class::<WalkGrid>()?;
    m.add_class::<VisionScan>()?;
    m.add_class::<MinionAI>()?;
    m.add_class::<BotHelpers>()?;
    m.add_function(wrap_pyfunction!(obstacle_hits, m)?)?;
    Ok(())
}
