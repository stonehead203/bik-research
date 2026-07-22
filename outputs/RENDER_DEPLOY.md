# Render Deployment

## Files

- `company_analysis_app.py`: Flask app entry
- `company_analysis.html`: UI template
- `requirements.txt`: Python dependencies
- `runtime.txt`: Python version for Render
- `Procfile`: Render/Heroku-style process command
- `render.yaml`: Optional Render Blueprint config

## Render Settings

When creating a new Render Web Service:

- Root Directory: `outputs`
- Runtime: `Python`
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn company_analysis_app:app`
- Instance Type: `Free`

The Flask app already reads Render's `PORT` environment variable:

```python
port = int(os.environ.get("PORT", "5001"))
app.run(debug=True, port=port)
```

For production, Render will use Gunicorn and ignore the local `app.run(...)` block.

## Notes

- The app depends on Yahoo Finance data through `yfinance`, so responses can be slow or temporarily fail depending on Yahoo/network availability.
- Free Render instances may sleep when unused. The first request after sleep can take longer.
- Login uses Flask sessions. Set these Render environment variables before sharing accounts:
  - `SECRET_KEY`: a long random string
  - `APP_USERNAME`: login username
  - `APP_PASSWORD`: login password
  - `INGEST_SECRET`: shared secret for the OCI Toss collector upload endpoint
  - `MARKET_DATA_CACHE_SECONDS`: optional dashboard API cache TTL, defaults to `55`

## Persistent User Storage

Account signups are stored in `users.json`. For production, attach a Render Disk so this file survives deploys and restarts.

Recommended Render Disk settings:

- Mount Path: `/var/data`
- Size: 1 GB is enough for JSON-based user storage

Recommended environment variable:

- `USERS_FILE=/var/data/users.json`

If `/var/data` exists, the app automatically defaults to `/var/data/users.json`. Setting `USERS_FILE` explicitly is still recommended so the storage path is obvious in Render.

Do not upload `users.json` to GitHub. It contains user emails and password hashes.

## Domestic ETF Daily Collector (Free Render)

A Free Render web service can spin down when idle, so its in-process scheduler needs
incoming traffic during the collection window.

Recommended free setup with cron-job.org:

- URL: `https://bikresearch.com/api/domestic-etf-dashboard`
- Method: `GET`
- Time zone: `Asia/Seoul`
- Weekdays: Monday through Friday
- Hours: `18`, `19`, and `20`
- Minutes: `00`, `10`, `20`, `30`, `40`, and `50`
- Request timeout: at least 120 seconds

The first request wakes the Render service. Subsequent requests keep it active while
the app resumes 100-ETF batches from the Supabase checkpoint. The endpoint never
returns the Supabase credentials or KRX authentication key.

`collect_domestic_etf.py` remains available for local runs or a future paid Render
Cron Job, but it is not required for the Free Render setup.

Required web-service environment variables remain:

- `KRX_OPEN_API_AUTH_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

`KRX_ID` and `KRX_PW` are retained only for the legacy fallback path and are not
used by the normal Open API collection.

