(() => {
  const HEALTH = { 0: 'ok', 1: 'stale', 2: 'fault' };

  const els = {
    strip: document.getElementById('strip'),
    tbody: document.getElementById('tbody'),
    conn: document.getElementById('conn'),
    hz: document.getElementById('hz'),
    blocked: document.getElementById('blocked'),
    ossd: document.getElementById('ossd'),
    host: document.getElementById('host'),
    port: document.getElementById('port'),
    connectBtn: document.getElementById('connect'),
  };

  els.host.value = location.hostname || 'localhost';

  let beamEls = [];
  let rowEls = [];
  let lastBeamCount = 0;
  let frameTimes = [];
  let ros = null;

  function rebuild(n) {
    els.strip.innerHTML = '';
    els.tbody.innerHTML = '';
    beamEls = [];
    rowEls = [];
    for (let i = 0; i < n; i++) {
      const cell = document.createElement('div');
      cell.className = 'beam';
      cell.textContent = i;
      els.strip.appendChild(cell);
      beamEls.push(cell);

      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${i}</td><td class="state state-clear">clear</td><td>ok</td>`;
      els.tbody.appendChild(tr);
      rowEls.push({ state: tr.children[1], health: tr.children[2] });
    }
    lastBeamCount = n;
  }

  function applyStatus(msg) {
    const n = msg.beam_count || msg.beams.length;
    if (n !== lastBeamCount) rebuild(n);

    for (const b of msg.beams) {
      const cell = beamEls[b.index];
      const row = rowEls[b.index];
      if (!cell) continue;
      cell.classList.remove('blocked', 'stale', 'fault');
      const healthName = HEALTH[b.health] || 'ok';
      if (b.health === 1) cell.classList.add('stale');
      else if (b.health === 2) cell.classList.add('fault');
      else if (b.blocked) cell.classList.add('blocked');

      row.state.textContent = b.blocked ? 'BLOCKED' : 'clear';
      row.state.className = 'state ' + (b.blocked ? 'state-blocked' : 'state-clear');
      row.health.textContent = healthName;
    }

    els.blocked.textContent = `${msg.blocked_count} / ${n} blocked`;
    els.blocked.className = 'pill ' + (msg.blocked_count > 0 ? 'bad' : 'good');

    const ossd = msg.ossd_a && msg.ossd_b;
    els.ossd.textContent = `OSSD ${ossd ? 'ON' : 'OFF'}${msg.lockout ? ' · LOCKOUT' : ''}${msg.muted ? ' · MUTED' : ''}`;
    els.ossd.className = 'pill ' + (ossd ? 'good' : 'bad');

    const now = performance.now();
    frameTimes.push(now);
    while (frameTimes.length > 0 && now - frameTimes[0] > 1000) frameTimes.shift();
    els.hz.textContent = `${frameTimes.length} Hz`;
  }

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

    const topic = new ROSLIB.Topic({
      ros,
      name: '/gl_r/status',
      messageType: 'keyence_glr_msgs/msg/CurtainStatus',
    });
    topic.subscribe(applyStatus);
  }

  els.connectBtn.addEventListener('click', connect);
  connect();
})();
