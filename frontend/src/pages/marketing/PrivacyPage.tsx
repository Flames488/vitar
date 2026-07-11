/**
 * Vitar — Privacy Policy
 * Converted from the LiveVault static demo site's privacy.html.
 */
import MarketingSubpageChrome from '@/components/marketing/MarketingSubpageChrome';
import '@/styles/landing.css';

export default function PrivacyPage() {
  return (
    <div className="lv-marketing lv-docs">
      <MarketingSubpageChrome
        footerLinks={[
          { label: 'Home', to: '/' },
          { label: 'Terms of Service', to: '/terms' },
          { label: 'Contact', to: '/contact' },
        ]}
      >
        <section className="doc-hero">
          <p className="eyebrow">Legal</p>
          <h1>Privacy Policy</h1>
          <p>How Vitar, built by LiveVault, collects, uses, and protects clinic and patient information.</p>
        </section>

        <div className="doc-wrap">
          <div className="doc-note">
            <strong>Draft template.</strong> This page is a starting point written for a Nigerian clinic-software product and references the Nigeria Data Protection Act (NDPA) 2023. It hasn't been reviewed by a lawyer — have one confirm it fits your actual data flows (especially payment processing and any data stored or processed outside Nigeria) before treating it as final.
          </div>

          <h2>1. Who this policy covers</h2>
          <p>This policy applies to clinics and hospitals ("clinics") that use Vitar, and to the staff, doctors, and patients whose information clinics enter into Vitar. Vitar is built and operated by LiveVault ("we," "us").</p>

          <h2>2. Information we collect</h2>
          <p>We collect information in two ways: what a clinic enters directly, and what our systems generate while the product runs.</p>
          <ul>
            <li><strong>Clinic account data:</strong> clinic name, address, staff names, contact details, and billing information.</li>
            <li><strong>Patient records:</strong> names, contact numbers, appointment history, and clinical notes that clinic staff choose to enter.</li>
            <li><strong>Usage data:</strong> login activity, device and browser information, and how features are used, collected to keep the service reliable and secure.</li>
            <li><strong>Communications:</strong> reminders sent by SMS, email, or WhatsApp, and any replies used to confirm or reschedule appointments.</li>
          </ul>

          <h2>3. How we use information</h2>
          <ul>
            <li>To provide appointment scheduling, reminders, patient records, and analytics inside Vitar.</li>
            <li>To reduce missed appointments through automated, opt-out-able reminders.</li>
            <li>To bill clinics for their subscription and process payments through our payment provider.</li>
            <li>To maintain security, prevent abuse, and fix issues.</li>
            <li>To improve Vitar based on aggregated, non-identifying usage patterns.</li>
          </ul>

          <h2>4. Who can see clinic and patient data</h2>
          <p>Patient records entered by a clinic are visible only to that clinic's authorized staff accounts. LiveVault staff do not access patient records except when needed to provide support you've requested, or where required to maintain the security of the service.</p>

          <h2>5. Third parties and processors</h2>
          <p>Vitar relies on a small number of providers to operate: payment processing, SMS/WhatsApp delivery, cloud hosting, and error monitoring. These providers only receive the data needed to perform their specific function and are not permitted to use it for their own purposes.</p>

          <h2>6. Data storage and security</h2>
          <p>Data is encrypted in transit and at rest, backed up regularly, and access is restricted to authenticated clinic accounts. No system is completely immune to risk, and we disclose any confirmed breach affecting patient data in line with NDPA requirements.</p>

          <h2>7. Data retention</h2>
          <p>Clinic and patient data is retained for as long as a clinic maintains an active account, plus a limited period afterward to allow account recovery, unless a clinic requests earlier deletion or longer retention is required by law (for example, medical record-keeping obligations).</p>

          <h2>8. Your rights</h2>
          <p>Clinics can request access to, correction of, or deletion of the data their account holds, subject to any legal obligation to retain medical records. Patients should direct data requests to their clinic in the first instance, since the clinic — not LiveVault — controls what is entered into Vitar about them.</p>

          <h2>9. Changes to this policy</h2>
          <p>We'll update this page if how we handle data changes, and note the date below.</p>

          <h2>10. Contact</h2>
          <p>Questions about this policy can be sent to <a href="mailto:vitarhealthcare@gmail.com">vitarhealthcare@gmail.com</a> or via <a href="https://wa.me/2347016479713" target="_blank" rel="noopener">WhatsApp</a>.</p>

          <p style={{ marginTop: 32, fontSize: '0.82rem', color: 'var(--slate)' }}>Last updated: draft, not yet published.</p>
        </div>
      </MarketingSubpageChrome>
    </div>
  );
}
