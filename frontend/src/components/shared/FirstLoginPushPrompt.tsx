/**
 * FirstLoginPushPrompt — one-time "Enable appointment reminders?" nudge a
 * few seconds after a fresh login/registration. Push notifications are
 * currently opt-in-only via a settings-page toggle (PushNotificationToggle)
 * that a new clinic would only find by looking — this surfaces the same
 * subscribe() action right after first login instead, same reasoning as
 * FirstLoginInstallPrompt for the PWA install prompt.
 *
 * Mount once inside DashboardLayout, alongside FirstLoginInstallPrompt.
 * Reads the same 'vitar_just_logged_in' signal but does NOT consume it —
 * FirstLoginInstallPrompt already does, and two components racing to
 * sessionStorage.removeItem the same key would make whichever mounts
 * second never see it. Own separate snooze/shown-once key, own delay
 * (after the install prompt's) so they don't stack.
 */

import { useEffect, useState } from 'react'
import { Bell } from 'lucide-react'
import { usePushNotifications } from '@/lib/usePushNotifications'

const SNOOZE_KEY = 'vitar_push_prompt_snoozed_until'
const SNOOZE_DAYS = 30
const SHOWN_THIS_SESSION_KEY = 'vitar_push_prompt_shown_this_session'
const SHOW_DELAY_MS = 11000 // after FirstLoginInstallPrompt's 6s, so they don't overlap

function isSnoozed(): boolean {
  const until = localStorage.getItem(SNOOZE_KEY)
  return !!until && Date.now() < Number(until)
}

export default function FirstLoginPushPrompt() {
  const { isSupported, isSubscribed, permission, subscribe } = usePushNotifications()
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!sessionStorage.getItem('vitar_just_logged_in')) return
    if (sessionStorage.getItem(SHOWN_THIS_SESSION_KEY)) return
    if (!isSupported || isSubscribed || permission === 'denied' || isSnoozed()) return

    const timer = setTimeout(() => {
      sessionStorage.setItem(SHOWN_THIS_SESSION_KEY, '1')
      setVisible(true)
    }, SHOW_DELAY_MS)
    return () => clearTimeout(timer)
  }, [isSupported, isSubscribed, permission])

  const snooze = () => {
    localStorage.setItem(SNOOZE_KEY, String(Date.now() + SNOOZE_DAYS * 24 * 60 * 60 * 1000))
    setVisible(false)
  }

  const handleEnable = () => {
    setVisible(false)
    subscribe()
  }

  if (!visible) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={snooze} />
      <div className="relative w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-teal-600">
          <Bell className="h-6 w-6 text-white" />
        </div>
        <h3 className="text-base font-semibold text-gray-900 mb-1.5">Turn on appointment reminders</h3>
        <p className="text-sm text-gray-500 mb-5">
          Get notified the moment a new booking comes in, even when Vitar isn't open in your browser.
        </p>
        <div className="flex gap-2">
          <button
            onClick={snooze}
            className="flex-1 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Not Now
          </button>
          <button
            onClick={handleEnable}
            className="flex-1 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 transition-colors"
          >
            Enable
          </button>
        </div>
      </div>
    </div>
  )
}
