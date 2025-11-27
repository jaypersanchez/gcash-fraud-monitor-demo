const API_BASE = "http://localhost:5005/api";

const alertsBody = document.getElementById("alerts-body");
const alertsEmpty = document.getElementById("alerts-empty");
const refreshBtn = document.getElementById("refresh-alerts");
const alertsNav = document.getElementById("alerts-nav");
const alertsSection = document.getElementById("alerts-section");
const neoTestButton = document.getElementById("neo-test");
const neoStatus = document.getElementById("neo-status");
const graphSvg = document.getElementById("graph-svg");
const loadGraphBtn = document.getElementById("load-graph");
const riskSlider = document.getElementById("riskThreshold");
const limitInput = document.getElementById("limitInput");
const riskValue = document.getElementById("riskValue");
const ruleSelect = document.getElementById("ruleSelect");
const minRiskyInput = document.getElementById("minRisky");
const selectionInfo = document.getElementById("selection-info");
const flagAccountBtn = document.getElementById("flag-account");
const flagDeviceBtn = document.getElementById("flag-device");
const actionStatus = document.getElementById("action-status");

let alertsCache = [];
let selectedAccountId = null;
let selectedDeviceId = null;
let lastParams = "";
let selectedRuleKey = null;

const severityClass = (severity) => {
  const map = {
    CRITICAL: "badge-critical",
    HIGH: "badge-high",
    MEDIUM: "badge-medium",
    LOW: "badge-low",
    Critical: "badge-critical",
    High: "badge-high",
    Medium: "badge-medium",
  };
  return map[severity] || "badge-low";
};

function getRule() {
  return (ruleSelect && ruleSelect.value) || "R1";
}

function getRiskThreshold() {
  if (riskSlider) return parseFloat(riskSlider.value) || 0.8;
  return 0.8;
}

function getLimit() {
  if (limitInput) return parseInt(limitInput.value || "50", 10);
  return 50;
}

function getMinRisky() {
  if (minRiskyInput) return parseInt(minRiskyInput.value || "2", 10);
  return 2;
}

async function fetchAlerts() {
  setLoadingState(true);
  try {
    const params = new URLSearchParams();
    const rule = getRule();
    if (rule === "R1") {
      params.append("riskThreshold", getRiskThreshold());
    } else if (rule === "R2") {
      params.append("highRiskThreshold", getRiskThreshold());
      params.append("minRiskyAccounts", getMinRisky());
    } else if (rule === "R3" || rule === "R7" || rule === "ALL") {
      params.append("riskThreshold", getRiskThreshold());
      params.append("minRiskyAccounts", getMinRisky());
    }
    params.append("limit", getLimit());
    lastParams = params.toString();
    let endpoint = "/neo-alerts/r1";
    if (rule === "R2") endpoint = "/neo-alerts/r2";
    if (rule === "R3") endpoint = "/neo-alerts/r3";
    if (rule === "R7") endpoint = "/neo-alerts/r7";
    if (rule === "ALL") endpoint = "/neo-alerts/search";
    const res = await fetch(`${API_BASE}${endpoint}?${params.toString()}`);
    const data = await res.json();
    renderAlerts(data);
    if (data && data.length) {
      const first = data[0];
      const anchorRule = first.ruleKey || rule;
      selectedRuleKey = anchorRule;
      if (anchorRule === "R2") {
        selectedDeviceId = first.deviceId;
        selectedAccountId = null;
      } else {
        selectedAccountId = first.accountId;
        selectedDeviceId = null;
      }
      loadGraphForSelected();
    } else if (neoStatus) {
      neoStatus.textContent = "No alerts to load graph.";
    }
  } catch (err) {
    console.error("Failed to fetch alerts", err);
  } finally {
    setLoadingState(false);
  }
}

function renderAlerts(alerts) {
  alertsBody.innerHTML = "";
  alertsEmpty.style.display = alerts.length ? "none" : "block";
  alertsCache = alerts;

  alerts.forEach((alert) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><span class="badge ${severityClass(alert.severity)}">${alert.severity}</span></td>
      <td class="muted">#${alert.id}</td>
      <td>${alert.rule || "Account Risk"}</td>
      <td>${alert.summary}</td>
      <td><span class="status-chip">${alert.status}</span></td>
      <td class="muted">${alert.created ? new Date(alert.created).toLocaleString() : ""}</td>
    `;
    row.addEventListener("click", () => {
      const rowRule = alert.ruleKey || getRule();
      if (rowRule === "R1" || rowRule === "R3" || rowRule === "R7") {
        selectedAccountId = alert.accountId;
        selectedDeviceId = null;
        if (neoStatus) neoStatus.textContent = `Selected account ${alert.accountId} (${rowRule})`;
      } else if (rowRule === "R2") {
        selectedDeviceId = alert.deviceId;
        selectedAccountId = null;
        if (neoStatus) neoStatus.textContent = `Selected device ${alert.deviceId} (${rowRule})`;
      } else {
        selectedAccountId = alert.accountId;
        selectedDeviceId = null;
        if (neoStatus) neoStatus.textContent = `Selected account ${alert.accountId} (${rowRule})`;
      }
      selectedRuleKey = rowRule;
      Array.from(alertsBody.children).forEach((tr) => tr.classList.remove("selected-row"));
      row.classList.add("selected-row");
      updateSelectionInfo();
      loadGraphForSelected();
    });
    alertsBody.appendChild(row);
  });
}

async function refreshAlerts() {
  refreshBtn.textContent = "Refreshing...";
  refreshBtn.disabled = true;
  try {
    await fetchAlerts();
  } catch (err) {
    console.error("Failed to refresh alerts", err);
  } finally {
    refreshBtn.textContent = "Refresh Alerts";
    refreshBtn.disabled = false;
  }
}
function setLoadingState(isLoading) {
  refreshBtn.textContent = isLoading ? "Loading..." : "Refresh Alerts";
  refreshBtn.disabled = isLoading;
}

refreshBtn.addEventListener("click", refreshAlerts);

alertsNav.addEventListener("click", () => {
  alertsSection.scrollIntoView({ behavior: "smooth" });
});

async function testNeo4j() {
  if (!neoStatus) return;
  neoStatus.textContent = "Testing Neo4j connectivity...";
  try {
    const res = await fetch(`${API_BASE}/neo4j/health`);
    const data = await res.json();
    if (res.ok && data.status === "ok") {
      neoStatus.textContent = "Neo4j connection successful.";
    } else {
      neoStatus.textContent = `Neo4j error: ${data.message || "Unknown error"}`;
    }
  } catch (err) {
    neoStatus.textContent = "Neo4j connectivity check failed.";
    console.error(err);
  }
}

if (neoTestButton) {
  neoTestButton.addEventListener("click", testNeo4j);
}

async function loadGraphForSelected() {
  const rule = getRule();
  const accountId = selectedAccountId || (alertsCache[0] && alertsCache[0].accountId);
  const deviceId = selectedDeviceId || (alertsCache[0] && alertsCache[0].deviceId);
  const anchor = rule === "R2" ? deviceId : accountId;
  if (!anchor) {
    if (neoStatus) neoStatus.textContent = "No anchor found on alert.";
    return;
  }
  const paramsDisplay = lastParams ? ` (filters: ${lastParams})` : "";
  const ruleLabel = selectedRuleKey || rule;
  neoStatus.textContent = `Loading graph for ${anchor} (${ruleLabel})${paramsDisplay}...`;
  try {
    const endpoint = rule === "R2" ? "/neo4j/graph/device/" : "/neo4j/graph/account/";
    const res = await fetch(`${API_BASE}${endpoint}${encodeURIComponent(anchor)}`);
    const data = await res.json();
    if (!res.ok) {
      neoStatus.textContent = data.message || "Graph load failed.";
      return;
    }
    neoStatus.textContent = `Graph loaded for ${anchor} (${ruleLabel}).`;
    renderGraph(data.nodes || [], data.edges || []);
  } catch (err) {
    neoStatus.textContent = "Graph load failed.";
    console.error(err);
  }
}

function renderGraph(nodes, edges) {
  if (!graphSvg) return;
  const width = graphSvg.clientWidth || 600;
  const height = 320;
  graphSvg.setAttribute("width", width);
  graphSvg.setAttribute("height", height);
  graphSvg.innerHTML = "";

  const accounts = nodes.filter((n) => n.type === "Account");
  const devices = nodes.filter((n) => n.type === "Device");
  const txs = nodes.filter((n) => n.type === "Transaction");

  const layout = (arr, y) => arr.map((n, idx) => ({ ...n, x: 80 + idx * (width / Math.max(arr.length, 1)), y }));
  const accPlaced = layout(accounts, 60);
  const devPlaced = layout(devices, 160);
  const txPlaced = layout(txs, 260);
  const placedMap = {};
  [...accPlaced, ...devPlaced, ...txPlaced].forEach((n) => (placedMap[n.id] = n));

  const svgNS = "http://www.w3.org/2000/svg";

  const defs = document.createElementNS(svgNS, "defs");
  const marker = document.createElementNS(svgNS, "marker");
  marker.setAttribute("id", "arrow");
  marker.setAttribute("markerWidth", "10");
  marker.setAttribute("markerHeight", "10");
  marker.setAttribute("refX", "5");
  marker.setAttribute("refY", "3");
  marker.setAttribute("orient", "auto");
  const path = document.createElementNS(svgNS, "path");
  path.setAttribute("d", "M0,0 L0,6 L6,3 z");
  path.setAttribute("fill", "#a5b4d0");
  marker.appendChild(path);
  defs.appendChild(marker);
  graphSvg.appendChild(defs);

  edges.forEach((e) => {
    const src = placedMap[e.source];
    const tgt = placedMap[e.target];
    if (!src || !tgt) return;
    const line = document.createElementNS(svgNS, "line");
    line.setAttribute("x1", src.x);
    line.setAttribute("y1", src.y);
    line.setAttribute("x2", tgt.x);
    line.setAttribute("y2", tgt.y);
    line.setAttribute("stroke", "#a5b4d0");
    line.setAttribute("stroke-width", "2");
    line.setAttribute("marker-end", "url(#arrow)");
    if (e.label) {
      const title = document.createElementNS(svgNS, "title");
      title.textContent = `${e.type}${e.label ? " - " + e.label : ""}`;
      line.appendChild(title);
    }
    graphSvg.appendChild(line);
  });

  const drawNode = (n, color) => {
    const g = document.createElementNS(svgNS, "g");
    const circle = document.createElementNS(svgNS, "circle");
    circle.setAttribute("cx", n.x);
    circle.setAttribute("cy", n.y);
    circle.setAttribute("r", 14);
    circle.setAttribute("fill", color);
    circle.setAttribute("stroke", "#0c1a36");
    circle.setAttribute("stroke-width", "1");
    g.appendChild(circle);
    const text = document.createElementNS(svgNS, "text");
    text.setAttribute("x", n.x);
    text.setAttribute("y", n.y + 28);
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("font-size", "10");
    text.setAttribute("fill", "#0c1a36");
    text.textContent = n.label;
    g.appendChild(text);
    graphSvg.appendChild(g);
  };

  accPlaced.forEach((n) => drawNode(n, n.isSubject ? "#ff8c42" : "#0077f6"));
  devPlaced.forEach((n) => drawNode(n, n.isSubject ? "#ff8c42" : "#01c2c5"));
  txPlaced.forEach((n) => drawNode(n, "#ffd166"));
}

if (loadGraphBtn) {
  loadGraphBtn.addEventListener("click", loadGraphForSelected);
}

if (riskSlider && riskValue) {
  riskSlider.addEventListener("input", () => {
    riskValue.textContent = Number(riskSlider.value).toFixed(2);
  });
}

if (limitInput) {
  limitInput.addEventListener("change", () => {
    if (limitInput.value === "" || Number(limitInput.value) < 1) {
      limitInput.value = "50";
    }
  });
}

if (minRiskyInput) {
  minRiskyInput.addEventListener("change", () => {
    if (minRiskyInput.value === "" || Number(minRiskyInput.value) < 1) {
      minRiskyInput.value = "2";
    }
  });
}

if (ruleSelect) {
  ruleSelect.addEventListener("change", () => {
    selectedAccountId = null;
    selectedDeviceId = null;
    selectedRuleKey = null;
    fetchAlerts();
  });
}

function updateSelectionInfo() {
  const ruleLabel = selectedRuleKey || getRule();
  const anchor = ruleLabel === "R2" ? selectedDeviceId : selectedAccountId;
  if (selectionInfo) {
    selectionInfo.textContent = anchor ? `Selected ${anchor} (${ruleLabel})` : "No selection yet.";
  }
}

async function flagAnchor() {
  const ruleLabel = selectedRuleKey || getRule();
  let endpoint = null;
  let anchor = null;
  if (ruleLabel === "R2") {
    anchor = selectedDeviceId;
    endpoint = anchor ? `/neo4j/flag/device/${encodeURIComponent(anchor)}` : null;
  } else {
    anchor = selectedAccountId;
    endpoint = anchor ? `/neo4j/flag/account/${encodeURIComponent(anchor)}` : null;
  }
  if (!endpoint) {
    if (actionStatus) actionStatus.textContent = "No selection to flag.";
    return;
  }
  actionStatus.textContent = "Flagging...";
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      actionStatus.textContent = data.message || "Flag failed.";
      return;
    }
    actionStatus.textContent = `Flagged ${anchor}. Refreshing alerts...`;
    await fetchAlerts();
  } catch (err) {
    actionStatus.textContent = "Flag failed.";
    console.error(err);
  }
}

if (flagAccountBtn) {
  flagAccountBtn.addEventListener("click", flagAnchor);
}
if (flagDeviceBtn) {
  flagDeviceBtn.addEventListener("click", flagAnchor);
}

updateSelectionInfo();
fetchAlerts();
