"use strict";

// ---------------------------------------------------------------- diagnostics
// Help diagnose missing zoom plugin (most common cause: cached old HTML).
if (typeof Chart === "undefined") {
  console.error("[chart] Chart.js 未加载");
} else if (!Chart.registry.plugins.get("zoom")) {
  console.warn(
    "[chart] zoom 插件未注册 — 检查 chartjs-plugin-zoom 是否被加载（按 Ctrl+F5 强制刷新通常能解决）",
  );
} else if (typeof Hammer === "undefined") {
  console.warn(
    "[chart] zoom 已注册但 hammer.js 未加载 — 滚轮缩放可用但鼠标拖拽平移会失效",
  );
} else {
  console.log("[chart] zoom + hammer 就绪 ✓");
}

// ---------------------------------------------------------------- state
const POLL_INTERVAL = window.POLL_INTERVAL || 10;
const state = {
  characters: [],            // [{id,name,gender,group,image,vote_count}]
  selected: new Set(),       // selected vote_ids
  series: new Map(),         // vote_id -> [{x: Date, y: count}, ...]
  lastTs: new Map(),         // vote_id -> latest ts loaded
  filter: "all",
  search: "",
  mode: localStorage.getItem("mode") || "cumulative",  // "cumulative" | "delta"
};

// ---------------------------------------------------------------- color
// Distinct, deterministic color per character via golden-angle HSL spread.
function colorFor(id) {
  const hue = (id * 137.508) % 360;          // golden angle
  return `hsl(${hue.toFixed(0)} 70% 60%)`;
}

// ---------------------------------------------------------------- chart
const ctx = document.getElementById("chart").getContext("2d");
const chart = new Chart(ctx, {
  type: "line",
  data: { datasets: [] },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    parsing: false,
    interaction: { mode: "nearest", axis: "x", intersect: false },
    plugins: {
      legend: { labels: { color: "#e6e8ee", boxWidth: 14 } },
      tooltip: {
        callbacks: {
          title: (items) => new Date(items[0].parsed.x).toLocaleString("zh-CN"),
          label: (item) => {
            const y = item.parsed.y;
            if (state.mode === "delta") {
              const sign = y >= 0 ? "+" : "";
              return `${item.dataset.label}: ${sign}${y.toLocaleString()} 票`;
            }
            return `${item.dataset.label}: ${y.toLocaleString()}`;
          },
        },
      },
      zoom: {
        pan: {
          enabled: true,
          mode: "xy",
          threshold: 5,              // 抖动 5px 内当点击，不触发平移
          onPanStart: ({ chart }) => {
            console.log("[chart] pan start");
            chart.canvas.classList.add("panning");
          },
          onPanComplete: ({ chart }) => {
            console.log("[chart] pan end");
            chart.canvas.classList.remove("panning");
          },
        },
        zoom: {
          wheel: { enabled: true, speed: 0.1 },
          pinch: { enabled: true },
          mode: "xy",
        },
        limits: {
          x: { minRange: 5000 },     // 至少保留 5s 视窗
          y: { min: 0 },             // 累计模式不允许下探到 0 以下
        },
      },
    },
    scales: {
      x: {
        type: "time",
        time: { tooltipFormat: "yyyy-MM-dd HH:mm:ss" },
        ticks: { color: "#8a93a6" },
        grid: { color: "rgba(255,255,255,0.05)" },
      },
      y: {
        beginAtZero: true,
        ticks: {
          color: "#8a93a6",
          precision: 0,                       // 累计票数为整数，默认无小数刻度
          callback: (v) => v.toLocaleString(),
        },
        grid: { color: "rgba(255,255,255,0.05)" },
        title: { display: false, text: "", color: "#8a93a6" },
      },
    },
  },
});

// Convert cumulative [{x,y}, ...] into raw per-record increments.
// 票数本身是整数，相邻记录的差值也必然是整数 — 不做时间归一化。
function toDeltaSeries(points) {
  if (points.length < 2) return [];
  const out = [];
  for (let i = 1; i < points.length; i++) {
    out.push({ x: points[i].x, y: points[i].y - points[i - 1].y });
  }
  return out;
}

function getDisplayPoints(id) {
  const raw = state.series.get(id) || [];
  return state.mode === "delta" ? toDeltaSeries(raw) : raw;
}

function rebuildDatasets() {
  chart.data.datasets = [...state.selected].map((id) => {
    const c = state.characters.find((x) => x.id === id);
    return {
      label: c ? c.name : `#${id}`,
      data: getDisplayPoints(id),
      borderColor: colorFor(id),
      backgroundColor: colorFor(id),
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.15,
      stepped: false,
    };
  });
  const yScale = chart.options.scales.y;
  const yLimits = chart.options.plugins.zoom.limits.y;
  if (state.mode === "delta") {
    // 增幅是相邻记录的票数差，依然是整数，且票数只增不减，y 也锁 0
    yScale.ticks.precision = 0;
    yLimits.min = 0;
    yScale.title.display = true;
    yScale.title.text = "新增票数";
  } else {
    // 累计票数：整数刻度，y 下限锁在 0
    yScale.ticks.precision = 0;
    yLimits.min = 0;
    yScale.title.display = false;
  }
  yScale.beginAtZero = true;
  chart.update("none");
}

// ---------------------------------------------------------------- data
async function loadCharacters() {
  const res = await fetch("/api/characters");
  state.characters = await res.json();
  renderList();
}

async function loadSeries(ids, since = 0) {
  if (!ids.length) return;
  const res = await fetch(`/api/series?ids=${ids.join(",")}&since=${since}`);
  const data = await res.json();
  for (const id of ids) {
    const points = (data[id] || []).map(([ts, c]) => ({ x: ts * 1000, y: c }));
    if (since === 0) {
      state.series.set(id, points);
    } else {
      const arr = state.series.get(id) || [];
      arr.push(...points);
      state.series.set(id, arr);
    }
    if (points.length) {
      const lastTs = points[points.length - 1].x / 1000;
      state.lastTs.set(id, Math.max(state.lastTs.get(id) || 0, lastTs));
    }
  }
}

async function refreshAll() {
  // Always refresh sidebar counts + status, even with nothing selected — the
  // sidebar should reflect the latest scrape regardless of chart state.
  await refreshCounts();
  updateStatus();
  const ids = [...state.selected];
  if (!ids.length) return;
  const minSince = Math.min(...ids.map((id) => state.lastTs.get(id) || 0));
  await loadSeries(ids, minSince);
  rebuildDatasets();
}

async function refreshCounts() {
  const res = await fetch("/api/characters");
  const list = await res.json();
  const newIds = list.map((c) => c.id).join(",");
  const oldIds = state.characters.map((c) => c.id).join(",");
  if (newIds !== oldIds) {
    // Roster changed (new stage activated characters) — full re-render.
    state.characters = list;
    renderList();
    return;
  }
  const map = new Map(list.map((c) => [c.id, c.vote_count]));
  for (const c of state.characters) c.vote_count = map.get(c.id) ?? c.vote_count;
  for (const li of document.querySelectorAll(".char-item")) {
    const id = Number(li.dataset.id);
    const v = map.get(id);
    if (v != null) li.querySelector(".char-count").textContent = v.toLocaleString();
  }
}

// ---------------------------------------------------------------- status
function stageLabel(stage) {
  return ({ 5: "第一轮投票", 6: "第二轮投票", 7: "复活赛", 8: "决赛" })[stage] || `阶段 ${stage}`;
}

async function updateStatus() {
  try {
    const r = await fetch("/api/status");
    const s = await r.json();
    const dot = document.getElementById("status-dot");
    const txt = document.getElementById("status-text");
    if (s.last_error) {
      dot.className = "dot err";
      txt.textContent = "出错: " + s.last_error;
      return;
    }
    if (!s.last_ts) {
      dot.className = "dot warn";
      txt.textContent = "等待第一次抓取…";
      return;
    }
    const age = Math.floor(Date.now() / 1000 - s.last_ts);
    const t = new Date(s.last_ts * 1000).toLocaleTimeString("zh-CN");
    const stage = stageLabel(s.stage);
    let msg;
    if (s.last_total === 0) {
      // lstV 为空，意味着投票未开启或本阶段已结束
      dot.className = "dot warn";
      msg = `${stage}未开启 · 当前候选 ${s.roster_size} 人 · 最后检查 ${t} (${age}s 前)`;
    } else {
      dot.className = age <= POLL_INTERVAL * 3 ? "dot ok" : "dot warn";
      msg = `${stage}进行中 · 跟踪 ${s.last_total}/${s.roster_size} 人 · 最近更新 ${t} (${age}s 前)`;
    }
    txt.textContent = msg;
  } catch {
    document.getElementById("status-dot").className = "dot err";
    document.getElementById("status-text").textContent = "无法连接服务";
  }
}

// ---------------------------------------------------------------- list UI
function renderList() {
  const ul = document.getElementById("char-list");
  ul.innerHTML = "";
  for (const c of state.characters) {
    const li = document.createElement("li");
    li.className = "char-item";
    li.dataset.id = c.id;
    li.dataset.gender = c.gender;
    li.innerHTML = `
      <input type="checkbox" />
      <span class="color-chip" style="background:${colorFor(c.id)}"></span>
      <span class="char-name">${escapeHtml(c.name)}</span>
      <span class="char-gender ${c.gender}">${genderLabel(c.gender)}</span>
      <span class="char-count">${(c.vote_count || 0).toLocaleString()}</span>
    `;
    li.addEventListener("click", (e) => {
      if (e.target.tagName !== "INPUT") {
        const cb = li.querySelector("input");
        cb.checked = !cb.checked;
      }
      toggleSelected(c.id, li.querySelector("input").checked);
    });
    ul.appendChild(li);
  }
  applyFilter();
  updateSelectedUI();
}

function applyFilter() {
  const q = state.search.toLowerCase();
  for (const li of document.querySelectorAll(".char-item")) {
    const matchGender = state.filter === "all" || li.dataset.gender === state.filter;
    const name = li.querySelector(".char-name").textContent.toLowerCase();
    const matchSearch = !q || name.includes(q);
    li.classList.toggle("hidden", !(matchGender && matchSearch));
  }
}

function genderLabel(g) {
  return g === "female" ? "女" : g === "male" ? "男" : g === "mascot" ? "萌宠" : g;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[m]));
}

function updateSelectedUI() {
  for (const li of document.querySelectorAll(".char-item")) {
    const id = Number(li.dataset.id);
    const cb = li.querySelector("input");
    cb.checked = state.selected.has(id);
    li.classList.toggle("selected", cb.checked);
  }
  document.getElementById("selected-count").textContent = `已选 ${state.selected.size}`;
}

async function toggleSelected(id, on) {
  if (on) {
    state.selected.add(id);
    if (!state.series.has(id)) {
      await loadSeries([id], 0);
    }
  } else {
    state.selected.delete(id);
  }
  // Persist selection across reloads.
  localStorage.setItem("selected", JSON.stringify([...state.selected]));
  updateSelectedUI();
  rebuildDatasets();
}

// ---------------------------------------------------------------- events
document.querySelectorAll(".pill").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".pill").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.filter = btn.dataset.gender;
    applyFilter();
  });
});

document.getElementById("search").addEventListener("input", (e) => {
  state.search = e.target.value;
  applyFilter();
});

document.getElementById("select-top10").addEventListener("click", async () => {
  const top = [...state.characters]
    .sort((a, b) => (b.vote_count || 0) - (a.vote_count || 0))
    .slice(0, 10);
  for (const c of top) {
    if (!state.selected.has(c.id)) await toggleSelected(c.id, true);
  }
});

document.getElementById("select-none").addEventListener("click", () => {
  state.selected.clear();
  state.series.clear();
  state.lastTs.clear();
  localStorage.setItem("selected", "[]");
  updateSelectedUI();
  rebuildDatasets();
});

document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const next = btn.dataset.mode;
    if (next === state.mode) return;
    document.querySelectorAll(".mode-btn").forEach((b) =>
      b.classList.toggle("active", b.dataset.mode === next),
    );
    state.mode = next;
    localStorage.setItem("mode", next);
    // Different y-scale magnitude — clear any prior zoom so the new view fits.
    chart.resetZoom("none");
    rebuildDatasets();
  });
});

function syncModeButtons() {
  document.querySelectorAll(".mode-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.mode === state.mode),
  );
}

document.getElementById("reset-zoom").addEventListener("click", () => {
  chart.resetZoom();
});

// ---------------------------------------------------------------- boot
async function boot() {
  syncModeButtons();
  await loadCharacters();
  // Restore selection from previous session.
  try {
    const saved = JSON.parse(localStorage.getItem("selected") || "[]");
    for (const id of saved) state.selected.add(Number(id));
  } catch {}
  if (state.selected.size) {
    await loadSeries([...state.selected], 0);
    updateSelectedUI();
  }
  // Always rebuild so the y-axis title/beginAtZero reflect the restored mode.
  rebuildDatasets();
  updateStatus();
  setInterval(refreshAll, POLL_INTERVAL * 1000);
}

boot();
