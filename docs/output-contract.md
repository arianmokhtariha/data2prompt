# The Output Contract — LLM-Facing Document Architecture

**Read this before changing anything that affects the generated `PROMPT.md` /
`PROMPT.xml`** — a new parser or file type, a new tool notice, a new inclusion
status, a new stats counter, or any edit to the system-instruction preambles.

This is a cross-cutting design contract, not a module doc. It records the
*invariants* of the output architecture and the *checklists* for extending it,
so that every future change integrates into the system the same way. The
current concrete structure lives in the module docs:

| Concern | Where it is documented |
| --- | --- |
| Document structure of both formats, File Index, stats, end anchor | [`output.md`](output.md) |
| Every existing `-- [...] --` notice and which function emits it | [`parsers.md`](parsers.md) — "Tool-Notice Grammar" |
| Preamble text, `INCLUSION_STATUS_MAP`, `STATS_SUMMARY_LABELS`, tags | [`constants.md`](constants.md) |
| Orchestration and the stats dict lifecycle | [`architecture.md`](architecture.md) |

## Design Rationale

The generated document is the product. It is consumed by an LLM, not a human,
so it is engineered around how LLMs actually read: a reading contract up front
(instructions before content), an authoritative File Index early (so attention
has a map to bind file content to), grounding facts attached directly to every
partial rendering (so the model cannot mistake a sample for the whole), and a
closing recap at the end (recency anchor). Every extension must preserve this
shape — a feature that is correct in code but breaks one of these properties
degrades the product.

## The Seven Invariants

1. **Format parity.** Markdown and XML are logically identical: same
   information, same section order, same vocabulary — only the syntax differs.
   Every addition lands in *both* generators and *both* preambles, or in
   neither. There is no Markdown-only or XML-only feature.

2. **The document teaches the LLM how to read itself.** The preambles
   (`SYSTEM_INSTRUCTIONS_MARKDOWN` / `SYSTEM_INSTRUCTIONS_XML` in
   `constants.py`) are the reading contract: document layout, structural
   conventions (fencing, cells, sheets, schema blocks), the notice grammar,
   and the accuracy rules. Any new structural convention the LLM must know
   about (e.g. a new sub-section marker for a new file type) must be described
   there — in both preambles, kept logically identical, source lines ≤ 88
   characters.

3. **Nothing partial may ever look complete.** This is the anti-hallucination
   core. Any sampling, truncation, or omission must (a) carry a `-- [...] --`
   notice at the point of reduction, (b) cite the full-dataset count, captured
   *before* reducing (the `total_rows = len(df)` pattern — capture first, then
   sample), and (c) surface an honest status in the File Index. A file that
   appears in the scan but is not rendered must still appear in the index
   (status `Omitted`) — nothing silently vanishes.

4. **One notice grammar.** Every tool-inserted line uses exactly
   `-- [Category: detail] --`. Never `*Note: ...*` prose, never emoji, never
   ad-hoc wording. The preambles teach this grammar once, generically, which
   is what lets the LLM separate tool notices from file content — a notice in
   any other shape is invisible to that rule.

5. **One canonical path key.** Every file has exactly one display path:
   project-relative, forward-slashed via `Path.as_posix()` (produced by
   `ProjectScanner.generate_tree()` and normalized again by
   `_display_path()` in `output.py`). The *identical string* appears in the
   File Index, the `## File:` header / `path="..."` attribute, and any notice
   that names the file. The LLM cross-references sections by literal string
   match; two spellings of one path breaks that link.

6. **Controlled vocabularies only.** Raw parser statuses never reach the LLM
   directly — they pass through `resolve_inclusion_status()` (exact
   `INCLUSION_STATUS_MAP` lookup → `Skipped (...)`-prefix fallback to
   `Skipped` → verbatim passthrough; it never raises). The closed status list
   in the preambles' accuracy rules must always equal the set of values that
   function can emit. Likewise, stats reach the document only through
   `STATS_SUMMARY_LABELS` — an unlabeled stats key is deliberately invisible.

7. **Fixed attention anchors.** `GENERATION_FLAG` is line 1 of both formats
   (the `DefaultParser` reads only the first 100 characters to detect
   previously generated output — nothing may precede it). The preamble sits
   at the top, the File Index before all content, and the end-of-codebase
   recap is the final section — nothing renders after it. The token
   placeholders `{{TOTAL_TOKENS}}` / `{{TOKEN_METHOD}}` are substituted by
   `main.py` *after* generation; new sections must be fully known at
   `generate()` time and must never emit those literal placeholder strings.

## Integration Checklists

### Adding a new file type / parser (e.g. `.db`)

1. Read `architecture.md`, `parsers.md`, `output.md`, `constants.md`, and this
   contract first (per the CLAUDE.md docs-first rule).
2. Implement the parser and register it in the `ParserRegistry`. Pick its raw
   status string(s) deliberately — reuse an existing raw status
   (`Read`, `Sampled`, `Truncated`, ...) whenever the semantics match.
3. **Status:** if the parser introduces a *new* raw status, add it to
   `INCLUSION_STATUS_MAP` mapping onto an existing LLM-facing term where
   possible. Only invent a new LLM-facing term when no existing one is honest
   — and then follow the "Adding a new inclusion status" checklist below.
4. **Notices:** every partial rendering emits notices per invariants 3–4,
   with full-dataset counts captured before reduction.
5. **Stats:** if the type deserves a counter, increment a `<type>_count` key
   in `main.py` and add a label to `STATS_SUMMARY_LABELS` (dict order = render
   order; zero counts are dropped automatically).
6. **Structure:** if the type renders as multiple sub-sections (like notebook
   cells or Excel sheets), define the marker in both generators
   (Markdown heading form + XML element with `quoteattr`-escaped attributes)
   and document the convention in *both* preambles' reading conventions.
7. **Paths:** any path the parser displays goes through `.as_posix()`,
   project-relative (see `ExcelParser.parse` for the pattern).
8. **Docs:** update `parsers.md` (including its Tool-Notice Grammar table),
   `output.md` if the document structure changed, and `constants.md` if any
   constant changed.
9. **Tests:** structural tests in `tests/`, developer-executed only. Respect
   the preamble-collision rule below.

### Adding a new `-- [...] --` tool notice

1. Shape: `-- [Category: detail] --`. Reuse an existing category word
   (`Sample`, `Truncated`, `Schema only`, `Skipped`, `Error`, `Binary`, ...)
   before inventing a new one — consistency is what the LLM keys on.
2. If the notice hides data, it must cite what is hidden:
   `random {n} of {total:,} rows`, captured before sampling (invariant 3).
3. Add a row to the Tool-Notice Grammar table in `parsers.md`.
4. The preambles already cover the generic `-- [...] --` form — touch them
   only if the notice introduces a semantic the accuracy rules must address
   (rare).
5. Tests: assert the notice starts with `-- [` and carries its counts. Keep
   existing marker substrings intact — several tests grep for phrases like
   `"CSV truncated"`, `"Sheet truncated"`, `"Table data truncated"`,
   `"Malformed"`; grep `tests/` before rewording any existing notice.

### Adding a new inclusion status

1. Add the raw → LLM-facing mapping to `INCLUSION_STATUS_MAP` in
   `constants.py`.
2. Add the term to the closed vocabulary list in **both** preambles' accuracy
   rules — the lists and the map must never drift apart.
3. Update the status tables in `output.md` and `constants.md`.
4. Add a mapping test beside `test_markdown_file_index_maps_statuses` in
   `tests/test_output.py`.

Note the fallback design: a raw status like `Skipped (Env)` needs *no* map
entry — the `Skipped (...)` prefix rule folds it into `Skipped`. Only map it
explicitly if it deserves its own LLM-facing term.

### Adding a new stats counter

1. Increment the key in `main.py`'s stats dict.
2. Add its label to `STATS_SUMMARY_LABELS` at the position where it should
   render (insertion order is render order). Both generators pick it up
   automatically via `summarize_stats()` — no generator change needed.
3. Document it in `constants.md`.

### Editing the preambles

1. Edit both `SYSTEM_INSTRUCTIONS_MARKDOWN` and `SYSTEM_INSTRUCTIONS_XML`
   together; they must stay logically identical (invariant 1).
2. Keep the four-part outline: Purpose → Document layout → Reading
   conventions → Accuracy rules.
3. Source lines ≤ 88 characters.
4. Update the outline description in `constants.md` if the structure shifts.
5. **Collision awareness:** any literal marker you quote in a preamble (e.g.
   `**Outputs:**`, `<schema>`) becomes a whole-document substring — see the
   test rule below.

## The Preamble-Collision Test Rule

A self-describing document contains the markers it describes. Therefore any
test assertion about a marker string that a preamble mentions must **scope
past the preamble** before asserting, or it will pass (or fail) trivially:

- Markdown: assert within `output.split("# Files", 1)[1]` — the preamble
  never contains the literal `# Files` heading.
- XML: assert within `output.split("</purpose>", 1)[1]` — the closing
  preamble tag occurs exactly once. Do **not** split on `<files>`; the
  preamble mentions that tag.

Worked examples live in `tests/test_output.py`
(`test_markdown_notebook_cell_without_outputs_omits_outputs_block`,
`test_xml_renders_notebook_cells`). Whenever you add a marker to a preamble,
grep `tests/` for that literal and re-scope any whole-document assertion on it.

## Definition of Done for Output-Touching Changes

A change is complete only when all of these hold:

- [ ] Both generators updated in parity (or neither needed changing).
- [ ] Both preambles updated if any reading convention or vocabulary changed.
- [ ] `INCLUSION_STATUS_MAP` / `STATS_SUMMARY_LABELS` and the preamble
      vocabulary lists are in sync.
- [ ] Every new partial rendering carries a grounded `-- [...] --` notice.
- [ ] All displayed paths are project-relative, forward-slashed, and
      identical across index, headers/attributes, and notices.
- [ ] `parsers.md`, `output.md`, `constants.md`, `architecture.md` updated as
      applicable (CLAUDE.md 1:1 docs rule).
- [ ] Tests written for the developer to run, respecting the
      preamble-collision rule.
