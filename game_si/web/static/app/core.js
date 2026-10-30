// Pure helpers shared by the pages. No DOM access here, so they can be tested with Node.
export const DEFAULT_LIMITS = {archive_bytes: 104857600, source_bytes: 1073741824, files: 20000};
const EXCLUDED_DIRS = new Set([".git", "bin", "obj", "node_modules", "build", "packages", ".vs", "dist", "__pycache__", ".venv", "venv", "testresults"]);
const SOURCE_EXTENSION = /\.(cs|c|cc|cpp|cxx|h|hpp|hh|hxx|inl|inc)$/i;
export const LANGUAGE_LABELS = {csharp: "C#", c: "C", cpp: "C++"};
const STATE_LABELS = {importing: "소스 가져오는 중", ready: "범위 확인", running: "분석 중", complete: "분석 완료",
  partial: "부분 분석 완료", failed: "작업 실패", interrupted: "분석 중단"};
export const METRIC_LABELS = {cc: "복잡도(CC)", coupling: "연결된 파일", dependency_cycle: "순환 고리",
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
  return async function api(url, options = {}, retried = false) {
    const headers = {...options.headers};
    const post = Boolean(options.method && options.method.toUpperCase() === "POST");
    if (post) {
      headers["X-Game-SI-Token"] = token;
      if (typeof options.body === "string") headers["Content-Type"] = "application/json";
    }
    let response;
    try { response = await fetcher(url, {...options, headers, credentials: "same-origin"}); }
    catch (_) { throw new Error("앱에 연결할 수 없습니다. 로컬 서버가 실행 중인지 확인하고 다시 시도해 주세요."); }
    // The server makes a new token each time it starts: a page opened before a restart takes the new one
    // and asks once more instead of showing the refusal.
    if (response.status === 403 && post && !retried) {
      try {
        const fresh = await (await fetcher("/api/session", {credentials: "same-origin"})).json();
        if (fresh.token && fresh.token !== token) { token = fresh.token; return api(url, options, true); }
      } catch (_) { /* fall through to the refusal below */ }
    }
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

// What G-SI, its grades and "상위 N%" mean (grade limits mirror game_si/si.py `_grade`).
export const GRADE_RULES = [["A", "20 미만"], ["B", "20~40"], ["C", "40~60"], ["D", "60~80"], ["E", "80 이상"]];
export const GSI_HELP = "G-SI는 파일마다 매긴 엉킴 점수(0~100)입니다. 이 프로젝트 안에서의 순위라서, 높을수록 먼저 살펴볼 곳입니다.";
export const GRADE_HELP = `등급은 G-SI로 나눕니다: ${GRADE_RULES.map(([g, r]) => `${g} ${r}`).join(" · ")}.`;
export const TOP_HELP = "‘상위 N%’는 그 항목이 이 프로젝트의 전체 파일 중 높은 쪽 몇 %에 드는지입니다. 작을수록 더 심합니다.";

export function topText(unit, key) {
  return unit.raw[key] ? `상위 ${unit.top[key]}%` : "—";
}

// Place among all units for one measure: "2위" or "공동 2위 (6개)" (null when the value is 0 or unknown).
// The tie size says why a shared first place can still read "상위 12%".
export function placeText(unit, key) {
  const rank = unit.rank?.[key], ties = unit.tie_count?.[key];
  return unit.raw[key] && rank ? `${unit.tied?.[key] ? "공동 " : ""}${rank}위${unit.tied?.[key] && ties > 1 ? ` (${ties}개)` : ""}` : null;
}

// Short note under a card bar before the card is opened.
export function barNote(unit, key) {
  return unit.raw[key] ? {text: `상위 ${unit.top[key]}%`, hot: unit.top[key] <= 10} : {text: "없음", hot: false};
}

export function whyRows(unit, summary) {
  const label = summary.unit_label;
  const f = unit.functions[0];
  const raw = unit.raw;
  return [
    {key: "cc", label: METRIC_LABELS.cc, text: f ? `가장 복잡한 함수 ${f.name}의 복잡도 ${f.cc}` : "함수 정보 없음"},
    {key: "coupling", label: label === "파일" ? "연결된 파일" : "연결된 클래스",
     text: `부르는 ${label} ${unit.calls.length}개 · 불리는 ${label} ${unit.called_by.length}개`},
    {key: "dependency_cycle", label: METRIC_LABELS.dependency_cycle,
     text: unit.in_cycle ? `${unit.cycle_size || summary.cycle_size}개 ${label}의 고리 안에서 연결 ${raw.dependency_cycle}개` : "순환 고리 밖"},
    {key: "global_state", label: METRIC_LABELS.global_state,
     text: raw.global_state ? `전역 변수를 ${raw.global_state}번 읽고 바꿈` : "전역 변수 접근 없음"},
    {key: "game_loop_centrality", label: METRIC_LABELS.game_loop_centrality,
     text: raw.game_loop_centrality > 0 ? "매 프레임 실행 흐름과 가까움" : "이름으로 찾은 게임 루프 시작점에서 닿지 않음"},
  ].map(row => ({...row, top: topText(unit, row.key), place: placeText(unit, row.key)}));
}

export function barTone(pct) {
  return pct >= 85 ? "hot" : pct >= 60 ? "warm" : "cool";
}

// --- readable AI text ----------------------------------------------------
// A sentence ends at . ! ? before a space, the end, or Hangul ("좋다.그래서") — not inside "3.5" or "opentyr.h".
const SENTENCE_END = /(?<=[.!?])(?=\s|$|[가-힣])/;
// Code names inside Korean prose: file names, names with "_", camelCase/PascalCase, MACROS, name().
const CODE_NAME = /(\b[A-Za-z_]\w*\(\)|[\w./-]*\w\.(?:c|h|cpp|hpp|cc|cxx|cs)\b|\b[A-Za-z_]\w*_\w*\b|\b[a-z]+[A-Z]\w*\b|\b[A-Z][a-z0-9]+[A-Z]\w*\b|\b[A-Z]{2,}[a-z]\w*\b|\b[A-Z][A-Z0-9_]{2,}\b)/;

const WHOLE_CODE_NAME = new RegExp(`^${CODE_NAME.source}$`);
const PLAIN_WORDS = new Set(["API", "JSON", "HTML", "URL", "SDK", "ZIP", "LOC", "CPU", "GPU", "SHA", "UTF", "PDF", "CLI", "DLL", "EXE"]);

export function codeTokens(text) {
  // `code` written by the AI in Markdown is a code name as it stands; the backticks are not shown.
  return String(text || "").split(/`([^`\n]{1,200})`/).flatMap((part, i) => i % 2 ? [{code: part}]
    : part.split(CODE_NAME).filter(Boolean).map(p => WHOLE_CODE_NAME.test(p) && !PLAIN_WORDS.has(p) ? {code: p} : {text: p}));
}

// Why a file's change was turned down, in plain words, with what to do next. The program's own
// wording stays available as `detail`. Unknown reasons are shown as they are.
const PLAIN_REASONS = [
  [/시간을 초과|분 안에 답하지/, "AI가 제한 시간 안에 답을 끝내지 못했습니다. 원본은 그대로입니다. 다시 만들어 보거나 이 파일은 빼고 진행하세요."],
  [/실제 코드 편집\(edits\)을 보내지 않았/, "AI가 고치겠다고 설명만 하고 실제 코드 편집은 보내지 않았습니다."],
  [/대상 함수의 실제 변경을 확인할 수 없/,"AI가 고치겠다고 밝힌 함수를 실제로는 바꾸지 않았습니다(답이 중간에 끊겼거나 편집을 빠뜨림)."],
  [/수정 대상이 일치하지|대상 함수 밖|밖의 파일을 바꾸는|대상 .*함수를 실제 함수 목록에서/,
    "AI가 고치겠다고 밝힌 함수 말고 다른 곳까지 바꾸려 해서 받지 않았습니다(원본 보호 규칙)."],
  [/새 보조 함수는/, "AI가 새로 만든 함수가 안전 규칙(이 파일 안에서만 쓰고, 고친 함수에서 부르기)을 지키지 않아 받지 않았습니다."],
  [/제공한 코드 범위 밖|여러 곳에 나타납니다|변경할 코드가 없거나/, "AI가 바꿀 코드 위치를 정확히 짚지 못해 받지 않았습니다."],
  [/필수 내용이 누락|형식|해석하지 못했|요약을 확인하지/, "AI 답의 형식이 맞지 않아 받지 않았습니다."],
  [/사용 한도에 도달/, "AI 사용 한도에 도달해 답을 받지 못했습니다. 한도가 풀린 뒤(자세한 이유에 풀리는 시각) 이 파일만 다시 만들 수 있습니다."],
  [/요청을 취소/, "요청을 취소해 멈췄습니다."],
  [/로그인|사용 한도|요청이 완료되지|요청에 실패/, "AI 프로그램이 답하지 못했습니다. 로그인과 사용 한도를 확인한 뒤 다시 만들어 주세요."],
  [/전체 제한 시간이 지나/, "다른 파일을 처리하느라 정한 시간이 지나 시작하지 않았습니다. 이 파일만 다시 만들 수 있습니다."],
];
export function plainReason(error) {
  const text = String(error || "");
  const hit = PLAIN_REASONS.find(([pattern]) => pattern.test(text));
  return hit ? {text: hit[1], detail: text} : {text, detail: ""};
}

// AI prose as paragraphs of sentences. A line "[file.c] …" (one file of a change made per file)
// becomes its own paragraph with that file as the label. Nothing is dropped.
export function proseParts(text) {
  return String(text || "").split(/\n+/).map(line => line.trim()).filter(Boolean).map(line => {
    const tag = /^\[([^\]\n]{1,120})\]\s*/.exec(line);
    const body = tag ? line.slice(tag[0].length) : line;
    return {label: tag ? tag[1] : null,
      sentences: body.split(SENTENCE_END).map(s => s.trim()).filter(Boolean).map(codeTokens)};
  });
}

// --- result helpers ------------------------------------------------------
// A unit as people know it: the analyser's internal prefix ("clang.file.a.c") left out ("a.c").
export function unitDisplay(id) {
  return String(id || "").replace(/^[a-z-]+\.file\./, "");
}

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
    // Say what the list below holds: existing functions that got simpler and the new helper functions.
    const simpler = counts.simpler - 1, moved = `옮겨 간 코드는 새로 만든 함수 ${counts.new}개에 있습니다.`;
    const also = simpler > 0 && counts.new ? ` 기존 함수 ${simpler}개도 함께 단순해졌고, ${moved}`
      : simpler > 0 ? ` 기존 함수 ${simpler}개도 함께 단순해졌습니다.` : counts.new ? ` ${moved}` : "";
    lines.push(`이번 라운드에서 고친 함수 가운데 복잡도가 가장 크게 줄었습니다.${also}`);
  } else if (top) {
    title = `${top.short} 길이 ${top.before.loc} → ${top.after.loc}줄 (${changeText(top.before.loc, top.after.loc, "줄")})`;
    lines.push("복잡도(CC)는 그대로이고 함수 길이가 줄었습니다.");
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
// Gemini is one of the addresses under the other AIs (an API key); "gemini" stays only to name old records.
export const AI_LABELS = {claude: "Claude", codex: "ChatGPT (Codex)", compatible: "기타 AI (Gemini 등 · 주소로 연결)"};
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
  // Claude Code first, then Codex; a confirmed login beats an unknown one.
  const prefer = ["claude", "codex"];
  const programs = connections.filter(c => c.id !== "compatible")
    .sort((a, b) => (prefer.indexOf(a.id) + 1 || 99) - (prefer.indexOf(b.id) + 1 || 99));
  let service = ids.includes(saved.service) ? saved.service
    : (programs.find(c => c.installed && c.logged_in === true) || programs.find(c => c.installed && c.logged_in !== false)
      || programs.find(c => c.installed))?.id
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

// ------------------------------------------------------------ guided stages (result and finishing pages)
// The code a diff leaves after the change (context and added lines).
function afterCode(diff = "") {
  return diff.split("\n").filter(l => !/^(---|\+\+\+|@@)/.test(l) && !l.startsWith("-")).map(l => l.slice(1)).join("\n");
}

// A round that split functions, from its changed functions' code: each original function with the new
// helpers it now calls (directly, or through another new helper), and the numbers the page shows.
export function splitSummary(functions = []) {
  const created = functions.filter(f => f.created && f.after);
  const kept = functions.filter(f => !f.created && f.before && f.after);
  const code = new Map(functions.map(f => [f, afterCode(f.diff)]));
  // A call, with type arguments too (C# Helper<int>(…), C++ helper<T>(…)).
  const calls = (f, name) => new RegExp(`\\b${name.replace(/[^A-Za-z0-9_]/g, "")}\\s*(<[^<>();]*>)?\\s*\\(`).test(code.get(f));
  const parentOf = (helper, seen = new Set()) => {
    const direct = kept.find(f => f.file === helper.file && calls(f, helper.name));
    if (direct) return direct;
    seen.add(helper);
    for (const via of created.filter(f => f.file === helper.file && !seen.has(f) && calls(f, helper.name))) {
      const found = parentOf(via, seen);
      if (found) return found;
    }
    return null;
  };
  const targets = kept.map(f => ({...f, helpers: []}));
  const helpers = created.map(f => {
    const parent = parentOf(f);
    const row = {...f, parent: parent?.name || null};
    targets.find(t => t.file === parent?.file && t.name === parent?.name)?.helpers.push(row);
    return row;
  });
  const split = targets.filter(t => t.helpers.length).sort((a, b) => (b.before.loc - b.after.loc) - (a.before.loc - a.after.loc));
  const longest = split.reduce((m, t) => !m || t.before.loc > m.before.loc ? t : m, null);
  const avgLoc = helpers.length ? Math.round(helpers.reduce((s, h) => s + h.after.loc, 0) / helpers.length) : 0;
  // The example: a helper of the longest function, about the size of an average one.
  const example = longest ? [...longest.helpers].sort((a, b) => Math.abs(a.after.loc - avgLoc) - Math.abs(b.after.loc - avgLoc))[0] : null;
  return {targets: split, helpers, longest, avgLoc, simple: helpers.filter(h => h.after.cc <= 20).length, example};
}

// What to try in the game after the change, grouped by where in the game (checks without a place
// are grouped by file). Same action from two rounds is listed once.
export function playGroups(rounds = []) {
  const groups = new Map(), seen = new Set();
  for (const round of rounds) {
    for (const c of round.play_checks || []) {
      // The same action in two places is two checks; the same place and action from two stages is one.
      if (!c.action || seen.has(`${c.where}|${c.action}`)) continue;
      seen.add(`${c.where}|${c.action}`);
      const key = c.where || c.file.split("/").pop();
      if (!groups.has(key)) groups.set(key, {where: key, placed: Boolean(c.where), items: []});
      groups.get(key).items.push({key: `${key}: ${c.action}`, action: c.action, file: c.file, targets: c.targets || []});
    }
  }
  // Named places first (in the order the AI met them), then files.
  return [...groups.values()].sort((a, b) => b.placed - a.placed);
}

// Places any game has: offered in a problem report after this change's own checklist.
export const COMMON_PLACES = ["게임이 켜질 때", "처음 메뉴·설정", "게임 플레이 중", "저장·불러오기", "게임을 끌 때", "잘 모르겠어요"];
export const REPORT_KINDS = ["화면이 이상해요", "조작이 안 돼요", "멈추거나 꺼져요", "소리가 달라요", "기타"];

// The job steps already done (가져오기, 진단, AI 리팩토링, 단계 결과, 마무리), whichever page is open:
// a finished job keeps its checks when an earlier step is looked at again.
export function stepsReached(job, rounds) {
  const analysed = ["complete", "partial"].includes(job?.state), n = rounds?.current || 0;
  return [analysed, analysed, n > 0, n > 0, Boolean(n && rounds.rounds?.[n - 1]?.checks?.play?.ok)];
}
