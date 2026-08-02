import assert from 'node:assert/strict';
import { chmod, mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { atomicWriteToken, launchHeadlessChrome, validateJwt } from '../refresh-token.mjs';

function encode(value) {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

function jwt(payload) {
  return `${encode({ alg: 'none' })}.${encode(payload)}.signature`;
}

test('validateJwt accepts a future numeric expiry', () => {
  const value = jwt({ exp: 2000 });
  assert.deepEqual(validateJwt(value, 1000), { token: value, exp: 2000 });
});

test('validateJwt rejects malformed and expired tokens', () => {
  assert.throws(() => validateJwt('not-a-jwt', 1000), /invalid length|three-part JWT/);
  assert.throws(() => validateJwt(`${encode({ alg: 'none' })}.${'x'.repeat(40)}.signature`, 1000), /invalid JWT payload/);
  assert.throws(() => validateJwt(jwt({}), 1000), /numeric expiry/);
  assert.throws(() => validateJwt(jwt({ exp: '2000' }), 1000), /numeric expiry/);
  assert.throws(() => validateJwt(jwt({ exp: 999 }), 1000), /expired/);
});

test('atomicWriteToken replaces the token completely at mode 0600', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'credit-claim-token-test.'));
  const tokenPath = join(directory, 'token');
  const value = jwt({ exp: Math.floor(Date.now() / 1000) + 3600 });
  try {
    await writeFile(tokenPath, 'old-token\n', { mode: 0o600 });
    await atomicWriteToken(tokenPath, value);
    assert.equal(await readFile(tokenPath, 'utf8'), `${value}\n`);
    assert.equal((await stat(tokenPath)).mode & 0o777, 0o600);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test('launchHeadlessChrome cleans up a child that never exposes DevTools', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'credit-claim-chrome-test.'));
  const fakeChrome = join(directory, 'fake-chrome');
  const pidFile = join(directory, 'pid');
  const profile = join(directory, 'profile');
  try {
    await writeFile(
      fakeChrome,
      '#!/bin/bash\nprintf \'%s\\n\' "$$" > "$CREDIT_CLAIM_TEST_PID_FILE"\nexec sleep 30\n',
    );
    await chmod(fakeChrome, 0o755);
    process.env.CREDIT_CLAIM_TEST_PID_FILE = pidFile;
    await assert.rejects(
      launchHeadlessChrome(fakeChrome, profile, Date.now() + 750),
      /Timed out starting headless Chrome/,
    );
    const pid = Number.parseInt((await readFile(pidFile, 'utf8')).trim(), 10);
    assert.throws(
      () => process.kill(pid, 0),
      (error) => error.code === 'ESRCH',
      'spawned browser process should be gone after startup failure',
    );
  } finally {
    delete process.env.CREDIT_CLAIM_TEST_PID_FILE;
    await rm(directory, { recursive: true, force: true });
  }
});
