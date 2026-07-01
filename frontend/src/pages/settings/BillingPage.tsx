/**
 * Vitar - Billing & Subscription Page
 * Subscription flow: clinic selects plan → sees bank transfer instructions →
 * transfers directly to Vitar owner's account → owner activates via superadmin.
 * No Paystack account required on the clinic side.
 */

import { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  CheckCircle, Zap, Building, AlertCircle, ExternalLink,
  Banknote, Copy, Check, Clock, X,
} from 'lucide-react';
import { billingApi } from '@/lib/api/services';
import { formatNaira } from '@/lib/currency';
import { useAuthStore } from '@/stores/authStore';
import { toast } from 'sonner';

const PLAN_ICONS = { basic: Zap, pro: CheckCircle, enterprise: Building };
const currency = 'NGN';
const formatMoney = formatNaira;

function formatCountdown(ms: number) {
  if (ms <= 0) return '00:00';
  const totalSeconds = Math.floor(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// ── Bank Transfer Instructions Modal ─────────────────────────────────────────

function BankTransferModal({
  data,
  onClose,
  onActivated,
}: {
  data: {
    amount: number;
    currency: string;
    currency_symbol: string;
    plan: string;
    billing_cycle: string;
    reference: string;
    instructions: string;
    expires_at?: string;
    bank_details: { bank_name: string; account_number: string; account_name: string } | null;
  };
  onClose: () => void;
  onActivated: () => void;
}) {
  const [copiedRef, setCopiedRef] = useState(false);
  const [copiedAcc, setCopiedAcc] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const expiresAtMs = data.expires_at ? new Date(data.expires_at).getTime() : null;
  const isAutomated = !!data.expires_at;

  const { data: statusData } = useQuery({
    queryKey: ['billing', 'payment-status', data.reference],
    queryFn: () => billingApi.getPaymentStatus(data.reference),
    enabled: isAutomated,
    refetchInterval: 10_000,
  });
  const status = statusData?.status ?? 'pending';

  // Local 1s ticker for the countdown display.
  useEffect(() => {
    if (!isAutomated) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [isAutomated]);

  useEffect(() => {
    if (status === 'paid') {
      toast.success('Your subscription is now active.');
      onActivated();
    }
  }, [status]);

  function copy(text: string, which: 'ref' | 'acc') {
    navigator.clipboard.writeText(text).then(() => {
      if (which === 'ref') { setCopiedRef(true); setTimeout(() => setCopiedRef(false), 2000); }
      else { setCopiedAcc(true); setTimeout(() => setCopiedAcc(false), 2000); }
    });
  }

  const planLabel = data.plan.charAt(0).toUpperCase() + data.plan.slice(1);
  const cycleLabel = data.billing_cycle === 'monthly' ? '/month' : '/year';
  const remainingMs = expiresAtMs ? expiresAtMs - now : null;
  const isExpired = status === 'expired' || (remainingMs !== null && remainingMs <= 0);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-teal-100 rounded-xl flex items-center justify-center">
              <Banknote className="w-5 h-5 text-teal-700" />
            </div>
            <div>
              <h2 className="font-bold text-slate-900">Complete Your Payment</h2>
              <p className="text-sm text-slate-500">{planLabel} Plan · {data.currency_symbol}{data.amount.toLocaleString()}{cycleLabel}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Paid state */}
        {status === 'paid' && (
          <div className="bg-teal-50 border border-teal-200 rounded-xl p-5 text-center space-y-2">
            <CheckCircle className="w-10 h-10 text-teal-600 mx-auto" />
            <p className="font-semibold text-teal-800">Payment confirmed</p>
            <p className="text-sm text-teal-700">Your subscription is now active.</p>
          </div>
        )}

        {/* Amount mismatch state */}
        {status === 'amount_mismatch' && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-5 text-center space-y-2">
            <AlertCircle className="w-10 h-10 text-red-600 mx-auto" />
            <p className="font-semibold text-red-800">Wrong payment amount detected.</p>
            <p className="text-sm text-red-700">
              Contact support at{' '}
              <a href="mailto:support@vitar.health" className="underline font-medium">support@vitar.health</a>.
            </p>
          </div>
        )}

        {/* Expired state */}
        {isExpired && status !== 'paid' && status !== 'amount_mismatch' && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 text-center space-y-3">
            <Clock className="w-10 h-10 text-amber-600 mx-auto" />
            <p className="font-semibold text-amber-800">Payment session expired</p>
            <p className="text-sm text-amber-700">This payment window has closed.</p>
            <button
              onClick={onClose}
              className="w-full bg-amber-600 hover:bg-amber-700 text-white font-semibold py-2.5 rounded-xl transition-colors text-sm"
            >
              Generate New Payment
            </button>
          </div>
        )}

        {/* Pending: instructions + bank details + countdown */}
        {status === 'pending' && !isExpired && (
          <>
            <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-800 leading-relaxed">
              {data.instructions}
            </div>

            {/* Bank details */}
            {data.bank_details?.account_number ? (
              <div className="bg-slate-50 border border-slate-200 rounded-xl divide-y divide-slate-200">
                <div className="flex justify-between items-center px-4 py-3 text-sm">
                  <span className="text-slate-500">Bank</span>
                  <span className="font-semibold text-slate-900">{data.bank_details.bank_name}</span>
                </div>
                <div className="flex justify-between items-center px-4 py-3 text-sm">
                  <span className="text-slate-500">Account number</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-slate-900 tracking-wider">
                      {data.bank_details.account_number}
                    </span>
                    <button
                      onClick={() => copy(data.bank_details!.account_number, 'acc')}
                      className="text-teal-600 hover:text-teal-800 transition-colors"
                      title="Copy account number"
                    >
                      {copiedAcc ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <div className="flex justify-between items-center px-4 py-3 text-sm">
                  <span className="text-slate-500">Account name</span>
                  <span className="font-semibold text-slate-900">{data.bank_details.account_name}</span>
                </div>
                <div className="flex justify-between items-center px-4 py-3 text-sm">
                  <span className="text-slate-500">Amount</span>
                  <span className="font-bold text-teal-700 text-base">
                    {data.currency_symbol}{data.amount.toLocaleString()}
                  </span>
                </div>
              </div>
            ) : (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
                Bank details not configured yet. Please contact{' '}
                <a href="mailto:support@vitar.health" className="font-medium underline">
                  support@vitar.health
                </a>{' '}
                to complete your subscription.
              </div>
            )}

            {/* Reference */}
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-slate-600 uppercase tracking-wide">
                Payment Reference (use as description)
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 bg-slate-100 border border-slate-200 rounded-lg px-3 py-2.5 text-sm font-mono font-bold text-slate-900 select-all">
                  {data.reference}
                </code>
                <button
                  onClick={() => copy(data.reference, 'ref')}
                  className="shrink-0 inline-flex items-center gap-1.5 border border-slate-200 bg-white rounded-lg px-3 py-2.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                >
                  {copiedRef ? <><Check className="w-3.5 h-3.5 text-teal-600" /> Copied</> : <><Copy className="w-3.5 h-3.5" /> Copy</>}
                </button>
              </div>
            </div>

            {/* Status indicator + countdown */}
            <div className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-xl p-4">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500" />
                </span>
                <p className="text-xs text-slate-600">
                  Waiting for payment — checks automatically every 10s
                </p>
              </div>
              {remainingMs !== null && (
                <span className="text-xs font-mono font-bold text-slate-700">
                  {formatCountdown(remainingMs)}
                </span>
              )}
            </div>
          </>
        )}

        {status === 'pending' && (
          <button
            onClick={onClose}
            className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-2.5 rounded-xl transition-colors text-sm"
          >
            Done — I've made the transfer
          </button>
        )}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function BillingPage() {
  const clinic = useAuthStore((s) => s.clinic);
  const refreshClinic = useAuthStore((s) => s.refreshClinic);
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'annual'>('monthly');
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
  const [transferData, setTransferData] = useState<any>(null);

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
      if (data.payment_method === 'bank_transfer') {
        // Show bank transfer instructions
        setTransferData(data);
      } else if (data.checkout_url) {
        // Fallback: Paystack redirect (if configured)
        window.location.href = data.checkout_url;
      } else {
        toast.success('Subscription activated!');
        refetchSub();
        refreshClinic();
      }
    },
    onError: () => toast.error('Failed to initiate subscription. Please try again.'),
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

      {transferData && (
        <BankTransferModal
          data={transferData}
          onClose={() => { setTransferData(null); refetchSub(); }}
          onActivated={() => { refetchSub(); refreshClinic(); }}
        />
      )}

      <div>
        <h1 className="text-2xl font-bold text-slate-900">Billing & Subscription</h1>
        <p className="text-slate-500 text-sm mt-1">
          Pricing shown in {currency} · Pay via direct bank transfer
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
                onClick={() => { if (confirm('Cancel at end of billing period?')) cancelMutation.mutate(); }}
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
            const isPending = subscribeMutation.isPending && selectedPlan === plan.plan;

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
                    onClick={() => {
                      setSelectedPlan(plan.plan);
                      subscribeMutation.mutate({ plan: plan.plan, cycle: billingCycle });
                    }}
                    disabled={isPending}
                    className={`w-full font-semibold py-2.5 rounded-xl transition-colors flex items-center justify-center gap-2 ${
                      isPopular
                        ? 'bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white'
                        : 'border-2 border-teal-600 text-teal-700 hover:bg-teal-50 disabled:opacity-60'
                    }`}
                  >
                    <Banknote className="w-4 h-4" />
                    {isPending ? 'Loading...' : `Upgrade to ${plan.name}`}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Payment method note */}
      <div className="flex items-center gap-2 text-slate-400 text-xs justify-center">
        <Banknote className="w-4 h-4" />
        <span>
          Pay via direct bank transfer · No card required ·
          Plans activated within 24 hours · Cancel anytime
        </span>
      </div>
    </div>
  );
}
