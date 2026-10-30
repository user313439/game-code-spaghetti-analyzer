import {GRADE_HELP, GSI_HELP, LANGUAGE_LABELS, METRIC_KEYS, TOP_HELP, METRIC_LABELS, barNote, barTone, obj, subj, whyRows} from "./core.js";
import {bar, gradeBadge, h, notice, fill} from "./ui.js";
import {createMap, MAP_LIMIT} from "./map.js";
import {createPrescriptionPanel} from "./prescription.js";

const FIRST_CARDS = 8;

export async function render(view, ctx, {jobId}) {
  let job, data;
  ctx.setSteps(jobId, 1);
  const loading = h("section", {class: "wrap"}, h("p", {class: "empty"}, "진단 결과를 불러오고 있습니다."));
  view.append(loading);
  try {
    [job, data] = await Promise.all([ctx.api(`/api/jobs/${jobId}`), ctx.api(`/api/jobs/${jobId}/diagnosis`)]);
  } catch (error) {
    fill(loading, notice(error.status === 409 ? "아직 분석이 끝나지 않았습니다. 분석이 끝나면 진단을 볼 수 있습니다." : error.message),
      h("a", {class: "btn ghost", href: `#/job/${jobId}`}, "분석 상태 보기"));
    return;
  }
  loading.remove();
  ctx.setCrumb(job.name);
  ctx.setSteps(jobId, 1, {refactor: true, result: Boolean(data.round)});
  const s = data.summary, label = s.unit_label;
  let plan = [], map = null, mapHost, pickCard, showAll = false;
  const names = new Map(data.units.map(u => [u.fqn, u.name || u.fqn]));
  const nameOf = id => names.get(id) || id;

  // ---------------------------------------------------------------- cards
  const cards = h("div", {class: "cards"});
  function chips(list) {
    const box = h("div", {class: "chips small"});
    const shown = 8;
    list.forEach((id, i) => box.append(h("button", {class: `chip link ${i >= shown ? "more" : ""}`, type: "button", title: id, onclick: () => showOnMap(id)}, nameOf(id))));
    if (list.length > shown) {
      const toggle = h("button", {class: "chip toggle", type: "button"}, `+${list.length - shown}개 더 보기`);
      toggle.addEventListener("click", () => { box.classList.toggle("all"); toggle.textContent = box.classList.contains("all") ? "접기" : `+${list.length - shown}개 더 보기`; box.append(toggle); });
      box.append(toggle);
    }
    if (!list.length) box.append(h("span", {class: "sub"}, "없음"));
    return box;
  }
  function card(u, index) {
    const rank = plan.indexOf(u.fqn);
    const worst = u.functions[0];
    const maxcc = Math.max(1, worst ? worst.cc : 1);
    const score = h("div", {class: `score g${u.grade}`, title: `G-SI ${Math.round(u.si)}점 · ${u.grade}등급. ${GRADE_HELP}`}, Math.round(u.si));
    const detail = h("div", {class: "detail"},
      h("div", null, h("h5", null, "왜 엉켰나요?"),
        h("div", {class: "why"}, ...whyRows(u, s).flatMap(r => [h("b", null, r.label), h("span", null, r.text),
          h("span", {class: "p"}, r.place ? [h("b", null, r.place), h("small", null, `${s.units}개 중 · ${r.top}`)] : r.top)]))),
      h("div", null, h("h5", null, `복잡한 함수 ${u.functions.length} / ${u.function_count}개`),
        h("table", {class: "ftab"}, h("tbody", null, ...u.functions.map(f => h("tr", null,
          h("td", {class: "mono"}, f.name), h("td", {class: "sub"}, `${f.line}행부터`), h("td", null, "CC ", h("b", null, f.cc)),
          h("td", null, bar(100 * f.cc / maxcc, f.cc >= 50 ? "hot" : "cool")))))),
        h("h5", {class: "gap"}, `이 ${subj(label)} 부르는 ${label} ${u.calls.length}개`), chips(u.calls),
        h("h5", null, `이 ${obj(label)} 부르는 ${label} ${u.called_by.length}개`), chips(u.called_by)),
      h("div", {class: "detail-actions"}, h("button", {class: "btn ghost sm", type: "button", onclick: () => showOnMap(u.fqn)}, "지도에서 보기")));
    const head = h("button", {class: "fhead", type: "button", "aria-expanded": "false"},
      score,
      h("div", {class: "fmain"},
        h("div", {class: "fname"}, `${index + 1}. ${u.name}`, h("small", null, `${u.file} · ${u.loc.toLocaleString()}줄`), rank >= 0 ? h("span", {class: "rec"}, `AI 처방 ${rank + 1}순위`) : null),
        h("div", {class: "say"}, u.sentence),
        h("div", {class: "mbars"}, ...METRIC_KEYS.map(k => { const note = barNote(u, k);
          return h("div", null, METRIC_LABELS[k], bar(u.pct[k], barTone(u.pct[k])), h("small", {class: `mnote ${note.hot ? "hot" : ""}`, title: TOP_HELP}, note.text)); }))),
      h("div", {class: "fn"}, "가장 복잡한 함수", h("br"), worst ? [h("b", null, worst.name), ` · CC ${worst.cc} · ${worst.loc}줄`] : "없음"),
      h("span", {class: "chev", "aria-hidden": "true"}, "▾"));
    const el = h("article", {class: `card fc ${rank >= 0 ? "recd" : ""}`, id: `fc-${u.fqn}`}, head, detail);
    head.addEventListener("click", () => { el.classList.toggle("open"); head.setAttribute("aria-expanded", String(el.classList.contains("open"))); });
    return el;
  }
  function drawCards() {
    const open = new Set([...cards.querySelectorAll(".fc.open")].map(e => e.id));
    const units = showAll ? data.units : data.units.slice(0, FIRST_CARDS);
    fill(cards, ...units.map(card));
    for (const id of open) cards.querySelector(`#${CSS.escape(id)}`)?.classList.add("open");
    if (data.units.length > FIRST_CARDS) cards.append(h("button", {class: "btn ghost block", type: "button", onclick: () => { showAll = !showAll; drawCards(); }},
      showAll ? "상위 8개만 보기" : `나머지 ${data.units.length - FIRST_CARDS}개 ${label} 보기`));
  }

  // ---------------------------------------------------------------- map
  const seg = (items, onChange) => {
    const box = h("div", {class: "seg sm"});
    items.forEach(([value, text], i) => box.append(h("button", {type: "button", class: i === 0 ? "on" : "", "aria-pressed": String(i === 0), onclick: e => {
      box.querySelectorAll("button").forEach(b => { const on = b === e.currentTarget; b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on)); }); onChange(value); }}, text)));
    return box;
  };
  const filterSeg = seg([["all", "전체 연결"], ["cycle", "순환 고리만"], ["plan", "AI 처방 주변"]], v => map?.setFilter(v));
  // 'AI 처방 주변' means nothing until a prescription names files: keep it off until then.
  function syncPlanFilter() {
    const [all, , near] = filterSeg.querySelectorAll("button");
    near.disabled = !plan.length;
    near.title = plan.length ? "" : "AI 처방을 받으면 선택할 수 있습니다";
    if (!plan.length && near.classList.contains("on")) all.click();
  }
  syncPlanFilter();
  mapHost = h("div", {class: "map-host"});
  pickCard = h("div", {class: "card pick", hidden: true});
  const mapCard = h("section", {class: "card mapcard", hidden: true},
    h("div", {class: "mapbar"}, h("div", {class: "h2"}, "스파게티 지도"),
      seg([["force", "자유 배치"], ["circle", "원형 배치"]], v => map?.setLayout(v)),
      filterSeg),
    mapHost,
    h("div", {class: "zoombox"}, h("button", {type: "button", "aria-label": "확대", onclick: () => map?.zoomBy(1.4)}, "+"),
      h("button", {type: "button", "aria-label": "축소", onclick: () => map?.zoomBy(1 / 1.4)}, "−"),
      h("button", {type: "button", "aria-label": "화면에 맞추기", onclick: () => map?.fit()}, "⤢")),
    h("div", {class: "legend"}, ...["E", "D", "C", "B", "A"].map(g => h("span", null, h("i", {class: `dot g${g}`}), g === "E" ? "E 심함" : g === "A" ? "A 깔끔" : g)),
      h("span", null, h("i", {class: "dot ring"}), "AI 처방"), h("span", null, h("i", {class: "line out"}), `이 ${subj(label)} 부름`), h("span", null, h("i", {class: "line in"}), `이 ${obj(label)} 부름`)),
    pickCard);
  function ensureMap() {
    if (map) return;
    map = createMap(mapHost, {nodes: data.graph.nodes, edges: data.graph.edges, unitLabel: label, onPick: showPick});
    map.setPlan(plan);
    if (map.truncated) mapCard.append(h("p", {class: "map-note"}, `${subj(label)} 많아 G-SI 상위 ${MAP_LIMIT}개만 표시합니다.`));
  }
  function showPick(v) {
    if (!v) { pickCard.hidden = true; return; }
    const unit = data.units.find(u => u.fqn === v.id);
    pickCard.hidden = false;
    fill(pickCard, 
      h("div", {class: "row-gap"}, gradeBadge(v.grade), h("b", {title: v.id}, v.label || v.id), h("span", {class: "push"}, Number(v.si).toFixed(1)),
        h("button", {class: "pick-close", type: "button", "aria-label": "선택 해제하고 전체 지도 보기", title: "선택 해제 · 전체 지도 보기", onclick: () => map?.clearFocus()}, "×")),
      h("p", {class: "sub"}, `부르는 ${label} ${v.fout} · 불리는 ${label} ${v.fin} · ${v.in_cycle ? "순환 고리 안" : "순환 고리 밖"}`),
      unit ? h("button", {class: "btn ghost sm block", type: "button", onclick: () => openCard(unit.fqn)}, "진단서에서 자세히 보기") : null);
  }
  const viewHelp = h("p", {class: "help"});
  const helpText = which => which === "map" ? `점을 누르면 그 ${label}의 연결만 보입니다. 휠이나 오른쪽 아래 버튼으로 확대·축소합니다.` : `${obj(label)} 누르면 점수의 이유와 연결이 펼쳐집니다.`;
  viewHelp.textContent = helpText("cards");
  function setView(which) {
    viewHelp.textContent = helpText(which);
    viewSeg.querySelectorAll("button").forEach(b => { b.classList.toggle("on", b.dataset.v === which); b.setAttribute("aria-pressed", String(b.dataset.v === which)); });
    mapCard.hidden = which !== "map";
    cards.hidden = which === "map";
    if (which === "map") { ensureMap(); map.refresh(); }
  }
  function showOnMap(id) { setView("map"); requestAnimationFrame(() => map.focusOn(id)); }
  function openCard(id, flash = false) {
    const index = data.units.findIndex(u => u.fqn === id);
    if (index >= FIRST_CARDS && !showAll) { showAll = true; drawCards(); }
    setView("cards");
    const el = cards.querySelector(`#${CSS.escape(`fc-${id}`)}`);
    if (!el) return;
    el.classList.add("open");
    el.querySelector(".fhead")?.setAttribute("aria-expanded", "true");
    el.scrollIntoView({behavior: "smooth", block: "start"});
    if (flash) { el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
  }
  const viewSeg = h("div", {class: "seg"},
    h("button", {type: "button", class: "on", "aria-pressed": "true", dataset: {v: "cards"}, onclick: () => setView("cards")}, "진단서"),
    h("button", {type: "button", "aria-pressed": "false", dataset: {v: "map"}, onclick: () => setView("map")}, "스파게티 지도"));

  // ---------------------------------------------------------------- page
  const lang = LANGUAGE_LABELS[s.language] || s.language || "";
  // The static report of the round shown here, in the current theme (decided when clicked).
  const reportHref = () => `${data.revision ? `/revisions/${jobId}/${data.revision}` : `/results/${jobId}`}/index.html?theme=${ctx.theme() === "dark" ? "dark" : "blue"}`;
  const worst = s.worst_function;
  const panel = createPrescriptionPanel(ctx, {jobId, data, onPlan: names => {
    if (names.join("|") === plan.join("|")) return;   // polling repeats the same plan; keep cards as they are
    plan = names; drawCards(); map?.setPlan(plan); syncPlanFilter();
  }, onFocus: id => {
    // Same view, that file: on the map it is picked and centred; in the report its card opens.
    if (!mapCard.hidden && map) { map.focusOn(id); mapCard.scrollIntoView({behavior: "smooth", block: "nearest"}); }
    else openCard(id, true);
  }});
  view.append(h("section", {class: "wrap wide"},
    h("div", {class: "page-head"},
      h("div", null, h("div", {class: "eyebrow"}, `엉킴 진단 · ${lang} ${s.units}개 ${label}${data.round ? ` · ${data.round}라운드 수정본 기준` : ""}`), h("h1", {class: "h1"}, data.headline),
        s.backend === "clang" && s.state === "complete" ? h("p", {class: "chip good"}, "✓ 정밀 분석(Clang) · 모든 파일을 컴파일러 기준으로 해석했습니다") : null,
        s.state === "partial" && s.backend === "clang" ? h("p", {class: "chip warn"}, `⚠ ${s.compiler_error_files || 0}개 파일에서 컴파일 오류가 있어 일부만 해석했습니다`) : null,
        s.state === "partial" && s.backend !== "clang" ? h("p", {class: "chip warn"}, `⚠ ${s.syntax_files}개 파일은 일부 문법을 건너뛰고 분석했습니다`) : null)),
    h("div", {class: "layout"},
      h("div", null,
        h("div", {class: "sum"},
          h("div", {class: "card stat", title: `${GRADE_HELP} E등급은 G-SI 80 이상입니다.`}, h("b", {class: "hot-text"}, `${s.e_count} / ${s.units}`), h("span", null, `심하게 엉킨 ${label} (E등급)`)),
          // Every unit in any cycle, the same count the result page compares round by round.
          h("div", {class: "card stat"}, h("b", null, (s.cycle_units ?? s.cycle_size) > 1 ? `${s.cycle_units ?? s.cycle_size}개 ${label}` : "없음"),
            h("span", null, s.cycles > 1 ? `순환 고리 ${s.cycles}개에 묶인 ${label}` : "서로 꼬리를 무는 순환 고리")),
          h("div", {class: "card stat"}, h("b", null, `${s.links.toLocaleString()}개`), h("span", null, `${label} 사이 연결선`)),
          h("div", {class: "card stat"}, h("b", null, worst ? `CC ${worst.cc}` : "—"), h("span", null, worst ? `가장 복잡한 함수 · ${worst.name}` : "함수 정보 없음"))),
        h("details", {class: "gsi-guide"}, h("summary", null, "G-SI·등급·‘상위 %’는 무슨 뜻인가요?"),
          h("p", null, GSI_HELP), h("p", null, GRADE_HELP), h("p", null, TOP_HELP)),
        // The tabs sit right above what they switch.
        h("div", {class: "viewbar"}, viewSeg, viewHelp),
        cards, mapCard,
        h("p", {class: "foot"}, h("a", {href: reportHref(), target: "_blank", rel: "noopener", onclick: e => { e.currentTarget.href = reportHref(); }}, "원본 HTML 보고서 열기 ↗"),
          " · G-SI는 이 프로젝트 안에서의 순위(0~100)이며, 먼저 살펴볼 곳을 고르는 데 씁니다.")),
      panel.el)));
  drawCards();
  return () => { map?.destroy(); panel.destroy?.(); };
}
