"use strict";

function el(id) {
  return document.getElementById(id);
}

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
