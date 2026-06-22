#!/usr/bin/env python3
"""
Vitar — Create Superadmin

Bootstrap the first superadmin account. Safe to run multiple times —
it checks for an existing account before creating one.

Usage (from the backend/ directory):
    python scripts/create_superadmin.py

Or with explicit credentials (non-interactive, for CI/CD):
    ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=secret ADMIN_NAME="Admin" \
        python scripts/create_superadmin.py

Requirements:
    - DATABASE_URL must be set in environment (or .env loaded by config.py)
    - Run AFTER migrations: alembic upgrade head
"""

import os
import sys

# Allow running from repo root or backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.models.models import User, Base


def get_input(prompt: str, env_key: str, secret: bool = False) -> str:
    val = os.environ.get(env_key, "").strip()
    if val:
        return val
    if secret:
        import getpass
        return getpass.getpass(prompt)
    return input(prompt).strip()


def main():
    print("=== Vitar Superadmin Bootstrap ===\n")

    email = get_input("Admin email: ", "ADMIN_EMAIL")
    password = get_input("Admin password: ", "ADMIN_PASSWORD", secret=True)
    full_name = get_input("Admin name [Vitar Admin]: ", "ADMIN_NAME") or "Vitar Admin"

    if not email or not password:
        print("ERROR: email and password are required.")
        sys.exit(1)

    if len(password) < 8:
        print("ERROR: password must be at least 8 characters.")
        sys.exit(1)

    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            if existing.is_superadmin:
                print(f"[OK] Superadmin already exists: {email}")
            else:
                existing.is_superadmin = True
                existing.is_active = True
                db.commit()
                print(f"[UPDATED] Existing user promoted to superadmin: {email}")
            return

        import uuid
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_active=True,
            is_verified=True,
            is_superadmin=True,
        )
        db.add(user)
        db.commit()
        print(f"\n[CREATED] Superadmin account created: {email}")
        print("\nAccess the API directly — there is no separate admin UI.")
        print("The superadmin flag grants elevated permissions on admin-only endpoints.")

    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
