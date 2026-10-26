# Joint advisor implementation plan

User approved the preceding design discussion. Implement in place; no Git mutations or live AI calls. Use isolated synthetic fixtures. Apply writing-plans, TDD and subagent-driven development with file ownership to avoid collisions.

- [x] Main: tests then bounded source context builder, fresh per-file response validation, separate pre-review cache/API, source hashes and legacy preservation.
- [x] UI worker: tests then overview + per-file tabs in proposals/diffs/results, pre-review controls/cache display, concise progress/game card, right-aligned actions. Own assistant.html/js/css and assistant-view.js.
- [x] Layout/demo worker: response-only full-width table wrapper and real demo build progress metadata. Own report-embed.js/css, report-light.css, demo.py, casual_demo.py and focused tests.
- [x] Integration: preserve live preview SHA and school/report hashes; inspect real stored response plus synthetic new response, all five file decisions, cache reuse/invalidation, compact >360KB inputs, no out-of-scope apply.
- [x] Verify: browser blue/dark/light widths and tab switching, concise UI and progress, isolated cache flow; relevant then full tests with .NET8/Clang; independent spec and quality review; docs/handoff/screenshots. No new actual AI response or gameplay claim.

Final evidence: 473 tests passed; JS syntax checks passed; live preview, school originals, report v2 Word/PDF and HEAD unchanged. See docs/joint-advisor-verification-2026-10-19.md and docs/_ops/next_codex_session_handoff_2026-10-19.md. Actual new AI requests and pending game edits were not executed; synthetic fixtures exercised the end-to-end UI.
