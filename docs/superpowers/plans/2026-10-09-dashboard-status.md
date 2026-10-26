# Dashboard Status Implementation Plan

> **For agentic workers:** Execute inline with review checkpoints. No Git mutations or browser policy workarounds are authorized.

**Goal:** Apply the approved explanatory status layout to all report backends without altering analysis results.

**Architecture:** Keep the existing report template and `data-tooltip` pattern. Share status-card markup, derive counts and diagnostic explanations from existing status dictionaries, and offer an optional subtitle through the canonical analyze command.

**Tech Stack:** Python, pytest, HTML/CSS, existing standalone JavaScript.

### Task 1: Regression tests

Files: new `tests/test_report_status_ui.py`, existing `tests/test_clang_integration.py` (replace assertions for removed technical clutter).

- [x] Add parametrized tests for native complete/partial/failed, basic C#/C/C++, unknown status, escaped diagnostic text, absent native counts, zero warnings, generic diagnostic reasons, compact markup and collapsed explanations. Example: `view = _render_analysis_status(status); assert 'data-tooltip=' in view; assert 'entry_index' not in view`.
- [x] Test header separation and parser support: `args = _build_parser().parse_args(['analyze', 'input', '--project-subtitle', '선택 범위']); assert args.project_subtitle == '선택 범위'`.
- [x] Run `py -3.10 -B -m pytest tests/test_report_status_ui.py -q -p no:cacheprovider`; confirm failures reflect missing behavior. Initial 22 failures; final 23 UI tests passed including canonical subtitle forwarding.

### Task 2: Focused implementation

Files: `game_si/report.py`, `game_si/cli.py`.

- [x] Replace the two status-renderer implementations with shared card composition and escaped, focusable tooltip spans. Preserve existing labels/counts and limitations; no full configuration/diagnostic dump.
- [x] Summarize recognized diagnostic categories using message matching; keep unknown causes explicitly unconfirmed. No game-specific branches.
- [x] Add subtitle parameter with a backend-appropriate fallback; keep the project name separate from report kind. Add `--project-subtitle` to analyze and forward with `getattr(args, 'project_subtitle', None)` for compatibility with other callers.
- [x] Add narrowly scoped status-card CSS and tooltip focus support. Run the new tests and existing report/integration tests.

### Task 3: Existing HTML refresh and final checks

Files: `docs/_verification/2026-10-09-dashboard-status/refresh_html.py`, 11 live case `index.html` files, new `reports/verification-dashboard-status-2026-10-09.json`.

- [x] Hash current case JSON, HTML script bodies and root index before refresh. Refresh only CSS/header/status markup, preserving original meta time and script bytes. Give the two new cases simple names and truthful scope subtitles.
- [x] Parse refreshed HTML and compare tooltip/status counts against source data. Check scripts with `node --check` and compare original script/JSON/root-index hashes. Record browser verification as false. All 11 cases retain script bodies and other nonpresentation content; 166 prior JSON files preserved.
- [x] Run the full native-enabled pytest suite with existing local runtime paths; no new installation, game execution or paid API calls. Fresh result: 280 passed, no skips, 52.57 seconds.
- [x] Self-review diff against the approved spec, record fresh verification and remaining actual-click limitation. No commits or pushes. Presentation choices remain only in the local refresh script; generic report generation contains no game-specific conditions.

### Follow-up: User-requested shorter compiler tooltips

User feedback on 2026-10-09: error/warning hover descriptions are too long. Keep the approved layout and full collapsed explanations; shorten hover text to the shared meaning plus at most two observed diagnostic labels, with a maximum of 150 characters.

- [x] Add regression tests for short contextual descriptions, unknown diagnoses and zero counts; run and confirm failure before implementation. Three contextual cases initially failed; all 27 UI tests now pass.
- [x] Modify only `game_si/report.py` and `tests/test_report_status_ui.py`. Reuse existing diagnostic matching with an optional concise output; no game-name conditions.
- [x] Refresh only the status regions in 11 live HTML files, keeping previous snapshots and evidence intact. Verify all JSON, script bodies and non-status HTML remain unchanged; create a separate tooltip verification record. Eleven cases checked, only two native-case HTML files changed, all 167 prior JSON files preserved.
- [x] Run the native-enabled full suite and report fresh evidence. Fresh result: 284 passed, no skips, 52.22 seconds. Actual browser verification remains blocked; no Git operations.
