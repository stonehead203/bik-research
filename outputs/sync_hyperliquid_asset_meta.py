import argparse
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
    args = parser.parse_args()

    response = requests.get(DOC_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    items = build_asset_meta(response.text)

    if args.include_simple_icons:
        items = attach_simple_icon_urls(items, verify=not args.no_verify_icons)

    if args.preserve_icons:
        remote = load_remote_cache()
        remote_items = remote.get("items", {}) if isinstance(remote, dict) else {}
        for key, value in remote_items.items():
            normalized = str(key or "").upper()
            if normalized in items and isinstance(value, dict):
                for icon_key in ("iconUrl", "iconSource", "iconLicense", "iconUpdatedAt"):
                    if value.get(icon_key):
                        items[normalized][icon_key] = value[icon_key]

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
