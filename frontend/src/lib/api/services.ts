/**
 * Vitar v5 - API Services
 * All backend calls organised by domain
 */

import api from './client';

// ── Auth ──────────────────────────────────────────────────────────────────────

export const authApi = {
  register: (data: {
    full_name: string; email: string; password: string;
    phone: string; clinic_name: string; city: string; country: string;
  }) => api.post('/auth/register', data).then(r => r.data),

  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }).then(r => r.data),

  // v11: refresh token is sent automatically via httpOnly cookie — no body param needed.
  refresh: () =>
    api.post('/auth/refresh').then(r => r.data),

  forgotPassword: (email: string) =>
    api.post('/auth/forgot-password', { email }).then(r => r.data),

  resetPassword: (token: string, new_password: string) =>
    api.post('/auth/reset-password', { token, new_password }).then(r => r.data),

  // v12: session-restore that works for clinic owners AND superadmin-only
  // accounts with no clinic. Used by authStore.validateSession() on mount.
  me: () => api.get('/auth/me').then(r => r.data),
};

// ── Clinics ───────────────────────────────────────────────────────────────────

export const clinicsApi = {
  getMe: () => api.get('/clinics/me').then(r => r.data),
  update: (data: Record<string, unknown>) => api.patch('/clinics/me', data).then(r => r.data),
};

// ── Doctors ───────────────────────────────────────────────────────────────────

export const doctorsApi = {
  list: () => api.get('/doctors/').then(r => r.data),
  create: (data: Record<string, unknown>) => api.post('/doctors/', data).then(r => r.data),
  get: (id: string) => api.get(`/doctors/${id}`).then(r => r.data),
  update: (id: string, data: Record<string, unknown>) => api.patch(`/doctors/${id}`, data).then(r => r.data),
  delete: (id: string) => api.delete(`/doctors/${id}`).then(r => r.data),
  setAvailability: (id: string, slots: unknown[]) => api.put(`/doctors/${id}/availability`, slots).then(r => r.data),
  getAvailableSlots: (id: string, date: string) =>
    api.get(`/doctors/${id}/available-slots`, { params: { date } }).then(r => r.data),
  blockTime: (id: string, data: Record<string, unknown>) =>
    api.post(`/doctors/${id}/block-time`, data).then(r => r.data),
};

// ── Patients ──────────────────────────────────────────────────────────────────

export const patientsApi = {
  list: (params?: { search?: string; page?: number; limit?: number }) =>
    api.get('/patients/', { params }).then(r => r.data),
  create: (data: Record<string, unknown>) => api.post('/patients/', data).then(r => r.data),
  get: (id: string) => api.get(`/patients/${id}`).then(r => r.data),
  update: (id: string, data: Record<string, unknown>) => api.patch(`/patients/${id}`, data).then(r => r.data),
};

// ── Appointments ──────────────────────────────────────────────────────────────

export const appointmentsApi = {
  list: (params?: {
    status?: string; doctor_id?: string; patient_id?: string;
    date_from?: string; date_to?: string; page?: number; limit?: number;
  }) => api.get('/appointments/', { params }).then(r => r.data),

  create: (data: Record<string, unknown>) => api.post('/appointments/', data).then(r => r.data),
  get: (id: string) => api.get(`/appointments/${id}`).then(r => r.data),
  update: (id: string, data: Record<string, unknown>) => api.patch(`/appointments/${id}`, data).then(r => r.data),
  reschedule: (id: string, data: { new_scheduled_at: string; reason?: string }) =>
    api.post(`/appointments/${id}/reschedule`, data).then(r => r.data),
  cancel: (id: string, reason?: string) =>
    api.delete(`/appointments/${id}`, { params: { reason } }).then(r => r.data),
};

// ── Analytics ─────────────────────────────────────────────────────────────────

export const analyticsApi = {
  dashboard: () => api.get('/analytics/dashboard').then(r => r.data),
  summary: () => api.get('/analytics/summary').then(r => r.data),
};

// ── AI ────────────────────────────────────────────────────────────────────────

export const aiApi = {
  riskDashboard: () => api.get('/ai/risk-dashboard').then(r => r.data),
  predict: (appointment_id: string) => api.post(`/ai/predict/${appointment_id}`).then(r => r.data),
  noShowTrends: (months?: number) =>
    api.get('/ai/no-show-trends', { params: { months } }).then(r => r.data),
  chat: (message: string, history: unknown[]) =>
    api.post('/ai/chatbot', { message, conversation_history: history }).then(r => r.data),
};

// ── Billing ───────────────────────────────────────────────────────────────────

export const billingApi = {
  getPlans: (currency: string) =>
    api.get('/billing/plans', { params: { currency } }).then(r => r.data),
  getSubscription: () => api.get('/billing/subscription').then(r => r.data),
  subscribe: (plan: string, billing_cycle: string) =>
    api.post('/billing/subscribe', { plan, billing_cycle }).then(r => r.data),
  cancel: () => api.post('/billing/cancel').then(r => r.data),
  getBanks: () => api.get('/billing/banks').then(r => r.data),
  setupSubaccount: (bank_code: string, account_number: string) =>
    api.post('/billing/setup-subaccount', { bank_code, account_number }).then(r => r.data),
};

// ── Geo ───────────────────────────────────────────────────────────────────────

export const geoApi = {
  detect: () => api.get('/geo/detect').then(r => r.data),
  getPlansByCurrency: (currency: string) =>
    api.get(`/geo/plans/${currency}`).then(r => r.data),
};

// ── Notifications ─────────────────────────────────────────────────────────────

export const notificationsApi = {
  getSettings: () => api.get('/notifications/').then(r => r.data),
  updateSettings: (data: Record<string, unknown>) => api.patch('/notifications/', data).then(r => r.data),
};

// ── Onboarding ────────────────────────────────────────────────────────────────

export const onboardingApi = {
  getStatus: () => api.get('/onboarding/status').then(r => r.data),
  completeStep: (step: number, data?: Record<string, unknown>) =>
    api.post('/onboarding/complete-step', { step, data }).then(r => r.data),
};

// ── Waiting List ──────────────────────────────────────────────────────────────

export const waitingListApi = {
  list: () => api.get('/waiting-list/').then(r => r.data),
  remove: (id: string) => api.delete(`/waiting-list/${id}`).then(r => r.data),
};

// ── Public Booking ────────────────────────────────────────────────────────────

export const bookingApi = {
  getClinic: (slug: string) => api.get(`/booking/clinic/${slug}`).then(r => r.data),
  book: (slug: string, data: Record<string, unknown>) =>
    api.post(`/booking/clinic/${slug}/book`, data).then(r => r.data),
  confirm: (token: string) => api.get(`/booking/confirm/${token}`).then(r => r.data),
  getCancelPage: (token: string) => api.get(`/booking/cancel/${token}`).then(r => r.data),
  cancelByToken: (token: string) => api.post(`/booking/cancel/${token}`).then(r => r.data),
  joinWaitlist: (slug: string, data: Record<string, unknown>) =>
    api.post(`/booking/clinic/${slug}/waitlist`, data).then(r => r.data),
  // Hospital portal (QR scan flow)
  getPortal: (slug: string) => api.get(`/booking/clinic/${slug}/portal`).then(r => r.data),
  registerPatient: (slug: string, data: { full_name: string; phone: string; email?: string }) =>
    api.post(`/booking/clinic/${slug}/register-patient`, data).then(r => r.data),
};

// ── Admin Dashboard (superadmin only — see app/core/security.get_current_superadmin) ──

export const adminApi = {
  users: {
    list: (params?: {
      search?: string; role?: string; status?: string;
      sort_by?: string; sort_dir?: string; page?: number; limit?: number;
    }) => api.get('/admin/users/', { params }).then(r => r.data),
    get: (id: string) => api.get(`/admin/users/${id}`).then(r => r.data),
    updateRole: (id: string, is_superadmin: boolean, reason?: string) =>
      api.patch(`/admin/users/${id}/role`, { is_superadmin, reason }).then(r => r.data),
    updateStatus: (id: string, is_active: boolean, reason?: string) =>
      api.patch(`/admin/users/${id}/status`, { is_active, reason }).then(r => r.data),
    // Convenience: grant a user free access by finding their clinic then applying an override
    // Resolves via admin/users/{id} → clinic_id → admin/subscriptions/{clinic_id}/override
    grantFreeAccess: async (userId: string, plan: string = 'pro', reason?: string) => {
      const user = await api.get(`/admin/users/${userId}`).then(r => r.data);
      if (!user.clinic_id) throw new Error('This user has no clinic yet');
      return api.post(`/admin/subscriptions/${user.clinic_id}/override`, {
        action: 'grant_free',
        plan,
        reason: reason ?? 'Admin granted free access',
        notes: `Granted via user management panel for user ${userId}`,
      }).then(r => r.data);
    },
  },

  clinics: {
    list: (params?: { search?: string; status?: string; page?: number; limit?: number }) =>
      api.get('/admin/clinics/', { params }).then(r => r.data),
    get: (id: string) => api.get(`/admin/clinics/${id}`).then(r => r.data),
    updateStatus: (id: string, is_active: boolean, reason?: string) =>
      api.patch(`/admin/clinics/${id}/status`, { is_active, reason }).then(r => r.data),
    regenerateQr: (id: string) => api.post(`/admin/clinics/${id}/regenerate-qr`).then(r => r.data),
  },

  subscriptions: {
    list: (params?: { search?: string; plan?: string; status?: string; page?: number; limit?: number }) =>
      api.get('/admin/subscriptions/', { params }).then(r => r.data),
    get: (clinicId: string) => api.get(`/admin/subscriptions/${clinicId}`).then(r => r.data),
    override: (clinicId: string, data: {
      action: 'grant_free' | 'grant_temporary' | 'grant_lifetime' | 'extend' | 'set_expiration' | 'revoke';
      plan?: string; duration_days?: number; expiration_date?: string;
      notes?: string; reason?: string;
    }) => api.post(`/admin/subscriptions/${clinicId}/override`, data).then(r => r.data),
  },

  analytics: {
    overview: () => api.get('/admin/analytics/overview').then(r => r.data),
    business: () => api.get('/admin/analytics/business').then(r => r.data),
    exportCsvUrl: () => `${api.defaults.baseURL}/admin/analytics/export.csv`,
  },

  auditLogs: {
    list: (params?: { entity_type?: string; entity_id?: string; clinic_id?: string; action?: string; page?: number; limit?: number }) =>
      api.get('/admin/audit-logs/', { params }).then(r => r.data),
  },
};
