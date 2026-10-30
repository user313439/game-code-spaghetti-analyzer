import {changeText, elapsedText, functionChanges, resultHeadline, safetyBadges, splitSummary, unitDisplay} from "./core.js";
import {diffView} from "./diff.js";
import {METHODS} from "./prescription.js";
import {confirmDialog, fill, h, notice, progressBlock, toast} from "./ui.js";

const MAX_STAGES = 3;

const APPLY_STAGES = ["사본 만들기", "다시 분석", "전후 비교", "정리"];
const KEYS = [["cycle_units", "순환 고리에 묶인"], ["links", "사이 연결선"], ["complex_excess", "매우 복잡한 부분 Σ(CC−20)"], ["excess_complexity", "초과 복잡도 Σ(CC−10)"]];
const SHOWN_FUNCTIONS = 6;   // other changed functions listed before "더 보기"

function value(round, key) { return round.components.find(c => c.key === key)?.after ?? 0; }

// Before/after bars on one scale (max = the longest bar in the group).
function pairBars(before, after, max, mini = false) {
  const bar = (cls, v, key) => {
    const fillBar = h("span"); fillBar.style.width = `${v ? Math.max(2, 100 * v / max) : 0}%`;
    return h("div", {class: `pb ${cls}`}, mini ? null : h("span", {class: "pb-k"}, key), h("div", {class: "pb-t"}, fillBar));
  };
  return h("div", {class: `pbars ${mini ? "mini" : ""}`, "aria-hidden": "true"},
    before === null ? null : bar("was", before, "전"),
    after === null ? null : bar(after < (before ?? after) ? "now good" : after > (before ?? after) ? "now worse" : "now", after, "후"));
}

function delta(before, after, unit = "") {
  return after === before ? h("span", {class: "delta same"}, "변화 없음")
    : h("span", {class: `delta ${after < before ? "down" : "up"}`}, changeText(before, after, unit));
}

// One measure of the highlighted function (or of the links between units): big numbers, change, bars.
function metric(title, before, after, unit = "") {
  return h("div", {class: "fix-metric"}, h("span", {class: "fix-k"}, title),
    h("div", {class: "fix-num"}, h("s", null, `${before.toLocaleString()} →`),
      h("b", {class: after < before ? "good-text" : ""}, `${after.toLocaleString()}${unit}`), delta(before, after, unit)),
    pairBars(before, after, Math.max(before, after, 1)));
}

const fmt = v => v.toLocaleString();
const fmtAvg = v => Number(v).toLocaleString(undefined, {maximumFractionDigits: 1});   // an average: one decimal at most

// "코드가 이렇게 바뀌었습니다": each changed function's code before and after, the most reduced first.
function codeView(list) {
  if (!list?.length) return null;
  const view = h("div", {class: "code-view"});
  const tabs = h("div", {class: "code-tabs", role: "tablist", "aria-label": "바뀐 함수"});
  const name = row => row.name || row.file.split("/").pop();
  const label = row => row.created ? `${name(row)} · 새 함수` : row.removed ? `${name(row)} · 삭제`
    : row.before && row.after ? `${name(row)} · ${row.before.cc} → ${row.after.cc}` : name(row);
  const show = row => {
    tabs.querySelectorAll("button").forEach((b, i) => { const on = list[i] === row; b.classList.toggle("on", on); b.setAttribute("aria-selected", String(on)); });
    fill(view, h("div", {class: "dhead"}, h("b", {class: "mono"}, name(row)), h("span", {class: "sub"}, row.file),
      row.before && row.after ? h("span", {class: "push sub"}, `복잡도 ${row.before.cc} → ${row.after.cc} · 길이 ${row.before.loc} → ${row.after.loc}줄`) : null),
      diffView({diff: row.diff}));
  };
  list.forEach(row => tabs.append(h("button", {type: "button", role: "tab", class: "chip", onclick: () => show(row)}, label(row))));
  show(list[0]);
  return h("div", {class: "fix-code"}, h("div", {class: "fix-sub"}, "코드가 이렇게 바뀌었습니다"),
    h("p", {class: "help"}, "왼쪽은 원래 코드, 오른쪽은 고친 뒤입니다. 새로 만든 함수는 오른쪽에만 있습니다. 함수 이름을 누르면 바꿔 볼 수 있습니다."),
    tabs, view);
}

function owner(row) { return unitDisplay(row.name.length > row.short.length ? row.name.slice(0, row.name.length - row.short.length - 1) : ""); }

export async function render(view, ctx, {jobId}) {
  const root = h("section", {class: "wrap wide"}, h("p", {class: "empty"}, "수정 결과를 불러오고 있습니다."));
  view.append(root);
  ctx.setSteps(jobId, 3, {refactor: true, result: true});
  let alive = true, timer = null, shown = "";
  const progress = progressBlock(APPLY_STAGES);

  async function load() {
    try {
      const [job, state, rounds, tangle, game, diag, presc] = await Promise.all([ctx.api(`/api/jobs/${jobId}`), ctx.api(`/api/jobs/${jobId}/assistant`),
        ctx.api(`/api/jobs/${jobId}/rounds`), ctx.api(`/api/jobs/${jobId}/tangle`), ctx.api(`/api/jobs/${jobId}/demo`), ctx.api(`/api/jobs/${jobId}/diagnosis`),
        ctx.api(`/api/jobs/${jobId}/prescription`).catch(() => ({state: "unknown"}))]);
      ctx.setCrumb(job.name);
      // The changed functions' code: which new helpers each original function now calls.
      const changes = rounds.current ? await ctx.api(`/api/jobs/${jobId}/rounds/${rounds.current}/changes`).catch(() => ({functions: []})) : {functions: []};
      draw({state, rounds, tangle, game, label: diag.summary.unit_label, presc, code: changes?.functions || []});
    } catch (error) {
      if (!alive) return;
      // While applying, a missed poll is retried; otherwise offer a manual retry.
      if (shown === "applying") { clearTimeout(timer); timer = setTimeout(() => alive && load(), 1500); return; }
      fill(root, notice(error.message), h("button", {class: "btn ghost", type: "button", onclick: load}, "다시 불러오기"));
    }
  }

  function applying(state) {
    const p = state.progress || {};
    progress.update({step: Math.min(3, p.step || 0), total: 4, text: p.label || "", indeterminate: p.indeterminate,
      elapsed: state.started_at ? elapsedText(Date.now() / 1000 - state.started_at) : ""});
    if (shown !== "applying") {
      fill(root, h("div", {class: "card running"}, h("div", {class: "eyebrow"}, "변경안 적용 중"),
        h("h2", {class: "h2"}, "원본은 그대로 두고 사본에 적용한 뒤 다시 분석하고 있습니다"), progress.el));
      shown = "applying";
    }
    clearTimeout(timer); timer = setTimeout(() => alive && load(), 1000);
  }

  function draw({state, rounds, tangle, game, label, presc = {state: "idle"}, code = []}) {
    if (!alive) return;
    if (state.state === "running" && state.action === "apply") { applying(state); return; }
    shown = "result";
    // The last apply may have failed after earlier rounds succeeded: say so above the last good round.
    const failedApply = state.action === "apply" && ["failed", "interrupted"].includes(state.state);
    if (!rounds.current) {
      fill(root, h("div", {class: "card running"}, h("div", {class: "eyebrow"}, "수정 결과"), h("h2", {class: "h2"}, "아직 적용한 수정이 없습니다"),
        failedApply ? notice(`변경안을 적용하지 못했습니다. ${state.error || ""}`) : null,
        h("p", {class: "sub"}, "엉킴 진단에서 AI 처방을 받고 변경안을 적용하면 여기에서 결과를 확인할 수 있습니다."),
        h("div", {class: "actions"}, h("a", {class: "btn primary", href: `#/job/${jobId}/diagnosis`}, "엉킴 진단으로 →"))));
      return;
    }
    const n = rounds.current, round = rounds.rounds[n - 1];
    const active = tangle.rounds.filter(r => r.active);
    const cur = tangle.rounds.find(r => r.round === n), prev = tangle.rounds.find(r => r.round === n - 1);
    const comp = round.comparison || {before: [], after: [], functions: []};
    const changes = functionChanges(comp.functions || []);
    const cycle = [value(prev, "cycle_units"), value(cur, "cycle_units")], links = [value(prev, "links"), value(cur, "links")];
    const checks = round.checks || {};
    const built = game.available && game.state === "complete" && game.revision === round.revision;
    const head = resultHeadline(changes, {label, cycle, links});

    // 1. What changed where the code was fixed: the most reduced function large, the others as a list.
    const top = changes.top, rest = changes.rows.filter(r => r !== top);
    const scale = Math.max(1, ...changes.rows.flatMap(r => [r.before?.cc || 0, r.after?.cc || 0]));
    const otherRow = r => {
      const b = r.before, a = r.after;
      const tag = r.kind === "new" ? h("span", {class: "tag new"}, "새로 만든 함수") : r.kind === "removed" ? h("span", {class: "tag keep"}, "삭제")
        : r.kind === "worse" ? h("span", {class: "tag worse"}, "복잡도 늘어남") : null;
      const numbers = b && a ? `복잡도 ${fmt(b.cc)} → ${fmt(a.cc)} · 길이 ${fmt(b.loc)} → ${fmt(a.loc)}줄` : `복잡도 ${fmt((a || b).cc)} · ${fmt((a || b).loc)}줄`;
      return h("li", {class: `fix-row ${r.kind}`}, h("div", {class: "fix-row-name"}, h("b", {class: "mono", title: r.name}, r.short), tag),
        pairBars(b ? b.cc : null, a ? a.cc : null, scale, true), h("span", {class: "fix-row-num"}, numbers),
        b && a ? (r.kind === "shorter" ? delta(b.loc, a.loc, "줄") : delta(b.cc, a.cc)) : h("span", {class: "delta"}));
    };
    const structure = cycle[1] < cycle[0] || links[1] < links[0] || !changes.rows.length
      ? h("div", {class: `fix-links ${top ? "secondary" : ""}`}, h("div", {class: "fix-sub"}, `${label} 사이 연결 구조 (${n > 1 ? `${n - 1}라운드` : "처음 상태"}와 비교)`),
        h("div", {class: "fix-metrics"}, metric(`순환 고리에 묶인 ${label}`, cycle[0], cycle[1], "개"), metric(`${label} 사이 연결`, links[0], links[1], "개")))
      : null;
    const totals = changes.totals, totalChange = totals.cc[0] ? changeText(totals.cc[0], totals.cc[1]) : "";
    // The code of the changed functions arrives separately (it can be large) and fills in below.
    const codeSlot = h("div", null, codeView(code));
    const hero = h("section", {class: "card fix", "aria-label": "고친 곳의 변화"},
      h("div", {class: "fix-head"}, h("div", {class: "eyebrow"}, "고친 곳의 변화"), h("span", {class: "help"}, "AI 설명이 아니라 수정본을 다시 분석해 측정한 값입니다.")),
      top ? h("div", {class: "fix-top"},
        h("div", {class: "fix-name"}, h("span", {class: "chip good"}, top.kind === "simpler" ? "복잡도가 가장 크게 줄어든 함수" : "길이가 가장 크게 줄어든 함수"),
          h("b", {class: "mono"}, top.short), owner(top) ? h("span", {class: "help mono"}, owner(top)) : null),
        h("div", {class: "fix-metrics"}, metric("복잡도(CC)", top.before.cc, top.after.cc), metric("길이", top.before.loc, top.after.loc, "줄"))) : null,
      rest.length ? h("div", {class: "fix-others"}, h("div", {class: "fix-sub"}, top ? `함께 바뀐 함수 ${rest.length}개` : `바뀐 함수 ${rest.length}개`),
        h("ul", {class: "fix-list"}, ...rest.slice(0, SHOWN_FUNCTIONS).map(otherRow)),
        rest.length > SHOWN_FUNCTIONS ? h("details", {class: "parts"}, h("summary", null, `함수 ${rest.length - SHOWN_FUNCTIONS}개 더 보기`),
          h("ul", {class: "fix-list"}, ...rest.slice(SHOWN_FUNCTIONS).map(otherRow))) : null) : null,
      changes.rows.length > 1 ? h("p", {class: "fix-total"}, h("b", null, `바뀐 함수 ${changes.rows.length}개를 모두 합치면`),
        ` 복잡도 ${fmt(totals.cc[0])} → ${fmt(totals.cc[1])}${totalChange ? ` (${totalChange})` : ""}`,
        ` · 길이 ${fmt(totals.loc[0])} → ${fmt(totals.loc[1])}줄`, changes.counts.new ? h("span", {class: "help"}, "새로 만든 함수로 옮겨 간 복잡도까지 더한 값입니다.") : null) : null,
      structure, codeSlot);

    // 2. Safety: short badges up here, the details folded. Building and playing happen on the finishing page.
    const check = (ok, title, text, more) => h("div", {class: "check"}, h("span", {class: `ok ${ok ? "" : "todo"}`}, ok ? "✓" : "·"),
      h("div", null, h("b", null, title), h("p", null, text), more ? h("details", null, h("summary", null, "자세히"), more) : null));
    const re = checks.reanalyzed || {};
    const checkList = h("div", {class: "checks"},
      round.migrated ? h("p", {class: "help"}, "이 라운드는 라운드 기록을 남기기 전에 적용한 수정본이라 원본 보존·승인한 변경과 동일·다시 분석 확인 기록이 없습니다.") : null,
      check(true, "검사 규칙 통과", "AI 변경안은 프로그램 검사를 통과해야 검토 화면에 나오고 적용할 수 있습니다.",
        "설명한 범위만 바뀌었는지 검사하고, 함수 본문을 바꾸지 않는 연결 정리는 문법 트리로 다시 확인합니다. 통과하지 못한 응답은 적용할 수 없습니다."),
      check(checks.original_preserved, "원본 보존", "원본 소스는 그대로 두고 사본에만 적용했습니다.", "적용 전후에 파일마다 지문(SHA-256)을 비교했습니다."),
      check(checks.matches_preview, "승인한 변경과 동일", "적용된 파일이 검토 화면에서 본 변경안과 정확히 같습니다.", `대상·함께 수정·새 파일 ${round.files.length}개`),
      check(["complete", "partial"].includes(re.state), "다시 분석", `수정본 파일 ${re.analyzed_files ?? "?"}개를 처음과 같은 기준으로 다시 분석했습니다.`,
        re.syntax_files ? `일부 문법을 건너뛴 파일 ${re.syntax_files}개는 처음과 같은 방식으로 분석했습니다.` : null),
      game.available ? check(built, "빌드", built ? "수정된 게임을 빌드했습니다." : "오른쪽 게임 카드에서 수정된 게임을 준비하면 빌드를 확인합니다.")
        : check(false, "빌드", "이 프로젝트에는 등록된 빌드 절차가 없습니다. 개발 환경에서 직접 빌드해 확인해 주세요."),
      game.available ? check(built && game.behavior_checked, "동작 비교", game.verification_summary || "게임을 준비한 뒤 원본과 수정본의 동작 비교 기록을 표시합니다.") : null,
      check(checks.play?.ok, "직접 플레이", checks.play ? (checks.play.ok ? "수정된 게임을 직접 해 보고 정상이라고 확인했습니다." : "직접 해 보니 문제가 있었다고 기록했습니다.")
          : "정리를 마무리할 때 빌드한 게임을 직접 해 보고 기록합니다.",
        checks.play?.at ? `${new Date(checks.play.at * 1000).toLocaleString("ko-KR")} 기록` : null));
    const mark = {ok: ["✓", "완료"], todo: ["·", "아직"], bad: ["✕", "문제"]};
    const safety = h("section", {class: "card safety", "aria-label": "안전 확인"},
      h("div", {class: "safety-head"}, h("b", null, "안전 확인"), h("span", {class: "help"}, "검사 규칙을 통과하고 승인한 변경만, 원본이 아닌 사본에 적용했습니다.")),
      h("ul", {class: "badges"}, ...safetyBadges(round, game).map(b => h("li", {class: `badge is-${b.state}`},
        h("i", {"aria-hidden": "true"}, mark[b.state][0]), h("span", {class: "visually-hidden"}, `${mark[b.state][1]}: `), b.label, b.note ? h("small", null, ` ${b.note}`) : null))),
      h("details", {class: "parts safety-more"}, h("summary", null, "확인 내용 자세히 보기"), checkList));

    const stat = (key, title) => {
      const a = value(prev, key), b = value(cur, key), d = b - a;
      return h("div", {class: `card stat ${d ? "" : "dim"}`}, h("span", null, key === "cycle_units" ? `순환 고리에 묶인 ${label}` : key === "links" ? `${label} 사이 연결선` : title),
        h("div", {class: "pair"}, h("s", null, `${a.toLocaleString()} →`), h("b", {class: d < 0 ? "good-text" : ""}, b.toLocaleString())),
        h("span", {class: d < 0 ? "good-text strong" : "muted"}, d ? `${d > 0 ? "+" : ""}${d.toLocaleString()}` : "변화 없음"));
    };
    const chartMax = Math.max(...active.map(r => r.index), 100);
    const chart = h("div", {class: "rounds"}, ...active.map(r => {
      const fillBar = h("span"); fillBar.style.height = `${Math.max(4, 100 * r.index / chartMax)}%`;
      return h("div", {class: `rbar ${r.round === n ? "on" : ""}`}, h("b", null, r.index.toFixed(r.index % 1 ? 2 : 0)), h("div", {class: "rcol"}, fillBar), h("span", null, r.round ? `${r.round}라운드` : "처음"));
    }));

    // Keyed by unit (fqn): one C# file can hold several classes.
    const unitKey = c => c.fqn || c.file_path;
    const before = new Map((comp.before || []).map(c => [unitKey(c), c]));
    const unitName = a => label === "파일" || !a.fqn ? h("b", null, a.file_path) : [h("b", null, a.fqn), h("br"), h("span", {class: "help"}, a.file_path)];
    const fileTable = h("table", {class: "tbl"}, h("thead", null, h("tr", null, ...[label, "G-SI", "복잡도(CC) · 복잡한 함수 상위 10% 평균", "연결", "순환 고리 연결"].map(t => h("th", null, t)))),
      h("tbody", null, ...(comp.after || []).map(a => { const b = before.get(unitKey(a)) || a; return h("tr", null, h("td", null, unitName(a)),
        h("td", null, `${b.si} → ${a.si}`), h("td", null, `${fmtAvg(b.raw.cc)} → `, h("b", {class: a.raw.cc < b.raw.cc ? "good-text" : ""}, fmtAvg(a.raw.cc))),
        h("td", null, `${b.raw.coupling} → `, h("b", {class: a.raw.coupling < b.raw.coupling ? "good-text" : ""}, a.raw.coupling)),
        h("td", null, `${b.raw.dependency_cycle} → `, h("b", {class: a.raw.dependency_cycle < b.raw.dependency_cycle ? "good-text" : ""}, a.raw.dependency_cycle))); })));

    const parts = h("details", {class: "parts"}, h("summary", null, "엉킴 총량 구성 보기"),
      h("table", {class: "tbl"}, h("thead", null, h("tr", null, ...["항목", "처음", `${n}라운드`, ""].map(t => h("th", null, t)))),
        h("tbody", null, ...cur.components.map(c => h("tr", {class: c.included ? "" : "muted"}, h("td", null, c.label.replace("단위", label)),
          h("td", null, c.before.toLocaleString()), h("td", null, h("b", {class: c.after < c.before ? "good-text" : ""}, c.after.toLocaleString())),
          h("td", {class: "help"}, c.included ? "" : "처음 값이 0이라 계산에서 뺍니다"))))));
    // 3. The whole game's tangle total: an auxiliary measure that barely moves in one round.
    const whole = h("section", {class: "card sec aux", "aria-label": "게임 전체 기준 보조 지표"},
      h("div", {class: "aux-head"}, h("div", {class: "h3"}, "게임 전체 기준 보조 지표"),
        h("p", {class: "help"}, "게임 전체의 절대량이라 한 라운드에 보통 2% 미만 움직입니다. 고친 곳의 변화는 위 카드에서 봅니다.")),
      h("div", {class: "tangle"}, h("div", null, h("div", {class: "eyebrow"}, "엉킴 총량 · 처음 상태 = 100"),
        h("div", {class: "big-index"}, h("s", null, "100 →"), h("b", null, cur.index.toFixed(cur.index % 1 ? 2 : 0))),
        h("p", {class: "help"}, "순환 고리·연결·매우 복잡한 부분·초과 복잡도·전역 변수 접근을 처음 상태와 비교한 값입니다."),
        cur.same_units ? null : h("p", {class: "chip warn"}, `⚠ 분석된 ${label} 구성이 처음과 달라(추가·삭제) 총량을 그대로 비교하기 어렵습니다`),
        parts), chart),
      // The total above compares with the first analysis; these four compare with the round before.
      h("p", {class: "help sum-note"}, `아래 네 값은 ${n > 1 ? `${n - 1}라운드` : "처음 상태"}와 비교한 이번 ${n}라운드의 게임 전체 값입니다.`),
      h("div", {class: "sum"}, ...KEYS.map(([key, title]) => stat(key, title))));

    // A round that split functions reads top to bottom in plain words; the measured details fold below.
    const split = splitSummary(code);
    lastWay = (round.method || (split.helpers.length ? "functions" : "declarations")) === "declarations" ? "link" : "internal";
    const scores = h("div", {class: "card sec"}, h("div", {class: "h2"}, `${label} 점수`), h("p", {class: "help"}, `G-SI는 프로젝트 안에서의 순위라서, 다른 ${label === "파일" ? "파일과" : "클래스와"} 비교한 위치가 같으면 그대로입니다.`),
      h("div", {class: "tbl-scroll"}, fileTable));
    const tools = h("div", {class: "s-links"},
      h("a", {class: "btn ghost sm", href: `/revisions/${jobId}/${round.revision}/modified-source.zip`}, "수정본 내려받기 (.zip)"),
      h("button", {class: "btn ghost sm", type: "button", onclick: undo}, "이 단계 되돌리기"));
    const detail = h("details", {class: "card s-detail"}, h("summary", null, "자세히 보기 ", h("small", null, "고친 함수의 코드와 측정값, 안전 확인")),
      split.helpers.length ? hero : null, safety, scores, whole, tools);
    // Only helpers found under an original function make the plain-words page (one that is never called
    // from a changed function, e.g. a call the search did not recognise, is left to the details).
    const body = split.targets.length ? [splitHead(split, n, round), effectsCard(split), shorterCard(split), exampleCard(split), detail]
      : [h("div", {class: "page-head"}, h("div", null, h("div", {class: "eyebrow"}, `수정 결과 · ${n}단계 · ${METHODS[lastWay].name}`),
          h("h1", {class: "h1"}, head.title), h("p", {class: "sub"}, head.lines.join(" ")), safeChips(round))), hero, detail];
    fill(root,
      failedApply ? notice(`마지막 변경안을 적용하지 못했습니다. ${state.error || ""} 아래는 그 전까지 적용된 결과입니다.`) : null,
      h("div", {class: "s-wrap"}, ...body, nextCard(n, presc, Boolean(state.next_pending) || presc.state === "running")));
    // The next stage's prescription is asked for by itself after applying: show it when it arrives.
    // The next stage's prescription is about to start, running, or could not be read: look again shortly.
    if (waiting(state, presc)) { clearTimeout(timer); timer = setTimeout(() => alive && load(), 2000); }
  }

  const waiting = (state, presc) => Boolean(state.next_pending) || ["running", "unknown"].includes(presc.state);
  const fmtN = v => Number(v).toLocaleString("ko-KR");
  const base = p => String(p).split("/").pop();
  function safeChips(round) {
    const re = (round.checks || {}).reanalyzed || {};
    return h("div", {class: "g-safe"}, h("span", null, "✓ 규칙 검사 통과"), round.checks?.original_preserved ? h("span", null, "✓ 원본은 그대로") : null,
      ["complete", "partial"].includes(re.state) ? h("span", null, "✓ 같은 기준으로 다시 분석") : null);
  }
  function splitHead(s, n, round) {
    const files = new Set(s.targets.map(t => t.file)).size;
    return h("header", {class: "s-head"}, h("div", {class: "eyebrow"}, `수정 결과 · ${n}단계 · 함수 나누기`),
      h("h1", null, "큰 함수 ", h("em", null, `${s.targets.length}개`), "를 작은 함수 ", h("em", null, `${s.helpers.length}개`), "로 나눴습니다"),
      h("p", null, `파일 ${files}개. 게임이 하는 일은 그대로 두고, 한 함수에 몰려 있던 코드를 이름 붙은 작은 함수로 옮겼습니다.`), safeChips(round));
  }
  function effectsCard(s) {
    const effect = (icon, title, ...text) => h("div", {class: "s-effect"}, h("div", {class: "ic", "aria-hidden": "true"}, icon), h("b", null, title), h("p", null, ...text));
    return h("section", {class: "card s-card"}, h("div", {class: "s-q"}, "이번 단계로 이렇게 좋아졌습니다"),
      h("div", {class: "s-title"}, "한 함수가 혼자 하던 여러 일을, 일마다 따로 맡겼습니다"),
      h("div", {class: "s-effects"},
        effect("🔍", "고칠 곳을 찾기 쉬워졌습니다", "기능 하나를 고치려고 ", h("strong", null, `${fmtN(s.longest.before.loc)}줄`), "짜리 ", h("code", {class: "mono"}, s.longest.name),
          " 함수를 다 읽는 대신, 평균 ", h("strong", null, `${s.avgLoc}줄`), "짜리 작은 함수 하나를 보면 됩니다."),
        effect("🏷️", "함수 이름으로 찾아갈 수 있습니다", "나눈 일 ", h("strong", null, `${s.helpers.length}가지`), "에 각각 이름을 붙였습니다.",
          s.example ? [" 예를 들어 이 일을 고치려면 ", h("code", {class: "mono"}, s.example.name), " 함수를 찾으면 됩니다."] : null),
        effect("🧩", "고친 뒤 확인할 범위가 좁아졌습니다", `작은 함수 ${s.helpers.length}개 중 `, h("strong", null, `${s.simple}개`), "는 갈림길(if·for·switch)이 20개 이하라 한눈에 읽힙니다.")),
      h("p", {class: "s-small"}, "게임 동작은 바꾸지 않았습니다. 버그를 고친 것이 아니라, 다음에 기능을 고치거나 더할 때의 출발점을 분명하게 만든 것입니다."));
  }
  function shorterCard(s) {
    const bar = (cls, width, key) => { const span = h("span"); span.style.width = `${width}%`; return h("div", {class: `s-bar ${cls}`}, h("em", null, key), h("div", null, span)); };
    const row = t => h("li", null, h("div", {class: "s-func-top"}, h("b", {class: "mono"}, t.name),
        h("span", null, `${fmtN(t.before.loc)}줄 → `, h("strong", null, `${fmtN(t.after.loc)}줄`), ` · 작은 함수 ${t.helpers.length}개로 나뉨`)),
      bar("", 100, "전"), bar("after", 100 * t.after.loc / Math.max(1, t.before.loc), "후"));
    return h("section", {class: "card s-card"}, h("div", {class: "s-q"}, "원래 함수는 얼마나 짧아졌나요?"), h("div", {class: "s-title"}, "한 번에 읽어야 하는 양이 줄었습니다"),
      h("ul", {class: "s-funcs"}, ...s.targets.slice(0, 3).map(row)),
      s.targets.length > 3 ? h("details", {class: "s-more"}, h("summary", null, `나머지 ${s.targets.length - 3}개 함수 보기`), h("ul", {class: "s-funcs"}, ...s.targets.slice(3).map(row))) : null);
  }
  function exampleCard(s) {
    const x = s.example;
    if (!x) return null;
    return h("section", {class: "card s-card"}, h("div", {class: "s-q"}, "예를 들어"), h("div", {class: "s-title"}, h("span", {class: "mono"}, x.name), " 함수가 맡은 일을 고치고 싶다면"),
      h("div", {class: "s-ex"},
        h("div", {class: "s-box"}, h("h3", null, "정리 전"), h("div", {class: "n"}, `${fmtN(s.longest.before.loc)}줄`),
          h("p", null, h("code", {class: "mono"}, s.longest.name), " 함수 전체를 읽으며 찾아야 했습니다.")),
        h("div", {class: "s-ex-arrow", "aria-hidden": "true"}, "→"),
        h("div", {class: "s-box after"}, h("h3", null, "정리 후"), h("div", {class: "n"}, `${fmtN(x.after.loc)}줄`),
          h("p", null, h("code", {class: "mono"}, x.name), ` 함수만 보면 됩니다. (${base(x.file)})`))));
  }
  // The last card: the next stage the AI proposes, or the way to building and playing.
  function nextCard(n, presc, pending) {
    const finish = text => h("a", {class: "btn primary", href: `#/job/${jobId}/finish`}, text);
    const end = (title, text) => h("section", {class: "card g-next is-end", "aria-label": "다음 단계"}, h("div", {class: "s-q"}, "정리는 여기까지입니다"),
      h("div", {class: "s-title"}, title), h("p", null, text), h("div", {class: "g-btns"}, finish("빌드하고 플레이해 보기 →")));
    if (n >= MAX_STAGES) return end("이제 게임을 빌드하고 직접 해 볼 차례입니다", `최대 ${MAX_STAGES}단계까지 정리했습니다. 단계를 더 하면 원래 동작과 달라질 위험이 커집니다.`);
    const r = presc.result, fresh = r && !presc.stale && (r.stage || 0) === n + 1;
    const card = (...children) => h("section", {class: "card g-next", "aria-label": "다음 단계"}, h("div", {class: "s-q"}, "다음 단계"), ...children);
    if (pending) return card(h("div", {class: "s-title"}, "AI가 이번 결과를 보고 다음 단계를 정하고 있습니다"),
      h("p", null, "잠시 뒤 더 정리할 곳이 있는지 여기에 알려 드립니다. 지금 마무리해도 됩니다."),
      h("div", {class: "g-btns"}, h("a", {class: "btn ghost", href: `#/job/${jobId}/finish`}, "여기서 마무리")));
    if (fresh && (r.done || !r.files.length)) return end("이제 게임을 빌드하고 직접 해 볼 차례입니다",
      "AI가 이번 결과를 다시 보고, 더 나눠도 효과가 작다고 판단했습니다.");
    if (fresh) {
      const kinds = [...new Set(r.files.map(f => f.kind))], way = kinds.length > 1 ? r.first || "internal" : kinds[0];
      const files = r.files.filter(f => f.kind === way);
      const names = files.flatMap(f => f.targets?.length ? f.targets : [f.name]).slice(0, 4);
      return card(h("div", {class: "s-title"}, `${METHODS[way].name}를 ${way === lastWay ? "한 번 더 " : ""}하면 더 좋아질 수 있습니다`),
        h("p", null, ...names.flatMap((t, i) => [i ? ", " : "", h("code", {class: "cname"}, t)]), ` 등 ${files.length}개 파일을 더 정리할 수 있다고 AI가 판단했습니다.`),
        h("p", {class: "help"}, `[${n + 1}단계 진행]은 처방 화면으로 돌아가 다음 단계를 시작합니다. [여기서 마무리]는 정리를 끝내고 빌드·직접 플레이로 넘어갑니다.`),
        h("div", {class: "g-btns"}, h("a", {class: "btn ghost", href: `#/job/${jobId}/finish`}, "여기서 마무리"),
          h("a", {class: "btn primary", href: `#/job/${jobId}/diagnosis`}, `${n + 1}단계 진행 →`)));
    }
    // No judgement yet (an API key is never kept, or the request failed): the user decides.
    return card(h("div", {class: "s-title"}, "다음 단계가 필요한지 AI에게 물어볼 수 있습니다"),
      h("p", null, presc.state === "failed" ? `다음 단계 판단을 받지 못했습니다. ${presc.error || ""}` : "처방 화면에서 이번 결과를 기준으로 다음 처방을 받을 수 있습니다."),
      h("div", {class: "g-btns"}, h("a", {class: "btn ghost", href: `#/job/${jobId}/finish`}, "여기서 마무리"),
        h("a", {class: "btn primary", href: `#/job/${jobId}/diagnosis`}, "다음 처방 받기 →")));
  }
  let lastWay = "internal";   // how the shown round changed the code: the next stage may do the same once more

  async function undo() {
    if (!await confirmDialog({title: "이 단계를 되돌릴까요?", body: "현재 수정본이 이 단계 전으로 돌아갑니다. 기록과 파일은 지우지 않고 보관합니다.", ok: "되돌리기"})) return;
    try { await ctx.api(`/api/jobs/${jobId}/rounds/undo`, {method: "POST", body: "{}"}); toast("이 단계 전으로 되돌렸습니다."); load(); }
    catch (error) { toast(error.message); }
  }

  await load();
  return () => { alive = false; clearTimeout(timer); };
}
