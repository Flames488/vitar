"""
Vitar — QR Code Generator (Enhanced CLI)

A flexible, safe replacement for one-off manual QR-generation sessions.
Generate a QR code for a single clinic by slug, by id, or for every
clinic missing one — with dry-run, force-regenerate, and JSON output
support for scripting.

Run inside the API container:

    PYTHONPATH=/app python /tmp/gen_qr.py --slug james-care
    PYTHONPATH=/app python /tmp/gen_qr.py --id 3f9a1c2e-...
    PYTHONPATH=/app python /tmp/gen_qr.py --all                 # missing only
    PYTHONPATH=/app python /tmp/gen_qr.py --all --force         # regenerate everyone
    PYTHONPATH=/app python /tmp/gen_qr.py --slug james-care --dry-run
    PYTHONPATH=/app python /tmp/gen_qr.py --all --json

Exit codes:
    0  all requested QR codes generated successfully
    1  one or more clinics failed (see output / --json "failed" list)
    2  bad arguments / no matching clinic found
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Optional

from app.core.database import SessionLocal
from app.models.models import Clinic
from app.services.qr_service import generate_clinic_qr


@dataclass
class Result:
    slug: str
    clinic_id: str
    ok: bool
    path: Optional[str] = None
    error: Optional[str] = None
    skipped: bool = False


@dataclass
class Report:
    results: list = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.ok and not r.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total": len(self.results),
                "succeeded": self.succeeded,
                "failed": self.failed,
                "skipped": self.skipped,
            },
            "results": [
                {
                    "slug": r.slug,
                    "clinic_id": r.clinic_id,
                    "ok": r.ok,
                    "path": r.path,
                    "error": r.error,
                    "skipped": r.skipped,
                }
                for r in self.results
            ],
        }


def _process_clinic(db, clinic: Clinic, *, force: bool, dry_run: bool) -> Result:
    label = clinic.slug or clinic.id

    if not clinic.slug:
        return Result(
            slug=label, clinic_id=clinic.id, ok=False,
            error="Clinic has no slug — cannot generate a portal QR code.",
        )

    if clinic.qr_code_path and not force:
        return Result(
            slug=clinic.slug, clinic_id=clinic.id, ok=True,
            path=clinic.qr_code_path, skipped=True,
        )

    if dry_run:
        return Result(
            slug=clinic.slug, clinic_id=clinic.id, ok=True,
            path="(dry-run — not generated)",
        )

    try:
        path = generate_clinic_qr(clinic)
        clinic.qr_code_path = path
        db.commit()
        return Result(slug=clinic.slug, clinic_id=clinic.id, ok=True, path=path)
    except Exception as exc:
        db.rollback()
        return Result(slug=clinic.slug, clinic_id=clinic.id, ok=False, error=str(exc))


def _print_human(report: Report, dry_run: bool) -> None:
    mode = "DRY RUN — " if dry_run else ""
    for r in report.results:
        if r.skipped:
            print(f"  SKIP  {r.slug:<30} already has a QR ({r.path})")
        elif r.ok:
            print(f"  OK    {r.slug:<30} -> {r.path}")
        else:
            print(f"  FAIL  {r.slug:<30} {r.error}")

    print(
        f"\n{mode}Done: {report.succeeded} succeeded, "
        f"{report.skipped} skipped, {report.failed} failed "
        f"(of {len(report.results)} total)."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Vitar clinic portal QR codes.",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--slug", help="Generate for a single clinic by slug.")
    target.add_argument("--id", help="Generate for a single clinic by id.")
    target.add_argument(
        "--all", action="store_true",
        help="Generate for every clinic. By default only clinics missing a "
             "QR code are processed; combine with --force to regenerate all.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Regenerate even if the clinic already has a qr_code_path.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would happen without generating files or writing to the DB.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print a machine-readable JSON report instead of human-readable text.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    report = Report()

    try:
        if args.slug:
            clinic = db.query(Clinic).filter(Clinic.slug == args.slug).first()
            if not clinic:
                msg = f"No clinic found with slug '{args.slug}'."
                if args.json:
                    print(json.dumps({"error": msg}))
                else:
                    print(msg)
                return 2
            clinics = [clinic]

        elif args.id:
            clinic = db.query(Clinic).filter(Clinic.id == args.id).first()
            if not clinic:
                msg = f"No clinic found with id '{args.id}'."
                if args.json:
                    print(json.dumps({"error": msg}))
                else:
                    print(msg)
                return 2
            clinics = [clinic]

        else:  # --all
            query = db.query(Clinic)
            if not args.force:
                query = query.filter(Clinic.qr_code_path.is_(None))
            clinics = query.order_by(Clinic.name).all()
            if not clinics and not args.json:
                print(
                    "No clinics need a QR code "
                    "(use --force to regenerate existing ones)."
                )

        for clinic in clinics:
            report.results.append(
                _process_clinic(db, clinic, force=args.force, dry_run=args.dry_run)
            )

        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_human(report, args.dry_run)

        return 1 if report.failed else 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
