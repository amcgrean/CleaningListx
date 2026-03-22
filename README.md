# CleaningListx

A one-page web app that recreates the printable cleaning schedule with login, week navigation, and persistent weekly history per user.

## Features
- Neon Auth bearer-token login (or local username/password when Neon Auth env vars are not set)
- Weekly tracker defaults to current week, with previous weeks retained
- Monthly and annual sections included in the same style
- Persistent storage for user accounts + task completion status
- Responsive layout designed to adapt to iPad widths
- **Family household accounts** — invite family members to share the same cleaning list and track who completed each task

## Family Households

Multiple users can be grouped into a household to share a cleaning list and see each other's progress.

**Creating a household:**
1. Log in and click the **Family** button in the toolbar
2. Enter a household name and click **Create**
3. An 8-character invite code is generated — copy and share it with family members

**Joining a household:**
1. Log in (register first if needed), click **Family**
2. Enter the invite code under "Join a household" and click **Join**

**Tracking who did what:**
Each task row shows a small colored circle for every household member. A faded circle means that person hasn't done the task yet; a full-color circle means they have. Hover to see the member's name.

The household owner can leave at any time — ownership transfers automatically to the next member. If the last member leaves, the household is deleted.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:3000.

By default local runs use SQLite (`cleaning.db`).

## Deploy to Vercel (with Neon Postgres)

1. Push this repo to GitHub.
2. Import the project in Vercel.
3. In Vercel project settings, add environment variables:
   - `DATABASE_URL` = your Neon connection string (postgres URL)
   - `SECRET_KEY` = a long random string for session signing
   - `NEON_AUTH_ISSUER` = issuer for Neon Auth JWTs
   - `NEON_AUTH_JWKS_URL` = Neon Auth JWKS endpoint
   - `NEON_AUTH_AUDIENCE` = expected audience claim (optional)
4. Deploy.

When Neon auth variables are set, the app expects a Neon JWT bearer token and auto-provisions a matching user record from `sub`. Without these variables, it falls back to built-in username/password auth.

The app auto-creates tables and seeds tasks on first request.
