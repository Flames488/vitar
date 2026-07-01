/**
 * Vitar Frontend — Sentry Initialization
 *
 * Tracks:
 *   React crashes      — via ErrorBoundary + Sentry.captureException
 *   API failures       — via apiClient interceptor
 *   Performance issues — via BrowserTracing + web vitals
 *
 * Install:
 *   npm install @sentry/react
 *
 * Required .env vars:
 *   VITE_SENTRY_DSN=https://xxx@oyyy.ingest.sentry.io/zzz
 *   VITE_APP_VERSION=1.0.0     (optional — set in CI)
 *   VITE_ENVIRONMENT=production (optional — defaults to NODE_ENV)
 *
 * Usage:
 *   import { initSentry } from '@/lib/sentry'
 *   initSentry()  // called once in main.tsx before React renders
 *
 *   import * as Sentry from '@sentry/react'
 *   Sentry.captureException(error)
 *   Sentry.captureMessage('something went wrong', 'warning')
 */

import * as Sentry from '@sentry/react'

let initialised = false

export function initSentry() {
  const dsn = import.meta.env.VITE_SENTRY_DSN as string
  if (!dsn || initialised) return

  const environment =
    (import.meta.env.VITE_ENVIRONMENT as string) ||
    (import.meta.env.DEV ? 'development' : 'production')

  const release =
    (import.meta.env.VITE_APP_VERSION as string) || 'vitar@1.0.0'

  Sentry.init({
    dsn,
    environment,
    release,

    // Sample 10% of transactions in production for performance monitoring.
    // Use 1.0 in dev/staging to capture everything.
    tracesSampleRate: environment === 'production' ? 0.1 : 1.0,

    integrations: [
      Sentry.browserTracingIntegration(),
      Sentry.replayIntegration({
        // Replay is useful but HIPAA-sensitive. Mask all text/inputs by default.
        maskAllText: true,
        blockAllMedia: true,
      }),
    ],

    // Capture Replay for 1% of sessions (0 in dev)
    replaysSessionSampleRate: environment === 'production' ? 0.01 : 0,
    // Capture Replay for 10% of error sessions
    replaysOnErrorSampleRate: environment === 'production' ? 0.1 : 0,

    // Don't send PII (emails, IPs) in payloads
    sendDefaultPii: false,

    // Ignore noisy browser extension errors
    ignoreErrors: [
      'ResizeObserver loop limit exceeded',
      'ResizeObserver loop completed with undelivered notifications',
      'Non-Error promise rejection captured',
    ],

    beforeSend(event: Sentry.ErrorEvent) {
      // Strip auth tokens from request headers in captured events
      if (event.request?.headers) {
        delete event.request.headers['Authorization']
        delete event.request.headers['X-API-Key']
        delete event.request.headers['Cookie']
      }
      return event
    },
  })

  initialised = true
}

/**
 * Enrich Sentry scope with authenticated user identity.
 * Call this right after login / validateSession succeeds.
 */
export function setSentryUser(user: {
  id: string
  email: string
  clinic_id?: string
}) {
  Sentry.setUser({
    id: user.id,
    email: user.email,  // remove this line if you want zero PII
    clinic_id: user.clinic_id,
  })
}

/**
 * Clear Sentry user identity on logout.
 */
export function clearSentryUser() {
  Sentry.setUser(null)
}

/**
 * Track an API error with extra context.
 * Call from the apiClient error interceptor.
 */
export function captureApiError(
  error: unknown,
  context: {
    url?: string
    method?: string
    status?: number
    clinic_id?: string
  },
) {
  Sentry.withScope((scope: Sentry.Scope) => {
    scope.setTag('error_type', 'api_failure')
    scope.setContext('api_request', context)
    if (context.status) scope.setTag('http_status', String(context.status))
    Sentry.captureException(error)
  })
}
