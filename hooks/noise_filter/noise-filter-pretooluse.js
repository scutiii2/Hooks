#!/usr/bin/env node
'use strict';

// PreToolUse hook (matcher: Bash). If the command about to run is the noisy
// kind (installs, builds, test runs, anything with a progress bar), rewrite
// it so its combined output is piped through noise-filter.js before Claude
// ever sees it. Anything else is left completely alone.

const path = require('path');
const { logRun } = require('../../core/js/runlog');

const started = Date.now();
const log = (outcome, extra) => logRun('noise_filter', { event: 'PreToolUse', matcher: 'Bash', outcome, ...extra }, started);

const NOISY_PATTERNS = [
  /\b(npm|yarn|pnpm|npx)\s+(install|ci\b|add|update|upgrade|dedupe|run\s+\S+|test|build)\b/i,
  /\bpip3?\s+install\b/i,
  /\bpoetry\s+(install|update|build)\b/i,
  /\bpytest\b/i,
  /\b(jest|vitest|mocha)\b/i,
  /\bcargo\s+(build|test|install|update)\b/i,
  /\bgo\s+(build|test|install|get|vet|mod\s+tidy)\b/i,
  /\b(mvn|mvnw)\b.*\b(install|test|package|compile)\b/i,
  /\b(gradle|gradlew)\b/i,
  /\bmake\b/i,
  /\bcmake\b--build\b/i,
  /\bdocker\s+(build|pull|push|compose)\b/i,
  /\bapt(-get)?\s+(install|upgrade|update)\b/i,
  /\bbrew\s+(install|upgrade|update)\b/i,
  /\bbundle\s+install\b/i,
  /\bcomposer\s+(install|update)\b/i,
  /\bdotnet\s+(build|restore|test|publish)\b/i,
  /\bwebpack\b/i,
  /\bvite\s+build\b/i,
  /\btox\b/i,
  /\bterraform\s+(plan|apply|init)\b/i,
];

function isNoisy(command) {
  return NOISY_PATTERNS.some((re) => re.test(command));
}

const chunks = [];
process.stdin.on('data', (d) => chunks.push(d));
process.stdin.on('end', () => {
  let input;
  try {
    input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    log('skipped', { reason: 'bad stdin' });
    process.exit(0);
  }

  const toolInput = input.tool_input || {};
  const command = toolInput.command || '';

  if (input.tool_name !== 'Bash' || !command || !isNoisy(command)) {
    log('skipped', { reason: 'not noisy' });
    process.exit(0);
  }

  const filterPath = path
    .join(__dirname, 'noise-filter.js')
    .replace(/\\/g, '/');

  // Capture the real exit code around the pipe (a bare pipeline would report
  // node's exit code instead of the command's).
  const wrapped =
    '_ec="$(mktemp)"; { ' +
    command +
    '; echo $? > "$_ec"; } 2>&1 | node "' +
    filterPath +
    '"; _rc="$(cat "$_ec")"; rm -f "$_ec"; exit "$_rc"';

  log('wrapped');
  const result = {
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      updatedInput: Object.assign({}, toolInput, { command: wrapped }),
    },
  };
  process.stdout.write(JSON.stringify(result));
});
