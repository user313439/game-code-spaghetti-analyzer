"use strict";

const DEFAULT_LIMITS = {archive_bytes: 104857600, source_bytes: 1073741824, files: 20000};
const EXCLUDED_DIRS = new Set([".git", "bin", "obj", "node_modules", "build", "packages", ".vs", "dist", "__pycache__", ".venv", "venv", "testresults"]);
const SOURCE_EXTENSION = /\.(cs|c|cc|cpp|cxx|h|hpp|hh|hxx|inl|inc)$/i;
const LANGUAGE_LABELS = {csharp: "C#", c: "C", cpp: "C++"};
const STATE_LABELS = {importing: "소스 가져오는 중", ready: "범위 확인", running: "분석 중", complete: "분석 완료", partial: "부분 분석 완료", failed: "작업 실패", interrupted: "분석 중단"};

function relativePath(value) {
  const path = String(value || "").replace(/\\/g, "/");
  if (!path || path.startsWith("/") || /^[a-z]:/i.test(path) || path.includes("\0") || path.split("/").some(part => !part || part === "." || part === "..")) {
    throw new Error("파일 경로를 확인할 수 없습니다. 소스 폴더를 다시 선택해 주세요.");
  }
  return path;
}

function isSourcePath(path) {
  const parts = path.split("/");
  return !parts.some(part => EXCLUDED_DIRS.has(part.toLowerCase()) || part.toLowerCase().startsWith(".env")) && SOURCE_EXTENSION.test(path);
}

function prepareUpload(items, kind, limits = {}) {
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

async function readDroppedEntries(entries, limits = {}) {
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

function safeResultUrl(value) {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u0020]/.test(value)) return null;
  return /^\/(?:results\/[a-z0-9]+|examples\/[a-z0-9-]+)\/(?:index|validation|timeseries)\.html$/.test(value) ? value : null;
}

function previewResultUrl(value, theme) {
  const path = safeResultUrl(value);
  return path && ["light", "dark", "blue"].includes(theme) ? `${path}?theme=${theme}` : path;
}

function formatSourceSize(bytes) {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) return "미확인";
  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(1)} GiB`;
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MiB`;
  return bytes >= 1024 ? `${(bytes / 1024).toFixed(1)} KiB` : `${bytes} B`;
}

function sortJobs(jobs, order = "latest") {
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

function groupExamples(examples) {
  const projects = [], auxiliary = [];
  for (const example of examples) {
    if (example.auxiliary) { auxiliary.push(example); continue; }
    let group = projects.find(item => item.project === example.project);
    if (!group) { group = {...example, examples: []}; projects.push(group); }
    group.examples.push(example);
  }
  return {projects, auxiliary};
}

function statusView(job) {
  const seconds = Math.max(0, Math.floor(Number(job.elapsed_seconds) || 0));
  return {
    title: STATE_LABELS[job.state] || "상태 확인 필요",
    stage: typeof job.stage === "string" ? job.stage : "상태를 확인하고 있습니다.",
    elapsed: seconds >= 60 ? `${Math.floor(seconds / 60)}분 ${seconds % 60}초` : `${seconds}초`,
    busy: ["importing", "running"].includes(job.state),
    result: ["complete", "partial"].includes(job.state) && Boolean(safeResultUrl(job.result_url))
  };
}

function jobDate(value) {
  if (value === null || value === undefined || value === "") return null;
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function canInspectJob(state) {
  return ["ready", "importing", "running", "failed", "interrupted"].includes(state);
}

function buildAnalysisOptions(values) {
  const payload = {lang: values.lang, backend: values.backend, subdir: values.subdir};
  if (values.backend === "clang") {
    payload.local_path = (values.local_path || "").trim();
    payload.compile_commands = (values.compile_commands || "").trim();
    payload.clang_library = (values.clang_library || "").trim();
    if (payload.local_path) payload.subdir = (values.local_subdir || ".").trim() || ".";
  }
  return payload;
}

function createApi(token, fetcher = globalThis.fetch) {
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
      const message = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? "입력값을 확인해 주세요. 필수 항목이나 경로 형식이 올바르지 않습니다." : typeof data.error === "string" ? data.error : data.error?.message || data.message || "요청을 처리하지 못했습니다.";
      throw new Error(message);
    }
    return data;
  };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {DEFAULT_LIMITS, prepareUpload, readDroppedEntries, safeResultUrl, previewResultUrl, statusView, jobDate, createApi, buildAnalysisOptions, canInspectJob, sortJobs, formatSourceSize, groupExamples};
}

if (typeof document !== "undefined") {
  const requestedTheme = new URLSearchParams(location.search).get("theme");
  const previewTheme = ["light", "dark", "blue"].includes(requestedTheme) ? requestedTheme : "blue";
  if (["dark", "blue"].includes(previewTheme)) {
    document.documentElement.setAttribute("data-preview-theme", previewTheme);
  } else {
    document.documentElement.removeAttribute("data-preview-theme");
  }
  const $ = id => document.getElementById(id);
  let api = createApi(""), limits = DEFAULT_LIMITS, sessionReady = false;
  let inputKind = "github", selectedUpload = null, activeJob = null, pending = false;
  let pollTimer = null, pollGeneration = 0;
  let historyJobs = [], historyGeneration = 0, historyMutating = false, pendingDelete = null, undoId = null;
  let detailGeneration = 0;
  let examplesGeneration = 0;

  function showNotice(message) {
    $("notice").textContent = message;
    $("notice").hidden = !message;
  }

  function lockInputs() {
    const busy = pending || (activeJob && statusView(activeJob).busy);
    for (const control of document.querySelectorAll("#import-form button, #import-form input, #scope-panel button, #scope-panel select, .advanced-content input, .advanced-content select")) {
      control.disabled = Boolean(busy || !sessionReady);
    }
    $("cancel-button").disabled = pending;
    $("reset-button").disabled = pending;
  }

  function stopPolling() {
    clearTimeout(pollTimer);
    pollGeneration++;
  }

  function setInputKind(kind, focus = false) {
    inputKind = kind;
    for (const name of ["github", "files"]) {
      const tab = $(`${name}-tab`), chosen = name === kind;
      tab.setAttribute("aria-selected", String(chosen));
      tab.tabIndex = chosen ? 0 : -1;
      tab.classList.toggle("is-active", chosen);
      $(`${name}-panel`).hidden = !chosen;
      if (chosen && focus) tab.focus();
    }
    showNotice("");
  }

  function formatBytes(value) {
    return value >= 1048576 ? `${(value / 1048576).toFixed(1)} MiB` : `${(value / 1024).toFixed(1)} KiB`;
  }

  function selectFiles(items, kind) {
    selectedUpload = null;
    $("selected-files").textContent = "아직 선택한 파일이 없습니다.";
    try {
      selectedUpload = prepareUpload(items, kind, limits);
      const label = kind === "zip" ? selectedUpload.files[0].name : selectedUpload.paths[0].split("/")[0];
      $("selected-files").textContent = `${label} · ${kind === "zip" ? "ZIP 1개" : `소스·헤더 ${selectedUpload.files.length.toLocaleString()}개`} · ${formatBytes(selectedUpload.bytes)}${selectedUpload.skipped ? ` · 제외 ${selectedUpload.skipped.toLocaleString()}개` : ""}`;
      showNotice("");
    } catch (error) { showNotice(error.message); }
  }

  function appendText(parent, tag, text, className) {
    const element = document.createElement(tag);
    element.textContent = text;
    if (className) element.className = className;
    parent.append(element);
    return element;
  }

  function renderScope(job) {
    $("source-label").textContent = job.name || "가져온 소스";
    const source = job.source || {};
    const meta = [];
    if (source.repository) meta.push(source.repository);
    if (source.commit) meta.push(`커밋 ${String(source.commit).slice(0, 12)}`);
    $("source-meta").textContent = meta.join(" · ");
    $("source-counts").replaceChildren();
    const languages = job.scan?.languages || {};
    let total = 0;
    for (const [lang, label] of Object.entries(LANGUAGE_LABELS)) {
      const count = Number(languages[lang]) || 0;
      total += count;
      if (count) appendText($("source-counts"), "span", `${label} ${count.toLocaleString()}개`, "count-chip");
    }
    appendText($("source-counts"), "span", `전체 소스 ${total.toLocaleString()}개`, "count-chip");
    $("scope-folder").replaceChildren();
    const folders = job.scan?.folders?.length ? job.scan.folders : ["."];
    for (const path of folders) {
      const option = appendText($("scope-folder"), "option", path === "." ? "전체 폴더" : path);
      option.value = path;
    }
    $("scope-language").value = $("analysis-language").value;
    $("scope-panel").hidden = false;
  }

  function renderJob(job, focus = false) {
    const wasReady = activeJob?.id === job.id && activeJob?.state === "ready";
    activeJob = job;
    const view = statusView(job);
    $("import-form").hidden = true;
    $("scope-panel").hidden = job.state !== "ready";
    $("job-panel").hidden = job.state === "ready";
    $("advanced-options").hidden = !["ready", "importing"].includes(job.state);
    $("step-label").textContent = job.state === "ready" ? "02 / 범위 확인" : job.state === "importing" ? "01 / 소스 가져오기" : "03 / 분석 결과";
    if (job.state === "ready") {
      if (!wasReady) renderScope(job);
      if (focus) $("start-button").focus();
    } else {
      $("job-title").textContent = view.title;
      $("job-stage").textContent = view.stage;
      $("elapsed").textContent = `경과 ${view.elapsed}`;
      $("status-symbol").classList.toggle("is-busy", view.busy);
      $("status-symbol").textContent = view.busy ? "" : view.result ? "✓" : "!";
      $("job-message").textContent = job.error ? String(job.error) : job.state === "partial" ? "일부 파일이나 설정에 제한이 있었습니다. 결과에서 분석 상태와 한계를 확인하세요." : job.state === "complete" ? "선택한 범위의 분석이 끝났습니다. 결과에서 구조와 검토 우선순위를 확인하세요." : job.state === "interrupted" ? "작업이 중단되었습니다. 분석 기록에서 상태를 확인하거나 다른 소스로 다시 시작할 수 있습니다." : view.busy ? "실제 처리 단계와 경과 시간을 표시합니다. 파일 수와 코드 구조에 따라 시간이 달라집니다." : "진행 로그에서 원인을 확인하고 다른 소스로 다시 시작할 수 있습니다.";
      $("result-link").hidden = !view.result;
      if (view.result) $("result-link").href = previewResultUrl(job.result_url, previewTheme);
      else $("result-link").removeAttribute("href");
      $("cancel-button").hidden = !view.busy;
      $("reset-button").hidden = view.busy;
      $("job-log").textContent = Array.isArray(job.log) ? job.log.join("\n") : String(job.log || "아직 기록된 로그가 없습니다.");
      if (focus && !view.busy) (view.result ? $("result-link") : $("reset-button")).focus();
    }
    lockInputs();
  }

  function schedulePoll(id, generation) {
    pollTimer = setTimeout(async () => {
      try {
        const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
        if (generation !== pollGeneration) return;
        showNotice("");
        const finished = activeJob?.state !== job.state && !statusView(job).busy;
        renderJob(job, finished);
        if (statusView(job).busy) schedulePoll(id, generation);
      } catch (error) {
        if (generation !== pollGeneration) return;
        showNotice(`${error.message} 현재 작업 상태를 다시 확인하고 있습니다.`);
        schedulePoll(id, generation);
      }
    }, 1000);
  }

  function followJob(job) {
    detailGeneration++;
    stopPolling();
    renderJob(job, true);
    if (statusView(job).busy) schedulePoll(job.id, pollGeneration);
  }

  async function importSource(event) {
    event.preventDefault();
    if (pending || !sessionReady) return;
    showNotice("");
    let path, body;
    try {
      if (inputKind === "github") {
        let url = $("github-url").value.trim();
        if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
        const parsed = new URL(url);
        if (parsed.protocol !== "https:" || parsed.hostname !== "github.com" || parsed.username || parsed.password || parsed.pathname.split("/").filter(Boolean).length !== 2) {
          throw new Error("공개 GitHub 저장소 주소를 입력해 주세요. 예: github.com/owner/repository");
        }
        path = "/api/import/github";
        body = JSON.stringify({url: parsed.href, name: $("analysis-name").value.trim()});
      } else {
        if (!selectedUpload) throw new Error("먼저 ZIP 파일이나 소스 폴더를 선택해 주세요.");
        path = "/api/import/files";
        body = new FormData();
        selectedUpload.files.forEach((file, index) => body.append("files", file, selectedUpload.paths[index]));
        body.append("paths", JSON.stringify(selectedUpload.paths));
        const name = selectedUpload.kind === "zip" ? selectedUpload.files[0].name.replace(/\.zip$/i, "") : selectedUpload.paths[0].split("/")[0];
        body.append("name", $("analysis-name").value.trim() || name);
      }
      pending = true;
      lockInputs();
      $("import-button").textContent = inputKind === "github" ? "저장소를 요청하고 있습니다…" : "소스를 전송하고 있습니다…";
      followJob(await api(path, {method: "POST", body}));
    } catch (error) { showNotice(error.message); }
    finally {
      pending = false;
      $("import-button").textContent = "소스 가져오기 →";
      lockInputs();
      if (activeJob?.state === "ready") $("start-button").focus();
    }
  }

  async function startAnalysis() {
    if (pending || activeJob?.state !== "ready") return;
    const lang = $("scope-language").value, backend = $("analysis-backend").value;
    if (backend === "clang" && !["c", "cpp"].includes(lang)) {
      showNotice("Clang 분석에서는 C 또는 C++ 언어를 선택해 주세요. C#은 기본 분석 방식을 사용합니다.");
      $("scope-language").focus();
      return;
    }
    if (backend === "clang" && !$("compile-commands").value.trim()) {
      $("advanced-options").open = true;
      showNotice("Clang 분석에 사용할 compile_commands.json 경로를 입력해 주세요.");
      $("compile-commands").focus();
      return;
    }
    const payload = buildAnalysisOptions({lang, subdir: $("scope-folder").value, backend,
      local_path: $("local-path").value, local_subdir: $("local-subdir").value,
      compile_commands: $("compile-commands").value, clang_library: $("clang-library").value});
    pending = true;
    showNotice("");
    lockInputs();
    try { followJob(await api(`/api/jobs/${encodeURIComponent(activeJob.id)}/start`, {method: "POST", body: JSON.stringify(payload)})); }
    catch (error) { showNotice(error.message); }
    finally { pending = false; lockInputs(); }
  }

  async function cancelAnalysis() {
    if (pending || !activeJob || !statusView(activeJob).busy) return;
    pending = true;
    lockInputs();
    try { followJob(await api(`/api/jobs/${encodeURIComponent(activeJob.id)}/cancel`, {method: "POST", body: "{}"})); }
    catch (error) { showNotice(error.message); }
    finally { pending = false; lockInputs(); }
  }

  function resetAnalysis() {
    detailGeneration++;
    stopPolling();
    activeJob = null;
    selectedUpload = null;
    $("zip-input").value = "";
    $("folder-input").value = "";
    $("selected-files").textContent = "아직 선택한 파일이 없습니다.";
    $("scope-panel").hidden = true;
    $("job-panel").hidden = true;
    $("import-form").hidden = false;
    $("advanced-options").hidden = false;
    $("advanced-options").open = false;
    $("step-label").textContent = "01 / 소스 가져오기";
    showNotice("");
    lockInputs();
    $(`${inputKind}-tab`).focus();
  }

  function drawHistory() {
    const list = $("history-list");
    list.replaceChildren();
      const jobs = sortJobs(historyJobs.filter(job => !job.deleted_at), $("history-sort").value);
      if (!jobs.length) appendText(list, "p", "아직 분석 기록이 없습니다. 새 분석에서 소스를 가져와 보세요.", "empty-state");
      for (const job of jobs) {
        const row = document.createElement("article");
        row.className = "collection-item";
        const info = document.createElement("div");
        appendText(info, "h3", job.name || "가져온 소스");
        const date = jobDate(job.created_at);
        appendText(info, "p", `${statusView(job).title} · ${date ? date.toLocaleString("ko-KR") : "시간 미확인"} · 소스 ${formatSourceSize(job.scan?.source_bytes)}`);
        if (job.error) appendText(info, "p", String(job.error));
        row.append(info);
        const actions = document.createElement("div");
        actions.className = "item-actions";
        if (statusView(job).result) {
          const link = appendText(actions, "a", "결과 열기 ↗", "button primary compact");
          link.href = previewResultUrl(job.result_url, previewTheme);
        }
        if (canInspectJob(job.state)) {
          const button = appendText(actions, "button", job.state === "ready" ? "범위 확인" : ["failed", "interrupted"].includes(job.state) ? "상태·로그 확인" : "진행 확인", "button secondary compact");
          button.type = "button";
          button.addEventListener("click", async () => {
            if (historyMutating) return;
            const generation = ++detailGeneration;
            try {
              const latest = await api(`/api/jobs/${encodeURIComponent(job.id)}`);
              if (generation !== detailGeneration || historyMutating) return;
              location.hash = "analyze";
              followJob(latest);
            } catch (error) {
              if (generation === detailGeneration && !historyMutating) button.textContent = error.message;
            }
          });
        }
        const trash = document.createElement("button");
        trash.type = "button";
        trash.className = "trash-button";
        trash.setAttribute("aria-label", `${job.name || "가져온 소스"} 기록 삭제`);
        trash.disabled = !job.can_delete || historyMutating || !sessionReady;
        trash.title = job.can_delete ? "기록 삭제" : "작업이 완전히 종료된 뒤 삭제할 수 있습니다.";
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("aria-hidden", "true");
        const icon = document.createElementNS("http://www.w3.org/2000/svg", "path");
        icon.setAttribute("d", "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7");
        svg.append(icon);
        trash.append(svg);
        trash.addEventListener("click", () => {
          pendingDelete = job;
          $("delete-name").textContent = job.name || "가져온 소스";
          $("delete-dialog").returnValue = "cancel";
          $("delete-dialog").showModal();
        });
        actions.append(trash);
        row.append(actions);
        list.append(row);
      }
    const deleted = $("deleted-list");
    deleted.replaceChildren();
    const archived = sortJobs(historyJobs.filter(job => job.deleted_at), $("history-sort").value);
    if (!archived.length) appendText(deleted, "p", "삭제한 기록이 없습니다.", "empty-state");
    for (const job of archived) {
      const row = document.createElement("article");
      row.className = "collection-item";
      const info = document.createElement("div");
      appendText(info, "h3", job.name || "가져온 소스");
      appendText(info, "p", `${statusView(job).title} · 소스 ${formatSourceSize(job.scan?.source_bytes)}`);
      row.append(info);
      const restore = appendText(row, "button", "복원", "button secondary compact");
      restore.type = "button";
      restore.setAttribute("aria-label", `${job.name || "가져온 소스"} 기록 복원`);
      restore.disabled = historyMutating || !sessionReady;
      restore.addEventListener("click", () => mutateHistory(job.id, "restore"));
      deleted.append(row);
    }
  }

  async function renderHistory() {
    if (historyMutating) return;
    const generation = ++historyGeneration;
    const list = $("history-list");
    list.replaceChildren();
    appendText(list, "p", "분석 기록을 불러오고 있습니다.", "empty-state");
    try {
      const jobs = await api("/api/jobs?include_deleted=true");
      if (generation !== historyGeneration) return;
      historyJobs = jobs;
      drawHistory();
    } catch (error) {
      if (generation !== historyGeneration) return;
      list.replaceChildren();
      appendText(list, "p", error.message, "empty-state");
    }
  }

  async function mutateHistory(id, action) {
    if (historyMutating || !sessionReady) return;
    historyMutating = true;
    historyGeneration++;
    detailGeneration++;
    $("undo-delete").disabled = true;
    drawHistory();
    try {
      const job = await api(`/api/jobs/${encodeURIComponent(id)}/${action}`, {method: "POST", body: "{}"});
      historyJobs = historyJobs.map(item => item.id === id ? job : item);
      if (action === "delete" && activeJob?.id === id) resetAnalysis();
      undoId = action === "delete" ? id : null;
      $("history-message").textContent = action === "delete" ? `‘${job.name}’ 기록을 삭제했습니다. 파일은 보관되어 있습니다.` : `‘${job.name}’ 기록을 복원했습니다.`;
      $("undo-delete").hidden = !undoId;
      $("history-notice").hidden = false;
    } catch (error) {
      $("history-message").textContent = error.message;
      $("history-notice").hidden = false;
    } finally {
      historyMutating = false;
      $("undo-delete").disabled = false;
      drawHistory();
      await renderHistory();
      if (action === "delete") $("undo-delete").focus();
    }
  }

  async function renderExamples() {
    const generation = ++examplesGeneration;
    const list = $("examples-list");
    list.replaceChildren();
    appendText(list, "p", "예시 결과를 불러오고 있습니다.", "empty-state");
    try {
      const examples = await api("/api/examples");
      if (generation !== examplesGeneration) return;
      list.replaceChildren();
      $("auxiliary-list").replaceChildren();
      let displayed = 0;
      const groups = groupExamples(examples.filter(example => safeResultUrl(example.url)));
      for (const project of groups.projects) {
        displayed++;
        const row = document.createElement("article");
        row.className = "collection-item project-card";
        const info = document.createElement("div");
        appendText(info, "h3", project.project);
        appendText(info, "p", `${project.genre} · ${project.language}`);
        appendText(info, "p", project.description);
        appendText(info, "p", `분석 범위: ${project.examples.map(example => example.scope).join(" / ")}`);
        appendText(info, "p", project.focus);
        const links = document.createElement("div");
        links.className = "example-links";
        for (const example of project.examples) {
          const link = appendText(links, "a", `${example.name} 결과 ↗`, "button secondary compact");
          link.href = previewResultUrl(example.url, previewTheme);
        }
        info.append(links);
        row.append(info);
        list.append(row);
      }
      $("auxiliary-examples").hidden = !groups.auxiliary.length;
      for (const example of groups.auxiliary) {
        const row = document.createElement("article");
        row.className = "collection-item";
        const info = document.createElement("div");
        appendText(info, "h3", example.name);
        appendText(info, "p", example.scope);
        row.append(info);
        const link = appendText(row, "a", "결과 열기 ↗", "button secondary compact");
        link.href = previewResultUrl(example.url, previewTheme);
        $("auxiliary-list").append(row);
      }
      if (!displayed) appendText(list, "p", "현재 제공되는 예시 결과가 없습니다.", "empty-state");
    } catch (error) {
      if (generation !== examplesGeneration) return;
      list.replaceChildren(); appendText(list, "p", error.message, "empty-state");
    }
  }

  function navigate() {
    detailGeneration++;
    const page = ["history", "examples"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "analyze";
    for (const name of ["analyze", "history", "examples"]) $(`${name}-page`).hidden = page !== name;
    for (const link of document.querySelectorAll(".nav-link")) {
      const active = link.getAttribute("href") === `#${page}`;
      link.classList.toggle("is-active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    if (page === "history") renderHistory();
    if (page === "examples") renderExamples();
  }

  for (const kind of ["github", "files"]) {
    $(`${kind}-tab`).addEventListener("click", () => setInputKind(kind));
    $(`${kind}-tab`).addEventListener("keydown", event => {
      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        setInputKind(event.key === "Home" ? "github" : event.key === "End" ? "files" : kind === "github" ? "files" : "github", true);
      }
    });
  }
  $("choose-zip").addEventListener("click", () => $("zip-input").click());
  $("choose-folder").addEventListener("click", () => $("folder-input").click());
  $("zip-input").addEventListener("change", event => { if (event.target.files.length) selectFiles(event.target.files, "zip"); });
  $("folder-input").addEventListener("change", event => { if (event.target.files.length) selectFiles(event.target.files, "folder"); });
  $("import-form").addEventListener("submit", importSource);
  $("start-button").addEventListener("click", startAnalysis);
  $("cancel-button").addEventListener("click", cancelAnalysis);
  $("reset-button").addEventListener("click", resetAnalysis);
  $("change-source-button").addEventListener("click", resetAnalysis);
  $("refresh-history").addEventListener("click", renderHistory);
  $("history-sort").addEventListener("change", drawHistory);
  $("undo-delete").addEventListener("click", () => { if (undoId) mutateHistory(undoId, "restore"); });
  $("delete-dialog").addEventListener("close", () => {
    const job = pendingDelete;
    pendingDelete = null;
    if (job && $("delete-dialog").returnValue === "delete") mutateHistory(job.id, "delete");
  });
  $("analysis-language").addEventListener("change", () => { $("scope-language").value = $("analysis-language").value; });
  $("scope-language").addEventListener("change", () => { $("analysis-language").value = $("scope-language").value; });
  $("analysis-backend").addEventListener("change", () => { $("clang-fields").hidden = $("analysis-backend").value !== "clang"; });
  $("drop-zone").addEventListener("keydown", event => { if (event.target === $("drop-zone") && ["Enter", " "].includes(event.key)) { event.preventDefault(); $("folder-input").click(); } });
  $("drop-zone").addEventListener("dragover", event => { event.preventDefault(); if (!pending && sessionReady) $("drop-zone").classList.add("is-over"); });
  $("drop-zone").addEventListener("dragleave", () => $("drop-zone").classList.remove("is-over"));
  $("drop-zone").addEventListener("drop", async event => {
    event.preventDefault();
    $("drop-zone").classList.remove("is-over");
    if (pending || !sessionReady) return;
    const droppedFiles = Array.from(event.dataTransfer.files);
    const items = Array.from(event.dataTransfer.items || []).filter(item => item.kind === "file");
    // Obtain entries during the drop event, before its transfer store expires.
    const entries = items.map(item => typeof item.webkitGetAsEntry === "function" ? item.webkitGetAsEntry() : null);
    if (droppedFiles.length === 1 && /\.zip$/i.test(droppedFiles[0].name) && !entries.some(entry => entry?.isDirectory)) {
      selectFiles(droppedFiles, "zip");
      return;
    }
    if (!entries.length || entries.some(entry => !entry)) {
      showNotice("이 브라우저에서는 폴더 끌어놓기를 지원하지 않습니다. ‘폴더 선택’ 버튼 또는 ZIP 파일을 사용해 주세요.");
      return;
    }
    if (!entries.some(entry => entry.isDirectory)) {
      showNotice("소스 폴더 전체를 놓거나 ZIP 파일 하나를 선택해 주세요.");
      return;
    }
    pending = true;
    lockInputs();
    $("selected-files").textContent = "폴더에서 소스 파일을 찾고 있습니다…";
    try { selectFiles(await readDroppedEntries(entries, limits), "folder"); }
    catch (error) { selectedUpload = null; $("selected-files").textContent = "폴더를 가져오지 못했습니다."; showNotice(error.message || "폴더에 접근하지 못했습니다. ‘폴더 선택’으로 다시 가져와 주세요."); }
    finally { pending = false; lockInputs(); }
  });
  window.addEventListener("hashchange", navigate);
  window.addEventListener("beforeunload", () => { clearTimeout(pollTimer); });

  async function initialize() {
    lockInputs();
    try {
      const session = await api("/api/session");
      if (!session.token) throw new Error("로컬 앱 세션을 준비하지 못했습니다. 페이지를 새로고침해 주세요.");
      api = createApi(session.token);
      limits = {...DEFAULT_LIMITS, ...session.limits};
      sessionReady = true;
      $("upload-help").textContent = `ZIP 최대 ${Math.round(limits.archive_bytes / 1048576)} MiB · 폴더 최대 ${(limits.source_bytes / 1073741824).toLocaleString()} GiB / ${limits.files.toLocaleString()}개 소스 파일`;
    } catch (error) { showNotice(error.message); }
    lockInputs();
    navigate();
  }
  initialize();
}
