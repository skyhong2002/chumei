const assert = require('node:assert/strict');
const vm = require('node:vm');
const script = require('node:fs').readFileSync(0, 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));

async function page(quota, responses = [], blockedReason = '') {
  const nodes = new Map(), events = {}, calls = [];
  const document = {
    querySelector(selector) {
      if (!nodes.has(selector)) nodes.set(selector, {
        innerHTML: '', textContent: '', classList: {toggle() {}},
        addEventListener() {},
      });
      return nodes.get(selector);
    },
    addEventListener(name, handler) { events[name] = handler; },
  };
  const source = {id: 'test', name: 'Test', platform: 'Threads', backend: 'RSSHub', status: 'due', blockedReason};
  const data = {counts: {}, sources: [source, {...source, id: 'other', name: 'Other'}], pipeline: {intervalHours: 3}};
  let initial = true;
  vm.runInNewContext(script, {document, Intl, Date, fetch: async (url, options = {}) => {
    if (url === '/api/status.json') return {ok: true, json: async () => data};
    if (initial) { initial = false; return {ok: true, json: async () => quota}; }
    calls.push({url, ...options});
    const response = responses.shift();
    if (response instanceof Error) throw response;
    assert.ok(response, 'unexpected request');
    return {ok: response.status < 400, status: response.status, json: async () => response.body};
  }});
  await settle();
  return {
    html: () => nodes.get('#source-rows').innerHTML,
    snapshot: () => nodes.get('#snapshot').textContent,
    calls,
    click(action) {
      events.click({target: {closest: () => ({dataset: {sourceRequest: 'test', weightAction: action}})}});
    },
  };
}

(async () => {
  const guest = await page({authenticated: false, weights: {test: 7}, remainingToday: 0});
  assert.match(guest.html(), /總權重 7/);
  assert.doesNotMatch(guest.html(), /data-weight-action/);
  const empty = await page({authenticated: true, remainingToday: 0, weights: {test: 3}, myWeights: {test: 2}});
  assert.match(empty.html(), /data-weight-action="remove"/);
  assert.doesNotMatch(empty.html(), /data-weight-action="add"/);
  assert.match(empty.html(), /你投入 2/);
  const initial = {authenticated: true, remainingToday: 1, weights: {}, myWeights: {}};
  const added = {authenticated: true, remainingToday: 0, weights: {test: 1}, myWeights: {test: 1}, request: {sourceWeight: 1}};
  const ui = await page(initial, [{status: 201, body: added}, {status: 200, body: {...initial, request: {sourceWeight: 0}}}]);
  assert.match(ui.html(), /總權重 0/);
  assert.doesNotMatch(ui.html(), /data-weight-action="remove"/);
  ui.click('add'); ui.click('add');
  await settle();
  assert.equal(ui.calls.length, 1, 'double click must send one mutation');
  assert.equal(ui.calls[0].method, 'POST');
  assert.doesNotMatch(ui.html(), /data-weight-action="add"/, 'quota exhaustion hides plus on every row');
  assert.match(ui.html(), /總權重 1/);
  assert.match(ui.snapshot(), /尚餘 0 點/);
  ui.click('remove'); await settle();
  assert.equal(ui.calls[1].method, 'DELETE');
  assert.match(ui.html(), /總權重 0/);
  assert.doesNotMatch(ui.html(), /data-weight-action="remove"/);
  assert.match(ui.html(), /data-weight-action="add"/);
  assert.match(ui.snapshot(), /尚餘 1 點/);
  const blocked = await page({...added, remainingToday: 1}, [], '冷卻中');
  assert.match(blocked.html(), /data-weight-action="remove"[^>]* >−/);
  assert.match(blocked.html(), /data-weight-action="add"[^>]* disabled/);
  const stale = await page(initial, [
    {status: 429, body: {...added, error: 'daily request limit reached'}},
    {status: 200, body: added},
  ]);
  stale.click('add'); await settle();
  assert.doesNotMatch(stale.html(), /data-weight-action="add"/);
  const uncertain = await page(initial, [new Error('connection lost'), {status: 200, body: added}]);
  uncertain.click('add'); await settle();
  assert.match(uncertain.html(), /總權重 1/);
  assert.doesNotMatch(uncertain.html(), /data-weight-action="add"/);
  console.log('Status UI guest, quota, add, withdraw, pending and recovery checks passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
