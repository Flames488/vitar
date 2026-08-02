/**
 * usePWAInstall — manages the browser's beforeinstallprompt event, plus
 * platform detection for browsers that never fire it (iOS Safari, iOS
 * non-Safari WebKit wrappers, and other unsupported browsers).
 *
 * Returns:
 *   canInstall     — true when the browser deems the app installable natively
 *   isInstalled    — true when already running in standalone/installed mode
 *   isIOS          — true on any iOS browser
 *   isIOSSafari    — true on iOS Safari specifically (the only iOS browser
 *                    that can "install" via Add to Home Screen)
 *   isIOSNonSafari — true on iOS Chrome/Firefox/Edge (WebKit wrappers that
 *                    cannot install a standalone app)
 *   isUnsupported  — true when not iOS and no native install prompt has
 *                    surfaced (desktop Safari/Firefox, etc.)
 *   install()      — triggers the native install prompt
 *   dismiss()      — hides the prompt without installing
 *
 * Also fires PostHog events so you can track install funnel conversion.
 */

import { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import { analytics } from '@/lib/analytics'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const ua = typeof navigator !== 'undefined' ? navigator.userAgent : ''
const isIOS = /iPad|iPhone|iPod/.test(ua) && !(window as any).MSStream
const isIOSSafari = isIOS && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua)
const isIOSNonSafari = isIOS && !isIOSSafari

export function usePWAInstall() {
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null)
  const [canInstall, setCanInstall] = useState(false)
  const [isInstalled, setIsInstalled] = useState(
    () =>
      typeof window !== 'undefined' &&
      (window.matchMedia('(display-mode: standalone)').matches || (window.navigator as any).standalone === true)
  )

  useEffect(() => {
    if (isInstalled) return

    const handler = (e: Event) => {
      e.preventDefault()
      setInstallEvent(e as BeforeInstallPromptEvent)
      setCanInstall(true)
      analytics.pwaInstallPromptShown()
    }

    const handleInstalled = () => {
      setIsInstalled(true)
      setCanInstall(false)
      setInstallEvent(null)
      analytics.pwaInstalled()
      toast.success('Vitar has been installed successfully.')
    }

    window.addEventListener('beforeinstallprompt', handler)
    window.addEventListener('appinstalled', handleInstalled)

    return () => {
      window.removeEventListener('beforeinstallprompt', handler)
      window.removeEventListener('appinstalled', handleInstalled)
    }
  }, [isInstalled])

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

  return {
    canInstall,
    isInstalled,
    isIOS,
    isIOSSafari,
    isIOSNonSafari,
    // Not iOS, not installed, and no native prompt has surfaced — either it
    // never will (Firefox/desktop Safari) or it just hasn't fired yet.
    isUnsupported: !isIOS && !isInstalled && !canInstall,
    install,
    dismiss,
  }
}
