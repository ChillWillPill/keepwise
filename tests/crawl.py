"""Taps every visible button on every main screen, one at a time from a fresh start, and fails on any script error
or a blank screen. Run: python3 tests/crawl.py <src/app.html|www/index.html>. It reuses the helpers in test_app.py."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "test_app.py")).read()
prefix, main = src[:src.index("async def main(")], src[src.index("async def main("):]
crawl = '''
TESTS.clear()
SKIP = ("data-reset", "data-lock-erase", "data-acc-del", "data-acc-out", "data-sure", "data-plus-off", "data-reset-yes", "data-erase", "data-restore", "data-del-account")
SCREENS = []
def screen(name):
    def deco(fn): SCREENS.append((name, fn)); return fn
    return deco
@screen("month overview")
async def _a(pg): await pg.click("[data-mseg=now]")
@screen("month budget")
async def _b(pg): await pg.click("[data-mseg=budget]")
@screen("month income")
async def _c(pg): await pg.click("[data-mseg=more]")
@screen("subs")
async def _d(pg): await tab(pg, "subs")
@screen("split")
async def _f(pg): await tab(pg, "split")
@screen("banks")
async def _g(pg): await pg.click("[data-tab=banks]")
for seg in ("money", "invoices", "miles", "tax"):
    async def _h(pg, seg=seg):
        await pg.click("[data-mseg=more]"); await pg.click("[data-space=business]"); await pg.wait_for_timeout(100)
        if not await pg.locator("[data-biz-hero], [data-bseg]").count():
            for _ in range(7): await pg.click("[data-plus-tap]", force=True)
            await pg.wait_for_timeout(200)
        await pg.click(f"[data-bseg={seg}]")
    SCREENS.append((f"business {seg}", _h))
@screen("plus page")
async def _i(pg): await menu_to(pg, "plus")
@screen("settings")
async def _j(pg): await menu_to(pg, "settings")
@screen("security")
async def _k(pg): await menu_to(pg, "security")
@screen("your data")
async def _l(pg): await menu_to(pg, "data")

@test
async def zz_every_button_on_every_screen(ctx):
    pg = await open_app(ctx, month_tabs=True)
    pg.on("dialog", lambda d: d.dismiss())
    pg.on("filechooser", lambda fc: None)
    snap = await pg.evaluate("localStorage.getItem('keepwise-app-v1')")
    total, problems = 0, []
    for name, nav in SCREENS:
        i = 0
        while True:
            await pg.evaluate("s => { window.__kwErasing = true; localStorage.setItem('keepwise-app-v1', s); }", snap); await pg.reload(); await pg.wait_for_timeout(250)
            pg.errors.clear()
            try: await nav(pg); await pg.wait_for_timeout(200)
            except Exception as e: problems.append(f"{name}: could not open ({str(e)[:80]})"); break
            btns = pg.locator("#view button:visible:not([disabled])")
            n = await btns.count()
            if i >= n: break
            b = btns.nth(i); attrs = await b.evaluate("e => e.outerHTML.slice(0, 160)")
            i += 1
            if any(k in attrs for k in SKIP): continue
            try: await b.click(timeout=2000); await pg.wait_for_timeout(250)
            except Exception: continue   # covered by something else for a moment: not an error
            total += 1
            errs = [e for e in pg.errors if "status of 4" not in e and "status of 5" not in e and "Failed to load resource" not in e]
            if errs: problems.append(f"{name} · {attrs[:90]} → {errs[0][:160]}")
            body = await pg.evaluate("(document.getElementById('view').innerText || '').trim().length + (document.getElementById('lockscreen').hidden ? 0 : 1)")
            if body == 0: problems.append(f"{name} · {attrs[:90]} → blank screen")
    print(f"crawl: {total} taps")
    assert not problems, "\\n".join(problems[:40])
'''
exec(compile(prefix + crawl + "\n" + main, "crawl", "exec"))
