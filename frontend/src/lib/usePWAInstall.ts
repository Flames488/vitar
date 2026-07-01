/**
 * usePWAInstall — manages the browser's beforeinstallprompt event.
 *
 * Returns:
 *   canInstall  — true when the browser deems the app installable
 *   install()   — triggers the native install prompt
 *   dismiss()   — hides the prompt without installing
 *
 * Also fires PostHog events so you can track install funnel conversion.
 */

import { useState, useEffect, useCallback } from 'react'
import { analytics } from '@/lib/analytics'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export function usePWAInstall() {
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null)
  const [canInstall, setCanInstall] = useState(false)
  const [isInstalled, setIsInstalled] = useState(false)

  useEffect(() => {
    // Already installed (standalone mode)
    if (window.matchMedia('(display-mode: standalone)').matches) {
      setIsInstalled(true)
      return
    }

    const handler = (e: Event) => {
      e.preventDefault()
      setInstallEvent(e as BeforeInstallPromptEvent)
      setCanInstall(true)
      analytics.pwaInstallPromptShown()
    }

    window.addEventListener('beforeinstallprompt', handler)
    window.addEventListener('appinstalled', () => {
      setIsInstalled(true)
      setCanInstall(false)
      analytics.pwaInstalled()
    })

    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  const install = useCallback(async () => {
    if (!installEvent) return
    await installEvent.prompt()
    const { outcome } = await installEvent.userChoice
    if (outcome === 'accepted') {
      analytics.pwaInstalled()
    } else {
      analytics.pwaInstallDismissed()
    }
    setInstallEvent(null)
    setCanInstall(false)
  }, [installEvent])

  const dismiss = useCallback(() => {
    analytics.pwaInstallDismissed()
    setCanInstall(false)
    setInstallEvent(null)
  }, [])

  return { canInstall, isInstalled, install, dismiss }
}
