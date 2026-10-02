
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, StringConstraints
from psycopg.errors import ExclusionViolation

from db import get_connection

app = FastAPI(title="HealthAI Booking API")


# Reject empty or whitespace-only identifiers.
NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class BookingRequest(BaseModel):
    patient_id: NonEmptyString
    clinic_id: NonEmptyString
    provider_id: NonEmptyString
    start_at: datetime


@app.post("/appointments", status_code=201)
def create_appointment(request: BookingRequest):
    start = request.start_at

    if start.tzinfo is None or start.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail="Appointment time must include a timezone.",
        )

    end = start + timedelta(minutes=30)
    appointment_id = uuid4()

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO appointments (
                        id, patient_id, clinic_id, provider_id,
                        start_at, ends_at, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, patient_id, clinic_id, provider_id,
                              start_at, ends_at, status
                    """,
                    (
                        appointment_id,
                        request.patient_id,
                        request.clinic_id,
                        request.provider_id,
                        start,
                        end,
                        "booked",
                    ),
                )
                row = cur.fetchone()

    except ExclusionViolation:
        raise HTTPException(
            status_code=409,
            detail="Provider already has an overlapping appointment.",
        )

    return {
        "id": str(row[0]),
        "patient_id": row[1],
        "clinic_id": row[2],
        "provider_id": row[3],
        "start_at": row[4],
        "ends_at": row[5],
        "status": row[6],
    }


@app.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(appointment_id: UUID):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE appointments
                SET status = 'cancelled'
                WHERE id = %s
                  AND status = 'booked'
                RETURNING id, patient_id, clinic_id,
                          provider_id, start_at, ends_at, status
                """,
                (appointment_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Booked appointment not found.",
        )

    return {
        "id": str(row[0]),
        "patient_id": row[1],
        "clinic_id": row[2],
        "provider_id": row[3],
        "start_at": row[4],
        "ends_at": row[5],
        "status": row[6],
    }


@app.get("/appointments")
def list_appointments():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, patient_id, clinic_id, provider_id,
                       start_at, ends_at, status
                FROM appointments
                ORDER BY start_at ASC
                """
            )
            rows = cur.fetchall()

    return [
        {
            "id": str(row[0]),
            "patient_id": row[1],
            "clinic_id": row[2],
            "provider_id": row[3],
            "start_at": row[4],
            "ends_at": row[5],
            "status": row[6],
        }
        for row in rows
    ]


@app.get("/appointments/{appointment_id}")
def get_appointment(appointment_id: UUID):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, patient_id, clinic_id, provider_id,
                       start_at, ends_at, status
                FROM appointments
                WHERE id = %s
                """,
                (appointment_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found.",
        )

    return {
        "id": str(row[0]),
        "patient_id": row[1],
        "clinic_id": row[2],
        "provider_id": row[3],
        "start_at": row[4],
        "ends_at": row[5],
        "status": row[6],
    }


@app.put("/appointments/{appointment_id}")
def reschedule_appointment(
    appointment_id: UUID,
    new_start_at: datetime,
):
    if new_start_at.tzinfo is None or new_start_at.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail="Appointment time must include a timezone.",
        )

    new_end_at = new_start_at + timedelta(minutes=30)

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE appointments
                    SET start_at = %s,
                        ends_at = %s
                    WHERE id = %s
                      AND status = 'booked'
                    RETURNING id, patient_id, clinic_id, provider_id,
                              start_at, ends_at, status
                    """,
                    (new_start_at, new_end_at, appointment_id),
                )
                row = cur.fetchone()

    except ExclusionViolation:
        raise HTTPException(
            status_code=409,
            detail="Provider already has an overlapping appointment.",
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Booked appointment not found.",
        )

    return {
        "id": str(row[0]),
        "patient_id": row[1],
        "clinic_id": row[2],
        "provider_id": row[3],
        "start_at": row[4],
        "ends_at": row[5],
        "status": row[6],
    }