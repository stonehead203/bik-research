from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import html as html_lib
import json
import math
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

import pandas as pd
import yfinance as yf
from deep_translator import GoogleTranslator
from flask import Flask, jsonify, render_template, request, send_from_directory, session


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


@app.route("/favicon.svg")
def favicon():
    return send_from_directory(app.template_folder, "favicon.svg", mimetype="image/svg+xml")


@app.route("/og-image.svg")
def og_image():
    return send_from_directory(app.template_folder, "og-image.svg", mimetype="image/svg+xml")


@app.route("/og-image.png")
def og_image_png():
    return send_from_directory(app.template_folder, "og-image.png", mimetype="image/png")


@app.route("/api/auth/status")
def auth_status():
    return jsonify({
        "loggedIn": bool(session.get("logged_in")),
        "username": session.get("username"),
    })


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))

    if username == APP_USERNAME and password == APP_PASSWORD:
        session["logged_in"] = True
        session["username"] = username
        return jsonify({"ok": True, "username": username})

    return jsonify({"ok": False, "error": "아이디 또는 비밀번호가 올바르지 않습니다."}), 401


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
    articles = []
    seen = set()
    for source in RSS_SOURCES:
        for article in fetch_rss_articles(source):
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

    return jsonify({
        "items": top_articles,
        "sources": list(dict.fromkeys(source["name"] for source in RSS_SOURCES)),
        "sourceNote": "RSS 기반 최신 글로벌 뉴스",
    })


@app.route("/api/company")
def company_info():
    ticker_symbol = request.args.get("ticker", "").strip().upper()
    if not ticker_symbol:
        return jsonify({"error": "티커를 입력하세요."}), 400
    if ticker_symbol.isdigit() and len(ticker_symbol) == 6:
        ticker_symbol = f"{ticker_symbol}.KS"

    try:
        ticker = yf.Ticker(ticker_symbol)
        try:
            info = ticker.info or {}
        except Exception as exc:
            print(f"회사 기본 정보 조회 실패({ticker_symbol}): {exc}", flush=True)
            info = {}

        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        if not current_price:
            try:
                history = ticker.history(period="1d")
                current_price = float(history["Close"].iloc[-1]) if not history.empty else get_fast_price(ticker)
            except Exception as exc:
                print(f"현재가 조회 실패({ticker_symbol}): {exc}", flush=True)
                current_price = get_fast_price(ticker)

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
            "marketCap": info.get("marketCap", "N/A"),
            "currency": info.get("currency", "USD"),
            "market": info.get("exchange", "N/A"),
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
        return jsonify(result)
    except Exception as exc:
        print(f"종목 검색 오류: {exc}", flush=True)
        return jsonify({"error": "데이터 조회 중 오류가 발생했습니다."}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(debug=True, port=port)
