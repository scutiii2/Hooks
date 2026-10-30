'use strict';
// One line per hook run in .data/<hook>/runs.jsonl: event, working folder, outcome, duration.
// Never throws: a broken log must not block a hook.
const { JsonlLog } = require('./log');
const { dataPath } = require('./paths');

function logRun(hook, record, startedAt) {
  try {
    new JsonlLog(dataPath(hook, 'runs.jsonl')).append({
      hook,
      cwd: process.cwd(),
      ...record,
      duration_ms: Date.now() - startedAt,
    });
  } catch {
    // fail open
  }
}

module.exports = { logRun };
