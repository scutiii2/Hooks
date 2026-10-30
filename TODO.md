# Hooks TODO

- [ ] **Per-hook logs and audits.** Every hook records when and how it was triggered (event, matcher, working folder, what it did or skipped, outcome, duration), so a run can be traced afterwards. Applies to every hook under `hooks/`; the log helper exists in `core/py/` and `core/js/` (wired into `coding_rules` and `noise_filter` via `core/js/runlog.js`, one line per run in `.data/<hook>/runs.jsonl`). Open: the Python hooks (`model_router`, `skill_router`, `source_of_truth`, `token_economizer_patch`) still need the same run log. Format, location, 10 MB rotation and fail-open are settled.
- [x] Restructure `AI/Hooks` into one repo: `core/py/`, `core/js/`, `hooks/<name>/`, `.data/`, `.memory/`, `.cache/`, `run.bat`, `monitor.bat` (done 2026-10-30).
