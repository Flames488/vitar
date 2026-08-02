/**
 * InstallInstructionsModal — shared "how to install" dialog used by both
 * InstallAppButton and FirstLoginInstallPrompt for the platforms where a
 * native install prompt isn't available (iOS Safari, iOS non-Safari, and
 * generic unsupported browsers).
 */

import { Share, X, Copy } from 'lucide-react'
import { toast } from 'sonner'

export type InstallModalVariant = 'ios-safari' | 'ios-non-safari' | 'unsupported'

interface InstallInstructionsModalProps {
  variant: InstallModalVariant
  onClose: () => void
}

export default function InstallInstructionsModal({ variant, onClose }: InstallInstructionsModalProps) {
  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.origin)
      toast.success('Link copied')
    } catch {
      toast.error('Could not copy link')
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl">
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          aria-label="Close"
        >
          <X className="w-4 h-4" />
        </button>

        {variant === 'ios-safari' && (
          <>
            <h3 className="text-base font-semibold text-gray-900 mb-2">Install Vitar</h3>
            <p className="text-sm text-gray-600 mb-4">
              Tap the <Share className="inline w-4 h-4 -mt-0.5 mx-0.5" /> Share icon in Safari's toolbar, then
              select <span className="font-medium text-gray-900">"Add to Home Screen"</span>.
            </p>
            <button
              onClick={onClose}
              className="w-full rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 transition-colors"
            >
              Got it
            </button>
          </>
        )}

        {variant === 'ios-non-safari' && (
          <>
            <h3 className="text-base font-semibold text-gray-900 mb-2">Open in Safari to install</h3>
            <p className="text-sm text-gray-600 mb-4">
              iOS doesn't allow installing apps from this browser. Open Vitar in Safari, then tap the Share icon and
              choose "Add to Home Screen".
            </p>
            <div className="flex gap-2">
              <button
                onClick={copyLink}
                className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                <Copy className="w-3.5 h-3.5" />
                Copy Link
              </button>
              <button
                onClick={onClose}
                className="flex-1 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 transition-colors"
              >
                Got it
              </button>
            </div>
          </>
        )}

        {variant === 'unsupported' && (
          <>
            <h3 className="text-base font-semibold text-gray-900 mb-3">Install Vitar</h3>
            <div className="space-y-3 mb-4">
              <div>
                <p className="text-sm font-medium text-gray-900">Android (Chrome)</p>
                <p className="text-sm text-gray-600">Tap the menu (⋮) and select "Install app" or "Add to Home screen".</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900">iPhone (Safari)</p>
                <p className="text-sm text-gray-600">Tap the Share icon, then "Add to Home Screen".</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="w-full rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 transition-colors"
            >
              Got it
            </button>
          </>
        )}
      </div>
    </div>
  )
}
