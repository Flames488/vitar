/**
 * InstallAppButton — navbar "Install App" button. Handles the native
 * install flow on Chrome/Edge, and falls back to instruction modals on
 * iOS Safari, iOS non-Safari, and other unsupported browsers.
 *
 * Drop into any navbar; matches the existing button sizing conventions
 * used alongside Sign in / Start free trial links.
 */

import { useState } from 'react'
import { Download, Check } from 'lucide-react'
import { usePWAInstall } from '@/lib/usePWAInstall'
import InstallInstructionsModal, { type InstallModalVariant } from '@/components/shared/InstallInstructionsModal'

interface InstallAppButtonProps {
  className?: string
  compact?: boolean // icon-only, for tight mobile spaces
  dark?: boolean // for use on dark backgrounds, e.g. the dashboard sidebar
}

export default function InstallAppButton({ className = '', compact = false, dark = false }: InstallAppButtonProps) {
  const { canInstall, isInstalled, isIOSSafari, isIOSNonSafari, isUnsupported, install } = usePWAInstall()
  const [modalVariant, setModalVariant] = useState<InstallModalVariant | null>(null)

  if (isInstalled) {
    if (compact) return null
    return (
      <span
        className={`inline-flex items-center gap-1.5 text-sm font-medium cursor-default ${
          dark ? 'text-slate-500' : 'text-gray-400'
        } ${className}`}
        title="Vitar is installed"
      >
        <Check className="w-4 h-4" />
        Installed
      </span>
    )
  }

  const handleClick = () => {
    if (canInstall) {
      install()
      return
    }
    if (isIOSSafari) {
      setModalVariant('ios-safari')
    } else if (isIOSNonSafari) {
      setModalVariant('ios-non-safari')
    } else if (isUnsupported) {
      setModalVariant('unsupported')
    }
  }

  return (
    <>
      <button
        onClick={handleClick}
        className={
          compact
            ? `p-2 rounded-lg transition-colors ${
                dark ? 'text-slate-300 hover:bg-white/5' : 'text-gray-600 hover:bg-gray-100'
              } ${className}`
            : `inline-flex items-center gap-1.5 text-sm font-medium transition-colors ${
                dark ? 'text-slate-300 hover:text-white' : 'text-slate-600 hover:text-slate-900'
              } ${className}`
        }
        aria-label="Install App"
        title="Install App"
      >
        <Download className="w-4 h-4" />
        {!compact && 'Install App'}
      </button>

      {modalVariant && <InstallInstructionsModal variant={modalVariant} onClose={() => setModalVariant(null)} />}
    </>
  )
}
