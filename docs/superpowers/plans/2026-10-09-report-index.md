# Report Index Implementation Plan

> **For agentic workers:** Execute the approved scoped update inline with review checkpoints. Preserve the user's existing checkout and changes. No branches, commits, pushes, browser workarounds or new game analyses.

**Goal:** Add author identity and the DOOM 3 partial case, remove duplicate help, and collapse OpenRA supplementary cases.

**Architecture:** The canonical landing page is the hand-maintained `reports/index.html`. Change only its approved presentation regions and add tests against saved HTML/current result JSON. Existing per-case HTML and analysis data remain immutable.

**Tech Stack:** Existing HTML/CSS and Python/pytest with standard-library HTML parsing.

### Task 1: Regression tests

- [x] Create `tests/test_report_index.py`: assert author in header, absence of duplicate usage section, original four primary links, collapsed auxiliary disclosure with four links, and distinct DOOM expansion card with truthful scope/counts from JSON. Example: `assert '2018313439 · 안영진' in header`.
- [x] Check all nine local case links resolve beneath reports and sample-only OpenRCT2 is not promoted. Verify source information identifies four game repositories without claiming four-project statistical validation.
- [x] Run `py -3.10 -B -m pytest tests/test_report_index.py -q -p no:cacheprovider` and observe the missing layout fail before changing HTML.

### Task 2: Landing page only

- [x] Snapshot the current root index, all per-case/archive HTML and all report JSON fingerprints to a new local verification folder before editing.
- [x] Add `.project-author` header text/CSS and remove only the duplicate `대시보드 사용법 간단 정리` section.
- [x] Keep the main four cards unchanged; add an independent `컴파일 설정 기반 확장 사례` section linking DOOM 3 Clang. Show partial state, selected 69 files, 4,375 methods/functions and compiler diagnostic input counts; no whole-game or equal-statistical-validation claim.
- [x] Wrap OpenRA auxiliary cards in a collapsed `details`, convert cards to the existing HTML links, keep Server's insufficient-sample notice, and replace technical wording with a short scope explanation.
- [x] Update introduction/target metadata for DOOM 3 and optional Clang while retaining the original three-project statistical validation boundary.
- [x] Run focused tests, inspect HTML tag nesting, and compare the original four primary cards byte-for-byte with the snapshot.

### Task 3: Acceptance and handoff

- [x] Verify saved report links, initial collapsed state, source/count accuracy and unchanged per-case HTML/report JSON; write a new `reports/verification-report-index-2026-10-09.json` without replacing earlier evidence.
- [x] Run full native-enabled `py -3.10 -B -m pytest tests/ -q -p no:cacheprovider` with the existing runtime paths. Check whitespace diff.
- [x] Record actual test results and recheck fingerprints. Hand off the root index for user refresh/feedback; actual browser interaction remains unverified due local file security policy.
