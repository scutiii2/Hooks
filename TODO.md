# Hooks TODO

- [ ] **Per-hook logs and audits.** Every hook records when and how it was triggered (event, matcher, working folder, what it did or skipped, outcome, duration), so a run can be traced afterwards. Applies to every hook under `hooks/`; the log helper exists in `core/py/` and `core/js/` (wired into `coding_rules` and `noise_filter` via `core/js/runlog.js`, one line per run in `.data/<hook>/runs.jsonl`). Open: shared log format and location, rotation, and how to keep a failing log from ever blocking a hook (hooks must fail open).
- [x] Restructure `AI/Hooks` into one repo: `core/py/`, `core/js/`, `hooks/<name>/`, `.data/`, `.memory/`, `.cache/`, `run.bat`, `monitor.bat` (done 2026-10-30).
