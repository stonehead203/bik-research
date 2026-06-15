from datetime import datetime
import math
import os

import pandas as pd
import yfinance as yf
from deep_translator import GoogleTranslator
from flask import Flask, jsonify, render_template, request, send_from_directory, session


app = Flask(__name__, template_folder=".")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

APP_USERNAME = os.environ.get("APP_USERNAME", "hodu")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "academy")


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
    fast = ticker_obj.fast_info
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
        return {"price": safe_number(latest), "change": safe_number(change)}

    price = get_fast_price(ticker)
    return {"price": safe_number(price), "change": 0}


def has_activity_near_price(calls, puts, current_price, column, band=0.15):
    try:
        low = current_price * (1 - band)
        high = current_price * (1 + band)
        calls_near = calls[(calls["strike"] >= low) & (calls["strike"] <= high)]
        puts_near = puts[(puts["strike"] >= low) & (puts["strike"] <= high)]
        call_sum = pd.to_numeric(calls_near[column], errors="coerce").fillna(0).sum()
        put_sum = pd.to_numeric(puts_near[column], errors="coerce").fillna(0).sum()
        return (call_sum + put_sum) > 0
    except Exception:
        return False


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
            if has_activity_near_price(calls, puts, current_price, "volume", band):
                return expiry, chain, "volume"
        except Exception as exc:
            print(f"옵션 만기 조회 실패({expiry}): {exc}")

    return None, None, None


def translate_to_korean(text):
    if not text:
        return text
    try:
        return GoogleTranslator(source="auto", target="ko").translate(text)
    except Exception:
        return text


def build_option_data(ticker_symbol, ticker, current_price):
    empty = {
        "optionStrikes": [],
        "optionCallVolume": [],
        "optionPutVolume": [],
        "optionIv": [],
        "optionView": "N/A",
        "optionPcr": "N/A",
        "optionExpiry": "N/A",
        "optionDaysLeft": "N/A",
        "optionBasis": "거래량",
        "optionDominantZone": "N/A",
    }
    if ".KS" in ticker_symbol or ".KQ" in ticker_symbol:
        return empty

    try:
        expiry, chain, basis = get_valid_option_chain(ticker, current_price)
        if not expiry or not chain:
            return empty

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
            return empty

        def call_moneyness(strike):
            if abs(strike - current_price) / current_price <= 0.01:
                return "ATM"
            return "ITM" if strike < current_price else "OTM"

        def put_moneyness(strike):
            if abs(strike - current_price) / current_price <= 0.01:
                return "ATM"
            return "ITM" if strike > current_price else "OTM"

        call_values = [int(x) for x in merged["volume_call"]]
        put_values = [int(x) for x in merged["volume_put"]]
        total_call = sum(call_values)
        total_put = sum(put_values)
        pcr = round(total_put / total_call, 2) if total_call else "N/A"

        strikes = [float(x) for x in merged["strike"]]
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
            view = "콜/풋 균형: 변동성 이벤트 대기 가능성"
        elif pcr < 0.85:
            view = "콜 거래 우위: 단기 상방 관심 증가"
        else:
            view = "풋 거래 우위: 방어적 수요 증가"

        iv_values = []
        for _, row in merged.iterrows():
            call_iv = row["impliedVolatility_call"]
            put_iv = row["impliedVolatility_put"]
            valid = [x for x in (call_iv, put_iv) if x > 0]
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
        print(f"옵션 처리 오류: {exc}")
        return empty


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


@app.route("/api/company")
def company_info():
    ticker_symbol = request.args.get("ticker", "").strip().upper()
    if not ticker_symbol:
        return jsonify({"error": "티커를 입력하세요."}), 400
    if ticker_symbol.isdigit() and len(ticker_symbol) == 6:
        ticker_symbol = f"{ticker_symbol}.KS"

    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        if not info or len(info) <= 5:
            return jsonify({"error": "회사 데이터를 찾을 수 없습니다."}), 404

        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        if not current_price:
            history = ticker.history(period="1d")
            current_price = float(history["Close"].iloc[-1]) if not history.empty else get_fast_price(ticker)

        dividend_rate = info.get("dividendRate") or 0
        raw_yield = info.get("dividendYield") or 0
        if dividend_rate and current_price:
            dividend_yield = (dividend_rate / current_price) * 100 if raw_yield > 0.1 else raw_yield * 100
        else:
            dividend_yield = 0

        news = []
        try:
            for item in (ticker.news or [])[:5]:
                content = item.get("content", {})
                title = item.get("title") or content.get("title")
                if not title:
                    continue
                publisher = item.get("publisher") or content.get("provider", {}).get("name") or "Yahoo Finance"
                link = item.get("link") or content.get("clickThroughUrl", {}).get("url") or content.get("url") or "#"
                news.append({
                    "title": translate_to_korean(title),
                    "publisher": publisher,
                    "link": link,
                })
        except Exception as exc:
            print(f"뉴스 수집 오류: {exc}")

        summary = info.get("longBusinessSummary") or info.get("description") or "회사 소개 정보가 없습니다."
        if summary != "회사 소개 정보가 없습니다.":
            summary = translate_to_korean(summary)

        result = {
            "ticker": ticker_symbol,
            "name": info.get("longName") or info.get("shortName") or ticker_symbol,
            "price": safe_number(current_price),
            "marketCap": info.get("marketCap", "N/A"),
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
        print(f"종목 검색 오류: {exc}")
        return jsonify({"error": "데이터 조회 중 오류가 발생했습니다."}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(debug=True, port=port)
