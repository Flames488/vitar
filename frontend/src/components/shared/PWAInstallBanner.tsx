/**
 * PWAInstallBanner — shows a subtle "Install App" prompt at the bottom
 * of the screen when the browser signals the app is installable.
 *
 * Drop this inside DashboardLayout (or App.tsx) so it only shows to
 * logged-in clinic users, not on the public booking / landing pages.
 */

import { usePWAInstall } from '@/lib/usePWAInstall'

export default function PWAInstallBanner() {
  const { canInstall, install, dismiss } = usePWAInstall()

  if (!canInstall) return null

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-md">
      <div className="flex items-center gap-3 rounded-xl border border-teal-200 bg-white px-4 py-3 shadow-lg shadow-teal-900/10">
        {/* Icon */}
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-teal-600">
          <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
          </svg>
        </div>

        {/* Text */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900">Install Vitar</p>
          <p className="text-xs text-gray-500 truncate">Add to home screen for quick access</p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={dismiss}
            className="text-xs text-gray-400 hover:text-gray-600 transition-colors px-1"
            aria-label="Dismiss install prompt"
          >
            Not now
          </button>
          <button
            onClick={install}
            className="rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-teal-700 transition-colors"
          >
            Install
          </button>
        </div>
      </div>
    </div>
  )
}
