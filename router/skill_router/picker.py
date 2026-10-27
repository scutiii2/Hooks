"""Ask the active classifier (Jev or Laya) which skill should handle a
request. The classifier only ever names a skill (or "none") — it never
runs or writes anything.
"""
from ..core import provider as _provider
from ..core import config as _config
from .catalog import SKILLS


class SkillPicker:
    """Batches the skill catalog if needed, runs a final round among
    batch winners, and applies the confidence threshold.

    Batching has a real cost: a correct skill can lose to a
    locally-stronger competitor within its own batch and never reach the
    final round (verified against this catalog: "loop" lost its batch to
    "schedule" before ever facing "caveman:verify-and-stop"). Skipping
    batching entirely removes that bug but made Laya noisier with 75
    simultaneous options, producing a *confident* wrong pick instead of a
    low-confidence one — worse, since a low-confidence miss safely falls
    back. Default batch size is tuned for that trade-off; adjust
    `skill_picker_batch_size` in router_config.json if you find a better
    number for your catalog.

    batch_size=None and threshold=None (defaults) resolve from
    router_config.json / .env at call time, so they track live config
    changes. Pass explicit values to override.
    """

    def __init__(self, skills=None, batch_size=None, threshold=None):
        self.skills = skills if skills is not None else SKILLS
        self.batch_size = batch_size
        self.threshold = threshold

    def _resolved_batch_size(self) -> int:
        return self.batch_size if self.batch_size is not None \
            else _config.get_skill_picker_batch_size()

    def _batches(self, batch_size):
        return [self.skills[i:i + batch_size]
                for i in range(0, len(self.skills), batch_size)]

    def pick(self, request: str, timeout: float = 5.0) -> dict:
        """Returns {"skill", "confidence", "provider"}.

        Raises provider.ProviderError on failure (caller should fall back
        to normal skill matching, never block on this).
        """
        batch_size = self._resolved_batch_size()

        if len(self.skills) <= batch_size:
            return _provider.pick_skill(request, self.skills, timeout=timeout)

        winners = []
        for batch in self._batches(batch_size):
            result = _provider.pick_skill(request, batch, timeout=timeout)
            if result["skill"] != "none":
                desc = next((d for n, d in batch if n == result["skill"]), "")
                winners.append((result["skill"], desc))

        if not winners:
            return {"skill": "none", "confidence": 0,
                     "provider": _provider._provider_name()}

        final = _provider.pick_skill(request, winners, timeout=timeout)
        return final

    def choose(self, request: str, timeout: float = 5.0) -> dict:
        """pick() + threshold logic.

        Returns {"decision": "use"|"fallback", "skill": str|None,
                 "confidence": int, "provider": str|None,
                 "error": str|None}.
        """
        try:
            result = self.pick(request, timeout=timeout)
        except _provider.ProviderError as e:
            return {"decision": "fallback", "skill": None, "confidence": 0,
                    "provider": None, "error": str(e)}

        threshold = self.threshold if self.threshold is not None else _provider.get_threshold(result["provider"])
        decision = "use" if (result["skill"] != "none"
                              and result["confidence"] >= threshold) else "fallback"
        return {"decision": decision, "skill": result["skill"],
                "confidence": result["confidence"],
                "provider": result["provider"], "error": None}


# Module-level default instance — same call sites as before (skill_picker.choose(...)).
_default_picker = SkillPicker()
pick_skill = _default_picker.pick
choose = _default_picker.choose
