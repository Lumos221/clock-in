"""Tests for the Dashboard desk — the inbox layout (rail of counts + one list).

These EXECUTE the panel's own JavaScript under node rather than matching its text.
The board's rules have always lived in JS and so have never been tested; every desk
bug this month (phantom L2 chips, the tile that said 11 while the header said 16, an
unstyled kind rendering an invisible dot) was a rule nothing could verify. A stubbed
DOM is enough to run the pure parts: the lane partition, the filter table, and what
each filter renders.

Run: python3 skills/orchestrate/scripts/test_desk.py
"""
import os, re, sys, json, shutil, subprocess, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board

NODE = shutil.which("node")

# A DOM thin enough to be obvious and fat enough to let the pure functions run. Every
# element is the same recording stub, so `innerHTML` written by drawDesk is readable back.
PRELUDE = r"""
// The conversation composer's subtree, modelled just enough to tell a REBUILD from a
// PATCH. Writing #composer's innerHTML mints a brand-new #ctext (which is exactly what
// the bug did to them typing); patching it must reach these children and leave the
// textarea node alone. A test can therefore hold the element and watch its identity.
let COMPOSER_KIDS = null;
// style starts as empty strings, not undefined — a real CSSStyleDeclaration reads back
// '' for an unset property, and JSON.stringify silently drops undefined.
function El(id){ this._id=id; this._innerHTML=''; this.textContent=''; this.value=''; this.placeholder='';
  this.outerHTML='';
  this.style={ paddingBottom:'', height:'', bottom:'', display:'' };
  this.classList={ _s:new Set(), add(x){this._s.add(x)}, remove(x){this._s.delete(x)},
    toggle(x,on){ on?this._s.add(x):this._s.delete(x) }, contains(x){return this._s.has(x)} };
  this.dataset={}; this.offsetHeight=120; this.scrollHeight=46;
  this.focus=()=>{}; this.setSelectionRange=()=>{}; this.addEventListener=()=>{};
  this.scrollIntoView=()=>{};
  // Geometry: the composer sizes its frame from a live rect, so a stub without one
  // takes down every test that opens a box. Zeros are honest here — these tests are
  // about what gets rendered, not about where it lands on the glass.
  this.getBoundingClientRect=()=>({top:0,bottom:0,left:0,right:0,height:0,width:0});
  this.querySelector=(s)=>((this._id==='composer'||this._id==='cwrap') && COMPOSER_KIDS)
    ? (COMPOSER_KIDS[s] || null) : null;
  this.querySelectorAll=()=>[];
  this.scrollTop=0; this.clientHeight=0; this.offsetTop=0;
  Object.defineProperty(this,'innerHTML',{
    get(){ return this._innerHTML; },
    // The compose box is rendered INSIDE the desk list, so the textarea is a fresh
    // element on every redraw. Model that: after the list is written, #ctext exists
    // only if the markup contains it, carrying whatever value the render put there.
    set(v){ this._innerHTML=v;
      if(this._id==='desklist') syncCtext(v);
      if(this._id==='composer') syncComposer(v); },
  });
}
// #ctext has two homes and only one exists at a time: inside a desk row (`.rcompose`,
// written into #desklist) or inside the conversation composer (#composer). They need
// separate flags — one shared flag meant whichever view rendered LAST decided whether the
// other's textarea was in the document, and the desk tests found it missing.
let CTEXT_IN_DOM = false;        // the desk-row box
let CTEXT_IN_COMPOSER = false;   // the conversation box
function syncComposer(html){
  if(!/class='cwrap'/.test(html)){ COMPOSER_KIDS = null; CTEXT_IN_COMPOSER = false; return; }
  const ta = (_els['ctext'] = new El('ctext'));      // a REBUILD mints a NEW element
  const m = /<textarea[^>]*>([\s\S]*?)<\/textarea>/.exec(html);
  ta.value = m ? unesc(m[1]) : '';
  CTEXT_IN_COMPOSER = true;
  COMPOSER_KIDS = { '.cwrap': new El('cwrap'), '.cctx': new El('cctx'),
                    '.chint': new El('chint'), '#sendbtn': new El('sendbtn') };
}
function unesc(s){ return String(s).replace(/&amp;/g,'&').replace(/&lt;/g,'<')
  .replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'"); }
function syncCtext(html){
  const m = /<textarea[^>]*id='ctext'([\s\S]*?)>([\s\S]*?)<\/textarea>/.exec(html);
  const ta = _els['ctext'] || (_els['ctext'] = new El('ctext'));
  CTEXT_IN_DOM = !!m;
  if(m){
    ta.value = unesc(m[2]);
    const f = /data-for='([^']*)'/.exec(m[1]);   // which row this box belongs to
    ta.dataset = { for: f ? f[1] : undefined };
  }
}
const _els={};
globalThis.document={
  documentElement:new El('html'),
  getElementById(id){
    if(id==='ctext' && !CTEXT_IN_DOM && !CTEXT_IN_COMPOSER) return null;
    return _els[id] || (_els[id]=new El(id));
  },
  querySelector(){ return null; },
  querySelectorAll(){ return []; },
  title:'', body:new El('body'), addEventListener(){}, removeEventListener(){},
};
globalThis.localStorage={ _m:{}, getItem(k){return this._m[k]??null}, setItem(k,v){this._m[k]=v} };
globalThis.location={ search:'' };
globalThis.addEventListener=function(){};
// The page binds its resize and theme listeners on `window`, not on the bare global. Left
// out, every test in this file died on one top-level ReferenceError and the whole suite
// read as 34 red — a harness that falls behind the page tests nothing at all.
globalThis.window=globalThis;
globalThis.scrollY=0; globalThis.innerHeight=800; globalThis.innerWidth=1200;
globalThis.matchMedia=function(){ return { matches:false, addEventListener(){}, addListener(){} }; };
globalThis.requestAnimationFrame=function(fn){ return 0; };
globalThis.setInterval=function(){ return 0; };
globalThis.setTimeout=function(){ return 0; };
globalThis.clearTimeout=function(){};
globalThis.POSTS=[];
globalThis.fetch=function(url, opt){
  POSTS.push({url, body: opt && opt.body ? JSON.parse(opt.body) : null});
  return Promise.resolve({json:()=>Promise.resolve({})});
};
// node 22 defines navigator as a getter-only global, so assignment throws
Object.defineProperty(globalThis, 'navigator',
  { value:{ clipboard:{ writeText(){ return Promise.resolve(); } } }, configurable:true });
"""


def panel_js():
    scripts = re.findall(r"<script>(.*?)</script>", board.PAGE, re.S)
    return max(scripts, key=len)


def run_js(body):
    """Run the panel script plus `body`, and return the JSON it prints."""
    # async so a test body can await the panel's own promises (send, basket writes)
    src = PRELUDE + panel_js() + "\n;(async function(){\n" + body + "\n})();\n"
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8") as f:
        f.write(src)
        path = f.name
    try:
        out = subprocess.run([NODE, path], capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            raise AssertionError("node failed:\n" + out.stderr[-2500:])
        return json.loads(out.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(path)


TASKS_JS = """
const TB = [
  {label:'#1', name:'a', status:'doing'},
  {label:'#2', name:'b', status:'doing'},
  {label:'#3', name:'c', status:'review'},
  {label:'#4', name:'d', status:'blocked'},
  {label:'#5', name:'e', status:'todo', l2:'pass'},   // passed, unmerged
  {label:'#6', name:'f', status:'todo'},
  {label:'#7', name:'g', status:'done', l2:'pass'},   // merged: not in flight
  {label:'#8', name:'h', status:'doing', l2:'pass'},  // passed AND doing: counted once
];
// The panel's OWN lane rule, not a copy of it — a re-implementation here would pass
// forever while the board drifted underneath, which is the exact fault these guard.
const lanes = deskLanes(TB);
"""


@unittest.skipIf(not NODE, "node not available")
class Partition(unittest.TestCase):
    """The Work lanes must PARTITION the header's in-flight number.

    The retired tile said 11 while the header said 16 about the same question on the
    same screen — two implementations of "how much work is live". The rail replaces
    the tile only if its lanes are disjoint and sum to inFlight exactly."""

    def test_lanes_sum_to_in_flight(self):
        r = run_js(TASKS_JS + """
        const flight = TB.filter(inFlight);
        const sum = lanes.doing.length + lanes.review.length + lanes.merge.length + lanes.blocked.length;
        console.log(JSON.stringify({flight: flight.length, sum}));
        """)
        self.assertEqual(r["sum"], r["flight"])

    def test_lanes_are_disjoint(self):
        """A card counted in two lanes would inflate the rail over the header."""
        r = run_js(TASKS_JS + """
        const seen = {}, dupes = [];
        for (const k of ['doing','review','merge','blocked'])
          for (const t of lanes[k]) { if (seen[t.label]) dupes.push(t.label); seen[t.label]=k; }
        console.log(JSON.stringify({dupes}));
        """)
        self.assertEqual(r["dupes"], [])

    def test_todo_excludes_a_card_awaiting_merge(self):
        """#5 passed review and is still filed todo. Left in Todo it would read as
        un-started work AND appear in 待合并 — the double-count the lanes exist to stop."""
        r = run_js(TASKS_JS + """
        console.log(JSON.stringify({todo: lanes.todo.map(t=>t.label), merge: lanes.merge.map(t=>t.label)}));
        """)
        self.assertEqual(r["merge"], ["#5"])
        self.assertNotIn("#5", r["todo"])

    def test_a_merged_card_is_not_in_flight(self):
        r = run_js(TASKS_JS + """
        console.log(JSON.stringify({merge: lanes.merge.map(t=>t.label),
                                    flight: TB.filter(inFlight).map(t=>t.label)}));
        """)
        self.assertNotIn("#7", r["merge"])
        self.assertNotIn("#7", r["flight"])


DESK_JS = """
const T = {list:[], byId:{}};
const mk = (id,kind,text,st) => ({id, dept:'CEO', kind, text, status:st||'open',
                                  created:'2026-07-27T09:00', updated:'2026-07-27T09:00'});
function seed(needs, info, parked, hist){
  DESKDATA = {
    T, needs, info, parked, hist,
    shipped: [], shipLine: x=>`<div class='done-line'>${x}</div>`,
    lastAnswered: 'last answered 5m ago',
    work: {doing:[], review:[], merge:[], blocked:[], todo:[]},
  };
}
"""


@unittest.skipIf(not NODE, "node not available")
class DeskList(unittest.TestCase):
    def test_an_empty_desk_shrinks_to_one_line(self):
        """Their call: with nothing waiting the desk gets SMALLER. It must not pad itself
        out with status, and it must still show the update feed underneath."""
        r = run_js(DESK_JS + """
        seed([], [mk('CEO-1','info','an fyi')], [], []);
        DFILTER='desk';
        const h = deskList(DESKDATA);
        console.log(JSON.stringify({clear: h.includes('dclear'), hot: /class="row[^"]*hot/.test(h),
                                    split: h.includes('dsplit'), rows: (h.match(/class="row/g)||[]).length}));
        """)
        self.assertTrue(r["clear"])
        self.assertFalse(r["hot"])
        self.assertTrue(r["split"], "the update feed still follows the clear line")

    def test_a_waiting_ask_renders_hot_above_the_updates(self):
        r = run_js(DESK_JS + """
        seed([mk('CEO-9','decide','answer me')], [mk('CEO-1','info','an fyi')], [], []);
        DFILTER='desk';
        const h = deskList(DESKDATA);
        console.log(JSON.stringify({clear: h.includes('dclear'), hot: /class="row[^"]*hot/.test(h),
                                    askFirst: h.indexOf('CEO-9') < h.indexOf('CEO-1')}));
        """)
        self.assertFalse(r["clear"], "no clear line while something waits")
        self.assertTrue(r["hot"], "a live ask carries the hot class, not an FYI's weight")
        self.assertTrue(r["askFirst"])

    def test_history_caps_and_says_so(self):
        """A bare count over a short list reads as a panel that lost the rest."""
        r = run_js(DESK_JS + """
        const many = Array.from({length: DESK_TAIL + 12}, (_,i)=>mk('H-'+i,'info','x','resolved'));
        seed([], [], [], many);
        DFILTER='history';
        const h = deskList(DESKDATA);
        console.log(JSON.stringify({rows: (h.match(/data-k="H-/g)||[]).length,
                                    more: /showing the latest/.test(h), tail: DESK_TAIL,
                                    total: many.length}));
        """)
        self.assertEqual(r["rows"], r["tail"])
        self.assertTrue(r["more"])

    def test_every_rail_row_has_an_empty_state(self):
        """A filter with no DEMPTY entry falls back to "Nothing here." — a dead end that
        tells their nothing about the lane they just opened."""
        js = panel_js()
        keys = re.findall(r"railRow\('([a-z]+)'", js)
        self.assertTrue(keys, "no rail rows found — the desk markup moved")
        r = run_js("console.log(JSON.stringify({empties: Object.keys(DEMPTY)}));")
        for k in keys:
            self.assertIn(k, r["empties"], "rail row %r has no empty state" % k)

    def test_each_filter_renders_without_throwing_when_its_lane_is_empty(self):
        r = run_js(DESK_JS + """
        seed([], [], [], []);
        const bad = [];
        for (const k of Object.keys(DEMPTY)) {
          DFILTER = k;
          try { const h = deskList(DESKDATA); if (!h) bad.push(k+':blank'); }
          catch(e) { bad.push(k+':'+e.message); }
        }
        console.log(JSON.stringify({bad}));
        """)
        self.assertEqual(r["bad"], [])

    def test_a_lane_row_shows_the_age_without_repeating_the_lane(self):
        """stageAge() appends where the card sits. In a lane that filters on exactly
        that stage every row would end with the name of the lane it is already in."""
        r = run_js("""
        const t = {label:'#1', name:'x', status:'todo', l2:'pass',
                   since: new Date(Date.now()-19*3600*1000).toISOString().slice(0,16)};
        console.log(JSON.stringify({full: stageAge(t).txt, row: deskTask(t)}));
        """)
        self.assertIn("待合并", r["full"], "stageAge still names the stage for the card grid")
        self.assertNotIn("待合并", r["row"], "the lane row must not repeat its own lane")
        self.assertRegex(r["row"], r"""<span class='rage' data-since="[^"]+">\d+[mhd]</span>""")

    def test_an_em_dash_dept_reads_as_unassigned(self):
        """A card store writes a placeholder as readily as it writes nothing; only the
        empty string counted, so a placeholder drew a chip naming a department "—"."""
        r = run_js("""
        console.log(JSON.stringify({dash: dchip({dept:'—'}, true), blank: dchip({dept:''}, true),
                                    real: dchip({dept:'Ops'}, true)}));
        """)
        self.assertEqual(r["dash"], r["blank"])
        self.assertIn("未派", r["dash"])
        self.assertIn("Ops", r["real"])

    def test_the_task_header_states_the_choice_and_menus_hold_the_rest(self):
        """Notion's view controls: the header states the current lane + count and the
        sort; alternatives live in a popover. Aggregates pick alone; the value lanes
        are checkboxes that UNION, and the menu stays open while they tick them."""
        r = run_js("""
        TASKS = [{label:'#1', status:'doing'}, {label:'#2', status:'todo'},
                 {label:'#3', status:'done'}];
        drawTasks();
        const flat = document.getElementById('filters').innerHTML;
        fmenu('fmenu');                       // open the lane menu
        tfToggle('doing'); tfToggle('todo');  // tick two lanes
        const multi = document.getElementById('filters').innerHTML;
        const shown = TSHOWN.map(t=>t.label);
        tfToggle('doing'); tfToggle('todo');  // untick both → falls back to In flight
        const back = document.getElementById('filters').innerHTML;
        console.log(JSON.stringify({flat, multi, shown, back}));
        """)
        self.assertIn("In flight", r["flat"])             # the current lane, stated
        self.assertIn("排序", r["flat"])
        self.assertNotIn("class='f ", r["flat"])          # the flat strip is gone
        self.assertNotIn("fmenu open", r["flat"])         # menus start closed
        for alt in ("Doing", "Todo", "Done", "Everything", "停滞最久"):
            self.assertIn(alt, r["flat"])                 # alternatives live in the menus
        self.assertIn("Doing, Todo", r["multi"])          # the face names the selection
        self.assertIn("fmenu open", r["multi"])           # ticking kept the menu open
        self.assertEqual(sorted(r["shown"]), ["#1", "#2"])  # union of the two lanes
        self.assertIn("In flight", r["back"])             # an emptied set falls back

    def test_the_chip_wears_the_dept_and_the_seats_ceo_given_nickname(self):
        """The handle's trailing number is the seat's card, not the department: the face
        strips it, and the number keys the CEO-given 花名 out of the spawn record — by
        the handle written on the card, or by dept plus the card's own number."""
        r = run_js("""
        NICKS = {'Frontend-1099': {nickname:'Lisa'}, 'Ops-376': {nickname:'Eric'}};
        console.log(JSON.stringify({
          joined: dchip({dept:'Frontend', label:'#1099'}, true),
          handle: dchip({dept:'Ops-376'}, true),
          plain:  dchip({dept:'Ops'}, true),
          bare:   dchip({dept:'Frontend', label:'#1101'}, true)}));
        """)
        self.assertIn("Frontend · Lisa", r["joined"])
        self.assertIn("Ops · Eric", r["handle"])
        self.assertNotIn("376", r["handle"].split("title=")[1].split(">")[1],
                         "the card number never reaches the face")
        self.assertIn("Frontend", r["bare"])
        self.assertNotIn("Lisa", r["bare"])
        hue = lambda chip: re.search(r"--dh:(\d+)", chip).group(1)
        self.assertEqual(hue(r["handle"]), hue(r["plain"]),
                         "one dept, one colour, however many numbered seats")

    def test_an_unknown_filter_falls_back_instead_of_blanking(self):
        r = run_js(DESK_JS + """
        seed([], [], [], []);
        DFILTER='nonesuch';
        const h = deskList(DESKDATA);
        console.log(JSON.stringify({len: h.length, empty: h.includes('colempty')}));
        """)
        self.assertTrue(r["empty"])


INFO_JS = """
const I1 = {id:'CEO-1', dept:'CEO', kind:'info', status:'open',
            created:'2026-07-27T09:00', updated:'2026-07-27T09:00', text:'an fyi'};
DESKDATA = {
  T:{list:[], byId:{}}, needs:[], info:[I1], parked:[], hist:[],
  shipped:[], shipLine:x=>x, lastAnswered:'',
  work:{doing:[], review:[], merge:[], blocked:[], todo:[]},
};
DFILTER = 'desk';
"""


@unittest.skipIf(not NODE, "node not available")
class ReadTick(unittest.TestCase):
    """The tick archives on THE BOSS'S side: it applies at the click and tells nobody.

    It has been two other things. First it folded the row the instant the box was clicked,
    so the item vanished under its own tick and read as lost. Then it staged into the
    basket and rode out with the next Send as "N marked read" — a 已读回执 asking the
    reader to do nothing, which they cut (2026-08-03): "点击ask才发消息，已读就是我这边
    archive了的行为". What is left is `archive()`: no receipt, no Send, no staging."""

    def test_the_tick_archives_at_the_click_and_sends_no_receipt(self):
        r = run_js(INFO_JS + """
        archive('CEO-1', true);
        console.log(JSON.stringify({
          reads: POSTS.filter(p=>p.url==='/read').map(p=>p.body),
          acks: POSTS.filter(p=>p.url==='/basket').map(p=>p.body),
          staged: BASKET.size,
        }));
        """)
        self.assertEqual(r["reads"], [{"id": "CEO-1", "read": True}],
                         "archiving applies at the click, not at the next Send")
        self.assertEqual(r["staged"], 0, "nothing is staged — there is no receipt to send")
        self.assertEqual([a["text"] for a in r["acks"]], [""],
                         "the only /basket write clears a legacy staged ack")

    def test_an_untick_brings_it_back_out_of_history(self):
        """Untick needs no confirm, so it has to be exactly reversible."""
        r = run_js(INFO_JS + """
        archive('CEO-1', true);
        archive('CEO-1', false);
        console.log(JSON.stringify({
          reads: POSTS.filter(p=>p.url==='/read').map(p=>p.body),
          staged: BASKET.size,
        }));
        """)
        self.assertEqual(r["reads"], [{"id": "CEO-1", "read": True},
                                      {"id": "CEO-1", "read": False}])
        self.assertEqual(r["staged"], 0)

    def test_archiving_drops_a_staged_answer_for_that_item(self):
        """The basket holds one entry per item. Archiving is a decision not to answer, so
        it must take the staged answer with it rather than leave it to ride out at Send."""
        r = run_js(INFO_JS + """
        openCompose('CEO-1','ask');
        document.getElementById('ctext').value = 'which one?';
        stageCompose();
        const before = BASKET.size;
        archive('CEO-1', true);
        console.log(JSON.stringify({before, after: BASKET.size}));
        """)
        self.assertEqual(r["before"], 1)
        self.assertEqual(r["after"], 0)


COMPOSE_JS = """
const E1 = {id:'CEO-1', dept:'CEO', kind:'decide', status:'open',
            created:'2026-07-27T09:00', updated:'2026-07-27T09:00',
            text:'Sign it as target, or treat it as a gap? :: the long detail'};
const E2 = {id:'CEO-2', dept:'CEO', kind:'decide', status:'open',
            created:'2026-07-27T09:00', updated:'2026-07-27T09:00', text:'Second question'};
DESKDATA = {
  T:{list:[], byId:{}}, needs:[E1, E2], info:[], parked:[], hist:[],
  shipped:[], shipLine:x=>x, lastAnswered:'',
  work:{doing:[], review:[], merge:[], blocked:[], todo:[]},
};
DFILTER = 'desk';
// "Type" into the box the render just produced, the way a keystroke would.
function type(s){ const t = document.getElementById('ctext'); t.value = s; return t; }
const boxOpenOn = () => {
  const h = document.getElementById('desklist').innerHTML;
  const m = /data-k="([^"]+)"(?:(?!data-k=)[\\s\\S])*?id='ctext'/.exec(h);
  return m ? m[1] : null;
};
"""


@unittest.skipIf(not NODE, "node not available")
class Composer(unittest.TestCase):
    """The reply box. It lives INSIDE the row it answers — a bar fixed to the foot of
    the window is a chat composer, which is the wrong shape for replying to one item in
    a list: it covered its own subject, and under zoom it stranded itself away from it."""

    def test_the_box_renders_inside_the_row_it_answers(self):
        r = run_js(COMPOSE_JS + """
        openCompose('CEO-1','reply');
        console.log(JSON.stringify({on: boxOpenOn(), hasBox: /rcompose/.test(document.getElementById('desklist').innerHTML)}));
        """)
        self.assertEqual(r["on"], "CEO-1")
        self.assertTrue(r["hasBox"])

    def test_only_the_targeted_row_carries_a_box(self):
        """Two textareas would mean two elements sharing one id, and stageCompose would
        read whichever the browser handed back first."""
        r = run_js(COMPOSE_JS + """
        openCompose('CEO-2','reply');
        const h = document.getElementById('desklist').innerHTML;
        console.log(JSON.stringify({boxes: (h.match(/rcompose/g)||[]).length, on: boxOpenOn()}));
        """)
        self.assertEqual(r["boxes"], 1)
        self.assertEqual(r["on"], "CEO-2")

    def test_the_row_being_answered_is_forced_open(self):
        """Its collapsed face is one clamped line; the box would hang off an item whose
        text is cut mid-sentence."""
        r = run_js(COMPOSE_JS + r"""
        openCompose('CEO-1','reply');
        const h = document.getElementById('desklist').innerHTML;
        // Match the class LIST, not its order: the row also carries lane and kind
        // classes, and pinning `x` to one position tested the stylesheet's word order.
        const m = /class="([^"]*)"[^>]*data-k="CEO-1"/.exec(h);
        console.log(JSON.stringify({expanded: !!m && m[1].split(/\s+/).includes('x')}));
        """)
        self.assertTrue(r["expanded"])

    def test_a_click_in_the_box_does_not_collapse_the_row(self):
        """The row toggles on click and the box is inside it, so without this every
        click into the textarea would fold the answer away."""
        r = run_js(COMPOSE_JS + r"""
        openCompose('CEO-1','reply');
        console.log(JSON.stringify({stops: /rcompose' onclick='event.stopPropagation\(\)'/.test(
          document.getElementById('desklist').innerHTML)}));
        """)
        self.assertTrue(r["stops"])

    def test_an_unstaged_draft_survives_cancel(self):
        """Cancel used to destroy typing — the one thing a compose box must never do."""
        r = run_js(COMPOSE_JS + """
        openCompose('CEO-1','reply'); type('half an answer'); closeCompose();
        openCompose('CEO-1','reply');
        console.log(JSON.stringify({restored: document.getElementById('ctext').value}));
        """)
        self.assertEqual(r["restored"], "half an answer")

    def test_switching_to_another_ask_keeps_the_first_draft(self):
        """A mis-click on another row's Reply is the likeliest way to lose an answer."""
        r = run_js(COMPOSE_JS + """
        openCompose('CEO-1','reply'); type('draft A');
        openCompose('CEO-2','reply');
        const blank = document.getElementById('ctext').value;
        openCompose('CEO-1','reply');
        console.log(JSON.stringify({blank, back: document.getElementById('ctext').value}));
        """)
        self.assertEqual(r["blank"], "", "the second ask starts empty")
        self.assertEqual(r["back"], "draft A")

    def test_typing_survives_a_redraw_under_her_hands(self):
        """The box is part of the list, so any poll that changes the board rebuilds the
        element they are typing into. The text has to come back with it."""
        r = run_js(COMPOSE_JS + """
        openCompose('CEO-1','reply'); type('mid-sentence when the board moved');
        drawDesk();                       // what an incoming board change triggers
        console.log(JSON.stringify({kept: document.getElementById('ctext').value, on: boxOpenOn()}));
        """)
        self.assertEqual(r["kept"], "mid-sentence when the board moved")
        self.assertEqual(r["on"], "CEO-1")

    def test_editing_an_already_staged_answer_survives_a_redraw(self):
        """The earlier draft rule skipped anything already in the basket, so a redraw
        mid-edit silently reverted the edit to the staged text."""
        r = run_js(COMPOSE_JS + """
        openCompose('CEO-1','reply'); type('first version'); stageCompose();
        openCompose('CEO-1','reply'); type('first version, revised');
        drawDesk();
        console.log(JSON.stringify({kept: document.getElementById('ctext').value,
                                    staged: BASKET.get('CEO-1').text}));
        """)
        self.assertEqual(r["kept"], "first version, revised")
        self.assertEqual(r["staged"], "first version", "not staged until they stage it")

    def test_staging_consumes_the_draft(self):
        r = run_js(COMPOSE_JS + """
        openCompose('CEO-1','reply'); type('my decision'); stageCompose();
        console.log(JSON.stringify({staged: BASKET.get('CEO-1').text,
                                    draft: DRAFTS.has('CEO-1'), on: boxOpenOn()}));
        """)
        self.assertEqual(r["staged"], "my decision")
        self.assertFalse(r["draft"])
        self.assertIsNone(r["on"], "the box closes when the answer is staged")

    def test_an_emptied_box_unstages_rather_than_staging_blank(self):
        r = run_js(COMPOSE_JS + """
        openCompose('CEO-1','reply'); type('x'); stageCompose();
        openCompose('CEO-1','reply'); type('   '); stageCompose();
        console.log(JSON.stringify({has: BASKET.has('CEO-1')}));
        """)
        self.assertFalse(r["has"])

    def test_stage_and_send_stages_first_then_delivers(self):
        """Delivering before staging would drop the answer they just wrote."""
        r = run_js(COMPOSE_JS + """
        POSTS.length = 0;
        openCompose('CEO-1','reply'); type('ship it'); stageCompose(true);
        const urls = POSTS.map(p=>p.url);
        console.log(JSON.stringify({urls, basketBody: POSTS.find(p=>p.url==='/basket').body}));
        """)
        self.assertIn("/basket", r["urls"])
        self.assertIn("/send", r["urls"])
        self.assertLess(r["urls"].index("/basket"), r["urls"].index("/send"))
        self.assertEqual(r["basketBody"]["text"], "ship it")

    def test_the_send_button_counts_the_whole_batch(self):
        """Sending flushes everything staged, not just this row. Say the real number."""
        r = run_js(COMPOSE_JS + """
        const label = () => (/id='csend'[^>]*>([^<]*)</.exec(
          document.getElementById('desklist').innerHTML)||[])[1];
        openCompose('CEO-1','reply'); type('a'); stageCompose();
        openCompose('CEO-2','reply');
        const two = label();
        type('b'); stageCompose();
        openCompose('CEO-1','reply');
        console.log(JSON.stringify({two, editingStaged: label()}));
        """)
        self.assertEqual(r["two"], "Stage &amp; send all 2")
        self.assertEqual(r["editingStaged"], "Stage &amp; send all 2",
                         "re-editing a staged answer must not inflate the count")

    def test_the_staged_tray_reserves_only_its_own_height(self):
        """The tray is the one fixed bar left. The compose box is in the flow now, so
        the page must not reserve room for it."""
        r = run_js(COMPOSE_JS + """
        const pad = () => document.body.style.paddingBottom;
        const before = pad();
        openCompose('CEO-1','reply');
        const composing = pad();
        type('a'); stageCompose();
        console.log(JSON.stringify({before, composing, staged: pad()}));
        """)
        self.assertEqual(r["before"], "")
        self.assertEqual(r["composing"], "", "an inline box needs no reserved space")
        self.assertTrue(r["staged"].endswith("px"), "the tray does")


STATE_JS = """
// A payload the panel's OWN tick() parses. The desk ordering rule lives inside tick, so a
// test that sorted its own copy would pass forever while the board drifted underneath.
function serve(state){
  globalThis.fetch = function(url, opt){
    if(String(url).startsWith('/state.json'))
      return Promise.resolve({json:()=>Promise.resolve(state)});
    POSTS.push({url, body: opt && opt.body ? JSON.parse(opt.body) : null});
    return Promise.resolve({json:()=>Promise.resolve({})});
  };
}
const ask = (id, created) => ({id, dept:'CEO', kind:'decide', status:'open',
                               text:'ask '+id, created, updated:created});
const fyi = (id, created) => ({id, dept:'CEO', kind:'info', status:'open',
                               text:'fyi '+id, created, updated:created});
const STATE = {project:'t', taskboard:{tasks:[], shipped:[]}, entries:[
  ask('CEO-1','2026-07-28T09:00'), ask('CEO-2','2026-07-29T09:00'), ask('CEO-3','2026-07-30T09:00'),
  fyi('CEO-4','2026-07-28T10:00'), fyi('CEO-5','2026-07-30T10:00'),
]};
"""


@unittest.skipIf(not NODE, "node not available")
class DeskClock(unittest.TestCase):
    """Order and time on the desk — both of them things the Boss reads off the top of the page.

    Needs-you used to drain oldest-first, so the ask they had just watched arrive landed at
    the bottom of the lane. And every time on the page is an age derived at render, while a
    render only happens when the data changes: on a quiet board the ages froze while the
    masthead reprinted the wall clock every 1.5s, so the page looked live and read stale:
    the one number visibly changing was the one with no data behind it."""

    def test_needs_you_reads_newest_first(self):
        r = run_js(STATE_JS + """
        serve(STATE); await tick();
        console.log(JSON.stringify({needs: DESKDATA.needs.map(e=>e.id),
                                    info: DESKDATA.info.map(e=>e.id), fails}));
        """)
        self.assertEqual(r["fails"], 0, "tick threw before it finished the desk")
        self.assertEqual(r["needs"], ["CEO-3", "CEO-2", "CEO-1"])
        self.assertEqual(r["info"], ["CEO-5", "CEO-4"], "the update feed leads with the freshest too")

    def test_the_stamp_names_the_last_content_change_not_the_poll(self):
        """It printed `new Date()` on every poll, so it claimed "updated <now>" forty times
        a minute on a board where nothing had moved since breakfast."""
        r = run_js(STATE_JS + """
        serve(STATE); await tick();
        lastChange = new Date(2020, 0, 1, 3, 4, 5);     // pretend the last change was long ago
        const marker = lastChange.toLocaleTimeString();
        await tick();                                    // same payload: nothing changed
        const st = document.getElementById('stamp');
        const quiet = st.textContent, title = st.title;
        serve({...STATE, entries: STATE.entries.concat([ask('CEO-9','2026-07-31T09:00')])});
        await tick();                                    // the data really moved
        console.log(JSON.stringify({marker, quiet, title, moved: st.textContent}));
        """)
        self.assertEqual(r["quiet"], "last change " + r["marker"],
                         "a poll that changed nothing must not restamp the board")
        self.assertNotEqual(r["moved"], r["quiet"], "a real change must restamp it")
        self.assertIn("last checked", r["title"], "liveness still has to be provable")

    def test_an_age_reticks_in_place_without_a_redraw(self):
        """In place is the whole point: a redraw would collapse whatever they had expanded
        and destroy the box they are typing into, which is why the board only redraws on a
        data change in the first place."""
        r = run_js("""
        const mkEl = (ds) => ({dataset: ds, textContent: 'stale',
          classList:{ _s:new Set(), add(x){this._s.add(x)}, remove(x){this._s.delete(x)},
            toggle(x,on){ on?this._s.add(x):this._s.delete(x) }, contains(x){return this._s.has(x)} }});
        const iso = mins => new Date(Date.now() - mins*60000).toISOString();
        const row  = mkEl({ts: iso(45)});
        const line = mkEl({ts: iso(45), pre:'last answered ', post:' ago'});
        const chip = mkEl({since: iso(5*1440), where:'in 审查'});
        chip.classList.add('age');
        const lane = mkEl({since: iso(90)});
        const laneOld = mkEl({since: iso(5*1440)});   // old enough to colour, if it were a chip
        document.querySelectorAll = sel => sel === '[data-ts]' ? [row, line] : [chip, lane, laneOld];
        retick();
        console.log(JSON.stringify({row: row.textContent, line: line.textContent,
                                    chip: chip.textContent, stale: chip.classList.contains('stale'),
                                    lane: lane.textContent, laneStale: lane.classList.contains('stale'),
                                    laneOld: laneOld.textContent, oldStale: laneOld.classList.contains('stale')}));
        """)
        self.assertEqual(r["row"], "45m")
        self.assertEqual(r["line"], "last answered 45m ago", "a framed line keeps its frame")
        self.assertEqual(r["chip"], "5d in 审查", "a stage chip keeps the stage it names")
        self.assertTrue(r["stale"], "5 days in one stage is still stale after a retick")
        self.assertEqual(r["lane"], "2h")
        self.assertFalse(r["laneStale"])
        self.assertEqual(r["laneOld"], "5d")
        self.assertFalse(r["oldStale"], "only the card chip is coloured by staleness — .rage.stale is a dead class")

    def test_a_quiet_poll_still_reticks(self):
        """The poll that changes nothing is the ONLY one that matters here — the one that
        redraws re-derives every age on its way past."""
        r = run_js(STATE_JS + """
        serve(STATE); await tick();                 // first poll: a full render
        const el = {dataset:{ts: new Date(Date.now()-45*60000).toISOString()}, textContent:'—',
                    classList:{contains:()=>false, toggle(){}}};
        document.querySelectorAll = sel => sel === '[data-ts]' ? [el] : [];
        await tick();                                // same payload: no redraw at all
        console.log(JSON.stringify({text: el.textContent, fails}));
        """)
        self.assertEqual(r["fails"], 0)
        self.assertEqual(r["text"], "45m", "a poll with no data change must still move the clock")

    def test_a_drawn_row_carries_the_timestamp_the_reticker_needs(self):
        """Without the stamp on the element there is nothing to re-derive from, and the
        reticker degrades to a no-op that no assertion above would notice."""
        r = run_js(DESK_JS + """
        seed([mk('CEO-9','decide','answer me')], [], [], []);
        DFILTER='desk';
        const h = deskList(DESKDATA);
        const t = {label:'#1', name:'x', status:'todo', l2:'pass',
                   since: new Date(Date.now()-19*3600*1000).toISOString().slice(0,16)};
        console.log(JSON.stringify({row: /data-ts="2026-07-27T09:00"/.test(h),
                                    lane: /data-since="/.test(deskTask(t)),
                                    card: /data-since="/.test(pCard(t,0))}));
        """)
        self.assertTrue(r["row"], "a desk row must carry its own created time")
        self.assertTrue(r["lane"], "a Work lane row must carry its since")
        self.assertTrue(r["card"], "a task card chip must carry its since")

    def test_the_clear_line_dates_itself_from_a_timestamp(self):
        """It used to be baked as a phrase at render — "last answered 5m ago" then sat
        there saying 5m for the rest of the morning, on the one view that appears when
        nothing else is moving."""
        r = run_js(DESK_JS + """
        seed([], [], [], []);
        DESKDATA.lastAnsweredTs = new Date(Date.now() - 45*60000).toISOString();
        DFILTER='desk';
        const h = deskList(DESKDATA);
        DESKDATA.lastAnsweredTs = '';
        console.log(JSON.stringify({h, none: deskList(DESKDATA)}));
        """)
        self.assertIn("last answered 45m ago", r["h"])
        self.assertRegex(r["h"], r"""data-pre="last answered " data-post=" ago\"""")
        self.assertIn("dclear", r["none"], "no answer on file must not break the clear line")
        self.assertNotIn("last answered", r["none"])


class Markup(unittest.TestCase):
    """Structural guards for the parts that are CSS, not logic."""

    def test_the_dashboard_is_a_rail_and_a_list(self):
        p = board.PAGE
        self.assertIn("id='rail'", p)
        self.assertIn("id='desklist'", p)

    def test_the_retired_tiles_and_glance_band_are_gone(self):
        """They are what they saw first: four numbers, three of them zero."""
        p = board.PAGE
        self.assertNotIn("id='monitor'", p)
        self.assertNotIn("id='glance'", p)

    def test_the_dot_has_a_default_colour(self):
        """Enumerating kinds failed silently: `ask`, `decide` and `sign` are all live in
        the store and none had a class, so each drew a blank where its marker belongs.
        The BASE must carry a colour, in both themes, or the next new kind repeats it."""
        p = board.PAGE
        base = re.search(r"\.dot2 \{[^}]*\}", p, re.S)
        self.assertIsNotNone(base)
        self.assertIn("background", base.group(0))
        self.assertRegex(p, r"html\.dark \.dot2 \{[^}]*background")

    def test_the_source_of_truth_band_collapses(self):
        """At full height it pushed the first actionable thing below the fold every visit."""
        self.assertIn("data-k='sot'", board.PAGE)

    def test_the_desk_row_is_deep_linkable(self):
        """Parity with ?tab= and ?task= — and the only way a headless screenshot reaches
        a lane that sits behind a click."""
        self.assertIn("get('desk')", board.PAGE)


if __name__ == "__main__":
    unittest.main(verbosity=1)


CONVO_JS = """
const A1 = {id:'CEO-1', dept:'CEO', kind:'decide', status:'open',
            created:'2026-07-27T09:00', updated:'2026-07-27T09:00', text:'first :: detail'};
const A2 = {id:'CEO-2', dept:'CEO', kind:'decide', status:'open',
            created:'2026-07-27T10:00', updated:'2026-07-27T10:00', text:'second :: detail'};
DESKDATA = { T:{list:[], byId:{}}, all:[A1,A2], needs:[A1,A2], info:[], parked:[], hist:[],
  shipped:[], shipLine:x=>x, lastAnswered:'',
  work:{doing:[], review:[], merge:[], blocked:[], todo:[]} };
DFILTER = 'convo'; CONVO = 'CEO';
TARGET = {ok:true, title:'\\u2802 Retrieve exact tool call', tty:'/dev/ttys004'};
drawComposer(true);                       // first build — the box now exists
const box = document.getElementById('ctext');
box.value = 'half a sentence';
"""


@unittest.skipIf(not NODE, "node not available")
class TheBoxSheIsTypingIntoIsNeverRebuilt(unittest.TestCase):
    """A new message must never disturb the box the Boss is typing in — not the caret,
    not the text, not the composer. Two guards used to stand between their keyboard and a rebuild —
    an IME flag and a signature — and both leaked. The signature carried the destination
    pane's iTerm title, which for a working Claude Code pane is its status line with an
    ANIMATING braille spinner, so it changed on every poll and rebuilt the box several
    times a second whether or not anything had arrived. The guards are not the fix; not
    rebuilding is."""

    def test_a_spinning_destination_pane_is_not_a_change(self):
        r = run_js(CONVO_JS + """
        const a = composerSignature();
        TARGET = {ok:true, title:'\\u2810 Retrieve exact tool call', tty:'/dev/ttys004'};
        const b = composerSignature();
        TARGET = {ok:false, why:'pane is gone'};
        const c = composerSignature();
        console.log(JSON.stringify({sameFrame: a===b, realChange: a!==c}));
        """)
        self.assertTrue(r["sameFrame"], "two spinner frames of one pane read as a change")
        self.assertTrue(r["realChange"], "a target that actually broke must still redraw")

    def test_the_textarea_survives_a_redraw_that_changes_everything_around_it(self):
        r = run_js(CONVO_JS + """
        BASKET.set('CEO-2', {kind:'reply', text:'staged'});   // moves the signature
        TARGET = {ok:false, why:'pane is gone'};              // and again
        drawComposer();
        const after = document.getElementById('ctext');
        console.log(JSON.stringify({
          sameNode: after === box,
          text: after.value,
          hint: (COMPOSER_KIDS && COMPOSER_KIDS['.chint'].innerHTML) || '',
        }));
        """)
        self.assertTrue(r["sameNode"], "the element they was typing into was replaced")
        self.assertEqual(r["text"], "half a sentence", "their typing did not survive")
        self.assertIn("pane is gone", r["hint"], "the chrome around it still updates")

    def test_a_quiet_poll_touches_nothing(self):
        r = run_js(CONVO_JS + """
        const sig0 = composerSig;
        drawComposer(); drawComposer(); drawComposer();
        const after = document.getElementById('ctext');
        console.log(JSON.stringify({sameNode: after === box, text: after.value,
                                    sigHeld: composerSig === sig0}));
        """)
        self.assertTrue(r["sameNode"])
        self.assertEqual(r["text"], "half a sentence")
        self.assertTrue(r["sigHeld"])

    def test_binding_the_box_to_another_ask_does_swap_the_draft(self):
        """The one case where the value SHOULD change: they click Reply on a different
        item, so the box now belongs to that item and carries its draft."""
        r = run_js(CONVO_JS + """
        DRAFTS.set('CEO-2', 'the other draft');
        cTarget = {id:'CEO-2', kind:'reply'};
        drawComposer();
        const after = document.getElementById('ctext');
        console.log(JSON.stringify({sameNode: after === box, text: after.value,
                                    boundTo: after.dataset.for}));
        """)
        self.assertTrue(r["sameNode"], "even a rebind must not replace the element")
        self.assertEqual(r["text"], "the other draft")
        self.assertEqual(r["boundTo"], "CEO-2")


@unittest.skipIf(not NODE, "node not available")
class AnUnfinishedSentenceSurvivesAReload(unittest.TestCase):
    """Staged answers have survived a restart since the day a page of them was lost, but
    the draft still being typed lived only in memory — so the automatic reload a plugin
    update triggers took whatever was in the box. Both halves belong to them."""

    def test_typing_is_written_to_this_browser_on_every_keystroke(self):
        r = run_js(CONVO_JS + """
        cTarget = {id:'CEO-1', kind:'reply'};
        drawComposer(true);
        document.getElementById('ctext').dataset = {for:'CEO-1'};
        document.getElementById('ctext').value = 'half a sen';
        saveDraft();
        console.log(JSON.stringify({stored: localStorage.getItem('board-drafts')}));
        """)
        self.assertIn("half a sen", r["stored"] or "")

    def test_it_is_read_back_and_never_clobbers_a_live_one(self):
        r = run_js("""
        localStorage.setItem('board-drafts',
          JSON.stringify({d:[['CEO-1','from the last page load']], f:'free text'}));
        DRAFTS.set('CEO-1','typed since');    // a live draft wins over the stored one
        draftsLoad();
        console.log(JSON.stringify({live: DRAFTS.get('CEO-1'), restored: DRAFTS.size}));
        """)
        self.assertEqual(r["live"], "typed since")

    def test_sending_clears_the_stored_draft_too(self):
        """Otherwise a reload after a send puts the delivered words back in the box."""
        r = run_js(CONVO_JS + """
        cTarget = {id:'CEO-1', kind:'reply'};
        drawComposer(true);
        const ta = document.getElementById('ctext');
        ta.dataset = {for:'CEO-1'}; ta.value = 'the answer'; saveDraft();
        const before = localStorage.getItem('board-drafts');
        commitCompose(false);
        console.log(JSON.stringify({before, after: localStorage.getItem('board-drafts')}));
        """)
        self.assertIn("the answer", r["before"] or "")
        self.assertNotIn("the answer", r["after"] or "")


SENT_JS = """
const A1 = {id:'BIO-20', dept:'Backend-IO', kind:'decide', status:'resolved',
            created:'2026-08-05T10:30', updated:'2026-08-05T10:40',
            sum:'找到记录，字段有出入', text:'两案 A/B :: detail'};
const A2 = {id:'BIO-21', dept:'Backend-IO', kind:'info', status:'open',
            created:'2026-08-05T10:52', updated:'2026-08-05T10:52', text:'图例字节收讫 :: detail'};
DESKDATA = { T:{list:[], byId:{}}, all:[A1,A2], needs:[], info:[A2], parked:[], hist:[],
  shipped:[], shipLine:x=>x, lastAnswered:'',
  work:{doing:[], review:[], merge:[], blocked:[], todo:[]} };
DFILTER = 'convo'; CONVO = 'Backend-IO';
"""


@unittest.skipIf(not NODE, "node not available")
class EverythingSheSendsIsInTheThread(unittest.TestCase):
    """Reply, ask and plain message are three ways of sending, and all three belong in
    the thread. Only a REPLY was ever kept — as the item's `sum` — so a question the Boss asked about an item, and
    a message they wrote to a department, went to the session and left nothing behind: the
    thread showed the item, then the session's answer, with the words they wrote to provoke
    it missing from between them."""

    def test_an_ask_she_sent_is_drawn(self):
        r = run_js(SENT_JS + """
        SENT = [{id:'BIO-21', dept:'Backend-IO', kind:'ask',
                 text:'「有出入」只作降级条目徽章下的细节措辞', at:'2026-08-05T10:55'}];
        const h = convoThread(DESKDATA);
        console.log(JSON.stringify({drawn: h.includes('只作降级条目徽章下的细节措辞'),
                                    quoted: h.includes('↩ BIO-21'),
                                    onHerSide: /class='msg out'[\\s\\S]*只作降级/.test(h)}));
        """)
        self.assertTrue(r["drawn"], "the question the Boss asked is not on the board at all")
        self.assertTrue(r["quoted"], "it must say which item the Boss asked about")
        self.assertTrue(r["onHerSide"])

    def test_a_message_bound_to_nothing_is_drawn_in_its_own_right(self):
        r = run_js(SENT_JS + """
        SENT = [{id:'', dept:'Backend-IO', kind:'msg',
                 text:'这个是什么？', at:'2026-08-05T10:58'}];
        const h = convoThread(DESKDATA);
        console.log(JSON.stringify({drawn: h.includes('这个是什么？'),
                                    quotesNothing: !/↩ BIO/.test(h.split('这个是什么？')[0].slice(-400))}));
        """)
        self.assertTrue(r["drawn"], "a message typed with nothing bound vanished")
        self.assertTrue(r["quotesNothing"], "it answers no item, so it quotes none")

    def test_several_things_she_said_about_one_item_keep_their_order(self):
        r = run_js(SENT_JS + """
        SENT = [{id:'BIO-20', dept:'Backend-IO', kind:'reply', text:'FIRST', at:'2026-08-05T10:40'},
                {id:'BIO-20', dept:'Backend-IO', kind:'ask',   text:'SECOND', at:'2026-08-05T10:45'}];
        const h = convoThread(DESKDATA);
        console.log(JSON.stringify({order: h.indexOf('FIRST') < h.indexOf('SECOND'),
                                    both: h.includes('FIRST') && h.includes('SECOND')}));
        """)
        self.assertTrue(r["both"])
        self.assertTrue(r["order"])

    def test_a_message_lands_in_the_thread_by_its_clock(self):
        r = run_js(SENT_JS + """
        SENT = [{id:'', dept:'Backend-IO', kind:'msg', text:'BETWEEN', at:'2026-08-05T10:45'}];
        const h = convoThread(DESKDATA);
        console.log(JSON.stringify({after20: h.indexOf('BETWEEN') > h.indexOf('BIO-20'),
                                    before21: h.indexOf('BETWEEN') < h.indexOf('BIO-21')}));
        """)
        self.assertTrue(r["after20"])
        self.assertTrue(r["before21"], "it was sent before that item arrived")

    def test_another_conversation_never_borrows_her_words(self):
        r = run_js(SENT_JS + """
        SENT = [{id:'', dept:'CEO', kind:'msg', text:'FOR THE CEO', at:'2026-08-05T10:55'}];
        console.log(JSON.stringify({leaked: convoThread(DESKDATA).includes('FOR THE CEO')}));
        """)
        self.assertFalse(r["leaked"])

    def test_history_with_no_send_log_still_shows_her_reply(self):
        """Everything answered before the log existed lives in `sum` and must keep drawing."""
        r = run_js(SENT_JS + """
        SENT = [];
        console.log(JSON.stringify({legacy: convoThread(DESKDATA).includes('找到记录，字段有出入')}));
        """)
        self.assertTrue(r["legacy"])

    def test_a_logged_reply_does_not_draw_twice(self):
        r = run_js(SENT_JS + """
        SENT = [{id:'BIO-20', dept:'Backend-IO', kind:'reply',
                 text:'找到记录，字段有出入', at:'2026-08-05T10:40'}];
        const h = convoThread(DESKDATA);
        console.log(JSON.stringify({n: h.split('找到记录，字段有出入').length - 1}));
        """)
        self.assertEqual(r["n"], 1, "the log and the legacy field both drew it")


@unittest.skipIf(not NODE, "node not available")
class OpeningAConversationLandsOnTheNewest(unittest.TestCase):
    """`.list.thread` sets `scroll-behavior: smooth`, so assigning scrollTop ANIMATED the
    jump: opening a conversation crawled the whole thread from the oldest message to the
    newest, which is the scrolling the jump exists to save them (2026-08-05)."""

    def test_the_jump_is_instant_and_re_applied_after_layout(self):
        src = board.PAGE
        i = src.index("if(convoJump || atEnd){")
        seg = src[i:i + 900]
        self.assertIn("behavior: 'auto'", seg,
                      "the stylesheet animates a plain scrollTop assignment")
        self.assertIn("requestAnimationFrame(bottom)", seg,
                      "the thread is still growing when this runs")

    def test_it_goes_to_the_bottom_when_a_conversation_is_opened(self):
        r = run_js(SENT_JS + """
        SENT = [];
        const list = document.getElementById('desklist');
        list.scrollHeight = 5000; list.clientHeight = 400; list.scrollTop = 0;
        const seen = [];
        list.scrollTo = (o)=>{ seen.push(o); list.scrollTop = o.top; };
        convoJump = true;
        drawDesk();
        console.log(JSON.stringify({calls: seen, top: list.scrollTop, jumpCleared: convoJump===false}));
        """)
        self.assertTrue(r["calls"], "it never asked to scroll at all")
        self.assertEqual(r["calls"][0]["behavior"], "auto")
        self.assertEqual(r["top"], 5000)
        self.assertTrue(r["jumpCleared"], "or every later poll would yank their to the bottom")

    def test_a_poll_redraw_keeps_her_where_she_was_reading(self):
        r = run_js(SENT_JS + """
        SENT = [];
        const list = document.getElementById('desklist');
        list.scrollHeight = 5000; list.clientHeight = 400; list.scrollTop = 1200;
        const seen = [];
        list.scrollTo = (o)=>{ seen.push(o); list.scrollTop = o.top; };
        convoJump = false;
        drawDesk();
        console.log(JSON.stringify({jumped: seen.length > 0, top: list.scrollTop}));
        """)
        self.assertFalse(r["jumped"], "a poll must never yank their out of what they are reading")
        self.assertEqual(r["top"], 1200)
