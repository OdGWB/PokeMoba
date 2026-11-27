//! Float helpers with exactly CPython's results. `hypot` is the bit-exact port
//! in lib.rs; the libm functions go to the same MSVC UCRT routines that CPython
//! calls (checked by tests/test_sim_core.py); the rest mirror Python operators.

#![allow(dead_code)] // helpers used from phase 1 on

use crate::hypot;

pub const DEG_TO_RAD: f64 = std::f64::consts::PI / 180.0;
pub const RAD_TO_DEG: f64 = 180.0 / std::f64::consts::PI;

/// `math.radians(x)`.
#[inline]
pub fn radians(x: f64) -> f64 {
    x * DEG_TO_RAD
}

/// `math.degrees(x)`.
#[inline]
pub fn degrees(x: f64) -> f64 {
    x * RAD_TO_DEG
}

// math.floor / math.ceil / round(x) return an INT in Python: no -0.0
// (adding +0.0 turns -0.0 into 0.0 and leaves every other value alone).

/// `float(math.floor(x))`.
#[inline]
pub fn py_floor(x: f64) -> f64 {
    x.floor() + 0.0
}

/// `float(math.ceil(x))`.
#[inline]
pub fn py_ceil(x: f64) -> f64 {
    x.ceil() + 0.0
}

/// `float(round(x))` with no digits (half to even).
#[inline]
pub fn py_round(x: f64) -> f64 {
    x.round_ties_even() + 0.0
}

/// Python float `a % b` (sign of b), as float_rem in Objects/floatobject.c.
#[inline]
pub fn py_mod(a: f64, b: f64) -> f64 {
    let m = a % b;
    if m != 0.0 {
        if (b < 0.0) != (m < 0.0) {
            m + b
        } else {
            m
        }
    } else {
        0.0f64.copysign(b)
    }
}

/// Python float `a // b`, as _float_div_mod in Objects/floatobject.c.
#[inline]
pub fn py_floordiv(a: f64, b: f64) -> f64 {
    let m = a % b;
    let mut div = (a - m) / b;
    if m != 0.0 && ((b < 0.0) != (m < 0.0)) {
        div -= 1.0;
    }
    if div != 0.0 {
        let fl = div.floor();
        if div - fl > 0.5 {
            fl + 1.0
        } else {
            fl
        }
    } else {
        0.0f64.copysign(a / b)
    }
}

/// Function by name, for the parity tests (`pokemoba_native.sim_math`).
pub fn by_name(name: &str) -> Option<fn(f64, f64) -> f64> {
    Some(match name {
        "sin" => |x, _| x.sin(),
        "cos" => |x, _| x.cos(),
        "atan2" => |x, y| x.atan2(y),
        "acos" => |x, _| x.acos(),
        "exp" => |x, _| x.exp(),
        "sqrt" => |x, _| x.sqrt(),
        "floor" => |x, _| py_floor(x),
        "ceil" => |x, _| py_ceil(x),
        "hypot" => |x, y| hypot(x, y),
        "radians" => |x, _| radians(x),
        "degrees" => |x, _| degrees(x),
        "round" => |x, _| py_round(x),
        "mod" => |x, y| py_mod(x, y),
        "floordiv" => |x, y| py_floordiv(x, y),
        "pow" => |x, y| x.powf(y),
        _ => return None,
    })
}

/// `hash(n)` for an int that fits in i64 (Objects/longobject.c, modulus 2**61-1).
#[inline]
pub fn py_hash_int(n: i64) -> i64 {
    const P: u64 = (1u64 << 61) - 1;
    let h = (n.unsigned_abs() % P) as i64;
    let h = if n < 0 { -h } else { h };
    if h == -1 {
        -2
    } else {
        h
    }
}

/// `hash(tuple_of_ints)` (Objects/tupleobject.c, xxHash-based, 64-bit).
pub fn py_hash_int_tuple(items: &[i64]) -> i64 {
    const P1: u64 = 11_400_714_785_074_694_791;
    const P2: u64 = 14_029_467_366_897_019_727;
    const P5: u64 = 2_870_177_450_012_600_261;
    let mut acc = P5;
    for &it in items {
        let lane = py_hash_int(it) as u64;
        acc = acc.wrapping_add(lane.wrapping_mul(P2));
        acc = acc.rotate_left(31);
        acc = acc.wrapping_mul(P1);
    }
    acc = acc.wrapping_add((items.len() as u64) ^ (P5 ^ 3_527_539));
    if acc == u64::MAX {
        1_546_275_796
    } else {
        acc as i64
    }
}

/// Python int `a % b` (sign of b).
#[inline]
pub fn py_imod(a: i64, b: i64) -> i64 {
    a.rem_euclid(b) + if b < 0 && a.rem_euclid(b) != 0 { b } else { 0 }
}

/// `float.hex()` exactly as CPython writes it (Objects/floatobject.c float_hex).
pub fn float_hex(x: f64) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf".to_string() } else { "-inf".to_string() };
    }
    let sign = if x.is_sign_negative() { "-" } else { "" };
    if x == 0.0 {
        return format!("{sign}0x0.0p+0");
    }
    let b = x.to_bits();
    let e = ((b >> 52) & 0x7ff) as i64;
    let frac = b & ((1u64 << 52) - 1);
    if e == 0 {
        format!("{sign}0x0.{frac:013x}p-1022")
    } else {
        format!("{sign}0x1.{frac:013x}p{:+}", e - 1023)
    }
}

#[inline]
fn pow2(e: i64) -> f64 {
    f64::from_bits(((e + 1023) as u64) << 52) // -1022 <= e <= 1023
}

/// Inverse of `float_hex` (also `float.fromhex` on the strings float.hex makes).
pub fn parse_float_hex(s: &str) -> Option<f64> {
    let (neg, t) = match s.strip_prefix('-') {
        Some(r) => (true, r),
        None => (false, s.strip_prefix('+').unwrap_or(s)),
    };
    let v = match t {
        "inf" => f64::INFINITY,
        "nan" => f64::NAN,
        _ => {
            let t = t.strip_prefix("0x")?;
            let (mant_s, exp) = match t.split_once('p') {
                Some((m, e)) => (m, e.parse::<i64>().ok()?),
                None => (t, 0),
            };
            let (ip, fp) = mant_s.split_once('.').unwrap_or((mant_s, ""));
            if ip.len() + fp.len() > 15 || ip.is_empty() {
                return None;
            }
            let mut mant: u64 = 0;
            for c in ip.chars().chain(fp.chars()) {
                mant = mant * 16 + c.to_digit(16)? as u64;
            }
            let mut f = mant as f64; // < 2**60, exact for float.hex strings (<= 53 bits)
            let mut e = exp - 4 * fp.len() as i64;
            while e > 0 {
                let k = e.min(1000);
                f *= pow2(k);
                e -= k;
            }
            while e < 0 {
                let k = (-e).min(1000);
                f *= pow2(-k);
                e += k;
            }
            f
        }
    };
    Some(if neg { -v } else { v })
}
