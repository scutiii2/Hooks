"""Walk unreviewed real classifications and confirm/correct the gold label.

Usage:
    python -m core.py.tools.label_review skill      # review skill_router_log.jsonl

For each entry: press Enter to accept the predicted label as correct, or
type the correct label and press Enter to record a correction. Confirmed
entries move to .memory/core/labeled.jsonl — the actual training set.
Ctrl+C at any point stops early; already-reviewed entries are remembered
(by timestamp) so re-running only shows new ones.
"""
import sys

from ..training_log import skill_router_log, labeled_log

KIND_CONFIG = {
    "skill": {
        "log": skill_router_log,
        "kind": "skill_router",
        "predicted_field": "predicted_skill",
        "gold_field": "skill",
        "prompt_label": "skill name (or 'none')",
    },
}


def _already_reviewed_timestamps(kind: str) -> set:
    return {r["source_timestamp"] for r in labeled_log.read_all()
            if r.get("kind") == kind and "source_timestamp" in r}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in KIND_CONFIG:
        print("Usage: python -m core.py.tools.label_review skill")
        sys.exit(1)

    cfg = KIND_CONFIG[sys.argv[1]]
    entries = cfg["log"].read_all()
    reviewed = _already_reviewed_timestamps(cfg["kind"])
    pending = [e for e in entries if e["timestamp"] not in reviewed]

    if not pending:
        print("Nothing new to review.")
        return

    print(f"{len(pending)} entries to review. Enter = accept prediction, "
          f"or type the correct {cfg['prompt_label']}. Ctrl+C to stop.\n")

    reviewed_count = 0
    try:
        for entry in pending:
            predicted = entry.get(cfg["predicted_field"])
            print(f"Input: {entry['input_text']}")
            print(f"Predicted: {predicted} (confidence {entry.get('confidence')}%)")
            correction = input(f"Correct {cfg['prompt_label']} [{predicted}]: ").strip()
            gold = correction if correction else predicted

            labeled_log.append({
                "kind": cfg["kind"],
                "source_timestamp": entry["timestamp"],
                "input_text": entry["input_text"],
                cfg["gold_field"]: gold,
                "predicted": predicted,
                "was_correct": gold == predicted,
                "confidence": entry.get("confidence"),
                "provider": entry.get("provider"),
            })
            reviewed_count += 1
            print()
    except KeyboardInterrupt:
        print("\nStopped early.")

    print(f"Reviewed {reviewed_count} entries. Labeled set: {labeled_log.path}")


if __name__ == "__main__":
    main()
