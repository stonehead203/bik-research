import argparse
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


DOC_URL = "https://docs.trade.xyz/consolidated-resources/specification-index"
CACHE_KEY = "hyperliquid:asset_meta"
DEFAULT_OUTPUT = Path(__file__).with_name("hyperliquid_asset_meta.json")


DISPLAY_NAMES = {
    "SP500": "S&P 500",
    "XYZ100": "Nasdaq 100",
    "BRENTOIL": "Brent Oil",
    "WTIOIL": "WTI Oil",
    "NATGAS": "Natural Gas",
    "GOLD": "Gold",
    "SILVER": "Silver",
    "PLATINUM": "Platinum",
    "PALLADIUM": "Palladium",
    "COPPER": "Copper",
    "JPY": "Japanese Yen",
    "EUR": "Euro",
    "GBP": "British Pound",
    "SKHYNIX": "SK hynix",
    "SAMSUNG": "Samsung Electronics",
    "TSLA": "Tesla",
    "NVDA": "NVIDIA",
    "GOOGL": "Alphabet",
    "INTC": "Intel",
    "MU": "Micron",
    "PLTR": "Palantir",
    "ORCL": "Oracle",
    "MSTR": "Strategy",
    "MSFT": "Microsoft",
    "META": "Meta Platforms",
    "AMZN": "Amazon",
    "AMD": "AMD",
    "AAPL": "Apple",
    "COIN": "Coinbase",
    "HOOD": "Robinhood",
    "NFLX": "Netflix",
    "CRCL": "Circle",
    "SNDK": "SanDisk",
    "RIVN": "Rivian",
    "USAR": "USA Rare Earth",
    "TSM": "TSMC",
    "HYUNDAI": "Hyundai Motor",
    "BABA": "Alibaba",
    "DKNG": "DraftKings",
    "HIMS": "Hims & Hers",
    "COST": "Costco",
    "LLY": "Eli Lilly",
    "JP225": "Nikkei 225",
    "KR200": "KOSPI 200",
    "DRAM": "DRAM",
    "XLE": "Energy Select Sector SPDR Fund",
    "BX": "Blackstone",
    "GME": "GameStop",
    "RKLB": "Rocket Lab",
    "MRVL": "Marvell",
    "ZM": "Zoom",
    "EBAY": "eBay",
    "ARM": "Arm Holdings",
    "ASML": "ASML",
    "IBM": "IBM",
    "DELL": "Dell",
    "AVGO": "Broadcom",
    "NOW": "ServiceNow",
    "WDC": "Western Digital",
    "NBIS": "Nebius",
    "SPCX": "SPCX",
    "BE": "Bloom Energy",
    "SMH": "VanEck Semiconductor ETF",
    "NOK": "Nokia",
    "QCOM": "Qualcomm",
    "AMAT": "Applied Materials",
}


DOC_SYMBOL_ALIASES = {
    "WTIOIL": ["XYZ:WTIOIL", "XYZ:CL"],
    "SKHYNIX": ["XYZ:SKHYNIX", "XYZ:SKHX"],
    "SAMSUNG": ["XYZ:SAMSUNG", "XYZ:SMSN"],
}


HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
HYPERLIQUID_TRADE_URL = "https://app.hyperliquid.xyz/trade/{coin}"
COIN_INFO_BUTTON_XPATH = '//*[@id="coinInfo"]/div/div[2]/div[1]/div/div[1]/div/div[1]/div'
LOCAL_ICON_FIELDS = ("iconUrl", "iconSource", "iconLicense", "iconOriginalUrl", "iconUpdatedAt")


SIMPLE_ICON_SLUGS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "xrp",
    "BNB": "binance",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "AVAX": "avalanche",
    "LINK": "chainlink",
    "TON": "ton",
    "LTC": "litecoin",
    "BCH": "bitcoincash",
    "PAXG": "paxos",
    "XYZ:TSLA": "tesla",
    "XYZ:NVDA": "nvidia",
    "XYZ:GOOGL": "google",
    "XYZ:INTC": "intel",
    "XYZ:PLTR": "palantir",
    "XYZ:ORCL": "oracle",
    "XYZ:MSFT": "microsoft",
    "XYZ:META": "meta",
    "XYZ:AMZN": "amazon",
    "XYZ:AMD": "amd",
    "XYZ:AAPL": "apple",
    "XYZ:COIN": "coinbase",
    "XYZ:HOOD": "robinhood",
    "XYZ:NFLX": "netflix",
    "XYZ:RIVN": "rivian",
    "XYZ:TSM": "tsmc",
    "XYZ:SAMSUNG": "samsung",
    "XYZ:SMSN": "samsung",
    "XYZ:BABA": "alibabadotcom",
    "XYZ:COST": "costco",
    "XYZ:ARM": "arm",
    "XYZ:ASML": "asml",
    "XYZ:IBM": "ibm",
    "XYZ:DELL": "dell",
    "XYZ:AVGO": "broadcom",
    "XYZ:NOW": "servicenow",
    "XYZ:NOK": "nokia",
    "XYZ:QCOM": "qualcomm",
    "XYZ:AMAT": "appliedmaterials",
}

CRYPTO_META = {
    "BTC": {"name": "Bitcoin", "description": "Bitcoin perpetual market on Hyperliquid."},
    "ETH": {"name": "Ethereum", "description": "Ethereum perpetual market on Hyperliquid."},
    "HYPE": {"name": "Hyperliquid", "description": "Hyperliquid native token perpetual market."},
    "SOL": {"name": "Solana", "description": "Solana perpetual market on Hyperliquid."},
    "XRP": {"name": "XRP", "description": "XRP perpetual market on Hyperliquid."},
    "BNB": {"name": "BNB", "description": "BNB perpetual market on Hyperliquid."},
    "DOGE": {"name": "Dogecoin", "description": "Dogecoin perpetual market on Hyperliquid."},
    "ADA": {"name": "Cardano", "description": "Cardano perpetual market on Hyperliquid."},
    "AVAX": {"name": "Avalanche", "description": "Avalanche perpetual market on Hyperliquid."},
    "LINK": {"name": "Chainlink", "description": "Chainlink perpetual market on Hyperliquid."},
    "TRX": {"name": "TRON", "description": "TRON perpetual market on Hyperliquid."},
    "SUI": {"name": "Sui", "description": "Sui perpetual market on Hyperliquid."},
    "TON": {"name": "Toncoin", "description": "Toncoin perpetual market on Hyperliquid."},
    "APT": {"name": "Aptos", "description": "Aptos perpetual market on Hyperliquid."},
    "ARB": {"name": "Arbitrum", "description": "Arbitrum perpetual market on Hyperliquid."},
    "OP": {"name": "Optimism", "description": "Optimism perpetual market on Hyperliquid."},
    "LTC": {"name": "Litecoin", "description": "Litecoin perpetual market on Hyperliquid."},
    "BCH": {"name": "Bitcoin Cash", "description": "Bitcoin Cash perpetual market on Hyperliquid."},
    "PAXG": {"name": "PAX Gold", "description": "PAX Gold perpetual market on Hyperliquid."},
}


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def derive_name(symbol, description):
    if symbol in DISPLAY_NAMES:
        return DISPLAY_NAMES[symbol]
    match = re.search(r"common stock in ([^.]+)", description, flags=re.IGNORECASE)
    if match:
        name = re.sub(r",?\s+(Inc|Inc\.|Corporation|Corp\.?|Ltd\.?|N\.V\.|PLC)$", "", match.group(1).strip())
        return name.strip()
    return symbol


def parse_trade_xyz_specs(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for row in soup.select("[role=row]"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.select("[role=cell], [role=columnheader]")]
        if len(cells) < 2 or cells[0].lower() == "instrument":
            continue
        rows.append(cells)
    if rows:
        return rows

    paragraphs = [clean_text(p.get_text(" ", strip=True)) for p in soup.select("p")]
    paragraphs = [item for item in paragraphs if item]
    known_symbols = set(DISPLAY_NAMES) | {"WTIOIL", "SKHYNIX", "SAMSUNG"}
    for index, value in enumerate(paragraphs):
        symbol = value.upper()
        if symbol in known_symbols and index + 1 < len(paragraphs):
            rows.append(paragraphs[index:index + 8])
    return rows


def build_asset_meta(html):
    items = {}
    for key, value in CRYPTO_META.items():
        items[key] = {**value, "source": "manual", "assetClass": "crypto"}

    for cells in parse_trade_xyz_specs(html):
        symbol = cells[0].upper()
        description = clean_text(cells[1])
        item = {
            "name": derive_name(symbol, description),
            "description": description,
            "instrument": symbol,
            "underlying": cells[2] if len(cells) > 2 else "",
            "maxLeverage": cells[3] if len(cells) > 3 else "",
            "source": "trade.xyz",
            "sourceUrl": DOC_URL,
            "assetClass": "global",
        }
        keys = DOC_SYMBOL_ALIASES.get(symbol, [f"XYZ:{symbol}"])
        for key in keys:
            items[key.upper()] = dict(item)
    return items


def post_hyperliquid_info(payload):
    response = requests.post(HYPERLIQUID_INFO_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_hyperliquid_coin_symbols():
    data = post_hyperliquid_info({"type": "metaAndAssetCtxs"})
    universe = (data[0] or {}).get("universe", []) if isinstance(data, list) and data else []
    symbols = []
    for item in universe:
        name = clean_text(item.get("name"))
        if name:
            symbols.append(name.upper())
    return list(dict.fromkeys(symbols))


def parse_coin_popup_description(text, coin):
    lines = [clean_text(line) for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    header = lines[0]
    if header.upper().startswith(f"{coin.upper()}-") or header.upper() == coin.upper():
        lines = lines[1:]
    description = clean_text(" ".join(lines))
    noisy = ("Trade Outcomes Portfolio Earn Vaults", "Connect", "Order Book", "No open positions yet")
    if any(token in description for token in noisy):
        return ""
    return description


async def collect_coin_descriptions_with_playwright(symbols, delay_ms=350):
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        raise RuntimeError("Playwright is required for --include-coin-descriptions") from exc

    descriptions = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1365, "height": 900})
        for coin in symbols:
            try:
                await page.goto(HYPERLIQUID_TRADE_URL.format(coin=coin), wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_selector("#coinInfo", timeout=30000)
                await page.wait_for_timeout(1500)
                button = page.locator(f"xpath={COIN_INFO_BUTTON_XPATH}")
                if await button.count():
                    await button.click(timeout=10000)
                else:
                    await page.locator("#coinInfo svg").first.click(timeout=10000)
                await page.wait_for_timeout(900)
                chunks = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('#root > div')).map((node) => (node.innerText || '').trim())
                """)
                for chunk in reversed(chunks):
                    description = parse_coin_popup_description(chunk, coin)
                    if description:
                        descriptions[coin.upper()] = description
                        break
                await page.keyboard.press("Escape")
                if delay_ms:
                    await page.wait_for_timeout(delay_ms)
            except Exception as exc:
                print(f"coin description lookup failed ({coin}): {exc}", flush=True)
        await browser.close()
    return descriptions


def apply_coin_descriptions(items, descriptions):
    for coin, description in descriptions.items():
        item = items.setdefault(coin.upper(), {"name": coin.upper(), "assetClass": "crypto"})
        item["description"] = description
        item["source"] = "hyperliquid"
        item["sourceUrl"] = HYPERLIQUID_TRADE_URL.format(coin=coin.upper())
        item["assetClass"] = "crypto"
    return items


def load_local_payload(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def preserve_icon_fields(items, *payloads):
    for payload in payloads:
        payload_items = payload.get("items", {}) if isinstance(payload, dict) else {}
        if not isinstance(payload_items, dict):
            continue
        for key, value in payload_items.items():
            normalized = str(key or "").upper()
            if normalized in items and isinstance(value, dict):
                for icon_key in LOCAL_ICON_FIELDS:
                    if value.get(icon_key):
                        items[normalized][icon_key] = value[icon_key]
    return items


def attach_simple_icon_urls(items, verify=True):
    session = requests.Session()
    for key, slug in SIMPLE_ICON_SLUGS.items():
        normalized = key.upper()
        if normalized not in items:
            continue
        url = f"https://cdn.simpleicons.org/{slug}"
        if verify:
            try:
                response = session.get(url, timeout=8)
                content_type = response.headers.get("content-type", "")
                if response.status_code != 200 or "svg" not in content_type:
                    continue
            except Exception:
                continue
        items[normalized]["iconUrl"] = url
        items[normalized]["iconSource"] = "Simple Icons"
        items[normalized]["iconLicense"] = "CC0-1.0; trademarks remain with their owners"
    return items

def load_remote_cache():
    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    table = os.environ.get("SUPABASE_APP_CACHE_TABLE", "app_cache").strip()
    if not supabase_url or not service_key:
        return None
    response = requests.get(
        f"{supabase_url}/rest/v1/{table}",
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        params={"key": f"eq.{CACHE_KEY}", "select": "payload", "limit": "1"},
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0].get("payload") if rows else None


def upsert_supabase(payload):
    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    table = os.environ.get("SUPABASE_APP_CACHE_TABLE", "app_cache").strip()
    if not supabase_url or not service_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for --upload")
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
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase upsert failed: {response.status_code} {response.text[:500]}")


def main():
    parser = argparse.ArgumentParser(description="Sync Hyperliquid/XYZ asset metadata from trade.xyz docs.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Local JSON output path.")
    parser.add_argument("--upload", action="store_true", help="Upload payload to Supabase app_cache.")
    parser.add_argument("--preserve-icons", action="store_true", help="Keep existing iconUrl/iconSource fields from Supabase.")
    parser.add_argument("--include-simple-icons", action="store_true", help="Attach verified Simple Icons CDN SVG URLs where available.")
    parser.add_argument("--no-verify-icons", action="store_true", help="Skip HTTP verification for Simple Icons URLs.")
    parser.add_argument("--include-coin-descriptions", action="store_true", help="Scrape full crypto descriptions from Hyperliquid coin info popovers with Playwright.")
    parser.add_argument("--coin-symbols", default="", help="Comma-separated crypto symbols to scrape. Defaults to all Hyperliquid main coins.")
    parser.add_argument("--coin-limit", type=int, default=0, help="Limit crypto description scraping count for testing.")
    parser.add_argument("--coin-delay-ms", type=int, default=350, help="Delay between Hyperliquid coin pages while scraping.")
    args = parser.parse_args()

    response = requests.get(DOC_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    items = build_asset_meta(response.text)

    if args.include_simple_icons:
        items = attach_simple_icon_urls(items, verify=not args.no_verify_icons)

    local_payload = load_local_payload(args.output)
    remote = load_remote_cache() if args.preserve_icons else None
    items = preserve_icon_fields(items, local_payload, remote)

    if args.include_coin_descriptions:
        if args.coin_symbols:
            symbols = [clean_text(item).upper() for item in args.coin_symbols.split(",") if clean_text(item)]
        else:
            symbols = fetch_hyperliquid_coin_symbols()
        if args.coin_limit:
            symbols = symbols[: max(0, args.coin_limit)]
        descriptions = asyncio.run(collect_coin_descriptions_with_playwright(symbols, delay_ms=args.coin_delay_ms))
        items = apply_coin_descriptions(items, descriptions)

    payload = {
        "items": items,
        "source": "trade.xyz",
        "sourceUrl": DOC_URL,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.upload:
        upsert_supabase(payload)
    print(json.dumps({"items": len(items), "output": str(output_path), "uploaded": args.upload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
