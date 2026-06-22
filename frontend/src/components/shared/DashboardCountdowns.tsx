/**
 * Vitar — Dashboard Countdown Strip
 * Surfaces up to three live countdowns on the clinic dashboard:
 *   1. Trial expiry      (highest priority — only shown while clinic is on trial)
 *   2. Next appointment  (next upcoming appointment today/this week)
 *   3. Subscription renewal (only shown for active paid subscriptions)
 *
 * Each is rendered as its own CountdownCard. Cards stack on mobile and
 * sit side-by-side on wider screens.
 */

import CountdownCard from '@/components/shared/CountdownCard';

interface TrialInfo {
  is_trial: boolean;
  trial_ends_at: string | null;
  is_expired: boolean;
  bookings_used: number;
  bookings_limit: number;
}

interface NextAppointmentInfo {
  scheduled_at: string;
  doctor_name?: string;
  patient_name?: string;
}

interface RenewalInfo {
  current_period_end: string | null;
  plan?: string;
  status?: string;
}

interface DashboardCountdownsProps {
  trial?: TrialInfo | null;
  nextAppointment?: NextAppointmentInfo | null;
  renewal?: RenewalInfo | null;
}

export default function DashboardCountdowns({ trial, nextAppointment, renewal }: DashboardCountdownsProps) {
  const showTrial = !!trial?.is_trial && !!trial.trial_ends_at;
  const showAppointment = !!nextAppointment?.scheduled_at;
  const showRenewal = !!renewal?.current_period_end && renewal?.status === 'active';

  if (!showTrial && !showAppointment && !showRenewal) return null;

  const cardCount = [showTrial, showAppointment, showRenewal].filter(Boolean).length;

  return (
    <div
      className={`grid gap-3 sm:gap-4 ${
        cardCount === 1 ? 'grid-cols-1' : cardCount === 2 ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1 lg:grid-cols-3'
      }`}
    >
      {showTrial && (
        <CountdownCard
          variant="trial"
          targetIso={trial!.trial_ends_at}
          title="Free trial ends in"
          subtitle={`${trial!.bookings_used}/${trial!.bookings_limit} bookings used`}
          ctaLabel="Upgrade plan"
          ctaTo="/settings/billing"
          urgentBelowHours={24}
        />
      )}

      {showAppointment && (
        <CountdownCard
          variant="appointment"
          targetIso={nextAppointment!.scheduled_at}
          title="Next appointment"
          subtitle={
            nextAppointment!.doctor_name && nextAppointment!.patient_name
              ? `${nextAppointment!.patient_name} with Dr. ${nextAppointment!.doctor_name}`
              : nextAppointment!.patient_name ?? nextAppointment!.doctor_name
          }
          ctaLabel="View appointments"
          ctaTo="/appointments"
          urgentBelowHours={1}
        />
      )}

      {showRenewal && (
        <CountdownCard
          variant="renewal"
          targetIso={renewal!.current_period_end}
          title="Plan renews in"
          subtitle={renewal!.plan ? `${renewal!.plan.charAt(0).toUpperCase()}${renewal!.plan.slice(1)} plan` : undefined}
          ctaLabel="Manage billing"
          ctaTo="/settings/billing"
          urgentBelowHours={24}
        />
      )}
    </div>
  );
}
