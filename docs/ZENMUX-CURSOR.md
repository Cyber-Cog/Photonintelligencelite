# ZenMux in Cursor (this project only)

This setup is for **Cursor IDE**, not the PIC Lite web app. No backend or frontend code is involved.

## 1. Get a chat API key

In [ZenMux Console](https://zenmux.ai), create a **chat API key** (`sk-ai-v1-…` or `sk-ss-v1-…`).

Do **not** use a management key (`sk-mg-v1-…`) — that is for billing/usage APIs, not chat.

For the **PIC Lite web API** (local `.env` / Render), see [ZENMUX-API-SETUP.md](./ZENMUX-API-SETUP.md).

If a key was pasted in chat, rotate it in the console.

## 2. Cursor Settings → Models

1. Open **Cursor Settings** (gear icon) → **Models**
2. **OpenAI API Key** — turn **ON**, paste your ZenMux **chat** key
3. **Override OpenAI Base URL** — turn **ON**, set exactly:
   ```
   https://zenmux.ai/api/v1
   ```
   No trailing slash.

## 3. Add a custom model name

Cursor does not auto-discover ZenMux models. Add one manually:

1. **+ Add Custom Model**
2. Enter a **unique** name (avoid built-in names like `gpt-4o`):
   - Suggested display name in this project: **`zenmux-gemini-flash`**
3. In the model id field (if separate), use the ZenMux slug, e.g.:
   ```
   google/gemini-2.5-flash
   ```
4. Enable the toggle next to the new model

Pick any slug from [zenmux.ai/models](https://zenmux.ai/models).

## 4. Use it

- Chat / Agent: choose **`zenmux-gemini-flash`** (or your custom name) in the model dropdown
- Project subagent: `/pic-lite-analyst` — see `.cursor/agents/pic-lite-analyst.md`

## 5. Cursor Pro

Custom third-party models usually require **Cursor Pro**. If you only see `auto` or upgrade prompts, that is a Cursor plan limit, not a ZenMux misconfiguration.

Official guide: [ZenMux + Cursor](https://docs.zenmux.ai/best-practices/cursor)

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| 401 / invalid key | Use `sk-ai-v1-…`, no extra spaces |
| Model not found | Copy exact slug from ZenMux model list |
| Still uses Cursor billing | Custom name must differ from built-in models |
| Claude/GPT tool errors | Route only via OpenAI override + custom model; disable conflicting provider keys |

**Never commit API keys to this repo.**
