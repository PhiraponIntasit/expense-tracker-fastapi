import { api, el, showError } from "./common.js";

const $ = (id) => document.getElementById(id);
const errorBox = $("error");
const addForm = $("add-form");

async function load() {
  try {
    render(await api("/api/categories"));
  } catch (error) {
    showError(errorBox, error);
  }
}

function render(categories) {
  for (const type of ["expense", "income"]) {
    $(`${type}-list`).replaceChildren(
      ...categories.filter((c) => c.type === type).map(renderRow),
    );
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
  const save = el("button", { type: "submit", className: "secondary outline" }, "Rename");
  const remove = el(
    "button",
    { type: "button", className: "secondary outline", onclick: () => deleteCategory(category) },
    "Delete",
  );
  return el(
    "form",
    {
      className: "category-row",
      onsubmit: async (event) => {
        event.preventDefault();
        await run(() =>
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
  await run(() => api(`/api/categories/${category.id}`, { method: "DELETE" }));
}

// Runs a change, then reloads the list; errors (e.g. 409 conflicts) are shown inline.
async function run(change) {
  showError(errorBox, null);
  try {
    await change();
  } catch (error) {
    showError(errorBox, error);
  }
  await load();
}

addForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fields = addForm.elements;
  await run(async () => {
    await api("/api/categories", {
      method: "POST",
      body: { name: fields.name.value, type: fields.type.value },
    });
    fields.name.value = "";
  });
});

load();
