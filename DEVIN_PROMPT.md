# Devin initial instruction (paste into Devin)

You are implementing **Islamic Book Processor (IBP)** from scratch. Treat this as a **mission‑critical correctness system**.

## Canonical documents
Read **in this order** and follow exactly:
1) `docs/SPEC.md` (authoritative)
2) `docs/04_ACCEPTANCE.md` (measurable pass/fail)
3) `docs/03_HEADING_ENGINE_SPEC.md` (heading engine detail)
4) `docs/02_DATASETS.md` (fixtures + gold labels)

If anything conflicts, **SPEC.md wins**.

## Mission
Ingest Arabic Islamic books exported from **Shamela Desktop as HTML** and produce:
- a **reviewable plan** for chunk boundaries + topic placement + heading injections,
- then, **only after human approval**, apply the plan to write outputs.

## Non‑negotiables you must enforce
- **Correctness > everything.** No silent guesses.
- **Fail‑closed:** uncertainty ⇒ `_REVIEW/` with explicit reason + evidence.
- **Strict anchors only:** only Markdown headings `##/###/...` are split anchors.
- **Human approval for ALL injected headings** (not only ambiguous ones).
- **Exercises policy:** exercise-like sections (أسئلة/تمرين/تطبيق/تدريبات/...) default to a dedicated Exercises/Applications topic family, but remain **review‑gated**.
- **Canonical chunks are append‑only**; never rewrite bodies in place.
- **Topic folders are a projection/view**; safe to move via registry mapping.
- **No destructive reruns:** implement `--clean-book` to archive prior outputs.

## Data you must use
- Fixtures: `fixtures/shamela_exports/` (immutable; do not edit raw HTML)
- Gold labels: `training/gold_snippets/heading_gold_v3.cleaned.jsonl`
- Must-not-heading: `training/gold_snippets/must_not_heading.jsonl`
- Split sets: `training/gold_snippets/splits/train.jsonl` and `.../holdout.jsonl`

## Build order (MVP milestones)
1) Repo scaffold: Python 3.11+, `src/ibp/`, CLI `ibp`, tests.
2) Deterministic ingest: manifest hashing, encoding safety, file ordering.
3) BookCatcher scan: detect pages, running headers, footnotes, metadata zones, embedded TOC (including TOC-at-end).
4) Heading candidates (Layer A) + deterministic scoring (Layer B).
5) Optional LLM verification (Layer C) **only to propose labels**; still requires human approval to inject.
   - Implement token-bucket throttling, exponential backoff, resumable cache keyed by `(candidate_id, model, prompt_hash)`.
6) Generate `heading_injections.proposed.jsonl` + plan report.
7) Approval gate: user can accept/reject/edit each injection.
8) Apply: inject headings into derived Markdown; run strict splitting; produce chunk plan; approval gate; apply to canonical chunks + projection.

## Output expectations (high level)
- Every run has `run_id` and an immutable `runs/<run_id>/` folder with all artifacts.
- Every decision affecting boundaries/placement is traceable to evidence (DOM signature, excerpt, score, optional LLM JSON).

## Secrets
Never commit `.env`. Read key from environment variable `OPENAI_API_KEY` only.
