// Apply the saved theme before the stylesheet paints (CSP forbids inline scripts).
(function () {
  var theme = "light";
  try { theme = localStorage.getItem("gsi-theme") === "dark" ? "dark" : "light"; } catch (e) { /* storage blocked */ }
  document.documentElement.setAttribute("data-theme", theme);
})();
