# ClaudeRouters

Two opt-in routers for Claude Code, both **OFF by default**:

- **Model router** — classifies each message by size (`tiny`/`everyday`/`large`/`hardest`) and, when confident enough, dispatches it to a Haiku- or Sonnet-pinned subagent instead of the main session model.
- **Skill router** — classifies each message against your installed skill catalog and suggests the best-fitting skill, so I invoke it directly instead of guessing.

Both use a pluggable classifier: **Laya** (local, free, runs on your machine) or **Jev** (remote, paid, via TypeSafe's own API). Neither router ever blocks a message — any failure, timeout, or low confidence just falls back to normal behavior, as if the router wasn't there.

## How it works

Claude Code's `UserPromptSubmit` hook can't replace a response or pick a model outright — it can only inject extra context or block a prompt. So the actual flow is:

1. A hook (`router/model_router/hook.py` or `router/skill_router/hook.py`) runs before I see your message. It classifies the message and injects a tag like `[ROUTER size=large confidence=72% threshold=25% decision=use]` or `[SKILL_SUGGESTION skill=code-review confidence=78%]`.
2. I read that tag and act on it per the rules in `CLAUDE.md`: dispatch to a subagent (model router) or invoke a skill (skill router) when `decision=use`; otherwise answer/pick normally myself.
3. Both hooks fail open: any exception, timeout, or missing dependency and the tag is simply never emitted — you get normal behavior, nothing blocks.

## Setup

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # installs laya (local classifier)
```

Copy your TypeSafe API key into `.env` if you want to use Jev instead of Laya:

```
TYPESAFE_API_KEY=your-key-here
```

Laya needs no API key — it downloads model weights (~1.6GB, one-time) to your machine on first use.

## Turning routers on/off

Both default to **OFF**. Toggle via CLI or the `.bat` file:

```bash
python -m router.model_router.toggle on|off|status
python -m router.skill_router.toggle on|off|status
```

```bat
router_toggle.bat                    :: interactive menu
router_toggle.bat model on|off|status
router_toggle.bat skill on|off|status
```

Or hand-edit `router_state.json` / `skill_router_state.json` directly — `{"enabled": true|false}`.

**Privacy note**: with `PROVIDER=laya` (the default), classification runs entirely on your machine — nothing leaves it. With `PROVIDER=jev`, every message you send while the router is ON is sent to TypeSafe AI (Jev's maker) over its API. Keep routers off, or switch to `laya`, for private work.

## Laya server (why the first prompt is skipped)

Loading Laya takes ~35 s, far over a hook's timeout, so with `provider=laya` the hooks ask one resident background process (`router/core/laya_server.py`, loopback `127.0.0.1:8765` only, ~1.6 GB RAM) instead of loading the model themselves. If it is not running, the hook skips that prompt, starts it in the background, and prompts after it has loaded (~15-35 s) are routed. Output goes to `laya_server.log`.

```bash
python -m router.core.laya_server status   # running / not running
python -m router.core.laya_server stop     # free the RAM
```

To start it at every login, run `laya_server.bat autostart-on` yourself (it creates a scheduled task; `autostart-off` removes it). Or use `laya_server.bat` with no arguments for a menu.

Port: `laya_server_port` in `router_config.json` or `LAYA_SERVER_PORT` in `.env`. It stays up until you stop it or reboot.

## Configuration

`router_config.json` at the project root:

```json
{
  "provider": "laya",
  "confidence_threshold": { "jev": 60, "laya": 25 },
  "skill_picker_batch_size": 20
}
```

| Setting | What it does |
|---|---|
| `provider` | `"laya"` (local, free) or `"jev"` (remote, paid, needs a TypeSafe API key) |
| `confidence_threshold` | Per-provider cutoff a classification must clear before it's trusted enough to act on (`decision=use`). Below it, the router's pick is ignored and things proceed normally. This is a safety gate, not an accuracy knob — raising it reduces wrong dispatches at the cost of also losing some correct ones. |
| `skill_picker_batch_size` | Skill catalogs larger than this get split into batches, each judged separately, with a final round among batch winners. Batching has a real trade-off (see `router/skill_router/picker.py` for the tested reasoning) — don't lower it casually. |

Anything set in `.env` (`PROVIDER`, `CONFIDENCE_THRESHOLD`, `SKILL_PICKER_BATCH_SIZE`) overrides `router_config.json`, for quick one-off testing.

## Model router details

- Confidence-tag format: `[ROUTER size=<size> confidence=<N>% threshold=<T>% decision=<use|fallback>]`
- Size → subagent mapping (see `CLAUDE.md`): `tiny`/`everyday` → `router-haiku`, `large`/`hardest` → `router-sonnet` (`.claude/agents/router-haiku.md`, `.claude/agents/router-sonnet.md`).
- Short, conversation-only replies (e.g. "yes do that but shorter") are filtered out by a regex heuristic before classification even runs — they're always handled by me directly.
- Stats: `python -m router.model_router.toggle status` shows counts by size and failures.

## Skill router details

- Confidence-tag format: `[SKILL_SUGGESTION skill=<name> confidence=<N>%]`
- Catalog lives in `router/skill_router/catalog.py` — name + one-line purpose per skill. Keep it in sync by hand when skills are added/removed.
- Jev/Laya only ever *names* a skill (or `"none"`) — never runs or writes anything.
- Manual, on-demand test (no toggle needed): `python -m router.skill_router.pick "your request text"`
- Always-on hook mode has its own switch (`skill_router_state.json`), independent of the model router.

## Training data / fine-tuning path

Laya's confidence scores are explicitly uncalibrated on this checkpoint, which limits how well a confidence threshold can work. A real fix is fine-tuning Laya on your own labeled examples, using [Laya's Kaggle notebook](https://github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb) (free 2xT4 GPUs, ~5 min training once you have data). This repo includes the data-collection half of that pipeline:

1. **Logging** — while a router is ON, every real classification is appended locally to `training_data/model_router_log.jsonl` / `skill_router_log.jsonl`. Nothing is sent anywhere beyond the classifier call that already happens.
2. **Review/correct** — `python -m router.tools.label_review model|skill` walks unreviewed entries one at a time: press Enter to accept the prediction, or type the correct label. Confirmed entries move to `training_data/labeled.jsonl`. Reruns only show new entries.
3. **Export** — `python -m router.tools.export_training_data model|skill > out.jsonl` converts labeled data into the `{state, questions, gold}` shape the fine-tuning notebook expects.

`training_data/` is gitignored — it's your data. The notebook's own benchmark used ~1,200 labeled cases; that's a rough sizing reference, not a hard requirement.

Both decision logs include `session_id`. The PostToolUse hook records only the session, tool, target skill/subagent, and timestamp in `training_data/followed_log.jsonl`, without tool prompts. The watcher (`python -m router.tools.watch_decisions`) shows these actions as green `followed` when they match the latest applicable `use` decision in the same session within five minutes, or yellow `unprompted` otherwise. To install all three hooks, run `.venv\Scripts\python.exe -m router.tools.manage_hooks add` yourself; installation updates your Claude settings and must be performed by you.

With the followed hook installed and `followed_log.jsonl` present, a live `use` decision with no matching action after 90 seconds prints a red `ignored?` hint once. The question mark matters: Claude may legitimately answer directly for a short reply that needs conversation context, and a skill suggestion is a hint, not a command.

## Project layout

```
router/
├── core/               # provider-agnostic: classifiers, config, provider switch, JSON storage base
│   ├── classifiers.py  # Classifier ABC, JevClassifier, LayaClassifier
│   ├── provider.py     # picks a classifier per router_config.json / env
│   ├── config.py       # router_config.json loader with env-var overrides
│   ├── json_store.py   # base class for on/off-switch and stats files
│   └── training_log.py # append-only JSONL logging for fine-tuning data
├── model_router/       # size classifier: state, toggle CLI, hook
├── skill_router/       # skill picker: catalog, picker, state, toggle CLI, hook, manual pick CLI
├── cli/                # shared ToggleCLI base class
├── tools/              # label_review.py, export_training_data.py
└── tests/              # manual real-classifier test scripts

.claude/
├── settings.json       # wires both hooks into UserPromptSubmit
└── agents/              # router-haiku.md, router-sonnet.md subagent definitions

CLAUDE.md                # my own instructions for reading router tags
router_config.json        # adjustable settings
.env                       # secrets + optional per-run overrides
router_toggle.bat          # Windows toggle shortcut
```

## Known limitations

- Laya's confidence isn't well-calibrated on this checkpoint (its own disclosed limitation) — treat raw picks as more trustworthy than the confidence number.
- Skill-picker batching can eliminate a correct answer before the final round if a topically-similar skill in the same batch scores higher (verified case: `loop` lost to `schedule` before ever facing its actual competitor). Raising the batch size to avoid this made Laya *noisier* with more simultaneous options instead — a real trade-off, not a simple fix.
- Two near-duplicate skills in a catalog (e.g. two "schedule" skills) will confuse the picker regardless of tuning; worth consolidating if you hit this.
