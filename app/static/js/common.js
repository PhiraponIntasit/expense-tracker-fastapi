// Helpers shared by every page. Data from the API (category names, notes) is
// user input, so DOM is always built with textContent, never innerHTML.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function describeError(body) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((e) => `${e.loc.at(-1)}: ${e.msg}`).join("; ");
  }
  return "Something went wrong. Please try again.";
}

export async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401) {
    window.location.assign("/login");
    throw new ApiError(401, "Your session has expired.");
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, describeError(data));
  return data;
}

// --- formatting -------------------------------------------------------------

const baht = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "THB",
  currencyDisplay: "narrowSymbol",
});
const bahtCompact = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "THB",
  currencyDisplay: "narrowSymbol",
  notation: "compact",
  maximumFractionDigits: 1,
});

// Amounts arrive as exact decimal strings; Number() is only used for display.
export const formatBaht = (value) => baht.format(Number(value));
export const formatBahtCompact = (value) => bahtCompact.format(Number(value));

// --- months ("YYYY-MM", in the browser's local time) ------------------------

const pad = (n) => String(n).padStart(2, "0");

export function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
}

export function todayISO() {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function addMonths(month, delta) {
  const [year, m] = month.split("-").map(Number);
  const index = year * 12 + (m - 1) + delta;
  return `${Math.floor(index / 12)}-${pad((index % 12) + 1)}`;
}

export function isMonth(value) {
  return /^\d{4}-(0[1-9]|1[0-2])$/.test(value ?? "");
}

const monthFormats = {
  long: new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }),
  short: new Intl.DateTimeFormat("en-US", { month: "short", year: "2-digit" }),
};

export function formatMonth(month, style = "long") {
  const [year, m] = month.split("-").map(Number);
  return monthFormats[style].format(new Date(year, m - 1, 1));
}

const dayFormat = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function formatDay(isoDate) {
  const [year, m, d] = isoDate.split("-").map(Number);
  return dayFormat.format(new Date(year, m - 1, d));
}

// --- DOM ---------------------------------------------------------------------

export function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === undefined || value === null || value === false) continue;
    if (name === "className") node.className = value;
    else if (name === "dataset") Object.assign(node.dataset, value);
    else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else node.setAttribute(name, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function showError(node, error) {
  if (!error) {
    node.hidden = true;
    node.textContent = "";
    return;
  }
  node.textContent = error instanceof Error ? error.message : String(error);
  node.hidden = false;
}

export function cssVar(name, scope = document.documentElement) {
  return getComputedStyle(scope).getPropertyValue(name).trim();
}
