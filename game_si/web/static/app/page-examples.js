import {groupExamples, reportUrl, safeResultUrl} from "./core.js";
import {h, notice, fill} from "./ui.js";

export async function render(view, ctx) {
  const list = h("div", {class: "list"}, h("p", {class: "empty"}, "예시 결과를 불러오고 있습니다."));
  const extra = h("div", {class: "list"});
  const extraBox = h("details", {class: "archive", hidden: true}, h("summary", null, "OpenRA 보조 모듈"),
    h("p", {class: "help"}, "같은 OpenRA 프로젝트에 속한 추가 모듈의 분석 결과입니다."), extra);
  view.append(h("section", {class: "wrap"},
    h("div", {class: "page-head"}, h("div", null, h("div", {class: "eyebrow"}, "예시 결과"), h("h1", {class: "h1"}, "실험에 사용한 게임 프로젝트"),
      h("p", {class: "sub"}, "보고서의 고정 실험에서 실제로 분석한 범위와 결과입니다. 결과는 별도의 HTML 보고서로 열립니다."))),
    list, extraBox));
  try {
    const groups = groupExamples((await ctx.api("/api/examples")).filter(e => safeResultUrl(e.url)));
    fill(list, ...(groups.projects.length ? groups.projects.map(p => h("article", {class: "card item"},
      h("div", null, h("h3", {class: "h3"}, p.project), h("p", {class: "sub"}, `${p.genre} · ${p.language}`), h("p", null, p.description),
        h("p", {class: "sub"}, `분석 범위: ${p.examples.map(e => e.scope).join(" / ")}`), h("p", {class: "sub"}, p.focus),
        h("div", {class: "row-gap"}, ...p.examples.map(e => h("a", {class: "btn ghost sm", href: reportUrl(e.url, ctx.theme()), onclick: ev => { ev.currentTarget.href = reportUrl(e.url, ctx.theme()); }}, `${e.name} 결과 ↗`)))))) :
      [h("p", {class: "empty"}, "현재 제공되는 예시 결과가 없습니다.")]));
    extraBox.hidden = !groups.auxiliary.length;
    fill(extra, ...groups.auxiliary.map(e => h("article", {class: "card item"},
      h("div", null, h("h3", {class: "h3"}, e.name), h("p", {class: "sub"}, e.scope)),
      h("a", {class: "btn ghost sm", href: reportUrl(e.url, ctx.theme()), onclick: ev => { ev.currentTarget.href = reportUrl(e.url, ctx.theme()); }}, "결과 열기 ↗"))));
  } catch (error) { fill(list, notice(error.message)); }
}
