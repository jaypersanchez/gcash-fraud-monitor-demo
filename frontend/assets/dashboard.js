const urlParams = new URLSearchParams(window.location.search || "");
const SAME_ORIGIN_API = `${window.location.origin}/api`;
const API_BASE =
  urlParams.get("apiBase") ||
  window.API_BASE ||
  localStorage.getItem("API_BASE") ||
  (window.location.hostname.includes("ngrok-free.dev") ? SAME_ORIGIN_API : "http://localhost:5005/api");

const timeRangeSelect = document.getElementById("timeRange");
const severitySelect = document.getElementById("severity");
const ruleSelect = document.getElementById("ruleId");
const refreshBtn = document.getElementById("refreshDashboard");
const kpiAlertsTotal = document.getElementById("kpi-alerts-total");
const kpiAlertsOpen = document.getElementById("kpi-alerts-open");
const kpiCasesOpen = document.getElementById("kpi-cases-open");
const kpiSuspects = document.getElementById("kpi-suspects");
const charts = {};

const skeletonBlocks = document.querySelectorAll("[data-skeleton]");

const severityLabel = (value) => {
  const map = { CRITICAL: "high", HIGH: "high", MEDIUM: "medium", LOW: "low" };
  return map[value] || "low";
};

function setLoading(isLoading) {
  skeletonBlocks.forEach((block) => {
    if (isLoading) {
      block.classList.add("is-loading");
    } else {
      block.classList.remove("is-loading");
    }
  });
}

async function loadRuleOptions() {
  try {
    const res = await fetch(`${API_BASE}/rules`);
    const data = await res.json();
    if (Array.isArray(data)) {
      data.forEach((rule) => {
        const opt = document.createElement("option");
        opt.value = rule.name || rule.id;
        opt.textContent = rule.name || `Rule ${rule.id}`;
        ruleSelect.appendChild(opt);
      });
    }
  } catch (err) {
    console.warn("Rule fetch failed, using defaults.", err);
  }
}

function renderKpis(kpis) {
  kpiAlertsTotal.textContent = kpis.alerts_total ?? 0;
  kpiAlertsOpen.textContent = kpis.alerts_open ?? 0;
  kpiCasesOpen.textContent = kpis.cases_open ?? 0;
  kpiSuspects.textContent = kpis.suspects_flagged ?? 0;
}

function formatTs(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleString(undefined, { hour: "2-digit", minute: "2-digit", month: "short", day: "numeric" });
}

function buildOrUpdateChart(key, ctx, config) {
  if (charts[key]) {
    charts[key].data = config.data;
    charts[key].options = { ...charts[key].options, ...config.options };
    charts[key].update();
    return;
  }
  charts[key] = new Chart(ctx, config);
}

function renderCharts(chartsData) {
  const alertsByHour = chartsData.alerts_by_hour || [];
  const severityCounts = chartsData.alerts_by_severity || [];
  const ruleHits = chartsData.rule_hits || [];

  buildOrUpdateChart("alertsByHour", document.getElementById("chart-alerts-by-hour"), {
    type: "line",
    data: {
      labels: alertsByHour.map((d) => formatTs(d.ts)),
      datasets: [
        {
          label: "Alerts",
          data: alertsByHour.map((d) => d.count || 0),
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59, 130, 246, 0.12)",
          tension: 0.3,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, grid: { color: "#e5e7eb" } },
        x: { grid: { display: false } },
      },
    },
  });

  buildOrUpdateChart("alertsBySeverity", document.getElementById("chart-alerts-by-severity"), {
    type: "doughnut",
    data: {
      labels: severityCounts.map((d) => d.severity),
      datasets: [
        {
          data: severityCounts.map((d) => d.count || 0),
          backgroundColor: ["#ef4444", "#f59e0b", "#22c55e", "#3b82f6"],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
    },
  });

  buildOrUpdateChart("ruleHits", document.getElementById("chart-rule-hits"), {
    type: "bar",
    data: {
      labels: ruleHits.map((d) => d.rule_id || d.ruleId || "Unknown"),
      datasets: [
        {
          label: "Hits",
          data: ruleHits.map((d) => d.count || 0),
          backgroundColor: "rgba(34, 197, 94, 0.6)",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, grid: { color: "#e5e7eb" } },
        x: { grid: { display: false } },
      },
    },
  });
}

function renderTopSuspects(rows) {
  const tbody = document.querySelector("#top-suspects tbody");
  tbody.innerHTML = "";
  if (!rows || !rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.textContent = "No suspects available for the current filters.";
    td.classList.add("muted");
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.id || "-"}</td>
      <td>${row.risk_score ?? "-"}</td>
      <td>${row.flags ?? 0}</td>
      <td>${row.degree ?? 0}</td>
      <td>${row.last_seen || ""}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadDashboard() {
  setLoading(true);
  const params = new URLSearchParams({
    time_range: timeRangeSelect.value,
    severity: severitySelect.value,
    rule_id: ruleSelect.value,
  });
  try {
    const res = await fetch(`${API_BASE}/analytics/dashboard?${params.toString()}`);
    const data = await res.json();
    renderKpis(data.kpis || {});
    renderCharts(data.charts || {});
    renderTopSuspects(data.tables?.top_suspects || []);
  } catch (err) {
    console.error("Failed to load dashboard data", err);
  } finally {
    setLoading(false);
  }
}

function wireFilters() {
  [timeRangeSelect, severitySelect, ruleSelect].forEach((el) => {
    if (el) el.addEventListener("change", loadDashboard);
  });
  if (refreshBtn) refreshBtn.addEventListener("click", loadDashboard);
}

document.addEventListener("DOMContentLoaded", () => {
  wireFilters();
  loadRuleOptions();
  loadDashboard();
});
