

# ─── QR Onboarding additions (appended — does not modify anything above) ─────
#
# These two endpoints support the public portal page (/portal/{slug} in the
# frontend) that a patient lands on after scanning a clinic's QR code.
#
#   GET  /booking/clinic/{slug}/portal   -> minimal public clinic info,
#                                            reuses the same Clinic lookup
#                                            pattern as get_clinic_booking_page
#                                            above but without requiring
#                                            booking_page_enabled (a clinic
#                                            may want QR registration without
#                                            exposing live booking slots).
#
#   POST /booking/clinic/{slug}/register-patient
#                                          -> creates (or updates) a Patient
#                                            row tied to this clinic. Same
#                                            upsert-by-phone pattern as
#                                            public_book_appointment above —
#                                            no password, no login, matches
#                                            existing Vitar patient model
#                                            (Patient has no auth fields).
#
# Works for every clinic/org type (hospital, clinic, eye clinic, lab, ...)
# since Vitar already represents all of these as `Clinic` rows — no new
# model required.


class PatientSelfRegisterRequest(BaseModel):
    full_name: str
    phone: str
    email: Optional[EmailStr] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None


@router.get("/clinic/{slug}/portal")
def get_clinic_portal_info(slug: str, db: Session = Depends(get_db)):
    """
    Minimal public info for the QR-landing portal page. Deliberately does
    NOT require booking_page_enabled or online_booking_enabled — a clinic
    may want patients to be able to register via QR even if they manage
    bookings manually over the phone.
    """
    clinic = db.query(Clinic).filter(
        Clinic.slug == slug,
        Clinic.is_active == True,
    ).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Hospital/clinic not found")

    return {
        "id": str(clinic.id),
        "name": clinic.name or "",
        "slug": clinic.slug or "",
        "logo_url": clinic.logo_url or "",
        "address": clinic.address or "",
        "city": clinic.city or "",
        "phone": clinic.phone or "",
        "booking_enabled": bool(clinic.online_booking_enabled and clinic.booking_page_enabled),
    }


@router.post("/clinic/{slug}/register-patient", status_code=201)
def register_patient_via_qr(
    slug: str,
    body: PatientSelfRegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Patient self-registration entry point reached by scanning a clinic's
    QR code. Creates a Patient record scoped to this clinic — same
    upsert-by-phone semantics as the existing booking flow, so a patient
    who later books an appointment through the normal booking page is
    matched to the same record instead of being duplicated.

    No login/credentials are created — this mirrors Vitar's existing
    patient model, which has no authentication fields. Patients are
    identified by phone number within a clinic, consistent with
    public_book_appointment() above.
    """
    clinic = db.query(Clinic).filter(
        Clinic.slug == slug,
        Clinic.is_active == True,
    ).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Hospital/clinic not found")

    if not body.phone:
        raise HTTPException(status_code=422, detail="Phone number is required")

    patient = db.query(Patient).filter(
        Patient.clinic_id == clinic.id,
        Patient.phone == body.phone,
    ).first()

    created = False
    if not patient:
        patient = Patient(
            clinic_id=clinic.id,
            full_name=body.full_name or "",
            phone=body.phone,
            email=body.email,
            date_of_birth=body.date_of_birth,
            gender=body.gender,
        )
        db.add(patient)
        created = True
    else:
        # Already registered at this clinic — treat as a profile refresh,
        # not an error, so a re-scan never fails for the patient.
        if body.full_name:
            patient.full_name = body.full_name
        if body.email:
            patient.email = body.email
        if body.gender:
            patient.gender = body.gender
        if body.date_of_birth:
            patient.date_of_birth = body.date_of_birth

    try:
        db.commit()
        db.refresh(patient)
    except Exception as e:
        db.rollback()
        logger.error(f"QR patient self-registration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Registration failed — please try again")

    log_booking_event(
        "patient_self_registered_via_qr" if created else "patient_self_registered_via_qr_updated",
        patient.id,
        clinic.id,
    )

    return {
        "patient_id": patient.id,
        "clinic": clinic.name or "",
        "clinic_slug": clinic.slug,
        "message": f"You're registered at {clinic.name}.",
        "booking_enabled": bool(clinic.online_booking_enabled and clinic.booking_page_enabled),
    }
