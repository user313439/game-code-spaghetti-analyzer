import {canInspectJob, formatSourceSize, jobDate, sortJobs, statusView} from "./core.js";
import {confirmDialog, h, notice, fill} from "./ui.js";

// How far the AI tidying went, next to the name: so "분석 완료" alone never hides a job stopped at stage 3.
export function progressChip(p = {}) {
  const [text, tone] = p.play === "ok" ? [`정리 완료 · ${p.stages}단계`, "is-ok"]
    : p.play === "problem" ? [`${p.stages}단계 · 플레이 중 문제 기록`, "is-bad"]
    : p.stages ? [`AI 정리 ${p.stages}단계까지 · 마무리 전`, "is-now"]
    : p.prescribed ? ["AI 처방만 받음", ""] : ["진단만", ""];
  return h("span", {class: `h-progress ${tone}`}, text);
}

export async function render(view, ctx) {
  let jobs = [], busy = false, undoId = null, alive = true;
  const sort = h("select", {id: "history-sort"}, h("option", {value: "latest"}, "최신순"), h("option", {value: "name"}, "이름순"), h("option", {value: "size"}, "소스 용량 큰 순"));
  const message = h("div", {class: "alert-slot", role: "status"});
  const list = h("div", {class: "list"});
  const archived = h("div", {class: "list"});
  view.append(h("section", {class: "wrap"},
    h("div", {class: "page-head"}, h("div", null, h("div", {class: "eyebrow"}, "분석 기록"), h("h1", {class: "h1"}, "이 컴퓨터에서 분석한 코드"),
      h("p", {class: "sub"}, "다시 열어 진단과 수정 결과를 이어서 볼 수 있습니다.")),
      h("div", {class: "row-gap"}, h("label", {for: "history-sort", class: "sub"}, "정렬"), sort, h("button", {class: "btn ghost sm", type: "button", onclick: load}, "새로고침"))),
    message, list,
    h("details", {class: "archive"}, h("summary", null, "삭제한 기록"), h("p", {class: "help"}, "복원하면 기존 소스와 결과를 다시 볼 수 있습니다."), archived)));
  sort.addEventListener("change", draw);

  function row(job) {
    const v = statusView(job), date = jobDate(job.created_at);
    const actions = h("div", {class: "row-gap"});
    // A job opens where it was left: the finished record, the last stage's result, or the diagnosis.
    const p = job.progress || {};
    if (v.result && p.stages) {
      actions.append(h("a", {class: "btn ghost sm", href: `#/job/${job.id}/diagnosis`}, "진단 보기"),
        p.play ? h("a", {class: "btn primary sm", href: `#/job/${job.id}/finish`}, p.play === "ok" ? "정리 기록 보기 →" : "문제 기록 보기 →")
          : h("a", {class: "btn primary sm", href: `#/job/${job.id}/result`}, `${p.stages}단계 결과 보기 →`));
    } else if (v.result) actions.append(h("a", {class: "btn primary sm", href: `#/job/${job.id}/diagnosis`}, "진단 보기 →"));
    if (canInspectJob(job.state)) actions.append(h("a", {class: "btn ghost sm", href: `#/job/${job.id}`},
      job.state === "ready" ? "범위 확인" : ["failed", "interrupted"].includes(job.state) ? "상태·기록 확인" : "진행 확인"));
    actions.append(h("button", {class: "icon-btn trash", type: "button", disabled: !job.can_delete || busy || !ctx.ready,
      title: job.can_delete ? "기록 삭제" : "작업이 끝난 뒤 삭제할 수 있습니다.", "aria-label": `${job.name || "가져온 소스"} 기록 삭제`,
      onclick: async () => { if (await confirmDialog({title: "분석 기록을 삭제할까요?", body: `‘${job.name || "가져온 소스"}’ 기록을 목록에서 숨깁니다. 소스와 결과 파일은 보관되며 ‘삭제한 기록’에서 복원할 수 있습니다.`, ok: "기록 삭제"})) mutate(job.id, "delete"); }}, "🗑"));
    return h("article", {class: "card item"},
      h("div", null, h("h3", {class: "h3"}, job.name || "가져온 소스", v.result ? progressChip(p) : null),
        h("p", {class: "sub"}, `${v.title} · ${date ? date.toLocaleString("ko-KR") : "시간 미확인"} · 소스 ${formatSourceSize(job.scan?.source_bytes)}`),
        job.error ? h("p", {class: "sub warn"}, String(job.error)) : null),
      actions);
  }
  function draw() {
    const live = sortJobs(jobs.filter(j => !j.deleted_at), sort.value);
    const gone = sortJobs(jobs.filter(j => j.deleted_at), sort.value);
    fill(list, ...(live.length ? live.map(row) : [h("p", {class: "empty"}, "아직 분석 기록이 없습니다. 새 분석에서 소스를 가져와 보세요.")]));
    fill(archived, ...(gone.length ? gone.map(job => h("article", {class: "card item"},
      h("div", null, h("h3", {class: "h3"}, job.name || "가져온 소스"), h("p", {class: "sub"}, `${statusView(job).title} · 소스 ${formatSourceSize(job.scan?.source_bytes)}`)),
      h("button", {class: "btn ghost sm", type: "button", disabled: busy || !ctx.ready, onclick: () => mutate(job.id, "restore")}, "복원"))) : [h("p", {class: "empty"}, "삭제한 기록이 없습니다.")]));
  }
  async function load() {
    fill(list, h("p", {class: "empty"}, "분석 기록을 불러오고 있습니다."));
    try { jobs = await ctx.api("/api/jobs?include_deleted=true"); if (alive) draw(); }
    catch (error) { fill(list, notice(error.message)); }
  }
  async function mutate(id, action) {
    if (busy || !ctx.ready) return;
    busy = true; draw();
    try {
      const job = await ctx.api(`/api/jobs/${id}/${action}`, {method: "POST", body: "{}"});
      undoId = action === "delete" ? id : null;
      fill(message, h("div", {class: "notice info"},
        action === "delete" ? `‘${job.name}’ 기록을 삭제했습니다. 파일은 보관되어 있습니다.` : `‘${job.name}’ 기록을 복원했습니다.`,
        undoId ? h("button", {class: "btn ghost sm", type: "button", onclick: () => mutate(undoId, "restore")}, "되돌리기") : null));
    } catch (error) { fill(message, notice(error.message)); }
    finally { busy = false; await load(); }
  }
  await load();
  return () => { alive = false; };
}
