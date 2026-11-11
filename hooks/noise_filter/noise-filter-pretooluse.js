#!/usr/bin/env node
'use strict';

// PreToolUse hook (matcher: Bash). If the command about to run usually prints a lot
// (installs, big builds, full test runs), rewrite it so its combined output goes through
// noise-filter.js before Claude sees it. Anything else is left completely alone.

const path = require('path');
const { logRun } = require('../../core/js/runlog');

const started = Date.now();
let sessionId;
const log = (outcome, extra) => logRun('noise_filter', { event: 'PreToolUse', matcher: 'Bash', session_id: sessionId, outcome, ...extra }, started);

// Commands that print hundreds of lines even when they succeed.
const NOISY_PATTERNS = [
  /\b(npm|yarn|pnpm)\s+(install|ci|add|update|upgrade|dedupe)\b/i,
  /\bpip3?\s+install\b/i,
  /\bpoetry\s+(install|update)\b/i,
  /\bcargo\s+(build|install|update)\b/i,
  /\b(mvn|mvnw)\b.*\b(install|package|compile)\b/i,
  /\b(gradle|gradlew)\b/i,
  /\bcmake\s+--build\b/i,
  /\bdocker\s+(build|pull|push)\b/i,
  /\bapt(-get)?\s+(install|upgrade|update)\b/i,
  /\bbrew\s+(install|upgrade|update)\b/i,
  /\bbundle\s+install\b/i,
  /\bcomposer\s+(install|update)\b/i,
  /\bdotnet\s+(build|restore|publish)\b/i,
  /\bterraform\s+(plan|apply|init)\b/i,
];

// Test runners: noisy only for a full run. At the start of a command, so `cat jest.config.js` is not a match.
const RUNNER = '(^|[;&|(]\\s*|\\s-m\\s+|\\bnpx\\s+)';
const TEST_PATTERNS = [
  new RegExp(RUNNER + '(pytest|jest|vitest|mocha)\\b', 'i'),
  /\b(npm|yarn|pnpm)\s+test\b/i,
  /\b(go|cargo|dotnet)\s+test\b/i,
  /\b(mvn|mvnw)\b.*\btest\b/i,
];
// A quiet flag or a single file, test or name filter means a short run.
const TARGETED = /(\s-q+\b|--quiet|::|\.py\b|\.(test|spec)\.|\s-k\s|\s-t\s|--testNamePattern|\s-run\s)/;
// Output already cut or sent to a file.
const ALREADY_SHORT = /\|\s*(head|tail)\b|(?<![0-9&])>>?\s*(?!&)\S/;

function isNoisy(raw) {
  // shortcut: quoted text is ignored, so a commit message that says "pip install" is no match
  // (and `bash -c "pip install x"` is not wrapped); upgrade when that matters.
  const command = raw.replace(/"[^"]*"|'[^']*'/g, '""');
  if (ALREADY_SHORT.test(command)) return false;
  if (NOISY_PATTERNS.some((re) => re.test(command))) return true;
  return !TARGETED.test(command) && TEST_PATTERNS.some((re) => re.test(command));
}

// Program and subcommand only ("pip install"), so the log never holds arguments such as tokens.
const label = (command) => command.trim().split(/\s+/).slice(0, 2).join(' ').replace(/[^\w .:-]/g, '').slice(0, 40);

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

  sessionId = input.session_id;
  const toolInput = input.tool_input || {};
  const command = toolInput.command || '';

  if (input.tool_name !== 'Bash' || !command || !isNoisy(command)) {
    log('skipped', { reason: 'not noisy' });
    process.exit(0);
  }

  const filterPath = path
    .join(__dirname, 'noise-filter.js')
    .replace(/\\/g, '/');

  // Save the real exit code in a temp file (a bare pipeline would report node's exit code).
  // The filter reads the same file at end of input, so it can keep a failed run whole.
  const wrapped =
    '_ec="$(mktemp)"; { ' +
    command +
    '; echo $? > "$_ec"; } 2>&1 | node "' +
    filterPath +
    '" "$_ec" "' + label(command) + '"; _rc="$(cat "$_ec")"; rm -f "$_ec"; exit "$_rc"';

  log('wrapped', { command: label(command) });
  const result = {
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      updatedInput: Object.assign({}, toolInput, { command: wrapped }),
    },
  };
  process.stdout.write(JSON.stringify(result));
});
