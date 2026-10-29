// Finishing a guided refactor: build the changed game, try what the change touched, then a done record.
import {COMMON_PLACES, REPORT_KINDS, elapsedText, playGroups} from "./core.js";
import {METHODS} from "./prescription.js";
import {confirmDialog, fill, h, notice, progressBlock, toast} from "./ui.js";

const fmt = v => Number(v).toLocaleString("ko-KR");

// One line per applied stage: what it did, in the words of the result page.
export function stageLine(round) {
  const rows = round.comparison?.functions || [];
  const made = rows.filter(f => !f.before && f.after).length;
  const shrunk = rows.filter(f => f.before && f.after && f.after.loc < f.before.loc).length;
  const way = round.method === "declarations" ? "link" : "internal";
  const what = way === "internal" && made ? `큰 함수 ${shrunk}개 → 작은 함수 ${made}개` : `파일 ${round.files.length}개 정리`;
  return {title: `${round.round}단계 ${METHODS[way].name}`, what};
}

export async function render(view, ctx, {jobId}) {
  const root = h("section", {class: "f-wrap"}, h("p", {class: "empty"}, "마무리 정보를 불러오고 있습니다."));
  view.append(root);
  ctx.setSteps(jobId, 4, {refactor: true, result: true, finish: true});
  let alive = true, timer = null, data = null, retry = false, closeReport = null;   // closes an open problem report
  const checked = new Set();
  // What was ticked, kept as a record: each item cut short so 3 stages of checks fit one request.
  const ticked = () => [...checked].map(k => k.slice(0, 200));

  async function load() {
    try {
      const [job, rounds, tangle, game] = await Promise.all([ctx.api(`/api/jobs/${jobId}`), ctx.api(`/api/jobs/${jobId}/rounds`),
        ctx.api(`/api/jobs/${jobId}/tangle`), ctx.api(`/api/jobs/${jobId}/demo`)]);
      ctx.setCrumb(job.name);
      data = {job, rounds, tangle, game};
      draw();
    } catch (error) {
      if (alive) fill(root, notice(error.message), h("button", {class: "btn ghost", type: "button", onclick: load}, "다시 불러오기"));
    }
  }

  function draw() {
    if (!alive) return;
    const {job, rounds, tangle, game} = data;
    const n = rounds.current;
    if (!n) {
      fill(root, h("div", {class: "card s-card"}, h("div", {class: "s-q"}, "마무리"), h("div", {class: "s-title"}, "아직 적용한 정리가 없습니다"),
        h("p", {class: "s-lead"}, "엉킴 진단에서 처방을 받고 변경안을 적용한 뒤 마무리할 수 있습니다."),
        h("div", {class: "actions"}, h("a", {class: "btn primary", href: `#/job/${jobId}/diagnosis`}, "엉킴 진단으로 →"))));
      return;
    }
    const active = rounds.rounds.slice(0, n), round = active[n - 1];
    const play = round.checks?.play;
    if (play?.ok && !retry) { fill(root, ...done(job, active, tangle, play)); return; }
    const built = game.available && game.state === "complete" && game.revision === round.revision;
    const reported = play && !play.ok && !retry;
    const at = reported ? 1 : built || !game.available ? 1 : 0;
    const summary = h("div", {class: "card f-sum", "aria-label": "이번에 정리한 것"},
      h("i", {"aria-hidden": "true"}, "✓"), h("span", null, ...active.flatMap((r, i) => { const s = stageLine(r); return [i ? " · " : "", h("b", null, s.title), ` ${s.what}`]; })),
      h("a", {class: "btn ghost sm push", href: `#/job/${jobId}/result`}, "단계 결과 다시 보기"));
    const names = ["빌드", "직접 플레이", "완료"];
    const steps = h("ol", {class: "f-steps", "aria-label": "마무리 순서"}, ...names.map((name, i) => {
      const bad = reported && i === 1;
      const cls = i < at ? "is-done" : i === at ? (bad ? "is-bad" : "is-now") : "";
      return h("li", {class: cls}, h("i", null, i < at ? "✓" : bad ? "!" : String(i + 1)), name, bad ? " · 문제 있음" : "");
    }));
    const head = h("header", {class: "s-head"}, h("div", {class: "eyebrow"}, "마무리"),
      h("h1", null, "게임이 예전처럼 움직이는지 확인합니다"),
      h("p", null, "정리한 코드를 빌드해 게임을 켜고, 바뀐 곳과 관련된 동작을 직접 해 봅니다."), summary, steps);
    let main;
    if (game.available && !built) main = [buildCard(game, round)];
    else if (reported) main = [builtRow(game, round), reportedCard(play, active)];
    else main = [builtRow(game, round), playCard(active, n)];
    fill(root, head, ...main);
  }

  // ------------------------------------------------------------ build
  function buildCard(game, round) {
    const status = h("div", {class: "game-status"});
    const gp = progressBlock();
    const button = h("button", {class: "btn primary", type: "button"}, "게임 빌드하고 실행 ▶");
    const showProgress = state => {
      const p = state.progress || {};
      gp.update({step: p.step || 0, total: p.total || 4, text: p.label || "", indeterminate: p.indeterminate,
        elapsed: state.started_at ? elapsedText((Date.now() - new Date(state.started_at).getTime()) / 1000) : ""});
      fill(status, gp.el);
    };
    async function watch() {
      let state;
      try { state = await ctx.api(`/api/jobs/${jobId}/demo`); }
      catch (_) { if (alive) timer = setTimeout(watch, 1000); return; }
      if (!alive) return;
      if (state.state === "running") { showProgress(state); timer = setTimeout(watch, 1000); return; }
      if (state.state === "complete" && state.revision === round.revision) { await launch(); load(); return; }
      fill(status, notice(state.error || "게임을 빌드하지 못했습니다.")); button.disabled = false;
    }
    button.addEventListener("click", async () => {
      button.disabled = true;
      try { showProgress(await ctx.api(`/api/jobs/${jobId}/demo/prepare`, {method: "POST", body: "{}"})); watch(); }
      catch (error) { fill(status, notice(error.message)); button.disabled = false; }
    });
    if (game.state === "running") { button.disabled = true; showProgress(game); timer = setTimeout(watch, 1000); }
    else if (game.state === "failed") fill(status, notice(`지난번 빌드에 실패했습니다. ${game.error || ""}`));
    return h("section", {class: "card s-card f-build"}, h("div", {class: "s-q"}, "1. 빌드"), h("div", {class: "s-title"}, "버튼 하나로 빌드하고 게임을 켭니다"),
      h("p", {class: "s-lead"}, "수정본을 컴파일해 실행 파일을 만들고 바로 실행합니다. 보통 1~2분 걸립니다."), button, status);
  }
  async function launch() {
    try { const r = await ctx.api(`/api/jobs/${jobId}/demo/launch`, {method: "POST", body: JSON.stringify({version: "modified"})}); toast(r.message || "게임을 켰습니다."); }
    catch (error) { toast(error.message); }
  }
  function builtRow(game, round) {
    if (!game.available) {   // no build steps are registered for this project: the user builds it
      return h("div", {class: "card f-sum"}, h("span", null, h("b", null, "직접 빌드"), " · 이 프로젝트에는 등록된 빌드 절차가 없습니다. 수정본을 내려받아 평소처럼 빌드한 뒤 해 보세요."),
        h("a", {class: "btn ghost sm push", href: `/revisions/${jobId}/${round.revision}/modified-source.zip`}, "수정본 내려받기 (.zip)"));
    }
    return h("div", {class: "card f-sum"}, h("i", {"aria-hidden": "true"}, "✓"), h("span", null, h("b", null, "빌드 성공"), " · 게임이 켜졌습니다"),
      h("button", {class: "btn ghost sm push", type: "button", onclick: launch}, "게임 다시 실행 ▶"));
  }

  // ------------------------------------------------------------ play
  function playCard(active, n) {
    const groups = playGroups(active);
    const total = groups.reduce((s, g) => s + g.items.length, 0);
    const count = h("div", {class: "f-count"}), bar = h("span");
    const sync = () => { count.textContent = `${checked.size} / ${total} 확인`; bar.style.width = `${total ? 100 * checked.size / total : 0}%`; };
    const item = it => {
      const box = h("input", {type: "checkbox", checked: checked.has(it.key)});
      const label = h("label", {class: checked.has(it.key) ? "is-checked" : ""}, box,
        h("span", null, it.action, h("small", null, `바뀐 곳: ${it.file.split("/").pop()}${it.targets.length ? ` · ${it.targets.join(", ")}` : ""}`)));
      box.addEventListener("change", () => { box.checked ? checked.add(it.key) : checked.delete(it.key); label.classList.toggle("is-checked", box.checked); sync(); });
      return h("li", null, label);
    };
    const ok = h("button", {class: "btn primary", type: "button"}, "정상입니다");
    ok.addEventListener("click", async () => {
      ok.disabled = true;
      try { await ctx.api(`/api/jobs/${jobId}/rounds/${n}/play`, {method: "POST", body: JSON.stringify({ok: true, checked: ticked()})}); retry = false; load(); }
      catch (error) { toast(error.message); ok.disabled = false; }
    });
    sync();
    return h("section", {class: "card s-card"}, h("div", {class: "s-q"}, "2. 직접 플레이"), h("div", {class: "s-title"}, "바뀐 곳과 관련된 동작을 해 보세요"),
      h("p", {class: "s-lead"}, total ? "AI가 변경안을 만들면서 적은 ‘확인할 동작’을 게임의 화면별로 묶었습니다. 해 본 것에 체크하세요. 모두 체크하지 않아도 됩니다."
        : "이번 변경안에는 확인할 동작 목록이 없습니다. 게임을 평소처럼 해 보고 결과를 알려 주세요."),
      total ? [count, h("div", {class: "f-prog"}, bar)] : null,
      ...groups.map(g => h("div", {class: "f-group"}, h("h4", null, g.where, g.placed ? null : h("small", null, "파일")), h("ul", {class: "f-items"}, ...g.items.map(item)))),
      h("div", {class: "f-verdict"}, ok, h("button", {class: "btn ghost", type: "button", onclick: () => reportWindow(active, n, groups)}, "문제가 있었습니다"),
        h("p", {class: "help"}, "‘정상입니다’를 누르면 정리를 마칩니다.")));
  }

  // A problem found while playing: kind, where, words and a screenshot, kept in this job's folder.
  function reportWindow(active, n, groups) {
    let kind = REPORT_KINDS[1], shot = null;
    const tags = h("div", {class: "g-tags"});
    const drawTags = () => fill(tags, ...REPORT_KINDS.map(k => h("button", {type: "button", class: k === kind ? "is-on" : "", "aria-pressed": String(k === kind),
      onclick: () => { kind = k; drawTags(); }}, k)));
    drawTags();
    const where = h("select", null,
      ...groups.map(g => h("optgroup", {label: `확인 목록 · ${g.where}`}, ...g.items.map(it => h("option", {value: `${g.where} · ${it.action}`}, it.action)))),
      h("optgroup", {label: "그 밖 (어느 게임이든 같은 항목)"}, ...COMMON_PLACES.map(p => h("option", {value: p}, p))));
    const note = h("textarea", {placeholder: "예: 상점에서 오른쪽 키를 누르면 선택이 두 칸씩 움직여요", maxlength: "2000"});
    const shotName = h("span");
    const file = h("input", {type: "file", accept: "image/png,image/jpeg,image/webp", hidden: true});
    const takeImage = blob => { if (!blob || !/^image\/(png|jpeg|webp)$/.test(blob.type)) { toast("PNG·JPG·WEBP 이미지만 붙일 수 있습니다."); return; } shot = blob; shotName.textContent = `✓ 이미지 1장 (${Math.ceil(blob.size / 1024)}KB)`; };
    file.addEventListener("change", () => takeImage(file.files[0]));
    const drop = h("div", {class: "g-shot", tabindex: "0"}, "Ctrl+V로 붙여 넣거나 이미지를 끌어 놓으세요", h("br"),
      h("button", {class: "btn ghost sm", type: "button", onclick: () => file.click()}, "이미지 고르기"), " ", shotName, file);
    drop.addEventListener("dragover", e => e.preventDefault());
    drop.addEventListener("drop", e => { e.preventDefault(); takeImage(e.dataTransfer.files[0]); });
    const onPaste = e => { const img = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith("image/")); if (img) takeImage(img.getAsFile()); };
    document.addEventListener("paste", onPaste);
    // Closing twice is harmless; a late reply from an older window never forgets the open one.
    const close = () => { document.removeEventListener("paste", onPaste); overlay.remove(); if (closeReport === close) closeReport = null; };
    closeReport = close;
    const send = h("button", {class: "btn primary", type: "button"}, "기록하기");
    send.addEventListener("click", async () => {
      send.disabled = true;
      const form = new FormData();
      form.append("kind", kind); form.append("where", where.value); form.append("note", note.value.trim());
      form.append("checked", JSON.stringify(ticked()));
      if (shot) form.append("screenshot", shot, "screenshot");
      try { await ctx.api(`/api/jobs/${jobId}/rounds/${n}/report`, {method: "POST", body: form}); close(); retry = false; load(); }
      catch (error) { toast(error.message); send.disabled = false; }
    });
    const overlay = h("div", {class: "g-modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "report-title"},
      h("div", {class: "g-modal-box"}, h("h2", {id: "report-title"}, "어떤 문제가 있었나요?"), h("p", null, "적어 주신 내용으로 관련 코드를 찾아 드립니다."),
        h("div", {class: "g-field"}, h("span", null, "어떤 문제인가요?"), tags),
        h("label", {class: "g-field"}, h("span", null, "어디서 생겼나요?"), where),
        h("label", {class: "g-field"}, h("span", null, "자세히 적어 주세요 ", h("small", null, "(선택)")), note),
        h("div", {class: "g-field"}, h("span", null, "스크린샷 ", h("small", null, "(선택)")), drop),
        h("div", {class: "g-modal-foot"}, h("p", {class: "help"}, "기록은 이 작업 폴더에만 저장되고, 밖으로 보내지 않습니다."),
          h("button", {class: "btn ghost", type: "button", onclick: close}, "취소"), send)));
    overlay.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
    document.body.append(overlay);
    tags.querySelector("button")?.focus();
  }

  function reportedCard(play, active) {
    // The functions behind the place the problem was seen (the checklist item names its file and targets).
    const items = active.flatMap(r => r.play_checks || []);
    const hit = items.find(c => play.where === `${c.where || c.file.split("/").pop()} · ${c.action}`);
    // The result page shows the last stage: a check from an earlier stage says which one changed it.
    const stage = hit && active.findIndex(r => (r.play_checks || []).includes(hit)) + 1;
    const earlier = stage && stage < active.length;
    const undo = async () => {
      if (!await confirmDialog({title: "이 단계를 되돌릴까요?", body: "수정본이 이 단계 전으로 돌아갑니다. 기록과 파일은 지우지 않고 보관합니다.", ok: "되돌리기"})) return;
      try { await ctx.api(`/api/jobs/${jobId}/rounds/undo`, {method: "POST", body: "{}"}); toast("이 단계 전으로 되돌렸습니다."); location.hash = `#/job/${jobId}/result`; }
      catch (error) { toast(error.message); }
    };
    return h("section", {class: "card s-card f-report"}, h("div", {class: "s-q warn-text"}, "문제를 기록했습니다"), h("div", {class: "s-title"}, "어떻게 할까요?"),
      h("dl", null, h("dt", null, "문제"), h("dd", null, play.kind), h("dt", null, "어디서"), h("dd", null, play.where || "—"),
        play.note ? [h("dt", null, "메모"), h("dd", null, play.note)] : null, play.screenshot ? [h("dt", null, "스크린샷"), h("dd", null, "1장 첨부")] : null),
      hit ? h("p", {class: "help"}, `이 동작과 관련해 ${earlier ? `${stage}단계에서 ` : ""}바뀐 곳: ${hit.file}`, ...(hit.targets || []).map(t => [" ", h("code", {class: "cname"}, t)]),
        earlier ? ` (단계 결과 화면은 마지막 ${active.length}단계만 보여 줍니다. 이 단계를 되돌리고 확인하거나 수정본을 내려받아 비교해 주세요.)` : null) : null,
      h("div", {class: "s-links"}, earlier ? h("a", {class: "btn primary", href: `/revisions/${jobId}/${active[active.length - 1].revision}/modified-source.zip`}, "수정본 내려받기 (.zip)")
        : h("a", {class: "btn primary", href: `#/job/${jobId}/result`}, "바뀐 코드 전후 비교 보기"),
        h("button", {class: "btn ghost", type: "button", onclick: undo}, "이 단계 되돌리기"),
        h("button", {class: "btn ghost", type: "button", onclick: () => { retry = true; draw(); }}, "다시 해 보기")),
      h("p", {class: "help"}, "되돌리면 수정본이 이 단계 전으로 돌아갑니다. 기록과 파일은 지우지 않고 보관합니다."));
  }

  // ------------------------------------------------------------ done
  function done(job, active, tangle, play) {
    const cur = tangle.rounds.find(r => r.round === active.length);
    const excess = cur?.components.find(c => c.key === "complex_excess");
    const pct = excess && excess.before ? Math.round(100 * (excess.before - excess.after) / excess.before) : 0;
    // Each function from its first measure to its last, across the stages (100 → 60 → 30 shows 100 → 30).
    const across = new Map();
    for (const f of active.flatMap(r => r.comparison?.functions || [])) {
      const seen = across.get(f.name);
      across.set(f.name, {name: f.name, before: seen ? seen.before : f.before, after: f.after});
    }
    const functions = [...across.values()];
    // The function that got shortest by the most lines (the longest one may barely have moved).
    const longest = functions.filter(f => f.before && f.after && f.after.loc < f.before.loc).sort((a, b) => (b.before.loc - b.after.loc) - (a.before.loc - a.after.loc))[0];
    const when = new Date((active[active.length - 1].applied_at || Date.now() / 1000) * 1000).toLocaleDateString("ko-KR", {month: "long", day: "numeric"});
    const numbers = [...active.map(r => { const s = stageLine(r); return [s.title, s.what]; }),
      longest ? [`가장 많이 줄어든 함수 ${longest.name.split(".").pop()}`, `${fmt(longest.before.loc)} → ${fmt(longest.after.loc)}줄`] : null,
      pct > 0 ? ["매우 복잡한 부분", `−${pct}%`] : null].filter(Boolean);
    const okList = ["규칙 검사 통과", "원본은 그대로, 사본에 적용", data.game.available ? "빌드 성공" : "직접 빌드",
      play.checked?.length ? `직접 플레이 ${play.checked.length}가지 확인 · 정상` : "직접 플레이 · 정상"];
    const record = h("div", {class: "f-record", "aria-label": "정리 기록"},
      h("div", {class: "f-record-head"}, h("b", null, `정리 기록 · ${job.name}`), h("span", null, `${when} · ${active.length}단계`)),
      h("div", {class: "f-record-body"},
        h("div", null, h("h4", null, "무엇이 좋아졌나"), ...numbers.map(([k, v]) => h("div", {class: "f-num"}, h("span", null, k), h("b", null, v)))),
        h("div", null, h("h4", null, "어떻게 확인했나"), h("ul", {class: "f-ok-list"}, ...okList.map(t => h("li", null, t))))));
    const revision = active[active.length - 1].revision;
    const choice = (cls, title, sub, attrs) => h(attrs.href ? "a" : "button", {class: cls, ...(attrs.href ? {} : {type: "button"}), ...attrs}, h("b", null, title), h("small", null, sub));
    return [h("section", {class: "card f-hero"}, h("div", {class: "big", "aria-hidden": "true"}, "✓"),
        h("h1", null, "정리를 마쳤습니다"), h("p", null, `${job.name}의 동작은 그대로 두고 코드를 읽기 쉽게 정리했고, 빌드와 직접 플레이로 확인했습니다.`), record),
      h("section", {class: "card s-card"}, h("div", {class: "s-q"}, "이제 무엇을 할까요?"),
        h("div", {class: "f-next"},
          choice("main", "수정본 내려받기", "정리한 코드 전체(.zip)", {href: `/revisions/${jobId}/${revision}/modified-source.zip`}),
          choice("", "바뀐 코드 보기", "함수마다 전후 비교", {href: `#/job/${jobId}/result`}),
          choice("", "정리 기록 저장", "위 기록 카드를 이미지로 · 보고서·발표용", {onclick: () => saveRecord(job.name, when, numbers, okList)})),
        h("div", {class: "s-links"}, h("a", {class: "btn ghost sm", href: "#/"}, "다른 게임 분석하기"),
          h("button", {class: "btn ghost sm", type: "button", onclick: () => { retry = true; draw(); }}, "플레이 결과 다시 기록하기")))];
  }

  // The record card drawn on a canvas and saved as a PNG file.
  function saveRecord(name, when, numbers, okList) {
    const canvas = document.createElement("canvas");
    const w = 900, rowH = 34, hgt = 150 + Math.max(numbers.length, okList.length) * rowH + 40;
    canvas.width = w * 2; canvas.height = hgt * 2;
    const g = canvas.getContext("2d");
    g.scale(2, 2);
    g.fillStyle = "#ffffff"; g.fillRect(0, 0, w, hgt);
    g.fillStyle = "#1E7F4E"; g.font = "800 28px 'Pretendard', 'Malgun Gothic', sans-serif"; g.fillText("✓ 정리를 마쳤습니다", 36, 56);
    g.fillStyle = "#0F1B2D"; g.font = "700 18px 'Pretendard', 'Malgun Gothic', sans-serif"; g.fillText(`정리 기록 · ${name}`, 36, 94);
    g.fillStyle = "#6B7A90"; g.font = "500 14px 'Pretendard', 'Malgun Gothic', sans-serif"; g.fillText(`${when} · G-SI 게임 코드 스파게티 분석기`, 36, 118);
    g.font = "700 13px 'Pretendard', 'Malgun Gothic', sans-serif"; g.fillText("무엇이 좋아졌나", 36, 150); g.fillText("어떻게 확인했나", 520, 150);
    numbers.forEach(([k, v], i) => {
      const y = 180 + i * rowH;
      g.fillStyle = "#33445C"; g.font = "500 15px 'Pretendard', 'Malgun Gothic', sans-serif"; g.fillText(k, 36, y);
      g.fillStyle = "#1E7F4E"; g.font = "800 15px 'Pretendard', 'Malgun Gothic', sans-serif"; g.textAlign = "right"; g.fillText(v, 480, y); g.textAlign = "left";
    });
    okList.forEach((t, i) => { g.fillStyle = "#1E7F4E"; g.font = "700 15px 'Pretendard', 'Malgun Gothic', sans-serif"; g.fillText(`✓ ${t}`, 520, 180 + i * rowH); });
    canvas.toBlob(blob => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = `정리기록-${name}.png`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
  }

  await load();
  return () => { alive = false; clearTimeout(timer); closeReport?.(); };
}
