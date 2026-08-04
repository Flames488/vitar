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
 *   bannerDismissed — true while PWAInstallBanner's 7-day snooze is active
 *   install()      — triggers the native install prompt (no-op if unavailable)
 *   dismiss()      — snoozes PWAInstallBanner for 7 days (localStorage,
 *                    same pattern as FirstLoginInstallPrompt's 30-day one)
 */
import { useCallback, useState, useSyncExternalStore } from 'react'
import { analytics } from '@/lib/analytics'
import { subscribe, getSnapshot, triggerInstall } from '@/lib/pwaInstallCapture'

const ua = typeof navigator !== 'undefined' ? navigator.userAgent : ''
const isIOS = /iPad|iPhone|iPod/.test(ua) && !(window as any).MSStream
const isIOSSafari = isIOS && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua)
const isIOSNonSafari = isIOS && !isIOSSafari

// Shorter than FirstLoginInstallPrompt's 30-day snooze — this is a
// lower-friction, always-visible banner, not a one-time interruption.
const BANNER_SNOOZE_KEY = 'vitar_pwa_banner_dismissed_until'
const BANNER_SNOOZE_DAYS = 7

function isBannerSnoozed(): boolean {
  const until = localStorage.getItem(BANNER_SNOOZE_KEY)
  return !!until && Date.now() < Number(until)
}

export function usePWAInstall() {
  const { canInstall, isInstalled } = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  // Local state (not just a plain localStorage read) so dismiss() triggers
  // an immediate re-render in whichever component called this hook —
  // reading localStorage directly on every render would never notice its
  // own write without some other unrelated re-render happening first.
  const [bannerDismissed, setBannerDismissed] = useState(isBannerSnoozed)

  const install = useCallback(async () => {
    const outcome = await triggerInstall()
    if (outcome === 'accepted') analytics.pwaInstalled()
    else if (outcome === 'dismissed') analytics.pwaInstallDismissed()
  }, [])

  const dismiss = useCallback(() => {
    localStorage.setItem(BANNER_SNOOZE_KEY, String(Date.now() + BANNER_SNOOZE_DAYS * 24 * 60 * 60 * 1000))
    setBannerDismissed(true)
    analytics.pwaInstallDismissed()
  }, [])

  return {
    canInstall,
    isInstalled,
    isIOS,
    isIOSSafari,
    isIOSNonSafari,
    bannerDismissed,
    install,
    dismiss,
  }
}
