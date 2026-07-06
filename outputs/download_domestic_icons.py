import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
import re
import time

import requests

import toss_collector


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "domestic_icons")
TOSS_ICON_URL = "https://static.toss.im/png-icons/securities/icn-sec-fill-{symbol}.png"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def normalize_symbol(value):
    symbol = re.sub(r"\s+", "", str(value or "").upper())
    return symbol if re.fullmatch(r"[A-Z0-9]{6}", symbol) else ""


def load_symbols(args):
    if args.symbols:
        symbols = [normalize_symbol(item) for item in re.split(r"[\s,]+", args.symbols)]
        return [{"symbol": item, "name": item, "market": ""} for item in symbols if item]

    session = requests.Session()
    rows = toss_collector.load_kr_universe(session)
    cleaned = []
    seen = set()
    for row in rows:
        symbol = normalize_symbol(row.get("symbol"))
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        cleaned.append(row)
    if args.limit > 0:
        cleaned = cleaned[: args.limit]
    return cleaned


def download_icon(row, output_dir, force=False, timeout=20):
    symbol = normalize_symbol(row.get("symbol"))
    if not symbol:
        return {"symbol": row.get("symbol"), "ok": False, "error": "invalid-symbol"}

    path = os.path.join(output_dir, f"{symbol}.png")
    if os.path.exists(path) and not force and os.path.getsize(path) > 0:
        return {"symbol": symbol, "ok": True, "skipped": True, "path": path}

    url = TOSS_ICON_URL.format(symbol=symbol)
    headers = {"User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"}
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code == 404:
            return {"symbol": symbol, "ok": False, "status": 404, "url": url, "error": "not-found"}
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if not response.content.startswith(b"\x89PNG") or "image" not in content_type:
            return {"symbol": symbol, "ok": False, "status": response.status_code, "url": url, "error": f"unexpected-content:{content_type}"}

        temp_path = f"{path}.tmp"
        with open(temp_path, "wb") as file:
            file.write(response.content)
        os.replace(temp_path, path)
        return {
            "symbol": symbol,
            "name": row.get("name") or symbol,
            "market": row.get("market") or "",
            "ok": True,
            "bytes": len(response.content),
            "url": url,
            "path": path,
        }
    except Exception as exc:
        return {"symbol": symbol, "ok": False, "url": url, "error": str(exc)[:240]}


def write_manifest(output_dir, results):
    manifest = {
        "source": "Toss Securities static stock icon URL pattern",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "ok": sum(1 for item in results if item.get("ok")),
        "failed": sum(1 for item in results if not item.get("ok")),
        "items": results,
    }
    with open(os.path.join(output_dir, "manifest.json"), "w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Download Korean stock icons from Toss static icon URLs.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--symbols", default="", help="Comma/space separated symbols. Example: 005930,000660")
    parser.add_argument("--limit", type=int, default=0, help="Limit KRX universe rows for testing. 0 means all.")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--delay", type=float, default=0.02, help="Small delay between scheduling requests.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    rows = load_symbols(args)
    if not rows:
        raise SystemExit("No symbols to download.")

    results = []
    workers = max(1, min(args.workers, 24))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for row in rows:
            futures.append(executor.submit(download_icon, row, args.output_dir, args.force))
            if args.delay > 0:
                time.sleep(args.delay)
        for index, future in enumerate(as_completed(futures), 1):
            item = future.result()
            results.append(item)
            status = "skip" if item.get("skipped") else "ok" if item.get("ok") else "fail"
            print(f"[{index}/{len(futures)}] {status} {item.get('symbol')} {item.get('error', '')}")

    results.sort(key=lambda item: str(item.get("symbol") or ""))
    manifest = write_manifest(args.output_dir, results)
    print(f"Done. ok={manifest['ok']} failed={manifest['failed']} output={args.output_dir}")


if __name__ == "__main__":
    main()
