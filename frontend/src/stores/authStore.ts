/**
 * Vitar v11 — Auth Store (Zustand)
 *
 * Key changes from v10:
 *   - No localStorage token persistence — tokens live in httpOnly cookies.
 *   - csrfManager stores the CSRF token in memory; it's set from each
 *     login/register/refresh response and sent as X-CSRF-Token header.
 *   - The Zustand persist middleware still saves user + clinic profile
 *     (non-sensitive data) for instant UI restoration after page reload.
 *     On reload, the app re-validates the session via /auth/me before
 *     treating the user as authenticated.
 *   - logout() calls POST /auth/logout so the server revokes the refresh
 *     token in the DB and clears server-side cookies.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { csrfManager } from '@/lib/api/client';
import { authApi, clinicsApi } from '@/lib/api/services';
import api from '@/lib/api/client';

interface User {
  id: string;
  email: string;
  full_name: string;
}

interface Clinic {
  id: string;
  name: string;
  slug: string;
  country: string;
  currency: string;
  trial_ends_at: string | null;
  onboarding_completed: boolean;
  onboarding_step: number;
  trial?: {
    is_trial: boolean;
    days_left: number;
    bookings_used: number;
    bookings_left: number;
    bookings_limit: number;
    show_upgrade_nudge: boolean;
    is_expired: boolean;
  };
}

interface AuthState {
  user: User | null;
  clinic: Clinic | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  sessionChecked: boolean;   // true once we've validated session on mount

  login: (email: string, password: string) => Promise<void>;
  register: (data: {
    full_name: string; email: string; password: string;
    phone: string; clinic_name: string; city: string; country: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  refreshClinic: () => Promise<void>;
  setClinic: (clinic: Clinic) => void;
  validateSession: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      clinic: null,
      isAuthenticated: false,
      isLoading: false,
      sessionChecked: false,

      login: async (email, password) => {
        set({ isLoading: true });
        try {
          const data = await authApi.login(email, password);
          // Server sets httpOnly cookies; we only handle the CSRF token
          csrfManager.set(data.csrf_token);
          set({
            user: data.user,
            clinic: data.clinic,
            isAuthenticated: true,
            isLoading: false,
            sessionChecked: true,
          });
        } catch (err) {
          set({ isLoading: false });
          throw err;
        }
      },

      register: async (formData) => {
        set({ isLoading: true });
        try {
          const data = await authApi.register(formData);
          csrfManager.set(data.csrf_token);
          set({
            user: data.user,
            clinic: data.clinic,
            isAuthenticated: true,
            isLoading: false,
            sessionChecked: true,
          });
        } catch (err) {
          set({ isLoading: false });
          throw err;
        }
      },

      logout: async () => {
        try {
          // Server revokes refresh token in DB and clears cookies
          await api.post('/auth/logout');
        } catch {
          // Ignore errors — clear local state regardless
        }
        csrfManager.clear();
        set({ user: null, clinic: null, isAuthenticated: false, sessionChecked: true });
      },

      refreshClinic: async () => {
        try {
          const data = await clinicsApi.getMe();
          set({ clinic: data });
        } catch {
          // Silently fail
        }
      },

      setClinic: (clinic) => set({ clinic }),

      /**
       * Called on app mount to validate the existing session.
       * If the httpOnly access cookie is still valid, the API call succeeds
       * and we restore isAuthenticated. If not, the axios interceptor
       * attempts a silent cookie refresh automatically.
       */
      validateSession: async () => {
        const { user } = get();
        if (!user) {
          set({ sessionChecked: true });
          return;
        }
        try {
          const clinic = await clinicsApi.getMe();
          set({ isAuthenticated: true, clinic, sessionChecked: true });
        } catch {
          // Session invalid — clean up local state
          csrfManager.clear();
          set({ user: null, clinic: null, isAuthenticated: false, sessionChecked: true });
        }
      },
    }),
    {
      name: 'vitar_auth',
      // Only persist non-sensitive profile data — no tokens
      partialize: (state) => ({
        user: state.user,
        clinic: state.clinic,
        // isAuthenticated is NOT persisted — it's re-validated on mount
      }),
    }
  )
);
