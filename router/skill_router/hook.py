"""UserPromptSubmit hook: ask Jev which skill fits, inject a suggestion tag.

Contract: NEVER block, NEVER raise past this file, NEVER run/write anything.
Jev only names a skill. This hook only suggests via additionalContext — it
does not and cannot force-load a skill. Any failure => silent no-op.
"""
import json
import sys


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        prompt = payload.get("prompt", "")
        if isinstance(prompt, dict):
            prompt = prompt.get("type", "") or ""

        from . import state
        from . import picker
        from ..core.training_log import skill_router_log

        if not state.is_enabled():
            sys.exit(0)

        if not prompt.strip():
            sys.exit(0)

        result = picker.choose(prompt, timeout=3.0)

        if result["error"]:
            state.record_failure()
            sys.exit(0)

        state.record(result["decision"], result["cost_usd"])

        skill_router_log.append({
            "input_text": prompt,
            "predicted_skill": result["skill"],
            "confidence": result["confidence"],
            "decision": result["decision"],
            "provider": result["provider"],
        })

        if result["decision"] != "use":
            sys.exit(0)

        tag = f"[SKILL_SUGGESTION skill={result['skill']} confidence={result['confidence']}%]"
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": tag,
            }
        }))
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
