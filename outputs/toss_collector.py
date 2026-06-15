import argparse
from datetime import datetime
import os
import time

import requests

from company_analysis_app import (
    toss_calendar_card,
    toss_company_info,
    toss_exchange_card,
)


DEFAULT_SYMBOLS = ["NVDA", "AAPL", "MSFT", "TSLA", "005930", "000660"]


def build_payload(symbols):
    companies = {}
    for symbol in symbols:
        symbol = symbol.strip().upper()
        if not symbol:
            continue
        try:
            companies[symbol] = toss_company_info(symbol)
            print(f"[ok] company {symbol}")
        except Exception as exc:
            print(f"[skip] company {symbol}: {exc}")

    market = {}
    try:
        market["exchangeRate"] = toss_exchange_card()
        print("[ok] market exchangeRate")
    except Exception as exc:
        print(f"[skip] market exchangeRate: {exc}")
    for country in ("KR", "US"):
        try:
            market[country] = toss_calendar_card(country)
            print(f"[ok] market {country}")
        except Exception as exc:
            print(f"[skip] market {country}: {exc}")

    return {
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "companies": companies,
        "market": market,
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


def run_once(symbols, ingest_url, ingest_secret):
    payload = build_payload(symbols)
    result = upload_payload(payload, ingest_url, ingest_secret)
    print(f"[uploaded] {result}")


def main():
    parser = argparse.ArgumentParser(description="Collect Toss OpenAPI data locally and upload it to the Render app cache.")
    parser.add_argument("--symbols", default=os.environ.get("TOSS_SYMBOLS", ",".join(DEFAULT_SYMBOLS)))
    parser.add_argument("--url", default=os.environ.get("RENDER_INGEST_URL", "https://bikresearch.onrender.com/api/ingest/toss-cache"))
    parser.add_argument("--secret", default=os.environ.get("INGEST_SECRET", ""))
    parser.add_argument("--interval", type=int, default=int(os.environ.get("COLLECT_INTERVAL_SECONDS", "0")))
    args = parser.parse_args()

    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    if args.interval <= 0:
        run_once(symbols, args.url, args.secret)
        return

    while True:
        started_at = time.time()
        try:
            run_once(symbols, args.url, args.secret)
        except Exception as exc:
            print(f"[error] upload failed: {exc}")
        elapsed = time.time() - started_at
        time.sleep(max(1, args.interval - elapsed))


if __name__ == "__main__":
    main()
