"""Layout sweep: every main screen of the app and the website, at phone, tablet and desktop sizes, in each browser
engine given. Flags sideways scroll, text cut off without an ellipsis, things sticking out of the screen and buttons
that overlap. Saves a screenshot of each screen. Run: python3 tests/sweep.py www/index.html [chromium,firefox,webkit] [outdir]"""
import os, sys, json, asyncio
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "test_app.py")).read()
prefix = src[:src.index("async def main(")]
APP_ARG = sys.argv[1] if len(sys.argv) > 1 else "www/index.html"
ENGINES = (sys.argv[2] if len(sys.argv) > 2 else "chromium").split(",")
OUT = sys.argv[3] if len(sys.argv) > 3 else "/tmp/sweep"
sys.argv = [sys.argv[0], APP_ARG]
exec(compile(prefix, "test_app.py", "exec"))
os.makedirs(OUT, exist_ok=True)

SIZES = [("se", 320, 568), ("android", 360, 740), ("iphone", 390, 844), ("max", 430, 932), ("ipad", 768, 1024), ("laptop", 1280, 800), ("desktop", 1920, 1080)]

CHECK = r"""() => {
  const pinned = e => { for (let p = e; p; p = p.parentElement){ const ps = getComputedStyle(p).position; if (ps === 'fixed' || ps === 'sticky') return true; } return false; }; const out = [], W = innerWidth, H = innerHeight, top = e => { const r = e.getBoundingClientRect(), x = Math.min(W - 1, Math.max(0, r.left + r.width / 2)), y = r.top + r.height / 2; if (y < 0 || y > H) return true; const t = document.elementFromPoint(x, y); return !!t && (t === e || e.contains(t) || t.contains(e)); }, vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity !== 0; };
  const name = e => (e.getAttribute('aria-label') || e.innerText || e.className || e.tagName).toString().trim().replace(/\s+/g, ' ').slice(0, 50);
  if (document.documentElement.scrollWidth > W + 1) out.push(['sideways scroll', document.documentElement.scrollWidth + ' > ' + W]);
  const scrollers = el => { for (let p = el.parentElement; p; p = p.parentElement){ const s = getComputedStyle(p); if (/(auto|scroll)/.test(s.overflowX) && p.scrollWidth > p.clientWidth) return true; } return false; };
  for (const e of document.querySelectorAll('button, a, b, strong, h1, h2, h3, p, small, span, label, em, li, input, select')){
    if (!vis(e) || e.closest('[hidden],[aria-hidden=true],svg,.kws-marq,[data-scroll-x],.ss-chips,.dm-scroll,.leaflet-container')) continue;
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    if ((r.right > W + 1 || r.left < -1) && !scrollers(e) && s.position !== 'fixed') out.push(['off screen', name(e) + ' @' + Math.round(r.left) + '..' + Math.round(r.right)]);
    if (e.children.length === 0 && top(e) && e.scrollWidth > e.clientWidth + 2 && s.overflowX === 'hidden' && !/rect\(|inset/.test(s.clip + s.clipPath) && s.textOverflow !== 'ellipsis' && e.clientWidth > 0) out.push(['text cut', name(e)]);
    if (e.children.length === 0 && /^(BUTTON|A)$/.test(e.tagName) && e.scrollHeight > e.clientHeight + 4 && s.overflowY === 'hidden') out.push(['text cut (height)', name(e)]);
  }
  const btns = [...document.querySelectorAll('button, a.btn, .btn')].filter(e => vis(e) && !e.closest('[hidden],svg,.dm,.kws-marq') && !pinned(e) && top(e));
  for (let i = 0; i < btns.length; i++) for (let j = i + 1; j < btns.length; j++){ const a = btns[i], b = btns[j]; if (a.contains(b) || b.contains(a)) continue;
    const p = a.getBoundingClientRect(), q = b.getBoundingClientRect(), ov = Math.min(p.right, q.right) - Math.max(p.left, q.left), oh = Math.min(p.bottom, q.bottom) - Math.max(p.top, q.top);
    if (ov > 4 && oh > 4) out.push(['buttons overlap', name(a) + ' / ' + name(b)]); }
  return out.slice(0, 40);
}"""

async def open_menu(pg, key): await menu_to(pg, key); await pg.wait_for_timeout(250)
async def seg(pg, s):
    await tab(pg, "month"); m = pg.locator(f"#view [data-mseg={s}]")
    if await m.count() and await m.first.is_visible(): await m.first.click(); await pg.wait_for_timeout(250)
async def plus(pg):
    await pg.click("[data-tab=banks]"); await pg.wait_for_timeout(150); el = pg.locator("[data-plus-open]").first; await el.scroll_into_view_if_needed(); await el.click(); await pg.wait_for_timeout(300)
async def io(pg):
    await tab(pg, "month"); b = pg.locator("[data-io-open]")
    if await b.count(): await b.click(); await pg.wait_for_timeout(300)
async def owl(pg): await pg.click("#wise"); await pg.wait_for_timeout(600)
async def bizsheet(pg):   # a business entry's sheet: its last row (Edit, Receipt, Refund, Delete) must be whole and on screen
    await space(pg, "business"); await pg.click("[data-bz-demo-on]"); await pg.wait_for_timeout(300)
    await pg.locator("[data-bz-needs] button").first.click(); await pg.wait_for_timeout(500)
    await pg.evaluate("document.querySelector('.bz-sheet').scrollTop = 1e5"); await pg.wait_for_timeout(200)
    bad = await pg.evaluate("""() => { const s = document.querySelector('.bz-sheet'), r = s.getBoundingClientRect(), out = [];
      for (const b of s.querySelectorAll('.bz-acts button')){ const q = b.getBoundingClientRect(); if (q.bottom > Math.min(r.bottom, innerHeight) + 1 || b.clientHeight + 2 < b.scrollHeight) out.push(['sheet row cut', b.innerText.trim() + ' ' + Math.round(q.bottom) + ' > ' + Math.round(Math.min(r.bottom, innerHeight))]); }
      return out; }""")
    pg.extra = bad
async def acct(pg): await open_account(pg); await pg.wait_for_timeout(300)

SCREENS = [("month", lambda pg: seg(pg, "now")), ("budget", lambda pg: seg(pg, "budget")), ("income", lambda pg: seg(pg, "more")),
  ("breakdown", io), ("subs", lambda pg: tab(pg, "subs")), ("banks", lambda pg: pg.click("[data-tab=banks]")), ("split", lambda pg: tab(pg, "split")),
  ("plus", plus), ("owl", owl), ("bizsheet", bizsheet), ("account", acct), ("settings", lambda pg: open_menu(pg, "settings")), ("security", lambda pg: open_menu(pg, "security")),
  ("support", lambda pg: open_menu(pg, "support")), ("data", lambda pg: open_menu(pg, "data"))]

async def site(ctx, w, h):
    pg = await ctx.new_page(); await pg.set_viewport_size({"width": w, "height": h}); pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    await pg.add_init_script("window.KEEPWISE_FIREBASE = null;"); await pg.goto(URL + "?site"); await pg.wait_for_timeout(1200)
    return pg

async def main():
    report = {}
    async with async_playwright() as p:
        for eng in ENGINES:
            b = await getattr(p, eng).launch()
            for sz, w, h in SIZES:
                ctx = await b.new_context(viewport={"width": w, "height": h}, has_touch=w < 800, is_mobile=(w < 800 and eng != "firefox"))
                for nm, fn in SCREENS:
                    key = f"{eng}/{sz}/{nm}"
                    try:
                        pg = await open_app(ctx, w=w, h=h, fb=(nm in ("account", "security")))
                        await fn(pg); await pg.wait_for_timeout(250)
                        found = await pg.evaluate(CHECK) + [["script error", x[:120]] for x in pg.errors] + list(getattr(pg, "extra", []))
                        if found: report[key] = found
                        await pg.screenshot(path=f"{OUT}/{eng}-{sz}-{nm}.png", full_page=w >= 768)
                        await pg.close()
                    except Exception as e: report[key] = [["could not open", str(e).split("\n")[0][:140]]]
                try:
                    pg = await site(ctx, w, h); found = await pg.evaluate(CHECK) + [["script error", x[:120]] for x in pg.errors]
                    if found: report[f"{eng}/{sz}/website"] = found
                    await pg.screenshot(path=f"{OUT}/{eng}-{sz}-website.png", full_page=True); await pg.close()
                except Exception as e: report[f"{eng}/{sz}/website"] = [["could not open", str(e).split("\n")[0][:140]]]
                await ctx.close()
            await b.close()
    json.dump(report, open(f"{OUT}/report.json", "w"), indent=1)
    n = sum(len(v) for v in report.values()); print(f"{n} issues on {len(report)} screens");
    for k, v in report.items():
        for x in v[:6]: print(k, "|", x[0], "|", x[1])
asyncio.run(main())
