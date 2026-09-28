const form = document.querySelector("#upload-form");
const fileInput = document.querySelector("#file-input");
const dropzone = document.querySelector("#dropzone");
const fileLabel = document.querySelector("#file-label");
const analyzeButton = document.querySelector("#analyze-button");
const uploadMessage = document.querySelector("#upload-message");
const recentList = document.querySelector("#recent-list");
const recentCount = document.querySelector("#recent-count");
let selectedFile = null;
let currentDocument = null;

const groups = [
  { title: "Income statement", keys: ["revenue", "gross_profit", "operating_income", "profit", "gross_margin", "operating_margin"] },
  { title: "Balance sheet", keys: ["total_assets", "total_liabilities", "cash_and_equivalents"] },
  { title: "Cash flow", keys: ["operating_cash_flow", "free_cash_flow"] },
  { title: "Per share", keys: ["eps"] },
];
const labels = {
  revenue: "Revenue", gross_profit: "Gross Profit", operating_income: "Operating Income", profit: "Profit",
  gross_margin: "Gross Margin", operating_margin: "Operating Margin", total_assets: "Total Assets",
  total_liabilities: "Total Liabilities", cash_and_equivalents: "Cash and Equivalents",
  operating_cash_flow: "Operating Cash Flow", free_cash_flow: "Free Cash Flow", eps: "Earnings Per Share",
};

function message(text, error = false) {
  uploadMessage.textContent = text;
  uploadMessage.classList.toggle("error", error);
  uploadMessage.hidden = false;
}

function selectFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    selectedFile = null;
    fileInput.value = "";
    fileLabel.textContent = "Choose a PDF to analyze";
    analyzeButton.disabled = true;
    message("Please select a PDF file.", true);
    return;
  }
  selectedFile = file;
  fileLabel.textContent = file.name;
  analyzeButton.disabled = false;
  uploadMessage.hidden = true;
}

fileInput.addEventListener("change", () => selectFile(fileInput.files[0]));
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
for (const eventName of ["dragenter", "dragover"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragover");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragover");
  });
}
dropzone.addEventListener("drop", (event) => selectFile(event.dataTransfer.files[0]));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedFile) return;
  const body = new FormData();
  body.append("file", selectedFile);
  analyzeButton.disabled = true;
  analyzeButton.classList.add("is-loading");
  analyzeButton.querySelector("span:first-child").textContent = "Analyzing filing…";
  message("Extracting figures and filing context. This can take a little while.");
  try {
    const response = await fetch("/documents", { method: "POST", body });
    const documentData = await response.json();
    if (!response.ok) throw new Error(documentData.detail || "The document could not be analyzed.");
    currentDocument = documentData;
    renderDocument(documentData);
    message("Analysis complete.");
    await loadRecentDocuments();
  } catch (error) {
    message(error.message || "Could not reach the analyzer. Check that the server is running.", true);
  } finally {
    analyzeButton.disabled = !selectedFile;
    analyzeButton.classList.remove("is-loading");
    analyzeButton.querySelector("span:first-child").textContent = "Analyze document";
  }
});

function renderDocument(documentData) {
  const result = documentData.result || {};
  document.querySelector("#results-empty").hidden = true;
  document.querySelector("#results-content").hidden = false;
  document.querySelector("#result-filename").textContent = documentData.filename || "Untitled filing";
  document.querySelector("#result-meta").textContent = `STATUS: ${documentData.status || "complete"} · REF ${String(documentData.id || "").slice(0, 8).toUpperCase()}`;
  document.querySelector("#summary-text").textContent = result.summary || makeSummary(result);
  renderMetrics(result);
  renderSentiment(result.sentiment);
  renderRisks(result.risk_factors);
}

function makeSummary(result) {
  const lines = ["revenue", "profit", "operating_cash_flow"]
    .map((key) => [key, result[key]?.[0]])
    .filter(([, item]) => item?.value)
    .map(([key, item]) => `${labels[key]} for ${item.period} was ${item.value}`);
  return lines.length ? `${lines.join(". ")}.` : "The filing was analyzed. Review the extracted figures and disclosures below.";
}

function renderMetrics(result) {
  const container = document.querySelector("#metrics-groups");
  container.replaceChildren();
  for (const group of groups) {
    const available = group.keys.filter((key) => Array.isArray(result[key]) && result[key].length);
    if (!available.length) continue;
    const periods = [...new Set(available.flatMap((key) => result[key].map((item) => item.period).filter(Boolean)))];
    const section = document.createElement("section");
    section.className = "metric-group";
    const title = document.createElement("h4");
    title.className = "metric-group-title";
    title.textContent = group.title;
    section.append(title);
    const heading = document.createElement("div");
    heading.className = "metric-head";
    heading.style.setProperty("--period-count", String(Math.max(periods.length, 1)));
    heading.append(document.createElement("span"));
    for (const period of periods) {
      const cell = document.createElement("span");
      cell.textContent = period;
      heading.append(cell);
    }
    section.append(heading);
    for (const key of available) {
      const byPeriod = new Map(result[key].map((item) => [item.period, item]));
      const row = document.createElement("div");
      row.className = "metric-row";
      row.style.setProperty("--period-count", String(Math.max(periods.length, 1)));
      const label = document.createElement("span");
      label.className = "metric-label";
      label.textContent = result[key][0].label || labels[key] || key;
      row.append(label);
      for (const period of periods) {
        const item = byPeriod.get(period);
        const value = document.createElement("span");
        value.className = "metric-value";
        value.textContent = item?.value ?? "—";
        if (item?.unit) {
          const unit = document.createElement("small");
          unit.textContent = item.unit;
          value.append(unit);
        }
        row.append(value);
      }
      section.append(row);
    }
    container.append(section);
  }
  if (!container.childElementCount) {
    const empty = document.createElement("p");
    empty.className = "metric-empty";
    empty.textContent = "No financial figures were extracted from this filing.";
    container.append(empty);
  }
}

function renderSentiment(sentiment) {
  const container = document.querySelector("#sentiment-content");
  container.replaceChildren();
  if (!sentiment || typeof sentiment !== "object") {
    const empty = document.createElement("p");
    empty.textContent = "No sentiment assessment was returned.";
    container.append(empty);
    return;
  }
  const badge = document.createElement("span");
  badge.className = `sentiment-badge ${(sentiment.label || "neutral").toLowerCase()}`;
  badge.textContent = sentiment.label || "Not reported";
  container.append(badge);
  if (sentiment.justification) {
    const text = document.createElement("p");
    text.textContent = sentiment.justification;
    container.append(text);
  }
}

function renderRisks(risks) {
  const container = document.querySelector("#risk-content");
  container.replaceChildren();
  if (!Array.isArray(risks) || !risks.length) {
    const empty = document.createElement("p");
    empty.className = "no-risks";
    empty.textContent = "No risk factors were extracted.";
    container.append(empty);
    return;
  }
  const list = document.createElement("ul");
  list.className = "risk-list";
  for (const risk of risks) {
    const item = document.createElement("li");
    item.textContent = typeof risk === "string" ? risk : JSON.stringify(risk);
    list.append(item);
  }
  container.append(list);
}

document.querySelector("#download-json").addEventListener("click", () => {
  if (!currentDocument) return;
  const data = new Blob([JSON.stringify(currentDocument, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${(currentDocument.filename || "analysis").replace(/\.pdf$/i, "")}-analysis.json`;
  link.click();
  URL.revokeObjectURL(url);
});

async function loadRecentDocuments() {
  try {
    const response = await fetch("/documents");
    if (!response.ok) return;
    const documents = await response.json();
    recentCount.textContent = String(documents.length);
    recentList.replaceChildren();
    if (!documents.length) {
      const empty = document.createElement("p");
      empty.className = "empty-recent";
      empty.textContent = "Your analyzed filings will appear here.";
      recentList.append(empty);
      return;
    }
    for (const item of [...documents].reverse().slice(0, 5)) {
      const row = document.createElement("div");
      row.className = "recent-row";
      const icon = document.createElement("span");
      icon.className = "recent-file-icon";
      icon.textContent = "PDF";
      const name = document.createElement("span");
      name.className = "recent-name";
      const filename = document.createElement("strong");
      filename.textContent = item.filename || "Untitled filing";
      const status = document.createElement("span");
      status.textContent = item.status || "unknown";
      name.append(filename, status);
      row.append(icon, name);
      if (item.result) {
        const open = document.createElement("button");
        open.className = "recent-open";
        open.type = "button";
        open.textContent = "View";
        open.setAttribute("aria-label", `View ${item.filename || "document"} analysis`);
        open.addEventListener("click", () => {
          currentDocument = item;
          renderDocument(item);
          document.querySelector("#results-content").scrollIntoView({ behavior: "smooth", block: "start" });
        });
        row.append(open);
      }
      recentList.append(row);
    }
  } catch {
    recentCount.textContent = "0";
  }
}

loadRecentDocuments();