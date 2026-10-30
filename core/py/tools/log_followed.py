"""PostToolUse hook: log only the invoked skill, never its arguments."""
import json
import sys


def main():
    try:
        payload = json.load(sys.stdin)
        tool = payload.get("tool_name")
        if tool != "Skill":
            return
        target = payload.get("tool_input", {}).get("skill")
        if not isinstance(target, str) or not target.strip():
            return
        from ..training_log import followed_log

        followed_log.append({"session_id": payload.get("session_id"), "tool": tool, "target": target})
    except Exception:
        pass  # A hook failure must never interrupt Claude.


if __name__ == "__main__":
    main()
