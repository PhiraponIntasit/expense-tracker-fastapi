// Show progress on "Try the demo" and stop double clicks from creating two accounts.
const form = document.getElementById("demo-form");
form?.addEventListener("submit", () => {
  const button = form.querySelector("button");
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = "Preparing your demo…";
});
