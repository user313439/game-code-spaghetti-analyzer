// Spaghetti map without external libraries: force / circle layout, zoom & pan, hover focus, filters, plan halos.
import {h, svg, fill} from "./ui.js";
import {subj, unitDisplay} from "./core.js";

export const MAP_LIMIT = 150;

function radius(n) { return Math.min(28, 6 + Math.sqrt(Math.max(1, n.loc || 1)) / 4.5); }

// Deterministic force simulation with the same forces as the approved mock-up
// (d3-style velocity Verlet: links 95px/0.03, many-body −300, centring x 0.07 / y 0.09, collision).
export function forceLayout(nodes, edges, width, height, iterations = 300) {
  const n = nodes.length;
  if (!n) return;
  const cx = width / 2, cy = height / 2;
  nodes.forEach((v, i) => {   // phyllotaxis start, as d3 does
    const r = 10 * Math.sqrt(0.5 + i), a = i * Math.PI * (3 - Math.sqrt(5));
    v.x = cx + r * Math.cos(a); v.y = cy + r * Math.sin(a); v.vx = 0; v.vy = 0;
  });
  const degree = new Map(nodes.map(v => [v, 0]));
  for (const {s, t} of edges) { degree.set(s, degree.get(s) + 1); degree.set(t, degree.get(t) + 1); }
  const DISTANCE = 95, LINK = 0.03, CHARGE = -300, GX = 0.07, GY = 0.09, KEEP = 0.6;
  let alpha = 1;
  const decay = 1 - Math.pow(0.001, 1 / iterations);
  for (let step = 0; step < iterations; step++) {
    alpha += (0 - alpha) * decay;
    for (const {s, t} of edges) {
      let dx = t.x + t.vx - s.x - s.vx, dy = t.y + t.vy - s.y - s.vy;
      let l = Math.hypot(dx, dy) || 1e-6;
      l = (l - DISTANCE) / l * alpha * LINK;
      dx *= l; dy *= l;
      const bias = degree.get(s) / (degree.get(s) + degree.get(t));
      t.vx -= dx * bias; t.vy -= dy * bias; s.vx += dx * (1 - bias); s.vy += dy * (1 - bias);
    }
    for (let i = 0; i < n; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < n; j++) {
        const b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y, l = dx * dx + dy * dy;
        if (l < 1) { dx = (i - j) * 1e-3 || 1e-3; dy = 1e-3; l = 1; }
        const w = CHARGE * alpha / l;
        a.vx += dx * w; a.vy += dy * w; b.vx -= dx * w; b.vy -= dy * w;
      }
    }
    for (const v of nodes) { v.vx += (cx - v.x) * GX * alpha; v.vy += (cy - v.y) * GY * alpha; }
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const a = nodes[i], b = nodes[j], need = radius(a) + radius(b) + 8;
      const dx = b.x + b.vx - a.x - a.vx, dy = b.y + b.vy - a.y - a.vy, d = Math.hypot(dx, dy) || 1e-6;
      if (d < need) { const push = (need - d) / d * 0.35; a.vx -= dx * push; a.vy -= dy * push; b.vx += dx * push; b.vy += dy * push; }
    }
    for (const v of nodes) { v.vx *= KEEP; v.vy *= KEEP; v.x += v.vx; v.y += v.vy; }
  }
  for (let pass = 0; pass < 6; pass++) {
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const a = nodes[i], b = nodes[j], need = radius(a) + radius(b) + 6;
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.max(0.01, Math.hypot(dx, dy));
      if (d < need) { const push = (need - d) / 2; a.x -= (dx / d) * push; a.y -= (dy / d) * push; b.x += (dx / d) * push; b.y += (dy / d) * push; }
    }
  }
  for (const v of nodes) { v.fx = v.x; v.fy = v.y; }
}

export function circleLayout(nodes, width, height) {
  const order = [...nodes].sort((a, b) => (b.in_cycle - a.in_cycle) || (b.si - a.si));
  const R = Math.max(120, Math.min(width, height) / 2 - 110);
  order.forEach((v, i) => { v.angle = (i / order.length) * Math.PI * 2 - Math.PI / 2; v.cx = width / 2 + R * Math.cos(v.angle); v.cy = height / 2 + R * Math.sin(v.angle); });
}

export function createMap(host, {nodes, edges, unitLabel = "파일", onPick} = {}) {
  const truncated = nodes.length > MAP_LIMIT;
  const kept = truncated ? [...nodes].sort((a, b) => b.si - a.si).slice(0, MAP_LIMIT) : nodes;
  const N = kept.map(n => ({...n}));
  const byId = new Map(N.map(n => [n.id, n]));
  const E = edges.filter(([s, t]) => byId.has(s) && byId.has(t) && s !== t).map(([s, t]) => ({s: byId.get(s), t: byId.get(t)}));
  const W = Math.max(480, host.clientWidth || 900), H = Math.max(420, host.clientHeight || 640);
  forceLayout(N, E, W, H);
  circleLayout(N, W, H);
  let layout = "force", filter = "all", plan = [], focus = null, pinned = null, view = {k: 1, x: 0, y: 0}, tween = 0, minK = 1;
  for (const v of N) { v.px = v.fx; v.py = v.fy; }

  const root = svg("g");
  const canvas = svg("svg", {class: "map-svg", width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "group", "aria-label": `${unitLabel} 사이 연결 지도`}, root);
  const edgeLayer = svg("g"), haloLayer = svg("g"), nodeLayer = svg("g"), labelLayer = svg("g");
  root.append(edgeLayer, haloLayer, nodeLayer, labelLayer);
  const tip = h("div", {class: "map-tip", role: "tooltip"});
  host.append(canvas, tip);

  const edgeEls = E.map(e => { const p = svg("path", {class: "edge"}); edgeLayer.append(p); return p; });
  const neighbours = new Map(N.map(n => [n, new Set([n])]));
  E.forEach(({s, t}) => { neighbours.get(s).add(t); neighbours.get(t).add(s); });
  const nodeEls = N.map(v => {
    const c = svg("circle", {class: `node g${v.grade}`, r: radius(v), tabindex: "0", "aria-label": `${v.label || v.id} ${v.grade} ${v.si}`});
    c.addEventListener("pointerenter", e => hover(v, e));
    c.addEventListener("focus", () => hover(v, null));
    c.addEventListener("pointerleave", leave);
    c.addEventListener("blur", leave);
    c.addEventListener("pointermove", move);
    c.addEventListener("click", e => { e.stopPropagation(); pick(v); });
    c.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(v); } });
    nodeLayer.append(c);
    return c;
  });
  const haloEls = N.map(() => {
    const g = svg("g", {class: "halo"}), ring = svg("circle", {class: "halo-ring"}), badge = svg("circle", {class: "halo-badge", r: 9}), num = svg("text", {class: "halo-num"});
    g.append(ring, badge, num); haloLayer.append(g); return {g, ring, badge, num};
  });
  const labelEls = N.map(v => { const t = svg("text", {class: "lbl"}, v.label || v.id); labelLayer.append(t); return t; });

  function pos(v) { return [v.px, v.py]; }
  function edgePath({s, t}) {
    const [ax, ay] = pos(s), [bx, by] = pos(t);
    if (layout === "circle") { const k = 0.25; return `M${ax},${ay} Q${W / 2 + (ax + bx - W) / 2 * k},${H / 2 + (ay + by - H) / 2 * k} ${bx},${by}`; }
    const mx = (ax + bx) / 2 + (ay - by) * 0.12, my = (ay + by) / 2 + (bx - ax) * 0.12;
    return `M${ax},${ay} Q${mx},${my} ${bx},${by}`;
  }
  function visible(e) {
    if (filter === "cycle") return e.s.in_cycle && e.t.in_cycle;
    if (filter === "plan") return plan.includes(e.s.id) || plan.includes(e.t.id);
    return true;
  }
  function place() {
    E.forEach((e, i) => edgeEls[i].setAttribute("d", edgePath(e)));
    N.forEach((v, i) => {
      const [x, y] = pos(v), r = radius(v);
      nodeEls[i].setAttribute("cx", x); nodeEls[i].setAttribute("cy", y);
      const halo = haloEls[i];
      halo.ring.setAttribute("cx", x); halo.ring.setAttribute("cy", y); halo.ring.setAttribute("r", r + 5);
      halo.badge.setAttribute("cx", x + r + 4); halo.badge.setAttribute("cy", y - r - 4);
      halo.num.setAttribute("x", x + r + 4); halo.num.setAttribute("y", y - r);
      const label = labelEls[i];
      if (layout === "circle") {
        const right = Math.cos(v.angle) >= 0;
        label.setAttribute("x", x + (r + 8) * Math.cos(v.angle)); label.setAttribute("y", y + (r + 8) * Math.sin(v.angle) + 4);
        label.setAttribute("text-anchor", right ? "start" : "end");
      } else {
        label.setAttribute("x", x); label.setAttribute("y", y - r - 8); label.setAttribute("text-anchor", "middle");
      }
    });
  }
  function paint() {
    const f = focus || pinned, near = f ? neighbours.get(f) : null;
    E.forEach((e, i) => {
      const el = edgeEls[i], mine = f && (e.s === f || e.t === f);
      el.classList.toggle("off", !visible(e));
      el.classList.toggle("dim", Boolean(f) && !mine);
      el.classList.toggle("out", Boolean(f) && e.s === f);
      el.classList.toggle("in", Boolean(f) && e.t === f);
      el.classList.toggle("plan", !f && (plan.includes(e.s.id)));
    });
    N.forEach((v, i) => {
      nodeEls[i].classList.toggle("dim", Boolean(near && !near.has(v)) || (!f && filter === "cycle" && !v.in_cycle));
      nodeEls[i].classList.toggle("pinned", pinned === v);
      const rank = plan.indexOf(v.id);
      haloEls[i].g.classList.toggle("show", rank >= 0);
      haloEls[i].g.classList.toggle("dim", rank >= 0 && Boolean(near && !near.has(v)));
      haloEls[i].num.textContent = rank >= 0 ? String(rank + 1) : "";
      const important = v.si >= 88 || rank >= 0 || layout === "circle";
      labelEls[i].classList.toggle("show", near ? near.has(v) : important);
      labelEls[i].classList.toggle("minor", layout === "circle" && !(v.si >= 88 || rank >= 0));
    });
    declutter();
  }
  // Hide labels that would overlap a more important one (plan files and higher G-SI win).
  function declutter() {
    const order = N.map((v, i) => i).filter(i => labelEls[i].classList.contains("show"))
      .sort((a, b) => ((N[b] === (focus || pinned)) - (N[a] === (focus || pinned))) || (plan.includes(N[b].id) - plan.includes(N[a].id)) || N[b].si - N[a].si);
    const kept = [];
    for (const i of order) {
      let box;
      try { box = labelEls[i].getBBox(); } catch (_) { return; }
      if (!box.width) continue;
      const pad = 2 / view.k;
      const hit = kept.some(k => box.x < k.x + k.width + pad && k.x < box.x + box.width + pad && box.y < k.y + k.height + pad && k.y < box.y + box.height + pad);
      if (hit) labelEls[i].classList.remove("show");
      else kept.push(box);
    }
  }
  function hover(v, event) {
    focus = v; paint();
    fill(tip, h("b", null, v.label || v.id), h("span", {class: `tip-grade g${v.grade}`}, `${v.grade} · ${Number(v.si).toFixed(1)}`),
      v.label && v.label !== unitDisplay(v.id) ? h("div", {class: "tip-id"}, unitDisplay(v.id)) : null,
      h("div", null, `${(v.loc || 0).toLocaleString()}줄 · 부르는 ${unitLabel} ${v.fout} · 불리는 ${unitLabel} ${v.fin}`),
      h("div", null, v.in_cycle ? "순환 고리 안" : "순환 고리 밖", v.top ? ` · 최고 복잡 함수 ${v.top.name} (CC ${v.top.cc})` : ""),
      v.leverage ? h("div", {class: "tip-em"}, `정리하면 고리에서 ${v.leverage}개 ${subj(unitLabel)} 빠질 수 있음`) : null);
    tip.classList.add("show");
    if (event) move(event); else { const r = host.getBoundingClientRect(), c = nodeEls[N.indexOf(v)].getBoundingClientRect(); placeTip(c.right - r.left, c.bottom - r.top); }
  }
  function move(event) { const r = host.getBoundingClientRect(); placeTip(event.clientX - r.left, event.clientY - r.top); }
  function placeTip(x, y) { tip.style.left = `${Math.min(x + 14, host.clientWidth - 280)}px`; tip.style.top = `${Math.min(y + 14, host.clientHeight - 120)}px`; }
  function leave() { focus = null; tip.classList.remove("show"); paint(); }
  function pick(v) { pinned = v; paint(); onPick?.(v); }
  canvas.addEventListener("click", () => { if (dragged) return; pinned = null; paint(); onPick?.(null); });

  // zoom & pan -------------------------------------------------------------
  let declutterTimer = null;
  function applyView() {
    root.setAttribute("transform", `translate(${view.x},${view.y}) scale(${view.k})`);
    for (const l of labelEls) l.setAttribute("font-size", String(12 / view.k));
    clearTimeout(declutterTimer);
    declutterTimer = setTimeout(paint, 120);   // labels shrink when zooming in, so re-check overlaps
  }
  function fitView() {
    const xs = N.map(v => pos(v)[0]), ys = N.map(v => pos(v)[1]);
    if (!xs.length) return {k: 1, x: 0, y: 0};
    const pad = layout === "circle" ? 90 : 40, top = 56, bottom = 52;
    const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
    const k = Math.min(W / (x1 - x0), (H - top - bottom) / (y1 - y0), 1.8);
    return {k, x: W / 2 - k * (x0 + x1) / 2, y: top + (H - top - bottom) / 2 - k * (y0 + y1) / 2};
  }
  function fitNow() { const target = fitView(); minK = Math.min(minK, target.k); animateView(target); }
  function animateView(target, ms = 260) {
    const from = {...view}, started = performance.now();
    const step = now => { const p = Math.min(1, (now - started) / ms), e = p * (2 - p);
      view = {k: from.k + (target.k - from.k) * e, x: from.x + (target.x - from.x) * e, y: from.y + (target.y - from.y) * e};
      applyView(); if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  function zoomAt(factor, px = W / 2, py = H / 2) {
    const k = Math.max(Math.min(0.4, minK), Math.min(6, view.k * factor)), f = k / view.k;
    view = {k, x: px - (px - view.x) * f, y: py - (py - view.y) * f}; applyView();
  }
  // Screen → viewBox coordinates, including the letterboxing of preserveAspectRatio.
  function svgPoint(event) {
    const matrix = canvas.getScreenCTM();
    if (!matrix) { const r = canvas.getBoundingClientRect(); return [(event.clientX - r.left) * W / r.width, (event.clientY - r.top) * H / r.height]; }
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    return [p.x, p.y];
  }
  // Plain wheel scrolls the page; only Ctrl/⌘ + wheel zooms the map.
  canvas.addEventListener("wheel", e => { if (!e.ctrlKey && !e.metaKey) return; e.preventDefault(); const [x, y] = svgPoint(e); zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, x, y); }, {passive: false});
  let drag = null, dragged = false;
  canvas.addEventListener("pointerdown", e => { if (e.target !== canvas && !e.target.classList.contains("edge")) return; drag = [...svgPoint(e), view.x, view.y]; dragged = false; canvas.setPointerCapture(e.pointerId); canvas.classList.add("grabbing"); });
  canvas.addEventListener("pointermove", e => { if (!drag) return; const [x, y] = svgPoint(e); if (Math.abs(x - drag[0]) + Math.abs(y - drag[1]) > 3) dragged = true; view = {...view, x: drag[2] + x - drag[0], y: drag[3] + y - drag[1]}; applyView(); });
  const stopDrag = () => { drag = null; canvas.classList.remove("grabbing"); setTimeout(() => { dragged = false; }, 0); };
  canvas.addEventListener("pointerup", stopDrag);
  canvas.addEventListener("pointercancel", stopDrag);

  function setLayout(next) {
    if (next === layout) return;
    layout = next;
    const started = performance.now(), from = N.map(v => [v.px, v.py]), id = ++tween;
    const to = N.map(v => next === "circle" ? [v.cx, v.cy] : [v.fx, v.fy]);
    const step = now => { if (id !== tween) return; const p = Math.min(1, (now - started) / 320), e = p * (2 - p);
      N.forEach((v, i) => { v.px = from[i][0] + (to[i][0] - from[i][0]) * e; v.py = from[i][1] + (to[i][1] - from[i][1]) * e; });
      place(); if (p < 1) requestAnimationFrame(step); else { paint(); fitNow(); } };
    paint();
    requestAnimationFrame(step);
  }

  place(); paint(); view = fitView(); minK = view.k; applyView();
  return {
    truncated, shown: N.length,
    setPlan(names) { plan = names || []; paint(); },
    refresh() { paint(); },
    setLayout,
    setFilter(next) { filter = next; paint(); },
    zoomBy(factor) { zoomAt(factor); },
    fit() { fitNow(); },
    focusOn(id) {
      const v = byId.get(id); if (!v) return false;
      pinned = v; paint(); onPick?.(v);
      const [x, y] = pos(v), k = Math.max(view.k, 1.6);
      animateView({k, x: W / 2 - k * x, y: H / 2 - k * y});
      return true;
    },
    destroy() { tween++; canvas.remove(); tip.remove(); },
  };
}
