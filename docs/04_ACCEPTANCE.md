# Acceptance criteria (measurable)

These criteria are intentionally conservative and safety‑biased. Passing means “safe to scale”, not “perfect”.

If anything conflicts, `docs/SPEC.md` is authoritative.

## A) End‑to‑end workflow (target scenario)
For a lab book (start with `BK001_shadha_al_urf`), a passing run must:

1) **Scan** the HTML (deterministic) and produce diagnostics (signatures, page markers, likely TOC regions).
2) **Propose** heading injections (do not apply).
3) **Halt for human approval** of **ALL** heading injections.
4) Apply approved injections to **derived** Markdown (raw HTML must remain unchanged).
5) Run **strict-anchor splitting** (`##/###/...` anchors only).
6) **Propose** chunk boundary + topic placement plan.
7) **Halt for human approval** of the chunk/placement plan.
8) Apply approved plan to write:
   - canonical chunks (append-only)
   - projection by topic (regenerable view)
   - run artifacts + review report

## B) Metrics

### B1) Anchor-miss reduction (strict policy unchanged)
Baseline: strict anchors on the unmodified HTML→MD output.

After heading injection:
- `anchor_miss_after < anchor_miss_before`

Initial target:
- **≥ 40% relative reduction** on the lab book  
  i.e. `(before - after) / before >= 0.40`

### B2) Precision guardrail (must-not-heading)
On `training/gold_snippets/must_not_heading.jsonl`:
- **0 injected headings** without explicit human approval
- any match must appear in the review report with a “blocked by must-not-heading” reason

### B3) Holdout stability (no overfitting)
A deterministic holdout set exists:
- `training/gold_snippets/splits/holdout.jsonl`

Minimum expectation for Phase 1:
- no regression in false-positive rate on holdout compared to train (report both)

(Exact thresholds may be tuned after first implementation, but regression is not allowed.)

## C) Safety / determinism

### C1) No destructive reruns
A rerun must never silently mix outputs:
- implement `--clean-book` to archive prior outputs under `_ARCHIVE/<book_id>/<timestamp>/...`

### C2) Traceability
For each injected heading:
- store the DOM signature, excerpt, score, and (if used) cached LLM JSON
- link it to the derived Markdown line range it modified

### C3) Secrets hygiene
CI must fail if `.env` or API keys are committed.
