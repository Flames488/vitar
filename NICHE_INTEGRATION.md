# Vitar — Wabizz Integration Changes

## What Was Added

### New Files
| File | Purpose |
|------|---------|
| `backend/app/middleware/api_key_auth.py` | FastAPI dependency: validates X-API-Key header against bcrypt-hashed keys in api_keys table |
| `backend/app/models/api_key.py` | SQLAlchemy model for api_keys table + `generate()` and `verify()` helpers |
| `backend/alembic/versions/006_add_api_keys.py` | Alembic migration: creates api_keys table with indexes |
| `frontend/src/pages/admin/ApiKeys.tsx` | Admin UI: list/generate/revoke API keys (key shown once at creation) |

### Modified Files
| File | Changes |
|------|---------|
| `backend/app/api/v1/endpoints/doctors.py` | Added `GET /api/v1/doctors/wabizz/list` and `GET /api/v1/doctors/wabizz/{id}/slots` — API-key-protected, no clinic JWT needed |
| `backend/app/api/v1/endpoints/patients.py` | Added `GET /api/v1/patients/by-phone/{phone}`, `POST /api/v1/patients/wabizz`, `GET /api/v1/patients/wabizz/{id}/appointments` |
| `backend/app/api/v1/endpoints/appointments.py` | Added `POST /api/v1/appointments/wabizz`, `GET /api/v1/appointments/wabizz/{id}`, `PATCH /api/v1/appointments/wabizz/{id}` |
| `backend/app/main.py` | Added CORSMiddleware allowing Wabizz Workers domain |
| `frontend/src/App.tsx` | Added `/settings/api-keys` route for ApiKeys page |

## Wabizz API Endpoint Reference

All endpoints below require `X-API-Key: <your-key>` header. No browser session needed.

### Doctors
```
GET  /api/v1/doctors/wabizz/list?specialty=<optional>   → list active doctors
GET  /api/v1/doctors/wabizz/{id}/slots?date=YYYY-MM-DD  → available slots (WAT timezone, ISO 8601)
```

### Patients
```
GET  /api/v1/patients/by-phone/{E164phone}              → find patient, 404 if not found
POST /api/v1/patients/wabizz                            → create patient {full_name, phone, email?}
GET  /api/v1/patients/wabizz/{id}/appointments          → patient appointment history (last 20)
```

### Appointments
```
POST  /api/v1/appointments/wabizz                        → book appointment {doctor_id, patient_id, scheduled_at, ...}
GET   /api/v1/appointments/wabizz/{id}                   → get appointment details
PATCH /api/v1/appointments/wabizz/{id}                   → update status/notes/reschedule
```

## Generating a Wabizz API Key (Clinic Admin)

1. Log into your Vitar dashboard
2. Go to **Settings → API Keys** (`/settings/api-keys`)
3. Click **Generate Key**, enter label "Wabizz Integration"
4. **Copy the key immediately** — it is only shown once
5. Store it in Wabizz's Supabase Vault (see Wabizz NICHE_INTEGRATION.md)

## What Was NOT Changed

Everything else in Vitar is untouched:
- Doctor management, availability, specialties
- Patient records and history
- Appointment booking logic and anti-double-booking
- Celery reminder scheduling and no-show AI scoring
- Paystack billing and subscription management
- SMS/WhatsApp/Email notification system
- Analytics and reporting
- All existing browser-auth endpoints
