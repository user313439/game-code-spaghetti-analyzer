# Compiler-aware C/C++ implementation plan

> For agentic workers: use subagent-driven-development, sequential implementers, spec review before quality review. User approval covers this plan's scope. No commits, branches, pushes, dependency/environment-file changes, game builds, or paid AI requests. Preserve the dirty checkout.

**Goal:** Add an optional compiler-context extractor to the canonical `game_si analyze` pipeline while preserving the basic analyzer and honestly reporting incomplete inputs.

**Architecture:** Validate an `arguments` compilation database in the parent; parse each selected implementation input in an isolated Python worker loading optional libclang; merge main-file definitions into one file-based unit per input; resolve symbol/owner links only within the selected set; pass the existing AST schema to unchanged metrics/scoring. The native worker never executes compiler commands.

**Stack:** Python 3.10+, optional clang 20 bindings, compatible native libclang, existing pytest/networkx/tree-sitter. Test native runtime is isolated under `docs/_verification/2026-10-05-cpp-feasibility/`; product code must not hardcode that location.

## Checklist / authority boundaries

- [x] Read README, existing canonical CLI/configs, approved design and current dirty status.
- [x] Task 1: safe configuration + isolated native extraction, passing fixture tests, independent reviews. Native core 103 tests; full suite 208 tests. Spec/quality findings fixed using failing regressions; independent quality re-run 103 passed.
- [x] Task 2: canonical CLI/status/HTML/advisor safety integration, passing integration tests, independent reviews. Integration 49 tests; full suite 257 passed. Stale backend failure metadata fixed with failing regressions; independent spec 49 passed and quality 49 passed with default status/HTML preservation checks.
- [x] Task 3: two real-project runs, manual function checks, basic regression preservation, usage docs and evidence. DOOM 3 registered 69 inputs / 4,375 definitions remain partial (26 compiler-error inputs); OpenRCT2 selected 3 inputs / 71 definitions complete. Each case's two runs match except time. All 16 evidence checks passed, including 8 basic cases and 47 previous artifacts; final spec review independently passed 37 comparisons. Evidence is dated 2026-10-07.
- [x] Final independent review and fresh complete suite. Final spec independently passed 37 comparisons; final quality review passed on 2026-10-08. Fresh native-enabled full suite: 257 passed in 56.36s. Product/result fingerprints, 47 previous artifacts and benchmark sources/revisions remain unchanged; 29 existing source files outside the approved integration edits were separately rechecked unchanged. Final resume evidence: `reports/verification-clang-final-2026-10-08.json`. No Git writes or new AI calls; browser interaction and game build/execution remain explicitly unverified.

Do not change G-SI weights/formula, C# extraction, basic C/C++ extraction, earlier reports or benchmark sources. This is not whole-engine support, automatic refactoring, or proof of accuracy. Real browser interaction remains unverified because local page access was denied; do not bypass that denial.

## Task 1 — Configuration and native extraction

**Files:** add `game_si/clang_analyzer.py`, focused `game_si/clang_config.py` and `game_si/clang_worker.py` if necessary; add `tests/test_clang_analysis.py` and small fixtures under `tests/samples/clang/`. Existing `cpp_analyzer` helpers may be imported without edits.

### Step 1: Write failing safe-input tests

Public contract:

```python
analyze_clang(input_path: Path, compile_commands: Path, excludes=(),
              output_path=None, clang_library=None, timeout=60.0)
# returns CppAnalysisResult-like .data/.errors/.elapsed_ms
# validated jobs: absolute source, directory, sanitized arguments, database index
```

Tests create JSON with `directory`, `file`, `arguments`. Verify relative include/file paths resolve from the entry directory, selected files intersect the requested root, default/user excludes work, duplicate configurations choose first and record alternatives, unregistered files are separately listed. Reject malformed JSON/schema, command-only entries, wrappers, response files, plugin flags including forwarded plugin load, and no intersection. Whitelist parser-relevant flags; strip build/output/link operands, reject unknown flags rather than pass through. Executable name is validated but never run; only regular clang/gcc/MSVC compiler names supported. Bare source operand must match the entry source. No shell/split command execution.

Expected initial failure: `ModuleNotFoundError` for the new module. Run:

```powershell
py -3.10 -B -m pytest tests/test_clang_analysis.py -q -p no:cacheprovider
```

### Step 2: Implement minimum validated loader

Use existing collection/default excludes, normalized absolute path keys and sorted order. Validate all selected entries (not unrelated external inputs); keep config digest/index and selected/not-selected lists. A malformed selected first configuration fails instead of silently choosing another.

### Step 3: Write failing real-native fixture assertions

Create small C++ header with namespace class, overloaded methods, static member, external/global declarations. Two `.cpp` files implement methods; two differently named function-like macros generate methods; conditional macro controls an active branch. Include header inline body as exclusion control. C fixture has ordinary functions/global/static variables and macro-generated function. Assert:

- definitions have correct semantic owner, FQN, distinct USR, source lines and macro invocation metadata;
- inactive branches and header definitions are not selected methods;
- CC base 1, if/ordinary for/while/do/switch case+default/catch/ternary/short-circuit operators follow basic C/C++ convention; label any intentional range-for treatment;
- direct calls carry resolved USRs, overload calls stay distinct, indirect/external calls have explicit limitations;
- resolved variable references contribute static/global accesses, automatic locals do not;
- file relationships map selected definition/owner symbols to selected units, not external headers;
- repeated extraction differs only in timestamp/elapsed time.

Native tests require `GAME_SI_TEST_CLANG_LIBRARY` and Python bindings on `PYTHONPATH`; skip explicitly when absent, never pretend skipped tests passed native validation. Run native fixture tests in the available isolated runtime.

### Step 4: Implement worker and parent aggregation

Worker protocol: `python -m game_si.clang_worker`, JSON job on stdin and JSON result on stdout. Import bindings only in the worker, keep Windows DLL-directory handle alive; convert native version to plain str. Catch native-load errors with actionable messages; parent rejects invalid worker output, isolates crash/timeout, continues remaining inputs. Use subprocess `shell=False` and `sys.executable`, bounded timeout. Never traverse full SDK bodies: filter top-level nodes by main-file location and semantic containers, then visit selected bodies. Normalize/cache source paths instead of repeatedly resolving paths.

Output includes standard schema/summary/files/errors plus backend `clang`, scope `implementation_file`, configuration provenance and compiler diagnostics. Error/fatal severities retain recovered definitions but force partial status later. Warning alone does not. Keep raw compiler diagnostics out of `syntax_files`. One synthetic compilation-unit class per parsed main file; its referenced types contain selected unit IDs derived from resolved symbol or owner mappings. Macro bodies cannot be reconstructed safely from invocation lines.

### Step 5: Test isolation and review

Use deterministic process-failure/timeout simulation at the process boundary, plus actual malformed/missing header/semantic error fixtures and missing native-library run. Test output-write errors propagate. Self-review, then independent spec review and quality review; fix findings with regression tests. No Git writes.

## Task 2 — Canonical integration

**Files:** focused additions to `game_si/cli.py`, `game_si/diagnostics.py`, `game_si/report.py`, `game_si/advisor.py`, `pyproject.toml`; add `tests/test_clang_integration.py`. Save original copies before editing because HEAD already has prior user changes.

### Step 1: Write failing CLI/status tests

New analyze-only options:

```text
--cpp-backend {tree-sitter,clang}       default tree-sitter
--compile-commands PATH               required for clang
--clang-library PATH                 optional native library
--clang-timeout SECONDS               finite positive, default 60
```

Reject clang with C#, missing configuration, and irrelevant clang settings in basic mode. Ensure normal no-new-options behavior stays unchanged. Integration test invokes canonical `main([...])` with real native fixtures and verifies `ast.json`, `analysis_status.json`, `metrics.json`, `scoring.json`, `index.html`. Complete=0, partial=3, failed/save-error=1. Test stale-output failure marker behavior, warning-only complete, compiler error partial, zero definitions failed, unmatched inputs failed. Add CLI subprocess test as well as in-process assertions.

### Step 2: Wire dispatch and honest status

Only `analyze` dispatch changes; leave score-full/timeseries/validation/tuning unchanged. Optional dependency extra `clang` supports bindings compatible with tested native major (20). No global installation or lock update.

`summarize_analysis` branches on backend only for new results; retain old branch output unchanged. Include compiler error/warning file counts separately, selected/skipped configs, backend/version/unit/scope/limits. Report overall error/fatal partial independent of warning. Failed files are worker/read failures, not unregistered inputs or compiler-warning files.

### Step 3: Small HTML and macro advisor safety

Show file-based unit, backend and selected/not-selected input counts in status block, with escaped diagnostics/provenance. Avoid claims that header ownership mapping equals complete class coupling. Existing help stays collapsed. For Clang screens clarify file-based ranking without redesigning basic screens. In advisor snippet selection filter `is_macro_generated`; macro-only units return no source snippet. Do not send macro invocation as complete function. Test both mixed normal/macro and macro-only cases; no API request.

### Step 4: Verification and two reviews

Run new integration tests and entire suite with the optional runtime. Verify old helper behavior unchanged and HTML safe escaping. Independent spec then quality review. Fix findings with failing regression tests first.

## Task 3 — Real-project evidence and handoff docs

**Files:** generated separate result directories `reports/doom3-gameplay-clang/` and `reports/openrct2-clang-sample/`; add `docs/compiler-aware-cpp.md` and `reports/verification-clang-integration-2026-10-07.json` (실제 마무리 검수일). Update approved spec/plan status. Optional small README entry for usage. Do not modify existing index/cases or feasibility evidence.

### Step 1: Prepare explicitly labeled analysis configurations

Generate ignored JSON database under `docs/_verification/2026-10-05-clang-integration/` from actual DOOM `neo/game.vcxproj` registered 69 inputs and `_Common/_Game/_Debug.props` definitions. Record modern Windows SDK includes and C++17 analysis standard: it is analysis context, not original MSVC build reproduction. OpenRCT2 representative Guard/Path/String use documented CMake NOMINMAX/char8 and thirdparty include with C++20. No game-specific code inside analyzer; no suppressions or benchmark edits.

### Step 2: Run canonical CLI twice per case

Set process-only `PYTHONPATH` to isolated bindings and pass native DLL explicitly. Use first output under public separate result directories, second under ignored verification. Run:

```text
python -m game_si analyze benchmarks/DOOM-3/neo/game --lang cpp --cpp-backend clang --compile-commands ANALYSIS_JSON --clang-library DLL --out reports/doom3-gameplay-clang
python -m game_si analyze benchmarks/OpenRCT2/src/openrct2/core --lang cpp --cpp-backend clang --compile-commands SAMPLE_JSON --clang-library DLL --out reports/openrct2-clang-sample
```

The second samples only three registered files; all other core implementations must be listed as not selected. Expect DOOM partial compatibility diagnostics; do not force complete. Compare AST/metrics/scoring/status excluding timestamp and elapsed fields, not ignoring any substantive discrepancy.

### Step 3: Manually audit representative extraction

Compare Physics_Player ownership/macros, Player.UpdateFocus, Script_Interpreter.Execute and Game_local.RunFrame definitions/lines/CC/direct calls against original source and independent basic/Lizard rules. Test default case difference is documented. Function count growth is not accuracy proof. Record all compiler counts and limitations.

### Step 4: Regression and static artifact checks

Fresh full tests; unchanged basic analyzer/formula/C#/benchmark hashes; previous 40 case JSON/HTML artifact hashes and old DOOM6 unchanged; root index unchanged. Check generated HTML backend/scope/status, escaped text, embedded JSON and JavaScript syntax if Node available. Actual browser interaction not verified; do not bypass blocked page access.

### Step 5: Document and final review

Usage prerequisites, commands, supported flag boundary, compiler config meaning, timeout/failure behavior, macro/header/dynamic limits and score interpretation. Explain to novice: basic path unchanged; optional engine-aware context improves extraction in defined scope; real DOOM remains partial; OpenRA vs DOOM demo choice deferred. Independent final review, fresh suite, update checklist only on evidence. No final-report authoring, commits or pushes in this task.
