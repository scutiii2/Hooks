"""Run 10 real requests through the skill picker, flag misses vs expected."""
from src.skill_router import picker as skill_picker
from src.core import provider

# (request, expected skill or None if no skill should fire)
SAMPLES = [
    ("review the diff on my current branch for bugs", "code-review"),
    ("write a commit message for these staged changes", "caveman:caveman-commit"),
    ("I keep hitting the same permission prompt for npm test, can you fix that", "fewer-permission-prompts"),
    ("check every 10 minutes if the deploy finished", "loop"),
    ("make a chart of Q3 revenue by region", "dataviz"),
    ("set up a CLAUDE.md for this new repo", "init"),
    ("resolve the merge conflicts in this rebase", "mattpocock-skills:resolving-merge-conflicts"),
    ("write tests first then implement the retry logic", "superpowers:test-driven-development"),
    ("what's the weather like today", "none"),
    ("summarize this PDF for me", "anthropic-skills:pdf"),
]


def main():
    rows = []
    misses = []
    for request, expected in SAMPLES:
        try:
            result = skill_picker.pick_skill(request, timeout=10.0)
            picked = result["skill"]
            conf = result["confidence"]
        except provider.ProviderError as e:
            picked = "ERROR"
            conf = str(e)

        is_miss = picked != expected
        rows.append((request, expected, picked, conf, "MISS" if is_miss else "ok"))
        if is_miss:
            misses.append((request, expected, picked))

    widths = [45, 30, 30, 10, 5]
    header = ("request", "expected", "jev picked", "conf", "flag")
    print(" | ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        trimmed = list(row)
        if len(trimmed[0]) > widths[0]:
            trimmed[0] = trimmed[0][:widths[0] - 2] + ".."
        print(" | ".join(str(c).ljust(w) for c, w in zip(trimmed, widths)))

    if misses:
        print("\nMisses — suggest clearer one-line descriptions:")
        for request, expected, picked in misses:
            print(f"  - Expected {expected!r}, got {picked!r} for: {request!r}")
            print(f"    Fix: sharpen the one-line purpose for {expected!r} so it "
                  f"names the trigger words in this request more directly.")


if __name__ == "__main__":
    main()
