const assert = require('node:assert/strict');
const vm = require('node:vm');
const script = require('node:fs').readFileSync(0, 'utf8');
const summary = {innerHTML: 'initial estimate'};
let timer, visibility, calls = 0, fail = false, release;
const document = {
  hidden: false,
  querySelector(selector) {assert.equal(selector, '#contribution-crawl-summary'); return summary;},
  addEventListener(name, callback) {assert.equal(name, 'visibilitychange'); visibility = callback;},
};
vm.runInNewContext(script, {
  document,
  setInterval(callback, delay) {assert.equal(delay, 60000); timer = callback;},
  fetch: async (url, options) => {
    assert.equal(url, '/auth/crawl-frequency');
    assert.equal(options.cache, 'no-store');
    calls++;
    if (fail) throw Error('offline');
    if (release) await new Promise(resolve => {release = resolve;});
    return {ok:true, json:async () => ({html:'updated estimate ' + calls})};
  },
});
(async () => {
  await timer(); assert.equal(summary.innerHTML, 'updated estimate 1');
  document.hidden = true;
  await timer(); assert.equal(calls, 1);
  document.hidden = false;
  visibility(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(summary.innerHTML, 'updated estimate 2');
  fail = true; await timer(); assert.equal(summary.innerHTML, 'updated estimate 2');
  fail = false; await timer(); assert.equal(summary.innerHTML, 'updated estimate 4');
  release = true;
  const pending = timer(); await timer(); assert.equal(calls, 5);
  release(); await pending; assert.equal(summary.innerHTML, 'updated estimate 5');
})().catch(error => {console.error(error); process.exitCode = 1;});
