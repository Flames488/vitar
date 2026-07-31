# Vitar changes — trial bug fix + Doctor Details ("Talk with a Doctor") feature

Every file here replaces the file at the same relative path in your repo
(`backend/app/...`, `frontend/src/...`). Nothing else in your codebase needs
to change.

## 1. Trial expiry desync fix

**File:** `backend/app/api/v1/endpoints/admin_subscriptions.py`

Your superadmin override actions (`grant_free`, `grant_temporary`,
`grant_lifetime`, `extend`, `set_expiration`, `revoke`) only ever updated
`Subscription.current_period_end`. But the code that actually enforces trial
limits and computes "days left" (`app/services/trial_guard.py`) reads
`Clinic.trial_ends_at` — a **separate column** that those overrides never
touched. The two could silently drift apart. This fix keeps them in sync on
every override action.

**This alone doesn't prove what happened to your client** — I can't see your
live database from here. To actually confirm/fix that specific account, SSH
in and run:

```bash
ssh root@162.35.183.95
cd /path/to/vitar   # wherever docker-compose.yml lives on the VPS
docker exec -it $(docker compose ps -q api) printenv | grep TRIAL_DAYS
```
If that prints nothing, `TRIAL_DAYS` is using the code default (30) — good.
If it prints something other than 30, that's your bug; fix it in the VPS's
`.env` and restart the api container.

Then check the actual stored dates for the affected clinic:
```bash
docker exec -it $(docker compose ps -q postgres) psql -U <db_user> -d vitar -c \
  "SELECT c.name, c.trial_started_at, c.trial_ends_at, s.current_period_start, s.current_period_end, s.status
   FROM clinics c JOIN subscriptions s ON s.clinic_id = c.id
   WHERE c.name ILIKE '%aproko%';"
```
(swap `<db_user>` for whatever's in your `.env` — likely `vitar` or `postgres`)

If `trial_ends_at` isn't exactly `trial_started_at + 30 days`, that confirms
a bad write happened (manual override, old buggy deploy, etc.) — you can
correct it directly:
```sql
UPDATE clinics SET trial_ends_at = trial_started_at + interval '30 days' WHERE id = '<clinic_id>';
UPDATE subscriptions SET current_period_end = (SELECT trial_ends_at FROM clinics WHERE id = '<clinic_id>') WHERE clinic_id = '<clinic_id>';
```

## 2. Doctor Details / "Talk with a Doctor" (new paid feature)

**New column:** `doctors.consultation_contact_enabled` (bool, default false)
— migration `backend/alembic/versions/015_doctor_consultation_contact.py`.

**Gating rule** (in `app/services/trial_guard.py`, `has_doctor_contact_access`):
- Every clinic gets it free while `status == "trialing"`.
- After the trial ends, only clinics on an active **basic/pro/enterprise**
  plan can use it — no further per-tier distinction.

**Backend files changed:**
- `app/services/trial_guard.py` — new `has_doctor_contact_access(clinic)` helper.
- `app/api/v1/endpoints/doctors.py` — `PATCH /doctors/{id}` now accepts
  `consultation_contact_enabled`; turning it **on** is rejected with a 402
  (`DOCTOR_CONTACT_NOT_AVAILABLE`) if the clinic isn't entitled. Doctor
  responses now include `consultation_contact_enabled` (the doctor's own
  toggle) and `doctor_contact_feature_available` (whether the clinic is
  currently entitled at all).
- `app/api/v1/endpoints/booking.py` — the **public** booking page endpoint
  now includes a doctor's `email`/`phone` only when both the doctor opted in
  AND the clinic is entitled. Cached response (5-min TTL) picks this up
  automatically.

**Frontend files changed:**
- `frontend/src/pages/dashboard/DoctorDetailPage.tsx` — doctors/clinic staff
  can now edit a doctor's email/phone after creation (previously only
  settable at creation time), and toggle "Talk with a Doctor" visibility,
  with a lock icon + upgrade prompt when the clinic isn't entitled.
- `frontend/src/pages/booking/PublicBookingPage.tsx` — shows a "Talk with
  Dr. X directly" contact card (tel:/mailto: links) once a doctor is
  selected, only when the backend actually included contact info.

## 3. Deploying

```bash
ssh root@162.35.183.95
cd /path/to/vitar
# copy the changed files in from wherever you extract this bundle, then:
docker compose exec api alembic upgrade head
docker compose build api          # if you rebuild images rather than bind-mount source
docker compose up -d api
# for the frontend, rebuild/redeploy however you normally ship frontend/ (e.g. npm run build then your usual static deploy step)
```

If your prod setup is Docker with bind-mounted source (no rebuild needed for
Python), you may only need `docker compose restart api` after the alembic
migration. Check `docker-compose.prod.yml` to confirm which mode you're in.
