/**
 * Vitar v5 - Landing Page
 */
import { Link } from 'react-router-dom';
import { Brain, Bell, BarChart3, Shield, CheckCircle, Zap, Globe } from 'lucide-react';

const FEATURES = [
  { icon: Brain,    title: 'AI No-Show Prediction',   desc: 'Machine learning scores each appointment 0–100% risk. Target 40–70% fewer no-shows.' },
  { icon: Bell,     title: 'Smart Multi-Channel Reminders', desc: 'SMS, WhatsApp, and Email reminders timed by risk score. High-risk patients get more touchpoints.' },
  { icon: Zap,      title: 'Auto Slot Refill',         desc: 'When a patient cancels, waiting list patients are notified instantly to fill the gap.' },
  { icon: BarChart3,title: 'Revenue Recovery Dashboard', desc: 'See exactly how much revenue Vitar\'s reminders have saved your clinic this month.' },
  { icon: Globe,    title: 'Multi-Region Pricing',     desc: 'Priced for Nigeria, UK, US, and more. Pay with Paystack, Stripe, or Flutterwave.' },
  { icon: Shield,   title: 'No Double-Booking',        desc: 'Transaction-level slot locking prevents double-booking even under concurrent load.' },
];

const STATS = [
  { value: '40–70%', label: 'No-show reduction' },
  { value: '< 10min', label: 'Clinic setup time' },
  { value: '3 channels', label: 'SMS · WhatsApp · Email' },
  { value: '14 days', label: 'Free trial' },
];

export default function LandingPage() {
  return (
    <div className="bg-white">
      {/* Hero */}
      <section className="relative overflow-hidden bg-gradient-to-br from-slate-900 via-teal-900 to-slate-900 text-white py-24 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-teal-500/20 border border-teal-500/30 text-teal-300 text-sm px-4 py-1.5 rounded-full mb-6">
            <Brain className="w-3.5 h-3.5" />
            AI-powered no-show reduction for clinics
          </div>
          <h1 className="text-4xl sm:text-6xl font-extrabold leading-tight mb-6">
            Stop Losing Revenue<br />
            <span className="text-teal-400">to No-Shows</span>
          </h1>
          <p className="text-slate-300 text-lg sm:text-xl max-w-2xl mx-auto mb-10">
            Vitar predicts which patients will no-show and automatically sends smart reminders —
            reducing no-shows by 40–70% and recovering thousands in lost revenue each month.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/register"
              className="w-full sm:w-auto bg-teal-500 hover:bg-teal-400 text-white font-bold px-8 py-4 rounded-xl text-lg transition-colors">
              Start Free 30-day Trial →
            </Link>
            <Link to="/pricing"
              className="w-full sm:w-auto border border-white/20 hover:border-white/40 text-white px-8 py-4 rounded-xl text-lg transition-colors">
              View Pricing
            </Link>
          </div>
          <p className="text-slate-500 text-sm mt-4">No credit card required · Set up in under 10 minutes</p>
        </div>
      </section>

      {/* Stats */}
      <section className="bg-teal-600 text-white py-10 px-4">
        <div className="max-w-4xl mx-auto grid grid-cols-2 sm:grid-cols-4 gap-6 text-center">
          {STATS.map(({ value, label }) => (
            <div key={label}>
              <p className="text-3xl font-extrabold">{value}</p>
              <p className="text-teal-200 text-sm mt-1">{label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold text-slate-900">Everything your clinic needs</h2>
            <p className="text-slate-500 mt-3 text-lg">From AI prediction to automated reminders to revenue analytics</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="bg-slate-50 rounded-2xl p-6 hover:shadow-md transition-shadow">
                <div className="w-10 h-10 bg-teal-100 rounded-xl flex items-center justify-center mb-4">
                  <Icon className="w-5 h-5 text-teal-600" />
                </div>
                <h3 className="font-bold text-slate-900 mb-2">{title}</h3>
                <p className="text-slate-500 text-sm leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-slate-50 py-20 px-4">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-slate-900 mb-12">How Vitar Works</h2>
          <div className="space-y-6">
            {[
              { step: '01', title: 'Clinic registers & onboards', desc: 'Add doctors, set availability, connect your booking page — under 10 minutes.' },
              { step: '02', title: 'Patients book online or staff books manually', desc: 'Public booking page or in-dashboard manual entry. No-show risk is calculated instantly.' },
              { step: '03', title: 'AI scores each appointment', desc: 'Risk model analyses history, timing, behaviour. High-risk patients get more reminders.' },
              { step: '04', title: 'Smart reminders sent automatically', desc: 'SMS, WhatsApp, and Email reminders fire at optimal times. Zero manual work.' },
              { step: '05', title: 'Dashboard shows recovered revenue', desc: 'Track no-show rates, reminder effectiveness, and revenue saved each month.' },
            ].map(({ step, title, desc }) => (
              <div key={step} className="flex items-start gap-4 text-left bg-white rounded-xl p-5 shadow-sm">
                <div className="w-10 h-10 bg-teal-600 text-white rounded-full flex items-center justify-center font-bold text-sm flex-shrink-0">
                  {step}
                </div>
                <div>
                  <p className="font-semibold text-slate-900">{title}</p>
                  <p className="text-slate-500 text-sm mt-0.5">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-teal-700 text-white py-20 px-4 text-center">
        <h2 className="text-3xl font-bold mb-4">Ready to stop losing revenue to no-shows?</h2>
        <p className="text-teal-200 mb-8 text-lg">Join clinics across Nigeria, UK, and beyond using Vitar AI.</p>
        <Link to="/register"
          className="inline-block bg-white text-teal-700 font-bold px-10 py-4 rounded-xl text-lg hover:bg-teal-50 transition-colors">
          Start Free Trial — No Card Required
        </Link>
      </section>
    </div>
  );
}
