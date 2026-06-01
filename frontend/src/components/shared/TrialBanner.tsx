/**
 * Vitar v5 - Trial Banner Component
 */

import { AlertTriangle, X, ArrowRight } from 'lucide-react';
import { useState } from 'react';

interface TrialBannerProps {
  trial: {
    days_left: number;
    bookings_used: number;
    bookings_limit: number;
    is_expired: boolean;
  };
  onUpgrade: () => void;
}

export default function TrialBanner({ trial, onUpgrade }: TrialBannerProps) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const isUrgent = trial.days_left <= 1 || trial.is_expired;

  return (
    <div className={`flex items-center justify-between gap-4 px-4 py-2.5 text-sm ${
      isUrgent ? 'bg-red-600 text-white' : 'bg-amber-500 text-white'
    }`}>
      <div className="flex items-center gap-2">
        <AlertTriangle className="w-4 h-4 flex-shrink-0" />
        <span>
          {trial.is_expired
            ? 'Your free trial has expired. Upgrade to continue.'
            : `${trial.days_left} day${trial.days_left !== 1 ? 's' : ''} left in your trial · ${trial.bookings_used}/${trial.bookings_limit} bookings used`
          }
        </span>
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">
        <button
          onClick={onUpgrade}
          className="flex items-center gap-1 bg-white/20 hover:bg-white/30 px-3 py-1 rounded-full text-white text-xs font-semibold transition-colors"
        >
          Upgrade <ArrowRight className="w-3 h-3" />
        </button>
        {!trial.is_expired && (
          <button onClick={() => setDismissed(true)} className="text-white/70 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}
