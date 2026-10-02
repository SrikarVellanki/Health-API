
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import app
from db import get_connection

client = TestClient(app)


@pytest.fixture
def clinic_id():
    # Give each test an isolated clinic ID.
    test_clinic = f"TEST-{uuid4()}"

    yield test_clinic

    # Remove only this test's records, never existing bookings.
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM appointments WHERE clinic_id = %s",
                (test_clinic,),
            )



def test_successful_booking(clinic_id):
    response = client.post("/appointments", json={
        "patient_id": "FAKE-P001",
        "clinic_id": clinic_id,
        "provider_id": "DOCTOR-001",
        "start_at": "2030-06-15T10:00:00+05:30",
    })

    assert response.status_code == 201
    data = response.json()

    assert data["status"] == "booked"
    assert data["patient_id"] == "FAKE-P001"

    # Verify the appointment was actually saved in PostgreSQL.
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT patient_id, status
                FROM appointments
                WHERE id = %s
                """,
                (data["id"],),
            )
            saved_record = cur.fetchone()

    assert saved_record is not None
    assert saved_record[0] == "FAKE-P001"
    assert saved_record[1] == "booked"


def test_reject_overlapping_booking(clinic_id):
    payload = {
        "patient_id": "FAKE-P001",
        "clinic_id": clinic_id,
        "provider_id": "DOCTOR-001",
        "start_at": "2030-06-15T10:00:00+05:30",
    }

    first = client.post("/appointments", json=payload)

    second = client.post("/appointments", json={
        **payload,
        "patient_id": "FAKE-P002",
        "start_at": "2030-06-15T10:15:00+05:30",
    })

    assert first.status_code == 201
    assert second.status_code == 409


def test_reject_timezone_naive_datetime(clinic_id):
    response = client.post("/appointments", json={
        "patient_id": "FAKE-P003",
        "clinic_id": clinic_id,
        "provider_id": "DOCTOR-001",
        "start_at": "2030-06-15T10:00:00",
    })

    assert response.status_code == 422


def test_different_provider_can_be_booked(clinic_id):
    payload = {
        "patient_id": "FAKE-P001",
        "clinic_id": clinic_id,
        "provider_id": "DOCTOR-001",
        "start_at": "2030-06-15T10:00:00+05:30",
    }

    first = client.post("/appointments", json=payload)

    second = client.post("/appointments", json={
        **payload,
        "patient_id": "FAKE-P002",
        "provider_id": "DOCTOR-002",
    })

    assert first.status_code == 201
    assert second.status_code == 201
def test_cancel_appointment(clinic_id):
    # Create a synthetic appointment
    response = client.post("/appointments", json={
        "patient_id": "FAKE-CANCEL-001",
        "clinic_id": clinic_id,
        "provider_id": "DOCTOR-001",
        "start_at": "2030-06-15T10:00:00+05:30",
    })

    assert response.status_code == 201
    appointment_id = response.json()["id"]

    # Cancel the appointment
    cancel_response = client.post(
        f"/appointments/{appointment_id}/cancel"
    )

    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    # Verify the change was saved in PostgreSQL
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM appointments WHERE id = %s",
                (appointment_id,),
            )
            saved_status = cur.fetchone()

    assert saved_status is not None
    assert saved_status[0] == "cancelled"
def test_cancelled_slot_can_be_booked_again(clinic_id):
    payload = {
        "patient_id": "FAKE-P001",
        "clinic_id": clinic_id,
        "provider_id": "DOCTOR-001",
        "start_at": "2030-06-15T10:00:00+05:30",
    }

    # Book the slot
    first = client.post("/appointments", json=payload)
    assert first.status_code == 201

    appointment_id = first.json()["id"]

    # Cancel the first booking
    cancelled = client.post(
        f"/appointments/{appointment_id}/cancel"
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # A different patient books the same slot
    second = client.post("/appointments", json={
        **payload,
        "patient_id": "FAKE-P002",
    })

    assert second.status_code == 201
    assert second.json()["status"] == "booked"
def test_get_appointment_by_id(clinic_id):
    # Create a synthetic appointment
    response = client.post("/appointments", json={
        "patient_id": "FAKE-GET-001",
        "clinic_id": clinic_id,
        "provider_id": "DOCTOR-001",
        "start_at": "2030-06-15T10:00:00+05:30",
    })

    assert response.status_code == 201
    appointment_id = response.json()["id"]

    # Retrieve that appointment
    result = client.get(f"/appointments/{appointment_id}")

    assert result.status_code == 200
    assert result.json()["id"] == appointment_id
    assert result.json()["patient_id"] == "FAKE-GET-001"
def test_get_nonexistent_appointment():
    response = client.get(
        "/appointments/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Appointment not found."

def test_successful_reschedule(clinic_id):
    # Create a synthetic appointment
    response = client.post("/appointments", json={
        "patient_id": "FAKE-RESCHEDULE-001",
        "clinic_id": clinic_id,
        "provider_id": "DOCTOR-001",
        "start_at": "2030-07-10T10:00:00+05:30",
    })

    assert response.status_code == 201
    appointment_id = response.json()["id"]

    # Move the appointment from 10:00 to 11:00
    result = client.put(
        f"/appointments/{appointment_id}",
        params={"new_start_at": "2030-07-10T11:00:00+05:30"},
    )

    assert result.status_code == 200
    assert result.json()["id"] == appointment_id
    assert result.json()["status"] == "booked"
    assert result.json()["start_at"].startswith("2030-07-10T11:00:00")
    assert result.json()["ends_at"].startswith("2030-07-10T11:30:00")

def test_reschedule_conflict_preserves_original_booking(clinic_id):
    # Create the first appointment at 10:00
    first = client.post("/appointments", json={
        "patient_id": "FAKE-RESCHEDULE-001",
        "clinic_id": clinic_id,
        "provider_id": "DOCTOR-001",
        "start_at": "2030-07-10T10:00:00+05:30",
    })
    assert first.status_code == 201
    appointment_id = first.json()["id"]

    # Create another appointment at 11:00
    second = client.post("/appointments", json={
        "patient_id": "FAKE-RESCHEDULE-002",
        "clinic_id": clinic_id,
        "provider_id": "DOCTOR-001",
        "start_at": "2030-07-10T11:00:00+05:30",
    })
    assert second.status_code == 201

    # Try to move the first appointment into the occupied 11:00 slot
    result = client.put(
        f"/appointments/{appointment_id}",
        params={"new_start_at": "2030-07-10T11:00:00+05:30"},
    )

    assert result.status_code == 409

    # Confirm the original appointment remains at 10:00
    check = client.get(f"/appointments/{appointment_id}")

    assert check.status_code == 200
    assert check.json()["start_at"].startswith("2030-07-10T10:00:00")
    assert check.json()["status"] == "booked"

def test_reject_blank_patient_id(clinic_id):
    response = client.post("/appointments", json={
        "patient_id": "   ",
        "clinic_id": clinic_id,
        "provider_id": "DOCTOR-001",
        "start_at": "2030-07-10T10:00:00+05:30",
    })

    assert response.status_code == 422