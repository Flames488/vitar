/**
 * Vitar — Contact Page
 * Converted from the LiveVault static demo site's contact.html.
 * The original demo had a disabled "coming soon" contact form here.
 * Since this is the live product now, that placeholder form has been
 * removed rather than shown disabled — the real, working channels below
 * (email, WhatsApp, enterprise) are the actual way to reach the team.
 */
import MarketingSubpageChrome from '@/components/marketing/MarketingSubpageChrome';
import { VITAR_SALES_WHATSAPP } from '@/lib/whatsapp';
import { VITAR_SUPPORT_EMAIL } from '@/lib/contact';
import '@/styles/landing.css';

export default function ContactPage() {
  return (
    <div className="lv-marketing lv-contact">
      <MarketingSubpageChrome
        footerLinks={[
          { label: 'Home', to: '/' },
          { label: 'Sign up', to: '/register' },
          { label: 'Give feedback', to: '/feedback' },
          { label: 'Privacy Policy', to: '/privacy' },
          { label: 'Terms of Service', to: '/terms' },
          { label: VITAR_SUPPORT_EMAIL, href: `mailto:${VITAR_SUPPORT_EMAIL}` },
        ]}
      >
        <section className="hero">
          <div className="hero-badge"><span>●</span> We usually reply within one business day</div>
          <h1>Let's talk about your clinic</h1>
          <p>Questions about pricing, a demo, or partnering with Vitar? Reach us directly below.</p>
        </section>

        <div className="content content--single">
          <div>
            <div className="channels">
              <div className="channel-card">
                <div className="channel-ic">✉️</div>
                <div>
                  <h3>Email</h3>
                  <p>For general questions, demos, and support.</p>
                  <a className="link" href={`mailto:${VITAR_SUPPORT_EMAIL}`}>{VITAR_SUPPORT_EMAIL}</a>
                </div>
              </div>
              <div className="channel-card">
                <div className="channel-ic">💼</div>
                <div>
                  <h3>Enterprise & sales</h3>
                  <p>Multi-branch clinics and hospital groups: add "Enterprise" to your subject line.</p>
                  <a className="link" href={`mailto:${VITAR_SUPPORT_EMAIL}?subject=Enterprise%20enquiry`}>{VITAR_SUPPORT_EMAIL}</a>
                </div>
              </div>
              <div className="channel-card">
                <div className="channel-ic">📱</div>
                <div>
                  <h3>WhatsApp / Call</h3>
                  <p>Chat with our team the same way your patients will.</p>
                  <a className="link" href={`https://wa.me/${VITAR_SALES_WHATSAPP}`} target="_blank" rel="noopener">+234 815 679 2070</a>
                </div>
              </div>
            </div>
            <div className="office-note" style={{ marginTop: 16 }}>
              <b>Based in Nigeria.</b> Vitar is built and supported locally, so replies come from a team that understands Naira pricing, WhatsApp-first patients, and the day-to-day of running a Nigerian clinic.
            </div>
          </div>
        </div>
      </MarketingSubpageChrome>
    </div>
  );
}
