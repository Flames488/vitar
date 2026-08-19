/**
 * Vitar — Feedback Page
 * Converted from the LiveVault static demo site's feedback.html.
 * Submits to the same Google Form the demo site used (see
 * src/lib/marketingForms.ts) — no backend changes required, and no
 * loss of functionality versus the static version.
 */
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import MarketingSubpageChrome from '@/components/marketing/MarketingSubpageChrome';
import { submitFeedback } from '@/lib/marketingForms';
import { VITAR_SUPPORT_EMAIL } from '@/lib/contact';
import '@/styles/landing.css';

export default function FeedbackPage() {
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [clinicName, setClinicName] = useState('');
  const [email, setEmail] = useState('');
  const [noShowRate, setNoShowRate] = useState('');
  const [currentTool, setCurrentTool] = useState('');
  const [whoBooks, setWhoBooks] = useState('');
  const [willingnessToPay, setWillingnessToPay] = useState('');
  const [extraNotes, setExtraNotes] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!clinicName.trim()) return;
    setSubmitting(true);
    await submitFeedback({ clinicName, email, noShowRate, currentTool, whoBooks, willingnessToPay, extraNotes });
    setSubmitting(false);
    setSubmitted(true);
  };

  return (
    <div className="lv-marketing lv-feedback">
      <MarketingSubpageChrome
        footerLinks={[
          { label: 'Home', to: '/' },
          { label: 'Sign up', to: '/register' },
          { label: VITAR_SUPPORT_EMAIL, href: `mailto:${VITAR_SUPPORT_EMAIL}` },
        ]}
      >
        <section className="hero">
          <div className="hero-badge"><span>●</span> Takes about 2 minutes</div>
          <h1>Help us build Vitar around your clinic</h1>
          <p>We're onboarding a small batch of Nigerian clinics first. A few honest answers here shape what we build next. No sales pitch, just questions.</p>
        </section>

        <div className="content">
          {!submitted ? (
            <div className="form-card" id="feedback-form-card">
              <h2>A few questions about how you run things today</h2>
              <p className="sub">Answer as many as apply. Every field except clinic name is optional.</p>

              <form id="feedback-form" onSubmit={handleSubmit}>
                <div className="field">
                  <label>Clinic / hospital name</label>
                  <input
                    type="text"
                    placeholder="e.g. Adeyemi Family Clinic"
                    required
                    value={clinicName}
                    onChange={(e) => setClinicName(e.target.value)}
                  />
                </div>

                <div className="field">
                  <label>Email <span className="optional">(optional, only if you'd like us to follow up)</span></label>
                  <input type="email" placeholder="you@clinic.com" value={email} onChange={(e) => setEmail(e.target.value)} />
                </div>

                <div className="field">
                  <label>What's your rough no-show rate today?</label>
                  <select value={noShowRate} onChange={(e) => setNoShowRate(e.target.value)}>
                    <option value="">Select an estimate</option>
                    <option value="Under 10%">Under 10%</option>
                    <option value="10-25%">10–25%</option>
                    <option value="25-40%">25–40%</option>
                    <option value="Over 40%">Over 40%</option>
                    <option value="Not sure">Not sure</option>
                  </select>
                </div>

                <div className="field">
                  <label>What do you use today to manage bookings?</label>
                  <select value={currentTool} onChange={(e) => setCurrentTool(e.target.value)}>
                    <option value="">Select one</option>
                    <option value="Paper register">Paper register</option>
                    <option value="WhatsApp">WhatsApp</option>
                    <option value="Another app or software">Another app or software</option>
                    <option value="Nothing formal">Nothing formal</option>
                    <option value="Other">Other</option>
                  </select>
                </div>

                <div className="field">
                  <label>Who books appointments at your clinic?</label>
                  <select value={whoBooks} onChange={(e) => setWhoBooks(e.target.value)}>
                    <option value="">Select one</option>
                    <option value="Front desk staff">Front desk staff</option>
                    <option value="Walk-in only">Walk-in only</option>
                    <option value="Phone calls">Phone calls</option>
                    <option value="Mix of methods">Mix of methods</option>
                  </select>
                </div>

                <div className="field">
                  <label>Would ₦6,000/month be reasonable for this?</label>
                  <select value={willingnessToPay} onChange={(e) => setWillingnessToPay(e.target.value)}>
                    <option value="">Select one</option>
                    <option value="Yes, definitely">Yes, definitely</option>
                    <option value="Maybe, depends on features">Maybe, depends on features</option>
                    <option value="No, too expensive">No, too expensive</option>
                    <option value="Need to know more first">Need to know more first</option>
                  </select>
                </div>

                <div className="field">
                  <label>Anything else you'd want this to do? <span className="optional">(optional)</span></label>
                  <textarea
                    rows={3}
                    placeholder="Tell us what's missing from tools you've tried..."
                    value={extraNotes}
                    onChange={(e) => setExtraNotes(e.target.value)}
                  />
                </div>

                <button type="submit" className="submit-btn" disabled={submitting}>
                  {submitting ? 'Sending…' : 'Send feedback →'}
                </button>
                <p className="form-note">Your answers go straight to our team. Nothing is shared or sold.</p>
              </form>
            </div>
          ) : (
            <div className="form-card success-state" id="feedback-success">
              <div className="success-badge">✓</div>
              <h3>Thank you, this genuinely helps</h3>
              <p>We read every response. If you left an email, we may reach out with a couple of follow-up questions or an early invite.</p>
              <Link className="back-link" to="/">← Back to home</Link>
            </div>
          )}
        </div>
      </MarketingSubpageChrome>
    </div>
  );
}
