import { api, currentMonth, el, formatBaht, formatDay, icon, isMonth, showError, toast } from "./common.js";
import { openEditor } from "./editor.js";
import { txRow } from "./tx.js";

const PAGE_SIZE = 50;
const $ = (id) => document.getElementById(id);
const filtersForm = $("filters");
const errorBox = $("error");

const params = new URLSearchParams(window.location.search);
const state = {
  // An explicit empty month in the URL means "all time".
  month: params.has("month") ? (isMonth(params.get("month")) ? params.get("month") : "") : currentMonth(),
  type: ["income", "expense"].includes(params.get("type")) ? params.get("type") : "",
  categoryId: /^\d+$/.test(params.get("category_id") ?? "") ? params.get("category_id") : "",
  offset: 0,
  categories: [],
};
let latestRequest = 0;

function filterQuery() {
  const query = new URLSearchParams();
  if (state.month) query.set("month", state.month);
  if (state.type) query.set("type", state.type);
  if (state.categoryId) query.set("category_id", state.categoryId);
  return query;
}

// --- category filter ---------------------------------------------------------------

function renderCategoryFilter() {
  const select = filtersForm.elements.category_id;
  const types = state.type ? [state.type] : ["expense", "income"];
  const groups = types.map((type) =>
    el(
      "optgroup",
      { label: type === "expense" ? "Expenses" : "Income" },
      state.categories.filter((c) => c.type === type).map((c) => el("option", { value: c.id }, c.name)),
    ),
  );
  select.replaceChildren(el("option", { value: "" }, "All categories"), ...groups);
  // Drop a selected category that the type filter just hid.
  if (![...select.options].some((o) => o.value === state.categoryId)) state.categoryId = "";
  select.value = state.categoryId;
}

// --- list ------------------------------------------------------------------------

async function loadTransactions() {
  const request = ++latestRequest;
  const query = filterQuery();
  query.set("limit", PAGE_SIZE);
  query.set("offset", state.offset);
  $("table-wrap").classList.add("is-loading");
  showError(errorBox, null);
  try {
    const page = await api(`/api/transactions?${query}`);
    if (request === latestRequest) renderPage(page);
  } catch (error) {
    if (request === latestRequest) showError(errorBox, error);
  } finally {
    if (request === latestRequest) $("table-wrap").classList.remove("is-loading");
  }
}

function renderPage(page) {
  const income = Number(page.income);
  const expense = Number(page.expense);
  $("count-label").textContent = `Net · ${page.total} ${page.total === 1 ? "transaction" : "transactions"}`;
  $("total-net").textContent = formatBaht(income - expense);
  $("total-income").textContent = state.type === "expense" ? "–" : formatBaht(income);
  $("total-expense").textContent = state.type === "income" ? "–" : formatBaht(expense);

  $("rows").replaceChildren(...groupByDay(page.items));
  $("empty").hidden = page.items.length > 0;

  const first = page.total ? state.offset + 1 : 0;
  const last = state.offset + page.items.length;
  $("page-info").textContent = page.total ? `${first}–${last} of ${page.total}` : "";
  $("prev-page").disabled = state.offset === 0;
  $("next-page").disabled = last >= page.total;
}

function groupByDay(items) {
  const days = new Map();
  for (const t of items) {
    if (!days.has(t.occurred_on)) days.set(t.occurred_on, []);
    days.get(t.occurred_on).push(t);
  }
  return [...days].map(([day, rows]) => {
    const net = rows.reduce((sum, t) => sum + (t.category.type === "income" ? 1 : -1) * Number(t.amount), 0);
    return el(
      "section",
      { className: "day-group" },
      el(
        "div",
        { className: "day-head" },
        el("span", {}, formatDay(day)),
        el("span", {}, `${net >= 0 ? "+" : "−"}${formatBaht(Math.abs(net))}`),
      ),
      el("ul", { className: "tx-list" }, rows.map((t) => txRow(t, { showDate: false, actions: rowActions(t) }))),
    );
  });
}

function rowActions(t) {
  const label = `${t.category.name} ${formatBaht(t.amount)} on ${formatDay(t.occurred_on)}`;
  return el(
    "div",
    { className: "tx-actions" },
    el(
      "button",
      { type: "button", className: "icon-button ghost", "aria-label": `Edit ${label}`, title: "Edit", onclick: () => openEditor(t) },
      icon("edit"),
    ),
    el(
      "button",
      { type: "button", className: "icon-button ghost", "aria-label": `Delete ${label}`, title: "Delete", onclick: () => remove(t) },
      icon("trash"),
    ),
  );
}

async function remove(t) {
  if (!window.confirm(`Delete the ${formatBaht(t.amount)} ${t.category.name} transaction on ${formatDay(t.occurred_on)}?`)) {
    return;
  }
  try {
    await api(`/api/transactions/${t.id}`, { method: "DELETE" });
    // Step back a page if this removed the last row on it.
    if ($("rows").querySelectorAll(".tx").length === 1 && state.offset > 0) state.offset -= PAGE_SIZE;
    toast("Transaction deleted");
    await loadTransactions();
  } catch (error) {
    showError(errorBox, error);
  }
}

// --- filters -----------------------------------------------------------------------

function syncFilterInputs() {
  filtersForm.elements.month.value = state.month;
  for (const pill of $("type-pills").querySelectorAll("button")) {
    pill.setAttribute("aria-pressed", String(pill.dataset.type === state.type));
  }
  renderCategoryFilter();
  const query = filterQuery();
  $("export-link").href = `/api/transactions/export.csv${query.size ? `?${query}` : ""}`;
  // Keep "all time" bookmarkable as an explicit empty month.
  if (!state.month) query.set("month", "");
  window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
}

function applyFilters() {
  state.offset = 0;
  syncFilterInputs();
  loadTransactions();
}

filtersForm.addEventListener("change", () => {
  state.month = filtersForm.elements.month.value;
  state.categoryId = filtersForm.elements.category_id.value;
  applyFilters();
});
filtersForm.addEventListener("submit", (event) => event.preventDefault());
$("type-pills").addEventListener("click", (event) => {
  const pill = event.target.closest("button[data-type]");
  if (!pill) return;
  state.type = pill.dataset.type;
  applyFilters();
});
$("all-time").addEventListener("click", () => {
  state.month = "";
  applyFilters();
});
$("prev-page").addEventListener("click", () => {
  state.offset = Math.max(0, state.offset - PAGE_SIZE);
  loadTransactions();
});
$("next-page").addEventListener("click", () => {
  state.offset += PAGE_SIZE;
  loadTransactions();
});
window.addEventListener("transactions:changed", loadTransactions);

// --- start -------------------------------------------------------------------------

async function start() {
  try {
    state.categories = await api("/api/categories");
  } catch (error) {
    showError(errorBox, error);
    return;
  }
  syncFilterInputs();
  await loadTransactions();
}

start();
