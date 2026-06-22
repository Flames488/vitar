/**
 * Vitar v5 - App Router
 */

import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';

import { useAuthStore } from '@/stores/authStore';
import { useGeoStore } from '@/stores/geoStore';

// Layouts
import DashboardLayout from '@/layouts/DashboardLayout';
import MarketingLayout from '@/layouts/MarketingLayout';
import AuthLayout from '@/layouts/AuthLayout';

// Marketing
import LandingPage from '@/pages/marketing/LandingPage';
import PricingPage from '@/pages/marketing/PricingPage';

// Auth
import LoginPage from '@/pages/auth/LoginPage';
import RegisterPage from '@/pages/auth/RegisterPage';
import ForgotPasswordPage from '@/pages/auth/ForgotPasswordPage';
import ResetPasswordPage from '@/pages/auth/ResetPasswordPage';

// Onboarding
import OnboardingPage from '@/pages/onboarding/OnboardingPage';

// Dashboard
import DashboardPage from '@/pages/dashboard/DashboardPage';
import AppointmentsPage from '@/pages/dashboard/AppointmentsPage';
import AppointmentDetailPage from '@/pages/dashboard/AppointmentDetailPage';
import NewAppointmentPage from '@/pages/dashboard/NewAppointmentPage';
import DoctorsPage from '@/pages/dashboard/DoctorsPage';
import DoctorDetailPage from '@/pages/dashboard/DoctorDetailPage';
import NewDoctorPage from '@/pages/dashboard/NewDoctorPage';
import PatientsPage from '@/pages/dashboard/PatientsPage';
import PatientDetailPage from '@/pages/dashboard/PatientDetailPage';
import AnalyticsPage from '@/pages/dashboard/AnalyticsPage';
import EarningsPage from '@/pages/dashboard/EarningsPage';
import AIRiskPage from '@/pages/dashboard/AIRiskPage';
import WaitingListPage from '@/pages/dashboard/WaitingListPage';

// Settings
import SettingsPage from '@/pages/settings/SettingsPage';
import BillingPage from '@/pages/settings/BillingPage';
import NotificationSettingsPage from '@/pages/settings/NotificationSettingsPage';
import BookingPageSettings from '@/pages/settings/BookingPageSettings';
import ApiKeysPage from '@/pages/admin/ApiKeys';
import QrCodeSettings from '@/pages/QrCodeSettings';

// Superadmin Dashboard (/admin/*) — distinct from pages/admin/ApiKeys above,
// which is clinic-level settings, not the platform superadmin control panel.
import AdminLayout from '@/layouts/AdminLayout';
import AdminOverviewPage from '@/pages/superadmin/OverviewPage';
import AdminUsersPage from '@/pages/superadmin/UsersPage';
import AdminClinicsPage from '@/pages/superadmin/ClinicsPage';
import AdminSubscriptionsPage from '@/pages/superadmin/SubscriptionsPage';
import AdminAnalyticsPage from '@/pages/superadmin/AnalyticsPage';
import AdminAuditLogPage from '@/pages/superadmin/AuditLogPage';

// Public Booking
import PublicBookingPage from '@/pages/booking/PublicBookingPage';
import BookingConfirmationPage from '@/pages/booking/BookingConfirmationPage';
import CancelAppointmentPage from '@/pages/booking/CancelAppointmentPage';
import Portal from '@/pages/Portal';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

// ── Protected Route ───────────────────────────────────────────────────────────

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const sessionChecked = useAuthStore((s) => s.sessionChecked);
  // Wait for validateSession() to finish before deciding — avoids bouncing
  // authenticated users to /login on every hard refresh (isAuthenticated is
  // not persisted to localStorage; sessionChecked is the gate).
  if (!sessionChecked) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

// ── Onboarding Guard ──────────────────────────────────────────────────────────

function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const clinic = useAuthStore((s) => s.clinic);
  if (clinic && !clinic.onboarding_completed) {
    return <Navigate to="/onboarding" replace />;
  }
  return <>{children}</>;
}

// ── Superadmin Guard ──────────────────────────────────────────────────────────
// Frontend gate is a UX nicety only — every /admin/* API call is independently
// enforced server-side via get_current_superadmin (app/core/security.py).

function SuperadminRoute({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const sessionChecked = useAuthStore((s) => s.sessionChecked);
  if (!sessionChecked) return null; // wait for validateSession() before deciding
  if (!user?.is_superadmin) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

// ── Superadmin-only Login Redirect ────────────────────────────────────────────
// Superadmin accounts with no clinic must land on /admin, not /dashboard.
// Without this they'd be sent to /dashboard, which calls clinicsApi.getMe()
// (404), then OnboardingGuard would loop them to /onboarding, which also 404s.

function AdminOrDashboard() {
  const user = useAuthStore((s) => s.user);
  const clinic = useAuthStore((s) => s.clinic);
  if (user?.is_superadmin && !clinic) return <Navigate to="/admin/overview" replace />;
  return <Navigate to="/dashboard" replace />;
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const detect = useGeoStore((s) => s.detect);
  const validateSession = useAuthStore((s) => s.validateSession);

  useEffect(() => {
    detect();
    // v12 FIX: validateSession existed but was never called — isAuthenticated
    // wasn't persisted, so every hard refresh bounced everyone to /login even
    // with a valid session cookie. This restores the session (and works for
    // superadmin-only accounts with no clinic, via /auth/me).
    validateSession();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* ── Public Marketing ──────────────────────────────────────── */}
          <Route element={<MarketingLayout />}>
            <Route path="/" element={<LandingPage />} />
            <Route path="/pricing" element={<PricingPage />} />
          </Route>

          {/* ── Auth ──────────────────────────────────────────────────── */}
          <Route element={<AuthLayout />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
          </Route>

          {/* ── Public Booking (no auth) ───────────────────────────────── */}
          <Route path="/book/:slug" element={<PublicBookingPage />} />
          {/* /portal/:slug — QR scan landing page (patient self-registration) */}
          <Route path="/portal/:slug" element={<Portal />} />
          <Route path="/confirm/:token" element={<BookingConfirmationPage />} />
          <Route path="/cancel/:token" element={<CancelAppointmentPage />} />

          {/* ── Onboarding ────────────────────────────────────────────── */}
          <Route
            path="/onboarding"
            element={
              <ProtectedRoute>
                <OnboardingPage />
              </ProtectedRoute>
            }
          />

          {/* ── Dashboard ─────────────────────────────────────────────── */}
          <Route
            element={
              <ProtectedRoute>
                <OnboardingGuard>
                  <DashboardLayout />
                </OnboardingGuard>
              </ProtectedRoute>
            }
          >
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/appointments" element={<AppointmentsPage />} />
            <Route path="/appointments/new" element={<NewAppointmentPage />} />
            <Route path="/appointments/:id" element={<AppointmentDetailPage />} />
            <Route path="/doctors" element={<DoctorsPage />} />
            <Route path="/doctors/new" element={<NewDoctorPage />} />
            <Route path="/doctors/:id" element={<DoctorDetailPage />} />
            <Route path="/patients" element={<PatientsPage />} />
            <Route path="/patients/:id" element={<PatientDetailPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/earnings" element={<EarningsPage />} />
            <Route path="/ai-risk" element={<AIRiskPage />} />
            <Route path="/waiting-list" element={<WaitingListPage />} />

            {/* Settings */}
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/settings/billing" element={<BillingPage />} />
            <Route path="/settings/notifications" element={<NotificationSettingsPage />} />
            <Route path="/settings/booking-page" element={<BookingPageSettings />} />
            <Route path="/settings/api-keys" element={<ApiKeysPage />} />
            <Route path="/settings/qr-code" element={<QrCodeSettings />} />
          </Route>

          {/* ── Superadmin Dashboard ──────────────────────────────────── */}
          <Route
            element={
              <ProtectedRoute>
                <SuperadminRoute>
                  <AdminLayout />
                </SuperadminRoute>
              </ProtectedRoute>
            }
          >
            <Route path="/admin" element={<Navigate to="/admin/overview" replace />} />
            <Route path="/admin/overview" element={<AdminOverviewPage />} />
            <Route path="/admin/users" element={<AdminUsersPage />} />
            <Route path="/admin/clinics" element={<AdminClinicsPage />} />
            <Route path="/admin/subscriptions" element={<AdminSubscriptionsPage />} />
            <Route path="/admin/analytics" element={<AdminAnalyticsPage />} />
            <Route path="/admin/audit-log" element={<AdminAuditLogPage />} />
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors closeButton />
    </QueryClientProvider>
  );
}
