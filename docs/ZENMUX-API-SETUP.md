# ZenMux API key setup (PIC Lite)

PIC Lite’s AI integrity / upload checks call ZenMux **chat completions**. That needs a **chat** key, not a management key.

| Key prefix | Where created | Works for chat? |
|---|---|---|
| `sk-ai-v1-…` | [Pay As You Go](https://zenmux.ai/platform/pay-as-you-go) | Yes (needs PAYG balance / credits) |
| `sk-ss-v1-…` | [Subscription](https://zenmux.ai/platform/subscription) | Yes (uses subscription quota; fine for local/dev) |
| `sk-mg-v1-…` | Console → Management | **No** — billing/usage APIs only → HTTP 403 on `/chat/completions` |

There is **no** public ZenMux API to mint chat keys from a management key. Someone signed into the ZenMux console must create the key once and paste it.

---

## Exact clicks: create the key

### Option A — fastest for local UAT (subscription)

Your ZenMux account already has a free Builder quota (management API confirmed remaining flows). Use that for local testing:

1. Open **https://zenmux.ai/platform/subscription** (sign in if needed).
2. Open **Subscription Management** / API keys for the plan.
3. Click **Create API Key** (or equivalent).
4. Copy the key — it must start with **`sk-ss-v1-`**.

### Option B — production / PAYG

PAYG balance on this account was **$0** when last checked — top up before relying on `sk-ai-v1` in production.

1. Open **https://zenmux.ai/platform/pay-as-you-go** (or Console → **Manage → Pay As You Go**).
2. If Total Balance is `$0`, click **Top Up** and complete payment.
3. In **Pay As You Go API Keys**, click **+ Create API Key**.
4. Name it e.g. `pic-lite`, enable it, copy the key — it must start with **`sk-ai-v1-`**.

Official docs: [Pay As You Go](https://docs.zenmux.ai/guide/pay-as-you-go.html) · [Quick start](https://docs.zenmux.ai/guide/quickstart)

---

## Where to paste the key

### 1. Local (gitignored)

File: **`C:\Users\ayush.r\Desktop\PIC Lite\.env`**

Set (replace the value; keep the other lines):

```env
ZENMUX_API_KEY=sk-ai-v1-…   # or sk-ss-v1-…
ZENMUX_BASE_URL=https://zenmux.ai/api/v1
ZENMUX_MODEL=google/gemini-2.5-flash
```

- `.env` is gitignored (`.env*` ignored; only `.env.example` is tracked).
- Restart the local API process after editing so settings reload.
- Or paste the key in chat — an agent can write `.env` and probe completions in seconds.

### 2. Production API (Render)

Service: **`pic-lite-api`** (`https://pic-lite-api.onrender.com`)

1. Open [Render Dashboard](https://dashboard.render.com) → workspace with **pic-lite-api**.
2. Service **pic-lite-api** → **Environment**.
3. Add / update:
   - `ZENMUX_API_KEY` = your `sk-ai-v1-…` (prefer PAYG for production) or `sk-ss-v1-…` for light use
   - `ZENMUX_BASE_URL` = `https://zenmux.ai/api/v1` (optional if default)
   - `ZENMUX_MODEL` = `google/gemini-2.5-flash` (optional if default)
4. **Save** → wait for redeploy / restart.

Do **not** put this key in Vercel frontend env (`VITE_*`). Server-side only.

---

## Quick verify

After the key is set locally:

```bash
# Expect HTTP 200 (not 403)
curl https://zenmux.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $ZENMUX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"google/gemini-2.5-flash","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
```

Then re-run a fault-run / integrity UAT in the app — AI layer should be OK when the key is chat-capable and the account has quota/credits.

---

## What we already tried (do not re-hunt)

With the local `sk-mg-v1-…` management key:

| Call | Result |
|---|---|
| `GET /management/payg/balance` | 200 (balance `$0`) |
| `GET /management/subscription/detail` | 200 (free tier; remaining flows) |
| `GET/POST …/management/keys`, `…/api-keys`, `…/keys` | 404 / HTML 500 — **no key-mint API** |
| `POST /chat/completions` | **403** |

Render CLI is authenticated for this workspace but **cannot set env vars** (no `render env` command) — use the dashboard path above once you have a chat key.
