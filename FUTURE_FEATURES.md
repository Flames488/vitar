# Future Features — Not Scheduled Yet

Ideas parked for later. Nothing here is committed to a timeline.

---

## Minimal EMR / clinical notes (proposed 2026-08-20)

**Problem:** Vitar has zero clinical documentation — no diagnosis, prescription,
vitals, or visit-history fields anywhere in the schema. Once a patient walks
in the door, Vitar has nothing to offer the doctor. `Appointment.notes`
(backend/app/models/models.py) already exists but is unused in any
doctor-facing UI.

**Why it matters:** scheduling and reminders are copyable by any competitor
in a weekend. Structured clinical data is what actually locks a clinic in —
it's the reason switching away gets expensive.

**Validate before building the full version.** Cheapest first step: surface
the existing `Appointment.notes` field as a "Consultation notes" box on the
appointment detail page — zero migration, zero new model. If doctors
actually use it, that's the signal to invest in the real version:

- New `ConsultationRecord` model (vitals as JSONB, diagnosis, prescription,
  clinical_notes) tied to a completed appointment
- "Start Consultation" action on the appointment detail view
- "Visit History" tab on the patient detail page
- v1.5: shareable prescription via the existing WhatsApp reminder channel

**Explicitly out of scope for v1:** ICD-10 coding, drug-interaction
checking, lab-result uploads, HMO/insurance claims — real needs, bigger
builds, not worth the risk until the cheap validation step above shows
actual doctor demand.

**Decision (2026-08-20):** holding off for now — see conversation notes.
Revisit once there's more clinic traction to justify the investment.
