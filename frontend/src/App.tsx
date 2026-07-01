/**
 * Vitar — App Router
 * Updated: Sentry user identity + PostHog + PWA install banner
 */

import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import * as Sentry from '@sentry/react';

import { useAuthStore } from '@/stores/authStore';
import { useGeoStore } from '@/stores/geoStore';
import { identifyUser, resetAnalytics } from '@/lib/analytics';
import { usePageTracking } from '@/lib/usePageTracking';
import { setSentryUser, clearSentryUser } from '@/lib/sentry';

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

// Superadmin
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

// PWA
import PWAInstallBanner from '@/components/shared/PWAInstallBanner';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const sessionChecked = useAuthStore((s) => s.sessionChecked);
  if (!sessionChecked) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const clinic = useAuthStore((s) => s.clinic);
  if (clinic && !clinic.onboarding_completed) {
    return <Navigate to="/onboarding" replace />;
  }
  return <>{children}</>;
}

function SuperadminRoute({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const sessionChecked = useAuthStore((s) => s.sessionChecked);
  if (!sessionChecked) return null;
  if (!user?.is_superadmin) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

function AdminOrDashboard() {
  const user = useAuthStore((s) => s.user);
  const clinic = useAuthStore((s) => s.clinic);
  if (user?.is_superadmin && !clinic) return <Navigate to="/admin/overview" replace />;
  return <Navigate to="/dashboard" replace />;
}

function PageTracker() {
  usePageTracking();
  return null;
}

/**
 * AuthObserver — syncs PostHog AND Sentry identity with auth state.
 */
function AuthObserver() {
  const user = useAuthStore((s) => s.user);
  const clinic = useAuthStore((s) => s.clinic);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    if (isAuthenticated && user) {
      // PostHog identity
      identifyUser({
        id: user.id,
        email: user.email,
        full_name: user.full_name,
        is_superadmin: user.is_superadmin,
        clinic_id: clinic?.id,
        clinic_name: clinic?.name,
        clinic_country: clinic?.country,
        clinic_currency: clinic?.currency,
        is_trial: clinic?.trial?.is_trial,
      });
      // Sentry identity
      setSentryUser({ id: user.id, email: user.email, clinic_id: clinic?.id });
    } else if (!isAuthenticated) {
      resetAnalytics();
      clearSentryUser();
    }
  }, [isAuthenticated, user, clinic]);

  return null;
}

// Wrap the whole app in Sentry's ErrorBoundary so crashes are captured
const SentryErrorBoundary = Sentry.withErrorBoundary(
  function AppInner() {
    return (
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <PageTracker />
          <AuthObserver />

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

            {/* ── Public Booking ────────────────────────────────────────── */}
            <Route path="/book/:slug" element={<PublicBookingPage />} />
            <Route path="/portal/:slug" element={<Portal />} />
            <Route path="/confirm/:token" element={<BookingConfirmationPage />} />
            <Route path="/cancel/:token" element={<CancelAppointmentPage />} />

            {/* ── Onboarding ────────────────────────────────────────────── */}
            <Route
              path="/onboarding"
              element={<ProtectedRoute><OnboardingPage /></ProtectedRoute>}
            />

            {/* ── Dashboard ─────────────────────────────────────────────── */}
            <Route
              element={
                <ProtectedRoute>
                  <OnboardingGuard><DashboardLayout /></OnboardingGuard>
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
                  <SuperadminRoute><AdminLayout /></SuperadminRoute>
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

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>

          <PWAInstallBanner />
          <Toaster position="top-right" richColors closeButton />
        </BrowserRouter>
      </QueryClientProvider>
    );
  },
  {
    fallback: (
      <div className="flex h-screen items-center justify-center text-center p-8">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 mb-2">Something went wrong</h1>
          <p className="text-gray-500 mb-4">This error has been reported. Please refresh the page.</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700"
          >
            Refresh
          </button>
        </div>
      </div>
    ),
  },
);

export default function App() {
  const detect = useGeoStore((s) => s.detect);
  const validateSession = useAuthStore((s) => s.validateSession);

  useEffect(() => {
    detect();
    validateSession();
  }, []);

  return <SentryErrorBoundary />;
}
