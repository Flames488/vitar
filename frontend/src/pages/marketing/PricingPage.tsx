/**
 * Vitar v5 - Pricing Page
 * Auto-detects region and shows local pricing
 */
import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle, Building, Zap, Globe } from 'lucide-react';
import { useGeoStore } from '@/stores/geoStore';

const PLAN_FEATURES = {
  basic: [
    'Up to 2 doctors',
    '200 bookings/month',
    'SMS & Email reminders',
    'Basic no-show analytics',
    'Public booking page',
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

const PLAN_ICONS = { basic: Zap, pro: CheckCircle, enterprise: Building };

export default function PricingPage() {
  const { currency, currency_format, plans, detect, detected } = useGeoStore();

  useEffect(() => {
    if (!detected) detect();
  }, []);

  const formatPrice = (amount: number | null) => {
    if (amount == null) return 'Custom';
    const sym = currency_format?.symbol ?? '₦';
    const dec = currency_format?.decimals ?? 0;
    if (dec === 0) return `${sym}${Math.round(amount).toLocaleString()}`;
    return `${sym}${amount.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec })}`;
  };

  return (
    <div className="py-20 px-4 bg-white">
      <div className="max-w-5xl mx-auto">

        {/* Header */}
        <div className="text-center mb-4">
          <h1 className="text-4xl font-extrabold text-slate-900">Simple, Transparent Pricing</h1>
          <p className="text-slate-500 text-lg mt-3">
            14-day free trial included. No credit card required.
          </p>
          <div className="inline-flex items-center gap-1.5 bg-teal-50 border border-teal-200 text-teal-700 text-sm px-3 py-1.5 rounded-full mt-3">
            <Globe className="w-3.5 h-3.5" />
            Showing prices in <strong>{currency}</strong> for your region
          </div>
        </div>

        {/* Plans */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12">
          {(plans.length > 0 ? plans : [
            { plan: 'basic',      name: 'Starter',    monthly: 2500,  annual: 25000, annual_savings_percent: 17, features: PLAN_FEATURES.basic },
            { plan: 'pro',        name: 'Pro',        monthly: 7500,  annual: 75000, annual_savings_percent: 17, features: PLAN_FEATURES.pro, popular: true },
            { plan: 'enterprise', name: 'Enterprise', monthly: null,  annual: null,  features: PLAN_FEATURES.enterprise },
          ]).map((plan: any) => {
            const Icon = PLAN_ICONS[plan.plan as keyof typeof PLAN_ICONS] ?? Zap;
            const isPopular = plan.plan === 'pro';
            const features = (plan.features as string[]) ?? PLAN_FEATURES[plan.plan as keyof typeof PLAN_FEATURES] ?? [];

            return (
              <div key={plan.plan} className={`relative bg-white rounded-2xl border-2 p-7 flex flex-col ${isPopular ? 'border-teal-500 shadow-xl' : 'border-slate-200'}`}>
                {isPopular && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                    <span className="bg-teal-600 text-white text-xs font-bold px-4 py-1 rounded-full">MOST POPULAR</span>
                  </div>
                )}

                <div className="flex items-center gap-3 mb-5">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${isPopular ? 'bg-teal-100' : 'bg-slate-100'}`}>
                    <Icon className={`w-5 h-5 ${isPopular ? 'text-teal-600' : 'text-slate-600'}`} />
                  </div>
                  <h3 className="text-xl font-bold text-slate-900">{plan.name}</h3>
                </div>

                <div className="mb-6">
                  {plan.monthly != null ? (
                    <>
                      <div className="flex items-end gap-1">
                        <span className="text-4xl font-extrabold text-slate-900">{formatPrice(plan.monthly)}</span>
                        <span className="text-slate-500 text-sm mb-1">/month</span>
                      </div>
                      {plan.annual != null && (
                        <p className="text-green-600 text-sm font-medium mt-1">
                          or {formatPrice(plan.annual)}/year — save {plan.annual_savings_percent ?? 17}%
                        </p>
                      )}
                    </>
                  ) : (
                    <div className="text-4xl font-extrabold text-slate-900">
                      {plan.plan === 'enterprise' ? 'Custom' : '—'}
                    </div>
                  )}
                  <p className="text-slate-400 text-xs mt-1">14-day free trial · Cancel anytime</p>
                </div>

                <ul className="space-y-2.5 flex-1 mb-7">
                  {features.map((f: string) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-slate-600">
                      <CheckCircle className="w-4 h-4 text-teal-500 flex-shrink-0 mt-0.5" />
                      {f}
                    </li>
                  ))}
                </ul>

                {plan.plan === 'enterprise' ? (
                  <a href="mailto:sales@vitar.health"
                    className="block text-center border-2 border-slate-300 hover:border-teal-500 text-slate-700 hover:text-teal-700 font-semibold py-3 rounded-xl transition-colors">
                    Contact Sales
                  </a>
                ) : (
                  <Link to="/register"
                    className={`block text-center font-bold py-3 rounded-xl transition-colors ${
                      isPopular ? 'bg-teal-600 hover:bg-teal-700 text-white' : 'border-2 border-teal-600 text-teal-700 hover:bg-teal-50'
                    }`}>
                    Start Free Trial
                  </Link>
                )}
              </div>
            );
          })}
        </div>

        {/* FAQ */}
        <div className="mt-20">
          <h2 className="text-2xl font-bold text-slate-900 text-center mb-8">Frequently Asked Questions</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 max-w-3xl mx-auto">
            {[
              { q: 'Do I need a credit card to start?', a: 'No. Your 14-day free trial starts immediately — no card required. You only need payment details when upgrading.' },
              { q: 'Can I cancel anytime?', a: 'Yes. Cancel before your trial ends and you won\'t be charged. Paid plans can be cancelled at any time, effective at end of billing period.' },
              { q: 'What payment methods are supported?', a: 'Nigeria: Paystack and Flutterwave (cards, bank transfer, USSD). Global: Stripe (Visa, Mastercard, AMEX).' },
              { q: 'How does the AI prediction work?', a: 'Vitar analyses patient history, appointment timing, lead time, and behavioural signals to score each appointment\'s no-show risk from 0–100%.' },
              { q: 'Does Vitar guarantee 0 no-shows?', a: 'No — that would be unrealistic. We target a 40–70% reduction in no-show rates, verified by your analytics dashboard.' },
              { q: 'Can I add more doctors later?', a: 'Yes. Upgrade your plan any time to unlock more doctor seats.' },
            ].map(({ q, a }) => (
              <div key={q} className="bg-slate-50 rounded-xl p-5">
                <p className="font-semibold text-slate-900 mb-2">{q}</p>
                <p className="text-slate-500 text-sm leading-relaxed">{a}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
