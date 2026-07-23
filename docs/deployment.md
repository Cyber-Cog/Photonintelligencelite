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

### 3. Vercel (UI + same-origin `/api` proxy)

1. Import this repo. Root stays the repo root (`vercel.json` builds `frontend/`).
2. **Do not set** `VITE_API_BASE_URL` on Vercel (or remove it). The browser calls
   same-origin `/api/*`; `vercel.json` rewrites those to the Render API.
3. Deploy. Production URL e.g. `https://pic-lite.vercel.app`.
4. Keep-alive (free-tier sleep):
   - GitHub Actions workflow `.github/workflows/keepalive.yml` pings Render every 5 minutes
   - Daily Vercel cron hits `/api/keepalive` (Hobby cannot run sub-daily crons)
   - Open browser tabs also soft-ping `/api/health` every 4 minutes

### 4. Wire origins (second Render pass)

1. On Render, set `CORS_ORIGINS` and `PUBLIC_APP_URL` to the **exact** Vercel origin
   (scheme + host, no trailing slash). Redeploy/restart if needed.
2. Login cookies: with same-origin proxy, the browser stores session cookies on the
   Vercel host. Keep `COOKIE_SECURE=true` on Render (HTTPS).

### 5. Verify

1. `GET https://pic-lite.vercel.app/api/health` — expect JSON in a few seconds when warm
2. Open the Vercel app → **Sign up** or log in as superadmin → Upload / Admin / Run demo
3. Optional later: run `scripts/benchmark_ingest.py` against Render and set `JOB_TIMEOUT_SEC`
   (see below).

Free tier targets **one month of 15-minute data**, not dense 1-minute multi-inverter data
(Render free tier: 512 MB RAM, ephemeral disk — see docs/PRD.md §0).

### Why the API stays on Render (not Vercel serverless)

Analyses use an in-process worker pool and can run longer than Hobby serverless limits.
Vercel hosts the UI and reverse-proxies `/api`; Render keeps the long-lived FastAPI process.
If you later move the API off Render, use the Postgres **external** connection string
(internal `*.render.internal` hostnames will not work from Vercel/Fly).

### Cross-origin cookies (legacy direct `VITE_API_BASE_URL`)

If you point the browser at Render directly, set `COOKIE_SECURE=true` so cookies use
`SameSite=None; Secure`. Prefer the same-origin proxy above instead.

### Keep-alive

Render free tier sleeps when idle (often ~15 min). This repo keeps the API warm via:

1. **GitHub Actions** `.github/workflows/keepalive.yml` — every **5 minutes** (primary)
2. **Vercel cron** `/api/keepalive` — once daily (Hobby limit; backup only)
3. **Open browser tabs** soft-ping `/api/health` every 4 minutes

Keep-alive removes multi-minute cold-start waits for login/demo **start**. It does **not**
make free-tier CPU match a laptop — analysis (pandas/numpy) still runs slower on 512 MB free
instances.

### Why cloud feels slower than local

| Factor | Local | Free cloud (current) |
|--------|-------|----------------------|
| API wake | Always on | Sleeps without keep-alive |
| Network | localhost | Browser → Vercel proxy → Render → Neon |
| CPU/RAM | Your laptop | Shared free instance (~0.1–0.5 CPU, 512 MB) |
| Demo start | Sync validation ~1–3s | Was 15–25s blocking HTTP; now returns immediately and validates in background |

Same-origin `/api` proxy (already in `vercel.json`) avoids CORS preflight. Put Neon Postgres in the
**same region as Render** (typically Oregon / `us-west`). Prefer Neon’s pooled URL; Render
internal DB hostnames only work if Postgres is also on Render.

### Matching local speed (paid)

Free tier **cannot** equal local after keep-alive alone. Closest options:

- **Render Starter** (always-on) + Neon same region, or
- **~$5 VPS** (Hetzner/DigitalOcean) running `docker compose` with API + Postgres together

That removes sleep and puts CPU next to the data — the only path to “feels like local.”

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
