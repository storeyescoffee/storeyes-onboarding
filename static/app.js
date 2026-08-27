"use strict";

function el(id) {
  return document.getElementById(id);
}

/* --- theme toggle ------------------------------------------------------- */
function currentTheme() {
  const forced = document.documentElement.dataset.theme;
  if (forced === "light" || forced === "dark") return forced;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function updateThemeButton() {
  const btn = el("theme-toggle");
  if (btn) btn.textContent = currentTheme() === "dark" ? "☀ Light" : "☾ Dark";
}

function toggleTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch (e) {}
  updateThemeButton();
}

(function initTheme() {
  const btn = el("theme-toggle");
  if (btn) btn.addEventListener("click", toggleTheme);
  updateThemeButton();
  try {
    window.matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", updateThemeButton);
  } catch (e) {}
})();

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function getJSON(url) {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? null : JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.ok === false) {
    throw new Error(data.error || r.statusText);
  }
  return data;
}

/**
 * Call `fn` now and then every `ms` until the returned stop() is invoked.
 * Errors from `fn` are swallowed so a transient failure doesn't kill the loop.
 */
function poll(fn, ms) {
  let stopped = false;
  const tick = async () => {
    if (stopped) return;
    try { await fn(); } catch (_) { /* keep polling */ }
    if (!stopped) setTimeout(tick, ms);
  };
  tick();
  return () => { stopped = true; };
}
