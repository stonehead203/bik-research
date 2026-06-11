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
