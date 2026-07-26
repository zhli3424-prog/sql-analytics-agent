const loginCard = document.querySelector("#login-card");
const appShell = document.querySelector("#app-shell");
const loginForm = document.querySelector("#login-form");
const loginStatus = document.querySelector("#login-status");
const question = document.querySelector("#question");
const submit = document.querySelector("#submit");
const statusText = document.querySelector("#status");
const result = document.querySelector("#result");
const emptyState = document.querySelector("#empty-state");
let currentTraceId = null;

async function api(url, options = {}) {
  const response = await fetch(url, options);
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (response.status === 401) {
    showLogin();
    throw new Error("登录已失效，请重新登录");
  }
  if (!response.ok) {
    const detail = data.detail || {};
    throw new Error(detail.message || detail || "请求失败");
  }
  return data;
}

function showLogin() {
  loginCard.classList.remove("hidden");
  appShell.classList.add("hidden");
}

async function showApp(user) {
  loginCard.classList.add("hidden");
  appShell.classList.remove("hidden");
  document.querySelector("#current-user").textContent = user.username;
  await Promise.all([loadHistory(), loadSchema()]);
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginStatus.textContent = "正在登录…";
  const payload = {
    username: document.querySelector("#username").value.trim(),
    password: document.querySelector("#password").value,
  };
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    loginForm.reset();
    loginStatus.textContent = "";
    await showApp(data.user);
  } catch (error) {
    loginStatus.textContent = error.message;
  }
});

document.querySelector("#logout").addEventListener("click", async () => {
  await fetch("/api/auth/logout", {method: "POST"});
  showLogin();
});

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
  try {
    const data = await api("/api/analytics/query", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: value}),
    });
    render(data);
    statusText.textContent = "分析完成，结果已保存到查询历史。";
    await loadHistory();
  } catch (error) {
    statusText.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

document.querySelector("#copy-sql").addEventListener("click", async () => {
  await navigator.clipboard.writeText(document.querySelector("#sql").textContent);
  statusText.textContent = "SQL 已复制。";
});

document.querySelector("#download-csv").addEventListener("click", () => {
  if (currentTraceId) window.location.href = `/api/analytics/history/${currentTraceId}/csv`;
});

document.querySelector("#refresh-history").addEventListener("click", loadHistory);

async function loadSchema() {
  try {
    const data = await api("/api/analytics/schema");
    document.querySelector("#schema-badge").textContent = `${data.schema} · ${data.tables.length} 张只读表`;
  } catch (error) {
    document.querySelector("#schema-badge").textContent = "数据源不可用";
  }
}

async function loadHistory() {
  const list = document.querySelector("#history-list");
  try {
    const data = await api("/api/analytics/history?limit=30");
    list.textContent = "";
    if (!data.history.length) {
      list.innerHTML = '<p class="muted">暂无查询记录</p>';
      return;
    }
    data.history.forEach((trace) => {
      const button = document.createElement("button");
      button.className = "history-item";
      const title = document.createElement("strong");
      title.textContent = trace.question;
      const meta = document.createElement("span");
      meta.textContent = `#${trace.id} · ${trace.status === "success" ? `${trace.row_count} 行` : "失败"} · ${formatTime(trace.created_at)}`;
      button.append(title, meta);
      button.addEventListener("click", () => loadTrace(trace.id));
      list.appendChild(button);
    });
  } catch (error) {
    list.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
  }
}

async function loadTrace(traceId) {
  try {
    const data = await api(`/api/analytics/history/${traceId}`);
    if (data.trace.status !== "success") {
      statusText.textContent = data.trace.error || "该查询执行失败";
      return;
    }
    render(data.trace);
    statusText.textContent = `已打开历史查询 #${traceId}`;
  } catch (error) {
    statusText.textContent = error.message;
  }
}

function render(data) {
  currentTraceId = data.trace_id || data.id;
  document.querySelector("#summary").textContent = data.summary || "查询完成。";
  document.querySelector("#sql").textContent = data.sql || "";
  document.querySelector("#meta").textContent =
    `Trace #${currentTraceId} · ${data.execution_ms ?? "-"} ms · ${data.rows.length} 行 · SQL 尝试 ${data.attempts} 次`;
  renderTable(data.columns, data.rows);
  renderChart(data.chart || inferChart(data.columns, data.rows), data.columns, data.rows);
  emptyState.classList.add("hidden");
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

function inferChart(columns, rows) {
  if (!rows.length || columns.length < 2) return null;
  const numeric = columns.map((_, index) => rows.some((row) => typeof row[index] === "number"));
  let yIndex = numeric.lastIndexOf(true);
  if (yIndex < 0) return null;
  let xIndex = columns.findIndex((column, index) => index !== yIndex && !column.endsWith("_id") && !numeric[index]);
  if (xIndex < 0) xIndex = columns.findIndex((_, index) => index !== yIndex);
  if (xIndex < 0) return null;
  const x = columns[xIndex], y = columns[yIndex];
  const type = /(date|month|day|week|year|time)/i.test(x) ? "line" : "bar";
  return {type, x, y, title: `${y} 按 ${x}`};
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
    add("text", {x, y: height - bottom + 22, class: "label", "text-anchor": "middle"}, point.label.slice(0, 10));
  });
  add("text", {x: left - 8, y: top + 5, class: "label", "text-anchor": "end"}, formatNumber(max));
  add("text", {x: left - 8, y: height - bottom + 5, class: "label", "text-anchor": "end"}, "0");
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN", {notation: "compact", maximumFractionDigits: 1}).format(value);
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString("zh-CN", {month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"}) : "";
}

function escapeHtml(value) {
  const node = document.createElement("span");
  node.textContent = value;
  return node.innerHTML;
}

(async () => {
  try {
    const data = await api("/api/auth/me");
    await showApp(data.user);
  } catch (_) {
    showLogin();
  }
})();
