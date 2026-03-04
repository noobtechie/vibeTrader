import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 — redirect to login
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("access_token");
      window.location.href = "/connect";
    }
    return Promise.reject(error);
  }
);

// ─── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  register: (email: string, password: string) =>
    api.post("/auth/register", { email, password }),
  login: (email: string, password: string) =>
    api.post("/auth/login", { email, password }),
  me: () => api.get("/auth/me"),
};

// ─── Brokerage ─────────────────────────────────────────────────────────────────
export const brokerageApi = {
  status: () => api.get("/brokerage/status"),
  connectQuestrade: (refreshToken: string) =>
    api.post("/brokerage/connect/questrade", { refresh_token: refreshToken }),
  disconnect: () => api.delete("/brokerage/disconnect"),
  accounts: () => api.get("/brokerage/accounts"),
  positions: (accountId: string) =>
    api.get(`/brokerage/accounts/${accountId}/positions`),
  balances: (accountId: string) =>
    api.get(`/brokerage/accounts/${accountId}/balances`),
  orders: (accountId: string) =>
    api.get(`/brokerage/accounts/${accountId}/orders`),
  quotes: (symbols: string) =>
    api.get(`/brokerage/quotes?symbols=${symbols}`),
  searchSymbols: (query: string) =>
    api.get(`/brokerage/symbols/search?query=${query}`),
  optionChain: (symbol: string, expiryDate?: string) =>
    api.get(`/brokerage/symbols/${symbol}/options${expiryDate ? `?expiry_date=${expiryDate}` : ""}`),
  candles: (symbolId: number, start: string, end: string, interval = "1d") =>
    api.get(`/brokerage/candles/${symbolId}?start_time=${start}&end_time=${end}&interval=${interval}`),
};

// ─── Risk ──────────────────────────────────────────────────────────────────────
export const riskApi = {
  getSettings: () => api.get("/risk/settings"),
  updateSettings: (data: object) => api.put("/risk/settings", data),
  getEvents: () => api.get("/risk/events"),
  resetCircuitBreaker: () => api.post("/risk/circuit-breaker/reset"),
};

// ─── Playbook / Strategies ─────────────────────────────────────────────────────
export const playbookApi = {
  list: () => api.get("/strategies/playbooks"),
  get: (id: string) => api.get(`/strategies/playbooks/${id}`),
  create: (data: object) => api.post("/strategies/playbooks", data),
  update: (id: string, data: object) => api.put(`/strategies/playbooks/${id}`, data),
  delete: (id: string) => api.delete(`/strategies/playbooks/${id}`),
  getStrategies: (playbookId: string) => api.get(`/strategies/playbooks/${playbookId}/strategies`),
  createStrategy: (playbookId: string, data: object) =>
    api.post(`/strategies/playbooks/${playbookId}/strategies`, data),
  updateStrategy: (id: string, data: object) => api.put(`/strategies/${id}`, data),
};

// ─── Journal ───────────────────────────────────────────────────────────────────
export const journalApi = {
  list: (params?: object) => api.get("/journal/entries", { params }),
  get: (id: string) => api.get(`/journal/entries/${id}`),
  create: (data: object) => api.post("/journal/entries", data),
  update: (id: string, data: object) => api.put(`/journal/entries/${id}`, data),
  delete: (id: string) => api.delete(`/journal/entries/${id}`),
  analytics: () => api.get("/journal/analytics"),
  exportCsv: () => api.get("/journal/export/csv", { responseType: "blob" }),
};

// ─── Backtesting ───────────────────────────────────────────────────────────────
export const backtestApi = {
  run: (data: object) => api.post("/backtest/run", data),
  getResult: (id: string) => api.get(`/backtest/${id}`),
  list: () => api.get("/backtest/list"),
};

// ─── Automation ────────────────────────────────────────────────────────────────
export const automationApi = {
  status: () => api.get("/automation/status"),
  signals: () => api.get("/automation/signals"),
  confirmSignal: (signalId: string) => api.post(`/automation/signals/${signalId}/confirm`),
  rejectSignal: (signalId: string) => api.post(`/automation/signals/${signalId}/reject`),
};

// ─── Dashboard ─────────────────────────────────────────────────────────────────
export const dashboardApi = {
  get: () => api.get("/dashboard"),
};
