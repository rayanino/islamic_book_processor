# Heading detection + injection engine (core blocker)

## Why this exists
Shamela HTML is inconsistent in how it encodes headings (centered/bold/font spans/etc.). A naïve HTML→Markdown conversion often produces headings as **plain text** or **bold**, not `##`.

Under the strict splitting rule (**anchors are Markdown headings only**), this causes massive `_ANCHOR_MISS`.

**We do NOT relax strictness.** We recover boundaries by detecting headings in HTML and injecting `##/###` into derived Markdown.

## Binding policies (do not change)
- **Strict anchors only:** only Markdown headings `##/###/...` count as split anchors.
- **Fail-closed:** if unsure whether something is a heading, do not inject; route to review.
- **Human approval for ALL injected headings:** every injected heading is a plan item that must be approved before application.
- **Content preservation:** heading injection may add Markdown heading markers, but must not rewrite body text.

## Where the stage lives
Insert a dedicated stage between HTML→MD and splitting:

**HTML → DOM → heading candidates → (score + verify) → proposed injections → human approval → inject `##/###` → strict split**

## Layer A — Candidate generation (DOM signatures)
Parse HTML into a DOM and emit candidates from common Shamela patterns:
- Centered blocks: `align="center"`, `style="text-align: center"`, `<center>`
- Typography blocks: `<b>`, `<strong>`, `<font>` with “title-like” structure
- Shamela spans: `span.title`, `span.PartName`, `PageHead`, `PageText`, `PageNumber`, `footnote`
- HR separators and large whitespace before/after
- Common Arabic heading tokens: باب، فصل، تنبيه، قاعدة، فائدة، مسألة، تمهيد، خاتمة، … (+ numbered variants)

Each candidate MUST include:
- `candidate_id` (stable across runs)
- `text` (exact surface text)
- `kind` (best-effort: title/metadata/pagehead/footnote/body)
- `signature` (deterministic structural fingerprint)
- `context_before` / `context_after`
- `html_excerpt` (small excerpt; enough to judge structure)

## Layer B — Deterministic scoring (no LLM)
Compute a score using only deterministic features:
- Structure: centered, isolated paragraph, bold/strong, span.title, preceded by HR, etc.
- Lexical: heading tokens, numbering (١/1), punctuation patterns
- Length: too short (single token) vs too long (sentence paragraph)
- Position: early pages (metadata zones), repeated per page (pagehead), inside footnotes, etc.

Output:
- `score` in [0, 1]
- `suggested.is_heading`, `suggested.level` (2 or 3), `suggested.reason`, `suggested.confidence`

**Never inject solely from score.** Score only ranks candidates and proposes.

## Layer C — Optional LLM verifier (advisory, JSON-only)
For ambiguous candidates, call an LLM verifier with strict JSON output:

```json
{"is_heading": true, "level": 2, "normalized_title": "باب الإدغام", "confidence": 0.84, "reason": "title"}
```

Rules:
- LLM output is **advisory only**.
- Deterministic caching keyed by `(candidate_id, model, prompt_hash)`.
- Token-bucket throttling + exponential backoff + resumable runs (no partial “null” fields).

## Plan + approval (the safety gate)
The engine produces a **proposal**:

- `heading_injections.proposed.jsonl` (or equivalent)
- a human-readable report summarizing:
  - counts by `kind`, score bands
  - top uncertain candidates
  - must-not-heading matches
  - expected anchor-miss reduction estimate

**Human approval is required for every injected heading** (even high-confidence ones).
Approval output:
- `heading_injections.approved.jsonl`

Only the approved set is applied to derived Markdown.

## Level policy (## vs ###)
Default to:
- `##` for primary headings (chapter-level)
- `###` only when there is strong evidence of a real nested hierarchy on that page/region

If unsure, prefer `##` and route ambiguous hierarchy to review.

## Must-not-heading guardrail
Before proposing injection, check candidates against:
- `training/gold_snippets/must_not_heading.jsonl`

Matches must default to **reject** unless explicitly approved.

## Exercises / applications detection
When a candidate heading or section marker indicates exercises:
- tokens: أسئلة، سؤال، تمرين، تطبيق، تدريبات، اختبار، …
Policy:
- default classification is **Exercises/Applications** topic family
- still **review-gated** (plan item; human approval required)
