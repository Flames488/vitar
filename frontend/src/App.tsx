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

// Public Booking
import PublicBookingPage from '@/pages/booking/PublicBookingPage';
import BookingConfirmationPage from '@/pages/booking/BookingConfirmationPage';
import CancelAppointmentPage from '@/pages/booking/CancelAppointmentPage';

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

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const detect = useGeoStore((s) => s.detect);
  const refreshClinic = useAuthStore((s) => s.refreshClinic);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    detect();
    if (isAuthenticated) {
      refreshClinic();
    }
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
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors closeButton />
    </QueryClientProvider>
  );
}
