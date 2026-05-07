"""
Monitoring Dashboard — Real-time workflow visualization served via FastAPI.

Provides a single-page HTML dashboard that displays:
  - Live workflow status overview (pending, running, completed, failed)
  - Stage transition timeline per workflow
  - Aggregate metrics (success rate, avg confidence, avg duration)
  - Dead-letter queue inspector with replay capability
  - Per-workflow drilldown with full transition history

Served at GET /dashboard when the API server is running.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone

from persistence.state_store import get_state_store
from persistence.dead_letter import get_dead_letter_queue

logger = logging.getLogger(__name__)


def get_dashboard_metrics() -> dict:
    """
    Gather aggregate metrics for the monitoring dashboard.

    Returns dict with:
      - workflow_counts: by status
      - recent_workflows: last 20
      - dead_letter_count: total dead-lettered
      - dead_letter_entries: last 10
    """
    store = get_state_store()
    dlq = get_dead_letter_queue()

    all_workflows = store.list_workflows(limit=200)
    dead_letters = dlq.list_entries(limit=10)

    # Count by status
    status_counts = {"completed": 0, "failed": 0, "running": 0, "partial": 0}
    for w in all_workflows:
        s = w.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "workflow_counts": status_counts,
        "total_workflows": len(all_workflows),
        "recent_workflows": all_workflows[:20],
        "dead_letter_count": len(dead_letters),
        "dead_letter_entries": dead_letters,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# Dashboard HTML — self-contained, no external dependencies
# ══════════════════════════════════════════════════════════════════

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Research Workflow Monitor</title>
<style>
  :root {
    --bg: #0f172a; --surface: #1e293b; --surface-2: #334155;
    --text: #e2e8f0; --text-dim: #94a3b8; --accent: #38bdf8;
    --green: #4ade80; --red: #f87171; --amber: #fbbf24; --purple: #a78bfa;
    --radius: 12px; --shadow: 0 4px 24px rgba(0,0,0,0.3);
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg); color: var(--text);
    min-height: 100vh; padding: 24px;
  }
  header {
    display: flex; align-items: center; gap: 16px;
    margin-bottom: 32px; padding-bottom: 16px;
    border-bottom: 1px solid var(--surface-2);
  }
  header h1 { font-size: 1.5rem; font-weight: 600; }
  header .badge {
    background: var(--accent); color: var(--bg);
    padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 700;
  }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }
  .card {
    background: var(--surface); border-radius: var(--radius);
    padding: 20px; box-shadow: var(--shadow);
    border: 1px solid var(--surface-2);
    transition: transform 0.2s, border-color 0.2s;
  }
  .card:hover { transform: translateY(-2px); border-color: var(--accent); }
  .card .label { font-size: 0.8rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; }
  .card .value { font-size: 2rem; font-weight: 700; margin-top: 4px; }
  .card .value.green { color: var(--green); }
  .card .value.red { color: var(--red); }
  .card .value.amber { color: var(--amber); }
  .card .value.blue { color: var(--accent); }
  .section { margin-bottom: 32px; }
  .section h2 { font-size: 1.1rem; margin-bottom: 16px; color: var(--text-dim); }
  table { width: 100%; border-collapse: collapse; background: var(--surface); border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow); }
  th { background: var(--surface-2); padding: 12px 16px; text-align: left; font-size: 0.8rem; text-transform: uppercase; color: var(--text-dim); letter-spacing: 0.05em; }
  td { padding: 10px 16px; border-top: 1px solid var(--surface-2); font-size: 0.85rem; }
  tr:hover td { background: rgba(56,189,248,0.05); }
  .status-badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 0.75rem; font-weight: 600;
  }
  .status-completed { background: rgba(74,222,128,0.15); color: var(--green); }
  .status-failed, .status-dead_lettered { background: rgba(248,113,113,0.15); color: var(--red); }
  .status-running, .status-started { background: rgba(56,189,248,0.15); color: var(--accent); }
  .status-partial { background: rgba(251,191,36,0.15); color: var(--amber); }
  .btn {
    padding: 6px 16px; border-radius: 8px; border: none;
    font-size: 0.8rem; font-weight: 600; cursor: pointer;
    transition: all 0.2s;
  }
  .btn-replay { background: var(--purple); color: #fff; }
  .btn-replay:hover { opacity: 0.85; transform: scale(1.03); }
  .btn-refresh { background: var(--accent); color: var(--bg); }
  .btn-refresh:hover { opacity: 0.85; }
  .refresh-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
  .refresh-bar span { font-size: 0.8rem; color: var(--text-dim); }
  .timeline { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
  .timeline .dot {
    width: 10px; height: 10px; border-radius: 50%;
    display: inline-block; transition: transform 0.2s;
  }
  .timeline .dot:hover { transform: scale(1.5); }
  .dot-completed { background: var(--green); }
  .dot-failed { background: var(--red); }
  .dot-started { background: var(--accent); }
  .dot-retrying { background: var(--amber); }
  .empty { text-align: center; padding: 40px; color: var(--text-dim); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
  .loading { animation: pulse 1.5s infinite; }
</style>
</head>
<body>
<header>
  <h1>🔬 Research Workflow Monitor</h1>
  <span class="badge">LIVE</span>
</header>

<div class="refresh-bar">
  <button class="btn btn-refresh" onclick="refresh()">↻ Refresh</button>
  <span id="lastRefresh">Loading...</span>
</div>

<div class="grid" id="metricsGrid">
  <div class="card"><div class="label">Total Workflows</div><div class="value blue" id="totalCount">-</div></div>
  <div class="card"><div class="label">Completed</div><div class="value green" id="completedCount">-</div></div>
  <div class="card"><div class="label">Failed</div><div class="value red" id="failedCount">-</div></div>
  <div class="card"><div class="label">Dead-Lettered</div><div class="value amber" id="dlCount">-</div></div>
</div>

<div class="section">
  <h2>📋 Recent Workflows</h2>
  <table id="workflowTable">
    <thead><tr><th>Correlation ID</th><th>Stage</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead>
    <tbody id="workflowBody"><tr><td colspan="5" class="empty loading">Loading workflows...</td></tr></tbody>
  </table>
</div>

<div class="section">
  <h2>💀 Dead-Letter Queue</h2>
  <table id="dlTable">
    <thead><tr><th>Correlation ID</th><th>Failed Stage</th><th>Retries</th><th>Errors</th><th>Created</th><th>Actions</th></tr></thead>
    <tbody id="dlBody"><tr><td colspan="6" class="empty loading">Loading...</td></tr></tbody>
  </table>
</div>

<div class="section" id="historySection" style="display:none">
  <h2>🔍 Workflow History — <span id="historyId"></span></h2>
  <table id="historyTable">
    <thead><tr><th>Stage</th><th>Status</th><th>Confidence</th><th>Error</th><th>Timestamp</th></tr></thead>
    <tbody id="historyBody"></tbody>
  </table>
</div>

<script>
async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

function statusBadge(s) {
  return `<span class="status-badge status-${s}">${s}</span>`;
}

function shortId(id) { return id ? id.substring(0, 20) + '…' : '—'; }
function shortTime(t) { return t ? new Date(t).toLocaleString() : '—'; }

async function refresh() {
  try {
    const [wf, dl] = await Promise.all([
      fetchJSON('/workflows?limit=20'),
      fetchJSON('/dead-letter?limit=10'),
    ]);

    // Metrics
    const counts = {};
    wf.workflows.forEach(w => { counts[w.status] = (counts[w.status]||0)+1; });
    document.getElementById('totalCount').textContent = wf.count;
    document.getElementById('completedCount').textContent = counts.completed||0;
    document.getElementById('failedCount').textContent = counts.failed||0;
    document.getElementById('dlCount').textContent = dl.count;

    // Workflow table
    const wBody = document.getElementById('workflowBody');
    if (wf.workflows.length === 0) {
      wBody.innerHTML = '<tr><td colspan="5" class="empty">No workflows yet. Submit one via POST /research</td></tr>';
    } else {
      wBody.innerHTML = wf.workflows.map(w => `
        <tr>
          <td><code>${shortId(w.correlation_id)}</code></td>
          <td>${w.stage||'—'}</td>
          <td>${statusBadge(w.status)}</td>
          <td>${shortTime(w.created_at)}</td>
          <td><button class="btn btn-refresh" onclick="showHistory('${w.correlation_id}')">History</button></td>
        </tr>`).join('');
    }

    // Dead-letter table
    const dBody = document.getElementById('dlBody');
    if (dl.dead_letters.length === 0) {
      dBody.innerHTML = '<tr><td colspan="6" class="empty">No dead-lettered workflows ✅</td></tr>';
    } else {
      dBody.innerHTML = dl.dead_letters.map(d => `
        <tr>
          <td><code>${shortId(d.correlation_id)}</code></td>
          <td>${d.failed_stage}</td>
          <td>${d.retry_count}</td>
          <td>${(d.error_log||[]).slice(-1)[0]||'—'}</td>
          <td>${shortTime(d.created_at)}</td>
          <td><button class="btn btn-replay" onclick="replayDL('${d.correlation_id}')">↻ Replay</button></td>
        </tr>`).join('');
    }

    document.getElementById('lastRefresh').textContent = 'Last refresh: ' + new Date().toLocaleTimeString();
  } catch(e) {
    console.error('Refresh failed:', e);
    document.getElementById('lastRefresh').textContent = 'Refresh failed: ' + e.message;
  }
}

async function showHistory(corrId) {
  try {
    const data = await fetchJSON(`/research/${corrId}/history`);
    document.getElementById('historySection').style.display = 'block';
    document.getElementById('historyId').textContent = corrId.substring(0, 20) + '…';
    const hBody = document.getElementById('historyBody');
    hBody.innerHTML = data.transitions.map(t => `
      <tr>
        <td>${t.stage}</td>
        <td>${statusBadge(t.status)}</td>
        <td>${(t.confidence||0).toFixed(2)}</td>
        <td>${t.error_message||'—'}</td>
        <td>${shortTime(t.created_at)}</td>
      </tr>`).join('');
    document.getElementById('historySection').scrollIntoView({behavior:'smooth'});
  } catch(e) {
    alert('Failed to load history: ' + e.message);
  }
}

async function replayDL(corrId) {
  if (!confirm('Replay this dead-lettered workflow?')) return;
  try {
    const res = await fetch(`/dead-letter/${corrId}/replay`, {method:'POST'});
    const data = await res.json();
    alert(`Replay initiated!\\nNew correlation ID: ${data.new_correlation_id}`);
    refresh();
  } catch(e) { alert('Replay failed: ' + e.message); }
}

refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>"""
