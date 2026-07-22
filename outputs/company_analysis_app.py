from datetime import datetime, time as datetime_time, timedelta, timezone
import ast
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
import html as html_lib
import hashlib
import io
import ipaddress
import json
import math
import os
import re
import secrets
import smtplib
import socket
import threading
from functools import wraps
import time
import urllib.request
from urllib.parse import quote, urljoin, urlparse
import xml.etree.ElementTree as ET
import zipfile
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from flask import Flask, jsonify, has_request_context, render_template, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


app = Flask(__name__, template_folder=".")


def load_local_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except Exception as exc:
        print(f"Local .env load failed: {exc}", flush=True)


load_local_env()

app.secret_key = os.environ.get("SECRET_KEY", "").strip() or "dev-secret-change-me"
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=int(os.environ.get("SESSION_DAYS", "30") or "30")),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "true").lower() != "false",
)

APP_USERNAME = os.environ.get("APP_USERNAME", "hodu")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "academy")
SUPER_ADMIN_USERNAME = os.environ.get("SUPER_ADMIN_USERNAME", "hodu")
KST = timezone(timedelta(hours=9))
API_CACHE = {}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOMESTIC_ICON_DIR = os.path.join(BASE_DIR, "domestic_icons")
DEFAULT_USERS_FILE = "/var/data/users.json" if os.path.isdir("/var/data") else os.path.join(BASE_DIR, "users.json")
USERS_FILE = os.environ.get("USERS_FILE", DEFAULT_USERS_FILE)
COMMUNITY_FILE = os.environ.get("COMMUNITY_FILE", os.path.join(BASE_DIR, "community_posts.json"))
COMMUNITY_LIKE_WINDOW_SECONDS = int(os.environ.get("COMMUNITY_LIKE_WINDOW_SECONDS", "20"))
COMMUNITY_LIKE_MAX_EVENTS = int(os.environ.get("COMMUNITY_LIKE_MAX_EVENTS", "8"))
DEFAULT_TOSS_CACHE_FILE = "/var/data/toss_cache.json" if os.path.isdir("/var/data") else os.path.join(BASE_DIR, "toss_cache.json")
TOSS_CACHE_FILE = os.environ.get("TOSS_CACHE_FILE", DEFAULT_TOSS_CACHE_FILE)
DEFAULT_TOSS_DETAIL_CACHE_DIR = "/var/data/toss_detail_cache" if os.path.isdir("/var/data") else os.path.join(BASE_DIR, "toss_detail_cache")
TOSS_DETAIL_CACHE_DIR = os.environ.get("TOSS_DETAIL_CACHE_DIR", DEFAULT_TOSS_DETAIL_CACHE_DIR)
INGEST_SECRET = os.environ.get("INGEST_SECRET", "").strip()
DART_API_KEY = os.environ.get("DART_API_KEY", "").strip()
DART_CORP_CODE_FILE = os.environ.get(
    "DART_CORP_CODE_FILE",
    "/var/data/dart_corp_codes.json" if os.path.isdir("/var/data") else os.path.join(BASE_DIR, "dart_corp_codes.json"),
)
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or "587")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = re.sub(r"\s+", "", os.environ.get("SMTP_PASSWORD", ""))
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USERNAME).strip()
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() != "false"
SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "false").lower() == "true" or SMTP_PORT == 465
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_FROM = os.environ.get("RESEND_FROM", SMTP_FROM or "Hodu Academy <onboarding@resend.dev>").strip()
SUPABASE_URL = re.sub(r"/rest/v1/?$", "", os.environ.get("SUPABASE_URL", "").strip().rstrip("/"))
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_USERS_TABLE = os.environ.get("SUPABASE_USERS_TABLE", "hodu_users").strip()
SUPABASE_COMMUNITY_TABLE = os.environ.get("SUPABASE_COMMUNITY_TABLE", "hodu_community_posts").strip()
SUPABASE_COMMUNITY_LIKES_TABLE = os.environ.get("SUPABASE_COMMUNITY_LIKES_TABLE", "hodu_community_likes").strip()
SUPABASE_COMMUNITY_REACTIONS_TABLE = os.environ.get("SUPABASE_COMMUNITY_REACTIONS_TABLE", "hodu_community_reactions").strip()
SUPABASE_COMMUNITY_CHANNELS_TABLE = os.environ.get("SUPABASE_COMMUNITY_CHANNELS_TABLE", "hodu_community_channels").strip()
SUPABASE_ADMIN_AUDIT_TABLE = os.environ.get("SUPABASE_ADMIN_AUDIT_TABLE", "hodu_admin_audit_logs").strip()
SUPABASE_USAGE_DAILY_TABLE = os.environ.get("SUPABASE_USAGE_DAILY_TABLE", "hodu_usage_daily").strip()
USAGE_TAB_NAMES = frozenset({
    "dashboard", "market-status", "insight", "company-beta", "export",
    "watchlist", "prediction", "eth-tracker", "notice", "community",
    "channel", "privacy",
})
COMMUNITY_REACTION_EMOJIS = (
    "👍", "❤️", "🔥", "😂", "👏", "😮", "😢", "😡",
    "🤮", "💩", "🎉", "🤔", "👀", "🙏", "💯", "🚀",
)


def normalize_channel_reaction_emojis(value, fallback=None):
    source = value if isinstance(value, list) else fallback
    if not isinstance(source, list):
        source = list(COMMUNITY_REACTION_EMOJIS)
    clean = []
    for emoji in source:
        emoji = str(emoji or "").strip()
        if emoji in COMMUNITY_REACTION_EMOJIS and emoji not in clean:
            clean.append(emoji)
    return clean or list(COMMUNITY_REACTION_EMOJIS)

CHANNEL_AUTO_DELETE_DAYS = {0, 1, 2, 3, 4, 5, 6, 7, 14, 30, 90, 180, 365}


def normalize_channel_auto_delete_days(value, fallback=0):
    try:
        days = int(value)
    except (TypeError, ValueError):
        days = int(fallback or 0)
    return days if days in CHANNEL_AUTO_DELETE_DAYS else 0


SUPABASE_COMMUNITY_BUCKET = os.environ.get("SUPABASE_COMMUNITY_BUCKET", "hodu-community").strip()
SUPABASE_APP_CACHE_TABLE = os.environ.get("SUPABASE_APP_CACHE_TABLE", "app_cache").strip()
COMMUNITY_ATTACHMENT_MAX_BYTES = int(os.environ.get("COMMUNITY_ATTACHMENT_MAX_BYTES", str(5 * 1024 * 1024)) or str(5 * 1024 * 1024))
COMMUNITY_ATTACHMENT_MAX_COUNT = 3
CHANNEL_ATTACHMENT_MAX_COUNT = 10
COMMUNITY_ATTACHMENT_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}
PROFILE_PHOTO_MAX_BYTES = int(os.environ.get("PROFILE_PHOTO_MAX_BYTES", str(2 * 1024 * 1024)) or str(2 * 1024 * 1024))
PROFILE_PHOTO_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
COMMUNITY_STORAGE_BUCKET_READY = False
EMAIL_VERIFICATION_CODES = {}
SIGNUP_LOCK = threading.Lock()
USER_SETTINGS_SAVE_LOCK = threading.Lock()


def serialize_user_settings_save(handler):
    def wrapped(*args, **kwargs):
        with USER_SETTINGS_SAVE_LOCK:
            return handler(*args, **kwargs)
    wrapped.__name__ = handler.__name__
    return wrapped
EMAIL_VERIFICATION_TTL_SECONDS = 180

ETH_MARKET_FILE = os.path.join(BASE_DIR, "eth_market_data.json")
ETH_NEWS_FILE = os.path.join(BASE_DIR, "eth_tokenpost_news.json")
HYPERLIQUID_ASSET_META_FILE = os.path.join(BASE_DIR, "hyperliquid_asset_meta.json")
KOREA_EXPORT_DASHBOARD_FILE = os.environ.get("KOREA_EXPORT_DASHBOARD_FILE", os.path.join(BASE_DIR, "korea_export_dashboard.json"))
KOREA_EXPORT_STOCK_MAPPING_FILE = os.environ.get("KOREA_EXPORT_STOCK_MAPPING_FILE", os.path.join(BASE_DIR, "korea_export_stock_mapping.json"))
HYPERLIQUID_ICON_DIR = os.path.join(BASE_DIR, "icons")
MARKET_DATA_CACHE_SECONDS = int(os.environ.get("MARKET_DATA_CACHE_SECONDS", "55") or "55")
ETH_MARKET_INTERVAL = 300
ETH_NEWS_INTERVAL = 3600
TOKENPOST_URL = "https://www.tokenpost.kr/news/blockchain/"
TOKENPOST_BASE = "https://www.tokenpost.kr"
UPBIT_TICKER_API = "https://api.upbit.com/v1/ticker?markets=KRW-ETH"
UPBIT_STAKING_PUBLIC_API = "https://uss.upbit.com/api/v2/staking/public"
NAVER_FINANCE_URL = "https://finance.naver.com/"
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "").strip()
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
HYPERLIQUID_INFO_URL = os.environ.get("HYPERLIQUID_INFO_URL", "https://api.hyperliquid.xyz/info").strip()
HYPERLIQUID_DEXES = [item.strip() for item in os.environ.get("HYPERLIQUID_DEXES", ",xyz").split(",")]
HYPERLIQUID_ICON_BASE_URL = "https://app.hyperliquid.xyz/coins"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
HYPERDASH_FLOWS_URL = os.environ.get("HYPERDASH_FLOWS_URL", "https://t.me/s/hyperdashflows").strip()
ETH_CRAWLER_SESSION = requests.Session()
ETH_CRAWLER_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome Safari",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
})
ETH_MARKET_RUNNING = False
ETH_NEWS_RUNNING = False
ETH_SCHEDULER_STARTED = False


def get_cached_value(key, ttl_seconds):
    cached = API_CACHE.get(key)
    if not cached:
        return None
    age = (datetime.now(timezone.utc) - cached["created_at"]).total_seconds()
    if age > ttl_seconds:
        return None
    return cached["value"]


def get_stale_cached_value(key, max_age_seconds=3600):
    cached = API_CACHE.get(key)
    if not cached:
        return None
    age = (datetime.now(timezone.utc) - cached["created_at"]).total_seconds()
    if age > max_age_seconds:
        API_CACHE.pop(key, None)
        return None
    value = cached.get("value")
    if isinstance(value, dict):
        stale_value = dict(value)
        stale_value["stale"] = True
        stale_value["refreshing"] = True
        return stale_value
    return value


BACKGROUND_REFRESHING = set()


def refresh_cache_in_background(key, worker):
    if key in BACKGROUND_REFRESHING:
        return
    BACKGROUND_REFRESHING.add(key)

    def run():
        try:
            worker()
        except Exception as exc:
            print(f"Background refresh failed({key}): {exc}", flush=True)
        finally:
            BACKGROUND_REFRESHING.discard(key)

    start_thread(run)


def set_cached_value(key, value):
    API_CACHE[key] = {
        "created_at": datetime.now(timezone.utc),
        "value": value,
    }
    return value

AAII_FALLBACK = {
    "ok": True,
    "source": "AAII",
    "date": "6/10/2026",
    "bullish": 30.4,
    "neutral": 22.0,
    "bearish": 47.7,
    "bull_avg": 37.5,
    "neut_avg": 31.5,
    "bear_avg": 31.0,
    "bull_8w": 33.5,
    "delta": {"bullish": -5.9, "neutral": -4.7, "bearish": 10.7},
    "stale": True,
    "warning": "AAII 원본 페이지가 봇 차단을 반환해 마지막 정상 수집값을 표시합니다.",
}


@app.after_request
def add_cache_headers(response):
    path = request.path if has_request_context() else ""

    # API 응답은 최신 데이터가 중요하므로 브라우저 캐시를 막는다.
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "-1"
        return response

    # 이미지/아이콘류는 새로고침 때마다 다시 받을 필요가 없다.
    if path.startswith("/domestic-icons/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
        return response

    if path.startswith("/icons/"):
        response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "-1"
        return response

    if path.endswith((".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico")):
        response.headers["Cache-Control"] = "public, max-age=86400"
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
        return response

    # SPA HTML은 너무 길게 캐시하지 않고 짧게만 허용한다.
    response.headers["Cache-Control"] = "public, max-age=60, must-revalidate"
    response.headers.pop("Pragma", None)
    response.headers.pop("Expires", None)
    return response


@app.route("/")
def index():
    return render_template("company_analysis.html")


@app.route("/Dashboard")
@app.route("/dashboard")
@app.route("/Market")
@app.route("/market")
@app.route("/Market-Status")
@app.route("/market-status")
@app.route("/Company")
@app.route("/company")
@app.route("/Insight")
@app.route("/insight")
@app.route("/Hodu-Insight")
@app.route("/hodu-insight")
@app.route("/Company-Beta")
@app.route("/company-beta")
@app.route("/Export")
@app.route("/export")
@app.route("/Korea-Export")
@app.route("/korea-export")
@app.route("/Trade-Export")
@app.route("/trade-export")
@app.route("/Watchlist")
@app.route("/watchlist")
@app.route("/Polymarket")
@app.route("/polymarket")
@app.route("/Prediction-Market")
@app.route("/prediction-market")
@app.route("/ETHtracker")
@app.route("/ethtracker")
@app.route("/Ethereum-Tracker")
@app.route("/ethereum-tracker")
@app.route("/Notice")
@app.route("/notice")
@app.route("/Community")
@app.route("/community")
@app.route("/auth/join")
@app.route("/Privacy")
@app.route("/privacy")
def tab_index():
    return render_template("company_analysis.html")


@app.route("/<path:client_path>")
def client_side_route(client_path):
    if client_path.startswith("api/"):
        return jsonify({"error": "not found"}), 404
    if "." in client_path:
        return jsonify({"error": "not found"}), 404
    return render_template("company_analysis.html")


@app.route("/favicon.svg")
def favicon():
    return send_from_directory(app.template_folder, "favicon.svg", mimetype="image/svg+xml")


@app.route("/og-image.svg")
def og_image():
    return send_from_directory(app.template_folder, "og-image.svg", mimetype="image/svg+xml")


@app.route("/og-image.png")
def og_image_png():
    return send_from_directory(app.template_folder, "og-image.png", mimetype="image/png")



@app.route("/icons/<path:filename>")
def hyperliquid_icon(filename):
    response = send_from_directory(HYPERLIQUID_ICON_DIR, filename, mimetype="image/svg+xml", max_age=0)
    response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
    return response


@app.route("/api/hyperliquid-icon/<path:symbol>")
def hyperliquid_generated_icon(symbol):
    label = re.sub(r"[^A-Za-z0-9]", "", str(symbol or "").split(":")[-1]).upper()[:6] or "HL"
    font_size = 21 if len(label) <= 4 else 16
    safe_label = html_lib.escape(label)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 56 56" role="img" aria-label="{safe_label}">
<rect width="56" height="56" rx="28" fill="#111827"/>
<rect x="1" y="1" width="54" height="54" rx="27" fill="none" stroke="#334155" stroke-width="2"/>
<text x="28" y="29" dominant-baseline="middle" text-anchor="middle" fill="#e5e7eb" font-family="Inter,Arial,sans-serif" font-size="{font_size}" font-weight="800">{safe_label}</text>
</svg>"""
    response = app.response_class(svg, mimetype="image/svg+xml")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@app.route("/domestic-icons/<path:filename>")
def domestic_icon(filename):
    if not re.fullmatch(r"[A-Za-z0-9]{6}\.png", filename or ""):
        return jsonify({"ok": False, "error": "invalid icon"}), 400
    icon_name = f"{filename[:6].upper()}.png"
    return send_from_directory(DOMESTIC_ICON_DIR, icon_name, mimetype="image/png", max_age=86400)

@app.route("/donation_qr.png")
def donation_qr():
    return send_from_directory(app.template_folder, "donation_qr.png", mimetype="image/png")


def read_template_json(filename, fallback):
    path = os.path.join(app.template_folder, filename)
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as exc:
        print(f"JSON load failed({filename}): {exc}", flush=True)
        return fallback


def clean_text(value):
    return re.sub(r"\s+", " ", html_lib.unescape(value or "")).strip()


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
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, path)


def supabase_enabled():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def supabase_headers(prefer=None):
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def supabase_cache_upsert(key, payload):
    if not supabase_enabled():
        return False
    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_APP_CACHE_TABLE}",
            headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "key"},
            json={
                "key": key,
                "payload": payload,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=20,
        )
        if response.status_code >= 400:
            print(f"Supabase cache upsert failed({key}): {response.status_code} {response.text[:500]}", flush=True)
            return False
        return True
    except Exception as exc:
        print(f"Supabase cache upsert failed({key}): {exc}", flush=True)
        return False


def supabase_cache_get(key, fallback=None):
    if not supabase_enabled():
        return fallback
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_APP_CACHE_TABLE}",
            headers=supabase_headers(),
            params={
                "key": f"eq.{key}",
                "select": "payload,updated_at",
                "limit": "1",
            },
            timeout=20,
        )
        if response.status_code >= 400:
            print(f"Supabase cache get failed({key}): {response.status_code} {response.text[:500]}", flush=True)
            return fallback
        rows = response.json()
        if not rows:
            return fallback
        payload = rows[0].get("payload")
        if isinstance(payload, dict):
            payload.setdefault("_supabaseUpdatedAt", rows[0].get("updated_at"))
            return payload
        return fallback
    except Exception as exc:
        print(f"Supabase cache get failed({key}): {exc}", flush=True)
        return fallback


def supabase_cache_list(prefix):
    if not supabase_enabled():
        return {}

    # Supabase/PostgREST may cap a single REST response (often around 1,000 rows).
    # Toss cache currently stores thousands of rows (candles, price limits, price chunks,
    # stock-info chunks, meta). If we only read the first page, company beta may see
    # candles but miss kr_prices_* and show “수집 대상 없음”. Read with Range pagination.
    result = {}
    page_size = max(100, min(1000, int(os.environ.get("SUPABASE_CACHE_PAGE_SIZE", "1000") or "1000")))
    offset = 0

    try:
        while True:
            headers = supabase_headers()
            headers["Range-Unit"] = "items"
            headers["Range"] = f"{offset}-{offset + page_size - 1}"

            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_APP_CACHE_TABLE}",
                headers=headers,
                params={
                    "key": f"like.{prefix}%",
                    "select": "key,payload,updated_at",
                    "order": "key.asc",
                },
                timeout=45,
            )
            if response.status_code >= 400:
                print(f"Supabase cache list failed({prefix}): {response.status_code} {response.text[:500]}", flush=True)
                return result

            rows = response.json()
            if not isinstance(rows, list) or not rows:
                break

            for row in rows:
                key = str(row.get("key") or "")
                payload = row.get("payload")
                if isinstance(payload, dict):
                    payload.setdefault("_supabaseUpdatedAt", row.get("updated_at"))
                    result[key] = payload

            if len(rows) < page_size:
                break
            offset += page_size

        return result
    except Exception as exc:
        print(f"Supabase cache list failed({prefix}): {exc}", flush=True)
        return result


TOSS_DETAIL_ITEM_PATTERN = re.compile(r"^kr_(?:candles_(?:1d|1m)|price_limit)_([A-Z0-9]{6})$")


def is_toss_detail_item_name(name):
    return bool(TOSS_DETAIL_ITEM_PATTERN.match(str(name or "")))


def toss_detail_item_path(name):
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(name or ""))
    return os.path.join(TOSS_DETAIL_CACHE_DIR, f"{safe_name}.json")


def split_toss_detail_items(items):
    if not isinstance(items, dict):
        return {}, {}
    main_items = {}
    detail_items = {}
    for name, item in items.items():
        if is_toss_detail_item_name(name):
            detail_items[name] = item
        else:
            main_items[name] = item
    return main_items, detail_items


def write_toss_detail_items(detail_items):
    if not detail_items:
        return 0
    os.makedirs(TOSS_DETAIL_CACHE_DIR, exist_ok=True)
    written = 0
    for name, item in detail_items.items():
        write_json_file(toss_detail_item_path(name), item)
        written += 1
    return written


def read_toss_detail_item(name):
    return read_json_file(toss_detail_item_path(name), None)

def hydrate_toss_cache_items(cache):
    """TOSS_CACHE_FILE의 요약 itemNames를 실제 detail cache 내용으로 확장한다."""
    if not isinstance(cache, dict):
        return {}

    hydrated = dict(cache)
    items = dict(hydrated.get("items") or {})

    item_names = set()
    if isinstance(hydrated.get("itemNames"), list):
        item_names.update(str(name) for name in hydrated.get("itemNames") if name)

    if isinstance(items, dict):
        item_names.update(str(name) for name in items.keys() if name)

    for item_name in sorted(item_names):
        if item_name in items:
            continue
        detail_item = read_toss_detail_item(item_name)
        if detail_item is not None:
            items[item_name] = detail_item

    hydrated["items"] = items
    return hydrated


def load_toss_cache():
    """
    Toss cache를 Supabase app_cache에서 우선 로드하고,
    Supabase가 비어 있거나 실패하면 기존 Render 로컬 파일을 fallback으로 사용한다.

    주의: app_cache에는 kr_candles_1d_* / kr_price_limit_* 같은 종목별 상세 row가
    수천 개 저장될 수 있다. 기업 분석 베타의 기본 검색에는 kr_prices_* / kr_stocks_* /
    kr_universe만 있으면 되므로, 새로고침·검색마다 candles 전체를 읽지 않는다.
    필요한 종목별 price_limit는 /api/toss-company에서 해당 ticker 1건만 별도 조회한다.
    """
    cached = get_cached_value("supabase_toss_cache", 30)
    if isinstance(cached, dict):
        return cached

    rows = {}
    meta = supabase_cache_get("toss:meta", None)
    if isinstance(meta, dict):
        rows["toss:meta"] = meta

    universe = supabase_cache_get("toss:kr_universe", None)
    if isinstance(universe, dict):
        rows["toss:kr_universe"] = universe

    # 기업 분석 베타 검색에 필요한 chunk만 읽는다.
    # toss: 전체를 읽으면 kr_candles_1d_* 수천 건 때문에 느려지고 egress가 커진다.
    rows.update(supabase_cache_list("toss:kr_prices_"))
    rows.update(supabase_cache_list("toss:kr_stocks_"))

    if rows:
        meta = rows.get("toss:meta")
        items = {}
        for key, payload in rows.items():
            if key == "toss:meta":
                continue
            item_name = key.removeprefix("toss:")
            items[item_name] = payload

        cache = dict(meta) if isinstance(meta, dict) else {}
        cache["items"] = items
        cache["itemNames"] = sorted(items.keys())
        cache["itemCount"] = len(items)
        cache["loadedFrom"] = "supabase_main_only"
        set_cached_value("supabase_toss_cache", cache)
        return cache

    cache = hydrate_toss_cache_items(read_json_file(TOSS_CACHE_FILE, {}))
    if isinstance(cache, dict):
        cache["loadedFrom"] = "local_file"
    return cache


def save_toss_cache_to_supabase(cache):
    """
    Render가 OCI collector payload를 ingest하면, compact items를 Supabase에 영구 저장한다.
    Render 무료 인스턴스 재시작으로 로컬 파일이 날아가도 Supabase에서 복원 가능하다.
    """
    if not isinstance(cache, dict):
        return False

    items = cache.get("items") if isinstance(cache.get("items"), dict) else {}
    meta = {key: value for key, value in cache.items() if key != "items"}
    meta["itemNames"] = sorted(items.keys())
    meta["itemCount"] = len(items)

    ok = supabase_cache_upsert("toss:meta", meta)
    for item_name, item_payload in items.items():
        ok = supabase_cache_upsert(f"toss:{item_name}", item_payload) and ok

    # 방금 저장한 cache를 프로세스 메모리에도 짧게 유지해서 Supabase 왕복을 줄인다.
    cached = dict(meta)
    cached["items"] = items
    cached["loadedFrom"] = "supabase"
    set_cached_value("supabase_toss_cache", cached)
    return ok


def merge_toss_cache(existing, incoming):
    if not isinstance(existing, dict):
        existing = {}
    if not isinstance(incoming, dict):
        return existing

    merged = dict(existing)
    existing_items = existing.get("items") if isinstance(existing.get("items"), dict) else {}
    incoming_items = incoming.get("items") if isinstance(incoming.get("items"), dict) else {}
    compact_existing_items, _ = split_toss_detail_items(existing_items)
    compact_incoming_items, detail_items = split_toss_detail_items(incoming_items)
    write_toss_detail_items(detail_items)
    merged.update({key: value for key, value in incoming.items() if key not in {"items", "errors"}})
    merged["items"] = {**compact_existing_items, **compact_incoming_items}
    if isinstance(incoming.get("errors"), list):
        merged["errors"] = incoming["errors"]
    merged["detailItemCount"] = len(detail_items)
    merged["detailCacheDir"] = TOSS_DETAIL_CACHE_DIR
    return merged


def is_valid_ingest_request():
    if not INGEST_SECRET:
        return False
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        if secrets.compare_digest(token, INGEST_SECRET):
            return True
    header_secret = request.headers.get("X-Ingest-Secret", "").strip()
    return bool(header_secret) and secrets.compare_digest(header_secret, INGEST_SECRET)


def file_age_seconds(path):
    if not os.path.exists(path):
        return float("inf")
    return max(0, time.time() - os.path.getmtime(path))


def load_app_cache_payload(cache_key, local_path=None, fallback=None):
    """
    Supabase app_cache를 우선 읽고, 없으면 로컬 JSON 파일을 읽는다.
    Render 무료 인스턴스 재시작으로 로컬 파일이 없어져도 마지막 정상값을 복원하기 위한 공통 helper.
    """
    cached = supabase_cache_get(cache_key, None)
    if isinstance(cached, dict):
        cached["loadedFrom"] = "supabase"
        return cached

    if local_path:
        local_payload = read_json_file(local_path, None)
        if isinstance(local_payload, dict):
            local_payload["loadedFrom"] = "local_file"
            return local_payload

    return fallback.copy() if isinstance(fallback, dict) else fallback


def save_app_cache_payload(cache_key, payload, local_path=None):
    """
    로컬 JSON fallback을 유지하면서 Supabase app_cache에도 저장한다.
    """
    if isinstance(payload, dict):
        payload = dict(payload)
        payload.pop("loadedFrom", None)
        payload.pop("_supabaseUpdatedAt", None)

    if local_path:
        try:
            write_json_file(local_path, payload)
        except Exception as exc:
            print(f"Local cache save failed({local_path}): {exc}", flush=True)

    return supabase_cache_upsert(cache_key, payload)



DOMESTIC_ETF_FILE = os.environ.get(
    "DOMESTIC_ETF_FILE",
    "/var/data/domestic_etf_dashboard.json"
    if os.path.isdir("/var/data")
    else os.path.join(BASE_DIR, "domestic_etf_dashboard.json"),
)
DOMESTIC_ETF_CACHE_KEY = "domestic-etf:dashboard:v1"
DOMESTIC_ETF_LAST_READY_CACHE_KEY = "domestic-etf:dashboard:last-ready:v1"
_domestic_etf_file_root, _domestic_etf_file_ext = os.path.splitext(DOMESTIC_ETF_FILE)
DOMESTIC_ETF_LAST_READY_FILE = (
    f"{_domestic_etf_file_root}.last-ready{_domestic_etf_file_ext or '.json'}"
)
ETF_HOLDINGS_UNIVERSE_SIZE = 0  # Collect every listed domestic ETF.
ETF_TRACKING_UNIVERSE_SIZE = max(5, int(os.environ.get("ETF_TRACKING_UNIVERSE_SIZE", "20") or "20"))
ETF_MIN_TRADING_VALUE = max(0, int(os.environ.get("ETF_MIN_TRADING_VALUE", "100000000") or "100000000"))
ETF_KRX_CONNECT_TIMEOUT = max(
    3.0, float(os.environ.get("ETF_KRX_CONNECT_TIMEOUT", "8") or "8")
)
ETF_KRX_READ_TIMEOUT = max(
    15.0, float(os.environ.get("ETF_KRX_READ_TIMEOUT", "30") or "30")
)
ETF_HOLDINGS_REQUEST_DELAY_SECONDS = max(
    0.1, float(os.environ.get("ETF_HOLDINGS_REQUEST_DELAY_SECONDS", "0.3") or "0.3")
)
ETF_HOLDINGS_BATCH_SIZE = max(
    10, min(250, int(os.environ.get("ETF_HOLDINGS_BATCH_SIZE", "100") or "100"))
)
ETF_HOLDINGS_FALLBACK_TIMEOUT = max(
    5.0, float(os.environ.get("ETF_HOLDINGS_FALLBACK_TIMEOUT", "12") or "12")
)
DOMESTIC_ETF_REFRESH_LOCK = threading.Lock()
DOMESTIC_ETF_REFRESHING = False
DOMESTIC_ETF_SCHEDULER_STARTED = False
DOMESTIC_ETF_LAST_ERROR = ""
DOMESTIC_ETF_OPEN_API_LAST_ERROR = ""
DOMESTIC_ETF_AUTH_STATUS = "not_checked"
DOMESTIC_ETF_AUTH_CHECKED_AT = None


def _empty_domestic_etf_dashboard():
    return {
        "status": "empty",
        "asOf": None,
        "generatedAt": None,
        "rankings": {},
        "holdingsByEtf": {},
        "reverseHoldings": {},
        "changes": {"added": [], "removed": []},
    }


def _domestic_etf_payload_displayable(payload):
    if not isinstance(payload, dict) or payload.get("status") != "ready":
        return False
    rankings = payload.get("rankings") or {}
    return bool(
        rankings
        or payload.get("turnover")
        or payload.get("etfDirectory")
        or payload.get("holdingsByEtf")
    )


def _merge_domestic_etf_holdings(active, stable):
    active_holdings = dict((active or {}).get("holdingsByEtf") or {})
    stable_holdings = dict((stable or {}).get("holdingsByEtf") or {})
    if not stable_holdings:
        return active

    merged = dict(active)
    merged_holdings = dict(stable_holdings)
    merged_holdings.update(active_holdings)
    merged["holdingsByEtf"] = merged_holdings
    merged["servedPreviousHoldings"] = True
    merged["previousHoldingsAsOf"] = (stable or {}).get("asOf")

    merged_reverse = {}
    for source in (
        (stable or {}).get("reverseHoldings") or {},
        (active or {}).get("reverseHoldings") or {},
    ):
        for stock_ticker, rows in source.items():
            by_etf = {
                str(item.get("ticker") or ""): dict(item)
                for item in (merged_reverse.get(stock_ticker) or [])
                if item.get("ticker")
            }
            for item in rows or []:
                etf_ticker = str(item.get("ticker") or "")
                if etf_ticker:
                    by_etf[etf_ticker] = dict(item)
            merged_reverse[stock_ticker] = sorted(
                by_etf.values(),
                key=lambda item: float(item.get("weight") or 0),
                reverse=True,
            )[:5]
    merged["reverseHoldings"] = merged_reverse

    concentration = []
    for ticker, item in merged_holdings.items():
        concentration.append({
            "ticker": ticker,
            "name": item.get("name") or ticker,
            "concentration": round(sum(
                float(row.get("weight") or 0)
                for row in (item.get("holdings") or [])[:5]
            ), 4),
        })
    concentration.sort(
        key=lambda item: float(item.get("concentration") or 0), reverse=True
    )
    merged["concentration"] = concentration[:5]
    scope = dict(merged.get("scope") or {})
    scope["holdingsUniverseCount"] = len(merged_holdings)
    merged["scope"] = scope
    return merged


def load_domestic_etf_dashboard():
    active = load_app_cache_payload(
        DOMESTIC_ETF_CACHE_KEY, DOMESTIC_ETF_FILE, None
    )
    active_displayable = _domestic_etf_payload_displayable(active)
    needs_stable_holdings = active_displayable and (
        str((active or {}).get("enrichmentStatus") or "") in {
            "collecting", "unavailable"
        }
        or not (active or {}).get("holdingsByEtf")
    )

    stable = None
    if not active_displayable or needs_stable_holdings:
        stable = load_app_cache_payload(
            DOMESTIC_ETF_LAST_READY_CACHE_KEY,
            DOMESTIC_ETF_LAST_READY_FILE,
            None,
        )

    if active_displayable:
        if needs_stable_holdings and _domestic_etf_payload_displayable(stable):
            return _merge_domestic_etf_holdings(active, stable)
        return active

    if _domestic_etf_payload_displayable(stable):
        stable = dict(stable)
        stable["servedFromLastGood"] = True
        stable["activeCacheStatus"] = (
            active.get("status") if isinstance(active, dict) else "unavailable"
        )
        return stable

    return active if isinstance(active, dict) else _empty_domestic_etf_dashboard()


def save_domestic_etf_dashboard(payload, promote_last_ready=False):
    saved = save_app_cache_payload(
        DOMESTIC_ETF_CACHE_KEY, payload, DOMESTIC_ETF_FILE
    )
    if promote_last_ready and _domestic_etf_payload_displayable(payload):
        stable = dict(payload)
        stable["lastReadySavedAt"] = datetime.now(KST).isoformat()
        stable.pop("servedFromLastGood", None)
        stable.pop("activeCacheStatus", None)
        save_app_cache_payload(
            DOMESTIC_ETF_LAST_READY_CACHE_KEY,
            stable,
            DOMESTIC_ETF_LAST_READY_FILE,
        )
    return saved


def _etf_number(value, integer=False):
    try:
        if value is None or pd.isna(value):
            return None
        number = float(value)
        return int(round(number)) if integer else round(number, 4)
    except (TypeError, ValueError):
        return None


def _etf_column(frame, *names):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype="float64")
    for name in names:
        if name in frame.columns:
            return frame[name]
    return pd.Series(index=frame.index, dtype="float64")


def _etf_normalize_frame(frame):
    result = frame.copy()
    result.index = result.index.map(lambda value: str(value).zfill(6))
    return result


def _etf_latest_sessions(pykrx_stock, count=2):
    found = []
    cursor = datetime.now(KST).date()
    for offset in range(16):
        day = cursor - timedelta(days=offset)
        day_text = day.strftime("%Y%m%d")
        try:
            frame = pykrx_stock.get_etf_ohlcv_by_ticker(day_text)
        except Exception:
            continue
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            found.append((day_text, _etf_normalize_frame(frame)))
            if len(found) >= count:
                return found
    raise RuntimeError("No recent KRX ETF trading session was found.")


def _etf_name(pykrx_stock, ticker, cache):
    ticker = str(ticker).zfill(6)
    if ticker not in cache:
        try:
            cache[ticker] = str(pykrx_stock.get_etf_ticker_name(ticker) or ticker)
        except Exception:
            cache[ticker] = ticker
    return cache[ticker]


def _domestic_stock_name_map():
    names = {}
    try:
        cache = load_toss_cache()
        for _, row in iter_toss_result_rows(cache):
            ticker = normalize_toss_symbol(row.get("symbol"))
            name = str(first_present(
                row, ["name", "stockName", "companyName", "displayName"]
            ) or "").strip()
            if re.fullmatch(r"\d{6}", ticker or "") and name and name != ticker:
                names[ticker] = name
    except Exception:
        pass
    return names


def _etf_component_name(pykrx_stock, ticker, current_name, cache):
    ticker = str(ticker or "").strip()
    current_name = str(current_name or "").strip()
    mapped_name = str(cache.get(ticker) or "").strip()
    if mapped_name and mapped_name != ticker:
        return mapped_name
    if current_name and current_name != ticker:
        return current_name
    return ""


def _etf_rank_rows(frame, rate_column, name_cache, pykrx_stock, limit=5, ascending=False):
    if not isinstance(frame, pd.DataFrame) or frame.empty or rate_column not in frame:
        return []
    working = _etf_normalize_frame(frame)
    value_column = next((name for name in ("\uac70\ub798\ub300\uae08", "\ub204\uc801\uac70\ub798\ub300\uae08") if name in working), None)
    if value_column:
        liquid = pd.to_numeric(working[value_column], errors="coerce").fillna(0)
        working = working[liquid >= ETF_MIN_TRADING_VALUE]
    numeric = pd.to_numeric(working[rate_column], errors="coerce")
    working = working.assign(_rank_value=numeric).dropna(subset=["_rank_value"])
    working = working.sort_values("_rank_value", ascending=ascending).head(limit)
    rows = []
    for ticker, row in working.iterrows():
        rows.append({
            "ticker": ticker,
            "name": _etf_name(pykrx_stock, ticker, name_cache),
            "rate": _etf_number(row.get("_rank_value")),
            "close": _etf_number(row.get("\uc885\uac00") or row.get("\uc885\ub8cc\uc9c0\uc218"), integer=True),
            "tradingValue": _etf_number(row.get("\uac70\ub798\ub300\uae08") or row.get("\ub204\uc801\uac70\ub798\ub300\uae08"), integer=True),
        })
    return rows


def _etf_metric_rows(series, current_frame, pykrx_stock, name_cache, limit=5, ascending=False, key="value"):
    numeric = pd.to_numeric(series, errors="coerce").dropna().sort_values(ascending=ascending).head(limit)
    rows = []
    for ticker, value in numeric.items():
        ticker = str(ticker).zfill(6)
        current_row = current_frame.loc[ticker] if ticker in current_frame.index else {}
        rows.append({
            "ticker": ticker,
            "name": _etf_name(pykrx_stock, ticker, name_cache),
            key: _etf_number(value),
            "close": _etf_number(current_row.get("\uc885\uac00") if hasattr(current_row, "get") else None, integer=True),
        })
    return rows


def _etf_component_ticker(value):
    ticker = str(value or "").strip().upper()
    if re.fullmatch(r"A\d{5,6}", ticker):
        ticker = ticker[1:]
    if ticker.isdigit():
        return ticker.zfill(6)
    return ticker


def _etf_portfolio_rows(frame, limit=None):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    frame = frame.copy()
    frame.index = frame.index.map(_etf_component_ticker)
    weight = pd.to_numeric(_etf_column(frame, "\ube44\uc911"), errors="coerce").fillna(0)
    amount = pd.to_numeric(_etf_column(frame, "\uae08\uc561"), errors="coerce").fillna(0)
    contracts = pd.to_numeric(_etf_column(frame, "\uacc4\uc57d\uc218"), errors="coerce").fillna(0)
    names = _etf_column(frame, "\uad6c\uc131\uc885\ubaa9\uba85", "\uc885\ubaa9\uba85").fillna("")
    rows = []
    ordered = frame.assign(
        _weight=weight, _amount=amount, _contracts=contracts, _name=names
    ).sort_values("_weight", ascending=False)
    if limit:
        ordered = ordered.head(limit)
    for ticker, row in ordered.iterrows():
        rows.append({
            "ticker": ticker,
            "name": str(row.get("_name") or ticker).strip(),
            "weight": _etf_number(row.get("_weight")),
            "amount": _etf_number(row.get("_amount"), integer=True),
            "contracts": _etf_number(row.get("_contracts"), integer=True),
        })
    return rows



def _naver_etf_portfolio_rows(ticker):
    """Read previous-session top holdings without a KRX login session."""
    response = requests.get(
        "https://finance.naver.com/item/main.naver",
        params={"code": str(ticker).zfill(6)},
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; BIKResearch/1.0)",
            "Accept-Language": "ko-KR,ko;q=0.9",
        },
        timeout=(4, ETF_HOLDINGS_FALLBACK_TIMEOUT),
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    heading = soup.find(
        lambda tag: tag.name in {"h3", "h4", "span"}
        and "ETF \uc8fc\uc694 \uad6c\uc131\uc790\uc0b0" in tag.get_text(" ", strip=True)
    )
    table = heading.find_next("table") if heading else None
    if table is None:
        return []

    rows = []
    for table_row in table.select("tr"):
        cells = table_row.find_all("td", recursive=False)
        name_cell = table_row.select_one("td.ctg")
        if len(cells) < 3 or name_cell is None:
            continue
        name = name_cell.get_text(" ", strip=True)
        link = name_cell.find("a", href=True)
        match = re.search(r"[?&]code=(\d{6})", link.get("href", "")) if link else None
        component_ticker = match.group(1) if match else name
        weight_match = re.search(r"-?[\d,.]+", cells[2].get_text(" ", strip=True))
        if not name or not weight_match:
            continue
        contracts = _krx_api_number(cells[1].get_text(" ", strip=True), True)
        price = _krx_api_number(cells[3].get_text(" ", strip=True), True) if len(cells) > 3 else 0
        rows.append({
            "ticker": component_ticker,
            "name": name,
            "weight": round(float(weight_match.group(0).replace(",", "")), 4),
            "amount": int(contracts * price) if contracts and price else 0,
            "contracts": contracts,
        })
    return sorted(rows, key=lambda row: float(row.get("weight") or 0), reverse=True)[:10]


def _rebuild_etf_holding_indexes(holdings_by_etf):
    reverse = {}
    concentration = []
    for ticker, item in holdings_by_etf.items():
        rows = list((item or {}).get("holdings") or [])
        concentration.append({
            "ticker": ticker,
            "name": (item or {}).get("name") or ticker,
            "concentration": round(sum(float(row.get("weight") or 0) for row in rows[:5]), 4),
        })
        for row in rows:
            stock_ticker = str(row.get("ticker") or "").strip()
            if re.fullmatch(r"\d{6}", stock_ticker):
                reverse.setdefault(stock_ticker, []).append({
                    "ticker": ticker,
                    "name": (item or {}).get("name") or ticker,
                    "weight": float(row.get("weight") or 0),
                })
    for stock_ticker, rows in reverse.items():
        reverse[stock_ticker] = sorted(
            rows, key=lambda row: float(row.get("weight") or 0), reverse=True
        )[:5]
    concentration.sort(key=lambda row: float(row.get("concentration") or 0), reverse=True)
    return reverse, concentration[:5]


def _enrich_domestic_etf_holdings(payload):
    """Collect one resumable batch and save a checkpoint after every ten successes."""
    payload = dict(payload or {})
    directory = list(payload.get("etfDirectory") or [])
    universe = [str(row.get("ticker") or "").zfill(6) for row in directory if row.get("ticker")]
    names = {
        str(row.get("ticker") or "").zfill(6): str(row.get("name") or row.get("ticker") or "")
        for row in directory if row.get("ticker")
    }
    target = str(payload.get("asOf") or "")[:10]
    holdings = dict(payload.get("holdingsByEtf") or {})
    changes = payload.get("changes") or {}
    added = list(changes.get("added") or [])
    removed = list(changes.get("removed") or [])
    total = len(universe)
    cursor = int(payload.get("enrichmentCursor") or 0) % max(total, 1)
    ordered = universe[cursor:] + universe[:cursor]
    pending = [
        ticker for ticker in ordered
        if str((holdings.get(ticker) or {}).get("asOf") or "") != target
    ]
    batch = pending[:ETF_HOLDINGS_BATCH_SIZE]
    failures = []
    successes = 0
    payload = _save_domestic_etf_enrichment_checkpoint(
        payload, "holdings", holdings, payload.get("reverseHoldings") or {},
        added, removed,
        progress={"processed": total - len(pending), "total": total, "batchSize": len(batch)},
    )

    for ticker in batch:
        cursor = (universe.index(ticker) + 1) % max(total, 1)
        old_item = dict(holdings.get(ticker) or {})
        try:
            rows = _naver_etf_portfolio_rows(ticker)
            etf_name = names.get(ticker) or old_item.get("name") or ticker
            old_names = {
                str(row.get("ticker") or ""): row.get("name") or ""
                for row in old_item.get("holdings") or []
            }
            new_names = {
                str(row.get("ticker") or ""): row.get("name") or ""
                for row in rows
            }
            if old_names and str(old_item.get("asOf") or "") != target:
                for code in sorted(set(new_names) - set(old_names)):
                    added.append({"etfTicker": ticker, "etfName": etf_name, "stockTicker": code, "stockName": new_names[code]})
                for code in sorted(set(old_names) - set(new_names)):
                    removed.append({"etfTicker": ticker, "etfName": etf_name, "stockTicker": code, "stockName": old_names[code]})
            holdings[ticker] = {
                "ticker": ticker,
                "asOf": target,
                "name": etf_name,
                "holdings": rows,
                "holdingCount": len(rows),
                "namesResolved": True,
                "nameResolverVersion": 3,
                "provider": "Naver Finance",
                "collectionStatus": "ready" if rows else "no_data",
            }
            successes += 1
        except Exception as exc:
            failures.append(f"{ticker}: {exc}")
            print(f"ETF holdings fallback failed({ticker}): {exc}", flush=True)
            if len(failures) >= 5 and successes == 0:
                break

        if successes and successes % 10 == 0:
            reverse, concentration = _rebuild_etf_holding_indexes(holdings)
            payload.update({
                "enrichmentCursor": cursor,
                "holdingsByEtf": holdings,
                "reverseHoldings": reverse,
                "concentration": concentration,
                "changes": {"added": added[-50:], "removed": removed[-50:]},
                "enrichmentProgress": {
                    "processed": sum(1 for row in holdings.values() if str((row or {}).get("asOf") or "") == target),
                    "total": total,
                    "batchSize": len(batch),
                },
                "enrichmentUpdatedAt": datetime.now(KST).isoformat(),
            })
            save_domestic_etf_dashboard(payload)
        time.sleep(ETF_HOLDINGS_REQUEST_DELAY_SECONDS)

    current_count = sum(
        1 for row in holdings.values() if str((row or {}).get("asOf") or "") == target
    )
    reverse, concentration = _rebuild_etf_holding_indexes(holdings)
    complete = current_count >= total
    payload.update({
        "enrichmentStatus": "ready" if complete else "collecting",
        "enrichmentStage": "complete" if complete else "holdings",
        "enrichmentProgress": {"processed": current_count, "total": total, "batchSize": len(batch)},
        "enrichmentCursor": cursor,
        "enrichmentUpdatedAt": datetime.now(KST).isoformat(),
        "enrichmentError": (
            f"Holdings fallback failed for {len(failures)} ETFs; automatic retry queued."
            if failures else None
        ),
        "holdingsProvider": "Naver Finance (previous-session top 10)",
        "holdingsByEtf": holdings,
        "reverseHoldings": reverse,
        "concentration": concentration,
        "changes": {"added": added[-50:], "removed": removed[-50:]},
    })
    scope = dict(payload.get("scope") or {})
    scope["holdingsUniverseCount"] = len(holdings)
    scope["holdingsCurrentCount"] = current_count
    payload["scope"] = scope
    save_domestic_etf_dashboard(payload, promote_last_ready=True)
    return payload


def _etf_open_api_row(row):
    ticker = str(row.get("ISU_SRT_CD") or row.get("ISU_CD") or "").strip()
    close = _krx_api_number(row.get("TDD_CLSPRC"), True)
    nav = _krx_api_number(row.get("NAV") or row.get("TDD_NAV"))
    return {
        "date": str(row.get("BAS_DD") or "").strip(),
        "ticker": ticker,
        "name": str(row.get("ISU_NM") or ticker).strip(),
        "close": close,
        "nav": nav,
        "rate": _krx_api_number(row.get("FLUC_RT")),
        "volume": _krx_api_number(row.get("ACC_TRDVOL"), True),
        "tradingValue": _krx_api_number(row.get("ACC_TRDVAL"), True),
        "marketCap": _krx_api_number(row.get("MKTCAP"), True),
        "netAsset": _krx_api_number(row.get("INVSTASST_NETASST_TOTAMT"), True),
        "listedShares": _krx_api_number(row.get("LIST_SHRS"), True),
        "indexName": str(row.get("IDX_IND_NM") or "").strip(),
        "premium": round(((close / nav) - 1) * 100, 4) if close > 0 and nav > 0 else None,
    }


def _etf_open_api_session_on_or_before(target_date, lookback=10):
    for offset in range(lookback + 1):
        date_value = target_date - timedelta(days=offset)
        date_text = date_value.strftime("%Y%m%d")
        try:
            rows = _krx_open_api_rows("etp/etf_bydd_trd", date_text)
        except Exception as exc:
            print(f"KRX ETF Open API session skipped({date_text}): {exc}", flush=True)
            continue
        if rows:
            normalized = [_etf_open_api_row(row) for row in rows]
            has_trading = any(
                int(item.get("tradingValue") or 0) > 0
                and int(item.get("close") or 0) > 0
                for item in normalized
            )
            if not has_trading:
                continue
            actual_date = next(
                (str(item.get("date") or "") for item in normalized if item.get("date")),
                date_text,
            )
            return actual_date, normalized
    return None, []


def _etf_open_rank(items, key, limit=5, reverse=True, liquidity=True):
    rows = [
        item for item in items
        if item.get(key) is not None
        and (not liquidity or int(item.get("tradingValue") or 0) >= ETF_MIN_TRADING_VALUE)
    ]
    return [dict(item) for item in sorted(
        rows, key=lambda item: float(item.get(key) or 0), reverse=reverse
    )[:limit]]


def _etf_open_period_rank(current_rows, start_rows):
    start_map = {
        item["ticker"]: float(item.get("close") or 0)
        for item in start_rows if item.get("ticker")
    }
    period_rows = []
    for item in current_rows:
        start_close = start_map.get(item["ticker"], 0)
        current_close = float(item.get("close") or 0)
        if start_close <= 0 or current_close <= 0:
            continue
        row = dict(item)
        row["rate"] = round(((current_close / start_close) - 1) * 100, 4)
        period_rows.append(row)
    return {
        "gainers": _etf_open_rank(period_rows, "rate"),
        "losers": _etf_open_rank(period_rows, "rate", reverse=False),
    }


def collect_domestic_etf_open_api_snapshot():
    if not KRX_OPEN_API_AUTH_KEY:
        raise RuntimeError("KRX_OPEN_API_AUTH_KEY environment variable is required.")
    today = datetime.now(KST).date()
    as_of, current_rows = _etf_open_api_session_on_or_before(today, 14)
    if not as_of or not current_rows:
        raise RuntimeError("KRX ETF Open API returned no recent data.")
    as_of_date = datetime.strptime(as_of, "%Y%m%d").date()
    previous_as_of, previous_rows = _etf_open_api_session_on_or_before(as_of_date - timedelta(days=1), 10)
    previous_map = {item["ticker"]: item for item in previous_rows}

    volume_rows = []
    for item in current_rows:
        previous_volume = int((previous_map.get(item["ticker"]) or {}).get("volume") or 0)
        if previous_volume <= 0:
            continue
        row = dict(item)
        row["rate"] = round(((int(item.get("volume") or 0) / previous_volume) - 1) * 100, 4)
        volume_rows.append(row)

    rankings = {
        "1d": {
            "gainers": _etf_open_rank(current_rows, "rate"),
            "losers": _etf_open_rank(current_rows, "rate", reverse=False),
        }
    }
    for key, days in (("1w", 7), ("1m", 31), ("3m", 93)):
        _, start_rows = _etf_open_api_session_on_or_before(as_of_date - timedelta(days=days), 10)
        rankings[key] = _etf_open_period_rank(current_rows, start_rows)

    premiums = [item for item in current_rows if item.get("premium") is not None]
    payload = {
        "status": "ready",
        "asOf": as_of_date.isoformat(),
        "previousAsOf": (
            datetime.strptime(previous_as_of, "%Y%m%d").date().isoformat()
            if previous_as_of else None
        ),
        "generatedAt": datetime.now(KST).isoformat(),
        "source": "KRX Open API",
        "enrichmentStatus": "collecting",
        "rankings": rankings,
        "turnover": _etf_open_rank(current_rows, "tradingValue", liquidity=False),
        "volumeSurge": _etf_open_rank(volume_rows, "rate"),
        "premium": _etf_open_rank(premiums, "premium"),
        "discount": _etf_open_rank(premiums, "premium", reverse=False),
        "trackingError": [],
        "concentration": [],
        "etfDirectory": [
            {"ticker": item.get("ticker"), "name": item.get("name") or item.get("ticker")}
            for item in current_rows if item.get("ticker")
        ],
        "holdingsByEtf": {},
        "reverseHoldings": {},
        "changes": {"added": [], "removed": []},
        "scope": {
            "totalEtfCount": len(current_rows),
            "holdingsUniverseCount": 0,
            "trackingUniverseCount": 0,
            "minimumTradingValue": ETF_MIN_TRADING_VALUE,
        },
    }
    previous_payload = load_domestic_etf_dashboard()
    if isinstance(previous_payload, dict) and previous_payload.get("holdingsByEtf"):
        previous_as_of = str(previous_payload.get("asOf") or "")
        carried_holdings = {}
        for ticker, item in (previous_payload.get("holdingsByEtf") or {}).items():
            carried = dict(item or {})
            carried["asOf"] = str(carried.get("asOf") or previous_as_of)
            carried_holdings[str(ticker)] = carried
        payload["holdingsByEtf"] = carried_holdings
        payload["reverseHoldings"] = dict(
            previous_payload.get("reverseHoldings") or {}
        )
        payload["concentration"] = list(
            previous_payload.get("concentration") or []
        )
        payload["holdingsCarryAsOf"] = previous_as_of or None
        previous_scope = previous_payload.get("scope") or {}
        payload["scope"]["holdingsUniverseCount"] = len(carried_holdings)
        payload["scope"]["trackingUniverseCount"] = int(
            previous_scope.get("trackingUniverseCount") or 0
        )
        if previous_payload.get("asOf") == payload.get("asOf"):
            for key in (
                "enrichmentStatus", "enrichmentStage", "enrichmentProgress",
                "enrichmentUpdatedAt", "enrichmentError", "enrichmentCursor",
                "holdingsProvider", "trackingError", "changes",
            ):
                if key in previous_payload:
                    payload[key] = previous_payload[key]
    save_domestic_etf_dashboard(payload)
    return payload


def _save_domestic_etf_enrichment_checkpoint(
    base_payload,
    stage,
    holdings_by_etf=None,
    reverse_holdings=None,
    added=None,
    removed=None,
    tracking_error=None,
    progress=None,
):
    if not isinstance(base_payload, dict) or base_payload.get("status") != "ready":
        return base_payload
    payload = dict(base_payload)
    payload["enrichmentStatus"] = "collecting"
    payload["enrichmentStage"] = stage
    payload["enrichmentProgress"] = dict(progress or {})
    payload["enrichmentUpdatedAt"] = datetime.now(KST).isoformat()
    payload["enrichmentError"] = None
    if holdings_by_etf is not None:
        payload["holdingsByEtf"] = holdings_by_etf
        concentration = []
        for ticker, item in holdings_by_etf.items():
            concentration.append({
                "ticker": ticker,
                "name": item.get("name") or ticker,
                "concentration": round(sum(
                    float(row.get("weight") or 0)
                    for row in (item.get("holdings") or [])[:5]
                ), 4),
            })
        concentration.sort(
            key=lambda item: float(item.get("concentration") or 0), reverse=True
        )
        payload["concentration"] = concentration[:5]
    if reverse_holdings is not None:
        prepared_reverse = {}
        for stock_ticker, rows in reverse_holdings.items():
            prepared_reverse[stock_ticker] = sorted(
                rows,
                key=lambda item: float(item.get("weight") or 0),
                reverse=True,
            )[:5]
        payload["reverseHoldings"] = prepared_reverse
    if added is not None or removed is not None:
        payload["changes"] = {
            "added": list(added or [])[:50],
            "removed": list(removed or [])[:50],
        }
    if tracking_error is not None:
        payload["trackingError"] = sorted(
            tracking_error,
            key=lambda item: float(item.get("trackingError") or 0),
            reverse=True,
        )
    scope = dict(payload.get("scope") or {})
    if holdings_by_etf is not None:
        scope["holdingsUniverseCount"] = len(holdings_by_etf)
    if tracking_error is not None:
        scope["trackingUniverseCount"] = int(
            (progress or {}).get("trackingProcessed") or len(tracking_error)
        )
    payload["scope"] = scope
    save_domestic_etf_dashboard(payload)
    return payload


class _PykrxTimeoutAdapter(requests.adapters.HTTPAdapter):
    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = (
                ETF_KRX_CONNECT_TIMEOUT,
                ETF_KRX_READ_TIMEOUT,
            )
        return super().send(request, **kwargs)


def _configure_pykrx_timeout(auth_session):
    session = getattr(auth_session, "session", None)
    if session is None:
        raise RuntimeError("KRX authenticated HTTP session is unavailable.")
    adapter = _PykrxTimeoutAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)


def collect_domestic_etf_dashboard():
    global DOMESTIC_ETF_OPEN_API_LAST_ERROR
    global DOMESTIC_ETF_AUTH_STATUS, DOMESTIC_ETF_AUTH_CHECKED_AT
    open_api_payload = None
    if KRX_OPEN_API_AUTH_KEY:
        try:
            open_api_payload = collect_domestic_etf_open_api_snapshot()
            DOMESTIC_ETF_OPEN_API_LAST_ERROR = ""
        except Exception as exc:
            DOMESTIC_ETF_OPEN_API_LAST_ERROR = str(exc)
            print(f"KRX ETF Open API snapshot failed: {exc}", flush=True)
    if open_api_payload:
        DOMESTIC_ETF_AUTH_STATUS = "not_required"
        DOMESTIC_ETF_AUTH_CHECKED_AT = datetime.now(KST).isoformat()
        return _enrich_domestic_etf_holdings(open_api_payload)
    if not os.environ.get("KRX_ID", "").strip() or not os.environ.get("KRX_PW", "").strip():
        if open_api_payload:
            open_api_payload["enrichmentStatus"] = "unavailable"
            save_domestic_etf_dashboard(open_api_payload, promote_last_ready=True)
            return open_api_payload
        raise RuntimeError("KRX_ID and KRX_PW environment variables are required.")
    open_api_payload = _save_domestic_etf_enrichment_checkpoint(
        open_api_payload, "login", progress={"processed": 0, "total": 0}
    )
    try:
        from pykrx import stock as pykrx_stock
        from pykrx.website.comm.auth import get_auth_session
    except Exception as exc:
        raise RuntimeError("pykrx is not installed.") from exc

    try:
        auth_session = get_auth_session()
    except Exception as exc:
        DOMESTIC_ETF_AUTH_STATUS = "error"
        DOMESTIC_ETF_AUTH_CHECKED_AT = datetime.now(KST).isoformat()
        raise RuntimeError(f"KRX login request failed: {exc}") from exc
    if auth_session is None:
        DOMESTIC_ETF_AUTH_STATUS = "failed"
        DOMESTIC_ETF_AUTH_CHECKED_AT = datetime.now(KST).isoformat()
        raise RuntimeError(
            "KRX login failed. Use a direct data.krx.co.kr member ID and password, "
            "then verify the account can sign in on the KRX Data Marketplace website."
        )
    DOMESTIC_ETF_AUTH_STATUS = "authenticated"
    DOMESTIC_ETF_AUTH_CHECKED_AT = datetime.now(KST).isoformat()
    _configure_pykrx_timeout(auth_session)

    open_api_payload = _save_domestic_etf_enrichment_checkpoint(
        open_api_payload, "sessions", progress={"processed": 0, "total": 0}
    )
    sessions = _etf_latest_sessions(pykrx_stock, 2)
    as_of, current = sessions[0]
    previous_day, previous = sessions[1]
    name_cache = {
        str(item.get("ticker") or "").zfill(6): str(item.get("name") or item.get("ticker") or "")
        for item in ((open_api_payload or {}).get("etfDirectory") or [])
        if item.get("ticker")
    }
    component_name_cache = _domestic_stock_name_map()
    close = pd.to_numeric(_etf_column(current, "\uc885\uac00"), errors="coerce")
    nav = pd.to_numeric(_etf_column(current, "NAV"), errors="coerce")
    trading_value = pd.to_numeric(_etf_column(current, "\uac70\ub798\ub300\uae08"), errors="coerce").fillna(0)
    volume = pd.to_numeric(_etf_column(current, "\uac70\ub798\ub7c9"), errors="coerce").fillna(0)
    previous_volume = pd.to_numeric(_etf_column(previous, "\uac70\ub798\ub7c9"), errors="coerce").reindex(current.index).fillna(0)
    daily_rate_name = "\ub4f1\ub77d\ub960"

    rankings = {
        "1d": {
            "gainers": _etf_rank_rows(current, daily_rate_name, name_cache, pykrx_stock),
            "losers": _etf_rank_rows(current, daily_rate_name, name_cache, pykrx_stock, ascending=True),
        }
    }
    period_days = {"1w": 7, "1m": 31, "3m": 93}
    as_of_date = datetime.strptime(as_of, "%Y%m%d").date()
    for key, days in period_days.items():
        start = (as_of_date - timedelta(days=days)).strftime("%Y%m%d")
        try:
            period_frame = pykrx_stock.get_etf_price_change_by_ticker(start, as_of)
            rankings[key] = {
                "gainers": _etf_rank_rows(period_frame, "\ub4f1\ub77d\ub960", name_cache, pykrx_stock),
                "losers": _etf_rank_rows(period_frame, "\ub4f1\ub77d\ub960", name_cache, pykrx_stock, ascending=True),
            }
        except Exception as exc:
            print(f"ETF period ranking failed({key}): {exc}", flush=True)
            rankings[key] = {"gainers": [], "losers": []}

    liquid_mask = trading_value >= ETF_MIN_TRADING_VALUE
    premium = ((close / nav) - 1.0) * 100
    premium = premium.where(liquid_mask).replace([float("inf"), float("-inf")], pd.NA).dropna()
    volume_surge = ((volume / previous_volume.replace(0, pd.NA)) - 1.0) * 100
    volume_surge = volume_surge.where(liquid_mask).replace([float("inf"), float("-inf")], pd.NA).dropna()

    turnover_rows = _etf_metric_rows(trading_value, current, pykrx_stock, name_cache, key="tradingValue")
    volume_rows = _etf_metric_rows(volume_surge, current, pykrx_stock, name_cache, key="rate")
    premium_rows = _etf_metric_rows(premium, current, pykrx_stock, name_cache, key="premium")
    discount_rows = _etf_metric_rows(premium, current, pykrx_stock, name_cache, ascending=True, key="premium")

    ordered_universe = trading_value.sort_values(ascending=False).index
    if ETF_HOLDINGS_UNIVERSE_SIZE > 0:
        ordered_universe = ordered_universe[:ETF_HOLDINGS_UNIVERSE_SIZE]
    universe = [str(ticker).zfill(6) for ticker in ordered_universe]
    holdings_by_etf = dict((open_api_payload or {}).get("holdingsByEtf") or {})
    reverse_holdings = dict((open_api_payload or {}).get("reverseHoldings") or {})
    previous_changes = (open_api_payload or {}).get("changes") or {}
    added = list(previous_changes.get("added") or [])
    removed = list(previous_changes.get("removed") or [])

    tracking_error = []
    holdings_target_as_of = datetime.strptime(as_of, "%Y%m%d").strftime("%Y-%m-%d")

    def current_holdings_count():
        return sum(
            1 for item in holdings_by_etf.values()
            if str((item or {}).get("asOf") or "") == holdings_target_as_of
        )

    open_api_payload = _save_domestic_etf_enrichment_checkpoint(
        open_api_payload,
        "holdings",
        holdings_by_etf,
        reverse_holdings,
        added,
        removed,
        progress={"processed": current_holdings_count(), "total": len(universe)},
    )

    consecutive_holdings_failures = 0
    holdings_warning = None
    for index, ticker in enumerate(universe, start=1):
        cached_item = holdings_by_etf.get(ticker) or {}
        if (
            str(cached_item.get("asOf") or "") == holdings_target_as_of
            and int(cached_item.get("nameResolverVersion") or 0) >= 2
        ):
            continue
        try:
            current_pdf = pykrx_stock.get_etf_portfolio_deposit_file(ticker, as_of)
            previous_pdf = pykrx_stock.get_etf_portfolio_deposit_file(ticker, previous_day)
            all_rows = _etf_portfolio_rows(current_pdf)
            for row in all_rows:
                row["name"] = _etf_component_name(
                    pykrx_stock, row.get("ticker"), row.get("name"), component_name_cache
                )
            top_rows = all_rows[:5]
            etf_name = _etf_name(pykrx_stock, ticker, name_cache)
            for stock_ticker in list(reverse_holdings):
                reverse_holdings[stock_ticker] = [
                    row for row in reverse_holdings[stock_ticker]
                    if str(row.get("ticker") or "") != ticker
                ]
                if not reverse_holdings[stock_ticker]:
                    reverse_holdings.pop(stock_ticker, None)
            holdings_by_etf[ticker] = {
                "ticker": ticker,
                "asOf": holdings_target_as_of,
                "name": etf_name,
                "holdings": top_rows,
                "holdingCount": len(all_rows),
                "namesResolved": True,
                "nameResolverVersion": 2,
            }
            for row in top_rows:
                reverse_holdings.setdefault(row["ticker"], []).append({
                    "ticker": ticker,
                    "name": etf_name,
                    "weight": row["weight"],
                })
            previous_rows = _etf_portfolio_rows(previous_pdf)
            for row in previous_rows:
                row["name"] = _etf_component_name(
                    pykrx_stock, row.get("ticker"), row.get("name"), component_name_cache
                )
            current_names = {row["ticker"]: row.get("name") or "" for row in all_rows}
            previous_names = {row["ticker"]: row.get("name") or "" for row in previous_rows}
            current_codes = set(current_names)
            previous_codes = set(previous_names)
            for stock_ticker in sorted(current_codes - previous_codes):
                added.append({
                    "etfTicker": ticker,
                    "etfName": etf_name,
                    "stockTicker": stock_ticker,
                    "stockName": current_names.get(stock_ticker) or "",
                })
            for stock_ticker in sorted(previous_codes - current_codes):
                removed.append({
                    "etfTicker": ticker,
                    "etfName": etf_name,
                    "stockTicker": stock_ticker,
                    "stockName": previous_names.get(stock_ticker) or "",
                })
            consecutive_holdings_failures = 0
        except Exception as exc:
            consecutive_holdings_failures += 1
            print(f"ETF holdings failed({ticker}): {exc}", flush=True)
            if consecutive_holdings_failures >= 3:
                holdings_warning = (
                    "KRX ETF holdings requests failed three times in a row; "
                    f"last ticker={ticker}, error={exc}"
                )
                break
        if index % 10 == 0 or index == len(universe):
            open_api_payload = _save_domestic_etf_enrichment_checkpoint(
                open_api_payload,
                "holdings",
                holdings_by_etf,
                reverse_holdings,
                added,
                removed,
                progress={"processed": current_holdings_count(), "total": len(universe)},
            )
        time.sleep(ETF_HOLDINGS_REQUEST_DELAY_SECONDS)

    for stock_ticker in reverse_holdings:
        reverse_holdings[stock_ticker].sort(key=lambda item: float(item.get("weight") or 0), reverse=True)
        reverse_holdings[stock_ticker] = reverse_holdings[stock_ticker][:5]
    concentration = []
    for ticker, item in holdings_by_etf.items():
        concentration.append({
            "ticker": ticker,
            "name": item.get("name") or ticker,
            "concentration": round(sum(
                float(row.get("weight") or 0)
                for row in (item.get("holdings") or [])[:5]
            ), 4),
        })
    concentration.sort(key=lambda item: float(item.get("concentration") or 0), reverse=True)

    current_holdings_processed = current_holdings_count()
    holdings_complete = current_holdings_processed >= len(universe)
    payload = {
        "status": "ready",
        "asOf": datetime.strptime(as_of, "%Y%m%d").strftime("%Y-%m-%d"),
        "previousAsOf": datetime.strptime(previous_day, "%Y%m%d").strftime("%Y-%m-%d"),
        "generatedAt": datetime.now(KST).isoformat(),
        "source": "KRX Open API + pykrx" if open_api_payload else "KRX via pykrx",
        "enrichmentStatus": "ready" if holdings_complete else "collecting",
        "enrichmentStage": "complete" if holdings_complete else "holdings",
        "enrichmentProgress": {
            "processed": current_holdings_processed,
            "total": len(universe),
        },
        "enrichmentUpdatedAt": datetime.now(KST).isoformat(),
        "enrichmentError": holdings_warning,
        "scope": {
            "totalEtfCount": int(len(current.index)),
            "holdingsUniverseCount": len(holdings_by_etf),
            "minimumTradingValue": ETF_MIN_TRADING_VALUE,
        },
        "rankings": rankings,
        "turnover": turnover_rows,
        "volumeSurge": volume_rows,
        "premium": premium_rows,
        "discount": discount_rows,
        "concentration": concentration[:5],
        "etfDirectory": (open_api_payload or {}).get("etfDirectory") or [
            {"ticker": ticker, "name": item.get("name") or ticker}
            for ticker, item in holdings_by_etf.items()
        ],
        "holdingsByEtf": holdings_by_etf,
        "reverseHoldings": reverse_holdings,
        "changes": {"added": added[:50], "removed": removed[:50]},
    }
    save_domestic_etf_dashboard(payload, promote_last_ready=True)
    return payload


def run_domestic_etf_refresh():
    global DOMESTIC_ETF_REFRESHING, DOMESTIC_ETF_LAST_ERROR
    if not DOMESTIC_ETF_REFRESH_LOCK.acquire(blocking=False):
        return
    DOMESTIC_ETF_REFRESHING = True
    try:
        collect_domestic_etf_dashboard()
        DOMESTIC_ETF_LAST_ERROR = ""
    except Exception as exc:
        DOMESTIC_ETF_LAST_ERROR = str(exc)
        cached_payload = load_domestic_etf_dashboard()
        if (
            isinstance(cached_payload, dict)
            and cached_payload.get("status") == "ready"
            and cached_payload.get("enrichmentStatus") == "collecting"
        ):
            cached_payload["enrichmentStatus"] = "unavailable"
            cached_payload["enrichmentError"] = DOMESTIC_ETF_LAST_ERROR
            cached_payload["enrichmentAttemptedAt"] = datetime.now(KST).isoformat()
            save_domestic_etf_dashboard(cached_payload)
        print(f"Domestic ETF refresh failed: {exc}", flush=True)
    finally:
        DOMESTIC_ETF_REFRESHING = False
        DOMESTIC_ETF_REFRESH_LOCK.release()


def run_domestic_etf_enrichment_resume():
    global DOMESTIC_ETF_REFRESHING, DOMESTIC_ETF_LAST_ERROR
    if not DOMESTIC_ETF_REFRESH_LOCK.acquire(blocking=False):
        return
    DOMESTIC_ETF_REFRESHING = True
    try:
        payload = load_domestic_etf_dashboard()
        if (
            isinstance(payload, dict)
            and payload.get("status") == "ready"
            and payload.get("enrichmentStatus") == "collecting"
        ):
            _enrich_domestic_etf_holdings(payload)
        DOMESTIC_ETF_LAST_ERROR = ""
    except Exception as exc:
        DOMESTIC_ETF_LAST_ERROR = str(exc)
        print(f"Domestic ETF enrichment resume failed: {exc}", flush=True)
    finally:
        DOMESTIC_ETF_REFRESHING = False
        DOMESTIC_ETF_REFRESH_LOCK.release()


def _expected_krx_session_date(now=None):
    now = now or datetime.now(KST)
    candidate = now.date()
    if now.time() < datetime_time(18, 0):
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _krx_payload_session_is_old(payload, now=None):
    as_of = str((payload or {}).get("asOf") or "").strip()
    if not as_of:
        return True
    try:
        actual = datetime.strptime(as_of[:10], "%Y-%m-%d").date()
        return actual < _expected_krx_session_date(now)
    except (TypeError, ValueError):
        return True


def _next_krx_refresh_target(now, schedule):
    for day_offset in range(8):
        candidate_date = now.date() + timedelta(days=day_offset)
        if candidate_date.weekday() >= 5:
            continue
        for hour, minute in schedule:
            target = datetime.combine(
                candidate_date, datetime_time(hour, minute), tzinfo=KST
            )
            if target > now:
                return target
    return now + timedelta(hours=24)


def _domestic_etf_cache_stale(payload):
    generated = (payload or {}).get("generatedAt")
    if not generated or _krx_payload_session_is_old(payload):
        return True
    try:
        enrichment_status = str((payload or {}).get("enrichmentStatus") or "")
        activity_stamp = (
            (payload or {}).get("enrichmentUpdatedAt")
            if enrichment_status in {"collecting", "unavailable"}
            else generated
        ) or generated
        stamp = datetime.fromisoformat(str(activity_stamp).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=KST)
        age = datetime.now(KST) - stamp.astimezone(KST)
        if enrichment_status == "collecting" and age >= timedelta(minutes=2):
            return True
        if enrichment_status == "unavailable" and age >= timedelta(minutes=30):
            return True
        return age >= timedelta(hours=18)
    except (TypeError, ValueError):
        return True


def domestic_etf_scheduler():
    schedule = ((18, 10), (18, 50))
    while True:
        now = datetime.now(KST)
        target = _next_krx_refresh_target(now, schedule)
        time.sleep(max(60, (target - now).total_seconds()))
        run_domestic_etf_refresh()
        for _ in range(20):
            payload = load_domestic_etf_dashboard()
            if str((payload or {}).get("enrichmentStatus") or "") != "collecting":
                break
            time.sleep(30)
            run_domestic_etf_enrichment_resume()


def ensure_domestic_etf_scheduler():
    global DOMESTIC_ETF_SCHEDULER_STARTED
    if DOMESTIC_ETF_SCHEDULER_STARTED:
        return
    DOMESTIC_ETF_SCHEDULER_STARTED = True
    start_thread(domestic_etf_scheduler)


@app.get("/api/domestic-etf-dashboard")
def domestic_etf_dashboard_api():
    ensure_domestic_etf_scheduler()
    payload = load_domestic_etf_dashboard()
    can_refresh = bool(
        KRX_OPEN_API_AUTH_KEY
        or (
            os.environ.get("KRX_ID", "").strip()
            and os.environ.get("KRX_PW", "").strip()
        )
    )
    refresh_started = False
    retry_seconds = (
        120 if str((payload or {}).get("enrichmentStatus") or "") == "collecting"
        else 1800
    )
    recent_attempt = get_cached_value("domestic-etf-refresh-attempt", retry_seconds)
    if (
        can_refresh
        and _domestic_etf_cache_stale(payload)
        and not DOMESTIC_ETF_REFRESHING
        and recent_attempt is None
    ):
        set_cached_value(
            "domestic-etf-refresh-attempt",
            {"at": datetime.now(KST).isoformat()},
        )
        refresh_handler = (
            run_domestic_etf_enrichment_resume
            if (
                str((payload or {}).get("enrichmentStatus") or "") == "collecting"
                and not _krx_payload_session_is_old(payload)
            )
            else run_domestic_etf_refresh
        )
        start_thread(refresh_handler)
        refresh_started = True
    response = dict(payload or {})
    response["refreshing"] = bool(DOMESTIC_ETF_REFRESHING or refresh_started)
    response["expectedAsOf"] = _expected_krx_session_date().isoformat()
    response["stale"] = _krx_payload_session_is_old(response)
    stock_ticker = re.sub(r"\D", "", request.args.get("stock", ""))[:6]
    reverse_holdings = response.pop("reverseHoldings", {}) or {}
    response["stockQuery"] = stock_ticker
    response["stockRanking"] = reverse_holdings.get(stock_ticker, []) if stock_ticker else []
    response["openApiError"] = DOMESTIC_ETF_OPEN_API_LAST_ERROR or None
    response["enrichmentError"] = response.get("enrichmentError") or DOMESTIC_ETF_LAST_ERROR or None
    response["krxAuthStatus"] = DOMESTIC_ETF_AUTH_STATUS
    response["krxAuthCheckedAt"] = DOMESTIC_ETF_AUTH_CHECKED_AT
    if response.get("status") != "ready":
        if not os.environ.get("KRX_ID", "").strip() or not os.environ.get("KRX_PW", "").strip():
            response["message"] = "KRX credentials are not configured."
        elif DOMESTIC_ETF_LAST_ERROR:
            response["message"] = DOMESTIC_ETF_LAST_ERROR
        else:
            response["message"] = "The first daily ETF snapshot is being prepared."
    return jsonify(response)


KRX_OPEN_API_AUTH_KEY = os.environ.get("KRX_OPEN_API_AUTH_KEY", "").strip()
KRX_OPEN_API_BASE_URL = os.environ.get(
    "KRX_OPEN_API_BASE_URL",
    "http://data-dbg.krx.co.kr/svc/apis",
).strip().rstrip("/")
KRX_MARKET_CLOSE_FILE = os.environ.get(
    "KRX_MARKET_CLOSE_FILE",
    "/var/data/krx_market_close.json"
    if os.path.isdir("/var/data")
    else os.path.join(BASE_DIR, "krx_market_close.json"),
)
KRX_MARKET_CLOSE_CACHE_KEY = "krx:market-close:v1"
KRX_MARKET_MIN_TRADING_VALUE = max(
    0, int(os.environ.get("KRX_MARKET_MIN_TRADING_VALUE", "1000000000") or "1000000000")
)
KRX_MARKET_CLOSE_LOCK = threading.Lock()
KRX_MARKET_CLOSE_REFRESHING = False
KRX_MARKET_CLOSE_LAST_ERROR = ""
KRX_MARKET_CLOSE_SCHEDULER_STARTED = False


def load_krx_market_close():
    return load_app_cache_payload(KRX_MARKET_CLOSE_CACHE_KEY, KRX_MARKET_CLOSE_FILE, {
        "status": "empty",
        "asOf": None,
        "generatedAt": None,
        "indices": [],
        "markets": [],
        "rankings": {},
        "leaders": [],
        "dailyHistory": [],
    })


def _krx_open_api_rows(path, date_text):
    if not KRX_OPEN_API_AUTH_KEY:
        raise RuntimeError("KRX_OPEN_API_AUTH_KEY environment variable is required.")
    response = requests.get(
        f"{KRX_OPEN_API_BASE_URL}/{path.lstrip('/')}",
        params={"basDd": date_text},
        headers={"AUTH_KEY": KRX_OPEN_API_AUTH_KEY, "Accept": "application/json"},
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("OutBlock_1", "output", "data", "items"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
        for rows in payload.values():
            if isinstance(rows, list):
                return rows
        message = payload.get("message") or payload.get("msg") or payload.get("resultMsg")
        if message:
            raise RuntimeError(str(message))
    return []


def _krx_api_number(value, integer=False):
    try:
        number = float(str(value or "0").replace(",", "").replace("%", "").strip())
        return int(round(number)) if integer else round(number, 4)
    except (TypeError, ValueError):
        return 0 if integer else 0.0


def _krx_stock_row(row, market):
    return {
        "ticker": str(row.get("ISU_SRT_CD") or row.get("ISU_CD") or "").strip(),
        "name": str(row.get("ISU_NM") or "").strip(),
        "market": market,
        "close": _krx_api_number(row.get("TDD_CLSPRC"), True),
        "change": _krx_api_number(row.get("CMPPREVDD_PRC"), True),
        "rate": _krx_api_number(row.get("FLUC_RT")),
        "open": _krx_api_number(row.get("TDD_OPNPRC"), True),
        "high": _krx_api_number(row.get("TDD_HGPRC"), True),
        "low": _krx_api_number(row.get("TDD_LWPRC"), True),
        "volume": _krx_api_number(row.get("ACC_TRDVOL"), True),
        "tradingValue": _krx_api_number(row.get("ACC_TRDVAL"), True),
        "marketCap": _krx_api_number(row.get("MKTCAP"), True),
        "listedShares": _krx_api_number(row.get("LIST_SHRS"), True),
    }


def _krx_index_rows(rows, market):
    normalized = []
    for row in rows:
        name = str(row.get("IDX_NM") or "").strip()
        normalized.append({
            "name": name,
            "market": market,
            "close": _krx_api_number(row.get("CLSPRC_IDX")),
            "change": _krx_api_number(row.get("CMPPREVDD_IDX")),
            "rate": _krx_api_number(row.get("FLUC_RT")),
            "tradingValue": _krx_api_number(row.get("ACC_TRDVAL"), True),
            "marketCap": _krx_api_number(row.get("MKTCAP"), True),
        })
    preferred = "\ucf54\uc2a4\ud53c" if market == "KOSPI" else "\ucf54\uc2a4\ub2e5"
    exact = [item for item in normalized if item["name"].replace(" ", "").lower() in (preferred, market.lower())]
    return exact[:1] or normalized[:1]


def _krx_rank(items, key, limit=5, reverse=True, liquidity_floor=False):
    rows = items
    if liquidity_floor:
        rows = [item for item in rows if int(item.get("tradingValue") or 0) >= KRX_MARKET_MIN_TRADING_VALUE]
    return sorted(rows, key=lambda item: float(item.get(key) or 0), reverse=reverse)[:limit]


def _krx_find_latest_sessions(count=2):
    found = []
    cursor = datetime.now(KST).date()
    for offset in range(14):
        date_text = (cursor - timedelta(days=offset)).strftime("%Y%m%d")
        try:
            kospi = _krx_open_api_rows("sto/stk_bydd_trd", date_text)
            kosdaq = _krx_open_api_rows("sto/ksq_bydd_trd", date_text)
        except Exception as exc:
            print(f"KRX session lookup skipped({date_text}): {exc}", flush=True)
            continue
        if kospi or kosdaq:
            found.append((date_text, kospi, kosdaq))
            if len(found) >= count:
                return found
    raise RuntimeError("No recent KRX Open API trading session was found.")


def collect_krx_market_close():
    sessions = _krx_find_latest_sessions(2)
    as_of, kospi_raw, kosdaq_raw = sessions[0]
    previous_as_of, previous_kospi_raw, previous_kosdaq_raw = sessions[1]
    stocks = [
        *[_krx_stock_row(row, "KOSPI") for row in kospi_raw],
        *[_krx_stock_row(row, "KOSDAQ") for row in kosdaq_raw],
    ]
    stocks = [item for item in stocks if item["ticker"] and item["name"]]
    previous = {
        item["ticker"]: item
        for item in [
            *[_krx_stock_row(row, "KOSPI") for row in previous_kospi_raw],
            *[_krx_stock_row(row, "KOSDAQ") for row in previous_kosdaq_raw],
        ]
        if item["ticker"]
    }

    for item in stocks:
        previous_volume = int((previous.get(item["ticker"]) or {}).get("volume") or 0)
        item["volumeChangeRate"] = (
            round(((item["volume"] / previous_volume) - 1) * 100, 2)
            if previous_volume > 0 else None
        )

    indices = []
    for market, endpoint in (("KOSPI", "idx/kospi_dd_trd"), ("KOSDAQ", "idx/kosdaq_dd_trd")):
        try:
            indices.extend(_krx_index_rows(_krx_open_api_rows(endpoint, as_of), market))
        except Exception as exc:
            print(f"KRX index fetch failed({market}): {exc}", flush=True)

    markets = []
    for market in ("KOSPI", "KOSDAQ"):
        rows = [item for item in stocks if item["market"] == market]
        up = sum(1 for item in rows if item["rate"] > 0)
        down = sum(1 for item in rows if item["rate"] < 0)
        flat = max(0, len(rows) - up - down)
        markets.append({
            "market": market,
            "up": up,
            "down": down,
            "flat": flat,
            "total": len(rows),
            "tradingValue": sum(int(item["tradingValue"] or 0) for item in rows),
            "marketCap": sum(int(item["marketCap"] or 0) for item in rows),
        })

    gainers = _krx_rank(stocks, "rate", 5, True, True)
    losers = _krx_rank(stocks, "rate", 5, False, True)
    turnover_top20 = _krx_rank(stocks, "tradingValue", 20, True)
    volume_candidates = [
        item for item in stocks
        if item.get("volumeChangeRate") is not None
        and int(item.get("tradingValue") or 0) >= KRX_MARKET_MIN_TRADING_VALUE
    ]
    volume_surge = _krx_rank(volume_candidates, "volumeChangeRate", 5, True)

    previous_payload = load_krx_market_close()
    daily_history = [
        item for item in (previous_payload.get("dailyHistory") or [])
        if isinstance(item, dict) and str(item.get("date")) != datetime.strptime(as_of, "%Y%m%d").date().isoformat()
    ]
    daily_history.append({
        "date": datetime.strptime(as_of, "%Y%m%d").date().isoformat(),
        "turnoverTickers": [
            {"ticker": item["ticker"], "name": item["name"], "market": item["market"]}
            for item in turnover_top20
        ],
    })
    daily_history = sorted(daily_history, key=lambda item: str(item.get("date") or ""))[-30:]
    leader_map = {}
    for day in daily_history[-10:]:
        for rank, item in enumerate(day.get("turnoverTickers") or [], 1):
            ticker = str(item.get("ticker") or "")
            if not ticker:
                continue
            leader = leader_map.setdefault(ticker, {
                "ticker": ticker,
                "name": item.get("name") or ticker,
                "market": item.get("market") or "",
                "appearances": 0,
                "score": 0,
            })
            leader["appearances"] += 1
            leader["score"] += max(1, 21 - rank)
    leaders = sorted(
        leader_map.values(),
        key=lambda item: (int(item["appearances"]), int(item["score"])),
        reverse=True,
    )[:5]

    total_up = sum(item["up"] for item in markets)
    total_down = sum(item["down"] for item in markets)
    total_directional = max(1, total_up + total_down)
    up_ratio = round((total_up / total_directional) * 100, 1)
    if up_ratio >= 60:
        temperature = {"label": "\uac15\uc138", "tone": "hot"}
    elif up_ratio <= 40:
        temperature = {"label": "\uc57d\uc138", "tone": "cold"}
    else:
        temperature = {"label": "\uc911\ub9bd", "tone": "neutral"}
    temperature.update({"upRatio": up_ratio, "advanceDeclineRatio": round(total_up / max(1, total_down), 2)})

    payload = {
        "status": "ready",
        "source": "KRX Open API",
        "asOf": datetime.strptime(as_of, "%Y%m%d").date().isoformat(),
        "previousAsOf": datetime.strptime(previous_as_of, "%Y%m%d").date().isoformat(),
        "generatedAt": datetime.now(KST).isoformat(),
        "indices": indices,
        "markets": markets,
        "temperature": temperature,
        "rankings": {
            "gainers": gainers,
            "losers": losers,
            "turnover": turnover_top20[:5],
            "volumeSurge": volume_surge,
        },
        "leaders": leaders,
        "dailyHistory": daily_history,
        "scope": {
            "stockCount": len(stocks),
            "minimumTradingValue": KRX_MARKET_MIN_TRADING_VALUE,
            "leaderWindowDays": min(10, len(daily_history)),
        },
    }
    save_app_cache_payload(KRX_MARKET_CLOSE_CACHE_KEY, payload, KRX_MARKET_CLOSE_FILE)

    try:
        history_payload = load_kr_market_breadth_history()
        breadth_snapshot = {
            "asOf": f"{payload['asOf']}T15:40:00+09:00",
            "markets": [
                {"market": item["market"], "up": item["up"], "down": item["down"], "total": item["total"]}
                for item in markets
            ],
        }
        save_kr_market_breadth_history(
            update_history_with_snapshot(history_payload.get("items", []), breadth_snapshot)
        )
    except Exception as exc:
        print(f"KRX breadth history sync failed: {exc}", flush=True)
    return payload


def run_krx_market_close_refresh():
    global KRX_MARKET_CLOSE_REFRESHING, KRX_MARKET_CLOSE_LAST_ERROR
    if not KRX_MARKET_CLOSE_LOCK.acquire(blocking=False):
        return
    KRX_MARKET_CLOSE_REFRESHING = True
    try:
        collect_krx_market_close()
        KRX_MARKET_CLOSE_LAST_ERROR = ""
    except Exception as exc:
        KRX_MARKET_CLOSE_LAST_ERROR = str(exc)
        print(f"KRX market close refresh failed: {exc}", flush=True)
    finally:
        KRX_MARKET_CLOSE_REFRESHING = False
        KRX_MARKET_CLOSE_LOCK.release()


def _krx_market_close_stale(payload):
    generated = (payload or {}).get("generatedAt")
    if not generated or _krx_payload_session_is_old(payload):
        return True
    try:
        stamp = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=KST)
        return datetime.now(KST) - stamp.astimezone(KST) >= timedelta(hours=18)
    except (TypeError, ValueError):
        return True


def krx_market_close_scheduler():
    schedule = ((18, 0), (18, 40))
    while True:
        now = datetime.now(KST)
        target = _next_krx_refresh_target(now, schedule)
        time.sleep(max(60, (target - now).total_seconds()))
        run_krx_market_close_refresh()


def ensure_krx_market_close_scheduler():
    global KRX_MARKET_CLOSE_SCHEDULER_STARTED
    if KRX_MARKET_CLOSE_SCHEDULER_STARTED:
        return
    KRX_MARKET_CLOSE_SCHEDULER_STARTED = True
    start_thread(krx_market_close_scheduler)


@app.get("/api/krx-market-close")
def krx_market_close_api():
    ensure_krx_market_close_scheduler()
    payload = load_krx_market_close()
    refresh_started = False
    recent_attempt = get_cached_value("krx-market-close-refresh-attempt", 1800)
    if (
        KRX_OPEN_API_AUTH_KEY
        and _krx_market_close_stale(payload)
        and not KRX_MARKET_CLOSE_REFRESHING
        and recent_attempt is None
    ):
        set_cached_value("krx-market-close-refresh-attempt", {"at": datetime.now(KST).isoformat()})
        start_thread(run_krx_market_close_refresh)
        refresh_started = True
    response = dict(payload or {})
    response.pop("dailyHistory", None)
    response["refreshing"] = bool(KRX_MARKET_CLOSE_REFRESHING or refresh_started)
    response["expectedAsOf"] = _expected_krx_session_date().isoformat()
    response["stale"] = _krx_payload_session_is_old(response)
    if response.get("status") != "ready":
        if not KRX_OPEN_API_AUTH_KEY:
            response["message"] = "KRX_OPEN_API_AUTH_KEY environment variable is required."
        elif KRX_MARKET_CLOSE_LAST_ERROR:
            response["message"] = KRX_MARKET_CLOSE_LAST_ERROR
        else:
            response["message"] = "The first KRX market close snapshot is being prepared."
    return jsonify(response)

def load_eth_market_cache():
    return load_app_cache_payload("eth:market", ETH_MARKET_FILE, {
        "eth_krw": 0,
        "usd_krw": 0,
        "eth_apr": "0%",
        "updated_at": None,
    })


def save_eth_market_cache(payload):
    return save_app_cache_payload("eth:market", payload, ETH_MARKET_FILE)


def load_eth_news_cache():
    return load_app_cache_payload("eth:news", ETH_NEWS_FILE, {
        "updated_at": None,
        "articles": [],
    })


def save_eth_news_cache(payload):
    return save_app_cache_payload("eth:news", payload, ETH_NEWS_FILE)


def load_aaii_sentiment_fallback(reason=None):
    cached = supabase_cache_get("aaii:sentiment", None)
    if isinstance(cached, dict):
        cached["ok"] = True
        cached["source"] = cached.get("source") or "AAII"
        cached["stale"] = True
        cached["loadedFrom"] = "supabase"
        cached["warning"] = reason or "AAII 원본 데이터를 불러오지 못해 Supabase에 저장된 마지막 정상 수집값을 표시합니다."
        return cached

    fallback = AAII_FALLBACK.copy()
    if reason:
        fallback["warning"] = reason
    fallback["loadedFrom"] = "fallback"
    return fallback


def save_aaii_sentiment_cache(payload):
    if not isinstance(payload, dict):
        return False
    clean_payload = dict(payload)
    clean_payload.pop("stale", None)
    clean_payload.pop("warning", None)
    clean_payload.pop("loadedFrom", None)
    clean_payload.pop("_supabaseUpdatedAt", None)
    return supabase_cache_upsert("aaii:sentiment", clean_payload)


def get_eth_krw():
    response = ETH_CRAWLER_SESSION.get(UPBIT_TICKER_API, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not data:
        raise ValueError("empty Upbit ticker response")
    return int(float(data[0]["trade_price"]))


def get_eth_staking_apr():
    headers = {
        "User-Agent": ETH_CRAWLER_SESSION.headers["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.upbit.com",
        "Referer": "https://www.upbit.com/staking/items",
    }
    payload = [{
        "operationName": "GetItemsPage",
        "variables": {"serviceTextsKeys": ["markets_new_tag"]},
        "query": """
        query GetItemsPage($serviceTextsKeys: [String!]!) {
          markets {
            quoteSymbol
            baseSymbol
            weeklyApr
            productName
            stakingEvent { memberVolumeMin status __typename }
            __typename
          }
          serviceTexts(keys: $serviceTextsKeys) { key value __typename }
        }
        """,
    }]
    response = ETH_CRAWLER_SESSION.post(
        UPBIT_STAKING_PUBLIC_API,
        headers=headers,
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    root = data[0] if isinstance(data, list) and data else data
    markets = root.get("data", {}).get("markets", []) if isinstance(root, dict) else []
    for market in markets:
        if not isinstance(market, dict):
            continue
        product_name = str(market.get("productName") or "")
        if market.get("quoteSymbol") == "ETH" or market.get("baseSymbol") == "SETH" or "이더리움" in product_name:
            apr = market.get("weeklyApr")
            if apr in (None, ""):
                raise ValueError("ETH weeklyApr is empty")
            apr_text = str(apr).strip()
            return apr_text if apr_text.endswith("%") else f"{apr_text}%"
    raise ValueError("ETH staking item not found")


def get_usd_krw_from_naver():
    response = ETH_CRAWLER_SESSION.get(NAVER_FINANCE_URL, timeout=10)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    for pattern in [
        r"미국\s*USD\s*([0-9,]+(?:\.[0-9]+)?)",
        r"USD\s*([0-9,]+(?:\.[0-9]+)?)",
        r"달러\s*([0-9,]+(?:\.[0-9]+)?)",
    ]:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1).replace(",", ""))
    candidates = []
    for item in soup.stripped_strings:
        clean = item.replace(",", "")
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", clean):
            value = float(clean)
            if 1000 <= value <= 2500:
                candidates.append(value)
    if candidates:
        return candidates[0]
    raise ValueError("USD/KRW not found")


def crawl_eth_market():
    previous = load_eth_market_cache() or {}
    result = {
        "eth_krw": previous.get("eth_krw"),
        "usd_krw": previous.get("usd_krw"),
        "eth_apr": previous.get("eth_apr"),
        "updated_at": previous.get("updated_at"),
    }
    try:
        result["eth_krw"] = get_eth_krw()
    except Exception as exc:
        print(f"ETH price refresh failed: {exc}", flush=True)
    try:
        result["eth_apr"] = get_eth_staking_apr()
    except Exception as exc:
        print(f"ETH staking APR refresh failed: {exc}", flush=True)
    try:
        result["usd_krw"] = get_usd_krw_from_naver()
    except Exception as exc:
        print(f"USD/KRW refresh failed: {exc}", flush=True)
    result["updated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    save_eth_market_cache(result)
    return result


def extract_tokenpost_articles(limit=5):
    response = ETH_CRAWLER_SESSION.get(TOKENPOST_URL, timeout=15)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    articles = []
    seen_urls = set()
    for link in soup.select("a[href]"):
        href = link.get("href", "")
        title = clean_text(link.get_text(" ", strip=True))
        full_url = urljoin(TOKENPOST_BASE, href)
        if "/news/" not in full_url or full_url.rstrip("/") == TOKENPOST_URL.rstrip("/"):
            continue
        if full_url in seen_urls or len(title) < 8:
            continue
        seen_urls.add(full_url)
        articles.append({"title": title, "url": full_url})
        if len(articles) >= limit:
            break
    return articles


def extract_tokenpost_summary(url):
    response = ETH_CRAWLER_SESSION.get(url, timeout=15)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    for selector in ['meta[name="description"]', 'meta[property="og:description"]']:
        node = soup.select_one(selector)
        if node and node.get("content"):
            summary = clean_text(node.get("content"))
            if summary:
                return summary
    for selector in ["#articleContentArea", "article", ".article-content", ".view_con", ".content"]:
        node = soup.select_one(selector)
        if not node:
            continue
        for bad in node.select("script, style, iframe, ins"):
            bad.decompose()
        text = clean_text(node.get_text(" ", strip=True))
        if len(text) >= 30:
            return text[:500]
    return ""


def crawl_eth_news():
    results = []
    try:
        articles = extract_tokenpost_articles(limit=5)
    except Exception as exc:
        print(f"TokenPost article list refresh failed: {exc}", flush=True)
        articles = []
    for rank, item in enumerate(articles, start=1):
        try:
            summary = extract_tokenpost_summary(item["url"])
        except Exception as exc:
            print(f"TokenPost summary refresh failed({item.get('url')}): {exc}", flush=True)
            summary = ""
        results.append({
            "rank": rank,
            "title": item["title"],
            "url": item["url"],
            "ai_summary": summary,
        })
        time.sleep(0.25)
    payload = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "articles": results,
    }
    save_eth_news_cache(payload)
    return payload


def run_eth_market_refresh():
    global ETH_MARKET_RUNNING
    if ETH_MARKET_RUNNING:
        return
    ETH_MARKET_RUNNING = True
    try:
        crawl_eth_market()
    finally:
        ETH_MARKET_RUNNING = False


def run_eth_news_refresh():
    global ETH_NEWS_RUNNING
    if ETH_NEWS_RUNNING:
        return
    ETH_NEWS_RUNNING = True
    try:
        crawl_eth_news()
    finally:
        ETH_NEWS_RUNNING = False


def start_thread(target):
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


def maybe_start_eth_tracker_schedulers():
    if os.environ.get("DISABLE_ETH_JOBS", "false").lower() != "true":
        start_eth_tracker_schedulers()


def ensure_eth_market_fresh(force=False):
    maybe_start_eth_tracker_schedulers()
    if force or file_age_seconds(ETH_MARKET_FILE) > ETH_MARKET_INTERVAL:
        start_thread(run_eth_market_refresh)


def ensure_eth_news_fresh(force=False):
    maybe_start_eth_tracker_schedulers()
    if force or file_age_seconds(ETH_NEWS_FILE) > ETH_NEWS_INTERVAL:
        start_thread(run_eth_news_refresh)


@app.route("/api/eth-tracker/market")
def eth_tracker_market():
    ensure_eth_market_fresh(request.args.get("refresh") == "1")
    payload = load_eth_market_cache()
    payload["refreshing"] = ETH_MARKET_RUNNING
    return jsonify(payload)


@app.route("/api/eth-tracker/news")
def eth_tracker_news():
    ensure_eth_news_fresh(request.args.get("refresh") == "1")
    payload = load_eth_news_cache()
    payload["refreshing"] = ETH_NEWS_RUNNING
    return jsonify(payload)


@app.route("/api/eth-tracker/status")
def eth_tracker_status():
    return jsonify({
        "market": ETH_MARKET_RUNNING,
        "news": ETH_NEWS_RUNNING,
        "marketAgeSeconds": file_age_seconds(ETH_MARKET_FILE),
        "newsAgeSeconds": file_age_seconds(ETH_NEWS_FILE),
    })


@app.route("/api/toss-cache")
def toss_cache():
    # full=1일 때만 무거운 Toss 전체 payload를 로드한다.
    # 요약 조회는 Supabase의 toss:meta만 읽어서 첫 화면 새로고침 병목을 줄인다.
    if request.args.get("full") == "1":
        payload = load_toss_cache()
        return jsonify({
            "ok": bool(payload),
            "cache": payload,
            "ageSeconds": file_age_seconds(TOSS_CACHE_FILE),
            "loadedFrom": payload.get("loadedFrom"),
        })

    meta = supabase_cache_get("toss:meta", None)
    if isinstance(meta, dict):
        item_names = meta.get("itemNames") if isinstance(meta.get("itemNames"), list) else []
        return jsonify({
            "ok": True,
            "ageSeconds": file_age_seconds(TOSS_CACHE_FILE),
            "receivedAt": meta.get("receivedAt"),
            "updatedAt": meta.get("updatedAt"),
            "itemCount": int(meta.get("itemCount") or len(item_names)),
            "itemNames": sorted(str(name) for name in item_names)[:200],
            "detailCacheDir": TOSS_DETAIL_CACHE_DIR,
            "loadedFrom": "supabase_meta",
        })

    payload = load_toss_cache()
    items = payload.get("items") if isinstance(payload.get("items"), dict) else {}
    return jsonify({
        "ok": bool(payload),
        "ageSeconds": file_age_seconds(TOSS_CACHE_FILE),
        "receivedAt": payload.get("receivedAt"),
        "updatedAt": payload.get("updatedAt"),
        "itemCount": len(items),
        "itemNames": sorted(items.keys())[:200],
        "detailCacheDir": TOSS_DETAIL_CACHE_DIR,
        "loadedFrom": payload.get("loadedFrom"),
    })


@app.route("/api/ingest/toss-cache", methods=["POST"])
def ingest_toss_cache():
    if not INGEST_SECRET:
        return jsonify({"ok": False, "error": "INGEST_SECRET is not configured."}), 503
    if not is_valid_ingest_request():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "티커를 입력하세요."}), 400

    payload["receivedAt"] = datetime.now(KST).isoformat(timespec="seconds")
    existing = load_toss_cache()
    merged = merge_toss_cache(existing, payload)

    # 로컬 파일 fallback도 유지하되, 영구 저장은 Supabase app_cache에 우선 수행한다.
    write_json_file(TOSS_CACHE_FILE, merged)
    supabase_saved = save_toss_cache_to_supabase(merged)

    return jsonify({
        "ok": True,
        "receivedAt": merged["receivedAt"],
        "itemCount": len(merged.get("items", {})) if isinstance(merged.get("items"), dict) else None,
        "incomingItemCount": len(payload.get("items", {})) if isinstance(payload.get("items"), dict) else None,
        "detailItemCount": merged.get("detailItemCount", 0),
        "errorCount": len(payload.get("errors", [])) if isinstance(payload.get("errors"), list) else None,
        "supabaseSaved": supabase_saved,
    })


def normalize_toss_symbol(value):
    symbol = str(value or "").strip().upper().replace(" ", "")
    if symbol.endswith(".KS"):
        return symbol[:-3]
    return symbol


def iter_toss_payload_rows(value):
    if isinstance(value, list):
        for row in value:
            if isinstance(row, dict):
                yield row
        return
    if not isinstance(value, dict):
        return

    for key in ("result", "items", "stocks", "prices", "data"):
        nested = value.get(key)
        if nested is value:
            continue
        if isinstance(nested, (list, dict)):
            yielded = False
            for row in iter_toss_payload_rows(nested):
                yielded = True
                yield row
            if yielded:
                return

    list_values = [item for item in value.values() if isinstance(item, list)]
    for nested in list_values:
        yielded = False
        for row in iter_toss_payload_rows(nested):
            yielded = True
            yield row
        if yielded:
            return

    if any(key in value for key in ("symbol", "name", "market", "lastPrice", "price", "tradePrice")):
        yield value


def iter_toss_result_rows(cache):
    items = cache.get("items") or {}
    for item_name, item in items.items():
        if not isinstance(item, dict) or item.get("ok") is False:
            continue
        for row in iter_toss_payload_rows(item):
            yield item_name, row


def find_toss_row(cache, ticker, preferred_fields, item_name_hints=None):
    target = normalize_toss_symbol(ticker)
    item_name_hints = [hint.lower() for hint in (item_name_hints or [])]
    fallback = None
    for item_name, row in iter_toss_result_rows(cache):
        candidates = [row.get(field) for field in preferred_fields]
        candidates.extend([row.get("symbol"), item_name])
        if not any(normalize_toss_symbol(candidate) == target for candidate in candidates if candidate):
            continue
        lowered_name = str(item_name or "").lower()
        if item_name_hints and any(hint in lowered_name for hint in item_name_hints):
            return row
        if fallback is None:
            fallback = row
    return fallback


def normalize_company_search_text(value):
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def display_kr_market(value):
    market = str(value or "").strip()
    return {
        "??": "KOSPI",
        "????": "KOSPI",
        "??????": "KOSPI",
        "???": "KOSPI",
        "???": "KOSDAQ",
        "???": "KONEX",
        "KOSPI": "KOSPI",
        "KOSDAQ": "KOSDAQ",
        "KONEX": "KONEX",
    }.get(market, market or "N/A")


def toss_item_result(cache, item_name):
    item = (cache.get("items") or {}).get(item_name)
    if not isinstance(item, dict) or item.get("ok") is False:
        return None
    data = item.get("data", item)
    if isinstance(data, dict):
        if "result" in data:
            return data.get("result")
        if "items" in data:
            return data.get("items")
        return data
    return data


def normalize_toss_candles(value):
    if isinstance(value, list):
        candles = value
    elif isinstance(value, dict):
        candles = value.get("candles") or value.get("items") or value.get("result") or value.get("data")
    else:
        candles = []
    if not isinstance(candles, list):
        return []
    return [row for row in candles if isinstance(row, dict)]


def load_dart_corp_codes():
    cached = read_json_file(DART_CORP_CODE_FILE, {})
    if isinstance(cached, dict) and cached.get("byStockCode"):
        return cached
    if not DART_API_KEY:
        return {"byStockCode": {}}

    response = requests.get(
        "https://opendart.fss.or.kr/api/corpCode.xml",
        params={"crtfc_key": DART_API_KEY},
        timeout=20,
    )
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        xml_name = archive.namelist()[0]
        xml_bytes = archive.read(xml_name)
    root = ET.fromstring(xml_bytes)
    by_stock_code = {}
    for item in root.findall(".//list"):
        corp_code = (item.findtext("corp_code") or "").strip()
        corp_name = (item.findtext("corp_name") or "").strip()
        stock_code = (item.findtext("stock_code") or "").strip()
        if corp_code and re.fullmatch(r"\d{6}", stock_code or ""):
            by_stock_code[stock_code] = {"corpCode": corp_code, "corpName": corp_name, "stockCode": stock_code}
    payload = {"updatedAt": datetime.now(KST).isoformat(timespec="seconds"), "byStockCode": by_stock_code}
    write_json_file(DART_CORP_CODE_FILE, payload)
    return payload


@app.route("/api/dart-disclosures")
def dart_disclosures():
    ticker = normalize_toss_symbol(request.args.get("ticker", ""))
    if not re.fullmatch(r"\d{6}", ticker or ""):
        return jsonify({"ok": False, "error": "국내 6자리 종목코드를 입력하세요."}), 400
    if not DART_API_KEY:
        return jsonify({"ok": False, "error": "DART_API_KEY가 설정되지 않았습니다.", "items": []}), 503

    try:
        corp_codes = load_dart_corp_codes()
        corp = (corp_codes.get("byStockCode") or {}).get(ticker)
        if not corp:
            return jsonify({"ok": False, "error": "DART corp_code를 찾지 못했습니다.", "items": []}), 404
        today = datetime.now(KST).date()
        begin = today - timedelta(days=int(request.args.get("days", "365") or "365"))
        response = requests.get(
            "https://opendart.fss.or.kr/api/list.json",
            params={
                "crtfc_key": DART_API_KEY,
                "corp_code": corp["corpCode"],
                "bgn_de": begin.strftime("%Y%m%d"),
                "end_de": today.strftime("%Y%m%d"),
                "page_no": 1,
                "page_count": 5,
                "sort": "date",
                "sort_mth": "desc",
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") not in {"000", "013"}:
            return jsonify({"ok": False, "error": data.get("message") or "DART 조회 실패", "items": []}), 502
        items = []
        for row in data.get("list") or []:
            rcept_no = str(row.get("rcept_no") or "")
            items.append({
                "title": row.get("report_nm") or "",
                "corpName": row.get("corp_name") or corp.get("corpName"),
                "date": row.get("rcept_dt") or "",
                "submitter": row.get("flr_nm") or "",
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}" if rcept_no else "",
            })
        return jsonify({"ok": True, "corp": corp, "items": items, "source": "DART OpenAPI"})
    except Exception as exc:
        print(f"DART disclosure lookup failed({ticker}): {exc}", flush=True)
        return jsonify({"ok": False, "error": "네이버 뉴스를 불러오지 못했습니다.", "items": []}), 500


def parse_dart_amount(value):
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "N/A"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        number = float(text)
    except Exception:
        return None
    return -number if negative else number


def normalize_dart_account_text(value):
    return re.sub(r"[\s()\[\]??,./_-]+", "", str(value or "").lower())


def find_dart_account(rows, specs):
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        account_name = normalize_dart_account_text(row.get("account_nm"))
        account_id = normalize_dart_account_text(row.get("account_id"))
        statement = str(row.get("sj_div") or "").upper()
        for priority, spec in enumerate(specs):
            if spec.get("statement") and statement not in spec["statement"]:
                continue
            ids = [normalize_dart_account_text(item) for item in spec.get("ids", [])]
            if ids and not any(item and item in account_id for item in ids):
                continue
            includes = [normalize_dart_account_text(item) for item in spec.get("includes", [])]
            if includes and not all(item in account_name for item in includes):
                continue
            excludes = [normalize_dart_account_text(item) for item in spec.get("excludes", [])]
            if any(item and item in account_name for item in excludes):
                continue
            amount = parse_dart_amount(row.get("thstrm_amount") or row.get("thstrm_add_amount"))
            if amount is None:
                continue
            candidates.append((priority, amount, row.get("account_nm") or "", row.get("account_id") or ""))
            break
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[0])
    _, amount, account_name, account_id = candidates[0]
    return amount, {"accountName": account_name, "accountId": account_id}


DART_FINANCIAL_SPECS = {
    "revenue": [
        {"ids": ["ifrs-full_Revenue"], "statement": {"IS", "CIS"}},
        {"ids": ["ifrs-full_RevenueFromContractsWithCustomersExcludingAssessedTax"], "statement": {"IS", "CIS"}},
        {"includes": ["매출액"], "statement": {"IS", "CIS"}},
        {"includes": ["영업수익"], "statement": {"IS", "CIS"}},
    ],
    "operatingIncome": [
        {"ids": ["dart_OperatingIncomeLoss"], "statement": {"IS", "CIS"}},
        {"includes": ["영업이익"], "statement": {"IS", "CIS"}},
    ],
    "netIncomeControlling": [
        {"ids": ["ifrs-full_ProfitLossAttributableToOwnersOfParent"], "statement": {"IS", "CIS"}},
        {"includes": ["지배기업", "소유주", "당기순이익"], "statement": {"IS", "CIS"}},
        {"includes": ["지배주주", "순이익"], "statement": {"IS", "CIS"}},
        {"includes": ["당기순이익"], "excludes": ["비지배"], "statement": {"IS", "CIS"}},
    ],
    "assets": [
        {"ids": ["ifrs-full_Assets"], "statement": {"BS"}},
        {"includes": ["자산총계"], "statement": {"BS"}},
    ],
    "liabilities": [
        {"ids": ["ifrs-full_Liabilities"], "statement": {"BS"}},
        {"includes": ["부채총계"], "statement": {"BS"}},
    ],
    "equityControlling": [
        {"ids": ["ifrs-full_EquityAttributableToOwnersOfParent"], "statement": {"BS"}},
        {"includes": ["지배기업", "소유주", "자본"], "statement": {"BS"}},
        {"includes": ["지배주주", "지분"], "statement": {"BS"}},
        {"includes": ["자본총계"], "excludes": ["비지배"], "statement": {"BS"}},
    ],
}


def dart_json_request(endpoint, params, timeout=20):
    response = requests.get(f"https://opendart.fss.or.kr/api/{endpoint}", params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_dart_financial_rows(corp_code, year):
    base_params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": "11011",
    }
    last_message = ""
    for fs_div in ("CFS", "OFS"):
        data = dart_json_request("fnlttSinglAcntAll.json", {**base_params, "fs_div": fs_div})
        if data.get("status") == "000" and isinstance(data.get("list"), list):
            return data.get("list") or [], fs_div, data.get("message") or ""
        last_message = data.get("message") or last_message
    return [], None, last_message


def fetch_dart_dividend_per_share(corp_code, year):
    data = dart_json_request(
        "alotMatter.json",
        {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": "11011",
        },
    )
    if data.get("status") not in {"000", "013"}:
        return None, data.get("message") or ""
    for row in data.get("list") or []:
        label = normalize_dart_account_text(row.get("se"))
        stock_kind = normalize_dart_account_text(row.get("stock_knd"))
        if "주당" in label and "현금배당금" in label and ("보통" in stock_kind or not stock_kind):
            return parse_dart_amount(row.get("thstrm")), row.get("se") or ""
    return None, ""


def fetch_dart_common_shares(corp_code, year):
    data = dart_json_request(
        "stockTotqySttus.json",
        {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": "11011",
        },
    )
    if data.get("status") not in {"000", "013"}:
        return None, data.get("message") or ""
    preferred_fields = [
        "distb_stock_co",
        "now_to_isstk_re_co",
        "istc_totqy",
        "issu_stock_totqy",
    ]
    for row in data.get("list") or []:
        label = normalize_dart_account_text(row.get("se"))
        if "보통" not in label:
            continue
        for field in preferred_fields:
            amount = parse_dart_amount(row.get(field))
            if amount:
                return amount, field
    return None, ""


def fetch_naver_year_end_closes(ticker, years):
    clean_years = sorted({int(year) for year in years if year})
    if not clean_years:
        return {}
    cache_key = f"naver-year-end-close:{ticker}:{','.join(map(str, clean_years))}"
    cached = get_cached_value(cache_key, 86400)
    if cached is not None:
        return cached

    closes = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome Safari",
        "Referer": f"https://finance.naver.com/item/main.naver?code={ticker}",
    }
    for year in clean_years:
        try:
            response = requests.get(
                "https://api.finance.naver.com/siseJson.naver",
                params={
                    "symbol": ticker,
                    "requestType": 1,
                    "startTime": f"{year}1201",
                    "endTime": f"{year}1231",
                    "timeframe": "day",
                },
                headers=headers,
                timeout=12,
            )
            response.raise_for_status()
            rows = ast.literal_eval(response.text.strip())
            data_rows = [row for row in rows[1:] if isinstance(row, list) and len(row) >= 5]
            if not data_rows:
                continue
            latest = data_rows[-1]
            close = parse_dart_amount(latest[4])
            date = str(latest[0])
            if close:
                closes[year] = {"close": close, "date": date, "source": "Naver Finance"}
        except Exception as exc:
            print(f"Naver year-end close lookup failed({ticker}, {year}): {exc}", flush=True)
    set_cached_value(cache_key, closes)
    return closes


def clean_naver_numeric_text(value):
    text = BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)
    text = text.replace(",", "").replace("%", "").strip()
    if not text or text in {"-", "N/A"}:
        return None
    return parse_dart_amount(text)


def parse_naver_financial_table(table):
    header_rows = table.select("thead tr")
    if not header_rows:
        return None
    headers = []
    for header_row in header_rows:
        candidate = [cell.get_text(" ", strip=True) for cell in header_row.find_all(["th", "td"])]
        if any("." in item or "(E)" in item or "E" in item for item in candidate):
            headers = candidate
            break
    if not headers:
        headers = [cell.get_text(" ", strip=True) for cell in header_rows[0].find_all(["th", "td"])]
    headers = [item for item in headers if item]
    if not headers:
        return None
    values_by_label = {}
    for row in table.select("tbody tr"):
        title_cell = row.find("th")
        if not title_cell:
            continue
        label = normalize_dart_account_text(title_cell.get_text(" ", strip=True))
        values_by_label[label] = [clean_naver_numeric_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
    return headers, values_by_label


def pick_naver_financial_value(values_by_label, labels, index):
    for label in labels:
        normalized = normalize_dart_account_text(label)
        for key, values in values_by_label.items():
            if normalized != key and normalized not in key and key not in normalized:
                continue
            if values and index < len(values):
                value = values[index]
                if value is not None:
                    return value
    return None


def fetch_naver_annual_consensus(ticker):
    cache_key = f"naver-annual-consensus:{ticker}"
    cached = get_cached_value(cache_key, 86400)
    if cached is not None:
        return cached
    try:
        response = requests.get(
            f"https://finance.naver.com/item/main.naver?code={ticker}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome Safari",
                "Referer": f"https://finance.naver.com/item/main.naver?code={ticker}",
            },
            timeout=15,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "cp949"
        soup = BeautifulSoup(response.text, "html.parser")
        parsed = None
        for table in soup.select("table"):
            text = table.get_text(" ", strip=True)
            if "PER" in text and "PBR" in text and "2026.12" in text:
                parsed = parse_naver_financial_table(table)
                break
        if not parsed:
            set_cached_value(cache_key, None)
            return None
        headers, values_by_label = parsed
        forecast_index = None
        forecast_label = ""
        for index, header in enumerate(headers[:4]):
            if "(E)" in header or "E" in header:
                forecast_index = index
                forecast_label = header
                break
        if forecast_index is None:
            set_cached_value(cache_key, None)
            return None
        multiplier = 100_000_000
        result = {
            "year": re.sub(r"\D", "", forecast_label)[:4] + "F" if re.sub(r"\D", "", forecast_label) else "Forecast",
            "revenue": None,
            "operatingIncome": None,
            "netIncomeControlling": None,
            "dividendPerShare": None,
            "dividendYield": None,
            "peRatio": None,
            "pbRatio": None,
            "source": "Naver Finance consensus",
        }
        revenue = pick_naver_financial_value(values_by_label, ["매출액"], forecast_index)
        operating_income = pick_naver_financial_value(values_by_label, ["영업이익"], forecast_index)
        net_income = pick_naver_financial_value(values_by_label, ["당기순이익", "지배주주순이익"], forecast_index)
        dividend = pick_naver_financial_value(values_by_label, ["주당배당금"], forecast_index)
        per = pick_naver_financial_value(values_by_label, ["PER"], forecast_index)
        pbr = pick_naver_financial_value(values_by_label, ["PBR"], forecast_index)
        result.update({
            "revenue": revenue * multiplier if revenue is not None else None,
            "operatingIncome": operating_income * multiplier if operating_income is not None else None,
            "netIncomeControlling": net_income * multiplier if net_income is not None else None,
            "dividendPerShare": dividend,
            "dividendYield": None,
            "peRatio": per,
            "pbRatio": pbr,
        })
        set_cached_value(cache_key, result)
        return result
    except Exception as exc:
        print(f"Naver annual consensus lookup failed({ticker}): {exc}", flush=True)
        set_cached_value(cache_key, None)
        return None


def clean_news_text(value):
    return BeautifulSoup(html_lib.unescape(str(value or "")), "html.parser").get_text(" ", strip=True)


def infer_news_publisher(url):
    host = (urlparse(str(url or "")).netloc or "").lower()
    host = re.sub(r"^m\.", "", re.sub(r"^www\.", "", host))
    if not host:
        return "Naver"
    known = {
        "edaily.co.kr": "이데일리",
        "mk.co.kr": "매일경제",
        "hankyung.com": "한국경제",
        "yna.co.kr": "연합뉴스",
        "newsis.com": "뉴시스",
        "fnnews.com": "파이낸셜뉴스",
        "sedaily.com": "서울경제",
        "biz.chosun.com": "조선비즈",
        "chosun.com": "조선일보",
        "joongang.co.kr": "중앙일보",
        "donga.com": "동아일보",
        "heraldcorp.com": "헤럴드경제",
        "mt.co.kr": "머니투데이",
        "etoday.co.kr": "이투데이",
        "asiae.co.kr": "아시아경제",
        "etnews.com": "전자신문",
        "zdnet.co.kr": "지디넷코리아",
    }
    for domain, label in known.items():
        if host == domain or host.endswith(f".{domain}"):
            return label
    parts = host.split(".")
    return parts[-3] if len(parts) >= 3 and parts[-2] in {"co", "com", "net", "or"} else parts[0]


def hyperliquid_info_request(payload):
    response = requests.post(
        HYPERLIQUID_INFO_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=12,
    )
    response.raise_for_status()
    return response.json()



DEFAULT_HYPERLIQUID_ASSET_META = {
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
    "XYZ:CL": {
        "name": "WTI Oil",
        "description": "CL tracks the value of 1 barrel of West Texas Intermediate (WTI) Light Sweet Crude Oil. WTI is a primary global benchmark for oil prices.",
    },
    "XYZ:GOLD": {"name": "Gold", "description": "Tracks the price of gold as a global precious-metals benchmark."},
    "XYZ:SILVER": {"name": "Silver", "description": "Tracks the price of silver as a global precious-metals benchmark."},
    "XYZ:SP500": {"name": "S&P 500", "description": "Tracks the S&P 500, a broad benchmark for large-cap U.S. equities."},
    "XYZ:XYZ100": {"name": "Nasdaq 100", "description": "Tracks Nasdaq 100-style U.S. growth and technology equity exposure."},
    "XYZ:KR200": {"name": "KOSPI 200", "description": "Tracks Korea's KOSPI 200 large-cap equity benchmark."},
    "XYZ:DRAM": {"name": "DRAM", "description": "Tracks DRAM memory market pricing as a semiconductor cycle indicator."},
    "XYZ:HOOD": {"name": "Robinhood", "description": "Tracks Robinhood Markets synthetic equity market pricing on Hyperliquid."},
    "XYZ:SPCX": {"name": "SPCX", "description": "Tracks the SPCX global market listed on Hyperliquid."},
    "XYZ:TSLA": {"name": "Tesla", "description": "Tracks Tesla synthetic equity market pricing on Hyperliquid."},
    "XYZ:NVDA": {"name": "NVIDIA", "description": "Tracks NVIDIA synthetic equity market pricing on Hyperliquid."},
    "XYZ:AAPL": {"name": "Apple", "description": "Tracks Apple synthetic equity market pricing on Hyperliquid."},
    "XYZ:MSFT": {"name": "Microsoft", "description": "Tracks Microsoft synthetic equity market pricing on Hyperliquid."},
    "XYZ:GOOGL": {"name": "Alphabet", "description": "Tracks Alphabet synthetic equity market pricing on Hyperliquid."},
    "XYZ:AMZN": {"name": "Amazon", "description": "Tracks Amazon synthetic equity market pricing on Hyperliquid."},
    "XYZ:META": {"name": "Meta Platforms", "description": "Tracks Meta Platforms synthetic equity market pricing on Hyperliquid."},
    "XYZ:AMD": {"name": "AMD", "description": "Tracks AMD synthetic equity market pricing on Hyperliquid."},
    "XYZ:INTC": {"name": "Intel", "description": "Tracks Intel synthetic equity market pricing on Hyperliquid."},
    "XYZ:PLTR": {"name": "Palantir", "description": "Tracks Palantir synthetic equity market pricing on Hyperliquid."},
    "XYZ:COIN": {"name": "Coinbase", "description": "Tracks Coinbase synthetic equity market pricing on Hyperliquid."},
    "XYZ:ORCL": {"name": "Oracle", "description": "Tracks Oracle synthetic equity market pricing on Hyperliquid."},
    "XYZ:MU": {"name": "Micron", "description": "Tracks Micron synthetic equity market pricing on Hyperliquid."},
    "XYZ:TSM": {"name": "TSMC", "description": "Tracks TSMC synthetic equity market pricing on Hyperliquid."},
    "XYZ:MSTR": {"name": "Strategy", "description": "Tracks Strategy synthetic equity market pricing on Hyperliquid."},
    "XYZ:NFLX": {"name": "Netflix", "description": "Tracks Netflix synthetic equity market pricing on Hyperliquid."},
    "XYZ:COST": {"name": "Costco", "description": "Tracks Costco synthetic equity market pricing on Hyperliquid."},
    "XYZ:LLY": {"name": "Eli Lilly", "description": "Tracks Eli Lilly synthetic equity market pricing on Hyperliquid."},
    "XYZ:BABA": {"name": "Alibaba", "description": "Tracks Alibaba synthetic equity market pricing on Hyperliquid."},
    "XYZ:RIVN": {"name": "Rivian", "description": "Tracks Rivian synthetic equity market pricing on Hyperliquid."},
    "XYZ:CRCL": {"name": "Circle", "description": "Tracks Circle synthetic equity market pricing on Hyperliquid."},
    "XYZ:SKHX": {"name": "SK hynix", "description": "Tracks SK hynix synthetic equity market pricing on Hyperliquid."},
    "XYZ:JPY": {"name": "Japanese Yen", "description": "Tracks Japanese yen foreign-exchange market pricing on Hyperliquid."},
    "XYZ:EUR": {"name": "Euro", "description": "Tracks euro foreign-exchange market pricing on Hyperliquid."},
    "XYZ:BRENTOIL": {"name": "Brent Oil", "description": "Tracks Brent crude oil market pricing on Hyperliquid."},
    "XYZ:NATGAS": {"name": "Natural Gas", "description": "Tracks natural gas market pricing on Hyperliquid."},
    "XYZ:COPPER": {"name": "Copper", "description": "Tracks copper market pricing on Hyperliquid."},
    "XYZ:ALUMINIUM": {"name": "Aluminium", "description": "Tracks aluminium market pricing on Hyperliquid."},
}


def merge_hyperliquid_asset_meta(meta, source):
    if not isinstance(source, dict):
        return meta
    items = source.get("items") if isinstance(source.get("items"), dict) else source
    if not isinstance(items, dict):
        return meta
    for key, value in items.items():
        normalized = str(key or "").strip().upper()
        if not normalized or not isinstance(value, dict):
            continue
        item = dict(meta.get(normalized, {}))
        for field in (
            "name",
            "displayName",
            "description",
            "instrument",
            "underlying",
            "maxLeverage",
            "source",
            "sourceUrl",
            "assetClass",
            "iconUrl",
            "iconSource",
            "iconLicense",
        ):
            raw_value = value.get(field)
            if raw_value is None:
                continue
            cleaned = str(raw_value).strip() if isinstance(raw_value, str) else raw_value
            if cleaned:
                item[field] = cleaned[:800] if isinstance(cleaned, str) else cleaned
        if item.get("displayName") and not item.get("name"):
            item["name"] = item["displayName"]
        if item:
            meta[normalized] = item
    return meta


def load_hyperliquid_asset_meta_file():
    try:
        if not os.path.exists(HYPERLIQUID_ASSET_META_FILE):
            return None
        with open(HYPERLIQUID_ASSET_META_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        print(f"Hyperliquid asset meta file load failed: {exc}", flush=True)
        return None


def load_hyperliquid_asset_meta():
    meta = {key: dict(value) for key, value in DEFAULT_HYPERLIQUID_ASSET_META.items()}
    cached = get_cached_value("hyperliquid-asset-meta", 300)
    if isinstance(cached, dict):
        return cached

    meta = merge_hyperliquid_asset_meta(meta, load_hyperliquid_asset_meta_file())
    remote = supabase_cache_get("hyperliquid:asset_meta", None)
    if isinstance(remote, dict):
        meta = merge_hyperliquid_asset_meta(meta, remote)
    elif supabase_enabled():
        supabase_cache_upsert("hyperliquid:asset_meta", {"items": meta, "updatedAt": datetime.now(KST).isoformat()})
    set_cached_value("hyperliquid-asset-meta", meta)
    return meta


HYPERLIQUID_META_ENRICH_LOCK = threading.Lock()


def hyperliquid_meta_key(coin, dex=""):
    normalized = str(coin or "").strip().upper()
    if str(dex or "").strip().lower() == "xyz" and normalized and not normalized.startswith("XYZ:"):
        return f"XYZ:{normalized}"
    return normalized


def hyperliquid_readable_name(symbol):
    base = str(symbol or "").split(":")[-1].strip()
    if not base:
        return "Hyperliquid Market"
    return re.sub(r"[_-]+", " ", base).strip()


def hyperliquid_name_from_description(description):
    cleaned = re.sub(r"\s+", " ", str(description or "")).strip()
    match = re.match(r"^([A-Z][A-Za-z0-9 .&'/-]{1,60}?)\s+(?:is|are)\b", cleaned)
    return match.group(1).strip() if match else ""


def fetch_hyperliquid_spot_names():
    names = {}
    try:
        payload = hyperliquid_info_request({"type": "spotMeta"})
        for token in payload.get("tokens", []) if isinstance(payload, dict) else []:
            symbol = str(token.get("name") or "").strip().upper()
            full_name = str(token.get("fullName") or "").strip()
            if symbol and full_name:
                names[symbol] = full_name
    except Exception as exc:
        print(f"Hyperliquid spot name lookup failed: {exc}", flush=True)
    return names


def fetch_coingecko_asset_meta(symbols):
    symbols = sorted({str(symbol or "").strip().lower() for symbol in symbols if str(symbol or "").strip()})
    if not symbols:
        return {}
    result = {}
    for start in range(0, len(symbols), 40):
        chunk = symbols[start:start + 40]
        try:
            response = requests.get(
                COINGECKO_MARKETS_URL,
                params={
                    "vs_currency": "usd",
                    "symbols": ",".join(chunk),
                    "per_page": "250",
                    "page": "1",
                    "sparkline": "false",
                },
                headers={"Accept": "application/json", "User-Agent": "BIKResearch/1.0"},
                timeout=10,
            )
            response.raise_for_status()
            rows = response.json()
        except Exception as exc:
            print(f"CoinGecko asset meta lookup failed: {exc}", flush=True)
            continue
        for item in rows if isinstance(rows, list) else []:
            symbol = str(item.get("symbol") or "").strip().lower()
            if symbol not in chunk:
                continue
            rank = safe_number(item.get("market_cap_rank"), default=None)
            current_rank = result.get(symbol, {}).get("_rank")
            if symbol in result and current_rank is not None and (rank is None or current_rank <= rank):
                continue
            result[symbol] = {
                "name": str(item.get("name") or "").strip(),
                "iconUrl": str(item.get("image") or "").strip(),
                "_rank": rank,
            }
    for item in result.values():
        item.pop("_rank", None)
    return result


def fetch_trade_xyz_asset_meta():
    try:
        from sync_hyperliquid_asset_meta import DOC_URL, build_asset_meta

        response = requests.get(DOC_URL, timeout=12, headers={"User-Agent": "Mozilla/5.0 BIKResearch/1.0"})
        response.raise_for_status()
        return build_asset_meta(response.text)
    except Exception as exc:
        print(f"trade.xyz asset meta lookup failed: {exc}", flush=True)
        return {}


def verified_hyperliquid_icon_url(coin):
    raw_coin = str(coin or "").strip()
    if not raw_coin:
        return ""
    icon_url = f"{HYPERLIQUID_ICON_BASE_URL}/{quote(raw_coin, safe='')}.svg"
    try:
        response = requests.get(icon_url, timeout=8, headers={"User-Agent": "Mozilla/5.0 BIKResearch/1.0"})
        content_type = str(response.headers.get("content-type") or "").lower()
        if response.status_code == 200 and "svg" in content_type and "<svg" in response.text[:600].lower():
            return icon_url
    except Exception:
        pass
    return ""


def enrich_hyperliquid_asset_meta(rows, current_meta):
    missing_rows = []
    for row in rows:
        key = hyperliquid_meta_key(row.get("coin"), row.get("dex"))
        existing = current_meta.get(key, {}) if key else {}
        local_icon_url = hyperliquid_local_icon_url(row.get("coin"), row.get("dex"))
        local_icon_mismatch = bool(local_icon_url and existing.get("iconUrl") != local_icon_url)
        if key and (
            not existing.get("name")
            or not existing.get("description")
            or not existing.get("iconUrl")
            or local_icon_mismatch
        ):
            missing_rows.append(row)
    if not missing_rows:
        return current_meta

    with HYPERLIQUID_META_ENRICH_LOCK:
        latest_meta = load_hyperliquid_asset_meta()
        targets = []
        for row in missing_rows:
            key = hyperliquid_meta_key(row.get("coin"), row.get("dex"))
            existing = latest_meta.get(key, {}) if key else {}
            local_icon_url = hyperliquid_local_icon_url(row.get("coin"), row.get("dex"))
            local_icon_mismatch = bool(local_icon_url and existing.get("iconUrl") != local_icon_url)
            if key and (
                not existing.get("name")
                or not existing.get("description")
                or not existing.get("iconUrl")
                or local_icon_mismatch
            ):
                targets.append((row, key))
        if not targets:
            return latest_meta

        crypto_symbols = [
            str(row.get("coin") or "").split(":")[-1]
            for row, _ in targets
            if str(row.get("dex") or "").lower() != "xyz"
        ]
        spot_names = fetch_hyperliquid_spot_names() if crypto_symbols else {}
        coingecko_meta = fetch_coingecko_asset_meta(crypto_symbols)
        trade_meta = fetch_trade_xyz_asset_meta() if any(
            str(row.get("dex") or "").lower() == "xyz" for row, _ in targets
        ) else {}

        for row, key in targets:
            coin = str(row.get("coin") or "").strip()
            base = coin.split(":")[-1].upper()
            is_global = str(row.get("dex") or "").lower() == "xyz" or key.startswith("XYZ:")
            existing = dict(latest_meta.get(key, {}))
            documented = trade_meta.get(key, {}) if is_global else {}
            coin_meta = coingecko_meta.get(base.lower(), {}) if not is_global else {}
            existing_name = str(existing.get("name") or "").strip()
            existing_name_is_symbol = existing_name.upper() == base
            if is_global:
                name = documented.get("name") or existing_name or hyperliquid_readable_name(base)
            else:
                name = (
                    ("" if existing_name_is_symbol else existing_name)
                    or spot_names.get(base)
                    or coin_meta.get("name")
                    or hyperliquid_name_from_description(existing.get("description"))
                    or existing_name
                    or hyperliquid_readable_name(base)
                )
            description = existing.get("description") or documented.get("description")
            if not description:
                if is_global:
                    description = f"{name} \uac00\uaca9\uc744 \ucd94\uc885\ud558\ub294 Hyperliquid \uae00\ub85c\ubc8c \ubb34\uae30\ud55c \uc120\ubb3c \uc2dc\uc7a5\uc785\ub2c8\ub2e4."
                else:
                    description = f"{name} ({base})\uc758 Hyperliquid \ubb34\uae30\ud55c \uc120\ubb3c \uc2dc\uc7a5\uc785\ub2c8\ub2e4."
            needs_core_meta = not existing.get("name") or not existing.get("description")
            local_icon_url = hyperliquid_local_icon_url(coin, row.get("dex"))
            icon_url = (
                local_icon_url
                or existing.get("iconUrl")
                or coin_meta.get("iconUrl")
                or (verified_hyperliquid_icon_url(coin) if needs_core_meta else "")
                or f"/api/hyperliquid-icon/{quote(coin, safe='')}"
            )
            latest_meta[key] = {
                **existing,
                **documented,
                "name": name,
                "description": description,
                "assetClass": "global" if is_global else "crypto",
                "source": documented.get("source") or ("CoinGecko + Hyperliquid" if coin_meta else "Hyperliquid"),
                "sourceUrl": documented.get("sourceUrl") or f"https://app.hyperliquid.xyz/trade/{quote(coin, safe=':')}",
            }
            if icon_url:
                latest_meta[key]["iconUrl"] = icon_url
                latest_meta[key]["iconSource"] = (
                    "local"
                    if local_icon_url == icon_url
                    else existing.get("iconSource")
                    or (
                        "CoinGecko"
                        if coin_meta.get("iconUrl") == icon_url
                        else "generated"
                        if icon_url.startswith("/api/hyperliquid-icon/")
                        else "Hyperliquid"
                    )
                )

        payload = {
            "items": latest_meta,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "source": "automatic",
        }
        supabase_cache_upsert("hyperliquid:asset_meta", payload)
        set_cached_value("hyperliquid-asset-meta", latest_meta)
        return latest_meta


def hyperliquid_local_icon_url(symbol, dex=""):
    raw = str(symbol or "").strip()
    if not raw:
        return ""
    normalized = raw.upper()
    candidates = []
    if normalized.startswith("XYZ:"):
        base = normalized.replace("XYZ:", "", 1)
        candidates.append(f"xyz-{base.lower()}.svg")
        candidates.append(f"{base.lower()}.svg")
    elif str(dex or "").lower() == "xyz":
        candidates.append(f"xyz-{normalized.lower()}.svg")
        candidates.append(f"{normalized.lower()}.svg")
    else:
        candidates.append(f"{normalized.lower()}.svg")
    for filename in candidates:
        if re.fullmatch(r"[a-z0-9_.:-]+\.svg", filename or "") and os.path.exists(os.path.join(HYPERLIQUID_ICON_DIR, filename)):
            return f"/icons/{filename}"
    return ""


def apply_hyperliquid_asset_meta(row, asset_meta):
    coin = str((row or {}).get("coin") or "").upper()
    dex = str((row or {}).get("dex") or "").lower()
    keys = [coin]
    if dex == "xyz" and not coin.startswith("XYZ:"):
        keys.append(f"XYZ:{coin}")
    if coin.startswith("XYZ:"):
        keys.append(coin.replace("XYZ:", "", 1))
    meta = next((asset_meta.get(key) for key in keys if asset_meta.get(key)), {})
    if meta:
        row["assetName"] = meta.get("name") or ""
        row["assetDescription"] = meta.get("description") or ""
        row["assetIconUrl"] = meta.get("iconUrl") or ""
        row["assetIconSource"] = meta.get("iconSource") or ""
    local_icon_url = hyperliquid_local_icon_url(coin, dex)
    if local_icon_url:
        row["assetIconUrl"] = local_icon_url
        row["assetIconSource"] = "local"
    return row
def build_hyperliquid_rows_for_dex(dex_name=None):
    dex_name = str(dex_name or "").strip()
    mids_payload = {"type": "allMids"}
    meta_request = {"type": "metaAndAssetCtxs"}
    if dex_name:
        mids_payload["dex"] = dex_name
        meta_request["dex"] = dex_name
    mids = hyperliquid_info_request(mids_payload)
    meta_payload = hyperliquid_info_request(meta_request)
    meta = meta_payload[0] if isinstance(meta_payload, list) and meta_payload else {}
    ctxs = meta_payload[1] if isinstance(meta_payload, list) and len(meta_payload) > 1 else []
    universe = meta.get("universe") if isinstance(meta, dict) else []
    if not isinstance(universe, list):
        universe = []
    if not isinstance(ctxs, list):
        ctxs = []

    asset_meta = load_hyperliquid_asset_meta()
    rows = []
    for index, asset in enumerate(universe):
        if not isinstance(asset, dict):
            continue
        coin = str(asset.get("name") or "").strip()
        if not coin:
            continue
        ctx = ctxs[index] if index < len(ctxs) and isinstance(ctxs[index], dict) else {}
        mid = safe_number(mids.get(coin) if isinstance(mids, dict) else None, default=None)
        if mid is None:
            mid = safe_number(first_present(ctx, ["midPx", "markPx", "oraclePx"]), default=None)
        prev = safe_number(first_present(ctx, ["prevDayPx", "prevDayPrice", "prevPx"]), default=None)
        change_pct = round(((mid - prev) / prev) * 100, 2) if mid is not None and prev else None
        row = {
            "coin": coin,
            "dex": dex_name or "main",
            "price": mid,
            "prevDayPrice": prev,
            "changePct": change_pct,
            "volume24h": safe_number(first_present(ctx, ["dayNtlVlm", "volume24h", "dayBaseVlm"]), default=None),
            "openInterest": safe_number(first_present(ctx, ["openInterest", "openInterestUsd"]), default=None),
            "funding": safe_number(first_present(ctx, ["funding", "fundingRate"]), default=None),
            "maxLeverage": safe_number(asset.get("maxLeverage"), default=None),
            "onlyIsolated": bool(asset.get("onlyIsolated")) if "onlyIsolated" in asset else None,
        }
        rows.append(row)
    asset_meta = enrich_hyperliquid_asset_meta(rows, asset_meta)
    rows = [apply_hyperliquid_asset_meta(row, asset_meta) for row in rows]
    return rows


@app.route("/api/hyperliquid-markets")
def hyperliquid_markets():
    cached = get_cached_value("hyperliquid-markets", 90)
    if cached:
        return jsonify(cached)
    try:
        rows = []
        seen = set()
        dexes = HYPERLIQUID_DEXES or [""]
        for dex_name in dexes:
            try:
                for row in build_hyperliquid_rows_for_dex(dex_name):
                    key = str(row.get("coin") or "").upper()
                    if key and key not in seen:
                        seen.add(key)
                        rows.append(row)
            except Exception as dex_exc:
                print(f"Hyperliquid dex lookup failed ({dex_name or 'main'}): {dex_exc}", flush=True)
        if not rows:
            raise RuntimeError("No Hyperliquid markets returned")

        preferred_order = ["BTC", "ETH", "HYPE", "SOL", "XYZ:SKHX", "XYZ:NVDA", "XYZ:TSLA", "XYZ:AAPL", "XYZ:AMD", "SPX", "GOLD", "OIL", "HYNIX"]
        by_coin = {row["coin"].upper(): row for row in rows}
        featured = [by_coin[coin] for coin in preferred_order if coin in by_coin]
        if len(featured) < 8:
            leftovers = [row for row in rows if row not in featured]
            leftovers.sort(key=lambda item: item.get("volume24h") or 0, reverse=True)
            featured.extend(leftovers[: max(0, 8 - len(featured))])
        rows.sort(key=lambda item: item.get("volume24h") or 0, reverse=True)
        payload = {
            "ok": True,
            "source": "Hyperliquid",
            "asOf": datetime.now(KST).isoformat(),
            "featured": featured[:12],
            "markets": rows,
            "count": len(rows),
            "note": "Hyperliquid perpetual futures and synthetic market data",
        }
        set_cached_value("hyperliquid-markets", payload)
        return jsonify(payload)
    except Exception as exc:
        print(f"Hyperliquid market lookup failed: {exc}", flush=True)
        fallback = get_cached_value("hyperliquid-markets", 3600)
        if fallback:
            fallback = {**fallback, "stale": True, "warning": "?? Hyperliquid ??? ???? ?? ???? ?????."}
            return jsonify(fallback)
        return jsonify({"ok": False, "error": "Hyperliquid ???? ???? ?????.", "markets": [], "featured": []}), 502


def parse_hyperdash_flow_message(message_text, hrefs=None, created_at=None):
    raw = re.sub(r"\s+", " ", str(message_text or "")).strip()
    if not raw or "Liquidated" not in raw:
        return None
    hash_chars = "#" + chr(0xFF03)
    match = re.search(
        r"[" + re.escape(hash_chars) + r"]([^\s:]+)(?:\s*:\s*([^\s]+))?\s+Liquidated\s+(Short|Long):\s*\$?([0-9.,]+\s*[KMB]?)\s+at\s+\$?([0-9.,]+)",
        raw,
        re.IGNORECASE,
    )
    if not match:
        return None

    base_symbol = match.group(1).strip()
    suffix_symbol = (match.group(2) or "").strip()
    symbol = f"{base_symbol}:{suffix_symbol}" if suffix_symbol else base_symbol
    side = match.group(3).strip().lower()
    amount_text = re.sub(r"\s+", "", match.group(4).strip())
    price_text = match.group(5).strip()
    hrefs = hrefs or []
    dash_url = next((url for url in hrefs if "/address/" in url), "")
    chart_url = next((url for url in hrefs if "/asset/" in url), "")
    display_symbol = re.sub(r"^xyz:", "", symbol, flags=re.IGNORECASE)
    created_at_value = created_at or datetime.now(timezone.utc).isoformat()
    return {
        "id": f"{symbol}:{side}:{amount_text}:{price_text}:{created_at_value}",
        "symbol": symbol,
        "displaySymbol": display_symbol,
        "marketType": "global" if symbol.lower().startswith("xyz:") else "coin",
        "side": side,
        "sideLabel": "\uC20F \uCCAD\uC0B0" if side == "short" else "\uB871 \uCCAD\uC0B0" if side == "long" else "\uCCAD\uC0B0",
        "color": "green" if side == "short" else "red" if side == "long" else "slate",
        "amount": f"${amount_text}",
        "price": f"${price_text}",
        "amountRaw": amount_text,
        "priceRaw": price_text,
        "dashUrl": dash_url,
        "chartUrl": chart_url,
        "createdAt": created_at_value,
        "raw": raw[:280],
    }

def hyperdash_sort_key(item):
    try:
        value = str((item or {}).get("createdAt") or "")
        if value:
            return parsedate_to_datetime(value).timestamp() if "," in value else datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        pass
    return 0


def fetch_hyperdash_flows(limit=5, force=False):
    cached = None if force else get_cached_value("hyperdash-flows", 30)
    if cached:
        return cached
    response = requests.get(
        HYPERDASH_FLOWS_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome Safari",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        },
        timeout=10,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    items = []
    seen = set()
    for wrap in soup.select(".tgme_widget_message_wrap"):
        body = wrap.select_one(".tgme_widget_message_text")
        if not body:
            continue
        hrefs = [a.get("href") or "" for a in body.select("a[href]")]
        time_tag = wrap.select_one("time[datetime]")
        created_at = time_tag.get("datetime") if time_tag else ""
        item = parse_hyperdash_flow_message(body.get_text(" ", strip=True), hrefs, created_at)
        if item and item["id"] not in seen:
            seen.add(item["id"])
            items.append(item)
    if not items:
        for body in soup.select(".tgme_widget_message_text"):
            hrefs = [a.get("href") or "" for a in body.select("a[href]")]
            item = parse_hyperdash_flow_message(body.get_text(" ", strip=True), hrefs, "")
            if item and item["id"] not in seen:
                seen.add(item["id"])
                items.append(item)

    items.sort(key=hyperdash_sort_key, reverse=True)
    payload = {
        "ok": True,
        "source": "t.me/hyperdashflows",
        "asOf": datetime.now(KST).isoformat(),
        "updatedAt": datetime.now(KST).isoformat(),
        "cacheSeconds": 30,
        "items": items[:limit],
    }
    set_cached_value("hyperdash-flows", payload)
    save_app_cache_payload("hyperdash:flows", payload)
    return payload


@app.route("/api/hyperdash-flows")
def hyperdash_flows():
    try:
        limit = max(5, min(30, int(request.args.get("limit", "5") or "5")))
        force = request.args.get("refresh") == "1"
        return jsonify(fetch_hyperdash_flows(limit, force=force))
    except Exception as exc:
        print(f"Hyperdash flows lookup failed: {exc}", flush=True)
        fallback = get_cached_value("hyperdash-flows", 3600) or load_app_cache_payload("hyperdash:flows", fallback=None)
        if fallback:
            return jsonify({**fallback, "stale": True, "warning": "\u0048yperdash \uccad\uc0b0 \uc54c\ub9bc \ucd5c\uc2e0 \uc870\ud68c\uc5d0 \uc2e4\ud328\ud574 \uce90\uc2dc\ub97c \ud45c\uc2dc\ud569\ub2c8\ub2e4."})
        return jsonify({"ok": False, "error": "\u0048yperdash \uccad\uc0b0 \uc54c\ub9bc\uc744 \ubd88\ub7ec\uc624\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.", "items": []}), 502


@app.route("/api/naver-news")
def naver_news():
    ticker = normalize_toss_symbol(request.args.get("ticker", ""))
    name = str(request.args.get("name", "") or "").strip()
    if not ticker and not name:
        return jsonify({"ok": False, "error": "검색할 종목을 입력하세요.", "items": []}), 400
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return jsonify({"ok": False, "error": "NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 설정되지 않았습니다.", "items": []}), 503

    query = name or ticker
    cache_key = f"naver-news:{ticker}:{query}"
    cached = get_cached_value(cache_key, 900)
    if cached:
        return jsonify(cached)

    try:
        response = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers={
                "X-Naver-Client-Id": NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            },
            params={
                "query": f"{query} {ticker}".strip(),
                "display": 5,
                "start": 1,
                "sort": "date",
            },
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
        items = []
        for row in data.get("items") or []:
            title = clean_news_text(row.get("title"))
            summary = clean_news_text(row.get("description"))
            original = row.get("originallink") or row.get("link") or ""
            link = row.get("link") or original
            items.append({
                "title": title,
                "summary": summary,
                "url": original or link,
                "naverUrl": link,
                "source": infer_news_publisher(original or link),
                "publishedAt": row.get("pubDate") or "",
            })
        payload = {"ok": True, "items": items, "source": "Naver Search API"}
        set_cached_value(cache_key, payload)
        return jsonify(payload)
    except Exception as exc:
        print(f"Naver news lookup failed({ticker}, {query}): {exc}", flush=True)
        return jsonify({"ok": False, "error": "네이버 뉴스를 불러오지 못했습니다.", "items": []}), 500


@app.route("/api/dart-financials")
def dart_financials():
    ticker = normalize_toss_symbol(request.args.get("ticker", ""))
    try:
        years_requested = int(request.args.get("years", "5") or "5")
    except Exception:
        years_requested = 5
    years_requested = max(1, min(5, years_requested))
    if not re.fullmatch(r"\d{6}", ticker or ""):
        return jsonify({"ok": False, "error": "국내 6자리 종목코드를 입력하세요.", "years": []}), 400
    if not DART_API_KEY:
        return jsonify({"ok": False, "error": "DART_API_KEY가 설정되지 않았습니다.", "years": []}), 503

    cache_key = f"dart-financials:v2:{ticker}:{years_requested}"
    cached = get_cached_value(cache_key, 86400)
    if cached:
        return jsonify(cached)
    stored = supabase_cache_get(cache_key, None)
    if isinstance(stored, dict) and stored.get("ok"):
        stored["loadedFrom"] = stored.get("loadedFrom") or "supabase"
        set_cached_value(cache_key, stored)
        return jsonify(stored)

    try:
        corp_codes = load_dart_corp_codes()
        corp = (corp_codes.get("byStockCode") or {}).get(ticker)
        if not corp:
            return jsonify({"ok": False, "error": "DART corp_code를 찾지 못했습니다.", "years": []}), 404

        cache = load_toss_cache()
        price_row = find_toss_row(cache, ticker, ["symbol"], ["kr_prices", "price", "prices"])
        stock_info_row = find_toss_row(cache, ticker, ["symbol"], ["kr_stocks", "stock", "stocks", "info"]) or {}
        price = safe_number(first_present(price_row or {}, ["lastPrice", "price", "tradePrice", "currentPrice", "close"]), default=None)
        toss_shares = safe_number(first_present(stock_info_row, ["commonSharesOutstanding", "sharesOutstanding", "issuedShares", "listedShares", "numberOfListedShares"]), 0, default=None)

        current_year = datetime.now(KST).year
        candidate_years = list(range(current_year - 7, current_year))
        year_end_closes = fetch_naver_year_end_closes(ticker, candidate_years)
        financial_years = []
        warnings = []
        for year in range(current_year - 1, current_year - 8, -1):
            if len(financial_years) >= years_requested:
                break
            rows, fs_div, message = fetch_dart_financial_rows(corp["corpCode"], year)
            if not rows:
                if message:
                    warnings.append(f"{year}: {message}")
                continue
            metrics = {}
            account_sources = {}
            for key, specs in DART_FINANCIAL_SPECS.items():
                amount, source = find_dart_account(rows, specs)
                metrics[key] = amount
                if source:
                    account_sources[key] = source
            if not any(value is not None for value in metrics.values()):
                continue
            dividend, dividend_source = fetch_dart_dividend_per_share(corp["corpCode"], year)
            shares, shares_source = fetch_dart_common_shares(corp["corpCode"], year)
            if not shares:
                shares = toss_shares
                shares_source = "Toss OpenAPI"
            close_info = year_end_closes.get(year) or {}
            year_end_close = close_info.get("close")
            market_cap = year_end_close * shares if year_end_close and shares else None
            if market_cap is None and price and shares:
                market_cap = price * shares
                close_info = {"close": price, "source": "Toss OpenAPI current price"}
            net_income = metrics.get("netIncomeControlling")
            equity = metrics.get("equityControlling")
            financial_years.append({
                "year": year,
                "fsDiv": fs_div,
                "revenue": metrics.get("revenue"),
                "operatingIncome": metrics.get("operatingIncome"),
                "netIncomeControlling": net_income,
                "assets": metrics.get("assets"),
                "liabilities": metrics.get("liabilities"),
                "equityControlling": equity,
                "dividendPerShare": dividend,
                "dividendYield": round((dividend / year_end_close) * 100, 2) if dividend and year_end_close else None,
                "commonSharesOutstanding": shares,
                "commonStockMarketCap": market_cap,
                "yearEndClose": year_end_close,
                "yearEndCloseDate": close_info.get("date"),
                "peRatio": round(market_cap / net_income, 2) if market_cap and net_income else None,
                "pbRatio": round(market_cap / equity, 2) if market_cap and equity else None,
                "marketCap": market_cap,
                "accountSources": account_sources,
                "dividendSource": dividend_source,
                "sharesSource": shares_source,
                "marketCapSource": close_info.get("source"),
            })

        latest_year = financial_years[0] if financial_years else {}
        latest_shares = latest_year.get("commonSharesOutstanding") or toss_shares
        current_market_cap = price * latest_shares if price and latest_shares else None
        latest_dividend = latest_year.get("dividendPerShare")
        latest_net_income = latest_year.get("netIncomeControlling")
        latest_equity = latest_year.get("equityControlling")
        consensus = fetch_naver_annual_consensus(ticker) or {}
        if current_market_cap or latest_dividend or consensus:
            forecast_net_income = consensus.get("netIncomeControlling") or latest_net_income
            forecast_dividend = latest_dividend
            financial_years.append({
                "year": consensus.get("year") or f"{current_year}F",
                "fsDiv": "Forecast",
                "revenue": consensus.get("revenue"),
                "operatingIncome": consensus.get("operatingIncome"),
                "netIncomeControlling": consensus.get("netIncomeControlling"),
                "assets": None,
                "liabilities": None,
                "equityControlling": None,
                "dividendPerShare": forecast_dividend,
                "dividendYield": round((latest_dividend / price) * 100, 2) if latest_dividend and price else None,
                "commonSharesOutstanding": latest_shares,
                "commonStockMarketCap": current_market_cap,
                "yearEndClose": price,
                "yearEndCloseDate": None,
                "peRatio": consensus.get("peRatio") or (round(current_market_cap / forecast_net_income, 2) if current_market_cap and forecast_net_income else None),
                "pbRatio": consensus.get("pbRatio") or (round(current_market_cap / latest_equity, 2) if current_market_cap and latest_equity else None),
                "marketCap": current_market_cap,
                "accountSources": {},
                "dividendSource": latest_year.get("dividendSource"),
                "sharesSource": latest_year.get("sharesSource") or "Toss OpenAPI",
                "marketCapSource": "Toss OpenAPI current price",
                "forecast": True,
            })

        payload = {
            "ok": True,
            "ticker": ticker,
            "corp": corp,
            "years": financial_years,
            "price": price,
            "source": "DART OpenAPI",
            "warnings": warnings[:5],
        }
        set_cached_value(cache_key, payload)
        save_app_cache_payload(cache_key, payload)
        return jsonify(payload)
    except Exception as exc:
        print(f"DART financial lookup failed({ticker}): {exc}", flush=True)
        return jsonify({"ok": False, "error": "DART 재무요약 조회 중 오류가 발생했습니다.", "years": []}), 500


def resolve_toss_company_query(cache, query):
    raw_query = str(query or "").strip()
    normalized_symbol = normalize_toss_symbol(raw_query)
    if re.fullmatch(r"[A-Z0-9]{6}", normalized_symbol):
        return normalized_symbol, None, []

    normalized_query = normalize_company_search_text(raw_query)
    if not normalized_query:
        return "", None, []

    matches = []
    for item_name, row in iter_toss_result_rows(cache):
        item_label = str(item_name or "").lower()
        if not any(hint in item_label for hint in ["universe", "stock", "stocks", "info"]):
            continue
        symbol = normalize_toss_symbol(row.get("symbol"))
        if not re.fullmatch(r"[A-Z0-9]{6}", symbol or ""):
            continue
        names = [
            row.get("name"),
            row.get("englishName"),
            row.get("symbol"),
        ]
        searchable = [normalize_company_search_text(name) for name in names if name]
        if normalized_query in searchable:
            matches.insert(0, row)
        elif any(normalized_query and normalized_query in value for value in searchable):
            matches.append(row)

    seen = set()
    unique_matches = []
    for row in matches:
        symbol = normalize_toss_symbol(row.get("symbol"))
        if symbol and symbol not in seen:
            seen.add(symbol)
            unique_matches.append(row)

    if unique_matches:
        return normalize_toss_symbol(unique_matches[0].get("symbol")), unique_matches[0], unique_matches[:10]
    return normalized_symbol, None, []


def toss_row_market(row):
    return display_kr_market(first_present(row, ["market", "marketName", "exchange", "stockMarket", "marketType"]))


def toss_row_change_percent(row):
    value = first_present(row, ["changeRate", "changePercent", "fluctuationRate", "signedChangeRate", "priceChangeRate"])
    if value is None:
        value = first_present(row, ["change", "priceChange", "signedChangePrice"])
    if value is None:
        return None
    text = str(value).replace("%", "").replace(",", "").strip()
    try:
        return float(text)
    except Exception:
        return None


KR_MARKET_BREADTH_HISTORY_KEY = "kr-market-breadth:history"
KR_MARKET_BREADTH_INTRADAY_PREFIX = "kr-market-breadth:intraday:"
KR_MARKET_BREADTH_SAMPLE_SECONDS = int(os.environ.get("KR_MARKET_BREADTH_SAMPLE_SECONDS", "300") or "300")


def load_kr_market_breadth_seed():
    path = os.path.join(os.path.dirname(__file__), "korean_market_breadth_seed.json")
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"Korean market breadth seed load failed: {exc}", flush=True)
        return []


def safe_int_count(value, default=0):
    text = re.sub(r"[^\d-]", "", str(value or ""))
    if not text:
        return default
    try:
        return int(text)
    except Exception:
        return default


def normalize_breadth_market(value):
    market = value if isinstance(value, dict) else {}
    up = safe_int_count(market.get("up"))
    down = safe_int_count(market.get("down"))
    index = safe_int_count(market.get("index"))
    return {"up": up, "down": down, "index": index, "total": up + down}


def normalize_breadth_record(record):
    if not isinstance(record, dict):
        return None
    date_text = str(record.get("date") or "").strip()[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        return None
    return {
        "date": date_text,
        "kospi": normalize_breadth_market(record.get("kospi")),
        "kosdaq": normalize_breadth_market(record.get("kosdaq")),
    }


def merge_breadth_history(*record_groups):
    merged = {}
    for records in record_groups:
        if not isinstance(records, list):
            continue
        for record in records:
            normalized = normalize_breadth_record(record)
            if normalized:
                merged[normalized["date"]] = normalized
    return [merged[key] for key in sorted(merged.keys(), reverse=True)]


def load_kr_market_breadth_history():
    seed = load_kr_market_breadth_seed()
    remote = supabase_cache_get(KR_MARKET_BREADTH_HISTORY_KEY, None)
    remote_items = remote.get("items") if isinstance(remote, dict) else []
    items = merge_breadth_history(seed, remote_items)
    payload = {"items": items, "updatedAt": datetime.now(KST).isoformat(timespec="seconds")}
    if supabase_enabled() and (not isinstance(remote, dict) or len(remote_items or []) < len(items)):
        save_app_cache_payload(KR_MARKET_BREADTH_HISTORY_KEY, payload)
    return payload


def save_kr_market_breadth_history(items):
    payload = {"items": merge_breadth_history(items), "updatedAt": datetime.now(KST).isoformat(timespec="seconds")}
    save_app_cache_payload(KR_MARKET_BREADTH_HISTORY_KEY, payload)
    return payload


def naver_breadth_value(soup, position):
    selector = f"#contentarea_left > div:nth-of-type(2) > div > div:nth-of-type(2) table tbody tr:nth-of-type(4) td ul li:nth-of-type({position}) a span"
    node = soup.select_one(selector)
    if node:
        value = safe_int_count(node.get_text(" ", strip=True))
        if value:
            return value
    spans = soup.select("#contentarea_left table tbody tr:nth-of-type(4) td ul li a span")
    index = position - 1
    if 0 <= index < len(spans):
        value = safe_int_count(spans[index].get_text(" ", strip=True))
        if value:
            return value
    label = "\uc0c1\uc2b9\uc885\ubaa9\uc218" if position == 2 else "\ud558\ub77d\uc885\ubaa9\uc218"
    for row in soup.select("#contentarea_left tr"):
        text = row.get_text(" ", strip=True)
        match = re.search(label + r"\s*([0-9,]+)", text)
        if match:
            return safe_int_count(match.group(1))
    text = soup.get_text(" ", strip=True)
    match = re.search(label + r"\s*([0-9,]+)", text)
    return safe_int_count(match.group(1)) if match else 0


def fetch_naver_market_breadth_snapshot():
    markets = []
    for market in ("KOSPI", "KOSDAQ"):
        response = requests.get(
            "https://finance.naver.com/sise/sise_index.naver",
            params={"code": market},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        up = naver_breadth_value(soup, 2)
        down = naver_breadth_value(soup, 4)
        if up <= 0 and down <= 0:
            raise ValueError(f"Naver breadth parse failed for {market}")
        markets.append({"market": market, "up": up, "down": down, "total": up + down})
    return {
        "ok": True,
        "source": "Naver Finance",
        "asOf": datetime.now(KST).isoformat(timespec="seconds"),
        "markets": markets,
    }


def kr_market_sampling_open(now):
    if now.weekday() >= 5:
        return False
    current = now.time()
    return datetime_time(9, 0) <= current <= datetime_time(15, 40)


def load_kr_market_breadth_intraday(date_text):
    key = f"{KR_MARKET_BREADTH_INTRADAY_PREFIX}{date_text}"
    payload = supabase_cache_get(key, None)
    if not isinstance(payload, dict):
        payload = {"date": date_text, "samples": []}
    samples = payload.get("samples")
    if not isinstance(samples, list):
        payload["samples"] = []
    return key, payload


def update_history_with_snapshot(history_items, snapshot):
    by_market = {item.get("market"): item for item in snapshot.get("markets", []) if isinstance(item, dict)}
    date_text = str(snapshot.get("asOf") or "")[:10] or datetime.now(KST).date().isoformat()
    record = {
        "date": date_text,
        "kospi": {
            "up": safe_int_count((by_market.get("KOSPI") or {}).get("up")),
            "down": safe_int_count((by_market.get("KOSPI") or {}).get("down")),
            "index": 0,
        },
        "kosdaq": {
            "up": safe_int_count((by_market.get("KOSDAQ") or {}).get("up")),
            "down": safe_int_count((by_market.get("KOSDAQ") or {}).get("down")),
            "index": 0,
        },
    }
    return merge_breadth_history([record], history_items)


def snapshot_from_history_record(record):
    normalized = normalize_breadth_record(record) or {}
    return {
        "ok": True,
        "source": "Supabase app_cache",
        "asOf": f"{normalized.get('date', datetime.now(KST).date().isoformat())}T15:40:00+09:00",
        "markets": [
            {"market": "KOSPI", **normalize_breadth_market(normalized.get("kospi"))},
            {"market": "KOSDAQ", **normalize_breadth_market(normalized.get("kosdaq"))},
        ],
    }


@app.route("/api/korean-market-breadth")
def korean_market_breadth():
    force = request.args.get("refresh") == "1"
    cached = None if force else get_cached_value("korean-market-breadth", 30)
    if cached is not None:
        return jsonify(cached)

    now = datetime.now(KST)
    today = now.date().isoformat()
    history_payload = load_kr_market_breadth_history()
    history_items = history_payload.get("items", [])
    intraday_key, intraday_payload = load_kr_market_breadth_intraday(today)
    samples = intraday_payload.get("samples", [])
    latest_sample = samples[-1] if samples else None
    should_fetch = force or kr_market_sampling_open(now)
    if latest_sample and not force:
        try:
            latest_time = datetime.fromisoformat(str(latest_sample.get("asOf")))
            should_fetch = should_fetch and (now - latest_time).total_seconds() >= KR_MARKET_BREADTH_SAMPLE_SECONDS
        except Exception:
            pass

    snapshot = None
    if should_fetch:
        try:
            snapshot = fetch_naver_market_breadth_snapshot()
            samples.append({
                "asOf": snapshot.get("asOf"),
                "markets": snapshot.get("markets", []),
                "source": snapshot.get("source"),
            })
            intraday_payload = {"date": today, "samples": samples[-120:], "updatedAt": now.isoformat(timespec="seconds")}
            save_app_cache_payload(intraday_key, intraday_payload)
            history_items = update_history_with_snapshot(history_items, snapshot)
            history_payload = save_kr_market_breadth_history(history_items)
        except Exception as exc:
            print(f"Naver market breadth fetch failed: {exc}", flush=True)

    if snapshot is None and latest_sample:
        snapshot = {
            "ok": True,
            "source": latest_sample.get("source") or "Supabase app_cache",
            "asOf": latest_sample.get("asOf") or now.isoformat(timespec="seconds"),
            "markets": latest_sample.get("markets") or [],
        }
    if snapshot is None and history_items:
        snapshot = snapshot_from_history_record(history_items[0])
    if snapshot is None:
        snapshot = {"ok": False, "error": "\uad6d\ub0b4 \uc2dc\uc7a5 \ub4f1\ub77d\ube44\uc728\uc744 \ubd88\ub7ec\uc624\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.", "markets": []}

    snapshot["history"] = history_payload.get("items", [])[:120]
    snapshot["sampleSeconds"] = KR_MARKET_BREADTH_SAMPLE_SECONDS
    set_cached_value("korean-market-breadth", snapshot)
    status = 200 if snapshot.get("ok") else 500
    return jsonify(snapshot), status


@app.route("/api/korea-export-dashboard")
def korea_export_dashboard():
    payload = read_json_file(KOREA_EXPORT_DASHBOARD_FILE, {})
    if not isinstance(payload, dict) or not payload.get("industries"):
        return jsonify({
            "ok": False,
            "error": "?? ?? ???? ???? ?????.",
            "industries": [],
            "summary": {},
            "signals": [],
        }), 500
    payload["ok"] = True
    return jsonify(payload)


@app.route("/api/korea-export-stock-mapping")
def korea_export_stock_mapping():
    payload = read_json_file(KOREA_EXPORT_STOCK_MAPPING_FILE, {})
    if not isinstance(payload, dict) or not payload.get("industries"):
        return jsonify({
            "ok": False,
            "error": "\uC218\uCD9C \uC0B0\uC5C5\uBCC4 \uC885\uBAA9 \uB9E4\uD551 \uB370\uC774\uD130\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.",
            "industries": {},
        }), 500
    payload["ok"] = True
    return jsonify(payload)


@app.route("/api/toss-company")
def toss_company():
    query = request.args.get("ticker", "")
    cache = load_toss_cache()
    ticker, resolved_row, matches = resolve_toss_company_query(cache, query)
    if not ticker:
        return jsonify({"ok": False, "error": "티커를 입력하세요."}), 400

    price_row = find_toss_row(cache, ticker, ["symbol"], ["kr_prices", "price", "prices"])
    stock_info_row = find_toss_row(cache, ticker, ["symbol"], ["kr_stocks", "stock", "stocks", "info"])
    universe_row = find_toss_row(cache, ticker, ["symbol"], ["kr_universe", "universe"])
    info_row = {**(universe_row or {}), **(stock_info_row or {})} or resolved_row or price_row
    if not price_row:
        return jsonify({
            "ok": False,
            "error": "아직 이 국내종목은 수집된 시세 데이터가 없습니다. OCI collector 수집 상태를 확인해 주세요.",
            "ticker": ticker,
            "query": query,
            "dataSource": "Toss / KRX / DART / Naver",
            "availableSymbols": sorted({
                normalize_toss_symbol(row.get("symbol"))
                for _, row in iter_toss_result_rows(cache)
                if row.get("symbol")
            })[:50],
            "matches": [
                {
                    "symbol": normalize_toss_symbol(row.get("symbol")),
                    "name": row.get("name"),
                    "market": row.get("market"),
                }
                for row in matches
            ],
        }), 404

    price = first_present(price_row, ["lastPrice", "price", "tradePrice", "currentPrice", "close"])
    currency = first_present(price_row, ["currency"]) or first_present(info_row or {}, ["currency"]) or "USD"
    as_of = first_present(price_row, ["timestamp", "asOf", "updatedAt", "time", "date"]) or cache.get("receivedAt") or cache.get("updatedAt")
    name = first_present(info_row or {}, ["name", "stockName", "koreanName", "englishName", "symbol"]) or ticker
    market = display_kr_market(first_present(info_row or {}, ["market", "exchange", "marketName"]))
    status = first_present(info_row or {}, ["status", "listingStatus", "listedStatus", "stockStatus"]) or "N/A"
    security_type = first_present(info_row or {}, ["securityType", "securityTypeName", "stockType", "type"]) or "N/A"
    korean_market_detail = info_row.get("koreanMarketDetail") if isinstance(info_row, dict) else None
    if not isinstance(korean_market_detail, dict):
        korean_market_detail = {
            key: info_row.get(key)
            for key in ("nxtSupported", "krxTradingSuspended", "nxtTradingSuspended", "liquidationTrading")
            if isinstance(info_row, dict) and key in info_row
        }
    price_limit_item = read_toss_detail_item(f"kr_price_limit_{ticker}")
    if price_limit_item is None:
        price_limit_item = supabase_cache_get(f"toss:kr_price_limit_{ticker}", None)

    # 현재 웹 페이지에서는 candle 차트를 제외했으므로, 새로고침/검색마다 Supabase에서
    # kr_candles_1d_* 전체 또는 개별 candle을 읽지 않는다. 나중에 차트를 다시 붙일 때만
    # 해당 ticker 1건을 별도 조회하도록 되살리면 된다.
    daily_candle_item = read_toss_detail_item(f"kr_candles_1d_{ticker}")
    minute_candle_item = read_toss_detail_item(f"kr_candles_1m_{ticker}")

    price_limit = toss_item_result({"items": {f"kr_price_limit_{ticker}": price_limit_item}}, f"kr_price_limit_{ticker}") or toss_item_result(cache, f"kr_price_limit_{ticker}") or {}
    daily_candles = normalize_toss_candles(toss_item_result({"items": {f"kr_candles_1d_{ticker}": daily_candle_item}}, f"kr_candles_1d_{ticker}") or toss_item_result(cache, f"kr_candles_1d_{ticker}"))
    minute_candles = normalize_toss_candles(toss_item_result({"items": {f"kr_candles_1m_{ticker}": minute_candle_item}}, f"kr_candles_1m_{ticker}") or toss_item_result(cache, f"kr_candles_1m_{ticker}"))

    if currency != "KRW" or not re.fullmatch(r"\d{6}", ticker):
        return jsonify({
            "ok": False,
            "error": "국내종목 분석 베타는 현재 6자리 국내 종목코드만 지원합니다.",
            "ticker": ticker,
            "dataSource": "Toss / KRX / DART / Naver",
        }), 400

    return jsonify({
        "ok": True,
        "ticker": ticker,
        "query": query,
        "resolvedByName": bool(resolved_row),
        "name": name,
        "englishName": first_present(info_row or {}, ["englishName", "nameEng", "englishStockName", "stockEnglishName"]),
        "price": safe_number(price),
        "logoUrl": f"https://images.tossinvest.com/https%3A%2F%2Fstatic.toss.im%2Fpng-icons%2Fsecurities%2Ficn-sec-fill-{ticker}.png?width=48&height=48",
        "currency": currency,
        "market": market,
        "industry": first_present(info_row or {}, ["industry", "sector", "industryName"]),
        "status": status,
        "securityType": security_type,
        "isinCode": first_present(info_row or {}, ["isinCode", "isin", "isinCd"]),
        "listDate": first_present(info_row or {}, ["listDate", "listedDate", "listingDate"]),
        "sharesOutstanding": safe_number(first_present(info_row or {}, ["sharesOutstanding", "issuedShares", "listedShares", "numberOfListedShares"]), 0),
        "isCommonShare": first_present(info_row or {}, ["isCommonShare"]),
        "koreanMarketDetail": korean_market_detail or {},
        "priceLimit": price_limit,
        "dailyCandles": daily_candles[:60],
        "minuteCandles": minute_candles[:60],
        "dataSource": "Toss / KRX / DART / Naver",
        "asOf": as_of,
        "receivedAt": cache.get("receivedAt"),
        "updatedAt": cache.get("updatedAt"),
    })


def eth_market_scheduler():
    while True:
        run_eth_market_refresh()
        time.sleep(ETH_MARKET_INTERVAL)


def eth_news_scheduler():
    while True:
        run_eth_news_refresh()
        time.sleep(ETH_NEWS_INTERVAL)


def start_eth_tracker_schedulers():
    global ETH_SCHEDULER_STARTED
    if ETH_SCHEDULER_STARTED:
        return
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    ETH_SCHEDULER_STARTED = True
    start_thread(eth_market_scheduler)
    start_thread(eth_news_scheduler)


def load_users():
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
                headers={
                    "apikey": SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                },
                params={
                    "select": "username,nickname,email,passwordHash,createdAt",
                    "order": "createdAt.desc",
                },
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            print(f"Supabase user store load failed: {exc}", flush=True)
            return []

    try:
        if not os.path.exists(USERS_FILE):
            return []
        with open(USERS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return data.get("users", [])
        if isinstance(data, list):
            return data
    except Exception as exc:
        print(f"User store load failed: {exc}", flush=True)
    return []


def save_users(users):
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            if not users:
                return
            user = users[-1]
            payload = {
                "username": user.get("username"),
                "nickname": user.get("nickname"),
                "email": user.get("email"),
                "passwordHash": user.get("passwordHash"),
                "createdAt": user.get("createdAt"),
            }
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
                headers={
                    "apikey": SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json=payload,
                timeout=15,
            )
            if response.status_code >= 400:
                print(
                    f"Supabase user store save failed: {response.status_code} {response.text[:500]}",
                    flush=True,
                )
            response.raise_for_status()
            return
        except Exception as exc:
            print(f"Supabase user store save failed: {exc}", flush=True)
            raise

    directory = os.path.dirname(USERS_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    payload = {"users": users}
    with open(USERS_FILE, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def normalize_login_id(value):
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def email_already_registered(email, users=None):
    normalized = normalize_login_id(email)
    if not normalized:
        return False
    if normalized == normalize_login_id(APP_USERNAME):
        return True

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
                headers={
                    "apikey": SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                },
                params={"email": f"eq.{normalized}", "select": "username,email", "limit": "1"},
                timeout=8,
            )
            if response.status_code >= 400:
                print(f"Supabase email lookup failed: {response.status_code} {response.text[:500]}", flush=True)
            elif response.json():
                return True
        except Exception as exc:
            print(f"Supabase email lookup failed: {exc}", flush=True)

    if users is None:
        users = load_users()
    return any(normalize_login_id(user.get("email")) == normalized for user in users)


def normalize_channel_intro(value):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines)[:1000]


def normalize_profile_message(value):
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:60]


def get_user_profile_settings(username):
    normalized = normalize_login_id(username)
    if not normalized:
        return default_app_settings()
    try:
        return get_user_app_settings(normalized)
    except Exception as exc:
        print(f"User profile settings load failed: {exc}", flush=True)
        return default_app_settings()


def public_user(user):
    settings = get_user_profile_settings(user.get("username"))
    profile_photo = normalize_profile_photo(settings.get("profilePhoto"))
    return {
        "username": user.get("username"),
        "nickname": user.get("nickname") or user.get("username"),
        "email": user.get("email"),
        "createdAt": user.get("createdAt"),
        "avatarUrl": profile_photo.get("url"),
        "profilePhoto": profile_photo,
        "profileMessage": normalize_profile_message(settings.get("profileMessage")),
    }


def find_user(login_id):
    raw_login_id = str(login_id or "").strip()
    normalized = normalize_login_id(raw_login_id)
    if not normalized:
        return None

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        }
        select_fields = "username,nickname,email,passwordHash,createdAt"
        candidates = []
        for value in (raw_login_id, normalized):
            if value and value not in candidates:
                candidates.append(value)
        for field in ("username", "email", "nickname"):
            for candidate in candidates:
                try:
                    response = requests.get(
                        f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
                        headers=headers,
                        params={field: f"eq.{candidate}", "select": select_fields, "limit": "1"},
                        timeout=8,
                    )
                    if response.status_code >= 400:
                        print(f"Supabase user lookup failed({field}): {response.status_code} {response.text[:500]}", flush=True)
                        continue
                    data = response.json()
                    if data:
                        return data[0]
                except Exception as exc:
                    print(f"Supabase user lookup failed({field}): {exc}", flush=True)
        return None

    for user in load_users():
        if normalize_login_id(user.get("username")) == normalized:
            return user
        if normalize_login_id(user.get("nickname")) == normalized:
            return user
        if normalize_login_id(user.get("email")) == normalized:
            return user
    return None


USER_DISPLAY_NAME_CACHE = {}
USER_DISPLAY_NAME_CACHE_TTL_SECONDS = 60
COMMUNITY_FOLLOWER_COUNT_CACHE = {}
COMMUNITY_FOLLOWER_COUNT_CACHE_TTL_SECONDS = 60


def invalidate_user_display_name_cache(username):
    normalized = normalize_login_id(username)
    if normalized:
        USER_DISPLAY_NAME_CACHE.pop(normalized, None)


def normalize_profile_photo(value):
    if not isinstance(value, dict):
        return {}
    url = str(value.get("url") or "").strip()
    path = str(value.get("path") or "").strip().lstrip("/")
    content_type = str(value.get("contentType") or value.get("type") or "").strip().lower()[:80]
    try:
        size = int(float(value.get("size") or value.get("sizeBytes") or 0))
    except (TypeError, ValueError):
        size = 0
    if not url:
        return {}
    if content_type and content_type not in PROFILE_PHOTO_ALLOWED_TYPES:
        return {}
    return {
        "url": url[:600],
        "path": path[:300],
        "contentType": content_type or "image/jpeg",
        "size": max(0, min(size, PROFILE_PHOTO_MAX_BYTES)),
    }


def get_user_profile_photo(username):
    return normalize_profile_photo(get_user_profile_settings(username).get("profilePhoto"))


def count_community_followers(username):
    target = normalize_login_id(username)
    if not target:
        return 0
    cached = COMMUNITY_FOLLOWER_COUNT_CACHE.get(target)
    now = time.time()
    if cached and now - cached.get("ts", 0) < COMMUNITY_FOLLOWER_COUNT_CACHE_TTL_SECONDS:
        return int(cached.get("count") or 0)
    count = 0
    try:
        if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
                headers={
                    "apikey": SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                },
                params={"select": "appSettings"},
                timeout=15,
            )
            if response.status_code >= 400:
                print(f"Supabase community follower count failed: {response.status_code} {response.text[:500]}", flush=True)
                response.raise_for_status()
            users = response.json()
        else:
            users = load_users()
        for user_row in users:
            settings = sanitize_app_settings((user_row or {}).get("appSettings"))
            follows = {normalize_login_id(item) for item in settings.get("communityFollows", []) if normalize_login_id(item)}
            if target in follows:
                count += 1
    except Exception as exc:
        print(f"Community follower count failed: {exc}", flush=True)
    COMMUNITY_FOLLOWER_COUNT_CACHE[target] = {"ts": now, "count": count}
    return count

def count_community_channel_followers(channel_ids):
    channel_ids = [str(channel_id or "").strip() for channel_id in channel_ids]
    channel_ids = list(dict.fromkeys(channel_id for channel_id in channel_ids if channel_id))
    if not channel_ids:
        return {}
    now = time.time()
    counts = {}
    missing = []
    for channel_id in channel_ids:
        key = f"channel:{channel_id}"
        cached = COMMUNITY_FOLLOWER_COUNT_CACHE.get(key)
        if cached and now - cached.get("ts", 0) < COMMUNITY_FOLLOWER_COUNT_CACHE_TTL_SECONDS:
            counts[channel_id] = int(cached.get("count") or 0)
        else:
            missing.append(channel_id)
            counts[channel_id] = 0
    if missing:
        try:
            if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
                response = requests.get(
                    f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
                    headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"},
                    params={"select": "appSettings"},
                    timeout=15,
                )
                response.raise_for_status()
                users = response.json()
            else:
                users = load_users()
            missing_keys = {f"channel:{channel_id}": channel_id for channel_id in missing}
            for user_row in users:
                settings = sanitize_app_settings((user_row or {}).get("appSettings"))
                follows = {normalize_login_id(item) for item in settings.get("communityFollows", []) if normalize_login_id(item)}
                for key in follows.intersection(missing_keys):
                    counts[missing_keys[key]] += 1
        except Exception as exc:
            print(f"Community channel follower count failed: {exc}", flush=True)
        for channel_id in missing:
            COMMUNITY_FOLLOWER_COUNT_CACHE[f"channel:{channel_id}"] = {"ts": now, "count": counts[channel_id]}
    return counts


def user_follows_community_channel(username, channel_id):
    username = normalize_login_id(username)
    channel_id = str(channel_id or "").strip()
    if not username or not channel_id:
        return False
    return f"channel:{channel_id}" in get_user_app_settings(username).get("communityFollows", [])


def can_access_community_channel(channel, username=None):
    if not channel:
        return False
    if str(channel.get("visibility") or "public") != "private":
        return True
    username = normalize_login_id(username if username is not None else session.get("username"))
    return bool(username and (normalize_login_id(channel.get("owner")) == username or is_super_admin(username) or user_follows_community_channel(username, channel.get("id"))))


def can_access_community_channel_post(post, username=None):
    channel_id = extract_community_channel_id(post) if post else ""
    if not channel_id:
        return True
    channel = next((item for item in load_community_channels() if str(item.get("id")) == channel_id), None)
    return can_access_community_channel(channel, username)


def filter_accessible_community_posts(posts, username=None):
    posts = list(posts or [])
    channel_ids = {extract_community_channel_id(post) for post in posts if extract_community_channel_id(post)}
    if not channel_ids:
        return posts
    channels = {str(channel.get("id")): channel for channel in load_community_channels() if str(channel.get("id")) in channel_ids}
    return [post for post in posts if not extract_community_channel_id(post) or can_access_community_channel(channels.get(extract_community_channel_id(post)), username)]


def list_community_followers(username, limit=100):
    target = normalize_login_id(username)
    if not target:
        return []
    followers = []
    try:
        if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
                headers={
                    "apikey": SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                },
                params={"select": "username,nickname,appSettings", "limit": "1000"},
                timeout=15,
            )
            if response.status_code >= 400:
                print(f"Supabase community follower list failed: {response.status_code} {response.text[:500]}", flush=True)
                response.raise_for_status()
            users = response.json()
        else:
            users = load_users()
        for user_row in users:
            follower_username = normalize_login_id((user_row or {}).get("username"))
            if not follower_username:
                continue
            settings = sanitize_app_settings((user_row or {}).get("appSettings"))
            follows = {normalize_login_id(item) for item in settings.get("communityFollows", []) if normalize_login_id(item)}
            if target not in follows:
                continue
            profile = get_user_public_profile(follower_username, (user_row or {}).get("nickname") or follower_username)
            followers.append({
                "username": follower_username,
                "author": profile.get("name") or (user_row or {}).get("nickname") or follower_username,
                "avatarUrl": profile.get("avatarUrl") or "",
                "profileMessage": profile.get("profileMessage") or "",
                "followerCount": int(profile.get("followerCount") or 0),
            })
            if len(followers) >= limit:
                break
    except Exception as exc:
        print(f"Community follower list failed: {exc}", flush=True)
    return followers


def get_user_public_profile(username, fallback=None):
    normalized = normalize_login_id(username)
    clean_fallback = str(fallback or "").strip()
    if not normalized:
        return {"name": clean_fallback or "익명", "avatarUrl": "", "profileMessage": "", "followerCount": 0}
    cached = USER_DISPLAY_NAME_CACHE.get(normalized)
    now = time.time()
    if cached and now - cached.get("ts", 0) < USER_DISPLAY_NAME_CACHE_TTL_SECONDS:
        return {
            "name": cached.get("name") or clean_fallback or str(username),
            "avatarUrl": cached.get("avatarUrl") or "",
            "profileMessage": cached.get("profileMessage") or "",
            "channelIntro": cached.get("channelIntro") or "",
            "channelName": cached.get("channelName") or "",
            "channelCreated": bool(cached.get("channelCreated")),
            "followerCount": count_community_followers(normalized),
        }
    user = find_user(username)
    display_name = (user or {}).get("nickname") or (user or {}).get("username") or clean_fallback or str(username)
    settings = get_user_profile_settings((user or {}).get("username") or username)
    avatar_url = normalize_profile_photo(settings.get("profilePhoto")).get("url") or ""
    profile_message = normalize_profile_message(settings.get("profileMessage"))
    channel_intro = normalize_channel_intro(settings.get("channelIntro"))
    channel_name = re.sub(r"\s+", " ", str(settings.get("channelName") or "").strip())[:40]
    channel_created = bool(settings.get("channelCreated"))
    USER_DISPLAY_NAME_CACHE[normalized] = {"ts": now, "name": display_name, "avatarUrl": avatar_url, "profileMessage": profile_message, "channelIntro": channel_intro, "channelName": channel_name, "channelCreated": channel_created}
    return {"name": display_name, "avatarUrl": avatar_url, "profileMessage": profile_message, "channelIntro": channel_intro, "channelName": channel_name, "channelCreated": channel_created, "followerCount": count_community_followers(normalized)}


def get_user_display_name(username, fallback=None):
    return get_user_public_profile(username, fallback).get("name")


def update_user(username, updates):
    normalized = normalize_login_id(username)
    allowed_updates = {key: value for key, value in updates.items() if key in {"nickname", "passwordHash"}}
    if not allowed_updates:
        return find_user(username)

    invalidate_user_display_name_cache(normalized)
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            params={
                "username": f"eq.{username}",
                "select": "username,nickname,email,passwordHash,createdAt",
            },
            json=allowed_updates,
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Supabase user store update failed: {response.status_code} {response.text[:500]}", flush=True)
        response.raise_for_status()
        data = response.json()
        return data[0] if data else find_user(username)

    users = load_users()
    updated_user = None
    for user in users:
        if normalize_login_id(user.get("username")) == normalized:
            user.update(allowed_updates)
            updated_user = user
            break
    if not updated_user:
        return None
    save_users(users)
    return updated_user


def delete_user(username):
    normalized = normalize_login_id(username)
    user = find_user(username)
    if not user:
        return False

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.delete(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
            params={"username": f"eq.{user.get('username')}"},
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Supabase user delete failed: {response.status_code} {response.text[:500]}", flush=True)
        response.raise_for_status()
        return True

    users = load_users()
    filtered = [item for item in users if normalize_login_id(item.get("username")) != normalized]
    if len(filtered) == len(users):
        return False
    save_users(filtered)
    return True


def default_app_settings():
    return {"watchlist": [], "companyWatchlistMeta": {}, "ethTracker": {}, "communityLikes": [], "communityCommentLikes": [], "communityFollows": [], "communityChannelReadAt": {}, "companyBeta": {}, "hyperliquidAlerts": {}, "hyperliquidPinned": [], "hyperliquidPinnedTouched": False, "notificationDismissed": [], "profilePhoto": {}, "profileMessage": "", "channelIntro": "", "channelName": "", "channelCreated": False}


def sanitize_app_settings(value):
    source = value if isinstance(value, dict) else {}
    settings = default_app_settings()

    watchlist = source.get("watchlist")
    if isinstance(watchlist, list):
        clean_symbols = []
        for symbol in watchlist:
            normalized = re.sub(r"\s+", "", str(symbol or "").strip().upper())
            if re.fullmatch(r"\d{6}", normalized):
                normalized = f"{normalized}.KS"
            if normalized and normalized not in clean_symbols:
                clean_symbols.append(normalized)
        settings["watchlist"] = clean_symbols[:10]

    company_watch_meta = source.get("companyWatchlistMeta")
    if isinstance(company_watch_meta, dict):
        clean_company_meta = {}
        allowed_symbols = set(settings.get("watchlist") or [])
        for symbol, item in company_watch_meta.items():
            normalized = re.sub(r"\s+", "", str(symbol or "").strip().upper())[:20]
            if not normalized or (allowed_symbols and normalized not in allowed_symbols) or not isinstance(item, dict):
                continue
            clean_item = {"symbol": normalized}
            name_text = re.sub(r"\s+", " ", str(item.get("name") or "").strip())
            if name_text and len(name_text) <= 100:
                clean_item["name"] = name_text
            for key in ("marketCap", "price"):
                try:
                    number_value = float(item.get(key))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(number_value) and number_value >= 0:
                    clean_item[key] = number_value
            updated_at = str(item.get("updatedAt") or "").strip()[:40]
            if updated_at:
                clean_item["updatedAt"] = updated_at
            clean_company_meta[normalized] = clean_item
        settings["companyWatchlistMeta"] = clean_company_meta

    eth_tracker = source.get("ethTracker")
    if isinstance(eth_tracker, dict):
        clean_eth = {}
        for key in ("eth-amount", "eth-average-price"):
            value_text = str(eth_tracker.get(key, "")).strip()
            if len(value_text) <= 32:
                clean_eth[key] = value_text
        settings["ethTracker"] = clean_eth

    company_beta = source.get("companyBeta")
    if isinstance(company_beta, dict):
        clean_company_beta = {}
        ticker = normalize_toss_symbol(company_beta.get("ticker") or company_beta.get("symbol") or "")
        query = re.sub(r"\s+", " ", str(company_beta.get("query") or "").strip())
        name = re.sub(r"\s+", " ", str(company_beta.get("name") or "").strip())
        if re.fullmatch(r"[A-Z0-9]{6}", ticker or ""):
            clean_company_beta["ticker"] = ticker
        if query and len(query) <= 40:
            clean_company_beta["query"] = query
        if name and len(name) <= 80:
            clean_company_beta["name"] = name
        beta_watchlist = company_beta.get("watchlist")
        clean_beta_watchlist = []
        if isinstance(beta_watchlist, list):
            for symbol in beta_watchlist:
                normalized = normalize_toss_symbol(symbol)
                if normalized and len(normalized) <= 20 and normalized not in clean_beta_watchlist:
                    clean_beta_watchlist.append(normalized)
            clean_company_beta["watchlist"] = clean_beta_watchlist[:10]
        beta_meta = company_beta.get("watchlistMeta")
        if isinstance(beta_meta, dict):
            clean_meta = {}
            allowed_symbols = set(clean_beta_watchlist[:10])
            for symbol, item in beta_meta.items():
                normalized = normalize_toss_symbol(symbol)
                if not normalized or (allowed_symbols and normalized not in allowed_symbols) or not isinstance(item, dict):
                    continue
                clean_item = {"symbol": normalized}
                name_text = re.sub(r"\s+", " ", str(item.get("name") or "").strip())
                if name_text and len(name_text) <= 80:
                    clean_item["name"] = name_text
                for key in ("marketCap", "price"):
                    try:
                        number_value = float(item.get(key))
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(number_value) and number_value >= 0:
                        clean_item[key] = number_value
                updated_at = str(item.get("updatedAt") or "").strip()[:40]
                if updated_at:
                    clean_item["updatedAt"] = updated_at
                clean_meta[normalized] = clean_item
            if clean_meta:
                clean_company_beta["watchlistMeta"] = clean_meta
        settings["companyBeta"] = clean_company_beta

    community_likes = source.get("communityLikes")
    if isinstance(community_likes, list):
        clean_likes = []
        for post_id in community_likes:
            normalized = str(post_id or "").strip()
            if normalized and normalized not in clean_likes:
                clean_likes.append(normalized)
        settings["communityLikes"] = clean_likes[:1000]

    community_comment_likes = source.get("communityCommentLikes")
    if isinstance(community_comment_likes, list):
        clean_comment_likes = []
        for comment_id in community_comment_likes:
            normalized = str(comment_id or "").strip()
            if normalized and normalized not in clean_comment_likes:
                clean_comment_likes.append(normalized)
        settings["communityCommentLikes"] = clean_comment_likes[:3000]

    community_follows = source.get("communityFollows")
    if isinstance(community_follows, list):
        clean_follows = []
        for username in community_follows:
            normalized = normalize_login_id(username)
            if normalized and normalized not in clean_follows:
                clean_follows.append(normalized)
        settings["communityFollows"] = clean_follows[:500]


    community_channel_read_at = source.get("communityChannelReadAt")
    if isinstance(community_channel_read_at, dict):
        clean_channel_read_at = {}
        allowed_follow_users = set(settings.get("communityFollows") or [])
        for username, value in community_channel_read_at.items():
            normalized = normalize_login_id(username)
            timestamp = str(value or "").strip()[:40]
            if normalized and timestamp and (not allowed_follow_users or normalized in allowed_follow_users):
                clean_channel_read_at[normalized] = timestamp
        settings["communityChannelReadAt"] = clean_channel_read_at

    notification_dismissed = source.get("notificationDismissed")
    if isinstance(notification_dismissed, list):
        clean_dismissed = []
        for notification_id in notification_dismissed:
            normalized = str(notification_id or "").strip()[:180]
            if normalized and normalized not in clean_dismissed:
                clean_dismissed.append(normalized)
        settings["notificationDismissed"] = clean_dismissed[-500:]

    hyperliquid_alerts = source.get("hyperliquidAlerts")
    if isinstance(hyperliquid_alerts, dict):
        clean_alerts = {}
        for coin, item in hyperliquid_alerts.items():
            normalized_coin = str(coin or "").strip().upper()[:40]
            if not normalized_coin or not isinstance(item, dict):
                continue
            try:
                target = float(item.get("target"))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(target) or target <= 0:
                continue
            direction = str(item.get("direction") or "above").strip().lower()
            if direction not in {"above", "below"}:
                direction = "above"
            clean_alerts[normalized_coin] = {
                "target": target,
                "direction": direction,
                "enabled": bool(item.get("enabled", True)),
                "createdAt": str(item.get("createdAt") or "")[:40],
                "triggeredAt": str(item.get("triggeredAt") or "")[:40],
            }
        settings["hyperliquidAlerts"] = dict(list(clean_alerts.items())[:100])

    hyperliquid_pinned = source.get("hyperliquidPinned")
    if isinstance(hyperliquid_pinned, list):
        clean_pinned = []
        for coin in hyperliquid_pinned:
            normalized_coin = str(coin or "").strip().upper()[:40]
            if normalized_coin and re.fullmatch(r"[A-Z0-9:_-]{1,40}", normalized_coin) and normalized_coin not in clean_pinned:
                clean_pinned.append(normalized_coin)
        settings["hyperliquidPinned"] = clean_pinned[:8]
    settings["hyperliquidPinnedTouched"] = bool(source.get("hyperliquidPinnedTouched"))

    profile_photo = normalize_profile_photo(source.get("profilePhoto"))
    if profile_photo:
        settings["profilePhoto"] = profile_photo

    settings["profileMessage"] = normalize_profile_message(source.get("profileMessage"))
    settings["channelIntro"] = normalize_channel_intro(source.get("channelIntro"))
    settings["channelName"] = re.sub(r"\s+", " ", str(source.get("channelName") or "").strip())[:40]
    settings["channelCreated"] = bool(source.get("channelCreated"))

    return settings


def canonical_session_username(username):
    return normalize_login_id(username)


def get_user_app_settings(username):
    normalized = canonical_session_username(username)
    if not normalized:
        return default_app_settings()

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            params={
                "username": f"eq.{normalized}",
                "select": "appSettings",
                "limit": "1",
            },
            timeout=8,
        )
        if response.status_code >= 400:
            print(f"Supabase app settings load failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        return sanitize_app_settings((data[0] if data else {}).get("appSettings"))

    user = find_user(normalized)
    if not user:
        return default_app_settings()
    return sanitize_app_settings(user.get("appSettings"))


def save_user_app_settings(username, settings):
    normalized = canonical_session_username(username)
    if not normalized:
        return None
    clean_settings = sanitize_app_settings(settings)

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            params={
                "username": f"eq.{normalized}",
                "select": "appSettings",
            },
            json={"appSettings": clean_settings},
            timeout=8,
        )
        if response.status_code >= 400:
            print(f"Supabase app settings save failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        return clean_settings if response.json() else None

    user = find_user(normalized)
    if not user:
        return None
    users = load_users()
    for item in users:
        if normalize_login_id(item.get("username")) == normalize_login_id(user.get("username")):
            item["appSettings"] = clean_settings
            break
    save_users(users)
    return clean_settings


def community_likes_table_enabled():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_COMMUNITY_LIKES_TABLE)


def community_like_headers(extra=None):
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    if extra:
        headers.update(extra)
    return headers


def get_table_community_like_ids(username):
    normalized = canonical_session_username(username)
    if not normalized or not community_likes_table_enabled():
        return None
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_LIKES_TABLE}",
            headers=community_like_headers(),
            params={"username": f"eq.{normalized}", "select": "post_id", "limit": "1000"},
            timeout=8,
        )
        if response.status_code >= 400:
            print(f"Supabase community likes table load failed: {response.status_code} {response.text[:500]}", flush=True)
            return None
        return {str(row.get("post_id")) for row in response.json() if row.get("post_id")}
    except Exception as exc:
        print(f"Supabase community likes table load failed: {exc}", flush=True)
        return None


def count_table_community_post_likes(post_id):
    post_id = str(post_id or "").strip()
    if not post_id or not community_likes_table_enabled():
        return None
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_LIKES_TABLE}",
            headers=community_like_headers(),
            params={"post_id": f"eq.{post_id}", "select": "username", "limit": "10000"},
            timeout=8,
        )
        if response.status_code >= 400:
            print(f"Supabase community likes count failed: {response.status_code} {response.text[:500]}", flush=True)
            return None
        return len(response.json())
    except Exception as exc:
        print(f"Supabase community likes count failed: {exc}", flush=True)
        return None


def set_table_community_post_like(post_id, username, liked):
    post_id = str(post_id or "").strip()
    normalized = canonical_session_username(username)
    if not post_id or not normalized or not community_likes_table_enabled():
        return None
    try:
        if liked:
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_LIKES_TABLE}",
                headers=community_like_headers({"Content-Type": "application/json", "Prefer": "resolution=ignore-duplicates,return=minimal"}),
                json={"post_id": post_id, "username": normalized, "created_at": datetime.now(timezone.utc).isoformat()},
                timeout=8,
            )
        else:
            response = requests.delete(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_LIKES_TABLE}",
                headers=community_like_headers(),
                params={"post_id": f"eq.{post_id}", "username": f"eq.{normalized}"},
                timeout=8,
            )
        if response.status_code >= 400:
            print(f"Supabase community likes toggle failed: {response.status_code} {response.text[:500]}", flush=True)
            return None
        return True
    except Exception as exc:
        print(f"Supabase community likes toggle failed: {exc}", flush=True)
        return None


def current_community_like_ids(username=None):
    if username is None:
        if not has_request_context():
            return set()
        username = session.get("username")
    if not username:
        return set()
    table_likes = get_table_community_like_ids(username)
    if table_likes is not None:
        return table_likes
    try:
        settings = get_user_app_settings(username)
    except Exception as exc:
        print(f"Community liked ids load failed: {exc}", flush=True)
        return set()
    return {str(item) for item in settings.get("communityLikes", []) if item}


def count_community_post_likes(post_id):
    post_id = str(post_id or "").strip()
    if not post_id:
        return 0
    table_count = count_table_community_post_likes(post_id)
    if table_count is not None:
        return table_count
    count = 0
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
                headers={
                    "apikey": SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                },
                params={"select": "appSettings"},
                timeout=15,
            )
            if response.status_code >= 400:
                print(f"Supabase community like count fallback failed: {response.status_code} {response.text[:500]}", flush=True)
                response.raise_for_status()
            for user_row in response.json():
                settings = sanitize_app_settings((user_row or {}).get("appSettings"))
                liked_posts = {str(item) for item in settings.get("communityLikes", []) if item}
                if post_id in liked_posts:
                    count += 1
            return count
        except Exception as exc:
            print(f"Community like count fallback failed: {exc}", flush=True)
    for user_row in load_users():
        settings = sanitize_app_settings((user_row or {}).get("appSettings"))
        liked_posts = {str(item) for item in settings.get("communityLikes", []) if item}
        if post_id in liked_posts:
            count += 1
    return count


def current_community_comment_like_ids(username=None):
    if username is None:
        if not has_request_context():
            return set()
        username = session.get("username")
    if not username:
        return set()
    try:
        settings = get_user_app_settings(username)
    except Exception as exc:
        print(f"Community comment liked ids load failed: {exc}", flush=True)
        return set()
    return {str(item) for item in settings.get("communityCommentLikes", []) if item}



def normalize_community_attachments(value, max_count=COMMUNITY_ATTACHMENT_MAX_COUNT):
    raw_items = value if isinstance(value, list) else []
    try:
        max_count = max(0, min(int(max_count), CHANNEL_ATTACHMENT_MAX_COUNT))
    except (TypeError, ValueError):
        max_count = COMMUNITY_ATTACHMENT_MAX_COUNT
    attachments = []
    seen = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        path = str(item.get("path") or "").strip()
        name = re.sub(r"\s+", " ", str(item.get("name") or "image").strip())[:120]
        content_type = str(item.get("contentType") or item.get("type") or "").strip().lower()[:80]
        try:
            size = int(float(item.get("size") or item.get("sizeBytes") or 0))
        except (TypeError, ValueError):
            size = 0
        unique_key = path or url
        if not url or unique_key in seen:
            continue
        if content_type and content_type not in COMMUNITY_ATTACHMENT_ALLOWED_TYPES:
            continue
        seen.add(unique_key)
        attachments.append({
            "url": url[:600],
            "path": path[:300],
            "name": name or "image",
            "contentType": content_type or "application/octet-stream",
            "size": max(0, min(size, COMMUNITY_ATTACHMENT_MAX_BYTES)),
        })
        if len(attachments) >= max_count:
            break
    return attachments


def supabase_storage_headers(extra=None):
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    if extra:
        headers.update(extra)
    return headers


def ensure_community_storage_bucket():
    global COMMUNITY_STORAGE_BUCKET_READY
    if COMMUNITY_STORAGE_BUCKET_READY:
        return True
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY or not SUPABASE_COMMUNITY_BUCKET:
        return False
    try:
        response = requests.get(
            f"{SUPABASE_URL}/storage/v1/bucket/{quote(SUPABASE_COMMUNITY_BUCKET, safe='')}",
            headers=supabase_storage_headers(),
            timeout=8,
        )
        if response.status_code == 200:
            COMMUNITY_STORAGE_BUCKET_READY = True
            return True
        create_response = requests.post(
            f"{SUPABASE_URL}/storage/v1/bucket",
            headers=supabase_storage_headers({"Content-Type": "application/json"}),
            json={
                "id": SUPABASE_COMMUNITY_BUCKET,
                "name": SUPABASE_COMMUNITY_BUCKET,
                "public": True,
                "file_size_limit": COMMUNITY_ATTACHMENT_MAX_BYTES,
                "allowed_mime_types": sorted(COMMUNITY_ATTACHMENT_ALLOWED_TYPES),
            },
            timeout=8,
        )
        if create_response.status_code in {200, 201, 409}:
            COMMUNITY_STORAGE_BUCKET_READY = True
            return True
        print(f"Supabase community bucket create failed: {create_response.status_code} {create_response.text[:500]}", flush=True)
    except Exception as exc:
        print(f"Supabase community bucket check failed: {exc}", flush=True)
    return False


def community_attachment_paths(items):
    paths = []
    seen = set()
    for item in normalize_community_attachments(items, CHANNEL_ATTACHMENT_MAX_COUNT):
        path = str(item.get("path") or "").strip().lstrip("/")
        if not path or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def delete_community_attachment_paths(paths):
    clean_paths = []
    seen = set()
    for path in paths or []:
        normalized = str(path or "").strip().lstrip("/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        clean_paths.append(normalized)
    if not clean_paths or not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY or not SUPABASE_COMMUNITY_BUCKET:
        return
    try:
        response = requests.delete(
            f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_COMMUNITY_BUCKET, safe='')}",
            headers=supabase_storage_headers({"Content-Type": "application/json"}),
            json={"prefixes": clean_paths},
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Supabase community attachment delete failed: {response.status_code} {response.text[:500]}", flush=True)
    except Exception as exc:
        print(f"Supabase community attachment delete failed: {exc}", flush=True)


def upload_profile_photo_file(file_storage, user):
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase Storage 설정이 필요합니다.")
    if not ensure_community_storage_bucket():
        raise RuntimeError("프로필 사진 Storage bucket을 준비하지 못했습니다.")
    if not file_storage or not getattr(file_storage, "filename", ""):
        raise ValueError("프로필 사진을 선택해주세요.")
    content_type = (file_storage.mimetype or "").split(";")[0].strip().lower()
    if content_type not in PROFILE_PHOTO_ALLOWED_TYPES:
        raise ValueError("JPG, PNG, WebP, GIF 이미지만 사용할 수 있습니다.")
    data = file_storage.read(PROFILE_PHOTO_MAX_BYTES + 1)
    if not data:
        raise ValueError("빈 파일은 사용할 수 없습니다.")
    if len(data) > PROFILE_PHOTO_MAX_BYTES:
        raise ValueError("프로필 사진은 2MB 이하로 올려주세요.")
    original_name = secure_filename(file_storage.filename) or "profile"
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        ext = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }.get(content_type, ".jpg")
    username = canonical_session_username((user or {}).get("username") or session.get("username")) or "user"
    storage_path = f"profiles/{username}/{secrets.token_hex(12)}{ext}"
    upload_response = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_COMMUNITY_BUCKET, safe='')}/{quote(storage_path, safe='/')}",
        headers=supabase_storage_headers({
            "Content-Type": content_type,
            "x-upsert": "false",
            "Cache-Control": "31536000",
        }),
        data=data,
        timeout=20,
    )
    if upload_response.status_code >= 400:
        print(f"Supabase profile photo upload failed: {upload_response.status_code} {upload_response.text[:500]}", flush=True)
        upload_response.raise_for_status()
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{quote(SUPABASE_COMMUNITY_BUCKET, safe='')}/{quote(storage_path, safe='/')}"
    return {
        "url": public_url,
        "path": storage_path,
        "contentType": content_type,
        "size": len(data),
    }


def upload_community_attachment_file(file_storage, user):
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase Storage 설정이 필요합니다.")
    if not ensure_community_storage_bucket():
        raise RuntimeError("커뮤니티 첨부 Storage bucket을 준비하지 못했습니다.")
    if not file_storage or not getattr(file_storage, "filename", ""):
        raise ValueError("첨부할 사진을 선택해주세요.")
    content_type = (file_storage.mimetype or "").split(";")[0].strip().lower()
    if content_type not in COMMUNITY_ATTACHMENT_ALLOWED_TYPES:
        raise ValueError("JPG, PNG, WebP, GIF, PDF 파일만 첨부할 수 있습니다.")
    data = file_storage.read(COMMUNITY_ATTACHMENT_MAX_BYTES + 1)
    if not data:
        raise ValueError("빈 파일은 첨부할 수 없습니다.")
    if len(data) > COMMUNITY_ATTACHMENT_MAX_BYTES:
        raise ValueError("파일은 개당 5MB 이하로 첨부해주세요.")
    original_name = secure_filename(file_storage.filename) or "image"
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}:
        ext = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "application/pdf": ".pdf",
        }.get(content_type, ".bin")
    username = canonical_session_username((user or {}).get("username") or session.get("username")) or "user"
    date_part = datetime.now(KST).strftime("%Y%m%d")
    storage_path = f"{username}/{date_part}/{secrets.token_hex(12)}{ext}"
    upload_response = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_COMMUNITY_BUCKET, safe='')}/{quote(storage_path, safe='/')}",
        headers=supabase_storage_headers({
            "Content-Type": content_type,
            "x-upsert": "false",
            "Cache-Control": "31536000",
        }),
        data=data,
        timeout=20,
    )
    if upload_response.status_code >= 400:
        print(f"Supabase community attachment upload failed: {upload_response.status_code} {upload_response.text[:500]}", flush=True)
        upload_response.raise_for_status()
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{quote(SUPABASE_COMMUNITY_BUCKET, safe='')}/{quote(storage_path, safe='/')}"
    return {
        "url": public_url,
        "path": storage_path,
        "name": original_name[:120],
        "contentType": content_type,
        "size": len(data),
    }

def normalize_community_comments(post):
    raw_comments = post.get("comments") or []
    if isinstance(raw_comments, str):
        try:
            raw_comments = json.loads(raw_comments)
        except Exception:
            raw_comments = []
    if not isinstance(raw_comments, list):
        return []

    comments = []
    for item in raw_comments[-500:]:
        if not isinstance(item, dict):
            continue
        body = str(item.get("body") or "").strip()
        if not body:
            continue
        raw_liked_by = item.get("likedBy") or []
        if not isinstance(raw_liked_by, list):
            raw_liked_by = []
        liked_by = []
        for liked_username in raw_liked_by:
            normalized_liked_username = normalize_login_id(liked_username)
            if normalized_liked_username and normalized_liked_username not in liked_by:
                liked_by.append(normalized_liked_username)
        comments.append({
            "id": str(item.get("id") or secrets.token_hex(8)),
            "body": body[:500],
            "author": item.get("author") or "\ud68c\uc6d0",
            "username": item.get("username"),
            "createdAt": item.get("createdAt"),
            "likes": max(int(item.get("likes") or 0), len(liked_by)),
            "likedBy": liked_by[:1000],
        })
    return comments


def can_edit_community_comment(comment, username=None):
    if not comment:
        return False
    if username is None:
        username = session.get("username") if has_request_context() else None
    if not username:
        return False
    if is_super_admin(username):
        return True
    return normalize_login_id(comment.get("username")) == normalize_login_id(username)


def public_community_comment(comment, liked_comment_ids=None):
    comment_id = str(comment.get("id") or "")
    if liked_comment_ids is None:
        liked_comment_ids = current_community_comment_like_ids()
    username = session.get("username") if has_request_context() else None
    liked_by = comment.get("likedBy") or []
    if not isinstance(liked_by, list):
        liked_by = []
    normalized_username = normalize_login_id(username)
    is_liked = comment_id in liked_comment_ids or (normalized_username and normalized_username in liked_by)
    author_profile = get_user_public_profile(comment.get("username"), comment.get("author") or "\uc775\uba85")
    return {
        "id": comment.get("id"),
        "body": comment.get("body") or "",
        "author": author_profile.get("name") or "\uc775\uba85",
        "username": comment.get("username"),
        "avatarUrl": author_profile.get("avatarUrl") or "",
        "profileMessage": author_profile.get("profileMessage") or "",
        "channelIntro": author_profile.get("channelIntro") or "",
        "channelName": author_profile.get("channelName") or "",
        "channelCreated": bool(author_profile.get("channelCreated")),
        "followerCount": int(author_profile.get("followerCount") or 0),
        "createdAt": comment.get("createdAt"),
        "likes": max(int(comment.get("likes") or 0), len(liked_by)),
        "liked": bool(is_liked),
        "canDelete": can_edit_community_comment(comment),
    }


def validate_community_comment_payload(payload):
    body = str(payload.get("body", "")).strip()
    if len(body) < 2 or len(body) > 500:
        raise ValueError("\ub2f5\uae00\uc740 2~500\uc790\ub85c \uc785\ub825\ud574\uc8fc\uc138\uc694.")
    return body


def community_channel_marker(channel_id):
    return f"{{{{channel:{channel_id}}}}}" if channel_id else ""

def extract_community_channel_id(post):
    direct = str(post.get("channelId") or "").strip()
    if direct:
        return direct
    match = re.match(r"^\{\{channel:([A-Za-z0-9_-]{1,64})\}\}\s*", str(post.get("body") or ""))
    return match.group(1) if match else ""

def strip_community_channel_marker(body):
    return re.sub(r"^\{\{channel:[A-Za-z0-9_-]{1,64}\}\}\s*", "", str(body or ""), count=1)

def public_community_post(post, liked_post_ids=None, liked_comment_ids=None):
    category = post.get("category") or "\uae30\ud0c0"
    if category == "\uae30\ud0c0":
        category = "\uc8fc\uc808\uc8fc\uc808"
    post_id = str(post.get("id") or "")
    if liked_post_ids is None:
        liked_post_ids = current_community_like_ids()
    if liked_comment_ids is None:
        liked_comment_ids = current_community_comment_like_ids()
    visibility = post.get("visibility") or "public"
    can_view = can_view_community_post(post) if visibility == "private" else True
    comments = normalize_community_comments(post)
    attachment_limit = CHANNEL_ATTACHMENT_MAX_COUNT if category == "\ucc44\ub110" else COMMUNITY_ATTACHMENT_MAX_COUNT
    attachments = normalize_community_attachments(post.get("attachments"), attachment_limit) if can_view else []
    author_profile = get_user_public_profile(post.get("username"), post.get("author") or "\uc775\uba85")
    return {
        "id": post.get("id"),
        "category": category,
        "title": (post.get("title") or "") if can_view else "\ube44\uacf5\uac1c \uae00\uc785\ub2c8\ub2e4",
        "body": strip_community_channel_marker(post.get("body")) if can_view else "",
        "author": author_profile.get("name") or "\uc775\uba85",
        "avatarUrl": author_profile.get("avatarUrl") or "",
        "profileMessage": author_profile.get("profileMessage") or "",
        "channelIntro": author_profile.get("channelIntro") or "",
        "channelName": author_profile.get("channelName") or "",
        "channelCreated": bool(author_profile.get("channelCreated")),
        "followerCount": int(author_profile.get("followerCount") or 0),
        "username": post.get("username"),
        "status": post.get("status") or "\uc811\uc218",
        "createdAt": post.get("createdAt"),
        "updatedAt": post.get("updatedAt"),
        "views": int(post.get("views") or 0),
        "likes": int(post.get("likes") or 0),
        "liked": post_id in liked_post_ids,
        "visibility": visibility,
        "canView": can_view,
        "canEdit": can_edit_community_post(post),
        "commentCount": len(comments),
        "comments": [public_community_comment(item, liked_comment_ids) for item in comments] if can_view else [],
        "attachments": attachments,
        "channelId": extract_community_channel_id(post),
    }
def is_super_admin(username=None):
    if username is None:
        username = session.get("username") if has_request_context() else None
    return normalize_login_id(username) == normalize_login_id(SUPER_ADMIN_USERNAME)


def can_view_community_post(post, username=None):
    if not post:
        return False
    if post.get("visibility") != "private":
        return True
    if username is None:
        username = session.get("username") if has_request_context() else None
    if is_super_admin(username):
        return True
    return normalize_login_id(post.get("username")) == normalize_login_id(username)


def can_edit_community_post(post, username=None):
    if not post:
        return False
    if username is None:
        username = session.get("username") if has_request_context() else None
    if not username:
        return False
    if is_super_admin(username):
        return True
    return normalize_login_id(post.get("username")) == normalize_login_id(username)


def normalize_community_category_value(value):
    category = str(value or "주절주절").strip()
    if category == "기타":
        category = "주절주절"
    if category not in {"불편사항", "개선요청", "주절주절", "채널"}:
        category = "주절주절"
    return category


def validate_community_payload(payload):
    category = normalize_community_category_value(payload.get("category"))
    visibility = str(payload.get("visibility", "public")).strip()
    if visibility not in {"public", "private"}:
        visibility = "public"
    title = re.sub(r"\s+", " ", str(payload.get("title", "")).strip())
    body = str(payload.get("body", "")).strip()
    if len(title) < 2 or len(title) > 80:
        raise ValueError("제목은 2~80자로 입력해주세요.")
    if len(body) < 5 or len(body) > 1000:
        raise ValueError("내용은 5~1000자로 입력해주세요.")
    return category, visibility, title, body


def load_community_posts(limit=50):
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            params={
                "select": "*",
                "order": "createdAt.desc",
                "limit": str(limit),
            },
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Supabase community load failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        liked_post_ids = current_community_like_ids()
        liked_comment_ids = current_community_comment_like_ids()
        username = session.get("username") if has_request_context() and session.get("logged_in") else None
        rows = filter_accessible_community_posts(response.json(), username)
        return [public_community_post(item, liked_post_ids, liked_comment_ids) for item in rows]

    data = read_json_file(COMMUNITY_FILE, {"posts": []})
    posts = data.get("posts", []) if isinstance(data, dict) else []
    posts = sorted(posts, key=lambda item: item.get("createdAt") or "", reverse=True)
    liked_post_ids = current_community_like_ids()
    liked_comment_ids = current_community_comment_like_ids()
    username = session.get("username") if has_request_context() and session.get("logged_in") else None
    visible_posts = filter_accessible_community_posts(posts[:limit], username)
    return [public_community_post(item, liked_post_ids, liked_comment_ids) for item in visible_posts]


def create_community_post(user, payload):
    category, visibility, title, body = validate_community_payload(payload)
    attachment_limit = CHANNEL_ATTACHMENT_MAX_COUNT if category == "\ucc44\ub110" else COMMUNITY_ATTACHMENT_MAX_COUNT
    attachments = normalize_community_attachments(payload.get("attachments"), attachment_limit)
    channel_id = str(payload.get("channelId") or "").strip()[:64]
    if category == "채널":
        channel = next((item for item in load_community_channels() if str(item.get("id")) == channel_id), None)
        if not channel or normalize_login_id(channel.get("owner")) != normalize_login_id(user.get("username")):
            raise PermissionError("본인이 운영하는 채널에만 메시지를 올릴 수 있습니다.")

    if category == "채널" and channel_id:
        body = community_channel_marker(channel_id) + body

    post = {
        "id": secrets.token_hex(8),
        "category": category,
        "title": title,
        "body": body,
        "author": user.get("nickname") or user.get("username") or "회원",
        "username": user.get("username"),
        "status": "접수",
        "createdAt": datetime.now(KST).isoformat(),
        "visibility": visibility,
        "views": 0,
        "likes": 0,
        "comments": [],
        "attachments": attachments,
        "channelId": channel_id,
    }

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        base_post = {key: post[key] for key in ("id", "category", "title", "body", "author", "username", "status", "createdAt")}
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=post,
            timeout=15,
        )
        if response.status_code >= 400 and any(field in response.text for field in ("visibility", "views", "likes", "comments", "attachments", "channelId")):
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
                headers={
                    "apikey": SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                },
                json=base_post,
                timeout=15,
            )
        if response.status_code >= 400:
            print(f"Supabase community save failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        return public_community_post(data[0] if data else post)

    data = read_json_file(COMMUNITY_FILE, {"posts": []})
    posts = data.get("posts", []) if isinstance(data, dict) else []
    posts.insert(0, post)
    write_json_file(COMMUNITY_FILE, {"posts": posts[:200]})
    return public_community_post(post)


def update_community_post(post_id, user, payload):
    existing = get_community_post(post_id, increment_views=False)
    if not existing:
        return None
    username = user.get("username") if user else session.get("username")
    if not can_edit_community_post(existing, username):
        raise PermissionError("작성자만 게시글을 수정할 수 있습니다.")

    category, visibility, title, body = validate_community_payload(payload)
    channel_id = str(payload.get("channelId") or existing.get("channelId") or "").strip()[:64]
    if category == "채널" and channel_id:
        body = community_channel_marker(channel_id) + body
    attachment_limit = CHANNEL_ATTACHMENT_MAX_COUNT if category == "\ucc44\ub110" else COMMUNITY_ATTACHMENT_MAX_COUNT
    next_attachments = normalize_community_attachments(payload.get("attachments"), attachment_limit)
    old_attachment_paths = set(community_attachment_paths(existing.get("attachments")))
    next_attachment_paths = set(community_attachment_paths(next_attachments))
    removed_attachment_paths = sorted(old_attachment_paths - next_attachment_paths)
    updates = {
        "category": category,
        "visibility": visibility,
        "title": title,
        "body": body,
        "attachments": next_attachments,
        "updatedAt": datetime.now(KST).isoformat(),
    }

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            params={"id": f"eq.{post_id}", "select": "*"},
            json=updates,
            timeout=15,
        )
        if response.status_code >= 400 and "updatedAt" in response.text:
            fallback_updates = {key: value for key, value in updates.items() if key != "updatedAt"}
            response = requests.patch(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
                headers={
                    "apikey": SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                },
                params={"id": f"eq.{post_id}", "select": "*"},
                json=fallback_updates,
                timeout=15,
            )
        if response.status_code >= 400:
            print(f"Supabase community update failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        delete_community_attachment_paths(removed_attachment_paths)
        updated_post = data[0] if data else {**existing, **updates}
        if updates.get("updatedAt") and not updated_post.get("updatedAt"):
            updated_post = {**updated_post, "updatedAt": updates.get("updatedAt")}
        return public_community_post(updated_post)

    data = read_json_file(COMMUNITY_FILE, {"posts": []})
    posts = data.get("posts", []) if isinstance(data, dict) else []
    for item in posts:
        if str(item.get("id")) == str(post_id):
            if not can_edit_community_post(item, username):
                raise PermissionError("작성자만 게시글을 수정할 수 있습니다.")
            item.update(updates)
            write_json_file(COMMUNITY_FILE, {"posts": posts})
            delete_community_attachment_paths(removed_attachment_paths)
            return public_community_post(item)
    return None


def delete_community_post(post_id, user):
    existing = get_community_post(post_id, increment_views=False)
    if not existing:
        return False
    username = user.get("username") if user else session.get("username")
    if not can_edit_community_post(existing, username):
        raise PermissionError("작성자만 게시글을 삭제할 수 있습니다.")

    attachment_paths = community_attachment_paths(existing.get("attachments"))

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.delete(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            params={"id": f"eq.{post_id}"},
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Supabase community delete failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        delete_community_attachment_paths(attachment_paths)
        return True

    data = read_json_file(COMMUNITY_FILE, {"posts": []})
    posts = data.get("posts", []) if isinstance(data, dict) else []
    next_posts = []
    deleted = False
    for item in posts:
        if str(item.get("id")) == str(post_id):
            if not can_edit_community_post(item, username):
                raise PermissionError("작성자만 게시글을 삭제할 수 있습니다.")
            deleted = True
            continue
        next_posts.append(item)
    if deleted:
        write_json_file(COMMUNITY_FILE, {"posts": next_posts})
        delete_community_attachment_paths(attachment_paths)
    return deleted


def get_community_post_raw(post_id):
    post_id = str(post_id or "").strip()
    if not post_id:
        return None

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            params={
                "id": f"eq.{post_id}",
                "select": "*",
                "limit": "1",
            },
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Supabase community raw load failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        return data[0] if data else None

    data = read_json_file(COMMUNITY_FILE, {"posts": []})
    posts = data.get("posts", []) if isinstance(data, dict) else []
    for post in posts:
        if str(post.get("id")) == post_id:
            return post
    return None


def get_community_post(post_id, increment_views=False):
    post_id = str(post_id or "").strip()
    if not post_id:
        return None

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            params={
                "id": f"eq.{post_id}",
                "select": "*",
                "limit": "1",
            },
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Supabase community detail load failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        if not data:
            return None
        post = data[0]
        if increment_views:
            next_views = int(post.get("views") or 0) + 1
            try:
                patch = requests.patch(
                    f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
                    headers={
                        "apikey": SUPABASE_SERVICE_ROLE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation",
                    },
                    params={"id": f"eq.{post_id}", "select": "*"},
                    json={"views": next_views},
                    timeout=15,
                )
                if patch.status_code < 400:
                    patched = patch.json()
                    post = patched[0] if patched else {**post, "views": next_views}
                else:
                    post["views"] = next_views
            except Exception as exc:
                print(f"Community views update failed: {exc}", flush=True)
                post["views"] = next_views
        return public_community_post(post)

    data = read_json_file(COMMUNITY_FILE, {"posts": []})
    posts = data.get("posts", []) if isinstance(data, dict) else []
    for post in posts:
        if str(post.get("id")) == post_id:
            if increment_views:
                post["views"] = int(post.get("views") or 0) + 1
                write_json_file(COMMUNITY_FILE, {"posts": posts})
            return public_community_post(post)
    return None


def check_community_like_rate_limit():
    now = time.time()
    window = max(5, COMMUNITY_LIKE_WINDOW_SECONDS)
    max_events = max(3, COMMUNITY_LIKE_MAX_EVENTS)
    events = session.get("community_like_events") or []
    events = [float(item) for item in events if isinstance(item, (int, float)) and now - float(item) < window]
    if len(events) >= max_events:
        retry_after = max(1, int(window - (now - events[0])))
        return False, retry_after
    events.append(now)
    session["community_like_events"] = events
    session.modified = True
    return True, None


def like_community_post(post_id, username=None):
    username = username if username is not None else session.get("username")
    if not username:
        raise PermissionError("\ub85c\uadf8\uc778 \ud6c4 \uc88b\uc544\uc694\ub97c \ub204\ub97c \uc218 \uc788\uc2b5\ub2c8\ub2e4.")

    post_id = str(post_id or "").strip()
    normalized_username = canonical_session_username(username)
    post = get_community_post(post_id, increment_views=False)
    if not post:
        return None

    liked_posts = current_community_like_ids(normalized_username)
    was_liked = post_id in liked_posts
    next_liked = not was_liked
    table_updated = set_table_community_post_like(post_id, normalized_username, next_liked)

    if table_updated is not True:
        settings = get_user_app_settings(normalized_username)
        liked_posts_list = [str(item) for item in settings.get("communityLikes", []) if item]
        if was_liked:
            next_liked_posts = [item for item in liked_posts_list if item != post_id]
        else:
            next_liked_posts = ([post_id] + [item for item in liked_posts_list if item != post_id])[:1000]
        settings["communityLikes"] = next_liked_posts
        save_user_app_settings(normalized_username, settings)
        next_liked_ids = set(next_liked_posts)
    else:
        next_liked_ids = set(liked_posts)
        if next_liked:
            next_liked_ids.add(post_id)
        else:
            next_liked_ids.discard(post_id)

    next_likes = count_community_post_likes(post_id)
    updated_post = None
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            params={"id": f"eq.{post_id}", "select": "*"},
            json={"likes": next_likes},
            timeout=8,
        )
        if response.status_code >= 400:
            print(f"Supabase community like failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        updated_post = data[0] if data else {**post, "likes": next_likes}
    else:
        data = read_json_file(COMMUNITY_FILE, {"posts": []})
        posts = data.get("posts", []) if isinstance(data, dict) else []
        for item in posts:
            if str(item.get("id")) == post_id:
                item["likes"] = next_likes
                write_json_file(COMMUNITY_FILE, {"posts": posts})
                updated_post = item
                break

    if not updated_post:
        updated_post = {**post, "likes": next_likes}
    return public_community_post(updated_post, next_liked_ids)


def add_community_comment(post_id, user, payload):
    username = user.get("username") if user else session.get("username")
    if not username:
        raise PermissionError("\ub85c\uadf8\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4.")
    body = validate_community_comment_payload(payload)
    post = get_community_post_raw(post_id)
    if not post:
        return None
    if not can_view_community_post(post, username):
        raise PermissionError("\ube44\uacf5\uac1c \uae00\uc5d0\ub294 \ub2f5\uae00\uc744 \ub0a8\uae38 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.")

    comments = normalize_community_comments(post)
    comments.append({
        "id": secrets.token_hex(8),
        "body": body,
        "author": user.get("nickname") or user.get("username") or "\ud68c\uc6d0",
        "username": username,
        "createdAt": datetime.now(KST).isoformat(),
        "likes": 0,
        "likedBy": [],
    })
    comments = comments[-500:]

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            params={"id": f"eq.{post_id}", "select": "*"},
            json={"comments": comments},
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Supabase community comment save failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        return public_community_post(data[0] if data else {**post, "comments": comments})

    data = read_json_file(COMMUNITY_FILE, {"posts": []})
    posts = data.get("posts", []) if isinstance(data, dict) else []
    for item in posts:
        if str(item.get("id")) == str(post_id):
            item["comments"] = comments
            write_json_file(COMMUNITY_FILE, {"posts": posts})
            return public_community_post(item)
    return None


def like_community_comment(post_id, comment_id, username=None):
    username = username if username is not None else session.get("username")
    if not username:
        raise PermissionError("\ub85c\uadf8\uc778 \ud6c4 \uc88b\uc544\uc694\ub97c \ub204\ub97c \uc218 \uc788\uc2b5\ub2c8\ub2e4.")

    post = get_community_post_raw(post_id)
    if not post:
        return None
    if not can_view_community_post(post, username):
        raise PermissionError("\ube44\uacf5\uac1c \uae00\uc785\ub2c8\ub2e4.")

    comments = normalize_community_comments(post)
    target = next((item for item in comments if str(item.get("id")) == str(comment_id)), None)
    if not target:
        return post

    comment_id = str(comment_id or "").strip()
    normalized_username = normalize_login_id(username)
    liked_by = target.get("likedBy") or []
    if not isinstance(liked_by, list):
        liked_by = []
    liked_by = [normalize_login_id(item) for item in liked_by if normalize_login_id(item)]
    liked_by = list(dict.fromkeys(liked_by))
    was_liked = normalized_username in liked_by

    if was_liked:
        liked_by = [item for item in liked_by if item != normalized_username]
    else:
        liked_by = ([normalized_username] + liked_by)[:1000]
    target["likedBy"] = liked_by
    target["likes"] = len(liked_by)

    updated_post = None
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            params={"id": f"eq.{post_id}", "select": "*"},
            json={"comments": comments},
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Supabase community comment like failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        updated_post = data[0] if data else {**post, "comments": comments}
    else:
        data = read_json_file(COMMUNITY_FILE, {"posts": []})
        posts = data.get("posts", []) if isinstance(data, dict) else []
        for item in posts:
            if str(item.get("id")) == str(post_id):
                item["comments"] = comments
                write_json_file(COMMUNITY_FILE, {"posts": posts})
                updated_post = item
                break

    if not updated_post:
        return None

    try:
        settings = get_user_app_settings(username)
        liked_comments = [str(item) for item in settings.get("communityCommentLikes", []) if item]
        if was_liked:
            next_liked_comments = [item for item in liked_comments if item != comment_id]
        else:
            next_liked_comments = ([comment_id] + liked_comments)[:3000]
        settings["communityCommentLikes"] = next_liked_comments
        save_user_app_settings(username, settings)
    except Exception as exc:
        print(f"Community comment like settings save skipped: {exc}", flush=True)

    return public_community_post(updated_post, current_community_like_ids(username), current_community_comment_like_ids(username))


def delete_community_comment(post_id, comment_id, user):
    username = user.get("username") if user else session.get("username")
    if not username:
        raise PermissionError("\ub85c\uadf8\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4.")
    post = get_community_post_raw(post_id)
    if not post:
        return None
    if not can_view_community_post(post, username):
        raise PermissionError("\ube44\uacf5\uac1c \uae00\uc785\ub2c8\ub2e4.")
    comments = normalize_community_comments(post)
    target = next((item for item in comments if str(item.get("id")) == str(comment_id)), None)
    if not target:
        return post
    if not can_edit_community_comment(target, username):
        raise PermissionError("\ub2f5\uae00 \uc791\uc131\uc790\ub098 \uad00\ub9ac\uc790\ub9cc \uc0ad\uc81c\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.")
    next_comments = [item for item in comments if str(item.get("id")) != str(comment_id)]

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            params={"id": f"eq.{post_id}", "select": "*"},
            json={"comments": next_comments},
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Supabase community comment delete failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        return public_community_post(data[0] if data else {**post, "comments": next_comments})

    data = read_json_file(COMMUNITY_FILE, {"posts": []})
    posts = data.get("posts", []) if isinstance(data, dict) else []
    for item in posts:
        if str(item.get("id")) == str(post_id):
            item["comments"] = next_comments
            write_json_file(COMMUNITY_FILE, {"posts": posts})
            return public_community_post(item)
    return None

def prune_email_codes():
    now = time.time()
    expired = [email for email, item in EMAIL_VERIFICATION_CODES.items() if item.get("expiresAt", 0) < now]
    for email in expired:
        EMAIL_VERIFICATION_CODES.pop(email, None)


def send_verification_email(email, code):
    subject = "[BiK] 호두 아카데미 인증코드입니다"
    text = (
        "인증 코드를 입력해 이메일 인증을 완료해 주세요.\n\n"
        f"인증코드: {code}\n\n"
        "본인이 요청하지 않은 경우 이 메일은 무시해 주세요.\n"
        "인증 코드는 발송 시점으로부터 3분 후 만료됩니다."
    )
    html = (
        "<div dir=\"ltr\" style=\"background:#ffffff;margin:0;padding:0\">"
        "<table border=\"0\" cellpadding=\"0\" cellspacing=\"0\" width=\"100%\" bgcolor=\"#ffffff\" "
        "style=\"font-family:'Malgun Gothic','맑은 고딕',AppleSDGothicNeo-Regular,dotum,'돋움',sans-serif\">"
        "<tr><td>"
        "<table align=\"center\" border=\"0\" cellpadding=\"0\" cellspacing=\"0\" width=\"600\" "
        "style=\"width:600px;max-width:100%;padding:60px 40px;font-size:15px;color:#0c0c0c;letter-spacing:-0.2px;margin:0 auto\">"
        "<tr><td>"
        "<a target=\"_blank\" href=\"https://bikresearch.onrender.com\" style=\"display:inline-block;padding:5px 10px;text-decoration:none\">"
        "<span style=\"display:inline-block;color:#a51332;font-weight:900;font-size:26px;letter-spacing:0\">BiK</span>"
        "</a>"
        "</td></tr>"
        "<tr><td height=\"60\"></td></tr>"
        "<tr><td align=\"center\">"
        "<table align=\"center\" border=\"0\" cellpadding=\"0\" cellspacing=\"0\" width=\"420\" style=\"width:100%;padding:0 50px;font-size:15px\">"
        "<tr><td style=\"font-weight:700;font-size:26px;padding-bottom:12px;line-height:140%;letter-spacing:-0.5px\">"
        "인증 코드를 입력해<br>이메일 인증을 완료해 주세요."
        "</td></tr>"
        "<tr><td style=\"padding-bottom:36px;line-height:140%\">"
        "본인이 요청하지 않은 경우 이 메일은 무시해 주세요.<br>인증 코드는 발송 시점으로부터 3분 후 만료됩니다."
        "</td></tr>"
        "<tr><td bgcolor=\"#F9F9FA\" style=\"border:1px solid #e8e8e8;border-radius:4px;padding:22px 0\">"
        "<table align=\"center\" border=\"0\" cellpadding=\"0\" cellspacing=\"0\" width=\"100%\">"
        "<tr><td align=\"center\" style=\"font-size:13px;color:#8e8e93\">인증번호</td></tr>"
        "<tr><td height=\"6\"></td></tr>"
        f"<tr><td align=\"center\" style=\"font-size:39px;color:#0c0c0c;letter-spacing:6px\"><strong>{code}</strong></td></tr>"
        "</table>"
        "</td></tr>"
        "<tr><td height=\"60\"></td></tr>"
        "<tr><td height=\"1\" bgcolor=\"#eee\"></td></tr>"
        "<tr><td height=\"32\"></td></tr>"
        "<tr><td style=\"font-size:13px;color:#8e8e93;line-height:145%\">"
        "본 메일은 발신 전용입니다.<br>궁금하신 내용은 호두 아카데미 설정 메뉴를 이용해 주세요."
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</div>"
    )

    if RESEND_API_KEY:
        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": RESEND_FROM,
                    "to": [email],
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
                timeout=15,
            )
            if response.status_code < 400:
                return True, None
            print(f"Resend email failed: {response.status_code} {response.text[:500]}", flush=True)
            return False, "인증메일 발송에 실패했습니다. Resend 발신자/도메인 설정을 확인해주세요."
        except Exception as exc:
            print(f"Resend email failed: {exc}", flush=True)
            return False, "인증메일 발송에 실패했습니다. Resend 연결을 확인해주세요."

    if not SMTP_HOST or not SMTP_USERNAME or not SMTP_PASSWORD or not SMTP_FROM:
        return False, "메일 발송 설정이 필요합니다. Render 환경변수에 RESEND_API_KEY 또는 SMTP 정보를 추가해주세요."

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_FROM
    message["To"] = email
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        smtp_client = smtplib.SMTP_SSL if SMTP_USE_SSL else smtplib.SMTP
        with smtp_client(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            if SMTP_USE_TLS and not SMTP_USE_SSL:
                server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        return True, None
    except Exception as exc:
        print(f"Verification email failed: {exc}", flush=True)
        return False, "인증메일 발송에 실패했습니다. 메일 설정을 확인해주세요."


def verify_email_code(email, code, purpose=None):
    prune_email_codes()
    item = EMAIL_VERIFICATION_CODES.get(normalize_login_id(email))
    if not item:
        return False
    if purpose and item.get("purpose") != purpose:
        return False
    if not check_password_hash(item.get("codeHash", ""), str(code or "").strip()):
        return False
    item["verified"] = True
    return True


def record_usage_rpc(function_name, payload):
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return False
    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/{function_name}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=8,
        )
        if response.status_code >= 400:
            print(f"Usage analytics RPC failed({function_name}): {response.status_code} {response.text[:300]}", flush=True)
            return False
        return True
    except Exception as exc:
        print(f"Usage analytics RPC failed({function_name}): {exc}", flush=True)
        return False


def record_login_activity(username):
    normalized = normalize_login_id(username)
    if not normalized:
        return False
    return record_usage_rpc("hodu_record_login", {"p_username": normalized})


def record_tab_activity(username, tab_name):
    normalized = normalize_login_id(username)
    tab_name = str(tab_name or "").strip().lower()
    if not normalized or tab_name not in USAGE_TAB_NAMES:
        return False
    return record_usage_rpc(
        "hodu_record_tab_view",
        {"p_username": normalized, "p_tab_name": tab_name},
    )


def delete_user_usage_activity(username):
    normalized = normalize_login_id(username)
    if not normalized or not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_USAGE_DAILY_TABLE):
        return False
    try:
        response = requests.delete(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_USAGE_DAILY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Prefer": "return=minimal",
            },
            params={"username": f"eq.{normalized}"},
            timeout=10,
        )
        return response.status_code < 400
    except Exception as exc:
        print(f"User usage cleanup failed: {exc}", flush=True)
        return False


@app.route("/api/usage/tab", methods=["POST"])
def usage_tab_view():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "???? ?????."}), 401
    payload = request.get_json(silent=True) or {}
    tab_name = str(payload.get("tab") or "").strip().lower()
    if tab_name not in USAGE_TAB_NAMES:
        return jsonify({"ok": False, "error": "???? ?? ????."}), 400
    recorded = record_tab_activity(session.get("username"), tab_name)
    return jsonify({"ok": True, "recorded": recorded})


@app.route("/api/auth/status")
def auth_status():
    logged_in = bool(session.get("logged_in"))
    return jsonify({
        "loggedIn": logged_in,
        "username": session.get("username") if logged_in else None,
        "nickname": session.get("nickname") if logged_in else None,
        "email": None,
        "isSuperAdmin": is_super_admin() if logged_in else False,
    })


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))

    user = find_user(username)
    if user and check_password_hash(user.get("passwordHash", ""), password):
        session.permanent = True
        session["logged_in"] = True
        session["username"] = user.get("username")
        session["nickname"] = user.get("nickname") or user.get("username")
        start_thread(lambda: record_login_activity(user.get("username")))
        return jsonify({"ok": True, "username": user.get("username"), "nickname": session["nickname"]})

    if username == APP_USERNAME and password == APP_PASSWORD:
        session.permanent = True
        session["logged_in"] = True
        session["username"] = username
        session["nickname"] = username
        start_thread(lambda: record_login_activity(username))
        return jsonify({"ok": True, "username": username, "nickname": username})

    return jsonify({"ok": False, "error": "아이디 또는 비밀번호가 올바르지 않습니다."}), 401


@app.route("/api/auth/send-verification", methods=["POST"])
def auth_send_verification():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"ok": False, "error": "올바른 이메일을 입력해주세요."}), 400

    if email_already_registered(email):
        return jsonify({"ok": False, "error": "이미 가입된 이메일입니다."}), 409

    prune_email_codes()
    normalized = normalize_login_id(email)
    existing = EMAIL_VERIFICATION_CODES.get(normalized)
    now = time.time()
    if existing and now - existing.get("sentAt", 0) < 60:
        return jsonify({"ok": False, "error": "인증메일은 1분 뒤 다시 발송할 수 있습니다."}), 429

    code = f"{secrets.randbelow(1000000):06d}"
    sent, error = send_verification_email(email, code)
    if not sent:
        return jsonify({"ok": False, "error": error}), 503

    EMAIL_VERIFICATION_CODES[normalized] = {
        "codeHash": generate_password_hash(code),
        "sentAt": now,
        "expiresAt": now + EMAIL_VERIFICATION_TTL_SECONDS,
        "verified": False,
        "purpose": "signup",
    }
    return jsonify({"ok": True, "email": email, "expiresInSeconds": EMAIL_VERIFICATION_TTL_SECONDS})


@app.route("/api/auth/verify-code", methods=["POST"])
def auth_verify_code():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    verification_code = str(payload.get("verificationCode", "")).strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"ok": False, "error": "올바른 이메일을 입력해주세요."}), 400
    if not verify_email_code(email, verification_code, "signup"):
        return jsonify({"ok": False, "error": "인증코드가 올바르지 않거나 만료되었습니다."}), 400
    return jsonify({"ok": True, "email": email})


@app.route("/api/auth/password-reset/send", methods=["POST"])
def auth_password_reset_send():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"ok": False, "error": "올바른 이메일을 입력해주세요."}), 400

    prune_email_codes()
    normalized = normalize_login_id(email)
    existing = EMAIL_VERIFICATION_CODES.get(normalized)
    now = time.time()
    if existing and existing.get("purpose") == "password-reset" and now - existing.get("sentAt", 0) < 60:
        return jsonify({"ok": False, "error": "재설정 메일은 1분 뒤 다시 발송할 수 있습니다."}), 429

    user = find_user(email)
    if user:
        code = f"{secrets.randbelow(1000000):06d}"
        sent, error = send_verification_email(email, code)
        if not sent:
            return jsonify({"ok": False, "error": error}), 503
        EMAIL_VERIFICATION_CODES[normalized] = {
            "codeHash": generate_password_hash(code),
            "sentAt": now,
            "expiresAt": now + EMAIL_VERIFICATION_TTL_SECONDS,
            "verified": False,
            "purpose": "password-reset",
            "username": user.get("username"),
        }

    return jsonify({
        "ok": True,
        "email": email,
        "expiresInSeconds": EMAIL_VERIFICATION_TTL_SECONDS,
        "message": "가입된 이메일이라면 인증코드가 발송됩니다.",
    })


@app.route("/api/auth/password-reset/confirm", methods=["POST"])
def auth_password_reset_confirm():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    verification_code = str(payload.get("verificationCode", "")).strip()
    password = str(payload.get("password", ""))
    password_confirm = str(payload.get("passwordConfirm", ""))

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"ok": False, "error": "올바른 이메일을 입력해주세요."}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "error": "새 비밀번호는 8자 이상으로 입력해주세요."}), 400
    if password != password_confirm:
        return jsonify({"ok": False, "error": "새 비밀번호 확인이 일치하지 않습니다."}), 400
    if not verify_email_code(email, verification_code, "password-reset"):
        return jsonify({"ok": False, "error": "인증코드가 올바르지 않거나 만료되었습니다."}), 400

    item = EMAIL_VERIFICATION_CODES.get(normalize_login_id(email)) or {}
    user = find_user(item.get("username") or email)
    if not user:
        return jsonify({"ok": False, "error": "계정을 찾을 수 없습니다."}), 404

    try:
        updated_user = update_user(user.get("username"), {"passwordHash": generate_password_hash(password)})
    except Exception as exc:
        print(f"Password reset failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "비밀번호 재설정에 실패했습니다. 잠시 후 다시 시도해주세요."}), 500

    if not updated_user:
        return jsonify({"ok": False, "error": "비밀번호 재설정에 실패했습니다. 잠시 후 다시 시도해주세요."}), 500

    EMAIL_VERIFICATION_CODES.pop(normalize_login_id(email), None)
    return jsonify({"ok": True})


@app.route("/api/auth/check-profile", methods=["POST"])
def auth_check_profile():
    payload = request.get_json(silent=True) or {}
    nickname = str(payload.get("nickname", "")).strip()
    if len(nickname) < 2 or len(nickname) > 20:
        return jsonify({"ok": False, "error": "닉네임은 2~20자로 입력해주세요."}), 400
    if find_user(nickname) or normalize_login_id(nickname) == normalize_login_id(APP_USERNAME):
        return jsonify({"ok": False, "error": "이미 사용 중인 닉네임입니다."}), 409
    return jsonify({"ok": True})


@app.route("/api/auth/profile")
def auth_profile():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user = find_user(session.get("username"))
    if not user:
        return jsonify({
            "ok": True,
            "user": {
                "username": session.get("username"),
                "nickname": session.get("nickname") or session.get("username"),
                "email": "",
                "createdAt": "",
                "managed": False,
            }
        })
    profile = public_user(user)
    profile["managed"] = True
    return jsonify({"ok": True, "user": profile})


@app.route("/api/auth/profile", methods=["PATCH"])
def auth_update_profile():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user = find_user(session.get("username"))
    if not user:
        return jsonify({"ok": False, "error": "기본 관리자 계정은 프로필 수정 대상이 아닙니다."}), 400

    payload = request.get_json(silent=True) or {}
    nickname = str(payload.get("nickname", "")).strip()
    current_password = str(payload.get("currentPassword", ""))
    new_password = str(payload.get("newPassword", ""))
    new_password_confirm = str(payload.get("newPasswordConfirm", ""))
    profile_message = normalize_profile_message(payload.get("profileMessage"))
    updates = {}
    settings_changed = False
    current_settings = get_user_app_settings(user.get("username"))
    if profile_message != normalize_profile_message(current_settings.get("profileMessage")):
        current_settings["profileMessage"] = profile_message
        settings_changed = True

    if nickname and nickname != user.get("nickname"):
        if len(nickname) < 2 or len(nickname) > 20:
            return jsonify({"ok": False, "error": "닉네임은 2~20자로 입력해주세요."}), 400
        found = find_user(nickname)
        if found and normalize_login_id(found.get("username")) != normalize_login_id(user.get("username")):
            return jsonify({"ok": False, "error": "이미 사용 중인 닉네임입니다."}), 409
        updates["nickname"] = nickname

    if new_password or new_password_confirm or current_password:
        if not check_password_hash(user.get("passwordHash", ""), current_password):
            return jsonify({"ok": False, "error": "현재 비밀번호가 올바르지 않습니다."}), 400
        if len(new_password) < 8:
            return jsonify({"ok": False, "error": "새 비밀번호는 8자 이상으로 입력해주세요."}), 400
        if new_password != new_password_confirm:
            return jsonify({"ok": False, "error": "새 비밀번호 확인이 일치하지 않습니다."}), 400
        updates["passwordHash"] = generate_password_hash(new_password)

    if settings_changed:
        try:
            saved_settings = save_user_app_settings(user.get("username"), current_settings)
            if saved_settings is None:
                return jsonify({"ok": False, "error": "프로필 메시지 저장에 실패했습니다."}), 500
            invalidate_user_display_name_cache(user.get("username"))
        except Exception as exc:
            print(f"Profile message update failed: {exc}", flush=True)
            return jsonify({"ok": False, "error": "프로필 메시지 저장에 실패했습니다."}), 500

    if not updates:
        profile = public_user(user)
        profile["managed"] = True
        return jsonify({"ok": True, "user": profile})

    try:
        updated = update_user(user.get("username"), updates)
    except Exception as exc:
        print(f"Profile update failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "프로필 저장에 실패했습니다."}), 500
    if not updated:
        return jsonify({"ok": False, "error": "사용자를 찾을 수 없습니다."}), 404

    invalidate_user_display_name_cache(updated.get("username") or user.get("username"))
    session["nickname"] = updated.get("nickname") or updated.get("username")
    profile = public_user(updated)
    profile["managed"] = True
    return jsonify({"ok": True, "user": profile})


@app.route("/api/auth/profile/photo", methods=["POST"])
def auth_upload_profile_photo():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user = find_user(session.get("username"))
    if not user:
        return jsonify({"ok": False, "error": "기본 관리자 계정은 프로필 사진 수정 대상이 아닙니다."}), 400
    try:
        current_settings = get_user_app_settings(user.get("username"))
        old_photo = normalize_profile_photo(current_settings.get("profilePhoto"))
        profile_photo = upload_profile_photo_file(request.files.get("file"), user)
        next_settings = current_settings.copy()
        next_settings["profilePhoto"] = profile_photo
        saved = save_user_app_settings(user.get("username"), next_settings)
        if saved is None:
            delete_community_attachment_paths([profile_photo.get("path")])
            return jsonify({"ok": False, "error": "프로필 사진 저장에 실패했습니다."}), 500
        old_path = old_photo.get("path")
        if old_path and old_path != profile_photo.get("path"):
            delete_community_attachment_paths([old_path])
        invalidate_user_display_name_cache(user.get("username"))
        profile = public_user(user)
        profile["managed"] = True
        return jsonify({"ok": True, "user": profile})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        print(f"Profile photo upload failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "프로필 사진 업로드에 실패했습니다."}), 500


@app.route("/api/auth/profile/photo", methods=["DELETE"])
def auth_delete_profile_photo():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user = find_user(session.get("username"))
    if not user:
        return jsonify({"ok": False, "error": "기본 관리자 계정은 프로필 사진 수정 대상이 아닙니다."}), 400
    try:
        current_settings = get_user_app_settings(user.get("username"))
        old_photo = normalize_profile_photo(current_settings.get("profilePhoto"))
        next_settings = current_settings.copy()
        next_settings["profilePhoto"] = {}
        saved = save_user_app_settings(user.get("username"), next_settings)
        if saved is None:
            return jsonify({"ok": False, "error": "프로필 사진 삭제에 실패했습니다."}), 500
        if old_photo.get("path"):
            delete_community_attachment_paths([old_photo.get("path")])
        invalidate_user_display_name_cache(user.get("username"))
        profile = public_user(user)
        profile["managed"] = True
        return jsonify({"ok": True, "user": profile})
    except Exception as exc:
        print(f"Profile photo delete failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "프로필 사진 삭제에 실패했습니다."}), 500


@app.route("/api/auth/profile", methods=["DELETE"])
def auth_delete_profile():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user = find_user(session.get("username"))
    if not user:
        return jsonify({"ok": False, "error": "기본 관리자 계정은 회원 탈퇴 대상이 아닙니다."}), 400

    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password", ""))
    if not check_password_hash(user.get("passwordHash", ""), password):
        return jsonify({"ok": False, "error": "비밀번호가 올바르지 않습니다."}), 400

    try:
        deleted = delete_user(user.get("username"))
    except Exception as exc:
        print(f"Profile delete failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "회원 탈퇴 처리에 실패했습니다. 잠시 후 다시 시도해주세요."}), 500
    if not deleted:
        return jsonify({"ok": False, "error": "사용자를 찾을 수 없습니다."}), 404

    delete_user_usage_activity(user.get("username"))
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/user/settings")
def user_settings():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    try:
        settings = get_user_app_settings(session.get("username"))
    except Exception as exc:
        print(f"User settings load failed: {exc}", flush=True)
        return jsonify({
            "ok": False,
            "error": "계정 설정을 불러오지 못했습니다. Supabase appSettings 컬럼을 확인해주세요.",
        }), 500
    return jsonify({"ok": True, "settings": settings})


@app.route("/api/user/settings", methods=["PATCH"])
@serialize_user_settings_save
def update_user_settings():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    payload = request.get_json(silent=True) or {}
    try:
        current = get_user_app_settings(session.get("username"))
        next_settings = current.copy()
        if "watchlist" in payload:
            incoming_watchlist = payload.get("watchlist")
            allow_empty_watchlist = bool(payload.get("_allowEmptyWatchlist"))
            if not (isinstance(incoming_watchlist, list) and not incoming_watchlist and current.get("watchlist") and not allow_empty_watchlist):
                next_settings["watchlist"] = incoming_watchlist
        if "companyWatchlistMeta" in payload:
            next_settings["companyWatchlistMeta"] = payload.get("companyWatchlistMeta")
        if "ethTracker" in payload:
            next_settings["ethTracker"] = payload.get("ethTracker")
        if "companyBeta" in payload:
            incoming_company_beta = payload.get("companyBeta")
            allow_empty_beta_watchlist = bool(payload.get("_allowEmptyCompanyBetaWatchlist"))
            if isinstance(incoming_company_beta, dict):
                current_beta_watchlist = current.get("companyBeta", {}).get("watchlist") if isinstance(current.get("companyBeta"), dict) else []
                incoming_beta_watchlist = incoming_company_beta.get("watchlist")
                if isinstance(incoming_beta_watchlist, list) and not incoming_beta_watchlist and current_beta_watchlist and not allow_empty_beta_watchlist:
                    incoming_company_beta = {**incoming_company_beta, "watchlist": current_beta_watchlist}
            next_settings["companyBeta"] = incoming_company_beta
        if "hyperliquidAlerts" in payload:
            next_settings["hyperliquidAlerts"] = payload.get("hyperliquidAlerts")
        if "hyperliquidPinned" in payload:
            next_settings["hyperliquidPinned"] = payload.get("hyperliquidPinned")
        if "hyperliquidPinnedTouched" in payload:
            next_settings["hyperliquidPinnedTouched"] = bool(payload.get("hyperliquidPinnedTouched"))
        if "notificationDismissed" in payload:
            next_settings["notificationDismissed"] = payload.get("notificationDismissed")
        if "communityFollows" in payload:
            next_settings["communityFollows"] = payload.get("communityFollows")
            COMMUNITY_FOLLOWER_COUNT_CACHE.clear()
        if "communityChannelReadAt" in payload:
            next_settings["communityChannelReadAt"] = payload.get("communityChannelReadAt")
        if "channelIntro" in payload:
            next_settings["channelIntro"] = payload.get("channelIntro")
        if "channelName" in payload:
            next_settings["channelName"] = payload.get("channelName")
        if "channelCreated" in payload:
            next_settings["channelCreated"] = bool(payload.get("channelCreated"))
            invalidate_user_display_name_cache(session.get("username"))
        saved = save_user_app_settings(session.get("username"), next_settings)
        if saved is None:
            raise RuntimeError("Supabase user settings row was not updated")
    except Exception as exc:
        print(f"User settings save failed: {exc}", flush=True)
        return jsonify({
            "ok": False,
            "error": "계정 설정 저장에 실패했습니다. Supabase appSettings 컬럼을 확인해주세요.",
        }), 500
    return jsonify({"ok": True, "settings": saved})


def load_community_posts_raw(limit=200):
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            params={"select": "*", "order": "createdAt.desc", "limit": str(limit)},
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Supabase community notification load failed: {response.status_code} {response.text[:500]}", flush=True)
            response.raise_for_status()
        return response.json()
    data = read_json_file(COMMUNITY_FILE, {"posts": []})
    posts = data.get("posts", []) if isinstance(data, dict) else []
    return sorted(posts, key=lambda item: item.get("createdAt") or "", reverse=True)[:limit]


def build_user_notifications(username):
    normalized_username = normalize_login_id(username)
    if not normalized_username:
        return []
    notifications = []
    try:
        settings = get_user_app_settings(normalized_username)
        followed_users = {normalize_login_id(item) for item in settings.get("communityFollows", []) if normalize_login_id(item)}
    except Exception as exc:
        print(f"Community follow notification settings load failed: {exc}", flush=True)
        followed_users = set()
    for post in load_community_posts_raw(200):
        post_id = str(post.get("id") or "")
        post_title = str(post.get("title") or "게시글")[:80]
        post_author = normalize_login_id(post.get("username"))
        comments = normalize_community_comments(post)
        if post_author in followed_users and post_author != normalized_username and post.get("visibility") != "private":
            author_name = str(get_user_display_name(post.get("username"), post.get("author") or "회원"))[:30]
            notifications.append({
                "id": f"community-follow-post:{post_id}",
                "type": "community-follow-post",
                "title": f"{author_name}님이 새 글을 올렸습니다",
                "body": post_title,
                "url": f"/Community/{post_id}",
                "createdAt": post.get("createdAt"),
            })
        if post_author == normalized_username:
            for comment in comments:
                if normalize_login_id(comment.get("username")) == normalized_username:
                    continue
                comment_id = str(comment.get("id") or secrets.token_hex(6))
                comment_author = str(get_user_display_name(comment.get("username"), comment.get("author") or "\ud68c\uc6d0"))[:30]
                comment_created_at = comment.get("createdAt") or post.get("createdAt")
                notifications.append({
                    "id": f"community-comments:{post_id}:{comment_id}",
                    "type": "community-comment",
                    "title": "내 글에 새 답글이 달렸습니다",
                    "body": f"{comment_author}님이 {post_title}에 답글을 남겼습니다",
                    "url": f"/Community/{post_id}",
                    "createdAt": comment_created_at,
                })
            likes = int(post.get("likes") or 0)
            if likes > 0:
                notifications.append({
                    "id": f"community-post-likes:{post_id}:{likes}",
                    "type": "community-like",
                    "title": "내 글에 좋아요가 달렸습니다",
                    "body": f"{post_title}에 좋아요 {likes}개",
                    "url": f"/Community/{post_id}",
                    "createdAt": post.get("createdAt"),
                })
        for comment in comments:
            if normalize_login_id(comment.get("username")) != normalized_username:
                continue
            likes = int(comment.get("likes") or 0)
            if likes > 0:
                notifications.append({
                    "id": f"community-comment-likes:{post_id}:{comment.get('id')}:{likes}",
                    "type": "community-comment-like",
                    "title": "내 답글에 좋아요가 달렸습니다",
                    "body": f"{post_title}의 답글에 좋아요 {likes}개",
                    "url": f"/Community/{post_id}",
                    "createdAt": comment.get("createdAt") or post.get("createdAt"),
                })
    notifications.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return notifications[:50]


@app.route("/api/notifications")
def user_notifications():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "\ub85c\uadf8\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4."}), 401
    try:
        return jsonify({"ok": True, "items": build_user_notifications(session.get("username"))})
    except Exception as exc:
        print(f"Notification load failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "\uc54c\ub9bc\uc744 \ubd88\ub7ec\uc624\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."}), 500



@app.route("/api/community/attachments", methods=["POST"])
def upload_community_attachment_route():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user = find_user(session.get("username"))
    if not user:
        user = {"username": session.get("username"), "nickname": session.get("nickname")}
    try:
        attachment = upload_community_attachment_file(request.files.get("file"), user)
        return jsonify({"ok": True, "item": attachment})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        print(f"Community attachment upload failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "사진 업로드에 실패했습니다."}), 500

@app.route("/api/community/users/<path:username>/followers")
def community_user_followers(username):
    target = normalize_login_id(username)
    if not target:
        return jsonify({"ok": False, "error": "사용자를 찾을 수 없습니다."}), 400
    items = list_community_followers(target)
    return jsonify({"ok": True, "items": items, "count": count_community_followers(target)})


def community_reaction_rows(post_ids):
    ids = [str(item).strip() for item in post_ids if str(item).strip()][:100]
    if not ids:
        return []
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_REACTIONS_TABLE}",
            headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"},
            params={"select": "post_id,username,emoji", "post_id": f"in.({','.join(ids)})"},
            timeout=10,
        )
        if response.status_code < 400:
            return response.json()
    data = read_json_file(os.path.join(os.path.dirname(__file__), "community_reactions.json"), {"items": []})
    return [row for row in data.get("items", []) if str(row.get("post_id")) in ids]


def public_community_reactions(post_ids):
    username = normalize_login_id(session.get("username"))
    rows = community_reaction_rows(post_ids)
    result = {}
    for post_id in post_ids:
        items = []
        for emoji in COMMUNITY_REACTION_EMOJIS:
            matching = [row for row in rows if str(row.get("post_id")) == str(post_id) and row.get("emoji") == emoji]
            if matching:
                items.append({"emoji": emoji, "count": len(matching), "reacted": any(normalize_login_id(row.get("username")) == username for row in matching)})
        result[str(post_id)] = items
    return result


def toggle_community_reaction(post_id, username, emoji):
    if emoji not in COMMUNITY_REACTION_EMOJIS:
        raise ValueError("지원하지 않는 공감입니다.")
    post = get_community_post_raw(post_id)
    channel_id = extract_community_channel_id(post) if post else ""
    if channel_id:
        channel = next((item for item in load_community_channels() if str(item.get("id")) == channel_id), None)
        if not channel or not can_access_community_channel(channel, username):
            raise PermissionError("이 채널에 접근할 수 없습니다.")
        if emoji not in channel.get("reactionEmojis", COMMUNITY_REACTION_EMOJIS):
            raise ValueError("이 채널에서 허용하지 않는 공감입니다.")
    username = normalize_login_id(username)
    rows = community_reaction_rows([post_id])
    exists = any(
        str(row.get("post_id")) == str(post_id)
        and normalize_login_id(row.get("username")) == username
        and row.get("emoji") == emoji
        for row in rows
    )
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_REACTIONS_TABLE}"
        headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json"}
        response = requests.delete(url, headers=headers, params={"post_id": f"eq.{post_id}", "username": f"eq.{username}"}, timeout=10)
        if response.status_code < 400:
            if not exists:
                response = requests.post(url, headers={**headers, "Prefer": "return=minimal"}, json={"post_id": str(post_id), "username": username, "emoji": emoji}, timeout=10)
                response.raise_for_status()
            return
    path = os.path.join(os.path.dirname(__file__), "community_reactions.json")
    data = read_json_file(path, {"items": []})
    items = [
        row for row in data.get("items", [])
        if not (str(row.get("post_id")) == str(post_id) and normalize_login_id(row.get("username")) == username)
    ]
    if not exists:
        items.append({"post_id": str(post_id), "username": username, "emoji": emoji})
    write_json_file(path, {"items": items})

def validate_preview_url(value):
    url = urlparse(str(value or "").strip())
    if url.scheme not in {"http", "https"} or not url.hostname:
        raise ValueError("올바른 링크가 아닙니다.")
    for info in socket.getaddrinfo(url.hostname, url.port or (443 if url.scheme == "https" else 80), type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("허용되지 않는 링크입니다.")
    return url.geturl()


def fetch_link_preview(value):
    url = validate_preview_url(value)
    for _ in range(4):
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 BiKLinkPreview/1.0"}, timeout=6, allow_redirects=False, stream=True)
        if response.is_redirect:
            url = validate_preview_url(urljoin(url, response.headers.get("Location", "")))
            continue
        response.raise_for_status()
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            raise ValueError("미리보기를 지원하지 않는 링크입니다.")
        body = bytearray()
        for chunk in response.iter_content(16384):
            body.extend(chunk)
            if len(body) > 524288:
                break
        soup = BeautifulSoup(bytes(body), "html.parser")
        def meta(*names):
            for name in names:
                node = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
                if node and node.get("content"):
                    return str(node.get("content")).strip()
            return ""
        title = meta("og:title", "twitter:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
        image = meta("og:image", "twitter:image")
        return {"url": url, "title": title[:200], "description": meta("og:description", "twitter:description", "description")[:320], "image": urljoin(url, image) if image else "", "siteName": (meta("og:site_name") or urlparse(url).hostname or "")[:100]}
    raise ValueError("리디렉션이 너무 많습니다.")


@app.route("/api/community/reactions")
def community_reactions_route():
    ids = [item for item in request.args.get("postIds", "").split(",") if item]
    return jsonify({"ok": True, "items": public_community_reactions(ids)})


@app.route("/api/community/posts/<post_id>/reactions", methods=["POST"])
def community_post_reaction_route(post_id):
    if not session.get("username"):
        return jsonify({"ok": False, "error": "로그인 후 공감할 수 있습니다."}), 401
    post = get_community_post(post_id, increment_views=False)
    if not post or post.get("category") != "채널":
        return jsonify({"ok": False, "error": "채널 메시지를 찾을 수 없습니다."}), 404
    try:
        toggle_community_reaction(post_id, session.get("username"), (request.get_json(silent=True) or {}).get("emoji"))
        return jsonify({"ok": True, "items": public_community_reactions([post_id]).get(str(post_id), [])})
    except (ValueError, PermissionError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        print(f"Community reaction failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "공감 처리에 실패했습니다."}), 500


@app.route("/api/link-preview")
def link_preview_route():
    try:
        return jsonify({"ok": True, "item": fetch_link_preview(request.args.get("url", ""))})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        print(f"Link preview failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "링크 미리보기를 불러오지 못했습니다."}), 502


def load_community_channels():
    rows = []
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.get(f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_CHANNELS_TABLE}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}, params={"select": "*", "order": "createdAt.asc"}, timeout=10)
        if response.status_code < 400:
            rows = response.json()
    if not rows:
        rows = read_json_file(os.path.join(BASE_DIR, "community_channels.json"), {"items": []}).get("items", [])
    represented = {normalize_login_id(row.get("owner")) for row in rows}
    try:
        for post in load_community_posts_raw(200):
            owner = normalize_login_id(post.get("username"))
            if post.get("category") != "채널" or not owner or owner in represented:
                continue
            profile = get_user_public_profile(owner)
            rows.append({"id": "legacy-" + hashlib.sha256(owner.encode("utf-8")).hexdigest()[:16], "owner": owner, "name": profile.get("channelName") or profile.get("name") or "채널", "intro": profile.get("channelIntro") or "", "createdAt": post.get("createdAt")})
            represented.add(owner)
    except Exception as exc:
        print(f"Legacy community channels failed: {exc}", flush=True)
    result = []
    for row in rows:
        if not row.get("id") or not row.get("owner"):
            continue
        profile = get_user_public_profile(row.get("owner"))
        result.append({"id": str(row.get("id")), "owner": normalize_login_id(row.get("owner")), "name": str(row.get("name") or "채널")[:40], "handle": str(row.get("handle") or "").lower(), "intro": normalize_channel_intro(row.get("intro")), "avatarUrl": str(row.get("avatarUrl") or profile.get("avatarUrl") or ""), "backgroundUrl": str(row.get("backgroundUrl") or ""), "pinnedPostId": str(row.get("pinnedPostId") or ""), "visibility": "private" if row.get("visibility") == "private" else "public", "reactionEmojis": normalize_channel_reaction_emojis(row.get("reactionEmojis")), "autoDeleteDays": normalize_channel_auto_delete_days(row.get("autoDeleteDays")), "createdAt": row.get("createdAt"), "canEdit": can_edit_community_post({"username": row.get("owner")})})
    subscriber_counts = count_community_channel_followers(item.get("id") for item in result)
    for item in result:
        item["subscriberCount"] = int(subscriber_counts.get(item.get("id"), 0))
    return result


def save_community_channel(owner, payload, channel_id=None):
    owner = normalize_login_id(owner)
    name = re.sub(r"\s+", " ", str(payload.get("name") or "").strip())[:40]
    requested_handle = str(payload.get("handle") or "").strip().lower().lstrip("@")
    if requested_handle and not re.fullmatch(r"[a-z0-9_]{3,30}", requested_handle):
        raise ValueError("채널 ID는 영문 소문자, 숫자, 밑줄로 3~30자까지 입력해주세요.")
    intro = normalize_channel_intro(payload.get("intro"))
    existing = next((row for row in load_community_channels() if str(row.get("id")) == str(channel_id)), None) if channel_id else None
    background_url = str(payload.get("backgroundUrl") or (existing.get("backgroundUrl") if existing else "") or "").strip()[:1000]
    visibility = "private" if payload.get("visibility") == "private" else "public"
    reaction_emojis = normalize_channel_reaction_emojis(payload.get("reactionEmojis"), (existing or {}).get("reactionEmojis"))
    auto_delete_days = normalize_channel_auto_delete_days(payload.get("autoDeleteDays"), (existing or {}).get("autoDeleteDays"))
    if len(name) < 2:
        raise ValueError("채널 이름은 2자 이상 입력해주세요.")
    avatar_url = str(payload.get("avatarUrl") or "").strip()[:1000]
    legacy_existing = bool(existing and str(existing.get("id") or "").startswith("legacy-"))
    handle = requested_handle or str((existing or {}).get("handle") or "").lower()
    if not handle:
        handle = "channel_" + secrets.token_hex(4)
    duplicate = next((row for row in load_community_channels() if str(row.get("handle") or "").lower() == handle and str(row.get("id")) != str(channel_id or "")), None)
    if duplicate:
        raise ValueError("이미 사용 중인 채널 ID입니다.")
    if existing and normalize_login_id(existing.get("owner")) != owner and not is_super_admin(owner):
        raise PermissionError("채널 소유자만 수정할 수 있습니다.")
    item = {"id": str(channel_id or secrets.token_hex(8)), "owner": owner, "name": name, "handle": handle, "intro": intro, "avatarUrl": avatar_url, "backgroundUrl": background_url, "pinnedPostId": str((existing or {}).get("pinnedPostId") or ""), "visibility": visibility, "reactionEmojis": reaction_emojis, "autoDeleteDays": auto_delete_days, "createdAt": existing.get("createdAt") if existing else datetime.now(KST).isoformat(), "updatedAt": datetime.now(KST).isoformat()}
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_CHANNELS_TABLE}"
        headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}
        response = requests.patch(url, headers=headers, params={"id": f"eq.{item['id']}", "select": "*"}, json={"name": name, "handle": handle, "intro": intro, "avatarUrl": avatar_url, "backgroundUrl": background_url, "visibility": visibility, "reactionEmojis": reaction_emojis, "autoDeleteDays": auto_delete_days, "updatedAt": item["updatedAt"]}, timeout=10) if existing and not legacy_existing else requests.post(url, headers=headers, json=item, timeout=10)
        if response.status_code < 400:
            data = response.json()
            return data[0] if data else item
    path = os.path.join(BASE_DIR, "community_channels.json")
    data = read_json_file(path, {"items": []})
    items = data.get("items", [])
    index = next((idx for idx, row in enumerate(items) if str(row.get("id")) == item["id"]), -1)
    if index >= 0:
        items[index] = item
    else:
        items.append(item)
    write_json_file(path, {"items": items})
    return item


@app.route("/api/community/channels")
def community_channels_route():
    username = session.get("username") if session.get("logged_in") else None
    return jsonify({"ok": True, "items": [channel for channel in load_community_channels() if can_access_community_channel(channel, username)]})


@app.route("/api/community/channels/<channel_id>/subscribers")
def community_channel_subscribers_route(channel_id):
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    channel = next((item for item in load_community_channels() if str(item.get("id")) == str(channel_id)), None)
    if not channel:
        return jsonify({"ok": False, "error": "채널을 찾을 수 없습니다."}), 404
    username = normalize_login_id(session.get("username"))
    if normalize_login_id(channel.get("owner")) != username and not is_super_admin(username):
        return jsonify({"ok": False, "error": "채널 소유자만 구독자를 확인할 수 있습니다."}), 403
    key = f"channel:{channel_id}"
    subscribers = []
    for user in load_admin_users():
        settings = sanitize_app_settings((user or {}).get("appSettings"))
        if key not in settings.get("communityFollows", []):
            continue
        profile = get_user_public_profile((user or {}).get("username"), (user or {}).get("nickname") or "회원")
        subscribers.append({"name": profile.get("name") or "회원", "avatarUrl": profile.get("avatarUrl") or ""})
    return jsonify({"ok": True, "items": subscribers})


@app.route("/api/community/channels", methods=["POST"])
def create_community_channel_route():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    try:
        return jsonify({"ok": True, "item": save_community_channel(session.get("username"), request.get_json(silent=True) or {})})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/community/channels/<channel_id>", methods=["PATCH"])
def update_community_channel_route(channel_id):
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    try:
        return jsonify({"ok": True, "item": save_community_channel(session.get("username"), request.get_json(silent=True) or {}, channel_id)})
    except (ValueError, PermissionError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/community/channels/<channel_id>/pin", methods=["PATCH"])
def update_community_channel_pin_route(channel_id):
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    channel = next((item for item in load_community_channels() if str(item.get("id")) == str(channel_id)), None)
    if not channel:
        return jsonify({"ok": False, "error": "채널을 찾을 수 없습니다."}), 404
    if normalize_login_id(channel.get("owner")) != normalize_login_id(session.get("username")) and not is_super_admin():
        return jsonify({"ok": False, "error": "채널 소유자만 메시지를 고정할 수 있습니다."}), 403
    post_id = str((request.get_json(silent=True) or {}).get("postId") or "").strip()[:180]
    if post_id:
        post = get_community_post_raw(post_id)
        post_channel_id = extract_community_channel_id(post) if post else ""
        same_channel = post and (
            post_channel_id == str(channel_id)
            or (
                not post_channel_id
                and normalize_login_id(post.get("username")) == normalize_login_id(channel.get("owner"))
            )
        )
        if not same_channel:
            return jsonify({"ok": False, "error": "이 채널의 메시지만 고정할 수 있습니다."}), 400
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_CHANNELS_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            params={"id": f"eq.{channel_id}"},
            json={"pinnedPostId": post_id},
            timeout=10,
        )
        if response.status_code >= 400:
            print(f"Channel pin update failed: {response.status_code} {response.text[:500]}", flush=True)
            return jsonify({"ok": False, "error": "고정 상태를 저장하지 못했습니다."}), 500
    else:
        path = os.path.join(BASE_DIR, "community_channels.json")
        data = read_json_file(path, {"items": []})
        items = data.get("items", []) if isinstance(data, dict) else []
        updated = False
        for item in items:
            if str(item.get("id")) == str(channel_id):
                item["pinnedPostId"] = post_id
                updated = True
                break
        if not updated:
            return jsonify({"ok": False, "error": "채널 저장 데이터를 찾을 수 없습니다."}), 404
        write_json_file(path, {"items": items})
    channel["pinnedPostId"] = post_id
    return jsonify({"ok": True, "item": channel})


@app.route("/api/community/channels/<channel_id>", methods=["DELETE"])
def delete_community_channel_route(channel_id):
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    channel = next((item for item in load_community_channels() if str(item.get("id")) == str(channel_id)), None)
    if not channel:
        return jsonify({"ok": False, "error": "채널을 찾을 수 없습니다."}), 404
    if normalize_login_id(channel.get("owner")) != normalize_login_id(session.get("username")) and not is_super_admin():
        return jsonify({"ok": False, "error": "채널 소유자만 삭제할 수 있습니다."}), 403
    channel_post_ids = []
    try:
        channel_post_ids = [
            str(post.get("id")) for post in load_community_posts_raw(500)
            if extract_community_channel_id(post) == str(channel_id)
        ]
    except Exception as exc:
        print(f"Channel message cleanup lookup failed: {exc}", flush=True)
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}
        requests.delete(f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_CHANNELS_TABLE}", headers=headers, params={"id": f"eq.{channel_id}"}, timeout=10)
        requests.delete(f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}", headers=headers, params={"channelId": f"eq.{channel_id}"}, timeout=10)
        for post_id in channel_post_ids:
            requests.delete(f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}", headers=headers, params={"id": f"eq.{post_id}"}, timeout=10)
    path = os.path.join(BASE_DIR, "community_channels.json")
    data = read_json_file(path, {"items": []})
    write_json_file(path, {"items": [item for item in data.get("items", []) if str(item.get("id")) != str(channel_id)]})
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        posts_data = read_json_file(COMMUNITY_FILE, {"posts": []})
        posts = [post for post in posts_data.get("posts", []) if extract_community_channel_id(post) != str(channel_id)]
        write_json_file(COMMUNITY_FILE, {"posts": posts})
    return jsonify({"ok": True})

COMMUNITY_CHANNEL_PURGE_LOCK = threading.Lock()
COMMUNITY_CHANNEL_PURGE_AT = 0.0


def purge_expired_channel_messages():
    global COMMUNITY_CHANNEL_PURGE_AT
    now_monotonic = time.monotonic()
    if now_monotonic - COMMUNITY_CHANNEL_PURGE_AT < 60:
        return
    with COMMUNITY_CHANNEL_PURGE_LOCK:
        if time.monotonic() - COMMUNITY_CHANNEL_PURGE_AT < 60:
            return
        COMMUNITY_CHANNEL_PURGE_AT = time.monotonic()
        channels = [item for item in load_community_channels() if normalize_channel_auto_delete_days(item.get("autoDeleteDays"))]
        if not channels:
            return
        now = datetime.now(KST)
        if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
            headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}
            for channel in channels:
                cutoff = (now - timedelta(days=channel["autoDeleteDays"])).isoformat()
                response = requests.delete(
                    f"{SUPABASE_URL}/rest/v1/{SUPABASE_COMMUNITY_TABLE}",
                    headers=headers,
                    params={"channelId": f"eq.{channel['id']}", "createdAt": f"lt.{cutoff}"},
                    timeout=10,
                )
                if response.status_code >= 400:
                    print(f"Channel auto-delete failed: {response.status_code} {response.text[:300]}", flush=True)
            return
        cutoffs = {str(item["id"]): now - timedelta(days=item["autoDeleteDays"]) for item in channels}
        data = read_json_file(COMMUNITY_FILE, {"posts": []})
        kept = []
        for post in data.get("posts", []):
            cutoff = cutoffs.get(extract_community_channel_id(post))
            try:
                created_at = datetime.fromisoformat(str(post.get("createdAt") or "").replace("Z", "+00:00"))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=KST)
            except ValueError:
                created_at = now
            if not cutoff or created_at >= cutoff:
                kept.append(post)
        if len(kept) != len(data.get("posts", [])):
            write_json_file(COMMUNITY_FILE, {"posts": kept})


@app.route("/api/community/posts")
def community_posts():
    try:
        purge_expired_channel_messages()
        return jsonify({"ok": True, "items": load_community_posts()})
    except Exception as exc:
        print(f"Community posts load failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "커뮤니티 글을 불러오지 못했습니다."}), 500


@app.route("/api/community/posts", methods=["POST"])
def create_community_post_route():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user = find_user(session.get("username"))
    if not user:
        user = {"username": session.get("username"), "nickname": session.get("nickname")}
    payload = request.get_json(silent=True) or {}
    try:
        post = create_community_post(user, payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except Exception as exc:
        print(f"Community post save failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "커뮤니티 글 저장에 실패했습니다."}), 500
    return jsonify({"ok": True, "item": post})


@app.route("/api/community/posts/<post_id>", methods=["PATCH"])
def update_community_post_route(post_id):
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user = find_user(session.get("username"))
    if not user:
        user = {"username": session.get("username"), "nickname": session.get("nickname")}
    payload = request.get_json(silent=True) or {}
    try:
        post = update_community_post(post_id, user, payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except Exception as exc:
        print(f"Community post update failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "게시글 수정에 실패했습니다."}), 500
    if not post:
        return jsonify({"ok": False, "error": "게시글을 찾을 수 없습니다."}), 404
    return jsonify({"ok": True, "item": post})


@app.route("/api/community/posts/<post_id>", methods=["DELETE"])
def delete_community_post_route(post_id):
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user = find_user(session.get("username"))
    if not user:
        user = {"username": session.get("username"), "nickname": session.get("nickname")}
    try:
        deleted = delete_community_post(post_id, user)
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except Exception as exc:
        print(f"Community post delete failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "게시글 삭제에 실패했습니다."}), 500
    if not deleted:
        return jsonify({"ok": False, "error": "게시글을 찾을 수 없습니다."}), 404
    return jsonify({"ok": True})


@app.route("/api/community/posts/<post_id>")
def community_post_detail(post_id):
    try:
        post = get_community_post(post_id, increment_views=request.args.get("view") == "1")
    except Exception as exc:
        print(f"Community detail failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "게시글을 불러오지 못했습니다."}), 500
    if not post:
        return jsonify({"ok": False, "error": "게시글을 찾을 수 없습니다."}), 404
    if not can_access_community_channel_post(post, session.get("username")):
        return jsonify({"ok": False, "error": "이 채널에 접근할 수 없습니다."}), 403
    if not can_view_community_post(post):
        return jsonify({"ok": False, "error": "비공개 글은 작성자와 관리자만 볼 수 있습니다."}), 403
    return jsonify({"ok": True, "item": post})


@app.route("/api/community/posts/<post_id>/comments", methods=["POST"])
def create_community_comment_route(post_id):
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "\ub85c\uadf8\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4."}), 401
    user = find_user(session.get("username"))
    if not user:
        user = {"username": session.get("username"), "nickname": session.get("nickname")}
    payload = request.get_json(silent=True) or {}
    try:
        post = add_community_comment(post_id, user, payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except Exception as exc:
        print(f"Community comment save failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "\ub2f5\uae00 \uc800\uc7a5\uc5d0 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4."}), 500
    if not post:
        return jsonify({"ok": False, "error": "\uac8c\uc2dc\uae00\uc744 \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4."}), 404
    return jsonify({"ok": True, "item": post})


@app.route("/api/community/posts/<post_id>/comments/<comment_id>/like", methods=["POST"])
def like_community_comment_route(post_id, comment_id):
    username = session.get("username")
    if not username:
        return jsonify({"ok": False, "error": "\ub85c\uadf8\uc778 \ud6c4 \uc88b\uc544\uc694\ub97c \ub204\ub97c \uc218 \uc788\uc2b5\ub2c8\ub2e4."}), 401
    allowed, retry_after = check_community_like_rate_limit()
    if not allowed:
        return jsonify({
            "ok": False,
            "error": "\uc88b\uc544\uc694\ub97c \ub108\ubb34 \ube60\ub974\uac8c \ub204\ub974\uace0 \uc788\uc2b5\ub2c8\ub2e4. \uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574\uc8fc\uc138\uc694.",
            "retryAfter": retry_after,
        }), 429
    try:
        post = like_community_comment(post_id, comment_id, username)
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except Exception as exc:
        print(f"Community comment like failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "\ub2f5\uae00 \uc88b\uc544\uc694 \ucc98\ub9ac\uc5d0 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4."}), 500
    if not post:
        return jsonify({"ok": False, "error": "\uac8c\uc2dc\uae00\uc744 \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4."}), 404
    return jsonify({"ok": True, "item": post})


@app.route("/api/community/posts/<post_id>/comments/<comment_id>", methods=["DELETE"])
def delete_community_comment_route(post_id, comment_id):
    if not session.get("logged_in"):
        return jsonify({"ok": False, "error": "\ub85c\uadf8\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4."}), 401
    user = find_user(session.get("username"))
    if not user:
        user = {"username": session.get("username"), "nickname": session.get("nickname")}
    try:
        post = delete_community_comment(post_id, comment_id, user)
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except Exception as exc:
        print(f"Community comment delete failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "\ub2f5\uae00 \uc0ad\uc81c\uc5d0 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4."}), 500
    if not post:
        return jsonify({"ok": False, "error": "\uac8c\uc2dc\uae00\uc744 \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4."}), 404
    return jsonify({"ok": True, "item": post})


@app.route("/api/community/posts/<post_id>/like", methods=["POST"])
def community_post_like(post_id):
    username = session.get("username")
    if not username:
        return jsonify({"ok": False, "error": "로그인 후 좋아요를 누를 수 있습니다."}), 401
    allowed, retry_after = check_community_like_rate_limit()
    if not allowed:
        return jsonify({
            "ok": False,
            "error": "좋아요를 너무 빠르게 누르고 있습니다. 잠시 후 다시 시도해주세요.",
            "retryAfter": retry_after,
        }), 429
    try:
        existing = get_community_post(post_id, increment_views=False)
        if not existing:
            return jsonify({"ok": False, "error": "게시글을 찾을 수 없습니다."}), 404
        if not can_view_community_post(existing, username):
            return jsonify({"ok": False, "error": "비공개 글은 작성자와 관리자만 좋아요를 누를 수 있습니다."}), 403
        post = like_community_post(post_id, username)
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except Exception as exc:
        print(f"Community like failed: {exc}", flush=True)
        return jsonify({"ok": False, "error": "좋아요 처리에 실패했습니다."}), 500
    if not post:
        return jsonify({"ok": False, "error": "게시글을 찾을 수 없습니다."}), 404
    return jsonify({"ok": True, "item": post})


@app.route("/api/auth/signup", methods=["POST"])
def auth_signup():
    payload = request.get_json(silent=True) or {}
    nickname = str(payload.get("nickname", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    password_confirm = str(payload.get("passwordConfirm", ""))
    verification_code = str(payload.get("verificationCode", "")).strip()

    if len(nickname) < 2 or len(nickname) > 20:
        return jsonify({"ok": False, "error": "닉네임은 2~20자로 입력해주세요."}), 400
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"ok": False, "error": "올바른 이메일을 입력해주세요."}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "error": "비밀번호는 8자 이상으로 입력해주세요."}), 400
    if password != password_confirm:
        return jsonify({"ok": False, "error": "비밀번호 확인이 일치하지 않습니다."}), 400
    if not verify_email_code(email, verification_code, "signup"):
        return jsonify({"ok": False, "error": "이메일 인증코드가 올바르지 않거나 만료되었습니다."}), 400

    username_base = re.sub(r"[^a-z0-9._-]+", "", email.split("@", 1)[0].lower()) or "user"
    with SIGNUP_LOCK:
        users = load_users()
        existing_ids = {normalize_login_id(user.get("username")) for user in users}
        existing_nicknames = {normalize_login_id(user.get("nickname")) for user in users}
        if email_already_registered(email, users):
            return jsonify({"ok": False, "error": "이미 가입된 이메일입니다."}), 409
        if normalize_login_id(nickname) in existing_nicknames or normalize_login_id(nickname) == normalize_login_id(APP_USERNAME):
            return jsonify({"ok": False, "error": "이미 사용 중인 닉네임입니다."}), 409

        username = username_base
        suffix = 2
        while normalize_login_id(username) in existing_ids or normalize_login_id(username) == normalize_login_id(APP_USERNAME):
            username = f"{username_base}{suffix}"
            suffix += 1

        now = datetime.now(KST).isoformat()
        user = {
            "username": username,
            "nickname": nickname,
            "email": email,
            "passwordHash": generate_password_hash(password),
            "createdAt": now,
        }
        users.append(user)
        try:
            save_users(users)
        except Exception as exc:
            print(f"User store save failed: {exc}", flush=True)
            return jsonify({"ok": False, "error": "계정 저장에 실패했습니다. 잠시 후 다시 시도해주세요."}), 500

    session["logged_in"] = True
    session.permanent = True
    session["username"] = username
    session["nickname"] = nickname
    EMAIL_VERIFICATION_CODES.pop(normalize_login_id(email), None)
    return jsonify({"ok": True, "user": public_user(user)})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


def safe_number(value, digits=2, default="N/A"):
    try:
        if value is None or pd.isna(value) or (isinstance(value, float) and math.isnan(value)):
            return default
        return round(float(value), digits)
    except Exception:
        return default


TOSS_MARKET_MAP = {
    "S&P 500": {"keys": ["sp500"], "fallback": "^GSPC", "basis": "현물 지수"},
    "나스닥 종합": {"keys": ["nasdaq"], "fallback": "^IXIC", "basis": "현물 지수"},
    "다우 존스": {"keys": ["dow"], "fallback": "^DJI", "basis": "현물 지수"},
    "S&P 500 선물": {"keys": ["sp500_futures"], "fallback": "ES=F", "basis": "장외 선물"},
    "나스닥 100 선물": {"keys": ["nasdaq100_futures"], "fallback": "NQ=F", "basis": "장외 선물"},
    "다우 선물": {"keys": ["dow_futures"], "fallback": "YM=F", "basis": "장외 선물"},
    "WTI 원유 ($/bbl)": {"keys": ["wti"], "fallback": "CL=F", "basis": "선물"},
    "국제 금 시세 ($/oz)": {"keys": ["gold"], "fallback": "GC=F", "basis": "선물"},
    "미국 국채 10년물 금리 (%)": {"keys": ["us10y"], "fallback": "^TNX", "basis": "금리"},
}

US_EASTERN = ZoneInfo("America/New_York")


def is_us_regular_market_hours(now=None):
    eastern_now = (now or datetime.now(timezone.utc)).astimezone(US_EASTERN)
    if eastern_now.weekday() >= 5:
        return False
    market_open = datetime_time(9, 30)
    market_close = datetime_time(16, 0)
    return market_open <= eastern_now.time() < market_close


def dashboard_index_labels():
    if is_us_regular_market_hours():
        return ["S&P 500", "나스닥 종합", "다우 존스"]
    return ["S&P 500 선물", "나스닥 100 선물", "다우 선물"]


def first_present(mapping, keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def flatten_toss_data(value):
    if not isinstance(value, dict):
        return {}
    nested = value.get("data")
    if isinstance(nested, dict):
        return {**value, **nested}
    return value


def toss_market_card(cache, item_keys, default_basis=None):
    items = cache.get("items") or {}
    item = next((items.get(key) for key in item_keys if isinstance(items.get(key), dict)), None)
    if not isinstance(item, dict) or item.get("ok") is False:
        return None

    data = flatten_toss_data(item)
    price = first_present(data, [
        "price", "tradePrice", "close", "last", "lastPrice", "currentPrice",
        "stck_prpr", "idx", "value", "yield", "rate",
    ])
    change = first_present(data, [
        "change", "changePercent", "changeRate", "fluctuationRate",
        "signedChangeRate", "prdy_ctrt", "rateOfChange",
    ])
    as_of = first_present(data, ["asOf", "updatedAt", "timestamp", "time", "date"])
    basis = first_present(data, ["basis", "marketType", "session", "assetType"]) or default_basis
    if price is None:
        return None

    change_number = safe_number(change, default=0)
    if isinstance(change_number, (int, float)) and abs(change_number) <= 1 and "Rate" in "".join(data.keys()):
        change_number = round(change_number * 100, 2)

    return {
        "price": safe_number(price),
        "change": change_number,
        "source": "Toss OpenAPI",
        "detail": basis,
        "asOf": as_of or cache.get("receivedAt") or cache.get("updatedAt"),
    }


def market_card_from_toss_or_yahoo(cache, label):
    config = TOSS_MARKET_MAP[label]
    toss_card = toss_market_card(cache, config["keys"], config.get("basis"))
    if toss_card:
        return toss_card
    yahoo_card = get_price_change(config["fallback"])
    yahoo_card["detail"] = config.get("basis")
    return yahoo_card


DASHBOARD_HYPERLIQUID_INDEX_MAP = {
    "S&P 500": "xyz:SP500",
    "\ub098\uc2a4\ub2e5 100": "xyz:XYZ100",
    "\ucf54\uc2a4\ud53c 200": "xyz:KR200",
}

DASHBOARD_HYPERLIQUID_MACRO_MAP = {
    "WTI": "xyz:CL",
    "Gold": "xyz:GOLD",
    "DRAM": "xyz:DRAM",
}


def hyperliquid_dashboard_card(row):
    if not isinstance(row, dict):
        return {"price": "N/A", "change": 0, "source": "Hyperliquid XYZ"}
    return {
        "price": safe_number(row.get("price"), default="N/A"),
        "change": safe_number(row.get("changePct"), default=0),
        "source": "Hyperliquid XYZ",
        "detail": "24H synthetic market",
        "asOf": datetime.now(KST).isoformat(),
    }


def get_hyperliquid_xyz_dashboard_cards():
    rows = build_hyperliquid_rows_for_dex("xyz")
    by_coin = {str(row.get("coin") or "").upper(): row for row in rows}
    indices = {
        label: hyperliquid_dashboard_card(by_coin.get(symbol.upper()))
        for label, symbol in DASHBOARD_HYPERLIQUID_INDEX_MAP.items()
    }
    macro = {
        label: hyperliquid_dashboard_card(by_coin.get(symbol.upper()))
        for label, symbol in DASHBOARD_HYPERLIQUID_MACRO_MAP.items()
    }
    return indices, macro



def get_fast_info_value(ticker_obj, names, default=None):
    try:
        fast = ticker_obj.fast_info
    except Exception:
        return default
    for name in names:
        for key in (name, re.sub(r"_([a-z])", lambda m: m.group(1).upper(), name)):
            try:
                if isinstance(fast, dict):
                    value = fast.get(key)
                else:
                    value = getattr(fast, key, None)
                if value not in (None, ""):
                    return value
            except Exception:
                continue
    return default


def safe_float(value, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def get_history_quote(ticker_obj, period="5d"):
    try:
        history = ticker_obj.history(period=period)
        if history is None or history.empty:
            return {}
        closes = history["Close"].dropna()
        if closes.empty:
            return {}
        latest = safe_float(closes.iloc[-1])
        previous = safe_float(closes.iloc[-2]) if len(closes) >= 2 else None
        change = ((latest - previous) / previous) * 100 if latest and previous else None
        return {"price": latest, "previousClose": previous, "changePercent": change}
    except Exception as exc:
        print(f"Yahoo history quote fallback failed: {exc}", flush=True)
        return {}
def get_fast_price(ticker_obj):
    try:
        fast = ticker_obj.fast_info
    except Exception:
        return 0
    for attr in ("lastPrice", "last_price", "previousClose", "previous_close"):
        try:
            value = getattr(fast, attr, None)
            if value:
                return float(value)
        except Exception:
            continue
    return 0


def get_price_change(symbol):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="5d")
    if hist is not None and not hist.empty and len(hist["Close"].dropna()) >= 2:
        closes = hist["Close"].dropna()
        latest = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        change = ((latest - prev) / prev) * 100 if prev else 0
        return {"price": safe_number(latest), "change": safe_number(change), "source": "Yahoo Finance"}

    price = get_fast_price(ticker)
    return {"price": safe_number(price), "change": 0, "source": "Yahoo Finance"}


def get_aaii_sentiment():
    url = "https://www.aaii.com/sentimentsurvey"
    try:
        request_obj = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; HoduAcademy/1.0; +https://bikresearch.onrender.com)"
            },
        )
        with urllib.request.urlopen(request_obj, timeout=12) as response:
            raw_html = response.read().decode("utf-8", errors="ignore")

        text = re.sub(r"<(script|style).*?</\1>", " ", raw_html, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html_lib.unescape(text)
        text = re.sub(r"\s+", " ", text)
        if "Pardon Our Interruption" in raw_html or "reeseSkipExpirationCheck" in raw_html:
            return load_aaii_sentiment_fallback("AAII 원본 페이지가 봇 차단을 반환해 Supabase에 저장된 마지막 정상 수집값을 표시합니다.")

        rows_region = text.split("Historical View", 1)[0]
        row_pattern = re.compile(
            r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%"
        )
        rows = [
            {
                "date": match.group(1),
                "bullish": float(match.group(2)),
                "neutral": float(match.group(3)),
                "bearish": float(match.group(4)),
            }
            for match in row_pattern.finditer(rows_region)
        ]
        if not rows:
            return load_aaii_sentiment_fallback("AAII 원본 페이지에서 설문 데이터를 찾지 못해 Supabase에 저장된 마지막 정상 수집값을 표시합니다.")

        latest = rows[0]
        previous = rows[1] if len(rows) > 1 else None
        avg_match = re.search(
            r"Historical Averages\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%",
            text,
        )
        averages = {
            "bullish": float(avg_match.group(1)) if avg_match else 37.5,
            "neutral": float(avg_match.group(2)) if avg_match else 31.5,
            "bearish": float(avg_match.group(3)) if avg_match else 31.0,
        }
        bull_8w = sum(row["bullish"] for row in rows[:8]) / min(len(rows), 8)

        def delta(key):
            if not previous:
                return None
            return round(latest[key] - previous[key], 1)

        result = {
            "ok": True,
            "source": "AAII",
            "date": latest["date"],
            "bullish": latest["bullish"],
            "neutral": latest["neutral"],
            "bearish": latest["bearish"],
            "bull_avg": averages["bullish"],
            "neut_avg": averages["neutral"],
            "bear_avg": averages["bearish"],
            "bull_8w": round(bull_8w, 1),
            "delta": {
                "bullish": delta("bullish"),
                "neutral": delta("neutral"),
                "bearish": delta("bearish"),
            },
        }
        save_aaii_sentiment_cache(result)
        result["loadedFrom"] = "live"
        return result
    except Exception as exc:
        return load_aaii_sentiment_fallback(f"AAII 원본 데이터를 불러오지 못해 Supabase에 저장된 마지막 정상 수집값을 표시합니다: {exc}")


def get_cnn_fear_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    labels = {
        "market_momentum_sp500": "시장 모멘텀",
        "stock_price_strength": "주가 강도",
        "stock_price_breadth": "시장 폭",
        "put_call_options": "풋/콜 비율",
        "market_volatility_vix": "VIX 변동성",
        "junk_bond_demand": "정크본드",
        "safe_haven_demand": "안전자산",
    }
    rating_labels = {
        "extreme fear": "극도의 공포",
        "fear": "공포",
        "neutral": "중립",
        "greed": "탐욕",
        "extreme greed": "극도의 탐욕",
    }

    try:
        request_obj = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://www.cnn.com/markets/fear-and-greed",
            },
        )
        with urllib.request.urlopen(request_obj, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8", errors="ignore"))

        headline = data.get("fear_and_greed") or {}
        score = safe_number(headline.get("score"), 1, default=None)
        rating = str(headline.get("rating") or "").replace("_", " ").lower()
        if score is None:
            return None

        indicators = {}
        for key, label in labels.items():
            item = data.get(key) or {}
            item_score = safe_number(item.get("score"), 1, default=None)
            item_rating = str(item.get("rating") or "").replace("_", " ").lower()
            indicators[key] = {
                "label": label,
                "score": item_score,
                "rating": item_rating,
                "status": rating_labels.get(item_rating, item_rating.title() if item_rating else "-"),
                "timestamp": item.get("timestamp"),
            }

        return {
            "score": score,
            "rating": rating,
            "status": rating_labels.get(rating, rating.title() if rating else "-"),
            "timestamp": headline.get("timestamp"),
            "source": "CNN Fear & Greed",
            "previousClose": safe_number(headline.get("previous_close"), 1),
            "previousWeek": safe_number(headline.get("previous_1_week"), 1),
            "previousMonth": safe_number(headline.get("previous_1_month"), 1),
            "previousYear": safe_number(headline.get("previous_1_year"), 1),
            "indicators": indicators,
        }
    except Exception as exc:
        print(f"CNN Fear & Greed load failed: {exc}", flush=True)
        return None


RSS_SOURCES = [
    {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss"},
    {"name": "NYT", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    {"name": "BBC", "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "CNBC", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
    {"name": "MarketWatch", "url": "https://www.marketwatch.com/rss/marketpulse"},
    {"name": "MarketWatch", "url": "https://www.marketwatch.com/rss/topstories"},
]

MARKET_NEWS_KEYWORDS_EN = [
    "market", "markets", "stock", "stocks", "shares", "bond", "bonds", "yield", "yields", "fed",
    "rate", "rates", "inflation", "tariff", "tariffs", "trade", "oil", "crude", "energy", "gas",
    "gold", "dollar", "currency", "forex", "economy", "economic", "gdp", "recession", "earnings",
    "chip", "chips", "semiconductor", "ai", "bank", "banks", "central bank", "treasury", "debt",
    "supply chain", "china", "trump", "war", "sanction", "sanctions", "hormuz", "israel", "iran",
    "ukraine",
]

MARKET_NEWS_KEYWORDS_KO = [
    "시장", "증시", "주식", "주가", "코스피", "코스닥", "환율", "달러", "원화", "금리", "국채",
    "채권", "연준", "물가", "인플레", "관세", "무역", "유가", "원유", "금값", "반도체", "AI",
    "경제", "성장률", "침체", "은행", "중앙은행", "부채", "제재", "중동", "호르무즈",
]


def clean_text(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", str(value))
    value = html_lib.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_rss_datetime(value):
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def get_child_text(item, tag_name):
    for child in list(item):
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name == tag_name:
            return child.text or ""
    return ""


def fetch_rss_articles(source, limit=6):
    cache_key = f"rss:{source['url']}"
    cached_articles = get_cached_value(cache_key, 300)
    if cached_articles is not None:
        return cached_articles[:limit]

    try:
        request_obj = urllib.request.Request(
            source["url"],
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; HoduAcademy/1.0; +https://bikresearch.onrender.com)",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        with urllib.request.urlopen(request_obj, timeout=10) as response:
            content = response.read()
        root = ET.fromstring(content)
        articles = []
        for item in root.findall(".//item"):
            title = clean_text(get_child_text(item, "title"))
            link = clean_text(get_child_text(item, "link"))
            description = clean_text(get_child_text(item, "description"))
            published_raw = get_child_text(item, "pubdate") or get_child_text(item, "published")
            published = parse_rss_datetime(published_raw)
            published_kst = published.astimezone(KST) if published.year > 1900 else published
            if not title or not link:
                continue
            articles.append({
                "title": title,
                "url": link,
                "source": source["name"],
                "scoreText": f"{title} {description}",
                "publishedAt": published_kst.isoformat(),
                "publishedLabel": published_kst.strftime("%m/%d %H:%M KST") if published_kst.year > 1900 else "",
            })
        set_cached_value(cache_key, articles)
        return articles[:limit]
    except Exception as exc:
        print(f"RSS load failed: {source['name']} - {exc}", flush=True)
        return []


def market_news_score(article):
    text = clean_text(article.get("scoreText") or article.get("title") or "").lower()
    score = 0
    for keyword in MARKET_NEWS_KEYWORDS_EN:
        pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            score += 1
    for keyword in MARKET_NEWS_KEYWORDS_KO:
        if keyword.lower() in text:
            score += 1
    if article.get("source") == "Bloomberg":
        score += 2
    if article.get("source") in {"CNBC", "MarketWatch"}:
        score += 1
    return score


def company_news_keywords(ticker_symbol, company_name):
    base_ticker = ticker_symbol.split(".", 1)[0].lower()
    stop_words = {
        "inc", "inc.", "corp", "corp.", "corporation", "company", "co", "co.", "ltd", "ltd.",
        "plc", "class", "common", "stock", "ordinary", "holdings", "holding", "group",
    }
    words = re.findall(r"[A-Za-z0-9가-힣]+", company_name or "")
    keywords = {base_ticker}
    for word in words:
        lowered = word.lower()
        if len(lowered) >= 3 and lowered not in stop_words:
            keywords.add(lowered)
    return keywords


def article_matches_company(article, keywords):
    text = clean_text(article.get("scoreText") or article.get("title") or "").lower()
    for keyword in keywords:
        if re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text):
            return True
    return False


def get_company_news(ticker_symbol, company_name, ticker_obj, limit=5):
    news = []
    seen = set()
    keywords = company_news_keywords(ticker_symbol, company_name)

    def add_news(title, link, publisher, published_at=""):
        if not title or not link:
            return
        normalized_link = link.split("?")[0]
        normalized_title = title.lower().strip()
        key = (normalized_title, normalized_link)
        if key in seen:
            return
        seen.add(key)
        news.append({
            "title": title,
            "originalTitle": title,
            "publisher": publisher,
            "link": link,
            "publishedAt": published_at,
        })

    try:
        for item in (ticker_obj.news or [])[:8]:
            content = item.get("content") or {}
            title = item.get("title") or content.get("title")
            if not article_matches_company({"title": title, "summary": ""}, keywords):
                continue
            publisher = item.get("publisher") or (content.get("provider") or {}).get("name") or "Yahoo Finance"
            link = item.get("link") or (content.get("clickThroughUrl") or {}).get("url") or content.get("url") or "#"
            publish_ts = item.get("providerPublishTime")
            if publish_ts:
                published_at = datetime.fromtimestamp(float(publish_ts), tz=timezone.utc).isoformat()
            else:
                published_at = str(content.get("pubDate") or "")
            add_news(title, link, publisher, published_at)
    except Exception as exc:
        print(f"Yahoo 뉴스 수집 오류: {exc}", flush=True)

    rss_matches = []
    for source in RSS_SOURCES:
        for article in fetch_rss_articles(source, limit=10):
            if article_matches_company(article, keywords):
                rss_matches.append(article)

    rss_matches.sort(key=lambda item: item.get("publishedAt") or "", reverse=True)
    for article in rss_matches:
        add_news(article.get("title"), article.get("url"), article.get("source"), article.get("publishedAt", ""))

    news.sort(key=lambda item: item.get("publishedAt") or "", reverse=True)
    top_news = news[:limit]
    for item in top_news:
        item["originalTitle"] = item["title"]
        item["title"] = translate_to_korean(item["title"])
    return top_news


def translate_to_korean(text):
    if not text:
        return text
    try:
        return GoogleTranslator(source="auto", target="ko").translate(text)
    except Exception:
        return text


def empty_option_data(message="옵션 데이터가 없습니다."):
    return {
        "optionStrikes": [],
        "optionCallVolume": [],
        "optionPutVolume": [],
        "optionIv": [],
        "optionView": message,
        "optionPcr": "N/A",
        "optionExpiry": "N/A",
        "optionDaysLeft": "N/A",
        "optionBasis": "N/A",
        "optionDominantZone": "N/A",
    }


def get_valid_option_chain(ticker, current_price, band=0.15):
    options = list(ticker.options)
    if not options:
        return None, None, None

    today = datetime.now().date()
    future_options = []
    for expiry in options:
        try:
            expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
            if expiry_date >= today:
                future_options.append(expiry)
        except Exception:
            continue

    for expiry in future_options or options:
        try:
            chain = ticker.option_chain(expiry)
            calls = chain.calls.copy()
            puts = chain.puts.copy()
            low = current_price * (1 - band)
            high = current_price * (1 + band)
            calls_near = calls[(calls["strike"] >= low) & (calls["strike"] <= high)]
            puts_near = puts[(puts["strike"] >= low) & (puts["strike"] <= high)]
            call_sum = pd.to_numeric(calls_near.get("openInterest"), errors="coerce").fillna(0).sum()
            put_sum = pd.to_numeric(puts_near.get("openInterest"), errors="coerce").fillna(0).sum()
            if call_sum + put_sum > 0:
                return expiry, chain, "openInterest"
        except Exception as exc:
            print(f"옵션 만기 조회 실패({expiry}): {exc}", flush=True)

    return None, None, None


def build_option_data(ticker_symbol, ticker, current_price):
    if ".KS" in ticker_symbol or ".KQ" in ticker_symbol:
        return empty_option_data("국내 종목 옵션 데이터는 현재 제공되지 않습니다.")

    try:
        expiry, chain, _basis = get_valid_option_chain(ticker, current_price)
        if not expiry or not chain:
            return empty_option_data()

        days_left = (datetime.strptime(expiry, "%Y-%m-%d").date() - datetime.now().date()).days
        calls = chain.calls.copy()
        puts = chain.puts.copy()
        for frame in (calls, puts):
            frame["openInterest"] = pd.to_numeric(frame.get("openInterest"), errors="coerce").fillna(0)
            frame["impliedVolatility"] = pd.to_numeric(frame["impliedVolatility"], errors="coerce").fillna(0)

        merged = pd.merge(
            calls[["strike", "openInterest", "impliedVolatility"]],
            puts[["strike", "openInterest", "impliedVolatility"]],
            on="strike",
            how="outer",
            suffixes=("_call", "_put"),
        ).fillna(0)
        merged = merged[(merged["strike"] >= current_price * 0.85) & (merged["strike"] <= current_price * 1.15)]
        if len(merged) > 15:
            merged["distance"] = (merged["strike"] - current_price).abs()
            merged = merged.sort_values("distance").head(15)
        merged = merged.sort_values("strike")
        if merged.empty:
            return empty_option_data()

        def call_moneyness(strike):
            if abs(strike - current_price) / current_price <= 0.01:
                return "ATM"
            return "ITM" if strike < current_price else "OTM"

        def put_moneyness(strike):
            if abs(strike - current_price) / current_price <= 0.01:
                return "ATM"
            return "ITM" if strike > current_price else "OTM"

        strikes = [float(x) for x in merged["strike"]]
        call_values = [int(x) for x in merged["openInterest_call"]]
        put_values = [int(x) for x in merged["openInterest_put"]]
        total_call = sum(call_values)
        total_put = sum(put_values)
        pcr = round(total_put / total_call, 2) if total_call else "N/A"
        call_states = [call_moneyness(strike) for strike in strikes]
        put_states = [put_moneyness(strike) for strike in strikes]
        buckets = {
            "콜 OTM": sum(value for value, state in zip(call_values, call_states) if state == "OTM"),
            "콜 ATM": sum(value for value, state in zip(call_values, call_states) if state == "ATM"),
            "콜 ITM": sum(value for value, state in zip(call_values, call_states) if state == "ITM"),
            "풋 OTM": sum(value for value, state in zip(put_values, put_states) if state == "OTM"),
            "풋 ATM": sum(value for value, state in zip(put_values, put_states) if state == "ATM"),
            "풋 ITM": sum(value for value, state in zip(put_values, put_states) if state == "ITM"),
        }
        dominant_zone, dominant_volume = max(buckets.items(), key=lambda item: item[1])
        if pcr == "N/A":
            view = "콜 미결제약정 부족으로 OI PCR 산출 불가"
        elif buckets["콜 OTM"] == dominant_volume and pcr < 1.0:
            view = "콜 OTM 미결제약정 집중: 상방 베팅이 누적된 구간"
        elif buckets["풋 OTM"] == dominant_volume and pcr > 1.0:
            view = "풋 OTM 미결제약정 집중: 하방 방어/보험 포지션 누적"
        elif buckets["콜 ATM"] + buckets["풋 ATM"] >= (total_call + total_put) * 0.35:
            view = "ATM 미결제약정 집중: 현재가 부근 포지션 공방 심화"
        elif total_call > 0 and total_put > 0 and 0.85 <= pcr <= 1.15:
            view = "콜·풋 균형: 변동성 이벤트 대기 가능성"
        elif pcr < 0.85:
            view = "콜 미결제약정 우위: 상방 포지션 누적"
        else:
            view = "풋 미결제약정 우위: 방어적 포지션 누적"

        iv_values = []
        for _, row in merged.iterrows():
            valid = [x for x in (row["impliedVolatility_call"], row["impliedVolatility_put"]) if x > 0]
            iv_values.append(round((sum(valid) / len(valid)) * 100, 1) if valid else 0)

        return {
            "optionStrikes": strikes,
            "optionCallVolume": call_values,
            "optionPutVolume": put_values,
            "optionIv": iv_values,
            "optionView": view,
            "optionPcr": pcr,
            "optionExpiry": expiry,
            "optionDaysLeft": "D-Day" if days_left == 0 else f"D-{days_left}",
            "optionBasis": "미결제약정",
            "optionDominantZone": dominant_zone if dominant_volume else "N/A",
        }
    except Exception as exc:
        print(f"옵션 처리 오류: {exc}", flush=True)
        return empty_option_data()


@app.route("/api/ping")
def api_ping():
    maybe_start_eth_tracker_schedulers()
    return jsonify({"ok": True, "ts": datetime.now(KST).isoformat()})


def build_market_data_payload():
    try:
        indices_data, macro_data = get_hyperliquid_xyz_dashboard_cards()
    except Exception as exc:
        print(f"Hyperliquid dashboard lookup failed: {exc}", flush=True)
        indices_data = {
            label: {"price": "N/A", "change": 0, "source": "Hyperliquid XYZ"}
            for label in DASHBOARD_HYPERLIQUID_INDEX_MAP
        }
        macro_data = {
            label: {"price": "N/A", "change": 0, "source": "Hyperliquid XYZ"}
            for label in DASHBOARD_HYPERLIQUID_MACRO_MAP
        }

    sentiment = get_cnn_fear_greed()
    if sentiment is None:
        try:
            hist = yf.Ticker("^GSPC").history(period="125d")
            if hist is not None and len(hist) >= 20:
                current_close = float(hist["Close"].iloc[-1])
                moving_average = float(hist["Close"].mean())
                score = int(50 + (((current_close / moving_average) * 100) - 100) * 5)
                sentiment_score = max(5, min(95, score))
            else:
                sentiment_score = 52
        except Exception:
            sentiment_score = 52

        if sentiment_score <= 25:
            status = "극도의 공포"
        elif sentiment_score <= 45:
            status = "공포"
        elif sentiment_score <= 55:
            status = "중립"
        elif sentiment_score <= 75:
            status = "탐욕"
        else:
            status = "극도의 탐욕"
        sentiment = {
            "score": sentiment_score,
            "rating": "",
            "status": status,
            "timestamp": None,
            "source": "Yahoo Finance 근사",
            "indicators": {},
        }

    return {
        "indices": indices_data,
        "macro": macro_data,
        "sentiment": sentiment,
        "aaii": get_aaii_sentiment(),
    }


@app.route("/api/market-data")
def market_data():
    cached = get_cached_value("market-data", MARKET_DATA_CACHE_SECONDS)
    if cached is not None:
        return jsonify(cached)
    stale = get_stale_cached_value("market-data", 1800)
    if stale is not None:
        refresh_cache_in_background("market-data", lambda: set_cached_value("market-data", build_market_data_payload()))
        return jsonify(stale)
    payload = build_market_data_payload()
    set_cached_value("market-data", payload)
    return jsonify(payload)


def build_global_news_payload():
    articles = []
    seen = set()
    for source in RSS_SOURCES:
        for article in fetch_rss_articles(source):
            article = dict(article)
            key = (article["title"].lower(), article["url"].split("?")[0])
            if key in seen:
                continue
            seen.add(key)
            score = market_news_score(article)
            if score <= 0:
                continue
            article["marketScore"] = score
            article.pop("scoreText", None)
            articles.append(article)

    articles.sort(key=lambda item: (item.get("marketScore", 0), item.get("publishedAt") or ""), reverse=True)
    top_articles = articles[:5]
    for article in top_articles:
        article["originalTitle"] = article["title"]
        article["title"] = translate_to_korean(article["title"])

    return {
        "items": top_articles,
        "sources": list(dict.fromkeys(source["name"] for source in RSS_SOURCES)),
        "sourceNote": "RSS 기반 최신 글로벌 뉴스",
    }


@app.route("/api/global-news")
def global_news():
    cached = get_cached_value("global-news", 180)
    if cached is not None:
        return jsonify(cached)
    stale = get_stale_cached_value("global-news", 3600)
    if stale is not None:
        refresh_cache_in_background("global-news", lambda: set_cached_value("global-news", build_global_news_payload()))
        return jsonify(stale)
    payload = build_global_news_payload()
    set_cached_value("global-news", payload)
    return jsonify(payload)


@app.route("/api/company")
def company_info():
    ticker_symbol = request.args.get("ticker", "").strip().upper()
    lite_mode = request.args.get("lite") == "1"
    if not ticker_symbol:
        return jsonify({"error": "티커를 입력하세요."}), 400
    if re.fullmatch(r"\d{6}", ticker_symbol or "") or ticker_symbol.endswith((".KS", ".KQ")):
        return jsonify({"error": "\ud574\uc678 \uae30\uc5c5 \ubd84\uc11d\uc5d0\uc11c\ub294 \uad6d\ub0b4 \uc885\ubaa9\uc744 \uac80\uc0c9\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. \uad6d\ub0b4 \uae30\uc5c5 \ubd84\uc11d \ud0ed\uc744 \uc774\uc6a9\ud574 \uc8fc\uc138\uc694."}), 400

    cache_ttl = 900 if lite_mode else 300
    cache_key = f"company:{'lite' if lite_mode else 'full'}:{ticker_symbol}"
    cached = get_cached_value(cache_key, cache_ttl)
    if cached is not None:
        return jsonify(cached)

    try:
        ticker = yf.Ticker(ticker_symbol)
        try:
            info = ticker.info or {}
        except Exception as exc:
            print(f"회사 기본 정보 조회 실패({ticker_symbol}): {exc}", flush=True)
            info = {}

        history_quote = get_history_quote(ticker, "5d")
        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or history_quote.get("price") or get_fast_price(ticker)
        change_percent = info.get("regularMarketChangePercent")
        if change_percent is None:
            change_percent = history_quote.get("changePercent")
        previous_close = info.get("regularMarketPreviousClose") or history_quote.get("previousClose") or get_fast_info_value(ticker, ["previous_close", "previousClose"])
        if change_percent is None and current_price and previous_close:
            previous_close_number = safe_float(previous_close, 0)
            if previous_close_number:
                change_percent = ((safe_float(current_price, 0) - previous_close_number) / previous_close_number) * 100

        fast_market_cap = get_fast_info_value(ticker, ["market_cap", "marketCap"])
        shares = info.get("sharesOutstanding") or get_fast_info_value(ticker, ["shares", "sharesOutstanding"])
        market_cap = info.get("marketCap") or fast_market_cap
        if not market_cap and current_price and shares:
            market_cap = safe_float(current_price, 0) * safe_float(shares, 0)
        currency = info.get("currency") or get_fast_info_value(ticker, ["currency"]) or ("KRW" if ticker_symbol.endswith(".KS") else "USD")
        exchange = info.get("exchange") or get_fast_info_value(ticker, ["exchange"]) or ("KSC" if ticker_symbol.endswith(".KS") else "NMS")
        market_state = info.get("marketState") or info.get("regularMarketState") or get_fast_info_value(ticker, ["market_state", "marketState"]) or "UNKNOWN"
        volume = info.get("regularMarketVolume") or info.get("volume") or get_fast_info_value(ticker, ["last_volume", "lastVolume"]) or 0
        avg_volume = info.get("averageVolume") or get_fast_info_value(ticker, ["ten_day_average_volume", "three_month_average_volume"]) or 0

        if not current_price and not market_cap and not info.get("longName") and not info.get("shortName") and not exchange:
            return jsonify({"error": "올바른 티커를 입력하세요."}), 404
        dividend_rate = info.get("dividendRate") or 0
        raw_yield = info.get("dividendYield") or 0
        if dividend_rate and current_price:
            dividend_yield = (dividend_rate / current_price) * 100 if raw_yield > 0.1 else raw_yield * 100
        else:
            dividend_yield = 0

        company_name = info.get("longName") or info.get("shortName") or ticker_symbol
        news = [] if lite_mode else get_company_news(ticker_symbol, company_name, ticker)

        summary = info.get("longBusinessSummary") or info.get("description") or "회사 소개 정보가 없습니다."
        if lite_mode:
            summary = ""
        elif summary != "회사 소개 정보가 없습니다.":
            summary = translate_to_korean(summary)

        result = {
            "ticker": ticker_symbol,
            "name": company_name,
            "price": safe_number(current_price),
            "changePercent": safe_number(change_percent),
            "marketCap": safe_number(market_cap, 0),
            "currency": currency,
            "market": exchange,
            "marketState": market_state,
            "status": "Yahoo Finance",
            "asOf": datetime.now().isoformat(timespec="seconds"),
            "dataSource": "Yahoo Finance",
            "warnings": [],
            "peRatio": safe_number(info.get("trailingPE") or info.get("forwardPE")),
            "pbrRatio": safe_number(info.get("priceToBook")),
            "pegRatio": safe_number(info.get("pegRatio")),
            "dividendYield": safe_number(dividend_yield),
            "summary": summary,
            "instOwnership": safe_number((info.get("heldPercentInstitutions") or 0) * 100),
            "insiderOwnership": safe_number((info.get("heldPercentInsiders") or 0) * 100),
            "shortRatio": info.get("shortRatio", "N/A"),
            "shortPctFloat": safe_number((info.get("shortPercentOfFloat") or 0) * 100),
            "targetMean": safe_number(info.get("targetMeanPrice")),
            "targetHigh": safe_number(info.get("targetHighPrice")),
            "targetLow": safe_number(info.get("targetLowPrice")),
            "recommendation": (info.get("recommendationKey") or "N/A").replace("_", " ").upper(),
            "analystCount": info.get("numberOfAnalystOpinions", "N/A"),
            "eps": safe_number(info.get("trailingEps")),
            "debtToEquity": safe_number(info.get("debtToEquity")),
            "volume": volume,
            "avgVolume": avg_volume,
            "high52w": safe_number(info.get("fiftyTwoWeekHigh")),
            "low52w": safe_number(info.get("fiftyTwoWeekLow")),
            "avg50d": safe_number(info.get("fiftyDayAverage")),
            "avg200d": safe_number(info.get("twoHundredDayAverage")),
            "news": news,
        }
        if lite_mode:
            result.update(empty_option_data("lite"))
            result["lite"] = True
        else:
            result.update(build_option_data(ticker_symbol, ticker, float(current_price or 0)))
        set_cached_value(cache_key, result)
        return jsonify(result)
    except Exception as exc:
        print(f"종목 검색 오류: {exc}", flush=True)
        return jsonify({"error": "데이터 조회 중 오류가 발생했습니다."}), 500


# ETH tracker jobs are started lazily after the web process is serving requests.
# This keeps Render startup/health checks from waiting on external crawlers.


ADMIN_AUDIT_FILE = os.path.join(BASE_DIR, "admin_audit_log.json")
ADMIN_AUDIT_LOCK = threading.Lock()


def admin_api_required(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
        if not is_super_admin():
            return jsonify({"ok": False, "error": "관리자 권한이 필요합니다."}), 403
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("X-Admin-Action") != "1":
            return jsonify({"ok": False, "error": "관리자 작업 헤더가 필요합니다."}), 400
        return handler(*args, **kwargs)
    return wrapped


def normalize_admin_audit_row(row):
    return {
        "id": str((row or {}).get("id") or ""),
        "actor": str((row or {}).get("actor") or ""),
        "action": str((row or {}).get("action") or ""),
        "targetType": str((row or {}).get("target_type") or (row or {}).get("targetType") or ""),
        "targetId": str((row or {}).get("target_id") or (row or {}).get("targetId") or ""),
        "details": (row or {}).get("details") if isinstance((row or {}).get("details"), dict) else {},
        "createdAt": str((row or {}).get("created_at") or (row or {}).get("createdAt") or ""),
    }


def load_admin_audit_logs(limit=100):
    limit = max(1, min(int(limit or 100), 500))
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_ADMIN_AUDIT_TABLE:
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_ADMIN_AUDIT_TABLE}",
                headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"},
                params={"select": "*", "order": "created_at.desc", "limit": str(limit)},
                timeout=10,
            )
            if response.status_code < 400:
                return [normalize_admin_audit_row(row) for row in response.json()]
        except Exception as exc:
            print(f"Admin audit load failed: {exc}", flush=True)
    rows = read_json_file(ADMIN_AUDIT_FILE, {"items": []}).get("items", [])
    return [normalize_admin_audit_row(row) for row in rows[-limit:]][::-1]


def append_admin_audit(action, target_type, target_id="", details=None):
    row = {
        "id": secrets.token_hex(12),
        "actor": normalize_login_id(session.get("username")),
        "action": str(action or "")[:80],
        "target_type": str(target_type or "")[:40],
        "target_id": str(target_id or "")[:180],
        "details": details if isinstance(details, dict) else {},
        "created_at": datetime.now(KST).isoformat(),
    }
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_ADMIN_AUDIT_TABLE:
        try:
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_ADMIN_AUDIT_TABLE}",
                headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"},
                json=row,
                timeout=10,
            )
            if response.status_code < 400:
                return normalize_admin_audit_row(row)
            print(f"Admin audit save failed: {response.status_code} {response.text[:300]}", flush=True)
        except Exception as exc:
            print(f"Admin audit save failed: {exc}", flush=True)
    with ADMIN_AUDIT_LOCK:
        data = read_json_file(ADMIN_AUDIT_FILE, {"items": []})
        items = data.get("items", []) if isinstance(data, dict) else []
        items.append(row)
        write_json_file(ADMIN_AUDIT_FILE, {"items": items[-1000:]})
    return normalize_admin_audit_row(row)


def load_admin_usage_rows(days=30):
    days = max(1, min(int(days or 30), 365))
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_USAGE_DAILY_TABLE):
        return []
    since = (datetime.now(KST).date() - timedelta(days=days - 1)).isoformat()
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_USAGE_DAILY_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            params={
                "select": "username,usage_date,tab_name,view_count,last_viewed_at",
                "usage_date": f"gte.{since}",
                "order": "usage_date.desc,last_viewed_at.desc",
                "limit": "10000",
            },
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Admin usage load skipped: {response.status_code} {response.text[:300]}", flush=True)
            return []
        return response.json()
    except Exception as exc:
        print(f"Admin usage load failed: {exc}", flush=True)
        return []


def build_admin_usage_summary(rows, days=30):
    tab_totals = {}
    daily_totals = {}
    user_totals = {}
    for row in rows or []:
        username = normalize_login_id((row or {}).get("username"))
        tab_name = str((row or {}).get("tab_name") or "").strip().lower()
        usage_date = str((row or {}).get("usage_date") or "")[:10]
        views = max(0, int((row or {}).get("view_count") or 0))
        last_viewed_at = str((row or {}).get("last_viewed_at") or "")
        if not username or tab_name not in USAGE_TAB_NAMES or not usage_date:
            continue
        tab_item = tab_totals.setdefault(tab_name, {"tab": tab_name, "views": 0, "users": set()})
        tab_item["views"] += views
        tab_item["users"].add(username)
        daily_item = daily_totals.setdefault(usage_date, {"date": usage_date, "views": 0, "users": set()})
        daily_item["views"] += views
        daily_item["users"].add(username)
        user_item = user_totals.setdefault(username, {"views": 0, "lastViewedAt": "", "tabs": {}})
        user_item["views"] += views
        user_item["tabs"][tab_name] = user_item["tabs"].get(tab_name, 0) + views
        if last_viewed_at > user_item["lastViewedAt"]:
            user_item["lastViewedAt"] = last_viewed_at
    tabs = [
        {"tab": item["tab"], "views": item["views"], "users": len(item["users"])}
        for item in tab_totals.values()
    ]
    tabs.sort(key=lambda item: (item["views"], item["users"]), reverse=True)
    daily = [
        {"date": item["date"], "views": item["views"], "activeUsers": len(item["users"])}
        for item in daily_totals.values()
    ]
    daily.sort(key=lambda item: item["date"], reverse=True)
    by_user = {}
    for username, item in user_totals.items():
        top_tabs = sorted(item["tabs"].items(), key=lambda pair: pair[1], reverse=True)[:3]
        by_user[username] = {
            "views": item["views"],
            "lastViewedAt": item["lastViewedAt"],
            "topTabs": [{"tab": tab, "views": views} for tab, views in top_tabs],
        }
    return {
        "days": int(days),
        "activeUsers": len(user_totals),
        "totalViews": sum(item["views"] for item in tabs),
        "tabs": tabs,
        "daily": daily,
        "byUser": by_user,
    }


def admin_user_rows(users, channels, usage_by_user=None):
    usage_by_user = usage_by_user or {}
    channel_counts = {}
    for channel in channels:
        owner = normalize_login_id(channel.get("owner"))
        channel_counts[owner] = channel_counts.get(owner, 0) + 1
    rows = []
    for user in users:
        username = normalize_login_id((user or {}).get("username"))
        if not username:
            continue
        settings = sanitize_app_settings((user or {}).get("appSettings"))
        channel_follows = [item for item in settings.get("communityFollows", []) if str(item).startswith("channel:")]
        usage = usage_by_user.get(username) or {}
        stored_active = str((user or {}).get("lastActiveAt") or "")
        usage_active = str(usage.get("lastViewedAt") or "")
        rows.append({
            "username": username,
            "nickname": str((user or {}).get("nickname") or username),
            "createdAt": str((user or {}).get("createdAt") or ""),
            "lastLoginAt": str((user or {}).get("lastLoginAt") or ""),
            "lastActiveAt": max(stored_active, usage_active),
            "loginCount": max(0, int((user or {}).get("loginCount") or 0)),
            "usageViews": max(0, int(usage.get("views") or 0)),
            "topTabs": usage.get("topTabs") or [],
            "channelCount": int(channel_counts.get(username, 0)),
            "subscriptionCount": len(set(channel_follows)),
            "isAdmin": is_super_admin(username),
        })
    return sorted(rows, key=lambda item: item.get("createdAt") or "", reverse=True)


def load_admin_users():
    """Load user settings and optional activity columns for operations views."""
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        selections = (
            "username,nickname,createdAt,appSettings,lastLoginAt,lastActiveAt,loginCount",
            "username,nickname,createdAt,appSettings",
        )
        for index, selection in enumerate(selections):
            try:
                response = requests.get(
                    f"{SUPABASE_URL}/rest/v1/{SUPABASE_USERS_TABLE}",
                    headers={
                        "apikey": SUPABASE_SERVICE_ROLE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                    },
                    params={"select": selection, "order": "createdAt.desc"},
                    timeout=15,
                )
                if response.status_code < 400:
                    return response.json()
                if index == len(selections) - 1:
                    print(f"Admin user store load failed: {response.status_code} {response.text[:300]}", flush=True)
            except Exception as exc:
                if index == len(selections) - 1:
                    print(f"Admin user store load failed: {exc}", flush=True)
        return []
    return load_users()

def admin_content_rows(posts, channels):
    channel_names = {str(channel.get("id")): str(channel.get("name") or "채널") for channel in channels}
    rows = []
    for post in posts:
        post_id = str((post or {}).get("id") or "")
        if not post_id:
            continue
        channel_id = extract_community_channel_id(post)
        body = str((post or {}).get("body") or "").replace("\u200b", "").strip()
        rows.append({"id": post_id, "category": str((post or {}).get("category") or ""), "title": str((post or {}).get("title") or "")[:120], "body": body[:320], "author": str((post or {}).get("author") or ""), "username": normalize_login_id((post or {}).get("username")), "channelId": channel_id, "channelName": channel_names.get(str(channel_id), "") if channel_id else "", "visibility": str((post or {}).get("visibility") or "public"), "createdAt": str((post or {}).get("createdAt") or ""), "attachmentCount": len((post or {}).get("attachments") or []), "commentCount": len((post or {}).get("comments") or [])})
    return rows


@app.route("/admin")
def admin_page_route():
    if not session.get("logged_in") or not is_super_admin():
        return "", 404
    return render_template("admin.html")


@app.route("/api/admin/overview")
@admin_api_required
def admin_overview_route():
    users = load_admin_users()
    channels = load_community_channels()
    posts = load_community_posts_raw(500)
    usage_summary = build_admin_usage_summary(load_admin_usage_rows(30), 30)
    usage_by_user = usage_summary.pop("byUser", {})
    user_rows = admin_user_rows(users, channels, usage_by_user)
    content_rows = admin_content_rows(posts, channels)
    channel_message_counts = {}
    for item in content_rows:
        channel_id = str(item.get("channelId") or "")
        if channel_id:
            channel_message_counts[channel_id] = channel_message_counts.get(channel_id, 0) + 1
    channel_rows = []
    for channel in channels:
        row = dict(channel)
        row["messageCount"] = int(channel_message_counts.get(str(channel.get("id") or ""), 0))
        channel_rows.append(row)
    message_count = sum(channel_message_counts.values())
    attachment_count = sum(int(item.get("attachmentCount") or 0) for item in content_rows)
    subscription_count = sum(int(channel.get("subscriberCount") or 0) for channel in channels)
    return jsonify({"ok": True, "generatedAt": datetime.now(KST).isoformat(), "stats": {"users": len(user_rows), "channels": len(channels), "posts": len(content_rows) - message_count, "messages": message_count, "subscriptions": subscription_count, "attachments": attachment_count}, "users": user_rows, "channels": channel_rows, "content": content_rows, "usage": usage_summary, "audit": load_admin_audit_logs(150)})


@app.route("/api/admin/channels/<channel_id>/subscribers")
@admin_api_required
def admin_channel_subscribers_route(channel_id):
    channel = next((item for item in load_community_channels() if str(item.get("id")) == str(channel_id)), None)
    if not channel:
        return jsonify({"ok": False, "error": "채널을 찾을 수 없습니다."}), 404
    key = f"channel:{channel_id}"
    subscribers = []
    for user in load_admin_users():
        settings = sanitize_app_settings((user or {}).get("appSettings"))
        if key not in settings.get("communityFollows", []):
            continue
        subscribers.append({"username": normalize_login_id((user or {}).get("username")), "nickname": str((user or {}).get("nickname") or (user or {}).get("username") or "회원"), "createdAt": str((user or {}).get("createdAt") or "")})
    return jsonify({"ok": True, "channel": {"id": channel_id, "name": channel.get("name")}, "items": subscribers})


@app.route("/api/admin/channels/<channel_id>", methods=["DELETE"])
@admin_api_required
def admin_delete_channel_route(channel_id):
    channel = next((item for item in load_community_channels() if str(item.get("id")) == str(channel_id)), None)
    if not channel:
        return jsonify({"ok": False, "error": "채널을 찾을 수 없습니다."}), 404
    payload = request.get_json(silent=True) or {}
    if str(payload.get("confirmText") or "").strip() != str(channel.get("name") or "").strip():
        return jsonify({"ok": False, "error": "채널 이름 확인이 일치하지 않습니다."}), 400
    response = app.make_response(delete_community_channel_route(channel_id))
    if response.status_code < 400:
        append_admin_audit("delete", "channel", channel_id, {"name": channel.get("name"), "owner": channel.get("owner")})
    return response


@app.route("/api/admin/content/<post_id>", methods=["DELETE"])
@admin_api_required
def admin_delete_content_route(post_id):
    post = get_community_post(post_id, increment_views=False)
    if not post:
        return jsonify({"ok": False, "error": "콘텐츠를 찾을 수 없습니다."}), 404
    payload = request.get_json(silent=True) or {}
    if str(payload.get("confirmText") or "").strip() != "DELETE":
        return jsonify({"ok": False, "error": "DELETE 확인 문구가 필요합니다."}), 400
    response = app.make_response(delete_community_post_route(post_id))
    if response.status_code < 400:
        append_admin_audit("delete", "content", post_id, {"title": post.get("title"), "username": post.get("username"), "category": post.get("category")})
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(debug=False, port=port)













