// One transaction row, shared by the dashboard's "recent" list and the
// transactions page.
import { el, formatBaht, formatDay, icon } from "./common.js";

export function signedAmount(t) {
  const income = t.category.type === "income";
  return `${income ? "+" : "−"}${formatBaht(t.amount)}`;
}

export function txRow(t, { actions = null, showDate = true } = {}) {
  const kind = t.category.type;
  const sub = [showDate ? formatDay(t.occurred_on) : null, t.note].filter(Boolean).join(" · ");
  return el(
    "li",
    { className: "tx" },
    el(
      "span",
      { className: `badge-icon ${kind}`, title: kind === "income" ? "Income" : "Expense" },
      icon(kind),
    ),
    el(
      "div",
      { className: "tx-main" },
      el("p", { className: "tx-title" }, t.category.name),
      el("p", { className: "tx-sub" }, sub || (kind === "income" ? "Income" : "Expense")),
    ),
    el("span", { className: `amount ${kind}` }, signedAmount(t)),
    actions ?? el("span"),
  );
}
