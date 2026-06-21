# Toss 국내종목 자동 수집 설정

이 버전은 `TOSS_REQUESTS_JSON`에 종목을 하나씩 넣지 않아도 됩니다.
OCI collector가 KRX/KIND 상장법인 목록을 가져와 국내 종목코드를 만들고, Toss `/api/v1/prices`를 200개씩 나눠 호출합니다.

`/etc/bik-toss-collector.env`에 아래 값을 추가하거나 수정하세요.

```bash
TOSS_KR_UNIVERSE_ENABLED=true
TOSS_COLLECT_KR_PRICES=true
TOSS_COLLECT_KR_STOCK_INFO=true
TOSS_COLLECT_KR_PRICE_LIMITS=false
TOSS_COLLECT_KR_CANDLES=false
TOSS_STOCK_INFO_INTERVAL_SECONDS=86400
TOSS_BATCH_SIZE=200
TOSS_BATCH_SLEEP_SECONDS=0.15
TOSS_UPLOAD_CHUNK_SIZE=120
TOSS_DETAIL_CACHE_DIR=/home/ubuntu/bik-research/outputs/toss_detail_cache
TOSS_COLLECTOR_STATE_FILE=/home/ubuntu/bik-research/outputs/toss_collector_state.json
TOSS_COLLECTOR_LOCK_FILE=/tmp/bik-toss-collector.lock
TOSS_REQUESTS_JSON=[]
```

기존의 `RENDER_INGEST_URL`, `INGEST_SECRET`, `TOSSINVEST_BASE_URL`, `TOSSINVEST_API_KEY`, `TOSSINVEST_SECRET_KEY`는 유지해야 합니다.

## 수집 주기 구조

현재가와 일봉은 분리해서 돌립니다.

- `bik-toss-collector.timer`: 60초마다 전종목 현재가와 종목정보 캐시를 갱신합니다.
- `bik-toss-collector-eod.timer`: KRX 정규장 마감 이후와 NXT 마감 이후 하루 2회 전종목 일봉/상하한가를 갱신합니다.

서버 시간이 UTC 기준이면 아래 두 시간이 각각 KST 15:45, KST 20:15입니다.

```bash
sudo cp /home/ubuntu/bik-research/outputs/oci/bik-toss-collector.service /etc/systemd/system/bik-toss-collector.service
sudo cp /home/ubuntu/bik-research/outputs/oci/bik-toss-collector.timer /etc/systemd/system/bik-toss-collector.timer
sudo cp /home/ubuntu/bik-research/outputs/oci/bik-toss-collector-eod.service /etc/systemd/system/bik-toss-collector-eod.service
sudo cp /home/ubuntu/bik-research/outputs/oci/bik-toss-collector-eod.timer /etc/systemd/system/bik-toss-collector-eod.timer
sudo systemctl daemon-reload
sudo systemctl enable --now bik-toss-collector.timer
sudo systemctl enable --now bik-toss-collector-eod.timer
```

EOD collector는 service 파일에서 아래처럼 override합니다. 그래서 `/etc/bik-toss-collector.env`에 같은 값이 없어도 됩니다.

```bash
TOSS_COLLECT_KR_PRICE_LIMITS=true
TOSS_COLLECT_KR_CANDLES=true
TOSS_CANDLE_INTERVALS=1d
TOSS_CANDLE_COUNT=60
TOSS_DETAIL_SYMBOL_SCOPE=all
TOSS_DETAIL_SYMBOL_LIMIT=0
TOSS_DETAIL_INTERVAL_SECONDS=0
```

테스트:

```bash
sudo bash -c 'set -a; . /etc/bik-toss-collector.env; set +a; cd /home/ubuntu/bik-research/outputs; .venv/bin/python toss_collector.py --dry-run'
```

정상이라면 `kr_universe`, `kr_prices_001`, `kr_price_limit_005930`, `kr_candles_1d_005930` 같은 항목이 보입니다.

## Render memory notes

The Render app now keeps large per-symbol detail items outside the main `toss_cache.json`.
Items named like `kr_candles_1d_005930`, `kr_candles_1m_005930`, and `kr_price_limit_005930` are stored in `TOSS_DETAIL_CACHE_DIR` as separate JSON files. `/api/toss-company` reads only the requested symbol detail file, so the company beta tab can keep the daily chart without loading every candle into memory on each search.

`TOSS_UPLOAD_CHUNK_SIZE` makes the OCI collector upload items in smaller chunks. Keep this around `80` to `150` on Render Free to avoid large request bodies.

## Current-price-first mode

Start with the lightweight mode below. It collects all Korean stock prices and stock info, but skips per-symbol price limits and candles. The company beta tab can search symbols with current prices first. The daily chart will show a waiting message until the EOD/detail collector is enabled.

```bash
TOSS_KR_UNIVERSE_ENABLED=true
TOSS_COLLECT_KR_PRICES=true
TOSS_COLLECT_KR_STOCK_INFO=true
TOSS_COLLECT_KR_PRICE_LIMITS=false
TOSS_COLLECT_KR_CANDLES=false
TOSS_REQUESTS_JSON=[]
```

After the current-price search is stable, enable the EOD/detail timer for charts by setting `TOSS_COLLECT_KR_CANDLES=true` only in that EOD run.

