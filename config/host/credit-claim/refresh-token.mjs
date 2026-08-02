#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import {
  chmod,
  lstat,
  mkdir,
  open,
  readFile,
  rename,
  rm,
} from 'node:fs/promises';
import { homedir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const DEFAULT_CHROME = '/usr/bin/google-chrome-stable';
const DEFAULT_TIMEOUT_MS = 45_000;
const POLL_INTERVAL_MS = 250;

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

function decodeBase64Url(value) {
  const padding = '='.repeat((4 - (value.length % 4)) % 4);
  return Buffer.from(value.replaceAll('-', '+').replaceAll('_', '/') + padding, 'base64');
}

export function validateJwt(token, nowSeconds = Date.now() / 1000) {
  if (typeof token !== 'string' || token.length < 32 || token.length > 4096) {
    throw new Error('TOKEN has an invalid length');
  }

  const parts = token.trim().split('.');
  if (parts.length !== 3 || parts.some((part) => part.length === 0)) {
    throw new Error('TOKEN is not a three-part JWT');
  }

  let payload;
  try {
    payload = JSON.parse(decodeBase64Url(parts[1]).toString('utf8'));
  } catch {
    throw new Error('TOKEN has an invalid JWT payload');
  }

  if (typeof payload.exp !== 'number' || !Number.isFinite(payload.exp)) {
    throw new Error('TOKEN has no numeric expiry');
  }
  if (payload.exp <= nowSeconds) {
    throw new Error('TOKEN is expired');
  }

  return { token: token.trim(), exp: payload.exp };
}

export async function atomicWritePrivateFile(path, contents) {
  const directory = dirname(path);
  const temporaryPath = join(
    directory,
    `.${basename(path)}.${process.pid}.${randomBytes(6).toString('hex')}`,
  );

  await mkdir(directory, { recursive: true, mode: 0o700 });
  let handle;
  try {
    handle = await open(temporaryPath, 'wx', 0o600);
    await handle.writeFile(contents, { encoding: 'utf8' });
    await handle.sync();
    await handle.close();
    handle = undefined;
    await rename(temporaryPath, path);
    await chmod(path, 0o600);
  } catch (error) {
    if (handle) {
      await handle.close().catch(() => {});
    }
    await rm(temporaryPath, { force: true }).catch(() => {});
    throw error;
  }
}

export async function atomicWriteToken(path, token) {
  const validated = validateJwt(token);
  await atomicWritePrivateFile(path, `${validated.token}\n`);
  return validated;
}

class CdpClient {
  constructor(webSocketUrl) {
    this.webSocketUrl = webSocketUrl;
    this.nextId = 1;
    this.pending = new Map();
  }

  async connect() {
    this.socket = new WebSocket(this.webSocketUrl);
    await new Promise((resolvePromise, reject) => {
      const onOpen = () => {
        this.socket.removeEventListener('error', onError);
        resolvePromise();
      };
      const onError = () => {
        this.socket.removeEventListener('open', onOpen);
        reject(new Error('Could not connect to Chrome DevTools'));
      };
      this.socket.addEventListener('open', onOpen, { once: true });
      this.socket.addEventListener('error', onError, { once: true });
    });
    this.socket.addEventListener('message', (event) => this.onMessage(event));
    this.socket.addEventListener('close', () => {
      for (const { reject } of this.pending.values()) {
        reject(new Error('Chrome DevTools connection closed'));
      }
      this.pending.clear();
    });
  }

  onMessage(event) {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    if (!message.id || !this.pending.has(message.id)) {
      return;
    }
    const { resolve: resolvePromise, reject } = this.pending.get(message.id);
    this.pending.delete(message.id);
    if (message.error) {
      reject(new Error(`Chrome DevTools ${message.error.message || 'command failed'}`));
    } else {
      resolvePromise(message.result || {});
    }
  }

  send(method, params = {}, sessionId = undefined) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('Chrome DevTools is not connected'));
    }
    const id = this.nextId++;
    return new Promise((resolvePromise, reject) => {
      this.pending.set(id, { resolve: resolvePromise, reject });
      const message = { id, method, params };
      if (sessionId) {
        message.sessionId = sessionId;
      }
      this.socket.send(JSON.stringify(message));
    });
  }

  close() {
    if (this.socket && this.socket.readyState < WebSocket.CLOSING) {
      this.socket.close();
    }
  }
}

async function readOptional(path) {
  try {
    return (await readFile(path, 'utf8')).trim();
  } catch (error) {
    if (error.code === 'ENOENT') {
      return null;
    }
    throw error;
  }
}

async function devToolsPortFromFile(path) {
  const contents = await readFile(path, 'utf8');
  const [portValue] = contents.split(/\r?\n/);
  const port = Number.parseInt(portValue, 10);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('Chrome DevTools port file is invalid');
  }
  return port;
}

async function devToolsEndpointFromFile(path) {
  const contents = await readFile(path, 'utf8');
  const [portValue, webSocketPath] = contents.split(/\r?\n/);
  const port = Number.parseInt(portValue, 10);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('Chrome DevTools port file is invalid');
  }
  if (!webSocketPath?.startsWith('/devtools/browser/')) {
    throw new Error('Chrome DevTools endpoint file is invalid');
  }
  return {
    port,
    webSocketUrl: `ws://127.0.0.1:${port}${webSocketPath}`,
  };
}

async function getTargets(port) {
  const response = await fetch(`http://127.0.0.1:${port}/json/list`);
  if (!response.ok) {
    throw new Error(`Chrome DevTools target listing returned HTTP ${response.status}`);
  }
  return response.json();
}

function targetOrigin(target) {
  try {
    return new URL(target.url).origin;
  } catch {
    return null;
  }
}

function chooseSourceTarget(targets, apiOrigin) {
  const candidates = targets.filter(
    (target) => target.type === 'page' && targetOrigin(target) === apiOrigin,
  );
  const preferred = candidates.find((target) => /\/(subscribe|subscription|account)(\/|$)/i.test(new URL(target.url).pathname));
  const target = preferred || candidates[0];
  if (!target) {
    throw new Error('Open the authenticated subscription/account page in Chrome before bootstrapping');
  }
  return target;
}

async function evaluateByValue(client, expression) {
  const response = await client.send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (response.exceptionDetails) {
    throw new Error('The page rejected a local storage operation');
  }
  return response.result?.value;
}

async function captureSourceSession(browserClient, target, pageUrl) {
  const attached = await browserClient.send('Target.attachToTarget', {
    targetId: target.targetId,
    flatten: true,
  });
  const sessionId = attached.sessionId;
  try {
    await browserClient.send('Network.enable', {}, sessionId);
    const cookieResponse = await browserClient.send('Network.getCookies', { urls: [pageUrl] }, sessionId);
    const storage = await evaluateByValue(
      {
        send(method, params) {
          return browserClient.send(method, params, sessionId);
        },
      },
      'Object.fromEntries(Array.from({length: localStorage.length}, (_, i) => { const key = localStorage.key(i); return [key, localStorage.getItem(key)]; }))',
    );
    if (!storage || typeof storage !== 'object') {
      throw new Error('Could not read the authenticated page storage');
    }
    return { cookies: cookieResponse.cookies || [], storage };
  } finally {
    await browserClient.send('Target.detachFromTarget', { sessionId }).catch(() => {});
  }
}

function cookieForSet(cookie) {
  const value = {
    name: cookie.name,
    value: cookie.value,
    domain: cookie.domain,
    path: cookie.path,
    secure: cookie.secure,
    httpOnly: cookie.httpOnly,
  };
  for (const key of ['sameSite', 'priority', 'sameParty', 'sourceScheme', 'sourcePort', 'partitionKey']) {
    if (cookie[key] !== undefined) {
      value[key] = cookie[key];
    }
  }
  if (typeof cookie.expires === 'number' && cookie.expires > 0) {
    value.expires = cookie.expires;
  }
  return value;
}

async function waitForPortFile(path, chromeProcess, deadline) {
  while (Date.now() < deadline) {
    if (chromeProcess.startupError) {
      throw new Error('Could not start headless Chrome');
    }
    if (chromeProcess.exitCode !== null) {
      throw new Error('Headless Chrome exited before DevTools became ready; the dedicated profile may be in use');
    }
    try {
      return await devToolsPortFromFile(path);
    } catch (error) {
      if (error.code !== 'ENOENT') {
        throw error;
      }
    }
    await sleep(POLL_INTERVAL_MS);
  }
  throw new Error('Timed out starting headless Chrome');
}

async function waitForPageTarget(port, deadline) {
  while (Date.now() < deadline) {
    const targets = await getTargets(port).catch(() => []);
    const target = targets.find((item) => item.type === 'page' && item.webSocketDebuggerUrl);
    if (target) {
      return target;
    }
    await sleep(POLL_INTERVAL_MS);
  }
  throw new Error('Timed out waiting for a headless Chrome page');
}

async function waitForOrigin(client, expectedOrigin, deadline) {
  while (Date.now() < deadline) {
    const origin = await evaluateByValue(client, 'location.origin').catch(() => null);
    if (origin === expectedOrigin) {
      return;
    }
    await sleep(POLL_INTERVAL_MS);
  }
  throw new Error('The dedicated Chrome profile is not logged in; open it visibly and sign in again');
}

async function waitForFreshToken(client, previousToken, expectedOrigin, deadline) {
  let sawExpectedOrigin = false;
  while (Date.now() < deadline) {
    const origin = await evaluateByValue(client, 'location.origin').catch(() => null);
    if (origin === expectedOrigin) {
      sawExpectedOrigin = true;
      const candidate = await evaluateByValue(client, "localStorage.getItem('TOKEN')").catch(() => null);
      if (typeof candidate === 'string' && candidate.trim() !== previousToken?.trim()) {
        try {
          return validateJwt(candidate);
        } catch {
          // The page may replace an old token asynchronously; keep polling.
        }
      }
    }
    await sleep(POLL_INTERVAL_MS);
  }
  if (!sawExpectedOrigin) {
    throw new Error('The dedicated Chrome profile is not logged in; open it visibly and sign in again');
  }
  throw new Error('The page did not produce a different, unexpired TOKEN before timeout');
}

async function stopChrome(client, chromeProcess) {
  if (client) {
    await client.send('Browser.close').catch(() => {});
    client.close();
  }
  if (!chromeProcess || chromeProcess.exitCode !== null || chromeProcess.startupError) {
    return;
  }
  const exited = new Promise((resolvePromise) => chromeProcess.once('exit', resolvePromise));
  await Promise.race([exited, sleep(3000)]);
  if (chromeProcess.exitCode === null) {
    chromeProcess.kill('SIGTERM');
    await Promise.race([exited, sleep(2000)]);
  }
  if (chromeProcess.exitCode === null) {
    chromeProcess.kill('SIGKILL');
  }
}

export async function launchHeadlessChrome(chromePath, profileDirectory, deadline) {
  await mkdir(profileDirectory, { recursive: true, mode: 0o700 });
  await chmod(profileDirectory, 0o700);

  const singletonLock = join(profileDirectory, 'SingletonLock');
  try {
    await lstat(singletonLock);
    throw new Error('The dedicated Chrome profile is already open; close it before refreshing');
  } catch (error) {
    if (error.code !== 'ENOENT') {
      throw error;
    }
  }

  const portFile = join(profileDirectory, 'DevToolsActivePort');
  await rm(portFile, { force: true });
  const chromeProcess = spawn(
    chromePath,
    [
      '--headless=new',
      '--remote-debugging-port=0',
      `--user-data-dir=${profileDirectory}`,
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-sync',
      '--window-size=1280,900',
      'about:blank',
    ],
    { stdio: ['ignore', 'ignore', 'ignore'] },
  );
  chromeProcess.once('error', (error) => {
    chromeProcess.startupError = error;
  });
  let client;
  try {
    const port = await waitForPortFile(portFile, chromeProcess, deadline);
    const target = await waitForPageTarget(port, deadline);
    client = new CdpClient(target.webSocketDebuggerUrl);
    await client.connect();
    return { chromeProcess, client };
  } catch (error) {
    await stopChrome(client, chromeProcess);
    throw error;
  }
}

async function seedDedicatedProfile(client, pageUrl, sourceSession, deadline) {
  await client.send('Network.enable');
  if (sourceSession.cookies.length > 0) {
    const result = await client.send('Network.setCookies', {
      cookies: sourceSession.cookies.map(cookieForSet),
    });
    if (result.success === false) {
      throw new Error('Chrome rejected the site cookie bootstrap');
    }
  }
  await client.send('Page.enable');
  await client.send('Page.navigate', { url: pageUrl });
  const origin = new URL(pageUrl).origin;
  await waitForOrigin(client, origin, deadline);
  const serializedStorage = JSON.stringify(sourceSession.storage);
  await evaluateByValue(
    client,
    `(() => { const values = ${serializedStorage}; for (const [key, value] of Object.entries(values)) localStorage.setItem(key, value); return true; })()`,
  );
  await client.send('Page.reload', { ignoreCache: true });
  await waitForOrigin(client, origin, deadline);
}

async function resolveBootstrapPage(configDirectory, apiOrigin, browserClient) {
  const response = await browserClient.send('Target.getTargets');
  const targets = (response.targetInfos || []).map((target) => ({
    targetId: target.targetId,
    type: target.type,
    url: target.url,
  }));
  const target = chooseSourceTarget(targets, apiOrigin);
  const page = new URL(target.url);
  page.search = '';
  page.hash = '';
  const pageUrl = page.href;
  await atomicWritePrivateFile(join(configDirectory, 'page_url'), `${pageUrl}\n`);
  return { target, pageUrl };
}

async function main() {
  const bootstrap = process.argv.slice(2).includes('--bootstrap-from-active-chrome');
  const configDirectory = resolve(
    process.env.CREDIT_CLAIM_CONFIG_DIR || join(homedir(), '.config/credit-claim'),
  );
  await mkdir(configDirectory, { recursive: true, mode: 0o700 });
  await chmod(configDirectory, 0o700);
  const tokenPath = join(configDirectory, 'token');
  const apiUrlValue = await readOptional(join(configDirectory, 'api_url'));
  if (!apiUrlValue) {
    throw new Error('api_url is missing');
  }
  const apiOrigin = new URL(apiUrlValue).origin;
  let pageUrl = await readOptional(join(configDirectory, 'page_url'));
  let sourceSession;

  if (bootstrap) {
    const sourcePortFile = resolve(
      process.env.CREDIT_CLAIM_SOURCE_PORT_FILE
        || join(homedir(), '.config/google-chrome/DevToolsActivePort'),
    );
    const sourceEndpoint = await devToolsEndpointFromFile(sourcePortFile);
    const sourceClient = new CdpClient(sourceEndpoint.webSocketUrl);
    await sourceClient.connect();
    try {
      const resolved = await resolveBootstrapPage(configDirectory, apiOrigin, sourceClient);
      pageUrl = resolved.pageUrl;
      sourceSession = await captureSourceSession(sourceClient, resolved.target, pageUrl);
    } finally {
      sourceClient.close();
    }
  }

  if (!pageUrl) {
    throw new Error('page_url is missing; run once with --bootstrap-from-active-chrome');
  }
  const page = new URL(pageUrl);
  if (page.origin !== apiOrigin) {
    throw new Error('page_url and api_url must use the same origin');
  }

  const timeoutMs = Number.parseInt(
    process.env.CREDIT_CLAIM_REFRESH_TIMEOUT_MS || String(DEFAULT_TIMEOUT_MS),
    10,
  );
  if (!Number.isInteger(timeoutMs) || timeoutMs < 5000 || timeoutMs > 120_000) {
    throw new Error('CREDIT_CLAIM_REFRESH_TIMEOUT_MS must be between 5000 and 120000');
  }
  const deadline = Date.now() + timeoutMs;
  const chromePath = process.env.CREDIT_CLAIM_CHROME || DEFAULT_CHROME;
  const profileDirectory = join(configDirectory, 'chrome-profile');
  let chromeProcess;
  let client;

  try {
    ({ chromeProcess, client } = await launchHeadlessChrome(chromePath, profileDirectory, deadline));
    if (bootstrap) {
      await seedDedicatedProfile(client, pageUrl, sourceSession, deadline);
      console.log('Headless Chrome profile bootstrap succeeded');
      return;
    }

    await client.send('Page.enable');
    await client.send('Page.navigate', { url: pageUrl });
    const previousToken = await readOptional(tokenPath);
    const refreshed = await waitForFreshToken(client, previousToken, page.origin, deadline);
    await atomicWriteToken(tokenPath, refreshed.token);
    console.log(`Headless token refresh succeeded; expires ${new Date(refreshed.exp * 1000).toISOString()}`);
  } finally {
    await stopChrome(client, chromeProcess);
  }
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href;
if (isMain) {
  main().catch((error) => {
    console.error(`ERROR: ${error.message}`);
    process.exitCode = 1;
  });
}
