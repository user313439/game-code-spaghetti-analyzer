import {aiName, codeTokens, elapsedText, obj, plainReason, proseParts} from "./core.js";
import {diffView, lineCounts} from "./diff.js";
import {connectionPicker} from "./prescription.js";
import {codeText, fill, h, notice, progressBlock, prose} from "./ui.js";

const STAGES = ["코드 준비", "AI가 변경안 작성", "변경 범위 검사", "비교 준비"];
const WAY = "gsi-change-way";
// One file's progress in a change made per file ('deep').
const WORKER = {waiting: ["대기", ""], running: ["작성 중", "t-busy"], checking: ["검사 중", "t-busy"], done: ["완료", "t-ok"],
  no_changes: ["바꿀 곳 없음", "t-muted"], failed: ["거절", "t-bad"], skipped: ["건너뜀", "t-bad"], cancelled: ["취소됨", "t-muted"]};
// How one pass of a file ended (the program hands a big function to the AI again, up to 3 times).
const PASS = {kept: ["반영", "t-ok"], rejected: ["검사에서 빠짐", "t-bad"], limit: ["사용 한도로 멈춤", "t-bad"],
  failed: ["AI가 답하지 못함", "t-bad"], empty: ["더 바꿀 곳 없다고 답함", "t-muted"], cancelled: ["취소로 멈춤", "t-muted"]};

// Pass by pass: which blocks of which function went into which new helpers, and the complexity of
// the target functions before and after that pass. A pass that was not kept says why.
export function passView(w, open = false) {
  const rows = w.passes || [];
  if (!rows.length) return null;
  return h("details", {class: "passes", "data-key": `${w.key}:passes`, open},
    h("summary", null, `단계별로 무엇을 했는지 보기 · ${rows.length}단계`),
    h("ol", null, ...rows.map(p => {
      const [label, tone] = PASS[p.state] || [p.state, ""];
      const kept = p.state === "kept";
      return h("li", {class: "pass"},
        h("div", {class: "wline"}, h("b", null, `${p.step}단계`), h("span", {class: `wstate ${tone}`}, label),
          ...(p.cc || []).map(c => h("span", {class: "sub"}, h("code", {class: "cname"}, c.name), ` 복잡도 ${c.before} → ${c.after}`))),
        p.helpers?.length ? h("div", {class: "wtargets"}, "새로 만든 함수 ", ...p.helpers.map(t => h("code", {class: "cname"}, t))) : null,
        p.change ? h("p", null, kept ? null : h("i", null, "AI가 하려던 정리(반영하지 않음): "), ...codeText(codeTokens(p.change))) : null,
        p.evidence?.length ? h("ul", null, ...p.evidence.map(e => h("li", null, ...codeText(codeTokens(e))))) : null,
        p.reason ? h("div", {class: "sub"}, "이유: ", ...codeText(codeTokens(plainReason(p.reason).text))) : null);
    })));
}

// A reason in plain words; the program's own wording folds away under "자세한 이유".
// `key` names the folded detail so it stays open while the rows are drawn again every second.
function reasonView(error, tone = "werr", key = "") {
  const {text, detail} = plainReason(error);
  return h("div", {class: tone}, ...codeText(codeTokens(text)),
    detail ? h("details", {class: "reason-more", "data-key": key}, h("summary", null, "자세한 이유"), h("p", null, ...codeText(codeTokens(detail)))) : null);
}

function openPasses(event) {
  const more = event.currentTarget.closest(".worker")?.querySelector("details.passes");
  if (more) more.open = !more.open;
}

export function workerRows(workers) {
  return h("ul", {class: "workers"}, ...workers.map(w => {
    const [named, tone] = WORKER[w.state] || [w.state, ""];
    // Done, but a later pass did not get through: the passes before it are what the change holds.
    const label = w.state === "done" && w.stopped_at ? `${named}(${w.stopped_at}단계까지)` : named;
    const live = ["running", "checking"].includes(w.state) && w.started_at;
    const seconds = live ? Date.now() / 1000 - w.started_at : w.seconds;
    const sent = !w.mode ? "" : w.mode === "full" ? `통째로 보냄 · ${w.sent_kb}KB` : `큰 파일 · 대상 함수는 통째로 · ${w.sent_kb}KB / ${w.file_kb}KB`;
    // A big function is handed to the AI again (up to `steps` times), each pass going on from the last.
    const pass = live && w.step > 1 ? `이어서 정리 ${w.step}/${w.steps}단계` : "";
    return h("li", {class: `worker ${tone}`},
      h("div", {class: "wline"}, h("b", {class: "mono"}, w.label), h("span", {class: `wstate ${tone}`}, label),
        w.attempt > 1 ? h("span", {class: "sub"}, `다시 만들기 ${w.attempt - 1}회째`) : null,
        // Pressing the pass (or the target functions) opens what the earlier passes did.
        pass ? h("span", {class: `sub${w.passes?.length ? " w-link" : ""}`, onclick: openPasses}, pass) : null,
        sent ? h("span", {class: "sub"}, sent) : null, seconds ? h("span", {class: "sub"}, elapsedText(seconds)) : null),
      w.targets?.length ? h("div", {class: `wtargets${w.passes?.length ? " w-link" : ""}`, onclick: openPasses}, "대상 함수 ", ...w.targets.map(t => h("code", {class: "cname"}, t))) : null,
      w.helpers?.length ? h("div", {class: "wtargets"}, "새로 만든 함수 ", ...w.helpers.map(t => h("code", {class: "cname"}, t))) : null,
      w.skipped_targets?.length ? h("div", {class: "wwarn"}, `너무 커서 이번에 보내지 못한 함수: ${w.skipped_targets.join(", ")}`) : null,
      w.note && w.state === "done" ? h("div", {class: "sub"}, w.note,
        w.note_detail ? h("details", {class: "reason-more", "data-key": `${w.key}:note`}, h("summary", null, "자세한 이유"), h("p", null, ...codeText(codeTokens(w.note_detail)))) : null) : null,
      w.error && ["failed", "skipped"].includes(w.state) ? reasonView(w.error, "werr", `${w.key}:error`) : null,
      w.error && w.state === "cancelled" ? h("div", {class: "sub"}, w.error) : null,
      passView(w),
      // The program asks the AI once more by itself when a reply is turned down.
      w.retried && live ? h("div", {class: "sub"}, "첫 답이 검사에 걸려 이유를 알려 주고 자동으로 다시 만드는 중입니다: ",
        plainReason(w.retry_reason).text) : null,
      w.error && w.state === "no_changes" ? h("div", {class: "sub"}, ...codeText(codeTokens(w.error))) : null,
      w.last_error && w.attempt > 1 && ["waiting", "running", "checking"].includes(w.state)
        ? h("div", {class: "sub"}, "지난번 거절 이유: ", plainReason(w.last_error).text) : null);
  }));
}

export async function render(view, ctx, {jobId, query}) {
  const pick = new URLSearchParams(query || "").get("pick") === "1";
  const root = h("section", {class: "wrap wide"}, h("p", {class: "empty"}, "변경안 정보를 불러오고 있습니다."));
  const bar = h("div", {class: "bar-actions", hidden: true});
  view.append(root, bar);
  let alive = true, timer = null, job, diag, presc, connections, candidates, shown = "";
  const slot = h("div", {class: "alert-slot"});   // one notice at a time, above the current view
  const say = (message, tone) => fill(slot, message ? notice(message, tone) : null);
  ctx.setSteps(jobId, 2, {refactor: true});
  try {
    [job, diag, presc, connections, candidates] = await Promise.all([ctx.api(`/api/jobs/${jobId}`), ctx.api(`/api/jobs/${jobId}/diagnosis`),
      ctx.api(`/api/jobs/${jobId}/prescription`), ctx.api("/api/assistant/connections"), ctx.api(`/api/jobs/${jobId}/assistant/candidates`)]);
  } catch (error) { fill(root, notice(error.message)); return; }
  ctx.setCrumb(job.name);
  ctx.setSteps(jobId, 2, {refactor: true, result: Boolean(diag.round)});
  const label = diag.summary.unit_label;
  const units = new Map(diag.units.map(u => [u.fqn, u]));
  const plan = presc.result && !presc.result.done && !presc.stale ? presc.result.files : [];
  // Units the server can hand to the AI (source file inside the analysed folder, at most 180KB).
  const editable = new Set(candidates.map(c => c.fqn));

  async function load() {
    try { draw(await ctx.api(`/api/jobs/${jobId}/assistant`)); }
    catch (error) {
      if (!alive) return;
      if (shown === "running") { say(`진행 상태를 불러오지 못해 다시 시도합니다. ${error.message}`); poll(); return; }
      fill(root, notice(error.message), h("button", {class: "btn ghost", type: "button", onclick: load}, "다시 불러오기"));
      shown = "";
    }
  }
  function poll() { clearTimeout(timer); timer = setTimeout(() => alive && load(), 1000); }

  // ------------------------------------------------------------ selection
  function selection(state) {
    shown = "selection";
    bar.hidden = false;
    // After a cancelled or failed request the same files stay picked, ready to try again.
    const retry = ["cancelled", "failed"].includes(state.state) && state.action === "preview" ? state.candidates || [] : [];
    const chosen = new Set((retry.length ? retry : pick || !plan.length ? [] : plan.map(f => f.name)).filter(n => editable.has(n)));
    const picker = connectionPicker(connections, ctx.api, {step: "refactor"});
    // How the change is made: each file in depth (default), or links between files in one joint call.
    let saved = "deep";
    try { saved = localStorage.getItem(WAY) === "link" ? "link" : "deep"; } catch (_) { /* storage blocked */ }
    const way = h("select", {id: "change-way", "aria-label": "변경 방식"},
      h("option", {value: "deep"}, "한 번에 깊게 — 파일마다 복잡한 함수를 크게 나눠 정리 (권장)"),
      h("option", {value: "link"}, "파일 사이 연결 정리 — 헤더·#include 같은 선언을 함께 옮기기"));
    way.value = saved;
    const wayHelp = h("p", {class: "help"});
    const syncWay = () => {
      wayHelp.textContent = way.value === "deep"
        ? "파일마다 AI를 따로 불러 동시에 처리하고, 큰 함수는 한 번에 다 바꾸지 않고 최대 3번 이어서 나눠 정리합니다. 단계마다 검사해 통과한 만큼만 남기며, 보통 10~15분 걸립니다. 한 파일이 거절돼도 나머지는 그대로 남고, 그 파일만 다시 만들 수 있습니다."
        : "고른 파일을 한 번에 보내 공용 헤더를 나누거나 #include를 정리합니다. 정밀 분석(Clang)은 실제 호출·참조로 연결을 세므로 이 방식으로는 숫자가 거의 바뀌지 않을 수 있습니다.";
      try { localStorage.setItem(WAY, way.value); } catch (_) { /* storage blocked */ }
    };
    way.addEventListener("change", syncWay);
    syncWay();
    const go = h("button", {class: "btn primary", type: "button"}, "변경안 만들기 →");
    const count = h("span", {class: "sub"});
    const sync = () => { count.textContent = `${chosen.size}개 ${label} 선택 · 최대 5개`; go.disabled = !chosen.size; };
    const option = (u, extra) => {
      const can = editable.has(u.fqn);
      const box = h("input", {type: "checkbox", checked: chosen.has(u.fqn), disabled: !can});
      box.addEventListener("change", () => {
        if (box.checked && chosen.size >= 5) { box.checked = false; say(`한 번에 최대 5개 ${obj(label)} 고를 수 있습니다.`, "info"); return; }
        // One file is sent once: two classes of the same C# file cannot be picked together.
        const twin = box.checked && [...chosen].find(n => units.get(n)?.file === u.file);
        if (twin) { box.checked = false; say(`${u.file}에서는 ${label} 하나만 고를 수 있습니다 (이미 고른 ${label}: ${twin}).`, "info"); return; }
        box.checked ? chosen.add(u.fqn) : chosen.delete(u.fqn); say(""); sync();
      });
      return h("label", {class: `pickrow card ${can ? "" : "off"}`}, box, h("span", {class: `score sm g${u.grade}`}, Math.round(u.si)),
        h("div", null, h("b", null, u.file || u.name), extra || h("p", {class: "sub"}, u.sentence),
          can ? null : h("p", {class: "help"}, "이 파일은 AI에게 보낼 수 없습니다(분석 폴더 밖이거나 1MB를 넘는 파일).")));
    };
    const planned = plan.length && !pick ? h("div", null, h("h2", {class: "h2"}, "AI 처방대로 고칠 파일"),
      h("p", {class: "sub"}, `${presc.result.headline} 처방에서 고른 ${obj(label)} 그대로 사용합니다.`),
      h("div", {class: "picklist"}, ...plan.map(f => units.get(f.name) && option(units.get(f.name),
        h("p", {class: "sub"}, h("span", {class: `kind ${f.kind}`}, f.kind === "link" ? "연결 정리" : "파일 안 정리"), " ", f.change_idea))))) : null;
    // Picking by hand still lists the prescribed files (first, marked), so they can be kept or dropped.
    const inPlan = u => plan.some(f => f.name === u.fqn);
    const top = diag.units.filter(u => !inPlan(u)).slice(0, 12);
    const listed = pick ? [...plan.map(f => units.get(f.name)).filter(Boolean), ...top] : top;
    // Files picked for the cancelled/failed request are shown even when outside the top list.
    const extra = [...chosen].map(n => units.get(n)).filter(u => u && !listed.includes(u) && (pick || !inPlan(u)));
    const others = [...extra, ...listed];
    const rank = u => plan.findIndex(f => f.name === u.fqn);
    fill(root,
      h("div", {class: "page-head"}, h("div", null, h("div", {class: "eyebrow"}, "AI 리팩토링"),
        h("h1", {class: "h1"}, `어떤 ${obj(label)} 고칠까요?`),
        h("p", {class: "sub"}, `고른 ${label}의 실제 코드와, 그 ${obj(label)} 부르는 ${label}들의 #include 부분을 AI에게 보내 변경안을 받습니다. 원본은 바뀌지 않습니다.`))),
      slot,
      state.state === "failed" ? notice((state.workers || []).length
        ? `고른 파일 ${state.workers.length}개가 모두 변경안에 들어가지 못했습니다. 원본은 그대로입니다. 아래에서 파일별 이유를 보고 다시 만들 수 있습니다.`
        : plainReason(state.error || "변경안을 만들지 못했습니다.").text) : null,
      state.state === "cancelled" ? notice("AI 요청을 취소했습니다. 고칠 파일을 확인하고 다시 만들 수 있습니다.", "info") : null,
      state.no_changes ? notice("AI가 안전하게 바꿀 수 있는 코드가 없다고 답했습니다. 다른 파일을 고르거나 다시 시도해 주세요.", "info") : null,
      (state.workers || []).length && (state.no_changes || ["failed", "cancelled"].includes(state.state))
        ? h("div", {class: "card fails"}, h("div", {class: "h3"}, "파일별 결과"), workerRows(state.workers),
          state.state === "failed" ? h("div", {class: "actions"}, h("button", {class: "btn primary sm", type: "button", onclick: () => go.click()},
            "같은 파일로 다시 만들기 →")) : null) : null,
      planned,
      h("details", {class: "archive", open: pick || !plan.length || extra.length > 0}, h("summary", null, plan.length && !pick ? `직접 다른 ${label} 고르기` : `G-SI 상위 ${label}`),
        h("div", {class: "picklist"}, ...others.map(u => option(u, rank(u) >= 0
          ? h("p", {class: "sub"}, h("span", {class: "rec"}, `AI 처방 ${rank(u) + 1}순위`), " ", u.sentence) : null)))),
      h("div", {class: "card conn-card"}, h("label", {for: "change-way"}, "변경 방식"), way, wayHelp),
      h("div", {class: "card conn-card"}, picker.el));
    fill(bar, h("div", {class: "in"}, count, h("span", {class: "push"}), go));
    sync();
    go.addEventListener("click", async () => {
      const missing = picker.problem();
      if (missing) { say(missing); return; }
      const body = {action: "preview", candidates: [...chosen], ...picker.value(), ...(way.value === "deep" ? {strategy: "deep"} : {})};
      const fromPlan = plan.length && !pick && [...chosen].every(n => plan.some(f => f.name === n));
      body[fromPlan ? "use_prescription" : "direct"] = true;
      go.disabled = true;
      say("");
      try { draw(await ctx.api(`/api/jobs/${jobId}/assistant`, {method: "POST", body: JSON.stringify(body)})); }
      catch (error) { say(error.message); go.disabled = false; }
    });
  }

  // ------------------------------------------------------------ running
  const progress = progressBlock(STAGES);
  async function cancel(event) {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "취소하는 중…";
    try { draw(await ctx.api(`/api/jobs/${jobId}/assistant/cancel`, {method: "POST", body: "{}"})); }
    catch (error) { say(error.message); if (button.isConnected) { button.disabled = false; button.textContent = "요청 취소"; } }
  }
  function running(state) {
    bar.hidden = true;
    const p = state.progress || {};
    const elapsed = state.started_at ? elapsedText(Date.now() / 1000 - state.started_at) : "";
    progress.update({step: Math.min(3, p.step || 0), total: 4, text: p.label || "", elapsed, indeterminate: p.indeterminate});
    const deep = (state.workers || []).length > 0;
    if (shown !== "running") {   // build once; later polls only move the progress and the context line
      const names = (state.candidates || []).map(n => units.get(n)?.file || n).join(" · ");
      say("");
      fill(root, slot, h("div", {class: "card running"}, h("div", {class: "eyebrow"}, deep ? "변경안 만드는 중 · 한 번에 깊게" : "변경안 만드는 중"),
        h("h2", {class: "h2"}, deep ? `AI가 파일 ${state.workers.length}개를 하나씩 맡아 깊게 정리하고 있습니다` : `AI가 ${names}의 실제 코드 변경안을 작성하고 있습니다`),
        h("p", {class: "sub"}, deep
          ? "파일마다 AI를 따로 불러 동시에 진행하고, 큰 함수는 최대 3번 이어서 나눠 정리합니다. 받은 변경안은 단계마다 설명한 함수만 바뀌었는지 프로그램이 검사하고, 통과한 것만 하나의 변경안으로 묶습니다."
          : "받은 변경안은 설명한 범위만 바뀌었는지 프로그램이 검사합니다. 함수 본문을 바꾸지 않는 연결 정리는 문법 트리로 다시 확인합니다."),
        progress.el, h("p", {class: "help context"}), h("div", {class: "workers-slot"}),
        h("div", {class: "actions"}, h("button", {class: "btn ghost", type: "button", onclick: cancel}, "요청 취소"))));
      shown = "running";
    } else say("");
    root.querySelector(".context").textContent = deep ? ""
      : state.context ? `보낸 코드 ${(state.context.sent_source_bytes / 1024).toFixed(0)}KB · 함께 수정 후보 ${(state.companion_candidates || []).length}개` : "";
    if (deep) {
      const slot = root.querySelector(".workers-slot");
      const opened = new Set([...slot.querySelectorAll("details[open]")].map(d => d.dataset.key));
      fill(slot, workerRows(state.workers));
      for (const more of slot.querySelectorAll("details[data-key]")) more.open = opened.has(more.dataset.key);
    }
    poll();
  }

  // ------------------------------------------------------------ ready
  const rich = text => prose(proseParts(text));
  function deepSummary(workers) {
    const count = k => workers.filter(w => w.state === k).length;
    const parts = [`파일 ${workers.length}개를 하나씩 맡겨 정리했습니다 · 변경 ${count("done")}개`];
    if (count("no_changes")) parts.push(`바꿀 곳 없음 ${count("no_changes")}개`);
    if (count("failed") + count("skipped")) parts.push(`거절·건너뜀 ${count("failed") + count("skipped")}개`);
    return parts.join(" · ");
  }
  // Files of a per-file change that were rejected or not started: their reasons, and a way to redo just them.
  function failures(state) {
    const rows = state.preview_failures || [];
    if (!rows.length) return null;
    const picker = connectionPicker(connections, ctx.api, {step: "refactor"});
    const redo = async (event, keys) => {
      const button = event.currentTarget;
      const missing = picker.problem();
      if (missing) { say(missing); return; }
      button.disabled = true;
      const body = {action: "preview", strategy: "deep", retry_of: state.preview_id, candidates: keys, ...picker.value(),
        ...(state.plan_source === "prescription" ? {use_prescription: true} : {direct: true})};
      try { draw(await ctx.api(`/api/jobs/${jobId}/assistant`, {method: "POST", body: JSON.stringify(body)})); }
      catch (error) { say(error.message); button.disabled = false; }
    };
    return h("div", {class: "card fails"},
      h("div", {class: "h3"}, `변경안에 들어가지 못한 파일 ${rows.length}개`),
      h("p", {class: "help"}, "아래 파일은 검사에서 거절됐거나 시간이 부족해 시작하지 못했습니다. 나머지 파일의 변경안은 그대로이며, 이 파일만 다시 만들어 같은 변경안에 더할 수 있습니다."),
      h("ul", {class: "workers"}, ...rows.map(w => h("li", {class: "worker t-bad"},
        h("div", {class: "wline"}, h("b", {class: "mono"}, w.label), h("span", {class: "wstate t-bad"}, w.state === "skipped" ? "건너뜀" : "거절"),
          h("button", {class: "btn ghost sm push", type: "button", onclick: e => redo(e, [w.key])}, "이 파일만 다시 만들기")),
        w.error ? reasonView(w.error) : null))),
      rows.length > 1 ? h("div", {class: "actions"}, h("button", {class: "btn ghost sm", type: "button", onclick: e => redo(e, rows.map(w => w.key))}, "모두 다시 만들기")) : null,
      picker.el);
  }
  function ready(state) {
    shown = "ready";
    const advice = state.change_advice || {};
    const deep = (state.workers || []).length > 0;
    const files = state.preview.files.map(item => ({...item, ...lineCounts(item)}));
    const reviews = new Map((advice.file_reviews || []).map(r => [r.path, r]));
    const companions = new Map((advice.companions || []).map(c => [c.path, c.reason]));
    const targets = files.filter(f => (f.role || "target") === "target"), partners = files.filter(f => f.role === "companion"), created = files.filter(f => f.role === "created");
    const kept = (advice.file_reviews || []).filter(r => r.decision !== "refactor");
    let selected = targets[0] || files[0];
    const left = h("div", {class: "card files"}), center = h("div", {class: "card diffcard"}), right = h("aside", {class: "card ai-note"});
    const item = (f, extra) => {
      const el = h("button", {type: "button", class: `fitem ${f === selected ? "on" : ""}`, "aria-pressed": String(f === selected), dataset: {path: f.path},
        onclick: () => { selected = f; paint(); left.querySelector(`[data-path="${CSS.escape(f.path)}"]`)?.focus(); }},
        h("b", null, f.path), h("div", {class: "tags"}, extra, h("span", {class: "plus"}, `+${f.add}`), h("span", {class: "minus"}, `−${f.rem}`)));
      return el;
    };
    // Files the AI read (the picked files and their same-name headers) but decided to leave as they are.
    const keptItems = kept.map(r => ({path: r.path, role: "kept", review: r}));
    const keptItem = f => h("button", {type: "button", class: `fitem kept ${f === selected ? "on" : ""}`, "aria-pressed": String(f === selected), dataset: {path: f.path},
      onclick: () => { selected = f; paint(); left.querySelector(`[data-path="${CSS.escape(f.path)}"]`)?.focus(); }},
      h("b", null, f.path), h("div", {class: "tags"}, h("span", {class: "tag keep"}, "그대로 둠")));
    function paint() {
      fill(left, h("div", {class: "h3"}, `바뀌는 파일 ${targets.length}개`),
        ...targets.map(f => item(f, h("span", {class: "tag chg"}, reviews.get(f.path)?.change_type === "declarations" ? "선언 정리" : "변경"))),
        keptItems.length ? h("details", {class: "group kept", open: keptItems.includes(selected)}, h("summary", null, `AI가 함께 읽고 그대로 둔 파일 ${keptItems.length}개`),
          h("p", {class: "help"}, "처방에 들어 있거나 고른 파일의 짝 헤더라서 함께 보냈지만, 이번 변경안에서는 바꾸지 않은 파일입니다. 누르면 그대로 둔 이유를 볼 수 있습니다."),
          ...keptItems.map(keptItem)) : null,
        partners.length ? h("details", {class: "group", open: partners.includes(selected)}, h("summary", null, `함께 수정되는 파일 ${partners.length}개`),
          h("p", {class: "help"}, "#include/using 줄만 바뀝니다."), ...partners.map(f => item(f, h("span", {class: "tag keep"}, "include")))) : null,
        created.length ? h("div", null, h("div", {class: "h3 gap"}, "새 파일"), ...created.map(f => item(f, h("span", {class: "tag new"}, "새 헤더")))) : null,
        (advice.relationships || []).length ? h("div", {class: "rel"}, h("b", null, "파일 사이 관계"),
          h("ul", null, ...advice.relationships.map(r => h("li", null, ...codeText(codeTokens(r)))))) : null);
      for (const el of left.querySelectorAll(".fitem")) {
        const on = el.dataset.path === selected.path;
        el.classList.toggle("on", on);
        if (el.tagName === "BUTTON") el.setAttribute("aria-pressed", String(on));
      }
      const r = reviews.get(selected.path);
      if (selected.role === "kept") {
        fill(center, h("div", {class: "dhead"}, h("b", null, selected.path), h("span", {class: "push sub"}, "변경 없음")),
          h("p", {class: "nochange"}, "이 파일은 이번 변경안에서 바뀌지 않습니다. 오른쪽에서 AI가 그대로 둔 이유를 볼 수 있습니다."));
        // A review the server filled in for a context-only file says nothing of its own; say it plainly.
        const filled = (r?.finding || "").startsWith("AI가 이 파일을 따로 설명하지 않았습니다");
        fill(right, h("div", {class: "eyebrow"}, `AI 소견 · ${selected.path}`),
          filled || !r ? h("div", {class: "bubble"}, h("h4", null, "왜 함께 보냈나요?"), "고른 파일과 같은 이름의 헤더라서 문맥으로 함께 보냈습니다. AI는 이 파일을 바꾸지 않았습니다.")
            : [h("div", {class: "bubble"}, h("h4", null, "이 파일은 어떤 역할인가요?"), rich(r.role)),
              h("div", {class: "bubble"}, h("h4", null, "왜 그대로 두나요?"), rich(r.reason)),
              h("div", {class: "bubble"}, h("h4", null, "AI가 본 내용"), rich(r.finding)),
              r.change ? h("div", {class: "bubble"}, h("h4", null, "AI의 판단"), rich(r.change)) : null]);
        return;
      }
      fill(center, h("div", {class: "dhead"}, h("b", null, selected.path),
        ...(r?.targets || []).map(t => h("span", {class: "chip mono"}, t)),
        ...(selected.added_helpers || []).map(t => h("span", {class: "chip mono new"}, `새 함수 ${t}`)),
        h("span", {class: "push sub"}, h("span", {class: "plus"}, `+${selected.add}`), " ", h("span", {class: "minus"}, `−${selected.rem}`))), diffView(selected));
      if (selected.role === "companion") {
        fill(right, h("div", {class: "eyebrow"}, `함께 수정 · ${selected.path}`), h("div", {class: "bubble"}, h("h4", null, "왜 함께 바꾸나요?"), companions.get(selected.path) || ""),
          h("div", {class: "bubble"}, h("h4", null, "무엇이 바뀌나요?"), "#include/using 줄만 바뀝니다. 이 파일의 함수와 동작 코드는 그대로입니다."));
      } else if (selected.role === "created") {
        fill(right, h("div", {class: "eyebrow"}, `새 파일 · ${selected.path}`), h("div", {class: "bubble"}, h("h4", null, "왜 새로 만드나요?"), selected.reason || ""),
          h("div", {class: "bubble"}, h("h4", null, "무엇이 들어가나요?"), "자료형·매크로 같은 선언만 담습니다. 함수 정의는 넣을 수 없습니다."));
      } else if (r) {
        fill(right, h("div", {class: "eyebrow"}, `AI 소견 · ${selected.path}`),
          h("div", {class: "bubble"}, h("h4", null, "이 파일은 어떤 역할인가요?"), rich(r.role)),
          h("div", {class: "bubble"}, h("h4", null, "무엇이 문제인가요?"), rich(r.finding)),
          h("div", {class: "bubble"}, h("h4", null, "왜 이렇게 바꾸나요?"), rich(r.reason)),
          h("div", {class: "bubble"}, h("h4", null, "무엇을 바꾸나요?"), rich(r.change)),
          (worker => worker?.passes?.length > 1 ? h("div", {class: "bubble"}, h("h4", null, "단계별로 무엇을 했나요?"), passView(worker))
            : null)((state.workers || []).find(w => w.path === selected.path)),
          h("div", {class: "bubble"}, h("h4", null, "무엇이 좋아지나요?"), rich(r.expected_effect)),
          h("details", {class: "bubble"}, h("summary", null, `영향을 받는 곳과 확인할 동작 (${(r.checks || []).length})`), rich(r.impact),
            h("ul", null, ...(r.checks || []).map(c => h("li", null, ...codeText(codeTokens(c)))))));
      } else fill(right, h("p", {class: "sub"}, "이 파일에 대한 설명이 없습니다."));
    }
    const o = advice.overview || {};
    fill(root,
      h("div", {class: "page-head"}, h("div", null, h("div", {class: "eyebrow"}, `AI 리팩토링 · ${targets.length}개 ${label} 변경안`), h("h1", {class: "h1"}, o.title || "변경안"))),
      slot,
      h("div", {class: "card overview"}, h("div", {class: "row-gap"}, h("div", {class: "h2"}, "전체 요약"),
        h("span", {class: "sub"}, `${aiName(state.service, state.model)} · ${state.finished_at && state.started_at ? Math.round(state.finished_at - state.started_at) + "초" : ""}`)),
        deep ? h("p", {class: "help deep-sum"}, deepSummary(state.workers)) : null,
        h("div", {class: "ovgrid"}, ...[["무엇이 문제인가요?", o.problem], ["왜 바꿔야 하나요?", o.reason], ["어떻게 바꾸나요?", o.change], ["무엇이 좋아지나요?", o.expected_effect]]
          .map(([q, a], i) => h("div", {class: "q"}, h("h4", null, h("i", null, i + 1), q), a ? rich(a) : "")))),
      failures(state),
      h("div", {class: "bench"}, left, center, right));
    paint();
    const add = files.reduce((s, f) => s + f.add, 0), rem = files.reduce((s, f) => s + f.rem, 0);
    const apply = h("button", {class: "btn primary", type: "button"}, "이 변경안 적용하기 →");
    bar.hidden = false;
    fill(bar, h("div", {class: "in"},
      h("div", null, h("b", null, `${targets.length}개 ${label}${partners.length ? ` · 함께 수정 ${partners.length}개` : ""}${created.length ? ` · 새 파일 ${created.length}개` : ""}`),
        h("span", {class: "sub"}, " · ", h("span", {class: "plus"}, `+${add}`), " ", h("span", {class: "minus"}, `−${rem}`), "줄 · 원본은 그대로 두고 사본에 적용합니다")),
      h("span", {class: "push"}),
      h("button", {class: "btn ghost", type: "button", onclick: () => selection({state: "idle"})}, "변경안 다시 만들기"), apply));
    apply.addEventListener("click", async () => {
      apply.disabled = true;
      try { await ctx.api(`/api/jobs/${jobId}/assistant/apply`, {method: "POST", body: JSON.stringify({preview_id: state.preview_id})}); location.hash = `#/job/${jobId}/result`; }
      catch (error) { say(error.message); apply.disabled = false; }
    });
  }

  function draw(state) {
    if (!alive) return;
    clearTimeout(timer);
    if (state.state === "running" && state.action === "apply") { location.hash = `#/job/${jobId}/result`; return; }
    if (state.state === "running") { running(state); return; }
    if (state.state === "complete" && state.action === "preview" && state.preview && state.preview_id && !state.preview_stale) { ready(state); return; }
    selection(state);
    if (state.preview_stale) say("지난 변경안은 다른 라운드의 코드로 만든 것이라 적용할 수 없습니다. 현재 수정본 기준으로 다시 만들어 주세요.", "info");
  }
  await load();
  return () => { alive = false; clearTimeout(timer); bar.remove(); };
}
