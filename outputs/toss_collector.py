import argparse
from datetime import datetime, timezone
import json
import os
import time
from urllib.parse import urljoin

import requests


DEFAULT_INGEST_URL = "https://www.bikresearch.com/api/ingest/toss-cache"


def load_json_env(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} must be valid JSON: {exc}") from exc


def build_headers(extra_headers=None):
    headers = {
        "Accept": "application/json",
        "User-Agent": "bik-research-toss-collector/1.0",
    }
    token = os.environ.get("TOSS_BEARER_TOKEN", "").strip()
    api_key = os.environ.get("TOSS_API_KEY", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if api_key:
        headers["X-API-Key"] = api_key
    headers.update(load_json_env("TOSS_HEADERS_JSON", {}))
    if extra_headers:
        headers.update(extra_headers)
    return headers


def request_toss_item(session, base_url, spec):
    if not isinstance(spec, dict):
        raise RuntimeError("Each request spec must be a JSON object.")

    name = str(spec.get("name") or spec.get("path") or "unnamed").strip()
    method = str(spec.get("method", "GET")).upper()
    path = str(spec.get("path", "")).strip()
    url = spec.get("url") or urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    timeout = int(spec.get("timeout", 20))

    response = session.request(
        method,
        url,
        params=spec.get("params"),
        json=spec.get("json"),
        data=spec.get("data"),
        headers=build_headers(spec.get("headers")),
        timeout=timeout,
    )
    response.raise_for_status()
    try:
        body = response.json()
    except ValueError:
        body = response.text

    return name, {
        "ok": True,
        "statusCode": response.status_code,
        "url": url,
        "data": body,
    }


def build_payload(request_specs):
    base_url = os.environ.get("TOSS_BASE_URL", "").strip()
    if not base_url and any(not spec.get("url") for spec in request_specs if isinstance(spec, dict)):
        raise RuntimeError("TOSS_BASE_URL is required when a request spec uses path instead of url.")

    items = {}
    errors = []
    with requests.Session() as session:
        for spec in request_specs:
            try:
                name, item = request_toss_item(session, base_url, spec)
                items[name] = item
                print(f"[ok] {name}")
            except Exception as exc:
                name = spec.get("name") if isinstance(spec, dict) else "unnamed"
                errors.append({"name": name or "unnamed", "error": str(exc)})
                print(f"[skip] {name or 'unnamed'}: {exc}")

    return {
        "ok": not errors,
        "source": "toss-openapi",
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": items,
        "errors": errors,
    }


def upload_payload(payload, ingest_url, ingest_secret):
    if not ingest_url:
        raise RuntimeError("RENDER_INGEST_URL is required.")
    if not ingest_secret:
        raise RuntimeError("INGEST_SECRET is required.")
    response = requests.post(
        ingest_url,
        json=payload,
        headers={"Authorization": f"Bearer {ingest_secret}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def run_once(request_specs, ingest_url, ingest_secret, dry_run=False):
    payload = build_payload(request_specs)
    if dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return payload
    result = upload_payload(payload, ingest_url, ingest_secret)
    print(f"[uploaded] {result}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Collect Toss OpenAPI data on OCI and upload it to the Render app cache.")
    parser.add_argument("--requests-json", default=os.environ.get("TOSS_REQUESTS_JSON", "[]"))
    parser.add_argument("--url", default=os.environ.get("RENDER_INGEST_URL", DEFAULT_INGEST_URL))
    parser.add_argument("--secret", default=os.environ.get("INGEST_SECRET", ""))
    parser.add_argument("--interval", type=int, default=int(os.environ.get("COLLECT_INTERVAL_SECONDS", "0")))
    parser.add_argument("--dry-run", action="store_true", default=os.environ.get("DRY_RUN", "").lower() == "true")
    args = parser.parse_args()

    try:
        request_specs = json.loads(args.requests_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"--requests-json must be valid JSON: {exc}") from exc
    if not isinstance(request_specs, list) or not request_specs:
        raise RuntimeError("TOSS_REQUESTS_JSON must be a non-empty JSON array.")

    if args.interval <= 0:
        run_once(request_specs, args.url, args.secret, args.dry_run)
        return

    while True:
        started_at = time.time()
        try:
            run_once(request_specs, args.url, args.secret, args.dry_run)
        except Exception as exc:
            print(f"[error] collect/upload failed: {exc}")
        elapsed = time.time() - started_at
        time.sleep(max(1, args.interval - elapsed))


if __name__ == "__main__":
    main()
