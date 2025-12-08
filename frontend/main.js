const urlParams = new URLSearchParams(window.location.search || "");
const API_BASE =
  urlParams.get("apiBase") ||
  window.API_BASE ||
  localStorage.getItem("API_BASE") ||
  "http://localhost:5005/api";

const alertsBody = document.getElementById("alerts-body");
const alertsEmpty = document.getElementById("alerts-empty");
const refreshBtn = document.getElementById("refresh-alerts");
const refreshApiBtn = document.getElementById("refresh-alerts-api");
const alertsNav = document.getElementById("alerts-nav");
const alertsSection = document.getElementById("alerts-section");
const alertsStatus = document.getElementById("alerts-status");
const neoTestButton = document.getElementById("neo-test");
const neoStatus = document.getElementById("neo-status");
const graphContainer = document.getElementById("graph-container");
const loadGraphBtn = document.getElementById("load-graph");
const riskSlider = document.getElementById("riskThreshold");
const limitInput = document.getElementById("limitInput");
const riskValue = document.getElementById("riskValue");
const ruleSelect = document.getElementById("ruleSelect");
const minRiskyInput = document.getElementById("minRisky");
const hideFlaggedCheckbox = null;
const includeTemporalCheckbox = null;
const fafOnlyCheckbox = null;
const temporalNameInput = document.getElementById("temporalName");
const temporalDurationInput = document.getElementById("temporalDuration");
const temporalAmountInput = document.getElementById("temporalAmount");
const temporalMinAmountInput = document.getElementById("temporalMinAmount");
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
const afasaStatus = document.getElementById("afasa-status");
const afasaDetails = document.getElementById("afasa-details");
const afasaCreateBtn = document.getElementById("afasa-create");
const afasaHoldBtn = document.getElementById("afasa-hold");
const afasaReleaseBtn = document.getElementById("afasa-release");
const afasaActionStatus = document.getElementById("afasa-action-status");

let alertsCache = [];
let selectedAccountId = null;
let selectedDeviceId = null;
let selectedAnchorType = "ACCOUNT";
let lastParams = "";
let selectedRuleKey = null;
let selectedAlert = null;
const notesByAnchor = {};
const actionsByAnchor = {};
let graphTooltip = null;
let activeDisputeId = null;

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

function temporalParams() {
  return {
    name: (temporalNameInput && temporalNameInput.value) || "Aubree David",
    duration: temporalDurationInput ? parseInt(temporalDurationInput.value || "6500", 10) : 6500,
    amount: temporalAmountInput ? parseFloat(temporalAmountInput.value || "50000") : 50000,
    minAmount: temporalMinAmountInput ? parseFloat(temporalMinAmountInput.value || "1200000") : 1200000,
  };
}

async function fetchAlerts() {
  setLoadingState(true);
  const rule = getRule();
  const fafOnly = false;
  const isTemporalRule = rule === "R8" || rule === "R9" || rule === "R10";
  if (alertsStatus && isTemporalRule) {
    alertsStatus.textContent = "Running temporal query… this may take a few seconds for long paths.";
  } else if (alertsStatus) {
    alertsStatus.textContent = "";
  }
  try {
    const params = new URLSearchParams();
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
  if (rule === "ALL") {
    params.append("excludeFlagged", "false");
  }
  if (rule === "R8" || rule === "R9" || rule === "R10") {
    const t = temporalParams();
    params.append("name", t.name);
    params.append("duration", t.duration);
    params.append("amount", t.amount);
    params.append("minAmount", t.minAmount);
  }
  lastParams = params.toString();
  let endpoint = "/neo-alerts/r1";
  if (fafOnly) {
    endpoint = "/alerts?family=FAF";
    params.delete("riskThreshold");
    params.delete("minRiskyAccounts");
  } else {
    if (rule === "R2") endpoint = "/neo-alerts/r2";
    if (rule === "R3") endpoint = "/neo-alerts/r3";
    if (rule === "R7") endpoint = "/neo-alerts/r7";
    if (rule === "ALL") endpoint = "/neo-alerts/search";
    if (rule === "R8") endpoint = "/neo-alerts/r8";
    if (rule === "R9") endpoint = "/neo-alerts/r9";
    if (rule === "R10") endpoint = "/neo-alerts/r10";
  }
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
        selectedAnchorType = "DEVICE";
      } else {
        selectedAccountId = first.accountId;
        selectedDeviceId = null;
        selectedAnchorType = "ACCOUNT";
      }
      updateSelectionInfo();
      renderContext();
      loadGraphForSelected();
    } else if (neoStatus) {
      neoStatus.textContent = "No alerts to load graph.";
    }
  } catch (err) {
    console.error("Failed to fetch alerts", err);
    if (alertsStatus) alertsStatus.textContent = "Failed to load alerts.";
  } finally {
    setLoadingState(false);
    if (alertsStatus && isTemporalRule) {
      alertsStatus.textContent = alertsStatus.textContent || "Temporal query finished.";
    }
  }
}

function renderAlerts(alerts) {
  alertsBody.innerHTML = "";
  alertsEmpty.style.display = alerts.length ? "none" : "block";
  alertsCache = alerts;

  alerts.forEach((alert) => {
    const row = document.createElement("tr");
    const temporalMeta =
      alert.ruleKey === "R8" || alert.ruleKey === "R9" || alert.ruleKey === "R10"
        ? [`${alert.pathLength ? `${alert.pathLength} hops` : ""}`, alert.maxAmount ? `max ₱${Number(alert.maxAmount).toLocaleString()}` : ""]
            .filter(Boolean)
            .join(" · ")
        : "";
    const displaySummary = temporalMeta ? `${alert.summary} (${temporalMeta})` : alert.summary;
    const afasaBadge =
      alert.afasa_risk_score || alert.afasa_suspicion_type
        ? `<span class="status-chip" style="background:#ffe9d6;color:#a65b00;">AFASA ${alert.afasa_suspicion_type || ""} (${alert.afasa_risk_score || "n/a"})</span>`
        : "";
    row.innerHTML = `
      <td><span class="badge ${severityClass(alert.severity)}">${alert.severity}</span></td>
      <td class="muted">#${alert.id}</td>
      <td>${alert.rule || "Account Risk"}</td>
      <td>${displaySummary} ${afasaBadge}</td>
      <td><span class="status-chip">${alert.status}</span></td>
      <td class="muted">${alert.created ? new Date(alert.created).toLocaleString() : ""}</td>
    `;
    row.addEventListener("click", () => {
      const rowRule = alert.ruleKey || getRule();
      if (rowRule === "R1" || rowRule === "R3" || rowRule === "R7" || rowRule === "R8" || rowRule === "R9" || rowRule === "R10") {
        selectedAccountId = alert.accountId;
        selectedDeviceId = null;
        selectedAnchorType = "ACCOUNT";
        if (neoStatus) neoStatus.textContent = `Selected account ${alert.accountId} (${rowRule})`;
      } else if (rowRule === "R2") {
        selectedDeviceId = alert.deviceId;
        selectedAccountId = null;
        selectedAnchorType = "DEVICE";
        if (neoStatus) neoStatus.textContent = `Selected identifier ${alert.deviceId} (${rowRule})`;
      } else {
        selectedAccountId = alert.accountId;
        selectedDeviceId = null;
        selectedAnchorType = "ACCOUNT";
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
if (refreshApiBtn) {
  refreshApiBtn.addEventListener("click", async () => {
    refreshApiBtn.textContent = "Refreshing via API...";
    refreshApiBtn.disabled = true;
    try {
      const res = await fetch(`${API_BASE}/alerts/refresh`, { method: "POST" });
      const data = await res.json();
      const generated = data.generated_alerts || 0;
      if (alertsStatus) alertsStatus.textContent = `Refresh completed. Generated ${generated} alert(s).`;
      await fetchAlerts();
    } catch (err) {
      if (alertsStatus) alertsStatus.textContent = "Refresh failed.";
      console.error(err);
    } finally {
      refreshApiBtn.textContent = "Refresh Alerts (API)";
      refreshApiBtn.disabled = false;
    }
  });
}

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
  const anchor = selectedAnchorType === "DEVICE" ? deviceId : accountId;
  if (!anchor) {
    if (neoStatus) neoStatus.textContent = "No anchor found on alert.";
    return;
  }
  const paramsDisplay = lastParams ? ` (filters: ${lastParams})` : "";
  neoStatus.textContent = `Loading graph for ${anchor} (${ruleLabel})${paramsDisplay}...`;
  try {
    const endpoint = selectedAnchorType === "DEVICE" ? "/neo4j/graph/identifier/" : "/neo4j/graph/account/";
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

  const ruleLabel = selectedRuleKey || getRule();
  const anchorId = ruleLabel === "R2" ? selectedDeviceId : selectedAccountId;

  // Ensure anchor is marked as subject in case backend didn't tag it
  if (anchorId) {
    nodes = nodes.map((n) =>
      n.id === anchorId ? { ...n, isSubject: true } : n
    );
  }

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
    selectedAnchorType = looksLikeDevice ? "DEVICE" : "ACCOUNT";
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
if (hideFlaggedCheckbox) {
  hideFlaggedCheckbox.addEventListener("change", () => {
    if (getRule() === "ALL") {
      fetchAlerts();
    }
  });
}
if (includeTemporalCheckbox) {
  includeTemporalCheckbox.addEventListener("change", () => {
    if (getRule() === "ALL") {
      fetchAlerts();
    }
  });
}

function updateSelectionInfo() {
  const ruleLabel = selectedRuleKey || getRule();
  const anchor = selectedAnchorType === "DEVICE" ? selectedDeviceId : selectedAccountId;
  if (selectionInfo) {
    const noun = selectedAnchorType === "DEVICE" ? "identifier" : "account";
    selectionInfo.textContent = anchor ? `Selected ${noun} ${anchor} (${ruleLabel})` : "No selection yet.";
  }
  updateAfasaInfo();
  renderContext();
  updateFlagButtonsVisibility();
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

function updateAfasaInfo(dispute) {
  if (!afasaStatus || !afasaDetails) return;
  const alert = selectedAlert;
  const suspicion = (alert && (alert.afasa_suspicion_type || alert.suspicion_type)) || "n/a";
  const risk = (alert && (alert.afasa_risk_score || alert.riskScore)) || "n/a";
  afasaStatus.textContent = alert ? `Suspicion: ${suspicion} | Risk: ${risk}` : "No AFASA data";
  afasaDetails.textContent = dispute
    ? `Dispute #${dispute.id} status=${dispute.status}`
    : "Select an alert to view AFASA risk or create a dispute.";
}

async function createAfasaDispute() {
  if (!selectedAlert || !selectedAlert.id) {
    afasaActionStatus.textContent = "Select an alert with an ID to create a dispute.";
    return;
  }
  afasaActionStatus.textContent = "Creating dispute...";
  try {
    const res = await fetch(`${API_BASE}/afasa/disputes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        alert_id: selectedAlert.id,
        tx_id: selectedAlert.original_tx_id || null,
        reason_category: "FMS_DETECTED",
        suspicion_type: selectedAlert.afasa_suspicion_type || "OTHER",
        initiated_by: "ui_demo",
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      afasaActionStatus.textContent = data.message || "Failed to create dispute.";
      return;
    }
    activeDisputeId = data.id;
    afasaActionStatus.textContent = `Dispute ${data.id} created (status ${data.status}).`;
    updateAfasaInfo(data);
  } catch (err) {
    afasaActionStatus.textContent = "Failed to create dispute.";
    console.error(err);
  }
}

async function holdAfasaDispute() {
  if (!activeDisputeId) {
    afasaActionStatus.textContent = "Create a dispute first.";
    return;
  }
  afasaActionStatus.textContent = "Applying hold...";
  try {
    const res = await fetch(`${API_BASE}/afasa/disputes/${activeDisputeId}/hold`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor: "ui_demo" }),
    });
    const data = await res.json();
    if (!res.ok) {
      afasaActionStatus.textContent = data.message || "Hold failed.";
      return;
    }
    afasaActionStatus.textContent = `Hold applied (status ${data.status}).`;
    updateAfasaInfo(data);
  } catch (err) {
    afasaActionStatus.textContent = "Hold failed.";
    console.error(err);
  }
}

async function releaseAfasaDispute() {
  if (!activeDisputeId) {
    afasaActionStatus.textContent = "Create a dispute first.";
    return;
  }
  afasaActionStatus.textContent = "Releasing...";
  try {
    const res = await fetch(`${API_BASE}/afasa/disputes/${activeDisputeId}/release`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: "RELEASE", actor: "ui_demo" }),
    });
    const data = await res.json();
    if (!res.ok) {
      afasaActionStatus.textContent = data.message || "Release failed.";
      return;
    }
    afasaActionStatus.textContent = `Released dispute ${data.id}.`;
    updateAfasaInfo(data);
  } catch (err) {
    afasaActionStatus.textContent = "Release failed.";
    console.error(err);
  }
}

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

if (afasaCreateBtn) afasaCreateBtn.addEventListener("click", createAfasaDispute);
if (afasaHoldBtn) afasaHoldBtn.addEventListener("click", holdAfasaDispute);
if (afasaReleaseBtn) afasaReleaseBtn.addEventListener("click", releaseAfasaDispute);

updateSelectionInfo();
fetchAlerts();

function updateFlagButtonsVisibility() {
  const ruleLabel = selectedRuleKey || getRule();
  const isSearchAndDestroy = ruleLabel === "ALL";
  const displayStyle = isSearchAndDestroy ? "inline-block" : "none";
  if (flagAccountBtn) flagAccountBtn.style.display = displayStyle;
  if (flagDeviceBtn) flagDeviceBtn.style.display = displayStyle;
}
