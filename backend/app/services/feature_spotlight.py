"""
Vitar — Weekly Feature Spotlight content.

One entry sent per week to registered clinic owners (app.workers.tasks.
send_feature_spotlight), rotating by ISO week number so the same clinic
doesn't see the same tip twice for several weeks. Every entry describes a
feature that actually exists in the product today — this is user
education, not a product-roadmap teaser.
"""

SPOTLIGHTS = [
    {
        "subject": "Get found by patients searching for your clinic",
        "headline": "Patients can already search for you on Vitar",
        "body_html": """
        <p>Your clinic has a public profile on Vitar's patient search — no QR code
        or shared link required. A patient looking for a clinic near them can find
        <strong>your name</strong> directly and book straight in.</p>
        <p>Make sure your clinic name, address, and services are filled in under
        Settings so you show up clearly when a patient searches.</p>
        """,
    },
    {
        "subject": "Skip the front-desk paperwork with e-registration",
        "headline": "Let patients register before they arrive",
        "body_html": """
        <p>Patients can fill in their own registration details from their phone
        <strong>before</strong> they get to your clinic — no more handing out a
        clipboard at the front desk.</p>
        <p>By the time they walk in, their details are already in your dashboard
        and the doctor is ready to see them.</p>
        """,
    },
    {
        "subject": "Your booking page needs no app download",
        "headline": "One link, zero downloads, more booked slots",
        "body_html": """
        <p>Your public booking page works in any browser — a patient picks a
        doctor, a time, and a reason for the visit in under a minute, with
        nothing to install.</p>
        <p>Share your booking link on WhatsApp status, Instagram bio, or your
        signage — every extra place it's posted is another way patients find you.</p>
        """,
    },
    {
        "subject": "Reminders are already cutting your no-shows",
        "headline": "WhatsApp, SMS, and email — automatically",
        "body_html": """
        <p>Every booked appointment on Vitar gets automatic reminders across
        WhatsApp, SMS, and email — no front-desk staff member needs to
        remember to call anyone.</p>
        <p>Clinics using automated reminders consistently see fewer missed
        appointments than clinics relying on manual phone calls.</p>
        """,
    },
    {
        "subject": "Vitar flags which appointments are at risk",
        "headline": "Know which patients might not show up",
        "body_html": """
        <p>Vitar scores each upcoming appointment's no-show risk based on the
        patient's history, so your front desk can follow up personally with the
        ones most likely to skip.</p>
        <p>Check the risk indicator on your dashboard before the day starts to
        see where a quick reminder call is worth the extra effort.</p>
        """,
    },
    {
        "subject": "QR check-in speeds up your waiting room",
        "headline": "Check patients in with a scan, not a queue",
        "body_html": """
        <p>Your clinic's QR code lets arriving patients check themselves in
        instantly, instead of queuing at the front desk to confirm they're here.</p>
        <p>Print it at your reception or display it on a screen — it's under
        Settings → QR Code whenever you need to reprint it.</p>
        """,
    },
    {
        "subject": "See your clinic's numbers at a glance",
        "headline": "Your analytics dashboard is already tracking this",
        "body_html": """
        <p>Booking volume, no-show trends, and revenue are tracked automatically
        on your Analytics page — no spreadsheet required.</p>
        <p>Worth a weekly look: it's often the fastest way to spot a doctor's
        schedule filling up, or a slot that keeps going empty.</p>
        """,
    },
    {
        "subject": "A full slot doesn't have to mean a lost patient",
        "headline": "The waiting list fills cancellations automatically",
        "body_html": """
        <p>When a patient cancels, Vitar can offer that freed-up slot to patients
        on your waiting list automatically — instead of it just sitting empty.</p>
        <p>It's a quiet way to recover appointments you'd otherwise lose to a
        last-minute cancellation.</p>
        """,
    },
]


def get_weekly_spotlight(iso_week: int) -> dict:
    return SPOTLIGHTS[iso_week % len(SPOTLIGHTS)]
