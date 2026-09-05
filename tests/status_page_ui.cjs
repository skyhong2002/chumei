const assert = require('node:assert/strict');
const vm = require('node:vm');
const script = require('node:fs').readFileSync(0, 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));

async function page(quota, responses = [], blockedReason = '', sources = null) {
  const nodes = new Map(), events = {}, calls = [];
  const headers = ['name','backend','status','recent','next','weight'].map(key => ({
    dataset: {sourceSort: key}, attributes: {}, arrow: {textContent: ''},
    setAttribute(name, value) {this.attributes[name] = value;},
    querySelector() {return this.arrow;},
  }));
  const document = {
    querySelector(selector) {
      if (!nodes.has(selector)) nodes.set(selector, {
        innerHTML: '', textContent: '', classList: {toggle() {}},
        addEventListener(name, handler) {events[selector + ':' + name] = handler;},
        setAttribute() {},
      });
      return nodes.get(selector);
    },
    addEventListener(name, handler) { events[name] = handler; },
    querySelectorAll(selector) {return selector === '[data-source-sort]' ? headers : [];},
  };
  const source = {id: 'test', name: 'Test', platform: 'Threads', backend: 'RSSHub', status: 'due', blockedReason};
  const data = {counts: {}, sources: sources || [source, {...source, id: 'other', name: 'Other'}], pipeline: {intervalHours: 3}};
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
    headers,
    names: () => [...nodes.get('#source-rows').innerHTML.matchAll(/class="status-name">([^<]*)</g)].map(x => x[1]),
    sort(key) {events.click({target: {closest: selector => selector === '[data-source-sort]' ? {dataset: {sourceSort:key}} : null}});},
    selectSort(key) {events['#source-sort:change']({target: {value:key}});},
    reverseSort() {events['#source-sort-direction:click']();},
    search(value) {events['#source-search:input']({target: {value}});},
    showMore() {events.click({target: {closest: selector => selector === '[data-show-more]' ? {} : null}});},
    click(action) {
      events.click({target: {closest: selector => selector === '[data-source-request]' ? {dataset: {sourceRequest: 'test', weightAction: action}} : null}});
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
  const sources = [
    {id:'test',name:'A',backend:'Z',status:'ok',lastAttempt:20,nextDue:100},
    {id:'b',name:'B',backend:'A',status:'error',lastAttempt:3,nextDue:20},
    {id:'c',name:'C',backend:'M',status:'due',lastAttempt:100,nextDue:3},
    {id:'d',name:'D',backend:null,status:'blocked',lastAttempt:null,nextDue:null},
  ];
  const sorted = await page({weights:{test:2,b:10,d:1}}, [], '', sources);
  for (const [key, first, second] of [
    ['name', ['A','B','C','D'], ['D','C','B','A']],
    ['backend', ['B','C','A','D'], ['A','C','B','D']],
    ['recent', ['C','A','B','D'], ['B','A','C','D']],
    ['next', ['C','B','A','D'], ['A','B','C','D']],
    ['weight', ['B','A','D','C'], ['C','D','A','B']],
    ['status', ['B','D','C','A'], ['A','C','D','B']],
  ]) {
    sorted.sort(key); assert.deepEqual(sorted.names(), first, key + ' default order');
    const header = sorted.headers.find(h => h.dataset.sourceSort === key);
    assert.equal(header.attributes['aria-pressed'], 'true');
    sorted.sort(key); assert.deepEqual(sorted.names(), second, key + ' reverse order');
  }
  sorted.selectSort('weight'); assert.deepEqual(sorted.names(), ['B','A','D','C']);
  sorted.reverseSort(); assert.deepEqual(sorted.names(), ['C','D','A','B']);
  sorted.search('Z'); assert.deepEqual(sorted.names(), ['A']);
  sorted.search(''); assert.deepEqual(sorted.names(), ['C','D','A','B']);
  const many = await page({}, [], '', Array.from({length:130}, (_,i) => ({id:String(i),name:'Item '+i,status:'ok',nextDue:130-i})));
  many.selectSort('name');
  assert.equal(many.names().length, 120);
  assert.equal(many.names()[0], 'Item 0');
  assert.equal(many.names()[119], 'Item 119');
  many.showMore(); assert.equal(many.names().length, 130);
  many.sort('name'); assert.equal(many.names()[0], 'Item 129');
  assert.equal(many.names().length, 120);
  const reweighted = await page({...initial,weights:{b:2}}, [{status:201,body:{...added,weights:{test:3,b:2}}}], '', sources.slice(0,2));
  reweighted.selectSort('weight'); assert.equal(reweighted.names()[0], 'B');
  reweighted.click('add'); await settle();
  assert.equal(reweighted.names()[0], 'A');
  console.log('Status UI guest, quota, add, withdraw, pending and recovery checks passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
