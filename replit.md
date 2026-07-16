# Hospital Scheduling Demo API

A mock FastAPI backend for an Al Salam Hospital voice agent demo. Provides endpoints for doctor availability and appointment booking/cancellation — designed to be called by a DataQueue (or similar) voice agent via webhook nodes.

## How to run

The app starts automatically via the **Start application** workflow.

```
uvicorn main:app --host 0.0.0.0 --port 8000
```

- Interactive API docs: `/docs` (Swagger UI)
- Health check: `/`

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/doctors` | List all doctors (filter by `?specialty=`) |
| GET | `/availability` | Available slots (`?doctor_id=&date=YYYY-MM-DD`) |
| POST | `/book` | Book an appointment |
| POST | `/cancel` | Cancel an appointment |
| GET | `/appointment/{id}` | Look up a single appointment |
| GET | `/appointments` | List appointments (filter by `?patient_phone=`) |

## Configuration

- **Data storage**: `doctors.json` (read-only) and `appointments.json` (read/write, resets on redeploy)
- **API key**: Set the `API_KEY` environment secret to require `x-api-key` header on all requests. Leave unset for open access (default for demos).

## Stack

- Python 3.11
- FastAPI 0.115.0
- Uvicorn 0.30.6
- Pydantic 2.9.2

## User preferences

- Keep existing project structure and stack.
