/**
 * Vitar v5 - Billing Settings Page
 * Region-aware pricing, trial status, subscription management
 */

import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { CheckCircle, Zap, Building, AlertCircle, ExternalLink, CreditCard } from 'lucide-react';
import { billingApi } from '@/lib/api/services';
import { useGeoStore } from '@/stores/geoStore';
import { useAuthStore } from '@/stores/authStore';
import { toast } from 'sonner';

const PLAN_ICONS = { basic: Zap, pro: CheckCircle, enterprise: Building };

export default function BillingPage() {
  const { currency, formatMoney, payment_provider } = useGeoStore();
  const clinic = useAuthStore((s) => s.clinic);
  const refreshClinic = useAuthStore((s) => s.refreshClinic);
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'annual'>('monthly');
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);

  const { data: plansData, isLoading: plansLoading } = useQuery({
    queryKey: ['billing', 'plans', currency],
    queryFn: () => billingApi.getPlans(currency),
  });

  const { data: subData, refetch: refetchSub } = useQuery({
    queryKey: ['billing', 'subscription'],
    queryFn: billingApi.getSubscription,
  });

  const subscribeMutation = useMutation({
    mutationFn: ({ plan, cycle }: { plan: string; cycle: string }) =>
      billingApi.subscribe(plan, cycle),
    onSuccess: (data) => {
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        toast.success('Subscription activated!');
        refetchSub();
        refreshClinic();
      }
    },
    onError: () => toast.error('Failed to start checkout. Please try again.'),
  });

  const cancelMutation = useMutation({
    mutationFn: billingApi.cancel,
    onSuccess: () => {
      toast.success('Subscription will cancel at end of billing period');
      refetchSub();
    },
    onError: () => toast.error('Failed to cancel subscription'),
  });

  const plans = plansData?.plans ?? [];
  const sub = subData?.subscription;
  const trial = subData?.trial;

  const isCurrentPlan = (planKey: string) => sub?.plan === planKey && sub?.status === 'active';

  return (
    <div className="p-6 space-y-8 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Billing & Subscription</h1>
        <p className="text-slate-500 text-sm mt-1">
          Pricing shown in {currency} — based on your region
          {payment_provider === 'paystack' && ' · Payments via Paystack'}
          {payment_provider === 'stripe' && ' · Payments via Stripe'}
        </p>
      </div>

      {/* Trial status card */}
      {trial?.is_trial && (
        <div className={`rounded-xl border p-5 ${trial.is_expired ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'}`}>
          <div className="flex items-start gap-3">
            <AlertCircle className={`w-5 h-5 mt-0.5 ${trial.is_expired ? 'text-red-500' : 'text-amber-500'}`} />
            <div>
              <p className={`font-semibold ${trial.is_expired ? 'text-red-800' : 'text-amber-800'}`}>
                {trial.is_expired ? 'Trial Expired' : `Free Trial — ${trial.days_left} days remaining`}
              </p>
              <p className={`text-sm mt-1 ${trial.is_expired ? 'text-red-700' : 'text-amber-700'}`}>
                {trial.bookings_used}/{trial.bookings_limit} bookings used ·
                Upgrade to unlock unlimited bookings, more doctors, and full AI features
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Active subscription */}
      {sub?.status === 'active' && (
        <div className="bg-teal-50 border border-teal-200 rounded-xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-semibold text-teal-800">
                {sub.plan?.charAt(0).toUpperCase()}{sub.plan?.slice(1)} Plan — Active
              </p>
              <p className="text-teal-700 text-sm mt-0.5">
                {formatMoney(sub.amount ?? 0)}/month ·
                Renews {sub.current_period_end ? new Date(sub.current_period_end).toLocaleDateString() : '—'}
              </p>
            </div>
            {!sub.cancel_at_period_end && (
              <button
                onClick={() => {
                  if (confirm('Cancel at end of billing period?')) cancelMutation.mutate();
                }}
                disabled={cancelMutation.isPending}
                className="text-sm text-red-600 hover:text-red-700 font-medium"
              >
                Cancel plan
              </button>
            )}
            {sub.cancel_at_period_end && (
              <span className="text-sm text-orange-600 font-medium">Cancels at period end</span>
            )}
          </div>
        </div>
      )}

      {/* Billing cycle toggle */}
      <div className="flex items-center justify-center gap-3">
        <button
          onClick={() => setBillingCycle('monthly')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            billingCycle === 'monthly' ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
          }`}
        >
          Monthly
        </button>
        <button
          onClick={() => setBillingCycle('annual')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            billingCycle === 'annual' ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
          }`}
        >
          Annual
          <span className={`text-xs rounded-full px-1.5 py-0.5 ${billingCycle === 'annual' ? 'bg-white text-teal-700' : 'bg-green-100 text-green-700'}`}>
            Save 20%
          </span>
        </button>
      </div>

      {/* Plan cards */}
      {plansLoading ? (
        <div className="text-center py-12 text-slate-400">Loading plans...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {plans.map((plan: any) => {
            const Icon = PLAN_ICONS[plan.plan as keyof typeof PLAN_ICONS] ?? Zap;
            const price = billingCycle === 'monthly' ? plan.monthly : plan.annual;
            const isPopular = plan.plan === 'pro';
            const isCurrent = isCurrentPlan(plan.plan);

            return (
              <div
                key={plan.plan}
                className={`relative bg-white rounded-2xl border-2 p-6 flex flex-col ${
                  isPopular ? 'border-teal-500 shadow-lg' : 'border-slate-200'
                } ${isCurrent ? 'ring-2 ring-teal-400' : ''}`}
              >
                {isPopular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="bg-teal-600 text-white text-xs font-bold px-3 py-1 rounded-full">
                      MOST POPULAR
                    </span>
                  </div>
                )}
                {isCurrent && (
                  <div className="absolute -top-3 right-4">
                    <span className="bg-green-600 text-white text-xs font-bold px-3 py-1 rounded-full">
                      CURRENT PLAN
                    </span>
                  </div>
                )}

                <div className="flex items-center gap-2 mb-4">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${isPopular ? 'bg-teal-100' : 'bg-slate-100'}`}>
                    <Icon className={`w-5 h-5 ${isPopular ? 'text-teal-600' : 'text-slate-600'}`} />
                  </div>
                  <h3 className="font-bold text-slate-900 text-lg">{plan.name}</h3>
                </div>

                <div className="mb-4">
                  {price != null ? (
                    <>
                      <span className="text-3xl font-bold text-slate-900">{formatMoney(price)}</span>
                      <span className="text-slate-500 text-sm">/{billingCycle === 'monthly' ? 'mo' : 'yr'}</span>
                      {billingCycle === 'annual' && plan.annual_savings_percent && (
                        <p className="text-green-600 text-xs font-medium mt-0.5">
                          Save {plan.annual_savings_percent}% vs monthly
                        </p>
                      )}
                    </>
                  ) : (
                    <span className="text-2xl font-bold text-slate-900">Custom</span>
                  )}
                </div>

                <ul className="space-y-2 flex-1 mb-6">
                  {(plan.features ?? []).map((f: string) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-slate-600">
                      <CheckCircle className="w-4 h-4 text-teal-500 mt-0.5 flex-shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>

                {plan.plan === 'enterprise' ? (
                  <a
                    href="mailto:sales@vitar.health"
                    className="flex items-center justify-center gap-2 border-2 border-slate-300 hover:border-teal-500 text-slate-700 hover:text-teal-700 font-semibold py-2.5 rounded-xl transition-colors"
                  >
                    Contact Sales <ExternalLink className="w-4 h-4" />
                  </a>
                ) : isCurrent ? (
                  <button
                    disabled
                    className="w-full bg-green-100 text-green-700 font-semibold py-2.5 rounded-xl cursor-default"
                  >
                    ✓ Current Plan
                  </button>
                ) : (
                  <button
                    onClick={() => subscribeMutation.mutate({ plan: plan.plan, cycle: billingCycle })}
                    disabled={subscribeMutation.isPending && selectedPlan === plan.plan}
                    className={`w-full font-semibold py-2.5 rounded-xl transition-colors ${
                      isPopular
                        ? 'bg-teal-600 hover:bg-teal-700 text-white'
                        : 'border-2 border-teal-600 text-teal-700 hover:bg-teal-50'
                    }`}
                    onMouseEnter={() => setSelectedPlan(plan.plan)}
                  >
                    {subscribeMutation.isPending && selectedPlan === plan.plan
                      ? 'Starting checkout...'
                      : price != null
                      ? `Upgrade to ${plan.name}`
                      : 'Get started'}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Payment method note */}
      <div className="flex items-center gap-2 text-slate-400 text-xs justify-center">
        <CreditCard className="w-4 h-4" />
        <span>
          Secure payments via {payment_provider === 'paystack' ? 'Paystack' : 'Stripe'} ·
          Cancel anytime · No hidden fees
        </span>
      </div>
    </div>
  );
}
