/**
 * Vitar v12 — API Client (Cookie-based Auth)
 *
 * Changes from v11:
 *   - tokenManager shim removed — no call sites remain; csrfManager is the
 *     sole auth state. Import csrfManager directly if needed.
 *   - Tokens live in httpOnly cookies (XSS-proof); JS cannot read them.
 *   - CSRF token stored in memory, sent as X-CSRF-Token on mutating requests.
 *   - Refresh: POST /auth/refresh with credentials: 'include' — browser sends
 *     the httpOnly refresh cookie automatically.
 *   - On 401: silent cookie refresh, then retry. On refresh failure: /login.
 */

import axios, { AxiosError, type AxiosRequestConfig } from 'axios';

const rawBaseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const BASE_URL = rawBaseUrl.replace(/\/+$/, '').replace(/\/api\/v1$/, '');

// ── CSRF Token Manager (in-memory only) ──────────────────────────────────────
// The CSRF token is returned in the login/register/refresh response body.
// We keep it in memory — it never touches localStorage or a cookie we control.

let _csrfToken: string | null = null;

export const csrfManager = {
  get: (): string | null => _csrfToken,
  set: (token: string): void => { _csrfToken = token; },
  clear: (): void => { _csrfToken = null; },
};

// ── Axios Instance ────────────────────────────────────────────────────────────

export const api = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,   // CRITICAL: send httpOnly cookies on every request
});

// ── Request Interceptor: attach CSRF token ────────────────────────────────────

api.interceptors.request.use((config) => {
  const csrf = csrfManager.get();
  const method = (config.method ?? 'get').toLowerCase();
  const mutating = ['post', 'put', 'patch', 'delete'].includes(method);

  if (csrf && mutating) {
    config.headers['X-CSRF-Token'] = csrf;
  }
  return config;
});

// ── Response Interceptor: handle 401, silent cookie refresh ──────────────────

let isRefreshing = false;
let failedQueue: Array<{ resolve: (v: any) => void; reject: (e: any) => void }> = [];

const processQueue = (error: any) => {
  failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve(null)));
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !originalRequest._retry) {
      // Don't retry the refresh endpoint itself — avoids infinite loop
      if (originalRequest.url?.includes('/auth/refresh')) {
        csrfManager.clear();
        window.location.href = '/login';
        return Promise.reject(error);
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then(() => api(originalRequest)).catch((e) => Promise.reject(e));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // POST to /refresh — browser sends the httpOnly refresh cookie automatically.
        // Server rotates the token and sets fresh cookies in the response.
        const { data } = await axios.post(
          `${BASE_URL}/api/v1/auth/refresh`,
          {},
          {
            withCredentials: true,
            headers: { 'X-CSRF-Token': csrfManager.get() ?? '' },
          }
        );
        // New CSRF token comes back in the response body
        if (data.csrf_token) csrfManager.set(data.csrf_token);

        processQueue(null);
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError);
        csrfManager.clear();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// ── Typed API helpers ─────────────────────────────────────────────────────────

export function getApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    if (typeof data?.detail === 'string') return data.detail;
    if (typeof data?.detail === 'object') return data.detail?.message ?? 'An error occurred';
    if (typeof data?.message === 'string') return data.message;
    if (typeof data?.error === 'string') return data.error;
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return 'An unexpected error occurred';
}

export default api;
