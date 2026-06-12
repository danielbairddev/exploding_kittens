#!/usr/bin/env python3
"""Local training dashboard — reads log files and serves status at http://localhost:7777

Usage:
    python3 train_dashboard.py
"""
import json, os, re, time
from http.server import HTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(HERE, 'logs')

RUNS = [
    {
        'id': 'rhino',
        'name': 'Rhino',
        'emoji': '🦏',
        'log': os.path.join(LOGS, 'train_rhino.log'),
        'mode': 'win',       # greedy vs fleet metric to show
        'total_iters': 3000,
    },
    {
        'id': 'gorilla',
        'name': 'Orangutan2 (Gorilla)',
        'emoji': '🦧',
        'log': os.path.join(LOGS, 'train_orangutan_gorilla2.log'),
        'mode': 'win',
        'total_iters': 3000,
    },
    {
        'id': 'perdition2',
        'name': 'Perdition2',
        'emoji': '😭',
        'log': os.path.join(LOGS, 'train_perdition2_ppo.log'),
        'mode': 'win',
        'total_iters': 3000,
    },
]

# Matches both rhino/gorilla and perdition2 log line formats
_ITER_RE = re.compile(
    r'iter\s+(\d+)'
    r'.*?(?:rollout_win|rollout_loss)\s+([\d.]+)%'
    r'.*?greedy vs fleet: win\s+([\d.]+)%'
    r'.*?place\s+([\d.]+)'
    r'.*?\(best(?:\s+win)?\s+([\d.]+)%?\)'
    r'.*?([\d.]+)s/it'
    r'(.*)'
)


def _parse_log(path):
    if not os.path.exists(path):
        return {'status': 'no_log', 'iter': 0, 'total': 0}

    mtime = os.path.getmtime(path)
    last_iter = None
    baseline = None
    history = []  # list of (iter, win) for sparkline

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
            it = int(m.group(1))
            rollout = float(m.group(2))
            win = float(m.group(3))
            place = float(m.group(4))
            best = float(m.group(5))
            speed = float(m.group(6))
            tag = m.group(7).strip()
            is_new_best = 'new best' in tag
            last_iter = {
                'iter': it, 'rollout': rollout, 'win': win,
                'place': place, 'best': best, 'speed': speed,
                'new_best': is_new_best,
            }
            if len(history) == 0 or it > history[-1][0]:
                history.append((it, win))

    # Check for verdict lines (perdition2 evaluation)
    verdict = None
    for line in reversed(lines):
        if 'VERDICT:' in line:
            verdict = line.strip().replace('VERDICT: ', '')
            break

    age = time.time() - mtime
    if last_iter is None:
        return {'status': 'starting', 'iter': 0, 'total': 0, 'baseline': baseline}

    # Determine run status
    if last_iter['iter'] >= 3000:
        status = 'done'
    elif age > 300:
        status = 'stalled'
    else:
        status = 'running'

    # Build sparse sparkline (last 30 eval points)
    spark = history[-30:]

    return {
        'status': status,
        'iter': last_iter['iter'],
        'total': 3000,
        'rollout': last_iter['rollout'],
        'win': last_iter['win'],
        'place': last_iter['place'],
        'best': last_iter['best'],
        'speed': last_iter['speed'],
        'new_best': last_iter['new_best'],
        'baseline': baseline,
        'verdict': verdict,
        'age_s': int(age),
        'spark': spark,
    }


def get_status():
    out = []
    for run in RUNS:
        data = _parse_log(run['log'])
        data['id'] = run['id']
        data['name'] = run['name']
        data['emoji'] = run['emoji']
        out.append(data)
    return out


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
  h1 { font-size: 1.1rem; color: #94a3b8; margin-bottom: 20px; letter-spacing: 0.05em; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }
  .card {
    background: #1e2333; border: 1px solid #2d3548; border-radius: 10px;
    padding: 18px; position: relative; overflow: hidden;
  }
  .card.running  { border-color: #3b82f6; }
  .card.done     { border-color: #22c55e; }
  .card.stalled  { border-color: #f59e0b; }
  .card.no_log   { border-color: #374151; }
  .card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
  .card-title { font-size: 1rem; font-weight: 600; color: #f1f5f9; }
  .badge {
    font-size: 0.65rem; padding: 2px 8px; border-radius: 999px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em;
  }
  .badge.running  { background: #1d4ed8; color: #bfdbfe; }
  .badge.done     { background: #166534; color: #bbf7d0; }
  .badge.stalled  { background: #92400e; color: #fde68a; }
  .badge.starting { background: #374151; color: #9ca3af; }
  .badge.no_log   { background: #374151; color: #6b7280; }
  .stat-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
  .stat {
    background: #141824; border-radius: 6px; padding: 6px 10px;
    display: flex; flex-direction: column; align-items: center; flex: 1; min-width: 60px;
  }
  .stat-val { font-size: 1.05rem; font-weight: 700; color: #e2e8f0; }
  .stat-lbl { font-size: 0.6rem; color: #64748b; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.06em; }
  .stat-val.green { color: #4ade80; }
  .stat-val.blue  { color: #60a5fa; }
  .stat-val.amber { color: #fbbf24; }
  .progress-wrap { background: #141824; border-radius: 4px; height: 6px; overflow: hidden; margin-bottom: 10px; }
  .progress-bar  { height: 100%; background: #3b82f6; border-radius: 4px; transition: width 0.4s; }
  .card.done .progress-bar { background: #22c55e; }
  .spark-wrap { height: 40px; margin-bottom: 8px; }
  svg.spark { width: 100%; height: 100%; }
  .footer { font-size: 0.62rem; color: #4b5563; display: flex; justify-content: space-between; }
  .verdict { font-size: 0.75rem; margin-top: 6px; padding: 4px 8px; border-radius: 4px; background: #141824; color: #94a3b8; }
  .verdict.ROLLBACK { color: #f87171; }
  .verdict.DEPLOY   { color: #4ade80; }
  #last-update { font-size: 0.65rem; color: #4b5563; margin-bottom: 16px; }
</style>
</head>
<body>
<h1>🧠 Training Dashboard</h1>
<div id="last-update">—</div>
<div class="grid" id="grid"></div>

<script>
function sparkSVG(spark, minY, maxY) {
  if (!spark || spark.length < 2) return '';
  const W = 300, H = 40, pad = 2;
  const range = maxY - minY || 1;
  const xs = spark.map((_, i) => pad + (i / (spark.length - 1)) * (W - 2 * pad));
  const ys = spark.map(([, v]) => H - pad - ((v - minY) / range) * (H - 2 * pad));
  const pts = xs.map((x, i) => `${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
  const fillPts = `${xs[0].toFixed(1)},${H} ` + pts + ` ${xs[xs.length-1].toFixed(1)},${H}`;
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <polygon points="${fillPts}" fill="#3b82f620"/>
    <polyline points="${pts}" fill="none" stroke="#3b82f6" stroke-width="1.5"/>
  </svg>`;
}

function render(runs) {
  const grid = document.getElementById('grid');
  grid.innerHTML = runs.map(r => {
    const pct = r.total > 0 ? (r.iter / r.total * 100).toFixed(1) : 0;
    const statusClass = r.status || 'no_log';
    const badge = statusClass.charAt(0).toUpperCase() + statusClass.slice(1);

    let stats = '';
    if (r.win !== undefined) {
      stats = `
        <div class="stat-row">
          <div class="stat"><div class="stat-val blue">${r.win.toFixed(2)}%</div><div class="stat-lbl">win rate</div></div>
          <div class="stat"><div class="stat-val green">${r.best.toFixed(2)}%</div><div class="stat-lbl">best</div></div>
          <div class="stat"><div class="stat-val">${r.place ? r.place.toFixed(3) : '—'}</div><div class="stat-lbl">avg place</div></div>
          <div class="stat"><div class="stat-val amber">${r.rollout ? r.rollout.toFixed(1) + '%' : '—'}</div><div class="stat-lbl">rollout</div></div>
        </div>`;
    }

    const spark = r.spark && r.spark.length > 1
      ? sparkSVG(r.spark, 0, Math.max(...r.spark.map(([,v])=>v)) * 1.1)
      : '';

    const verdictHtml = r.verdict
      ? `<div class="verdict ${r.verdict}">${r.verdict}</div>` : '';

    const baselineNote = r.baseline !== undefined && r.baseline !== null
      ? `baseline ${r.baseline.toFixed(1)}%` : '';
    const speedNote = r.speed ? `${r.speed.toFixed(1)}s/it` : '';
    const ageNote = r.status === 'running' ? `updated ${r.age_s}s ago` : '';

    return `<div class="card ${statusClass}">
      <div class="card-header">
        <span class="card-title">${r.emoji} ${r.name}</span>
        <span class="badge ${statusClass}">${badge}</span>
      </div>
      ${stats}
      ${spark ? `<div class="spark-wrap">${spark}</div>` : ''}
      <div class="progress-wrap"><div class="progress-bar" style="width:${pct}%"></div></div>
      ${verdictHtml}
      <div class="footer">
        <span>iter ${r.iter} / ${r.total} (${pct}%)</span>
        <span>${[baselineNote, speedNote, ageNote].filter(Boolean).join(' · ')}</span>
      </div>
    </div>`;
  }).join('');
}

async function poll() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    render(data);
    document.getElementById('last-update').textContent =
      'Last updated: ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('last-update').textContent = 'fetch error: ' + e;
  }
}

poll();
setInterval(poll, 5000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # silence access log

    def do_GET(self):
        if self.path == '/api/status':
            body = json.dumps(get_status()).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        elif self.path in ('/', '/index.html'):
            body = HTML.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == '__main__':
    port = 7777
    server = HTTPServer(('127.0.0.1', port), Handler)
    print(f'Training dashboard running at http://localhost:{port}')
    server.serve_forever()
