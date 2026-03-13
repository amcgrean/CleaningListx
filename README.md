# CleaningListx

A one-page web app that recreates the printable cleaning schedule with login, week navigation, and persistent weekly history per user.

## Features
- Neon Auth bearer-token login (or local username/password when Neon Auth env vars are not set)
- Weekly tracker defaults to current week, with previous weeks retained
- Monthly and annual sections included in the same style
- Persistent storage for user accounts + task completion status
- Responsive layout designed to adapt to iPad widths

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
