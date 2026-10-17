import { api, el, icon, showError, toast } from "./common.js";

const $ = (id) => document.getElementById(id);
const errorBox = $("error");
const addForm = $("add-form");
let newType = "expense";

async function load() {
  try {
    render(await api("/api/categories"));
  } catch (error) {
    showError(errorBox, error);
  }
}

function render(categories) {
  for (const type of ["expense", "income"]) {
    const items = categories.filter((c) => c.type === type);
    $(`${type}-list`).replaceChildren(...items.map(renderRow));
    $(`${type}-count`).textContent = `${items.length}`;
  }
}

function renderRow(category) {
  const input = el("input", {
    type: "text",
    value: category.name,
    maxlength: "50",
    required: true,
    "aria-label": `Name of ${category.name}`,
  });
  const save = el(
    "button",
    { type: "submit", className: "icon-button ghost", "aria-label": `Save name of ${category.name}`, title: "Save", hidden: true },
    icon("check"),
  );
  input.addEventListener("input", () => {
    save.hidden = input.value.trim() === category.name;
  });
  const remove = el(
    "button",
    {
      type: "button",
      className: "icon-button ghost",
      "aria-label": `Delete ${category.name}`,
      title: "Delete",
      onclick: () => deleteCategory(category),
    },
    icon("trash"),
  );
  return el(
    "form",
    {
      className: "category-row",
      onsubmit: async (event) => {
        event.preventDefault();
        if (input.value.trim() === category.name) return;
        await run("Category renamed", () =>
          api(`/api/categories/${category.id}`, { method: "PATCH", body: { name: input.value } }),
        );
      },
    },
    input,
    save,
    remove,
  );
}

async function deleteCategory(category) {
  if (!window.confirm(`Delete the category "${category.name}"?`)) return;
  await run("Category deleted", () => api(`/api/categories/${category.id}`, { method: "DELETE" }));
}

// Runs a change, then reloads the list; errors (e.g. 409 conflicts) are shown inline.
async function run(message, change) {
  showError(errorBox, null);
  try {
    await change();
    toast(message);
    window.dispatchEvent(new CustomEvent("categories:changed"));
  } catch (error) {
    showError(errorBox, error);
  }
  await load();
}

$("new-type").addEventListener("click", (event) => {
  const pill = event.target.closest("button[data-type]");
  if (!pill) return;
  newType = pill.dataset.type;
  for (const button of $("new-type").querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button === pill));
  }
});

addForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = addForm.elements.name;
  await run("Category added", async () => {
    await api("/api/categories", { method: "POST", body: { name: name.value, type: newType } });
    name.value = "";
  });
});

load();
