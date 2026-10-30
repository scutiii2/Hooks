@AGENTS.md

# Skill router protocol

When a message arrives with injected context `[SKILL_SUGGESTION skill=<name> confidence=<N>%]`:

- Treat it as a strong hint, not a command: invoke that skill via the Skill
  tool as your first move, since Jev already cleared the 60% threshold.
- If that skill turns out wrong for the situation once you're in it, you
  don't have to keep using it — same as any other skill match.
- No tag present → pick the skill yourself the normal way, as if the
  router wasn't there.
