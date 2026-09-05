// Exercise the actual calendar renderers without a browser connection.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('site/assets/app.js', 'utf8');
function between(start, end) {
  const offset = source.indexOf(start);
  assert(offset >= 0 && source.indexOf(end, offset) > offset);
  return source.slice(offset, source.indexOf(end, offset));
}
const context = vm.createContext({
  window: {innerWidth: 390}, now: new Date('2026-09-06T12:00:00+08:00'),
  fullCurrentMonth: false, selectedDay: '2026-09-06',
  todayStr: () => '2026-09-06', esc: s => String(s || ''),
  goingBtn: () => '', organizerHtml: () => '', labels: {campus: {}},
  dayPanel: {innerHTML: '', scrollTop: 0},
  byDay: {'2026-09-06': [{id: 'talk', title: 'Talk', school: 'nthu', start_at: '2026-09-06T19:00:00+08:00', all_day: false}]},
  periodEvents: [
    {id: 'interview', title: 'Interview', school: 'nthu', start_at: '2026-09-02T00:00:00+08:00', end_at: '2026-09-07T23:59:59+08:00'},
    {id: 'exhibition', title: 'Exhibition', school: 'nthu', start_at: '2026-08-01T00:00:00+08:00', end_at: '2026-10-10T23:59:59+08:00'},
    {id: 'camp', title: 'Camp', school: 'both', start_at: '2026-09-03T00:00:00+08:00', end_at: '2026-09-05T23:59:59+08:00'}
  ]
});
vm.runInContext(between('  function isPeriodEvent(', '  // 活動列表依'), context);
vm.runInContext(between('    function periodsInRange(', '    var calendarOrgs'), context);
vm.runInContext(between('    function renderDay(', '    calEl.addEventListener'), context);
let mobile = vm.runInContext('agendaMonthHtml(new Date(2026, 8, 1))', context);
assert(mobile.includes('期間活動'));
assert(mobile.includes('9/2–9/7'));
assert.equal((mobile.match(/\/event\/interview\//g) || []).length, 1);
assert(!mobile.includes('/event/camp/'));
assert(mobile.includes('3 場'));
context.window.innerWidth = 1200;
let desktop = vm.runInContext('monthHtml(new Date(2026, 8, 1))', context);
assert(!desktop.includes('data-cal-event="interview"'));
assert(desktop.includes('/event/interview/'));
assert(desktop.includes('/event/camp/')); // desktop shows the whole month
assert(desktop.includes('4 場'));
vm.runInContext('renderDay()', context);
assert(context.dayPanel.innerHTML.includes('/event/interview/'));
assert(!context.dayPanel.innerHTML.includes('/event/camp/'));
let october = vm.runInContext('monthHtml(new Date(2026, 9, 1))', context);
assert(october.includes('/event/exhibition/'));
assert(!october.includes('/event/interview/'));
context.fullCurrentMonth = true;
assert(vm.runInContext('agendaMonthHtml(new Date(2026, 8, 1))', context).includes('/event/camp/'));
assert.equal(vm.runInContext('periodsInRange("2026-09-07", "2026-09-07").length', context), 2);
console.log('Calendar period rendering: mobile, desktop, selected day, month overlap and last day passed.');
