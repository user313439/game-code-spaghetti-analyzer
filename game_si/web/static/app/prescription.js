// AI prescription panel on the diagnosis page.
import {AI_LABELS, aiName, connectionProblem, elapsedText, obj, pickConnection, subj} from "./core.js";
import {bar, h, notice, progressBlock, fill} from "./ui.js";

const STORE = "gsi-ai-connection";

function remembered() {
  try { return JSON.parse(localStorage.getItem(STORE) || "{}"); } catch (_) { return {}; }
}
function remember(value) {
  try { localStorage.setItem(STORE, JSON.stringify(value)); } catch (_) { /* storage may be blocked */ }
}

// Connection picker shared by the AI steps. Any AI works: the official programs on this PC
// (the user's own subscription), their API keys, or any service or local model server that speaks
// the OpenAI-compatible API. Returns {el, value(), problem()}; the API key never leaves memory.
export function connectionPicker(connections, api) {
  const saved = remembered();
  const start = pickConnection(connections, saved);
  const labelled = (text, control) => h("label", {class: "conn-field"}, h("span", null, text), control);
  const ORDER = ["claude", "codex", "gemini", "compatible"];
  const ordered = [...connections].sort((a, b) => (ORDER.indexOf(a.id) + 1 || 99) - (ORDER.indexOf(b.id) + 1 || 99));
  const service = h("select", {"aria-label": "사용할 AI"}, ...ordered.map(c => h("option", {value: c.id}, AI_LABELS[c.id] || c.name)));
  service.value = start.service;
  const mode = h("select", {"aria-label": "연결 방법"}, h("option", {value: "cli"}, "이 PC의 프로그램 (내 구독 계정)"), h("option", {value: "api"}, "API 키"));
  mode.value = start.mode;
  // The model is optional for a program on this PC (its default is used) and required otherwise.
  const model = h("input", {type: "text", value: saved.model || "", "aria-label": "모델 이름", spellcheck: "false", list: "conn-models", autocomplete: "off"});
  const modelList = h("datalist", {id: "conn-models"});
  // new-password keeps the browser from offering to save the key; it only lives in this input.
  const key = h("input", {type: "password", autocomplete: "new-password", spellcheck: "false", "aria-label": "API 키"});
  const compatible = connections.find(c => c.id === "compatible");
  const presets = compatible?.presets || [];
  const preset = h("select", {"aria-label": "연결할 서비스"}, h("option", {value: ""}, "직접 입력"), ...presets.map(p => h("option", {value: p.url}, p.name)));
  const url = h("input", {type: "url", value: saved.base_url || "", placeholder: "https://…/v1", spellcheck: "false", "aria-label": "AI 주소"});
  preset.value = presets.some(p => p.url === url.value) ? url.value : "";
  const listButton = h("button", {class: "btn ghost sm", type: "button"}, "모델 목록 불러오기");
  const modeField = labelled("연결 방법", mode);
  const addressBox = h("div", {class: "conn-box"}, labelled("서비스", preset), labelled("주소", url));
  const keyField = labelled("API 키", key);
  const modelField = h("div", {class: "conn-field"}, h("span", null, "모델"), h("div", {class: "conn-model"}, model, listButton), modelList);
  const hint = h("div", {class: "conn-hint"});
  const say = (tone, ...parts) => fill(hint, h("p", {class: `conn-state conn-${tone}`}, ...parts));
  const sync = () => {
    const chosen = connections.find(c => c.id === service.value);
    const byAddress = service.value === "compatible";
    if (byAddress) mode.value = "api";
    modeField.hidden = byAddress;
    addressBox.hidden = !byAddress;
    keyField.hidden = mode.value !== "api";
    listButton.hidden = !byAddress;
    const local = byAddress && /^http:\/\/(localhost|127\.0\.0\.1|\[::1\])[:/]/.test(url.value.trim());
    key.placeholder = byAddress ? (local ? "이 PC의 AI 서버면 비워 두세요" : "서비스에서 받은 API 키 (저장하지 않습니다)") : "API 키 (저장하지 않습니다)";
    model.placeholder = byAddress ? "예: gpt-4.1, gemini-2.5-pro, llama3.1" : mode.value === "api" ? "모델 이름 (API 키로 연결할 때 필요)"
      : `비우면 프로그램 기본값${service.value === "claude" ? " (예: opus)" : ""}`;
    if (byAddress) say("info", "OpenAI 호환 API를 쓰는 AI라면 무엇이든 연결됩니다. 서비스를 고르거나 주소를 직접 넣고, 모델을 고르면 됩니다.",
      local ? " 이 PC에서 돌아가는 AI라 사용료가 들지 않습니다." : " 사용료는 키 주인 계정에 청구되며, 키는 이번 요청에만 쓰고 저장하지 않습니다.");
    else if (mode.value === "api") say("info", chosen && !chosen.installed ? `이 PC에서 ${chosen.name} 프로그램을 찾지 못해 API 키로 연결합니다. ` : "",
      "사용료는 키 주인 계정에 청구되며, 키는 이번 요청에만 쓰고 저장하지 않습니다.");
    else if (!chosen?.installed) say("warn", `이 PC에서 ${chosen?.name || "선택한"} 프로그램을 찾지 못했습니다. 연결 방법을 ‘API 키’로 바꾸거나, 프로그램을 설치하고 로그인한 뒤 새로 고쳐 주세요.`);
    else if (chosen.logged_in === false) say("warn", h("b", null, `${chosen.name}에 로그인되어 있지 않습니다.`),
      " 명령 프롬프트에서 아래 명령을 한 번 실행해 로그인한 뒤 이 화면을 새로 고쳐 주세요.",
      chosen.login_command ? h("code", {class: "cmd"}, chosen.login_command) : null);
    else say("ok", `✓ 이 PC의 ${chosen.name}에 로그인된 본인 계정으로 연결합니다.`);
    now();
  };
  const el = h("details", {class: "conn"}, h("summary", null, "AI 연결 ", h("span", {class: "sub conn-now"})),
    labelled("사용할 AI", service), modeField, addressBox, keyField, modelField, hint);
  function now() {
    const how = service.value === "compatible" ? (presets.find(p => p.url === url.value.trim())?.name || "주소로 연결") : mode.value === "api" ? "API 키" : "내 계정";
    el.querySelector(".conn-now").textContent = `· ${service.value === "compatible" ? "다른 AI" : AI_LABELS[service.value] || service.value} · ${how}${model.value.trim() ? ` · ${model.value.trim()}` : ""}`;
  }
  service.addEventListener("change", () => {
    const chosen = connections.find(c => c.id === service.value);
    if (chosen && service.value !== "compatible") mode.value = chosen.installed ? "cli" : "api";   // reach it somehow
    sync();
  });
  mode.addEventListener("change", sync);
  preset.addEventListener("change", () => { if (preset.value) url.value = preset.value; fill(modelList); sync(); });
  url.addEventListener("input", () => { preset.value = presets.some(p => p.url === url.value.trim()) ? url.value.trim() : ""; sync(); });
  model.addEventListener("input", now);
  listButton.addEventListener("click", async () => {
    listButton.disabled = true;
    const label = listButton.textContent;
    listButton.textContent = "불러오는 중…";
    try {
      const {models} = await api("/api/assistant/models", {method: "POST", body: JSON.stringify({base_url: url.value.trim(), api_key: key.value.trim()})});
      fill(modelList, ...models.map(m => h("option", {value: m})));
      say("ok", models.length ? `✓ 연결됐습니다. 모델 ${models.length}개를 찾았습니다. 모델 칸을 눌러 고르세요.` : "✓ 연결됐습니다. 모델 이름은 직접 입력해 주세요.");
      if (models.length && !model.value.trim()) { model.value = models[0]; now(); }
      model.focus();
    } catch (error) { say("warn", error.message); }
    finally { listButton.disabled = false; listButton.textContent = label; }
  });
  sync();
  if (connectionProblem({...value(false), api_key: "x"})) el.open = true;   // needs something filled in before the first request
  function value(store = true) {
    const body = {service: service.value, mode: service.value === "compatible" ? "api" : mode.value, model: model.value.trim()};
    if (service.value === "compatible") body.base_url = url.value.trim();
    if (store) remember(body);
    if (body.mode === "api") body.api_key = key.value.trim();
    return body;
  }
  return {
    el,
    value,
    problem() {
      const v = value(false);
      const missing = connectionProblem(v);
      if (missing) el.open = true;
      return missing;
    },
  };
}

export function createPrescriptionPanel(ctx, {jobId, data, onPlan, onFocus}) {
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
    const missing = picker.problem();
    if (missing) { say(missing); return; }
    const req = picker.value();
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
    picker = connectionPicker(connections || [], ctx.api);
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
    const meta = h("div", {class: "meta"}, h("span", null, `${when} 받은 처방 · ${aiName(r.service, r.model)}`),
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
      // The whole item opens the file in the diagnosis (the card list or the map, whichever is shown).
      const open = () => onFocus?.(f.name);
      return h("div", {class: "pitem link", role: "button", tabindex: "0", title: `${unit?.file || f.name} 진단 보기`, onclick: open,
          onkeydown: e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } }}, h("span", {class: "n"}, i + 1),
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
