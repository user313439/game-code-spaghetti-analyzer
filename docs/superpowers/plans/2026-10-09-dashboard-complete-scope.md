# Complete Scope UI Implementation Plan

> **For agentic workers:** Execute the approved focused update inline with checkpoints. Preserve the existing checkout and uncommitted work. No branches, commits, pushes, installations or browser-security bypasses.

**Goal:** Show scoped completion at 100%, restore concise help and collapsed limits, and identify the OpenRCT2 sample honestly.

**Architecture:** Only change the shared report renderer, regression tests and approved HTML presentation regions. Preserve the partial Clang ratio and all original analysis data.

**Tech Stack:** Existing Python/pytest and standalone HTML/CSS/JavaScript.

### Task 1: Tests before implementation

- [x] Update `tests/test_report_status_ui.py`: complete status has exactly one collapsed limits section; partial/failed retain two. Assert original limitations are escaped in the card, not help. Assert compiler warning explanations remain in the card.
- [x] Add complete basic/Clang checks for a focusable `100%` label, selected-input disclaimer, no invented compiler counts and no data mutation. Example: `assert '100%' in _render_analysis_status(status)`.
- [x] Restore the scope assertion in `tests/test_analysis_safety.py` to `분석 범위와 한계`.
- [x] Run `py -3.10 -B -m pytest tests/test_report_status_ui.py -q -p no:cacheprovider`; confirm failures are due to missing approved behavior.

### Task 2: Shared renderer

- [x] In `game_si/report.py`, insert a focusable `100%` span only in complete headings. Tooltip: selected inputs/config, not whole-game coverage/accuracy/build success; native excludes unregistered files and basic does not collect compiler diagnostics.
- [x] In `_status_card`, always render the limits disclosure; render reason disclosure only for non-complete states. Complete warning reasons move inside the limits disclosure using escaped list items.
- [x] Return the original `_render_help_box` markup without the recently added support section; remove its now-unused CSS. Keep the original scoring explanation and collapsed behavior.
- [x] Run focused tests and inspect changed rendering branches; preserve partial ratio and newline tooltip tests.

### Task 3: Refresh and verify

- [x] Create `docs/_verification/2026-10-09-dashboard-status/complete_scope_layout.py`; back up and validate all 11 HTML documents before writing. Replace only CSS/help/status; for the sample only, replace the subtitle with `Clang 기능 검증용 · 선택한 3개 구현 파일`.
- [x] Compare all other bytes, script bodies, analysis timestamps and prior report JSON fingerprints. Parse saved markup and run JavaScript syntax checks.
- [x] Write a new `reports/verification-dashboard-complete-scope-2026-10-09.json`, preserve earlier evidence; append a short current-state note to `docs/compiler-aware-cpp.md`.
- [x] Run native-enabled `py -3.10 -B -m pytest tests/ -q -p no:cacheprovider` using existing runtime paths, check whitespace diff, then verify saved HTML/source hashes again.
- [x] Record observed test results and explain browser interaction remains unverified. No real-game analysis rerun or Git writes.

Observed: initial red run 9 failed / 39 passed; focused tests 48 passed; native-enabled full suite 305 passed in 55.91 seconds. Saved reports verified 11, prior JSON preserved 169. Actual browser interaction not verified; no Git integration requested or performed.
