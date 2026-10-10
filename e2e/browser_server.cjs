const { spawn } = require('child_process');
function startApi(command, args, options = {}, timeout = 10000) {
  const child = spawn(command, args, { ...options, stdio: ['ignore', 'pipe', 'pipe'] });
  const ready = new Promise((resolve, reject) => {
    let buffer = '', stderr = '';
    const fail = error => { clearTimeout(timer); child.kill(); reject(error); };
    const timer = setTimeout(() => fail(new Error('Test API startup timed out')), timeout);
    child.once('error', fail);
    child.once('exit', code => fail(new Error(`Test API exited before readiness (${code}): ${stderr.slice(-1000)}`)));
    child.stderr.on('data', data => { stderr += data; });
    child.stdout.on('data', data => {
      buffer += data;
      if (!buffer.includes('\n')) return;
      const port = Number(buffer.split('\n')[0].trim());
      if (!Number.isInteger(port) || port <= 0 || port > 65535) return fail(new Error('Invalid test API port'));
      clearTimeout(timer); resolve(port);
    });
  });
  return { child, ready };
}
module.exports = { startApi };
