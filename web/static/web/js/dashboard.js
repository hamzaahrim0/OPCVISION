const fmt = new Intl.NumberFormat("fr-MA", { maximumFractionDigits: 2 });
const cleanNumber = (v) => Math.abs(Number(v)) < 1e-9 ? 0 : Number(v);
const money = (v) => v == null ? "n/a" : `${fmt.format(cleanNumber(v) / 1_000_000_000)} Md`;
const moneySmart = (v) => {
  if (v == null) return "n/a";
  const value = cleanNumber(v);
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `${fmt.format(value / 1_000_000_000)} Md`;
  if (abs >= 1_000_000) return `${fmt.format(value / 1_000_000)} M`;
  if (abs >= 1_000) return `${fmt.format(value / 1_000)} k`;
  return fmt.format(value);
};
const pct = (v) => v == null ? "n/a" : `${fmt.format(cleanNumber(v))} %`;
const num = (v) => v == null ? "n/a" : fmt.format(cleanNumber(v));
const cls = (v) => cleanNumber(v) > 0 ? "pos" : cleanNumber(v) < 0 ? "neg" : "";

let dimensions = {};
let latestMarket = null;
let fundOptions = [];
let selectedFunds = [];
let refreshTimer = null;
let requestGeneration = 0;
const inflight = new Map();
let searchTimer = null;

async function getJSON(url, group = "default") {
  if (inflight.has(group)) inflight.get(group).abort();
  const controller = new AbortController();
  inflight.set(group, controller);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `${url}: ${res.status}`);
    }
    return res.json();
  } finally {
    if (inflight.get(group) === controller) inflight.delete(group);
  }
}

function params(extra = {}) {
  const p = new URLSearchParams();
  const start = document.querySelector("#start-filter").value;
  const end = document.querySelector("#end-filter").value;
  const classification = document.querySelector("#classification-filter").value;
  const subscriber = document.querySelector("#subscriber-filter").value;
  const company = document.querySelector("#company-filter").value;
  if (start) p.set("start", start);
  if (end) p.set("end", end);
  if (classification) p.set("classification", classification);
  if (subscriber) p.set("subscriber_type", subscriber);
  if (company) p.set("management_company", company);
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== "" && value != null) p.set(key, value);
  });
  return p;
}

function debounceRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refresh, 300);
}

function fillSelect(id, values) {
  const el = document.querySelector(id);
  const current = el.value;
  el.querySelectorAll("option:not(:first-child)").forEach((opt) => opt.remove());
  values.forEach((value) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value;
    el.appendChild(opt);
  });
  el.value = current;
}

function renderTable(id, columns, rows) {
  const table = document.querySelector(id);
  table.innerHTML = "";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col.label;
    if (col.num) th.className = "num";
    head.appendChild(th);
  });
  thead.appendChild(head);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = columns.length;
    td.className = "empty";
    td.textContent = "Aucune donnée pour les filtres sélectionnés.";
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((col) => {
      const td = document.createElement("td");
      td.textContent = col.format ? col.format(row[col.key], row) : (row[col.key] ?? "");
      if (col.num) td.className = `num ${cls(row[col.key])}`;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}

function renderError(target, message) {
  const el = document.querySelector(target);
  if (el.tagName === "TABLE") {
    renderTable(target, [{ key: "message", label: "Erreur" }], [{ message }]);
  } else {
    el.innerHTML = `<div class="empty-chart">${message}</div>`;
  }
}

function renderChoice(target, title, detail, action) {
  const el = document.querySelector(target);
  el.innerHTML = `
    <div class="choice-state">
      <strong>${title}</strong>
      <span>${detail}</span>
      ${action ? `<em>${action}</em>` : ""}
    </div>
  `;
}

function setLoading(target) {
  const el = document.querySelector(target);
  if (el.tagName === "TABLE") {
    renderTable(target, [{ key: "loading", label: "" }], [{ loading: "Chargement..." }]);
  } else {
    el.innerHTML = '<div class="spinner"></div>';
  }
}

function applyShortcut() {
  const shortcut = document.querySelector("#range-shortcut").value;
  const endInput = document.querySelector("#end-filter");
  const startInput = document.querySelector("#start-filter");
  const latest = dimensions.latest_date;
  if (!latest || shortcut === "custom") return;
  const end = new Date(`${latest}T00:00:00`);
  const start = new Date(end);
  if (shortcut === "7d") start.setDate(start.getDate() - 7);
  if (shortcut === "1m") start.setMonth(start.getMonth() - 1);
  if (shortcut === "3m") start.setMonth(start.getMonth() - 3);
  if (shortcut === "6m") start.setMonth(start.getMonth() - 6);
  if (shortcut === "1y") start.setFullYear(start.getFullYear() - 1);
  if (shortcut === "ytd") start.setMonth(0, 1);
  if (shortcut === "all") startInput.value = dimensions.earliest_date || "";
  else startInput.value = start.toISOString().slice(0, 10);
  endInput.value = latest;
}

async function loadDimensions() {
  dimensions = await getJSON("/api/dimensions/", "dimensions");
  fillSelect("#classification-filter", dimensions.classifications);
  fillSelect("#ranking-classification", dimensions.classifications);
  fillSelect("#subscriber-filter", dimensions.subscriber_types);
  fillSelect("#company-filter", dimensions.management_companies);
  applyShortcut();
}

async function loadMarketOverview() {
  ["#market-chart", "#market-series"].forEach(setLoading);
  const data = await getJSON(`/api/market-overview/?${params()}`, "market");
  latestMarket = data;
  ["#total-aum", "#fund-count", "#hhi", "#top3"].forEach((id) => document.querySelector(id).classList.remove("loading"));
  document.querySelector("#total-aum").textContent = money(data.total_aum);
  document.querySelector("#aum-change").textContent = pct(data.aum_change_pct);
  document.querySelector("#aum-change").className = cls(data.aum_change_pct);
  document.querySelector("#fund-count").textContent = num(data.fund_count);
  document.querySelector("#company-count").textContent = `${num(data.management_company_count)} sociétés`;
  document.querySelector("#hhi").textContent = num(data.hhi);
  document.querySelector("#leader").textContent = data.leader || "n/a";
  document.querySelector("#top3").textContent = pct(data.top3);
  document.querySelector("#top5").textContent = `Top 5 ${pct(data.top5)}`;
  document.querySelector("#market-asof").textContent = data.as_of || "";
  renderTreemap();
  renderMarketSeries(data);
}

function renderTreemap() {
  const data = latestMarket;
  if (!data || !window.Plotly) return;
  const mode = document.querySelector("#treemap-mode").value;
  let rows = data.by_legal_nature || [];
  let label = "legal_nature";
  if (mode === "company") {
    rows = data.by_company || [];
    label = "company";
  }
  if (mode === "classification") {
    rows = data.by_classification || [];
    label = "classification";
  }
  if (!rows.length) {
    renderError("#market-chart", "Aucune donnée de marché.");
    return;
  }
  Plotly.newPlot("market-chart", [{
    type: "treemap",
    labels: rows.map((row) => row[label]),
    parents: rows.map(() => ""),
    values: rows.map((row) => row.aum),
    textinfo: "label+percent root",
    marker: { colors: ["#3b82f6", "#22c55e", "#ef4444", "#f59e0b", "#14b8a6", "#a855f7"] },
    hovertemplate: "%{label}<br>Actif net: %{value:,.0f}<br>Part: %{percentRoot:.2%}<extra></extra>",
  }], plotLayout({ margin: { l: 4, r: 4, t: 4, b: 4 } }), { displayModeBar: false, responsive: true });
}

function renderMarketSeries(data) {
  if (!window.Plotly) return;
  Plotly.newPlot("market-series", [{
    type: "scatter",
    mode: "lines",
    x: data.time_series.map((row) => row.date),
    y: data.time_series.map((row) => row.total_aum),
    line: { color: "#22c55e", width: 2 },
    hovertemplate: "%{x}<br>%{y:,.0f}<extra></extra>",
  }], plotLayout({
    yaxis: { gridcolor: "#303a45", color: "#8b98a5", tickformat: "~s", automargin: true },
  }), { displayModeBar: false, responsive: true });
}

async function loadRanking() {
  setLoading("#ranking-table");
  const classification = document.querySelector("#ranking-classification").value || document.querySelector("#classification-filter").value;
  const metric = document.querySelector("#ranking-metric").value;
  if (!classification) {
    renderTable("#ranking-table", [{ key: "message", label: "Choix requis" }], [{
      message: "Choisissez une classification pour afficher un classement cohérent entre fonds comparables.",
    }]);
    return;
  }
  const data = await getJSON(`/api/category-ranking/?${params({ classification, metric, limit: 15 })}`, "ranking");
  const rows = data.rows || Object.entries(data.categories || {}).flatMap(([category, value]) => value.rows.map((row) => ({ ...row, classification: category })));
  renderTable("#ranking-table", [
    { key: "rank", label: "#", num: true, format: num },
    { key: "fund_name", label: "OPCVM" },
    { key: "management_company", label: "Société" },
    { key: "classification", label: "Classe" },
    { key: metric, label: document.querySelector("#ranking-metric").selectedOptions[0].textContent, num: true, format: metric === "perf_1y" ? pct : moneySmart },
    { key: "percentile", label: "Percentile", num: true, format: pct },
  ], rows);
}

function navParams(extra = {}) {
  const p = new URLSearchParams();
  const start = document.querySelector("#start-filter").value;
  const end = document.querySelector("#end-filter").value;
  if (start) p.set("start", start);
  if (end) p.set("end", end);
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== "" && value != null) p.set(key, value);
  });
  return p;
}

async function searchFunds() {
  const query = document.querySelector("#fund-search").value.trim();
  const url = query.length >= 2
    ? `/api/funds/?search=${encodeURIComponent(query)}`
    : `/api/funds/`;
  try {
    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      fundOptions = data.results || data;
      const list = document.querySelector("#fund-options");
      list.innerHTML = "";
      fundOptions.slice(0, 30).forEach((fund) => {
        const opt = document.createElement("option");
        opt.value = `${fund.isin} - ${fund.name}`;
        list.appendChild(opt);
      });
    }
  } catch (e) {
    console.warn("searchFunds error:", e);
  }
}

async function addFund() {
  const inputEl = document.querySelector("#fund-search");
  const value = inputEl.value.trim();
  if (!value) return;

  const parts = value.split(" - ");
  const cleanIsin = parts[0].trim().toLowerCase();
  const cleanVal = value.toLowerCase();

  let fund = fundOptions.find((item) =>
    item.isin.toLowerCase() === cleanIsin ||
    item.isin.toLowerCase() === cleanVal ||
    item.name.toLowerCase() === cleanVal ||
    item.name.toLowerCase().includes(cleanVal) ||
    cleanVal.includes(item.isin.toLowerCase())
  );

  if (!fund) {
    try {
      const res = await fetch(`/api/funds/?search=${encodeURIComponent(value)}`);
      if (res.ok) {
        const data = await res.json();
        const list = data.results || data;
        if (Array.isArray(list) && list.length > 0) {
          fund = list.find((item) =>
            item.isin.toLowerCase() === cleanIsin ||
            item.name.toLowerCase().includes(cleanVal)
          ) || list[0];
        }
      }
    } catch (e) {
      console.warn("addFund direct fetch error:", e);
    }
  }

  if (!fund) {
    alert(`Aucun OPCVM trouvé pour "${value}".`);
    return;
  }

  if (selectedFunds.some((item) => item.isin === fund.isin)) {
    inputEl.value = "";
    return;
  }

  if (selectedFunds.length >= 10) {
    alert("Vous ne pouvez comparer que 10 OPCVM au maximum.");
    return;
  }

  selectedFunds.push(fund);
  inputEl.value = "";
  renderSelectedFunds();
  loadNavSeries().catch((err) => renderError("#nav-chart", err.message));
  loadSrTimeseries().catch((err) => renderError("#sr-timeseries", err.message));
}

function renderSelectedFunds() {
  const target = document.querySelector("#selected-funds");
  if (!selectedFunds.length) {
    target.innerHTML = "";
    return;
  }
  target.innerHTML = selectedFunds.map((fund) => `
    <button type="button" class="fund-chip" data-isin="${fund.isin}" title="${fund.name}">
      <span class="chip-name">${fund.name}</span>
      <span class="chip-isin">(${fund.isin})</span>
      <span class="chip-remove" aria-label="Supprimer">&times;</span>
    </button>
  `).join("");

  target.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      selectedFunds = selectedFunds.filter((fund) => fund.isin !== button.dataset.isin);
      renderSelectedFunds();
      loadNavSeries().catch((err) => renderError("#nav-chart", err.message));
      loadSrTimeseries().catch((err) => renderError("#sr-timeseries", err.message));
    });
  });
}

async function loadNavSeries() {
  setLoading("#nav-chart");
  if (!selectedFunds.length) {
    renderChoice("#nav-chart", "Choisissez des OPCVM", "Recherchez un nom ou un ISIN, puis cliquez sur Ajouter.", "Vous pouvez comparer jusqu'à 10 fonds en base 100 ou en VL brute.");
    return;
  }
  const isins = selectedFunds.map((fund) => fund.isin).join(",");
  const base100 = document.querySelector("#nav-base").value;
  const data = await getJSON(`/api/nav-series/?${navParams({ isins, base100 })}`, "nav-series");

  const validSeries = (data.series || []).filter((s) => s.points && s.points.length > 0);
  if (!validSeries.length) {
    renderError("#nav-chart", "Aucun historique de valeur liquidative disponible pour les fonds et la période sélectionnée.");
    return;
  }

  const yTitle = data.base100 ? "Indice (Base 100)" : "Valeur Liquidative (MAD)";

  Plotly.newPlot("nav-chart", validSeries.map((serie) => ({
    type: "scatter",
    mode: "lines",
    name: serie.fund_name,
    x: serie.points.map((point) => point.date),
    y: serie.points.map((point) => point.value),
    hovertemplate: `<b>%{fullData.name}</b><br>Date: %{x}<br>Valeur: %{y:,.2f}<extra></extra>`,
  })), plotLayout({
    yaxis: {
      title: { text: yTitle, font: { size: 11, color: "#8b98a5" } },
      gridcolor: "#303a45",
      color: "#8b98a5",
      automargin: true,
    },
  }), { displayModeBar: false, responsive: true });
}

async function loadSrTimeseries() {
  setLoading("#sr-timeseries");
  const isins = selectedFunds.map((fund) => fund.isin).join(",");
  const classification = document.querySelector("#classification-filter").value;
  if (!isins && !classification) {
    document.querySelector("#sr-scope").textContent = "Sélection requise";
    renderChoice("#sr-timeseries", "Choisissez le périmètre", "Sélectionnez une classification dans les filtres globaux ou ajoutez des OPCVM au comparateur.", "Le graphique affichera ensuite l'effet S-R et l'effet performance dans le temps.");
    return;
  }
  const data = await getJSON(`/api/sr-effect-timeseries/?${params({ isins, limit: 3000 })}`, "sr-timeseries");
  document.querySelector("#sr-scope").textContent = selectedFunds.length ? `${selectedFunds.length} OPCVM` : "Filtres globaux";
  const dates = data.series.map((row) => row.date);
  Plotly.newPlot("sr-timeseries", [
    { type: "bar", name: "Effet S-R", x: dates, y: data.series.map((row) => row.sr_effect), marker: { color: "#3b82f6" } },
    { type: "bar", name: "Effet perf.", x: dates, y: data.series.map((row) => row.performance_effect), marker: { color: "#22c55e" } },
  ], plotLayout({
    barmode: "relative",
    yaxis: { gridcolor: "#303a45", color: "#8b98a5", tickformat: "~s", automargin: true },
  }), { displayModeBar: false, responsive: true });
}

async function loadSrDetail() {
  setLoading("#sr-table");
  const data = await getJSON(`/api/sr-effect/?${params({ latest: "1", limit: 1000 })}`, "sr-detail");
  renderTable("#sr-table", [
    { key: "date", label: "Date" },
    { key: "fund_name", label: "OPCVM" },
    { key: "management_company", label: "Société" },
    { key: "sr_effect", label: "Effet S-R", num: true, format: moneySmart },
    { key: "performance_effect", label: "Effet perf.", num: true, format: moneySmart },
    { key: "sr_pct", label: "S-R %", num: true, format: pct },
  ], data.slice(0, 80));
}

async function loadWatchlist() {
  setLoading("#watchlist-table");
  const scenario = document.querySelector("#scenario-filter").value;
  const data = await getJSON(`/api/competitive/?${params({ scenario })}`, "watchlist");
  const rows = data.results || data;
  renderTable("#watchlist-table", [
    { key: "company", label: "Société" },
    { key: "market_share", label: "Part", num: true, format: pct },
    { key: "share_gain", label: "Gain", num: true, format: pct },
    { key: "collection_rate", label: "Collecte", num: true, format: pct },
    { key: "score", label: "Score", num: true, format: num },
    { key: "priority", label: "Priorité" },
  ], rows.slice(0, 40));
}

async function loadSnapshotExplorer() {
  setLoading("#fund-table");
  const end = document.querySelector("#end-filter").value;
  const data = await getJSON(`/api/snapshot/?${params({ date: end, limit: 120 })}`, "snapshot");
  const rows = data.results || data;
  renderTable("#fund-table", [
    { key: "isin", label: "ISIN" },
    { key: "fund_name", label: "OPCVM" },
    { key: "management_company", label: "Société" },
    { key: "classification", label: "Classe" },
    { key: "net_assets", label: "Actif net", num: true, format: money },
    { key: "nav", label: "VL", num: true, format: num },
    { key: "perf_1y", label: "1 an", num: true, format: pct },
  ], rows.slice(0, 120));
}

function plotLayout(extra = {}) {
  return {
    paper_bgcolor: "#171d24",
    plot_bgcolor: "#171d24",
    margin: { l: 56, r: 16, t: 12, b: 38 },
    xaxis: { gridcolor: "#303a45", color: "#8b98a5" },
    yaxis: { gridcolor: "#303a45", color: "#8b98a5", automargin: true },
    legend: { orientation: "h", font: { color: "#cbd5df" } },
    font: { color: "#e6edf3", size: 11 },
    ...extra,
  };
}

function refresh() {
  requestGeneration += 1;
  const generation = requestGeneration;
  const handle = (target) => (err) => {
    if (err.name === "AbortError" || generation !== requestGeneration) return;
    renderError(target, err.message);
  };
  loadMarketOverview().catch(handle("#market-chart"));
  loadRanking().catch(handle("#ranking-table"));
  loadWatchlist().catch(handle("#watchlist-table"));
  loadNavSeries().catch(handle("#nav-chart"));
  loadSrTimeseries().catch(handle("#sr-timeseries"));
  loadSrDetail().catch(handle("#sr-table"));
  loadSnapshotExplorer().catch(handle("#fund-table"));
}

document.querySelector("#refresh").addEventListener("click", refresh);
document.querySelector("#range-shortcut").addEventListener("change", () => {
  applyShortcut();
  refresh();
});
["#start-filter", "#end-filter"].forEach((id) => {
  document.querySelector(id).addEventListener("change", () => {
    document.querySelector("#range-shortcut").value = "custom";
    debounceRefresh();
  });
});
["#classification-filter", "#subscriber-filter", "#company-filter", "#scenario-filter", "#ranking-classification", "#ranking-metric", "#nav-base"].forEach((id) => {
  document.querySelector(id).addEventListener("change", debounceRefresh);
});
document.querySelector("#treemap-mode").addEventListener("change", renderTreemap);
const fundSearchInput = document.querySelector("#fund-search");
fundSearchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(searchFunds, 250);
});
fundSearchInput.addEventListener("focus", () => {
  if (!fundOptions.length) searchFunds();
});
fundSearchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    addFund();
  }
});
document.querySelector("#add-fund").addEventListener("click", addFund);

loadDimensions().then(refresh).catch((err) => {
  document.body.insertAdjacentHTML("afterbegin", `<pre class="boot-error">${err.message}</pre>`);
});
