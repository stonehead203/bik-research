import argparse
from datetime import datetime, timezone
try:
    import fcntl
except ImportError:
    fcntl = None
from html.parser import HTMLParser
import json
import math
import os
import re
import time
from urllib.parse import urljoin

import requests


DEFAULT_INGEST_URL = "https://www.bikresearch.com/api/ingest/toss-cache"
DEFAULT_TOSS_BASE_URL = "https://openapi.tossinvest.com"
DEFAULT_KR_UNIVERSE_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
DEFAULT_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "toss_collector_state.json")
DEFAULT_LOCK_FILE = "/tmp/bik-toss-collector.lock"
DEFAULT_DETAIL_SYMBOLS = [
    "005930", "000660", "035420", "035720", "005380", "000270", "068270", "207940",
    "051910", "006400", "373220", "005490", "105560", "055550", "086790", "012330",
    "028260", "066570", "323410", "096770", "034730", "003550", "017670", "032830",
    "015760", "009540", "010140", "042660", "009150", "000810",
]
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


def env_bool(name, default=False):
    raw = os.environ.get(name, "").strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


def env_int(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def normalize_symbol(value):
    return re.sub(r"\s+", "", str(value or "").upper())


def read_json_file(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return fallback


def write_json_file(path, payload):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


class HtmlTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_cell = False
        self.cell = ""
        self.row = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"td", "th"}:
            self.in_cell = True
            self.cell = ""

    def handle_data(self, data):
        if self.in_cell:
            self.cell += data

    def handle_endtag(self, tag):
        lowered = tag.lower()
        if lowered in {"td", "th"} and self.in_cell:
            self.row.append(" ".join(self.cell.split()))
            self.in_cell = False
        elif lowered == "tr":
            if self.row:
                self.rows.append(self.row)
            self.row = []


def parse_krx_universe_html(html):
    parser = HtmlTableParser()
    parser.feed(html)
    if not parser.rows:
        return []

    headers = parser.rows[0]
    try:
        name_idx = headers.index("회사명")
        market_idx = headers.index("시장구분")
        symbol_idx = headers.index("종목코드")
    except ValueError:
        return []

    rows = []
    allowed_markets = {
        market.strip()
        for market in os.environ.get("TOSS_KR_MARKETS", "유가,유가증권,유가증권시장,코스닥,코넥스,KOSPI,KOSDAQ,KONEX").split(",")
        if market.strip()
    }
    for row in parser.rows[1:]:
        if len(row) <= max(name_idx, market_idx, symbol_idx):
            continue
        symbol = normalize_symbol(row[symbol_idx])
        if not re.fullmatch(r"[A-Z0-9]{6}", symbol or ""):
            continue
        market = row[market_idx].strip()
        if allowed_markets and market not in allowed_markets:
            continue
        rows.append({
            "symbol": symbol,
            "name": row[name_idx].strip(),
            "market": market,
            "industry": row[3].strip() if len(row) > 3 else "",
            "listDate": row[5].strip() if len(row) > 5 else "",
        })
    return rows


def load_symbols_from_file(path):
    payload = read_json_file(path, None)
    rows = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                symbol = normalize_symbol(item.get("symbol") or item.get("code"))
                name = str(item.get("name") or item.get("companyName") or "").strip()
                market = str(item.get("market") or "").strip()
            else:
                symbol = normalize_symbol(item)
                name = ""
                market = ""
            if re.fullmatch(r"[A-Z0-9]{6}", symbol or ""):
                rows.append({"symbol": symbol, "name": name or symbol, "market": market})
    return rows


def load_kr_universe(session):
    file_path = os.environ.get("TOSS_KR_SYMBOLS_FILE", "").strip()
    if file_path:
        rows = load_symbols_from_file(file_path)
        if rows:
            return rows

    json_symbols = load_json_env("TOSS_KR_SYMBOLS_JSON", [])
    if isinstance(json_symbols, list) and json_symbols:
        rows = []
        for item in json_symbols:
            symbol = normalize_symbol(item.get("symbol") if isinstance(item, dict) else item)
            name = str(item.get("name") or symbol).strip() if isinstance(item, dict) else symbol
            market = str(item.get("market") or "").strip() if isinstance(item, dict) else ""
            if re.fullmatch(r"[A-Z0-9]{6}", symbol or ""):
                rows.append({"symbol": symbol, "name": name, "market": market})
        if rows:
            return rows

    universe_url = os.environ.get("TOSS_KR_UNIVERSE_URL", DEFAULT_KR_UNIVERSE_URL).strip()
    response = session.get(
        universe_url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "bik-research-toss-collector/1.0",
        },
        timeout=30,
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "euc-kr"
    rows = parse_krx_universe_html(response.text)
    if not rows:
        raise RuntimeError("KRX universe was empty or not parseable.")
    return rows


def chunked(values, size):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def load_detail_symbols(universe):
    scope = os.environ.get("TOSS_DETAIL_SYMBOL_SCOPE", "default").strip().lower()
    if scope in {"all", "universe", "krx"}:
        symbols = [row["symbol"] for row in universe]
    else:
        raw = os.environ.get("TOSS_KR_DETAIL_SYMBOLS", "").strip()
        symbols = [normalize_symbol(value) for value in raw.split(",") if value.strip()] if raw else DEFAULT_DETAIL_SYMBOLS

    universe_symbols = {row["symbol"] for row in universe}
    limit = max(0, env_int("TOSS_DETAIL_SYMBOL_LIMIT", 50))
    cleaned = []
    for symbol in symbols:
        if env_bool("TOSS_DETAIL_NUMERIC_ONLY", True) and not re.fullmatch(r"\d{6}", symbol or ""):
            continue
        if symbol in universe_symbols and symbol not in cleaned:
            cleaned.append(symbol)
        if limit and len(cleaned) >= limit:
            break
    return cleaned


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


def reset_toss_access_token():
    _TOKEN_CACHE["access_token"] = ""
    _TOKEN_CACHE["expires_at"] = 0.0


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


def request_with_toss_auth(session, method, url, base_url, spec, timeout):
    response = session.request(
        method,
        url,
        params=spec.get("params"),
        json=spec.get("json"),
        data=spec.get("data"),
        headers=build_headers(session, base_url, spec.get("headers")),
        timeout=timeout,
    )
    if response.status_code != 401 or first_env("TOSS_BEARER_TOKEN", "TOSSINVEST_BEARER_TOKEN"):
        return response

    reset_toss_access_token()
    response = session.request(
        method,
        url,
        params=spec.get("params"),
        json=spec.get("json"),
        data=spec.get("data"),
        headers=build_headers(session, base_url, spec.get("headers")),
        timeout=timeout,
    )
    return response


def request_toss_item(session, base_url, spec):
    if not isinstance(spec, dict):
        raise RuntimeError("Each request spec must be a JSON object.")

    name = str(spec.get("name") or spec.get("path") or "unnamed").strip()
    method = str(spec.get("method", "GET")).upper()
    path = str(spec.get("path", "")).strip()
    url = spec.get("url") or urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    timeout = int(spec.get("timeout", 20))

    response = request_with_toss_auth(session, method, url, base_url, spec, timeout)
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


def build_kr_universe_requests(session, state):
    if not env_bool("TOSS_KR_UNIVERSE_ENABLED", False):
        return [], None

    universe = load_kr_universe(session)
    symbols = [row["symbol"] for row in universe]
    batch_size = max(1, min(200, env_int("TOSS_BATCH_SIZE", 200)))
    requests_to_add = []

    if env_bool("TOSS_COLLECT_KR_PRICES", True):
        for batch_index, batch in enumerate(chunked(symbols, batch_size), start=1):
            requests_to_add.append({
                "name": f"kr_prices_{batch_index:03d}",
                "method": "GET",
                "path": "/api/v1/prices",
                "params": {"symbols": ",".join(batch)},
                "timeout": 30,
                "generated": "kr-universe",
            })

    stock_interval = env_int("TOSS_STOCK_INFO_INTERVAL_SECONDS", 86400)
    last_stock_refresh = float(state.get("kr_stock_info_refreshed_at") or 0)
    stock_info_fresh = (
        stock_interval > 0
        and last_stock_refresh
        and time.time() - last_stock_refresh < stock_interval
        and isinstance(state.get("kr_stock_items"), dict)
    )
    if env_bool("TOSS_COLLECT_KR_STOCK_INFO", True) and not stock_info_fresh:
        for batch_index, batch in enumerate(chunked(symbols, batch_size), start=1):
            requests_to_add.append({
                "name": f"kr_stocks_{batch_index:03d}",
                "method": "GET",
                "path": "/api/v1/stocks",
                "params": {"symbols": ",".join(batch)},
                "timeout": 30,
                "generated": "kr-universe-stock-info",
            })

    detail_interval = env_int("TOSS_DETAIL_INTERVAL_SECONDS", 300)
    last_detail_refresh = float(state.get("kr_detail_refreshed_at") or 0)
    detail_fresh = (
        detail_interval > 0
        and last_detail_refresh
        and time.time() - last_detail_refresh < detail_interval
        and isinstance(state.get("kr_detail_items"), dict)
    )
    detail_symbols = load_detail_symbols(universe)
    if detail_symbols and not detail_fresh:
        if env_bool("TOSS_COLLECT_KR_PRICE_LIMITS", False):
            for symbol in detail_symbols:
                requests_to_add.append({
                    "name": f"kr_price_limit_{symbol}",
                    "method": "GET",
                    "path": "/api/v1/price-limits",
                    "params": {"symbol": symbol},
                    "timeout": 20,
                    "generated": "kr-universe-detail",
                })

        if env_bool("TOSS_COLLECT_KR_CANDLES", False):
            intervals = [
                interval.strip()
                for interval in os.environ.get("TOSS_CANDLE_INTERVALS", "1d,1m").split(",")
                if interval.strip() in {"1d", "1m"}
            ]
            candle_count = max(1, min(200, env_int("TOSS_CANDLE_COUNT", 60)))
            for symbol in detail_symbols:
                for interval in intervals:
                    requests_to_add.append({
                        "name": f"kr_candles_{interval}_{symbol}",
                        "method": "GET",
                        "path": "/api/v1/candles",
                        "params": {"symbol": symbol, "interval": interval, "count": candle_count},
                        "timeout": 20,
                        "generated": "kr-universe-detail",
                    })

    universe_item = {
        "ok": True,
        "statusCode": 200,
        "url": os.environ.get("TOSS_KR_UNIVERSE_URL", DEFAULT_KR_UNIVERSE_URL),
        "data": {
            "result": universe,
            "count": len(universe),
            "detailSymbols": detail_symbols,
        },
    }
    return requests_to_add, universe_item


def sleep_between_generated_requests(spec):
    if not spec.get("generated"):
        return
    delay = float(os.environ.get("TOSS_BATCH_SLEEP_SECONDS", "0.15") or "0")
    if delay > 0:
        time.sleep(delay)


def build_payload(request_specs, persist_state=True):
    base_url = first_env("TOSS_BASE_URL", "TOSSINVEST_BASE_URL") or DEFAULT_TOSS_BASE_URL
    if not base_url and any(not spec.get("url") for spec in request_specs if isinstance(spec, dict)):
        raise RuntimeError("TOSS_BASE_URL is required when a request spec uses path instead of url.")

    items = {}
    errors = []
    state_file = os.environ.get("TOSS_COLLECTOR_STATE_FILE", DEFAULT_STATE_FILE)
    state = read_json_file(state_file, {})
    with requests.Session() as session:
        try:
            generated_specs, universe_item = build_kr_universe_requests(session, state)
            if universe_item:
                items["kr_universe"] = universe_item
                print(f"[ok] kr_universe ({universe_item['data']['count']} symbols)")
            request_specs = list(request_specs) + generated_specs
        except Exception as exc:
            errors.append({"name": "kr_universe", "error": str(exc)})
            print(f"[skip] kr_universe: {exc}")

        for spec in request_specs:
            try:
                name, item = request_toss_item(session, base_url, spec)
                items[name] = item
                print(f"[ok] {name}")
                if str(name).startswith("kr_stocks_"):
                    state.setdefault("kr_stock_items", {})[name] = item
                    state["kr_stock_info_refreshed_at"] = time.time()
                if str(name).startswith(("kr_price_limit_", "kr_candles_")):
                    state.setdefault("kr_detail_items", {})[name] = item
                    state["kr_detail_refreshed_at"] = time.time()
                sleep_between_generated_requests(spec)
            except Exception as exc:
                name = spec.get("name") if isinstance(spec, dict) else "unnamed"
                errors.append({"name": name or "unnamed", "error": str(exc)})
                print(f"[skip] {name or 'unnamed'}: {exc}")

    include_state_items = env_bool("TOSS_INCLUDE_STATE_ITEMS", True)
    if include_state_items and isinstance(state.get("kr_stock_items"), dict):
        for name, item in state["kr_stock_items"].items():
            items.setdefault(name, item)
    if include_state_items and isinstance(state.get("kr_detail_items"), dict):
        for name, item in state["kr_detail_items"].items():
            items.setdefault(name, item)
    if state and persist_state:
        write_json_file(state_file, state)

    return {
        "ok": not errors,
        "source": "toss-openapi",
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": items,
        "errors": errors,
    }


def post_payload(payload, ingest_url, ingest_secret):
    response = requests.post(
        ingest_url,
        json=payload,
        headers={"Authorization": f"Bearer {ingest_secret}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def upload_payload(payload, ingest_url, ingest_secret):
    if not ingest_url:
        raise RuntimeError("RENDER_INGEST_URL is required.")
    if not ingest_secret:
        raise RuntimeError("INGEST_SECRET is required.")

    items = payload.get("items") if isinstance(payload.get("items"), dict) else {}
    chunk_size = max(1, env_int("TOSS_UPLOAD_CHUNK_SIZE", 120))
    if len(items) <= chunk_size:
        return post_payload(payload, ingest_url, ingest_secret)

    results = []
    item_pairs = list(items.items())
    total_chunks = math.ceil(len(item_pairs) / chunk_size)
    for index, chunk in enumerate(chunked(item_pairs, chunk_size), start=1):
        chunk_payload = {key: value for key, value in payload.items() if key not in {"items", "errors"}}
        chunk_payload["items"] = dict(chunk)
        chunk_payload["chunkIndex"] = index
        chunk_payload["chunkTotal"] = total_chunks
        if index == total_chunks and isinstance(payload.get("errors"), list):
            chunk_payload["errors"] = payload["errors"]
        result = post_payload(chunk_payload, ingest_url, ingest_secret)
        results.append(result)
        print(f"[uploaded chunk] {index}/{total_chunks} {result}")
    return {"ok": True, "chunks": results, "chunkTotal": total_chunks}


def run_once(request_specs, ingest_url, ingest_secret, dry_run=False):
    payload = build_payload(request_specs, persist_state=not dry_run)
    if dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return payload
    result = upload_payload(payload, ingest_url, ingest_secret)
    print(f"[uploaded] {result}")
    return result


def acquire_collector_lock():
    lock_file = os.environ.get("TOSS_COLLECTOR_LOCK_FILE", DEFAULT_LOCK_FILE).strip() or DEFAULT_LOCK_FILE
    directory = os.path.dirname(lock_file)
    if directory:
        os.makedirs(directory, exist_ok=True)
    handle = open(lock_file, "w", encoding="utf-8")
    if fcntl is not None:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"[skip] another collector process is already running: {lock_file}")
            handle.close()
            return None
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


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
    if not isinstance(request_specs, list):
        raise RuntimeError("TOSS_REQUESTS_JSON must be a JSON array.")
    if not request_specs and not env_bool("TOSS_KR_UNIVERSE_ENABLED", False):
        raise RuntimeError("TOSS_REQUESTS_JSON must be non-empty unless TOSS_KR_UNIVERSE_ENABLED=true.")

    lock_handle = acquire_collector_lock()
    if lock_handle is None:
        return

    if args.interval <= 0:
        try:
            run_once(request_specs, args.url, args.secret, args.dry_run)
        finally:
            lock_handle.close()
        return

    try:
        while True:
            started_at = time.time()
            try:
                run_once(request_specs, args.url, args.secret, args.dry_run)
            except Exception as exc:
                print(f"[error] collect/upload failed: {exc}")
            elapsed = time.time() - started_at
            time.sleep(max(1, args.interval - elapsed))
    finally:
        lock_handle.close()


if __name__ == "__main__":
    main()
