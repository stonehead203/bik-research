import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

CACHE_KEY = "hyperliquid:asset_meta"
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_JSON = BASE_DIR / "hyperliquid_asset_meta.json"


def normalize_supabase_url(value):
    return str(value or "").strip().rstrip("/").removesuffix("/rest/v1")


def load_payload(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), dict):
        raise ValueError("asset meta JSON must be an object with an items object")
    return payload


def upload_payload(payload):
    supabase_url = normalize_supabase_url(os.environ.get("SUPABASE_URL"))
    service_key = str(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    table = str(os.environ.get("SUPABASE_APP_CACHE_TABLE") or "app_cache").strip()
    if not supabase_url or not service_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    payload = dict(payload)
    payload["uploadedAt"] = datetime.now(timezone.utc).isoformat()

    response = requests.post(
        f"{supabase_url}/rest/v1/{table}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        params={"on_conflict": "key"},
        json={
            "key": CACHE_KEY,
            "payload": payload,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase upload failed: {response.status_code} {response.text[:500]}")
    return len(payload.get("items", {}))


def main():
    json_path = Path(os.environ.get("HYPERLIQUID_ASSET_META_JSON") or DEFAULT_JSON)
    payload = load_payload(json_path)
    count = upload_payload(payload)
    print(json.dumps({"ok": True, "cacheKey": CACHE_KEY, "items": count, "json": str(json_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
