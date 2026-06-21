# Toss 국내종목 자동 수집 설정

이 버전은 `TOSS_REQUESTS_JSON`에 종목을 하나씩 넣지 않아도 됩니다.
OCI collector가 KRX/KIND 상장법인 목록을 가져와 국내 종목코드를 만들고, Toss `/api/v1/prices`를 200개씩 나눠 호출합니다.

`/etc/bik-toss-collector.env`에 아래 값을 추가하거나 수정하세요.

```bash
TOSS_KR_UNIVERSE_ENABLED=true
TOSS_COLLECT_KR_PRICES=true
TOSS_COLLECT_KR_STOCK_INFO=true
TOSS_STOCK_INFO_INTERVAL_SECONDS=86400
TOSS_BATCH_SIZE=200
TOSS_BATCH_SLEEP_SECONDS=0.15
TOSS_COLLECTOR_STATE_FILE=/home/ubuntu/bik-research/outputs/toss_collector_state.json
TOSS_COLLECTOR_LOCK_FILE=/tmp/bik-toss-collector.lock
TOSS_REQUESTS_JSON=[]
TOSS_COLLECT_KR_PRICE_LIMITS=true
TOSS_COLLECT_KR_CANDLES=true
TOSS_CANDLE_INTERVALS=1d,1m
TOSS_CANDLE_COUNT=60
TOSS_DETAIL_INTERVAL_SECONDS=300
# 쉼표로 구분한 상세 수집 종목. 비우면 대표 국내종목 기본값을 사용합니다.
# TOSS_KR_DETAIL_SYMBOLS=005930,000660,035420
```

기존의 `RENDER_INGEST_URL`, `INGEST_SECRET`, `TOSSINVEST_BASE_URL`, `TOSSINVEST_API_KEY`, `TOSSINVEST_SECRET_KEY`는 유지해야 합니다.

테스트:

```bash
sudo bash -c 'set -a; . /etc/bik-toss-collector.env; set +a; cd /home/ubuntu/bik-research/outputs; .venv/bin/python toss_collector.py --dry-run'
```

정상이라면 `kr_universe`, `kr_prices_001`, `kr_price_limit_005930`, `kr_candles_1d_005930` 같은 항목이 보입니다.

`price-limits`와 `candles`는 전체 국내 종목을 매분 모두 호출하지 않고 `TOSS_KR_DETAIL_SYMBOLS`에 지정한 상세 종목만 수집합니다. 기본값은 대표 종목 30개이며, 종목을 늘리려면 예를 들어 아래처럼 추가합니다.

```bash
TOSS_KR_DETAIL_SYMBOLS=005930,000660,035420,035720
TOSS_DETAIL_SYMBOL_LIMIT=50
```
