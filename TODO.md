# Hooks TODO

- [x] **Per-hook logs and audits.** Every hook records when and how it was triggered (event, working folder, outcome, duration), one line per run in `.data/<hook>/runs.jsonl`, via `core/js/runlog.js` and `core/py/runlog.py` (done 2026-10-30). The prompt text is never in it.
- [ ] **Codex.** Hooks install for Codex with `manage_hooks add --host codex` (done 2026-10-30); still to do by hand: trust them in Codex with `/hooks`. `noise_filter` stays off Codex: it needs `permissionDecision: "allow"` (skips approval) and bash, while Codex on Windows runs pwsh (decided 2026-11-10).
- [x] Restructure `AI/Hooks` into one repo: `core/py/`, `core/js/`, `hooks/<name>/`, `.data/`, `.memory/`, `.cache/`, `run.bat`, `monitor.bat` (done 2026-10-30).
