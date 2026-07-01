/**
 * usePageTracking — fires a PostHog $pageview on every route change.
 *
 * Maps raw React Router paths to human-readable page names so PostHog
 * dashboards show "Appointment Detail" not "/appointments/abc123".
 *
 * Usage: call once inside <BrowserRouter>, e.g. in a layout component
 * or directly in App.tsx after the <Routes> block.
 */

import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { trackPage } from '@/lib/analytics'

const PAGE_NAMES: Record<string, string> = {
  '/': 'Landing',
  '/pricing': 'Pricing',
  '/login': 'Login',
  '/register': 'Register',
  '/forgot-password': 'Forgot Password',
  '/reset-password': 'Reset Password',
  '/onboarding': 'Onboarding',
  '/dashboard': 'Dashboard',
  '/appointments': 'Appointments',
  '/appointments/new': 'New Appointment',
  '/doctors': 'Doctors',
  '/doctors/new': 'New Doctor',
  '/patients': 'Patients',
  '/analytics': 'Analytics',
  '/earnings': 'Earnings',
  '/ai-risk': 'AI Risk',
  '/waiting-list': 'Waiting List',
  '/settings': 'Settings',
  '/settings/billing': 'Billing',
  '/settings/notifications': 'Notification Settings',
  '/settings/booking-page': 'Booking Page Settings',
  '/settings/api-keys': 'API Keys',
  '/settings/qr-code': 'QR Code Settings',
  '/admin/overview': 'Admin: Overview',
  '/admin/users': 'Admin: Users',
  '/admin/clinics': 'Admin: Clinics',
  '/admin/subscriptions': 'Admin: Subscriptions',
  '/admin/analytics': 'Admin: Analytics',
  '/admin/audit-log': 'Admin: Audit Log',
}

function resolvePageName(pathname: string): string {
  // Exact match first
  if (PAGE_NAMES[pathname]) return PAGE_NAMES[pathname]

  // Dynamic segments — order matters (most specific first)
  if (/^\/appointments\/.+/.test(pathname)) return 'Appointment Detail'
  if (/^\/doctors\/.+/.test(pathname)) return 'Doctor Detail'
  if (/^\/patients\/.+/.test(pathname)) return 'Patient Detail'
  if (/^\/book\/.+/.test(pathname)) return 'Public Booking'
  if (/^\/portal\/.+/.test(pathname)) return 'Patient Portal'
  if (/^\/confirm\/.+/.test(pathname)) return 'Booking Confirmation'
  if (/^\/cancel\/.+/.test(pathname)) return 'Cancel Appointment'

  return 'Unknown Page'
}

export function usePageTracking() {
  const location = useLocation()

  useEffect(() => {
    const name = resolvePageName(location.pathname)
    trackPage(name, {
      path: location.pathname,
      search: location.search,
    })
  }, [location.pathname, location.search])
}
