// Loaded synchronously in <head> so the page never flashes the wrong theme.
// The choice is remembered per browser; until the user picks one, the page
// follows the operating system setting.
(function () {
  var KEY = "theme";
  var media = window.matchMedia("(prefers-color-scheme: dark)");

  function stored() {
    try {
      var value = localStorage.getItem(KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch (e) {
      return null;
    }
  }

  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      var next = theme === "dark" ? "light" : "dark";
      button.setAttribute("aria-label", "Switch to " + next + " mode");
      button.setAttribute("aria-pressed", String(theme === "dark"));
      var label = button.querySelector("[data-theme-label]");
      if (label) label.textContent = theme === "dark" ? "Light mode" : "Dark mode";
    });
    window.dispatchEvent(new CustomEvent("themechange", { detail: { theme: theme } }));
  }

  apply(stored() || (media.matches ? "dark" : "light"));

  media.addEventListener("change", function (event) {
    if (!stored()) apply(event.matches ? "dark" : "light");
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-theme-toggle]");
    if (!button) return;
    var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(KEY, next);
    } catch (e) {
      /* private mode: the toggle still works for this page */
    }
    apply(next);
  });

  // Buttons rendered after this script ran still need their labels.
  document.addEventListener("DOMContentLoaded", function () {
    apply(document.documentElement.getAttribute("data-theme"));
  });
})();
