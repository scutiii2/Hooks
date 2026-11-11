#!/usr/bin/env node
'use strict';

// Reads a command's combined stdout+stderr from stdin and prints a trimmed version:
// error lines with 2 lines of context, warning lines, and the last TAIL_LINES lines
// (where installers, builders and test runners print their summary).
// Short output passes through untouched, and so does a failed run under FAILED_KEEP_LINES.
// argv[2] = file holding the command's exit code, argv[3] = label for the log.

const fs = require('fs');
const { logRun } = require('../../core/js/runlog');

const started = Date.now();
const TAIL_LINES = 25;
const SHORT_OUTPUT_THRESHOLD = 80;
const FAILED_KEEP_LINES = 200;
const CONTEXT = 2;

// Lines that explain a failure: keep them with their neighbours.
const ERROR_PATTERNS = [
  /\berror\b/i,
  /\bexception\b/i,
  /\bfail(ed|ure|s)?\b/i,
  /\btraceback\b/i,
  /\bfatal\b/i,
  /\bnot found\b/i,
  /\bcannot find\b/i,
  /\bpermission denied\b/i,
  /\bENOENT\b/,
  /\bEACCES\b/,
  /^\s*npm ERR!/,
  /^\s*E:\s/,
  /[✗✖❌]/,
  /\bunhandled\b/i,
];
// Warnings repeat hundreds of times in an install: keep the line, not its neighbours.
const WARNING_PATTERNS = [/\bwarn(ing)?\b/i, /\bdeprecated\b/i];

const matches = (patterns, line) => patterns.some((re) => re.test(line));

function exitCode() {
  try {
    const n = parseInt(fs.readFileSync(process.argv[2], 'utf8'), 10);
    return Number.isNaN(n) ? null : n;
  } catch {
    return null; // run by hand, or the file is gone: treat as unknown
  }
}

// Records what the filter saved, so the log can show whether wrapping is worth it.
// command_ms = how long the wrapped command ran; filter_ms = time spent trimming.
function log(raw, out, linesIn, linesKept, code, endedAt) {
  logRun('noise_filter', {
    event: 'Filter', outcome: linesKept < linesIn ? 'trimmed' : 'passthrough', command: process.argv[3] || null,
    exit_code: code, bytes_in: Buffer.byteLength(raw), bytes_out: Buffer.byteLength(out),
    lines_in: linesIn, lines_kept: linesKept, command_ms: endedAt - started, filter_ms: Date.now() - endedAt,
  }, started);
}

function trim(lines) {
  const keep = new Set();
  lines.forEach((line, i) => {
    if (matches(WARNING_PATTERNS, line)) keep.add(i);
    if (matches(ERROR_PATTERNS, line)) {
      for (let j = Math.max(0, i - CONTEXT); j <= Math.min(lines.length - 1, i + CONTEXT); j++) keep.add(j);
    }
  });
  for (let i = Math.max(0, lines.length - TAIL_LINES); i < lines.length; i++) keep.add(i);

  const kept = Array.from(keep).sort((a, b) => a - b);
  const out = [];
  let prev = -1;
  for (const i of kept) {
    if (prev !== -1 && i > prev + 1) out.push(`… ${i - prev - 1} line(s) omitted …`);
    out.push(lines[i]);
    prev = i;
  }
  out.push('', `[noise-filter] kept ${kept.length}/${lines.length} lines`);
  return { text: out.join('\n') + '\n', kept: kept.length };
}

const chunks = [];
process.stdin.on('data', (d) => chunks.push(d));
process.stdin.on('end', () => {
  const endedAt = Date.now();
  const raw = Buffer.concat(chunks).toString('utf8');
  const code = exitCode();

  // A `\r` not followed by `\n` means "redraw this line" (progress bars).
  // Collapse each redraw run down to nothing — only the final `\n`-terminated
  // state of a line survives.
  const collapsed = raw.replace(/[^\n]*\r(?!\n)/g, '');
  const lines = collapsed.split(/\r\n|\n/);
  if (lines.length && lines[lines.length - 1] === '') lines.pop();

  const total = lines.length;
  const failed = code !== null && code !== 0;
  if (total <= SHORT_OUTPUT_THRESHOLD || (failed && total <= FAILED_KEEP_LINES)) {
    const out = lines.join('\n') + (lines.length ? '\n' : '');
    process.stdout.write(out);
    log(raw, out, total, total, code, endedAt);
    return;
  }

  const { text, kept } = trim(lines);
  process.stdout.write(text);
  log(raw, text, total, kept, code, endedAt);
});
