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

logRun('coding_rules', { event: 'SessionStart', outcome: 'injected', chars: rules.length }, started);
process.stdout.write(JSON.stringify({
  hookSpecificOutput: {
    hookEventName: 'SessionStart',
    additionalContext: `GLOBAL CODING RULES (user-defined, apply to all code you write):\n\n${rules}`,
  },
}));
