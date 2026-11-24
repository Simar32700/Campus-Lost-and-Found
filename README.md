# Campus Lost & Found

A local FastAPI prototype for reporting lost and found items, suggesting likely pairs, reviewing matches, and coordinating returns in a private chat. The frontend is plain HTML, CSS, and JavaScript; the database is SQLite. Matching uses TF-IDF text features and a small local classifier. No external API key is needed.

## Run locally

Use Python 3.10 or newer. In PowerShell, from this repository directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Open <http://127.0.0.1:8000>. The API documentation is at <http://127.0.0.1:8000/docs>.

On first startup, the app creates `campus_lost_found.db`, seeds sample reports and users, and places likely matches in the administrator review queue. It skips seeding when the database already contains users. Uploaded files go into `uploads/`. Both paths are ignored by Git.

For a separate fresh database, set `CAMPUS_DB_PATH` before starting the server:

```powershell
$env:CAMPUS_DB_PATH = "$PWD\fresh_demo.db"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

## Demo accounts

The page has one-click sign-in for these seeded accounts:

| Role | Email | Password |
| --- | --- | --- |
| Administrator | `admin@campus.edu` | `Admin@123` |
| Lost item reporter | `alex.chen@campus.edu` | `Student@123` |
| Found item reporter | `priya.patel@campus.edu` | `Student@123` |
| Lost item reporter | `marcus.johnson@campus.edu` | `Student@123` |

Use the administrator account to review pending matches. Approval changes both reports to `MATCHED` and opens a chat between their reporters. Both reporters must confirm a handover before the reports become `CLOSED`. Found reports are hidden from the administrator's lost item feed and from unrelated users.

## Verify

The end-to-end test uses a temporary database and does not change your local demo data:

```powershell
.\.venv\Scripts\python.exe -B test_e2e.py
.\.venv\Scripts\python.exe -B test_complaints.py
```

## Host a public demo on Render

`render.yaml` defines a free Python web service, a health check, and a generated JWT secret. Connect this repository to Render and create a Blueprint from `render.yaml`. Render will build the service and assign an `onrender.com` URL. The service uses the same sample accounts and one-click demo controls as the local app. Do not submit real personal data to this public demo.

Render's free web service filesystem is temporary: SQLite data and uploaded files disappear when the service restarts, redeploys, or spins down. For a durable deployment, use a persistent disk with a paid service or migrate the database and uploads to durable storage. The code accepts `CAMPUS_DB_PATH` and `CAMPUS_UPLOAD_DIR` for paths on an attached disk. Before hosting real users, remove the demo sign-in controls and sample credentials and add actual college email verification.

## Prototype limits

The registration form checks that an address has an academic domain pattern; it does not verify ownership of the mailbox or provide university single sign-on. New registrations always get the regular user role. The seeded passwords, one-click sign-in controls, and fallback JWT secret are for demonstrations. Set `JWT_SECRET_KEY` to a private random value and replace demo account provisioning before exposing this app to real users. SQLite and uploaded files are stored on the local machine. Chat messages are fetched by polling, not a live socket connection.
