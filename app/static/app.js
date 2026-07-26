const question = document.querySelector("#question");
const submit = document.querySelector("#submit");
const statusText = document.querySelector("#status");
const result = document.querySelector("#result");

document.querySelectorAll(".example").forEach((button) => {
  button.addEventListener("click", () => {
    question.value = button.textContent;
    question.focus();
  });
});

submit.addEventListener("click", async () => {
  const value = question.value.trim();
  if (value.length < 2) {
    statusText.textContent = "请先输入一个数据问题。";
    return;
  }
  submit.disabled = true;
  statusText.textContent = "Agent 正在理解问题、生成并检查 SQL…";
  result.classList.add("hidden");
  try {
    const response = await fetch("/api/analytics/query", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: value}),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail || {};
      throw new Error(detail.message || "查询失败");
    }
    render(data);
    statusText.textContent = "分析完成。";
  } catch (error) {
    statusText.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

document.querySelector("#copy-sql").addEventListener("click", () => {
  navigator.clipboard.writeText(document.querySelector("#sql").textContent);
});

function render(data) {
  document.querySelector("#summary").textContent = data.summary;
  document.querySelector("#sql").textContent = data.sql;
  document.querySelector("#meta").textContent =
    `Trace #${data.trace_id} · ${data.execution_ms} ms · ${data.rows.length} 行 · SQL 尝试 ${data.attempts} 次`;
  renderTable(data.columns, data.rows);
  renderChart(data.chart, data.columns, data.rows);
  result.classList.remove("hidden");
}

function renderTable(columns, rows) {
  const table = document.querySelector("#data-table");
  table.textContent = "";
  const head = table.createTHead().insertRow();
  columns.forEach((column) => {
    const th = document.createElement("th");
    th.textContent = column;
    head.appendChild(th);
  });
  const body = table.createTBody();
  rows.forEach((row) => {
    const tr = body.insertRow();
    row.forEach((value) => {
      const td = tr.insertCell();
      td.textContent = value ?? "";
    });
  });
}

function renderChart(spec, columns, rows) {
  const card = document.querySelector("#chart-card");
  const svg = document.querySelector("#chart");
  svg.textContent = "";
  if (!spec || rows.length === 0) {
    card.classList.add("hidden");
    return;
  }
  const xIndex = columns.indexOf(spec.x);
  const yIndex = columns.indexOf(spec.y);
  const points = rows.slice(0, 20)
    .map((row) => ({label: String(row[xIndex]), value: Number(row[yIndex])}))
    .filter((point) => Number.isFinite(point.value));
  if (!points.length) {
    card.classList.add("hidden");
    return;
  }
  card.classList.remove("hidden");
  document.querySelector("#chart-title").textContent = spec.title;
  const width = 900, height = 360, left = 72, bottom = 58, top = 20, right = 20;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const max = Math.max(...points.map((point) => point.value), 1);
  const ns = "http://www.w3.org/2000/svg";
  const add = (name, attrs, text = "") => {
    const node = document.createElementNS(ns, name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    node.textContent = text;
    svg.appendChild(node);
    return node;
  };
  add("line", {x1: left, y1: top, x2: left, y2: height - bottom, class: "axis"});
  add("line", {x1: left, y1: height - bottom, x2: width - right, y2: height - bottom, class: "axis"});
  if (spec.type === "line") {
    const coords = points.map((point, i) => {
      const x = left + (points.length === 1 ? plotWidth / 2 : i * plotWidth / (points.length - 1));
      const y = top + plotHeight - point.value / max * plotHeight;
      return {x, y, ...point};
    });
    add("polyline", {points: coords.map((p) => `${p.x},${p.y}`).join(" "), class: "chart-line"});
    coords.forEach((point) => add("circle", {cx: point.x, cy: point.y, r: 4, class: "chart-dot"}));
  } else {
    const gap = plotWidth / points.length;
    const barWidth = Math.max(8, gap * 0.62);
    points.forEach((point, i) => {
      const barHeight = point.value / max * plotHeight;
      add("rect", {
        x: left + i * gap + (gap - barWidth) / 2,
        y: top + plotHeight - barHeight,
        width: barWidth,
        height: barHeight,
        rx: 5,
        class: "chart-bar",
      });
    });
  }
  points.forEach((point, i) => {
    const x = left + (i + 0.5) * plotWidth / points.length;
    add("text", {x, y: height - bottom + 22, class: "label", "text-anchor": "middle"}, point.label.slice(0, 8));
  });
  add("text", {x: left - 8, y: top + 5, class: "label", "text-anchor": "end"}, formatNumber(max));
  add("text", {x: left - 8, y: height - bottom + 5, class: "label", "text-anchor": "end"}, "0");
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN", {notation: "compact", maximumFractionDigits: 1}).format(value);
}

