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
};
