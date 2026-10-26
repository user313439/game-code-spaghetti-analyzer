# Advisor experience implementation plan

> Execute inline with executing-plans and test-driven-development. The user approved the described design. Existing user constraints override skill suggestions to commit or branch.

**Goal:** Make the static analysis → readable advice → code approval → explained results → casual game flow understandable and verifiable.

**Architecture:** Preserve stored reports and sandbox isolation. Add response-only embedded sizing and hover fixes, shared theme control, testable presentation helpers, and three workspace steps. Keep actual AI replies immutable; derive explanations from their contents and measured results. Adapt a fixed trusted demo recipe to the selected new game.

**Tech Stack:** Existing FastAPI/Python, plain DOM JavaScript/CSS, pytest/Node, official CLI, existing C/C++ build environment.

## Task 1 — report scrolling and themes

Files: `app.py`, `static/report-embed.js`, `report-light.css`, `report-blue.css`, `theme.js`, `theme.css`, existing index/app JS, tests.
- [x] Add a failing embedded response test asserting `ResizeObserver` and no original-file mutation; preserve report CSP sandbox.
- [x] Inject frame sizing only with `embedded=1`. Parent accepts finite bounded height only from its report window.
- [x] Add failing theme tests for explicit query precedence, saved blue/dark preference, and white preservation. Implement shared toggle and apply theme to iframe URL.
- [x] Fix `.sec-info:hover` foreground/background consistently in response CSS; inspect collapsed/expanded hover in both themes.

## Task 2 — readable three-step workspace

Files: `assistant.html`, `assistant.js`, `assistant.css`, new `assistant-view.js`, tests.
- [x] Test pure aligned diff rows on insertion/deletion/replacement and HTML-looking source. Tests use Node assert and actual module exports.
- [x] Test result summary: `cc 29→28.2, SI 84.12→84.12` must say CC decreased and SI unchanged, never stability improved. Preserve unknown/failed verification states.
- [x] Implement 01/02/03 navigation, bottom CTA, existing SVG, compact scope/connection settings, polite proposal sections and side-by-side code preview.
- [x] Implement result summary first, then metric/function details. Move results out of advisor step. Render user/AI content with textContent.
- [x] Single modified-game action prepares when necessary then launches; expandable control instructions. Keep old backend recipe endpoints for existing evidence.
- [x] Extend new AI guidance with polite Korean and explicit what/why/expected-effect structure. Do not rewrite historical actual AI records.

## Task 3 — casual demo selection and preparation

Files: new `docs/_demo_phase_v2/`, candidate comparison, fixed demo recipe and tests.
- [x] Compare OpenTyrian, official raylib Asteroids Survival, and a verified third casual project using primary sources and actual source inspection. Record revision/license/build/scale/tradeoffs.
- [x] Download only official source/assets and preserve source hashes. Build selected original before deciding on refactor scope.
- [x] Run a new actual analysis and CLI advice/preview, review generated changes, apply to a separate copy, reanalyze and build.
- [x] Verify changed behavior with focused characterization or available replay/tests. Keep a truthful interactive-play status. Save evidence and easy launcher.

## Task 4 — end-to-end review

- [x] Browser inspect logo, full-page scrolling, bottom CTA, 3 steps, readable polite copy, aligned diff, outcome explanation, theme persistence and help hover.
- [x] Run relevant tests during changes, then full suite with .NET 8 and available optional Clang library. Save results.
- [x] Compare preserved report/school-source hashes, inspect Git diff scope, update usage/verification docs and handoff. No Git mutations.

## Final verification — 2026-10-18

All checklist items above were completed within their stated scope. Full suite: 442 passed; final presentation/web checks: 72 passed. Cold launcher start was verified with browser opening mocked. The actual game window launched, but interactive gameplay was not verified because Windows capture failed twice. The focused calculation comparison had 0 mismatches across 219,024 inputs and 512,000 update steps. See docs/advisor-experience-verification-2026-10-18.md for scope and preserved evidence. No commits, branches, push, paid API calls, or report-v2 edits.
