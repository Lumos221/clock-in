// Execute the panel's script and CALL its draw functions.
// A parse cannot catch a temporal dead zone and a top-level run cannot either: a TDZ fires
// only when the function that reads the binding is invoked. `drawComposer` read `ta` three
// lines before `const ta` and blanked the whole board; both checks passed it.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const html = fs.readFileSync(process.argv[2], 'utf8');
const src = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].pop()[1];

// Parse it as a MODULE first. A classic script tolerates the same function being declared
// twice — the second silently wins — so a copy-pasted `archive` sat in the page unnoticed
// while it made the whole desk suite (which loads this script as a module) unrunnable:
// 34 tests red for one duplicate, and the real drift underneath them invisible.
const mjs = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'smoke-')), 'panel.mjs');
fs.writeFileSync(mjs, src);
try { execFileSync(process.execPath, ['--check', mjs], { stdio: 'pipe' }); }
catch (e) {
  console.log('MODULE PARSE FAILED: ' + String(e.stderr || e.message).split('\n').slice(0, 6).join(' '));
  process.exit(1);
}
finally { fs.rmSync(path.dirname(mjs), { recursive: true, force: true }); }

const el = () => new Proxy({}, { get(t, k) {
  if (k === 'classList') return { toggle(){}, add(){}, remove(){}, contains: () => false };
  if (k === 'dataset' || k === 'style') return {};
  if (k === 'getBoundingClientRect') return () => ({ top:0, bottom:0, left:0, right:0, height:0, width:0 });
  if (k === 'querySelectorAll') return () => [];
  if (k === 'querySelector') return () => null;
  if (k === 'lastElementChild' || k === 'firstElementChild') return null;
  if (['value','innerHTML','textContent','className','id','placeholder'].includes(k)) return '';
  if (['scrollTop','scrollHeight','clientHeight','offsetTop','selectionStart','selectionEnd'].includes(k)) return 0;
  return () => {};
}, set() { return true; } });

global.document = new Proxy({}, { get(t, k) {
  if (k === 'getElementById') return el;
  if (k === 'querySelectorAll') return () => [];
  if (k === 'querySelector') return () => null;
  if (k === 'documentElement' || k === 'body') return el();
  if (k === 'activeElement') return null;
  return () => {};
}});
global.location = { search: '' };
global.window = global; global.innerHeight = 900; global.scrollY = 0;
global.addEventListener = () => {};
global.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
global.navigator = { platform: 'MacIntel', userAgent: '', clipboard: { writeText: () => Promise.resolve() } };
global.fetch = () => Promise.resolve({ json: () => Promise.resolve({}) });
global.requestAnimationFrame = () => {};
global.setInterval = () => 0; global.setTimeout = () => 0; global.clearTimeout = () => {};

const DATA = { T: { list: [], byId: {} }, all: [], needs: [], info: [], parked: [], hist: [],
  shipped: [], shipLine: () => '', lastAnsweredTs: '',
  work: { doing: [], review: [], merge: [], blocked: [], todo: [] } };

let fn;
// `setState` is the reason this catches anything: drawDesk opens with `if(!DESKDATA) return`,
// so calling it on an empty page walked no branch at all. A ReferenceError sat on the
// conversation path — their default view — for as long as the gate only called it blind.
try { fn = new Function('"use strict";' + src + '\n;return {drawComposer, drawDesk, renderTray, convoRail, convoThread, msgRow, sendTo, marker, commitCompose, ignoreItem, archive, BASKET, DEMPTY, setState: (d, f) => { DESKDATA = d; if (f) DFILTER = f; }};'); }
catch (e) { console.log('PARSE FAILED: ' + e.message); process.exit(1); }

let api;
try { api = fn(); } catch (e) { console.log('TOP-LEVEL FAILED: ' + e.constructor.name + ': ' + e.message); process.exit(1); }
// commitCompose only does anything with something staged and a conversation open.
try { api.BASKET.set('X-1', { kind: 'reply', text: 'probe' }); } catch (e) {}

// Now CALL them — this is the half that catches a dead zone.
const calls = [['drawComposer', []], ['sendTo', []], ['marker', []],
               ['convoRail', [DATA]], ['convoThread', [DATA]],
               ['commitCompose', [true]], ['commitCompose', [false]],
               ['renderTray', []], ['ignoreItem', ['X-1']], ['archive', ['X-1', true]]];
// drawDesk once per filter, with real state loaded, so every lane's branch is executed.
// TWICE per filter: the conversation view jumps to the newest message on the first draw
// after an open (`if(convoJump || atEnd)`), and a short-circuited `||` never evaluates its
// right side. One call per filter left the poll-redraw branch — the one that runs all day —
// unexecuted, and a ReferenceError lived there.
for (const f of Object.keys(api.DEMPTY || { desk: 1 })) calls.push(['drawDesk', [], f], ['drawDesk', [], f]);

for (const [name, args, filter] of calls) {
  try {
    if (filter) api.setState(DATA, filter);
    api[name] && api[name](...args);
  }
  catch (e) {
    const clickPath = ['commitCompose', 'ignoreItem', 'archive', 'renderTray', 'drawComposer'];
    if (e instanceof ReferenceError || e instanceof SyntaxError || clickPath.includes(name)) {
      console.log('CALL FAILED in ' + name + (filter ? ' [' + filter + ']' : '') +
                  ': ' + e.constructor.name + ': ' + e.message);
      process.exit(1);
    }
  }
}
console.log('panel smoke: OK');
