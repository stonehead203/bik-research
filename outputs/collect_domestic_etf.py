import json
import time

from company_analysis_app import (
    _enrich_domestic_etf_holdings,
    collect_domestic_etf_dashboard,
)


def main():
    payload = collect_domestic_etf_dashboard()
    for _ in range(20):
        if str((payload or {}).get("enrichmentStatus") or "") != "collecting":
            break
        time.sleep(30)
        payload = _enrich_domestic_etf_holdings(payload)

    progress = (payload or {}).get("enrichmentProgress") or {}
    summary = {
        "status": (payload or {}).get("status"),
        "asOf": (payload or {}).get("asOf"),
        "enrichmentStatus": (payload or {}).get("enrichmentStatus"),
        "processed": progress.get("processed"),
        "total": progress.get("total"),
        "provider": (payload or {}).get("holdingsProvider"),
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if summary["enrichmentStatus"] == "collecting":
        raise SystemExit("ETF holdings collection did not complete within 20 batches.")


if __name__ == "__main__":
    main()
