# Secrets and safety

## Non-negotiable
**Never commit API keys or `.env` files.** This repo contains fixtures and gold labels only.

If a key was ever committed to GitHub (even briefly), assume compromise and **rotate it immediately**.

## What to commit
- ✅ `.env.example` (placeholders only)
- ❌ `.env`, `.env.*`, keys, tokens, credentials

## CI enforcement
CI runs `tools/check_secrets.py` and fails if:
- any `.env` file is present (except `.env.example`)
- an OpenAI key-like string (`sk-...`) is detected in tracked files

## Suggested environment variables
- `OPENAI_API_KEY` (required)
- `OPENAI_MODEL` (optional, e.g. `gpt-4.1`)
- `IBP_AI_PROFILE` (optional: `max` / `balanced`)

## Local setup
Copy the example and fill locally:

```bash
cp .env.example .env
# edit .env (do NOT commit)
```
