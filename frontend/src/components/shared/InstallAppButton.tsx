/**
 * InstallAppButton — navbar "Install App" button. Triggers the real
 * native install prompt when the browser has one ready; does nothing
 * otherwise (no instructions modal — see usePWAInstall for why a real
 * prompt might not be available yet).
 *
 * Drop into any navbar; matches the existing button sizing conventions
 * used alongside Sign in / Start free trial links.
 */

import { Download, Check } from 'lucide-react'
import { usePWAInstall } from '@/lib/usePWAInstall'

interface InstallAppButtonProps {
  className?: string
  compact?: boolean // icon-only, for tight mobile spaces
  dark?: boolean // for use on dark backgrounds, e.g. the dashboard sidebar
  onClick?: () => void // fires before the install attempt, e.g. to close a mobile menu
}

export default function InstallAppButton({ className = '', compact = false, dark = false, onClick }: InstallAppButtonProps) {
  const { canInstall, isInstalled, install } = usePWAInstall()

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
    onClick?.()
    if (canInstall) install() // no-op if the browser hasn't offered a real install prompt yet
  }

  return (
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
  )
}
