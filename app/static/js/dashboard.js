import {
  addMonths,
  api,
  cssVar,
  currentMonth,
  el,
  formatBaht,
  formatBahtCompact,
  formatMonth,
  isMonth,
  showError,
} from "./common.js";

const { Chart } = window;
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;

const $ = (id) => document.getElementById(id);
const errorBox = $("error");
const loadingTargets = [$("tiles"), $("monthly-card"), $("breakdown-card")];

const params = new URLSearchParams(window.location.search);
const state = {
  month: isMonth(params.get("month")) ? params.get("month") : currentMonth(),
  months: [], // the 12 months shown in the chart
  totals: new Map(), // month -> {income, expense, net}, includes the month before the chart
  breakdown: [],
};
const charts = { monthly: null, breakdown: null };
let latestRequest = 0;

// The chart shows 12 months ending this month, unless the selected month is
// outside that window, in which case the window ends at the selected month.
function windowEnd(selected) {
  const now = currentMonth();
  return selected > now || selected < addMonths(now, -11) ? selected : now;
}

function theme() {
  const card = $("monthly-card");
  return {
    income: cssVar("--series-income"),
    expense: cssVar("--series-expense"),
    net: cssVar("--series-net"),
    text: cssVar("--chart-text"),
    muted: cssVar("--chart-muted"),
    grid: cssVar("--chart-grid"),
    axis: cssVar("--chart-axis"),
    band: cssVar("--chart-band"),
    surface: cssVar("--pico-card-background-color", card),
  };
}

// --- data ----------------------------------------------------------------------

async function load() {
  const request = ++latestRequest;
  loadingTargets.forEach((node) => node.classList.add("is-loading"));
  showError(errorBox, null);
  const end = windowEnd(state.month);
  try {
    // One extra month before the window so the first month still has a "vs last month".
    const [monthly, breakdown] = await Promise.all([
      api(`/api/summary/monthly?from=${addMonths(end, -12)}&to=${end}`),
      api(`/api/summary/by-category?month=${state.month}&type=expense`),
    ]);
    if (request !== latestRequest) return; // a newer selection has superseded this one
    state.totals = new Map(monthly.map((m) => [m.month, m]));
    state.months = monthly.slice(1).map((m) => m.month);
    state.breakdown = breakdown;
    render();
  } catch (error) {
    if (request === latestRequest) showError(errorBox, error);
  } finally {
    if (request === latestRequest) {
      loadingTargets.forEach((node) => node.classList.remove("is-loading"));
    }
  }
}

function selectMonth(month) {
  if (month === state.month) return;
  state.month = month;
  const url = new URL(window.location.href);
  url.searchParams.set("month", month);
  window.history.replaceState(null, "", url);
  load();
}

// --- rendering -----------------------------------------------------------------

function render() {
  if (!state.months.length) return; // nothing loaded yet
  $("month-title").textContent = formatMonth(state.month);
  $("transactions-link").href = `/transactions?month=${state.month}&new=1`;
  renderTiles();
  renderMonthly();
  renderBreakdown();
}

function renderTiles() {
  const current = state.totals.get(state.month);
  const previousMonth = addMonths(state.month, -1);
  const previous = state.totals.get(previousMonth);
  const versus = `vs ${formatMonth(previousMonth, "short")}`;

  for (const kind of ["income", "expense", "net"]) {
    const tile = document.querySelector(`.tile[data-kind="${kind}"]`);
    tile.querySelector(".tile-value").textContent = formatBaht(current[kind]);
    const delta = tile.querySelector(".tile-delta");
    delta.replaceChildren(...describeChange(kind, Number(current[kind]), Number(previous[kind]), versus));
  }
}

// Income and expenses compare as a percentage. Net can cross zero, where a
// percentage is meaningless, so it compares as an amount.
function describeChange(kind, now, before, versus) {
  const change = now - before;
  if (Math.abs(change) < 0.005) return [`No change ${versus}`];
  if (kind !== "net" && before === 0) return [`Nothing ${versus}`];

  const upIsGood = kind !== "expense";
  const good = change > 0 === upIsGood;
  const sign = change > 0 ? "+" : "−";
  const amount =
    kind === "net"
      ? `${sign}${formatBaht(Math.abs(change))}`
      : `${sign}${Math.abs((change / before) * 100).toFixed(0)}%`;
  const arrow = el(
    "span",
    { className: `arrow ${good ? "good" : "bad"}`, "aria-hidden": "true" },
    change > 0 ? "▲" : "▼",
  );
  return [arrow, `${amount} ${versus}`];
}

// Shades the selected month's column so it stays visible while the bars keep
// their series colors.
const selectedBand = {
  id: "selectedBand",
  beforeDatasetsDraw(chart, _args, options) {
    const { index, color } = options;
    if (index === undefined || index < 0) return;
    const { ctx, chartArea, scales } = chart;
    const count = chart.data.labels.length;
    const width = count > 1 ? scales.x.getPixelForValue(1) - scales.x.getPixelForValue(0) : chartArea.width;
    const center = scales.x.getPixelForValue(index);
    ctx.save();
    ctx.fillStyle = color;
    ctx.fillRect(center - width / 2, chartArea.top, width, chartArea.bottom - chartArea.top);
    ctx.restore();
  },
};

function legendLabels(chart) {
  // Legend keys mirror the mark: a filled square for bars, a short line for the
  // line. Listed in dataset order (Chart.js would otherwise sort by draw order).
  const items = Chart.defaults.plugins.legend.labels.generateLabels(chart);
  items.sort((a, b) => a.datasetIndex - b.datasetIndex);
  return items.map((item) => {
    const dataset = chart.data.datasets[item.datasetIndex];
    return dataset.type === "line"
      ? { ...item, pointStyle: "line", lineWidth: 2, strokeStyle: dataset.borderColor }
      : { ...item, pointStyle: "rect", lineWidth: 0 };
  });
}

function renderMonthly() {
  const t = theme();
  const rows = state.months.map((m) => state.totals.get(m));
  const labels = state.months.map((m) => formatMonth(m, "short"));
  const selectedIndex = state.months.indexOf(state.month);
  const bar = { type: "bar", maxBarThickness: 24, borderRadius: 4, borderSkipped: "start", order: 1 };

  const data = {
    labels,
    datasets: [
      { ...bar, label: "Income", data: rows.map((r) => Number(r.income)), backgroundColor: t.income },
      { ...bar, label: "Expenses", data: rows.map((r) => Number(r.expense)), backgroundColor: t.expense },
      {
        type: "line",
        label: "Net",
        data: rows.map((r) => Number(r.net)),
        borderColor: t.net,
        backgroundColor: t.net,
        borderWidth: 2,
        pointRadius: 4,
        pointHoverRadius: 5,
        pointBackgroundColor: t.net,
        pointBorderColor: t.surface,
        pointBorderWidth: 2,
        order: 0,
      },
    ],
  };

  if (charts.monthly) {
    charts.monthly.data = data;
    charts.monthly.options.plugins.selectedBand.index = selectedIndex;
    charts.monthly.update();
  } else {
    charts.monthly = new Chart($("monthly-chart"), {
      data,
      plugins: [selectedBand],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: "index", intersect: false },
        onClick(event, _elements, chart) {
          const [hit] = chart.getElementsAtEventForMode(event, "index", { intersect: false }, false);
          if (hit) selectMonth(state.months[hit.index]);
        },
        onHover(event, elements) {
          event.native.target.style.cursor = elements.length ? "pointer" : "default";
        },
        scales: {
          x: {
            grid: { display: false },
            border: { color: t.axis },
            // On narrow screens skip labels rather than tilting them.
            ticks: { color: t.muted, maxRotation: 0, autoSkip: true, autoSkipPadding: 12 },
          },
          y: {
            grid: { color: t.grid, lineWidth: 1 },
            border: { display: false },
            ticks: { color: t.muted, maxTicksLimit: 6, callback: (value) => formatBahtCompact(value) },
          },
        },
        plugins: {
          legend: {
            position: "top",
            align: "start",
            labels: { color: t.text, usePointStyle: true, generateLabels: legendLabels },
          },
          tooltip: {
            usePointStyle: true,
            itemSort: (a, b) => a.datasetIndex - b.datasetIndex,
            callbacks: {
              title: (items) => formatMonth(state.months[items[0].dataIndex]),
              label: (item) => `${formatBaht(item.raw)}  ${item.dataset.label}`,
              labelPointStyle: () => ({ pointStyle: "line", rotation: 0 }),
              labelColor: (item) => {
                const color = item.dataset.type === "line" ? item.dataset.borderColor : item.dataset.backgroundColor;
                return { borderColor: color, backgroundColor: color, borderWidth: 2 };
              },
            },
          },
          selectedBand: { index: selectedIndex, color: t.band },
        },
      },
    });
  }

  const body = $("monthly-table").tBodies[0];
  body.replaceChildren(
    ...state.months
      .slice()
      .reverse()
      .map((month) => {
        const row = state.totals.get(month);
        const link = el(
          "a",
          {
            href: `?month=${month}`,
            "aria-current": month === state.month ? "true" : null,
            onclick: (event) => {
              event.preventDefault();
              selectMonth(month);
            },
          },
          formatMonth(month),
        );
        return el(
          "tr",
          {},
          el("td", {}, link),
          el("td", { className: "num" }, formatBaht(row.income)),
          el("td", { className: "num" }, formatBaht(row.expense)),
          el("td", { className: "num" }, formatBaht(row.net)),
        );
      }),
  );
}

// Draws each bar's value just past its end, in text ink rather than the bar color.
const valueLabels = {
  id: "valueLabels",
  afterDatasetsDraw(chart, _args, options) {
    const { ctx } = chart;
    const meta = chart.getDatasetMeta(0);
    ctx.save();
    ctx.fillStyle = options.color;
    ctx.font = `12px ${Chart.defaults.font.family}`;
    ctx.textBaseline = "middle";
    meta.data.forEach((bar, i) => {
      ctx.fillText(formatBaht(chart.data.datasets[0].data[i]), bar.x + 6, bar.y);
    });
    ctx.restore();
  },
};

function renderBreakdown() {
  const t = theme();
  const items = state.breakdown;
  const total = items.reduce((sum, item) => sum + Number(item.total), 0);
  const monthName = formatMonth(state.month);

  $("breakdown-title").textContent = `Expenses by category · ${monthName}`;
  $("breakdown-subtitle").textContent = items.length
    ? `${formatBaht(total)} across ${items.length} ${items.length === 1 ? "category" : "categories"}`
    : " ";
  $("breakdown-empty").hidden = items.length > 0;
  $("breakdown-box").hidden = items.length === 0;

  const body = $("breakdown-table").tBodies[0];
  body.replaceChildren(
    ...items.map((item) =>
      el(
        "tr",
        {},
        el("td", {}, item.name),
        el("td", { className: "num" }, formatBaht(item.total)),
        el("td", { className: "num" }, `${((Number(item.total) / total) * 100).toFixed(1)}%`),
      ),
    ),
  );

  charts.breakdown?.destroy();
  charts.breakdown = null;
  if (!items.length) return;

  // Height follows the number of categories so bars never get squeezed.
  $("breakdown-box").style.height = `${items.length * 36 + 32}px`;
  charts.breakdown = new Chart($("breakdown-chart"), {
    type: "bar",
    data: {
      labels: items.map((item) => item.name),
      datasets: [
        {
          label: "Expenses",
          data: items.map((item) => Number(item.total)),
          backgroundColor: t.expense,
          maxBarThickness: 24,
          borderRadius: 4,
          borderSkipped: "start",
        },
      ],
    },
    plugins: [valueLabels],
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      layout: { padding: { right: 96 } },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: t.grid, lineWidth: 1 },
          border: { display: false },
          ticks: { color: t.muted, maxTicksLimit: 5, callback: (value) => formatBahtCompact(value) },
        },
        y: {
          grid: { display: false },
          border: { color: t.axis },
          ticks: { color: t.text },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item) => `${formatBaht(item.raw)} · ${((item.raw / total) * 100).toFixed(1)}%`,
          },
        },
        valueLabels: { color: t.text },
      },
    },
  });
}

// --- wiring ------------------------------------------------------------------

$("prev-month").addEventListener("click", () => selectMonth(addMonths(state.month, -1)));
$("next-month").addEventListener("click", () => selectMonth(addMonths(state.month, 1)));

// Dark mode uses its own validated colors, so rebuild the charts when it changes.
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  charts.monthly?.destroy();
  charts.monthly = null;
  render();
});

load();
