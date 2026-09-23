"""Convert training_data/labeled.jsonl into the {state, questions, gold}
shape used by Laya's fine-tuning notebook:
https://github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb

Usage:
    python -m router.tools.export_training_data model  > model_router_train.jsonl
    python -m router.tools.export_training_data skill   > skill_router_train.jsonl

Only "kind" matching entries are exported; each labeled.jsonl row becomes
one training case. Run this once you have enough labeled data to be worth
fine-tuning on (the notebook itself was trained on ~1,200 cases).
"""
import json
import sys

from ..core.training_log import labeled_log
from ..core.classifiers import SIZE_CRITERIA
from ..skill_router.catalog import SKILLS

MODEL_CRITERIA = SIZE_CRITERIA
SKILL_CRITERIA = {name: desc for name, desc in SKILLS}
SKILL_CRITERIA["none"] = "nothing here fits well"

KIND_CONFIG = {
    "model": {"kind": "model_router", "gold_field": "size", "criteria": MODEL_CRITERIA},
    "skill": {"kind": "skill_router", "gold_field": "skill", "criteria": SKILL_CRITERIA},
}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in KIND_CONFIG:
        print("Usage: python -m router.tools.export_training_data model|skill", file=sys.stderr)
        sys.exit(1)

    cfg = KIND_CONFIG[sys.argv[1]]
    entries = [r for r in labeled_log.read_all() if r.get("kind") == cfg["kind"]]

    if not entries:
        print(f"No labeled entries for kind={cfg['kind']!r} yet. "
              f"Run label_review.py first.", file=sys.stderr)
        sys.exit(1)

    count = 0
    for entry in entries:
        gold = entry.get(cfg["gold_field"])
        if not gold:
            continue
        case = {
            "state": {"input": entry["input_text"]},
            "questions": {
                "choice": {
                    "type": "choice",
                    "instructions": "Pick the single best-fitting option.",
                    "criteria": cfg["criteria"],
                }
            },
            "gold": {"choice": gold},
        }
        print(json.dumps(case))
        count += 1

    print(f"Exported {count} cases for kind={cfg['kind']!r}.", file=sys.stderr)


if __name__ == "__main__":
    main()
