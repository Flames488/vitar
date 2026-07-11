/**
 * Vitar — Screens Gallery Page
 * Converted from the LiveVault static demo site's screens.html.
 */
import MarketingSubpageChrome from '@/components/marketing/MarketingSubpageChrome';
import '@/styles/landing.css';

export default function ScreensPage() {
  return (
    <div className="lv-marketing lv-screens">
      <MarketingSubpageChrome
        footerLinks={[
          { label: 'Home', to: '/' },
          { label: 'Product Tour', href: '/demo.html' },
          { label: 'Sign up', to: '/register' },
          { label: 'Contact', to: '/contact' },
        ]}
      >
        <section className="hero">
          <p className="eyebrow">See it before you try it</p>
          <h1>Every screen your clinic will use</h1>
          <p>A closer look at the actual interface — no imagination required. Tap "Take the Product Tour" below to click through it yourself.</p>
        </section>

        <div className="gallery-wrap">
          <div className="gallery-grid">
            <div className="gallery-card">
              <div className="gallery-card-top"><i /><i /><i /><span>www.livevault.cloud</span></div>
              <div className="gallery-card-body">
                <div className="gallery-card-label"><span className="icon">📋</span><span className="name">Bookings</span></div>
                <div className="ap-metrics">
                  <div className="ap-metric"><span>Bookings today</span><strong>18</strong></div>
                  <div className="ap-metric"><span>Checked in</span><strong>11</strong></div>
                  <div className="ap-metric"><span>Pending</span><strong>4</strong></div>
                  <div className="ap-metric"><span>No-show risk</span><strong>3</strong></div>
                </div>
              </div>
              <p className="gallery-caption">Every booking, risk level, and reminder status in one view.</p>
            </div>

            <div className="gallery-card">
              <div className="gallery-card-top"><i /><i /><i /><span>www.livevault.cloud</span></div>
              <div className="gallery-card-body">
                <div className="gallery-card-label"><span className="icon">🗓️</span><span className="name">Appointments</span></div>
                <div className="ap-cal">
                  <div className="ap-cal-head"><span /><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span></div>
                  <div className="ap-cal-row"><span className="ap-cal-time">9AM</span><i className="busy low">Eze</i><i /><i className="busy med">Musa</i><i /><i className="busy low">Yusuf</i></div>
                  <div className="ap-cal-row"><span className="ap-cal-time">11AM</span><i /><i className="busy low">Okoro</i><i /><i className="busy low">Obi</i><i /></div>
                  <div className="ap-cal-row"><span className="ap-cal-time">2PM</span><i className="busy med">Bello</i><i /><i className="busy low">Ade</i><i /><i className="busy low">Kalu</i></div>
                </div>
              </div>
              <p className="gallery-caption">A week-at-a-glance view so nobody double-books a doctor.</p>
            </div>

            <div className="gallery-card">
              <div className="gallery-card-top"><i /><i /><i /><span>www.livevault.cloud</span></div>
              <div className="gallery-card-body">
                <div className="gallery-card-label"><span className="icon">🗂️</span><span className="name">Today's Schedule</span></div>
                <p style={{ fontSize: '0.82rem', color: 'var(--slate)', marginBottom: 10 }}>Adeyemi Family Clinic · Today</p>
                <table className="ap-table">
                  <thead><tr><th>Time</th><th>Patient</th><th>Status</th></tr></thead>
                  <tbody>
                    <tr><td>08:30 AM</td><td>Chiamaka Eze</td><td><span className="ap-pill low">Confirmed</span></td></tr>
                    <tr><td>09:15 AM</td><td>Musa Danjuma</td><td><span className="ap-pill med">Pending</span></td></tr>
                    <tr><td>10:00 AM</td><td>Amina Yusuf</td><td><span className="ap-pill low">Checked in</span></td></tr>
                  </tbody>
                </table>
              </div>
              <p className="gallery-caption">Every clinic's command centre — bookings, patients, and status in one screen.</p>
            </div>

            <div className="gallery-card">
              <div className="gallery-card-top"><i /><i /><i /><span>www.livevault.cloud</span></div>
              <div className="gallery-card-body">
                <div className="gallery-card-label"><span className="icon">📊</span><span className="name">Analytics</span></div>
                <div className="ap-bars">
                  <div className="ap-bar-row"><strong>Apr</strong><div className="ap-bar-track"><i style={{ width: '77%' }} /></div><span>141</span></div>
                  <div className="ap-bar-row"><strong>May</strong><div className="ap-bar-track"><i style={{ width: '90%' }} /></div><span>166</span></div>
                  <div className="ap-bar-row"><strong>Jun</strong><div className="ap-bar-track"><i style={{ width: '100%' }} /></div><span>184</span></div>
                </div>
              </div>
              <p className="gallery-caption">Track bookings and attendance trends month over month.</p>
            </div>
          </div>
        </div>

        <div className="tour-cta">
          <a href="/demo.html" className="btn-primary">Take the Product Tour →</a>
        </div>
      </MarketingSubpageChrome>
    </div>
  );
}
