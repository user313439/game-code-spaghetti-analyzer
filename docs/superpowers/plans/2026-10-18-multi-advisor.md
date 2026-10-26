# Multi-advisor implementation plan

> Execute inline with executing-plans and test-driven-development. User authorization covers the requested UI and multi-selection work. Final read-only review is delegated as required by requesting-code-review. No commits, branches, push or paid API calls.

**Goal:** Select up to five scored files, review one combined change, observe truthful progress and clearer results.

**Architecture:** Extend the existing request/state contract compatibly. Keep all raw AI records, original source checks, copy-only apply and sandbox report. One provider call per advice/preview. UI helpers derive facts from all changed rows.

**Tech Stack:** Existing FastAPI/Python, DOM JS/CSS, pytest/Node, browser QA.

- [x] Add endpoint tests for two selected files in one provider call, complete source-hash coverage, exact selection match, no out-of-scope edits and max-five/duplicate-file bounds. Run red.
- [x] Extend `AssistantRequest` and `AssistantJobs.start/_generate` to bounded multi-selection with legacy fallback. Publish real stage metadata, elapsed/estimated timing and immutable original evidence. Run endpoint tests green.
- [x] Add helper tests that multi-file summaries include every score pair, unknown estimates stay unknown, stage counts are not fake time percentages, and ranking cards deduplicate files. Run red, then implement in `assistant-view.js`.
- [x] Modify `assistant.html/js/css`: scored checkboxes, one-request notice, separate label/answer panels, stage progress shared across 02/03, immediate apply transition, distinct result hero and bottom-right game action. Keep textContent rendering and historical single records.
- [x] Browser check blue/dark/white, selected count and sixth-file refusal, narrow layout, advice/preview/apply progress and error state using isolated test records. Save screenshots; never replace actual game evidence.
- [x] Run relevant checks and full suite in existing .NET/Clang environment, JS syntax and diff checks. Update guide/handoff with measured verification and limitations.

Final verification: 456 full tests, 86 final related tests, independent read-only review with no actionable findings. Browser used synthetic AI replies for the five-file flow and missing-key validation error. Worker/error boundaries are covered by API tests. Reduced viewport capture was unavailable; responsive CSS was reviewed. Preserved school/report and live-game-state SHA checks passed.
