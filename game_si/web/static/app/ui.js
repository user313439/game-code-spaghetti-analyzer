// Small DOM helpers. Styles are applied through the CSSOM (the page CSP forbids inline style attributes).
const SVG_NS = "http://www.w3.org/2000/svg";

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function assign(el, props) {
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.setAttribute("class", value);
    else if (key === "style") Object.assign(el.style, value);
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  return el;
}

export function h(tag, props, ...children) {
  return append(assign(document.createElement(tag), props), children);
}

export function svg(tag, props, ...children) {
  return append(assign(document.createElementNS(SVG_NS, tag), props), children);
}

// Replace children, skipping null/false (replaceChildren would print them as text).
export function fill(el, ...children) {
  el.replaceChildren();
  return append(el, children);
}

export function clear(el) {
  el.replaceChildren();
  return el;
}

export function bar(pct, tone = "cool") {
  const meter = h("span");
  meter.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  return h("div", {class: `bar ${tone}`}, meter);
}

// Inline text with code names shown as code (wraps inside narrow boxes).
export function codeText(tokens) {
  return tokens.map(t => t.code ? h("code", {class: "cname"}, t.code) : t.text);
}

// AI prose, easier to read: one line per sentence, the first sentence of each paragraph in bold,
// code names as code, "[file.c] …" paragraphs labelled by file. The text itself is unchanged.
export function prose(parts, {list = true} = {}) {
  return h("div", {class: "prose"}, ...parts.map(p => h("div", {class: "prose-p"},
    p.label ? h("span", {class: "prose-file"}, p.label) : null,
    list && p.sentences.length > 1
      ? h("ul", null, ...p.sentences.map((s, i) => h("li", {class: i === 0 ? "lead" : ""}, ...codeText(s))))
      : h("p", null, ...p.sentences.flatMap((s, i) => [i ? " " : null, ...codeText(s)])))));
}

export function gradeBadge(grade) {
  return h("span", {class: `grade g${grade}`}, grade);
}

export function logo() {
  return svg("svg", {class: "logo-mark", viewBox: "0 0 32 32", "aria-hidden": "true"},
    svg("rect", {width: 32, height: 32, rx: 9, class: "logo-bg"}),
    svg("path", {d: "M9 10 L16 16 L23 9 M16 16 L10 23 M16 16 L23 22 M9 10 L10 23 M23 9 L23 22", class: "logo-line"}),
    ...[[9, 10, 2.6], [23, 9, 2.6], [16, 16, 3.2], [10, 23, 2.6], [23, 22, 2.6]].map(([cx, cy, r]) => svg("circle", {cx, cy, r, class: "logo-dot"})));
}

// Progress block: step chips + bar + label/elapsed. Returns {el, update(state)}.
export function progressBlock(steps = []) {
  const chips = h("div", {class: "stages"});
  const meter = h("span");
  const track = h("div", {class: "prog"}, meter);
  const label = h("span");
  const time = h("span");
  const el = h("div", {class: "progress"}, steps.length ? chips : null, track, h("div", {class: "prog-meta"}, label, time));
  function update({step = 0, total = steps.length || 1, text = "", elapsed = "", indeterminate = false} = {}) {
    const stage = Math.floor(step);   // a fractional step moves the bar within the current stage
    fill(chips, ...steps.map((name, i) => h("div", {class: `stg ${i < stage ? "done" : i === stage ? "now" : ""}`}, i < stage ? "✓ " : "", name)));
    track.classList.toggle("indeterminate", indeterminate);
    meter.style.width = indeterminate ? "" : `${Math.round(100 * Math.min(step, total) / total)}%`;
    label.textContent = text;
    time.textContent = elapsed ? `경과 ${elapsed}` : "";
  }
  update();
  return {el, update};
}

let toastTimer = null;
export function toast(message) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

export function notice(message, tone = "error") {
  return h("div", {class: `notice ${tone}`, role: tone === "error" ? "alert" : "status"}, message);
}

export function confirmDialog({title, body, ok = "확인", cancel = "취소"}) {
  return new Promise(resolve => {
    const dialog = h("dialog", {class: "dialog", "aria-labelledby": "dialog-title"},
      h("form", {method: "dialog"},
        h("h2", {id: "dialog-title"}, title), h("p", null, body),
        h("div", {class: "dialog-actions"},
          h("button", {class: "btn ghost", value: "cancel", autofocus: true}, cancel),
          h("button", {class: "btn primary", value: "ok"}, ok))));
    dialog.addEventListener("close", () => { resolve(dialog.returnValue === "ok"); dialog.remove(); });
    document.body.append(dialog);
    dialog.showModal();
  });
}
