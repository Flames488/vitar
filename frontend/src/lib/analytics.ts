/**
 * Vitar Analytics — PostHog wrapper  (updated: subscription + push events)
 *
 * Usage:
 *   import { analytics } from '@/lib/analytics'
 *   analytics.track('appointment_created', { doctor_id, patient_id })
 *
 * Identity:
 *   Call analytics.identify() right after login/validateSession succeeds.
 *   Call analytics.reset() on logout.
 *
 * All events follow the pattern: noun_verb (e.g. appointment_created)
 * so they're easy to filter in PostHog dashboards.
 */

import posthog from 'posthog-js'

const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_KEY as string
const POSTHOG_HOST = import.meta.env.VITE_POSTHOG_HOST as string ?? 'https://app.posthog.com'

let initialised = false

export function initAnalytics() {
  if (initialised || !POSTHOG_KEY) return

  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    capture_pageview: false,
    respect_dnt: true,
    disable_session_recording: true,
    autocapture: false,
    bootstrap: {
      distinctID: localStorage.getItem('vitar_ph_distinct_id') ?? undefined,
    },
    loaded: (ph) => {
      localStorage.setItem('vitar_ph_distinct_id', ph.get_distinct_id())
    },
  })

  initialised = true
}

// ── Identity ──────────────────────────────────────────────────────────────────

interface UserIdentity {
  id: string
  email: string
  full_name: string
  is_superadmin?: boolean
  clinic_id?: string
  clinic_name?: string
  clinic_country?: string
  clinic_currency?: string
  plan?: string
  is_trial?: boolean
}

export function identifyUser(user: UserIdentity) {
  if (!initialised) return
  posthog.identify(user.id, {
    email: user.email,
    name: user.full_name,
    is_superadmin: user.is_superadmin ?? false,
    clinic_id: user.clinic_id,
    clinic_name: user.clinic_name,
    clinic_country: user.clinic_country,
    clinic_currency: user.clinic_currency,
    plan: user.plan,
    is_trial: user.is_trial,
  })
}

export function resetAnalytics() {
  if (!initialised) return
  posthog.reset()
  localStorage.removeItem('vitar_ph_distinct_id')
}

// ── Page tracking ─────────────────────────────────────────────────────────────

export function trackPage(pageName: string, properties?: Record<string, unknown>) {
  if (!initialised) return
  posthog.capture('$pageview', {
    $current_url: window.location.href,
    page_name: pageName,
    ...properties,
  })
}

// ── Event catalogue ───────────────────────────────────────────────────────────

export const analytics = {
  // ── Auth ──────────────────────────────────────────────────────────
  userRegistered: (props: { clinic_name: string; country: string }) =>
    capture('user_registered', props),

  userLoggedIn: (props: { method?: string }) =>
    capture('user_logged_in', props),

  userLoggedOut: () =>
    capture('user_logged_out', {}),

  passwordResetRequested: () =>
    capture('password_reset_requested', {}),

  // ── Onboarding ────────────────────────────────────────────────────
  onboardingStepCompleted: (props: { step: number; step_name: string }) =>
    capture('onboarding_step_completed', props),

  onboardingCompleted: (props: { clinic_name: string; country: string }) =>
    capture('onboarding_completed', props),

  // ── Appointments ──────────────────────────────────────────────────
  appointmentCreated: (props: {
    doctor_id?: string
    patient_id?: string
    appointment_type?: string
    source?: 'dashboard' | 'public_booking'
  }) => capture('appointment_created', props),

  appointmentCancelled: (props: { appointment_id: string; reason?: string }) =>
    capture('appointment_cancelled', props),

  appointmentConfirmed: (props: { appointment_id: string }) =>
    capture('appointment_confirmed', props),

  // ── Patients ──────────────────────────────────────────────────────
  patientViewed: (props: { patient_id: string }) =>
    capture('patient_viewed', props),

  // ── Doctors ───────────────────────────────────────────────────────
  doctorAdded: (props: { specialty?: string }) =>
    capture('doctor_added', props),

  // ── Public booking ────────────────────────────────────────────────
  publicBookingStarted: (props: { clinic_slug: string }) =>
    capture('public_booking_started', props),

  publicBookingCompleted: (props: { clinic_slug: string; doctor_id?: string }) =>
    capture('public_booking_completed', props),

  publicBookingAbandoned: (props: { clinic_slug: string; step: string }) =>
    capture('public_booking_abandoned', props),

  // ── AI features ───────────────────────────────────────────────────
  aiRiskChecked: (props: { patient_id: string; risk_level?: string }) =>
    capture('ai_risk_checked', props),

  aiChatbotOpened: () =>
    capture('ai_chatbot_opened', {}),

  aiChatbotMessageSent: (props: { session_id?: string }) =>
    capture('ai_chatbot_message_sent', props),

  // ── Billing / Subscription ────────────────────────────────────────
  billingPageViewed: () =>
    capture('billing_page_viewed', {}),

  upgradeClicked: (props: { plan: string; source: string }) =>
    capture('upgrade_clicked', props),

  // trial_started — fired when clinic first sees the trial period begin
  trialStarted: (props: { plan?: string; days?: number }) =>
    capture('trial_started', props),

  // trial_completed — fired when trial period ends (no subscription taken)
  trialCompleted: (props: { days_used?: number }) =>
    capture('trial_completed', props),

  // subscription_started — first time a paying subscription is activated
  subscriptionStarted: (props: { plan: string; currency?: string; amount?: number }) =>
    capture('subscription_started', props),

  // subscription_upgraded — plan change (e.g. starter → growth)
  subscriptionUpgraded: (props: { old_plan: string; new_plan: string }) =>
    capture('subscription_upgraded', props),

  // subscription_cancelled — user-initiated cancellation
  subscriptionCancelled: (props: { plan: string; reason?: string }) =>
    capture('subscription_cancelled', props),

  // payment_failed — charge declined or recurring payment failure
  paymentFailed: (props: { plan?: string; reason?: string }) =>
    capture('payment_failed', props),

  // Legacy alias kept for backward compatibility
  subscriptionActivated: (props: { plan: string }) =>
    capture('subscription_started', props),

  trialExpired: () =>
    capture('trial_completed', {}),

  // ── Settings ──────────────────────────────────────────────────────
  qrCodeViewed: () =>
    capture('qr_code_viewed', {}),

  qrCodeDownloaded: () =>
    capture('qr_code_downloaded', {}),

  apiKeyCreated: () =>
    capture('api_key_created', {}),

  notificationSettingChanged: (props: { setting: string; enabled: boolean }) =>
    capture('notification_setting_changed', props),

  // ── PWA ───────────────────────────────────────────────────────────
  pwaInstallPromptShown: () =>
    capture('pwa_install_prompt_shown', {}),

  pwaInstalled: () =>
    capture('pwa_installed', {}),

  pwaInstallDismissed: () =>
    capture('pwa_install_dismissed', {}),

  // ── Push Notifications ────────────────────────────────────────────
  // appointment_reminder_sent — push notification delivered to browser
  appointmentReminderSent: (props: { appointment_id?: string; channel?: string }) =>
    capture('appointment_reminder_sent', props),

  // appointment_reminder_opened — user tapped the push notification
  appointmentReminderOpened: (props: { appointment_id?: string }) =>
    capture('appointment_reminder_opened', props),

  // push_notifications_enabled / push_notifications_disabled
  pushNotificationsEnabled: () =>
    capture('push_notifications_enabled', {}),

  pushNotificationsDisabled: () =>
    capture('push_notifications_disabled', {}),

  // ── Generic ───────────────────────────────────────────────────────
  track: (event: string, properties?: Record<string, unknown>) =>
    capture(event, properties ?? {}),
}

// ── Internal helper ───────────────────────────────────────────────────────────

function capture(event: string, properties: Record<string, unknown>) {
  if (!initialised) return
  posthog.capture(event, properties)
}
