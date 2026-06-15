from datetime import datetime
import math
import os
import time

import pandas as pd
import requests
import yfinance as yf
from deep_translator import GoogleTranslator
from flask import Flask, jsonify, render_template, request, send_from_directory, session


app = Flask(__name__, template_folder=".")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

APP_USERNAME = os.environ.get("APP_USERNAME", "hodu")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "academy")

TOSSINVEST_API_KEY = os.environ.get("TOSSINVEST_API_KEY") or os.environ.get("TOSSINVEST_CLIENT_ID")
TOSSINVEST_SECRET_KEY = os.environ.get("TOSSINVEST_SECRET_KEY") or os.environ.get("TOSSINVEST_CLIENT_SECRET")
TOSSINVEST_BASE_URL = os.environ.get("TOSSINVEST_BASE_URL", "https://openapi.tossinvest.com").rstrip("/")
TOSS_TOKEN_CACHE = {"access_token": None, "expires_at": 0}


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


def decimal_value(value, default=0.0):
    try:
        if value in (None, "", "N/A"):
            return default
        return float(value)
    except Exception:
        return default


def percent_change(latest, previous):
    latest = decimal_value(latest)
    previous = decimal_value(previous)
    if not previous:
        return 0
    return ((latest - previous) / previous) * 100


def normalize_symbol(raw_symbol):
    symbol = (raw_symbol or "").strip().upper()
    if symbol.endswith(".KS") or symbol.endswith(".KQ"):
        symbol = symbol[:-3]
    return symbol


def yfinance_symbol(symbol):
    symbol = normalize_symbol(symbol)
    if symbol.isdigit() and len(symbol) == 6:
        return f"{symbol}.KS"
    return symbol


def is_toss_configured():
    return bool(TOSSINVEST_API_KEY and TOSSINVEST_SECRET_KEY)


def toss_access_token():
    if not is_toss_configured():
        raise RuntimeError("Toss API credentials are not configured.")

    now = time.time()
    if TOSS_TOKEN_CACHE["access_token"] and TOSS_TOKEN_CACHE["expires_at"] > now + 30:
        return TOSS_TOKEN_CACHE["access_token"]

    response = requests.post(
        f"{TOSSINVEST_BASE_URL}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": TOSSINVEST_API_KEY,
            "client_secret": TOSSINVEST_SECRET_KEY,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    access_token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))
    TOSS_TOKEN_CACHE.update({
        "access_token": access_token,
        "expires_at": now + max(60, expires_in - 60),
    })
    return access_token


def toss_get(path, params=None):
    token = toss_access_token()
    response = requests.get(
        f"{TOSSINVEST_BASE_URL}{path}",
        params=params or {},
        headers={"Authorization": f"Bearer {token}"},
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("result", payload)


def first_item(value):
    if isinstance(value, list):
        return value[0] if value else {}
    return value or {}


def sorted_candles(candles):
    return sorted(candles or [], key=lambda item: item.get("timestamp") or "")


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
        return {"price": safe_number(latest), "change": safe_number(percent_change(latest, prev))}

    price = get_fast_price(ticker)
    return {"price": safe_number(price), "change": 0}


def translate_to_korean(text):
    if not text:
        return text
    try:
        return GoogleTranslator(source="auto", target="ko").translate(text)
    except Exception:
        return text


def empty_option_data(message="옵션 데이터는 현재 제공되지 않습니다."):
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
    if ".KS" in ticker_symbol or ".KQ" in ticker_symbol or ticker_symbol.isdigit():
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


def toss_calendar_card(country):
    try:
        result = toss_get(f"/api/v1/market-calendar/{country}")
        today = result.get("today", {})
        previous_day = result.get("previousBusinessDay", {})
        is_open = today.get("isBusinessDay")
        label = "정규장 운영" if is_open else "휴장"
        return {
            "price": label,
            "change": 0,
            "asOf": today.get("date"),
            "detail": f"이전 영업일: {previous_day.get('date', 'N/A')}",
            "source": "Toss OpenAPI",
        }
    except Exception as exc:
        print(f"Toss {country} market calendar failed: {exc}", flush=True)
        return {"price": "N/A", "change": 0, "source": "Fallback"}


def toss_exchange_card():
    try:
        result = toss_get("/api/v1/exchange-rate", {
            "baseCurrency": "USD",
            "quoteCurrency": "KRW",
        })
        change_type = result.get("rateChangeType") or ""
        change = 1 if change_type == "UP" else -1 if change_type == "DOWN" else 0
        return {
            "price": safe_number(result.get("rate")),
            "change": change,
            "asOf": result.get("validFrom"),
            "detail": f"mid {result.get('midRate', 'N/A')}",
            "source": "Toss OpenAPI",
        }
    except Exception as exc:
        print(f"Toss exchange-rate failed: {exc}", flush=True)
        return {"price": "N/A", "change": 0, "source": "Fallback"}


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
            indices_data[name] = {"price": "N/A", "change": 0}

    for name, symbol in macro.items():
        try:
            macro_data[name] = get_price_change(symbol)
        except Exception:
            macro_data[name] = {"price": "N/A", "change": 0}

    macro_data["USD/KRW 환율"] = toss_exchange_card()
    macro_data["한국 시장"] = toss_calendar_card("KR")
    macro_data["미국 시장"] = toss_calendar_card("US")

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
        status = "Extreme Fear (극도의 공포)"
    elif sentiment_score <= 45:
        status = "Fear (공포)"
    elif sentiment_score <= 55:
        status = "Neutral (중립)"
    elif sentiment_score <= 75:
        status = "Greed (탐욕)"
    else:
        status = "Extreme Greed (극도의 탐욕)"

    return jsonify({
        "indices": indices_data,
        "macro": macro_data,
        "sentiment": {"score": sentiment_score, "status": status},
    })


def toss_company_info(symbol):
    normalized = normalize_symbol(symbol)
    stock = first_item(toss_get("/api/v1/stocks", {"symbols": normalized}))
    price_info = first_item(toss_get("/api/v1/prices", {"symbols": normalized}))
    candles_page = toss_get("/api/v1/candles", {
        "symbol": normalized,
        "interval": "1d",
        "count": 200,
        "adjusted": "true",
    })
    candles = sorted_candles(candles_page.get("candles", []))
    closes = [decimal_value(item.get("closePrice")) for item in candles if item.get("closePrice") is not None]
    latest_candle = candles[-1] if candles else {}
    previous_candle = candles[-2] if len(candles) >= 2 else {}
    current_price = decimal_value(price_info.get("lastPrice") or latest_candle.get("closePrice"))
    previous_close = decimal_value(previous_candle.get("closePrice"))
    shares = decimal_value(stock.get("sharesOutstanding"))
    currency = price_info.get("currency") or stock.get("currency") or latest_candle.get("currency") or "USD"

    warnings = []
    try:
        warnings = toss_get(f"/api/v1/stocks/{normalized}/warnings")
        if not isinstance(warnings, list):
            warnings = warnings.get("warnings", [])
    except Exception as exc:
        print(f"Toss warnings failed({normalized}): {exc}", flush=True)

    market_cap = current_price * shares if current_price and shares else "N/A"
    high52w = max([decimal_value(item.get("highPrice")) for item in candles], default="N/A")
    low52w = min([decimal_value(item.get("lowPrice")) for item in candles], default="N/A")
    avg50d = sum(closes[-50:]) / min(50, len(closes)) if closes else "N/A"
    avg200d = sum(closes[-200:]) / min(200, len(closes)) if closes else "N/A"
    volume = decimal_value(latest_candle.get("volume"), 0)

    summary = (
        f"{stock.get('name') or normalized}은(는) {stock.get('market', 'N/A')} 시장의 "
        f"{stock.get('securityType', 'N/A')} 종목입니다. "
        f"실시간 현재가와 일봉 기반 가격 밴드는 Toss OpenAPI로 조회했습니다."
    )
    if warnings:
        warning_text = ", ".join(sorted({item.get("warningType", "UNKNOWN") for item in warnings}))
        summary += f" 현재 매수 유의사항: {warning_text}."

    return {
        "ticker": normalized,
        "name": stock.get("name") or stock.get("englishName") or normalized,
        "price": safe_number(current_price),
        "priceChange": safe_number(percent_change(current_price, previous_close)),
        "marketCap": safe_number(market_cap, 0) if market_cap != "N/A" else "N/A",
        "currency": currency,
        "market": stock.get("market", "N/A"),
        "status": stock.get("status", "N/A"),
        "asOf": price_info.get("timestamp") or latest_candle.get("timestamp"),
        "dataSource": "Toss OpenAPI",
        "warnings": warnings,
        "peRatio": "미제공",
        "pbrRatio": "미제공",
        "pegRatio": "미제공",
        "dividendYield": "미제공",
        "summary": summary,
        "instOwnership": "미제공",
        "insiderOwnership": "미제공",
        "shortRatio": "미제공",
        "shortPctFloat": "미제공",
        "targetMean": "미제공",
        "targetHigh": "미제공",
        "targetLow": "미제공",
        "recommendation": "TOSS LIVE",
        "analystCount": "Toss OpenAPI 미제공",
        "eps": "미제공",
        "debtToEquity": "미제공",
        "volume": int(volume),
        "avgVolume": "N/A",
        "high52w": safe_number(high52w),
        "low52w": safe_number(low52w),
        "avg50d": safe_number(avg50d),
        "avg200d": safe_number(avg200d),
        "news": [],
        **empty_option_data("Toss OpenAPI는 옵션 체인을 제공하지 않습니다."),
    }


def yfinance_company_info(symbol):
    ticker_symbol = yfinance_symbol(symbol)
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
        except Exception:
            current_price = get_fast_price(ticker)

    dividend_rate = info.get("dividendRate") or 0
    raw_yield = info.get("dividendYield") or 0
    dividend_yield = (dividend_rate / current_price) * 100 if dividend_rate and current_price and raw_yield > 0.1 else raw_yield * 100

    news = []
    try:
        for item in (ticker.news or [])[:5]:
            content = item.get("content", {})
            title = item.get("title") or content.get("title")
            if not title:
                continue
            publisher = item.get("publisher") or content.get("provider", {}).get("name") or "Yahoo Finance"
            link = item.get("link") or content.get("clickThroughUrl", {}).get("url") or content.get("url") or "#"
            news.append({"title": translate_to_korean(title), "publisher": publisher, "link": link})
    except Exception as exc:
        print(f"뉴스 수집 오류: {exc}", flush=True)

    summary = info.get("longBusinessSummary") or info.get("description") or "회사 소개 정보가 없습니다."
    if summary != "회사 소개 정보가 없습니다.":
        summary = translate_to_korean(summary)

    result = {
        "ticker": ticker_symbol,
        "name": info.get("longName") or info.get("shortName") or ticker_symbol,
        "price": safe_number(current_price),
        "priceChange": "N/A",
        "marketCap": info.get("marketCap", "N/A"),
        "currency": info.get("currency", "USD"),
        "market": info.get("exchange", "N/A"),
        "status": "Fallback",
        "asOf": datetime.now().isoformat(timespec="seconds"),
        "dataSource": "Yahoo Finance fallback",
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
    return result


@app.route("/api/company")
def company_info():
    ticker_symbol = normalize_symbol(request.args.get("ticker", ""))
    if not ticker_symbol:
        return jsonify({"error": "티커를 입력하세요."}), 400

    try:
        try:
            return jsonify(toss_company_info(ticker_symbol))
        except Exception as toss_exc:
            print(f"Toss 종목 조회 실패({ticker_symbol}), fallback 사용: {toss_exc}", flush=True)
            return jsonify(yfinance_company_info(ticker_symbol))
    except Exception as exc:
        print(f"종목 검색 오류: {exc}", flush=True)
        return jsonify({"error": "데이터 조회 중 오류가 발생했습니다."}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(debug=True, port=port)
