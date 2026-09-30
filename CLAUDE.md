# Model router protocol

When a message arrives with injected context
`[ROUTER size=<size> confidence=<N>% threshold=<T>% decision=<use|fallback>]`:

- The hook already applied the threshold (it varies by provider — Jev vs
  Laya — so don't re-derive it here). `decision=use` means confidence
  cleared the bar for that provider.
- `decision=use` → dispatch via the Agent tool:
  - `size` is `tiny` or `everyday` → `subagent_type: router-haiku`
  - `size` is `large` or `hardest` → `subagent_type: router-sonnet`
  - Pass the user's original message as the agent prompt, verbatim.
  - Relay the subagent's reply back as your response, unchanged.
- `decision=fallback`, or no tag is present, or the message is a short
  reply that only makes sense inside the current conversation: answer
  normally yourself, no dispatch.
- Never block or delay on this. If dispatch fails for any reason, answer
  normally yourself.

# Skill router protocol

When a message arrives with injected context `[SKILL_SUGGESTION skill=<name> confidence=<N>%]`:

- Treat it as a strong hint, not a command: invoke that skill via the Skill
  tool as your first move, since Jev already cleared the 60% threshold.
- If that skill turns out wrong for the situation once you're in it, you
  don't have to keep using it — same as any other skill match.
- No tag present → pick the skill yourself the normal way, as if the
  router wasn't there.

# Vault

Project note: `Brain/Projects/ClaudeRouters.md` in the Obsidian vault (`../../Brain/` from this folder).
