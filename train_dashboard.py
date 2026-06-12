#!/usr/bin/env python3
"""Local training dashboard — reads log files and serves status at http://localhost:7777

Usage:
    python3 train_dashboard.py

Requires: pip3 install psutil
Temperature: reads die-area temp from battery SMC sensor (Apple Silicon, no sudo needed).
"""
import collections, importlib, json, os, random, re, subprocess, sys, threading, time
from http.server import HTTPServer, BaseHTTPRequestHandler

import psutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(HERE, 'logs')

RUNS = [
    {
        'id': 'rhino',
        'name': 'Rhino',
        'emoji': '🦏',
        'log': os.path.join(LOGS, 'train_rhino.log'),
        'total_iters': 3000,
    },
    {
        'id': 'gorilla',
        'name': 'Orangutan2 (Gorilla)',
        'emoji': '🦧',
        'log': os.path.join(LOGS, 'train_orangutan_gorilla2.log'),
        'total_iters': 3000,
    },
    {
        'id': 'perdition2',
        'name': 'Perdition2',
        'emoji': '😭',
        'log': os.path.join(LOGS, 'train_perdition2_ppo.log'),
        'total_iters': 3000,
    },
]

_ITER_RE = re.compile(
    r'iter\s+(\d+)'
    r'.*?(?:rollout_win|rollout_loss)\s+([\d.]+)%'
    r'.*?greedy vs fleet: win\s+([\d.]+)%'
    r'.*?place\s+([\d.]+)'
    r'.*?\(best(?:\s+win)?\s+([\d.]+)%?\)'
    r'.*?([\d.]+)s/it'
    r'(.*)'
)

# ---- system monitor ----

_SYS_HISTORY = collections.deque(maxlen=150)  # ~5 min at 2s intervals
_SYS_LOCK    = threading.Lock()
_SYS_CACHE   = {}   # latest single snapshot

# Prime psutil counter so first real read is non-zero
psutil.cpu_percent(interval=None)


def _read_battery_temp():
    """Die-area temperature via Apple SMC battery sensor (no sudo, Apple Silicon)."""
    try:
        r = subprocess.run(
            ['ioreg', '-r', '-d', '1', '-c', 'AppleSmartBattery'],
            capture_output=True, text=True, timeout=2,
        )
        for line in r.stdout.split('\n'):
            m = re.search(r'"Temperature"\s*=\s*(\d+)', line)
            if m:
                return round(int(m.group(1)) / 100.0, 1)
    except Exception:
        pass
    return None


def _poll_system():
    """Background thread — samples CPU/mem/temp every 2 s."""
    psutil.cpu_percent(interval=None)  # throw away first delta
    while True:
        try:
            cpu    = psutil.cpu_percent(interval=None)
            percpu = psutil.cpu_percent(interval=None, percpu=True)
            mem    = psutil.virtual_memory()
            load   = psutil.getloadavg()
            temp   = _read_battery_temp()
            ts     = time.time()
            snap = {
                'ts':     ts,
                'cpu':    round(cpu, 1),
                'percpu': [round(v, 1) for v in percpu],
                'mem':    round(mem.percent, 1),
                'mem_mb': mem.used // 1024 // 1024,
                'mem_total_mb': mem.total // 1024 // 1024,
                'load':   [round(v, 2) for v in load],
                'temp':   temp,
            }
            with _SYS_LOCK:
                _SYS_HISTORY.append((ts, cpu, temp))
                _SYS_CACHE.update(snap)
        except Exception:
            pass
        time.sleep(2)


threading.Thread(target=_poll_system, daemon=True).start()


def get_system():
    with _SYS_LOCK:
        snap    = dict(_SYS_CACHE)
        history = list(_SYS_HISTORY)
    snap['history'] = history   # [(ts, cpu, temp), ...]
    return snap


# ---- training log parser ----

def _parse_log(path):
    if not os.path.exists(path):
        return {'status': 'no_log', 'iter': 0, 'total': 0}

    mtime = os.path.getmtime(path)
    last_iter = None
    baseline  = None
    history   = []

    try:
        with open(path, 'r') as f:
            lines = f.readlines()
    except OSError:
        return {'status': 'error', 'iter': 0, 'total': 0}

    for line in lines:
        line = line.strip()
        if line.startswith('baseline'):
            m = re.search(r'win\s+([\d.]+)%', line)
            if m:
                baseline = float(m.group(1))
        m = _ITER_RE.search(line)
        if m:
            it   = int(m.group(1))
            last_iter = {
                'iter':     it,
                'rollout':  float(m.group(2)),
                'win':      float(m.group(3)),
                'place':    float(m.group(4)),
                'best':     float(m.group(5)),
                'speed':    float(m.group(6)),
                'new_best': 'new best' in m.group(7),
            }
            if not history or it > history[-1][0]:
                history.append((it, last_iter['win']))

    verdict = None
    for line in reversed(lines):
        if 'VERDICT:' in line:
            verdict = line.strip().replace('VERDICT: ', '')
            break

    age = time.time() - mtime
    if last_iter is None:
        return {'status': 'starting', 'iter': 0, 'total': 0, 'baseline': baseline}

    if last_iter['iter'] >= 3000:
        status = 'done'
    elif age > 300:
        status = 'stalled'
    else:
        status = 'running'

    return {
        'status':   status,
        'iter':     last_iter['iter'],
        'total':    3000,
        'rollout':  last_iter['rollout'],
        'win':      last_iter['win'],
        'place':    last_iter['place'],
        'best':     last_iter['best'],
        'speed':    last_iter['speed'],
        'new_best': last_iter['new_best'],
        'baseline': baseline,
        'verdict':  verdict,
        'age_s':    int(age),
        'spark':    history[-30:],
    }


def get_status():
    out = []
    for run in RUNS:
        data = _parse_log(run['log'])
        data['id']    = run['id']
        data['name']  = run['name']
        data['emoji'] = run['emoji']
        out.append(data)
    return out


# ---- empirical battle eval ----

BATTLE_INTERVAL = 300        # seconds between eval runs
BATTLE_GAMES    = 500        # games per eval (fast enough ~60s, low CPU impact)
_BATTLE_HISTORY = collections.deque(maxlen=72)   # ~6 hrs at 5-min intervals
_BATTLE_LOCK    = threading.Lock()
_BATTLE_RUNNING = threading.Event()


CONTESTANTS = [
    {'id': 'rhino',      'name': 'Rhino',      'emoji': '🦏', 'color': '#8b5cf6',
     'module': 'agents.rhino_agent',      'cls': 'RhinoAgent'},
    {'id': 'orangutan2', 'name': 'Orangutan2', 'emoji': '🦧', 'color': '#f97316',
     'module': 'agents.orangutan2_agent', 'cls': 'Orangutan2Agent'},
    {'id': 'orangutan',  'name': 'Orangutan',  'emoji': '🦍', 'color': '#a3e635',
     'module': 'agents.orangutan_agent',  'cls': 'OrangutanAgent'},
]
FILLERS = [
    ('agents.coyote_agent',        'CoyoteAgent'),
    ('agents.survival_agent_v2',   'SurvivalAgentV2'),
]


def _fresh_class(module_name, class_name):
    """Import (or reload) a module and return the named class with fresh weights."""
    mod = importlib.import_module(module_name)
    importlib.reload(mod)
    return getattr(mod, class_name)


def _run_battle():
    """Run BATTLE_GAMES games, return {contestant_id: win_rate}."""
    try:
        from game.engine import GameEngine
        contestants = [(c, _fresh_class(c['module'], c['cls'])) for c in CONTESTANTS]
        fillers     = [_fresh_class(m, cn) for m, cn in FILLERS]
        # 5-player game: 3 contestants + 2 fillers
        rng = random.Random(int(time.time()))
        wins = {c['id']: 0 for c in CONTESTANTS}
        played = 0
        for _ in range(BATTLE_GAMES):
            agents = (
                [cls(name=c['id']) for c, cls in contestants] +
                [fc(name=f'filler{i}') for i, fc in enumerate(fillers)]
            )
            order = list(range(5)); rng.shuffle(order)
            seats = {order[i]: i for i in range(5)}   # original_idx -> seat
            try:
                r = GameEngine([agents[order[i]] for i in range(5)]).play_game(5)
            except Exception:
                continue
            if r['winner'] < 0:
                continue
            played += 1
            for idx, (c, _) in enumerate(contestants):
                if r['winner'] == seats[idx]:
                    wins[c['id']] += 1
        if played == 0:
            return None
        return {cid: round(w / played * 100, 2) for cid, w in wins.items()}, played
    except Exception as e:
        print(f'[battle] error: {e}', flush=True)
        return None


def _battle_loop():
    """Background thread: runs eval every BATTLE_INTERVAL seconds."""
    time.sleep(10)   # let dashboard start up first
    while True:
        _BATTLE_RUNNING.set()
        t0 = time.time()
        result = _run_battle()
        elapsed = time.time() - t0
        _BATTLE_RUNNING.clear()
        if result is not None:
            rates, played = result
            snap = {'ts': time.time(), 'rates': rates, 'games': played, 'elapsed': round(elapsed)}
            with _BATTLE_LOCK:
                _BATTLE_HISTORY.append(snap)
            names = ', '.join(f'{k}={v:.1f}%' for k, v in rates.items())
            print(f'[battle] {played} games in {elapsed:.0f}s — {names}', flush=True)
        # sleep until next interval, minus time already spent
        sleep_for = max(30, BATTLE_INTERVAL - elapsed)
        time.sleep(sleep_for)


threading.Thread(target=_battle_loop, daemon=True).start()


def get_battle():
    with _BATTLE_LOCK:
        history = list(_BATTLE_HISTORY)
    return {
        'history':    history,
        'running':    _BATTLE_RUNNING.is_set(),
        'interval':   BATTLE_INTERVAL,
        'games':      BATTLE_GAMES,
        'contestants': CONTESTANTS,
    }


# ---- HTML ----

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Training Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0f1117; color: #e2e8f0;
    font-family: 'SF Mono', 'Fira Code', monospace;
    padding: 24px;
  }
  h1 { font-size: 1.1rem; color: #94a3b8; margin-bottom: 6px; letter-spacing: 0.05em; }
  h2 { font-size: 0.8rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em;
       margin: 20px 0 10px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }

  /* ---- training cards ---- */
  .card {
    background: #1e2333; border: 1px solid #2d3548; border-radius: 10px;
    padding: 18px; overflow: hidden;
  }
  .card.running { border-color: #3b82f6; }
  .card.done    { border-color: #22c55e; }
  .card.stalled { border-color: #f59e0b; }
  .card.no_log  { border-color: #374151; }
  .card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
  .card-title  { font-size: 1rem; font-weight: 600; color: #f1f5f9; }
  .badge {
    font-size: 0.65rem; padding: 2px 8px; border-radius: 999px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em;
  }
  .badge.running  { background: #1d4ed8; color: #bfdbfe; }
  .badge.done     { background: #166534; color: #bbf7d0; }
  .badge.stalled  { background: #92400e; color: #fde68a; }
  .badge.starting, .badge.no_log { background: #374151; color: #9ca3af; }
  .stat-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
  .stat {
    background: #141824; border-radius: 6px; padding: 6px 10px;
    display: flex; flex-direction: column; align-items: center; flex: 1; min-width: 60px;
  }
  .stat-val { font-size: 1.05rem; font-weight: 700; color: #e2e8f0; }
  .stat-lbl { font-size: 0.6rem; color: #64748b; margin-top: 2px;
              text-transform: uppercase; letter-spacing: 0.06em; }
  .stat-val.green { color: #4ade80; }
  .stat-val.blue  { color: #60a5fa; }
  .stat-val.amber { color: #fbbf24; }
  .stat-val.red   { color: #f87171; }
  .progress-wrap { background: #141824; border-radius: 4px; height: 6px; overflow: hidden; margin-bottom: 10px; }
  .progress-bar  { height: 100%; background: #3b82f6; border-radius: 4px; transition: width 0.4s; }
  .card.done .progress-bar { background: #22c55e; }
  .spark-wrap { height: 40px; margin-bottom: 8px; }
  svg.spark { width: 100%; height: 100%; }
  .footer { font-size: 0.62rem; color: #4b5563; display: flex; justify-content: space-between; }
  .verdict { font-size: 0.75rem; margin-top: 6px; padding: 4px 8px;
             border-radius: 4px; background: #141824; color: #94a3b8; }
  .verdict.ROLLBACK { color: #f87171; }
  .verdict.DEPLOY   { color: #4ade80; }

  /* ---- system card ---- */
  #sys-card {
    background: #1e2333; border: 1px solid #6d28d9; border-radius: 10px;
    padding: 18px; margin-bottom: 0;
  }
  .sys-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  .sys-big {
    background: #141824; border-radius: 6px; padding: 8px 14px;
    display: flex; flex-direction: column; align-items: center; flex: 1; min-width: 80px;
  }
  .sys-big .val { font-size: 1.4rem; font-weight: 700; }
  .sys-big .lbl { font-size: 0.58rem; color: #64748b; text-transform: uppercase;
                  letter-spacing: 0.06em; margin-top: 2px; }
  .cores-row { display: flex; gap: 3px; align-items: flex-end; margin-bottom: 12px; }
  .core-bar-wrap { display: flex; flex-direction: column; align-items: center; flex: 1; }
  .core-bar-bg { width: 100%; background: #141824; border-radius: 2px; height: 32px;
                 display: flex; align-items: flex-end; }
  .core-bar { width: 100%; border-radius: 2px; transition: height 0.4s; }
  .core-lbl { font-size: 0.45rem; color: #4b5563; margin-top: 2px; }
  .chart-row { display: flex; gap: 12px; margin-bottom: 4px; }
  .chart-wrap { flex: 1; }
  .chart-title { font-size: 0.6rem; color: #64748b; text-transform: uppercase;
                 letter-spacing: 0.06em; margin-bottom: 4px; }
  svg.timechart { width: 100%; height: 60px; display: block; }
  #last-update { font-size: 0.65rem; color: #4b5563; margin-bottom: 16px; }
</style>
</head>
<body>
<h1>🧠 Training Dashboard</h1>
<div id="last-update">—</div>

<h2>⚔️ Battle</h2>
<div id="battle-card" style="background:#1e2333;border:1px solid #7c3aed;border-radius:10px;padding:18px;margin-bottom:0">
  <div style="color:#4b5563;font-size:0.75rem">First eval in ~10s…</div>
</div>

<h2>⚙️ System</h2>
<div id="sys-card"><div style="color:#4b5563;font-size:0.75rem">Loading…</div></div>

<h2>🏋️ Training Runs</h2>
<div class="grid" id="grid"></div>

<script>
/* ---- sparkline helpers ---- */
function polyline(pts, W, H, pad, minY, maxY) {
  const range = maxY - minY || 1;
  const xs = pts.map((_, i) => pad + (i / Math.max(pts.length - 1, 1)) * (W - 2*pad));
  const ys = pts.map(v => H - pad - ((v - minY) / range) * (H - 2*pad));
  return {
    pts: xs.map((x,i) => `${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' '),
    fill: `${xs[0].toFixed(1)},${H} ` + xs.map((x,i) => `${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ') + ` ${xs[xs.length-1].toFixed(1)},${H}`,
  };
}

function trainSparkSVG(spark) {
  if (!spark || spark.length < 2) return '';
  const vals = spark.map(([,v]) => v);
  const { pts, fill } = polyline(vals, 300, 40, 2, 0, Math.max(...vals) * 1.1);
  return `<svg class="spark" viewBox="0 0 300 40" preserveAspectRatio="none">
    <polygon points="${fill}" fill="#3b82f620"/>
    <polyline points="${pts}" fill="none" stroke="#3b82f6" stroke-width="1.5"/>
  </svg>`;
}

function timeChartSVG(history, key, color, minY, maxY, unitSuffix='') {
  if (!history || history.length < 2) return `<svg class="timechart" viewBox="0 0 300 60"><text x="10" y="30" fill="#4b5563" font-size="10">no data</text></svg>`;
  const vals = history.map(h => h[key] ?? null).filter(v => v !== null);
  if (vals.length < 2) return `<svg class="timechart" viewBox="0 0 300 60"><text x="10" y="30" fill="#4b5563" font-size="10">no data</text></svg>`;
  const hi = maxY ?? Math.max(...vals);
  const lo = minY ?? Math.min(...vals);
  const { pts, fill } = polyline(vals, 300, 60, 2, lo, hi);
  const cur = vals[vals.length - 1];
  return `<svg class="timechart" viewBox="0 0 300 60" preserveAspectRatio="none">
    <polygon points="${fill}" fill="${color}18"/>
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5"/>
    <text x="295" y="10" text-anchor="end" fill="${color}" font-size="9" font-family="monospace">${cur.toFixed(1)}${unitSuffix}</text>
  </svg>`;
}

/* ---- system card ---- */
function renderSystem(s) {
  if (!s || !s.cpu) return;
  const tempColor = !s.temp ? '#4b5563'
    : s.temp > 80 ? '#f87171' : s.temp > 65 ? '#fbbf24' : '#4ade80';
  const cpuColor  = s.cpu > 90 ? '#f87171' : s.cpu > 70 ? '#fbbf24' : '#60a5fa';
  const memColor  = s.mem > 90 ? '#f87171' : s.mem > 75 ? '#fbbf24' : '#a78bfa';

  const tempDisplay = s.temp != null ? `${s.temp.toFixed(1)}°C` : 'N/A';
  const tempNote    = s.temp != null ? '' : ' title="Apple Silicon: die-area temp via battery SMC"';

  // per-core bars
  const cores = (s.percpu || []).map((v, i) => {
    const h = Math.max(2, Math.round(v / 100 * 32));
    const c = v > 90 ? '#f87171' : v > 70 ? '#fbbf24' : '#60a5fa';
    return `<div class="core-bar-wrap">
      <div class="core-bar-bg"><div class="core-bar" style="height:${h}px;background:${c}"></div></div>
      <div class="core-lbl">C${i}</div>
    </div>`;
  }).join('');

  // time-series charts
  const hist = s.history || [];
  const cpuChart  = timeChartSVG(hist, 1, '#60a5fa', 0, 100, '%');
  const tempChart = s.temp != null
    ? timeChartSVG(hist.filter(h=>h[2]!=null), 2, '#4ade80', 20, 110, '°')
    : `<svg class="timechart" viewBox="0 0 300 60"><text x="10" y="30" fill="#4b5563" font-size="10">temp unavailable</text></svg>`;

  document.getElementById('sys-card').innerHTML = `
    <div class="card-header" style="margin-bottom:10px">
      <span class="card-title">💻 ${s.chip || 'Mac'}</span>
      <span style="font-size:0.65rem;color:#64748b">load ${(s.load||[]).map(v=>v.toFixed(2)).join(' / ')}</span>
    </div>
    <div class="sys-row">
      <div class="sys-big"><div class="val" style="color:${cpuColor}">${s.cpu.toFixed(1)}%</div><div class="lbl">CPU</div></div>
      <div class="sys-big"><div class="val" style="color:${memColor}">${s.mem.toFixed(1)}%</div><div class="lbl">RAM ${s.mem_mb}MB</div></div>
      <div class="sys-big"${tempNote}><div class="val" style="color:${tempColor}">${tempDisplay}</div><div class="lbl">Die temp</div></div>
    </div>
    <div class="cores-row">${cores}</div>
    <div class="chart-row">
      <div class="chart-wrap"><div class="chart-title">CPU % — 5 min</div>${cpuChart}</div>
      <div class="chart-wrap"><div class="chart-title">Temp °C — 5 min</div>${tempChart}</div>
    </div>`;
}

/* ---- training cards ---- */
function renderTraining(runs) {
  document.getElementById('grid').innerHTML = runs.map(r => {
    const pct = r.total > 0 ? (r.iter / r.total * 100).toFixed(1) : 0;
    const cls  = r.status || 'no_log';
    const badge = cls.charAt(0).toUpperCase() + cls.slice(1);

    const stats = r.win !== undefined ? `
      <div class="stat-row">
        <div class="stat"><div class="stat-val blue">${r.win.toFixed(2)}%</div><div class="stat-lbl">win rate</div></div>
        <div class="stat"><div class="stat-val green">${r.best.toFixed(2)}%</div><div class="stat-lbl">best</div></div>
        <div class="stat"><div class="stat-val">${r.place ? r.place.toFixed(3) : '—'}</div><div class="stat-lbl">avg place</div></div>
        <div class="stat"><div class="stat-val amber">${r.rollout ? r.rollout.toFixed(1)+'%' : '—'}</div><div class="stat-lbl">rollout</div></div>
      </div>` : '';

    const spark  = r.spark && r.spark.length > 1 ? `<div class="spark-wrap">${trainSparkSVG(r.spark)}</div>` : '';
    const verdict = r.verdict ? `<div class="verdict ${r.verdict}">${r.verdict}</div>` : '';
    const notes = [
      r.baseline != null ? `baseline ${r.baseline.toFixed(1)}%` : '',
      r.speed ? `${r.speed.toFixed(1)}s/it` : '',
      r.status === 'running' ? `updated ${r.age_s}s ago` : '',
    ].filter(Boolean).join(' · ');

    return `<div class="card ${cls}">
      <div class="card-header">
        <span class="card-title">${r.emoji} ${r.name}</span>
        <span class="badge ${cls}">${badge}</span>
      </div>
      ${stats}${spark}
      <div class="progress-wrap"><div class="progress-bar" style="width:${pct}%"></div></div>
      ${verdict}
      <div class="footer">
        <span>iter ${r.iter} / ${r.total} (${pct}%)</span>
        <span>${notes}</span>
      </div>
    </div>`;
  }).join('');
}

/* ---- battle card ---- */
function renderBattle(b) {
  const card = document.getElementById('battle-card');
  if (!b || !b.contestants) return;

  const history   = b.history || [];
  const running   = b.running;
  const latest    = history[history.length - 1] || null;
  const contestants = b.contestants;

  // current WR pills
  const pills = contestants.map(c => {
    const wr = latest ? (latest.rates[c.id] ?? '—') : '—';
    const wrStr = typeof wr === 'number' ? wr.toFixed(1) + '%' : wr;
    return `<div class="stat" style="border-left:3px solid ${c.color}">
      <div class="stat-val" style="color:${c.color}">${wrStr}</div>
      <div class="stat-lbl">${c.emoji} ${c.name}</div>
    </div>`;
  }).join('');

  // multi-line time-series SVG
  let chartHtml = '<div style="color:#4b5563;font-size:0.7rem;padding:8px 0">No data yet — first eval running…</div>';
  if (history.length >= 2) {
    const W = 560, H = 80, pad = 4;
    const n = history.length;
    const allWRs = history.flatMap(h => contestants.map(c => h.rates[c.id] ?? 0));
    const lo = 0, hi = Math.max(35, ...allWRs) * 1.08;

    const lines = contestants.map(c => {
      const vals = history.map(h => h.rates[c.id] ?? 0);
      const xs   = vals.map((_, i) => pad + (i / Math.max(n - 1, 1)) * (W - 2*pad));
      const ys   = vals.map(v => H - pad - ((v - lo) / (hi - lo)) * (H - 2*pad));
      const pts  = xs.map((x, i) => `${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
      const last = vals[vals.length - 1];
      return `<polyline points="${pts}" fill="none" stroke="${c.color}" stroke-width="2" stroke-linejoin="round"/>
              <text x="${(W-pad).toFixed(0)}" y="${(ys[ys.length-1]-3).toFixed(0)}" text-anchor="end"
                    fill="${c.color}" font-size="8" font-family="monospace">${last.toFixed(1)}%</text>`;
    }).join('');

    // y-axis labels
    const yLabels = [0, Math.round(hi * 0.5), Math.round(hi)].map(v => {
      const y = H - pad - ((v - lo) / (hi - lo)) * (H - 2*pad);
      return `<text x="0" y="${y.toFixed(0)}" fill="#374151" font-size="7" font-family="monospace">${v}%</text>`;
    }).join('');

    // x-axis time labels
    const xLabels = [0, Math.floor((n-1)/2), n-1].map(i => {
      if (!history[i]) return '';
      const x = pad + (i / Math.max(n-1,1)) * (W - 2*pad);
      const t = new Date(history[i].ts * 1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
      return `<text x="${x.toFixed(0)}" y="${H+12}" text-anchor="middle" fill="#374151" font-size="7" font-family="monospace">${t}</text>`;
    }).join('');

    chartHtml = `<svg viewBox="0 0 ${W} ${H+16}" style="width:100%;height:90px;display:block;overflow:visible">
      ${yLabels}${lines}${xLabels}
    </svg>`;
  }

  const gameNote = latest
    ? `${latest.games} games · ${latest.elapsed}s · ${new Date(latest.ts*1000).toLocaleTimeString()}`
    : '';
  const statusDot = running
    ? `<span style="color:#fbbf24;font-size:0.65rem">⏳ running eval…</span>`
    : `<span style="color:#4b5563;font-size:0.65rem">next in ~${b.interval/60|0}min · ${b.games} games</span>`;

  card.innerHTML = `
    <div class="card-header" style="margin-bottom:10px">
      <span class="card-title">⚔️ Rhino vs Orangutan2 vs Orangutan</span>
      ${statusDot}
    </div>
    <div class="stat-row">${pills}</div>
    ${chartHtml}
    <div style="font-size:0.6rem;color:#4b5563;margin-top:4px;text-align:right">${gameNote}</div>`;
}

/* ---- polling ---- */
async function poll() {
  const [trainRes, sysRes, battleRes] = await Promise.all([
    fetch('/api/status').then(r => r.json()).catch(() => null),
    fetch('/api/system').then(r => r.json()).catch(() => null),
    fetch('/api/battle').then(r => r.json()).catch(() => null),
  ]);
  if (trainRes)  renderTraining(trainRes);
  if (sysRes)    renderSystem(sysRes);
  if (battleRes) renderBattle(battleRes);
  document.getElementById('last-update').textContent =
    'Last updated: ' + new Date().toLocaleTimeString();
}

poll();
setInterval(poll, 2000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == '/api/status':
            body = json.dumps(get_status()).encode()
        elif self.path == '/api/system':
            body = json.dumps(get_system()).encode()
        elif self.path == '/api/battle':
            body = json.dumps(get_battle()).encode()
        elif self.path in ('/', '/index.html'):
            body = HTML.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
            return
        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    import socket
    # detect chip for display
    try:
        chip = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'],
                              capture_output=True, text=True).stdout.strip()
        if not chip:
            chip = subprocess.run(['sysctl', '-n', 'hw.model'],
                                  capture_output=True, text=True).stdout.strip()
    except Exception:
        chip = 'Mac'
    _SYS_CACHE['chip'] = chip

    port = 7777
    server = HTTPServer(('127.0.0.1', port), Handler)
    print(f'Training dashboard running at http://localhost:{port}')
    server.serve_forever()
