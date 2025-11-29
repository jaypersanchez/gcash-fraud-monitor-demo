const API_BASE = "http://localhost:5005/api";

const alertsBody = document.getElementById("alerts-body");
const alertsEmpty = document.getElementById("alerts-empty");
const refreshBtn = document.getElementById("refresh-alerts");
const alertsNav = document.getElementById("alerts-nav");
const alertsSection = document.getElementById("alerts-section");
const neoTestButton = document.getElementById("neo-test");
const neoStatus = document.getElementById("neo-status");
const graphContainer = document.getElementById("graph-container");
const loadGraphBtn = document.getElementById("load-graph");
const riskSlider = document.getElementById("riskThreshold");
const limitInput = document.getElementById("limitInput");
const riskValue = document.getElementById("riskValue");
const ruleSelect = document.getElementById("ruleSelect");
const minRiskyInput = document.getElementById("minRisky");
const selectionInfo = document.getElementById("selection-info");
const flagAccountBtn = document.getElementById("flag-account");
const flagDeviceBtn = document.getElementById("flag-device");
const loadDeviceBtn = document.getElementById("load-device");
const deviceSearch = document.getElementById("device-search");
const actionStatus = document.getElementById("action-status");
const contextInfo = document.getElementById("context-info");
const noteInput = document.getElementById("note-input");
const addNoteBtn = document.getElementById("add-note");
const noteList = document.getElementById("note-list");
const noteCount = document.getElementById("note-count");
const openWorkspaceBtn = document.getElementById("open-workspace");
const openImporterBtn = document.getElementById("open-importer");
const openBloomBtn = document.getElementById("open-bloom");
const caseStatus = document.getElementById("case-status");
const caseActionStatus = document.getElementById("case-action-status");
const caseBlockBtn = document.getElementById("case-block");
const caseSafeBtn = document.getElementById("case-safe");
const caseEscalateBtn = document.getElementById("case-escalate");

let alertsCache = [];
let selectedAccountId = null;
let selectedDeviceId = null;
let lastParams = "";
let selectedRuleKey = null;
let selectedAlert = null;
const notesByAnchor = {};
const actionsByAnchor = {};
let graphTooltip = null;

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
      selectedAlert = first;
      selectedRuleKey = anchorRule;
      if (anchorRule === "R2") {
        selectedDeviceId = first.deviceId;
        selectedAccountId = null;
      } else {
        selectedAccountId = first.accountId;
        selectedDeviceId = null;
      }
      updateSelectionInfo();
      renderContext();
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
        if (neoStatus) neoStatus.textContent = `Selected identifier ${alert.deviceId} (${rowRule})`;
      } else {
        selectedAccountId = alert.accountId;
        selectedDeviceId = null;
        if (neoStatus) neoStatus.textContent = `Selected account ${alert.accountId} (${rowRule})`;
      }
      selectedRuleKey = rowRule;
      selectedAlert = alert;
      Array.from(alertsBody.children).forEach((tr) => tr.classList.remove("selected-row"));
      row.classList.add("selected-row");
      updateSelectionInfo();
      renderContext();
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
  const ruleLabel = selectedRuleKey || rule;
  const accountId = selectedAccountId || (alertsCache[0] && alertsCache[0].accountId);
  const deviceId = selectedDeviceId || (alertsCache[0] && alertsCache[0].deviceId);
  const anchor = ruleLabel === "R2" ? deviceId : accountId;
  if (!anchor) {
    if (neoStatus) neoStatus.textContent = "No anchor found on alert.";
    return;
  }
  const paramsDisplay = lastParams ? ` (filters: ${lastParams})` : "";
  neoStatus.textContent = `Loading graph for ${anchor} (${ruleLabel})${paramsDisplay}...`;
  try {
    const endpoint = ruleLabel === "R2" ? "/neo4j/graph/identifier/" : "/neo4j/graph/account/";
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
  if (!graphContainer) return;
  if (!graphContainer || typeof cytoscape === "undefined") return;

  if (!graphTooltip) {
    graphTooltip = document.createElement("div");
    graphTooltip.id = "graph-tooltip";
    Object.assign(graphTooltip.style, {
      position: "fixed",
      display: "none",
      padding: "6px 10px",
      background: "#0c1a36",
      color: "#f8fbff",
      borderRadius: "6px",
      fontSize: "12px",
      boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
      zIndex: 9999,
      pointerEvents: "none",
      maxWidth: "240px",
      lineHeight: "1.3",
    });
    document.body.appendChild(graphTooltip);
  }

  const cy = cytoscape({
    container: graphContainer,
    elements: [
      ...nodes.map((n) => {
        const icon = (() => {
          if (n.type === "Account") return "👤";
          if (n.type === "Transaction") return "💸";
          if (n.deviceType === "Email") return "📧";
          if (n.deviceType === "Phone") return "📱";
          if (n.deviceType === "SSN") return "🪪";
          return "🔗";
        })();
        const displayLabel = `${icon} ${n.label}`;
        return {
          data: {
            id: n.id,
            label: displayLabel,
            type: n.type,
            isSubject: !!n.isSubject,
            isFlagged: !!n.isFlagged,
          },
        };
      }),
      ...edges.map((e, idx) => ({
        data: {
          id: `e-${idx}-${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          label: e.label || e.type,
          type: e.type,
        },
      })),
    ],
    layout: {
      name: "cose",
      padding: 40,
      animate: false,
      idealEdgeLength: 160,
      nodeRepulsion: 12000,
    },
    style: [
      {
        selector: "node",
        style: {
          "background-color": "#0077f6",
          "border-color": "#0c1a36",
          "border-width": 1,
          label: "data(label)",
          color: "#0c1a36",
          "font-size": 9,
          "text-outline-color": "#f8fbff",
          "text-outline-width": 2,
          "text-valign": "center",
          "text-halign": "center",
          "text-wrap": "wrap",
          "text-max-width": 110,
          "text-background-color": "#f8fbff",
          "text-background-opacity": 0.9,
          "text-background-shape": "roundrectangle",
          "text-background-padding": 2,
        },
      },
      {
        selector: "node[type = 'Device']",
        style: { "background-color": "#01c2c5", shape: "diamond" },
      },
      {
        selector: "node[type = 'Transaction']",
        style: { "background-color": "#ffd166", shape: "round-rectangle" },
      },
      {
        selector: "node[?isFlagged]",
        style: {
          "background-color": "#e63946",
          "border-color": "#8b1b1b",
          "border-width": 2,
          color: "#f8fbff",
          "text-outline-color": "#8b1b1b",
          "text-outline-width": 2,
        },
      },
      {
        selector: "node[?isSubject]",
        style: { "background-color": "#ff8c42", "border-width": 2 },
      },
      {
        selector: ".faded",
        style: {
          opacity: 0.15,
        },
      },
      {
        selector: "edge",
        style: {
          width: 2,
          "line-color": "#a5b4d0",
          "target-arrow-color": "#a5b4d0",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          label: "data(label)",
          "font-size": 8,
          color: "#627089",
          "text-outline-color": "#f8fbff",
          "text-outline-width": 1,
          "text-rotation": "autorotate",
          "text-background-color": "#f8fbff",
          "text-background-opacity": 0.8,
          "text-background-padding": 1,
        },
      },
    ],
  });

  const focusNode = (nodeEle) => {
    if (!nodeEle) return;
    const neighborhood = nodeEle.closedNeighborhood();
    cy.elements().removeClass("faded");
    cy.elements().not(neighborhood).addClass("faded");
    cy.fit(neighborhood, 80);
  };

  cy.on("tap", "node", (evt) => {
    const node = evt.target.data();
    // Only drill into 13+ digit account-like IDs; skip banks/merchants/etc.
    const looksLikeAccount = node.type === "Account" && /^[0-9]{13,}$/.test(node.id);
    const looksLikeDevice = node.type === "Device";
    focusNode(evt.target);
    if (looksLikeAccount) {
      selectedAccountId = node.id;
      selectedDeviceId = null;
      selectedRuleKey = selectedRuleKey || getRule();
      if (neoStatus) neoStatus.textContent = `Selected account ${node.id} (drill-down)`;
      updateSelectionInfo();
      loadGraphForSelected();
    } else if (looksLikeDevice) {
      selectedDeviceId = node.id;
      selectedAccountId = null;
      selectedRuleKey = "R2";
      if (neoStatus) neoStatus.textContent = `Selected identifier ${node.id} (R2)`;
      updateSelectionInfo();
      loadGraphForSelected();
    }
  });

  cy.on("tap", (evt) => {
    if (evt.target === cy) {
      cy.elements().removeClass("faded");
      cy.fit();
    }
  });

  const hideTooltip = () => {
    if (graphTooltip) graphTooltip.style.display = "none";
  };

  cy.on("mouseover", "node", (evt) => {
    if (!graphTooltip) return;
    const d = evt.target.data();
    const rect = graphContainer.getBoundingClientRect();
    const pos = evt.renderedPosition || { x: 0, y: 0 };
    const lines = [`${d.type}: ${d.label}`];
    const type = d.type || "";
    const label = d.label || "";
    const flagText = d.isFlagged ? "<br/><strong style='color:#ffd166;'>Flagged</strong>" : "";
    graphTooltip.innerHTML = `${type}: ${label}${flagText}`;
    graphTooltip.style.left = `${rect.left + pos.x + 12}px`;
    graphTooltip.style.top = `${rect.top + pos.y + 12}px`;
    graphTooltip.style.display = "block";
  });

  cy.on("mouseout", "node", hideTooltip);
  cy.on("pan zoom", hideTooltip);

  cy.zoomingEnabled(true);
  cy.panningEnabled(true);
  cy.fit();
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
    const noun = ruleLabel === "R2" ? "identifier" : "account";
    selectionInfo.textContent = anchor ? `Selected ${noun} ${anchor} (${ruleLabel})` : "No selection yet.";
  }
  renderContext();
}

function currentAnchorKey() {
  const ruleLabel = selectedRuleKey || getRule();
  const anchor = ruleLabel === "R2" ? selectedDeviceId : selectedAccountId;
  return anchor ? `${ruleLabel}:${anchor}` : null;
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

if (addNoteBtn) {
  addNoteBtn.addEventListener("click", async () => {
    const anchor = (selectedRuleKey === "R2" ? selectedDeviceId : selectedAccountId) || (selectedAlert && (selectedAlert.deviceId || selectedAlert.accountId));
    if (!anchor) {
      if (actionStatus) actionStatus.textContent = "No selection to add note.";
      return;
    }
    const note = (noteInput && noteInput.value.trim()) || "";
    if (!note) return;
    const key = `${selectedRuleKey || getRule()}:${anchor}`;
    try {
      const res = await fetch(`${API_BASE}/investigator/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          anchor_id: anchor,
          anchor_type: (selectedRuleKey || getRule()) === "R2" ? "DEVICE" : "ACCOUNT",
          rule_key: selectedRuleKey || getRule(),
          note,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (actionStatus) actionStatus.textContent = data.message || "Note failed.";
        return;
      }
      if (!notesByAnchor[key]) notesByAnchor[key] = [];
      notesByAnchor[key].push({ text: note, ts: data.created_at || new Date().toISOString() });
      noteInput.value = "";
      renderNotes(key);
      if (actionStatus) actionStatus.textContent = "Note saved.";
    } catch (err) {
      if (actionStatus) actionStatus.textContent = "Note failed.";
      console.error(err);
    }
  });
}

if (openWorkspaceBtn) {
  openWorkspaceBtn.addEventListener("click", () => {
    window.open("https://workspace.neo4j.io", "_blank");
  });
}
if (openImporterBtn) {
  openImporterBtn.addEventListener("click", () => {
    window.open("https://data-importer.neo4j.io", "_blank");
  });
}
if (openBloomBtn) {
  openBloomBtn.addEventListener("click", () => {
    // Use protocol handler for Neo4j Desktop Bloom
    window.location.href = "neo4j://graphapps/neo4j-bloom";
  });
}

function renderContext() {
  if (!contextInfo) return;
  const ruleLabel = selectedRuleKey || getRule();
  const a = selectedAlert || {};
  const anchor = ruleLabel === "R2" ? (selectedDeviceId || a.deviceId) : (selectedAccountId || a.accountId);
  if (!anchor) {
    contextInfo.textContent = "No context available.";
    renderNotes(null);
    return;
  }
  let lines = [];
  lines.push(`Rule: ${a.rule || ruleLabel}`);
  lines.push(`Anchor: ${anchor}`);
  const statusEntry = actionsByAnchor[currentAnchorKey()] || { status: "Open" };
  if (caseStatus) caseStatus.textContent = `Status: ${statusEntry.status}`;
  if (ruleLabel === "R1") {
    lines.push(`Risk: ${a.riskScore ?? "-"}`);
    lines.push(`is_fraud: ${a.isFraud}`);
  }
  if (ruleLabel === "R2") {
    lines.push(`Risky accounts: ${a.riskyAccounts ?? "-"}`);
    lines.push(`Total accounts: ${a.totalAccounts ?? "-"}`);
  }
  if (ruleLabel === "R3") {
    lines.push(`Ring size: ${a.ringSize ?? "-"}`);
    lines.push(`Risk: ${a.riskScore ?? "-"}`);
  }
  if (ruleLabel === "R7") {
    lines.push(`Risky senders: ${a.riskySenders ?? "-"}`);
    lines.push(`Tx count: ${a.txCount ?? "-"}`);
    lines.push(`Risk: ${a.riskScore ?? "-"}`);
  }
  contextInfo.textContent = lines.join(" | ");

  const key = `${ruleLabel}:${anchor}`;
  renderNotes(key);
}

function renderNotes(key) {
  if (!noteList || !noteCount) return;
  noteList.innerHTML = "";
  if (!key || !notesByAnchor[key] || !notesByAnchor[key].length) {
    noteCount.textContent = "0 note(s)";
    return;
  }
  const notes = notesByAnchor[key];
  noteCount.textContent = `${notes.length} note(s)`;
  notes.forEach((n) => {
    const li = document.createElement("li");
    li.textContent = `${new Date(n.ts).toLocaleString()}: ${n.text}`;
    noteList.appendChild(li);
  });
}

async function handleCaseAction(action) {
  const key = currentAnchorKey();
  if (!key) {
    if (caseActionStatus) caseActionStatus.textContent = "No selection to update case.";
    return;
  }
  const statusMap = { BLOCK: "Resolved", SAFE: "Resolved", ESCALATE: "In Progress" };
  const status = statusMap[action] || "Open";
  const [ruleLabel, anchor] = key.split(":");
  try {
    const res = await fetch(`${API_BASE}/investigator/actions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        anchor_id: anchor,
        anchor_type: ruleLabel === "R2" ? "DEVICE" : "ACCOUNT",
        rule_key: ruleLabel,
        action,
        status,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (caseActionStatus) caseActionStatus.textContent = data.message || "Case action failed.";
      return;
    }
    actionsByAnchor[key] = { status, lastAction: action, ts: data.created_at || new Date().toISOString() };
    if (caseActionStatus) caseActionStatus.textContent = `Action ${action} saved.`;
    if (caseStatus) caseStatus.textContent = `Status: ${status}`;
    renderNotes(key);
  } catch (err) {
    if (caseActionStatus) caseActionStatus.textContent = "Case action failed.";
    console.error(err);
  }
}

if (caseBlockBtn) caseBlockBtn.addEventListener("click", () => handleCaseAction("BLOCK"));
if (caseSafeBtn) caseSafeBtn.addEventListener("click", () => handleCaseAction("SAFE"));
if (caseEscalateBtn) caseEscalateBtn.addEventListener("click", () => handleCaseAction("ESCALATE"));

if (loadDeviceBtn) {
  loadDeviceBtn.addEventListener("click", () => {
    const devId = deviceSearch ? deviceSearch.value.trim() : "";
    if (!devId) {
      if (actionStatus) actionStatus.textContent = "Enter a device ID.";
      return;
    }
    selectedDeviceId = devId;
    selectedAccountId = null;
    selectedRuleKey = "R2";
    updateSelectionInfo();
    loadGraphForSelected();
  });
}

updateSelectionInfo();
fetchAlerts();
