"""UserPromptSubmit hook: ask Jev which skill fits, inject a suggestion tag.

Contract: NEVER block, NEVER raise past this file, NEVER run/write anything.
Jev only names a skill. This hook only suggests via additionalContext — it
does not and cannot force-load a skill. Any failure => silent no-op.
"""
import sys
import time


def _exit(tags: list[str]):
    from core.py.hook_io import emit_tag

    if tags:
        emit_tag(*tags)
    sys.exit(0)


def main():
    try:
        from core.py.env_load import load_env
        load_env("skill_router")
        from core.py.hook_io import read_payload, should_skip

        payload, prompt = read_payload()

        from . import builtins, picker, state
        from core.py.training_log import failure_log, skill_router_log

        if not state.is_enabled():
            sys.exit(0)

        notice = builtins.due_notice()
        tags = [notice] if notice else []

        if should_skip(prompt, payload.get("cwd") or ""):
            state.record_skipped()
            _exit(tags)

        started = time.perf_counter()
        result = picker.choose(prompt, timeout=3.0)
        elapsed_ms = round((time.perf_counter() - started) * 1000)

        if result["error"]:
            state.record_failure()
            failure_log.append({"source": "SKILL", "error": result["error"][:200], "elapsed_ms": elapsed_ms})
            _exit(tags)

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

        if result["decision"] == "use":
            tags.append(f"[SKILL_SUGGESTION skill={result['skill']} confidence={result['confidence']}%]")
        _exit(tags)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
