import {createApi, DEFAULT_LIMITS} from "./core.js";
import {h, clear, logo, fill} from "./ui.js";
import * as importPage from "./page-import.js";
import * as historyPage from "./page-history.js";
import * as examplesPage from "./page-examples.js";
import * as diagnosisPage from "./page-diagnosis.js";
import * as refactorPage from "./page-refactor.js";
import * as resultPage from "./page-result.js";

const ID = "([a-f0-9]{32})";
const ROUTES = [
  {pattern: /^#?\/?$/, page: importPage, nav: "new"},
  {pattern: /^#\/history$/, page: historyPage, nav: "history"},
  {pattern: /^#\/examples$/, page: examplesPage, nav: "examples"},
  {pattern: new RegExp(`^#/job/${ID}$`), page: importPage, nav: "new", params: m => ({jobId: m[1]})},
  {pattern: new RegExp(`^#/job/${ID}/diagnosis$`), page: diagnosisPage, params: m => ({jobId: m[1]})},
  {pattern: new RegExp(`^#/job/${ID}/refactor(?:\\?(.*))?$`), page: refactorPage, params: m => ({jobId: m[1], query: m[2] || ""})},
  {pattern: new RegExp(`^#/job/${ID}/result$`), page: resultPage, params: m => ({jobId: m[1]})},
];
const STEPS = [["소스 가져오기", ""], ["엉킴 진단", "/diagnosis"], ["AI 리팩토링", "/refactor"], ["수정 결과·검증", "/result"]];

const ctx = {api: createApi(""), limits: DEFAULT_LIMITS, ready: false, session: null};
let cleanup = null, generation = 0;

function theme() { return document.documentElement.dataset.theme === "dark" ? "dark" : "light"; }
ctx.theme = theme;

function setTheme(value) {
  document.documentElement.dataset.theme = value;
  try { localStorage.setItem("gsi-theme", value); } catch (_) { /* storage may be blocked */ }
  const button = document.getElementById("theme");
  button.textContent = value === "dark" ? "☀" : "☾";
  button.setAttribute("aria-label", value === "dark" ? "라이트 모드" : "다크 모드");
  button.title = button.getAttribute("aria-label");
  window.dispatchEvent(new CustomEvent("gsi-theme", {detail: value}));
}

// Header steps for job pages. available: which later steps can be opened.
ctx.setSteps = (jobId, active, available = {}) => {
  const nav = document.getElementById("steps");
  if (!jobId) { nav.hidden = true; nav.replaceChildren(); return; }
  nav.hidden = false;
  fill(nav, ...STEPS.map(([name, suffix], i) => {
    const done = i < active, on = i === active;
    const open = i === 0 || (i === 1 && available.diagnosis !== false) || (i === 2 && available.refactor) || (i === 3 && available.result);
    const content = [h("i", null, done ? "✓" : String(i + 1)), name];
    return open && !on
      ? h("a", {class: `step ${done ? "done" : ""}`, href: `#/job/${jobId}${suffix}`}, ...content)
      : h("span", {class: `step ${done ? "done" : ""} ${on ? "on" : ""} ${open ? "" : "locked"}`, "aria-current": on ? "step" : null}, ...content);
  }));
};
ctx.setCrumb = text => { document.getElementById("crumb").textContent = text || ""; };

function shell() {
  const header = h("header", {class: "topbar"},
    h("a", {class: "logo", href: "#/", "aria-label": "처음 화면"}, logo(), h("span", null, "GAME CODE", h("small", null, "SPAGHETTI ANALYZER"))),
    h("nav", {class: "mainnav", "aria-label": "주 메뉴"},
      h("a", {href: "#/", dataset: {nav: "new"}}, "새 분석"),
      h("a", {href: "#/history", dataset: {nav: "history"}}, "분석 기록"),
      h("a", {href: "#/examples", dataset: {nav: "examples"}}, "예시 결과")),
    h("div", {id: "crumb", class: "crumb"}),
    h("nav", {id: "steps", class: "steps", "aria-label": "진행 단계", hidden: true}),
    h("button", {id: "theme", class: "icon-btn", type: "button", onclick: () => setTheme(theme() === "dark" ? "light" : "dark")}, "☾"));
  document.body.prepend(h("a", {class: "skip", href: "#view", onclick: e => { e.preventDefault(); document.getElementById("view").focus(); }}, "본문으로 이동"), header);
  setTheme(theme());
}

async function route() {
  const id = ++generation;
  cleanup?.();
  cleanup = null;
  const hash = location.hash || "#/";
  const match = ROUTES.map(r => [r, hash.match(r.pattern)]).find(([, m]) => m);
  const view = clear(document.getElementById("view"));
  for (const link of document.querySelectorAll(".mainnav a")) link.classList.toggle("on", Boolean(match && link.dataset.nav === match[0].nav));
  ctx.setSteps(null);
  ctx.setCrumb("");
  if (!match) {
    view.append(h("section", {class: "wrap narrow"}, h("h1", {class: "h1"}, "페이지를 찾지 못했습니다"),
      h("p", {class: "sub"}, "주소를 확인하거나 처음 화면으로 돌아가 주세요."), h("a", {class: "btn primary", href: "#/"}, "처음 화면")));
    return;
  }
  const [r, m] = match;
  // Each render gets its own container and a header guard, so a page that finishes loading
  // after the user has moved on cannot write into the new page or its header.
  const host = h("div", {class: "page"});
  view.append(host);
  const current = () => id === generation;
  const pageCtx = {...ctx, current,
    setSteps: (...args) => { if (current()) ctx.setSteps(...args); },
    setCrumb: text => { if (current()) ctx.setCrumb(text); }};
  window.scrollTo(0, 0);
  const result = await r.page.render(host, pageCtx, r.params ? r.params(m) : {});
  if (current()) cleanup = result || null;
  else result?.();
}

async function start() {
  shell();
  try {
    const session = await ctx.api("/api/session");
    ctx.api = createApi(session.token);
    ctx.limits = {...DEFAULT_LIMITS, ...session.limits};
    ctx.ready = true;
  } catch (error) {
    ctx.sessionError = error.message;
  }
  window.addEventListener("hashchange", route);
  route();
}

start();
