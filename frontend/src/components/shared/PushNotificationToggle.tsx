/**
 * PushNotificationToggle
 *
 * A settings-page toggle that lets clinic users opt in/out of
 * browser push notifications for appointment reminders.
 *
 * Drop inside NotificationSettingsPage:
 *   import PushNotificationToggle from '@/components/shared/PushNotificationToggle'
 *   <PushNotificationToggle />
 */

import { usePushNotifications } from '@/lib/usePushNotifications'

export default function PushNotificationToggle() {
  const { isSupported, isSubscribed, isLoading, permission, subscribe, unsubscribe } =
    usePushNotifications()

  if (!isSupported) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
        <p className="text-sm text-gray-500">
          Push notifications are not supported in this browser.
        </p>
      </div>
    )
  }

  return (
    <div className="flex items-start justify-between rounded-lg border border-gray-200 px-4 py-4">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-900">Appointment Reminders (Push)</p>
        <p className="text-xs text-gray-500 mt-0.5">
          Receive browser notifications for upcoming appointments even when the app is closed.
        </p>
        {permission === 'denied' && (
          <p className="text-xs text-red-500 mt-1">
            Notifications blocked. Enable them in your browser site settings.
          </p>
        )}
      </div>

      <div className="ml-4 flex-shrink-0">
        <button
          onClick={isSubscribed ? unsubscribe : subscribe}
          disabled={isLoading || permission === 'denied'}
          className={[
            'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent',
            'transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            isSubscribed ? 'bg-teal-600' : 'bg-gray-200',
          ].join(' ')}
          role="switch"
          aria-checked={isSubscribed}
        >
          <span
            aria-hidden="true"
            className={[
              'pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow ring-0',
              'transform transition duration-200 ease-in-out',
              isSubscribed ? 'translate-x-5' : 'translate-x-0',
            ].join(' ')}
          />
        </button>
      </div>
    </div>
  )
}
