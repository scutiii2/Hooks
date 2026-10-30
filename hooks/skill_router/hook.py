"""UserPromptSubmit hook: ask Jev which skill fits, inject a suggestion tag.

Contract: NEVER block, NEVER raise past this file, NEVER run/write anything.
Jev only names a skill. This hook only suggests via additionalContext — it
does not and cannot force-load a skill. Any failure => silent no-op.
"""
import sys
import time


def _emit(tags: list[str]):
    from core.py.hook_io import emit_tag

    if tags:
        emit_tag(*tags)


def run() -> dict:
    """Do the work; return the run-log record (outcome plus what decided it)."""
    from core.py.env_load import load_env
    load_env("skill_router")
    from core.py.hook_io import read_payload, should_skip

    payload, prompt = read_payload()

    from . import builtins, picker, state
    from core.py.training_log import failure_log, skill_router_log

    if not state.is_enabled():
        return {"outcome": "disabled"}

    notice = builtins.due_notice()
    tags = [notice] if notice else []
    extra = {"builtin_check_due": True} if notice else {}

    if should_skip(prompt, payload.get("cwd") or ""):
        state.record_skipped()
        _emit(tags)
        return {"outcome": "skipped", **extra}

    started = time.perf_counter()
    result = picker.choose(prompt, timeout=3.0)
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    if result["error"]:
        state.record_failure()
        failure_log.append({"source": "SKILL", "error": result["error"][:200], "elapsed_ms": elapsed_ms})
        _emit(tags)
        return {"outcome": "failed", **extra}

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
    _emit(tags)
    return {"outcome": result["decision"], "skill": result["skill"], "confidence": result["confidence"], **extra}


def main():
    started = time.time()
    try:
        record = run()
    except Exception as e:
        record = {"outcome": "error", "error": f"{type(e).__name__}: {e}"[:200]}
    try:
        from core.py.runlog import log_run
        log_run("skill_router", {"event": "UserPromptSubmit", **record}, started)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
