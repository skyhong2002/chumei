// Shared JSON loader: HTTP status, timeout, network errors, shared retries and the retry UI.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('site/assets/app.js', 'utf8');
const start = source.indexOf('/* 共用 JSON 讀取');
const end = source.indexOf('(function () {\n  "use strict";\n  var fetchJSON');
assert(start >= 0 && end > start, 'helper block not found');
const helper = source.slice(start, end);

let handler;
const calls = [];
function element(tag) {
  const el = {
    tagName: tag, children: [], listeners: {}, attrs: {}, textContent: '', className: '', disabled: false,
    parentNode: null,
    setAttribute(k, v) { this.attrs[k] = v; },
    appendChild(child) { child.parentNode = this; this.children.push(child); return child; },
    insertBefore(child, ref) {
      child.parentNode = this;
      this.children.splice(this.children.indexOf(ref), 0, child);
      return child;
    },
    addEventListener(type, fn) { this.listeners[type] = fn; },
    remove() { const p = this.parentNode; if (p) p.children.splice(p.children.indexOf(this), 1); },
  };
  Object.defineProperty(el, 'innerHTML', { set() { this.children = []; }, get() { return ''; } });
  return el;
}
const context = vm.createContext({
  Promise, Error, setTimeout, clearTimeout, AbortController, window: {},
  navigator: { onLine: true },
  document: { createElement: element },
  fetch: (url, init) => { calls.push(url); return handler(url, init); },
});
vm.runInContext(helper, context);
const { chumeiFetchJSON: fetchJSON, chumeiLoadError: loadError } = context.window;

(async () => {
  handler = async () => ({ ok: true, status: 200, json: async () => ({ hello: 1 }) });
  assert.deepEqual(await fetchJSON('/a.json'), { hello: 1 });

  handler = async () => ({ ok: false, status: 503, json: async () => { throw new Error('html'); } });
  await assert.rejects(fetchJSON('/a.json'), e => e.kind === 'http' && e.status === 503);
  assert.match(loadError.describe({ kind: 'http', status: 503 }), /HTTP 503/);

  handler = async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError('bad'); } });
  await assert.rejects(fetchJSON('/a.json'), e => e.kind === 'parse');

  handler = async () => { throw new TypeError('Failed to fetch'); };
  await assert.rejects(fetchJSON('/a.json'), e => e.kind === 'network');

  // Abortable hang: the timer must abort and report a timeout.
  handler = (url, init) => new Promise((resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
  });
  await assert.rejects(fetchJSON('/slow.json', { timeout: 20 }), e => e.kind === 'timeout');

  // shared(): concurrent callers share one request; a failure is not cached.
  calls.length = 0;
  let fail = true;
  handler = async () => fail ? { ok: false, status: 502 } : { ok: true, status: 200, json: async () => ({ entries: [] }) };
  await Promise.all([
    assert.rejects(fetchJSON.shared('/data/sources.json')),
    assert.rejects(fetchJSON.shared('/data/sources.json')),
  ]);
  assert.equal(calls.length, 1);
  fail = false;
  const [x, y] = await Promise.all([fetchJSON.shared('/data/sources.json'), fetchJSON.shared('/data/sources.json')]);
  assert.equal(x, y);
  assert.equal(calls.length, 2);

  // Retry UI: replaces host content, button disables itself and calls retry with the box.
  const host = element('div');
  host.appendChild(element('p'));
  let retried = null;
  const box = loadError(host, '貼文載入失敗。', b => { retried = b; }, { replace: true });
  assert.equal(host.children.length, 1);
  assert.equal(box.attrs.role, 'alert');
  const button = box.children[1];
  assert.equal(button.textContent, '重試');
  button.listeners.click();
  assert.equal(retried, box);
  assert.equal(button.disabled, true);

  // before: keeps existing content and inserts the alert ahead of it.
  const parent = element('main');
  const feed = parent.appendChild(element('div'));
  loadError(feed, 'x', null, { before: true });
  assert.equal(parent.children[0].className, 'load-error');
  assert.equal(parent.children[1], feed);
  console.log('fetchJSON: ok/HTTP/parse/network/timeout errors, shared retry and retry UI passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
