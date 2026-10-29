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
assert.equal(rows[0].text, "가장 복잡한 함수 big의 복잡도 30"); assert.equal(rows[0].top, "상위 25%");
assert.equal(rows[3].text, "전역 변수 접근 없음"); assert.equal(rows[3].top, "—");
// Rank among all units, with ties; a zero value has no place.
const ranked = {...unit, rank: {cc: 2, coupling: 7, dependency_cycle: 1, global_state: 9, game_loop_centrality: 9}, tied: {cc: false, coupling: true}};
assert.equal(core.whyRows(ranked, {unit_label: "파일", cycle_size: 3})[0].place, "2위");
assert.equal(core.placeText(ranked, "coupling"), "공동 7위");
assert.equal(core.placeText({...ranked, tie_count: {coupling: 6}}, "coupling"), "공동 7위 (6개)");
assert.match(core.whyRows({...unit, cycle_size: 2}, {unit_label: "파일", cycle_size: 3})[2].text, /^2개 파일의 고리/);   // its own cycle assert.equal(core.placeText(ranked, "global_state"), null);
assert.equal(core.placeText(unit, "cc"), null);   // diagnosis saved before ranks existed
assert.deepEqual(core.barNote(unit, "cc"), {text: "상위 25%", hot: false});
assert.deepEqual(core.barNote({...unit, top: {...unit.top, cc: 4}}, "cc"), {text: "상위 4%", hot: true});
assert.deepEqual(core.barNote(unit, "global_state"), {text: "없음", hot: false});
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
// Codex found inside its desktop app and logged in: Claude Code is still the first choice, Codex next.
assert.deepEqual(core.pickConnection([{id: "codex", installed: true, logged_in: true}, {id: "claude", installed: true, logged_in: true}]), {service: "claude", mode: "cli"});
assert.deepEqual(core.pickConnection([{id: "codex", installed: true, logged_in: true}, {id: "claude", installed: true, logged_in: false}, {id: "gemini", installed: true}]), {service: "codex", mode: "cli"});
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


def test_ai_prose_is_split_into_sentences_with_code_names_and_file_labels():
    run('''
const parts = core.proseParts("opentyr.h에는 COUNTOF·MIN 매크로가 있습니다.그래서 keyboard.h도 3.5배 엮입니다. API 키는 쓰지 않습니다.\\n[varz.c] JE_doSpecialShot와 redrawShieldArmorBars()를 나눕니다.");
assert.equal(parts.length, 2);
assert.equal(parts[0].label, null); assert.equal(parts[0].sentences.length, 3);
assert.deepEqual(parts[0].sentences[0], [{code: "opentyr.h"}, {text: "에는 "}, {code: "COUNTOF"}, {text: "·"}, {code: "MIN"}, {text: " 매크로가 있습니다."}]);
assert.ok(parts[0].sentences[1].some(t => t.code === "keyboard.h") && parts[0].sentences[1].some(t => t.text && t.text.includes("3.5배")));
assert.ok(parts[0].sentences[2].every(t => !t.code));   // "API" is a plain word, not code
assert.equal(parts[1].label, "varz.c");
assert.deepEqual(parts[1].sentences[0].filter(t => t.code).map(t => t.code), ["JE_doSpecialShot", "redrawShieldArmorBars()"]);
// Nothing is lost: joining the pieces gives the text back.
const join = p => p.sentences.map(s => s.map(t => t.code || t.text).join("")).join(" ");
assert.equal(join(parts[1]), "JE_doSpecialShot와 redrawShieldArmorBars()를 나눕니다.");
assert.deepEqual(core.codeTokens("ESCPressed와 setupMenu, M_PI"), [{code: "ESCPressed"}, {text: "와 "}, {code: "setupMenu"}, {text: ", "}, {code: "M_PI"}]);
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
assert.equal(core.unitDisplay("clang.file.video_scale_hqNx.c"), "video_scale_hqNx.c");
assert.equal(core.unitDisplay("tree-sitter.file.a.c"), "a.c"); assert.equal(core.unitDisplay("Game.Menu"), "Game.Menu");
''')


def test_result_headline_leads_with_the_fixed_function():
    run('''
const fixed = core.functionChanges([{name: "q.menu.Default_MenuKey", before: {cc: 62, loc: 115}, after: {cc: 24, loc: 78}},
  {name: "q.menu.M_IsSelectButton", before: null, after: {cc: 2, loc: 4}}]);
let head = core.resultHeadline(fixed, {label: "파일", cycle: [0, 0], links: [11, 11]});
assert.equal(head.title, "Default_MenuKey 복잡도 62 → 24 (−61%)");
assert.match(head.lines.join(" "), /가장 크게 줄었습니다/); assert.match(head.lines.join(" "), /파일 사이의 연결과 순환 고리는 그대로/);
assert.match(head.lines[0], /새로 만든 함수 1개에 있습니다[.]$/);   // the list below holds the new helper
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
    "/rounds/1/changes": {functions: [
      {file: "q/client/menu.c", name: "Default_MenuKey", before: {cc: 62, loc: 115}, after: {cc: 24, loc: 78}, created: false,
       diff: ["--- 원본/q/client/menu.c", "+++ 수정본/q/client/menu.c", "@@ -1,2 +1,2 @@", " int Default_MenuKey(void)",
              "-    if (old) return 1;", "+    return M_IsSelectButton();", ""].join(String.fromCharCode(10))},
      {file: "q/client/menu.c", name: "M_IsSelectButton", created: true,
       diff: ["--- a", "+++ b", "@@ -0,0 +1,2 @@", "+static int M_IsSelectButton(void)", "+{ return 1; }", ""].join(String.fromCharCode(10))}]},
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
// The changed functions' code arrives after the page is drawn and shows inside the first card.
await new Promise(resolve => setTimeout(resolve, 0));
const code = view.querySelector(".fix").querySelector(".fix-code");
assert.ok(code, "code view");
assert.deepEqual(code.querySelector(".code-tabs").elements.map(b => b.textContent), ["Default_MenuKey · 62 → 24", "M_IsSelectButton · 새 함수"]);
assert.match(code.textContent, /복잡도 62 → 24 · 길이 115 → 78줄/); assert.ok(code.textContent.includes("return M_IsSelectButton();"));
''')


def test_per_file_progress_rows_show_state_size_and_reasons():
    run(DOM_SHIM.replace('const page = await import(PAGE);', '').replace('PAGE', '""') + r'''
const refactor = await import(REFACTOR);
const rows = refactor.workerRows([
  {label: "tyrian2.c", state: "running", mode: "full", sent_kb: 123, file_kb: 123, started_at: Date.now() / 1000 - 65, targets: ["JE_main"]},
  {label: "mainint.c", state: "done", mode: "focused", sent_kb: 95, file_kb: 410, seconds: 200, targets: ["JE_playerMovement"], helpers: ["move_ship"], skipped_targets: ["JE_huge"]},
  {label: "opentyr.c", state: "no_changes", seconds: 30, error: "setupMenu는 이미 표로 나뉘어 있습니다."},
  {label: "varz.c", state: "failed", error: "varz.h 밖의 파일을 바꾸는 변경은 적용할 수 없습니다."}]).elements;
assert.deepEqual(rows.map(r => r.getAttribute("class")), ["worker t-busy", "worker t-ok", "worker t-muted", "worker t-bad"]);   // never the global "ok"
const text = rows.map(r => r.textContent);
assert.match(text[0], /작성 중/); assert.match(text[0], /통째로 보냄 · 123KB/); assert.match(text[0], /1분 5초|1분 4초/); assert.match(text[0], /JE_main/);
assert.match(text[1], /큰 파일 · 대상 함수는 통째로 · 95KB \/ 410KB/); assert.match(text[1], /move_ship/); assert.match(text[1], /보내지 못한 함수: JE_huge/);
assert.match(text[2], /바꿀 곳 없음/); assert.match(text[2], /이미 표로/);
assert.match(text[3], /거절/); assert.ok(rows[3].querySelector(".werr").querySelector("code"));
'''.replace('REFACTOR', json.dumps((APP / 'page-refactor.js').as_uri())))


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


def test_each_step_suggests_a_model_that_fits_it():
    # The prescription judges (a stronger model, short answer); the change writes long code by rules (a lighter one).
    run(f'''
const {{stepAdvice}} = await import({json.dumps((APP / "prescription.js").as_uri())});
assert.equal(stepAdvice("claude", "refactor").pick, "sonnet");
assert.equal(stepAdvice("claude", "prescription").pick, undefined);   // left empty: Opus
assert.equal(stepAdvice("gemini", "refactor").pick, "flash");
assert.equal(stepAdvice("gemini", "prescription").pick, "pro");
const codex = ["gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"];
const fix = stepAdvice("codex", "refactor", codex), plan = stepAdvice("codex", "prescription", codex);
assert.equal(fix.pick, "gpt-6.1-sol"); assert.notEqual(fix.auto, false); assert.match(fix.text, /gpt-6-luna는 .*권하지 않습니다/);
assert.equal(plan.pick, "gpt-6-astra"); assert.equal(plan.auto, false);
assert.equal(stepAdvice("codex", "refactor", []).pick, undefined);   // unknown models: nothing named
assert.equal(stepAdvice("compatible", "refactor"), null);
''')


def test_rejection_reasons_are_said_plainly_with_the_original_kept():
    run('''
const timeout = core.plainReason("AI가 15분 안에 답하지 못했습니다. 원본은 그대로이며, 이 파일만 다시 만들거나 빼고 진행할 수 있습니다.");
assert.match(timeout.text, /제한 시간/); assert.match(timeout.detail, /15분/);
assert.match(core.plainReason("실제 변경 함수와 파일별 수정 대상이 일치하지 않습니다.").text, /다른 곳까지/);
assert.match(core.plainReason("선언한 대상 함수 밖의 기존 코드 변경은 승인할 수 없습니다.").text, /원본 보호/);
assert.match(core.plainReason("새 보조 함수는 정적 함수이며 설명에 이름이 있고 변경된 대상 함수에서 실제 호출되어야 합니다.").text, /안전 규칙/);
assert.match(core.plainReason("AI 안내의 필수 내용이 누락되었거나 너무 깁니다.").text, /형식/);
const other = core.plainReason("처음 보는 이유");
assert.equal(other.text, "처음 보는 이유"); assert.equal(other.detail, "");
''')


def test_backticked_code_from_the_ai_shows_as_code_without_backticks():
    run('''
const parts = core.codeTokens("앞부분 `if (i > 0)` 조건과 `w[2]` 값을 옮깁니다.");
assert.deepEqual(parts.filter(p => p.code).map(p => p.code), ["if (i > 0)", "w[2]"]);
assert.ok(!parts.some(p => (p.text || "").includes("`")));
''')


def test_grade_help_matches_the_scoring_thresholds():
    from game_si.si import _grade
    run('''
const rules = core.GRADE_RULES.map(([g]) => g).join("");
assert.equal(rules, "ABCDE");
assert.ok(core.GRADE_HELP.includes("E 80 이상") && core.GRADE_HELP.includes("A 20 미만"));
assert.ok(core.GSI_HELP.includes("0~100") && core.TOP_HELP.includes("상위"));
''')
    assert [_grade(s) for s in (19.9, 20, 40, 60, 80)] == list('ABCDE')


def test_map_zooms_with_the_wheel_and_import_waits_for_a_source():
    source = (APP / 'map.js').read_text(encoding='utf-8')
    assert 'canvas.addEventListener("wheel", e => { e.preventDefault();' in source   # user's choice: plain wheel zooms
    page = (APP / 'page-import.js').read_text(encoding='utf-8')
    assert 'importButton.disabled = Boolean(busy) || !ready' in page
    assert 'hero.hidden = Boolean(job)' in page
    css = (APP / 'app.css').read_text(encoding='utf-8')
    assert '.diffcard .diff { min-height:' in css


def test_a_page_opened_before_a_server_restart_takes_the_new_token_once():
    run('''
const sent = [];
const reply = (status, body) => ({status, ok: status < 400, json: async () => body});
const fetcher = async (url, options = {}) => {
  sent.push([url, options.headers?.["X-Game-SI-Token"] || ""]);
  if (url === "/api/session") return reply(200, {token: "new"});
  return options.headers["X-Game-SI-Token"] === "new" ? reply(202, {id: "job"}) : reply(403, {detail: "refused"});
};
const api = core.createApi("old", fetcher);
assert.deepEqual(await api("/api/jobs/x/start", {method: "POST", body: "{}"}), {id: "job"});
assert.deepEqual(sent, [["/api/jobs/x/start", "old"], ["/api/session", ""], ["/api/jobs/x/start", "new"]]);
// a refusal that a fresh token does not fix is shown, without asking again and again
const stuck = core.createApi("new", async url => url === "/api/session" ? reply(200, {token: "new"}) : reply(403, {detail: "refused"}));
await assert.rejects(stuck("/api/x", {method: "POST", body: "{}"}), /refused/);
''')
