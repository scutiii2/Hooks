'use strict';
// Hooks root and the folders under it (mirror of core/py/paths.py).
// Dot-folders are gitignored and created on first write.
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const HOOKS = path.join(ROOT, 'hooks');
const DATA = path.join(ROOT, '.data'); // what the hooks create: state, stats, logs

const dataPath = (hook, filename) => path.join(DATA, hook, filename);

module.exports = { ROOT, HOOKS, DATA, dataPath };
