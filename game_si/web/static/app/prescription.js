// AI prescription panel on the diagnosis page.
import {AI_LABELS, aiName, codeTokens, connectionProblem, elapsedText, obj, pickConnection, subj} from "./core.js";
import {bar, codeText, h, notice, progressBlock, fill} from "./ui.js";

const STORE = "gsi-ai-connection";
// The two ways a stage can change the code, in the words the prescription panel uses.
export const METHODS = {
  internal: {name: "함수 나누기", what: "큰 함수 안에서 한 가지 일을 하는 덩어리를 이름 붙은 작은 함수로 옮깁니다. 게임 동작은 바꾸지 않습니다."},
  link: {name: "선언 옮기기", what: "여러 파일이 함께 쓰는 자료형·선언을 새 헤더로 옮겨, 파일끼리 서로 포함하는 고리를 끊습니다. 함수 본문은 바꾸지 않습니다."}};

function remembered() {
  try { return JSON.parse(localStorage.getItem(STORE) || "{}"); } catch (_) { return {}; }
}
function remember(value) {
  try { localStorage.setItem(STORE, JSON.stringify(value)); } catch (_) { /* storage may be blocked */ }
}

// Connection picker shared by the AI steps. Any AI works: the official programs on this PC
// (the user's own subscription), their API keys, or any service or local model server that speaks
// the OpenAI-compatible API. Returns {el, value(), problem()}; the API key never leaves memory.
// `step` ("prescription" | "refactor") keeps a model per step and program and says which model suits it.
// The prescription reads the whole structure and judges where to fix (a stronger model; its answer is
// short), the change writes long code by set rules (a lighter model is enough and uses far less quota).
// `pick` is the suggested model; `auto: false` only offers it instead of filling it in.
export function stepAdvice(service, step, models = []) {
  const find = re => models.find(m => re.test(m));
  if (service === "claude") return step === "refactor"
    // Measured 2026-10-29 on OpenTyrian (5 files, one pass): haiku passed every check but moved little
    // (JE_main CC 388 → 381, against 388 → 337 with Codex sol).
    ? {pick: "sonnet", text: "변경안은 Sonnet을 권합니다. 처방이 정한 함수를 규칙대로 나누는 일이라 Sonnet으로 충분하고, 코드를 길게 쓰는 단계라 Opus보다 사용 한도를 훨씬 적게 씁니다. Haiku는 검사는 통과하지만 한 번에 조금만 나눕니다. 비워 두면 Opus(기본값)로 만듭니다."}
    : {text: "처방은 비워 두면 기본 모델(Opus)로 받습니다. 구조 전체를 읽고 어디를 고칠지 판단하는 단계라 상위 모델이 안정적이고, 답이 짧아 사용 한도는 적게 씁니다."};
  if (service === "codex") {
    const base = models[0], top = find(/astra/), light = find(/luna/), work = find(/sol/) || base;
    const named = base ? `(${base})` : "";
    // Measured 2026-10-29 on OpenTyrian (4 files, one pass): sol changed all 4 (90–150 lines moved each),
    // luna left 2 unchanged and moved about 60 lines in the others, with no fewer tokens.
    return step === "refactor"
      ? {pick: work, text: `변경안은 ${work || "Codex 기본 모델"}을 권합니다. 코딩용 주력 모델이라 큰 함수도 검사를 통과하게 나눕니다.${light ? ` ${light}는 사용 한도를 아끼려고 골라도 큰 함수는 고치지 않고 끝나거나 조금만 옮기는 경우가 많아 권하지 않습니다.` : ""}`}
      : {pick: top, auto: false, text: `처방은 비워 두면 Codex 기본 모델${named}로 받습니다.${top ? ` 더 깊게 검토하려면 ${top}(상위 모델, 사용 한도를 더 씀)을 고를 수 있습니다.` : ""}`};
  }
  return null;
}

export function connectionPicker(connections, api, {step} = {}) {
  const saved = remembered();
  const start = pickConnection(connections, saved);
  const modelsOf = id => connections.find(c => c.id === id)?.models || [];
  // The model shown for a program: the one last used for this step, else the suggested one, else empty.
  const stepModel = (id, how) => {
    const stored = saved.models?.[`${step}:${id}:${how}`];   // a program's alias (sonnet) is no API model id
    if (stored !== undefined) return stored;
    const advice = how === "cli" ? stepAdvice(id, step, modelsOf(id)) : null;
    return advice?.pick && advice.auto !== false ? advice.pick : "";
  };
  const labelled = (text, control) => h("label", {class: "conn-field"}, h("span", null, text), control);
  const ORDER = ["claude", "codex", "compatible"];
  const ordered = [...connections].sort((a, b) => (ORDER.indexOf(a.id) + 1 || 99) - (ORDER.indexOf(b.id) + 1 || 99));
  const service = h("select", {"aria-label": "사용할 AI"}, ...ordered.map(c => h("option", {value: c.id}, AI_LABELS[c.id] || c.name)));
  service.value = start.service;
  const mode = h("select", {"aria-label": "연결 방법"}, h("option", {value: "cli"}, "이 PC의 프로그램 (내 구독 계정)"), h("option", {value: "api"}, "API 키"));
  mode.value = start.mode;
  // The model is optional for a program on this PC (its default is used) and required otherwise.
  const firstModel = step ? stepModel(start.service, start.mode) : saved.model || "";
  const model = h("input", {type: "text", value: firstModel, "aria-label": "모델 이름", spellcheck: "false", autocomplete: "off"});
  // Known models are offered in a select styled like the other fields (a datalist pops up in the
  // browser's own colours); "직접 입력" opens the text box for any other name.
  const CUSTOM = "--custom--";   // not a model name
  const modelPick = h("select", {"aria-label": "모델 고르기"});
  let listed = [], typing = false;   // models an address listed; whether the user chose to type a name
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
  const tip = h("p", {class: "help conn-tip"});
  const modelField = h("div", {class: "conn-field"}, h("span", null, "모델"), modelPick, h("div", {class: "conn-model"}, model, listButton), tip);
  function fillModels(byAddress, cli) {
    const names = byAddress ? listed : cli ? modelsOf(service.value) : [];   // program aliases are no API model ids
    const current = model.value.trim();
    if (current && !names.includes(current)) typing = true;
    fill(modelPick, ...(cli ? [h("option", {value: ""}, "비워 두기 · 프로그램 기본값")] : [h("option", {value: "", disabled: true}, "모델을 고르세요")]),
      ...names.map(m => h("option", {value: m}, m)), h("option", {value: CUSTOM}, "직접 입력…"));
    modelPick.value = typing ? CUSTOM : current;
    modelPick.hidden = !names.length;
    model.hidden = Boolean(names.length) && !typing;
  }
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
    fillModels(byAddress, !byAddress && mode.value === "cli");
    const advice = step && mode.value === "cli" ? stepAdvice(service.value, step, modelsOf(service.value)) : null;
    tip.hidden = !advice;
    fill(tip, advice?.text || "", advice?.pick && model.value.trim() !== advice.pick
      ? h("button", {class: "btn ghost sm", type: "button", onclick: () => { model.value = advice.pick; typing = false; sync(); }}, `${advice.pick}로 바꾸기`) : null);
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
  // Always open: choosing the AI is a step the user takes before the request, not an extra.
  const el = h("div", {class: "conn"}, h("div", {class: "conn-head"}, h("b", null, "AI 연결 "), h("span", {class: "sub conn-now"})),
    labelled("사용할 AI", service), modeField, addressBox, keyField, modelField, hint);
  function now() {
    const how = service.value === "compatible" ? (presets.find(p => p.url === url.value.trim())?.name || "주소로 연결") : mode.value === "api" ? "API 키" : "내 계정";
    el.querySelector(".conn-now").textContent = `· ${service.value === "compatible" ? "다른 AI" : AI_LABELS[service.value] || service.value} · ${how}${model.value.trim() ? ` · ${model.value.trim()}` : ""}`;
  }
  service.addEventListener("change", () => {
    const chosen = connections.find(c => c.id === service.value);
    if (chosen && service.value !== "compatible") mode.value = chosen.installed ? "cli" : "api";   // reach it somehow
    if (step) model.value = stepModel(service.value, mode.value);   // a model name of one program means nothing to another
    typing = false;
    sync();
  });
  mode.addEventListener("change", () => { if (step) model.value = stepModel(service.value, mode.value); typing = false; sync(); });
  modelPick.addEventListener("change", () => {
    typing = modelPick.value === CUSTOM;
    if (!typing) model.value = modelPick.value;
    sync();
    if (typing) model.focus();
  });
  preset.addEventListener("change", () => { if (preset.value) url.value = preset.value; listed = []; sync(); });
  url.addEventListener("input", () => { preset.value = presets.some(p => p.url === url.value.trim()) ? url.value.trim() : ""; sync(); });
  model.addEventListener("input", sync);
  listButton.addEventListener("click", async () => {
    listButton.disabled = true;
    const label = listButton.textContent;
    listButton.textContent = "불러오는 중…";
    try {
      const {models} = await api("/api/assistant/models", {method: "POST", body: JSON.stringify({base_url: url.value.trim(), api_key: key.value.trim()})});
      listed = models;
      if (models.length && !model.value.trim()) { model.value = models[0]; typing = false; }
      sync();
      say("ok", models.length ? `✓ 연결됐습니다. 모델 ${models.length}개를 찾았습니다. 모델 칸에서 고르세요.` : "✓ 연결됐습니다. 모델 이름은 직접 입력해 주세요.");
      (models.length ? modelPick : model).focus();
    } catch (error) { say("warn", error.message); }
    finally { listButton.disabled = false; listButton.textContent = label; }
  });
  sync();
  function value(store = true) {
    const body = {service: service.value, mode: service.value === "compatible" ? "api" : mode.value, model: model.value.trim()};
    if (service.value === "compatible") body.base_url = url.value.trim();
    if (store) remember(step ? {...body, model: saved.model || "", models: {...remembered().models, [`${step}:${body.service}:${body.mode}`]: body.model}} : body);
    if (body.mode === "api") body.api_key = key.value.trim();
    return body;
  }
  return {
    el,
    value,
    problem() {
      const v = value(false);
      return connectionProblem(v);
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
  let timer = null, alive = true, picker = null, connections = null, shown = "", lastPlan = null, chosen = null;
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
    picker = connectionPicker(connections || [], ctx.api, {step: "prescription"});
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
    const stage = r.stage || 1;
    if (r.done || !r.files.length) {
      return [staleBox, h("div", {class: "eyebrow"}, stage > 1 ? `AI 처방 · ${stage}단계` : "AI 처방"), h("div", {class: "lead"}, stage > 1 ? "더 정리할 곳이 없습니다" : r.headline),
        h("p", {class: "sub"}, stage > 1 ? "앞 단계 결과를 다시 보고, 더 나눠도 효과가 작다는 답을 받았습니다. 이제 빌드하고 직접 플레이해 확인해 주세요."
          : "이 분석 기준으로는 더 정리할 만한 큰 매듭이 없다는 답을 받았습니다."),
        stage > 1 && !state.stale ? h("div", {class: "actions"}, h("a", {class: "btn primary", href: `#/job/${jobId}/finish`}, "빌드하고 플레이해 보기 →")) : null, meta];
    }
    // Both ways offered: the AI's pick comes first and the files below follow the way chosen.
    const kinds = [...new Set(r.files.map(f => f.kind))];
    const way = kinds.length > 1 ? chosen || r.first || "internal" : kinds[0];
    const choose = kind => () => { chosen = kind; fill(body, ...resultView(state)); };
    const methodBox = kinds.length > 1
      ? h("div", null, h("div", {class: "pick-q"}, "어느 것부터 할까요?"), h("div", {class: "choices"},
          ...kinds.sort((a, b) => (b === (r.first || "internal")) - (a === (r.first || "internal"))).map(kind => h("button", {type: "button",
            class: `choice ${way === kind ? "is-on" : ""}`, "aria-pressed": String(way === kind), onclick: choose(kind)},
            h("div", {class: "choice-top"}, h("i", {class: "radio", "aria-hidden": "true"}), h("b", null, METHODS[kind].name),
              kind === (r.first || "internal") ? h("span", {class: "ai-pick"}, "AI 추천") : null),
            h("p", null, METHODS[kind].what),
            kind === (r.first || "internal") && r.first_reason ? h("p", null, h("b", null, "먼저 하면 좋은 이유 "), ...codeText(codeTokens(r.first_reason))) : null))),
          h("p", {class: "help"}, "고르지 않은 방법은 다음 단계에서 이어서 제안합니다."))
      : h("div", {class: "method"}, h("b", null, `방법: ${METHODS[way].name}`), h("p", null, METHODS[way].what),
          h("p", {class: "help"}, `${stage}단계 · 단계가 끝나면 결과를 보여 드리고, 더 좋아질 곳이 있으면 다음 단계를 제안합니다(최대 3단계).`));
    const offered = r.files.filter(f => f.kind === way);
    let prev = r.effects.base;
    const items = offered.map((f, i) => {
      const st = r.effects.steps[r.files.indexOf(f)], unit = units.get(f.name);
      let effect = null;
      if (st.after !== null && st.reduced) { effect = h("div", {class: "effect"}, `고리 ${prev} → ${st.after}개 ${label}`); prev = st.after; }
      else if (st.after !== null) effect = h("div", {class: "effect warn"}, `⚠ 이 ${label}만으로는 고리가 거의 줄지 않습니다 (계산 결과 ${prev} → ${st.after}개)`);
      // The whole item opens the file in the diagnosis (the card list or the map, whichever is shown).
      const open = () => onFocus?.(f.name);
      return h("div", {class: "pitem link", role: "button", tabindex: "0", title: `${unit?.file || f.name} 진단 보기`, onclick: open,
          onkeydown: e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } }}, h("span", {class: "n"}, i + 1),
        h("div", null, h("b", null, unit?.file || f.name), h("span", {class: `kind ${f.kind}`}, f.kind === "link" ? "연결 정리" : "파일 안 정리"),
          h("p", null, ...codeText(codeTokens(f.reason))), h("p", {class: "how"}, ...codeText(codeTokens(f.change_idea))),
          f.targets?.length ? h("p", {class: "targets"}, "먼저 정리할 함수 ", ...f.targets.map(t => h("code", {class: "cname"}, t))) : null, effect));
    });
    return [staleBox,
      h("div", {class: "eyebrow"}, `AI 처방${stage > 1 ? ` · ${stage}단계` : ""} · ${offered.length}개 ${label}`), h("div", {class: "lead"}, r.headline),
      methodBox, cycleBox({...r, files: offered, effects: {...r.effects, steps: r.effects.steps.filter((_, i) => offered.includes(r.files[i]))}}), ...items,
      r.show_why_not_top ? h("div", {class: "bubble"}, h("h4", null, `왜 점수 1위 ‘${units.get(r.top_unit)?.name || r.top_unit}’부터 고치지 않나요?`), ...codeText(codeTokens(r.why_not_top))) : null,
      h("div", {class: "bubble"}, h("h4", null, "무엇이 좋아지나요?"), ...codeText(codeTokens(r.benefit))),
      state.stale ? null : h("div", {class: "actions"},
        h("a", {class: "btn ghost", href: `#/job/${jobId}/refactor?pick=1`}, "직접 고르기"),
        h("a", {class: "btn primary", href: `#/job/${jobId}/refactor${kinds.length > 1 ? `?way=${way}` : ""}`},
          kinds.length > 1 ? `${METHODS[way].name}로 진행 →` : "추천대로 진행 →")),
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
        fill(body, h("div", {class: "eyebrow"}, state.auto ? "AI 처방 · 다음 단계" : "AI 처방"),
          h("div", {class: "lead"}, state.auto ? "앞 단계 결과를 보고 다음 단계를 정하고 있습니다" : "전체 구조를 살펴보고 있습니다"), progress.el, h("p", {class: "help context"}),
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
