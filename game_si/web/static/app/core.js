// Pure helpers shared by the pages. No DOM access here, so they can be tested with Node.
export const DEFAULT_LIMITS = {archive_bytes: 104857600, source_bytes: 1073741824, files: 20000};
const EXCLUDED_DIRS = new Set([".git", "bin", "obj", "node_modules", "build", "packages", ".vs", "dist", "__pycache__", ".venv", "venv", "testresults"]);
const SOURCE_EXTENSION = /\.(cs|c|cc|cpp|cxx|h|hpp|hh|hxx|inl|inc)$/i;
export const LANGUAGE_LABELS = {csharp: "C#", c: "C", cpp: "C++"};
const STATE_LABELS = {importing: "소스 가져오는 중", ready: "범위 확인", running: "분석 중", complete: "분석 완료",
  partial: "부분 분석 완료", failed: "작업 실패", interrupted: "분석 중단"};
export const METRIC_LABELS = {cc: "분기 복잡도", coupling: "연결된 파일", dependency_cycle: "순환 고리",
  global_state: "전역 변수 접근", game_loop_centrality: "게임 루프 근접"};
export const METRIC_KEYS = Object.keys(METRIC_LABELS);

export function relativePath(value) {
  const path = String(value || "").replace(/\\/g, "/");
  if (!path || path.startsWith("/") || /^[a-z]:/i.test(path) || path.includes("\0") || path.split("/").some(part => !part || part === "." || part === "..")) {
    throw new Error("파일 경로를 확인할 수 없습니다. 소스 폴더를 다시 선택해 주세요.");
  }
  return path;
}

export function isSourcePath(path) {
  const parts = path.split("/");
  return !parts.some(part => EXCLUDED_DIRS.has(part.toLowerCase()) || part.toLowerCase().startsWith(".env")) && SOURCE_EXTENSION.test(path);
}

export function prepareUpload(items, kind, limits = {}) {
  const cap = {...DEFAULT_LIMITS, ...limits};
  const candidates = Array.from(items || []);
  if (kind === "zip") {
    if (candidates.length !== 1) throw new Error("ZIP 파일 하나를 선택해 주세요.");
    const file = candidates[0].file || candidates[0];
    if (!/\.zip$/i.test(file.name || "")) throw new Error("ZIP 형식의 파일을 선택해 주세요.");
    if (file.size > cap.archive_bytes) throw new Error("ZIP 크기 제한을 초과했습니다. 더 작은 범위의 소스를 가져와 주세요.");
    return {files: [file], paths: [relativePath(file.name)], bytes: file.size, skipped: 0, kind};
  }
  const files = [], paths = [];
  let bytes = 0, skipped = 0;
  for (const item of candidates) {
    const file = item.file || item;
    const rawPath = item.path || file.webkitRelativePath;
    if (!rawPath) throw new Error("폴더의 상대 경로를 확인할 수 없습니다. ‘폴더 선택’ 버튼으로 다시 가져와 주세요.");
    const path = relativePath(rawPath);
    if (!isSourcePath(path)) { skipped++; continue; }
    files.push(file);
    paths.push(path);
    bytes += file.size;
    if (files.length > cap.files) throw new Error("소스 파일 개수 제한을 초과했습니다. 하위 폴더를 선택해 주세요.");
    if (bytes > cap.source_bytes) throw new Error("폴더 크기 제한을 초과했습니다. 더 작은 소스 폴더를 선택해 주세요.");
  }
  if (!files.length) throw new Error("분석할 C#, C, C++ 소스 또는 헤더가 없습니다.");
  return {files, paths, bytes, skipped, kind: "folder"};
}

export async function readDroppedEntries(entries, limits = {}) {
  const cap = {...DEFAULT_LIMITS, ...limits};
  const files = [];
  let bytes = 0;
  async function visit(entry, parent = "") {
    const path = relativePath(parent ? `${parent}/${entry.name}` : entry.name);
    if (entry.isDirectory) {
      if (EXCLUDED_DIRS.has(entry.name.toLowerCase()) || entry.name.toLowerCase().startsWith(".env")) return;
      const reader = entry.createReader();
      // Chromium returns at most 100 entries in one batch; drain the reader.
      while (true) {
        const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
        if (!batch.length) break;
        for (const child of batch) await visit(child, path);
      }
    } else if (entry.isFile && isSourcePath(path)) {
      if (files.length >= cap.files) throw new Error("소스 파일 개수 제한을 초과했습니다. 하위 폴더를 선택해 주세요.");
      const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
      bytes += file.size;
      if (bytes > cap.source_bytes) throw new Error("폴더 크기 제한을 초과했습니다. 더 작은 소스 폴더를 선택해 주세요.");
      files.push({file, path});
    }
  }
  for (const entry of entries) await visit(entry);
  return files;
}

export function safeResultUrl(value) {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//") || /[\\\u0000- ]/.test(value)) return null;
  return /^\/(?:results\/[a-z0-9]+|examples\/[a-z0-9-]+)\/(?:index|validation|timeseries)\.html$/.test(value) ? value : null;
}

export function reportUrl(value, theme) {
  const path = safeResultUrl(value);
  return path ? `${path}?theme=${theme === "dark" ? "dark" : "blue"}` : null;
}

export function formatSourceSize(bytes) {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) return "미확인";
  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(1)} GiB`;
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MiB`;
  return bytes >= 1024 ? `${(bytes / 1024).toFixed(1)} KiB` : `${bytes} B`;
}

export function jobDate(value) {
  if (value === null || value === undefined || value === "") return null;
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function sortJobs(jobs, order = "latest") {
  const latest = (a, b) => (jobDate(b.created_at)?.getTime() || 0) - (jobDate(a.created_at)?.getTime() || 0);
  return [...jobs].sort((a, b) => {
    if (order === "name") return String(a.name || "").localeCompare(String(b.name || ""), "ko") || latest(a, b);
    if (order === "size") {
      const size = job => formatSourceSize(job.scan?.source_bytes) === "미확인" ? null : job.scan.source_bytes;
      const left = size(a), right = size(b);
      if (left === null && right !== null) return 1;
      if (right === null && left !== null) return -1;
      return (right ?? 0) - (left ?? 0) || latest(a, b);
    }
    return latest(a, b);
  });
}

export function groupExamples(examples) {
  const projects = [], auxiliary = [];
  for (const example of examples) {
    if (example.auxiliary) { auxiliary.push(example); continue; }
    let group = projects.find(item => item.project === example.project);
    if (!group) { group = {...example, examples: []}; projects.push(group); }
    group.examples.push(example);
  }
  return {projects, auxiliary};
}

export function elapsedText(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  return s >= 60 ? `${Math.floor(s / 60)}분 ${s % 60}초` : `${s}초`;
}

export function statusView(job) {
  return {
    title: STATE_LABELS[job.state] || "상태 확인 필요",
    stage: typeof job.stage === "string" ? job.stage : "상태를 확인하고 있습니다.",
    elapsed: elapsedText(job.elapsed_seconds),
    busy: ["importing", "running"].includes(job.state),
    result: ["complete", "partial"].includes(job.state),
  };
}

export function canInspectJob(state) {
  return ["ready", "importing", "running", "failed", "interrupted"].includes(state);
}

export function buildAnalysisOptions(values) {
  const payload = {lang: values.lang, backend: values.backend, subdir: values.subdir};
  if (values.backend === "clang") {
    payload.local_path = (values.local_path || "").trim();
    payload.compile_commands = (values.compile_commands || "").trim();
    payload.clang_library = (values.clang_library || "").trim();
    if (payload.local_path) payload.subdir = (values.local_subdir || ".").trim() || ".";
  }
  return payload;
}

export function parseGithubUrl(value) {
  let url = String(value || "").trim();
  if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
  let parsed;
  try { parsed = new URL(url); } catch (_) { parsed = null; }
  if (!parsed || parsed.protocol !== "https:" || parsed.hostname !== "github.com" || parsed.username || parsed.password
      || parsed.pathname.split("/").filter(Boolean).length !== 2) {
    throw new Error("공개 GitHub 저장소 주소를 입력해 주세요. 예: github.com/owner/repository");
  }
  return parsed.href;
}

export function createApi(token, fetcher = globalThis.fetch) {
  return async function api(url, options = {}) {
    const headers = {...options.headers};
    if (options.method && options.method.toUpperCase() === "POST") {
      headers["X-Game-SI-Token"] = token;
      if (typeof options.body === "string") headers["Content-Type"] = "application/json";
    }
    let response;
    try { response = await fetcher(url, {...options, headers, credentials: "same-origin"}); }
    catch (_) { throw new Error("앱에 연결할 수 없습니다. 로컬 서버가 실행 중인지 확인하고 다시 시도해 주세요."); }
    let data;
    try { data = await response.json(); }
    catch (_) { throw new Error("앱 응답을 읽을 수 없습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요."); }
    if (!response.ok) {
      const message = typeof data.detail === "string" ? data.detail
        : Array.isArray(data.detail) ? "입력값을 확인해 주세요. 필수 항목이나 경로 형식이 올바르지 않습니다."
        : typeof data.error === "string" ? data.error
        : data.error?.message || data.message || "요청을 처리하지 못했습니다.";
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return data;
  };
}

// --- diagnosis helpers ---------------------------------------------------
// Korean particles for the unit label ("파일" / "클래스").
export function subj(label) { return label + (label === "파일" ? "이" : "가"); }
export function obj(label) { return label + (label === "파일" ? "을" : "를"); }

export function topText(unit, key) {
  return unit.raw[key] ? `상위 ${unit.top[key]}%` : "—";
}

export function whyRows(unit, summary) {
  const label = summary.unit_label;
  const f = unit.functions[0];
  const raw = unit.raw;
  return [
    {key: "cc", label: METRIC_LABELS.cc, text: f ? `가장 복잡한 함수 ${f.name}의 분기 ${f.cc}개` : "함수 정보 없음"},
    {key: "coupling", label: label === "파일" ? "연결된 파일" : "연결된 클래스",
     text: `부르는 ${label} ${unit.calls.length}개 · 불리는 ${label} ${unit.called_by.length}개`},
    {key: "dependency_cycle", label: METRIC_LABELS.dependency_cycle,
     text: unit.in_cycle ? `${summary.cycle_size}개 ${label}의 고리 안에서 연결 ${raw.dependency_cycle}개` : "순환 고리 밖"},
    {key: "global_state", label: METRIC_LABELS.global_state,
     text: raw.global_state ? `여러 곳이 함께 쓰는 변수를 ${raw.global_state}번 읽고 바꿈` : "전역 상태 접근 없음"},
    {key: "game_loop_centrality", label: METRIC_LABELS.game_loop_centrality,
     text: raw.game_loop_centrality > 0 ? "매 프레임 실행 흐름과 가까움" : "게임 루프와 직접 닿지 않음"},
  ].map(row => ({...row, top: topText(unit, row.key)}));
}

export function barTone(pct) {
  return pct >= 85 ? "hot" : pct >= 60 ? "warm" : "cool";
}

// --- result helpers ------------------------------------------------------
// Function name without its owner ("game.menu.Default_MenuKey" → "Default_MenuKey", C# "A.B..ctor" → ".ctor").
export function shortName(fqn) {
  const name = String(fqn || "");
  return name.match(/\.(\.?[^.]+)$/)?.[1] || name;
}

// Signed whole-percent change, or null when there is no base to compare with.
export function changePct(before, after) {
  return before > 0 ? Math.round(100 * (after - before) / before) : null;
}

export function pctText(pct) {
  return pct === null ? "" : pct < 0 ? `−${-pct}%` : pct > 0 ? `+${pct}%` : "0%";
}

// "−61%", or the difference itself when it rounds to 0% (648 → 649줄 is "+1줄", not "0%").
export function changeText(before, after, unit = "") {
  const pct = changePct(before, after), diff = after - before;
  return pct ? pctText(pct) : diff ? `${diff < 0 ? "−" : "+"}${Math.abs(diff).toLocaleString()}${unit}` : "";
}

// The round's changed functions, the most reduced first. kind: simpler (CC down), shorter (same CC,
// fewer lines), new, worse (CC up), removed, other (same CC, not shorter).
const KIND_ORDER = {simpler: 0, shorter: 1, new: 2, worse: 3, removed: 4, other: 5};
export function functionChanges(functions = []) {
  const rows = functions.map(f => {
    const b = f.before, a = f.after;
    const kind = !b ? "new" : !a ? "removed" : a.cc < b.cc ? "simpler" : a.cc > b.cc ? "worse" : a.loc < b.loc ? "shorter" : "other";
    return {name: f.name, short: shortName(f.name), before: b, after: a, kind,
      ccPct: b && a ? changePct(b.cc, a.cc) : null, locPct: b && a ? changePct(b.loc, a.loc) : null,
      ccDrop: b && a ? b.cc - a.cc : 0, locDrop: b && a ? b.loc - a.loc : 0};
  });
  rows.sort((x, y) => KIND_ORDER[x.kind] - KIND_ORDER[y.kind] || y.ccDrop - x.ccDrop || y.locDrop - x.locDrop
    || x.short.localeCompare(y.short));
  const total = (side, key) => rows.reduce((sum, r) => sum + (r[side]?.[key] || 0), 0);
  const counts = Object.fromEntries(Object.keys(KIND_ORDER).map(kind => [kind, rows.filter(r => r.kind === kind).length]));
  return {rows, counts, top: ["simpler", "shorter"].includes(rows[0]?.kind) ? rows[0] : null,
    totals: {cc: [total("before", "cc"), total("after", "cc")], loc: [total("before", "loc"), total("after", "loc")]}};
}

// Title and explanation for the result page: the fixed function first, then links between units.
// cycle and links are [previous round, this round].
export function resultHeadline(changes, {label, cycle, links}) {
  const {top, counts} = changes;
  const cut = cycle[1] < cycle[0], cutLinks = links[1] < links[0];
  const lines = [];
  let title;
  if (top?.kind === "simpler") {
    title = `${top.short} 복잡도 ${top.before.cc} → ${top.after.cc} (${changeText(top.before.cc, top.after.cc)})`;
    lines.push(counts.simpler > 1 ? `이번 라운드에서 고친 함수 가운데 가장 크게 줄었고, 함수 ${counts.simpler - 1}개도 함께 단순해졌습니다.`
      : "이번 라운드에서 고친 함수 가운데 복잡도가 가장 크게 줄었습니다.");
  } else if (top) {
    title = `${top.short} 길이 ${top.before.loc} → ${top.after.loc}줄 (${changeText(top.before.loc, top.after.loc, "줄")})`;
    lines.push("분기 수(복잡도)는 그대로이고 함수 길이가 줄었습니다.");
  } else if (cut || cutLinks) {
    const [a, b] = cut ? cycle : links;
    title = `${cut ? `순환 고리에 묶인 ${label}` : `${label} 사이 연결`} ${a} → ${b}개 (${changeText(a, b, "개")})`;
    lines.push(`복잡도가 줄어든 함수는 없고, ${label} 사이의 연결을 정리한 수정입니다.`);
  } else {
    title = counts.worse ? "복잡도가 줄어든 함수가 없습니다" : "측정값이 줄어든 곳이 없습니다";
    lines.push(counts.worse ? `함수 ${counts.worse}개는 오히려 복잡도가 늘었습니다. 아래에서 확인하고, 필요하면 이 라운드를 되돌려 주세요.`
      : changes.rows.length ? `바뀐 함수는 있지만 복잡도나 길이가 줄지 않았고, ${label} 사이의 연결과 순환 고리도 그대로입니다.`
      : `이번 수정으로 복잡도나 길이가 바뀐 함수가 없고, ${label} 사이의 연결과 순환 고리도 그대로입니다.`);
  }
  if (counts.worse && (top || cut || cutLinks)) lines.push(`함수 ${counts.worse}개는 복잡도가 늘었습니다. 아래에서 확인해 주세요.`);
  if (top) {
    lines.push(cut ? `순환 고리에 묶인 ${subj(label)} ${cycle[0]} → ${cycle[1]}개로 줄어, 한 곳을 고칠 때 영향이 퍼지는 범위도 좁아졌습니다.`
      : cutLinks ? `${label} 사이 연결도 ${links[0]} → ${links[1]}개로 줄어, 한 곳을 고칠 때 영향이 퍼지는 범위가 좁아졌습니다.`
      : `${label} 안을 정리한 수정이라 ${label} 사이의 연결과 순환 고리는 그대로입니다.`);
  } else if (cut && cutLinks) {
    lines.push(`${label} 사이 연결도 ${links[0]} → ${links[1]}개로 줄었습니다.`);
  }
  return {title, lines};
}

// One-line safety summary of a round. state: ok | todo | bad; note says what is still open.
// Every applied change passed the change rules: a reply that fails them never becomes a change to approve.
// A round saved before rounds were recorded (migrated) has no check records.
export function safetyBadges(round = {}, game = {}) {
  const checks = round.checks || {};
  const built = Boolean(game.available && game.state === "complete" && game.revision === round.revision);
  const done = (key, label, ok, note = "") => ({key, label, state: ok ? "ok" : "todo", note: ok ? "" : note});
  const unknown = round.migrated ? "기록 없음" : "확인 안 됨";
  const play = checks.play;
  return [
    done("rules", "검사 규칙 통과", true),
    done("original", "원본 보존", checks.original_preserved, unknown),
    done("preview", "승인한 변경과 동일", checks.matches_preview, unknown),
    done("reanalyzed", "다시 분석", ["complete", "partial"].includes(checks.reanalyzed?.state), unknown),
    done("build", "빌드", built, game.available ? "게임 준비 전" : "직접 확인 필요"),
    game.available ? done("behavior", "동작 비교", built && game.behavior_checked, built ? "기록 없음" : "게임 준비 전") : null,
    play && !play.ok ? {key: "play", label: "직접 플레이", state: "bad", note: "문제 있음"} : done("play", "직접 플레이", play?.ok, "기록 전"),
  ].filter(Boolean);
}

// ---------------------------------------------------------------- AI connection
export const AI_LABELS = {claude: "Claude", codex: "ChatGPT (Codex)", gemini: "Gemini", compatible: "다른 AI (주소로 연결)"};
const PROGRAM_NAMES = {claude: "Claude Code", codex: "Codex", gemini: "Gemini CLI"};

// Name shown next to a result: the program, or the model for an address-based connection.
export function aiName(service, model = "") {
  if (service === "compatible") return model || "다른 AI";
  return PROGRAM_NAMES[service] || service || "";
}

// First choice when nothing is remembered: a program on this PC that is logged in, then any
// program on this PC, then a connection by address. A program that is not on this PC is reached
// with an API key instead, so the request can still go through.
export function pickConnection(connections, saved = {}) {
  const ids = connections.map(c => c.id);
  const programs = connections.filter(c => c.id !== "compatible");
  let service = ids.includes(saved.service) ? saved.service
    : (programs.find(c => c.installed && c.logged_in !== false) || programs.find(c => c.installed))?.id
      || (ids.includes("compatible") ? "compatible" : ids[0] || "claude");
  const chosen = connections.find(c => c.id === service);
  let mode = saved.service === service && saved.mode === "api" ? "api" : "cli";
  if (service === "compatible" || (chosen && !chosen.installed)) mode = "api";
  return {service, mode};
}

// What is still missing before the request can be sent (null when complete).
export function connectionProblem(value) {
  if (value.service === "compatible") {
    if (!value.base_url) return "연결할 AI의 주소를 입력해 주세요.";
    if (!value.model) return "사용할 모델 이름을 입력해 주세요. ‘모델 목록 불러오기’로 고를 수 있습니다.";
    return null;
  }
  if (value.mode === "api" && (!value.api_key || !value.model)) return "API 키와 모델 이름을 입력해 주세요.";
  return null;
}
