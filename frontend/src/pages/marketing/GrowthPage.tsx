/**
 * Vitar — Growth / Roadmap Page
 * Converted from the LiveVault static demo site's growth.html.
 */
import { Link } from 'react-router-dom';
import MarketingSubpageChrome from '@/components/marketing/MarketingSubpageChrome';
import '@/styles/landing.css';

export default function GrowthPage() {
  return (
    <div className="lv-marketing lv-growth">
      <MarketingSubpageChrome
        footerLinks={[
          { label: 'Home', to: '/' },
          { label: 'Sign up', to: '/register' },
          { label: 'Give feedback', to: '/feedback' },
          { label: 'Contact', to: '/contact' },
        ]}
      >
        <section className="hero">
          <p className="eyebrow">Growing with you</p>
          <h1>Growing every day</h1>
          <p>We're onboarding clinics now. This is where customer logos, usage numbers, and case studies will live as they come in.</p>
        </section>

        <div className="growth-wrap">
          <div className="growth-logos">
            <div className="logo-slot">Your clinic's logo</div>
            <div className="logo-slot">Your clinic's logo</div>
            <div className="logo-slot">Your clinic's logo</div>
            <div className="logo-slot">Your clinic's logo</div>
          </div>

          <div className="growth-stats">
            <div className="growth-stat"><span className="num">—</span><span className="label">Appointments managed</span></div>
            <div className="growth-stat"><span className="num">—</span><span className="label">Clinics onboarded</span></div>
            <div className="growth-stat"><span className="num">—</span><span className="label">Reminders sent</span></div>
          </div>
          <p className="growth-note">Real numbers will appear here as more clinics come on board.</p>

          <div className="case-study-card">
            <h3>Your clinic could be our next success story</h3>
            <p>As clinics onboard and run their day-to-day on Vitar, we'll share real results here — fewer no-shows, smoother scheduling, happier patients.</p>
          </div>

          <div className="growth-cta">
            <Link to="/register" className="btn-primary">Become one of our first 10 partner clinics →</Link>
          </div>
        </div>
      </MarketingSubpageChrome>
    </div>
  );
}
