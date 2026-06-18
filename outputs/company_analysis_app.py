from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
import html as html_lib
import json
import math
import os
import re
import secrets
import smtplib
import threading
import time
import urllib.request
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from flask import Flask, jsonify, render_template, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash


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

app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

APP_USERNAME = os.environ.get("APP_USERNAME", "hodu")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "academy")
KST = timezone(timedelta(hours=9))
API_CACHE = {}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_USERS_FILE = "/var/data/users.json" if os.path.isdir("/var/data") else os.path.join(BASE_DIR, "users.json")
USERS_FILE = os.environ.get("USERS_FILE", DEFAULT_USERS_FILE)
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
EMAIL_VERIFICATION_CODES = {}
EMAIL_VERIFICATION_TTL_SECONDS = 180

ETH_MARKET_FILE = os.path.join(BASE_DIR, "eth_market_data.json")
ETH_NEWS_FILE = os.path.join(BASE_DIR, "eth_tokenpost_news.json")
ETH_MARKET_INTERVAL = 300
ETH_NEWS_INTERVAL = 3600
TOKENPOST_URL = "https://www.tokenpost.kr/news/blockchain/"
TOKENPOST_BASE = "https://www.tokenpost.kr"
UPBIT_TICKER_API = "https://api.upbit.com/v1/ticker?markets=KRW-ETH"
UPBIT_STAKING_PUBLIC_API = "https://uss.upbit.com/api/v2/staking/public"
NAVER_FINANCE_URL = "https://finance.naver.com/"
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
        API_CACHE.pop(key, None)
        return None
    return cached["value"]


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
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "-1"
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
@app.route("/Watchlist")
@app.route("/watchlist")
@app.route("/Prediction-Market")
@app.route("/prediction-market")
@app.route("/Ethereum-Tracker")
@app.route("/ethereum-tracker")
@app.route("/auth/join")
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
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def file_age_seconds(path):
    if not os.path.exists(path):
        return float("inf")
    return max(0, time.time() - os.path.getmtime(path))


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
    previous = read_json_file(ETH_MARKET_FILE, {})
    result = {
        "eth_krw": previous.get("eth_krw"),
        "usd_krw": previous.get("usd_krw"),
        "eth_apr": previous.get("eth_apr"),
        "updated_at": None,
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
    write_json_file(ETH_MARKET_FILE, result)
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
    write_json_file(ETH_NEWS_FILE, payload)
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


def ensure_eth_market_fresh(force=False):
    if force or file_age_seconds(ETH_MARKET_FILE) > ETH_MARKET_INTERVAL:
        start_thread(run_eth_market_refresh)


def ensure_eth_news_fresh(force=False):
    if force or file_age_seconds(ETH_NEWS_FILE) > ETH_NEWS_INTERVAL:
        start_thread(run_eth_news_refresh)


@app.route("/api/eth-tracker/market")
def eth_tracker_market():
    ensure_eth_market_fresh(request.args.get("refresh") == "1")
    payload = read_json_file(ETH_MARKET_FILE, {
        "eth_krw": 0,
        "usd_krw": 0,
        "eth_apr": "0%",
        "updated_at": None,
    })
    payload["refreshing"] = ETH_MARKET_RUNNING
    return jsonify(payload)


@app.route("/api/eth-tracker/news")
def eth_tracker_news():
    ensure_eth_news_fresh(request.args.get("refresh") == "1")
    payload = read_json_file(ETH_NEWS_FILE, {
        "updated_at": None,
        "articles": [],
    })
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


def public_user(user):
    return {
        "username": user.get("username"),
        "nickname": user.get("nickname") or user.get("username"),
        "email": user.get("email"),
        "createdAt": user.get("createdAt"),
    }


def find_user(login_id):
    normalized = normalize_login_id(login_id)
    for user in load_users():
        if normalize_login_id(user.get("username")) == normalized:
            return user
        if normalize_login_id(user.get("nickname")) == normalized:
            return user
        if normalize_login_id(user.get("email")) == normalized:
            return user
    return None


def update_user(username, updates):
    normalized = normalize_login_id(username)
    allowed_updates = {key: value for key, value in updates.items() if key in {"nickname", "passwordHash"}}
    if not allowed_updates:
        return find_user(username)

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


def verify_email_code(email, code):
    prune_email_codes()
    item = EMAIL_VERIFICATION_CODES.get(normalize_login_id(email))
    if not item:
        return False
    if not check_password_hash(item.get("codeHash", ""), str(code or "").strip()):
        return False
    item["verified"] = True
    return True


@app.route("/api/auth/status")
def auth_status():
    user = find_user(session.get("username")) if session.get("logged_in") else None
    return jsonify({
        "loggedIn": bool(session.get("logged_in")),
        "username": session.get("username"),
        "nickname": (user or {}).get("nickname") or session.get("nickname"),
        "email": (user or {}).get("email"),
    })


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))

    user = find_user(username)
    if user and check_password_hash(user.get("passwordHash", ""), password):
        session["logged_in"] = True
        session["username"] = user.get("username")
        session["nickname"] = user.get("nickname") or user.get("username")
        return jsonify({"ok": True, "username": user.get("username"), "nickname": session["nickname"]})

    if username == APP_USERNAME and password == APP_PASSWORD:
        session["logged_in"] = True
        session["username"] = username
        session["nickname"] = username
        return jsonify({"ok": True, "username": username, "nickname": username})

    return jsonify({"ok": False, "error": "아이디 또는 비밀번호가 올바르지 않습니다."}), 401


@app.route("/api/auth/send-verification", methods=["POST"])
def auth_send_verification():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"ok": False, "error": "올바른 이메일을 입력해주세요."}), 400

    if find_user(email) or normalize_login_id(email) == normalize_login_id(APP_USERNAME):
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
    }
    return jsonify({"ok": True, "email": email, "expiresInSeconds": EMAIL_VERIFICATION_TTL_SECONDS})


@app.route("/api/auth/verify-code", methods=["POST"])
def auth_verify_code():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    verification_code = str(payload.get("verificationCode", "")).strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"ok": False, "error": "올바른 이메일을 입력해주세요."}), 400
    if not verify_email_code(email, verification_code):
        return jsonify({"ok": False, "error": "인증코드가 올바르지 않거나 만료되었습니다."}), 400
    return jsonify({"ok": True, "email": email})


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
    updates = {}

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

    session["nickname"] = updated.get("nickname") or updated.get("username")
    profile = public_user(updated)
    profile["managed"] = True
    return jsonify({"ok": True, "user": profile})


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
    if not verify_email_code(email, verification_code):
        return jsonify({"ok": False, "error": "이메일 인증코드가 올바르지 않거나 만료되었습니다."}), 400

    username_base = re.sub(r"[^a-z0-9._-]+", "", email.split("@", 1)[0].lower()) or "user"
    users = load_users()
    existing_ids = {normalize_login_id(user.get("username")) for user in users}
    existing_emails = {normalize_login_id(user.get("email")) for user in users}
    existing_nicknames = {normalize_login_id(user.get("nickname")) for user in users}
    if normalize_login_id(email) in existing_emails or normalize_login_id(email) == normalize_login_id(APP_USERNAME):
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
            return AAII_FALLBACK.copy()

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
            return AAII_FALLBACK.copy()

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
        return result
    except Exception as exc:
        fallback = AAII_FALLBACK.copy()
        fallback["warning"] = f"AAII 원본 데이터를 불러오지 못해 마지막 정상 수집값을 표시합니다: {exc}"
        return fallback


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
            call_sum = pd.to_numeric(calls_near["volume"], errors="coerce").fillna(0).sum()
            put_sum = pd.to_numeric(puts_near["volume"], errors="coerce").fillna(0).sum()
            if call_sum + put_sum > 0:
                return expiry, chain, "volume"
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
            frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
            frame["impliedVolatility"] = pd.to_numeric(frame["impliedVolatility"], errors="coerce").fillna(0)

        merged = pd.merge(
            calls[["strike", "volume", "impliedVolatility"]],
            puts[["strike", "volume", "impliedVolatility"]],
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
        call_values = [int(x) for x in merged["volume_call"]]
        put_values = [int(x) for x in merged["volume_put"]]
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
            view = "콜 거래량 부족으로 PCR 산출 불가"
        elif buckets["콜 OTM"] == dominant_volume and pcr < 1.0:
            view = "콜 OTM 거래량 집중: 단기 상방 기대 거래 증가"
        elif buckets["풋 OTM"] == dominant_volume and pcr > 1.0:
            view = "풋 OTM 거래량 집중: 급락 방어/하방 보험 수요 증가"
        elif buckets["콜 ATM"] + buckets["풋 ATM"] >= (total_call + total_put) * 0.35:
            view = "ATM 거래량 집중: 현재가 부근 방향성 공방 심화"
        elif total_call > 0 and total_put > 0 and 0.85 <= pcr <= 1.15:
            view = "콜·풋 균형: 변동성 이벤트 대기 가능성"
        elif pcr < 0.85:
            view = "콜 거래 우위: 단기 상방 관심 증가"
        else:
            view = "풋 거래 우위: 방어적 수요 증가"

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
            "optionBasis": "거래량",
            "optionDominantZone": dominant_zone if dominant_volume else "N/A",
        }
    except Exception as exc:
        print(f"옵션 처리 오류: {exc}", flush=True)
        return empty_option_data()


@app.route("/api/market-data")
def market_data():
    indices = {
        "S&P 500": "^GSPC",
        "나스닥 종합": "^IXIC",
        "다우 존스": "^DJI",
    }
    macro = {
        "WTI 원유 ($/bbl)": "CL=F",
        "국제 금 시세 ($/oz)": "GC=F",
        "미국 국채 10년물 금리 (%)": "^TNX",
    }

    indices_data = {}
    macro_data = {}
    for name, symbol in indices.items():
        try:
            indices_data[name] = get_price_change(symbol)
        except Exception:
            indices_data[name] = {"price": "N/A", "change": 0, "source": "Yahoo Finance"}

    for name, symbol in macro.items():
        try:
            macro_data[name] = get_price_change(symbol)
        except Exception:
            macro_data[name] = {"price": "N/A", "change": 0, "source": "Yahoo Finance"}

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

    return jsonify({
        "indices": indices_data,
        "macro": macro_data,
        "sentiment": sentiment,
        "aaii": get_aaii_sentiment(),
    })


@app.route("/api/global-news")
def global_news():
    cached = get_cached_value("global-news", 180)
    if cached is not None:
        return jsonify(cached)

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

    payload = {
        "items": top_articles,
        "sources": list(dict.fromkeys(source["name"] for source in RSS_SOURCES)),
        "sourceNote": "RSS 기반 최신 글로벌 뉴스",
    }
    set_cached_value("global-news", payload)
    return jsonify(payload)


@app.route("/api/company")
def company_info():
    ticker_symbol = request.args.get("ticker", "").strip().upper()
    if not ticker_symbol:
        return jsonify({"error": "티커를 입력하세요."}), 400
    if ticker_symbol.isdigit() and len(ticker_symbol) == 6:
        ticker_symbol = f"{ticker_symbol}.KS"

    cache_key = f"company:{ticker_symbol}"
    cached = get_cached_value(cache_key, 60)
    if cached is not None:
        return jsonify(cached)

    try:
        ticker = yf.Ticker(ticker_symbol)
        try:
            info = ticker.info or {}
        except Exception as exc:
            print(f"회사 기본 정보 조회 실패({ticker_symbol}): {exc}", flush=True)
            info = {}

        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        change_percent = info.get("regularMarketChangePercent")
        if not current_price:
            try:
                history = ticker.history(period="1d")
                current_price = float(history["Close"].iloc[-1]) if not history.empty else get_fast_price(ticker)
                if change_percent is None and len(history) >= 2:
                    prev_close = float(history["Close"].iloc[-2])
                    change_percent = ((current_price - prev_close) / prev_close) * 100 if prev_close else None
            except Exception as exc:
                print(f"현재가 조회 실패({ticker_symbol}): {exc}", flush=True)
                current_price = get_fast_price(ticker)

        if not current_price and not info.get("marketCap") and not info.get("longName") and not info.get("shortName") and not info.get("exchange"):
            return jsonify({"error": "올바른 티커를 입력하세요."}), 404

        dividend_rate = info.get("dividendRate") or 0
        raw_yield = info.get("dividendYield") or 0
        if dividend_rate and current_price:
            dividend_yield = (dividend_rate / current_price) * 100 if raw_yield > 0.1 else raw_yield * 100
        else:
            dividend_yield = 0

        company_name = info.get("longName") or info.get("shortName") or ticker_symbol
        news = get_company_news(ticker_symbol, company_name, ticker)

        summary = info.get("longBusinessSummary") or info.get("description") or "회사 소개 정보가 없습니다."
        if summary != "회사 소개 정보가 없습니다.":
            summary = translate_to_korean(summary)

        result = {
            "ticker": ticker_symbol,
            "name": company_name,
            "price": safe_number(current_price),
            "changePercent": safe_number(change_percent),
            "marketCap": info.get("marketCap", "N/A"),
            "currency": info.get("currency", "USD"),
            "market": info.get("exchange", "N/A"),
            "marketState": info.get("marketState") or info.get("regularMarketState") or "UNKNOWN",
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
            "volume": info.get("regularMarketVolume") or info.get("volume") or 0,
            "avgVolume": info.get("averageVolume") or 0,
            "high52w": safe_number(info.get("fiftyTwoWeekHigh")),
            "low52w": safe_number(info.get("fiftyTwoWeekLow")),
            "avg50d": safe_number(info.get("fiftyDayAverage")),
            "avg200d": safe_number(info.get("twoHundredDayAverage")),
            "news": news,
        }
        result.update(build_option_data(ticker_symbol, ticker, float(current_price or 0)))
        set_cached_value(cache_key, result)
        return jsonify(result)
    except Exception as exc:
        print(f"종목 검색 오류: {exc}", flush=True)
        return jsonify({"error": "데이터 조회 중 오류가 발생했습니다."}), 500


start_eth_tracker_schedulers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(debug=False, port=port)
