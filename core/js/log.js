'use strict';
// Append-only JSONL log (mirror of core/py/training_log.py): same record shape
// ({"timestamp": <epoch seconds>, ...record}) and one `<name>.1` backup past 10 MB.
const fs = require('fs');
const path = require('path');

const MAX_BYTES = 10 * 1024 * 1024;

class JsonlLog {
  constructor(file, maxBytes = MAX_BYTES) {
    this.path = file;
    this.maxBytes = maxBytes;
  }

  append(record) {
    fs.mkdirSync(path.dirname(this.path), { recursive: true });
    try {
      if (fs.statSync(this.path).size > this.maxBytes) fs.renameSync(this.path, this.path + '.1');
    } catch {
      // missing file, or another hook holds it open (Windows): try again on the next append
    }
    fs.appendFileSync(this.path, JSON.stringify({ timestamp: Date.now() / 1000, ...record }) + '\n');
  }
}

module.exports = { JsonlLog };
