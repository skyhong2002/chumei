const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('site/assets/app.js', 'utf8');
const code = source.slice(source.indexOf('  var eventIndexPromise;'), source.indexOf('  function archiveStatus('));
let calls = [], fail = false;
const bundle = {events: [{id: 'new', start_at: '2026-09-01'}], archive_url: '/data/events-archive.json'};
const context = vm.createContext({Promise, Error, fetch: async url => {
  calls.push(url);
  if (fail) return {ok: false};
  return {ok: true, json: async () => url.includes('archive')
    ? {events: [{id: 'new', start_at: '2026-09-01'}, {id: 'old', start_at: '2026-01-01'}]}
    : bundle};
}});
vm.runInContext(code, context);
(async () => {
  const [a, b] = await Promise.all([context.loadEventIndex(), context.loadEventIndex()]);
  assert.equal(a, b);
  assert.deepEqual(calls, ['/data/events-index.json']); // no speculative history
  fail = true;
  await assert.rejects(context.loadEventArchive(a));
  assert.equal(a.events.length, 1); // preserves usable current data on failure
  fail = false;
  await Promise.all([context.loadEventArchive(a), context.loadEventArchive(a)]);
  assert.deepEqual(a.events.map(e => e.id), ['old', 'new']);
  assert.equal(calls.filter(x => x.includes('archive')).length, 2); // failure + one shared retry
  await context.loadEventArchive(a);
  assert.equal(calls.length, 3);
  console.log('Compact index: lazy archive, shared requests, failure/retry, deduplication and ordering passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
