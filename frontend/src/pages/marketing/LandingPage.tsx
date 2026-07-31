/**
 * Vitar — Homepage
 *
 * Converted from the LiveVault static demo site's index.html into a
 * self-contained React page (own nav + hero + sections + footer,
 * matching the demo's exact layout, copy, and visual design).
 *
 * This page intentionally renders its own <nav>/<footer> instead of
 * using <MarketingLayout>, because the demo's navbar relies on
 * same-page anchor links (#product, #how-it-works, #pricing, #faq)
 * that only make sense on this page. Other marketing routes
 * (/pricing) keep using <MarketingLayout> exactly as before.
 */
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import Reveal from '@/components/marketing/Reveal';
import '@/styles/landing.css';

const ACTION_TABS = [
  { id: 'ap-dashboard', label: 'Dashboard' },
  { id: 'ap-calendar', label: 'Appointment Calendar' },
  { id: 'ap-appointments', label: 'Appointments' },
  { id: 'ap-patients', label: 'Patients' },
  { id: 'ap-doctors', label: 'Doctor Schedule' },
  { id: 'ap-booking', label: 'Booking Page' },
  { id: 'ap-analytics', label: 'Analytics' },
];

const FAQS = [
  {
    q: 'What is Vitar?',
    a: "Vitar is a clinic management platform built by LiveVault for Nigerian clinics. It handles appointments, patients, and reminders, and is designed to help reduce missed appointments — up to 40% based on industry benchmarks for automated reminders.",
  },
  {
    q: 'Is there a free trial?',
    a: 'Yes — 30 days full access, no credit card required.',
  },
  {
    q: 'What does Vitar cost?',
    a: 'The Pro plan is ₦15,000/month after your free trial. There\'s no setup fee and no long-term contract.',
  },
  {
    q: 'Do I need new hardware or an app?',
    a: 'No. Vitar runs in the browser on any phone, tablet, or laptop your staff already use.',
  },
  {
    q: "Is my clinic's data safe?",
    a: 'Patient data is encrypted and backed up automatically. Only your clinic\'s staff can access your records.',
  },
];

export default function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('ap-dashboard');
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const tickingRef = useRef(false);

  // Smooth scrolling for on-page anchors (#product, #pricing, etc.) —
  // scoped to this page only, restored on unmount.
  useEffect(() => {
    const prev = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = 'smooth';
    return () => { document.documentElement.style.scrollBehavior = prev; };
  }, []);

  // Lock body scroll while the mobile menu is open.
  useEffect(() => {
    document.body.style.overflow = menuOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [menuOpen]);

  // Scroll-to-top button visibility.
  useEffect(() => {
    const onScroll = () => {
      if (!tickingRef.current) {
        window.requestAnimationFrame(() => {
          setShowScrollTop(window.scrollY > 480);
          tickingRef.current = false;
        });
        tickingRef.current = true;
      }
    };
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="lv-marketing lv-home">
      {/* NAV */}
      <nav>
        <div className="nav-left">
          <Link to="/" className="nav-logo">
            <img src="/icon-192x192.png" alt="Vitar logo" />
            <span>Vitar</span>
          </Link>
          <div className="nav-links">
            <a href="#product">Features</a>
            <a href="#how-it-works">How it works</a>
            <a href="/demo.html" className="nav-demo-link"><span className="live-dot" />Product Tour</a>
            <Link to="/pricing">Pricing</Link>
            <Link to="/contact">Contact</Link>
          </div>
        </div>
        <div className="nav-right">
          <Link to="/login" className="nav-login">Log in</Link>
          <Link to="/register" className="nav-cta">Start Free Trial →</Link>
        </div>
        <button
          className={`hamburger${menuOpen ? ' open' : ''}`}
          aria-label="Open menu"
          onClick={() => setMenuOpen((v) => !v)}
        >
          <span /><span /><span />
        </button>
      </nav>

      <div className={`menu-overlay${menuOpen ? ' open' : ''}`} onClick={closeMenu} />
      <div className={`mobile-menu${menuOpen ? ' open' : ''}`}>
        <div className="mobile-menu-top">
          <Link to="/" className="nav-logo" onClick={closeMenu}>
            <img src="/icon-192x192.png" alt="Vitar logo" />
            <span>Vitar</span>
          </Link>
          <button className="mobile-menu-close" aria-label="Close menu" onClick={closeMenu}>✕</button>
        </div>
        <a href="#product" onClick={closeMenu}>Features</a>
        <a href="/demo.html" onClick={closeMenu} className="nav-demo-link"><span className="live-dot" />Product Tour</a>
        <Link to="/pricing" onClick={closeMenu}>Pricing</Link>
        <Link to="/contact" onClick={closeMenu}>Contact</Link>
        <Link to="/feedback" onClick={closeMenu}>Feedback</Link>
        <Link to="/login" onClick={closeMenu}>Log in</Link>
        <Link to="/register" onClick={closeMenu} className="mm-cta">Sign up — Start Free Trial →</Link>
      </div>

      {/* HERO */}
      <section className="hero">
        <div>
          <div className="hero-badge">
            <span className="dot" />
            Onboarding new clinics · 30-day free trial
          </div>
          <h1>
            Stop Losing Patients to<br />
            <span className="accent">Missed Appointments</span>
          </h1>
          <p className="hero-sub">
            Vitar helps Nigerian clinics reduce no-shows, simplify bookings, and manage patients from one powerful dashboard.
          </p>
          <div className="hero-actions">
            <a href="/demo.html" className="btn-primary btn-demo">
              Take the Product Tour →
            </a>
            <Link to="/register" className="btn-secondary">
              Start Free Trial
            </Link>
            <Link to="/login" className="hero-login-link">
              Log in
            </Link>
          </div>
          <p className="hero-microlink">Explore the real dashboard, no signup needed · <a href="#how-it-works">see how it works ↓</a></p>
        </div>

        <div className="hero-visual">
          <div className="hv-glow" />
          <div className="hero-phone-wrap">
            <div className="hero-phone">
              <div className="hero-phone-screen">
                <div className="hero-phone-notch" />
                <div className="hp-appbar">
                  <span className="hp-avatar">AF</span>
                  <div className="hp-appbar-text">
                    <strong>Adeyemi Clinic</strong>
                    <em>Reminder sent</em>
                  </div>
                  <span className="hp-time">10:24</span>
                </div>
                <div className="hp-thread">
                  <div className="hp-msg-group left">
                    <span className="hp-sender">Adeyemi Clinic</span>
                    <div className="hp-bubble">Hi Chiamaka 👋 this is a reminder that your appointment with <b>Dr. Adeyemi</b> is <b>tomorrow at 10:00 AM</b>.</div>
                    <div className="hp-bubble">Reply <b>1</b> to confirm or <b>2</b> to reschedule.</div>
                  </div>
                  <div className="hp-msg-group right">
                    <span className="hp-sender">Chiamaka</span>
                    <div className="hp-confirm">1</div>
                  </div>
                  <div className="hp-msg-group left">
                    <span className="hp-sender">Adeyemi Clinic</span>
                    <div className="hp-bubble">You're confirmed ✅ Please arrive <b>10 mins early</b> for check-in.</div>
                  </div>
                  <div className="hp-msg-group right">
                    <span className="hp-sender">Chiamaka</span>
                    <div className="hp-confirm">Noted, thank you! 🙏</div>
                  </div>
                  <div className="hp-seen">Seen · 10:26 AM</div>
                </div>
                <div className="hp-risk">
                  <div className="hp-risk-top">
                    <span className="hp-risk-label">No-show risk</span>
                    <span className="hp-risk-pct">Low · 18%</span>
                  </div>
                  <div className="hp-risk-track"><i /></div>
                </div>
              </div>
            </div>
            <div className="hp-float top">📈 No-shows down 40%</div>
            <div className="hp-float bottom">📅 Booked in 5 min</div>
          </div>
          <div className="hero-dash-stats">
            <div className="hero-dash-stat"><span className="hstat-num">Up to 40%</span><span className="hstat-label">Fewer no-shows*</span></div>
            <div className="hero-dash-stat"><span className="hstat-num">5 min</span><span className="hstat-label">To get started</span></div>
          </div>
        </div>
      </section>

      <div className="stats-bar-wrap">
        <div className="stats-bar">
          <div className="stat"><span className="stat-num">Up to 40%</span><span className="stat-label">Fewer no-shows*</span></div>
          <div className="stat"><span className="stat-num">30 days</span><span className="stat-label">Free trial · No card</span></div>
          <div className="stat"><span className="stat-num">₦6,000</span><span className="stat-label">Starting price/month</span></div>
          <div className="stat"><span className="stat-num">5 min</span><span className="stat-label">To get started</span></div>
        </div>
        <p className="stats-bar-note">*Based on industry benchmarks for automated appointment reminders, not a guaranteed result for every clinic.</p>
      </div>

      <div className="section" style={{ padding: '0 5vw 64px' }}>
        <div className="mini-teaser">
          <div className="mini-teaser-text">
            <p className="section-label">See it before you try it</p>
            <h3>Every screen your clinic will use</h3>
            <p className="mt-sub">Bookings, appointments, today's schedule, and analytics — a closer look at the real interface.</p>
          </div>
          <Link to="/screens" className="mini-teaser-link">See all screens →</Link>
        </div>
      </div>

      {/* HOW IT WORKS */}
      <section className="section how" id="how-it-works">
        <p className="section-label">How it works</p>
        <Reveal as="h2" className="section-title">A simple flow for busy clinics</Reveal>
        <Reveal as="p" className="section-sub">No new hardware. No complex setup. Staff can use it from a phone, tablet, or laptop.</Reveal>

        <Reveal as="p" className="how-subhead">For your patients</Reveal>
        <Reveal className="steps">
          <div className="step">
            <div className="step-num">1</div>
            <h4>Patient books online</h4>
            <p>No app download. A patient picks a doctor, a time, and a reason for the visit in under a minute.</p>
          </div>
          <div className="step">
            <div className="step-num">2</div>
            <h4>Clinic confirms appointment</h4>
            <p>Your front desk sees the request instantly and confirms it — no back-and-forth phone calls.</p>
          </div>
          <div className="step">
            <div className="step-num">3</div>
            <h4>Patient receives reminders and attends</h4>
            <p>WhatsApp, SMS, and email reminders go out automatically, so the patient shows up on time.</p>
          </div>
        </Reveal>

        <Reveal as="p" className="how-subhead">For your clinic staff</Reveal>
        <Reveal className="steps">
          <div className="step">
            <div className="step-num">4</div>
            <h4>Create the clinic profile</h4>
            <p>Add clinic details, doctors, services, and working hours.</p>
          </div>
          <div className="step">
            <div className="step-num">5</div>
            <h4>Book and remind patients</h4>
            <p>Staff schedule visits while Vitar sends reminders automatically.</p>
          </div>
          <div className="step">
            <div className="step-num">6</div>
            <h4>Track attendance</h4>
            <p>Use risk scores, analytics, and QR check-in to reduce empty slots.</p>
          </div>
        </Reveal>
      </section>

      {/* SEE VITAR IN ACTION */}
      <section className="section" id="product">
        <p className="section-label">See Vitar in action</p>
        <Reveal as="h2" className="section-title">The dashboard your front desk will actually use</Reveal>
        <Reveal as="p" className="section-sub">A real look at how Vitar organizes bookings, patients, and reminders — the same screens your staff will open every morning.</Reveal>
        <Reveal className="action-tabs" role="tablist" aria-label="Product screens">
          {ACTION_TABS.map((tab) => (
            <button
              key={tab.id}
              className={`action-tab${activeTab === tab.id ? ' active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </Reveal>
        <Reveal className="action-frame">
          <div className="action-frame-top">
            <i /><i /><i />
            <span>www.livevault.cloud</span>
          </div>

          <div className={`action-panel${activeTab === 'ap-dashboard' ? ' active' : ''}`}>
            <div className="ap-title">Clinic command centre</div>
            <p className="ap-sub">Today's bookings, risk levels, and reminders in one view.</p>
            <div className="ap-metrics">
              <div className="ap-metric"><span>Today's bookings</span><strong>18</strong></div>
              <div className="ap-metric"><span>Checked in</span><strong>11</strong></div>
              <div className="ap-metric"><span>High-risk visits</span><strong>3</strong></div>
              <div className="ap-metric"><span>Avg. no-show risk</span><strong>21%</strong></div>
            </div>
            <table className="ap-table">
              <thead><tr><th>Time</th><th>Patient</th><th>Doctor</th><th>Status</th></tr></thead>
              <tbody>
                <tr><td>08:30 AM</td><td>Chiamaka Eze</td><td>Dr. Adeyemi</td><td><span className="ap-pill low">Confirmed</span></td></tr>
                <tr><td>09:15 AM</td><td>Musa Danjuma</td><td>Dr. Nwosu</td><td><span className="ap-pill med">Pending</span></td></tr>
                <tr><td>10:00 AM</td><td>Amina Yusuf</td><td>Dr. Bello</td><td><span className="ap-pill low">Checked in</span></td></tr>
              </tbody>
            </table>
          </div>

          <div className={`action-panel${activeTab === 'ap-calendar' ? ' active' : ''}`}>
            <div className="ap-title">Appointment calendar</div>
            <p className="ap-sub">A week-at-a-glance view so nobody double-books a doctor.</p>
            <div className="ap-cal">
              <div className="ap-cal-head"><span /><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span></div>
              <div className="ap-cal-row"><span className="ap-cal-time">9AM</span><i className="busy low">Eze</i><i /><i className="busy med">Danjuma</i><i /><i className="busy low">Yusuf</i></div>
              <div className="ap-cal-row"><span className="ap-cal-time">11AM</span><i /><i className="busy low">Okoro</i><i /><i className="busy low">Obi</i><i className="busy med">Williams</i></div>
              <div className="ap-cal-row"><span className="ap-cal-time">1PM</span><i className="busy low">Bello</i><i /><i className="busy low">Musa</i><i /><i /></div>
              <div className="ap-cal-row"><span className="ap-cal-time">3PM</span><i /><i className="busy med">Chukwu</i><i /><i className="busy low">Nnamdi</i><i className="busy low">Aisha</i></div>
            </div>
          </div>

          <div className={`action-panel${activeTab === 'ap-appointments' ? ' active' : ''}`}>
            <div className="ap-title">Appointment scheduling</div>
            <p className="ap-sub">Book a slot, assign a doctor, and reminders go out automatically.</p>
            <table className="ap-table">
              <thead><tr><th>Time</th><th>Patient</th><th>Reason</th><th>Reminder</th></tr></thead>
              <tbody>
                <tr><td>11:30 AM</td><td>Nneka Okoro</td><td>Follow-up consultation</td><td><span className="ap-pill low">Sent</span></td></tr>
                <tr><td>01:00 PM</td><td>Emeka Obi</td><td>Lab result review</td><td><span className="ap-pill med">Scheduled</span></td></tr>
                <tr><td>03:30 PM</td><td>Sade Williams</td><td>General check-up</td><td><span className="ap-pill low">Sent</span></td></tr>
              </tbody>
            </table>
          </div>

          <div className={`action-panel${activeTab === 'ap-patients' ? ' active' : ''}`}>
            <div className="ap-title">Patient records</div>
            <p className="ap-sub">Search any patient's visit history in seconds — no folders.</p>
            <div className="ap-grid">
              <div className="ap-card"><strong>Chiamaka Eze</strong><span>Hypertension · 8 visits</span></div>
              <div className="ap-card"><strong>Musa Danjuma</strong><span>Diabetes review · 5 visits</span></div>
              <div className="ap-card"><strong>Amina Yusuf</strong><span>Antenatal care · 4 visits</span></div>
              <div className="ap-card"><strong>Emeka Obi</strong><span>Lab review · 2 visits</span></div>
              <div className="ap-card"><strong>Sade Williams</strong><span>Malaria follow-up · 3 visits</span></div>
              <div className="ap-card"><strong>Nneka Okoro</strong><span>New patient · 0 visits</span></div>
            </div>
          </div>

          <div className={`action-panel${activeTab === 'ap-doctors' ? ' active' : ''}`}>
            <div className="ap-title">Doctor schedule</div>
            <p className="ap-sub">See every doctor's availability and daily load at a glance.</p>
            <div className="ap-grid">
              <div className="ap-card"><strong>Dr. Tunde Adeyemi</strong><span>General practice · 7 patients today</span></div>
              <div className="ap-card"><strong>Dr. Ifeoma Nwosu</strong><span>Pediatrics · 5 patients today</span></div>
              <div className="ap-card"><strong>Dr. Kunle Bello</strong><span>Internal medicine · 6 patients today</span></div>
              <div className="ap-card"><strong>Dr. Grace Okafor</strong><span>Obstetrics · 4 patients today</span></div>
              <div className="ap-card"><strong>Dr. Ahmed Musa</strong><span>Family medicine · 8 patients today</span></div>
              <div className="ap-card"><strong>Dr. Bisi Fashola</strong><span>Off today · Back tomorrow, 9 AM</span></div>
            </div>
          </div>

          <div className={`action-panel${activeTab === 'ap-booking' ? ' active' : ''}`}>
            <div className="ap-title" style={{ textAlign: 'center' }}>Patient booking page</div>
            <p className="ap-sub" style={{ textAlign: 'center' }}>What patients see when they book — no app download needed.</p>
            <div className="ap-booking">
              <div className="ap-field"><label>Choose a doctor</label><div className="fake-input">Dr. Tunde Adeyemi</div></div>
              <div className="ap-field"><label>Preferred time</label><div className="fake-input">Tomorrow, 11:30 AM</div></div>
              <div className="ap-field"><label>Reason for visit</label><div className="fake-input">Follow-up consultation</div></div>
              <div className="btn-primary">Confirm booking →</div>
            </div>
          </div>

          <div className={`action-panel${activeTab === 'ap-analytics' ? ' active' : ''}`}>
            <div className="ap-title">Monthly analytics</div>
            <p className="ap-sub">Track attendance trends and see what your no-show rate is really costing you.</p>
            <div className="ap-bars">
              <div className="ap-bar-row"><strong>Jan</strong><div className="ap-bar-track"><i style={{ width: '64%' }} /></div><span>118</span></div>
              <div className="ap-bar-row"><strong>Feb</strong><div className="ap-bar-track"><i style={{ width: '72%' }} /></div><span>132</span></div>
              <div className="ap-bar-row"><strong>Mar</strong><div className="ap-bar-track"><i style={{ width: '81%' }} /></div><span>149</span></div>
              <div className="ap-bar-row"><strong>Apr</strong><div className="ap-bar-track"><i style={{ width: '77%' }} /></div><span>141</span></div>
              <div className="ap-bar-row"><strong>May</strong><div className="ap-bar-track"><i style={{ width: '90%' }} /></div><span>166</span></div>
              <div className="ap-bar-row"><strong>Jun</strong><div className="ap-bar-track"><i style={{ width: '100%' }} /></div><span>184</span></div>
            </div>
          </div>
        </Reveal>
        <Reveal style={{ textAlign: 'center', marginTop: 28 }}>
          <a href="/demo.html" className="btn-primary">Explore Full Product Tour →</a>
        </Reveal>
      </section>

      {/* PRICING */}
      <section className="section" id="pricing" style={{ background: 'var(--mist)' }}>
        <p className="section-label" style={{ textAlign: 'center' }}>Pricing</p>
        <Reveal as="h2" className="section-title" style={{ textAlign: 'center', maxWidth: '100%' }}>Simple pricing for every clinic size</Reveal>
        <Reveal as="p" className="section-sub" style={{ textAlign: 'center', maxWidth: '100%', marginBottom: 36 }}>Start free for 30 days. No credit card. Upgrade only when you see the value.</Reveal>
        <Reveal className="pricing-grid" style={{ maxWidth: 1180 }}>
          <div className="plan free">
            <div className="plan-name">Free Trial</div>
            <div className="plan-price">₦0 <span>/30 days</span></div>
            <div className="plan-desc">Try every Pro feature, risk-free</div>
            <ul className="plan-features">
              <li>Full access to Pro features</li>
              <li>Up to 2 doctors</li>
              <li>100 bookings included</li>
              <li>SMS &amp; email reminders</li>
              <li>No credit card required</li>
              <li>Cancel anytime</li>
            </ul>
            <Link to="/register" className="plan-btn outline">Start Free Trial</Link>
          </div>
          <div className="plan">
            <div className="plan-name">Starter</div>
            <div className="plan-price">₦6,000 <span>/month</span></div>
            <div className="plan-desc">For small clinics just getting started</div>
            <ul className="plan-features">
              <li>Up to 2 doctors</li>
              <li>200 bookings/month</li>
              <li>SMS &amp; email reminders</li>
              <li>Public booking page</li>
              <li>QR code check-in</li>
              <li>Email support</li>
            </ul>
            <Link to="/pricing" className="plan-btn ghost">Subscribe Now</Link>
          </div>
          <div className="plan popular">
            <div className="popular-badge">MOST POPULAR</div>
            <div className="plan-name">Pro</div>
            <div className="plan-price">₦15,000 <span>/month</span></div>
            <div className="plan-desc">For growing clinics that want full AI power</div>
            <ul className="plan-features">
              <li>Up to 10 doctors</li>
              <li>2,000 bookings/month</li>
              <li>SMS, WhatsApp &amp; email reminders</li>
              <li>No-show risk scoring</li>
              <li>Waiting list management</li>
              <li>Advanced analytics</li>
              <li>Priority support</li>
            </ul>
            <Link to="/pricing" className="plan-btn filled">Subscribe Now</Link>
          </div>
          <div className="plan">
            <div className="plan-name">Enterprise</div>
            <div className="plan-price" style={{ fontSize: '1.9rem' }}>Custom</div>
            <div className="plan-desc">For hospital groups and multi-branch clinics</div>
            <ul className="plan-features">
              <li>Unlimited doctors</li>
              <li>Unlimited bookings</li>
              <li>All Pro features</li>
              <li>Dedicated account manager</li>
              <li>Custom integrations</li>
              <li>SLA guarantee</li>
            </ul>
            <Link to="/contact" className="plan-btn ghost">Contact Sales</Link>
          </div>
        </Reveal>
        <p className="testimonial-note" style={{ marginTop: 24 }}>Early days, honest pricing — as Vitar grows with real clinic feedback, these plans will evolve too.</p>
      </section>

      {/* TRUST */}
      <section className="section trust" id="trust">
        <p className="section-label" style={{ textAlign: 'center' }}>Built to be trusted</p>
        <Reveal as="h2" className="section-title" style={{ margin: '0 auto 16px' }}>How Vitar protects your patients' data</Reveal>
        <Reveal as="p" className="section-sub" style={{ marginLeft: 'auto', marginRight: 'auto' }}>Clinics run on trust. Here's exactly what that means in practice, not just a badge.</Reveal>
        <Reveal as="p" className="section-sub" style={{ marginLeft: 'auto', marginRight: 'auto', marginTop: -8, fontWeight: 600, color: '#5eead4' }}>Your clinic's patient information is encrypted and stored securely to help protect sensitive medical records.</Reveal>
        <Reveal className="trust-grid">
          <div className="trust-card">
            <span className="icon">🔒</span>
            <h4>Encrypted patient records</h4>
            <p>Patient data is encrypted in transit and at rest, and only your clinic's authorized staff can access it.</p>
          </div>
          <div className="trust-card">
            <span className="icon">☁️</span>
            <h4>Hosted securely in the cloud</h4>
            <p>Vitar runs on cloud infrastructure, so your records are available from any device without a local server.</p>
          </div>
          <div className="trust-card">
            <span className="icon">🛡️</span>
            <h4>Automatic backups</h4>
            <p>Your clinic's data is backed up automatically, so a lost device or a bad day never means lost records.</p>
          </div>
          <div className="trust-card">
            <span className="icon">💬</span>
            <h4>Real support, real people</h4>
            <p>Reach us directly on WhatsApp or email. We're a small team onboarding early clinics, so we aim to reply within one business day.</p>
          </div>
          <div className="trust-card">
            <span className="icon">🇳🇬</span>
            <h4>Built for Nigerian clinics</h4>
            <p>Pricing in Naira, WhatsApp-first reminders, and a product built around how Nigerian clinics actually run.</p>
          </div>
          <div className="trust-card">
            <span className="icon">🏢</span>
            <h4>Who's behind Vitar</h4>
            <p>Built by LiveVault, a Nigerian software company focused on healthcare technology — based in Enugu State. <Link to="/contact">Reach out anytime</Link>.</p>
          </div>
        </Reveal>
      </section>

      {/* FAQ */}
      <section className="section" id="faq">
        <p className="section-label">FAQ</p>
        <Reveal as="h2" className="section-title">Questions clinics ask us</Reveal>
        <Reveal as="p" className="section-sub">Can't find what you're looking for? <Link to="/contact" style={{ color: 'var(--teal-dark)', fontWeight: 600 }}>Contact us directly</Link>.</Reveal>
        <Reveal className="faq-list">
          {FAQS.map((item, i) => (
            <div key={item.q} className={`faq-item${openFaq === i ? ' open' : ''}`}>
              <button className="faq-q" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
                {item.q}<span className="plus">+</span>
              </button>
              <div className="faq-a"><p>{item.a}</p></div>
            </div>
          ))}
        </Reveal>
      </section>

      <div className="section" style={{ padding: '0 5vw 64px' }}>
        <div className="mini-teaser dark">
          <div className="mini-teaser-text">
            <p className="section-label" style={{ color: 'var(--teal-lt)' }}>Growing with you</p>
            <h3>Coming next</h3>
            <p className="mt-sub">We're onboarding our first clinics now — see where customer logos, usage numbers, and case studies will live as they come in.</p>
          </div>
          <Link to="/growth" className="mini-teaser-link">See our roadmap →</Link>
        </div>
      </div>

      {/* FINAL CTA */}
      <section className="section final-cta" id="early-access">
        <p className="section-label" style={{ color: 'var(--teal-lt)', textAlign: 'center' }}>Early days · Become one of our first 10 partner clinics</p>
        <Reveal as="h2" className="section-title" style={{ textAlign: 'center', margin: '0 auto 16px' }}>Ready to modernize your clinic?</Reveal>
        <Reveal as="p" className="section-sub" style={{ textAlign: 'center', margin: '0 auto 10px', color: 'rgba(255,255,255,0.75)' }}>Vitar is brand new — try it free for 30 days, help shape what we build next, and lock in discounted lifetime pricing as one of our first 10 partner clinics.</Reveal>
        <Reveal className="final-cta-actions">
          <Link to="/register" className="btn-primary">Start Free Trial →</Link>
          <a href="/demo.html" className="btn-secondary" style={{ borderColor: 'rgba(255,255,255,0.3)', color: '#fff' }}>Take the Product Tour →</a>
        </Reveal>
        <p style={{ textAlign: 'center', marginTop: 28 }}>
          <Link to="/feedback" className="feedback-inline-link">💬 Already running a clinic? Tell us what you're dealing with today →</Link>
        </p>
      </section>

      {/* FOOTER */}
      <footer>
        <div className="footer-top">
          <div>
            <div className="footer-brand">
              <img src="/icon-96x96.png" alt="Vitar logo" />
              <span>Vitar</span>
            </div>
            <p className="footer-tag">Clinic management and appointment scheduling built for Nigerian private clinics.</p>
            <p className="footer-tag" style={{ marginTop: 6, color: 'rgba(255,255,255,0.32)' }}>Built by LiveVault</p>
          </div>
          <nav>
            <div className="col">
              <span className="col-title">Product</span>
              <a href="#product">Features</a>
              <Link to="/screens">Every screen</Link>
              <a href="/demo.html">Product Tour</a>
              <Link to="/pricing">Pricing</Link>
              <a href="#faq">FAQ</a>
              <a href="#how-it-works">How it works</a>
            </div>
            <div className="col">
              <span className="col-title">Account</span>
              <Link to="/register">Sign up</Link>
              <Link to="/login">Log in</Link>
            </div>
            <div className="col">
              <span className="col-title">Company</span>
              <Link to="/growth">Our growth</Link>
              <Link to="/contact">Contact</Link>
              <Link to="/feedback">Give feedback</Link>
              <a href="mailto:vitarhealthcare@gmail.com">vitarhealthcare@gmail.com</a>
              <a href="https://wa.me/2347016479713" target="_blank" rel="noopener">WhatsApp: +234 701 647 9713</a>
            </div>
            <div className="col">
              <span className="col-title">Legal</span>
              <Link to="/privacy">Privacy Policy</Link>
              <Link to="/terms">Terms of Service</Link>
            </div>
          </nav>
        </div>
        <div className="footer-bottom">
          <p>© {new Date().getFullYear()} LiveVault. Built for Nigerian healthcare.</p>
          <p>Enugu State, Nigeria</p>
        </div>
      </footer>

      <button
        className={`scroll-top-btn${showScrollTop ? ' visible' : ''}`}
        aria-label="Scroll back to top"
        title="Back to top"
        onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 19V5" />
          <path d="M5 12l7-7 7 7" />
        </svg>
      </button>
    </div>
  );
}
