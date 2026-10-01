# data2prompt Improvement Program

> **Status: design space** (per CLAUDE.md, `plans/` never describes current
> behavior; `docs/` does). This file is the **single, session-independent
> reference** for the improvement program: what is done, what is next, the specs
> for every open item, the decisions the owner made, and the exact workflow used to
> build and review the work. A new session should be able to continue from this file
> alone.
>
> Last updated: 2026-10-01, after Wave 1 (main `94b1204`, to ship as **v1.1.0**).
> It supersedes the unbuilt items of `value_boost_roadmap.md`: the owner already
> took what they wanted from it, so do not re-propose its items (API, MCP, config
> file, `--focus`, compression report, smart sampling, PII redaction, Excel
> formulas, cache/watch, `--split`, polars, DuckDB).

---

## 1. Quick start for a new session

1. **Read, in order:**
   - this file
   - the repo `CLAUDE.md`
   - `docs/architecture.md`
   - `docs/output-contract.md`
   - `.claude/backlog/BRIEFING.md`: the agent protocol, paths and environment
     traps
2. **Check the kit exists:** `.claude/backlog/` should hold `BRIEFING.md`,
   `make_fixture.py`, `snapshot.py`, `fixture_proj/` and `baseline/`, and
   `.claude/agents/` should hold `d2p-*.md`. Both folders are gitignored, so they
   are local to this machine. If they are missing, rebuild them from §3.3.
3. **Refresh the baseline from current main** before the wave starts:
   ```bash
   "/d/miniconda3/python.exe" .claude/backlog/snapshot.py . .claude/backlog/baseline
   "/d/miniconda3/python.exe" -m pytest -q        # record the test count
   ```
4. **Pick the wave** from §5 (Next wave) and run the pipeline in §3. Report to the
   owner at the end of the wave (§3.6).

---

## 2. Program status

| # | Item | Status | Where it lives now |
|---|---|---|---|
| 1 | Honest inclusion statuses | ✅ Done (W1) | `docs/parsers.md` (Inclusion Status), `docs/output-contract.md`, `docs/output.md` |
| 2 | Silent delimiter / encoding misreads | ⏳ Open, Wave 2 | §6 |
| 3 | Sample tables: broken rendering + wasted tokens | ✅ Done (W1) | `docs/parsers.md`, `docs/output.md`, `docs/constants.md` |
| 4 | Smart column profiles (+ 5b lean-stats step) | ⏳ Open, Wave 2 | §6 |
| 5a | Budget ladder: schema-only before dropping stats | ✅ Done (W1) | `docs/budget.md` |
| 5b | Budget ladder: intermediate "lean stats" step | ⏳ Open, built with item 4 | §6 (item 4) |
| 6 | Project Map: join keys + which code reads which data | ⏳ Open, Wave 3 | §6 |
| 7 | Table-limit truncation cuts rows and notices | ✅ Done (W1) | `docs/parsers.md` |
| 8 | Scanner hygiene: `.venv`, Office lock files | ✅ Done (W1) | `docs/constants.md`, `docs/utils.md`, `docs/cli.md` |
| 9 | Pipe-ready CLI: path argument, `--stdout`, `python -m` | ⏳ Open, Wave 2 | §6 |
| 10 | Wide tables: column-family folding | ⏳ Open, Wave 2 (after 4) | §6 |
| 11 | More tabular formats (`.tsv`, `.csv.gz`, `.jsonl`, …) | ⏳ Open, Wave 2 (after 2) | §6 |
| 12 | Notebooks: ANSI noise + execution-state forensics | ✅ Done (W1) | `docs/parsers.md`, `docs/constants.md` |
| 13 | Prompt-cache-friendly document prefix | ✅ Done (W1) | `docs/output.md`, `docs/output-contract.md` (invariant 7) |
| 14 | `--budget` reads each file once | ⏳ Open, Wave 3 | §6 |
| 15 | Optional fast readers (pyarrow CSV, calamine Excel) | ⏳ Open, Wave 3, **needs owner decision** | §6 |
| 16 | Parquet `--schema-only` from metadata | ⏳ Open, Wave 3 | §6 |
| 17 | Data diff mode `--diff <git-ref>` | ⏳ Open, Wave 4 | §6 |
| 18 | Agent Skill (`SKILL.md`) | ⏳ Open, Wave 2 (after 9) | §6 |
| 19 | Minor polish | ✅ Done (W1) | `docs/parsers.md` (seed note), `docs/constants.md` |
| 20 | Nested Parquet values (list/struct) | 🟡 Crash fixed in W1; rendering + test open, Wave 2 | §6 |
| 21 | SQL parser hardening | ⏳ Open, Wave 2 | §6 |
| 22 | Detect virtualenvs by `pyvenv.cfg` | ⏳ Open, Wave 2 | §6 |
| 23 | Ladder: text cap vs stats drop order | ⏳ Open, decide with 5b | §6 |
| 24 | Arrow-backed float widening | ⏳ Open, with 15 | §6 |
| 25 | Numeric precision caps | ✅ Done (W1) | `docs/parsers.md` (Numeric Precision), `docs/cli.md`, `docs/constants.md`, README |

Legend: ✅ implemented, reviewed, merged and graduated to `docs/` · ⏳ open ·
🟡 partially done.

---

## 3. Workflow (how every item is built)

The owner's rule: **no code counts as done until an independent, specialized
reviewer agent has approved it**. The loop new code → review → fix repeats until
the code is genuinely high quality and fits the architecture, with nothing left that
could become trouble later. The goal is engineered, standard code, not slop.

### 3.1 The pipeline

```
Implementer ─► Reviewer (full) ─► Fixer ─► Verifier ─► (loop until APPROVE) ─► Lead gate ─► merge ─► next track
 (own worktree)  (fresh, read-only)                                            (reads diff, runs tests + snapshot)
```

1. **Implementer** works in its own git worktree and branch:
   - bug fixes are red → green (the test fails on old code first)
   - docs are updated in the same branch
   - full suite green
   - snapshot diff of all 4 variants against the baseline
2. **Reviewer:** ONE unified reviewer covering code quality AND the output contract.
   It is fresh (it gets the spec and the diff, never the implementer's reasoning),
   read-only and adversarial. It runs the red-proof, mutation testing and its own
   repro scripts, and reads the generated document as the LLM would. Findings are
   rated BLOCKING / SHOULD-FIX / NIT.
3. **Lead decides** each finding, then sends a precise fix list.
4. **Fixer** applies it. **Verifier**, again fresh, re-checks every finding by
   reproduction and reviews the fix diff itself. Repeat until APPROVE with no
   BLOCKING or SHOULD-FIX left. Fix NITs too unless they are out of scope; those
   become backlog follow-ups.
5. **Lead gate:**
   - the lead reads the core diff personally
   - the merge is `git merge --ff-only` (rebase the branch first if main moved)
   - full suite on main
   - snapshot on main
6. **Checkpoint:** after each wave, a detailed report to the owner (§3.6).

### 3.2 Agent roles and model tiers (token efficiency, owner request)

Use Sonnet whenever the task or plan is clear. Reserve Opus for first full reviews
and open design problems. Match effort to the task. Agent types live in
`.claude/agents/` and load at session start:

| Agent type | Model / effort | Use for |
|---|---|---|
| `d2p-implementer` | Sonnet / high | Implementing a clearly specified item, or a fix list needing moderate design (rebases, plumbing) |
| `d2p-fixer` | Sonnet / medium | Applying a precise, already-decided fix list |
| `d2p-reviewer` | Opus / high | First full review of new work (unified code + contract) |
| `d2p-verifier` | Sonnet / high | Re-review after fixes |
| `general-purpose` + `model: opus` | Opus | Open design problems with no settled plan (e.g. items 4, 6, 17) |

Each agent's prompt names: the item(s) in this file, the worktree path and branch,
the runs/track id, the reference snapshot to diff against, and (for fixers and
verifiers) the finding IDs and the commit range.

### 3.3 The kit (`.claude/backlog/`, local, gitignored)

| File | Purpose |
|---|---|
| `BRIEFING.md` | The protocol every agent reads first: paths, environment traps, code standards, the implementer and reviewer protocols, report formats. |
| `make_fixture.py` | Builds `fixture_proj/`, a deterministic messy project that reproduces the backlog bugs. It covers: semicolon, pipe, cp1252, preamble and ragged CSVs; a CSV with `\|`, newlines and empty cells; DD/MM dates, `$` amounts, case variants, a `-999` sentinel and duplicate rows; a 63-column sensor table; a long-text table; `.tsv`, `.csv.gz`, `.jsonl` and `.json`; an Excel file with a title row; a corrupt xlsx and an Office lock file; SQLite with a foreign key; Parquet; a notebook with out-of-order runs and an ANSI traceback; a `.venv`; `.env`; code; and a README. **Add new cases here** when an item needs them (e.g. item 20 needs a list/struct Parquet). |
| `snapshot.py` | `snapshot.py <tree_root> <out_dir>` runs that tree's code (via `PYTHONPATH`) on a fresh temp copy of the fixture in 4 variants: `default_md`, `default_xml`, `schema_only`, `budget_12k`. It saves the documents with normalized timestamps, plus the terminal output. |
| `baseline/` | Snapshot of main at the start of the current wave. Refresh it at the start of every wave. |
| `runs/`, `review/` | Per-track outputs and reviewer scratch; they can be deleted between waves. |

If the kit is lost: recreate `BRIEFING.md` from §3.1–3.5 of this file plus
CLAUDE.md, and rebuild the fixture from the list above.

### 3.4 Environment traps (each one cost time in Wave 1)

- **Python:** only `"/d/miniconda3/python.exe"`. Bare `python` lacks the
  dependencies.
- **The `data2prompt` console script** is an editable install of the main repo.
  In a worktree it runs MAIN's code, so run trees via `snapshot.py` or
  `PYTHONPATH=<tree>/src`. Tests are safe: `tests/conftest.py` puts the tree's own
  `src/` first.
- **Stale worktree base:** a new agent worktree (`isolation: worktree`) may start
  from an OLD commit. The agent must check `git merge-base HEAD main` and run
  `git reset --hard main` if it has no work yet.
- **Untracked files** (e.g. an uncommitted plan) are not in worktrees. Point agents
  at the main repo path.
- **New agent types** in `.claude/agents/` only load at session start. Mid-session,
  use `general-purpose` with a `model` override and tell the agent to read the
  definition file as its instructions.
- **Parallel tracks** must own disjoint files. `parsers.py`, `output.py` and
  `constants.py` (preamble) are hotspots, so merge tracks one at a time and rebase
  the next branch onto main before its fix round.

### 3.5 Git and commit conventions

- Branches: `backlog/w<wave>-<track>-<slug>`, e.g. `backlog/w2-a-ingestion`. All
  local. The lead merges with `--ff-only`. **Nothing is pushed until the owner says
  so.**
- Commit style (strict): lowercase, dash-prefixed bullets, one short line per
  logical change stating what and briefly why. **Never a `Co-Authored-By` or any
  attribution trailer.** Fixes are new commits, never amends.
- After a wave is merged, remove its worktrees
  (`git worktree remove <path>`); the branches keep the history.

### 3.6 The end-of-wave report (owner expectation)

The report must be detailed but not boring, and lead with what matters:
- what the LLM now receives (with before/after excerpts)
- what the review loop caught that implementers missed
- the numbers: tests, tokens, rounds per track
- decisions the owner must make
- what the owner should check themselves, with exact commands, e.g.
  `code --diff <baseline> <new>`
- housekeeping

---

## 4. Decisions log (owner decisions; don't relitigate)

| Date | Decision |
|---|---|
| 2026-09-30 | Every code change goes through the independent review loop (§3). Agents commit on local branches; the owner reviews at a checkpoint after each wave. |
| 2026-09-30 | Bare `env/` is **not** a core-ignored folder: it is also a common config-folder name, and a folder ignore drops it silently. Item 22 is the better fix. |
| 2026-09-30 | An unreadable file is `Error` even under `--schema-only`. ANSI stripping alone does not make a notebook `Cleaned` (no content is lost). Dropping HTML while keeping text/plain still counts as `Cleaned`. A missing optional dependency (`xlrd`, `pyarrow`) is `Skipped (No …)`, not `Error`. |
| 2026-10-01 | Agents use Sonnet when the plan is clear, Opus for first reviews and open design; one unified reviewer instead of two (§3.2). |
| 2026-10-01 | **Numeric precision caps (item 25):** stats at most 4 decimals, data values at most 6, both configurable. Values below 1 keep at least 4 significant digits; values ≥ 1 follow the cap exactly. A 15-decimal data cap was rejected because it was measured to save ~6 tokens. |
| 2026-10-01 | Remaining fixes go to the next wave and the next release; Wave 1 ships as v1.1.0. |

---

## 5. Wave log and next waves

### Wave 1: done (2026-09-30 → 10-01), ships as v1.1.0

- **Items:** 1, 3, 5a, 7, 8, 12, 13, 19, 25.
- **Tracks:**
  - C (5a, 8, 19): 1 review round
  - A (3, 7, 13): 3 rounds
  - B (1, 12, 19 plural): 3 rounds
  - D (25): 2 rounds
- **Numbers:**
  - tests 235 → 377
  - fixture default output 39,839 → 38,880 tokens (smaller *and* more accurate)
  - cache-stable prefix after a one-line edit: 735 → ~42.7k tokens
- **Bugs the review loop caught that implementers missed:**
  - pandas' default CSV float parser wrong in the last digit on ~24% of values
    (fixed with `float_precision="round_trip"`)
  - a table cut at render time still labeled `Full`
  - the notebook notice mixing execution counts and cell numbers
  - SQL sampling counting `INSERT` header lines as rows (losing data)
  - empty strings indistinguishable from missing
  - the first cache-prefix fix not meeting its goal
  - the significance guard overriding the decimal cap
  - mutation coverage gaps (19/22 → all caught)
- **Shipped beyond the original specs:**
  - `tabulate` dependency removed
  - shared helpers `render_table_text`, `fit_table_rows`, `format_float`
  - `ParserResult.file_note` / `FileData.file_note` (file-level notes under the
    file header)
  - `-- [Output omitted: <mime>] --` notice
  - `Skipped (No xlrd)` status plus install hint
  - preamble slots (`{DATA_DECIMALS}`…) filled by `_fill_preamble_slots`, with a
    test that no slot survives unfilled
  - the v1.0.0 Parquet list-column crash fixed as a side effect (see item 20)

### Wave 2: next (proposed; confirm with the owner)

Ordered by importance and grouped into parallel tracks with disjoint file
ownership:

| Track | Items | Owns | Notes |
|---|---|---|---|
| A: robustness | 20 → 21 | `parsers.py` (nested values, `process_sql`, `SQLParser`) | Quick correctness wins first |
| B: ingestion | 2 → 11 | `parsers.py` read paths, registry, `main.get_ui_action`, `constants.py` skip list | 11 reuses 2's sniffing; coordinate `parsers.py` with A |
| C: CLI + reach | 9 → 18, 22 | `cli.py`, `main.py`, `ui.py`, `utils.py`, new `__main__.py`, `skills/` | 18 needs 9's `--stdout` |
| D: profiles | 4 + 5b → 10 (+ decide 23) | `build_table_schema` / `render_schema_block`, `budget.py` | Open design: **Opus implementer**. Merge after A and B, or rebase. |

### Wave 3: 6 (Project Map, Opus design), 14, 16, 15 (after the owner decides determinism) + 24.

### Wave 4: 17 (data diff) + its GitHub Action.

---

## 6. Open item specs

Specs cite functions and constants rather than line numbers, because line numbers
went stale after Wave 1. Locate code by symbol.

### 2. Silent delimiter / encoding misreads (Wave 2, Track B)

**Problem.** `process_csv` calls `pd.read_csv(..., float_precision="round_trip")`
with no dialect or encoding handling. On the fixture:
- A **semicolon CSV** (European/Excel export) is read as **one column**
  `Datum;Filiale;Umsatz` and labeled `Sampled`. Stats and samples are garbage
  presented as truth. This is the worst failure mode, because nothing signals it.
- A **pipe-delimited CSV** fails the same way.
- **cp1252/latin-1** CSVs, **preamble/title rows** and **one ragged row** each
  lose the whole file. Since Wave 1 they are at least labeled `Error`.
- Excel **title rows** become headers (`ACME Corp - Q3 Budget Report | Unnamed: 1`).

**Fix direction.**
- Encoding: try `utf-8` (pandas handles a BOM), then `cp1252`, then `latin-1`.
- Delimiter: sniff only when the default comma parse yields a single column or
  raises, using `csv.Sniffer` on the first ~64 KB with candidates `, ; \t |`.
- Decimal comma: when the separator is `;` and numeric-looking cells use `,`
  decimals, pass `decimal=","`.
- Preamble rows: find the first line whose field count matches the modal count of
  the following lines, and pass `skiprows`. Excel: the first row with mostly
  non-null string cells.
- Ragged rows: `on_bad_lines="skip"`, with a counted notice.
- A **"Read as" notice**, emitted only when non-default settings were used, e.g.
  `-- [Read as: encoding=cp1252, sep=';', decimal=',', skiprows=2] --`. It lets the
  LLM write a `read_csv` call that loads the file correctly. It is a new notice,
  so the output-contract checklist and preamble teaching apply.
- Keep `float_precision="round_trip"` on every read path.

**Acceptance.** The semicolon, pipe, cp1252, preamble and ragged fixtures produce
correct column counts and dtypes, with status `Sampled`/`Full` instead of
`Error`/garbage. Plain comma UTF-8 CSVs produce byte-identical output to before.

### 4. Smart column profiles + 5b lean-stats step (Wave 2, Track D, Opus design)

**Problem.** `build_table_schema` runs `df.describe(include="all")` and
`render_schema_block` prints it. Item 25 already capped the decimals, but the
content is still the wrong content:
- **Dates are opaque.** `DD/MM/YYYY` strings stay dtype `str`, so the model sees
  `top: 01/01/2024, freq 1` and never the range. Worse, when a column parses under
  both day-first and month-first, a naive `pd.to_datetime` silently corrupts it,
  and nothing warns the model.
- **Numbers stored as text** (`$1,234.00`) show only `unique`/`top`. This caused a
  real `TypeError` in the arena's test notebook.
- **Categories** show only one `top` value, so the model can't write filters.
  Case and whitespace variants (`shipped` / `'shipped '` / `Shipped`) are
  invisible.
- **Wasted cells.** Numeric columns carry empty `unique/top/freq`, text columns
  empty `mean/std/…`, and `count` duplicates `missing`.

**Fix direction.** Typed profiles on the full data:
- **Numeric table:** dtype, missing %, mean, std, min, quartiles, max. Values go
  through `format_float(..., stats_decimals)`.
- **Categorical/text table:** unique count, the full value list when unique ≤ ~10,
  otherwise the top-5 values with counts.
- **Per-column hints,** from a fixed small vocabulary, one line max, suppressed
  below a threshold: `date-like` (format, min → max, an `ambiguous DD/MM vs MM/DD`
  flag), `numeric-as-text` (currency or thousands separator), `sentinel` (e.g.
  `-999 in 10% of rows`), `case/whitespace variants`, `id-like` (unique per row,
  plus a pattern), `constant`.
- **Table-level:** duplicate row count.
- **Performance:** detect formats on ≤ 1k sampled values, then compute min/max on
  the full column.
- **5b, the lean-stats ladder step.** Define profile detail levels (full → lean →
  off). Lean keeps missing %, min/max and top values, and drops std, quartiles,
  hints and long value lists. Add a ladder step for lean before the step that drops
  stats. Also decide item 23 here.

**Measured** (pre-item-25): stats tokens −40% while adding date ranges and
category vocabularies. Re-measure on the current baseline.

**Touches.**
- `ColumnSchema`, `TableSchema`, `build_table_schema`, `render_schema_block`
  (shared by CSV, Excel, Arrow and SQLite)
- the `budget.py` ladder, `docs/budget.md`
- the tabular preamble bullet in `constants.py`
- `docs/parsers.md`, `docs/output-contract.md`
- tests asserting describe-era strings, which need rewriting

### 6. Project Map: join keys + which code reads which data (Wave 3, Opus design)

**Problem.** "Join these and build X" is the most common data request. The model
must rebuild relationships from column names spread through a long document, and
fails when names differ. Only SQLite exposes relationships, via its DDL. Nothing
links code to the data it reads.

**What.** A short section right after the File Index (~130 tokens on the test
project), in both formats:
- **Likely join keys** across all tables (CSV, Parquet, Excel sheets, SQLite
  tables), with match % and orphan count, e.g.
  `orders.csv.cust_id → customers.tsv.customer_id — 94.2% of 848 keys match, 49 orphans (inferred)`.
  SQLite's declared foreign keys are merged in and labeled `declared`.
- **Data ↔ code:** for each data file, which `.py` / `.ipynb` / `.sql` files
  mention its filename or relative path literally. Unreferenced data files are
  listed.

**Inference rules (to avoid false joins).**
- The target column must be unique (PK-like), with containment ≥ 90%.
- Require a name signal: equal names, or one contained in the other after
  stripping `_id`/`id`. Two unrelated `1..N` integer columns always match 100%,
  and the arena prototype hit exactly that false positive.
- Cap at 10k distinct values per key column (hash sets), captured during parsing
  on the full data, before sampling.
- Label every inferred match `inferred`. Code links use exact filename matches
  only.

**Touches.**
- a new module and doc (e.g. `relations.py` / `docs/relations.md`)
- `TableIR` gains a small key profile
- `main.py` runs a cross-file pass after the parse loop
- `output.py` renders the section
- a conditional preamble bullet
- the output-contract checklist (new section)

### 9. Pipe-ready CLI: path argument, `--stdout`, `python -m` (Wave 2, Track C)

**Problem.**
- **No path argument:** `data2prompt ../proj` gives "unrecognized arguments". The
  project root is `Path.cwd()` in `main._run`, and `parsers.py` also uses
  `Path.cwd()` for display paths: `_sanitize_error` and the Excel and SQLite parse
  display paths.
- **No stdout mode:** `-o -` writes a file named `-.md`, and the Rich UI
  (`Console()` in `ui.py`) prints to stdout, so piping would mix UI into the
  document.
- **`python -m data2prompt` fails:** there is no `src/data2prompt/__main__.py`.
- **An unwritable `-o` path** is detected only after all parsing is done.

**Fix direction.**
- **Path argument:** positional `path` (`nargs="?"`, default `.`), with an explicit
  `project_path` threaded everywhere `Path.cwd()` is used today. The output file
  lands in the current directory, as in repomix. Document this, and make sure the
  scanner still excludes the output file.
- **`--stdout`:** the document goes to stdout, all UI goes to stderr
  (`Console(stderr=True)`), and the animated banner is skipped.
- **Entry point:** add `__main__.py` calling `main()`.
- **Fail early:** validate the output path before scanning.

**Why.** Every competitor has it (repomix `--stdout`, gitingest `-o -`). It
enables `data2prompt ./proj --stdout -b 50k | llm "..."`, and item 18 depends on
it.

### 10. Wide tables: column-family folding (Wave 2, Track D, after 4)

**Problem.** Width is never capped. `table_limit` covers sample rows only, not the
schema block. The 63-column fixture sensor CSV was **72% of the whole document**,
and one sample row costs ~430 tokens versus ~32 for a 6-column table. A 400-column
CSV produced a 26k-token stats block.

**Fix direction.**
- **Folding:** normalize column names by replacing digit runs with `#`. Groups with
  the same pattern and dtype and ≥ 5 members fold into one profile row with stat
  ranges, e.g.
  `sensor_#_temp_c (60 cols, float64) | mean 61.2–120.1 | std 4.8–5.2 | min 42.6 | max 138.6`.
- **Outliers:** members whose null % or mean is far from the group keep their own
  row. The fixture's `sensor_17` (30% nulls) must stay visible.
- **Samples:** show the first and last member of each family, plus a notice:
  `-- [Columns folded: sensor_#_temp_c (60 columns); samples show sensor_01, sensor_60] --`.
- **Fallback** for wide tables with no pattern: a `--max-columns` cap (default
  ~50), with a notice listing the omitted columns.

**Measured.** The family stats row is ~54 tokens (was ~4.8k), and the whole
fixture document shrinks by ~68%. **Touches:** `parsers.py` (family detection
feeding schema and sampling), `output.py`, a new notice and preamble bullet, the
docs and the output contract.

### 11. More tabular formats (Wave 2, Track B, after 2)

**Problem.** Common data formats fall through to `DefaultParser`, which emits raw
text, or are skipped:
- `.tsv`, `.tab`, `.psv`: an 800-row TSV dumped raw (~12k tokens) with no schema.
- `.csv.gz`, `.csv.bz2`: skipped, because `.gz` is in `CORE_SKIP_EXTS` and dispatch
  uses only the last suffix.
- `.jsonl`, `.ndjson`, and `.json` holding an array of records: plain text, with
  no schema.

**Fix direction.** Route these into the tabular pipeline (`TableIR` → profiles →
samples):
- **Delimited variants:** the CSV path with an explicit separator. `.txt` tables
  reuse item 2's sniffing.
- **Compressed CSVs:** dispatch on the double suffix (`Path.suffixes`), let pandas
  decompress, and stop skipping `.csv.gz`-style names. A bare `.gz` stays skipped.
- **`.jsonl`:** `pd.read_json(lines=True)`, flattening nested keys with
  `pd.json_normalize` (cap the depth).
- **`.json`:** a table only if it is a list of flat-ish objects; otherwise keep
  today's text handling.
- **Wiring:** register the extensions, update `main.get_ui_action`, the stats
  counters and the File Index type labels, and follow the output-contract "new
  file type" checklist.

### 14. `--budget` reads each file once (Wave 3)

**Problem.** `budget._reparse_records` re-runs the full parser (disk read plus
full-data stats) for every affected file at every ladder step. One 175 MB CSV was
read 6 times: `-b 1500` took 72.8 s vs 19.7 s unbudgeted, with peak memory
1.9 GB vs 1.15 GB.

**Fix direction.**
- Split the tabular parsers into "read + profile" and "render at settings X".
- Cache per table: the full-data schema/profile, plus the largest sample drawn
  from one seeded permutation. A smaller sample is the first k rows of that same
  permutation, so it is a subset of the larger one.
- Re-render only; don't cache whole DataFrames.
- The status logic (`_tabular_status`, `_rows_were_cut`) must still be judged on
  the rendered text, including the decimal caps.
- Sample rows will change once relative to `df.sample(k)`; document this in
  `docs/budget.md`.

### 15. Optional fast readers (Wave 3; needs an owner decision first)

**What.**
- Use `pd.read_csv(engine="pyarrow")` when pyarrow is importable, and
  `pd.ExcelFile(engine="calamine")` when `python-calamine` is installed. Fall back
  to the current engines on any exception.
- Ship them as a `data2prompt[fast]` extra. Calamine also reads `.xlsb` and `.ods`.

**Measured.** `read_csv` 3.84 s → 0.20 s; Excel 11.46 s → 1.27 s; full run
19.7 s → 2.6 s.

**Owner decision needed: determinism.** Engines infer different dtypes (pyarrow
parses datetimes, for example). The pyarrow engine does not support
`float_precision="round_trip"`, and it can produce Arrow-backed dtypes (item 24).
So output could differ depending on the installed extras, which would break
"same command, same output". The options:
- normalize dtypes after reading
- record the engine in the document metadata
- only use it when the result is verifiably identical

### 16. Parquet `--schema-only` from metadata (Wave 3)

**Problem.** `--schema-only` still loads the whole file: a 45 MB Parquet file used
1.2 GB of memory. `pyarrow.parquet.read_metadata` returns the row count and column
types in ~3 ms, plus per-row-group null counts when statistics exist.

**Fix.** In schema-only mode without stats, read the metadata only. Fall back to a
full read when null-count statistics are missing and stats are requested.

### 17. Data diff mode `--diff <git-ref>` (Wave 4)

**What.**
- For each tabular file changed since the ref, parse the old version
  (`git show REF:path` into a temp file) and the current one.
- Compare the profiles: row-count delta, added/removed columns, dtype changes,
  missing % shifts, mean/std drift.
- Render a "Data changes" section plus a per-file notice, e.g.
  `-- [Changed since main: rows 1,204 → 1,390; +column region; price missing 0.2% → 11%] --`.
- Later: a GitHub Action posting it as a PR comment.

**Why.** A CSV text diff is useless for review. Code packers have git-diff modes
(repomix `--include-diffs`, code2prompt `--git-diff-branch`), but none diff the
data itself, which makes this a strong portfolio headline. **Risks:** Git LFS
pointer files (detect them and emit a notice), and renames. Benefits from item 4.

### 18. Agent Skill (`SKILL.md`) (Wave 2, Track C, after 9)

A `skills/data2prompt/SKILL.md` telling coding agents (Claude Code, Cursor, Codex,
…):
- when to run data2prompt before writing data code, e.g.
  `uvx data2prompt --stdout --budget 40k`
- how to read the File Index, the statuses and the `-- [...] --` notices

Optionally, a `.claude-plugin/marketplace.json` for one-line install. It is mostly
Markdown. Pin a major version in the command.

### 20. Nested Parquet values: list/struct (Wave 2, Track A)

**State.** v1.0.0 **crashed the whole run** on a Parquet file with a list column
(`pd.isna(list)` → `ValueError` in `render_schema_block`). Wave 1's
`_format_cell` (an `is_scalar` guard) fixed this as a side effect, and it ships in
v1.1.0. But **no regression test pins it**, and the fixture has no such file.

**Remaining problems** (verified on main):
- Lists render numpy-style, as `['a' 'b']` with no comma, which reads like one
  string.
- Struct values render with ints widened to floats (`{'k': 1.0}`), because a
  missing value in the column promotes the dtype.

**Fix direction.**
- Render list, dict and ndarray cells as compact JSON (`["a","b"]`, `{"k":1}`)
  through the shared `_format_cell`. Apply the same in the schema `top` values.
- Add a list/struct Parquet file to `make_fixture.py`.
- Add red → green tests for the crash path and the rendering.

### 21. SQL parser hardening (Wave 2, Track A)

- **`SQLParser`** always returns `Parsed` (→ `Sampled`), even on a read error or
  fully shown data. It is the same bug class as item 1. Derive the status from the
  parse outcome (`Error` / `Read` / `Parsed`).
- **`_is_bare_insert_header`** only matches a line ending in `VALUES`. It misses
  `VALUES -- comment` and `VALUES;`, and it matches a table named `my_values`. Each
  case makes a row count off by one. Use a regex like `\bVALUES\s*(--.*)?$`, plus
  tests.

### 22. Detect virtualenvs by marker (Wave 2, Track C)

Ignore any folder that contains `pyvenv.cfg`. That catches a venv of any name
(e.g. `env/`) with no false positives, and complements the name list in
`CORE_IGNORES`. **Touches:** the scanner in `utils.py`, `docs/utils.md`.

### 23. Ladder: text cap vs stats drop order (decide with 5b)

The step that caps text files to 10 KB runs after the stats-drop step, so on
text-heavy projects the stats are lost first. Decide the order when 5b redefines
the stats levels.

### 24. Arrow-backed float widening (with 15)

`float32[pyarrow]` values iterate as Python floats, so `0.1` would print as
`0.10000000149011612`. `_format_cell` parses `str(value)` for numpy floats; check
that the Arrow-backed path is covered too. It's unreachable today, and becomes
live if item 15 adopts `dtype_backend="pyarrow"`.

---

## 7. Completed items (summary; `docs/` is the source of truth)

| # | What shipped | Notes and deviations from the original spec |
|---|---|---|
| 1 | The status is derived from explicit parse signals (`TableIR.partial` / `.error`, `NotebookCellIR.trimmed` / `.error`) via `_tabular_status` / `_notebook_status`. Unreadable files are `Error`; fully shown files are `Read` → Full; tables cut at render time are `Sampled`. `fit_table_rows` is the single source of truth shared with the truncation. | `.sql` statuses are still hard-coded (item 21). |
| 3 | One renderer (`render_table_text` / `render_sample_table` / `_format_cell`) used by both generators and the token estimate. `\|` is escaped, `↵` marks a newline, a missing value is an empty cell, empty and whitespace strings are quoted (`""`), there is no padding, and the duplicate sampling footer is removed. | `tabulate` dropped. CSV floats are read with `float_precision="round_trip"` (the default parser was off by one ulp). A `cells` preamble trigger teaches the conventions only when cells render. |
| 5a | Ladder: schema-only (step 6) now runs before dropping stats (step 7). | 5b (lean stats) moved into item 4. |
| 7 | The table cap applies to the sample rows only, cuts at a row boundary, keeps both notes, emits no notice when nothing was cut, and says "lines" for SQL. Per-file estimates apply the same cap. | SQL sampling now counts data rows only (bare `INSERT` headers are kept and never counted or sampled). |
| 8 | `.venv`, `.conda`, `.tox`, `.nox` and `.ruff_cache` are in `CORE_IGNORES`; Office lock files are excluded via `OFFICE_LOCK_FILE_PATTERN` (`~$*`). | Bare `env` deliberately excluded (decisions log); item 22 is the better fix. |
| 12 | ANSI (ECMA-48 CSI + OSC) is stripped from all notebook outputs. A file-level execution-state notice (cell numbers; capped lists, `…(+N more)`) covers out-of-order runs, never-run cells, missing counts and the first error. `-- [Output omitted: <mime>] --` appears when no text form was kept. | Implemented as `ParserResult.file_note` under the file header, not a pseudo-cell. |
| 13 | The timestamp and token total moved to the end anchor in both formats. | The stable prefix after a one-line edit went from ~735 to ~42.7k tokens on the fixture. |
| 19 | The 2 MB warning suggests `--budget` (threshold constant `OUTPUT_SIZE_WARNING_KB`); forward-slash paths in the terminal report; singular/plural labels (`Excel (1 sheet)`); seed note in the docs. | Also: `Skipped (No xlrd)` plus an install hint. |
| 25 | `format_float` with the rule in the decisions log; flags `--stats-decimals` / `--data-decimals`; the preamble states the actual caps via slots. | Decimal parameters are required keyword-only (no silent defaults). |

---

## 8. Rejected (don't re-propose without new evidence)

| Idea | Why not |
|---|---|
| Hugging Face / Kaggle dataset URLs | Multi-GB downloads and Kaggle auth support burden. Revisit after item 9. |
| Plugin for Simon Willison's `llm` CLI | Small audience. About 60 lines once `--stdout` exists, so it can wait. |
| Regex-based lineage / dbt `ref()` graph | Fragile heuristics. The exact-filename part lives in item 6. |
| Hosted web UI, VS Code extension | High effort and upkeep; gitingest and repomix already own that niche. |
| Tree-sitter code compression | Targets code, not data; no differentiation. |
| 15-decimal data cap | Measured to save ~6 tokens; 6 decimals chosen instead (item 25). |
