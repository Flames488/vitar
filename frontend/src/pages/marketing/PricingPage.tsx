/**
 * Vitar — Pricing Page (redesigned)
 * Free Trial card (dark, full-width) + 3 paid plan cards below
 * Paid plans trigger real Paystack checkout via billingApi.subscribe
 */
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  CheckCircle, Building, Zap, Globe, Sparkles,
  ArrowRight, Shield, Clock, CreditCard,
} from 'lucide-react';
import { useGeoStore } from '@/stores/geoStore';
import { useAuthStore } from '@/stores/authStore';
import { billingApi } from '@/lib/api/services';
import { toast } from 'sonner';

const TRIAL_FEATURES = [
  '30 days full access — no card required',
  'Up to 2 doctors',
  '50 bookings during trial',
  'Appointment scheduling',
  'Patient management',
  'Public booking page & QR code',
  'Email & SMS reminders',
];

const PLAN_FEATURES = {
  basic: [
    'Up to 2 doctors',
    '200 bookings/month',
    'SMS & Email reminders',
    'Basic no-show analytics',
    'Public booking page',
    'QR code patient check-in',
    'Email support',
  ],
  pro: [
    'Up to 10 doctors',
    '2,000 bookings/month',
    'SMS, WhatsApp & Email',
    'AI no-show prediction',
    'Smart reminder engine',
    'Auto slot refill',
    'Waiting list management',
    'Advanced analytics',
    'Revenue recovery dashboard',
    'Priority support',
  ],
  enterprise: [
    'Unlimited doctors',
    'Unlimited bookings',
    'All Pro features',
    'Dedicated account manager',
    'Custom integrations',
    'SLA guarantee',
    'Custom branding',
    'On-site training',
  ],
};

const FAQ = [
  { q: 'Do I need a credit card to start?', a: 'No. Your 30-day free trial starts immediately — no card required. You only need payment details when upgrading to a paid plan.' },
  { q: 'Can I cancel anytime?', a: 'Yes. Cancel before your trial ends and you won\'t be charged. Paid plans can be cancelled at any time, effective at end of billing period.' },
  { q: 'What payment methods are supported?', a: 'Nigeria: Paystack (cards, bank transfer, USSD). Global: Stripe (Visa, Mastercard, AMEX).' },
  { q: 'How does the AI prediction work?', a: 'Vitar analyses patient history, appointment timing, lead time, and behavioural signals to score each appointment\'s no-show risk from 0–100%.' },
  { q: 'Does Vitar guarantee 0 no-shows?', a: 'No — that would be unrealistic. We target a 40–70% reduction in no-show rates, verified by your analytics dashboard.' },
  { q: 'Can I upgrade mid-trial?', a: 'Yes. Upgrade any time during your trial and billing starts from that date. Unused trial days are not carried over.' },
];

export default function PricingPage() {
  const { currency, currency_format, plans, detect, detected } = useGeoStore();
  const { isAuthenticated } = useAuthStore();
  const navigate = useNavigate();
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'annual'>('monthly');
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);

  useEffect(() => { if (!detected) detect(); }, []);

  const formatPrice = (amount: number | null) => {
    if (amount == null) return 'Custom';
    const sym = currency_format?.symbol ?? '₦';
    const dec = currency_format?.decimals ?? 0;
    if (dec === 0) return `${sym}${Math.round(amount).toLocaleString()}`;
    return `${sym}${amount.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec })}`;
  };

  const handleSubscribe = async (planKey: string) => {
    if (!isAuthenticated) { navigate('/register'); return; }
    setLoadingPlan(planKey);
    try {
      const data = await billingApi.subscribe(planKey, billingCycle);
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        toast.success('Subscription activated!');
        navigate('/settings/billing');
      }
    } catch {
      toast.error('Failed to start checkout. Please try again.');
    } finally {
      setLoadingPlan(null);
    }
  };

  const paidPlans = (plans.length > 0 ? plans : [
    { plan: 'basic',      name: 'Starter',    monthly: 2500,  annual: 25000, annual_savings_percent: 17, features: PLAN_FEATURES.basic },
    { plan: 'pro',        name: 'Pro',        monthly: 7500,  annual: 75000, annual_savings_percent: 17, features: PLAN_FEATURES.pro },
    { plan: 'enterprise', name: 'Enterprise', monthly: null,  annual: null,  features: PLAN_FEATURES.enterprise },
  ]).filter((p: any) => p.plan !== 'trial');

  return (
    <div className="min-h-screen bg-slate-50">

      {/* ── Hero header ── */}
      <div className="bg-white border-b border-slate-100">
        <div className="max-w-5xl mx-auto px-4 py-16 text-center">
          <div className="inline-flex items-center gap-2 bg-teal-50 border border-teal-200 text-teal-700 text-xs font-semibold px-3 py-1.5 rounded-full mb-5">
            <Globe className="w-3.5 h-3.5" />
            Prices shown in <strong className="ml-1">{currency}</strong>
          </div>
          <h1 className="text-4xl sm:text-5xl font-extrabold text-slate-900 tracking-tight">
            Simple, transparent pricing
          </h1>
          <p className="text-slate-500 text-lg mt-4 max-w-xl mx-auto">
            Start free for 30 days. No credit card. Upgrade when you're ready.
          </p>

          {/* Billing toggle */}
          <div className="inline-flex items-center mt-8 bg-slate-100 rounded-xl p-1 gap-1">
            <button
              onClick={() => setBillingCycle('monthly')}
              className={`px-5 py-2 rounded-lg text-sm font-semibold transition-all ${
                billingCycle === 'monthly'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => setBillingCycle('annual')}
              className={`px-5 py-2 rounded-lg text-sm font-semibold transition-all flex items-center gap-2 ${
                billingCycle === 'annual'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Annual
              <span className="bg-green-100 text-green-700 text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                SAVE 17%
              </span>
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-12 space-y-10">

        {/* ── FREE TRIAL card (dark, full-width, visually separate) ── */}
        <div
          className="relative rounded-2xl p-8 overflow-hidden"
          style={{
            background: 'linear-gradient(135deg, #0f172a 0%, #134e4a 100%)',
            boxShadow: '0 8px 40px rgba(13,148,136,0.18)',
          }}
        >
          <div
            className="absolute -top-20 -right-20 w-72 h-72 rounded-full opacity-10 pointer-events-none"
            style={{ background: 'radial-gradient(circle, #2dd4bf, transparent)' }}
          />
          <div className="relative flex flex-col lg:flex-row lg:items-center gap-8">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'rgba(45,212,191,0.15)', border: '1px solid rgba(45,212,191,0.25)' }}>
                  <Sparkles className="w-5 h-5 text-teal-400" />
                </div>
                <div>
                  <p className="text-teal-400 text-[10px] font-extrabold uppercase tracking-widest">Free — No card needed</p>
                  <h2 className="text-white text-2xl font-extrabold leading-tight">30-Day Full Access Trial</h2>
                </div>
              </div>
              <p className="text-slate-300 text-sm mb-6 max-w-lg leading-relaxed">
                Experience every core feature of Vitar — no payment details, no commitment.
                Most Nigerian clinics are fully set up and seeing results within the first week.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-2 gap-x-4">
                {TRIAL_FEATURES.map(f => (
                  <div key={f} className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-teal-400 flex-shrink-0" />
                    <span className="text-slate-300 text-sm">{f}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex-shrink-0 text-center">
              <div className="mb-4">
                <span className="text-6xl font-extrabold text-white">₦0</span>
                <p className="text-teal-300 text-sm font-semibold mt-1">Free for 30 days</p>
              </div>
              <Link
                to="/register"
                className="inline-flex items-center gap-2 text-white font-bold px-8 py-3.5 rounded-xl transition-all hover:scale-[1.02] active:scale-[0.98]"
                style={{
                  background: 'linear-gradient(90deg, #0d9488, #0891b2)',
                  boxShadow: '0 4px 20px rgba(13,148,136,0.4)',
                }}
              >
                Start Free Trial
                <ArrowRight className="w-4 h-4" />
              </Link>
              <p className="text-slate-500 text-xs mt-3 flex items-center justify-center gap-1">
                <Shield className="w-3 h-3" />
                No credit card · Cancel anytime
              </p>
            </div>
          </div>
        </div>

        {/* ── Section divider ── */}
        <div className="flex items-center gap-4">
          <div className="flex-1 h-px bg-slate-200" />
          <p className="text-slate-400 text-xs font-semibold uppercase tracking-widest whitespace-nowrap">
            Paid plans — upgrade when ready
          </p>
          <div className="flex-1 h-px bg-slate-200" />
        </div>

        {/* ── Paid plan cards ── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {paidPlans.map((plan: any) => {
            const isPopular = plan.plan === 'pro';
            const isEnterprise = plan.plan === 'enterprise';
            const features = (plan.features as string[]) ?? PLAN_FEATURES[plan.plan as keyof typeof PLAN_FEATURES] ?? [];
            const price = billingCycle === 'annual' ? plan.annual : plan.monthly;
            const isLoading = loadingPlan === plan.plan;

            return (
              <div
                key={plan.plan}
                className={`relative bg-white rounded-2xl flex flex-col transition-all hover:shadow-lg ${
                  isPopular
                    ? 'border-2 border-teal-500 shadow-xl shadow-teal-500/10'
                    : 'border border-slate-200 shadow-sm'
                }`}
              >
                {isPopular && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                    <span
                      className="text-white text-[10px] font-extrabold px-4 py-1 rounded-full tracking-widest"
                      style={{ background: 'linear-gradient(90deg, #0d9488, #0891b2)' }}
                    >
                      MOST POPULAR
                    </span>
                  </div>
                )}

                <div className="p-6 pb-0 flex-1">
                  {/* Plan header */}
                  <div className="flex items-center gap-3 mb-5">
                    <div
                      className="w-9 h-9 rounded-xl flex items-center justify-center"
                      style={isPopular
                        ? { background: 'rgba(13,148,136,0.1)', border: '1px solid rgba(13,148,136,0.2)' }
                        : { background: '#f8fafc', border: '1px solid #e2e8f0' }
                      }
                    >
                      {isEnterprise
                        ? <Building className="w-4 h-4 text-slate-500" />
                        : isPopular
                          ? <Sparkles className="w-4 h-4 text-teal-600" />
                          : <Zap className="w-4 h-4 text-slate-500" />
                      }
                    </div>
                    <div>
                      <h3 className="font-bold text-slate-900 text-base">{plan.name}</h3>
                      <p className="text-xs text-slate-400">
                        {isEnterprise ? 'For hospital groups' : isPopular ? 'Best for growing clinics' : 'For small clinics'}
                      </p>
                    </div>
                  </div>

                  {/* Price */}
                  <div className="mb-5">
                    {price != null ? (
                      <>
                        <div className="flex items-end gap-1">
                          <span className="text-3xl font-extrabold text-slate-900">{formatPrice(price)}</span>
                          <span className="text-slate-400 text-sm mb-1">/{billingCycle === 'annual' ? 'yr' : 'mo'}</span>
                        </div>
                        {billingCycle === 'monthly' && plan.annual != null && (
                          <p className="text-green-600 text-xs font-medium mt-0.5">
                            Save {plan.annual_savings_percent ?? 17}% with annual billing
                          </p>
                        )}
                        {billingCycle === 'annual' && plan.monthly != null && (
                          <p className="text-slate-400 text-xs mt-0.5">
                            {formatPrice(Math.round(price / 12))}/mo billed annually
                          </p>
                        )}
                      </>
                    ) : (
                      <div>
                        <span className="text-3xl font-extrabold text-slate-900">Custom</span>
                        <p className="text-slate-400 text-xs mt-0.5">Contact us for a quote</p>
                      </div>
                    )}
                  </div>

                  {/* Features */}
                  <ul className="space-y-2.5 pb-6">
                    {features.map((f: string) => (
                      <li key={f} className="flex items-start gap-2 text-sm text-slate-600">
                        <CheckCircle className="w-4 h-4 text-teal-500 flex-shrink-0 mt-0.5" />
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* CTA */}
                <div className="p-5 pt-0">
                  {isEnterprise ? (
                    <a
                      href="mailto:sales@vitar.health"
                      className="flex items-center justify-center gap-2 w-full border-2 border-slate-200 hover:border-teal-500 text-slate-600 hover:text-teal-700 font-semibold py-3 rounded-xl transition-all text-sm"
                    >
                      Contact Sales
                      <ArrowRight className="w-4 h-4" />
                    </a>
                  ) : (
                    <>
                      <button
                        onClick={() => handleSubscribe(plan.plan)}
                        disabled={isLoading}
                        className={`flex items-center justify-center gap-2 w-full font-bold py-3 rounded-xl transition-all text-sm disabled:opacity-60 disabled:cursor-not-allowed active:scale-[0.98] ${
                          isPopular ? 'text-white' : 'border-2 border-teal-600 text-teal-700 hover:bg-teal-50'
                        }`}
                        style={isPopular ? {
                          background: 'linear-gradient(90deg, #0d9488, #0891b2)',
                          boxShadow: '0 4px 16px rgba(13,148,136,0.3)',
                        } : {}}
                      >
                        {isLoading ? (
                          <>
                            <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                            </svg>
                            Processing…
                          </>
                        ) : (
                          <>
                            <CreditCard className="w-4 h-4" />
                            Subscribe · {formatPrice(price)}/{billingCycle === 'annual' ? 'yr' : 'mo'}
                          </>
                        )}
                      </button>
                      <p className="text-center text-slate-400 text-[11px] mt-2 flex items-center justify-center gap-1">
                        <Clock className="w-3 h-3" />
                        30-day trial included · Cancel anytime
                      </p>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* ── Trust signals ── */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            { icon: Shield,     title: 'Secure payments',        desc: 'Paystack & Stripe — bank-grade encryption on every transaction' },
            { icon: Clock,      title: 'Cancel anytime',         desc: 'No lock-in contracts. Cancel before your next billing date.' },
            { icon: CreditCard, title: 'Local payment methods',  desc: 'Cards, bank transfer, USSD — all supported in Nigeria' },
          ].map(({ icon: Icon, title, desc }) => (
            <div key={title} className="flex items-start gap-3 bg-white rounded-xl p-4 border border-slate-100 shadow-sm">
              <div className="w-8 h-8 rounded-lg bg-teal-50 flex items-center justify-center flex-shrink-0">
                <Icon className="w-4 h-4 text-teal-600" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800">{title}</p>
                <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>

        {/* ── FAQ ── */}
        <div className="pt-4">
          <h2 className="text-2xl font-bold text-slate-900 text-center mb-8">Frequently Asked Questions</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-3xl mx-auto">
            {FAQ.map(({ q, a }) => (
              <div key={q} className="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
                <p className="font-semibold text-slate-900 mb-2 text-sm">{q}</p>
                <p className="text-slate-500 text-sm leading-relaxed">{a}</p>
              </div>
            ))}
          </div>
        </div>

        {/* ── Bottom CTA ── */}
        <div
          className="rounded-2xl p-10 text-center"
          style={{ background: 'linear-gradient(135deg, #0f172a 0%, #134e4a 100%)' }}
        >
          <h3 className="text-2xl font-extrabold text-white mb-2">Ready to cut no-shows by 40%?</h3>
          <p className="text-slate-400 text-sm mb-6 max-w-md mx-auto">
            Join clinics across Nigeria using Vitar to run smarter, more efficient practices.
          </p>
          <Link
            to="/register"
            className="inline-flex items-center gap-2 text-white font-bold px-8 py-3.5 rounded-xl transition-all hover:scale-[1.02] active:scale-[0.98]"
            style={{
              background: 'linear-gradient(90deg, #0d9488, #0891b2)',
              boxShadow: '0 4px 20px rgba(13,148,136,0.4)',
            }}
          >
            Start Your 30-Day Free Trial
            <ArrowRight className="w-4 h-4" />
          </Link>
          <p className="text-slate-500 text-xs mt-3">No credit card required</p>
        </div>

      </div>
    </div>
  );
}
