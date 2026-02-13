# Context and severity

This project is a correctness-first pipeline. If chunk boundaries or topic placement are wrong, **years** of downstream work (encyclopedia synthesis) becomes unreliable. Therefore:

- **Accuracy > everything** (speed, convenience, elegance).
- **Fail closed**: when uncertain, route to `_REVIEW/` with an explicit reason.
- **No silent guesses.** Every non-trivial decision must be traceable.
- **Append-only by default.** Never delete or overwrite canonical artifacts without archiving.

The intended use is to build a lifelong Arabic morphology (ṣarf) encyclopedia, but the ingester must generalize to other Islamic sciences.

Key constraints:

- Input is **Arabic** Shamela HTML exports (irregular heading markup, inconsistent styles).
- Chunk splitting is **strict-anchor-based**: only Markdown headings (`##`, `###`, …) count as anchors.
- Because HTML→MD conversion often loses headings, the pipeline must include a **Heading Detection + Heading Injection** stage.


## Binding policy decisions (current)
- Human approval is required for **all** injected headings (slowest, safest).
- Exercise-like sections (أسئلة/تمرين/تطبيق/تدريبات/...) default to a dedicated **Exercises/Applications** topic family, but remain review-gated.

## Security
Never commit `.env` or API keys. CI fails if secrets are detected.
