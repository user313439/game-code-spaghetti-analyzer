// AI prescription panel on the diagnosis page.
import {elapsedText, obj, subj} from "./core.js";
import {bar, h, notice, progressBlock, fill} from "./ui.js";

const STORE = "gsi-ai-connection";
const SERVICE_NAMES = {codex: "Codex", claude: "Claude Code", gemini: "Gemini CLI"};

function remembered() {
  try { return JSON.parse(localStorage.getItem(STORE) || "{}"); } catch (_) { return {}; }
}
function remember(value) {
  try { localStorage.setItem(STORE, JSON.stringify(value)); } catch (_) { /* storage may be blocked */ }
}

// Connection picker shared by the AI steps. Returns {el, value()}; the API key never leaves memory.
export function connectionPicker(connections) {
  const saved = remembered();
  const installed = connections.filter(c => c.installed);
  const service = h("select", {"aria-label": "AI 서비스"}, ...connections.map(c => h("option", {value: c.id}, `${c.name}${c.installed ? "" : " (설치 필요)"}`)));
  service.value = saved.service && connections.some(c => c.id === saved.service) ? saved.service : (installed[0]?.id || connections[0]?.id || "codex");
  const mode = h("select", {"aria-label": "연결 방식"}, h("option", {value: "cli"}, "내 AI 프로그램 (구독 계정)"), h("option", {value: "api"}, "내 API 키"));
  mode.value = saved.mode === "api" ? "api" : "cli";
  // The model is optional for an installed program (its default is used) and required with an API key.
  const model = h("input", {type: "text", value: saved.model || "", "aria-label": "모델 이름", spellcheck: "false"});
  // new-password keeps the browser from offering to save the key; it only lives in this input.
  const key = h("input", {type: "password", placeholder: "API 키 (저장하지 않습니다)", autocomplete: "new-password", spellcheck: "false", "aria-label": "API 키"});
  const apiBox = h("div", {class: "conn-api"}, key);
  const hint = h("div", {class: "help conn-hint"});
  const sync = () => {
    apiBox.hidden = mode.value !== "api";
    const chosen = connections.find(c => c.id === service.value);
    model.placeholder = mode.value === "api" ? "모델 이름 (API 키 사용 시 필수)" : `모델 (비우면 기본값${service.value === "claude" ? ", 예: opus" : ""})`;
    if (mode.value === "api") fill(hint, "API 사용료는 키 주인 계정에 청구됩니다. 키는 이번 요청에만 쓰고 저장하지 않습니다.");
    else if (!chosen?.installed) fill(hint, `${chosen?.name || "선택한 AI"} 프로그램을 설치하고 로그인해야 합니다.`);
    else if (chosen.logged_in === false) fill(hint, h("b", null, `${chosen.name}에 로그인되어 있지 않습니다.`),
      " 명령 프롬프트에서 아래 명령을 한 번 실행해 본인 계정으로 로그인한 뒤 이 화면을 새로 고쳐 주세요.",
      chosen.login_command ? h("code", {class: "cmd"}, chosen.login_command) : null);
    else fill(hint, `${chosen.name}에 로그인된 본인 계정의 사용량을 씁니다.`);
  };
  service.addEventListener("change", sync); mode.addEventListener("change", sync); sync();
  const el = h("details", {class: "conn"}, h("summary", null, "AI 연결 ", h("span", {class: "sub conn-now"})), h("div", {class: "grid2"}, service, mode), model, apiBox, hint);
  const now = () => { el.querySelector(".conn-now").textContent = `· ${SERVICE_NAMES[service.value] || service.value} · ${mode.value === "api" ? "API 키" : "내 계정"}${model.value.trim() ? ` · ${model.value.trim()}` : ""}`; };
  model.addEventListener("input", now);
  service.addEventListener("change", now); mode.addEventListener("change", now); now();
  return {
    el,
    value() {
      const body = {service: service.value, mode: mode.value, model: model.value.trim()};
      remember(body);
      if (mode.value === "api") body.api_key = key.value.trim();
      return body;
    },
  };
}

export function createPrescriptionPanel(ctx, {jobId, data, onPlan}) {
  const s = data.summary, label = s.unit_label;
  const units = new Map(data.units.map(u => [u.fqn, u]));
  const slot = h("div", {class: "alert-slot"});                            // one notice at a time
  const body = h("div");
  const live = h("p", {class: "visually-hidden", "aria-live": "polite"});  // short status for screen readers
  const el = h("aside", {class: "card ai-panel", "aria-label": "AI 처방"}, slot, body, live);
  let timer = null, alive = true, picker = null, connections = null, shown = "", lastPlan = null;
  const progress = progressBlock(["구조 요약 준비", "AI가 살펴보는 중", "효과 계산"]);
  const say = (message, tone) => fill(slot, message ? notice(message, tone) : null);
  const announce = text => { if (live.textContent !== text) live.textContent = text; };

  async function load() {
    try {
      if (!connections) connections = await ctx.api("/api/assistant/connections");
      draw(await ctx.api(`/api/jobs/${jobId}/prescription`));
    } catch (error) { say(error.message); }
  }
  function poll() { clearTimeout(timer); timer = setTimeout(async () => { if (!alive) return; try { draw(await ctx.api(`/api/jobs/${jobId}/prescription`)); } catch (_) { poll(); } }, 1000); }
  async function request(event) {
    const button = event?.currentTarget;
    const req = picker.value();
    if (req.mode === "api" && (!req.api_key || !req.model)) { say("API 키와 모델 이름을 입력해 주세요."); return; }
    if (button) button.disabled = true;
    say("");
    try { draw(await ctx.api(`/api/jobs/${jobId}/prescription`, {method: "POST", body: JSON.stringify(req)})); }
    catch (error) { say(error.message); if (button?.isConnected) button.disabled = false; }
  }
  async function cancel(event) {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "취소하는 중…";
    try { draw(await ctx.api(`/api/jobs/${jobId}/prescription/cancel`, {method: "POST", body: "{}"})); }
    catch (error) { say(error.message); if (button.isConnected) { button.disabled = false; button.textContent = "요청 취소"; } }
  }
  const requestButton = (text, cls = "btn primary block") => h("button", {class: cls, type: "button", onclick: request}, text);
  function intro() {
    picker = connectionPicker(connections || []);
    return [h("div", {class: "eyebrow"}, "AI 처방"),
      h("div", {class: "lead"}, "어디부터 고치면 엉킴이 가장 많이 풀릴까요?"),
      h("p", {class: "sub"}, `AI가 ${s.units}개 ${label}의 점수·연결·순환 고리를 함께 보고, 먼저 정리할 ${obj(label)} 최대 5개까지 순서대로 추천합니다. 점수 1위가 아니라 여러 ${obj(label)} 묶고 있는 중심 ${subj(label)} 추천될 수도 있습니다.`),
      h("div", {class: "box"}, h("b", null, "AI에게 보내는 내용"), h("p", {class: "sub"}, `${s.units}개 ${label}의 점수·연결 관계 요약과 주요 ${label} 선언부 일부 (약 80KB 이하)`)),
      picker.el];
  }
  function askAgain() { say(""); shown = "ask"; fill(body, ...intro(), requestButton("AI 처방 다시 받기")); }
  function cycleBox(result) {
    const eff = result.effects;
    if (result.files.some(f => f.kind === "link") && eff.base > 1) {
      return h("div", {class: "box"}, h("b", null, `순환 고리에 묶인 ${label} 수`), h("p", {class: "help"}, "위에서부터 차례로 정리했을 때 · 프로그램이 구조로 계산"),
        h("div", {class: "cyc-row"}, h("span", null, "지금 상태"), bar(100, "hot"), h("b", null, eff.base)),
        ...eff.steps.map((st, i) => st.after === null
          ? h("div", {class: "cyc-row muted"}, h("span", null, units.get(st.name)?.name || st.name), h("span", {class: "help"}, "고리 변화 없음 · 파일 안 정리"), h("b"))
          : h("div", {class: "cyc-row"}, h("span", null, `${i ? "+ " : ""}${units.get(st.name)?.name || st.name} 정리 후`), bar(100 * st.after / eff.base, st.after <= eff.base * 0.2 ? "good" : st.after <= eff.base * 0.6 ? "warm" : "hot"), h("b", null, st.after))),
        h("p", {class: "help"}, "연결을 끊었다고 가정한 최대 기대치입니다. 실제 변화는 수정 후 다시 분석해서 확인합니다."));
    }
    return h("div", {class: "box"}, h("b", null, "먼저 정리할 함수"),
      ...result.files.map(f => { const fn = units.get(f.name)?.functions[0]; return fn ? h("div", {class: "cyc-row two"}, h("span", {class: "mono"}, `${units.get(f.name)?.name || f.name} · ${fn.name}`), h("b", null, `CC ${fn.cc} · ${fn.loc}줄`)) : null; }),
      h("p", {class: "help"}, `${label} 사이의 연결은 그대로 두고 함수 안을 정리하는 처방입니다.`));
  }
  function resultView(state) {
    const r = state.result;
    const when = r.created_at ? new Date(r.created_at * 1000).toLocaleString("ko-KR", {month: "long", day: "numeric", hour: "2-digit", minute: "2-digit"}) : "";
    const meta = h("div", {class: "meta"}, h("span", null, `${when} 받은 처방 · ${SERVICE_NAMES[r.service] || r.service}`),
      state.stale ? null : h("button", {class: "linkish", type: "button", onclick: askAgain}, "다시 받기"));
    // A prescription from an earlier round names files and numbers that may no longer hold:
    // it stays readable, but the only way forward is asking again.
    const staleBox = state.stale ? h("div", {class: "box warn-box"}, h("b", null, "이전 분석 기준 처방입니다"),
      h("p", {class: "sub"}, "그 뒤로 코드가 바뀌어 이 처방의 파일과 숫자가 지금과 다를 수 있습니다. 현재 코드 기준으로 다시 받아 주세요."),
      h("button", {class: "btn primary block", type: "button", onclick: askAgain}, "현재 코드로 다시 받기")) : null;
    if (r.done || !r.files.length) {
      return [staleBox, h("div", {class: "eyebrow"}, "AI 처방"), h("div", {class: "lead"}, r.headline),
        h("p", {class: "sub"}, "이 분석 기준으로는 더 정리할 만한 큰 매듭이 없다는 답을 받았습니다."), meta];
    }
    let prev = r.effects.base;
    const items = r.files.map((f, i) => {
      const st = r.effects.steps[i], unit = units.get(f.name);
      let effect = null;
      if (st.after !== null && st.reduced) { effect = h("div", {class: "effect"}, `고리 ${prev} → ${st.after}개 ${label}`); prev = st.after; }
      else if (st.after !== null) effect = h("div", {class: "effect warn"}, `⚠ 이 ${label}만으로는 고리가 거의 줄지 않습니다 (계산 결과 ${prev} → ${st.after}개)`);
      return h("div", {class: "pitem"}, h("span", {class: "n"}, i + 1),
        h("div", null, h("b", null, unit?.file || f.name), h("span", {class: `kind ${f.kind}`}, f.kind === "link" ? "연결 정리" : "파일 안 정리"),
          h("p", null, f.reason), h("p", {class: "how"}, f.change_idea), effect));
    });
    return [staleBox,
      h("div", {class: "eyebrow"}, `AI 처방 · ${r.files.length}개 ${label}`), h("div", {class: "lead"}, r.headline),
      cycleBox(r), ...items,
      r.show_why_not_top ? h("div", {class: "bubble"}, h("h4", null, `왜 점수 1위 ‘${units.get(r.top_unit)?.name || r.top_unit}’부터 고치지 않나요?`), r.why_not_top) : null,
      h("div", {class: "bubble"}, h("h4", null, "무엇이 좋아지나요?"), r.benefit),
      state.stale ? null : h("div", {class: "actions"},
        h("a", {class: "btn ghost", href: `#/job/${jobId}/refactor?pick=1`}, "직접 고르기"),
        h("a", {class: "btn primary", href: `#/job/${jobId}/refactor`}, "추천대로 진행 →")),
      meta];
  }
  function plan(names) {
    const key = names.join("|");
    if (key === lastPlan) return;
    lastPlan = key;
    onPlan?.(names);
  }
  function draw(state) {
    if (!alive) return;
    clearTimeout(timer);
    const r = state.result;
    plan(r && !r.done && !state.stale ? r.files.map(f => f.name) : []);
    if (state.state === "running") {
      const p = state.progress || {};
      progress.update({step: p.step || 0, total: 3, text: p.label || "", elapsed: elapsedText(state.elapsed_seconds), indeterminate: p.indeterminate});
      if (shown !== "running") {   // build once, then only the progress and the context line change
        say("");
        fill(body, h("div", {class: "eyebrow"}, "AI 처방"), h("div", {class: "lead"}, "전체 구조를 살펴보고 있습니다"), progress.el, h("p", {class: "help context"}),
          h("div", {class: "actions"}, h("button", {class: "btn ghost sm", type: "button", onclick: cancel}, "요청 취소")));
        shown = "running";
      }
      body.querySelector(".context").textContent = state.context
        ? `보낸 내용 ${(state.context.bytes / 1024).toFixed(0)}KB · ${label} ${state.context.units}개 · 선언부 ${state.context.excerpts}개` : "";
      announce("AI 처방을 받고 있습니다.");
      poll();
      return;
    }
    if (state.state === "failed" && !r) {
      shown = "failed";
      say("");
      announce("처방을 받지 못했습니다.");
      fill(body, h("div", {class: "eyebrow hot-text"}, "AI 처방 · 받지 못함"), h("div", {class: "lead"}, "처방을 받지 못했습니다"),
        h("p", {class: "sub"}, state.error || "AI 연결을 확인해 주세요."), ...intro().slice(3),
        h("div", {class: "actions"}, requestButton("다시 받기", "btn primary")),
        h("p", {class: "help"}, "진단 결과는 그대로 볼 수 있습니다."));
      return;
    }
    if (state.state === "cancelled" && !r) {
      shown = "ask";
      fill(body, ...intro(), requestButton("AI 처방 받기"));
      say("처방 요청을 취소했습니다.", "info");
      announce("처방 요청을 취소했습니다.");
      return;
    }
    if (r) {
      shown = "result";
      if (state.state === "cancelled") say("처방 요청을 취소해 이전 처방을 보여 드립니다.", "info");
      else say(state.state === "failed" ? `새 처방을 받지 못해 이전 처방을 보여 드립니다. ${state.error || ""}` : "");
      announce(state.state === "failed" ? "새 처방을 받지 못했습니다." : state.stale ? "이전 분석 기준 처방입니다. 다시 받아 주세요." : "처방을 받았습니다.");
      fill(body, ...resultView(state));
      return;
    }
    shown = "ask";
    fill(body, ...intro(), requestButton("AI 처방 받기"));
  }
  load();
  return {el, destroy() { alive = false; clearTimeout(timer); }};
}
