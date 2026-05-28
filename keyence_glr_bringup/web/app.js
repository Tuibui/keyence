(() => {
  const HEALTH = { 0: 'ok', 1: 'stale', 2: 'fault' };

  const els = {
    strip: document.getElementById('strip'),
    fields: document.getElementById('fields'),
    hex: document.getElementById('hex'),
    bin: document.getElementById('bin'),
    json: document.getElementById('json'),
    conn: document.getElementById('conn'),
    hz: document.getElementById('hz'),
    age: document.getElementById('age'),
    blocked: document.getElementById('blocked'),
    host: document.getElementById('host'),
    port: document.getElementById('port'),
    connectBtn: document.getElementById('connect'),
  };

  els.host.value = location.hostname || 'localhost';

  let beamEls = [];
  let lastBeamCount = 0;
  let frameTimes = [];
  let lastMsgAt = 0;
  let lastJsonAt = 0;
  let ros = null;

  // ---- helpers -----------------------------------------------------------
  const bit = (b) => (b ? '1' : '0');

  function rebuildStrip(n) {
    els.strip.innerHTML = '';
    beamEls = [];
    for (let i = 0; i < n; i++) {
      const cell = document.createElement('div');
      cell.className = 'beam';
      cell.innerHTML = `<small>${i}</small><b>0</b>`;
      els.strip.appendChild(cell);
      beamEls.push(cell.querySelector('b'));
      beamEls[i].parentEl = cell;
    }
    lastBeamCount = n;
  }

  function row(dl, key, val, cls) {
    const dt = document.createElement('dt');
    dt.textContent = key;
    const dd = document.createElement('dd');
    dd.textContent = val;
    if (cls) dd.className = cls;
    dl.appendChild(dt);
    dl.appendChild(dd);
  }

  function boolCls(v) { return v ? 'on' : 'off'; }

  // reconstruct the beam bitmap into bytes, LSB = beam 0
  function bitmapBytes(beams, n) {
    const nbytes = Math.ceil(n / 8);
    const bytes = new Uint8Array(nbytes);
    for (const b of beams) {
      if (b.blocked && b.index < n) bytes[b.index >> 3] |= (1 << (b.index & 7));
    }
    return bytes;
  }

  // ---- render ------------------------------------------------------------
  function applyStatus(msg) {
    const now = performance.now();
    lastMsgAt = now;
    const n = msg.beam_count || msg.beams.length;
    if (n !== lastBeamCount) rebuildStrip(n);

    for (const b of msg.beams) {
      const el = beamEls[b.index];
      if (!el) continue;
      const cell = el.parentEl;
      el.textContent = bit(b.blocked);
      cell.className = 'beam';
      if (b.health === 1) cell.classList.add('stale');
      else if (b.health === 2) cell.classList.add('fault');
      else if (b.blocked) cell.classList.add('blocked');
    }

    // fields panel
    const dl = els.fields;
    dl.innerHTML = '';
    const st = msg.header && msg.header.stamp ? msg.header.stamp : { sec: 0, nanosec: 0 };
    row(dl, 'stamp', `${st.sec}.${String(st.nanosec).padStart(9, '0')}`);
    row(dl, 'frame_id', (msg.header && msg.header.frame_id) || '');
    row(dl, 'beam_count', n);
    row(dl, 'ossd_a', bit(msg.ossd_a), boolCls(msg.ossd_a));
    row(dl, 'ossd_b', bit(msg.ossd_b), boolCls(msg.ossd_b));
    row(dl, 'lockout', bit(msg.lockout), boolCls(!msg.lockout));
    row(dl, 'muted', bit(msg.muted), boolCls(!msg.muted));
    row(dl, 'any_blocked', bit(msg.any_blocked), boolCls(!msg.any_blocked));
    row(dl, 'blocked_count', msg.blocked_count);

    // bitmap bytes
    const bytes = bitmapBytes(msg.beams, n);
    els.hex.textContent = Array.from(bytes, (x) => x.toString(16).padStart(2, '0')).join(' ');
    els.bin.textContent = Array.from(bytes, (x) => x.toString(2).padStart(8, '0')).join(' ');

    // header pills
    els.blocked.textContent = `${msg.blocked_count}/${n} blocked`;
    els.blocked.className = 'pill ' + (msg.blocked_count > 0 ? 'bad' : 'good');

    frameTimes.push(now);
    while (frameTimes.length && now - frameTimes[0] > 1000) frameTimes.shift();
    els.hz.textContent = `${frameTimes.length} Hz`;

    // raw json (throttled — the beams array is large)
    if (now - lastJsonAt > 250) {
      lastJsonAt = now;
      els.json.textContent = JSON.stringify(msg, null, 2);
    }
  }

  // age ticker — flags a stalled stream even when no messages arrive
  setInterval(() => {
    if (!lastMsgAt) return;
    const ms = performance.now() - lastMsgAt;
    els.age.textContent = `age ${ms < 1000 ? Math.round(ms) + ' ms' : (ms / 1000).toFixed(1) + ' s'}`;
    els.age.className = 'pill ' + (ms > 500 ? 'bad' : 'good');
  }, 100);

  // ---- connection --------------------------------------------------------
  function connect() {
    if (ros) { try { ros.close(); } catch (_) {} }
    const url = `ws://${els.host.value}:${els.port.value}`;
    ros = new ROSLIB.Ros({ url });
    ros.on('connection', () => {
      els.conn.textContent = `connected · ${url}`;
      els.conn.className = 'pill good';
    });
    ros.on('error', () => {
      els.conn.textContent = 'error';
      els.conn.className = 'pill bad';
    });
    ros.on('close', () => {
      els.conn.textContent = 'disconnected';
      els.conn.className = 'pill bad';
    });

    new ROSLIB.Topic({
      ros,
      name: '/gl_r/status',
      messageType: 'keyence_glr_msgs/msg/CurtainStatus',
    }).subscribe(applyStatus);
  }

  els.connectBtn.addEventListener('click', connect);
  connect();
})();
