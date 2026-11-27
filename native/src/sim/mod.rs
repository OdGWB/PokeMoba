//! Training engine (docs/RUST_ENGINE.md): the whole match runs in Rust from a
//! `MatchSpec` built by tools/sim_spec.py. Phase 0: foundations only (exact RNG,
//! exact math, spec parsing); `run_match` does not simulate yet.

pub mod mathx;
pub mod movement;
pub mod rng;
pub mod world;

use pyo3::exceptions::{PyIndexError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use rng::PyRng;

use crate::GridView;
use movement::MoveGrid;
use world::World;

/// Spec format understood by this build (tools/sim_spec.py SPEC_VERSION).
pub const SPEC_VERSION: i64 = 1;

/// The exact CPython RNG, exposed for the parity tests.
#[pyclass(module = "pokemoba_native")]
pub struct SimRandom {
    r: PyRng,
}

#[pymethods]
impl SimRandom {
    /// SimRandom(seed) == random.Random(seed).
    #[new]
    fn new(seed: i128) -> Self {
        SimRandom { r: PyRng::from_seed(seed) }
    }

    /// SimRandom.from_state(random.getstate()).
    #[staticmethod]
    fn from_state(state: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(SimRandom { r: rng_from_state(state)? })
    }

    /// Same shape as random.getstate(): (3, (624 words..., pos), None).
    fn getstate(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let (mut w, pos) = self.r.state();
        let mut v: Vec<u64> = w.drain(..).map(|x| x as u64).collect();
        v.push(pos as u64);
        let inner = pyo3::types::PyTuple::new(py, v)?;
        Ok((3, inner, py.None()).into_pyobject(py)?.into_any().unbind())
    }

    fn random(&mut self) -> f64 {
        self.r.random()
    }

    fn getrandbits(&mut self, k: u32) -> PyResult<u64> {
        if k > 64 {
            return Err(PyValueError::new_err("k > 64 not supported"));
        }
        Ok(self.r.getrandbits(k))
    }

    fn randbelow(&mut self, n: u64) -> PyResult<u64> {
        if n == 0 {
            return Err(PyValueError::new_err("n must be > 0"));
        }
        Ok(self.r.randbelow(n))
    }

    /// Index random.choice would take from a sequence of length n.
    fn choice_index(&mut self, n: usize) -> PyResult<usize> {
        if n == 0 {
            return Err(PyIndexError::new_err("Cannot choose from an empty sequence"));
        }
        Ok(self.r.choice_index(n))
    }

    #[pyo3(signature = (start, stop=None))]
    fn randrange(&mut self, start: i64, stop: Option<i64>) -> PyResult<i64> {
        let (a, b) = match stop {
            Some(s) => (start, s),
            None => (0, start),
        };
        if b <= a {
            return Err(PyValueError::new_err("empty range for randrange()"));
        }
        Ok(self.r.randrange(a, b))
    }

    /// random.shuffle(list(range(n))) result.
    fn shuffled_range(&mut self, n: usize) -> Vec<usize> {
        let mut v: Vec<usize> = (0..n).collect();
        self.r.shuffle(&mut v);
        v
    }

    fn uniform(&mut self, a: f64, b: f64) -> f64 {
        self.r.uniform(a, b)
    }
}

fn rng_from_state(state: &Bound<'_, PyAny>) -> PyResult<PyRng> {
    // random.getstate() -> (version, (624 words..., pos), gauss_next)
    let inner = state.get_item(1)?;
    let vals: Vec<u64> = inner.extract()?;
    if vals.len() != 625 {
        return Err(PyValueError::new_err("rng state must hold 625 ints"));
    }
    let words: Vec<u32> = vals[..624].iter().map(|&x| x as u32).collect();
    PyRng::from_state(&words, vals[624] as usize)
        .ok_or_else(|| PyValueError::new_err("bad rng state"))
}

/// Applies a math helper elementwise (parity tests against CPython's math).
#[pyfunction]
#[pyo3(signature = (name, xs, ys=None))]
pub fn sim_math(name: &str, xs: Vec<f64>, ys: Option<Vec<f64>>) -> PyResult<Vec<f64>> {
    let f = mathx::by_name(name).ok_or_else(|| PyValueError::new_err(format!("unknown fn {name}")))?;
    Ok(match ys {
        Some(ys) => xs.iter().zip(ys.iter()).map(|(&x, &y)| f(x, y)).collect(),
        None => xs.iter().map(|&x| f(x, 0.0)).collect(),
    })
}

/// hash(tuple(items)) for a tuple of ints, as CPython computes it.
#[pyfunction]
pub fn sim_tuple_hash(items: Vec<i64>) -> i64 {
    mathx::py_hash_int_tuple(&items)
}

/// float.hex() of each value, from Rust (parity tests).
#[pyfunction]
pub fn sim_float_hex(xs: Vec<f64>) -> Vec<String> {
    xs.into_iter().map(mathx::float_hex).collect()
}

/// float.fromhex of float.hex strings, from Rust (parity tests).
#[pyfunction]
pub fn sim_parse_hex(xs: Vec<String>) -> PyResult<Vec<f64>> {
    xs.iter()
        .map(|s| mathx::parse_float_hex(s).ok_or_else(|| PyValueError::new_err(format!("bad hex float {s:?}"))))
        .collect()
}

/// Fields the Rust state reads and the ones each ported system writes.
#[pyfunction]
pub fn sim_fields<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("in", world::FIELDS_IN.to_vec())?;
    d.set_item("world_tick", world::FIELDS_MOVE_OUT.to_vec())?;
    Ok(d)
}

/// Per-phase ns of World.tick in Rust (advance, collisions, towers), averaged
/// over `reps` runs on copies of the state built from `rows`.
#[pyfunction]
pub fn sim_world_tick_parts(nv: PyRef<'_, GridView>, cen: Vec<u8>, rows: &Bound<'_, PyList>,
                            dt: f64, reps: usize) -> PyResult<[f64; 3]> {
    let w = World::from_rows(rows)?;
    let g = MoveGrid { gv: &nv, cen: &cen };
    let mut t = [0u128; 3];
    for _ in 0..reps.max(1) {
        let mut c = w.clone();
        g.world_tick_timed(&mut c, dt, Some(&mut t));
        std::hint::black_box(&c);
    }
    let n = reps.max(1) as f64;
    Ok([t[0] as f64 / n, t[1] as f64 / n, t[2] as f64 / n])
}

/// World.tick(dt) on the Rust state built from canonical entity rows (only
/// world::FIELDS_IN needed). `nv` = grid.native_view(), `cen` =
/// grid._shape_cen_b. Returns (movement rows of the units after the step,
/// ns per step averaged over `reps` timed runs on copies of the state; 0 if
/// reps = 0). The timing covers the step alone, not the conversions.
#[pyfunction]
#[pyo3(signature = (nv, cen, rows, dt, reps=0))]
pub fn sim_world_tick<'py>(py: Python<'py>, nv: PyRef<'py, GridView>, cen: Vec<u8>,
                           rows: &Bound<'py, PyList>, dt: f64, reps: usize)
                           -> PyResult<(Bound<'py, PyList>, f64)> {
    if cen.len() != nv.w * nv.h {
        return Err(PyValueError::new_err("cen: one byte per tile expected"));
    }
    let mut w = World::from_rows(rows)?;
    let g = MoveGrid { gv: &nv, cen: &cen };
    let mut ns = 0.0;
    if reps > 0 {
        let mut total = 0u128;
        for _ in 0..reps {
            let mut c = w.clone();
            let t = std::time::Instant::now();
            g.world_tick(&mut c, dt);
            total += t.elapsed().as_nanos();
            std::hint::black_box(&c);
        }
        ns = total as f64 / reps as f64;
    }
    g.world_tick(&mut w, dt);
    Ok((w.movement_rows(py)?, ns))
}

fn req<'py>(d: &Bound<'py, PyDict>, k: &str) -> PyResult<Bound<'py, PyAny>> {
    d.get_item(k)?.ok_or_else(|| PyValueError::new_err(format!("spec: missing '{k}'")))
}

/// Runs one match from a spec (tools/sim_spec.py). Phase 0 stub: validates the
/// spec and returns what it parsed, plus the first RNG draw (to check that the
/// RNG handoff is exact). Raises on a spec version this build does not know.
#[pyfunction]
pub fn run_match<'py>(py: Python<'py>, spec: &Bound<'py, PyDict>) -> PyResult<Bound<'py, PyDict>> {
    let ver: i64 = req(spec, "version")?.extract()?;
    if ver != SPEC_VERSION {
        return Err(PyValueError::new_err(format!(
            "spec version {ver}, this build understands {SPEC_VERSION}"
        )));
    }
    let mut r = rng_from_state(&req(spec, "rng_state")?)?;
    let horizon: f64 = req(spec, "horizon")?.extract()?;
    let dt: f64 = req(spec, "dt")?.extract()?;
    let map = req(spec, "map")?;
    let map = map.cast::<PyDict>()?;
    let w: usize = req(map, "width")?.extract()?;
    let h: usize = req(map, "height")?.extract()?;
    let tiles: Vec<u8> = req(map, "tiles")?.extract()?;
    let shape: Vec<u8> = req(map, "shape")?.extract()?;
    if tiles.len() != w * h || shape.len() != w * h * 64 {
        return Err(PyValueError::new_err("spec: map sizes do not match width/height"));
    }
    let teams = req(spec, "teams")?;
    let teams = teams.cast::<PyList>()?;
    let mut sizes = Vec::new();
    for t in teams.iter() {
        sizes.push(t.cast::<PyList>()?.len());
    }
    let out = PyDict::new(py);
    out.set_item("stub", true)?;
    out.set_item("spec_version", ver)?;
    out.set_item("ticks", (horizon / dt).round() as i64)?;
    out.set_item("map", (w, h))?;
    out.set_item("team_sizes", sizes)?;
    out.set_item("rng_next", r.random())?;
    Ok(out)
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<SimRandom>()?;
    m.add_function(wrap_pyfunction!(sim_math, m)?)?;
    m.add_function(wrap_pyfunction!(run_match, m)?)?;
    m.add_function(wrap_pyfunction!(sim_tuple_hash, m)?)?;
    m.add_function(wrap_pyfunction!(sim_float_hex, m)?)?;
    m.add_function(wrap_pyfunction!(sim_parse_hex, m)?)?;
    m.add_function(wrap_pyfunction!(sim_fields, m)?)?;
    m.add_function(wrap_pyfunction!(sim_world_tick, m)?)?;
    m.add_function(wrap_pyfunction!(sim_world_tick_parts, m)?)?;
    m.add("SIM_SPEC_VERSION", SPEC_VERSION)?;
    Ok(())
}
