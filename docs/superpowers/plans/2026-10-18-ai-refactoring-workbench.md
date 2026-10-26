# AI Refactoring Workbench Implementation Plan

> Execute inline using executing-plans, with test-driven-development and verification-before-completion. User approved stage 1 and, where feasible, stage 2; no commits, branches, paid API calls, or changes to preserved results.

**Goal:** A local results workspace that generates grounded AI advice, previews exact changes, applies them to a separate source copy, reanalyzes, and prepares a playable game demonstration.

**Architecture:** Keep stored reports and their sandbox unchanged inside a results workspace iframe. New local endpoints manage independent AI tasks and revision copies. Provider adapters use installed official CLIs or explicit session-only user API credentials; no automatic billing fallback. AI can propose exact text replacements but cannot run commands. Applying requires source hash checks and a validated preview identifier. Original sources remain untouched.

**Tech Stack:** Existing FastAPI, Python stdlib subprocess/HTTP, existing analyzer, native browser UI, pytest.

## Task 1: AI provider and patch boundaries

Files: create `game_si/web/assistant.py`, `tests/test_web_assistant.py`.
- [x] Write tests proving traversal, ambiguous replacements, stale hashes, and missing credentials are rejected; original source bytes are preserved.
- [x] Run failing tests before implementation.
- [x] Implement a provider-neutral request with `reasons`, `suggestions`, `tests`, `uncertainty`, and optional `edits` entries (`path`, `old`, `new`). Limit file sizes, selected candidates, outputs and time. Preserve exact UTF-8 newlines and input SHA.
- [x] Implement Codex/Claude/Gemini CLI adapters with restricted tools and explicit authentication modes, plus user-key API adapters. Never read or display credential files; never persist supplied API keys.
- [x] Validate replies before saving. Unknown services, unsupported paths, external URLs, missing snippets, and malformed edits must fail with user-readable messages.

## Task 2: Web workspace and routes

Files: modify `game_si/web/app.py`, `game_si/web/static/app.js`; create `game_si/web/static/assistant.html`, `assistant.js`, `assistant.css`; extend tests.
- [x] Write route tests for CSRF protection, hidden/deleted jobs, independent task states, advice persistence, preview/apply hashes, and report preservation.
- [x] Mount `/workspace/{ident}` with the old report in a sandboxed iframe and a separate AI tab. Keep static reports immutable. Only render successful advice and validated diffs using DOM textContent.
- [x] Add capabilities, candidates, generate advice, generate preview, apply revision, poll status and download changed source endpoints.
- [x] Successful apply means a separate revision copy exists; reanalysis has its own state and link. No claim of successful game build or bug freedom from apply alone.

## Task 3: Actual provider verification

- [x] Use the existing ChatGPT-authenticated Codex only, without API key environment variables, on one selected candidate. Persist provider/model/time/source SHA and the exact advice and preview. Do not fabricate successful calls to unavailable providers.
- [x] Verify the full workflow in browser and meaningful backend tests. Run the existing relevant suite and then full tests once implementation is stable.

## Task 4: Game demonstration

- [x] Assess Chocolate Doom using existing fixed source and freely distributable Freedoom assets; preserve benchmarks. Confirm build environment and replay support before selection.
- [x] Store original/modified source, original/modified analysis, executables, actual AI artifacts, changes, logs and a concise Korean start page together in `docs/_demo_phase/`.
- [x] Refactor one explainable part using actual generated advice and review. Compare raw metrics and behavior rather than promising lower relative G-SI.
- [x] Build both versions and run reproducible replay/characterization checks where supported. State precisely whether interactive gameplay was inspected or only replay/build verified.
- [x] Provide one entry point for opening results and launching the prepared game; no IDE required. Preserve licenses.

## Acceptance

No paid API calls or Git mutations. No original source/report overwrite. AI failure does not erase analysis. Keys absent from files/logs/results. Advice is tied to exact source. The user can see a diff before apply, apply to a copy, open reanalysis and obtain the modified sources. Demo claims match actual build/replay/browser evidence. Existing final-report v2 remains an earlier snapshot until new verified results warrant a new version.

## Verification outcome

Implemented and reviewed inline. Full suite: 357 passed, 80 skipped. Live Codex advice and preview, separate-copy apply/reanalysis and fixed demo builds succeeded. Input characterization: 32,768 cases, zero differences. Three IWAD demos completed in both builds. Interactive gameplay remains unverified because Windows capture failed twice; no play-success claim is made. See docs/ai-refactoring-verification-2026-10-18.md for limits and evidence.
