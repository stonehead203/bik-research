import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / "icons"
META_PATH = BASE_DIR / "hyperliquid_asset_meta.json"
HYPERLIQUID_INFO_URL = os.environ.get("HYPERLIQUID_INFO_URL", "https://api.hyperliquid.xyz/info")
ICON_BASE_URL = "https://app.hyperliquid.xyz/coins"

TEXT_FALLBACK = {
    "xyz:WTIOIL": "Oil",
    "xyz:CL": "Oil",
    "xyz:BRENTOIL": "Oil",
    "xyz:NATGAS": "Gas",
    "xyz:TTF": "Gas",
    "xyz:GOLD": "Gold",
    "xyz:SILVER": "Silver",
    "xyz:COPPER": "Copper",
    "xyz:PLATINUM": "Plat",
    "xyz:PALLADIUM": "Pall",
    "xyz:ALUMINIUM": "Alum",
    "xyz:URANIUM": "Uran",
    "xyz:DRAM": "DRAM",
    "xyz:H100": "H100",
    "xyz:DXY": "DXY",
    "xyz:VIX": "VIX",
    "xyz:VOL": "VOL",
    "xyz:CORN": "Corn",
    "xyz:WHEAT": "Wheat",
    "xyz:IBOV": "IBOV",
    "xyz:NIFTY": "NIFTY",
}

FLAG_FALLBACK = {
    "xyz:JPY": ("JP", "JPY"),
    "xyz:EUR": ("\U0001F1EA\U0001F1FA", "EUR"),
    "xyz:GBP": ("\U0001F1EC\U0001F1E7", "GBP"),
    "xyz:KRW": ("KR", "KRW"),
    "xyz:SP500": ("US", "S&P"),
    "xyz:XYZ100": ("US", "NDX"),
    "xyz:KR200": ("KR", "KR200"),
    "xyz:JP225": ("JP", "225"),
}

TEXT_FALLBACK = {key.lower(): value for key, value in TEXT_FALLBACK.items()}
FLAG_FALLBACK = {key.lower(): value for key, value in FLAG_FALLBACK.items()}

def safe_filename(symbol):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", symbol).strip("-").lower() + ".svg"


def post_info(payload):
    response = requests.post(HYPERLIQUID_INFO_URL, json=payload, timeout=20)
    response.raise_for_status()
    return response.json()


def fetch_symbols():
    symbols = []
    main = post_info({"type": "metaAndAssetCtxs"})
    for item in (main[0] or {}).get("universe", []):
        name = str(item.get("name") or "").strip()
        if name:
            symbols.append(name)
    xyz = post_info({"type": "metaAndAssetCtxs", "dex": "xyz"})
    for item in (xyz[0] or {}).get("universe", []):
        name = str(item.get("name") or "").strip()
        if name:
            symbols.append(name)
    return list(dict.fromkeys(symbols))


def make_text_svg(label):
    label = str(label or "?")[:7]
    font_size = 22 if len(label) <= 4 else 17
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 56 56" role="img" aria-label="{label}">
  <rect width="56" height="56" rx="28" fill="#111827"/>
  <rect x="1" y="1" width="54" height="54" rx="27" fill="none" stroke="#334155" stroke-width="2"/>
  <text x="28" y="31" dominant-baseline="middle" text-anchor="middle" fill="#e5e7eb" font-family="Inter, Arial, sans-serif" font-size="{font_size}" font-weight="800">{label}</text>
</svg>
'''



def make_us_flag_svg(label):
    stripe_h = 56 / 13
    stripes = []
    for i in range(13):
        color = "#b22234" if i % 2 == 0 else "#ffffff"
        stripes.append(f'<rect y="{i * stripe_h:.4f}" width="56" height="{stripe_h:.4f}" fill="{color}"/>')
    stars = []
    for row in range(5):
        for col in range(6):
            stars.append(f'<circle cx="{3.8 + col * 5.1:.2f}" cy="{3.4 + row * 4.1:.2f}" r="0.72" fill="#ffffff"/>')
    for row in range(4):
        for col in range(5):
            stars.append(f'<circle cx="{6.35 + col * 5.1:.2f}" cy="{5.45 + row * 4.1:.2f}" r="0.72" fill="#ffffff"/>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 56 56" role="img" aria-label="United States flag {label}">
  <defs><clipPath id="clip"><circle cx="28" cy="28" r="28"/></clipPath></defs>
  <g clip-path="url(#clip)">
    {''.join(stripes)}
    <rect width="31" height="24" fill="#3c3b6e"/>
    {''.join(stars)}
  </g>
</svg>
"""


def make_jp_flag_svg(label):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 56 56" role="img" aria-label="Japan flag {label}">
  <defs><clipPath id="clip"><circle cx="28" cy="28" r="28"/></clipPath></defs>
  <g clip-path="url(#clip)">
    <rect width="56" height="56" fill="#ffffff"/>
    <circle cx="28" cy="28" r="13.2" fill="#bc002d"/>
  </g>
</svg>
"""


def make_kr_flag_svg(label):
    response = requests.get(
        "https://upload.wikimedia.org/wikipedia/commons/0/09/Flag_of_South_Korea.svg",
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    svg = response.text
    if "<svg" not in svg[:1000]:
        return make_text_svg(label)
    return svg


def make_country_flag_svg(country, label):
    if country == "US":
        return make_us_flag_svg(label)
    if country == "KR":
        return make_kr_flag_svg(label)
    if country == "JP":
        return make_jp_flag_svg(label)
    return make_text_svg(label)

def make_flag_svg(flag, code):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 56 56" role="img" aria-label="{code}">
  <rect width="56" height="56" rx="28" fill="#0f172a"/>
  <text x="28" y="25" dominant-baseline="middle" text-anchor="middle" font-family="Apple Color Emoji, Segoe UI Emoji, Noto Color Emoji, sans-serif" font-size="24">{flag}</text>
  <text x="28" y="42" dominant-baseline="middle" text-anchor="middle" fill="#cbd5e1" font-family="Inter, Arial, sans-serif" font-size="10" font-weight="800">{code}</text>
</svg>
'''


def download_icon(session, symbol):
    url = f"{ICON_BASE_URL}/{urllib.parse.quote(symbol, safe='')}.svg"
    response = session.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    content_type = response.headers.get("content-type", "")
    if response.status_code == 200 and "svg" in content_type and "<svg" in response.text[:500].lower():
        return response.text, url
    return None, url


def main():
    ICON_DIR.mkdir(exist_ok=True)
    symbols = fetch_symbols()
    meta = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {"items": {}}
    items = meta.setdefault("items", {})
    session = requests.Session()
    stats = {"downloaded": 0, "fallback": 0, "failed": 0}

    for index, symbol in enumerate(symbols, 1):
        filename = safe_filename(symbol)
        path = ICON_DIR / filename
        normalized = symbol.lower()
        source_url = ""
        if normalized in FLAG_FALLBACK:
            country, label = FLAG_FALLBACK[normalized]
            svg = make_country_flag_svg(country, label) if country in {"US", "KR", "JP"} else make_flag_svg(country, label)
            source = "generated-flag"
            stats["fallback"] += 1
        elif normalized in TEXT_FALLBACK:
            svg = make_text_svg(TEXT_FALLBACK[normalized])
            source = "generated-text"
            stats["fallback"] += 1
        else:
            svg, source_url = download_icon(session, symbol)
            source = "Hyperliquid"
            if not svg:
                svg = make_text_svg(symbol.split(":")[-1])
                source = "generated-text"
                stats["fallback"] += 1
            else:
                stats["downloaded"] += 1
        path.write_text(svg, encoding="utf-8")
        key = symbol.upper()
        items.setdefault(key, {})
        items[key]["iconUrl"] = f"/icons/{filename}"
        items[key]["iconSource"] = source
        items[key]["iconOriginalUrl"] = source_url if source == "Hyperliquid" else ""
        if index % 25 == 0:
            print(f"{index}/{len(symbols)} icons processed", flush=True)
        time.sleep(0.02)

    meta["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"symbols": len(symbols), **stats, "dir": str(ICON_DIR)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

