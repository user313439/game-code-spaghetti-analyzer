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
