# Authentication & superadmin

PIC Lite uses **httpOnly session cookies** (not bearer JWTs in localStorage), bcrypt password hashes, CSRF double-submit cookies on mutating requests, and server-side role checks. Client-only flags never unlock protected APIs.

## Local signup / login

1. Open the app → **Sign up** (header) or `/signup`.
2. Email + password (min 8 chars). Anyone can register.
3. If SMTP is **not** configured and `AUTH_AUTO_VERIFY=true` (default): the account is **auto-verified** and you can use Upload / Docs immediately.
4. If SMTP is configured (or `AUTH_AUTO_VERIFY=false`): check email, or use the `verification_link` returned by `POST /api/auth/signup` (also logged in the API console). Open `/verify-email?token=…`.
5. **Log in** at `/login`. After login from Upload/template CTAs, you return via `?next=`.

Password reset: `/forgot-password` → email or DEV `reset_link` → `/reset-password?token=…`.

## Run demo without auth

**Run demo** on the landing page calls `POST /api/demo` with **no login required**. Demo jobs are marked `is_demo=true` and remain readable without a session. Upload, templates, `/docs`, and non-demo job APIs require a verified session.

## Superadmin seed

Set in `.env` (or environment) before starting the API:

```env
# Lab default (allowed by auth email validation — .local is fine here):
PIC_SUPERADMIN_EMAIL=admin@pic.local
PIC_SUPERADMIN_PASSWORD=admin12345
PIC_SUPERADMIN_NAME=Superadmin

# Or use a public-looking address if you prefer:
# PIC_SUPERADMIN_EMAIL=admin@example.com
# PIC_SUPERADMIN_PASSWORD=choose-a-strong-password
```

On startup the API creates or repairs that user as `role=superadmin` (email already verified). If `PIC_SUPERADMIN_PASSWORD` is set and no longer matches the stored hash, it is synced from `.env`. Open `/admin` while logged in as that user.

Auth signup/login/forgot-password accept lab domains (`.local`, `.test`, `.invalid`, …) that strict `EmailStr` would reject. Local `.env` ships with `admin@pic.local` / `admin12345` — change credentials for any shared environment.

## SMTP (optional)

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM=noreply@example.com
SMTP_USE_TLS=true
PUBLIC_APP_URL=https://your-app.example
```

Without SMTP, verification and reset links are **logged** and returned in API JSON (`verification_link` / `reset_link`) for local DEV.

## Session / CSRF

- Cookie `pic_session` — httpOnly session id
- Cookie `pic_csrf` — readable CSRF token; send as `X-CSRF-Token` on POST/PATCH/DELETE
- `credentials: "include"` on all frontend fetches
- Rate limits on signup/login/forgot (per IP)
- **SameSite:** `COOKIE_SECURE=false` (local) → `SameSite=Lax`; `COOKIE_SECURE=true`
  (Vercel UI + Render API) → `SameSite=None; Secure` so cross-origin login works.
  See docs/deployment.md.

## Audit trail

Table `audit_events` (and UI at `/admin` → Audit). Events include:

`auth.signup`, `auth.login`, `auth.login_failed`, `auth.logout`, `auth.email_verified`, `auth.password_reset_requested`, `auth.password_reset`, `auth.profile_updated`, `auth.password_changed`, `admin.user_updated`, `admin.user_banned`, `admin.user_unbanned`, `admin.user_role_changed`, `admin.user_deleted`, `admin.user_force_verified`, `admin.user_reset_requested`, `admin.user_verification_resent`, `template.download`, `job.upload`, `job.mapping_save`, `job.plant_save`, `job.validation`, `analysis.start`, `analysis.complete`, `analysis.fail`, `report.download_pdf`, `report.download_excel`, `demo.start`, `job.abandoned`, …

## Superadmin user management

At `/admin` → Users (superadmin only):

| Action | API | Notes |
|--------|-----|--------|
| Edit name / role | `PATCH /api/admin/users/{id}` | Role change confirms in UI; cannot demote yourself; cannot demote last active superadmin |
| Ban / Unban | `PATCH` with `is_active` | Ban revokes sessions; banned users cannot log in |
| Delete | `DELETE /api/admin/users/{id}` | Soft-delete (anonymize email, deactivate); cannot delete yourself or last superadmin |
| Force verify | `POST …/force-verify` | Sets `email_verified=true` |
| Resend reset / verify | `POST …/resend-reset`, `POST …/resend-verification` | Optional links returned when SMTP unset |

All mutating admin routes require CSRF (`X-CSRF-Token`) + `role=superadmin` (403 otherwise).

## After pulling these changes

1. `pip install -r requirements.txt` (adds `bcrypt`, `email-validator`)
2. **Restart the API** (`stop.bat` then `start.bat`, or restart uvicorn) so seed runs and the lenient auth email validator loads
3. Hard-refresh the browser (Ctrl+Shift+R) so the new header/auth UI loads
4. Log in with the configured superadmin (default local: `admin@pic.local` / `admin12345`)
