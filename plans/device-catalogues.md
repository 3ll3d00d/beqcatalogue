# Device-specific optimised catalogues

Status: plan for review, revision 3, 2026-10-06. Nothing implemented yet.

Decisions from review 1:

1. Profiles are keyed by **numerical format** (`float32-96k`), not by device model.
2. Re-evaluation happens **only when explicitly signalled**: a committed `revision` bump in
   the profile config (§4).
3. Device stages publish **wherever the main catalogue publishes today**: every branch, and PRs
   to their head branch.
4. The website gains a **device comparison view**, similar to the compare chart. It shows only
   profiles that produced an optimisation, and title pages are flagged where one is available
   (§7). Badges go **under each format heading**, and the flag never makes a 404 request
   (decided in review 2).
   The flag finds entries by page URL, so frozen pages with no compare link are covered too.
   The initial build runs locally from the existing cache.

## Goal

Publish one extra catalogue per known format profile. Each holds only the catalogue entries
that beqforge's `beqoptimiser` improves for that profile, keyed by the main catalogue
`digest`, with the replacement biquads. The work runs incrementally as its own CI stage
after the main build, with one parallel job per profile. The profiles come from committed
config. The site shows the effect of the optimisation, and flags it on the title pages.

## What exists today

- **beqcatalogue** `update.yaml`: a single `build` job collates inputs, runs
  `beqcatalogue/__init__.py` (which writes `docs/database.json`, 15,474 entries and
  15,396 distinct digests), then commits with `git-auto-commit` and updates issues. It sits in
  concurrency group `publish` with `cancel-in-progress: true`.
- `digest` = sha256 of `title, filters, mv, season, episode`. ezbeq already indexes and looks up
  entries by it (`ezbeq/catalogue.py:find_by_digest`), so it is the natural join key. 75
  digests repeat across entries, but a shared digest means identical filters and offset, so
  the optimiser result is identical too.
- Published `filters[*].biquads` contain only `96000`. `beqoptimiser.cli.prepare_entry` treats
  them as the sent baseline at 96 kHz and falls back to RBJ at 48 kHz. That matches what ezbeq
  actually loads.
- **The compare feature**:
  - `build_compare_data` writes one slim `docs/compare/<key>.json` per title, plus
    `titles.json`.
  - `docs/javascripts/biquad.js` recomputes RBJ responses client-side, with `FS` hard-coded to
    96000.
  - `compare.js` overlays the responses in Chart.js.
  - Every title page carries a `[Compare across authors](../compare/index.md?t=<key>)` link.
    Generated pages have one per format section. The frozen aron7awol/mobe1969 pages have one
    page-level link, added by `scripts/backfill_compare_links.py`.
- **beqforge** (`../beqforge`, v0.1.0, not on PyPI yet, last tag v0.0.2):
  - `beqoptimiser.cli.optimise_entry(entry, rate=, settings=, cache=)` returns
    `{result: {outcome, original_error_db, candidate_error_db, ...}, variant: {..., biquads:
    [{b, a}]} | None}`.
  - Outcomes are `within_margin | replacement | no_replacement | unresolved`, and the CLI
    adds `unsupported`.
  - Precision is hard-wired to `Float32()` inside `optimise_entry`.
- **Optimiser cache**: `ResultCache(dir)` combines a disk cache with a bundled read-only
  seed of 29,268 results covering the 10 Sep 2026 snapshot at 48k and 96k, float32, default
  settings. A seed hit needs an exact implementation identity: beqforge `version` + the
  `core.py`/`biquad.py` hashes + **numpy 2.4.2 + scipy 1.18.1** + Linux x86_64 with an 80-bit
  long double. GitHub `ubuntu-latest` meets the platform part, so it can hit the seed only if
  numpy/scipy are pinned to those versions. A full cold run took about 4,400 s.

## Design

### 1. Profile config (committed; this drives the matrix)

`devices/profiles/<id>.json`, one file per profile:

```json
{
  "id": "float32-96k",
  "label": "float32 @ 96 kHz",
  "description": "float32 custom biquads at a 96 kHz internal rate (e.g. miniDSP 2x4 HD)",
  "rate": 96000,
  "storage": {"type": "float32"},
  "transport": {"type": "float32"},
  "settings": {},
  "revision": 1,
  "enabled": true
}
```

- `storage`/`transport` map onto `beqoptimiser.Float32` / `FixedPoint(integer_bits,
  fractional_bits)`. `settings` overrides `beqoptimiser.Settings` fields (empty = defaults,
  which keeps seed hits).
- The profile is a format, so devices sharing a format share one catalogue and one set of
  work. ezbeq owns the device→profile mapping. `description` may name example devices for
  humans only.
- `label` is what the website shows.
- `revision` is the re-evaluation signal (§4).
- Initial profiles: `float32-96k` and `float32-48k`, the two the seed and report already
  cover.

### 2. Files written

Per profile:

| Path | Purpose | Contents |
| --- | --- | --- |
| `docs/devices/<id>.json` | **Device catalogue** (the consumer contract, e.g. ezbeq) | Only entries with outcome `replacement` or `improvement` |
| `meta/devices/<id>.tsv` | **Evaluation ledger**, internal | One line per evaluated digest, whatever the outcome |

Shared and derived (§7), regenerated from the files above plus `database.json`:

| Path | Purpose |
| --- | --- |
| `docs/devices/index.json` | Profiles: id → file, label, rate, precision, entry count, content sha256 |
| `docs/devices/compare/<compare key>.json` | Per-title data for the device comparison view and title-page flag. Written only for titles with ≥1 optimisation |
| `docs/devices/titles.json` | Title search index for the view: optimised titles only |
| `docs/devices/pages/<NN>.json` | 256 hash-bucketed shards (by page path) of optimised entries, always all present, so the title-page flag never makes a 404 request (7d) |

Device catalogue, kept minimal. Provenance shared by all entries goes in the header once,
with nothing per entry except the coefficients:

```json
{"schema_version":1,"profile":"float32-96k","revision":1,"rate":96000,"storage":"float32",
 "transport":"float32","loading_model":"additive-feedback-decimal17-v1",
 "entries":{
"<digest>":[{"b":["…","…","…"],"a":["…","…"]},…],
…}}
```

- Sections are expanded (counts flattened) in cascade order, using the `b`/`a` additive-feedback
  17-digit strings from `variant.biquads`, the same convention as `filters[*].biquads`.
- `mv`, title and the rest are not duplicated, because the consumer joins on `digest`.
- No optimiser version is recorded in the header, because entries may come from different
  beqforge versions (§4). Per-digest versions live in the ledger.
- The file is written deterministically: keys sorted, one entry per line for small git diffs,
  and no timestamps.
- Add `docs/devices/*.json -delta` to `.gitattributes`, as for `database.*`.

Ledger, one sorted line per digest:

`<digest>\t<outcome>\t<revision>\t<original_error_db>\t<candidate_error_db>\t<beqforge version>`

- `outcome` is one of `R` (replacement), `I` (improvement), `W` (within margin), `N` (no replacement), `U`
  (unresolved) or `X` (unsupported).
- The error columns hold the optimiser's own validated maximum error over 2–200 Hz (empty
  where not applicable). The website displays these authoritative numbers, so they don't need
  to go in the device catalogue.
- The ledger exists because the device catalogue deliberately omits non-replacements. Without
  it we couldn't tell "evaluated, nothing to store" apart from "never evaluated".

### 3. The update algorithm (`beqcatalogue/devices.py update --profile <id>`)

Every run is a pure function of (current `docs/database.json`, current ledger, profile
config):

1. Load `database.json` and build `digest → first entry`.
2. **Prune**: drop ledger lines and device entries whose digest is no longer in the catalogue.
   This covers edited and removed entries. An edited entry gets a new digest, so it shows up
   as new.
3. **Pending** = catalogue digests that are not in the ledger, or whose ledger `revision` is
   lower than the profile's `revision`.
   - This is a set difference, not a git range, so it naturally covers any number of commits
     since the last run, as well as runs that failed or were cancelled.
4. Evaluate the pending digests in a `ProcessPoolExecutor` (4 vCPUs on ubuntu-latest), sorted
   by digest so the order is deterministic.
   - Call `optimise_entry` with the profile's rate, settings and a `ResultCache` at
     `.cache/beqoptimiser/<id>`.
   - Stop taking new work once the time budget runs out (`--budget-minutes`, default 45).
     Unfinished digests stay pending for the next run, so a big backlog drains over several
     runs instead of hitting the 6 h job limit.
5. Record each finished digest in the ledger with its outcome. Add `R` and `I` entries to the
   device catalogue, and remove any earlier entry for a digest that is no longer `R`. Every
   other outcome writes a ledger line only. An unexpected exception (not one of the CLI's
   "unsupported" exceptions) writes nothing and is reported. The digest is retried next run,
   but it never blocks the others.
6. Write both files only if their bytes changed. Print counts to `$GITHUB_STEP_SUMMARY`:
   pending, evaluated, by outcome, cache hits vs computed, remaining.

How each requirement is met:

- **Only new entries**: covered by the set difference in step 3.
- **Never re-optimise the same thing**: a ledger hit at the current revision skips the digest
  regardless of outcome, including `N`/`U`/`X`.
- **Only optimised entries stored**: covered by step 5.
- **Idempotent**: a second run with no catalogue change leaves zero pending and writes nothing,
  so there is no commit. Re-running after a partial or cancelled run converges on the same
  bytes, because the optimiser is deterministic and output is keyed and sorted.

`optimise_entry` hard-wires `Float32()`. Rather than copying it, add a small upstream change
in beqforge: `optimise_entry(..., precision=, transport=)` parameters defaulting to
`Float32()`. Until that lands, only float32 profiles are accepted, and `devices.py` rejects
any other config with a clear error.

### 4. Re-evaluation: only when signalled

- The **only** trigger for re-evaluating a digest that is already in the ledger is bumping
  `revision` in its committed profile config. Nothing else re-evaluates existing entries:
  not upgrading beqforge, not numpy/scipy bumps, not changing the workflow.
- The signal is a committed file change, so it is reviewable and auditable. It also survives
  partial progress: a revision bump drains over as many budgeted runs as it needs, and the
  ledger tracks which digests are already done at the new revision.
- An explicit `workflow_dispatch` input was rejected, because it would leave no committed
  state for the following runs to continue from.
- Changing a profile's `settings`/`storage`/`transport` without bumping `revision` fails
  validation, so a config edit can't silently leave mixed results behind. The `matrix` job
  checks this by comparing the config's hash with the hash recorded in the device catalogue
  header.
- While a re-evaluation is in progress, existing device entries **stay published** until
  their digest is re-evaluated at the new revision.
- Upgrading beqforge without a revision bump only affects digests that are evaluated for the
  first time from then on. The ledger's version column shows which version produced each
  result.

### 5. Dependencies

- Add an optional Poetry group, so the main build is unaffected:
  ```toml
  [tool.poetry.group.optimiser]
  optional = true
  [tool.poetry.group.optimiser.dependencies]
  beqforge = { git = "https://github.com/3ll3d00d/beqforge.git", rev = "<sha>", extras = ["optimiser"] }
  numpy = "==2.4.2"   # seed identity
  scipy = "==1.18.1"  # seed identity
  ```
  Switch to the PyPI release once beqforge publishes one. The Python ranges are compatible
  (catalogue 3.13; beqforge 3.13–3.14).
- The numpy/scipy pins matter only while CI is expected to hit the bundled seed. Once the
  ledger is bootstrapped (§9), CI only evaluates new digests, so the pins can be relaxed
  later.
- Move `compute_compare_key` (and `slugify` use, if needed) into a stdlib-only module, e.g.
  `beqcatalogue/keys.py`. `__init__.py`, `scripts/backfill_compare_links.py` and `devices.py`
  all import it from there.
- `devices.py` must not import `beqcatalogue/__init__.py` (markdown/jinja). Run it as a script,
  like the existing build. The `matrix` and `site` subcommands use only the standard library,
  so those jobs need no dependency install.

### 6. Workflow (`update.yaml`)

```
build ──► device-matrix ──► device-catalogue (matrix, fail-fast: false) ──► device-publish
```

- **`build`**: unchanged, apart from `poetry install --without optimiser` and a new output
  `commit=${{ steps.pub-cat.outputs.commit_hash || github.sha }}`.
- **`device-matrix`** (`needs: build`):
  - Checks out `needs.build.outputs.commit`, sets up Python and runs
    `python beqcatalogue/devices.py matrix >> $GITHUB_OUTPUT`.
  - It reads `devices/profiles/*.json` (enabled only) and validates each one (§4: a config
    change without a revision bump fails here). For each profile it computes pending work
    cheaply from `database.json` plus the ledger, with no optimiser needed.
  - Outputs:
    - `matrix={"include":[{"profile":"float32-96k","pending":12},…]}`: only profiles with
      pending > 0, so quiet runs cost almost nothing.
    - `has_work=true|false`: an empty matrix is a workflow error, so this gates the next job.
- **`device-catalogue`**:
  - Runs when `needs.device-matrix.outputs.has_work == 'true'` with
    `strategy.matrix: ${{ fromJSON(needs.device-matrix.outputs.matrix) }}` and
    `timeout-minutes: 60`.
  - Steps: checkout the same commit, then Python + Poetry, then
    `poetry install --only optimiser --no-root` (its own venv cache key).
  - **Optimiser cache**:
    - `actions/cache/restore` for `.cache/beqoptimiser/<profile>`, with key
      `beqopt-<profile>-<hash(poetry.lock, profile json)>-<run_id>-<attempt>` and
      `restore-keys: beqopt-<profile>-<hash>-`.
    - After the update, `actions/cache/save` with `if: always()`, so progress from failed or
      cancelled runs is kept.
    - The run id goes in the key because GitHub cache keys are immutable and can't be
      updated in place. A separate directory per profile stops parallel jobs racing to save.
  - Then run `python beqcatalogue/devices.py update --profile ${{ matrix.profile }} --cache-dir …`
    and upload `docs/devices/<id>.json` + `meta/devices/<id>.tsv` as artifact `device-<id>`.
  - **No commits happen in matrix jobs**, because parallel pushes would race.
- **`device-publish`**:
  - Uses `needs: [build, device-matrix, device-catalogue]` with
    `if: always() && needs.device-matrix.result == 'success'`, so it runs even when the matrix
    was skipped.
  - Checks out the same ref the build pushed to, as `build` does today
    (`ref: ${{ github.head_ref }}`).
  - Downloads any `device-*` artifacts (each profile owns its files, so they never clash).
  - Runs `python beqcatalogue/devices.py site` (§7). This always runs, even with no new
    evaluations, because a title rename can change compare keys without changing digests.
  - Commits with `git-auto-commit` ("Updated device catalogues") if anything changed.
  - A profile whose job failed simply has no artifact, so the others still publish.
- **Branch and PR behaviour**: identical to the current build, which publishes on every branch
  and pushes PR results to the head branch. No extra filtering.
- Keep the workflow-level `concurrency: publish, cancel-in-progress: true`. A newer push
  cancels in-flight device jobs, and the ledger plus `always()` cache save mean nothing is
  lost: the next run picks up the remainder.

### 7. Website: device comparison view and title-page flag

#### 7a. Per-title data (`devices.py site`)

This mirrors `build_compare_data`. It groups optimised digests by compare key and writes
`docs/devices/compare/<key>.json` only for titles where at least one entry has at least one
`R`:

```json
[{"digest":"…","author":"halcyon888","catalogue_url":"…/halcyon888/breaking/#dd-atmos",
  "audioTypes":["DD+ Atmos"],"edition":"","season":"","episode":"",
  "filters":[{"type":"LowShelf","freq":20,"gain":5,"q":0.9,"count":3,
              "biquads":{"96000":{"b":[…],"a":[…]}}}],
  "profiles":{"float32-96k":{"after":[{"b":[…],"a":[…]},…],
                              "before_db":12.766,"after_db":0.318}}}]
```

- Only profiles with an `R` for that digest appear, so "only shown where there is any
  optimisation" holds per entry.
- `before_db`/`after_db` come from the ledger: the optimiser's validated figures.
- The published `biquads` are included so the browser can reproduce the "before" curve
  exactly as it is loaded (see 7b).
- The function also writes `docs/devices/index.json`, `docs/devices/titles.json` and all
  256 `docs/devices/pages/<NN>.json` shards (7d). It deletes stale compare files, the same
  way `build_compare_data` does. Output is deterministic.

#### 7b. Response maths (`biquad.js`)

- Make the sample rate a parameter instead of the hard-coded `FS = 96000`. Callers in
  `compare.js` pass 96000, so its behaviour is unchanged.
- Add `cascadeFromCoefficients(sections, rate, {float32: true})`. It parses the `b`/`a`
  strings and rounds each one with `Math.fround`, which models float32 storage and
  transport. It then evaluates the magnitude with the feedback-sign convention converted.
- For each profile, mirror `prepare_entry`:
  - **Ideal**: float64 RBJ from the parameters at the profile rate.
  - **Before (as loaded)**: the published `biquads[rate]` if present, otherwise RBJ at that
    rate, then rounded to float32.
  - **After (as loaded)**: the device catalogue biquads, rounded to float32.

#### 7c. View (`docs/devices/index.md`, `devices.js`, nav entry "Device optimisation")

- Takes `?t=<key>`, with optional `&d=<digest>` to preselect an entry. Has the same title
  search as Compare, backed by a `docs/devices/titles.json` index of optimised titles.
- An entry picker (author, format, edition, season/episode) appears when the title has
  several optimised entries.
- One toggle per profile present for that entry, coloured as in Compare.
- **Chart 1, response**: ideal, plus before/after as loaded for each profile shown, at
  1–200 Hz on a log axis.
- **Chart 2, error vs ideal (dB)**: before (dashed) and after (solid) per profile, with the
  ±0.5 dB margin shaded. The improvement is a fraction of a dB to a few dB, which disappears
  on a ±15 dB response chart, so this is the chart that shows it.
- **Table**: profile label, rate, validated max error before → after (from the data file),
  with a note that these are predicted coefficient responses, not hardware measurements.
- A link back to the title page and to "Compare across authors".

#### 7d. Title-page flag (`devices-flag.js`, client-side, no page regeneration)

The flag finds a page's entries **by the page's own URL**, not through the compare link.
18 frozen pages (2 aron7awol, 16 mobe1969) have no compare link, because
`backfill_compare_links.py` skipped pages whose entries disagree on the compare key. A
lookup by URL covers every page, generated or frozen, with no backfill.

- `devices.py site` writes 256 page shards, `docs/devices/pages/<NN>.json`.
  - `NN` = FNV-1a 32-bit hash of the entry's page path mod 256, as two hex digits. The page
    path is `catalogue_url` with the site prefix and anchor removed, e.g.
    `aron7awol/56743108/`.
  - Each shard maps page path → `[{anchor, digest, key, profiles: [label, …]}]`.
  - Only optimised entries are listed, but all 256 files are always written, even when empty
    (`{}`). The request therefore always succeeds and **never 404s**.
  - At ~12k optimised entries that is roughly 50 entries and a few KB per shard, and the
    browser caches it.
- On each page load (via `document$.subscribe`, as in `compare.js`), the script:
  1. Works out the current page path relative to the site root, using the theme's `base`
     from the `#__config` JSON block that Material/materialx injects.
  2. Hashes the path and fetches that one shard.
  3. If the page is present, inserts a badge after each format heading whose `id` matches an
     entry's `anchor`, e.g. "Optimised for float32 @ 96 kHz, float32 @ 48 kHz". The badge
     links to `devices/?t=<key>&d=<digest>`.
- **Fallback**: if an entry's anchor isn't on the page, the badge goes under the page `h1`.
  That currently affects 3 frozen entries whose anchors don't match a heading.
- The flag needs only the shard, and the per-title compare file is fetched by the device
  view alone. A page that isn't in its shard shows nothing.
- FNV-1a is a few lines in both Python and JS. Unlike SubtleCrypto it isn't async and doesn't
  need a secure context. A shared fixture test pins the two implementations to the same
  bucket numbers.
- Why client-side:
  - The device stage runs after the main build. A statically rendered flag would lag one
    main build behind, and main builds are triggered by upstream author pushes, so the lag
    could be days.
  - Frozen pages would otherwise need regenerating or patching.
  - Trade-off: the flag needs JavaScript and isn't indexed by search.
- Optional: in Compare, a "device optimisation available" link next to each entry that has
  one, using the same data.

### 8. Tests

`tests/test_device_catalogue.py` injects a fake optimiser function, so it needs no scipy:

- pending = new ∪ revision below current
- pruning of removed or edited digests
- only `R` stored, and an `R` that becomes non-`R` after a revision bump is removed
- `X`/`N`/`U` recorded and not retried at the same revision
- an unexpected exception is not recorded
- a time-budget stop leaves the remainder pending, and a second run completes it
- **idempotency**: a second run is byte-identical and writes nothing
- duplicate digests are evaluated once
- deterministic output order
- a config change without a revision bump is rejected
- `matrix` output for zero, one and several profiles, with disabled profiles excluded and
  `has_work` handled
- `site`: per-title files only for titles with an optimisation, profiles filtered per entry,
  stale files removed, deterministic output, all 256 page shards always present, every
  optimised entry in exactly the right shard, and frozen-page paths covered

One integration test uses the real `beqoptimiser` (`pytest.importorskip`) on a tiny
two-entry catalogue at 48k and 96k.

For the JS, a small Node check (no framework) that `biquad.js`'s float32 coefficient path
reproduces the optimiser's before/after max errors within a small tolerance for a few
fixtures, e.g. Breaking (2022) at 96k and Tracers (2015). The browser uses a different
grid, so this is a sanity check, not an equality test. The same Node check compares JS FNV-1a
buckets with Python's for a shared list of fixture keys.

### 9. Bootstrap: run locally from the existing cache

The initial device catalogues are built **on the dev machine**, from the local cache, and
committed. CI never runs the full catalogue: its first run only handles entries added after
the bootstrap commit.

What the local cache holds (checked 2026-10-06):

- The bundled seed in `../beqforge/beqoptimiser/data/seed.json.gz`, with 29,268 results. Its
  identity matches the current checkout: the `core.py` and `biquad.py` sha256 values match
  `seed-manifest.json`, and beqforge's venv has numpy 2.4.2 and scipy 1.18.1.
- The same results in library-cache form at `/tmp/beqoptimiser-library-cache` (29,268
  files, 115 MB). `/tmp/beq-catalogue-report-cache` is the older report-format cache, which
  `ResultCache` can't read directly.
- `~/.cache/beqoptimiser` holds only 2 entries.
- Before the bootstrap, copy `/tmp/beqoptimiser-library-cache` into a durable directory,
  e.g. `~/.cache/beqoptimiser`, because `/tmp` doesn't survive a reboot. The seed alone is
  enough as long as the environment matches. The disk copy is insurance, and it also keeps
  whatever the bootstrap computes for entries newer than the 10 Sep snapshot.

Steps:

1. In beqcatalogue's venv, `poetry install --with optimiser`. For local runs only, beqforge
   may be overridden with an editable path dependency on `../beqforge`, using
   `poetry run pip install -e ../beqforge[optimiser]` so the lock file is untouched. The
   pinned git rev must be the same commit, so the seed and the implementation identity are
   identical in both.
2. Run `poetry run python beqcatalogue/devices.py bootstrap --cache-dir ~/.cache/beqoptimiser --workers 12`.
   - This runs `update` for every enabled profile with no time budget, then `site`.
   - `--workers` sets the process-pool size, which is 4 by default for CI.
   - Before it starts, it prints the implementation identity next to the seed manifest. If
     they differ, it stops unless `--allow-cold` is given, so you never start a long cold run
     by accident.
3. Check the summary per profile: there should be almost no computed results apart from
   entries added or changed since 10 Sep. Expect outcome counts close to the report's
   (96k: 10,400 replacements; 48k: 4,573), adjusted for catalogue changes since then.
4. Spot-check the device view and the badges locally with `mkdocs serve`: Breaking (2022)
   and Tracers (2015), a frozen mobe1969 page with no compare link, and a TV page.
5. Commit `devices/profiles/*`, `meta/devices/*`, `docs/devices/*`, the site changes and the
   workflow together.

CI's optimiser cache starts empty, and that's fine: the ledger means CI only ever evaluates
new digests, which would be misses in any cache.

## Implementation order

1. beqforge: add `precision`/`transport` parameters to `optimise_entry` (optional; float32-only
   is fine to start). Pin the commit.
2. `pyproject.toml` optimiser group, then `poetry lock`. Extract `keys.py`.
3. `beqcatalogue/devices.py` (`matrix`, `update`, `site`, `bootstrap`) with its tests.
4. `biquad.js` rate parameter and float32 path, then `devices.js`, `devices-flag.js`, the
   view page, the nav entry and CSS.
5. Profile configs, `devices.py bootstrap`, then run the bootstrap locally from the dev
   cache (§9).
6. Workflow jobs (§6), then verify on a branch with `workflow_dispatch`:
   - a run with no catalogue change only runs the matrix and site jobs, with no commit;
   - adding a test profile produces a matrix job that publishes;
   - bumping its `revision` re-evaluates it;
   - a re-run produces no commit.
7. Separately: the ezbeq consumer (load `devices/<profile>.json`, map the device to a format
   profile, fall back to authored filters). This is out of scope here.

## Remaining questions

None. Ready to implement on approval.

## Revision 2: publish improvements (2026-10-06)

beqforge's optimiser originally published a candidate only when it met the 0.5 dB margin, discarding
candidates that were better than the authored coefficients but missed it (the `N` outcome). At
revision 1 that was 2,366 titles at 96 kHz and 113 at 48 kHz, e.g. a 16.6 dB error improved to
1.3 dB. beqforge 0.2.0 assesses candidates over the 2-200 Hz matching band only (the out-of-band
guard no longer rejects anything) and returns a candidate which misses the margin but is strictly
better than the original as `improvement` (ledger `I`). Both profiles are bumped to revision 2 so
every digest is re-evaluated, and both `R` and `I` entries are published.
