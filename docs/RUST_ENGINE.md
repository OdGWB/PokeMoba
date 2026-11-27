# Rust training engine — design

Status: draft, 2026-11-27. Goal: maximum CMA-ES training throughput. The Python
engine stays the game and the reference; the Rust engine is a second
implementation of the same rules, used only by headless training
(`tools/tier_sim.py` / `tools/cma_tune.py`).

## 1. Why a full engine, not more ported functions

Measured on one 18-minute 5v5 (tickprof, strides 3/2, CPython 3.14 + current
native module): **1.10 ms/tick**, of which

| step | s / 21.5k ticks | share |
|---|---|---|
| `_update_ai` (bot utility 5.6, minion AI in Rust 2.6, bot 1.6, jungler 0.7) | 8.9 | 38% |
| `world.tick` (movement + collisions, already in Rust) | 3.5 | 15% |
| `_update_combat` | 2.4 | 10% |
| per-line `_update_*` hooks (20 lines) | 2.6 | 11% |
| `_update_status` | 1.5 | 6% |
| vision (already in Rust) | 1.2 | 5% |
| evolution, items, plates, regen, shop, rest | 3.4 | 15% |

The parts already in Rust are still expensive because every tick they read
Python objects attribute by attribute (~75 ns per `getattr` from Rust, ~330 ns
per `Vec2` built). Porting more single functions keeps paying that toll and the
remaining time is spread over ~50 steps, so each further port gains 1-3%.
The toll disappears only when **Rust owns the state** for the whole match.

PyPy was measured and rejected (4.8-6.5 ms/tick: numpy via cpyext, and the
abi3 native module cannot load there).

Expected gain (estimate, to be confirmed by phase 1): a native loop over ~70
entities should cost 30-60 µs/tick, i.e. **20-35x** per match. The laptop is
power-bound at ~60 matches/min today (12-20 workers), so CPU per match maps
almost directly to matches/min.

## 2. Shape

```
tier_sim.play(job)  ──(backend="rust")──►  native.run_match(spec) -> result dict
                     └─(backend="py")───►  current Python Match (unchanged)
native.run_matches(specs, threads) -> [result]   # rayon, GIL released
```

* **Python keeps setup**: job/roster/team composition (its own `random.Random`),
  JSON data loading, map loading. It builds a `MatchSpec`: map grid + wall shape
  mask, data tables (pokemon, moves, items, types, jungle, config constants),
  the 10 picks with lanes/plans/support flags, `BotParams` per team as a float
  vector, seed, horizon, vision/minion strides, early-stop options.
* **Rust runs the whole match** and returns the same dict `play()` returns
  today, trimmed to what `cma_tune` reads (`winner`, `timeout`, `time`,
  `phi_feat`, `networth`, `end.towers`, `early_stop`, per-unit `team`/`kills`
  and the stats tier reports use). No per-tick crossing at all.
* **Batching in one process**: `run_matches` runs N matches on a rayon pool with
  the GIL released; map/data/pathfinding tables are shared read-only (`Arc`).
  Removes spawn/pickle overhead and per-worker memory duplication.
* The existing `native` crate stays as is (it serves the live game); the engine
  is a new module in the same crate (`native/src/sim/`), sharing grid, LOS,
  pathfinding and `hypot` code.

### State layout

* `World { pokemon: Vec<Pokemon>, minions: Vec<Minion>, wilds: Vec<Wild>,
  structures: Vec<Structure>, pillars, spirits, projectiles, zones, ... }`
  with one global insertion-ordered id space, because Python iterates
  `world.entities` in insertion order and several steps depend on that order.
  Removal must keep relative order (tombstone + compaction at the same point
  the Python dict would drop the key).
* `Pokemon` (350 fields in Python, most of them per-line kit state) becomes
  common fields + `kit: Kit` where `enum Kit { Scizor(ScizorState), ... }`, one
  variant per evolution line (lines evolve within the variant).
* Per-line hooks from `engine/lines.py` (`init`, `update`, `precheck`, `cast`,
  `bot_cast`, `speed_mult`) become a `trait LineHooks`, called in
  `LINE_MIXINS` order exactly like `hook_names()` does.

## 3. Exactness (hash parity with pure Python)

Target: **bit-identical** state to pure CPython, tick by tick. This is what
makes drift detectable and porting reviewable; "behaviourally similar" gives no
way to tell a bug from noise.

* **RNG**: the engine uses the global `random` module (`random()`, `choice`,
  `randrange`, `uniform`, `seed`). Rust gets an exact MT19937 port with CPython
  semantics: `seed(int)` via `init_by_array`, `random()` from two 32-bit words
  (53 bits), `_randbelow` via `getrandbits` rejection, `choice`, `shuffle`,
  `uniform = a + (b-a)*random()`, `randrange`. Every draw must happen in the
  same order as in Python — this is the main porting discipline.
* **Math**: `hypot` already reimplemented as CPython's `vector_norm` (bit-exact).
  `sin/cos/atan2/acos/exp/sqrt/floor/ceil` go to the same MSVC UCRT libm that
  CPython uses on Windows; verified per function in phase 0. Python `round()`
  (banker's), `int()` truncation, `//` and `%` on negatives need helpers.
* **Float op order**: port expressions literally (`a*b + c` stays that order; no
  algebraic rewrites, no FMA — keep `-C target-feature` without `fma`).
* **Iteration order**: dicts → insertion order; any Python `set` iterated in
  the engine must be found and given a defined order (audit in phase 0).

## 4. Parity harness (built first, used forever)

* `tools/rust_parity.py <jobs> <seconds>`: runs the same job in Python and Rust,
  both dump a canonical per-tick state (every entity, every modelled field as
  `float.hex`, plus RNG draw count), and reports the **first diverging tick,
  entity and field**. Pure-Python reference (`POKEMOBA_NO_NATIVE=1`).
* Phase gates use "N jobs x full match, zero divergence".
* `cma_tune` / `tier_sim` with `backend="rust"` run a quick parity smoke
  (3 jobs x 60 s) at start-up against the current checkout and **fall back to
  Python** if it fails — so an engine change not yet ported can never silently
  train bots on wrong rules.

## 5. Phases

Each phase ends with zero divergence on its scope and is usable on its own.

0. **Harness + foundations.** Canonical dump in Python, parity tool, MT19937,
   libm check, set-iteration audit, `MatchSpec` builder, empty `run_match`.
1. **Core match without kits.** Grid/LOS/pathfinding (reuse), movement and
   collisions, towers/plates, waves and minion AI, jungle camps and wilds,
   basic attacks + damage formulas + crits/STAB/type chart, status, regen,
   gold/xp/levels, items and item effects, evolution, respawns, smite, recall,
   surrender, win check. Each system is verified on its own with
   `tools/sim_step_parity.py`: on every tick of real matches, the Python state
   right before the system goes into Rust, the Rust system runs on it, and its
   output must equal the Python state right after (no flag in the game needed).
   When all systems are in, the full Rust loop is checked with
   `tools/rust_parity.py --b rust`.
2. **Bot AI.** `bot_utility`, `bot_plan`, `_ai_bot`, `_ai_jungler`, flee, shop,
   with `BotParams` as input. Biggest single chunk of tick time.
3. **Lines, one per step** (26 lines, ~10k Python lines in `engine/<line>.py`),
   ordered by how often they are drafted. A match runs in Rust only if all 10
   picks are ported, otherwise in Python; optional `--roster ported` to train
   on the ported subset early (biases params toward that subset — decide
   per run).
4. **Switch-over.** `run_matches` batching in `cma_tune`, worker count retuned,
   throughput measured against today's ~60 matches/min.

Rough size: phases 0-1 are the foundation (~4-5k lines of Rust), phase 2 ~1.5k,
phase 3 the bulk (~10-12k). Phase 1 alone already gives a speed number to
decide whether to continue.

## 6. Maintenance — the real cost

`engine/` had 77 commits in the last month. Every rule change must then be
made twice. Policy proposed:

* Python stays the source of truth for the rules. This policy is about the
  training engine only: the live-game module (`native/`) is required by the
  published exe (`engine/backend.py`), and a change to a function it ports must
  be made in both (CI runs `rust_parity`, py vs native).
* A rule change is "done" for training only when `rust_parity` passes; until
  then training falls back to Python automatically (section 4).
* Bot logic (`bot_utility.py`, `bot_params.py`, owned by the CMA chat) changes
  most often: params cross as data and need no port; code changes do.

## 7. Phase 0 — done (2026-11-27)

* **Determinism bug fixed in the Python engine.** The same job gave different
  states under different `PYTHONHASHSEED`s, so training workers (each with a
  random hash seed) were not reproducible. Cause: the minion spawn jitter in
  `Match._spawn_minion` hashed a tuple containing the lane *name*; it now hashes
  the lane *index* (tuple of ints: same hash in every process). Verified: same
  state hash under seeds 0, 1, 7, 12345. New reference hashes (pure Python ==
  native, `state_hash.py <job> 360`): job 0 `747a9793cd9d7337bbe3aeaa0d6c0be8`,
  job 1 `a386fdc42fa2b1fa4befa30862e40c09`, job 2 `18d84514eb382e27297497fb2890df18`.
* **`native/src/sim/`**: `rng.rs` (MT19937 with CPython semantics: seed,
  getstate/setstate, random, getrandbits, _randbelow, choice, randrange,
  shuffle, uniform), `mathx.rs` (CPython-exact helpers: `hypot`, `floor`/`ceil`/
  `round` with int semantics — no `-0.0` —, float `%` and `//`, `radians`/
  `degrees`, `hash()` of int tuples), `mod.rs` (`SimRandom`, `sim_math`,
  `sim_tuple_hash`, stub `run_match`, `SIM_SPEC_VERSION`).
* **libm check** (tests/test_sim_core.py, ~24k inputs each, bit-exact):
  `sin cos atan2 acos exp sqrt pow` from Rust equal CPython's on Windows/UCRT.
  Re-run the test after any toolchain or platform change.
* **Set iteration audit**: only `hash()` call in the engine was the one above;
  sets are iterated in a few kit helpers but the state is now identical across
  hash seeds, so no observable order depends on string hashing. Sets of ints
  have a fixed CPython order: when porting a function that iterates a set, keep
  the order or check it is order-independent.
* **`tools/sim_spec.py`**: `capture(job)` runs `tier_sim.play` setup and stops
  before the first tick; `build_spec(job)` = map (tiles + fine wall mask), RNG
  state at that instant, teams, config, data JSON, and the full initial
  `snapshot()` (0.4 s, 1.9 MB). Python keeps all setup; Rust starts from the
  snapshot.
* **`tools/rust_parity.py`**: per-tick digests of the canonical snapshot
  (time, RNG, Match fields, every entity field; caches and back-references
  excluded), first diverging tick, then the differing fields. `py` vs `native`:
  zero divergence on 3 jobs x 240 s. `--b rust` reports the stub (exit 3).

Phase 1 starts by making `run_match` load `spec["initial"]` into Rust structs
and return the same snapshot at tick 0 (round-trip), then adds systems one at
a time with the parity tool on every step.

## 7b. Phase 1 — progress

* **Rust world state** (`sim/world.rs`): `Ent` rows loaded from the canonical
  snapshot (`sim_fields()["in"]`), written back in the same canonical form.
* **Per-system harness** (`tools/sim_step_parity.py`): hooks the real system in
  a Python match, feeds the state right before it to Rust, compares the fields
  the system writes. `--inject-stuck N` puts a unit inside a wall every N ticks
  (the anti-stuck branch never happens on its own in matches); `--parts R`
  times each Rust phase.
* **`World.tick` ported** (`sim/movement.rs`: advance_unit, circle collisions,
  tower push-out; grid helpers shared with the live `GridView`).
  Zero divergence on 3 jobs x 18 min (88.6k ticks) and on 2 jobs x 10 min with
  961 forced stuck-in-wall cases and 90k tower contacts.
* **Speed of this system**: Python + current extension 143-190 µs/tick (machine
  load varies), Rust on owned state 29 µs/tick (~5x), 74 units/tick. Per phase:
  advance 10.9, collisions 15.1, towers 0.2 µs. The collision pair set was a
  HashSet; now a bitset by unit index (21.4 -> 15.1 µs, also used by the live
  game, hashes unchanged). What is left is real work: `keep_off` (wall sampling)
  per overlapping pair, 2 iterations.
* **Revised estimate**: movement alone costs ~29 µs in Rust, so the full tick
  will be well above the 30-60 µs of section 1; a realistic guess is 100-200
  µs/tick, i.e. **~6-10x** per match instead of 20-35x. Re-measure after
  combat and minion AI are in.

## 8. Open decisions

1. Bit-identical parity (recommended) vs. behavioural parity.
2. Port-every-change policy vs. freezing a rules version for training runs.
3. Whether to train on a restricted roster during phase 3.
