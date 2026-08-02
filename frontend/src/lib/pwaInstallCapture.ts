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

const listeners = new Set<Listener>()
const notify = () => listeners.forEach((l) => l())

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

export function getSnapshot() {
  return { canInstall: !!deferredEvent, isInstalled: installed }
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
