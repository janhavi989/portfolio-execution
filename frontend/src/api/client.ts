import axios from "axios";

// In Docker: VITE_API_URL is empty → use same-origin "" (nginx proxies /api/ → backend)
// In local dev: VITE_API_URL is not set → use http://localhost:8000 (direct backend)
const API_BASE = import.meta.env.VITE_API_URL !== undefined && import.meta.env.VITE_API_URL !== ""
  ? import.meta.env.VITE_API_URL
  : import.meta.env.DEV
    ? "http://localhost:8000"
    : "";

export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

// Attach JWT token to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 globally
apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// ─── Auth ──────────────────────────────────────────────────────────────────
export const authApi = {
  login: (username: string, password: string) =>
    apiClient.post("/auth/login", { username, password }),
  register: (username: string, email: string, password: string) =>
    apiClient.post("/auth/register", { username, email, password }),
  me: () => apiClient.get("/auth/me"),
};

// ─── Broker ────────────────────────────────────────────────────────────────
export const brokerApi = {
  connect: (data: object) => apiClient.post("/broker/connect", data),
  sessions: () => apiClient.get("/broker/sessions"),
  disconnect: (broker: string) => apiClient.delete(`/broker/disconnect/${broker}`),
  holdings: (broker: string) => apiClient.get(`/broker/holdings/${broker}`),
  supported: () => apiClient.get("/broker/supported"),
  loginUrl: (broker: string, apiKey: string) =>
    apiClient.get(`/broker/login-url/${broker}?api_key=${apiKey}`),
  funds: (broker: string) => apiClient.get(`/broker/funds/${broker}`),
  credentials: (broker: string) => apiClient.get(`/broker/credentials/${broker}`),
  /**
   * Opens an SSE stream that launches a browser for Zerodha semi-auto login.
   * Returns an EventSource — caller listens to `.onmessage` for status events.
   */
  fetchZerodhaToken: (apiKey: string): EventSource => {
    const token = localStorage.getItem("access_token");
    const base = (import.meta.env.VITE_API_URL || "http://localhost:8000") + "/api/v1";
    return new EventSource(
      `${base}/broker/zerodha/fetch-token?api_key=${encodeURIComponent(apiKey)}&token=${encodeURIComponent(token || "")}`,
    );
  },
};

// ─── Execution ─────────────────────────────────────────────────────────────
export const executionApi = {
  execute: (data: object) => apiClient.post("/execution/execute", data),
  validate: (data: object) => apiClient.post("/execution/validate", data),
  batches: () => apiClient.get("/execution/batches"),
  batch: (id: string) => apiClient.get(`/execution/batches/${id}`),
  orders: (batchId?: string) =>
    apiClient.get(`/execution/orders${batchId ? `?batch_id=${batchId}` : ""}`),
};

// ─── System ────────────────────────────────────────────────────────────────
export const systemApi = {
  health: () => axios.get(`${API_BASE}/health`),
};

// ─── WebSocket ─────────────────────────────────────────────────────────────
export const createWebSocket = (userId: string): WebSocket => {
  const wsBase = (import.meta.env.VITE_API_URL || "http://localhost:8000")
    .replace("http://", "ws://")
    .replace("https://", "wss://");
  return new WebSocket(`${wsBase}/ws/${userId}`);
};


