(() => {
  let state, cursor, timer, busy = false, paused = false, pending = [];
  const channel = { onmessage: null, postMessage };
  window.hoduRoom = channel;

  function schedule(delay) {
    clearTimeout(timer);
    if (!paused) timer = setTimeout(sync, delay);
  }
  function postMessage({ kind, message, ...snapshot }) {
    state = snapshot;
    if (kind === 'leave') {
      paused = true;
      clearTimeout(timer);
      fetch('/api/hodutemple/room', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: state.id, leave: true }), keepalive: true
      }).catch(() => {});
      return;
    }
    if (kind === 'speech' || kind === 'pray') {
      pending.push({ id: crypto.randomUUID(), kind, message, expires: Date.now() + 4000 });
      pending = pending.slice(-4);
    }
    if (kind === 'hello') {
      paused = false;
      if (!busy) schedule(0);
    }
  }
  async function sync() {
    if (paused || busy || !state) return;
    busy = true;
    let delay = document.hidden ? 4500 : 650;
    const events = pending.filter(event => event.expires > Date.now());
    pending = events;
    try {
      const response = await fetch('/api/hodutemple/room', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: state.id, state, cursor, events }),
        signal: AbortSignal.timeout(5000)
      });
      if (paused) return;
      if (response.status === 401) {
        paused = true;
        location.replace('/hodutemple');
        return;
      }
      if (response.status === 409) {
        channel.onstatus?.('방이 가득 찼어요');
        delay = 3500;
        return;
      }
      if (!response.ok) throw new Error('Room unavailable');
      const data = await response.json();
      cursor = data.cursor;
      pending = pending.filter(event => !events.includes(event));
      for (const peer of data.peers) channel.onmessage?.({ data: peer });
      for (const event of data.events) {
        const peer = data.peers.find(item => item.id === event.id);
        if (peer) channel.onmessage?.({ data: { ...peer, ...event } });
      }
      channel.onsnapshot?.(new Set(data.peers.map(peer => peer.id)), data.nickname);
      channel.onstatus?.('');
    } catch {
      channel.onstatus?.('방에 다시 연결 중');
      delay = 2500;
    } finally {
      busy = false;
      schedule(delay);
    }
  }
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && !busy && state) schedule(0);
  });
})();
