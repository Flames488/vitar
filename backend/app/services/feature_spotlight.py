"""
Vitar — Feature Spotlight content.

Sent Monday/Wednesday/Friday to registered clinic owners
(app.workers.tasks.send_feature_spotlight), rotating by day-ordinal so the
rotation doesn't reset weekly. Every entry describes a feature that
actually exists in the product today — this is user education, not a
product-roadmap teaser. Kept short by design: one line, no filler.

Monday sends carry a short motivational closer; Friday sends carry a short
"have a great weekend" closer — see MONDAY_CLOSERS / FRIDAY_CLOSERS below.
"""

SPOTLIGHTS = [
    {
        "subject": "Get found by patients searching for your clinic",
        "headline": "Patients can already search for you on Vitar",
        "body_html": """
        <p>Your clinic shows up in Vitar's patient search — no QR code or shared
        link needed. Make sure your name, address, and services are filled in
        under Settings so patients find you easily.</p>
        """,
    },
    {
        "subject": "Skip the front-desk paperwork with e-registration",
        "headline": "Let patients register before they arrive",
        "body_html": """
        <p>Patients can fill in their registration from their phone before they
        get to your clinic — no clipboard, no queue at the front desk.</p>
        """,
    },
    {
        "subject": "Your booking page needs no app download",
        "headline": "One link, zero downloads, more booked slots",
        "body_html": """
        <p>Your public booking page works in any browser. Share the link on
        WhatsApp status, Instagram bio, or signage — every extra place it's
        posted is another way patients find you.</p>
        """,
    },
    {
        "subject": "Reminders are already cutting your no-shows",
        "headline": "WhatsApp, SMS, and email — automatically",
        "body_html": """
        <p>Every booking gets automatic reminders across WhatsApp, SMS, and
        email — no one on your team has to remember to call.</p>
        """,
    },
    {
        "subject": "Vitar flags which appointments are at risk",
        "headline": "Know which patients might not show up",
        "body_html": """
        <p>Vitar scores each appointment's no-show risk from patient history —
        check your dashboard each morning for who's worth a personal follow-up.</p>
        """,
    },
    {
        "subject": "QR check-in speeds up your waiting room",
        "headline": "Check patients in with a scan, not a queue",
        "body_html": """
        <p>Your clinic's QR code lets arriving patients check in instantly.
        Reprint it anytime under Settings → QR Code.</p>
        """,
    },
    {
        "subject": "See your clinic's numbers at a glance",
        "headline": "Your analytics dashboard is already tracking this",
        "body_html": """
        <p>Booking volume, no-shows, and revenue are tracked automatically on
        your Analytics page — worth a quick look each week.</p>
        """,
    },
    {
        "subject": "A full slot doesn't have to mean a lost patient",
        "headline": "The waiting list fills cancellations automatically",
        "body_html": """
        <p>When a patient cancels, Vitar can offer that slot to your waiting
        list automatically, instead of it sitting empty.</p>
        """,
    },
]

MONDAY_CLOSERS = [
    "New week, clean slate — let's make it a good one. 💪",
    "Monday momentum: small consistent effort wins the week.",
    "Here's to a productive week ahead for you and your clinic.",
]

FRIDAY_CLOSERS = [
    "You made it — have a great weekend! 🎉",
    "That's a wrap on the week. Enjoy your weekend!",
    "Well earned. Have a restful weekend ahead.",
]


def get_spotlight(day_ordinal: int) -> dict:
    return SPOTLIGHTS[day_ordinal % len(SPOTLIGHTS)]


def get_closer(weekday: int, day_ordinal: int) -> str | None:
    """weekday: Python-style, Monday=0 ... Sunday=6."""
    if weekday == 0:
        return MONDAY_CLOSERS[day_ordinal % len(MONDAY_CLOSERS)]
    if weekday == 4:
        return FRIDAY_CLOSERS[day_ordinal % len(FRIDAY_CLOSERS)]
    return None
