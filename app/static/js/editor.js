// The add/edit transaction dialog, available on every app page. Pages react
// to the "transactions:changed" event instead of knowing about the dialog.
import { api, showError, toast, todayISO } from "./common.js";

const dialog = document.getElementById("editor");
const form = document.getElementById("editor-form");
const errorBox = document.getElementById("editor-error");
const fields = form.elements;
let categories = null;
let editingId = null;

async function loadCategories() {
  categories ??= await api("/api/categories");
  return categories;
}

function fillCategories(type, selectedId) {
  if (!categories) return; // still loading; openEditor fills it when ready
  const options = categories
    .filter((c) => c.type === type)
    .map((c) => new Option(c.name, c.id, false, c.id === selectedId));
  fields.category_id.replaceChildren(...options);
}

function currentType() {
  return form.querySelector("input[name=type]:checked").value;
}

export async function openEditor(transaction = null) {
  showError(errorBox, null);
  form.reset();
  editingId = transaction?.id ?? null;
  document.getElementById("editor-title").textContent = transaction
    ? "Edit transaction"
    : "Add transaction";
  const type = transaction?.category.type ?? "expense";
  form.querySelector(`input[name=type][value=${type}]`).checked = true;
  form.dataset.type = type;
  fields.occurred_on.value = transaction?.occurred_on ?? todayISO();
  fields.amount.value = transaction?.amount ?? "";
  fields.note.value = transaction?.note ?? "";
  // Open straight away; categories fill in as soon as they arrive (usually
  // already cached by the prefetch below).
  dialog.showModal();
  fields.amount.focus();
  if (!categories) {
    fields.category_id.replaceChildren(new Option("Loading…", ""));
    fields.category_id.disabled = true;
  }
  try {
    await loadCategories();
    fillCategories(currentType(), transaction?.category.id);
  } catch (error) {
    showError(errorBox, error);
  } finally {
    fields.category_id.disabled = false;
  }
}

form.addEventListener("change", (event) => {
  if (event.target.name !== "type") return;
  form.dataset.type = currentType();
  fillCategories(currentType());
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const amount = fields.amount.value.trim().replace(/,/g, "");
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(amount) || Number(amount) <= 0) {
    showError(errorBox, "Enter a positive amount, like 120 or 89.50.");
    fields.amount.focus();
    return;
  }
  const body = {
    occurred_on: fields.occurred_on.value,
    amount,
    category_id: Number(fields.category_id.value),
    note: fields.note.value.trim() || null,
  };
  const save = document.getElementById("editor-save");
  save.setAttribute("aria-busy", "true");
  try {
    const editing = editingId !== null;
    await api(editing ? `/api/transactions/${editingId}` : "/api/transactions", {
      method: editing ? "PATCH" : "POST",
      body,
    });
    dialog.close();
    toast(editing ? "Transaction updated" : "Transaction added");
    window.dispatchEvent(new CustomEvent("transactions:changed"));
  } catch (error) {
    showError(errorBox, error);
  } finally {
    save.removeAttribute("aria-busy");
  }
});

dialog.querySelectorAll("[data-close]").forEach((button) =>
  button.addEventListener("click", () => dialog.close()),
);
// Close when clicking the backdrop.
dialog.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-add-transaction]")) openEditor();
});
window.addEventListener("categories:changed", () => {
  categories = null;
});

if (new URLSearchParams(window.location.search).has("new")) openEditor();
// Warm the category cache so the dialog's select is ready when it opens.
else loadCategories().catch(() => {});
