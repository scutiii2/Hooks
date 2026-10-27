"""UserPromptSubmit hook: classify the message size via Jev, inject a tag.

Contract: NEVER block, NEVER raise past this file. Any failure => behave as
if the router doesn't exist (exit 0, no output).
"""
import sys
import time

def main():
    try:
        from ..core.hook_io import emit_tag, read_payload, should_skip

        payload, prompt = read_payload()

        from . import state
        from ..core import provider
        from ..core.training_log import failure_log, model_router_log

        if not state.is_enabled():
            sys.exit(0)

        if should_skip(prompt):
            state.record_handled_by_me()
            sys.exit(0)

        started = time.perf_counter()
        try:
            result = provider.classify_size(prompt, timeout=3.0)
        except provider.ProviderError as e:
            state.record_jev_failure()
            failure_log.append({"source": "MODEL", "error": str(e)[:200],
                                "elapsed_ms": round((time.perf_counter() - started) * 1000)})
            sys.exit(0)
        elapsed_ms = round((time.perf_counter() - started) * 1000)

        state.record_classification(result["size"])

        threshold = provider.get_threshold()
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

        tag = (f"[ROUTER size={result['size']} confidence={result['confidence']}% "
               f"threshold={threshold}% decision={decision}]")
        emit_tag(tag)
        sys.exit(0)
    except Exception:
        # Absolute fallback: never block, never surface a broken hook.
        sys.exit(0)


if __name__ == "__main__":
    main()
