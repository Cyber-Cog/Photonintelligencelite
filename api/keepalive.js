/**
 * Keep-alive / wake ping for the Render API.
 *
 * - Vercel Hobby cron can only run daily (see vercel.json) — that is a backup.
 * - Primary cadence is GitHub Actions every 5 minutes (.github/workflows/keepalive.yml).
 * - This route is a Serverless Function and takes precedence over the /api/* rewrite.
 */
const API_ORIGIN = (process.env.API_ORIGIN || "https://pic-lite-api.onrender.com").replace(/\/$/, "");

module.exports = async function handler(req, res) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90_000);
  const started = Date.now();
  try {
    const upstream = await fetch(`${API_ORIGIN}/api/health`, {
      method: "GET",
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });
    const text = await upstream.text();
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {
      // non-JSON upstream body
    }
    res.setHeader("Cache-Control", "no-store");
    res.status(upstream.ok ? 200 : 502).json({
      ok: upstream.ok,
      upstream_status: upstream.status,
      elapsed_ms: Date.now() - started,
      health: json,
    });
  } catch (err) {
    res.setHeader("Cache-Control", "no-store");
    res.status(503).json({
      ok: false,
      elapsed_ms: Date.now() - started,
      error: err instanceof Error ? err.message : String(err),
    });
  } finally {
    clearTimeout(timer);
  }
};
