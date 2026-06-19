import argparse
from datetime import datetime, timezone
import json
import os
import time
from urllib.parse import urljoin

import requests


DEFAULT_INGEST_URL = "https://www.bikresearch.com/api/ingest/toss-cache"
DEFAULT_TOSS_BASE_URL = "https://openapi.tossinvest.com"
TOKEN_REFRESH_MARGIN_SECONDS = 60
_TOKEN_CACHE = {"access_token": "", "expires_at": 0.0}


def load_json_env(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} must be valid JSON: {exc}") from exc


def first_env(*names):
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def issue_toss_access_token(session, base_url):
    client_id = first_env("TOSSINVEST_API_KEY", "TOSS_CLIENT_ID")
    client_secret = first_env("TOSSINVEST_SECRET_KEY", "TOSS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("TOSSINVEST_API_KEY and TOSSINVEST_SECRET_KEY are required for OAuth token issuance.")

    token_url = urljoin(base_url.rstrip("/") + "/", "oauth2/token")
    response = session.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "bik-research-toss-collector/1.0",
        },
        timeout=20,
    )
    response.raise_for_status()
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("Toss OAuth token response was not JSON.") from exc

    access_token = str(body.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError(f"Toss OAuth token response did not include access_token: {body}")

    expires_in = int(body.get("expires_in") or 3600)
    _TOKEN_CACHE["access_token"] = access_token
    _TOKEN_CACHE["expires_at"] = time.time() + max(60, expires_in)
    return access_token


def get_toss_access_token(session, base_url):
    manual_token = first_env("TOSS_BEARER_TOKEN", "TOSSINVEST_BEARER_TOKEN")
    if manual_token:
        return manual_token

    cached_token = _TOKEN_CACHE.get("access_token", "")
    expires_at = float(_TOKEN_CACHE.get("expires_at") or 0)
    if cached_token and time.time() < expires_at - TOKEN_REFRESH_MARGIN_SECONDS:
        return cached_token

    return issue_toss_access_token(session, base_url)


def build_headers(session, base_url, extra_headers=None):
    headers = {
        "Accept": "application/json",
        "User-Agent": "bik-research-toss-collector/1.0",
        "Authorization": f"Bearer {get_toss_access_token(session, base_url)}",
    }
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
        headers=build_headers(session, base_url, spec.get("headers")),
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
    base_url = first_env("TOSS_BASE_URL", "TOSSINVEST_BASE_URL") or DEFAULT_TOSS_BASE_URL
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
