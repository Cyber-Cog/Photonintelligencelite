# Gemini / AI Studio setup (PIC Lite)

PIC Lite uses **Google Gemini** (AI Studio Generative Language API) **alongside** deterministic parsers:

1. **Upload parse-assist** — after heuristic column mapping / wide-CSV reshape, if signals look thin or headers are ambiguous, Gemini proposes canonical field mappings. High-confidence suggestions are merged into the mapping list; rules always run first.
2. **Upload + Results integrity** — rules always run; Gemini reviews contradictions when `GEMINI_API_KEY` is set. ZenMux remains an optional fallback if Gemini is unset (or fails and a non–`sk-mg` ZenMux chat key exists).

Not a chatbot. Keys are **server-side only** (never `VITE_*`).

## Create a key

1. Open [Google AI Studio → API keys](https://aistudio.google.com/apikey).
2. Create a key (e.g. named `Parsing`).
3. Paste the **full** key into this repo’s gitignored `.env`:

```env
GEMINI_API_KEY=your-full-key-here
GEMINI_MODEL=gemini-2.0-flash
```

Optional: `GEMINI_TIMEOUT_SEC=45`.

## Production (Render)

Set `GEMINI_API_KEY` (and optionally `GEMINI_MODEL`) on **pic-lite-api**. Do not put the key on Vercel/frontend.

## Smoke probe

```bash
# From repo root with .env loaded
python -c "from backend.app.config import Settings; from backend.app.services.gemini_client import call_gemini_generate; s=Settings(); t,m,e=call_gemini_generate(s, system='Reply JSON', user='{\"ping\":true}', json_mode=True); print(m, e or 'ok', (t or '')[:80])"
```

Expect HTTP 200 / no error. Integrity / parse-assist responses should show `ai_layer=ok`, `provider=gemini`, and `source=rules+gemini` (or `rules+ai` / `rules+zenmux` depending on provider).

## Security

- Never commit the key.
- Never log the full key (client redacts prefixes).
- Screenshot / UI often truncates keys with `…` — always copy the full value from AI Studio.
