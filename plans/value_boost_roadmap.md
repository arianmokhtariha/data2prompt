# Value-Boost Roadmap

> **Status: design space.** Per project convention, nothing in this file describes
> current behavior — features graduate to `docs/` only when implemented and stable.
>
> This roadmap absorbs and expands the rough ideas in `feature_plans.md`
> (polars, more parsers, Excel formulas, output optimization) and ranks everything
> by the ratio of user value to implementation effort, grounded in what
> data2prompt actually is: *the context packager for data-heavy projects*.

## The strategic lens

data2prompt's moat is not "codebase → prompt" (Repomix, code2prompt, gitingest all
do that). The moat is **understanding the shape of data projects**: sampling,
schemas, notebooks, token budgets. Every feature below either deepens that moat or
plugs the tool into the place where context is consumed (agents, teams, pipelines).

## Priority matrix

| # | Feature | Value | Effort | Priority |
|---|---------|-------|--------|----------|
| 1 | Token budget targeting (`--budget`) | ★★★★★ | Medium | **✅ Implemented** |
| 2 | SQLite/DuckDB parser | ★★★★★ | Low | **P0** |
| 3 | Programmatic API (`data2prompt.api`) | ★★★★ (enabler) | Low | **P0** |
| 4 | MCP server mode | ★★★★★ | Medium | **P1** |
| 5 | Config file (`[tool.data2prompt]`) | ★★★★ | Low | **P1** |
| 6 | `--focus` selective depth | ★★★★ | Low-Med | **P1** |
| 7 | Compression report (tokens saved) | ★★★ | Low | **P1** |
| 8 | Smart sampling strategies | ★★★★ | Medium | **P2** |
| 9 | PII redaction in data samples | ★★★★ | Medium | **P2** |
| 10 | Excel formula extraction | ★★★ | Medium | **P2** |
| 11 | Incremental cache / watch mode | ★★★ | Medium-High | **P3** |
| 12 | `--split` multi-part output | ★★ | Low | **P3** |
| 13 | Large-file streaming (polars/lazy) | ★★ | High | **P3** |

---

## P0 — build these first

### 1. Token budget targeting — `--budget 100k`

> **✅ Implemented and graduated.** Built in `src/data2prompt/budget.py` and
> documented in [docs/budget.md](../docs/budget.md). The design below is retained
> for historical context; `docs/budget.md` is the source of truth for actual
> behavior.

**What:** The user states the *outcome* ("fit this project into 100k tokens") and
data2prompt tunes its own knobs to hit it, instead of the user hand-adjusting
`--csv-sample-size`, `--max-lines`, `--table-limit`, `--max-file-size`, … per run.

**Why:** This is the entire promise of the tool, made literal. Every competitor
makes users guess; the 2MB warning panel data2prompt shows today is an admission
that the tool knows the problem but makes the human solve it. A budget flag turns
"try, check, tweak, retry" into one command. It is also the feature an *agent*
needs (see MCP below): agents know their remaining context window and can ask for
exactly that.

**How:**
1. Per-file token counts already exist (`ParserResult.tokens`). After the first
   parse pass, sum them plus a measured scaffolding overhead.
2. If over budget, apply a **de-escalation ladder**, re-parsing only affected
   files (parsing is cheap relative to LLM cost; a second pass is fine):
   - Step 1: halve `csv_sample_size` (floor 5) for the largest tables first.
   - Step 2: switch tables over N tokens to schema-only (`TableIR` already
     supports this per-file — thread a per-file override instead of the global
     `config.schema_only`).
   - Step 3: reduce notebook `max_lines`, drop notebook outputs entirely.
   - Step 4: truncate DefaultParser files to head-only.
   - Step 5 (last resort): demote files to tree-only listing, largest first,
     and say so in the output.
3. Emit what was done: a `## Budget report` block in the output ("`sales.csv`
   demoted to schema-only, notebook outputs dropped") so the LLM knows what it
   is not seeing.
4. Parse `100k`/`1m` suffixes in a small argparse type.

**Risks:** iterating to an exact count is a rabbit hole — target 95% of budget and
stop; the metadata already labels counts as estimates.

### 2. SQLite / DuckDB parser

**What:** `.db`, `.sqlite`, `.sqlite3` (and `.duckdb` behind an optional extra)
currently sit in `CORE_SKIP_EXTS` and vanish. Parse them instead: table list, DDL,
row counts, and a sampled `TableIR` per table — exactly what the CSV parser
produces, but for real databases.

**Why:** Data projects *are* databases. A `.db` file is the single
highest-information-density artifact in a data repo, and today the tool that is
"purpose-built for data-heavy projects" skips it silently. The stdlib `sqlite3`
module means **zero new dependencies** for the flagship case. No competitor does
this.

**How:**
1. New `SQLiteParser` registered for `.db/.sqlite/.sqlite3`; remove those from
   `CORE_SKIP_EXTS`. (Open read-only via
   `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`; guard with a
   `PRAGMA quick_check` / magic-bytes sniff since `.db` may not be SQLite.)
2. Schema: `SELECT name, sql FROM sqlite_master WHERE type IN ('table','view','index')`
   — reuse the existing SQL rendering (the DDL *is* `CREATE TABLE` text, the
   existing output style already handles it).
3. Per table: `SELECT COUNT(*)` and `SELECT * ... LIMIT k` sample loaded through
   `pd.read_sql_query` → `TableIR` → existing schema/stats machinery for free.
   Cap at `max_sheets`-style `--max-tables`.
4. Respect `--schema-only` naturally (skip the sample query).
5. DuckDB later as `data2prompt[duckdb]`, same shape via the `duckdb` package.

**Risks:** huge DBs — always `LIMIT`, never full-table reads; use `COUNT(*)` only
below a size threshold, else report "≈ unknown (large)".

### 3. Programmatic API — `data2prompt.api.pack()`

**What:** Extract the pipeline core out of `main._run()` into a callable:
`pack(path, config) -> PackResult` (rendered text + stats + per-file summaries),
with the TUI becoming one consumer of it.

**Why:** Enabler for everything downstream: the MCP server (#4), notebook use
(`from data2prompt import pack` — the audience lives in notebooks!), CI pipelines,
and tests that exercise the real pipeline without a subprocess. Today the pipeline
is welded to the progress bar and to `Path.cwd()`.

**How:**
1. Move the file loop from `_run()` into `api.pack(project_path: Path, config:
   Config, on_progress: Callable | None) -> PackResult` (a small dataclass:
   `text`, `stats`, `files: List[FileSummary]`, `total_tokens`, `method`).
2. `_run()` becomes: build config → call `pack` with a UI progress callback →
   write/clipboard → final report. UI stays in `ui.py`, untouched.
3. Replace the remaining `Path.cwd()` references in parsers (`ExcelParser`
   display path, `_sanitize_error`) with the explicit `project_path`.
4. New `docs/api.md`; export `pack` from `__init__.py`.

**Risks:** none real — this is a refactor with a big option value.

---

## P1 — plug into where context is consumed

### 4. MCP server mode — `data2prompt --mcp`

**What:** Run data2prompt as a Model Context Protocol server exposing tools like
`pack_project(path, budget, schema_only)` and `pack_file(path)`, so Claude
Code / Claude Desktop / Cursor can pull fresh, budget-fit project context *from
inside the conversation*.

**Why:** The highest-leverage distribution move available. Instead of "run CLI,
copy 200KB, paste", the agent calls the tool when it needs context, with the
budget it can afford (pairs perfectly with #1). MCP servers get discovered through
registries — this is how a portfolio CLI becomes something people install.

**How:**
1. Optional extra: `pip install data2prompt[mcp]` pulling the official `mcp`
   Python SDK; entry point `data2prompt-mcp` (stdio transport).
2. Tool handlers are thin wrappers over `api.pack()` (#3) with a non-TUI progress
   sink. Return the rendered markdown as the tool result.
3. Guard rails: refuse paths outside an allowlisted root passed at server start;
   never follow symlinks out of it; cap response size at the requested budget.
4. Document a `claude_desktop_config.json` / `.mcp.json` snippet in README.

**Risks:** MCP SDK API churn — pin a minimum version; keep the surface to 2 tools.

### 5. Config file — `[tool.data2prompt]` in `pyproject.toml` / `data2prompt.toml`

**What:** Persistent per-project settings with precedence
`constants < config file < CLI flags`.

**Why:** Anyone using the tool twice on the same repo retypes the same six flags;
teams cannot share settings at all today (`.data2promptignore` covers only
ignores). Also the natural home for future per-path rules (#6).

**How:**
1. `tomllib` (3.11+) with `tomli` backport for 3.10 — effectively stdlib.
2. In `setup_cli()`: parse args with `argparse`, then for every option the user
   did *not* pass explicitly (compare against `parser.get_default()` via a
   sentinel-default trick or `argparse.SUPPRESS` + manual defaulting), fill from
   the config file, then from constants.
3. Look for `data2prompt.toml` first, then `[tool.data2prompt]` in
   `pyproject.toml`. Validate unknown keys loudly.
4. `data2prompt --init-config` writes a commented starter file.

**Risks:** the defaulting logic must be tested carefully — precedence bugs are
silent. One table-driven test over all options covers it.

### 6. `--focus` selective depth

**What:** `data2prompt --focus "notebooks/**" --focus "data/sales.csv"` — files
matching focus globs get full treatment; everything else is demoted (data files →
schema-only, code → head truncation, or `--rest tree-only`).

**Why:** The real workflow is "help me with *this* analysis", not "here is
everything at equal depth". Focus typically halves tokens while making the prompt
*more* relevant — attention is a budget too, not just the context window.

**How:**
1. `pathspec` is already a dependency — compile focus globs into a spec.
2. Introduce per-file effective settings: a small `resolve_file_config(path,
   config) -> FileConfig` consulted by `process_target_file()`; non-focused data
   files get `schema_only=True`, non-focused text gets a low `max_file_size`.
3. Mark demoted files in the output (`*condensed — not in --focus*`) so the LLM
   knows it can ask for more.

**Risks:** interaction with `--schema-only` global flag — define focus as *raising*
detail above the global baseline, never lowering it.

### 7. Compression report — show the value every run

**What:** Track raw bytes/estimated raw tokens per file vs emitted tokens; show
"RAW → PACKED (−96%)" per file in the SCAN LIST and a headline total in the
summary panel. Optional `--report json` sidecar for automation.

**Why:** The tool's pitch ("dumping raw CSVs wastes 90% of your context") becomes
a measured fact the user sees at every run — self-marketing, tuning aid, and the
basis for honest README screenshots. Trivial to build on existing plumbing.

**How:**
1. `ParserResult` gains `raw_bytes: int` (from `stat()`, already available).
   Estimate raw tokens as `raw_bytes / 4` (label it an estimate) to avoid
   tokenizing gigabytes.
2. Extend `FileSummary` + the Rich table with a `SAVED` column; totals in the
   success panel.
3. `--report json` dumps `stats` + per-file summaries via `json.dump` — useful
   for CI ("fail if context > X tokens").

---

## P2 — deepen the data moat

### 8. Smart sampling strategies — `--sample-strategy`

**What:** `random` (today), `head-tail` (first k/2 + last k/2 — natural for time
series and logs), `stratified:<column>` (preserve category distribution), and
`edges` (random core + rows containing nulls + numeric min/max rows).

**Why:** A uniform random 15 rows silently misses rare classes, null pathologies,
and range extremes — precisely the rows an LLM needs to reason about data quality.
The stats block gives aggregate truth; smart samples give *representative
evidence*. This is a genuine differentiator no code-packer can copy cheaply.

**How:**
1. Strategy functions in `parsers.py` (or a new `sampling.py` + doc):
   `def sample_df(df, k, strategy, seed) -> pd.DataFrame`, used by CSV, Excel,
   and Arrow paths (they all sample identically today — factor first, then extend).
2. `stratified:<col>`: `df.groupby(col, group_keys=False).apply(lambda g:
   g.sample(max(1, round(k * len(g)/len(df))), random_state=seed))`, clamp to k.
3. `edges`: k−m random + up to m special rows (first null row per column,
   idxmin/idxmax of numeric columns), dedup, sort_index.
4. Annotate the header note with the strategy used.

### 9. PII redaction in data samples — `--redact-pii`

**What:** Scan *sampled cell values* (not whole files — samples are small) for
emails, phone numbers, credit-card-like digit runs, and high-entropy secrets;
replace with typed placeholders (`<email>`, `<phone>`, `<secret?>`) and count
redactions in a note.

**Why:** The `.env` redaction shows the tool takes leakage seriously — but the
*data* is where customer PII actually lives, and users are pasting these prompts
into third-party LLMs. "Safe to paste" is a trust feature enterprises filter
tools by. Effort is modest because only sampled rows are scanned.

**How:**
1. `redaction.py` (+ doc): compiled regex set + Luhn check for card numbers;
   `redact_df(df) -> tuple[pd.DataFrame, int]` applied to object columns after
   sampling; same for the `describe()` `top` values in the stats block.
2. Off by default (`--redact-pii` opt-in) to keep default output faithful;
   `--redact-pii aggressive` adds high-entropy-string masking.
3. Emit `-- [N value(s) redacted: PII patterns] --` header note per table.

**Risks:** false positives on id-like columns — that is why it is opt-in and typed
placeholders keep the schema readable.

### 10. Excel formula extraction — `--excel-formulas` *(from feature_plans.md #3)*

**What:** For `.xlsx`, also report the *logic* of a workbook: distinct formulas
with their anchor cells (`D2: =C2*B2 (filled D2:D400)`), named ranges, and
cross-sheet references.

**Why:** For analysts, the formulas *are* the business logic — values alone throw
it away. "Explain what this workbook computes" becomes answerable.

**How:**
1. Second open with `openpyxl.load_workbook(data_only=False, read_only=True)`
   (values still come from the pandas path — `data_only=True` cached values).
2. Walk cells, collect `cell.value` strings starting with `=`; **canonicalize**
   by replacing row numbers with `#` so `=C2*B2` and `=C3*B3` collapse into one
   pattern with a fill range; cap at N distinct patterns per sheet.
3. Append a `**Formulas**` block to each sheet's `TableIR.header_note` (or a
   dedicated field rendered by the generators).

**Risks:** read_only + non-data_only iteration is memory-heavier — cap scanned
cells (e.g. first 50k per sheet) and note when capped.

---

## P3 — worth doing, not worth doing first

### 11. Incremental cache / watch mode
Hash every file (mtime+size) into `.data2prompt.cache`; on re-run, re-parse only
changed files and splice cached renderings. Near-instant re-packs make the tool
feel like part of the edit loop instead of a batch step. Do after #3 (the API
refactor defines clean per-file boundaries to cache).

### 12. `--split 3` multi-part output
Emit `PROMPT.part1.md` … with a shared header and cross-references, for models
with small windows. Simple greedy bin-packing over per-file token counts —
becomes trivial once #1's accounting exists.

### 13. Large-file streaming *(reframed from feature_plans.md #1 "polars")*
A full polars migration is high-effort, low-differentiation: pandas is not the
bottleneck for sampled 15-row outputs — *whole-file reads* are. The cheaper win:
for CSVs above a size threshold, stream with `pd.read_csv(chunksize=...)` doing
reservoir sampling + streaming null counts, so 2GB files never fully load.
Optional `data2prompt[polars]` backend only if profiling proves demand.

---

## Suggested sequencing

```
#3 API refactor  ──►  #1 --budget ✅  ──►  #4 MCP server
      │                                   (uses both)
      ├──►  #5 config file  ──►  #6 --focus
      └──►  #7 compression report (anytime, independent)
Then: #2 SQLite parser (independent — can also ship first as a quick win)
Then: #8 sampling → #9 PII → #10 formulas
```

`#2` (SQLite) is deliberately schedulable anytime — it touches only the parser
registry and is the fastest headline feature ("data2prompt now reads your
databases") for a release note.
