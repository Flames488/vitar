/**
 * FirstLoginInstallPrompt — shows a one-time "Install Vitar?" modal a few
 * seconds after a fresh login/registration (not on every page load or
 * session restore). Respects the 30-day "Not Now" snooze and skips
 * entirely once the app is already installed.
 *
 * Mount once inside DashboardLayout.
 */

import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import { usePWAInstall } from '@/lib/usePWAInstall'
import InstallInstructionsModal, { type InstallModalVariant } from '@/components/shared/InstallInstructionsModal'
import { analytics } from '@/lib/analytics'

const SNOOZE_KEY = 'vitar_install_prompt_snoozed_until'
const SNOOZE_DAYS = 30
const SHOW_DELAY_MS = 6000 // within the 5-8s window

function isSnoozed(): boolean {
  const until = localStorage.getItem(SNOOZE_KEY)
  return !!until && Date.now() < Number(until)
}

export default function FirstLoginInstallPrompt() {
  const { canInstall, isInstalled, isIOSSafari, isIOSNonSafari, install } = usePWAInstall()
  const [visible, setVisible] = useState(false)
  const [fallbackModal, setFallbackModal] = useState<InstallModalVariant | null>(null)

  useEffect(() => {
    const justLoggedIn = sessionStorage.getItem('vitar_just_logged_in')
    if (!justLoggedIn) return
    sessionStorage.removeItem('vitar_just_logged_in')

    if (isInstalled || isSnoozed()) return
    // Only worth showing when there's actually some install path available.
    if (!canInstall && !isIOSSafari && !isIOSNonSafari) return

    const timer = setTimeout(() => setVisible(true), SHOW_DELAY_MS)
    return () => clearTimeout(timer)
  }, [isInstalled, canInstall, isIOSSafari, isIOSNonSafari])

  const snooze = () => {
    localStorage.setItem(SNOOZE_KEY, String(Date.now() + SNOOZE_DAYS * 24 * 60 * 60 * 1000))
    analytics.pwaInstallDismissed()
    setVisible(false)
  }

  const handleInstall = () => {
    setVisible(false)
    if (canInstall) {
      install()
    } else if (isIOSSafari) {
      setFallbackModal('ios-safari')
    } else if (isIOSNonSafari) {
      setFallbackModal('ios-non-safari')
    }
  }

  if (fallbackModal) {
    return <InstallInstructionsModal variant={fallbackModal} onClose={() => setFallbackModal(null)} />
  }

  if (!visible) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={snooze} />
      <div className="relative w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-teal-600">
          <Download className="h-6 w-6 text-white" />
        </div>
        <h3 className="text-base font-semibold text-gray-900 mb-1.5">Install Vitar</h3>
        <p className="text-sm text-gray-500 mb-5">
          Add Vitar to your home screen for faster access and a smoother, app-like experience.
        </p>
        <div className="flex gap-2">
          <button
            onClick={snooze}
            className="flex-1 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Not Now
          </button>
          <button
            onClick={handleInstall}
            className="flex-1 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 transition-colors"
          >
            Install App
          </button>
        </div>
      </div>
    </div>
  )
}
