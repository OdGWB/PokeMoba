//! MT19937 with exactly CPython's `random` semantics (Modules/_randommodule.c +
//! Lib/random.py, 3.14): same seeding, `random()`, `getrandbits`, `_randbelow`,
//! `choice`, `randrange`, `shuffle`, `uniform`. The training engine draws in the
//! same order as the Python engine, so the two stay bit-identical.

const N: usize = 624;
const M: usize = 397;
const MATRIX_A: u32 = 0x9908_b0df;
const UPPER: u32 = 0x8000_0000;
const LOWER: u32 = 0x7fff_ffff;

#[derive(Clone)]
pub struct PyRng {
    mt: [u32; N],
    mti: usize,
}

impl PyRng {
    fn init_genrand(&mut self, s: u32) {
        self.mt[0] = s;
        for i in 1..N {
            let p = self.mt[i - 1];
            self.mt[i] = 1_812_433_253u32.wrapping_mul(p ^ (p >> 30)).wrapping_add(i as u32);
        }
        self.mti = N;
    }

    fn init_by_array(&mut self, key: &[u32]) {
        self.init_genrand(19_650_218);
        let (mut i, mut j) = (1usize, 0usize);
        for _ in 0..N.max(key.len()) {
            let p = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ (p ^ (p >> 30)).wrapping_mul(1_664_525))
                .wrapping_add(key[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
            if j >= key.len() {
                j = 0;
            }
        }
        for _ in 0..N - 1 {
            let p = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ (p ^ (p >> 30)).wrapping_mul(1_566_083_941)).wrapping_sub(i as u32);
            i += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
        }
        self.mt[0] = 0x8000_0000;
    }

    /// `random.seed(n)` for an int n (all bits used, sign dropped).
    pub fn from_seed(n: i128) -> Self {
        let mut r = PyRng { mt: [0; N], mti: N + 1 };
        let mut a = n.unsigned_abs();
        let mut key = Vec::new();
        while a != 0 {
            key.push(a as u32);
            a >>= 32;
        }
        if key.is_empty() {
            key.push(0);
        }
        r.init_by_array(&key);
        r
    }

    /// `random.setstate(state)`: the 624 words plus the position (`getstate()[1]`).
    pub fn from_state(words: &[u32], pos: usize) -> Option<Self> {
        if words.len() != N || pos > N {
            return None;
        }
        let mut mt = [0u32; N];
        mt.copy_from_slice(words);
        Some(PyRng { mt, mti: pos })
    }

    pub fn state(&self) -> (Vec<u32>, usize) {
        (self.mt.to_vec(), self.mti)
    }

    pub fn next_u32(&mut self) -> u32 {
        if self.mti >= N {
            let mt = &mut self.mt;
            let mag = |y: u32| if y & 1 != 0 { MATRIX_A } else { 0 };
            for kk in 0..N - M {
                let y = (mt[kk] & UPPER) | (mt[kk + 1] & LOWER);
                mt[kk] = mt[kk + M] ^ (y >> 1) ^ mag(y);
            }
            for kk in N - M..N - 1 {
                let y = (mt[kk] & UPPER) | (mt[kk + 1] & LOWER);
                mt[kk] = mt[kk + M - N] ^ (y >> 1) ^ mag(y);
            }
            let y = (mt[N - 1] & UPPER) | (mt[0] & LOWER);
            mt[N - 1] = mt[M - 1] ^ (y >> 1) ^ mag(y);
            self.mti = 0;
        }
        let mut y = self.mt[self.mti];
        self.mti += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c_5680;
        y ^= (y << 15) & 0xefc6_0000;
        y ^ (y >> 18)
    }

    /// `random.random()`: 53 bits from two words.
    pub fn random(&mut self) -> f64 {
        let a = (self.next_u32() >> 5) as f64;
        let b = (self.next_u32() >> 6) as f64;
        (a * 67_108_864.0 + b) * (1.0 / 9_007_199_254_740_992.0)
    }

    /// `random.getrandbits(k)` for 0 <= k <= 64 (low word drawn first).
    pub fn getrandbits(&mut self, k: u32) -> u64 {
        if k == 0 {
            return 0;
        }
        if k <= 32 {
            return (self.next_u32() >> (32 - k)) as u64;
        }
        let lo = self.next_u32() as u64;
        let hi = (self.next_u32() >> (64 - k)) as u64;
        lo | (hi << 32)
    }

    /// `Random._randbelow(n)`, n > 0 (rejection on n.bit_length() bits).
    pub fn randbelow(&mut self, n: u64) -> u64 {
        let k = 64 - n.leading_zeros();
        let mut r = self.getrandbits(k);
        while r >= n {
            r = self.getrandbits(k);
        }
        r
    }

    /// Index picked by `random.choice(seq)` when len(seq) == len (> 0).
    pub fn choice_index(&mut self, len: usize) -> usize {
        self.randbelow(len as u64) as usize
    }

    /// `random.randrange(start, stop)` (step 1, stop > start).
    pub fn randrange(&mut self, start: i64, stop: i64) -> i64 {
        start + self.randbelow((stop - start) as u64) as i64
    }

    /// `random.shuffle(x)` in place.
    pub fn shuffle<T>(&mut self, x: &mut [T]) {
        for i in (1..x.len()).rev() {
            let j = self.randbelow(i as u64 + 1) as usize;
            x.swap(i, j);
        }
    }

    /// `random.uniform(a, b)`.
    pub fn uniform(&mut self, a: f64, b: f64) -> f64 {
        a + (b - a) * self.random()
    }
}
