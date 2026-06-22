"""
Vitar QR Onboarding — Apply Script

Run this INSIDE the vitar-api-1 container after copying in the new files.
Makes two minimal, surgical edits to EXISTING files:

  1. router.py  — adds one import + one include_router line for the new
                  qr.py endpoint module. Nothing else in router.py changes.

  2. auth.py    — adds a QR auto-generation call right after the clinic
                  is committed in register(). Wrapped in try/except so
                  a QR-generation failure (e.g. disk issue) NEVER blocks
                  clinic registration — registration still succeeds and
                  the QR can be lazily generated later via GET /qr/me.

booking.py is NOT edited by this script — it is fully replaced by
booking_py_append.py being concatenated onto the existing file (append,
not overwrite of existing content). That happens via a separate `cat >>`
shell step, not via string-replace, since we are adding wholly new code
at the end rather than modifying an existing line.
"""

# ── 1. Patch router.py ────────────────────────────────────────────────────
with open('/app/app/api/v1/router.py', 'r') as f:
    router_content = f.read()

old_import_block = """from app.api.v1.endpoints import (
    auth,
    clinics,
    doctors,
    patients,
    appointments,
    booking,
    notifications,
    billing,
    analytics,
    ai,
    webhooks,
    geo,
    onboarding,
    waiting_list,
    uploads,
    admin_api_keys,
)"""

new_import_block = """from app.api.v1.endpoints import (
    auth,
    clinics,
    doctors,
    patients,
    appointments,
    booking,
    notifications,
    billing,
    analytics,
    ai,
    webhooks,
    geo,
    onboarding,
    waiting_list,
    uploads,
    admin_api_keys,
    qr,
)"""

old_include_block = 'api_router.include_router(admin_api_keys.router, tags=["Admin — API Keys"])'
new_include_block = (
    'api_router.include_router(admin_api_keys.router, tags=["Admin — API Keys"])\n'
    'api_router.include_router(qr.router, prefix="/qr", tags=["QR Onboarding"])'
)

router_patched = True
if old_import_block in router_content:
    router_content = router_content.replace(old_import_block, new_import_block)
else:
    router_patched = False
    print("WARNING: router.py import block not found exactly as expected — skipped import patch")

if old_include_block in router_content:
    router_content = router_content.replace(old_include_block, new_include_block)
else:
    router_patched = False
    print("WARNING: router.py include_router line not found exactly as expected — skipped include patch")

if router_patched:
    with open('/app/app/api/v1/router.py', 'w') as f:
        f.write(router_content)
    print("router.py patched: qr router registered at /api/v1/qr")
else:
    print("router.py NOT patched — manual review needed (see WARNINGs above)")


# ── 2. Patch auth.py — auto-generate QR right after clinic commit ─────────
with open('/app/app/api/v1/endpoints/auth.py', 'r') as f:
    auth_content = f.read()

# This matches the exact block left after the earlier transaction-commit
# fix applied during local debugging (db.commit() + db.refresh(clinic)
# right after clinic creation).
anchor = """    db.add(clinic)
    db.commit()
    db.refresh(clinic)"""

hook = """    db.add(clinic)
    db.commit()
    db.refresh(clinic)

    # QR Onboarding: auto-generate this clinic's QR code now that it has
    # a committed id + slug. Never blocks registration — a clinic that
    # fails QR generation here still registers successfully; the QR can
    # be lazily generated later via GET /api/v1/qr/me.
    try:
        from app.services.qr_service import generate_clinic_qr
        clinic.qr_code_path = generate_clinic_qr(clinic)
        db.commit()
    except Exception as _qr_exc:
        import logging as _logging
        _logging.getLogger("vitar.auth").warning(
            f"QR auto-generation failed for clinic {clinic.id}: {_qr_exc}"
        )
        db.rollback()"""

auth_patched = False
if anchor in auth_content:
    # Only replace the FIRST occurrence to avoid touching anything else
    # that might coincidentally match.
    auth_content = auth_content.replace(anchor, hook, 1)
    with open('/app/app/api/v1/endpoints/auth.py', 'w') as f:
        f.write(auth_content)
    auth_patched = True
    print("auth.py patched: QR auto-generation hooked into register()")
else:
    print("WARNING: auth.py anchor block not found — QR auto-gen NOT hooked in. "
          "New clinics will get their QR lazily on first GET /api/v1/qr/me call instead, "
          "which still works fine, just isn't fully automatic at signup time.")

print("\nDone. Summary:")
print(f"  router.py patched: {router_patched}")
print(f"  auth.py patched:   {auth_patched}")
