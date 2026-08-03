/**
 * InstallInstructionsModal — shown instead of the native install prompt
 * whenever the browser can't offer one (iOS Safari, iOS Chrome/Firefox/Edge,
 * or any other browser without `beforeinstallprompt` support).
 *
 * Rendered by InstallAppButton on click when `canInstall` is false.
 */

import { Share, Copy, Check } from 'lucide-react'
import { useState } from 'react'

export type InstallInstructionsVariant = 'ios-safari' | 'ios-non-safari' | 'unsupported'

interface InstallInstructionsModalProps {
  variant: InstallInstructionsVariant
  onClose: () => void
}

export default function InstallInstructionsModal({ variant, onClose }: InstallInstructionsModalProps) {
  const [copied, setCopied] = useState(false)

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard API unavailable — silently ignore, the link is still visible in the address bar
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="text-base font-semibold text-gray-900 mb-1.5">Install Vitar</h3>

        {variant === 'ios-safari' && (
          <>
            <p className="text-sm text-gray-500 mb-4">
              Add Vitar to your home screen for the full app experience:
            </p>
            <ol className="space-y-3 mb-5">
              <li className="flex items-start gap-3 text-sm text-gray-700">
                <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-teal-50 text-teal-700 text-xs font-semibold">1</span>
                <span className="pt-0.5">
                  Tap the <Share className="inline w-4 h-4 -mt-0.5 mx-0.5" /> Share icon in Safari's toolbar
                </span>
              </li>
              <li className="flex items-start gap-3 text-sm text-gray-700">
                <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-teal-50 text-teal-700 text-xs font-semibold">2</span>
                <span className="pt-0.5">Scroll down and tap <strong>Add to Home Screen</strong></span>
              </li>
              <li className="flex items-start gap-3 text-sm text-gray-700">
                <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-teal-50 text-teal-700 text-xs font-semibold">3</span>
                <span className="pt-0.5">Tap <strong>Add</strong> to confirm</span>
              </li>
            </ol>
          </>
        )}

        {variant === 'ios-non-safari' && (
          <>
            <p className="text-sm text-gray-500 mb-4">
              On iOS, installing Vitar as an app only works in Safari — this browser can't do it,
              even though it looks similar. Open this page in Safari, then use Share → Add to Home Screen.
            </p>
            <button
              onClick={copyLink}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors mb-2"
            >
              {copied ? <Check className="w-4 h-4 text-teal-600" /> : <Copy className="w-4 h-4" />}
              {copied ? 'Link copied' : 'Copy link for Safari'}
            </button>
          </>
        )}

        {variant === 'unsupported' && (
          <>
            <p className="text-sm text-gray-500 mb-4">
              This browser doesn't support one-tap install. You can still add Vitar manually:
            </p>
            <div className="space-y-3 mb-5">
              <div className="rounded-lg bg-gray-50 p-3">
                <p className="text-xs font-semibold text-gray-900 mb-1">Android (Chrome)</p>
                <p className="text-xs text-gray-600">Tap the ⋮ menu → Add to Home screen / Install app</p>
              </div>
              <div className="rounded-lg bg-gray-50 p-3">
                <p className="text-xs font-semibold text-gray-900 mb-1">iPhone (Safari)</p>
                <p className="text-xs text-gray-600">Tap the Share icon → Add to Home Screen</p>
              </div>
            </div>
          </>
        )}

        <button
          onClick={onClose}
          className="w-full rounded-lg bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-700 transition-colors"
        >
          Got it
        </button>
      </div>
    </div>
  )
}
