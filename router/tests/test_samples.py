"""Run 10 sample messages through Jev directly and print a results table."""
from ..core.classifiers import JevClassifier, ClassifierError

SAMPLES = [
    ("tiny?", "What's the capital of France?"),
    ("tiny?", "Rename variable `usr` to `user` in this file."),
    ("everyday?", "Write a short email to my landlord asking to fix the sink."),
    ("everyday?", "Draft a 3-paragraph blog post about morning routines."),
    ("large?", "Research competitor pricing for 5 SaaS tools and write a full report."),
    ("large?", "Build a multi-step ETL pipeline that ingests CSVs and loads them into Postgres."),
    ("hardest?", "Should we raise prices 20% given churn risk? Get this wrong and we lose the quarter."),
    ("hardest?", "Design our company's fundraising strategy for the next 18 months."),
    ("short reply", "yes do that but make it shorter"),
    ("short reply", "ok go ahead"),
]

MODEL_MAP = {
    "tiny": "haiku",
    "everyday": "haiku",
    "large": "sonnet",
    "hardest": "sonnet",
}


def main():
    classifier = JevClassifier()
    rows = []
    for expected_hint, message in SAMPLES:
        try:
            result = classifier.classify_size(message, timeout=10.0)
            size = result["size"]
            conf = result["confidence"]
            model = MODEL_MAP.get(size, "?")
            rows.append((expected_hint, message, size, f"{conf}%", model))
        except ClassifierError as e:
            rows.append((expected_hint, message, "ERROR", str(e), "-"))

    widths = [14, 55, 10, 12, 8]
    header = ("hint", "message", "size", "confidence", "model")
    print(" | ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        trimmed = list(row)
        trimmed[1] = trimmed[1][:53] + ".." if len(trimmed[1]) > 55 else trimmed[1]
        print(" | ".join(str(c).ljust(w) for c, w in zip(trimmed, widths)))


if __name__ == "__main__":
    main()
