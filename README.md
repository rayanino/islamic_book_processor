# Islamic Book Processor (IBP)

**Mission:** deterministically ingest Arabic Islamic books exported from **Shamela Desktop (HTML)**, split them into **encyclopedic‑grade** topic chunks, and store them in a long‑lived corpus with **fail‑closed QA** (uncertain ⇒ review).

This is a **high‑assurance correctness system**. Wrong chunk boundaries or wrong placement silently corrupts downstream scholarship and can waste years.

## Read these first (canonical)
- `docs/SPEC.md` — authoritative requirements (if anything conflicts, SPEC wins)
- `docs/04_ACCEPTANCE.md` — measurable pass/fail targets
- `DEVIN_PROMPT.md` — paste as Devin’s initial instruction

## Non‑negotiables (hard)
- **Correctness > coverage > speed.**
- **Fail‑closed:** uncertainty routes to `_REVIEW/` with explicit reasons + evidence.
- **Plan‑first + human approval gate** before *any* writes.
- **Strict anchors:** only Markdown headings `##/###/...` are split anchors.
- **Heading injection is always review‑gated:** **every injected heading requires human approval** (slowest, safest).
- **Exercises policy:** exercise-like sections (أسئلة/تمرين/تطبيق/تدريبات/...) default to a dedicated **Exercises/Applications** topic family, but remain **review‑gated**.
- **Content preservation:** chunk bodies reproduce source text exactly (no paraphrase).
- **Canonical chunks are append‑only; topic folders are a projection** (safe moves without rewriting bodies).

## Repo contents
- `fixtures/shamela_exports/` — immutable Shamela HTML exports (+ `meta.json` per book)
- `training/gold_snippets/` — heading candidate snippets + gold labels + splits + must-not-heading
- `tools/` — deterministic helpers + CI checks (stdlib only)
- `docs/` — specs

## Security
Never commit secrets. Use `.env` locally (ignored by git). Commit only `.env.example`.
If a key was ever committed, rotate it immediately.
