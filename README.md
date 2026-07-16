# Hospital Scheduling Demo API

A mock backend for your Al Salam Hospital voice agent demo. It fakes a
doctor-availability / appointment-booking system so your DataQueue
agent has something real to call — check availability, book, cancel,
look up appointments. Swap it for the real hospital system later; the
endpoints won't need to change.

## 1. Run it locally first (2 min, sanity check)

```
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://127.0.0.1:8000/docs — that's an interactive test page for
every endpoint. Try `/doctors` and `/availability` there before going
further.

## 2. Put it online (free, ~5 min)

DataQueue needs a public HTTPS URL to call — your laptop isn't
reachable from the internet. Easiest free option:

**Render.com (recommended, free tier, no credit card):**
1. Push this folder to a GitHub repo (or use Render's "public git repo" option with any repo you own).
2. render.com → New → Web Service → connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Deploy. You'll get a URL like `https://your-app.onrender.com`.

**Or Replit (also free, if you prefer — same as your travel agent bot):**
1. Create a new Python Repl, upload these files.
2. Add a `.replit` run command: `uvicorn main:app --host 0.0.0.0 --port 8000`
3. Click Run, then "Open in new tab" to get your public URL.

Either way — test it's live by visiting `https://your-url/doctors` in
a browser. You should see the 3 mock doctors as JSON.

## 3. Connect it to your DataQueue agent

DataQueue's agent builder is called **Pathway** (Agent → Configuration
→ Pathway). Inside a pathway you add a **Webhook Node** — that's the
node that calls an external API and hands the response back to the
agent so it can speak it.

For this demo you'll add up to 4 webhook nodes, one per action:

| Purpose | Method | URL | Body / params |
|---|---|---|---|
| List doctors | GET | `https://your-url/doctors` | none |
| Check availability | GET | `https://your-url/availability?doctor_id={doctor_id}&date={date}` | pass extracted variables |
| Book appointment | POST | `https://your-url/book` | `{"doctor_id","date","time","patient_name","patient_phone"}` |
| Cancel appointment | POST | `https://your-url/cancel` | `{"appointment_id"}` |

Steps in the Pathway editor:
1. Open your agent → **Configuration → Pathway**.
2. Add a **Webhook Node** after the point where the agent has asked
   the caller which doctor/specialty and date they want.
3. Set the method (GET/POST) and URL from the table above.
4. Map the variables the agent already extracted from the
   conversation (doctor name → doctor_id, date, patient name, phone)
   into the request — DataQueue lets you insert extracted variables
   into the URL/body.
5. The webhook's JSON response becomes available to the agent as a
   variable — reference it in the next node's prompt so the agent
   reads back the real slots / confirmation / error to the caller.
6. Repeat for availability check, booking, and cancel.
7. Test with **Web Call** (no phone number needed) before wiring up a
   real number.

## 4. Things to say out loud when demoing

- "Doctor Ahmed Mansoor, cardiology, is he free Thursday?"
- "Book me the 10am slot with him."
- "Actually cancel that appointment."

Each of those should trigger a different webhook node and come back
with a real (mock) answer — that's the proof the agent can reliably
read/write data, not just chat.

## Notes

- Data is stored in `appointments.json` — resets to `[]` any time you
  redeploy on most free hosts (fine for a demo; move to a real
  database before production).
- To lock the API down, set an environment variable `API_KEY` on your
  host — every request will then need header `x-api-key: <value>`.
  Leave it unset while demoing so DataQueue can call it freely.
- Full endpoint reference is auto-generated at `/docs` once the app
  is running.
