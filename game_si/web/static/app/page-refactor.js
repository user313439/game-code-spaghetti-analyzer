import {aiName, elapsedText, obj} from "./core.js";
import {diffView, lineCounts} from "./diff.js";
import {connectionPicker} from "./prescription.js";
import {fill, h, notice, progressBlock} from "./ui.js";

const STAGES = ["코드 준비", "AI가 변경안 작성", "변경 범위 검사", "비교 준비"];

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
    const picker = connectionPicker(connections, ctx.api);
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
          can ? null : h("p", {class: "help"}, "이 파일은 AI에게 보낼 수 없습니다(180KB 초과이거나 분석 폴더 밖의 파일).")));
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
      state.state === "failed" ? notice(state.error || "변경안을 만들지 못했습니다.") : null,
      state.state === "cancelled" ? notice("AI 요청을 취소했습니다. 고칠 파일을 확인하고 다시 만들 수 있습니다.", "info") : null,
      state.no_changes ? notice("AI가 안전하게 바꿀 수 있는 코드가 없다고 답했습니다. 다른 파일을 고르거나 다시 시도해 주세요.", "info") : null,
      planned,
      h("details", {class: "archive", open: pick || !plan.length || extra.length > 0}, h("summary", null, plan.length && !pick ? `직접 다른 ${label} 고르기` : `G-SI 상위 ${label}`),
        h("div", {class: "picklist"}, ...others.map(u => option(u, rank(u) >= 0
          ? h("p", {class: "sub"}, h("span", {class: "rec"}, `AI 처방 ${rank(u) + 1}순위`), " ", u.sentence) : null)))),
      h("div", {class: "card conn-card"}, h("b", null, "AI 연결"), picker.el));
    fill(bar, h("div", {class: "in"}, count, h("span", {class: "push"}), go));
    sync();
    go.addEventListener("click", async () => {
      const missing = picker.problem();
      if (missing) { say(missing); return; }
      const body = {action: "preview", candidates: [...chosen], ...picker.value()};
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
    if (shown !== "running") {   // build once; later polls only move the progress and the context line
      const names = (state.candidates || []).map(n => units.get(n)?.file || n).join(" · ");
      say("");
      fill(root, slot, h("div", {class: "card running"}, h("div", {class: "eyebrow"}, "변경안 만드는 중"),
        h("h2", {class: "h2"}, `AI가 ${names}의 실제 코드 변경안을 작성하고 있습니다`),
        h("p", {class: "sub"}, "받은 변경안은 설명한 범위만 바뀌었는지 프로그램이 검사합니다. 함수 본문을 바꾸지 않는 연결 정리는 문법 트리로 다시 확인합니다."),
        progress.el, h("p", {class: "help context"}),
        h("div", {class: "actions"}, h("button", {class: "btn ghost", type: "button", onclick: cancel}, "요청 취소"))));
      shown = "running";
    } else say("");
    root.querySelector(".context").textContent = state.context
      ? `보낸 코드 ${(state.context.sent_source_bytes / 1024).toFixed(0)}KB · 함께 수정 후보 ${(state.companion_candidates || []).length}개` : "";
    poll();
  }

  // ------------------------------------------------------------ ready
  function ready(state) {
    shown = "ready";
    const advice = state.change_advice || {};
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
        (advice.relationships || []).length ? h("div", {class: "rel"}, h("b", null, "파일 사이 관계"), ...advice.relationships.map(r => h("p", null, `· ${r}`))) : null);
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
            : [h("div", {class: "bubble"}, h("h4", null, "이 파일은 어떤 역할인가요?"), r.role),
              h("div", {class: "bubble"}, h("h4", null, "왜 그대로 두나요?"), r.reason),
              h("div", {class: "bubble"}, h("h4", null, "AI가 본 내용"), r.finding),
              r.change ? h("div", {class: "bubble"}, h("h4", null, "AI의 판단"), r.change) : null]);
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
          h("div", {class: "bubble"}, h("h4", null, "이 파일은 어떤 역할인가요?"), r.role),
          h("div", {class: "bubble"}, h("h4", null, "무엇이 문제인가요?"), r.finding),
          h("div", {class: "bubble"}, h("h4", null, "왜 이렇게 바꾸나요?"), r.reason),
          h("div", {class: "bubble"}, h("h4", null, "무엇을 바꾸나요?"), r.change),
          h("div", {class: "bubble"}, h("h4", null, "무엇이 좋아지나요?"), r.expected_effect),
          h("details", {class: "bubble"}, h("summary", null, `영향을 받는 곳과 확인할 동작 (${(r.checks || []).length})`), h("p", null, r.impact), h("ul", null, ...(r.checks || []).map(c => h("li", null, c)))));
      } else fill(right, h("p", {class: "sub"}, "이 파일에 대한 설명이 없습니다."));
    }
    const o = advice.overview || {};
    fill(root,
      h("div", {class: "page-head"}, h("div", null, h("div", {class: "eyebrow"}, `AI 리팩토링 · ${targets.length}개 ${label} 변경안`), h("h1", {class: "h1"}, o.title || "변경안"))),
      slot,
      h("div", {class: "card overview"}, h("div", {class: "row-gap"}, h("div", {class: "h2"}, "전체 요약"),
        h("span", {class: "sub"}, `${aiName(state.service, state.model)} · ${state.finished_at && state.started_at ? Math.round(state.finished_at - state.started_at) + "초" : ""}`)),
        h("div", {class: "ovgrid"}, ...[["무엇이 문제인가요?", o.problem], ["왜 바꿔야 하나요?", o.reason], ["어떻게 바꾸나요?", o.change], ["무엇이 좋아지나요?", o.expected_effect]]
          .map(([q, a], i) => h("div", {class: "q"}, h("h4", null, h("i", null, i + 1), q), a || "")))),
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
