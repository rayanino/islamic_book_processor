# Requirements summary (MVP)

This file is a summary. If anything conflicts, **`docs/SPEC.md` wins**.

## Inputs
- Primary: **Arabic** Shamela Desktop export as **HTML** (default export; page markers enabled).
- Optional: separate TOC HTML (if available) or TOC embedded in the export (often at the end).

## Core behaviors (must)
- **Plan-first**: propose → human approve → apply.
- **Strict anchors**: only Markdown headings `##/###/...` are split anchors.
- **Heading injection stage** exists to recover headings from irregular HTML.
- **Human approval for ALL injected headings**.
- **Fail-closed**: uncertainty routes to `_REVIEW/` with evidence.
- **Content preservation**: extracted chunk bodies are verbatim from source (no rewriting).

## Outputs (implementation-defined layout)
The implementation must maintain:
- immutable run artifacts (`runs/<run_id>/...`)
- canonical chunk bodies that are append-only
- a registry (SQLite/JSONL) as source of truth
- a projection/view by topic (regenerable)

## Policies
- Exercises sections (أسئلة/تمرين/تطبيق/تدريبات/...) default to **Exercises/Applications** topic family, but remain **review-gated**.
