"""PostToolUse hook: log only the invoked skill or subagent, never its prompt."""
import json
import sys


def main():
    try:
        payload = json.load(sys.stdin)
        tool = payload.get("tool_name")
        field = {"Skill": "skill", "Agent": "subagent_type", "Task": "subagent_type"}.get(tool)
        if field is None:
            return
        target = payload.get("tool_input", {}).get(field)
        if not isinstance(target, str) or not target.strip():
            return
        from ..core.training_log import followed_log

        followed_log.append({"session_id": payload.get("session_id"), "tool": tool, "target": target})
    except Exception:
        pass  # A hook failure must never interrupt Claude.


if __name__ == "__main__":
    main()
