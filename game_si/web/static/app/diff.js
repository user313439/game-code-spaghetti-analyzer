// Side-by-side rendering of a unified diff (original left, revised right).
import {h} from "./ui.js";

export function parseUnified(diff) {
  const rows = [];
  let left = 0, right = 0, minus = [], plus = [], inHunk = false;
  const flush = () => {
    const n = Math.max(minus.length, plus.length);
    for (let i = 0; i < n; i++) {
      const l = minus[i] || null, r = plus[i] || null;
      rows.push({type: l && r ? "chg" : l ? "del" : "add", left: l, right: r});
    }
    minus = []; plus = [];
  };
  for (const line of String(diff || "").split(/\r?\n/)) {
    // File headers come before the first hunk; inside a hunk "---x" is a removed line "--x".
    if (!inHunk && (line.startsWith("---") || line.startsWith("+++"))) continue;
    const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(line);
    if (hunk) { flush(); inHunk = true; left = +hunk[1]; right = +hunk[2]; rows.push({type: "hunk", left, right}); continue; }
    if (!inHunk) continue;
    if (line.startsWith("-")) { minus.push([left++, line.slice(1)]); continue; }
    if (line.startsWith("+")) { plus.push([right++, line.slice(1)]); continue; }
    if (line.startsWith(" ")) { flush(); rows.push({type: "ctx", left: [left++, line.slice(1)], right: [right++, line.slice(1)]}); }
  }
  flush();
  return rows;
}

// Remove the indentation shared by every shown line so deep code stays readable.
export function dedent(rows) {
  const texts = rows.flatMap(r => r.type === "hunk" ? [] : [r.left, r.right]).filter(Boolean)
    .map(x => x[1].replace(/\t/g, "   ")).filter(s => s.trim());
  const cut = texts.length ? Math.min(...texts.map(s => s.match(/^ */)[0].length)) : 0;
  const tidy = x => x ? [x[0], x[1].replace(/\t/g, "   ").slice(cut)] : x;
  return rows.map(r => r.type === "hunk" ? r : {...r, left: tidy(r.left), right: tidy(r.right)});
}

export function diffView(item) {
  const rows = dedent(item.created
    ? String(item.after || "").split(/\r?\n/).map((text, i) => ({type: "add", left: null, right: [i + 1, text]}))
    : parseUnified(item.diff));
  const body = h("div", {class: "diff"});
  for (const r of rows) {
    if (r.type === "hunk") { body.append(h("div", {class: "dr hunk"}, h("div", null, `원본 ${r.left}행 · 수정본 ${r.right}행 부근`))); continue; }
    const lc = r.type === "ctx" ? "" : r.type === "add" ? "empty" : "del";
    const rc = r.type === "ctx" ? "" : r.type === "del" ? "empty" : "add";
    body.append(h("div", {class: "dr"},
      h("div", {class: `n ${r.left && lc === "del" ? "del" : ""}`}, r.left ? r.left[0] : ""), h("div", {class: `c ${lc}`}, r.left ? r.left[1] : ""),
      h("div", {class: `n ${r.right && rc === "add" ? "add" : ""}`}, r.right ? r.right[0] : ""), h("div", {class: `c ${rc}`}, r.right ? r.right[1] : "")));
  }
  return h("div", null, h("div", {class: "dcols"}, h("div", null, item.created ? "원본 (없음)" : "원본"), h("div", null, item.created ? "새 파일" : "수정본")), body);
}

export function lineCounts(item) {
  if (item.created) return {add: String(item.after || "").split(/\r?\n/).filter(Boolean).length, rem: 0};
  let add = 0, rem = 0, inHunk = false;
  for (const line of String(item.diff || "").split(/\r?\n/)) {
    if (line.startsWith("@@")) inHunk = true;
    else if (!inHunk) continue;
    else if (line.startsWith("+")) add++;
    else if (line.startsWith("-")) rem++;
  }
  return {add, rem};
}
