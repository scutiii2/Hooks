"""UserPromptSubmit hook: ask Jev which skill fits, inject a suggestion tag.

Contract: NEVER block, NEVER raise past this file, NEVER run/write anything.
Jev only names a skill. This hook only suggests via additionalContext — it
does not and cannot force-load a skill. Any failure => silent no-op.
"""
import json
import sys
import time


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        prompt = payload.get("prompt", "")
        if isinstance(prompt, dict):
            prompt = prompt.get("type", "") or ""

        from . import state
        from . import picker
        from ..core.training_log import failure_log, skill_router_log

        if not state.is_enabled():
            sys.exit(0)

        from ..core.privacy import is_private
        from ..model_router.hook import is_short_contextual_reply

        if not prompt.strip() or is_short_contextual_reply(prompt) or is_private(prompt):
            sys.exit(0)

        started = time.perf_counter()
        result = picker.choose(prompt, timeout=3.0)
        elapsed_ms = round((time.perf_counter() - started) * 1000)

        if result["error"]:
            state.record_failure()
            failure_log.append({"source": "SKILL", "error": result["error"][:200], "elapsed_ms": elapsed_ms})
            sys.exit(0)

        state.record(result["decision"])

        skill_router_log.append({
            "session_id": payload.get("session_id"),
            "input_text": prompt,
            "predicted_skill": result["skill"],
            "confidence": result["confidence"],
            "decision": result["decision"],
            "provider": result["provider"],
            "elapsed_ms": elapsed_ms,
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
