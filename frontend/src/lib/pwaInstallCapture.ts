/**
 * pwaInstallCapture — captures the browser's `beforeinstallprompt` event
 * the moment it fires, at module scope (not inside a React component).
 *
 * Chrome/Edge can fire this event as soon as installability criteria are
 * met, which is often before any React component has mounted and attached
 * its own listener — a listener attached late simply never sees the event,
 * and it cannot be recovered afterwards. Import this module as the very
 * first thing in main.tsx so it's listening before anything else runs.
 * usePWAInstall reads from this shared singleton instead of attaching its
 * own per-component listener, so every consumer stays in sync and none of
 * them can miss the event due to mount timing.
 */
import { toast } from 'sonner'
import { analytics } from '@/lib/analytics'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

type Listener = () => void

let deferredEvent: BeforeInstallPromptEvent | null = null
let installed =
  typeof window !== 'undefined' &&
  (window.matchMedia('(display-mode: standalone)').matches || (window.navigator as any).standalone === true)

// useSyncExternalStore requires getSnapshot to return a referentially
// stable value when nothing has changed — a fresh object literal on every
// call makes React think the store is changing on every render, which it
// detects as an infinite loop and throws. Only replace this reference
// when canInstall/isInstalled actually change (see setSnapshot below).
let snapshot = { canInstall: false, isInstalled: installed }
function setSnapshot() {
  const canInstall = !!deferredEvent
  if (snapshot.canInstall !== canInstall || snapshot.isInstalled !== installed) {
    snapshot = { canInstall, isInstalled: installed }
  }
}

const listeners = new Set<Listener>()
const notify = () => {
  setSnapshot()
  listeners.forEach((l) => l())
}

if (typeof window !== 'undefined' && !installed) {
  window.addEventListener('beforeinstallprompt', (e: Event) => {
    e.preventDefault()
    deferredEvent = e as BeforeInstallPromptEvent
    analytics.pwaInstallPromptShown()
    notify()
  })
  window.addEventListener('appinstalled', () => {
    installed = true
    deferredEvent = null
    analytics.pwaInstalled()
    toast.success('Vitar has been installed successfully.')
    notify()
  })
}

// vite-plugin-pwa's auto-injected registerSW.js (registerType: 'autoUpdate')
// is the bare minimum: it registers the service worker and nothing else — no
// handling for what happens once a new one takes over. autoUpdate makes a
// freshly-deployed SW call skipWaiting()/clientsClaim() on its own, but an
// already-open tab has no way to know that happened, so it just keeps
// running the JS it already loaded until someone manually reloads. That's
// what's been showing up as "I have to refresh to see the update" — this is
// the standard fix: reload once, automatically, the moment a new SW actually
// takes control, so nobody has to notice or do it themselves. Guarded so a
// stray double-fire of controllerchange can't cause a reload loop.
if (typeof window !== 'undefined' && 'serviceWorker' in navigator) {
  let reloadedForNewSW = false
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (reloadedForNewSW) return
    reloadedForNewSW = true
    window.location.reload()
  })
}

export function getSnapshot() {
  return snapshot
}

export function subscribe(listener: Listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Returns the outcome, or 'unavailable' if there's no captured event to use. */
export async function triggerInstall(): Promise<'accepted' | 'dismissed' | 'unavailable'> {
  if (!deferredEvent) return 'unavailable'
  const event = deferredEvent
  await event.prompt()
  const { outcome } = await event.userChoice
  deferredEvent = null
  notify()
  return outcome
}
