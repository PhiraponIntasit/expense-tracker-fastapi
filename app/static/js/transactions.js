import {
  api,
  currentMonth,
  el,
  formatBaht,
  formatDay,
  isMonth,
  showError,
  todayISO,
} from "./common.js";

const PAGE_SIZE = 50;
const $ = (id) => document.getElementById(id);
const filtersForm = $("filters");
const errorBox = $("error");
const editor = $("editor");
const editorForm = $("editor-form");
const editorError = $("editor-error");

const params = new URLSearchParams(window.location.search);
const state = {
  // An explicit empty month in the URL means "all time".
  month: params.has("month") ? (isMonth(params.get("month")) ? params.get("month") : "") : currentMonth(),
  type: ["income", "expense"].includes(params.get("type")) ? params.get("type") : "",
  categoryId: /^\d+$/.test(params.get("category_id") ?? "") ? params.get("category_id") : "",
  offset: 0,
  categories: [],
  editingId: null,
};
let latestRequest = 0;

function filterQuery() {
  const query = new URLSearchParams();
  if (state.month) query.set("month", state.month);
  if (state.type) query.set("type", state.type);
  if (state.categoryId) query.set("category_id", state.categoryId);
  return query;
}

// --- categories (filter + editor selects) --------------------------------------

function categoryOptions(select, placeholder) {
  const groups = ["expense", "income"].map((type) =>
    el(
      "optgroup",
      { label: type === "expense" ? "Expenses" : "Income" },
      state.categories
        .filter((c) => c.type === type)
        .map((c) => el("option", { value: c.id }, c.name)),
    ),
  );
  select.replaceChildren(...(placeholder ? [el("option", { value: "" }, placeholder)] : []), ...groups);
}

async function loadCategories() {
  state.categories = await api("/api/categories");
  categoryOptions(filtersForm.elements.category_id, "All categories");
  categoryOptions(editorForm.elements.category_id, null);
  filtersForm.elements.category_id.value = state.categoryId;
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
  const count = `${page.total} ${page.total === 1 ? "transaction" : "transactions"}`;
  const totals = [];
  if (state.type !== "expense") totals.push(`income ${formatBaht(page.income)}`);
  if (state.type !== "income") totals.push(`expenses ${formatBaht(page.expense)}`);
  $("summary").textContent = `${count} · ${totals.join(" · ")}`;

  $("rows").replaceChildren(...page.items.map(renderRow));
  $("empty").hidden = page.items.length > 0;

  const first = page.total ? state.offset + 1 : 0;
  const last = state.offset + page.items.length;
  $("page-info").textContent = page.total ? `${first}–${last} of ${page.total}` : "";
  $("prev-page").disabled = state.offset === 0;
  $("next-page").disabled = last >= page.total;
}

function renderRow(t) {
  const income = t.category.type === "income";
  return el(
    "tr",
    {},
    el("td", { className: "date" }, formatDay(t.occurred_on)),
    el(
      "td",
      {},
      t.category.name,
      el("span", { className: "type-badge" }, income ? "income" : "expense"),
      t.note ? el("small", { className: "note-inline muted" }, t.note) : null,
    ),
    el("td", { className: "col-note" }, t.note ?? ""),
    el("td", { className: "num" }, `${income ? "+" : "−"}${formatBaht(t.amount)}`),
    el(
      "td",
      { className: "actions" },
      el("button", { type: "button", className: "secondary outline", onclick: () => openEditor(t) }, "Edit"),
      el("button", { type: "button", className: "secondary outline", onclick: () => remove(t) }, "Delete"),
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
    if ($("rows").children.length === 1 && state.offset > 0) state.offset -= PAGE_SIZE;
    await loadTransactions();
  } catch (error) {
    showError(errorBox, error);
  }
}

// --- filters -----------------------------------------------------------------------

function syncFilterInputs() {
  filtersForm.elements.month.value = state.month;
  filtersForm.elements.type.value = state.type;
  filtersForm.elements.category_id.value = state.categoryId;
  const query = filterQuery();
  $("export-link").href = `/api/transactions/export.csv${query.size ? `?${query}` : ""}`;
  // Keep "all time" bookmarkable as an explicit empty month.
  if (!state.month) query.set("month", "");
  window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
}

function applyFilters() {
  state.month = filtersForm.elements.month.value;
  state.type = filtersForm.elements.type.value;
  state.categoryId = filtersForm.elements.category_id.value;
  state.offset = 0;
  syncFilterInputs();
  loadTransactions();
}

filtersForm.addEventListener("change", applyFilters);
filtersForm.addEventListener("submit", (event) => event.preventDefault());
$("all-time").addEventListener("click", () => {
  filtersForm.elements.month.value = "";
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

// --- add / edit dialog ---------------------------------------------------------------

function openEditor(transaction = null) {
  state.editingId = transaction?.id ?? null;
  showError(editorError, null);
  editorForm.reset();
  $("editor-title").textContent = transaction ? "Edit transaction" : "Add transaction";
  const fields = editorForm.elements;
  if (transaction) {
    fields.occurred_on.value = transaction.occurred_on;
    fields.amount.value = transaction.amount;
    fields.category_id.value = transaction.category.id;
    fields.note.value = transaction.note ?? "";
  } else {
    fields.occurred_on.value = todayISO();
    const firstExpense = state.categories.find((c) => c.type === "expense");
    if (firstExpense) fields.category_id.value = firstExpense.id;
  }
  editor.showModal();
  fields.amount.focus();
}

editorForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fields = editorForm.elements;
  const body = {
    occurred_on: fields.occurred_on.value,
    amount: fields.amount.value.trim(),
    category_id: Number(fields.category_id.value),
    note: fields.note.value.trim() || null,
  };
  const editing = state.editingId !== null;
  try {
    await api(editing ? `/api/transactions/${state.editingId}` : "/api/transactions", {
      method: editing ? "PATCH" : "POST",
      body,
    });
    editor.close();
    await loadTransactions();
  } catch (error) {
    showError(editorError, error);
  }
});

editor.querySelectorAll("[data-close]").forEach((button) =>
  button.addEventListener("click", () => editor.close()),
);
$("add-button").addEventListener("click", () => openEditor());

// --- start -------------------------------------------------------------------------

async function start() {
  try {
    await loadCategories();
  } catch (error) {
    showError(errorBox, error);
    return;
  }
  syncFilterInputs();
  await loadTransactions();
  if (params.has("new")) openEditor();
}

start();
