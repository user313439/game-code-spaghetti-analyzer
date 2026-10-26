# Dashboard Coverage Implementation Plan

> **For agentic workers:** Execute the user-approved scoped update inline with review checkpoints. Preserve the user's existing checkout; no branches, commits, pushes or browser-security bypasses.

**Goal:** Separate diagnostic lines, show truthful partial file coverage, and simplify complete-status cards.

**Architecture:** Modify only the shared report renderer and associated tests. Keep the existing status dictionary and tooltip pattern; relocate complete-case limits into the collapsed help. Mechanical HTML refresh changes only CSS/help/status regions.

**Tech Stack:** Existing Python/pytest, standalone HTML/CSS and JavaScript.

### Task 1: Regression tests

Files: `tests/test_report_status_ui.py`, `tests/test_analysis_safety.py`.

- [x] Add tests for explicit newline before `이번 진단:` and `white-space: pre-line` in status tooltip CSS.
- [x] Add percentage tests: partial native 43/69 = 62.3%; zero-error worker failure excludes failed inputs; invalid/missing/zero counts, basic, complete and failed cases omit the ratio. Example: `assert '62.3%' in _render_analysis_status(native_status())`.
- [x] Adjust existing complete-card expectations to the newly approved layout and assert limits/warning explanations remain escaped in `_render_help_box(True, status)`.
- [x] Run `py -3.10 -B -m pytest tests/test_report_status_ui.py -q -p no:cacheprovider` and confirm the new behavior fails before implementation.

### Task 2: Minimal renderer changes

File: `game_si/report.py`.

- [x] Use `\n이번 진단:` in tooltip attributes and status-only `white-space: pre-line` CSS.
- [x] Add `_render_file_coverage(status)` with explicit validation of available integral counts and the documented denominator. Render a labeled percentage/count, not an unlabeled progress bar. Leave data dictionaries untouched.
- [x] For complete cards, omit details and use `선택한 범위의 분석을 완료했습니다.`; retain two collapsed sections in partial/failed/unknown cases.
- [x] Forward `analysis_status` to `_render_help_box(file_units, analysis_status)`. Add a support-scope section, preserve complete-case limitations and warning explanations there, and keep source values escaped.
- [x] Run the focused tests and review all rendering branches.

### Task 3: Existing HTML refresh and acceptance checks

Files: new `docs/_verification/2026-10-09-dashboard-status/coverage_layout.py`, 11 live case `index.html` files, `reports/verification-dashboard-coverage-2026-10-09.json`, short documentation note in `docs/compiler-aware-cpp.md`.

- [x] Prepare backups and validate all 11 documents before replacing CSS/help/status markup. Preserve all nonpresentation bytes, script bodies, header/time and prior JSON fingerprints.
- [x] Parse stored HTML; compare the current renderers' output; check collapsed states, complete-card details removal, native ratio labels and tooltip newlines; run `node --check` on unchanged scripts.
- [x] Run the full native-enabled suite with existing runtime paths. No installations or environment-file changes.
- [x] Record results, self-review against the spec, and hand off with the actual-browser limitation. No Git writes.

Verification: 43 focused tests passed; full native-enabled suite passed 300 tests in 51.02 seconds. All 11 saved reports matched the current renderer; prior 168 JSON files and all nonpresentation HTML bytes remained unchanged. Actual browser interaction was not verified because local file access was blocked.
