"""Node checks for the redesigned UI modules (pure logic only)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'game_si/web/static/app'


def run(script):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    prelude = (f'import assert from "node:assert/strict";\n'
               f'const core = await import({json.dumps((APP / "core.js").as_uri())});\n'
               f'const map = await import({json.dumps((APP / "map.js").as_uri())});\n')
    result = subprocess.run([node, '--input-type=module'], input=prelude + script, text=True,
                            encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr


def test_upload_rules_and_history_sorting():
    run('''
const file = (path, size = 10) => ({file: {name: path.split("/").pop(), size}, path});
const picked = core.prepareUpload([file("Game/src/a.c"), file("Game/bin/b.c"), file("Game/readme.md")], "folder");
assert.deepEqual(picked.paths, ["Game/src/a.c"]); assert.equal(picked.skipped, 2);
assert.throws(() => core.prepareUpload([file("../x.c")], "folder"), /경로/);
assert.throws(() => core.prepareUpload([{name: "a.rar", size: 1}], "zip"), /ZIP/);
assert.equal(core.parseGithubUrl("github.com/o/r"), "https://github.com/o/r");
assert.throws(() => core.parseGithubUrl("https://gitlab.com/o/r"), /GitHub/);
const jobs = [{name: "b", created_at: 2, scan: {source_bytes: 5}}, {name: "a", created_at: 1, scan: {}}, {name: "c", created_at: 3, scan: {source_bytes: 9}}];
assert.deepEqual(core.sortJobs(jobs).map(j => j.name), ["c", "b", "a"]);
assert.deepEqual(core.sortJobs(jobs, "size").map(j => j.name), ["c", "b", "a"]);
assert.equal(core.reportUrl("/results/abc/index.html", "dark"), "/results/abc/index.html?theme=dark");
assert.equal(core.reportUrl("https://evil/x", "dark"), null);
''')


def test_diagnosis_text_helpers_use_korean_particles():
    run('''
assert.equal(core.subj("파일"), "파일이"); assert.equal(core.subj("클래스"), "클래스가");
assert.equal(core.obj("파일"), "파일을"); assert.equal(core.obj("클래스"), "클래스를");
const unit = {raw: {cc: 30, coupling: 3, dependency_cycle: 2, global_state: 0, game_loop_centrality: 0},
  top: {cc: 25, coupling: 25, dependency_cycle: 75, global_state: 100, game_loop_centrality: 100},
  functions: [{name: "big", cc: 30}], calls: ["b"], called_by: ["c", "d"], in_cycle: true};
const rows = core.whyRows(unit, {unit_label: "파일", cycle_size: 3});
assert.equal(rows[0].text, "가장 복잡한 함수 big의 분기 30개"); assert.equal(rows[0].top, "상위 25%");
assert.equal(rows[3].text, "전역 상태 접근 없음"); assert.equal(rows[3].top, "—");
assert.equal(core.barTone(90), "hot"); assert.equal(core.barTone(70), "warm"); assert.equal(core.barTone(10), "cool");
''')


def test_map_layout_is_deterministic_and_separates_nodes():
    run('''
const make = () => Array.from({length: 40}, (_, i) => ({id: "n" + i, si: 100 - i, loc: 50 + i * 30, in_cycle: i < 20}));
const edges = n => n.slice(1).map((v, i) => ({s: n[i], t: v}));
const a = make(), b = make();
map.forceLayout(a, edges(a), 900, 640); map.forceLayout(b, edges(b), 900, 640);
assert.deepEqual(a.map(v => [v.fx, v.fy]), b.map(v => [v.fx, v.fy]));
for (let i = 0; i < a.length; i++) for (let j = i + 1; j < a.length; j++) {
  const d = Math.hypot(a[i].fx - a[j].fx, a[i].fy - a[j].fy);
  assert.ok(d > 8, `nodes ${i} and ${j} overlap (${d})`);
}
map.circleLayout(a, 900, 640);
assert.ok(a.every(v => Number.isFinite(v.cx) && Number.isFinite(v.cy)));
assert.equal(map.MAP_LIMIT, 150);
''')


# --- checks carried over from the previous UI (same pure helpers, now in core.js) ---
def test_report_sort_marker_does_not_replace_the_tooltip():
    source = (APP.parents[2] / 'report.py').read_text(encoding='utf-8')
    assert 'th.sortable::before {{ content: " ↕";' in source
    assert 'th.sortable::after {{ content: " ↕";' not in source


def test_folder_upload_filters_artifacts_and_limits():
    run('''
const file = (path, size = 10) => ({name: path.split("/").pop(), webkitRelativePath: path, size});
const upload = core.prepareUpload([
  file("Game/src/main.cpp"), file("Game/include/game.hpp"), file("Game/a.cs"),
  file("Game/.git/secret.c"), file("Game/node_modules/a.c"), file("Game/bin/a.c"),
  file("Game/obj/a.c"), file("Game/build/a.c"), file("Game/packages/a.c"),
  file("Game/.vs/a.c"), file("Game/.env"), file("Game/readme.md")], "folder");
assert.deepEqual(upload.paths, ["Game/src/main.cpp", "Game/include/game.hpp", "Game/a.cs"]);
assert.equal(upload.skipped, 9); assert.equal(upload.bytes, 30);
assert.throws(() => core.prepareUpload([{name: "main.c", size: 1}], "folder"), /폴더/);
assert.equal(core.DEFAULT_LIMITS.archive_bytes, 100 * 1024 * 1024);
assert.equal(core.DEFAULT_LIMITS.files, 20000);
assert.throws(() => core.prepareUpload([{name: "a.zip", size: 101}], "zip", {archive_bytes: 100}), /크기/);
assert.throws(() => core.prepareUpload([{name: "a.zip", size: 1}, {name: "b.zip", size: 1}], "zip"), /하나/);
const f = {name: "a.c", webkitRelativePath: "Game/a.c", size: 10};
assert.throws(() => core.prepareUpload([f], "folder", {source_bytes: 9}), /크기/);
assert.throws(() => core.prepareUpload([f, f], "folder", {files: 1}), /개수/);
assert.throws(() => core.prepareUpload([{name: "notes.txt", webkitRelativePath: "Game/notes.txt", size: 1}], "folder"), /소스/);
''')


def test_directory_drop_drains_batches_and_stops_at_excluded_or_excess():
    run('''
const entry = i => ({isFile: true, name: `a${i}.c`, file: ok => ok({name: `a${i}.c`, size: 1})});
const batches = [Array.from({length: 100}, (_, i) => entry(i)), [entry(100)], []];
let reads = 0;
const root = {isDirectory: true, name: "Game", createReader: () => ({readEntries: ok => { reads++; ok(batches.shift()); }})};
const files = await core.readDroppedEntries([root]);
assert.equal(reads, 3); assert.equal(files.length, 101); assert.equal(files[100].path, "Game/a100.c");
assert.equal(core.prepareUpload(files, "folder").paths[100], "Game/a100.c");
const excluded = {isDirectory: true, name: "node_modules", createReader: () => { throw Error("must not read"); }};
assert.deepEqual(await core.readDroppedEntries([excluded]), []);
const one = {isFile: true, name: "a.c", file: ok => ok({name: "a.c", size: 2})};
await assert.rejects(() => core.readDroppedEntries([one, one], {files: 1}), /개수/);
await assert.rejects(() => core.readDroppedEntries([one], {source_bytes: 1}), /크기/);
''')


def test_status_view_and_result_urls_are_safe():
    run('''
const running = core.statusView({state: "running", stage: "클래스 추출", elapsed_seconds: 65});
assert.equal(running.title, "분석 중"); assert.equal(running.elapsed, "1분 5초");
assert.equal(running.busy, true); assert.equal(running.result, false);
assert.equal(core.statusView({state: "partial"}).result, true);
assert.equal(core.statusView({state: "failed"}).result, false);
assert.equal(core.statusView({state: "interrupted"}).title, "분석 중단");
for (const bad of ["javascript:alert(1)", "//other.example/result", "https://other.example/result"]) assert.equal(core.safeResultUrl(bad), null);
assert.equal(core.safeResultUrl("/results/a/index.html"), "/results/a/index.html");
''')


def test_api_tokens_multipart_and_readable_errors():
    run('''
const calls = [];
const api = core.createApi("session-token", async (url, options) => { calls.push({url, options}); return {ok: true, json: async () => ({id: "one"})}; });
await api("/api/jobs");
await api("/api/jobs/one/start", {method: "POST", body: JSON.stringify({lang: "c"})});
await api("/api/import/files", {method: "POST", body: {test: "form"}});
assert.equal(calls[0].options.headers["X-Game-SI-Token"], undefined);
assert.equal(calls[1].options.headers["X-Game-SI-Token"], "session-token");
assert.equal(calls[1].options.headers["Content-Type"], "application/json");
assert.equal(calls[2].options.headers["X-Game-SI-Token"], "session-token");
assert.equal(calls[2].options.headers["Content-Type"], undefined);
const reply = body => core.createApi("t", async () => ({ok: false, status: 400, json: async () => body}));
await assert.rejects(() => reply({error: "잘못된 요청"})("/x"), /잘못된 요청/);
await assert.rejects(() => reply({detail: "저장소 주소를 확인해 주세요."})("/x"), /저장소 주소/);
await assert.rejects(() => reply({detail: [{loc: ["body", "url"], msg: "Field required"}]})("/x"), /입력값을 확인/);
''')


def test_dates_and_clang_scope_options():
    run('''
assert.equal(core.jobDate(1791723600).getUTCFullYear(), 2026);
assert.equal(core.jobDate("2026-10-11T12:00:00Z").getUTCFullYear(), 2026);
assert.equal(core.jobDate(null), null); assert.equal(core.jobDate("not-a-date"), null);
assert.equal(core.buildAnalysisOptions({lang: "cpp", backend: "clang", subdir: "upload/src", local_path: "C:/Game", local_subdir: "src"}).subdir, "src");
assert.equal(core.buildAnalysisOptions({lang: "cpp", backend: "clang", subdir: "repo-SHA/src", local_path: "C:/Game"}).subdir, ".");
assert.equal(core.buildAnalysisOptions({lang: "cpp", backend: "tree-sitter", subdir: "Game/src", local_path: "C:/Game"}).subdir, "Game/src");
assert.equal(core.canInspectJob("failed"), true); assert.equal(core.canInspectJob("interrupted"), true);
''')


def test_diff_view_parses_side_by_side_and_dedents():
    script = r'''
const diff = await import(DIFF);
const rows = diff.parseUnified("--- a\n+++ b\n@@ -3,3 +3,3 @@\n \t\tkeep;\n-\t\told();\n+\t\tnew();\n \t\tend;\n");
assert.deepEqual(rows.map(r => r.type), ["hunk", "ctx", "chg", "ctx"]);
assert.deepEqual(rows[2].left, [4, "\t\told();"]); assert.deepEqual(rows[2].right, [4, "\t\tnew();"]);
const tidy = diff.dedent(rows);
assert.equal(tidy[2].left[1], "old();");
assert.deepEqual(diff.lineCounts({diff: "--- a\n+++ b\n@@ -1 +1,2 @@\n-x\n+y\n+z\n"}), {add: 2, rem: 1});
// Inside a hunk, "---x" is the removed line "--x", not a file header.
const dashes = "--- a\n+++ b\n@@ -1,2 +1,2 @@\n ctx\n---y\n+++z\n";
assert.deepEqual(diff.lineCounts({diff: dashes}), {add: 1, rem: 1});
assert.deepEqual(diff.parseUnified(dashes).map(r => r.type), ["hunk", "ctx", "chg"]);
assert.deepEqual(diff.parseUnified(dashes)[2].left, [2, "--y"]);
assert.deepEqual(diff.lineCounts({created: true, after: "a\nb\n"}), {add: 2, rem: 0});
'''.replace('DIFF', json.dumps((APP / 'diff.js').as_uri()))
    run(script)


def test_ai_connection_defaults_and_missing_fields():
    run('''
const rows = [{id: "codex", installed: false}, {id: "claude", installed: true, logged_in: true}, {id: "gemini", installed: true}, {id: "compatible", installed: false}];
assert.deepEqual(core.pickConnection(rows), {service: "claude", mode: "cli"});
// A program that is not on this PC is reached with an API key instead of being refused.
assert.deepEqual(core.pickConnection(rows, {service: "codex", mode: "cli"}), {service: "codex", mode: "api"});
assert.deepEqual(core.pickConnection(rows, {service: "compatible"}), {service: "compatible", mode: "api"});
assert.deepEqual(core.pickConnection([{id: "claude", installed: false}, {id: "compatible"}]), {service: "compatible", mode: "api"});
assert.equal(core.connectionProblem({service: "claude", mode: "cli"}), null);
assert.match(core.connectionProblem({service: "claude", mode: "api", model: "m"}), /API 키/);
assert.match(core.connectionProblem({service: "compatible", mode: "api", model: "m"}), /주소/);
assert.match(core.connectionProblem({service: "compatible", mode: "api", base_url: "http://localhost:11434/v1"}), /모델/);
assert.equal(core.connectionProblem({service: "compatible", mode: "api", base_url: "http://localhost:11434/v1", model: "llama3.1"}), null);
assert.equal(core.aiName("compatible", "llama3.1"), "llama3.1"); assert.equal(core.aiName("claude"), "Claude Code");
''')


def test_result_function_changes_put_the_most_reduced_first():
    run('''
assert.equal(core.shortName("id-Software-Quake-2.client.menu.Default_MenuKey"), "Default_MenuKey");
assert.equal(core.shortName("osu.Android.AndroidImportTask..ctor"), ".ctor");
assert.equal(core.shortName("main"), "main");
assert.equal(core.changePct(62, 24), -61); assert.equal(core.changePct(0, 3), null);
assert.equal(core.pctText(-61), "−61%"); assert.equal(core.pctText(12), "+12%"); assert.equal(core.pctText(null), "");
const changes = core.functionChanges([
  {name: "g.menu.M_IsSelectButton", before: null, after: {cc: 2, loc: 4}},
  {name: "g.menu.Small", before: {cc: 4, loc: 20}, after: {cc: 2, loc: 12}},
  {name: "g.menu.Default_MenuKey", before: {cc: 62, loc: 115}, after: {cc: 24, loc: 78}},
  {name: "g.menu.Grown", before: {cc: 3, loc: 10}, after: {cc: 5, loc: 14}},
  {name: "g.menu.Gone", before: {cc: 7, loc: 30}, after: null}]);
assert.deepEqual(changes.rows.map(r => r.kind), ["simpler", "simpler", "new", "worse", "removed"]);
assert.equal(changes.top.short, "Default_MenuKey"); assert.equal(changes.top.ccPct, -61); assert.equal(changes.top.locPct, -32);
assert.deepEqual(changes.totals.cc, [76, 33]); assert.deepEqual(changes.totals.loc, [175, 108]);
assert.equal(changes.counts.new, 1); assert.equal(changes.counts.worse, 1);
// Same branches, fewer lines: the length is the headline.
assert.equal(core.functionChanges([{name: "a.f", before: {cc: 5, loc: 40}, after: {cc: 5, loc: 30}}]).top.kind, "shorter");
assert.equal(core.functionChanges([{name: "a.f", before: null, after: {cc: 1, loc: 3}}]).top, null);
''')


def test_result_headline_leads_with_the_fixed_function():
    run('''
const fixed = core.functionChanges([{name: "q.menu.Default_MenuKey", before: {cc: 62, loc: 115}, after: {cc: 24, loc: 78}},
  {name: "q.menu.M_IsSelectButton", before: null, after: {cc: 2, loc: 4}}]);
let head = core.resultHeadline(fixed, {label: "파일", cycle: [0, 0], links: [11, 11]});
assert.equal(head.title, "Default_MenuKey 복잡도 62 → 24 (−61%)");
assert.match(head.lines.join(" "), /가장 크게 줄었습니다/); assert.match(head.lines.join(" "), /파일 사이의 연결과 순환 고리는 그대로/);
head = core.resultHeadline(fixed, {label: "클래스", cycle: [12, 10], links: [40, 38]});
assert.match(head.lines.join(" "), /순환 고리에 묶인 클래스가 12 → 10개로 줄어/);
// No function changed, but links between units did: the links lead.
head = core.resultHeadline(core.functionChanges([]), {label: "파일", cycle: [12, 10], links: [333, 320]});
assert.equal(head.title, "순환 고리에 묶인 파일 12 → 10개 (−17%)");
assert.match(head.lines.join(" "), /복잡도가 줄어든 함수는 없고/); assert.match(head.lines.join(" "), /연결도 333 → 320개/);
head = core.resultHeadline(core.functionChanges([]), {label: "파일", cycle: [2, 2], links: [224, 220]});
assert.equal(head.title, "파일 사이 연결 224 → 220개 (−2%)");
head = core.resultHeadline(core.functionChanges([]), {label: "파일", cycle: [2, 2], links: [224, 224]});
assert.equal(head.title, "측정값이 줄어든 곳이 없습니다"); assert.match(head.lines[0], /바뀐 함수가 없고/);
head = core.resultHeadline(core.functionChanges([{name: "a.f", before: {cc: 3, loc: 9}, after: {cc: 6, loc: 20}}]), {label: "파일", cycle: [0, 0], links: [5, 5]});
assert.equal(head.title, "복잡도가 줄어든 함수가 없습니다"); assert.match(head.lines[0], /오히려 복잡도가 늘었습니다/);
''')


def test_result_safety_badges_only_claim_what_was_checked():
    run('''
const checks = {original_preserved: true, matches_preview: true, reanalyzed: {state: "partial"}};
const round = more => ({revision: "r1", checks: {...checks, ...more}});
const states = list => Object.fromEntries(list.map(b => [b.key, b.state]));
// No registered game: no behaviour comparison badge, the build is the user's to check.
let badges = core.safetyBadges(round(), {available: false});
assert.deepEqual(badges.map(b => b.label), ["검사 규칙 통과", "원본 보존", "승인한 변경과 동일", "다시 분석", "빌드", "직접 플레이"]);
assert.deepEqual(states(badges), {rules: "ok", original: "ok", preview: "ok", reanalyzed: "ok", build: "todo", play: "todo"});
assert.equal(badges.find(b => b.key === "build").note, "직접 확인 필요");
// A build of another revision does not count; a build alone is not a behaviour comparison.
badges = core.safetyBadges(round(), {available: true, state: "complete", revision: "old"});
assert.equal(states(badges).build, "todo"); assert.equal(states(badges).behavior, "todo");
badges = core.safetyBadges(round(), {available: true, state: "complete", revision: "r1"});
assert.equal(states(badges).build, "ok"); assert.equal(states(badges).behavior, "todo");
badges = core.safetyBadges(round({play: {ok: true}}), {available: true, state: "complete", revision: "r1", behavior_checked: true});
assert.equal(states(badges).behavior, "ok"); assert.equal(states(badges).play, "ok");
assert.equal(states(core.safetyBadges(round({play: {ok: false}}), {available: false})).play, "bad");
assert.equal(core.safetyBadges({revision: "r1", checks: {}}, {available: false})[1].note, "확인 안 됨");
// A round saved before rounds were recorded has no check records, which is not a failed check.
const old = core.safetyBadges({revision: "r1", checks: {}, migrated: true}, {available: false});
assert.equal(old[1].state, "todo"); assert.equal(old[1].note, "기록 없음");
assert.equal(core.changeText(648, 649, "줄"), "+1줄"); assert.equal(core.changeText(62, 24), "−61%"); assert.equal(core.changeText(5, 5), "");
''')


# Just enough DOM for the page modules (ui.js h/fill, classList, querySelector by class or tag).
DOM_SHIM = r'''
class Node {}
class Text extends Node { constructor(text) { super(); this.data = String(text); } get textContent() { return this.data; } }
class Element extends Node {
  constructor(tag) {
    super(); this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {}; this.style = {}; this.dataset = {}; this.parentElement = null;
    const tokens = () => (this.attributes.class || "").split(/\s+/).filter(Boolean);
    this.classList = {contains: c => tokens().includes(c),
      toggle: (c, on) => { const t = tokens().filter(x => x !== c); if (on ?? !tokens().includes(c)) t.push(c); this.attributes.class = t.join(" "); }};
  }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k] ?? null; }
  addEventListener() {}
  append(...nodes) { for (const n of nodes) { const c = n instanceof Node ? n : new Text(n); c.parentElement = this; this.children.push(c); } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  get elements() { return this.children.filter(c => c instanceof Element); }
  get textContent() { return this.children.map(c => c.textContent).join(""); }
  set textContent(v) { this.replaceChildren(String(v)); }
  get isConnected() { return true; }
  querySelectorAll(sel) {
    const found = [], test = el => sel.startsWith(".") ? el.classList.contains(sel.slice(1)) : el.tagName === sel.toUpperCase();
    const walk = el => { for (const c of el.elements) { if (test(c)) found.push(c); walk(c); } };
    walk(this); return found;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
globalThis.Node = Node;
globalThis.document = {createElement: t => new Element(t), createElementNS: (_, t) => new Element(t), createTextNode: t => new Text(t),
  getElementById: () => null, body: new Element("body")};
const page = await import(PAGE);
const components = (cycle, links) => [["cycle_units", cycle], ["links", links], ["complex_functions", 40], ["excess_complexity", 900], ["global_access", 500]]
  .map(([key, after]) => ({key, label: key, before: after, after, included: true}));
async function show({functions, cycle = [0, 0], links = [11, 11], game = {available: false}}) {
  const unit = (si, cc) => ({fqn: "q.client.menu", file_path: "q/client/menu.c", si, raw: {cc, coupling: 1, dependency_cycle: 0}});
  const data = {
    "": {name: "Quake-2"}, "/assistant": {state: "complete", action: "apply"}, "/demo": game, "/diagnosis": {summary: {unit_label: "파일"}},
    "/rounds": {current: 1, rounds: [{round: 1, revision: "r1", files: ["q/client/menu.c"], checks: {original_preserved: true, matches_preview: true,
      reanalyzed: {state: "partial", analyzed_files: 187, syntax_files: 33}}, comparison: {before: [unit(98.93, 17.5)], after: [unit(98.93, 16.9)], functions}}]},
    "/tangle": {rounds: [{round: 0, active: true, index: 100, components: components(cycle[0], links[0]), same_units: true},
      {round: 1, active: true, index: 99.78, components: components(cycle[1], links[1]), same_units: true}]}};
  const view = document.createElement("main");
  const ctx = {setSteps() {}, setCrumb() {}, api: async url => data[url.replace("/api/jobs/job", "")]};
  await page.render(view, ctx, {jobId: "job"});
  return view;
}
'''


def run_page(script):
    run(DOM_SHIM.replace('PAGE', json.dumps((APP / 'page-result.js').as_uri())) + script)


def test_result_page_shows_the_fixed_function_before_the_whole_game_total():
    run_page(r'''
const view = await show({functions: [{name: "q.client.menu.Default_MenuKey", before: {cc: 62, loc: 115}, after: {cc: 24, loc: 78}},
  {name: "q.client.menu.M_IsSelectButton", before: null, after: {cc: 2, loc: 4}}]});
assert.equal(view.querySelector("h1").textContent, "Default_MenuKey 복잡도 62 → 24 (−61%)");
// Order: fixed place, safety, file scores, the whole game as an auxiliary measure, actions.
const main = view.querySelector(".layout").elements[0].elements.map(el => el.getAttribute("class"));
assert.deepEqual(main, ["card fix", "card safety", "card sec", "card sec aux", "actions"]);
const hero = view.querySelector(".fix").textContent;
assert.match(hero, /복잡도가 가장 크게 줄어든 함수/); assert.match(hero, /M_IsSelectButton/); assert.match(hero, /새로 만든 함수/);
assert.match(hero, /복잡도 62 → 26 \(−58%\)/); assert.match(hero, /115 →78줄/);
assert.ok(view.querySelectorAll(".pbars").length >= 3);
const badges = view.querySelectorAll(".badge").map(b => b.textContent);
assert.equal(badges[0], "✓완료: 검사 규칙 통과"); assert.ok(badges.some(t => t.includes("빌드") && t.includes("직접 확인 필요")));
assert.ok(view.querySelector(".play-ask"), "play can be recorded when no demo game is registered");
assert.ok(view.querySelector(".safety-more").textContent.includes("SHA-256"));
const aux = view.querySelector(".aux").textContent;
assert.match(aux, /보통 2% 미만/); assert.match(aux, /99\.78/); assert.match(aux, /엉킴 총량 구성 보기/);
const text = view.textContent;
for (const action of ["이 라운드 되돌리기", "진단 화면으로", "수정본 내려받기 (.zip)", "다음 처방 받기 →"]) assert.ok(text.includes(action), action);
''')


def test_result_page_without_function_changes_leads_with_links():
    run_page(r'''
let view = await show({functions: [], cycle: [12, 10], links: [333, 320]});
assert.equal(view.querySelector("h1").textContent, "순환 고리에 묶인 파일 12 → 10개 (−17%)");
assert.ok(view.querySelector(".fix-links")); assert.equal(view.querySelector(".fix-top"), null);
view = await show({functions: [], cycle: [2, 2], links: [224, 224]});
assert.equal(view.querySelector("h1").textContent, "측정값이 줄어든 곳이 없습니다");
assert.match(view.querySelector(".fix-links").textContent, /변화 없음/);
// A registered game that is not built yet: build and behaviour comparison wait, play cannot be recorded yet.
view = await show({functions: [], game: {available: true, state: "idle"}});
const open = view.querySelectorAll(".badge").filter(b => b.classList.contains("is-todo")).map(b => b.textContent);
assert.ok(open.some(t => t.includes("동작 비교"))); assert.equal(view.querySelector(".play-ask"), null);
''')
