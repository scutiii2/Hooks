# Hooks

My Claude Code hooks in one repo. Five hooks live under `hooks/` (see "Project layout"); the big one is the opt-in skill router, **OFF by default**:

- **Skill router** — classifies each message against your installed skill catalog and suggests the best-fitting skill, so I invoke it directly instead of guessing.

It classifies with **Jev** (remote, paid, via TypeSafe's own API). The router never blocks a message — any failure, timeout, or low confidence just falls back to normal behavior, as if the router wasn't there.

## How it works

Claude Code's `UserPromptSubmit` hook can't replace a response or pick a model outright — it can only inject extra context or block a prompt. So the actual flow is:

1. A hook (`hooks/skill_router/hook.py`) runs before I see your message. It classifies the message and injects a tag like `[SKILL_SUGGESTION skill=code-review confidence=78%]`.
2. I read that tag and act on it per the rules in `CLAUDE.md`: invoke the suggested skill; with no tag, pick normally myself.
3. The hook fails open: any exception, timeout, or missing dependency and the tag is simply never emitted — you get normal behavior, nothing blocks.

## Setup

```bash
python -m venv .venv
```

Copy `.env.example` to `.env` and add your TypeSafe API key:

```
TYPESAFE_API_KEY=your-key-here
```

## Turning routers on/off

Defaults to **OFF**. Toggle with the CLI:

```bat
.venv\Scripts\python.exe -m core.py.tools.cli skill_router on|off|status
```

Or hand-edit `.data/skill_router/state.json` directly — `{"enabled": true|false}`.

**Privacy note**: every message you send while a router is ON is sent to TypeSafe AI (Jev's maker) over its API. Keep the routers off for private work. Prompts that mention secrets (`.env`, passwords, API/SSH/private keys, access tokens, credentials, `sk-…` keys; see `core/py/privacy.py`) are skipped automatically, but that match is a safety net, not a guarantee.

## Configuration

Each router has its own `config.json` (shown merged here; the batch size only matters to the skill router):

```json
{
  "confidence_threshold": { "jev": 60 },
  "skill_picker_batch_size": 20,
  "skill_min_confidence": { "loop": 85 }
}
```

| Setting | What it does |
|---|---|
| `confidence_threshold` | Cutoff a classification must clear before it's trusted enough to act on (`decision=use`). Below it, the router's pick is ignored and things proceed normally. This is a safety gate, not an accuracy knob — raising it reduces wrong dispatches at the cost of also losing some correct ones. |
| `skill_picker_batch_size` | Skill catalogs larger than this get split into batches, each judged separately, with a final round among batch winners. Batching has a real trade-off (see `hooks/skill_router/picker.py` for the tested reasoning) — don't lower it casually. |
| `skill_min_confidence` | Per-skill floor above the global threshold, for skills that over-trigger (suggested often, rarely followed). A skill named here needs at least that confidence. |

These live in `hooks/skill_router/config.json`. Anything set in `.env` (`CONFIDENCE_THRESHOLD`, `SKILL_PICKER_BATCH_SIZE`) overrides them, for quick one-off testing; see "Config and env" below.

## Skill router details

- Confidence-tag format: `[SKILL_SUGGESTION skill=<name> confidence=<N>%]`
- The catalog is built on every hook run (`hooks/skill_router/catalog.py`) from the `SKILL.md` files of installed plugins and the `.claude/skills` of the current folder and its parents: name plus the first sentence of the description. Skills with `disable-model-invocation: true` are left out. `~/.claude/skills` is not scanned (here it only mirrors the remote `anthropic-skills:*`).
- Skills with no usable file (Claude Code built-ins, remote `anthropic-skills:*`, a few plugin skills) are listed by hand in `hooks/skill_router/builtins.py`. A month after `VERIFIED`, the skill hook adds a `[BUILTIN_SKILLS_CHECK ...]` tag (at most once a day) asking Claude to compare that list with its own skill list, fix it and bump `VERIFIED`.
- Jev only ever *names* a skill (or `"none"`) — never runs or writes anything.
- Manual, on-demand test (no toggle needed): `.venv\Scripts\python.exe -m core.py.tools.cli skill_pick "your request text"`
- Always-on hook mode has its own switch (`.data/skill_router/state.json`).

## Training data / fine-tuning path

Every classification can be reviewed and turned into labeled data, for example to evaluate Jev's picks or to fine-tune a classifier of your own. This repo includes the data-collection half of that pipeline:

1. **Logging** — while a router is ON, every real classification is appended locally to `.data/skill_router/decisions.jsonl`. Nothing is sent anywhere beyond the classifier call that already happens.
2. **Review/correct** — `.venv\Scripts\python.exe -m core.py.tools.cli label skill` walks unreviewed entries one at a time: press Enter to accept the prediction, or type the correct label. Confirmed entries move to `.memory/core/labeled.jsonl`. Reruns only show new entries.
3. **Export** — `.venv\Scripts\python.exe -m core.py.tools.cli export skill > out.jsonl` converts labeled data into the `{state, questions, gold}` shape the fine-tuning notebook expects.

`.data/` and `.memory/` are gitignored — they are your data. The notebook's own benchmark used ~1,200 labeled cases; that's a rough sizing reference, not a hard requirement.

The decision log includes `session_id`. The PostToolUse hook records only the session, tool, target skill, and timestamp in `.data/core/followed.jsonl`, without tool prompts. The watcher (`.venv\Scripts\python.exe -m core.py.tools.cli watch`) shows these actions as green `followed` when they match the latest applicable `use` decision in the same session within five minutes, or yellow `unprompted` otherwise. To install all three hooks, run `.venv\Scripts\python.exe -m core.py.tools.manage_hooks add` yourself; installation updates your Claude settings and must be performed by you.

With the followed hook installed and `followed.jsonl` present, a live `use` decision with no matching action after 90 seconds prints a red `ignored?` hint once. The question mark matters: Claude may legitimately answer directly for a short reply that needs conversation context, and a skill suggestion is a hint, not a command.

## Codex

The hooks also run under Codex. Claude Code stays the default; Codex gets its own install target:

```bat
.venv\Scripts\python.exe -m core.py.tools.manage_hooks add --host codex
```

This adds the hooks below to `~/.codex/hooks.json` (`--host codex remove` takes them out again; other hooks in the file are kept). **Codex runs a hook only after you trust it**: open Codex and review the new hooks with `/hooks`. Installing changes your Codex config, so you run it yourself, as with Claude.

| Hook | On Codex |
|---|---|
| `coding_rules` | yes: SessionStart |
| `source_of_truth` | yes: SessionStart, and after `apply_patch` / Bash |
| `token_economizer_patch` | yes: SessionStart (it already patched both hosts) |
| `skill_router` | yes: `--host codex`. Its catalog is `.agents/skills` (project and `~/.agents`) plus the skills of Codex plugins. The tag tells Codex to use `$skill`, so no global protocol file is needed |
| `noise_filter` | no: Codex accepts `updatedInput` only together with `permissionDecision: "allow"` (on Claude that would skip the permission prompt), and the rewrite is a bash command line, while Codex on Windows runs `pwsh.exe` (seen in its session logs), where `mktemp`, `$?` and `{ }` do not work. Decided 2026-11-10: stays off Codex |
| followed-tracking | no: Codex has no Skill or Agent tool call to match, so Codex decisions are logged with `host: codex` and left out of `followed` / `ignored?` and `calibrate` |

The command strings were checked to run in bash, cmd and PowerShell, and the stdin and stdout fields follow Codex's hook documentation (`prompt`, `tool_name`, `hookSpecificOutput.additionalContext`). Not checked: a live Codex session running them, because that needs the hooks trusted first.

If `~/.codex/hooks.json` already has hooks from before the restructure (an entry for `TokenEconomizerPatch/te_patch.py`, or a copy of `noise-filter-pretooluse.js` under `~/.codex/hooks/`), they are not touched. The first points at a path that no longer exists, so remove it in `/hooks`.

## Web interface

```bat
run.bat web              # starts the web page and opens it in your browser
```

`run.bat web` opens `http://127.0.0.1:8765/` (`--port N` changes it). Two pages:

- **Home**: the commands the CLI offers (`skill_router`, `skill_pick`, `te_patch`, `source_of_truth`, `calibrate`, `export`, `settings`), each with an arguments box and a Run button; the output shows under the card. A command stops after 120 seconds and gets no keyboard input. `web` (this server), `watch` (live terminal view) and `label` (interactive review) run from the terminal with the CLI.
- **Backup**: export `.data/` and `.memory/` as one `hooks-backup-<time>.zip` in a folder (Browse button), or with a password as an encrypted `.hbk`. Import takes a backup file or a folder (newest backup in it; an older plain `data/` + `memory/` copy also works), overwrites same-named files and keeps the rest. The `.hbk` format is stdlib only (scrypt key, HMAC-SHA256 counter-mode cipher, HMAC tag checked before decrypting); it is home-built, so for secrets that matter, wrap the zip in a vetted tool such as 7-Zip AES-256 instead. Details in `core/py/tools/transfer.py`.
- **Logs**: one tab per log under `.data/` (`runs.jsonl`, `decisions.jsonl`, `failures.jsonl`, `followed.jsonl`), newest row first, refreshed every 2 seconds, with a text filter. Decision rows get the watcher's `followed` / `pending` / `ignored?` status. Prompt text is hidden until you tick "show prompts".

The server listens on 127.0.0.1 only and rejects other Host headers. Running a command needs a POST with `Content-Type: application/json`, which other websites cannot send without a CORS preflight this server never grants. Home can change things (`settings add`, `te_patch apply`, `skill_router on`), exactly like the CLI; the logs are read-only.

## Project layout

```
core/                   # shared code, one folder per language; both write the same .data/ logs
├── py/                 # for the Python hooks
│   ├── classifiers.py, provider.py   # the classifier (Jev) and its threshold
│   ├── config.py, env_load.py        # hooks/<hook>/config.json and layered .env
│   ├── paths.py, json_store.py       # folders under the root, JSON state/stats base
│   ├── training_log.py, runlog.py    # append-only JSONL logs (rotated at 10 MB); one runs.jsonl line per hook run
│   ├── hook_io.py, privacy.py        # payload in, tag out, skip rules
│   ├── toggle_cli.py, run_hook.py    # shared toggle CLI; runs a hook from any working folder
│   └── tools/                        # manage_hooks, watch_decisions, web (+ web.html), calibrate, label_review, export_training_data, log_followed
└── js/                 # for the Node hooks: paths.js, log.js, runlog.js (same data folders and log format as py; tests/test_js_core.py checks the log agrees)
hooks/
├── skill_router/       # skill picker: catalog, built-ins, picker, hook, state, toggle, config.json
├── coding_rules/       # SessionStart: injects my global coding rules (node)
├── noise_filter/       # PreToolUse(Bash): trims long output of installs, builds, full test runs (node); review 2026-11-19, remove if it saves under 10%
├── source_of_truth/    # keeps AGENTS.md as the single source for CLAUDE.md and skills
├── hide_plugin_windows/   # SessionStart: wraps plugin hooks so they open no terminal window (Windows)
└── token_economizer_patch/   # reapplies my patch on TokenEconomizer after updates
tests/                  # offline tests (`python -m pytest tests`); tests/manual/ holds real-classifier scripts (run with python -m tests.manual.<name>). The last two hooks keep their tests beside them.
run.bat web             # web interface on 127.0.0.1, opens the browser: Home (CLI commands) and Logs
.claude/                # settings.json
CLAUDE.md, AGENTS.md    # agent instructions (CLAUDE.md adds the skill router protocol)
.env.example            # copy to .env
```

### Local folders (all gitignored: every `.*` path is, except `.gitignore`, `.github/`, `.claude/`, `.env.example`)

| Folder | Holds |
|---|---|
| `.data/<hook>/` | what a hook creates: `state.json`, `stats.json`, `decisions.jsonl`, `runs.jsonl` (every run: event, folder, outcome, duration; no prompt text); `.data/core/` has the shared `followed.jsonl` and `failures.jsonl` |
| `.memory/` | what improves a hook: `core/labeled.jsonl`, the reviewed examples (`label_review`) |
| `.venv/` | the Python environment the hooks run with |

### Config and env

- `hooks/<hook>/config.json` holds that hook's settings. `.env` at the root holds global values (the Jev key); `hooks/<hook>/.env` overrides them for one hook. A real environment variable beats both.

## Known limitations

- Skill-picker batching can eliminate a correct answer before the final round if a topically-similar skill in the same batch scores higher (verified case: `loop` lost to `schedule` before ever facing its actual competitor). Raising the batch size to avoid this made the classifier *noisier* with more simultaneous options instead — a real trade-off, not a simple fix.
- Two near-duplicate skills in a catalog (e.g. two "schedule" skills) will confuse the picker regardless of tuning; worth consolidating if you hit this.

## Keeping prompts private

Prompts that look like secrets are never sent to the classifier. To keep more out, add rules in either file (same keys):

- global: `.privacy.json` in this repo's root (git-ignored)
- per project: `.claude/hooks-privacy.json` in the project folder or any parent; the nearest one wins

```json
{ "folders": ["D:/Clients"], "patterns": ["acme", "salary"] }
```

| Key | Where | Meaning |
|---|---|---|
| `folders` | global | prompts from these folders and below are never sent |
| `patterns` | both | prompts matching any regex (case-insensitive) are never sent; project patterns add to global ones |
| `private` | project | `true`: nothing from this project is sent. `false`: ignore the global `folders` here |
| `inherit` | project | `false`: ignore the whole global file for this project |

A file that exists but cannot be parsed counts as private.
