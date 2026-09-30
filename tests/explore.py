"""KeepWise exhaustive explorer.
Presses every control on every screen (depth 1, then everything that appears after it, depth 2),
then runs randomized sessions (taps, typing edge-case values, tab switches, reloads, resizes, theme).
After every action it checks invariants: no JS errors, no sideways scroll, tab bar pinned, no NaN/undefined
text, no native dialogs, every button named, reload keeps state. Dead buttons (nothing changes) are reported.
Run: python3 tests/explore.py [app.html] [--quick]"""
import asyncio, sys, os, json, random, tempfile, re, hashlib
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
QUICK = "--quick" in sys.argv
APP = os.path.abspath(args[0] if args else os.path.join(HERE, "..", "www", "index.html"))
TMP = tempfile.mkdtemp(); PAGE = os.path.join(TMP, "index.html")
body = open(APP).read()
open(PAGE, "w").write(body if body.lstrip().lower().startswith("<!doctype") else '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' + body)
URL = "file://" + PAGE
CSV = os.path.join(TMP, "s.csv")
open(CSV, "w").write("Date,Description,Amount\n2026-09-01,NETFLIX.COM,-15.49\n2026-09-03,SPOTIFY USA,-11.99\n2026-09-05,PAYROLL ACME,3200.00\n2026-09-07,SHELL OIL 123,-48.20\n2026-09-09,HULU 877,-17.99\n2026-10-01,NETFLIX.COM,-15.49\n")
VCF = os.path.join(TMP, "c.vcf")
open(VCF, "w").write("BEGIN:VCARD\nVERSION:3.0\nFN:Zed Quinn\nTEL:+15551234567\nEMAIL:zed@example.com\nEND:VCARD\n")
PNG = os.path.join(HERE, "..", "www", "icons", "favicon-64.png")

ISSUES = {}
def issue(kind, where, detail=""):
    k = (kind, where, detail[:160])
    if k not in ISSUES and os.environ.get("XLIVE"):
        with open(os.environ["XLIVE"], "a") as f: f.write(f"{kind} | {where[:170]} | {detail[:160]}\n")
    ISSUES[k] = ISSUES.get(k, 0) + 1

CLICKABLES = """(()=>{const out=[];const sel='button, a[href], [role=button], summary, input[type=checkbox], input[type=radio], select, label:has(input[type=file])';
document.querySelectorAll(sel).forEach(el=>{
  if(el.closest('[inert],[aria-hidden=true]'))return; if(el.tagName!=='SUMMARY'&&el.closest('details:not([open])'))return;
  const r=el.getBoundingClientRect(); const cs=getComputedStyle(el);
  if(!r.width||!r.height||cs.visibility==='hidden'||cs.display==='none'||el.disabled)return;
  const ds=Object.entries(el.dataset).map(([k,v])=>k+'='+v).join('&');
  const t=(el.getAttribute('aria-label')||el.title||el.textContent||el.value||'').trim().replace(/\\s+/g,' ').slice(0,40);
  out.push({key:el.tagName+'|'+(el.id||'')+'|'+ds+'|'+t, tag:el.tagName, href:el.getAttribute('href')||'', target:el.target||'', t, w:r.width, h:r.height, dl:el.hasAttribute('download')});
});return out})()"""

INVARIANTS = """(()=>{const p=[];const d=document.documentElement;
if(d.scrollWidth>innerWidth+1)p.push('sideways scroll '+d.scrollWidth+'>'+innerWidth);
const tb=document.getElementById('tabbar'); const app=document.getElementById('app')||document.body;
if(tb && !document.querySelector('.typing') && getComputedStyle(tb).display!=='none'){const b=tb.getBoundingClientRect().bottom; if(Math.abs(b-innerHeight)>1)p.push('tabbar not at bottom '+b+' vs '+innerHeight);}
const txt=(document.getElementById('view')||document.body).innerText;
for(const bad of ['NaN','undefined','Infinity','[object','null ',' null']){ if(txt.includes(bad)) p.push('text contains '+bad+': '+txt.slice(Math.max(0,txt.indexOf(bad)-40),txt.indexOf(bad)+30).replace(/\\n/g,' '));}
const ids={};document.querySelectorAll('[id]').forEach(e=>{ids[e.id]=(ids[e.id]||0)+1});Object.entries(ids).forEach(([k,v])=>{if(v>1)p.push('duplicate id '+k)});
document.querySelectorAll('button, a[href], input:not([type=hidden]), select, textarea').forEach(el=>{
  if(el.closest('[inert],[aria-hidden=true]'))return; const r=el.getBoundingClientRect(); if(!r.width)return;
  let name=(el.getAttribute('aria-label')||el.title||el.textContent||el.placeholder||'').trim();
  if(!name && el.id){const l=document.querySelector('label[for="'+el.id+'"]'); if(l)name=l.textContent.trim();}
  if(!name && el.closest('label'))name=el.closest('label').textContent.trim();
  if(!name && el.getAttribute('aria-labelledby'))name='x';
  if(!name && el.value && el.tagName==='SELECT')name='sel';
  if(!name)p.push('unnamed '+el.tagName+' '+(el.className||'')+' '+Object.keys(el.dataset).join(','));
});
return p})()"""

SNAP = "(()=>{const h=t=>{let x=0;for(let i=0;i<t.length;i++)x=(x*31+t.charCodeAt(i))|0;return x};const f=[...document.querySelectorAll('input,select,textarea')].map(e=>e.type==='checkbox'?e.checked:e.value).join('|');return h(document.body.innerHTML)+'|'+h(localStorage.getItem('keepwise-app-v1')||'')+'|'+h(f)+'|'+(document.activeElement&&document.activeElement.outerHTML.slice(0,80))+'|'+document.documentElement.getAttribute('data-theme')+'|'+(document.getElementById('main')||{}).scrollTop})()"

async def new_page(ctx, w=390, h=844, scheme="light"):
    pg = await ctx.new_page()
    await pg.set_viewport_size({"width": w, "height": h})
    pg.errs = []; pg.dialogs = []; pg.chooser = []
    pg.on("pageerror", lambda e: pg.errs.append("pageerror: " + str(e)[:200]))
    pg.on("console", lambda m: m.type == "error" and not any(s in m.text for s in ("net::", "ERR_", "fonts.g", "Failed to load resource")) and pg.errs.append("console: " + m.text[:200]))
    async def on_dialog(d): pg.dialogs.append(d.type + ": " + d.message[:80]); await d.dismiss()
    pg.on("dialog", lambda d: asyncio.ensure_future(on_dialog(d)))
    async def on_chooser(fc):
        pg.chooser.append(1)
        acc = (await fc.element.get_attribute("accept")) or ""
        f = VCF if "vcf" in acc or "vcard" in acc else PNG if "image" in acc else CSV
        try: await fc.set_files(f)
        except Exception as e: pg.errs.append("chooser " + str(e)[:80])
    pg.on("filechooser", lambda fc: asyncio.ensure_future(on_chooser(fc)))
    async def serve_vendor(route):
        name = route.request.url.rsplit("/", 1)[-1]; path = os.path.join(HERE, "vendor", name)
        if os.path.exists(path): await route.fulfill(path=path, content_type="application/javascript")
        else: await route.abort()
    await pg.route("https://cdnjs.cloudflare.com/**", serve_vendor)
    await pg.add_init_script("window.KEEPWISE_FIREBASE = {apiKey:'t',authDomain:'t.firebaseapp.com',projectId:'t'};")
    async def serve_fb(route):
        if route.request.url.endswith("firebase-app-compat.js"): await route.fulfill(path=os.path.join(HERE, "mock_firebase.js"), content_type="application/javascript")
        else: await route.fulfill(body="", content_type="application/javascript")
    await pg.route("https://cdn.jsdelivr.net/npm/firebase@*/**", serve_fb)
    await pg.route("https://fonts.googleapis.com/**", lambda r: r.abort())
    await pg.emulate_media(color_scheme=scheme)
    await pg.goto(URL); await pg.wait_for_timeout(350)
    return pg

async def check(pg, where):
    for e in pg.errs: issue("JS error", where, e)
    for d in pg.dialogs: issue("native dialog", where, d)
    pg.errs.clear(); pg.dialogs.clear()
    try:
        for p in await pg.evaluate(INVARIANTS): issue("invariant", where, p)
    except Exception as e: issue("evaluate failed", where, str(e)[:120])

async def goto_screen(pg, screen):
    await pg.evaluate("document.activeElement&&document.activeElement.blur()")
    if screen in ("month", "subs", "cheaper", "codes", "plan", "split"): await pg.click(f"[data-tab={screen}]")
    elif screen == "account": await pg.click("#acct-btn")
    elif screen == "inbox":
        if not await pg.locator("#bell").is_visible(): return False
        await pg.click("#bell")
    await pg.wait_for_timeout(150)
    return True

async def click_key(pg, key):
    """Click the element with this key. Returns False if not found."""
    ok = await pg.evaluate("""k=>{const sel='button, a[href], [role=button], summary, input[type=checkbox], input[type=radio], select, label:has(input[type=file])';
      for(const el of document.querySelectorAll(sel)){ if(el.closest('[inert],[aria-hidden=true]'))continue; if(el.tagName!=='SUMMARY'&&el.closest('details:not([open])'))continue;
        const r=el.getBoundingClientRect(); if(!r.width||!r.height||el.disabled)continue;
        const ds=Object.entries(el.dataset).map(([a,b])=>a+'='+b).join('&');
        const t=(el.getAttribute('aria-label')||el.title||el.textContent||el.value||'').trim().replace(/\\s+/g,' ').slice(0,40);
        if(el.tagName+'|'+(el.id||'')+'|'+ds+'|'+t===k){ el.setAttribute('data-x-target','1'); return true; } } return false }""", key)
    if not ok: return False
    loc = pg.locator("[data-x-target]").first
    tag = await loc.evaluate("e=>e.tagName")
    try:
        if tag == "SELECT":
            opts = await loc.evaluate("e=>[...e.options].map(o=>o.value)")
            if len(opts) > 1: await loc.select_option(opts[-1] if opts[0] == await loc.input_value() else opts[0])
        else:
            await loc.scroll_into_view_if_needed(timeout=1500)
            # a real finger tap: is the element actually on top at its center?
            covered = await loc.evaluate("e=>{const r=e.getBoundingClientRect();const x=r.left+r.width/2,y=r.top+r.height/2; if(y<0||y>innerHeight)return 'offscreen'; const t=document.elementFromPoint(x,y); return t&&(t===e||e.contains(t)||t.contains(e)||(e.tagName==='INPUT'&&e.closest('label')&&e.closest('label').contains(t)))?'':(t?(t.className||t.tagName)+'':'none')}")
            if covered: issue("covered control", key, "tap lands on " + covered)
            await loc.click(timeout=2000, force=bool(covered))
    except Exception as e:
        issue("click failed", key, str(e).split("\n")[0][:140])
    finally:
        await pg.evaluate("document.querySelectorAll('[data-x-target]').forEach(e=>e.removeAttribute('data-x-target'))")
    await pg.wait_for_timeout(180)
    return True

SCREENS = os.environ.get('XSCREENS','').split(',') if os.environ.get('XSCREENS') else ["month", "subs", "cheaper", "codes", "plan", "split", "account", "inbox"]
IGNORE_DEAD = re.compile(r"legal|privacy|terms|mailto|http|#main|download", re.I)

async def sweep(browser, w, h, scheme, prep=None, label=""):
    ctx = await browser.new_context(accept_downloads=True)
    pg = await new_page(ctx, w, h, scheme)
    seen_small = set()
    total = 0
    async def fresh():
        await pg.evaluate("localStorage.clear()"); await pg.goto(URL); await pg.wait_for_timeout(300)
        if prep: await prep(pg)
    for screen in SCREENS:
        await fresh()
        if not await goto_screen(pg, screen): continue
        base = await pg.evaluate(CLICKABLES)
        print(f'  {label}{w}x{h} {screen}: {len(base)} controls', flush=True)
        where0 = f"{label}{w}x{h}/{scheme}/{screen}"
        await check(pg, where0)
        for c in base:
            if c["tag"] == "A" and (c["href"].startswith("http") or c["target"] == "_blank" or c["href"].endswith(".html")):
                continue
            if c["tag"] in ("BUTTON", "A", "SELECT", "LABEL") and (c["w"] < 32 or c["h"] < 32) and c["key"] not in seen_small:
                seen_small.add(c["key"]); issue("small touch target (<32px)", f"{screen}", f"{c['t']!r} {int(c['w'])}x{int(c['h'])}")
        keys = [c["key"] for c in base if not (c["tag"] == "A" and (c["href"].startswith("http") or c["target"] == "_blank" or c["href"].endswith(".html")))]
        keys = list(dict.fromkeys(keys))  # repeated rows share a key; press each kind once
        if os.environ.get('XPART'): a, m = map(int, os.environ['XPART'].split('/')); keys = keys[a::m]
        if QUICK: keys = keys[:25]
        for key in keys:
            if os.environ.get('XDEBUG'): print('    press', key, flush=True)
            await fresh(); await goto_screen(pg, screen)
            before = await pg.evaluate(SNAP)
            if not await click_key(pg, key): issue("vanished before click", where0, key); continue
            total += 1
            after = await pg.evaluate(SNAP)
            where = f"{where0} :: {key}"
            await check(pg, where)
            if before == after and not IGNORE_DEAD.search(key) and not pg.chooser: issue("dead control (nothing changed)", where0, key)
            pg.chooser.clear()
            # depth 2: everything that appeared
            now = await pg.evaluate(CLICKABLES)
            base_keys = set(keys)
            new = list(dict.fromkeys([c["key"] for c in now if c["key"] not in base_keys and "|tab=" not in c["key"] and not (c["tag"] == "A" and (c["href"].startswith("http") or c["href"].endswith(".html")))]))
            for k2 in new[: (6 if QUICK else 15)]:
                if os.environ.get('XDEBUG'): print('      then', k2, flush=True)
                b2 = await pg.evaluate(SNAP)
                if not await click_key(pg, k2): continue
                total += 1
                a2 = await pg.evaluate(SNAP)
                await check(pg, f"{where} >> {k2}")
                if b2 == a2 and not IGNORE_DEAD.search(k2) and not pg.chooser: issue("dead control (nothing changed)", f"{where0} after {key[:50]}", k2)
                pg.chooser.clear()
    await ctx.close()
    return total

EDGE = ["", "0", "-5", "1e9", "99999999999", "12.345", "abc", "  ", "😀", "<b>x</b>", "1,234.56", "$50", ".5", "007", "-0", "3" * 40,
        "O'Brien \"Jr\"", "a" * 200, "2026-02-30", "@", "+1 (555) 000-0000", "test@example.com"]

async def monkey(browser, seed, w, h, steps):
    rnd = random.Random(seed)
    ctx = await browser.new_context(accept_downloads=True)
    pg = await new_page(ctx, w, h, rnd.choice(["light", "dark"]))
    log = []
    for i in range(steps):
        where = f"monkey seed={seed} {w}x{h} step={i} after {' > '.join(log[-4:])}"
        r = rnd.random()
        try:
            if r < 0.10:
                s = rnd.choice(SCREENS); log.append("screen:" + s); await goto_screen(pg, s)
            elif r < 0.40:
                fields = await pg.evaluate("""(()=>{document.querySelectorAll('[data-x-field]').forEach(e=>e.removeAttribute('data-x-field'));const f=[...document.querySelectorAll('#view input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=hidden]), #view textarea')].filter(e=>e.getBoundingClientRect().width&&!e.closest('[inert],[aria-hidden=true]')&&!e.closest('details:not([open])')&&!e.disabled);f.forEach((e,i)=>e.setAttribute('data-x-field',i));return f.length})()""")
                if fields:
                    idx = rnd.randrange(fields); v = rnd.choice(EDGE + [str(rnd.randint(1, 5000)), str(round(rnd.uniform(0, 999), 2))])
                    loc = pg.locator(f'[data-x-field="{idx}"]')
                    typ = await loc.get_attribute("type") or ""
                    if typ == "date": v = rnd.choice(["2026-09-15", "2026-01-01", "2027-12-31"])
                    if typ == "color": v = "#336699"
                    log.append(f"type[{idx}]={v[:12]!r}")
                    await loc.scroll_into_view_if_needed(timeout=1500); await loc.click(timeout=1500)
                    await loc.fill(v, timeout=1500)
                    if rnd.random() < 0.5: await pg.keyboard.press("Enter")
                    else: await pg.evaluate("document.activeElement&&document.activeElement.blur()")
                    await pg.wait_for_timeout(120)
            elif r < 0.85:
                cs = [c for c in await pg.evaluate(CLICKABLES) if not (c["tag"] == "A" and (c["href"].startswith("http") or c["href"].endswith(".html") or c["target"]))]
                cs = [c for c in cs if not re.search(r"delete-yes|reset-yes|signout", c["key"]) or rnd.random() < 0.3]
                if cs:
                    c = rnd.choice(cs); log.append("tap:" + c["key"][:60]); await click_key(pg, c["key"])
            elif r < 0.90:
                before = await pg.evaluate("localStorage.getItem('keepwise-app-v1')")
                await pg.evaluate("document.activeElement&&document.activeElement.blur()"); await pg.wait_for_timeout(250)
                before = await pg.evaluate("(window.save&&save(),localStorage.getItem('keepwise-app-v1'))")
                log.append("reload"); await pg.reload(); await pg.wait_for_timeout(350)
                after = await pg.evaluate("localStorage.getItem('keepwise-app-v1')")
                if before and after:
                    b, a = json.loads(before), json.loads(after)
                    for k in set(b) | set(a):
                        if k not in ("seen", "lastOpen", "updatedAt") and b.get(k) != a.get(k): issue("state changed by reload", f"monkey seed={seed}", k)
            elif r < 0.95:
                nw, nh = rnd.choice([(320, 568), (390, 844), (768, 1024), (1280, 800), (844, 390)])
                log.append(f"resize {nw}x{nh}"); await pg.set_viewport_size({"width": nw, "height": nh}); await pg.wait_for_timeout(200)
                w, h = nw, nh
            else:
                log.append("theme"); await pg.click("#theme-btn"); await pg.wait_for_timeout(100)
        except Exception as e:
            issue("action failed", where, str(e).split("\n")[0][:140])
        await check(pg, where)
    await ctx.close()

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        n = 0
        async def empty(pg):  # a brand-new person who wiped the sample data
            await pg.click("[data-tab=plan]"); await pg.wait_for_timeout(120)
            if await pg.locator("[data-reset]").count():
                await pg.click("[data-reset]"); await pg.wait_for_timeout(120)
                if await pg.locator("[data-reset-yes]").count(): await pg.click("[data-reset-yes]"); await pg.wait_for_timeout(200)
            await pg.click("[data-tab=month]"); await pg.wait_for_timeout(120)
        configs = [(390, 844, "light", None, ""), (320, 568, "dark", None, ""), (1280, 800, "light", None, ""), (390, 844, "light", empty, "EMPTY ")]
        if QUICK: configs = configs[:1]
        if os.environ.get('XCFG'): configs = [configs[int(i)] for i in os.environ['XCFG'].split(',')]
        if os.environ.get('XMODE') == 'monkey': configs = []
        for w, h, s, prep, lab in configs:
            c = await sweep(b, w, h, s, prep, lab); n += c
            print(f"sweep {lab}{w}x{h} {s}: {c} presses, {len(ISSUES)} issue kinds so far", flush=True)
        seeds = 6 if QUICK else 40
        rng = range(seeds) if os.environ.get('XMODE') != 'sweep' else []
        if os.environ.get('XSEEDS'): a, z = map(int, os.environ['XSEEDS'].split('-')); rng = range(a, z)
        for sd in rng:
            w, h = [(390, 844), (320, 568), (1280, 800), (414, 896)][sd % 4]
            await monkey(b, sd, w, h, 60 if QUICK else 120)
        print(f"monkey: {seeds} sessions done", flush=True)
        await b.close()
    groups = {}
    for (kind, where, detail), cnt in ISSUES.items(): groups.setdefault(kind, []).append((where, detail, cnt))
    out = []
    for kind, items in sorted(groups.items()):
        out.append(f"\n=== {kind} ({len(items)}) ===")
        for where, detail, cnt in sorted(items)[:60]: out.append(f"  [{cnt}x] {where[:150]}  |  {detail}")
    report = "\n".join(out)
    open(os.environ.get("XOUT", os.path.join(TMP, "report.txt")), "w").write(report)
    print(report); print("\nreport:", os.path.join(TMP, "report.txt"), "presses:", n)

asyncio.run(main())
