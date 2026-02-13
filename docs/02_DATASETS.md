# Datasets in this repo

This repo is seed-only: fixtures + gold labels + specs. The implementation is expected to be built by Devin/Codex and audited by humans.

## 1) Shamela HTML fixtures

Location: `fixtures/shamela_exports/`

Each fixture book lives under a stable ASCII folder name (e.g. `BK003_taj_al_arus/`). The raw Shamela export is stored unchanged under:

- `fixtures/shamela_exports/<book_id>/source_raw/`

Metadata:

- `fixtures/shamela_exports/<book_id>/meta.json`

Current fixture set (11 books):

- `BK001_shadha_al_urf` — شذا العرف في فن الصرف
- `BK002_lisan_al_arab` — لسان العرب
- `BK003_taj_al_arus` — تاج العروس من جواهر القاموس
- `BK004_sharh_ibn_aqil` — شرح ابن عقيل على ألفية ابن مالك
- `BK005_al_muwafaqat` — الموافقات
- `BK006_al_jadwal_i3rab_al_quran` — الجدول في إعراب القرآن
- `BK007_al_mughni_ibn_qudama_turki` — المغني لابن قدامة - ت التركي
- `BK008_tafsir_ibn_kathir_salama` — تفسير ابن كثير - ت السلامة
- `BK009_siyar_a3lam_al_nubala_hadith` — سير أعلام النبلاء - ط الحديث
- `BK010_fath_al_bari_bukhari_salafiyya` — فتح الباري بشرح البخاري - ط السلفية
- `BK011_al_muzhir_ulum_al_lugha` — المزهر في علوم اللغة وأنواعها

### Why these fixtures?
They intentionally stress different failure modes:
- mixed heading markup (center / bold / font / spans)
- running headers (pagehead) vs real headings
- dense footnotes and marginalia
- dictionary-style entries (many short “false headings”)
- long multi-volume pagination + noisy page markers

### Pattern stats (deterministic)
- `fixtures/manifests/pattern_stats.json` contains counts of common HTML signatures across these fixtures.

### File manifest (immutability guard)
- `fixtures/manifests/manifest.json` lists every file with SHA256 and size to prevent silent drift.

## 2) Gold heading labels (Phase 1 supervision)

Location: `training/gold_snippets/`

Key files:
- `heading_candidates_v3.jsonl` — candidate snippets (with `html_excerpt` + local context).
- `heading_gold_v3.jsonl` — raw manual labels (198 items).
- `heading_gold_v3.cleaned.jsonl` — normalized labels used by CI and training.
- `splits/train.jsonl` and `splits/holdout.jsonl` — deterministic 80/20 split derived from the cleaned gold.
- `must_not_heading.jsonl` — 40 tricky false positives that must never be injected as headings.

Schema validation is enforced by:
- `tools/validate_gold.py`

## 3) Policy fixtures (important)
- **Human approval for ALL injected headings** (slowest, safest).
- Exercise-like sections (أسئلة/تمرين/تطبيق/تدريبات/...) default to **Exercises/Applications** topic family, but remain **review-gated**.
