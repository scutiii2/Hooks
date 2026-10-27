"""Try the skill picker on any request, anytime.

Usage:
    python -m src.skill_router.pick "your request text here"
"""
import sys

from . import picker


def main():
    if len(sys.argv) < 2:
        print('Usage: python -m src.skill_router.pick "your request text"')
        sys.exit(1)

    request = " ".join(sys.argv[1:])
    result = picker.choose(request)

    if result["error"]:
        print(f"Jev failed ({result['error']}) — falling back to normal skill matching.")
        return

    if result["decision"] == "use":
        print(f"Skill: {result['skill']}  (confidence: {result['confidence']}%)")
    else:
        skill_note = f" (leaning {result['skill']})" if result["skill"] != "none" else ""
        print(f"Not confident enough{skill_note} — confidence: {result['confidence']}%. "
              f"Falling back to normal skill matching.")


if __name__ == "__main__":
    main()
