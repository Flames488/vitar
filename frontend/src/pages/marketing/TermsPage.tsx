/**
 * Vitar — Terms of Service
 * Converted from the LiveVault static demo site's terms.html.
 */
import MarketingSubpageChrome from '@/components/marketing/MarketingSubpageChrome';
import '@/styles/landing.css';

export default function TermsPage() {
  return (
    <div className="lv-marketing lv-docs">
      <MarketingSubpageChrome
        footerLinks={[
          { label: 'Home', to: '/' },
          { label: 'Privacy Policy', to: '/privacy' },
          { label: 'Contact', to: '/contact' },
        ]}
      >
        <section className="doc-hero">
          <p className="eyebrow">Legal</p>
          <h1>Terms of Service</h1>
          <p>The agreement between your clinic and LiveVault for using Vitar.</p>
        </section>

        <div className="doc-wrap">
          <div className="doc-note">
            <strong>Draft template.</strong> This page is a starting point written for a Nigerian clinic-software product. It hasn't been reviewed by a lawyer. Have one confirm the liability, refund, and termination terms before treating it as final or binding.
          </div>

          <h2>1. Agreement</h2>
          <p>These terms govern use of Vitar by any clinic, hospital, or authorized staff member ("you," "your clinic") who creates an account. Vitar is built and operated by LiveVault ("we," "us"). By creating an account or starting a free trial, you agree to these terms.</p>

          <h2>2. The service</h2>
          <p>Vitar provides appointment scheduling, patient records, automated reminders, no-show risk scoring, and related clinic-management tools, delivered as a web-based subscription service.</p>

          <h2>3. Free trial and subscription</h2>
          <ul>
            <li>New clinics get a 30-day free trial with no credit card required.</li>
            <li>After the trial, continued use requires an active paid subscription at the price shown on the pricing page at the time of purchase.</li>
            <li>Subscriptions renew on a recurring basis until cancelled from within your account or by contacting us.</li>
            <li>Prices are shown in Naira and may change with notice before your next renewal.</li>
          </ul>

          <h2>4. Your responsibilities</h2>
          <ul>
            <li>You're responsible for the accuracy of the clinic, staff, and patient information entered into Vitar.</li>
            <li>You're responsible for controlling which of your staff have access to Vitar and for their use of your account.</li>
            <li>You must have a lawful basis (such as patient consent or legitimate clinical interest) for entering patient data into Vitar and for sending automated reminders.</li>
            <li>You won't use Vitar for anything unlawful or for a clinic you're not authorized to represent.</li>
          </ul>

          <h2>5. Patient data ownership</h2>
          <p>Patient and clinic records you enter into Vitar remain yours. We process that data to provide the service, as described in our <a href="/privacy">Privacy Policy</a>, and don't sell it or use it to build products for other clinics.</p>

          <h2>6. Availability and support</h2>
          <p>We aim to keep Vitar available and responsive, but like any hosted software, occasional downtime for maintenance or issues outside our control (including third-party SMS/WhatsApp/payment providers) can happen. We provide support through the contact channels listed on our <a href="/contact">Contact page</a>.</p>

          <h2>7. Cancellation and termination</h2>
          <p>You can cancel your subscription at any time; access continues until the end of the current billing period. We may suspend or terminate accounts that violate these terms, misuse the service, or fail to pay for an active subscription, after reasonable notice where practical.</p>

          <h2>8. Limitation of liability</h2>
          <p>Vitar is a scheduling and records tool, not a substitute for clinical judgment. We aren't liable for missed appointments, clinical decisions, or business losses arising from use of the service, to the maximum extent permitted by law. Our total liability for any claim is limited to the subscription fees you paid in the preceding three months.</p>

          <h2>9. Changes to these terms</h2>
          <p>We'll update this page if these terms change materially, and note the date below. Continued use after an update means you accept the revised terms.</p>

          <h2>10. Contact</h2>
          <p>Questions about these terms can be sent to <a href="mailto:vitarhealthcare@gmail.com">vitarhealthcare@gmail.com</a> or via <a href="https://wa.me/2347016479713" target="_blank" rel="noopener">WhatsApp</a>.</p>

          <p style={{ marginTop: 32, fontSize: '0.82rem', color: 'var(--slate)' }}>Last updated: draft, not yet published.</p>
        </div>
      </MarketingSubpageChrome>
    </div>
  );
}
