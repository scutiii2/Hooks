# SourceOfTruth

Keeps a single source of truth for agent rules and skills in every project under `Programming/`.

| Source of truth | Pointer for Claude Code |
|---|---|
| `AGENTS.md` | `CLAUDE.md` containing `@AGENTS.md` |
| `.agents/skills/` | `.claude/skills` symlink to `../.agents/skills` |
| each skill in `.agents/skills/` | a link `~/.codex/skills/<name>` so Codex loads the same copy |

Codex reads the source of truth directly. Claude Code follows the pointer. Nothing is ever copied or synced.

## What it does

Runs on SessionStart and after Write, Edit and Bash tool calls. It looks at the session folder and its git root, and only inside `Programming/`:

- real `.claude/skills/` and no `.agents/skills/`: moves it to `.agents/skills/`, links it back;
- `.agents/skills/` and no `.claude/skills`: adds the link;
- `CLAUDE.md` with real rules and no `AGENTS.md`: moves the rules to `AGENTS.md`, leaves `@AGENTS.md`;
- `AGENTS.md` and no `CLAUDE.md`: writes the `@AGENTS.md` stub;
- a skill with no `~/.codex/skills/<name>` link: adds the link (a link or junction already there is fine; a real folder is left alone and reported).

It never overwrites or deletes. If two real copies exist, it leaves both and reports it at the next SessionStart. A project with no rules or skills yet is left alone. Failures exit 0 silently; a hook must not block.

## Install (not done yet)

Add to `~/.claude/settings.json` under `hooks` (user level, so it covers every project):

```json
"SessionStart": [{"hooks": [{"type": "command", "command": "py \"D:/User/Documents/Programming/AI/Hooks/SourceOfTruth/source_of_truth.py\"", "timeout": 10}]}],
"PostToolUse": [{"matcher": "Write|Edit|MultiEdit|Bash", "hooks": [{"type": "command", "command": "py \"D:/User/Documents/Programming/AI/Hooks/SourceOfTruth/source_of_truth.py\"", "timeout": 10}]}]
```

Append to the existing arrays; keep the other hooks. Codex can use the same command in `~/.codex/hooks.json`.

## Use and test

```
py source_of_truth.py "D:/User/Documents/Programming/Python/Citadel"   # run by hand
py -m unittest test_source_of_truth                                    # from this folder
```

Needs Python 3.11+ and, on Windows, Developer Mode for native symlinks. To watch another root, change `ROOTS` in `source_of_truth.py`.
