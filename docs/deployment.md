# Deployment

## Local (Docker Compose)

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
# Edit .env: set SESSION_SECRET, optionally PIC_SUPERADMIN_* (see comments in .env.example)
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`, health at `/api/health`)
- Frontend: http://localhost:5173
- Postgres: localhost:5432 (`pic_lite` / `pic_lite`)

Local defaults target **one month of dense 1-minute multi-inverter data** (docs/PRD.md §0).
Keep `COOKIE_SECURE=false` locally (HTTP + same-site `SameSite=Lax`).

## Free tier connect checklist (Neon → Render → Vercel)

Do these in order. You create the accounts and paste URLs/secrets yourself; the repo already
has `render.yaml`, `vercel.json`, and Dockerfiles.

### 1. Neon

1. Create a Postgres project.
2. Copy the **pooled** connection string (`postgresql://…` or `postgres://…` is fine —
   the API normalizes to `postgresql+psycopg://`).

### 2. Render (API)

1. **New → Blueprint** → connect this Git repo → apply `render.yaml` (`pic-lite-api`).
2. In the service **Environment**, set every `sync: false` variable:

   | Variable | Value |
   |----------|--------|
   | `DATABASE_URL` | Neon pooled string from step 1 |
   | `CORS_ORIGINS` | Your Vercel origin once known (step 3), e.g. `https://….vercel.app` — no trailing slash |
   | `PUBLIC_APP_URL` | Same as the Vercel app URL |
   | `SESSION_SECRET` | Long random string (`openssl rand -hex 32`) |
   | `PIC_SUPERADMIN_EMAIL` | Your admin email |
   | `PIC_SUPERADMIN_PASSWORD` | Strong password (min 8 chars) |

   Already set by the blueprint (do not override unless you know why):

   - `PIC_LITE_FREE_TIER=true`
   - `COOKIE_SECURE=true` ← required so login cookies work cross-origin (`SameSite=None; Secure`)
   - `MAX_CONCURRENT_JOBS=1`
   - `AUTH_AUTO_VERIFY=true`
   - `JOB_ROOT=/tmp/pic-lite-jobs`

3. Deploy, then open `https://<your-service>.onrender.com/api/health` — expect OK/JSON.
4. Copy the public API base URL (no path), e.g. `https://pic-lite-api.onrender.com`.

### 3. Vercel (UI)

1. Import this repo. Root can stay the repo root (`vercel.json` already `cd`s into `frontend/`),
   **or** set Root Directory to `frontend/` (then ignore root `vercel.json` build paths).
2. Environment variable:

   | Variable | Value |
   |----------|--------|
   | `VITE_API_BASE_URL` | Render API URL from step 2 (no trailing slash) |

3. Deploy. Copy the production URL (e.g. `https://….vercel.app`).

### 4. Wire origins (second Render pass)

1. On Render, set `CORS_ORIGINS` and `PUBLIC_APP_URL` to the **exact** Vercel origin
   (scheme + host, no trailing slash). Redeploy/restart if needed.
2. Confirm login from the Vercel site works (cookie must be set for the Render host with
   `Secure` + `SameSite=None`).

### 5. Verify

1. `GET https://<render>/api/health`
2. Open the Vercel app → **Sign up** or log in as superadmin → Upload / Admin.
3. Optional later: run `scripts/benchmark_ingest.py` against Render and set `JOB_TIMEOUT_SEC`
   (see below).

Free tier targets **one month of 15-minute data**, not dense 1-minute multi-inverter data
(Render free tier: 512 MB RAM, ephemeral disk — see docs/PRD.md §0).

### Cross-origin cookies (why `COOKIE_SECURE=true`)

Vercel (UI) and Render (API) are **different origins**. Credentialed `fetch` only keeps
session cookies if they are `SameSite=None; Secure`. The API sets that automatically when
`COOKIE_SECURE=true` (see `backend/app/auth/sessions.py`). Local Docker keeps `false` / `Lax`.

**Optional same-origin proxy:** you can instead proxy `/api/*` through Vercel to Render and
point the UI at `""` / same origin so `SameSite=Lax` works — not configured by default;
prefer `COOKIE_SECURE=true` + explicit `VITE_API_BASE_URL`.

### No self-ping

Do **not** add a keepalive/self-ping cron against the Render URL. This is an explicit
product decision (docs/PRD.md §0) — Render treats such synthetic traffic as abnormal, and
the UI's own 2-3 second status poll during an active job plus the stale-job reclaim sweep
(`backend/app/services/cleanup_service.py`) are the whole mechanism.

### Setting `JOB_TIMEOUT_SEC`

The placeholder value in `analytics/config/defaults.yaml` (`900`s) must be replaced with
3× the measured full-pipeline wall-clock time for the bundled demo dataset on the deployed
Render instance (docs/PRD.md §0, §21 Phase 2/4). Run `scripts/benchmark_ingest.py` against
the deployed API and update `JOB_TIMEOUT_SEC` as a Render environment variable once
measured — see that script's docstring.

## Manual steps after cloud accounts are connected

1. **Install and test locally** (optional sanity check)

   ```bash
   pip install -r requirements.txt
   pytest -v
   cd frontend && npm install && npm run build
   ```

2. **Run the stack locally** with `docker compose up --build` and click through upload →
   mapping → validation → dashboard → report once.

3. **Benchmark on the deployed instance** (after free-tier connect checklist above):

   ```bash
   python scripts/benchmark_ingest.py --base-url https://<your-render-app>.onrender.com --stage ingest
   python scripts/benchmark_ingest.py --base-url https://<your-render-app>.onrender.com --stage full
   ```

   Take the `full` stage's `total_wall_clock`, multiply by 3, and set that as `JOB_TIMEOUT_SEC`
   in the Render dashboard (capped at `job_timeout_safety_cap_sec` in
   `analytics/config/defaults.yaml`).

4. **Walk the acceptance checklist** in the plan (§ Acceptance criteria) end-to-end against
   the deployed instance before calling the MVP done.
