/**
 * Vitar — Live Countdown Hook
 * Ticks down to a target ISO timestamp and returns a structured breakdown
 * (days / hours / minutes / seconds) plus convenience flags. Used by the
 * dashboard's trial, appointment, and renewal countdown cards.
 */

import { useEffect, useState } from 'react';

export interface CountdownBreakdown {
  totalMs: number;
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
  isPast: boolean;
}

function computeBreakdown(targetMs: number): CountdownBreakdown {
  const diff = targetMs - Date.now();
  const isPast = diff <= 0;
  const totalMs = Math.max(diff, 0);

  const days = Math.floor(totalMs / (1000 * 60 * 60 * 24));
  const hours = Math.floor((totalMs / (1000 * 60 * 60)) % 24);
  const minutes = Math.floor((totalMs / (1000 * 60)) % 60);
  const seconds = Math.floor((totalMs / 1000) % 60);

  return { totalMs, days, hours, minutes, seconds, isPast };
}

/**
 * @param targetIso ISO timestamp string to count down to. Pass null/undefined
 *   to disable the timer (returns null).
 * @param tickMs how often to recompute. Defaults to 1000ms (per-second).
 *   Pass 60_000 for a minute-granularity countdown (cheaper for long timers).
 */
export function useCountdown(targetIso: string | null | undefined, tickMs = 1000): CountdownBreakdown | null {
  const targetMs = targetIso ? new Date(targetIso).getTime() : null;
  const [breakdown, setBreakdown] = useState<CountdownBreakdown | null>(
    targetMs ? computeBreakdown(targetMs) : null
  );

  useEffect(() => {
    if (!targetMs) {
      setBreakdown(null);
      return;
    }
    setBreakdown(computeBreakdown(targetMs));
    const id = setInterval(() => setBreakdown(computeBreakdown(targetMs)), tickMs);
    return () => clearInterval(id);
  }, [targetMs, tickMs]);

  return breakdown;
}
