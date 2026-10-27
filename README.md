# ClaudeRouters

Two opt-in routers for Claude Code, both **OFF by default**:

- **Model router** — classifies each message by size (`tiny`/`everyday`/`large`/`hardest`) and, when confident enough, dispatches it to a Haiku- or Sonnet-pinned subagent instead of the main session model.
- **Skill router** — classifies each message against your installed skill catalog and suggests the best-fitting skill, so I invoke it directly instead of guessing.

Both classify with **Jev** (remote, paid, via TypeSafe's own API). Neither router ever blocks a message — any failure, timeout, or low confidence just falls back to normal behavior, as if the router wasn't there.

## How it works

Claude Code's `UserPromptSubmit` hook can't replace a response or pick a model outright — it can only inject extra context or block a prompt. So the actual flow is:

1. A hook (`src/model_router/hook.py` or `src/skill_router/hook.py`) runs before I see your message. It classifies the message and injects a tag like `[ROUTER size=large confidence=72% threshold=25% decision=use]` or `[SKILL_SUGGESTION skill=code-review confidence=78%]`.
2. I read that tag and act on it per the rules in `CLAUDE.md`: dispatch to a subagent (model router) or invoke a skill (skill router) when `decision=use`; otherwise answer/pick normally myself.
3. Both hooks fail open: any exception, timeout, or missing dependency and the tag is simply never emitted — you get normal behavior, nothing blocks.

## Setup

```bash
python -m venv .venv
```

Copy `.env.example` to `.env` and add your TypeSafe API key:

```
TYPESAFE_API_KEY=your-key-here
```

## Turning routers on/off

Both default to **OFF**. Toggle via CLI or the `.bat` file:

```bash
python -m src.model_router.toggle on|off|status
python -m src.skill_router.toggle on|off|status
```

```bat
scripts\router_toggle.bat                    :: interactive menu
scripts\router_toggle.bat model on|off|status
scripts\router_toggle.bat skill on|off|status
```

Or hand-edit `data/state/router_state.json` / `data/state/skill_router_state.json` directly — `{"enabled": true|false}`.

**Privacy note**: every message you send while a router is ON is sent to TypeSafe AI (Jev's maker) over its API. Keep the routers off for private work. Prompts that mention secrets (`.env`, passwords, API/SSH/private keys, access tokens, credentials, `sk-…` keys; see `src/core/privacy.py`) are skipped automatically, but that match is a safety net, not a guarantee.

## Configuration

`router_config.json` at the project root:

```json
{
  "confidence_threshold": { "jev": 60 },
  "skill_picker_batch_size": 20
}
```

| Setting | What it does |
|---|---|
| `confidence_threshold` | Cutoff a classification must clear before it's trusted enough to act on (`decision=use`). Below it, the router's pick is ignored and things proceed normally. This is a safety gate, not an accuracy knob — raising it reduces wrong dispatches at the cost of also losing some correct ones. |
| `skill_picker_batch_size` | Skill catalogs larger than this get split into batches, each judged separately, with a final round among batch winners. Batching has a real trade-off (see `src/skill_router/picker.py` for the tested reasoning) — don't lower it casually. |

Anything set in `.env` (`CONFIDENCE_THRESHOLD`, `SKILL_PICKER_BATCH_SIZE`) overrides `router_config.json`, for quick one-off testing.

## Model router details

- Confidence-tag format: `[ROUTER size=<size> confidence=<N>% threshold=<T>% decision=<use|fallback>]`
- Size → subagent mapping (see `CLAUDE.md`): `tiny`/`everyday` → `router-haiku`, `large`/`hardest` → `router-sonnet` (`.claude/agents/router-haiku.md`, `.claude/agents/router-sonnet.md`).
- Short, conversation-only replies (e.g. "yes do that but shorter") are filtered out by a regex heuristic before classification even runs — they're always handled by me directly.
- Stats: `python -m src.model_router.toggle status` shows counts by size and failures.

## Skill router details

- Confidence-tag format: `[SKILL_SUGGESTION skill=<name> confidence=<N>%]`
- Catalog lives in `src/skill_router/catalog.py` — name + one-line purpose per skill. Keep it in sync by hand when skills are added/removed. `python -m src.tools.check_catalog` lists installed skills missing from it (built-in and remote skills show as "unverified"; that is normal).
- Jev only ever *names* a skill (or `"none"`) — never runs or writes anything.
- Manual, on-demand test (no toggle needed): `python -m src.skill_router.pick "your request text"`
- Always-on hook mode has its own switch (`data/state/skill_router_state.json`), independent of the model router.

## Training data / fine-tuning path

Every classification can be reviewed and turned into labeled data, for example to evaluate Jev's picks or to fine-tune a classifier of your own. This repo includes the data-collection half of that pipeline:

1. **Logging** — while a router is ON, every real classification is appended locally to `data/training/model_router_log.jsonl` / `skill_router_log.jsonl`. Nothing is sent anywhere beyond the classifier call that already happens.
2. **Review/correct** — `python -m src.tools.label_review model|skill` walks unreviewed entries one at a time: press Enter to accept the prediction, or type the correct label. Confirmed entries move to `data/training/labeled.jsonl`. Reruns only show new entries.
3. **Export** — `python -m src.tools.export_training_data model|skill > out.jsonl` converts labeled data into the `{state, questions, gold}` shape the fine-tuning notebook expects.

`data/training/` is gitignored — it's your data. The notebook's own benchmark used ~1,200 labeled cases; that's a rough sizing reference, not a hard requirement.

Both decision logs include `session_id`. The PostToolUse hook records only the session, tool, target skill/subagent, and timestamp in `data/training/followed_log.jsonl`, without tool prompts. The watcher (`python -m src.tools.watch_decisions`) shows these actions as green `followed` when they match the latest applicable `use` decision in the same session within five minutes, or yellow `unprompted` otherwise. To install all three hooks, run `.venv\Scripts\python.exe -m src.tools.manage_hooks add` yourself; installation updates your Claude settings and must be performed by you.

With the followed hook installed and `followed_log.jsonl` present, a live `use` decision with no matching action after 90 seconds prints a red `ignored?` hint once. The question mark matters: Claude may legitimately answer directly for a short reply that needs conversation context, and a skill suggestion is a hint, not a command.

## Project layout

```
src/
├── core/               # classifiers, config, JSON storage base
│   ├── classifiers.py  # Classifier ABC, JevClassifier
│   ├── provider.py     # the classifier (Jev) and its threshold
│   ├── config.py       # router_config.json loader with env-var overrides
│   ├── json_store.py   # base class for on/off-switch and stats files
│   └── training_log.py # append-only JSONL logging for fine-tuning data
├── model_router/       # size classifier: state, toggle CLI, hook
├── skill_router/       # skill picker: catalog, picker, state, toggle CLI, hook, manual pick CLI
├── cli/                # shared ToggleCLI base class
└── tools/              # label_review, export_training_data, manage_hooks, watch_decisions, log_followed

tests/                  # offline tests (`pytest tests`); tests/manual/ holds real-classifier scripts (run with python -m tests.manual.<name>)
scripts/                # Windows launchers: router_toggle.bat, manage_hooks.bat, watch_decisions.bat
data/                   # generated, gitignored: state/, stats/, training/
.claude/                # settings.json (hooks), agents/ (router-haiku.md, router-sonnet.md)
CLAUDE.md, AGENTS.md    # agent instructions (CLAUDE.md adds the router protocols)
router_config.json      # adjustable settings
.env, .env.example      # secrets + optional per-run overrides
```

## Known limitations

- Skill-picker batching can eliminate a correct answer before the final round if a topically-similar skill in the same batch scores higher (verified case: `loop` lost to `schedule` before ever facing its actual competitor). Raising the batch size to avoid this made the classifier *noisier* with more simultaneous options instead — a real trade-off, not a simple fix.
- Two near-duplicate skills in a catalog (e.g. two "schedule" skills) will confuse the picker regardless of tuning; worth consolidating if you hit this.
