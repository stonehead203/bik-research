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
TOSS_REQUESTS_JSON=[]
```

기존의 `RENDER_INGEST_URL`, `INGEST_SECRET`, `TOSSINVEST_BASE_URL`, `TOSSINVEST_API_KEY`, `TOSSINVEST_SECRET_KEY`는 유지해야 합니다.

테스트:

```bash
sudo bash -c 'set -a; . /etc/bik-toss-collector.env; set +a; cd /home/ubuntu/bik-research/outputs; .venv/bin/python toss_collector.py --dry-run'
```

정상이라면 `kr_universe`, `kr_prices_001` 같은 항목이 보입니다.
