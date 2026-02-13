# Islamic Book Processor (IBP) — Canonical Specification
**High-assurance Arabic Islamic book ingestion → review-gated deep chunking → self-evolving topic corpus with zero silent corruption**

> Mission-critical warning: wrong chunk boundaries or wrong placement will silently corrupt an encyclopedia pipeline and waste years.  
> IBP must behave like a **fail-closed compiler**: staged, auditable, reproducible, review-gated.

**Priority order (hard):** Accuracy > Provenance/traceability > Determinism > Completeness > Speed/Cost  
**Default behavior:** If uncertain → **route to `_REVIEW`** (never silently commit).  
**Absolute invariant:** Canonical chunk bodies are append-only and never rewritten.

---

## 0) One-sentence objective
Ingest Arabic Islamic books (Shamela HTML), infer structure/substructure, propose a **human-reviewable chunk + taxonomy plan**, and only after approval emit **topic-pure, deep-granularity chunks** into a per-science corpus that can safely evolve forever.

---

## 1) Inputs (Arabic-first)

### 1.1 Primary input: Shamela Desktop HTML export (default options, page markers on)
- Multi-file volumes possible
- Inconsistent HTML semantics
- May contain TOC (often embedded, sometimes at end)
- Headings can be: centered, bold, font-sized spans, “PartName”, etc.
- Noise includes: running headers/footers, page numbers, footnotes, metadata pages

**Key constraint:** no manual TOC extraction as a requirement. TOC input is optional; the system must try to auto-detect embedded TOC when present.

### 1.2 Later (nice-to-have): PDF ingestion
- Requires OCR
- Must preserve page mapping
- Must still follow plan-first approval gating  
**HTML remains priority.**

---

## 2) Corpus layout (one database per science)
There is one `CORPUS_ROOT/`. Each science is isolated:

Sciences:
- Fiqh
- Aqidah
- Usul_al_Fiqh
- Imla
- Tajwid
- Sarf
- Nahw
- Balaghah
- Islamic_History

Per-science structure:

CORPUS_ROOT/
Sarf/
topics/ # taxonomy projection (folder tree)
chunks_by_book/ # canonical chunk store (append-only)
_REVIEW/ # ambiguous items requiring human decision
_ANCHOR_MISS/ # heading/anchor failures + diagnostics
runs/ # immutable run artifacts, reports, diffs
registry/ # SQLite indices: topics, books, projections, xrefs


---

## 3) Non-negotiables (strict constraints)

**Additional binding decisions:**
- **Human approval for ALL injected headings** (slowest, safest).
- Exercise-like sections (أسئلة/تمرين/تطبيق/تدريبات/...) default to a dedicated **Exercises/Applications** topic family, but remain review-gated.

1) **Plan-first + Mandatory Approval Gate**
   - Always generate a plan before writing chunks or changing taxonomy.
   - Pipeline halts until the user approves (and may edit) the plan.
   - No silent placement. No silent taxonomy mutation.

2) **Deep granularity**
   - Split to the lowest useful subtopic level (sub-sub-topic when present).
   - If one section contains separable subtopics, split them.

3) **Zero corruption of chunk bodies**
   - Chunk body must reproduce source content (meaning + citations) exactly.
   - Allowed cleaning: remove HTML wrappers, duplicated running headers/footers, structural noise.
   - Forbidden: paraphrasing, summarizing, “normalizing meaning”, LLM rewriting of body.

4) **Semantic placement, not slug matching**
   - Folder-name similarity is never sufficient.
   - Placement must compare Arabic heading + Arabic body content against existing topic nodes (and representative chunks).
   - If uncertain → `_REVIEW`.

5) **Automatic taxonomy evolution (but review-gated)**
   - New topic nodes/paths may be proposed automatically.
   - Nothing applies without approval.

6) **No deduplication / no chunk interference**
   - Do not merge/alter chunks due to similarity.
   - Duplicates are acceptable; downstream synthesis handles that.

7) **Strict anchor policy (critical)**
   - Chunk boundaries may use **only** Markdown headings `##` / `###` / ... as anchors.
   - Anchor regex: `^#{2,6}\s+`
   - Plain text, bold, centered lines are **not** anchors unless IBP injects heading tokens explicitly.

---

## 4) Core design: Canonical truth vs topic projection (prevents future regret)

### 4.1 Canonical storage (append-only)
Write canonical chunks once into:
- `chunks_by_book/<book_id>/chunk_<chunk_id>.md`

Rules:
- never rewrite canonical chunk bodies in place
- never delete canonical chunks
- if a correction is required: emit a new chunk_id, mark old as deprecated in registry

### 4.2 Topic folders are projections (safe to move)
`topics/` is a projection/view over canonical chunks.  
When taxonomy improves, chunks may “move” by updating the projection mapping (without touching canonical bodies).

Projection mechanism (Windows-first):
1) Try hard link
2) If hard link fails, fallback to copy + record `link_type`

Registry must record:
- topic_id → chunk_id list (+ canonical path + projected path + link_type)

---

## 5) Topic identity & folder naming (Arabic-first without chaos)

### 5.1 Stable topic IDs (identity ≠ folder name)
Topic identity must be a stable `topic_id` in a registry; folder paths are not identity.

Minimum topic registry fields:
- topic_id (stable, immutable)
- parent_topic_id
- display_title_ar
- display_title_en (optional)
- aliases_ar[], aliases_en[]
- status (active/merged/deprecated)
- created_by (rule/LLM/human)
- created_at
- notes

Store in `registry/topics.sqlite` (required), export to JSON for inspection.

### 5.2 Folder segment naming (stable ID prefix + Arabic title)
Format:
- `T000123__الإعلال_بالقلب`

Rules:
- Always prefix `T######__`
- Arabic part is sanitized
- Never rely on Arabic text for identity; identity is topic_id

Sanitization (Windows-safe):
- Unicode normalize NFC
- Replace spaces with `_`
- Remove illegal chars: `\/:*?"<>|`
- Trim trailing dots/spaces
- Limit segment length (e.g., 80 chars); keep full title in registry

---

## 6) Chunk identity & provenance (deterministic)
Chunk IDs must be deterministic and provenance-linked.

Recommended:
- `chunk_id = sha256(book_id + file + dom_anchor + start_offset + end_offset)`

Provenance must include:
- file name(s)
- page index if available
- DOM anchor signature or stable marker
- start/end offsets in normalized plain-text stream

---

## 7) Cross-references (capture smartly)
Detect xrefs like:
- "انظر" "كما سبق" "وسيأتي" "راجع" "كما تقدم" "في باب…"

Store structured metadata:
- `{type, span_text, target_hint, resolved_topic_id?, resolved_chunk_id?, status}`

Resolve only when high confidence; otherwise keep captured + unresolved.

---

## 8) Footnotes (optimized for future LLM)
Default:
- Preserve footnotes but separate them from main body.

Suggested chunk layout:
- main Arabic body
- then `## FOOTNOTES` section

---

## 9) Exercise-like sections (أسئلة/تمرين/تطبيق) — policy decision
This is a known placement hazard.

**Default policy (safe):**
- Detect exercise headings/blocks (أسئلة، تمرين، تطبيق، تدريبات، مسائل للتدريب…).
- Preserve content exactly.
- Create/target a dedicated topic family under the science, e.g.:
  - `Txxxxxx__تمارين_وتطبيقات`
- Mark these plan items `review_required=true` unless placement confidence is extremely high.
- Never inject headings into answer keys unless clearly delimited.

---

## 10) Heading Detection Engine + Heading Injection (core blocker)
We must convert inconsistent HTML “headings” into real Markdown headings so strict anchors become findable.

**Pipeline:**
HTML → DOM → candidates → verified decisions → inject `##/###` into derived MD → strict splitting.

### Layer A — DOM signatures (Shamela patterns)
Detect candidates using patterns like:
- centered paragraphs/divs (`align=center`, `text-align:center`)
- bold/strong blocks
- font-size changes, colored title spans, `PartName`, etc.
- preceding/following whitespace
- HR separators
- pagehead/page markers boundaries

### Layer B — Deterministic scoring
Score each candidate based on:
- structure (block isolation)
- typography hints (font/bold/center)
- Arabic cue tokens (باب/فصل/تنبيه/مسألة/… + numbering)
- repetition across pages (pagehead detection)
- “metadata zone” proximity (title page / author / publisher)

### Layer C — LLM verifier (ambiguous only)
For borderline candidates, call an LLM with strict JSON output:
```json
{"is_heading": true/false, "level": 2|3, "reason": "title|metadata|footnote|pagehead|body_line", "confidence": 0.0-1.0}

Rate-limit resilience is mandatory:

token-bucket throttling

exponential backoff retries

resume logic (never redo completed candidates)

persistent cache keyed by (candidate_id, model, prompt_hash)

Default injection policy (important):

Default injected level = ## (level=2)

Use ### only when hierarchy is clearly supported (TOC/structure evidence)

Any LLM-decided heading defaults to review_required=true (unless rules are extremely confident)

11) Plan artifacts (every run must be auditable)

Each run has a unique run_id and emits immutable artifacts under:

runs/<run_id>/

Minimum artifacts:

ingest_manifest.json (file list, ordering, hashes, encoding)

book_profile.json (structure reliability + stats)

heading_candidates.jsonl

heading_decisions.jsonl

heading_injections.jsonl

chunk_plan.proposed.json + .md (human-readable)

chunk_plan.approved.json

run_report.md + run_report.json

12) Chunk plan proposal (must be reviewable)

Every plan item includes:

proposed chunk_id

proposed topic_id + path

Arabic display title

preview excerpt (for human review)

provenance (file/page/anchor/offset)

confidence breakdown:

boundary_confidence

topic_purity_confidence

placement_confidence

decision basis (rules/TOC/LLM)

review_required + reason

13) Environment

Windows-first is acceptable

Python 3.11+

SQLite

Deterministic dependency management (uv/poetry) + lockfile

--dry-run mode that runs without LLM calls

Read OpenAI key only from env: OPENAI_API_KEY

Never commit secrets

14) Absolute golden rule

No silent decisions. No content corruption. No destructive migrations.
Everything is auditable. Everything ambiguous is review-gated.
