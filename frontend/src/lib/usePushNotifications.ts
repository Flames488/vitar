/**
 * usePushNotifications
 *
 * Manages Web Push subscription lifecycle:
 *   1. Registers the push service worker (sw-push.js)
 *   2. Requests notification permission
 *   3. Subscribes via the PushManager (VAPID)
 *   4. POSTs the subscription to /api/v1/push/subscribe
 *   5. Tracks analytics via PostHog
 *
 * Usage:
 *   const { isSupported, isSubscribed, subscribe, unsubscribe } = usePushNotifications()
 */

import { useState, useEffect, useCallback } from 'react'
import apiClient from '@/lib/api/client'
import { analytics } from '@/lib/analytics'

const PUSH_API = '/api/v1/push'

async function getVapidKey(): Promise<string> {
  const res = await apiClient.get<{ publicKey: string }>(`${PUSH_API}/vapid-key`)
  return res.data.publicKey
}

async function registerPushSW(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) return null
  try {
    return await navigator.serviceWorker.register('/sw-push.js', { scope: '/' })
  } catch {
    return null
  }
}

function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0))) as Uint8Array<ArrayBuffer>
}

export function usePushNotifications() {
  const isSupported =
    typeof window !== 'undefined' &&
    'Notification' in window &&
    'PushManager' in window &&
    'serviceWorker' in navigator

  const [isSubscribed, setIsSubscribed] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [permission, setPermission] =
    useState<NotificationPermission>(isSupported ? Notification.permission : 'denied')

  // Check current subscription state on mount
  useEffect(() => {
    if (!isSupported) return
    ;(async () => {
      const reg = await navigator.serviceWorker.getRegistration('/sw-push.js')
      if (!reg) return
      const sub = await reg.pushManager.getSubscription()
      setIsSubscribed(!!sub)
    })()
  }, [isSupported])

  const subscribe = useCallback(async () => {
    if (!isSupported || isSubscribed) return
    setIsLoading(true)
    try {
      // 1. Request permission
      const perm = await Notification.requestPermission()
      setPermission(perm)
      if (perm !== 'granted') return

      // 2. Register SW
      const reg = await registerPushSW()
      if (!reg) throw new Error('SW registration failed')

      // 3. Get VAPID public key
      const vapidKey = await getVapidKey()

      // 4. Subscribe via PushManager
      const pushSub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      })

      const json = pushSub.toJSON() as {
        endpoint: string
        keys: { p256dh: string; auth: string }
      }

      // 5. POST subscription to backend
      await apiClient.post(`${PUSH_API}/subscribe`, {
        endpoint: json.endpoint,
        keys: json.keys,
        user_agent: navigator.userAgent.slice(0, 200),
      })

      setIsSubscribed(true)
      analytics.track('push_notifications_enabled', {})
    } catch (err) {
      console.error('[push] subscribe error:', err)
    } finally {
      setIsLoading(false)
    }
  }, [isSupported, isSubscribed])

  const unsubscribe = useCallback(async () => {
    if (!isSupported || !isSubscribed) return
    setIsLoading(true)
    try {
      const reg = await navigator.serviceWorker.getRegistration('/sw-push.js')
      const sub = await reg?.pushManager.getSubscription()
      if (sub) {
        const json = sub.toJSON() as {
          endpoint: string
          keys: { p256dh: string; auth: string }
        }
        await sub.unsubscribe()
        await apiClient.delete(`${PUSH_API}/subscribe`, { data: { endpoint: json.endpoint, keys: json.keys } })
      }
      setIsSubscribed(false)
      analytics.track('push_notifications_disabled', {})
    } catch (err) {
      console.error('[push] unsubscribe error:', err)
    } finally {
      setIsLoading(false)
    }
  }, [isSupported, isSubscribed])

  return {
    isSupported,
    isSubscribed,
    isLoading,
    permission,
    subscribe,
    unsubscribe,
  }
}
