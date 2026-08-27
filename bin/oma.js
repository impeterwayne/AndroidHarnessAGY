#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');

const scriptPath = path.join(__dirname, '..', 'oma.py');
const args = [scriptPath, ...process.argv.slice(2)];

function run(cmd, onFail) {
  const child = spawn(cmd, args, { stdio: 'inherit', shell: process.platform === 'win32' });
  child.on('error', (err) => {
    if (err.code === 'ENOENT') {
      onFail();
    } else {
      console.error(err);
      process.exit(1);
    }
  });
  child.on('exit', (code) => {
    process.exit(code ?? 0);
  });
}

const primary = process.platform === 'win32' ? 'python' : 'python3';
const secondary = process.platform === 'win32' ? 'py' : 'python';

run(primary, () => {
  run(secondary, () => {
    console.error('Error: Python 3 was not found. Please ensure Python is installed and added to your PATH.');
    process.exit(1);
  });
});
