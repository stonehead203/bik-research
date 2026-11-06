const el = id => document.getElementById(id);
const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const seoulDay = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' });
const exchange = 'https://api.exchange.coinbase.com/products/BTC-USD';
const counterKey = 'moon-court-prayer-v1';
const buttons = [el('up'), el('down')];
let memory;
let series = [];
let candleTime = 0;
let quoteTime = 0;

function storeRead() {
  try {
    return JSON.parse(localStorage.getItem(counterKey)) ?? memory;
  } catch {
    return memory;
  }
}

function today() {
  const date = seoulDay.format(new Date());
  const saved = storeRead();
  return saved?.date === date ? saved : { date, up: 0, down: 0 };
}

function renderCounts() {
  const count = today();
  el('upCount').textContent = count.up;
  el('downCount').textContent = count.down;
}

let announcementTimer;
async function pray(direction) {
  buttons.forEach(button => { button.disabled = true; });
  try {
    function increment() {
      const record = today();
      record[direction] += 1;
      memory = record;
      try { localStorage.setItem(counterKey, JSON.stringify(record)); } catch {}
    }
    if (navigator.locks) await navigator.locks.request(counterKey, increment);
    else increment();
    renderCounts();
    window.dispatchEvent(new CustomEvent('moon:pray', { detail: direction }));
    el('announcement').textContent = direction === 'up' ? '상승을 바라며 절을 올렸어요.' : '하락을 바라며 절을 올렸어요.';
    clearTimeout(announcementTimer);
    announcementTimer = setTimeout(() => { el('announcement').textContent = ''; }, 2300);
  } finally {
    setTimeout(() => buttons.forEach(button => { button.disabled = false; }), 1100);
  }
}
buttons[0].addEventListener('click', () => pray('up'));
buttons[1].addEventListener('click', () => pray('down'));
window.addEventListener('storage', renderCounts);
document.addEventListener('visibilitychange', renderCounts);
setInterval(renderCounts, 60000);
renderCounts();
el('help').addEventListener('click', () => el('guide').showModal());

async function request(path) {
  const response = await fetch(exchange + path, { signal: AbortSignal.timeout(8500) });
  if (!response.ok) throw new Error('Coinbase HTTP ' + response.status);
  return response.json();
}

function display(price, state, stamp) {
  const prices = series.length ? [...series, price] : [];
  const priceText = money.format(price);
  window.moonQuote = { price, priceText, stamp, series: prices, label: state === '시세 연결' ? 'COINBASE EXCHANGE  /  BTC-USD' : 'COINBASE EXCHANGE  /  STALE QUOTE' };
  window.dispatchEvent(new CustomEvent('moon:quote', { detail: window.moonQuote }));
}

async function refresh() {
  try {
    const end = Math.floor(Date.now() / 900000) * 900000;
    const span = '&start=' + new Date(end - 86400000).toISOString() + '&end=' + new Date(end).toISOString();
    const [ticker, candles] = await Promise.allSettled([
      request('/ticker'),
      Date.now() - candleTime > 900000 ? request('/candles?granularity=900' + span) : Promise.resolve(null)
    ]);
    if (candles.status === 'fulfilled' && Array.isArray(candles.value)) {
      const next = candles.value.filter(row => Number.isFinite(row?.[4]) && row[4] > 0 && row[0] * 1000 >= end - 86400000 && row[0] * 1000 < end)
        .sort((a, b) => a[0] - b[0]).map(row => row[4]);
      if (next.length > 1) {
        series = next;
        candleTime = Date.now();
      }
    }
    const price = Number(ticker.value?.price);
    const stamp = Date.parse(ticker.value?.time);
    if (!(price > 0) || !Number.isFinite(stamp)) {
      if (window.moonQuote) display(window.moonQuote.price, '갱신 지연', quoteTime);
      else window.dispatchEvent(new CustomEvent('moon:quote', { detail: { label: 'QUOTE TEMPORARILY UNAVAILABLE' } }));
      return;
    }
    quoteTime = stamp;
    display(price, Date.now() - stamp < 90000 ? '시세 연결' : '갱신 지연', stamp);
  } finally {
    setTimeout(refresh, 20000);
  }
}
refresh();
