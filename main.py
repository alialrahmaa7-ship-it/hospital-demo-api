"""
Hospital Scheduling Demo API
-----------------------------
A small mock backend that simulates a hospital's doctor-availability
and appointment-booking system. Built so a DataQueue VoiceHub agent
(or any voice/chat agent) can call it through a Webhook Node to:

  - list doctors
  - check available slots for a doctor on a given date
  - book an appointment
  - cancel an appointment
  - look up an appointment

This is a DEMO. Data is stored in local JSON files, not a real database.
Swap the storage functions for a real DB/CRM later without touching
the endpoint logic.
"""

import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCTORS_FILE = os.path.join(BASE_DIR, "doctors.json")
APPOINTMENTS_FILE = os.path.join(BASE_DIR, "appointments.json")

# Optional shared-secret protection. Set API_KEY as an environment
# variable on your host to require it; leave unset to keep it open
# for a quick demo.
API_KEY = os.environ.get("API_KEY")

app = FastAPI(title="Hospital Scheduling Demo API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- storage helpers ----------

def load_doctors() -> List[dict]:
    with open(DOCTORS_FILE, "r") as f:
        return json.load(f)


def load_appointments() -> List[dict]:
    with open(APPOINTMENTS_FILE, "r") as f:
        return json.load(f)


def save_appointments(appointments: List[dict]) -> None:
    with open(APPOINTMENTS_FILE, "w") as f:
        json.dump(appointments, f, indent=2)


def check_key(x_api_key: Optional[str]):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------- request models ----------

class BookRequest(BaseModel):
    doctor_id: str
    date: str          # YYYY-MM-DD
    time: str           # HH:MM (24h)
    patient_name: str
    patient_phone: str


class CancelRequest(BaseModel):
    appointment_id: str


# ---------- core logic ----------

def get_doctor(doctor_id: str) -> dict:
    for d in load_doctors():
        if d["doctor_id"].lower() == doctor_id.lower():
            return d
    raise HTTPException(status_code=404, detail=f"No doctor found with id {doctor_id}")


def generate_day_slots(doctor: dict, date_str: str) -> List[str]:
    """All possible slot start times for a doctor on a given date, ignoring bookings."""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be in YYYY-MM-DD format")

    weekday_name = date_obj.strftime("%A")
    if weekday_name not in doctor["working_days"]:
        return []

    start = datetime.strptime(doctor["working_hours"]["start"], "%H:%M")
    end = datetime.strptime(doctor["working_hours"]["end"], "%H:%M")
    slot_minutes = doctor["slot_minutes"]

    slots = []
    cursor = start
    while cursor < end:
        slots.append(cursor.strftime("%H:%M"))
        cursor += timedelta(minutes=slot_minutes)
    return slots


def booked_times(doctor_id: str, date_str: str) -> List[str]:
    return [
        a["time"] for a in load_appointments()
        if a["doctor_id"].lower() == doctor_id.lower()
        and a["date"] == date_str
        and a["status"] == "booked"
    ]


# ---------- endpoints ----------

@app.get("/")
def health():
    return {"status": "ok", "service": "hospital-scheduling-demo-api"}


@app.get("/doctors")
def list_doctors(specialty: Optional[str] = None, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    doctors = load_doctors()
    if specialty:
        doctors = [d for d in doctors if d["specialty"].lower() == specialty.lower()]
    return {"doctors": doctors}


@app.get("/availability")
def availability(doctor_id: str, date: str, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    doctor = get_doctor(doctor_id)
    all_slots = generate_day_slots(doctor, date)
    taken = set(booked_times(doctor_id, date))
    free = [s for s in all_slots if s not in taken]
    return {
        "doctor_id": doctor["doctor_id"],
        "doctor_name": doctor["name"],
        "date": date,
        "available_slots": free,
    }


@app.post("/book")
def book(req: BookRequest, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    doctor = get_doctor(req.doctor_id)
    all_slots = generate_day_slots(doctor, req.date)

    if req.time not in all_slots:
        raise HTTPException(
            status_code=400,
            detail=f"{req.time} is not a valid slot for {doctor['name']} on {req.date}",
        )

    if req.time in booked_times(req.doctor_id, req.date):
        raise HTTPException(
            status_code=409,
            detail=f"{req.time} on {req.date} is already booked for {doctor['name']}",
        )

    appointments = load_appointments()
    appointment_id = uuid.uuid4().hex[:8].upper()
    appointments.append({
        "appointment_id": appointment_id,
        "doctor_id": doctor["doctor_id"],
        "doctor_name": doctor["name"],
        "date": req.date,
        "time": req.time,
        "patient_name": req.patient_name,
        "patient_phone": req.patient_phone,
        "status": "booked",
        "created_at": datetime.utcnow().isoformat(),
    })
    save_appointments(appointments)

    return {
        "confirmation": "booked",
        "appointment_id": appointment_id,
        "doctor_name": doctor["name"],
        "date": req.date,
        "time": req.time,
    }


@app.post("/cancel")
def cancel(req: CancelRequest, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    appointments = load_appointments()
    for a in appointments:
        if a["appointment_id"] == req.appointment_id:
            if a["status"] == "cancelled":
                return {"confirmation": "already_cancelled", "appointment_id": req.appointment_id}
            a["status"] = "cancelled"
            save_appointments(appointments)
            return {"confirmation": "cancelled", "appointment_id": req.appointment_id}
    raise HTTPException(status_code=404, detail=f"No appointment found with id {req.appointment_id}")


@app.get("/appointment/{appointment_id}")
def get_appointment(appointment_id: str, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    for a in load_appointments():
        if a["appointment_id"] == appointment_id:
            return a
    raise HTTPException(status_code=404, detail=f"No appointment found with id {appointment_id}")


@app.get("/appointments")
def list_appointments(patient_phone: Optional[str] = None, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    appointments = load_appointments()
    if patient_phone:
        appointments = [a for a in appointments if a["patient_phone"] == patient_phone]
    return {"appointments": appointments}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
