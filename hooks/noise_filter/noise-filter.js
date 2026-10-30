#!/usr/bin/env node
'use strict';

// Reads a command's combined stdout+stderr from stdin and prints a trimmed
// version: every line that looks like an error/failure, plus the last
// TAIL_LINES lines (where installers/builders/test runners print their final
// summary). Short output passes through untouched.

const TAIL_LINES = 15;
const SHORT_OUTPUT_THRESHOLD = 40;

const IMPORTANT_PATTERNS = [
  /\berror\b/i,
  /\bexception\b/i,
  /\bfail(ed|ure|s)?\b/i,
  /\btraceback\b/i,
  /\bfatal\b/i,
  /\bwarn(ing)?\b/i,
  /\bdeprecated\b/i,
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

function isImportant(line) {
  return IMPORTANT_PATTERNS.some((re) => re.test(line));
}

const chunks = [];
process.stdin.on('data', (d) => chunks.push(d));
process.stdin.on('end', () => {
  const raw = Buffer.concat(chunks).toString('utf8');

  // A `\r` not followed by `\n` means "redraw this line" (progress bars).
  // Collapse each redraw run down to nothing — only the final `\n`-terminated
  // state of a line survives.
  const collapsed = raw.replace(/[^\n]*\r(?!\n)/g, '');
  const lines = collapsed.split(/\r\n|\n/);
  if (lines.length && lines[lines.length - 1] === '') lines.pop();

  const total = lines.length;
  if (total <= SHORT_OUTPUT_THRESHOLD) {
    process.stdout.write(lines.join('\n') + (lines.length ? '\n' : ''));
    return;
  }

  const keep = new Set();
  lines.forEach((line, i) => {
    if (isImportant(line)) keep.add(i);
  });
  const tailStart = Math.max(0, total - TAIL_LINES);
  for (let i = tailStart; i < total; i++) keep.add(i);

  const keptIdx = Array.from(keep).sort((a, b) => a - b);
  const out = [];
  let prev = -1;
  for (const i of keptIdx) {
    if (prev !== -1 && i > prev + 1) {
      out.push(`… ${i - prev - 1} line(s) omitted …`);
    }
    out.push(lines[i]);
    prev = i;
  }
  out.push('', `[noise-filter] kept ${keptIdx.length}/${total} lines`);
  process.stdout.write(out.join('\n') + '\n');
});
