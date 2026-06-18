# OCI Toss Collector

This keeps the public web app on Render while running only the Toss OpenAPI collector from an OCI Always Free VM.

## Render environment

Add this environment variable to the Render web service:

```bash
INGEST_SECRET=<long-random-secret>
```

Optional, if you use a Render disk:

```bash
TOSS_CACHE_FILE=/var/data/toss_cache.json
```

The app exposes:

- `POST /api/ingest/toss-cache`: protected upload endpoint for the collector.
- `GET /api/toss-cache`: reads the latest uploaded Toss payload.
- `GET /api/market-data`: prefers the latest Toss cache for dashboard market cards and caches the combined response for 55 seconds by default.

## OCI VM setup

Install Python dependencies:

```bash
sudo apt update
sudo apt install -y python3 python3-venv git
git clone https://github.com/stonehead203/bik-research.git
cd bik-research/outputs
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Create `/etc/bik-toss-collector.env`:

```bash
RENDER_INGEST_URL=https://www.bikresearch.com/api/ingest/toss-cache
INGEST_SECRET=<same-secret-as-render>
TOSS_BASE_URL=https://<toss-openapi-host>
TOSS_BEARER_TOKEN=<optional-token>
TOSS_API_KEY=<optional-api-key>
TOSS_HEADERS_JSON={}
TOSS_REQUESTS_JSON=[
  {"name":"sp500","method":"GET","path":"/replace/with/sp500/endpoint"},
  {"name":"nasdaq","method":"GET","path":"/replace/with/nasdaq/endpoint"},
  {"name":"dow","method":"GET","path":"/replace/with/dow/endpoint"},
  {"name":"sp500_futures","method":"GET","path":"/replace/with/sp500-futures/endpoint"},
  {"name":"nasdaq100_futures","method":"GET","path":"/replace/with/nasdaq100-futures/endpoint"},
  {"name":"dow_futures","method":"GET","path":"/replace/with/dow-futures/endpoint"},
  {"name":"wti","method":"GET","path":"/replace/with/wti/endpoint"},
  {"name":"gold","method":"GET","path":"/replace/with/gold/endpoint"},
  {"name":"us10y","method":"GET","path":"/replace/with/us10y/endpoint"}
]
```

Test once:

```bash
set -a
. /etc/bik-toss-collector.env
set +a
python toss_collector.py --dry-run
python toss_collector.py
```

## systemd timer

Copy the service and timer files:

```bash
sudo cp oci/bik-toss-collector.service /etc/systemd/system/
sudo cp oci/bik-toss-collector.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bik-toss-collector.timer
sudo systemctl status bik-toss-collector.timer
```

View logs:

```bash
journalctl -u bik-toss-collector.service -n 100 --no-pager
```

## Notes

- Keep `www.bikresearch.com` pointed at Render.
- Keep the OCI VM public IP reserved if Toss requires IP allowlisting.
- The collector is endpoint-configurable because Toss request paths and auth headers should stay in VM environment variables, not GitHub.
- Dashboard index cards use spot cache item names `sp500`, `nasdaq`, and `dow` during regular US market hours, and futures cache item names `sp500_futures`, `nasdaq100_futures`, and `dow_futures` outside regular US market hours. Macro cards use `wti`, `gold`, and `us10y`. If an item is missing or cannot be normalized, the app falls back to Yahoo Finance for that card.
- The included systemd timer runs every 60 seconds. If Toss rate limits are tight, change `OnUnitActiveSec=60s` to `180s`.
