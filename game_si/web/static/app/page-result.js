import {elapsedText, subj} from "./core.js";
import {confirmDialog, fill, h, notice, progressBlock, toast} from "./ui.js";

const APPLY_STAGES = ["사본 만들기", "다시 분석", "전후 비교", "정리"];
const KEYS = [["cycle_units", "순환 고리에 묶인"], ["links", "사이 연결선"], ["complex_functions", "매우 복잡한 함수 (CC>20)"], ["excess_complexity", "초과 복잡도 Σ(CC−10)"]];

function value(round, key) { return round.components.find(c => c.key === key)?.after ?? 0; }

export async function render(view, ctx, {jobId}) {
  const root = h("section", {class: "wrap wide"}, h("p", {class: "empty"}, "수정 결과를 불러오고 있습니다."));
  view.append(root);
  ctx.setSteps(jobId, 3, {refactor: true, result: true});
  let alive = true, timer = null, gameTimer = null, watcher = 0, shown = "";
  const progress = progressBlock(APPLY_STAGES);

  async function load() {
    try {
      const [job, state, rounds, tangle, game, diag] = await Promise.all([ctx.api(`/api/jobs/${jobId}`), ctx.api(`/api/jobs/${jobId}/assistant`),
        ctx.api(`/api/jobs/${jobId}/rounds`), ctx.api(`/api/jobs/${jobId}/tangle`), ctx.api(`/api/jobs/${jobId}/demo`), ctx.api(`/api/jobs/${jobId}/diagnosis`)]);
      ctx.setCrumb(job.name);
      draw({state, rounds, tangle, game, label: diag.summary.unit_label});
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

  function draw({state, rounds, tangle, game, label}) {
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
    const fns = comp.functions || [];
    const simpler = fns.filter(f => f.before && f.after && f.after.cc < f.before.cc);
    const cycle = [value(prev, "cycle_units"), value(cur, "cycle_units")], links = [value(prev, "links"), value(cur, "links")];
    const checks = round.checks || {};
    const built = game.available && game.state === "complete" && game.revision === round.revision;
    // A play result can be recorded once the modified game exists: built here, or built by the user
    // in their own environment when no demo game is registered for this project.
    const canRecordPlay = !game.available || built;
    const tail = checks.play?.ok ? " 게임도 그대로 잘 동작합니다." : built ? " 게임 빌드도 통과했습니다." : "";
    const lead = cycle[1] < cycle[0] ? `순환 고리에 묶인 ${subj(label)} ${cycle[0]} → ${cycle[1]}개로 줄었습니다.`
      : links[1] < links[0] ? `${label} 사이 연결이 ${links[0]} → ${links[1]}개로 줄었습니다.`
      : simpler.length ? `함수 ${simpler.length}개가 단순해졌습니다.` : "코드를 정리했습니다.";
    const subline = cycle[1] < cycle[0] || links[1] < links[0]
      ? `${label} 사이의 연결이 끊어져, 한 곳을 고칠 때 영향이 퍼지는 범위가 좁아졌습니다.`
      : `이번 수정은 ${label} 안을 정리한 것이라 ${label} 사이의 연결과 순환 고리는 그대로입니다.`;

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

    const fnTable = h("table", {class: "tbl"}, h("thead", null, h("tr", null, ...["함수", "복잡도 (CC)", "길이", ""].map(t => h("th", null, t)))),
      h("tbody", null, ...fns.map(f => h("tr", null, h("td", {class: "mono"}, f.name),
        h("td", null, f.before ? `${f.before.cc} → ` : "", h("b", {class: f.before && f.after && f.after.cc < f.before.cc ? "good-text" : ""}, f.after ? f.after.cc : "삭제")),
        h("td", null, f.before && f.after ? `${f.before.loc} → ${f.after.loc}줄` : f.after ? `${f.after.loc}줄` : ""),
        h("td", null, !f.before ? h("span", {class: "tag new"}, "새로 만든 함수") : f.after && f.after.cc < f.before.cc ? h("b", {class: "good-text"}, `−${f.before.cc - f.after.cc}`) : "")))),
      fns.length ? null : h("caption", null, "복잡도가 바뀐 함수가 없습니다."));
    // Keyed by unit (fqn): one C# file can hold several classes.
    const unitKey = c => c.fqn || c.file_path;
    const before = new Map((comp.before || []).map(c => [unitKey(c), c]));
    const unitName = a => label === "파일" || !a.fqn ? h("b", null, a.file_path) : [h("b", null, a.fqn), h("br"), h("span", {class: "help"}, a.file_path)];
    const fileTable = h("table", {class: "tbl"}, h("thead", null, h("tr", null, ...[label, "G-SI", "복잡도", "연결", "순환 고리 연결"].map(t => h("th", null, t)))),
      h("tbody", null, ...(comp.after || []).map(a => { const b = before.get(unitKey(a)) || a; return h("tr", null, h("td", null, unitName(a)),
        h("td", null, `${b.si} → ${a.si}`), h("td", null, `${b.raw.cc} → `, h("b", {class: a.raw.cc < b.raw.cc ? "good-text" : ""}, a.raw.cc)),
        h("td", null, `${b.raw.coupling} → `, h("b", {class: a.raw.coupling < b.raw.coupling ? "good-text" : ""}, a.raw.coupling)),
        h("td", null, `${b.raw.dependency_cycle} → `, h("b", {class: a.raw.dependency_cycle < b.raw.dependency_cycle ? "good-text" : ""}, a.raw.dependency_cycle))); })));

    const check = (ok, title, text, more, action) => h("div", {class: "check"}, h("span", {class: `ok ${ok ? "" : "todo"}`}, ok ? "✓" : "·"),
      h("div", null, h("b", null, title), h("p", null, text), more ? h("details", null, h("summary", null, "자세히"), more) : null, action || null));
    const re = checks.reanalyzed || {};
    const playButtons = canRecordPlay ? h("div", {class: "row-gap"},
      h("button", {class: "btn ghost sm", type: "button", onclick: e => play(true, e)}, "직접 해 보니 정상입니다"),
      h("button", {class: "btn ghost sm", type: "button", onclick: e => play(false, e)}, "문제가 있었습니다")) : null;
    async function play(ok, event) {
      event.currentTarget.parentElement.querySelectorAll("button").forEach(b => { b.disabled = true; });
      try { await ctx.api(`/api/jobs/${jobId}/rounds/${n}/play`, {method: "POST", body: JSON.stringify({ok})}); toast(ok ? "직접 플레이 확인을 기록했습니다." : "문제가 있었다고 기록했습니다."); load(); }
      catch (error) { toast(error.message); load(); }
    }
    const checkList = h("div", {class: "checks"},
      check(checks.original_preserved, "원본 보존", "원본 소스는 그대로 두고 사본에만 적용했습니다.", "적용 전후에 파일마다 지문(SHA-256)을 비교했습니다."),
      check(checks.matches_preview, "승인한 변경과 동일", "적용된 파일이 검토 화면에서 본 변경안과 정확히 같습니다.", `대상·함께 수정·새 파일 ${round.files.length}개`),
      check(["complete", "partial"].includes(re.state), "다시 분석", `수정본 파일 ${re.analyzed_files ?? "?"}개를 처음과 같은 기준으로 다시 분석했습니다.`,
        re.syntax_files ? `일부 문법을 건너뛴 파일 ${re.syntax_files}개는 처음과 같은 방식으로 분석했습니다.` : null),
      game.available ? check(built, "빌드", built ? "수정된 게임을 빌드했습니다." : "오른쪽 게임 카드에서 수정된 게임을 준비하면 빌드를 확인합니다.")
        : check(false, "빌드", "이 프로젝트에는 등록된 빌드 절차가 없습니다. 개발 환경에서 직접 빌드해 확인해 주세요."),
      game.available && built && game.verification_summary ? check(true, "동작 비교", game.verification_summary) : null,
      check(checks.play?.ok, "직접 플레이", checks.play ? (checks.play.ok ? "수정된 게임을 직접 해 보고 정상이라고 확인했습니다." : "직접 해 보니 문제가 있었다고 기록했습니다.")
          : canRecordPlay ? "수정된 게임을 직접 해 본 뒤 결과를 기록해 주세요." : "먼저 오른쪽에서 수정된 게임을 준비해 실행한 뒤 결과를 기록할 수 있습니다.",
        checks.play?.at ? `${new Date(checks.play.at * 1000).toLocaleString("ko-KR")} 기록` : null, checks.play ? null : playButtons));

    const parts = h("details", {class: "parts"}, h("summary", null, "엉킴 총량 구성 보기"),
      h("table", {class: "tbl"}, h("thead", null, h("tr", null, ...["항목", "처음", `${n}라운드`, ""].map(t => h("th", null, t)))),
        h("tbody", null, ...cur.components.map(c => h("tr", {class: c.included ? "" : "muted"}, h("td", null, c.label.replace("단위", label)),
          h("td", null, c.before.toLocaleString()), h("td", null, h("b", {class: c.after < c.before ? "good-text" : ""}, c.after.toLocaleString())),
          h("td", {class: "help"}, c.included ? "" : "처음 값이 0이라 계산에서 뺍니다"))))));
    fill(root,
      failedApply ? notice(`마지막 변경안을 적용하지 못했습니다. ${state.error || ""} 아래는 그 전까지 적용된 결과입니다.`) : null,
      h("div", {class: "page-head"}, h("div", null, h("div", {class: "eyebrow"}, `수정 결과·검증 · ${n}라운드`),
        h("h1", {class: "h1"}, lead + tail), h("p", {class: "sub"}, subline))),
      h("div", {class: "layout"},
        h("div", null,
          h("div", {class: "tangle card"}, h("div", null, h("div", {class: "eyebrow"}, "엉킴 총량 · 처음 상태 = 100"),
            h("div", {class: "big-index"}, h("s", null, "100 →"), h("b", null, cur.index.toFixed(cur.index % 1 ? 2 : 0))),
            h("p", {class: "help"}, "순환 고리·연결·매우 복잡한 함수·초과 복잡도·전역 상태 접근을 처음 상태와 비교한 값입니다. G-SI 같은 순위가 아니라 실제 양이라 작은 개선도 드러납니다."),
            cur.same_units ? null : h("p", {class: "chip warn"}, `⚠ 분석된 ${label} 구성이 처음과 달라(추가·삭제) 총량을 그대로 비교하기 어렵습니다`),
            parts), chart),
          // The total above compares with the first analysis; these four compare with the round before.
          h("p", {class: "help sum-note"}, `아래 네 값은 ${n > 1 ? `${n - 1}라운드` : "처음 상태"}와 비교한 이번 ${n}라운드의 변화입니다.`),
          h("div", {class: "sum"}, ...KEYS.map(([key, title]) => stat(key, title))),
          h("div", {class: "card sec"}, h("div", {class: "h2"}, "함수별 변화"), h("p", {class: "help"}, "다시 분석해서 측정한 값입니다."), fnTable),
          h("div", {class: "card sec"}, h("div", {class: "h2"}, `${label} 점수`), h("p", {class: "help"}, `G-SI는 프로젝트 안에서의 순위라서, 다른 ${label === "파일" ? "파일과" : "클래스와"} 비교한 위치가 같으면 그대로입니다.`), fileTable),
          h("div", {class: "card sec"}, h("div", {class: "h2"}, "검증"), checkList),
          h("div", {class: "actions"},
            h("details", {class: "menu"}, h("summary", {class: "btn ghost", "aria-label": "더 보기", title: "더 보기"}, "…"), h("button", {class: "btn ghost sm", type: "button", onclick: undo}, "이 라운드 되돌리기")),
            h("a", {class: "btn ghost", href: `#/job/${jobId}/diagnosis`}, "진단 화면으로"),
            h("a", {class: "btn ghost", href: `/revisions/${jobId}/${round.revision}/modified-source.zip`}, "수정본 내려받기 (.zip)"),
            h("a", {class: "btn primary", href: `#/job/${jobId}/diagnosis`, onclick: () => toast(`${n}라운드 수정본 기준으로 다시 진단합니다.`)}, "다음 처방 받기 →"))),
        game.available ? gameCard(game, round) : h("aside", {class: "card game"}, h("div", {class: "eyebrow"}, "게임 실행"),
          h("p", {class: "sub"}, "이 프로젝트에는 등록된 시연 게임이 없습니다. 수정본을 내려받아 개발 환경에서 실행해 확인해 주세요."))));
  }

  async function undo() {
    if (!await confirmDialog({title: "이 라운드를 되돌릴까요?", body: "현재 수정본이 이전 라운드로 돌아갑니다. 기록과 파일은 지우지 않고 보관합니다.", ok: "되돌리기"})) return;
    try { await ctx.api(`/api/jobs/${jobId}/rounds/undo`, {method: "POST", body: "{}"}); toast("이전 라운드로 되돌렸습니다."); load(); }
    catch (error) { toast(error.message); }
  }

  function gameCard(game, round) {
    const prepared = game.state === "complete" && game.revision === round.revision;
    const status = h("div", {class: "game-status"});
    // One watcher per page: a redraw builds a new card, and the old card's watcher stops.
    const token = ++watcher;
    clearTimeout(gameTimer);
    const button = h("button", {class: "btn primary", type: "button"}, prepared ? "수정된 게임 실행 ▶" : "수정된 게임 준비하고 실행 ▶");
    const gp = progressBlock();
    function showProgress(state) {
      const p = state.progress || {};
      gp.update({step: p.step || 0, total: p.total || 4, text: p.label || "", indeterminate: p.indeterminate,
        elapsed: state.started_at ? elapsedText((Date.now() - new Date(state.started_at).getTime()) / 1000) : ""});
      fill(status, gp.el);
    }
    async function launch() {
      try { const r = await ctx.api(`/api/jobs/${jobId}/demo/launch`, {method: "POST", body: JSON.stringify({version: "modified"})}); fill(status, h("p", {class: "help"}, r.message)); }
      catch (error) { fill(status, notice(error.message)); }
      button.disabled = false;
    }
    const again = () => { clearTimeout(gameTimer); gameTimer = setTimeout(() => alive && token === watcher && watch(), 1000); };
    async function watch() {
      let state;
      try { state = await ctx.api(`/api/jobs/${jobId}/demo`); }
      catch (_) { if (alive && token === watcher) again(); return; }
      if (!alive || token !== watcher) return;
      if (state.state === "running") { showProgress(state); again(); return; }
      if (state.state === "complete" && state.revision === round.revision) { button.textContent = "수정된 게임 실행 ▶"; await launch(); load(); return; }
      fill(status, notice(state.error || "게임을 준비하지 못했습니다.")); button.disabled = false;
    }
    button.addEventListener("click", async () => {
      button.disabled = true;
      if (game.state === "complete" && game.revision === round.revision) { await launch(); return; }
      try { showProgress(await ctx.api(`/api/jobs/${jobId}/demo/prepare`, {method: "POST", body: "{}"})); watch(); }
      catch (error) { fill(status, notice(error.message)); button.disabled = false; }
    });
    if (game.state === "running") { button.disabled = true; showProgress(game); again(); }
    else if (game.state === "failed") fill(status, notice(`지난번 게임 준비에 실패했습니다. ${game.error || ""}`));
    return h("aside", {class: "card game"}, h("div", {class: "eyebrow"}, "수정된 게임"),
      h("div", {class: "h2"}, game.game_title || "시연 게임"), h("p", {class: "sub"}, game.description || ""),
      h("div", {class: "gthumb", "aria-hidden": "true"}, h("i", {class: "ship"})),
      h("details", {class: "controls"}, h("summary", null, "조작 방법"), h("p", null, game.controls || "")),
      status, h("div", {class: "game-actions"}, button));
  }

  await load();
  return () => { alive = false; clearTimeout(timer); clearTimeout(gameTimer); };
}
