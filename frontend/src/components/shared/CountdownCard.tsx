/**
 * Vitar — Countdown Card
 * Professional, glanceable countdown for trial expiry, next appointment,
 * or subscription renewal. Designed to sit prominently on the dashboard
 * directly under the page header.
 */

import { Link } from 'react-router-dom';
import { Clock3, CalendarClock, ShieldAlert, ArrowRight } from 'lucide-react';
import { useCountdown } from '@/lib/useCountdown';

type CountdownVariant = 'trial' | 'appointment' | 'renewal';

interface CountdownCardProps {
  variant: CountdownVariant;
  targetIso: string | null | undefined;
  /** Primary label, e.g. "Free trial ends in" / "Next appointment" / "Plan renews in" */
  title: string;
  /** Secondary line under the title, e.g. doctor name or plan name */
  subtitle?: string;
  ctaLabel?: string;
  ctaTo?: string;
  /** Hours remaining below which the card switches to an urgent (red) treatment */
  urgentBelowHours?: number;
}

const VARIANT_META: Record<CountdownVariant, { icon: typeof Clock3 }> = {
  trial: { icon: ShieldAlert },
  appointment: { icon: CalendarClock },
  renewal: { icon: Clock3 },
};

function TimeBlock({ value, label, urgent }: { value: number; label: string; urgent: boolean }) {
  return (
    <div className="flex flex-col items-center min-w-[3.25rem]">
      <span
        className={`text-2xl sm:text-3xl font-bold leading-none tabular-nums ${
          urgent ? 'text-white' : 'text-slate-900'
        }`}
      >
        {String(value).padStart(2, '0')}
      </span>
      <span
        className={`text-[10px] font-semibold uppercase tracking-wider mt-1 ${
          urgent ? 'text-white/70' : 'text-slate-400'
        }`}
      >
        {label}
      </span>
    </div>
  );
}

export default function CountdownCard({
  variant,
  targetIso,
  title,
  subtitle,
  ctaLabel,
  ctaTo,
  urgentBelowHours = 24,
}: CountdownCardProps) {
  const countdown = useCountdown(targetIso, 1000);
  const Icon = VARIANT_META[variant].icon;

  if (!targetIso || !countdown) return null;

  const urgent = !countdown.isPast && countdown.days === 0 && countdown.hours < urgentBelowHours;
  const expired = countdown.isPast;

  return (
    <div
      className={`relative overflow-hidden rounded-2xl border p-5 sm:p-6 shadow-sm transition-colors ${
        expired || urgent
          ? 'bg-gradient-to-br from-red-600 to-rose-600 border-red-700'
          : 'bg-white border-slate-200'
      }`}
    >
      {!expired && !urgent && (
        <div className="absolute -right-6 -top-6 w-28 h-28 rounded-full bg-teal-50" />
      )}

      <div className="relative flex flex-col sm:flex-row sm:items-center sm:justify-between gap-5">
        <div className="flex items-start gap-3 min-w-0">
          <div
            className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
              expired || urgent ? 'bg-white/20' : 'bg-teal-50'
            }`}
          >
            <Icon className={`w-5 h-5 ${expired || urgent ? 'text-white' : 'text-teal-600'}`} />
          </div>
          <div className="min-w-0">
            <p className={`text-sm font-semibold ${expired || urgent ? 'text-white' : 'text-slate-900'}`}>
              {expired ? `${title} — expired` : title}
            </p>
            {subtitle && (
              <p className={`text-xs mt-0.5 truncate ${expired || urgent ? 'text-white/80' : 'text-slate-500'}`}>
                {subtitle}
              </p>
            )}
          </div>
        </div>

        {!expired ? (
          <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
            {countdown.days > 0 && (
              <>
                <TimeBlock value={countdown.days} label="days" urgent={urgent} />
                <span className={`text-xl font-light pb-4 ${urgent ? 'text-white/40' : 'text-slate-300'}`}>:</span>
              </>
            )}
            <TimeBlock value={countdown.hours} label="hrs" urgent={urgent} />
            <span className={`text-xl font-light pb-4 ${urgent ? 'text-white/40' : 'text-slate-300'}`}>:</span>
            <TimeBlock value={countdown.minutes} label="min" urgent={urgent} />
            <span className={`text-xl font-light pb-4 ${urgent ? 'text-white/40' : 'text-slate-300'}`}>:</span>
            <TimeBlock value={countdown.seconds} label="sec" urgent={urgent} />
          </div>
        ) : (
          ctaLabel && ctaTo && (
            <Link
              to={ctaTo}
              className="flex-shrink-0 flex items-center justify-center gap-1.5 bg-white text-red-600 hover:bg-red-50 font-semibold px-4 py-2 rounded-lg text-sm transition-colors"
            >
              {ctaLabel} <ArrowRight className="w-4 h-4" />
            </Link>
          )
        )}
      </div>

      {!expired && ctaLabel && ctaTo && (
        <div className="relative mt-4 flex justify-end">
          <Link
            to={ctaTo}
            className={`flex items-center gap-1.5 text-xs font-semibold transition-colors ${
              urgent ? 'text-white hover:text-white/80' : 'text-teal-600 hover:text-teal-700'
            }`}
          >
            {ctaLabel} <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}
    </div>
  );
}
