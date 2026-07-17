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
from fastapi.responses import HTMLResponse
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
    reason: Optional[str] = None   # why they're visiting, if given


class RescheduleRequest(BaseModel):
    appointment_id: str
    new_date: str
    new_time: str


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
        and a["status"] in ("confirmed", "rescheduled")
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
        "reason": req.reason or "",
        "status": "confirmed",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "history": [f"Booked for {req.date} {req.time}"],
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
            a["updated_at"] = datetime.utcnow().isoformat()
            a.setdefault("history", []).append("Cancelled")
            save_appointments(appointments)
            return {"confirmation": "cancelled", "appointment_id": req.appointment_id}
    raise HTTPException(status_code=404, detail=f"No appointment found with id {req.appointment_id}")


@app.post("/reschedule")
def reschedule(req: RescheduleRequest, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    appointments = load_appointments()
    target = None
    for a in appointments:
        if a["appointment_id"] == req.appointment_id:
            target = a
            break
    if not target:
        raise HTTPException(status_code=404, detail=f"No appointment found with id {req.appointment_id}")
    if target["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot reschedule a cancelled appointment")

    doctor = get_doctor(target["doctor_id"])
    all_slots = generate_day_slots(doctor, req.new_date)
    if req.new_time not in all_slots:
        raise HTTPException(status_code=400, detail=f"{req.new_time} is not a valid slot on {req.new_date}")
    if req.new_time in booked_times(target["doctor_id"], req.new_date):
        raise HTTPException(status_code=409, detail=f"{req.new_time} on {req.new_date} is already booked")

    old_date, old_time = target["date"], target["time"]
    target["date"] = req.new_date
    target["time"] = req.new_time
    target["status"] = "rescheduled"
    target["updated_at"] = datetime.utcnow().isoformat()
    target.setdefault("history", []).append(f"Rescheduled from {old_date} {old_time} to {req.new_date} {req.new_time}")
    save_appointments(appointments)
    return {
        "confirmation": "rescheduled",
        "appointment_id": req.appointment_id,
        "date": req.new_date,
        "time": req.new_time,
    }


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


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Interactive CRM-style dashboard: live polling, search, filters, cancel/reschedule."""
    return DASHBOARD_HTML


DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Al Salam Hospital — Appointments CRM</title>
<meta charset="utf-8">
<style>
  :root { --navy:#0f1b3d; --navy-light:#1a2b5c; --gold:#c9a24b; --bg:#f4f5f7; --green:#16a34a; --red:#dc2626; --gray:#6b7280; }
  * { box-sizing:border-box; }
  body { font-family:-apple-system,'Segoe UI',Arial,sans-serif; background:var(--bg); margin:0; color:#1a1a2e; }
  header { background:var(--navy); color:white; padding:1.25rem 2rem; display:flex; justify-content:space-between; align-items:center; }
  header h1 { margin:0; font-size:1.3rem; font-weight:600; }
  header h1 span { color:var(--gold); }
  .live-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--green); margin-right:6px; animation:pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  .status-line { font-size:0.8rem; color:#c9c9d6; }
  .container { padding:1.5rem 2rem; }
  .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:1rem; margin-bottom:1.5rem; }
  .stat-card { background:white; border-radius:10px; padding:1rem 1.25rem; box-shadow:0 1px 3px rgba(0,0,0,0.06); border-left:4px solid var(--gold); }
  .stat-card .num { font-size:1.6rem; font-weight:700; color:var(--navy); }
  .stat-card .label { font-size:0.8rem; color:var(--gray); text-transform:uppercase; letter-spacing:0.03em; }
  .toolbar { display:flex; gap:0.75rem; margin-bottom:1rem; flex-wrap:wrap; align-items:center; }
  .toolbar input { padding:0.55rem 0.9rem; border:1px solid #ddd; border-radius:8px; font-size:0.9rem; min-width:220px; }
  .filter-btn { padding:0.5rem 1rem; border-radius:20px; border:1px solid #ddd; background:white; cursor:pointer; font-size:0.85rem; color:var(--gray); }
  .filter-btn.active { background:var(--navy); color:white; border-color:var(--navy); }
  table { width:100%; border-collapse:collapse; background:white; border-radius:10px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,0.08); }
  th { background:var(--navy-light); color:white; text-align:left; padding:0.7rem 1rem; font-size:0.78rem; text-transform:uppercase; letter-spacing:0.03em; }
  td { padding:0.7rem 1rem; border-bottom:1px solid #eee; font-size:0.88rem; vertical-align:top; }
  tr:hover td { background:#fafbfc; }
  .badge { padding:0.2rem 0.6rem; border-radius:12px; font-size:0.75rem; font-weight:600; text-transform:capitalize; }
  .badge.confirmed { background:#dcfce7; color:var(--green); }
  .badge.rescheduled { background:#fef3c7; color:#b45309; }
  .badge.pending { background:#e0e7ff; color:#4338ca; }
  .badge.cancelled { background:#fee2e2; color:var(--red); }
  .actions button { font-size:0.78rem; padding:0.3rem 0.6rem; border-radius:6px; border:1px solid #ddd; background:white; cursor:pointer; margin-right:0.3rem; }
  .actions button:hover { background:#f0f0f3; }
  .actions button.cancel-btn:hover { background:#fee2e2; border-color:var(--red); color:var(--red); }
  .empty { text-align:center; color:var(--gray); padding:3rem; }
  .reschedule-form { display:none; gap:0.4rem; margin-top:0.4rem; }
  .reschedule-form.open { display:flex; }
  .reschedule-form input { padding:0.3rem 0.5rem; font-size:0.78rem; border:1px solid #ddd; border-radius:5px; width:110px; }
  .reason-cell { color:var(--gray); font-style:italic; max-width:160px; }
</style>
</head>
<body>

<header>
  <h1>🏥 Al Salam Hospital <span>— Appointments CRM</span></h1>
  <div class="status-line"><span class="live-dot"></span>Live &middot; updated <span id="lastUpdated">--:--:--</span></div>
</header>

<div class="container">
  <div class="stats">
    <div class="stat-card"><div class="num" id="statTotal">0</div><div class="label">Total</div></div>
    <div class="stat-card"><div class="num" id="statConfirmed">0</div><div class="label">Confirmed</div></div>
    <div class="stat-card"><div class="num" id="statRescheduled">0</div><div class="label">Rescheduled</div></div>
    <div class="stat-card"><div class="num" id="statCancelled">0</div><div class="label">Cancelled</div></div>
    <div class="stat-card"><div class="num" id="statToday">0</div><div class="label">Today</div></div>
  </div>

  <div class="toolbar">
    <input id="searchBox" placeholder="Search patient, phone, doctor, or ID..." oninput="render()">
    <button class="filter-btn active" data-filter="all" onclick="setFilter('all')">All</button>
    <button class="filter-btn" data-filter="confirmed" onclick="setFilter('confirmed')">Confirmed</button>
    <button class="filter-btn" data-filter="pending" onclick="setFilter('pending')">Pending</button>
    <button class="filter-btn" data-filter="rescheduled" onclick="setFilter('rescheduled')">Rescheduled</button>
    <button class="filter-btn" data-filter="cancelled" onclick="setFilter('cancelled')">Cancelled</button>
  </div>

  <table>
    <thead>
      <tr>
        <th>ID</th><th>Patient</th><th>Phone</th><th>Doctor</th>
        <th>Date</th><th>Time</th><th>Reason</th><th>Status</th><th>Booked At</th><th>Actions</th>
      </tr>
    </thead>
    <tbody id="tableBody"></tbody>
  </table>
</div>

<script>
let allAppointments = [];
let currentFilter = 'all';

async function fetchData() {
  try {
    const res = await fetch('/appointments');
    const data = await res.json();
    allAppointments = data.appointments.sort((a,b) => (b.created_at||'').localeCompare(a.created_at||''));
    render();
    document.getElementById('lastUpdated').textContent = new Date().toLocaleTimeString();
  } catch (e) {
    console.error('Failed to fetch appointments', e);
  }
}

function setFilter(f) {
  currentFilter = f;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === f));
  render();
}

function render() {
  const search = document.getElementById('searchBox').value.toLowerCase();
  let rows = allAppointments.filter(a => {
    if (currentFilter !== 'all' && a.status !== currentFilter) return false;
    if (!search) return true;
    return (a.patient_name||'').toLowerCase().includes(search)
        || (a.patient_phone||'').toLowerCase().includes(search)
        || (a.doctor_name||'').toLowerCase().includes(search)
        || (a.appointment_id||'').toLowerCase().includes(search);
  });

  document.getElementById('statTotal').textContent = allAppointments.length;
  document.getElementById('statConfirmed').textContent = allAppointments.filter(a=>a.status==='confirmed').length;
  document.getElementById('statRescheduled').textContent = allAppointments.filter(a=>a.status==='rescheduled').length;
  document.getElementById('statCancelled').textContent = allAppointments.filter(a=>a.status==='cancelled').length;
  const today = new Date().toISOString().slice(0,10);
  document.getElementById('statToday').textContent = allAppointments.filter(a=>a.date===today).length;

  const tbody = document.getElementById('tableBody');
  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" class="empty">No appointments match</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map(a => `
    <tr>
      <td>${a.appointment_id}</td>
      <td>${a.patient_name}</td>
      <td>${a.patient_phone}</td>
      <td>${a.doctor_name}</td>
      <td>${a.date}</td>
      <td>${a.time}</td>
      <td class="reason-cell">${a.reason || '—'}</td>
      <td><span class="badge ${a.status}">${a.status}</span></td>
      <td>${(a.created_at||'').slice(0,19).replace('T',' ')}</td>
      <td class="actions">
        ${a.status !== 'cancelled' ? `
          <button onclick="toggleReschedule('${a.appointment_id}')">Reschedule</button>
          <button class="cancel-btn" onclick="cancelAppt('${a.appointment_id}')">Cancel</button>
          <div class="reschedule-form" id="resched-${a.appointment_id}">
            <input type="date" id="date-${a.appointment_id}" value="${a.date}">
            <input type="time" id="time-${a.appointment_id}" value="${a.time}">
            <button onclick="submitReschedule('${a.appointment_id}')">Save</button>
          </div>
        ` : '—'}
      </td>
    </tr>
  `).join('');
}

function toggleReschedule(id) {
  document.getElementById('resched-' + id).classList.toggle('open');
}

async function cancelAppt(id) {
  if (!confirm('Cancel appointment ' + id + '?')) return;
  await fetch('/cancel', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({appointment_id: id})
  });
  fetchData();
}

async function submitReschedule(id) {
  const newDate = document.getElementById('date-' + id).value;
  const newTime = document.getElementById('time-' + id).value;
  const res = await fetch('/reschedule', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({appointment_id: id, new_date: newDate, new_time: newTime})
  });
  if (!res.ok) {
    const err = await res.json();
    alert('Could not reschedule: ' + (err.detail || 'unknown error'));
    return;
  }
  fetchData();
}

fetchData();
setInterval(fetchData, 5000);
</script>

</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
