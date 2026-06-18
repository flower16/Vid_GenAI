import axios from "axios";

export const api = axios.create({ baseURL: "http://localhost:8000" });

// Attach JWT when present.
api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

// On 401 (expired/invalid token), drop it and reload to the login gate.
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token");
      if (!location.pathname.includes("login")) location.reload();
    }
    return Promise.reject(err);
  },
);

// ---- Auth ----
export async function register(email, password) {
  const { data } = await api.post("/auth/register", { email, password });
  localStorage.setItem("token", data.access_token);
  return data;
}

export async function login(email, password) {
  // OAuth2 password flow expects form-encoded "username"/"password".
  const form = new URLSearchParams();
  form.append("username", email);
  form.append("password", password);
  const { data } = await api.post("/auth/login", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  localStorage.setItem("token", data.access_token);
  return data;
}

export function logout() {
  localStorage.removeItem("token");
}

export function isAuthed() {
  return Boolean(localStorage.getItem("token"));
}

export async function startCompare(intake) {
  const { data } = await api.post("/compare", intake);
  return data.job_id;
}

export async function getResult(jobId) {
  const { data } = await api.get(`/compare/${jobId}`);
  return data;
}

export async function routeAgent(request, extra = {}) {
  const { data } = await api.post("/agent/route", { request, ...extra });
  return data; // {domain, status, result|detail|how_to_enable}
}

export async function getHistory() {
  const { data } = await api.get("/compare/history");
  return data; // [{job_id, status, created_at, best_provider, best_plan, best_annual}]
}

export async function listFiles() {
  const { data } = await api.get("/files");
  return data; // [{file_id, kind, original_name, parse_status, created_at}]
}

// Upload a bill PDF or solar/SMT CSV. kind: "bill" | "solar" | "smt".
// Returns { file_id, preview, ... } — pass file_id into startCompare.
export async function uploadFile(kind, file) {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await api.post(`/files/${kind}`, fd);
  return data;
}

export async function ingestPdf(file, meta) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("document_type", meta.documentType);
  if (meta.provider) fd.append("provider_name", meta.provider);
  if (meta.planName) fd.append("plan_name", meta.planName);
  const { data } = await api.post("/rag/ingest", fd);
  return data; // {status: 'complete' | 'skipped_duplicate', document_id, ...}
}
