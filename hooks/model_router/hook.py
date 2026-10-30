"""UserPromptSubmit hook: classify the message size via Jev, inject a tag.

Contract: NEVER block, NEVER raise past this file. Any failure => behave as
if the router doesn't exist (exit 0, no output).
"""
import sys
import time


def run() -> dict:
    """Do the work; return the run-log record (outcome plus what decided it)."""
    from core.py.env_load import load_env
    load_env("model_router")
    from core.py.hook_io import emit_tag, read_payload, should_skip

    payload, prompt = read_payload()

    from . import state
    from core.py import provider
    from core.py.classifiers import ClassifierError
    from core.py.training_log import failure_log, model_router_log

    if not state.is_enabled():
        return {"outcome": "disabled"}

    if should_skip(prompt, payload.get("cwd") or ""):
        state.record_handled_by_me()
        return {"outcome": "skipped"}

    started = time.perf_counter()
    try:
        result = provider.classify_size(prompt, timeout=3.0)
    except ClassifierError as e:
        state.record_jev_failure()
        failure_log.append({"source": "MODEL", "error": str(e)[:200],
                            "elapsed_ms": round((time.perf_counter() - started) * 1000)})
        return {"outcome": "failed"}
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    state.record_classification(result["size"])

    threshold = provider.get_threshold("model_router")
    decision = "use" if result["confidence"] >= threshold else "fallback"

    model_router_log.append({
        "session_id": payload.get("session_id"),
        "input_text": prompt,
        "predicted_size": result["size"],
        "confidence": result["confidence"],
        "threshold": threshold,
        "decision": decision,
        "provider": result["provider"],
        "elapsed_ms": elapsed_ms,
    })

    emit_tag(f"[ROUTER size={result['size']} confidence={result['confidence']}% "
             f"threshold={threshold}% decision={decision}]")
    return {"outcome": decision, "size": result["size"], "confidence": result["confidence"]}


def main():
    started = time.time()
    try:
        record = run()
    except Exception as e:
        # Absolute fallback: never block, never surface a broken hook.
        record = {"outcome": "error", "error": f"{type(e).__name__}: {e}"[:200]}
    try:
        from core.py.runlog import log_run
        log_run("model_router", {"event": "UserPromptSubmit", **record}, started)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
