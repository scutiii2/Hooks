#!/usr/bin/env node
// SessionStart hook: injects the global coding rules (coding-rules.md) into
// Claude's context. SessionStart also fires after /clear and compaction, so
// the rules survive context resets.
const fs = require('fs');
const path = require('path');
const { logRun } = require('../../core/js/runlog');

const started = Date.now();

const rulesPath = path.join(__dirname, 'coding-rules.md');

let rules;
try {
  rules = fs.readFileSync(rulesPath, 'utf8').trim();
} catch (err) {
  process.stderr.write(`coding-rules-inject: cannot read ${rulesPath}: ${err.message}\n`);
  process.exit(0);
}

let input = {};
try {
  input = JSON.parse(fs.readFileSync(0, 'utf8'));
} catch {
  // no stdin (hand run): log without the session
}
// source: startup, resume, clear or compact, to see how often the rules are injected again
logRun('coding_rules', { event: 'SessionStart', session_id: input.session_id, source: input.source, outcome: 'injected', chars: rules.length }, started);
process.stdout.write(JSON.stringify({
  hookSpecificOutput: {
    hookEventName: 'SessionStart',
    additionalContext: `GLOBAL CODING RULES (user-defined, apply to all code you write):\n\n${rules}`,
  },
}));
