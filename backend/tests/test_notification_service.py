"""
Tests for app/services/notification_service.py
Target: message template builders, channel selection logic,
        notification scheduling, message formatting.

Coverage goals: ≥85% of notification_service.py
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.services.notification_service import (
    build_reminder_message,
    build_confirmation_message,
    build_no_show_followup_message,
    build_reschedule_message,
)


BASE_URL = "https://vitar.health"
APT_TIME = datetime(2026, 6, 15, 14, 30)  # 2:30 PM


# ── build_reminder_message ─────────────────────────────────────────────────────

class TestBuildReminderMessage:
    def test_contains_patient_first_name(self):
        msg = build_reminder_message("Amaka", "Okonkwo", APT_TIME, "CityMed", "tok123", BASE_URL)
        assert "Amaka" in msg

    def test_contains_doctor_name(self):
        msg = build_reminder_message("Amaka", "Okonkwo", APT_TIME, "CityMed", "tok123", BASE_URL)
        assert "Okonkwo" in msg

    def test_contains_token_for_cancel_link(self):
        msg = build_reminder_message("Amaka", "Okonkwo", APT_TIME, "CityMed", "cancel-token-xyz", BASE_URL)
        assert "cancel-token-xyz" in msg

    def test_contains_clinic_name(self):
        msg = build_reminder_message("Amaka", "Okonkwo", APT_TIME, "City Medical Centre", "tok", BASE_URL)
        assert "City Medical Centre" in msg

    def test_contains_appointment_time(self):
        msg = build_reminder_message("Amaka", "Okonkwo", APT_TIME, "CityMed", "tok", BASE_URL)
        # Should include some representation of the time (14:30, 2:30, PM, etc.)
        assert any(x in msg for x in ["14:30", "2:30", "PM", "pm", "14", "Jun", "June", "15"])

    def test_contains_base_url(self):
        msg = build_reminder_message("Amaka", "Okonkwo", APT_TIME, "CityMed", "tok", BASE_URL)
        assert BASE_URL in msg or "vitar.health" in msg

    def test_non_empty_output(self):
        msg = build_reminder_message("A", "B", APT_TIME, "C", "tok", BASE_URL)
        assert len(msg) > 50

    def test_unicode_names_handled(self):
        msg = build_reminder_message("Adéolà", "Adéjọbí", APT_TIME, "Clinic", "tok", BASE_URL)
        assert "Adéolà" in msg

    def test_international_clinic_name(self):
        msg = build_reminder_message("Yuki", "Tanaka", APT_TIME, "東京クリニック", "tok", BASE_URL)
        assert "Yuki" in msg


# ── build_confirmation_message ────────────────────────────────────────────────

class TestBuildConfirmationMessage:
    def test_contains_patient_first_name(self):
        msg = build_confirmation_message("Tolu", "Adeleke", APT_TIME, "HealthCo", "conf-abc", BASE_URL)
        assert "Tolu" in msg

    def test_contains_confirmation_token(self):
        msg = build_confirmation_message("Tolu", "Adeleke", APT_TIME, "HealthCo", "conf-xyz-789", BASE_URL)
        assert "conf-xyz-789" in msg

    def test_contains_doctor_name(self):
        msg = build_confirmation_message("Tolu", "Adeleke", APT_TIME, "HealthCo", "tok", BASE_URL)
        assert "Adeleke" in msg

    def test_not_empty(self):
        msg = build_confirmation_message("A", "B", APT_TIME, "C", "tok", BASE_URL)
        assert len(msg) > 50

    def test_different_output_from_reminder(self):
        reminder = build_reminder_message("Tolu", "Adeleke", APT_TIME, "HealthCo", "tok", BASE_URL)
        confirmation = build_confirmation_message("Tolu", "Adeleke", APT_TIME, "HealthCo", "tok", BASE_URL)
        # Should be different messages (confirmation vs reminder)
        assert reminder != confirmation


# ── build_no_show_followup_message ─────────────────────────────────────────────

class TestBuildNoShowFollowupMessage:
    def test_contains_patient_first_name(self):
        msg = build_no_show_followup_message("Chidi", "Wellness Hub", "+2348012345678")
        assert "Chidi" in msg

    def test_contains_clinic_name(self):
        msg = build_no_show_followup_message("Chidi", "Wellness Hub Nigeria", "+2348012345678")
        assert "Wellness Hub Nigeria" in msg

    def test_contains_contact_number(self):
        msg = build_no_show_followup_message("Chidi", "Wellness Hub", "+2348012345678")
        assert "+2348012345678" in msg or "2348012345678" in msg

    def test_non_empty_output(self):
        msg = build_no_show_followup_message("A", "B", "+1234567890")
        assert len(msg) > 30

    def test_empathetic_tone(self):
        """Follow-up message should sound caring, not accusatory."""
        msg = build_no_show_followup_message("Chidi", "Clinic", "+2348012345678")
        # Should contain re-engagement wording
        empathy_words = ["missed", "hope", "reschedule", "help", "appointment", "contact", "book"]
        assert any(w.lower() in msg.lower() for w in empathy_words)


# ── build_reschedule_message ──────────────────────────────────────────────────

class TestBuildRescheduleMessage:
    def test_contains_patient_name(self):
        msg = build_reschedule_message("Ngozi", "Eze", APT_TIME, "MedCare")
        assert "Ngozi" in msg

    def test_contains_doctor_name(self):
        msg = build_reschedule_message("Ngozi", "Eze", APT_TIME, "MedCare")
        assert "Eze" in msg

    def test_contains_clinic_name(self):
        msg = build_reschedule_message("Ngozi", "Eze", APT_TIME, "MedCare Lagos")
        assert "MedCare Lagos" in msg

    def test_contains_new_time(self):
        new_time = datetime(2026, 7, 20, 9, 0)
        msg = build_reschedule_message("Ngozi", "Eze", new_time, "MedCare")
        assert any(x in msg for x in ["9:00", "09:00", "Jul", "July", "20"])

    def test_non_empty_output(self):
        msg = build_reschedule_message("A", "B", APT_TIME, "C")
        assert len(msg) > 30


# ── Cross-message consistency ─────────────────────────────────────────────────

class TestMessageConsistency:
    def test_all_builders_return_strings(self):
        assert isinstance(build_reminder_message("A", "B", APT_TIME, "C", "tok", BASE_URL), str)
        assert isinstance(build_confirmation_message("A", "B", APT_TIME, "C", "tok", BASE_URL), str)
        assert isinstance(build_no_show_followup_message("A", "B", "+1234"), str)
        assert isinstance(build_reschedule_message("A", "B", APT_TIME, "C"), str)

    def test_very_long_names_handled(self):
        long_name = "A" * 100
        msg = build_reminder_message(long_name, long_name, APT_TIME, long_name, "tok", BASE_URL)
        assert isinstance(msg, str)

    def test_special_characters_in_clinic_name(self):
        msg = build_reminder_message("Jo", "Doe", APT_TIME, "St. Mary's & Sons Ltd.", "tok", BASE_URL)
        assert isinstance(msg, str)
        assert len(msg) > 0
