/**
 * Vitar PWA — Push Notification Service Worker
 *
 * This SW handles incoming Web Push messages and the user actions
 * ("Confirm" / "Dismiss") on the notification.
 *
 * Registered via usePushNotifications.ts → registerPushSW().
 *
 * Events tracked (reported back to /api/v1/push/event):
 *   appointment_reminder_sent    — push arrives
 *   appointment_reminder_opened  — user taps the notification body
 *   appointment_confirmed        — user taps the "Confirm" action button
 */

self.addEventListener('push', (event) => {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: 'Vitar', body: event.data.text() };
  }

  // Silent ping — no visible notification needed
  if (payload.type === 'ping') return;

  const { title, body, icon, badge, tag, data, actions } = payload;

  event.waitUntil(
    self.registration.showNotification(title || 'Vitar', {
      body: body || '',
      icon: icon || '/icon-192x192.png',
      badge: badge || '/icon-72x72.png',
      tag: tag || 'vitar-reminder',
      data: data || {},
      actions: actions || [],
      renotify: true,
      requireInteraction: true,    // keep the notification on screen until actioned
      vibrate: [200, 100, 200],
    }).then(() => {
      // Report "reminder sent" back to backend analytics
      _reportEvent('appointment_reminder_sent', data?.appointment_id, data?.notification_id);
    })
  );
});


self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const { action } = event;
  const notifData = event.notification.data || {};
  const { appointment_id, notification_id, url } = notifData;

  if (action === 'confirm') {
    // "Confirm" action — report confirmation, then open the appointment page
    event.waitUntil(
      _reportEvent('appointment_confirmed', appointment_id, notification_id)
        .then(() => _openWindow(url || '/appointments'))
    );
  } else if (action === 'dismiss') {
    // Dismissed — no navigation needed
  } else {
    // User tapped the notification body
    event.waitUntil(
      _reportEvent('appointment_reminder_opened', appointment_id, notification_id)
        .then(() => _openWindow(url || '/appointments'))
    );
  }
});


// ── Helpers ──────────────────────────────────────────────────────────────────

async function _reportEvent(eventName, appointmentId, notificationId) {
  try {
    await fetch('/api/v1/push/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        event: eventName,
        appointment_id: appointmentId || null,
        notification_id: notificationId || null,
      }),
    });
  } catch {
    // SW fetch failures are expected when offline — not an error
  }
}

async function _openWindow(url) {
  const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  for (const client of clients) {
    if (client.url.includes(self.location.origin)) {
      client.focus();
      client.navigate(url);
      return;
    }
  }
  self.clients.openWindow(url);
}
