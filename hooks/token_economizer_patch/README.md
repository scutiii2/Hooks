# TokenEconomizerPatch

Installs TokenEconomizer for Claude Code and Codex when missing, then keeps the Claude-history bootstrap patch on it across updates.

- `history-bootstrap.patch`: our changes to upstream `tokeneconomizer/`.
- `te_patch.py`: SessionStart hook on both hosts (`~/.claude/settings.json`, `~/.codex/hooks.json`).
  - plugin missing on an enabled host: runs `<host> plugin marketplace add microsoft/TokenEconomizer` and the host's plugin install, detached in the background (lock `.ensure.lock`);
  - plugin installed: re-applies the patch if an update dropped it;
  - upstream changed the same lines: status `conflict`, bootstrap stays off there until `refresh`.
  - Fails open; speaks only on install, re-apply or conflict.
- Per-host switch: Claude `enabledPlugins`, Codex `[plugins."tokeneconomizer@tokeneconomizer"] enabled`. A host switched off is not installed or patched.

```
py te_patch.py status
py te_patch.py off [claude|codex]   # disable plugin, remove patch
py te_patch.py on  [claude|codex]   # enable plugin, install if missing, apply patch
py te_patch.py ensure               # install + patch now, in the foreground
py te_patch.py update [claude|codex]   # remove patch, update from the marketplace, re-apply
py te_patch.py rebuild [claude|codex]  # uninstall, reinstall from the marketplace, apply patch
```

`run.bat` is a two-stage menu over these: pick Claude or Codex, then Status, Update, Rebuild, Turn ON, Turn OFF, Run tests, Back.

```
py te_patch.py refresh              # rebuild patch from the Claude marketplace clone's git diff
```

Not verified: the Codex install and patch on a real machine. Codex drops the `lib` symlink on install, so the package is imported from the marketplace checkout; `CodexHost.targets` looks for that under `~/.codex`. If it is not found, `status` shows Codex as not installed and nothing is patched.
Also, Codex's history import is not implemented: the patch reads only `~/.claude/projects`.
`test_live_history.py` is a copy of the feature test (belongs in the clone's `tests/`). Tests: `py -m pytest test_te_patch.py`.
