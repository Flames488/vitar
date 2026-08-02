/**
 * usePWAInstall — reads the shared beforeinstallprompt capture (see
 * pwaInstallCapture.ts) plus does iOS platform detection.
 *
 * Returns:
 *   canInstall     — true when the browser has a real native prompt ready
 *   isInstalled    — true when already running in standalone/installed mode
 *   isIOS          — true on any iOS browser
 *   isIOSSafari    — true on iOS Safari specifically (the only iOS browser
 *                    that can "install" via Add to Home Screen)
 *   isIOSNonSafari — true on iOS Chrome/Firefox/Edge (WebKit wrappers that
 *                    cannot install a standalone app)
 *   install()      — triggers the native install prompt (no-op if unavailable)
 *   dismiss()      — records a dismissal (analytics only)
 */
import { useCallback, useSyncExternalStore } from 'react'
import { analytics } from '@/lib/analytics'
import { subscribe, getSnapshot, triggerInstall } from '@/lib/pwaInstallCapture'

const ua = typeof navigator !== 'undefined' ? navigator.userAgent : ''
const isIOS = /iPad|iPhone|iPod/.test(ua) && !(window as any).MSStream
const isIOSSafari = isIOS && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua)
const isIOSNonSafari = isIOS && !isIOSSafari

export function usePWAInstall() {
  const { canInstall, isInstalled } = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)

  const install = useCallback(async () => {
    const outcome = await triggerInstall()
    if (outcome === 'accepted') analytics.pwaInstalled()
    else if (outcome === 'dismissed') analytics.pwaInstallDismissed()
  }, [])

  const dismiss = useCallback(() => {
    analytics.pwaInstallDismissed()
  }, [])

  return {
    canInstall,
    isInstalled,
    isIOS,
    isIOSSafari,
    isIOSNonSafari,
    install,
    dismiss,
  }
}
