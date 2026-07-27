import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
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
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def normalize_symbol(value):
    symbol = re.sub(r"\s+", "", str(value or "").upper())
    return symbol if re.fullmatch(r"[A-Z0-9]{6}", symbol) else ""


def load_symbols(symbols="", limit=0):
    if symbols:
        values = [normalize_symbol(item) for item in re.split(r"[\s,]+", symbols)]
        return [{"symbol": item, "name": item, "market": ""} for item in values if item]

    session = requests.Session()
    rows = toss_collector.load_kr_universe(session)
    cleaned = []
    seen = set()
    for row in rows:
        symbol = normalize_symbol(row.get("symbol"))
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        cleaned.append({
            "symbol": symbol,
            "name": str(row.get("name") or symbol).strip(),
            "market": str(row.get("market") or "").strip(),
        })
    if limit > 0:
        cleaned = cleaned[:limit]
    return cleaned


def is_valid_png(path):
    try:
        with open(path, "rb") as file:
            header = file.read(24)
        return (
            len(header) >= 24
            and header.startswith(PNG_SIGNATURE)
            and int.from_bytes(header[16:20], "big") > 0
            and int.from_bytes(header[20:24], "big") > 0
        )
    except OSError:
        return False


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_icon(row, output_dir, force=False, timeout=20):
    symbol = normalize_symbol(row.get("symbol"))
    if not symbol:
        return {"symbol": row.get("symbol"), "ok": False, "error": "invalid-symbol"}

    path = os.path.join(output_dir, f"{symbol}.png")
    existed = is_valid_png(path)
    if existed and not force:
        return {"symbol": symbol, "ok": True, "skipped": True, "path": path}

    url = TOSS_ICON_URL.format(symbol=symbol)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code == 404:
            return {"symbol": symbol, "ok": False, "status": 404, "url": url, "error": "not-found"}
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if not response.content.startswith(PNG_SIGNATURE) or "image" not in content_type:
            return {
                "symbol": symbol,
                "ok": False,
                "status": response.status_code,
                "url": url,
                "error": f"unexpected-content:{content_type}",
            }

        temp_path = f"{path}.tmp"
        with open(temp_path, "wb") as file:
            file.write(response.content)
        if not is_valid_png(temp_path):
            os.remove(temp_path)
            return {"symbol": symbol, "ok": False, "url": url, "error": "invalid-png"}
        if existed and file_digest(path) == file_digest(temp_path):
            os.remove(temp_path)
            return {
                "symbol": symbol,
                "name": row.get("name") or symbol,
                "market": row.get("market") or "",
                "ok": True,
                "unchanged": True,
                "url": url,
                "path": path,
            }
        os.replace(temp_path, path)
        return {
            "symbol": symbol,
            "name": row.get("name") or symbol,
            "market": row.get("market") or "",
            "ok": True,
            "updated": existed,
            "downloaded": not existed,
            "bytes": len(response.content),
            "url": url,
            "path": path,
        }
    except Exception as exc:
        return {"symbol": symbol, "ok": False, "url": url, "error": str(exc)[:240]}


def list_local_symbols(output_dir):
    symbols = set()
    if not os.path.isdir(output_dir):
        return symbols
    for name in os.listdir(output_dir):
        match = re.fullmatch(r"([A-Z0-9]{6})\.PNG", str(name).upper())
        if match and is_valid_png(os.path.join(output_dir, name)):
            symbols.add(match.group(1))
    return symbols


def write_manifest(output_dir, mode, rows, results, started_at):
    universe_symbols = {normalize_symbol(row.get("symbol")) for row in rows}
    universe_symbols.discard("")
    local_symbols = list_local_symbols(output_dir)
    manifest = {
        "source": "Toss Securities static stock icon URL pattern",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "startedAt": started_at,
        "mode": mode,
        "universe": len(universe_symbols),
        "iconsAvailable": len(local_symbols & universe_symbols),
        "missing": len(universe_symbols - local_symbols),
        "orphaned": len(local_symbols - universe_symbols),
        "attempted": len(results),
        "downloaded": sum(1 for item in results if item.get("downloaded")),
        "updated": sum(1 for item in results if item.get("updated")),
        "unchanged": sum(1 for item in results if item.get("unchanged")),
        "skipped": sum(1 for item in results if item.get("skipped")),
        "total": len(results),
        "ok": sum(1 for item in results if item.get("ok")),
        "failed": sum(1 for item in results if not item.get("ok")),
        "items": [
            item
            for item in results
            if not item.get("ok") or item.get("downloaded") or item.get("updated")
        ],
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    temp_path = f"{manifest_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, manifest_path)
    return manifest


def sync_domestic_icons(mode="missing", output_dir=DEFAULT_OUTPUT_DIR, symbols="", limit=0, workers=8, delay=0.02):
    mode = str(mode or "missing").strip().lower()
    if mode not in {"missing", "full"}:
        raise ValueError("mode must be missing or full")

    started_at = datetime.now(timezone.utc).isoformat()
    os.makedirs(output_dir, exist_ok=True)
    rows = load_symbols(symbols=symbols, limit=limit)
    if not rows:
        raise RuntimeError("No symbols to download.")

    target_rows = rows
    if mode == "missing":
        target_rows = [
            row
            for row in rows
            if not is_valid_png(os.path.join(output_dir, f"{normalize_symbol(row.get('symbol'))}.png"))
        ]

    results = []
    worker_count = max(1, min(int(workers or 1), 24))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = []
        for row in target_rows:
            futures.append(executor.submit(download_icon, row, output_dir, mode == "full"))
            if delay > 0:
                time.sleep(delay)
        for index, future in enumerate(as_completed(futures), 1):
            item = future.result()
            results.append(item)
            status = (
                "skip"
                if item.get("skipped")
                else "same"
                if item.get("unchanged")
                else "ok"
                if item.get("ok")
                else "fail"
            )
            print(
                f"[{index}/{len(futures)}] {status} {item.get('symbol')} {item.get('error', '')}",
                flush=True,
            )

    results.sort(key=lambda item: str(item.get("symbol") or ""))
    return write_manifest(output_dir, mode, rows, results, started_at)


def main():
    parser = argparse.ArgumentParser(description="Download Korean stock icons from Toss static icon URLs.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--symbols", default="", help="Comma/space separated symbols. Example: 005930,000660")
    parser.add_argument("--limit", type=int, default=0, help="Limit KRX universe rows for testing. 0 means all.")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--delay", type=float, default=0.02, help="Small delay between scheduling requests.")
    parser.add_argument("--mode", choices=("missing", "full"), default="missing")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    mode = "full" if args.force else args.mode
    manifest = sync_domestic_icons(
        mode=mode,
        output_dir=args.output_dir,
        symbols=args.symbols,
        limit=args.limit,
        workers=args.workers,
        delay=args.delay,
    )
    print(
        f"Done. mode={mode} attempted={manifest['attempted']} "
        f"downloaded={manifest['downloaded']} updated={manifest['updated']} "
        f"missing={manifest['missing']} failed={manifest['failed']} output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
