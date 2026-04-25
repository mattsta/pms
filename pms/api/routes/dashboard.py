"""Dashboard UI routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_ui() -> HTMLResponse:
    """Serve the read-only dashboard UI."""
    html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PMS Command Center</title>
    <style>
      @import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap");

      :root {
        --bg: #0f141b;
        --bg-alt: #141c26;
        --card: #1a2430;
        --accent: #f7c845;
        --accent-2: #68d4ff;
        --accent-3: #ff8aa1;
        --text: #e9eef5;
        --muted: #9fb0c3;
        --risk-low: #54d99f;
        --risk-med: #f0b860;
        --risk-high: #ff6b6b;
        --shadow: 0 20px 50px rgba(3, 8, 20, 0.4);
        --radius: 18px;
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        font-family: "Space Grotesk", "Sora", "Segoe UI", sans-serif;
        color: var(--text);
        background: radial-gradient(circle at top right, #1d2a3a 0%, #0f141b 45%),
          radial-gradient(circle at 10% 20%, #162132 0%, transparent 40%),
          linear-gradient(140deg, #0c1218 0%, #111a22 60%, #141c26 100%);
        min-height: 100vh;
      }

      .page {
        max-width: 1200px;
        margin: 0 auto;
        padding: 48px 24px 80px;
      }

      header.hero {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 24px;
        margin-bottom: 32px;
      }

      .hero h1 {
        font-size: 40px;
        margin: 0 0 8px;
        letter-spacing: 0.5px;
      }

      .hero p {
        margin: 0;
        color: var(--muted);
        max-width: 520px;
      }

      .hero .meta {
        display: flex;
        align-items: center;
        gap: 12px;
      }

      .pill {
        background: rgba(255, 255, 255, 0.08);
        padding: 10px 14px;
        border-radius: 999px;
        font-size: 13px;
      }

      .pill span {
        color: var(--accent);
        margin-left: 6px;
      }

      button {
        font-family: inherit;
        border: none;
        border-radius: 999px;
        padding: 10px 18px;
        background: var(--accent);
        color: #121212;
        cursor: pointer;
        font-weight: 600;
        box-shadow: 0 8px 20px rgba(247, 200, 69, 0.35);
      }

      .controls {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 16px;
        padding: 18px;
        background: rgba(255, 255, 255, 0.03);
        border-radius: var(--radius);
        border: 1px solid rgba(255, 255, 255, 0.08);
        margin-bottom: 32px;
        box-shadow: var(--shadow);
      }

      .control-field label {
        display: block;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: var(--muted);
        margin-bottom: 6px;
      }

      .control-field input {
        width: 100%;
        padding: 12px 14px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        background: #0f1722;
        color: var(--text);
        font-family: "JetBrains Mono", ui-monospace, monospace;
        font-size: 13px;
      }

      .grid {
        display: grid;
        gap: 24px;
      }

      .panel {
        padding: 20px;
        background: rgba(18, 24, 34, 0.75);
        border-radius: var(--radius);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: var(--shadow);
      }

      .panel-head {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        margin-bottom: 16px;
      }

      .panel-head h2 {
        margin: 0;
        font-size: 22px;
      }

      .panel-head .filters {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }

      .panel-head .filters input {
        padding: 8px 10px;
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        background: #121a26;
        color: var(--text);
        font-family: "JetBrains Mono", ui-monospace, monospace;
        font-size: 12px;
        min-width: 160px;
      }

      .totals {
        display: flex;
        gap: 16px;
        flex-wrap: wrap;
        color: var(--muted);
        font-size: 13px;
      }

      .cards {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 16px;
      }

      .card {
        padding: 16px;
        border-radius: 16px;
        background: var(--card);
        border: 1px solid rgba(255, 255, 255, 0.06);
        display: grid;
        gap: 10px;
        position: relative;
      }

      .card::after {
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.04);
        pointer-events: none;
      }

      .card h3 {
        margin: 0;
        font-size: 18px;
      }

      .card .meta {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        font-size: 13px;
        color: var(--muted);
      }

      .risk {
        font-weight: 600;
        font-size: 12px;
        padding: 4px 10px;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        width: fit-content;
      }

      .risk.low {
        background: rgba(84, 217, 159, 0.15);
        color: var(--risk-low);
      }

      .risk.medium {
        background: rgba(240, 184, 96, 0.15);
        color: var(--risk-med);
      }

      .risk.high {
        background: rgba(255, 107, 107, 0.15);
        color: var(--risk-high);
      }

      .progress {
        height: 8px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.08);
        overflow: hidden;
      }

      .progress span {
        display: block;
        height: 100%;
        background: linear-gradient(90deg, var(--accent-2), var(--accent));
      }

      .status {
        font-size: 12px;
        color: var(--muted);
      }

      .status strong {
        color: var(--text);
      }

      .lineage-list {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 16px;
      }

      .lineage-card {
        padding: 16px;
        border-radius: 16px;
        background: rgba(26, 36, 48, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
      }

      .lineage-card h3 {
        margin: 0 0 6px;
        font-size: 18px;
      }

      .lineage-meta {
        color: var(--muted);
        font-size: 12px;
        margin-bottom: 10px;
      }

      .lineage-tags {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 10px;
      }

      .tag {
        padding: 6px 10px;
        border-radius: 999px;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        background: rgba(255, 255, 255, 0.08);
      }

      .tag.pass {
        background: rgba(84, 217, 159, 0.15);
        color: var(--risk-low);
      }

      .tag.fail {
        background: rgba(255, 107, 107, 0.15);
        color: var(--risk-high);
      }

      .tag.none {
        background: rgba(240, 184, 96, 0.15);
        color: var(--risk-med);
      }

      .tag.gate {
        background: rgba(255, 138, 161, 0.18);
        color: var(--accent-3);
      }

      .lineage-section {
        margin-top: 8px;
        font-size: 12px;
        color: var(--muted);
      }

      .lineage-listing {
        margin-top: 6px;
        display: grid;
        gap: 6px;
      }

      .lineage-row {
        display: flex;
        justify-content: space-between;
        gap: 10px;
      }

      .retention-bars {
        display: grid;
        gap: 12px;
        margin-bottom: 16px;
      }

      .retention-bar {
        display: grid;
        gap: 6px;
      }

      .retention-bar .label {
        font-size: 12px;
        color: var(--muted);
      }

      .retention-track {
        width: 100%;
        height: 8px;
        background: rgba(255, 255, 255, 0.08);
        border-radius: 999px;
        overflow: hidden;
      }

      .retention-track span {
        display: block;
        height: 100%;
        width: 0%;
        border-radius: inherit;
      }

      .retention-track.low span {
        background: var(--risk-low);
      }

      .retention-track.medium span {
        background: var(--risk-med);
      }

      .retention-track.high span {
        background: var(--risk-high);
      }

      .retention-list {
        display: grid;
        gap: 8px;
      }

      .queue-list {
        display: grid;
        gap: 12px;
      }

      .operator-shell {
        display: grid;
        gap: 16px;
      }

      .operator-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 16px;
      }

      .operator-card {
        padding: 16px;
        border-radius: 16px;
        background: rgba(26, 36, 48, 0.78);
        border: 1px solid rgba(255, 255, 255, 0.08);
        display: grid;
        gap: 10px;
      }

      .operator-card h3 {
        margin: 0;
        font-size: 18px;
      }

      .operator-card p {
        margin: 0;
        color: var(--muted);
        font-size: 13px;
      }

      .operator-list {
        display: grid;
        gap: 8px;
      }

      .operator-list-item {
        padding: 10px 12px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.05);
        font-size: 13px;
      }

      .operator-list-item strong {
        display: block;
        margin-bottom: 4px;
      }

      .operator-jumps {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }

      .operator-jumps a {
        color: var(--accent-2);
        text-decoration: none;
        font-size: 12px;
        padding: 8px 10px;
        border-radius: 999px;
        background: rgba(104, 212, 255, 0.12);
      }

      .queue-card {
        border: 1px solid rgba(11, 31, 61, 0.12);
        border-radius: 14px;
        padding: 12px 14px;
        background: rgba(255, 255, 255, 0.6);
      }

      .queue-card h3 {
        margin: 0 0 6px 0;
        font-size: 1.02rem;
      }

      .queue-card p {
        margin: 0;
        color: rgba(27, 47, 78, 0.8);
      }

      .snapshot-body {
        display: grid;
        gap: 10px;
      }

      .snapshot-row {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        padding: 10px 12px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.7);
        border: 1px solid rgba(11, 31, 61, 0.12);
        font-size: 13px;
      }

      .snapshot-row span {
        color: var(--muted);
      }

      .snapshot-list {
        display: grid;
        gap: 6px;
        font-size: 12px;
        color: var(--muted);
      }

      .snapshot-list div {
        display: flex;
        justify-content: space-between;
        gap: 8px;
      }

      .snapshot-review {
        display: grid;
        gap: 8px;
        margin-top: 12px;
      }

      .retention-row {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr 1fr 1.2fr 0.7fr;
        gap: 8px;
        font-size: 12px;
        color: var(--muted);
      }

      .retention-row.header {
        text-transform: uppercase;
        letter-spacing: 1px;
        font-size: 11px;
        color: var(--muted);
      }

      .retention-row span {
        color: var(--text);
      }

      .mono {
        font-family: "JetBrains Mono", ui-monospace, monospace;
        font-size: 11px;
      }

      @media (max-width: 700px) {
        .hero h1 {
          font-size: 30px;
        }
        button {
          width: 100%;
        }
      }
    </style>
  </head>
  <body>
    <div class="page">
      <header class="hero">
        <div>
          <h1>PMS Command Center</h1>
          <p>Organization, portfolio, and program rollups with plan -> task -> test lineage.</p>
        </div>
        <div class="meta">
          <div class="pill">API status<span id="api-status">disconnected</span></div>
          <button id="refresh-all">Refresh</button>
        </div>
      </header>

      <section class="controls">
        <div class="control-field">
          <label for="api-base">API base</label>
          <input id="api-base" placeholder="/api/v1" />
        </div>
        <div class="control-field">
          <label for="api-key">API key (X-API-Key)</label>
          <input id="api-key" placeholder="pms_..." type="password" />
        </div>
        <div class="control-field">
          <label for="auto-refresh">Auto refresh</label>
          <input id="auto-refresh" placeholder="Seconds (0 to disable)" />
        </div>
      </section>

      <section class="grid">
        <div class="panel" id="project-operator-panel">
          <div class="panel-head">
            <div>
              <h2>Project Operator Console</h2>
              <div class="totals" id="project-operator-totals"></div>
            </div>
            <div class="filters">
              <input id="operator-project-id" placeholder="Project id" />
              <button id="operator-refresh">Reload</button>
            </div>
          </div>
          <div class="operator-shell">
            <div class="operator-grid">
              <div class="operator-card">
                <h3>What Changed Since Review</h3>
                <div class="operator-list" id="operator-changed"></div>
              </div>
              <div class="operator-card">
                <h3>Blocked and Why</h3>
                <div class="operator-list" id="operator-blocked"></div>
              </div>
              <div class="operator-card">
                <h3>What Should Happen Next</h3>
                <div class="operator-list" id="operator-next"></div>
              </div>
              <div class="operator-card">
                <h3>Where To Jump</h3>
                <div class="operator-jumps" id="operator-jumps"></div>
              </div>
            </div>
          </div>
        </div>

        <div class="panel" id="org-panel">
          <div class="panel-head">
            <div>
              <h2>Organizations</h2>
              <div class="totals" id="org-totals"></div>
            </div>
          </div>
          <div class="cards" id="org-cards"></div>
        </div>

        <div class="panel" id="portfolio-panel">
          <div class="panel-head">
            <div>
              <h2>Portfolios</h2>
              <div class="totals" id="portfolio-totals"></div>
            </div>
            <div class="filters">
              <input id="portfolio-org-id" placeholder="Filter org_id" />
              <button id="portfolio-refresh">Reload</button>
            </div>
          </div>
          <div class="cards" id="portfolio-cards"></div>
        </div>

        <div class="panel" id="program-panel">
          <div class="panel-head">
            <div>
              <h2>Programs</h2>
              <div class="totals" id="program-totals"></div>
            </div>
            <div class="filters">
              <input id="program-org-id" placeholder="Filter org_id" />
              <input id="program-portfolio-id" placeholder="Filter portfolio_id" />
              <button id="program-refresh">Reload</button>
            </div>
          </div>
          <div class="cards" id="program-cards"></div>
        </div>

        <div class="panel" id="lineage-panel">
          <div class="panel-head">
            <div>
              <h2>Plan Lineage</h2>
              <div class="totals" id="lineage-totals"></div>
            </div>
            <div class="filters">
              <input id="lineage-plan-id" placeholder="Filter plan_id" />
              <input id="lineage-project-id" placeholder="Filter project_id" />
              <input id="lineage-status" placeholder="Filter status" />
              <button id="lineage-refresh">Reload</button>
            </div>
          </div>
          <div class="lineage-list" id="lineage-cards"></div>
        </div>

        <div class="panel" id="retention-panel">
          <div class="panel-head">
            <div>
              <h2>Test Run Retention</h2>
              <div class="totals" id="retention-totals"></div>
            </div>
            <div class="filters">
              <input id="retention-limit" placeholder="Limit (10)" />
              <input id="retention-sort" placeholder="Sort largest|recent" />
              <button id="retention-refresh">Reload</button>
            </div>
          </div>
          <div class="retention-bars" id="retention-bars"></div>
          <div class="retention-list" id="retention-list"></div>
        </div>

        <div class="panel" id="snapshot-panel">
          <div class="panel-head">
            <div>
              <h2>Work Snapshot</h2>
              <div class="totals" id="snapshot-totals"></div>
            </div>
            <div class="filters">
              <select id="snapshot-scope-type">
                <option value="project">project</option>
                <option value="portfolio">portfolio</option>
                <option value="program">program</option>
                <option value="organization">organization</option>
              </select>
              <input id="snapshot-scope-id" placeholder="Scope id" />
              <input id="snapshot-task-limit" placeholder="Task limit (5)" />
              <input id="snapshot-test-limit" placeholder="Test limit (5)" />
              <button id="snapshot-refresh">Reload</button>
            </div>
          </div>
          <div class="snapshot-body" id="snapshot-body"></div>
          <div class="snapshot-review">
            <input id="snapshot-reviewed-by" placeholder="Reviewed by" />
            <input id="snapshot-note" placeholder="Review note" />
            <button id="snapshot-review">Mark Reviewed</button>
          </div>
        </div>

        <div class="panel" id="queue-panel">
          <div class="panel-head">
            <div>
              <h2>Smart Queues</h2>
              <div class="totals" id="queue-totals"></div>
            </div>
            <div class="filters">
              <input id="queue-project-id" placeholder="Filter project_id" />
              <input id="queue-limit" placeholder="Limit (5)" />
              <button id="queue-refresh">Reload</button>
            </div>
          </div>
          <div class="queue-list" id="queue-list"></div>
        </div>
      </section>
    </div>

    <script>
      const apiKeyInput = document.getElementById("api-key");
      const apiBaseInput = document.getElementById("api-base");
      const autoRefreshInput = document.getElementById("auto-refresh");
      const apiStatus = document.getElementById("api-status");

      const orgCards = document.getElementById("org-cards");
      const orgTotals = document.getElementById("org-totals");
      const portfolioCards = document.getElementById("portfolio-cards");
      const portfolioTotals = document.getElementById("portfolio-totals");
      const programCards = document.getElementById("program-cards");
      const programTotals = document.getElementById("program-totals");
      const lineageCards = document.getElementById("lineage-cards");
      const lineageTotals = document.getElementById("lineage-totals");
      const retentionTotals = document.getElementById("retention-totals");
      const retentionBars = document.getElementById("retention-bars");
      const retentionList = document.getElementById("retention-list");
      const snapshotTotals = document.getElementById("snapshot-totals");
      const snapshotBody = document.getElementById("snapshot-body");
      const queueTotals = document.getElementById("queue-totals");
      const queueList = document.getElementById("queue-list");
      const operatorTotals = document.getElementById("project-operator-totals");
      const operatorChanged = document.getElementById("operator-changed");
      const operatorBlocked = document.getElementById("operator-blocked");
      const operatorNext = document.getElementById("operator-next");
      const operatorJumps = document.getElementById("operator-jumps");

      const portfolioOrgInput = document.getElementById("portfolio-org-id");
      const programOrgInput = document.getElementById("program-org-id");
      const programPortfolioInput = document.getElementById("program-portfolio-id");
      const lineagePlanInput = document.getElementById("lineage-plan-id");
      const lineageProjectInput = document.getElementById("lineage-project-id");
      const lineageStatusInput = document.getElementById("lineage-status");
      const queueProjectInput = document.getElementById("queue-project-id");
      const queueLimitInput = document.getElementById("queue-limit");
      const retentionLimitInput = document.getElementById("retention-limit");
      const retentionSortInput = document.getElementById("retention-sort");
      const snapshotScopeType = document.getElementById("snapshot-scope-type");
      const snapshotScopeId = document.getElementById("snapshot-scope-id");
      const snapshotTaskLimit = document.getElementById("snapshot-task-limit");
      const snapshotTestLimit = document.getElementById("snapshot-test-limit");
      const snapshotReviewedBy = document.getElementById("snapshot-reviewed-by");
      const snapshotNote = document.getElementById("snapshot-note");
      const operatorProjectId = document.getElementById("operator-project-id");

      let refreshTimer = null;

      function setStatus(message, ok = false) {
        apiStatus.textContent = message;
        apiStatus.style.color = ok ? "var(--risk-low)" : "var(--accent-3)";
      }

      function readSettings() {
        const apiBase = apiBaseInput.value || "/api/v1";
        const apiKey = apiKeyInput.value;
        return { apiBase, apiKey };
      }

      function persistSettings() {
        localStorage.setItem("pms-dashboard-api-base", apiBaseInput.value);
        localStorage.setItem("pms-dashboard-api-key", apiKeyInput.value);
        localStorage.setItem("pms-dashboard-auto-refresh", autoRefreshInput.value);
      }

      function loadSettings() {
        apiBaseInput.value =
          localStorage.getItem("pms-dashboard-api-base") || "/api/v1";
        apiKeyInput.value = localStorage.getItem("pms-dashboard-api-key") || "";
        autoRefreshInput.value =
          localStorage.getItem("pms-dashboard-auto-refresh") || "0";
      }

      async function fetchJson(path, params = {}) {
        const { apiBase, apiKey } = readSettings();
        const url = new URL(apiBase + path, window.location.origin);
        Object.entries(params).forEach(([key, value]) => {
          if (value) {
            url.searchParams.set(key, value);
          }
        });

        const res = await fetch(url.toString(), {
          headers: apiKey ? { "X-API-Key": apiKey } : {},
        });
        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || res.statusText);
        }
        return res.json();
      }

      async function postJson(path, payload = {}) {
        const { apiBase, apiKey } = readSettings();
        const url = new URL(apiBase + path, window.location.origin);
        const res = await fetch(url.toString(), {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(apiKey ? { "X-API-Key": apiKey } : {}),
          },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || res.statusText);
        }
        return res.json();
      }

      function clearChildren(node) {
        while (node.firstChild) {
          node.removeChild(node.firstChild);
        }
      }

      function renderTotals(node, totals, labels) {
        clearChildren(node);
        labels.forEach(([label, key]) => {
          const value = totals[key] ?? 0;
          const span = document.createElement("span");
          span.textContent = `${label}: ${value}`;
          node.appendChild(span);
        });
      }

      function renderSnapshotRow(label, value) {
        const row = document.createElement("div");
        row.className = "snapshot-row";
        const left = document.createElement("span");
        left.textContent = label;
        const right = document.createElement("strong");
        right.textContent = value;
        row.appendChild(left);
        row.appendChild(right);
        return row;
      }

      function renderSnapshotList(title, items) {
        const wrapper = document.createElement("div");
        const header = document.createElement("strong");
        header.textContent = title;
        wrapper.appendChild(header);
        const list = document.createElement("div");
        list.className = "snapshot-list";
        items.forEach((item) => list.appendChild(item));
        wrapper.appendChild(list);
        return wrapper;
      }

      function renderOperatorItem(container, title, summary) {
        const item = document.createElement("div");
        item.className = "operator-list-item";
        const strong = document.createElement("strong");
        strong.textContent = title;
        const body = document.createElement("div");
        body.textContent = summary;
        item.appendChild(strong);
        item.appendChild(body);
        container.appendChild(item);
      }

      function renderOperatorJump(container, label, href) {
        if (!href) return;
        const link = document.createElement("a");
        link.href = href;
        link.textContent = label;
        link.target = "_blank";
        link.rel = "noreferrer";
        container.appendChild(link);
      }

      function formatBytes(value) {
        if (value < 1024) return `${value} B`;
        let size = value;
        const units = ["KB", "MB", "GB", "TB", "PB"];
        for (const unit of units) {
          size /= 1024;
          if (size < 1024) {
            return `${size.toFixed(1)} ${unit}`;
          }
        }
        return `${size.toFixed(1)} EB`;
      }

      function formatRelative(value) {
        if (!value) return "-";
        const ts = new Date(value);
        if (Number.isNaN(ts.getTime())) return value;
        const now = new Date();
        let diffSeconds = Math.floor((now - ts) / 1000);
        const future = diffSeconds < 0;
        if (future) {
          diffSeconds = Math.abs(diffSeconds);
        }

        let amount = diffSeconds;
        let unit = "s";
        if (diffSeconds >= 86400) {
          amount = Math.floor(diffSeconds / 86400);
          unit = "d";
        } else if (diffSeconds >= 3600) {
          amount = Math.floor(diffSeconds / 3600);
          unit = "h";
        } else if (diffSeconds >= 60) {
          amount = Math.floor(diffSeconds / 60);
          unit = "m";
        }

        const relative = future ? `in ${amount}${unit}` : `${amount}${unit} ago`;
        return `${relative} (${ts.toISOString().slice(0, 19)})`;
      }

      function summarizeDigest(digest, reviewedAt) {
        if (!digest) return "-";
        const created = digest.tasks_created || 0;
        const completed = digest.tasks_completed || 0;
        const updated = digest.tasks_updated || 0;
        const since = reviewedAt ? formatRelative(reviewedAt) : "never";
        return `Δ tasks +${created} / done ${completed} / upd ${updated} since ${since}`;
      }

      function summarizeNextActions(actions) {
        if (!actions || actions.length === 0) return "-";
        const titles = actions.map((task) => task.title).filter(Boolean);
        if (titles.length === 0) return "-";
        const preview = titles.slice(0, 2).join(", ");
        if (titles.length > 2) return `${preview} +${titles.length - 2}`;
        return preview;
      }

      function summarizeEvidence(evidence) {
        if (!evidence) return "evidence -";
        const total = evidence.total_count || 0;
        const recent = evidence.new_count || 0;
        return `evidence ${total} (new ${recent})`;
      }

      function summarizeRetention(retention) {
        if (!retention) return "retention -";
        const totalBytes = retention.total_bytes || 0;
        const runs = retention.total_runs || 0;
        const alerts = retention.alerts ? retention.alerts.length : 0;
        let summary = `retention ${formatBytes(totalBytes)} / ${runs} runs`;
        if (alerts > 0) summary += ` / ${alerts} alerts`;
        return summary;
      }

      function renderRetentionBar(container, label, used, limit) {
        const percent = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
        const risk =
          percent >= 90 ? "high" : percent >= 70 ? "medium" : "low";
        const bar = document.createElement("div");
        bar.className = "retention-bar";

        const meta = document.createElement("div");
        meta.className = "label";
        const limitText = limit > 0 ? formatBytes(limit) : "disabled";
        meta.textContent = `${label}: ${formatBytes(used)} / ${limitText}`;

        const track = document.createElement("div");
        track.className = `retention-track ${risk}`;
        const fill = document.createElement("span");
        fill.style.width = `${percent}%`;
        track.appendChild(fill);

        bar.appendChild(meta);
        bar.appendChild(track);
        container.appendChild(bar);
      }

      function renderCard(container, title, stats, risk, progressLabel) {
        const card = document.createElement("div");
        card.className = "card";

        const h3 = document.createElement("h3");
        h3.textContent = title;
        card.appendChild(h3);

        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = stats;
        card.appendChild(meta);

        const riskPill = document.createElement("div");
        riskPill.className = `risk ${risk}`;
        riskPill.textContent = `risk ${risk}`;
        card.appendChild(riskPill);

        if (progressLabel) {
          const progress = document.createElement("div");
          progress.className = "progress";
          const bar = document.createElement("span");
          bar.style.width = progressLabel.percent;
          progress.appendChild(bar);
          card.appendChild(progress);

          const status = document.createElement("div");
          status.className = "status";
          status.innerHTML = `<strong>${progressLabel.label}</strong>`;
          card.appendChild(status);
        }

        container.appendChild(card);
      }

      function riskClass(riskLevel) {
        if (riskLevel === "high") return "high";
        if (riskLevel === "medium") return "medium";
        return "low";
      }

      function testTag(success) {
        if (success === true) {
          return { label: "tests passed", className: "pass" };
        }
        if (success === false) {
          return { label: "tests failed", className: "fail" };
        }
        return { label: "no tests", className: "none" };
      }

      function renderLineageCard(item) {
        const card = document.createElement("div");
        card.className = "lineage-card";

        const title = document.createElement("h3");
        title.textContent = item.plan.name;
        card.appendChild(title);

        const meta = document.createElement("div");
        meta.className = "lineage-meta";
        const planStatus = item.plan.status || "unknown";
        const projectLabel = item.plan.project_id
          ? `project ${item.plan.project_id}`
          : "project none";
        meta.textContent = `${planStatus} • ${projectLabel}`;
        card.appendChild(meta);

        const tags = document.createElement("div");
        tags.className = "lineage-tags";
        const taskTag = document.createElement("div");
        taskTag.className = "tag";
        taskTag.textContent = `tasks ${item.stats.completed_tasks}/${item.stats.total_tasks}`;
        tags.appendChild(taskTag);

        const blockedTag = document.createElement("div");
        blockedTag.className = "tag";
        blockedTag.textContent = `blocked ${item.stats.blocked_tasks}`;
        tags.appendChild(blockedTag);

        if (item.evidence) {
          const evidenceTag = document.createElement("div");
          evidenceTag.className = "tag";
          evidenceTag.textContent = `evidence ${item.evidence.total || 0}`;
          tags.appendChild(evidenceTag);

          const codeTag = document.createElement("div");
          codeTag.className = "tag";
          codeTag.textContent = `code ${item.evidence.code_total || 0}`;
          tags.appendChild(codeTag);
        }

        const testBadge = testTag(item.stats.latest_test_success);
        const testTagNode = document.createElement("div");
        testTagNode.className = `tag ${testBadge.className}`;
        testTagNode.textContent = testBadge.label;
        tags.appendChild(testTagNode);

        card.appendChild(tags);

        const tasksSection = document.createElement("div");
        tasksSection.className = "lineage-section";
        tasksSection.innerHTML = "<strong>Tasks</strong>";
        const taskList = document.createElement("div");
        taskList.className = "lineage-listing";
        if (item.tasks.length === 0) {
          const empty = document.createElement("div");
          empty.textContent = "No linked tasks.";
          taskList.appendChild(empty);
        } else {
          item.tasks.forEach((task) => {
            const row = document.createElement("div");
            row.className = "lineage-row";
            const name = document.createElement("span");
            name.textContent = task.title;
            const status = document.createElement("span");
            status.className = "mono";
            let statusText = task.status;
            if (task.evidence_gate && task.evidence_gate.blocked) {
              statusText += " • gate";
            }
            status.textContent = statusText;
            row.appendChild(name);
            row.appendChild(status);
            taskList.appendChild(row);
          });
        }
        tasksSection.appendChild(taskList);
        card.appendChild(tasksSection);

        const testsSection = document.createElement("div");
        testsSection.className = "lineage-section";
        testsSection.innerHTML = "<strong>Recent Tests</strong>";
        const testList = document.createElement("div");
        testList.className = "lineage-listing";
        if (item.test_runs.length === 0) {
          const empty = document.createElement("div");
          empty.textContent = "No linked test runs.";
          testList.appendChild(empty);
        } else {
          item.test_runs.forEach((run) => {
            const row = document.createElement("div");
            row.className = "lineage-row";
            const command = document.createElement("span");
            command.textContent = run.command || "test run";
            const status = document.createElement("span");
            status.className = "mono";
            status.textContent = run.success ? "pass" : "fail";
            row.appendChild(command);
            row.appendChild(status);
            testList.appendChild(row);
          });
        }
        testsSection.appendChild(testList);
        card.appendChild(testsSection);

        lineageCards.appendChild(card);
      }

      async function loadOrganizations() {
        clearChildren(orgCards);
        orgTotals.textContent = "Loading...";
        const data = await fetchJson("/organizations/dashboard", {
          include_digest: "true",
          include_next_actions: "true",
          include_evidence: "true",
          include_retention: "true",
          next_limit: "3",
        });
        renderTotals(orgTotals, data.totals, [
          ["orgs", "total_organizations"],
          ["teams", "total_teams"],
          ["portfolios", "total_portfolios"],
          ["programs", "total_programs"],
          ["projects", "total_projects"],
          ["goals", "total_goals"],
          ["objectives", "total_objectives"],
          ["tasks", "total_tasks"],
          ["blocked", "blocked_tasks"],
        ]);
        data.items.forEach((item) => {
          const stats = item.stats;
          const activity = formatRelative(item.last_activity_at);
          const transition = formatRelative(item.last_transition_at);
          const digestLine = summarizeDigest(item.digest, item.last_reviewed_at);
          const nextLine = summarizeNextActions(item.next_actions);
          const evidenceLine = summarizeEvidence(item.evidence);
          const retentionLine = summarizeRetention(item.retention);
          const summary = `projects ${stats.total_projects} | goals ${stats.completed_goals}/${stats.total_goals} | objectives ${stats.completed_objectives}/${stats.total_objectives} | tasks ${stats.total_tasks} (${stats.blocked_tasks} blocked) | activity ${activity} | transition ${transition} | ${digestLine} | ${evidenceLine} | ${retentionLine} | next ${nextLine}`;
          const avgProgress = stats.avg_goal_progress || 0;
          renderCard(
            orgCards,
            item.organization.name,
            summary,
            riskClass(item.risk_level),
            {
              percent: `${Math.round(avgProgress)}%`,
              label: `avg goal progress ${avgProgress.toFixed(1)}%`,
            }
          );
        });
      }

      async function loadPortfolios() {
        clearChildren(portfolioCards);
        portfolioTotals.textContent = "Loading...";
        const data = await fetchJson("/portfolios/dashboard", {
          org_id: portfolioOrgInput.value,
          include_digest: "true",
          include_next_actions: "true",
          include_evidence: "true",
          include_retention: "true",
          next_limit: "3",
        });
        renderTotals(portfolioTotals, data.totals, [
          ["portfolios", "total_portfolios"],
          ["projects", "total_projects"],
          ["goals", "total_goals"],
          ["objectives", "total_objectives"],
          ["tasks", "total_tasks"],
          ["blocked", "blocked_tasks"],
        ]);
        data.items.forEach((item) => {
          const stats = item.stats;
          const activity = formatRelative(item.last_activity_at);
          const transition = formatRelative(item.last_transition_at);
          const digestLine = summarizeDigest(item.digest, item.last_reviewed_at);
          const nextLine = summarizeNextActions(item.next_actions);
          const evidenceLine = summarizeEvidence(item.evidence);
          const retentionLine = summarizeRetention(item.retention);
          const summary = `projects ${stats.total_projects} | goals ${stats.completed_goals}/${stats.total_goals} | objectives ${stats.completed_objectives}/${stats.total_objectives} | tasks ${stats.total_tasks} (${stats.blocked_tasks} blocked) | activity ${activity} | transition ${transition} | ${digestLine} | ${evidenceLine} | ${retentionLine} | next ${nextLine}`;
          const avgProgress = stats.avg_goal_progress || 0;
          renderCard(
            portfolioCards,
            item.portfolio.name,
            summary,
            riskClass(item.risk_level),
            {
              percent: `${Math.round(avgProgress)}%`,
              label: `avg goal progress ${avgProgress.toFixed(1)}%`,
            }
          );
        });
      }

      async function loadPrograms() {
        clearChildren(programCards);
        programTotals.textContent = "Loading...";
        const data = await fetchJson("/programs/dashboard", {
          org_id: programOrgInput.value,
          portfolio_id: programPortfolioInput.value,
          include_digest: "true",
          include_next_actions: "true",
          include_evidence: "true",
          include_retention: "true",
          next_limit: "3",
        });
        renderTotals(programTotals, data.totals, [
          ["programs", "total_programs"],
          ["projects", "total_projects"],
          ["goals", "total_goals"],
          ["objectives", "total_objectives"],
          ["tasks", "total_tasks"],
          ["blocked", "blocked_tasks"],
        ]);
        data.items.forEach((item) => {
          const stats = item.stats;
          const activity = formatRelative(item.last_activity_at);
          const transition = formatRelative(item.last_transition_at);
          const digestLine = summarizeDigest(item.digest, item.last_reviewed_at);
          const nextLine = summarizeNextActions(item.next_actions);
          const evidenceLine = summarizeEvidence(item.evidence);
          const retentionLine = summarizeRetention(item.retention);
          const summary = `projects ${stats.total_projects} | goals ${stats.completed_goals}/${stats.total_goals} | objectives ${stats.completed_objectives}/${stats.total_objectives} | tasks ${stats.total_tasks} (${stats.blocked_tasks} blocked) | activity ${activity} | transition ${transition} | ${digestLine} | ${evidenceLine} | ${retentionLine} | next ${nextLine}`;
          const avgProgress = stats.avg_goal_progress || 0;
          renderCard(
            programCards,
            item.program.name,
            summary,
            riskClass(item.risk_level),
            {
              percent: `${Math.round(avgProgress)}%`,
              label: `avg goal progress ${avgProgress.toFixed(1)}%`,
            }
          );
        });
      }

      async function loadLineage() {
        clearChildren(lineageCards);
        lineageTotals.textContent = "Loading...";
        const data = await fetchJson("/plans/lineage", {
          status: lineageStatusInput.value,
          project_id: lineageProjectInput.value,
          plan_id: lineagePlanInput.value,
          task_limit: "4",
          test_limit: "3",
        });
        renderTotals(lineageTotals, data.totals, [
          ["plans", "total_plans"],
          ["tasks", "total_tasks"],
          ["tests", "total_test_runs"],
          ["failed", "failed_test_runs"],
          ["evidence", "total_evidence"],
          ["code", "total_code_evidence"],
        ]);
        data.items.forEach((item) => {
          renderLineageCard(item);
        });
      }

      async function loadRetention() {
        clearChildren(retentionBars);
        clearChildren(retentionList);
        retentionTotals.textContent = "Loading...";

        const data = await fetchJson("/test-runs/retention", {
          limit: retentionLimitInput.value || "10",
          sort: retentionSortInput.value || "largest",
        });

        retentionTotals.textContent = `runs ${data.total_runs} | total ${formatBytes(
          data.total_bytes
        )}`;

        renderRetentionBar(
          retentionBars,
          "logs",
          data.total_log_bytes_combined,
          data.max_log_bytes
        );
        renderRetentionBar(
          retentionBars,
          "artifacts",
          data.total_artifact_bytes,
          data.max_artifact_bytes
        );

        const header = document.createElement("div");
        header.className = "retention-row header";
        header.innerHTML = `
          <div>run</div>
          <div>logs</div>
          <div>artifacts</div>
          <div>total</div>
          <div>finished</div>
          <div>missing</div>
        `;
        retentionList.appendChild(header);

        data.items.forEach((item) => {
          const row = document.createElement("div");
          row.className = "retention-row";
          row.innerHTML = `
            <span class="mono">${item.run_id.slice(0, 8)}</span>
            <span>${formatBytes(item.log_total_bytes)}</span>
            <span>${formatBytes(item.artifact_bytes)}</span>
            <span>${formatBytes(item.total_bytes)}</span>
            <span>${formatRelative(item.finished_at)}</span>
            <span>${item.artifacts_missing || "-"}</span>
          `;
          retentionList.appendChild(row);
        });
      }

      async function loadWorkSnapshot() {
        clearChildren(snapshotBody);
        snapshotTotals.textContent = "";

        const scopeId = snapshotScopeId.value;
        if (!scopeId) {
          snapshotTotals.textContent = "Enter a scope id.";
          return;
        }

        snapshotTotals.textContent = "Loading...";
        const data = await fetchJson(
          `/work-snapshots/${snapshotScopeType.value}/${scopeId}`,
          {
            task_limit: snapshotTaskLimit.value || "5",
            test_limit: snapshotTestLimit.value || "5",
          }
        );

        renderTotals(snapshotTotals, data.totals, [
          ["projects", "total_projects"],
          ["goals", "total_goals"],
          ["tasks", "total_tasks"],
          ["blocked", "blocked_tasks"],
        ]);

        const digest = data.digest || {};
        const evidence = data.evidence || {};
        const retention = data.retention || null;
        const lineageTotals = data.lineage ? data.lineage.totals : null;

        snapshotBody.appendChild(
          renderSnapshotRow(
            "Last reviewed",
            data.last_reviewed_at ? formatRelative(data.last_reviewed_at) : "never"
          )
        );
        snapshotBody.appendChild(
          renderSnapshotRow(
            "Digest",
            `tasks +${digest.tasks_created || 0} / done ${digest.tasks_completed || 0} / upd ${
              digest.tasks_updated || 0
            }`
          )
        );
        snapshotBody.appendChild(
          renderSnapshotRow(
            "Plans",
            `created ${digest.plans_created || 0} / updated ${digest.plans_updated || 0}`
          )
        );
        snapshotBody.appendChild(
          renderSnapshotRow(
            "Tests",
            `runs ${digest.test_runs || 0} / failed ${digest.failed_test_runs || 0}`
          )
        );
        snapshotBody.appendChild(
          renderSnapshotRow(
            "Evidence",
            `total ${evidence.total_count || 0} / new ${evidence.new_count || 0}`
          )
        );

        if (retention) {
          snapshotBody.appendChild(
            renderSnapshotRow(
              "Retention",
              `runs ${retention.total_runs || 0} / bytes ${formatBytes(
                retention.total_bytes || 0
              )}`
            )
          );
        }

        if (lineageTotals) {
          snapshotBody.appendChild(
            renderSnapshotRow(
              "Lineage",
              `plans ${lineageTotals.total_plans || 0} / tasks ${
                lineageTotals.total_tasks || 0
              } / tests ${lineageTotals.total_test_runs || 0} / failed ${
                lineageTotals.failed_test_runs || 0
              }`
            )
          );
        }

        if (data.recent_tasks && data.recent_tasks.length) {
          const items = data.recent_tasks.map((task) => {
            const row = document.createElement("div");
            const statusText =
              task.status +
              (task.evidence_gate && task.evidence_gate.blocked ? " • gate" : "");
            row.innerHTML = `<span>${task.title}</span><span>${statusText}</span>`;
            return row;
          });
          snapshotBody.appendChild(renderSnapshotList("Recent Tasks", items));
        }

        if (data.recent_test_runs && data.recent_test_runs.length) {
          const items = data.recent_test_runs.map((run) => {
            const status = run.success ? "pass" : "fail";
            const row = document.createElement("div");
            row.innerHTML = `<span>${run.command || "test run"}</span><span>${status}</span>`;
            return row;
          });
          snapshotBody.appendChild(renderSnapshotList("Recent Test Runs", items));
        }
      }

      async function markWorkSnapshotReviewed() {
        const scopeId = snapshotScopeId.value;
        if (!scopeId) {
          snapshotTotals.textContent = "Enter a scope id.";
          return;
        }

        await postJson(
          `/work-snapshots/${snapshotScopeType.value}/${scopeId}/review`,
          {
            reviewed_by: snapshotReviewedBy.value || null,
            note: snapshotNote.value || null,
            metadata: {},
          }
        );
        await loadWorkSnapshot();
      }

      async function loadQueues() {
        clearChildren(queueList);
        queueTotals.textContent = "Loading...";

        const data = await fetchJson("/queues/presets", {
          project_id: queueProjectInput.value,
          limit: queueLimitInput.value || "5",
        });

        const total = data.reduce((acc, item) => acc + item.total_count, 0);
        queueTotals.textContent = `queues ${data.length} | tasks ${total}`;

        data.forEach((item) => {
          const card = document.createElement("div");
          card.className = "queue-card";
          const sample = item.items
            .slice(0, 3)
            .map((task) => task.title)
            .join(", ");
          card.innerHTML = `
            <h3>${item.name} <span class="pill">${item.total_count}</span></h3>
            <p>${item.description}</p>
            <p class="mono">${sample || "No tasks"}</p>
          `;
          queueList.appendChild(card);
        });
      }

      async function loadOperatorConsole() {
        clearChildren(operatorChanged);
        clearChildren(operatorBlocked);
        clearChildren(operatorNext);
        clearChildren(operatorJumps);
        operatorTotals.textContent = "";

        const projectId = operatorProjectId.value || snapshotScopeId.value;
        if (!projectId) {
          operatorTotals.textContent = "Enter a project id.";
          return;
        }

        const [overview, observability] = await Promise.all([
          fetchJson(`/projects/${projectId}/operator-overview`, {
            task_limit: "5",
            test_limit: "5",
            queue_limit: "3",
            lineage_limit: "3",
            history_limit: "5",
            include_timeline: "true",
            view: "overview",
          }),
          fetchJson("/observability/overview", {
            queue_limit: "3",
            lineage_limit: "5",
            retention_limit: "5",
            timeline_days: "7",
          }),
        ]);

        operatorTotals.textContent = `${overview.project.name} | health ${Math.round(
          (overview.health_score || 0) * 100
        )}% | blocked ${overview.stats?.blocked_tasks || 0}`;

        const daily = overview.daily || {};
        const snapshot = daily.snapshot || {};
        const digest = snapshot.digest || {};
        const reviewPreview = snapshot.review_history_preview || [];
        const lastReview = reviewPreview.length > 0 ? reviewPreview[0].reviewed_at : null;
        renderOperatorItem(
          operatorChanged,
          "Digest Delta",
          `tasks +${digest.tasks_created || 0} / done ${digest.tasks_completed || 0} / upd ${digest.tasks_updated || 0}`
        );
        renderOperatorItem(
          operatorChanged,
          "Last Review",
          lastReview ? formatRelative(lastReview) : "No review checkpoint yet"
        );
        renderOperatorItem(
          operatorChanged,
          "Recent Transitions",
          daily.recent_transitions && daily.recent_transitions.length
            ? `${daily.recent_transitions.length} recent transition(s) in scope`
            : "No recent transition history in current window"
        );

        const blockers = daily.blockers || [];
        if (blockers.length === 0) {
          renderOperatorItem(operatorBlocked, "Blocked Work", "No active blockers in scoped daily view");
        } else {
          blockers.slice(0, 3).forEach((task) => {
            renderOperatorItem(
              operatorBlocked,
              task.title || task.id,
              `${task.status}${task.project_name ? ` • ${task.project_name}` : ""}`
            );
          });
        }
        const topRisk = observability.top_risks_now && observability.top_risks_now[0];
        if (topRisk) {
          renderOperatorItem(operatorBlocked, topRisk.title, topRisk.summary || topRisk.why || "");
        }

        const nextActions = daily.next_actions || [];
        if (nextActions.length === 0) {
          renderOperatorItem(operatorNext, "Next Action", "No ready next actions in scoped daily view");
        } else {
          nextActions.slice(0, 3).forEach((task) => {
            renderOperatorItem(
              operatorNext,
              task.title || task.id,
              `${task.status}${task.project_name ? ` • ${task.project_name}` : ""}`
            );
          });
        }
        const recommendedAction =
          observability.recommended_actions && observability.recommended_actions[0];
        if (recommendedAction) {
          renderOperatorItem(
            operatorNext,
            recommendedAction.title,
            recommendedAction.why || recommendedAction.api_call || ""
          );
        }

        renderOperatorJump(operatorJumps, "Project Summary", overview.links?.project_summary);
        renderOperatorJump(operatorJumps, "Daily Review API", overview.links?.daily);
        renderOperatorJump(operatorJumps, "Plan Lineage API", overview.links?.lineage);
        renderOperatorJump(operatorJumps, "History Bundle API", overview.links?.history_bundle);
        renderOperatorJump(operatorJumps, "Observability API", observability.links?.self);
      }

      async function refreshAll() {
        persistSettings();
        try {
          await loadOperatorConsole();
          await loadOrganizations();
          await loadPortfolios();
          await loadPrograms();
          await loadLineage();
          await loadRetention();
          await loadWorkSnapshot();
          await loadQueues();
          setStatus("connected", true);
        } catch (error) {
          setStatus("error");
          console.error(error);
        }
      }

      function scheduleRefresh() {
        if (refreshTimer) {
          clearInterval(refreshTimer);
          refreshTimer = null;
        }
        const seconds = Number(autoRefreshInput.value);
        if (Number.isFinite(seconds) && seconds > 0) {
          refreshTimer = setInterval(refreshAll, seconds * 1000);
        }
      }

      document.getElementById("refresh-all").addEventListener("click", refreshAll);
      document
        .getElementById("operator-refresh")
        .addEventListener("click", loadOperatorConsole);
      document
        .getElementById("portfolio-refresh")
        .addEventListener("click", loadPortfolios);
      document
        .getElementById("program-refresh")
        .addEventListener("click", loadPrograms);
      document
        .getElementById("lineage-refresh")
        .addEventListener("click", loadLineage);
      document
        .getElementById("retention-refresh")
        .addEventListener("click", loadRetention);
      document
        .getElementById("snapshot-refresh")
        .addEventListener("click", loadWorkSnapshot);
      document
        .getElementById("snapshot-review")
        .addEventListener("click", markWorkSnapshotReviewed);
      document
        .getElementById("queue-refresh")
        .addEventListener("click", loadQueues);

      apiBaseInput.addEventListener("change", () => {
        persistSettings();
        refreshAll();
      });
      apiKeyInput.addEventListener("change", () => {
        persistSettings();
        refreshAll();
      });
      autoRefreshInput.addEventListener("change", () => {
        persistSettings();
        scheduleRefresh();
      });

      loadSettings();
      scheduleRefresh();
      refreshAll();
    </script>
  </body>
</html>"""
    return HTMLResponse(html)
