import {LANGUAGE_LABELS, buildAnalysisOptions, parseGithubUrl, prepareUpload, readDroppedEntries, statusView} from "./core.js";
import {h, notice, progressBlock, fill} from "./ui.js";

const IMPORT_STEPS = ["소스 가져오기", "범위 확인", "정적 분석", "완료"];

export async function render(view, ctx, params = {}) {
  let kind = "github", upload = null, job = null, pending = false, timer = null, alive = true;
  const alert = h("div", {class: "alert-slot"});
  const say = message => fill(alert, ...(message ? [notice(message)] : []));

  // --- source form -------------------------------------------------------
  const url = h("input", {id: "github-url", type: "url", placeholder: "github.com/owner/game-project", autocomplete: "url", spellcheck: "false"});
  const zipInput = h("input", {class: "visually-hidden", type: "file", accept: ".zip", tabindex: "-1", "aria-label": "ZIP 파일 선택"});
  const folderInput = h("input", {class: "visually-hidden", type: "file", webkitdirectory: true, multiple: true, tabindex: "-1", "aria-label": "소스 폴더 선택"});
  const picked = h("p", {class: "picked", "aria-live": "polite"}, "아직 선택한 파일이 없습니다.");
  // One source per analysis: once a ZIP/folder is picked the drop area gives way to "clear", so a
  // second pick cannot look like it is added to the first.
  const clearButton = h("button", {class: "btn ghost sm", type: "button", hidden: true, onclick: () => { clearPick(); drop.focus(); }}, "선택 지우기");
  const limitText = h("p", {class: "help"});
  const drop = h("div", {class: "drop", tabindex: "0", role: "group", "aria-label": "ZIP 파일 또는 소스 폴더를 여기에 놓으세요"},
    h("b", null, "ZIP 파일이나 폴더를 여기에 놓으세요"), h("span", {class: "sub"}, "또는 직접 선택해 가져올 수 있습니다."),
    h("div", {class: "row-gap"},
      h("button", {class: "btn ghost sm", type: "button", onclick: () => zipInput.click()}, "ZIP 선택"),
      h("button", {class: "btn ghost sm", type: "button", onclick: () => folderInput.click()}, "폴더 선택")));
  const githubPanel = h("div", {class: "panel"}, h("label", {for: "github-url"}, "공개 GitHub 저장소 주소"), url,
    h("p", {class: "help"}, "코드 파일만 저장하고 그림·소리 같은 리소스는 저장하지 않습니다. 가져온 뒤 분석할 폴더와 언어를 고릅니다."));
  const filesPanel = h("div", {class: "panel", hidden: true}, drop, zipInput, folderInput, h("div", {class: "picked-row"}, picked, clearButton), limitText,
    h("p", {class: "help"}, "소스·헤더만 가져오며 빌드 결과, 의존성 폴더, 환경 설정 파일은 제외합니다."));
  const tabs = ["github", "files"].map(name => h("button", {type: "button", role: "tab", class: "tab", onclick: () => setKind(name)}, name === "github" ? "GitHub" : "내 파일"));

  const name = h("input", {id: "analysis-name", type: "text", maxlength: "100", placeholder: "비워 두면 저장소·폴더 이름을 사용합니다"});
  const clangInputs = {
    local_path: h("input", {id: "clang-local-path", type: "text", placeholder: "C:\\Projects\\MyGame", spellcheck: "false"}),
    local_subdir: h("input", {id: "clang-local-subdir", type: "text", value: ".", spellcheck: "false"}),
    compile_commands: h("input", {id: "clang-compile-commands", type: "text", placeholder: "C:\\Projects\\MyGame\\build\\compile_commands.json", spellcheck: "false"}),
    clang_library: h("input", {id: "clang-library", type: "text", placeholder: "C:\\LLVM\\bin\\libclang.dll", spellcheck: "false"}),
  };
  const clangBox = h("div", {class: "clang", hidden: true},
    h("p", {class: "help"}, "Clang은 기존 빌드 환경이 필요합니다. 경로는 이 앱을 실행한 컴퓨터 기준입니다."),
    h("label", {for: "clang-local-path"}, "원래 소스 폴더 경로 (선택)"), clangInputs.local_path,
    h("label", {for: "clang-local-subdir"}, "원래 폴더 안의 분석 범위"), clangInputs.local_subdir,
    h("label", {for: "clang-compile-commands"}, "compile_commands.json 경로"), clangInputs.compile_commands,
    h("label", {for: "clang-library"}, "libclang 파일 경로 (자동 탐색 가능 시 생략)"), clangInputs.clang_library);
  // The name is sent with the import, so this box only matters before a source is imported.
  // How to analyse (basic / precise) is chosen once, on the scope step.
  const advanced = h("details", {class: "advanced"}, h("summary", null, "고급 설정 ", h("span", {class: "sub"}, "필요할 때만 조정하세요")),
    h("label", {for: "analysis-name"}, "분석 이름 (선택)"), name);
  const importButton = h("button", {class: "btn primary block", type: "submit"}, "소스 가져오기 →");
  const form = h("form", {class: "import-form", novalidate: true, onsubmit: importSource},
    h("div", {class: "tabs", role: "tablist", "aria-label": "소스 가져오기 방식"}, ...tabs), githubPanel, filesPanel, importButton);

  // --- scope + status -----------------------------------------------------
  const scope = h("section", {class: "scope", hidden: true});
  const status = h("section", {class: "status", hidden: true});
  const card = h("section", {class: "card import-card"},
    h("div", {class: "card-head"}, h("div", null, h("div", {class: "eyebrow"}, "새 분석"), h("h2", {class: "h2"}, "어떤 게임 코드를 살펴볼까요?"))),
    alert, form, scope, status, advanced);

  const hero = h("div", {class: "hero"}, h("div", {class: "eyebrow"}, "Game Code Spaghetti Analyzer"),
      h("h1", {class: "h1 big"}, "게임 코드의 엉킨 곳을 찾아 풀어 보세요."),
      h("p", {class: "sub"}, "소스를 가져오면 어디가 왜 엉켰는지 진단하고, AI와 함께 고친 뒤 게임이 잘 돌아가는지까지 확인합니다."),
      h("div", {class: "chips"}, ...["C#", "C", "C++"].map(t => h("span", {class: "chip"}, t)), h("span", {class: "chip muted"}, "이 PC에서 정적 분석")));
  const flow = h("div", {class: "flow"}, ...[
      ["01", "엉킴 진단", "파일마다 점수와 이유, 서로 얽힌 모습을 지도로 봅니다."],
      ["02", "AI 처방·리팩토링", "어디부터 고칠지 처방받고, 실제 코드 변경을 비교해 적용합니다."],
      ["03", "결과·검증", "엉킴이 얼마나 줄었는지 확인하고 수정된 게임을 실행합니다."]]
      .map(([n, t, d]) => h("div", {class: "card flow-item"}, h("span", {class: "num"}, n), h("b", null, t), h("p", {class: "sub"}, d))));
  view.append(h("section", {class: "wrap home"}, hero, card, flow));

  // --- behaviour ---------------------------------------------------------
  function lock() {
    const busy = pending || (job && statusView(job).busy) || !ctx.ready;
    for (const control of view.querySelectorAll(".import-form button, .import-form input, .scope button, .scope select, .scope input, .advanced input")) control.disabled = Boolean(busy);
    // Nothing to import until a ZIP/folder is picked (files tab) or an address is typed (GitHub tab).
    const ready = kind === "github" ? Boolean(url.value.trim()) : Boolean(upload);
    importButton.disabled = Boolean(busy) || !ready;
    importButton.title = ready ? "" : kind === "github" ? "GitHub 저장소 주소를 먼저 입력해 주세요." : "ZIP 파일이나 소스 폴더를 먼저 선택해 주세요.";
  }
  url.addEventListener("input", () => lock());
  function setKind(next) {
    kind = next;
    lock();
    tabs.forEach((tab, i) => { const on = (i === 0) === (next === "github"); tab.classList.toggle("on", on); tab.setAttribute("aria-selected", String(on)); });
    githubPanel.hidden = next !== "github";
    filesPanel.hidden = next === "github";
    say("");
  }
  function choose(items, type) {
    upload = null;
    picked.textContent = "아직 선택한 파일이 없습니다.";
    try {
      upload = prepareUpload(items, type, ctx.limits);
      const label = type === "zip" ? upload.files[0].name : upload.paths[0].split("/")[0];
      const size = upload.bytes >= 1048576 ? `${(upload.bytes / 1048576).toFixed(1)} MiB` : `${(upload.bytes / 1024).toFixed(1)} KiB`;
      picked.textContent = `${label} · ${type === "zip" ? "ZIP 1개" : `소스·헤더 ${upload.files.length.toLocaleString()}개`} · ${size}${upload.skipped ? ` · 제외 ${upload.skipped.toLocaleString()}개` : ""}`;
      say("");
    } catch (error) { say(error.message); }
    syncPick();
    lock();
  }
  function syncPick() { drop.hidden = Boolean(upload); clearButton.hidden = !upload; }
  function clearPick() {
    upload = null;
    zipInput.value = ""; folderInput.value = "";   // the same file can be picked again
    picked.textContent = "아직 선택한 파일이 없습니다.";
    say("");
    syncPick();
    lock();
  }
  zipInput.addEventListener("change", e => { if (e.target.files.length) choose(e.target.files, "zip"); });
  folderInput.addEventListener("change", e => { if (e.target.files.length) choose(e.target.files, "folder"); });
  drop.addEventListener("keydown", e => { if (e.target === drop && ["Enter", " "].includes(e.key)) { e.preventDefault(); folderInput.click(); } });
  drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", async e => {
    e.preventDefault();
    drop.classList.remove("over");
    if (pending || !ctx.ready) return;
    const dropped = Array.from(e.dataTransfer.files);
    const entries = Array.from(e.dataTransfer.items || []).filter(i => i.kind === "file").map(i => typeof i.webkitGetAsEntry === "function" ? i.webkitGetAsEntry() : null);
    if (dropped.length === 1 && /\.zip$/i.test(dropped[0].name) && !entries.some(x => x?.isDirectory)) { choose(dropped, "zip"); return; }
    if (!entries.length || entries.some(x => !x)) { say("이 브라우저에서는 폴더 끌어놓기를 지원하지 않습니다. ‘폴더 선택’ 버튼 또는 ZIP 파일을 사용해 주세요."); return; }
    if (!entries.some(x => x.isDirectory)) { say("소스 폴더 전체를 놓거나 ZIP 파일 하나를 선택해 주세요."); return; }
    pending = true; lock();
    picked.textContent = "폴더에서 소스 파일을 찾고 있습니다…";
    try { choose(await readDroppedEntries(entries, ctx.limits), "folder"); }
    catch (error) { upload = null; picked.textContent = "폴더를 가져오지 못했습니다."; say(error.message || "폴더에 접근하지 못했습니다."); }
    finally { pending = false; lock(); }
  });

  async function importSource(event) {
    event.preventDefault();
    if (pending || !ctx.ready) return;
    say("");
    let path, body;
    try {
      if (kind === "github") {
        path = "/api/import/github";
        body = JSON.stringify({url: parseGithubUrl(url.value), name: name.value.trim()});
      } else {
        if (!upload) throw new Error("먼저 ZIP 파일이나 소스 폴더를 선택해 주세요.");
        path = "/api/import/files";
        body = new FormData();
        upload.files.forEach((file, i) => body.append("files", file, upload.paths[i]));
        body.append("paths", JSON.stringify(upload.paths));
        const fallback = upload.kind === "zip" ? upload.files[0].name.replace(/\.zip$/i, "") : upload.paths[0].split("/")[0];
        body.append("name", name.value.trim() || fallback);
      }
      pending = true; lock();
      importButton.textContent = kind === "github" ? "저장소를 요청하고 있습니다…" : "소스를 전송하고 있습니다…";
      const created = await ctx.api(path, {method: "POST", body});
      history.replaceState(null, "", `#/job/${created.id}`);
      follow(created);
    } catch (error) { say(error.message); }
    finally { pending = false; importButton.textContent = "소스 가져오기 →"; lock(); }
  }

  function showScope() {
    const source = job.source || {}, languages = job.scan?.languages || {};
    const folder = h("select", {id: "scope-folder"}, ...(job.scan?.folders?.length ? job.scan.folders : ["."]).map(p => h("option", {value: p}, p === "." ? "전체 폴더" : p)));
    const lang = h("select", {id: "scope-language"}, h("option", {value: "auto"}, "자동 감지"), ...Object.entries(LANGUAGE_LABELS).map(([v, t]) => h("option", {value: v}, t)));
    // One place to choose how C/C++ is read: basic (no build settings), precise with the build settings
    // recognised for a known open-source game (its own project file's options), or the user's compile_commands.json.
    const presets = job.scan?.presets || [];
    const fits = f => presets.find(p => f === "." || p.folder === f || p.folder.startsWith(`${f}/`));
    const hasNative = Number(languages.c) > 0 || Number(languages.cpp) > 0;
    const mode = hasNative ? h("select", {id: "scope-mode"},
      presets.length ? h("option", {value: "clang-auto"}, "정밀 분석 (Clang · 자동 인식된 빌드 설정)") : null,
      h("option", {value: "tree-sitter"}, "기본 분석 (빠름 · 빌드 설정 없이)"),
      h("option", {value: "clang"}, "정밀 분석 (Clang · 내 빌드 설정 직접 지정)")) : null;
    const modeHelp = h("p", {class: "help"});
    const syncMode = () => {
      if (!mode) return;
      const hit = fits(folder.value), auto = mode.querySelector('[value="clang-auto"]');
      if (auto) auto.disabled = !hit;
      if (!hit && mode.value === "clang-auto") mode.value = "tree-sitter";
      clangBox.hidden = mode.value !== "clang";
      modeHelp.textContent = mode.value === "clang-auto" ? `이 소스를 ${hit.name} 원본으로 인식했습니다. 원본 프로젝트 파일에 적힌 컴파일 옵션(언어 표준·매크로·헤더 경로)으로 컴파일러처럼 모든 코드를 해석합니다 (약 1분). 처음 보는 게임은 기본 분석이나 직접 지정을 씁니다.`
        : mode.value === "clang" ? "직접 만든 compile_commands.json으로 컴파일러처럼 해석합니다. 빌드 환경이 있는 사람만 쓰는 방식입니다."
        : `빌드 설정 없이 코드를 읽습니다. 매크로 때문에 일부 줄을 건너뛸 수 있습니다(부분 분석).${presets.length && !hit ? ` 자동 인식된 빌드 설정은 ${presets[0].folder} 폴더에 맞습니다.` : ""}`;
    };
    // The whole import stays the first choice, as for any game: recognised build settings also fit the folders above theirs.
    folder.addEventListener("change", syncMode);
    mode?.addEventListener("change", syncMode);
    syncMode();
    let total = 0;
    const counts = Object.entries(LANGUAGE_LABELS).map(([k, label]) => { const n = Number(languages[k]) || 0; total += n; return n ? h("span", {class: "chip"}, `${label} ${n.toLocaleString()}개`) : null; });
    fill(scope, 
      h("div", {class: "scope-head"}, h("span", {class: "ok"}, "✓"), h("div", null, h("h3", {class: "h3"}, "분석할 범위를 확인하세요"),
        h("p", {class: "sub"}, job.name || "가져온 소스", source.repository ? ` · ${source.repository}` : "", source.commit ? ` · 커밋 ${String(source.commit).slice(0, 12)}` : ""))),
      h("div", {class: "chips"}, ...counts, h("span", {class: "chip"}, `전체 소스 ${total.toLocaleString()}개`)),
      h("div", {class: "grid2"}, h("div", null, h("label", {for: "scope-folder"}, "분석 대상 폴더"), folder), h("div", null, h("label", {for: "scope-language"}, "분석 언어"), lang)),
      mode ? h("div", {class: "scope-mode"}, h("label", {for: "scope-mode"}, "C / C++ 분석 방식"), mode, modeHelp, clangBox) : null,
      h("p", {class: "help"}, "표시된 파일 수는 가져온 전체 소스 기준입니다. 선택한 폴더와 언어가 실제 분석 범위를 정합니다.",
        Number(languages.csharp) > 0 ? " C# 파일은 Roslyn으로 분석합니다." : ""),
      h("div", {class: "actions"},
        h("button", {class: "btn ghost", type: "button", onclick: reset}, "소스 다시 선택"),
        h("button", {class: "btn primary", type: "button", onclick: () => start(folder.value, lang.value, mode?.value)}, "이 범위 분석하기 →")));
  }

  // The status block is built once and updated in place, so polling every second keeps the
  // opened log, its scroll position and keyboard focus where they are.
  const bar = progressBlock(IMPORT_STEPS);
  const statusDot = h("span", {class: "dot"}), statusTitle = h("h3", {class: "h3"});
  const statusMessage = h("p", {class: "sub", "aria-live": "polite"});
  const statusActions = h("div", {class: "actions"});
  const statusLog = h("pre", {tabindex: "0"});
  fill(status, h("div", {class: "status-head"}, statusDot, h("div", null, h("div", {class: "eyebrow"}, "분석 상태"), statusTitle)),
    bar.el, statusMessage, statusActions, h("details", {class: "log"}, h("summary", null, "진행 기록 보기"), statusLog));
  let actionsKey = "";
  function showStatus() {
    const v = statusView(job);
    // Precise analysis counts the files it has read: the bar fills within the analysis stage.
    const counted = job.state === "running" && job.progress?.total ? job.progress.done / job.progress.total : null;
    const step = job.state === "importing" ? 0 : job.state === "running" ? 2 + (counted ?? 0) * 0.9 : v.result ? 4 : 2;
    bar.update({step, total: 4, text: v.stage, elapsed: v.elapsed, indeterminate: v.busy && job.state === "running" && counted === null});
    const message = job.error ? String(job.error)
      : job.state === "partial" ? "일부 파일은 문법을 끝까지 해석하지 못했지만 분석 결과를 볼 수 있습니다."
      : job.state === "complete" ? "분석이 끝났습니다. 어디가 왜 엉켰는지 진단을 확인하세요."
      : job.state === "interrupted" ? "작업이 중단되었습니다. 다른 소스로 다시 시작할 수 있습니다."
      : v.busy ? "파일 수와 코드 구조에 따라 시간이 달라집니다." : "진행 기록에서 원인을 확인할 수 있습니다.";
    statusDot.className = `dot ${v.busy ? "busy" : v.result ? "good" : "bad"}`;
    if (statusTitle.textContent !== v.title) statusTitle.textContent = v.title;
    if (statusMessage.textContent !== message) statusMessage.textContent = message;
    const log = Array.isArray(job.log) ? job.log.join("\n") : String(job.log || "아직 기록된 내용이 없습니다.");
    if (statusLog.textContent !== log) {
      const atEnd = statusLog.scrollTop + statusLog.clientHeight >= statusLog.scrollHeight - 4;
      statusLog.textContent = log;
      if (atEnd) statusLog.scrollTop = statusLog.scrollHeight;
    }
    const key = `${job.id}:${v.busy}:${Boolean(v.result)}`;
    if (key === actionsKey) return;
    actionsKey = key;
    fill(statusActions,
      v.busy ? h("button", {class: "btn ghost", type: "button", onclick: cancel}, "작업 중단") : h("button", {class: "btn ghost", type: "button", onclick: reset}, "다른 코드 분석"),
      v.result ? h("a", {class: "btn primary", href: `#/job/${job.id}/diagnosis`}, "엉킴 진단 보기 →") : null);
    if (v.result) statusActions.lastChild.focus();
  }

  function render() {
    form.hidden = Boolean(job);
    scope.hidden = !job || job.state !== "ready";
    status.hidden = !job || job.state === "ready";
    advanced.hidden = Boolean(job);
    hero.hidden = Boolean(job);   // the intro banner is tall; once a source is open the scope button must stay on screen
    flow.hidden = Boolean(job);
    if (job?.state === "ready" && scope.dataset.job !== job.id) { scope.dataset.job = job.id; showScope(); }
    if (job && job.state !== "ready") showStatus();
    ctx.setSteps(job ? job.id : null, 0, {diagnosis: Boolean(job && statusView(job).result)});
    ctx.setCrumb(job ? job.name : "");
    lock();
  }

  function follow(next) {
    job = next;
    clearTimeout(timer);
    render();
    if (statusView(job).busy) timer = setTimeout(poll, 1000);
  }
  async function poll() {
    if (!alive || !job) return;
    try { follow(await ctx.api(`/api/jobs/${job.id}`)); say(""); }
    catch (error) { say(`${error.message} 다시 확인하고 있습니다.`); timer = setTimeout(poll, 1500); }
  }
  async function start(subdir, lang, preferred) {
    if (pending) return;
    const values = preferred === "clang" ? {lang, subdir, backend: "clang", ...Object.fromEntries(Object.entries(clangInputs).map(([k, el]) => [k, el.value]))}
      : {lang, subdir, backend: preferred || "tree-sitter"};
    if (values.backend === "clang" && !["c", "cpp"].includes(lang)) { say("직접 지정한 Clang 분석에서는 분석 언어를 C 또는 C++로 골라 주세요."); return; }
    if (values.backend === "clang" && !values.compile_commands.trim()) { clangInputs.compile_commands.focus(); say("Clang 분석에 사용할 compile_commands.json 경로를 입력해 주세요."); return; }
    pending = true; lock(); say("");
    try { follow(await ctx.api(`/api/jobs/${job.id}/start`, {method: "POST", body: JSON.stringify(buildAnalysisOptions(values))})); }
    catch (error) { say(error.message); }
    finally { pending = false; lock(); }
  }
  async function cancel() {
    pending = true; lock();
    try { follow(await ctx.api(`/api/jobs/${job.id}/cancel`, {method: "POST", body: "{}"})); }
    catch (error) { say(error.message); }
    finally { pending = false; lock(); }
  }
  function reset() {
    clearTimeout(timer);
    job = null; upload = null; scope.dataset.job = ""; actionsKey = "";
    zipInput.value = ""; folderInput.value = "";
    picked.textContent = "아직 선택한 파일이 없습니다.";
    syncPick();
    if (location.hash !== "#/") history.replaceState(null, "", "#/");
    say(""); render();
  }

  setKind("github");
  limitText.textContent = `ZIP 최대 ${Math.round(ctx.limits.archive_bytes / 1048576)} MiB · 폴더 최대 ${(ctx.limits.source_bytes / 1073741824).toLocaleString()} GiB / ${ctx.limits.files.toLocaleString()}개 소스 파일`;
  if (ctx.sessionError) say(ctx.sessionError);
  render();
  if (params.jobId) {
    try { follow(await ctx.api(`/api/jobs/${params.jobId}`)); }
    catch (error) { say(error.message); }
  }
  return () => { alive = false; clearTimeout(timer); };
}
