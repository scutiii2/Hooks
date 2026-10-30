"""Convert .memory/core/labeled.jsonl into the {state, questions, gold}
shape used for typed-decision fine-tuning.

Usage:
    python -m core.py.tools.export_training_data skill   > skill_router_train.jsonl

Only "kind" matching entries are exported; each labeled.jsonl row becomes
one training case. Run this once you have enough labeled data to be worth
fine-tuning on (a few hundred cases at least).
"""
import json
import sys

from ..classifiers import choice_question, skill_criteria
from ..training_log import labeled_log
from hooks.skill_router.catalog import SKILLS
from .label_review import KIND_CONFIG

CRITERIA = {"skill": skill_criteria(SKILLS)}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in KIND_CONFIG:
        print("Usage: python -m core.py.tools.export_training_data skill", file=sys.stderr)
        sys.exit(1)

    cfg = KIND_CONFIG[sys.argv[1]]
    criteria = CRITERIA[sys.argv[1]]
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
            "questions": {"choice": choice_question(criteria)},
            "gold": {"choice": gold},
        }
        print(json.dumps(case))
        count += 1

    print(f"Exported {count} cases for kind={cfg['kind']!r}.", file=sys.stderr)


if __name__ == "__main__":
    main()
