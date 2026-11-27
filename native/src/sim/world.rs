//! Rust-owned match state. Phase 1 grows it system by system; every field
//! mirrors the Python attribute of the same name (engine/entities.py), and
//! entities stay in World.entities insertion order (Python iterates that way).
//!
//! In and out it speaks the canonical rows of tools/sim_spec.py: floats as
//! `float.hex()` strings, Vec2 as ("V", x, y), lists in order.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use super::mathx::{float_hex, parse_float_hex};

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Kind {
    Pokemon,
    Minion,
    Wild,
    Structure,
    Core,
    Other,
}

impl Kind {
    fn from_name(s: &str) -> Kind {
        match s {
            "Pokemon" => Kind::Pokemon,
            "Minion" => Kind::Minion,
            "Wild" => Kind::Wild,
            "Structure" => Kind::Structure,
            "Core" => Kind::Core,
            _ => Kind::Other,
        }
    }

    /// isinstance(e, engine.entities.Unit)
    #[inline]
    pub fn is_unit(self) -> bool {
        matches!(self, Kind::Pokemon | Kind::Minion | Kind::Wild)
    }

    /// isinstance(e, engine.entities.Structure) (Core is a Structure)
    #[inline]
    pub fn is_structure(self) -> bool {
        matches!(self, Kind::Structure | Kind::Core)
    }
}

#[derive(Clone, Debug)]
pub struct Ent {
    pub id: i64,
    pub kind: Kind,
    pub team: i64,
    pub pos: (f64, f64),
    pub radius: f64,
    pub alive: bool,
    // Unit
    pub speed: f64,
    pub path: Vec<(f64, f64)>,
    pub moving: bool,
    pub facing: i64,
    pub bush_blocks: bool,
    pub air_z: f64, // Pokemon only; 0 for the others (getattr(u, "air_z", 0.0))
    // Structure.kind / Wild.kind
    pub skind: String,
}

#[derive(Clone, Default, Debug)]
pub struct World {
    pub ents: Vec<Ent>,
}

/// Entity fields the Rust state reads (tools pass only these).
pub const FIELDS_IN: &[&str] = &[
    "_type", "id", "team", "pos", "radius", "alive", "speed", "path", "moving", "facing",
    "bush_blocks", "air_z", "kind",
];
/// Unit fields the movement step writes (compared by the parity harness).
pub const FIELDS_MOVE_OUT: &[&str] = &["pos", "path", "moving", "facing"];

fn hexf(v: &Bound<'_, PyAny>, what: &str) -> PyResult<f64> {
    let s: String = v.extract()?;
    parse_float_hex(&s).ok_or_else(|| PyValueError::new_err(format!("{what}: bad float {s:?}")))
}

fn vec2(v: &Bound<'_, PyAny>, what: &str) -> PyResult<(f64, f64)> {
    let t = v.cast::<PyTuple>()?;
    if t.len() != 3 || t.get_item(0)?.extract::<String>()? != "V" {
        return Err(PyValueError::new_err(format!("{what}: expected (\"V\", x, y)")));
    }
    Ok((hexf(&t.get_item(1)?, what)?, hexf(&t.get_item(2)?, what)?))
}

fn opt<'py>(row: &Bound<'py, PyDict>, k: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
    row.get_item(k)
}

impl Ent {
    pub fn from_row(row: &Bound<'_, PyDict>) -> PyResult<Ent> {
        let ty: String = opt(row, "_type")?.ok_or_else(|| PyValueError::new_err("row: no _type"))?.extract()?;
        let id: i64 = opt(row, "id")?.ok_or_else(|| PyValueError::new_err("row: no id"))?.extract()?;
        let f = |k: &str, d: f64| -> PyResult<f64> {
            match opt(row, k)? {
                Some(v) => hexf(&v, k),
                None => Ok(d),
            }
        };
        let path = match opt(row, "path")? {
            Some(v) => {
                let l = v.cast::<PyList>()?;
                let mut p = Vec::with_capacity(l.len());
                for w in l.iter() {
                    p.push(vec2(&w, "path")?);
                }
                p
            }
            None => Vec::new(),
        };
        Ok(Ent {
            id,
            kind: Kind::from_name(&ty),
            team: match opt(row, "team")? { Some(v) => v.extract()?, None => 0 },
            pos: match opt(row, "pos")? { Some(v) => vec2(&v, "pos")?, None => (0.0, 0.0) },
            radius: f("radius", 0.35)?,
            alive: match opt(row, "alive")? { Some(v) => v.extract()?, None => true },
            speed: f("speed", 0.0)?,
            path,
            moving: match opt(row, "moving")? { Some(v) => v.extract()?, None => false },
            facing: match opt(row, "facing")? { Some(v) => v.extract()?, None => 0 },
            bush_blocks: match opt(row, "bush_blocks")? { Some(v) => v.extract()?, None => false },
            air_z: f("air_z", 0.0)?,
            skind: match opt(row, "kind")? { Some(v) => v.extract()?, None => String::new() },
        })
    }
}

/// Vec2 in canonical form: ("V", x.hex(), y.hex()).
fn v2<'py>(py: Python<'py>, p: (f64, f64)) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(py, ["V".to_string(), float_hex(p.0), float_hex(p.1)])
}

impl World {
    /// From canonical rows [[id, {field: value}], ...] (sim_spec.snapshot order).
    pub fn from_rows(rows: &Bound<'_, PyList>) -> PyResult<World> {
        let mut ents = Vec::with_capacity(rows.len());
        for r in rows.iter() {
            let pair = r.cast::<PyList>()?;
            let row = pair.get_item(1)?;
            ents.push(Ent::from_row(row.cast::<PyDict>()?)?);
        }
        Ok(World { ents })
    }

    /// Canonical rows of the units' movement fields (FIELDS_MOVE_OUT).
    pub fn movement_rows<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let out = PyList::empty(py);
        for e in self.ents.iter().filter(|e| e.kind.is_unit()) {
            let d = PyDict::new(py);
            d.set_item("pos", v2(py, e.pos)?)?;
            let path = PyList::empty(py);
            for &w in &e.path {
                path.append(v2(py, w)?)?;
            }
            d.set_item("path", path)?;
            d.set_item("moving", e.moving)?;
            d.set_item("facing", e.facing)?;
            out.append((e.id, d))?;
        }
        Ok(out)
    }
}
