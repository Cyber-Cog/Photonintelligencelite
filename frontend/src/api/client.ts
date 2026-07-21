import type {
  DetectEquipmentResponse,
  JobStatusResponse,
  PlantConfigInput,
  ResultsResponse,
  SetupContextResponse,
  UploadResponse,
  ValidationResponse,
} from "@/types";

/** Same-origin on Vite :5173 (proxied); otherwise env or localhost API. */
function resolveApiBase(): string {
  if (typeof window !== "undefined") {
    const { hostname, port } = window.location;
    if ((hostname === "localhost" || hostname === "127.0.0.1") && port === "5173") {
      return "";
    }
  }
  if (import.meta.env.VITE_API_BASE_URL) return import.meta.env.VITE_API_BASE_URL;
  return import.meta.env.DEV ? "" : "http://localhost:8000";
}

const BASE_URL = resolveApiBase();

export type AuthUser = {
  id: string;
  email: string;
  name: string;
  role: string;
  email_verified: boolean;
  created_at: string;
  last_login_at: string | null;
  tour_completed_at?: string | null;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)pic_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function authHeaders(json = true): HeadersInit {
  const headers: Record<string, string> = {};
  if (json) headers["Content-Type"] = "application/json";
  const csrf = getCsrfToken();
  if (csrf) headers["X-CSRF-Token"] = csrf;
  return headers;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : body.detail || message;
      if (Array.isArray(body.detail)) {
        message = body.detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join("; ");
      }
    } catch {
      // ignore body parse failure
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return undefined as T;
  return res.json() as Promise<T>;
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (method !== "GET" && method !== "HEAD") {
    const csrf = getCsrfToken();
    if (csrf && !headers.has("X-CSRF-Token")) headers.set("X-CSRF-Token", csrf);
  }
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  return handle<T>(res);
}

export async function uploadFiles(files: File[], onProgress?: (pct: number) => void): Promise<UploadResponse> {
  return _postUpload(`${BASE_URL}/api/upload`, files, onProgress);
}

/** Replace SCADA files on an existing job (keeps plant config; rematches mapping by column name). */
export async function replaceUploadFiles(
  jobId: string,
  files: File[],
  onProgress?: (pct: number) => void,
): Promise<UploadResponse> {
  return _postUpload(`${BASE_URL}/api/jobs/${jobId}/replace-upload`, files, onProgress);
}

function _postUpload(url: string, files: File[], onProgress?: (pct: number) => void): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", files[0]);
  for (let i = 1; i < files.length; i++) {
    form.append("additional_files", files[i]);
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.withCredentials = true;
    const csrf = getCsrfToken();
    if (csrf) xhr.setRequestHeader("X-CSRF-Token", csrf);
    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable && onProgress) onProgress(Math.round((evt.loaded / evt.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        let message = `Upload failed (${xhr.status})`;
        try {
          message = JSON.parse(xhr.responseText).detail || message;
        } catch {
          // ignore
        }
        reject(new ApiError(xhr.status, message));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error while uploading."));
    xhr.send(form);
  });
}

/** @deprecated use uploadFiles */
export async function uploadFile(file: File, onProgress?: (pct: number) => void): Promise<UploadResponse> {
  return uploadFiles([file], onProgress);
}

export const authApi = {
  me: () =>
    apiFetch<{
      user: AuthUser | null;
      csrf_token: string | null;
      smtp_configured: boolean;
      auth_auto_verify: boolean;
    }>("/api/auth/me"),
  signup: (email: string, password: string, name: string) =>
    apiFetch<{
      user: AuthUser;
      csrf_token: string;
      message?: string | null;
      verification_link?: string | null;
    }>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    }),
  login: (email: string, password: string) =>
    apiFetch<{ user: AuthUser; csrf_token: string; message?: string | null }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => apiFetch<{ message: string }>("/api/auth/logout", { method: "POST", headers: authHeaders() }),
  verifyEmail: (token: string) =>
    apiFetch<{ message: string }>("/api/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
  resendVerification: () =>
    apiFetch<{ message: string; verification_link?: string | null }>("/api/auth/resend-verification", {
      method: "POST",
      headers: authHeaders(),
    }),
  forgotPassword: (email: string) =>
    apiFetch<{ message: string; reset_link?: string | null }>("/api/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  resetPassword: (token: string, new_password: string) =>
    apiFetch<{ message: string }>("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password }),
    }),
  updateProfile: (name: string) =>
    apiFetch<{ user: AuthUser; csrf_token: string }>("/api/auth/profile", {
      method: "PATCH",
      headers: authHeaders(),
      body: JSON.stringify({ name }),
    }),
  changePassword: (current_password: string, new_password: string) =>
    apiFetch<{ message: string }>("/api/auth/change-password", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ current_password, new_password }),
    }),
  completeTour: () =>
    apiFetch<{ user: AuthUser; csrf_token: string }>("/api/auth/tour/complete", {
      method: "POST",
      headers: authHeaders(),
    }),
  resetTour: () =>
    apiFetch<{ user: AuthUser; csrf_token: string }>("/api/auth/tour/reset", {
      method: "POST",
      headers: authHeaders(),
    }),
};

export const adminApi = {
  users: () => apiFetch<import("@/types").AdminUser[]>("/api/admin/users"),
  updateUser: (
    id: string,
    body: { name?: string; role?: "user" | "superadmin"; is_active?: boolean; email_verified?: boolean },
  ) =>
    apiFetch<import("@/types").AdminUser>(`/api/admin/users/${id}`, {
      method: "PATCH",
      headers: authHeaders(),
      body: JSON.stringify(body),
    }),
  deleteUser: (id: string) =>
    apiFetch<{ message: string }>(`/api/admin/users/${id}`, {
      method: "DELETE",
      headers: authHeaders(),
    }),
  forceVerify: (id: string) =>
    apiFetch<import("@/types").AdminUser>(`/api/admin/users/${id}/force-verify`, {
      method: "POST",
      headers: authHeaders(),
    }),
  resendReset: (id: string) =>
    apiFetch<{ message: string; reset_link?: string | null }>(`/api/admin/users/${id}/resend-reset`, {
      method: "POST",
      headers: authHeaders(),
    }),
  resendVerification: (id: string) =>
    apiFetch<{ message: string; verification_link?: string | null }>(
      `/api/admin/users/${id}/resend-verification`,
      {
        method: "POST",
        headers: authHeaders(),
      },
    ),
  sessions: () => apiFetch<import("@/types").AdminSession[]>("/api/admin/sessions"),
  jobs: () => apiFetch<import("@/types").AdminJob[]>("/api/admin/jobs"),
  funnel: () => apiFetch<import("@/types").FunnelStats>("/api/admin/funnel"),
  audit: (params?: { action?: string; q?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.action) q.set("action", params.action);
    if (params?.q) q.set("q", params.q);
    if (params?.limit) q.set("limit", String(params.limit));
    const qs = q.toString();
    return apiFetch<import("@/types").AuditEvent[]>(`/api/admin/audit${qs ? `?${qs}` : ""}`);
  },
};

export async function submitMapping(jobId: string, columnToCanonical: Record<string, string>) {
  return apiFetch<{ job_id: string; state: string }>("/api/mapping", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId, column_to_canonical: columnToCanonical }),
  });
}

export async function submitPlantConfig(payload: PlantConfigInput) {
  return apiFetch<{ job_id: string; state: string }>("/api/plant-config", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function detectEquipment(jobId: string, columnToCanonical: Record<string, string>) {
  return apiFetch<DetectEquipmentResponse>("/api/detect-equipment", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId, column_to_canonical: columnToCanonical }),
  });
}

export function architectureTemplateUrl() {
  return `${BASE_URL}/api/architecture-template`;
}

/** Official Complete Analysis Pack — Excel (README + scada + architecture). */
export function completeAnalysisTemplateUrl() {
  return `${BASE_URL}/api/templates/complete-analysis`;
}

/** Same pack as ZIP of CSV + architecture Excel (for CSV-first clients). */
export function completeAnalysisZipUrl() {
  return `${BASE_URL}/api/templates/complete-analysis.zip`;
}

/** Download a gated template with session cookies (avoids bare <a href> 401). */
export async function downloadAuthenticated(url: string, filename: string) {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    let message = `Download failed (${res.status})`;
    try {
      const body = await res.json();
      message = body.detail || message;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, message);
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export async function uploadArchitectureExcel(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<import("@/types").ArchitectureUploadResponse>("/api/architecture-upload", {
    method: "POST",
    body: form,
    headers: (() => {
      const h: Record<string, string> = {};
      const csrf = getCsrfToken();
      if (csrf) h["X-CSRF-Token"] = csrf;
      return h;
    })(),
  });
}

export async function applyArchitecturePattern(payload: {
  inverter_ids: string[];
  smbs_per_inverter: number;
  strings_per_smb: number;
  rated_kw?: number | null;
  existing_inverters?: unknown[];
}) {
  return apiFetch<{ inverters: unknown[]; notes: string[] }>("/api/architecture-pattern", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getSetupContext(jobId: string) {
  return apiFetch<SetupContextResponse>(`/api/jobs/${jobId}/setup-context`);
}

export async function getValidation(jobId: string) {
  return apiFetch<ValidationResponse>(`/api/jobs/${jobId}/validation`);
}

export async function retryValidation(jobId: string, dropUnparseableTimestamps = false) {
  return apiFetch<{ job_id: string; state: string }>(`/api/jobs/${jobId}/retry-validation`, {
    method: "POST",
    body: JSON.stringify({ job_id: jobId, drop_unparseable_timestamps: dropUnparseableTimestamps }),
  });
}

export async function acknowledgeWarnings(jobId: string, dropUnparseableTimestamps = false) {
  return apiFetch<{ job_id: string; state: string }>(`/api/jobs/${jobId}/acknowledge`, {
    method: "POST",
    body: JSON.stringify({
      job_id: jobId,
      acknowledged: true,
      drop_unparseable_timestamps: dropUnparseableTimestamps,
    }),
  });
}

export async function getJobStatus(jobId: string) {
  return apiFetch<JobStatusResponse>(`/api/jobs/${jobId}/status`);
}

export async function getResults(jobId: string) {
  return apiFetch<ResultsResponse>(`/api/jobs/${jobId}/results`);
}

export async function startDemo() {
  return apiFetch<{ job_id: string; state: string }>("/api/demo", { method: "POST" });
}

export function reportUrl(jobId: string, format: "pdf" | "xlsx") {
  return `${BASE_URL}/api/jobs/${jobId}/report.${format}`;
}

export async function getDataPreview(
  jobId: string,
  offset = 0,
  limit = 100,
  opts?: { start?: string | null; end?: string | null },
) {
  const q = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (opts?.start) q.set("start", opts.start);
  if (opts?.end) q.set("end", opts.end);
  return apiFetch<import("@/types").DataPreviewResponse>(`/api/jobs/${jobId}/data-preview?${q}`);
}

export function dataExportUrl(jobId: string, opts?: { start?: string | null; end?: string | null }) {
  const q = new URLSearchParams();
  if (opts?.start) q.set("start", opts.start);
  if (opts?.end) q.set("end", opts.end);
  const qs = q.toString();
  return `${BASE_URL}/api/jobs/${jobId}/data-export.csv${qs ? `?${qs}` : ""}`;
}

export async function getArchitectureView(jobId: string) {
  return apiFetch<import("@/types").ArchitectureViewResponse>(`/api/jobs/${jobId}/architecture-view`);
}

export async function getExplorerEquipment(jobId: string, level: string) {
  return apiFetch<{ level: string; equipment_ids: string[] }>(
    `/api/jobs/${jobId}/explorer/equipment?level=${encodeURIComponent(level)}`,
  );
}

export async function getExplorerSignals(jobId: string, level: string) {
  return apiFetch<{ level: string; signals: { id: string; label: string }[] }>(
    `/api/jobs/${jobId}/explorer/signals?level=${encodeURIComponent(level)}`,
  );
}

export async function getExplorerTimeseries(
  jobId: string,
  equipmentIds: string[],
  signals: string[],
  opts?: { start?: string | null; end?: string | null; maxPoints?: number },
) {
  const q = new URLSearchParams({
    equipment_ids: equipmentIds.join(","),
    signals: signals.join(","),
  });
  if (opts?.start) q.set("start", opts.start);
  if (opts?.end) q.set("end", opts.end);
  if (opts?.maxPoints) q.set("max_points", String(opts.maxPoints));
  return apiFetch<import("@/types").TimeseriesResponse>(`/api/jobs/${jobId}/explorer/timeseries?${q}`);
}

export async function appendUpload(jobId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<{ job_id: string; row_count: number; sources: string[] }>(`/api/jobs/${jobId}/append-upload`, {
    method: "POST",
    body: form,
    headers: (() => {
      const h: Record<string, string> = {};
      const csrf = getCsrfToken();
      if (csrf) h["X-CSRF-Token"] = csrf;
      return h;
    })(),
  });
}

export { BASE_URL };
