"""KeepWise end-to-end test suite (Playwright, Chromium).
Run: python3 tests/test_app.py [path/to/app.html]
Each test gets a fresh browser context (empty storage)."""
import asyncio, sys, os, re, json, tempfile, traceback
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "app.html"))
TMP = tempfile.mkdtemp()
PAGE = os.path.join(TMP, "app_test.html")
with open(APP) as f, open(PAGE, "w") as o:
    body = f.read()
    o.write(body if body.lstrip().lower().startswith("<!doctype") else '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' + body)
URL = "file://" + PAGE
MOCK = os.path.join(HERE, "mock_claude.js")

TESTS = []
def test(fn): TESTS.append(fn); return fn

def money(s):  # "$1,456.99" -> 1456.99 ; handles "−"
    m = re.search(r"(-|−)?\$([\d,]+(?:\.\d+)?)", s)
    assert m, f"no money in {s!r}"
    v = float(m.group(2).replace(",", ""))
    return -v if m.group(1) else v

async def open_app(ctx, mock=False, w=390, h=844, scheme="light", fb=False, preview=False, welcome=False):
    pg = await ctx.new_page()
    await pg.set_viewport_size({"width": w, "height": h})
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append("pageerror: " + str(e)))
    pg.on("console", lambda m: m.type == "error" and "ERR_TUNNEL" not in m.text and "fonts.g" not in m.text and "net::" not in m.text and pg.errors.append("console: " + m.text))
    if mock: await pg.add_init_script(path=MOCK)
    # pdf.js normally comes from cdnjs; serve the same version locally so tests run offline
    async def serve_vendor(route):
        name = route.request.url.rsplit("/", 1)[-1]
        path = os.path.join(HERE, "vendor", name)
        if os.path.exists(path): await route.fulfill(path=path, content_type="application/javascript")
        else: await route.abort()
    await pg.route("https://cdnjs.cloudflare.com/**", serve_vendor)
    if welcome is False: await pg.add_init_script("window.KEEPWISE_NO_SETUP = true;")  # most tests start on the example month
    if not fb and not preview: await pg.add_init_script("window.KEEPWISE_FIREBASE = null;")  # no network sign-in in ordinary tests
    if fb:  # sign-in tests: a project config plus an offline stand-in for the Firebase SDK
        await pg.add_init_script("window.KEEPWISE_FIREBASE = {apiKey: 'test', authDomain: 'test.firebaseapp.com', projectId: 'test'};")
        async def serve_fb(route):
            if route.request.url.endswith("firebase-app-compat.js"): await route.fulfill(path=os.path.join(HERE, "mock_firebase.js"), content_type="application/javascript")
            else: await route.fulfill(body="", content_type="application/javascript")
        await pg.route("https://cdn.jsdelivr.net/npm/firebase@*/**", serve_fb)
    await pg.emulate_media(color_scheme=scheme)
    await pg.goto(URL); await pg.wait_for_timeout(500)
    return pg

async def state(pg): return await pg.evaluate("JSON.parse(localStorage.getItem('keepwise-app-v1') || 'null')")
async def tab(pg, name):
    # like tapping away to close the keyboard first (the tab bar hides while typing)
    await pg.evaluate("document.activeElement && document.activeElement.blur()"); await pg.wait_for_timeout(120)
    await pg.click(f"[data-tab={name}]"); await pg.wait_for_timeout(120)
async def text(pg, sel): return (await pg.inner_text(sel)).replace("\n", " ")

# ---------------- layout ----------------
@test
async def layout_tabbar_flush_every_size(ctx):
    for w, h in [(320, 568), (375, 667), (390, 844), (430, 932), (768, 1024), (1280, 800)]:
        pg = await open_app(ctx, w=w, h=h)
        g = await pg.evaluate("(()=>{const t=tabbar.getBoundingClientRect(),hd=document.querySelector('.app-header').getBoundingClientRect();return {b:t.bottom,vh:innerHeight,top:hd.top,sw:document.documentElement.scrollWidth,cw:innerWidth}})()")
        assert abs(g["b"] - g["vh"]) < 1, f"{w}x{h}: tab bar bottom {g['b']} != {g['vh']}"
        assert g["top"] == 0, f"{w}x{h}: header not at top"
        assert g["sw"] <= g["cw"], f"{w}x{h}: horizontal scroll {g['sw']}>{g['cw']}"
        await pg.close()

OVERFLOW = """(()=>{const vw=document.documentElement.clientWidth,bad=[];
document.querySelectorAll('#view *, .app-header *, #tabbar *').forEach(el=>{
  if(el.closest('svg')||el.closest('.sr'))return; const r=el.getBoundingClientRect(); if(!r.width)return;
  if(r.left<-0.5||r.right>vw+0.5) bad.push((el.className||el.tagName)+':'+Math.round(r.left)+'-'+Math.round(r.right));
  if(/^(SPAN|B|P|H1|H2|H3|BUTTON|DIV)$/.test(el.tagName)&&el.children.length===0&&getComputedStyle(el).textOverflow!=='ellipsis'&&el.scrollWidth>el.clientWidth+1&&getComputedStyle(el).overflowX!=='visible') bad.push('clipped '+el.textContent.slice(0,20));
});
const labels=[...document.querySelectorAll('#tabbar .tab span:last-child')].filter(s=>s.scrollWidth>s.clientWidth+1).map(s=>s.textContent);
return {sw:document.documentElement.scrollWidth,vw,bad:bad.slice(0,6),labels}})()"""

@test
async def responsive_every_tab_every_size(ctx):
    sizes = [(280, 653), (320, 568), (360, 740), (390, 844), (414, 896), (600, 960), (768, 1024), (1024, 768), (1440, 900), (844, 390)]
    for w, h in sizes:
        pg = await open_app(ctx, w=w, h=h)
        for name in ["month", "subs", "cheaper", "codes", "plan", "split"]:
            await tab(pg, name)
            if name == "month":
                await pg.click("[data-env-open=needs]"); await pg.click("[data-compare]"); await pg.wait_for_timeout(80)
            if name == "split":
                await pg.click("[data-new-split]"); await pg.select_option("[data-d=method]", "percent"); await pg.wait_for_timeout(80)
            r = await pg.evaluate(OVERFLOW)
            assert r["sw"] <= r["vw"], f"{w}x{h} {name}: page scrolls sideways ({r['sw']}>{r['vw']})"
            assert not r["bad"], f"{w}x{h} {name}: overflow {r['bad']}"
            assert not r["labels"], f"{w}x{h}: tab labels cut off {r['labels']}"
            g = await pg.evaluate("[tabbar.getBoundingClientRect().bottom, innerHeight]")
            assert abs(g[0] - g[1]) < 1, f"{w}x{h} {name}: tab bar not at bottom {g}"
        await pg.close()

COLLIDE = """(()=>{const bad=[];const boxes=[...document.querySelectorAll('.summary3 b, .legend span, .row-top > div, .cmp-val, .big, .bigsoft')];
boxes.forEach(el=>{const r=document.createRange();r.selectNodeContents(el);const t=r.getBoundingClientRect(),b=el.getBoundingClientRect();if(t.width>b.width+1)bad.push(el.textContent.trim().slice(0,24))});
const s=[...document.querySelectorAll('.summary3 b')].map(e=>e.getBoundingClientRect());for(let i=0;i<s.length;i++)for(let j=i+1;j<s.length;j++){const a=s[i],c=s[j];if(a.left<c.right&&c.left<a.right&&a.top<c.bottom&&c.top<a.bottom)bad.push('totals overlap')}
return bad})()"""

@test
async def long_currency_amounts_never_collide(ctx):
    for w in [320, 390, 768]:
        pg = await open_app(ctx, w=w, h=844)
        for cur in ["CAD", "PKR", "AED"]:
            await tab(pg, "month"); await pg.select_option("#m-cur", cur); await pg.fill("#m-income", "125000"); await pg.wait_for_timeout(100)
            for name in ["month", "subs", "cheaper", "split"]:
                await tab(pg, name); bad = await pg.evaluate(COLLIDE)
                assert not bad, f"{w}px {cur} {name}: {bad}"
        await pg.close()

@test
async def theme_switch_light_dark_auto(ctx):
    pg = await open_app(ctx, scheme="light")
    bg = lambda: pg.evaluate("getComputedStyle(document.body).backgroundColor")
    assert await bg() == "rgb(243, 239, 230)"
    await pg.click("#theme-btn"); assert await pg.evaluate("document.documentElement.dataset.theme") == "light"
    await pg.click("#theme-btn"); await pg.wait_for_timeout(50)
    assert await pg.evaluate("document.documentElement.dataset.theme") == "dark" and await bg() == "rgb(20, 22, 19)"
    assert await pg.evaluate("document.querySelector('meta[name=theme-color]').content") == "#141613"
    await pg.reload(); await pg.wait_for_timeout(400)
    assert await bg() == "rgb(20, 22, 19)", "dark choice must survive reload"
    await pg.click("#theme-btn"); await pg.wait_for_timeout(50)   # back to auto
    assert await pg.evaluate("document.documentElement.hasAttribute('data-theme')") is False and await bg() == "rgb(243, 239, 230)"
    await pg.emulate_media(color_scheme="dark"); await pg.wait_for_timeout(100)
    assert await bg() == "rgb(20, 22, 19)", "auto follows the phone"
    # light forced while phone is dark
    await pg.click("#theme-btn"); await pg.wait_for_timeout(50)
    assert await bg() == "rgb(243, 239, 230)"

@test
async def layout_after_reload_and_resize(ctx):
    pg = await open_app(ctx)
    await pg.fill("#m-income", "5000"); await pg.locator("#m-income").blur()
    await pg.reload(); await pg.wait_for_timeout(500)
    await pg.set_viewport_size({"width": 390, "height": 600}); await pg.wait_for_timeout(200)
    g = await pg.evaluate("[tabbar.getBoundingClientRect().bottom, innerHeight, scrollY]")
    assert abs(g[0] - g[1]) < 1 and g[2] == 0, g

@test
async def layout_tabbar_hides_while_typing(ctx):
    pg = await open_app(ctx)
    await pg.focus("#m-income"); await pg.wait_for_timeout(100)
    assert await pg.evaluate("getComputedStyle(tabbar).display") == "none"
    await pg.locator("#m-income").blur(); await pg.wait_for_timeout(150)
    assert await pg.evaluate("getComputedStyle(tabbar).display") != "none"

@test
async def fonts_and_colors_match_grok(ctx):
    pg = await open_app(ctx)
    h1 = await pg.evaluate("(()=>{const c=getComputedStyle(document.querySelector('h1'));return [c.fontFamily,c.fontWeight,c.fontSize,c.letterSpacing,c.color]})()")
    assert h1[0].startswith("Fraunces") and h1[1] == "600" and h1[2] == "36px" and h1[3] == "-0.9px" and h1[4] == "rgb(28, 36, 32)", h1
    big = await pg.evaluate("(()=>{const c=getComputedStyle(document.querySelector('.big'));return [c.fontFamily,c.fontSize,c.color]})()")
    assert big == ["Fraunces, ui-serif, Georgia, serif", "48px", "rgb(27, 104, 67)"], big
    body = await pg.evaluate("[getComputedStyle(document.body).fontFamily, getComputedStyle(document.body).backgroundColor]")
    assert body[0].startswith("Figtree") and body[1] == "rgb(243, 239, 230)", body
    href = await pg.evaluate("[...document.querySelectorAll('link[rel=stylesheet]')].map(l=>l.href).join(' ')")
    assert "family=Figtree:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700" in href, href

@test
async def dark_mode_readable(ctx):
    pg = await open_app(ctx, scheme="dark")
    c = await pg.evaluate("[getComputedStyle(document.body).backgroundColor, getComputedStyle(document.querySelector('h1')).color]")
    assert c[0] != "rgb(243, 239, 230)" and c[1] != "rgb(28, 36, 32)", c

# ---------------- month ----------------
@test
async def month_math_is_consistent(ctx):
    pg = await open_app(ctx)
    leg = await text(pg, ".legend")
    needs, misc, sav = [money(x) for x in re.findall(r"\$[\d,.]+", leg)]
    assert abs(5200 - needs - misc - sav) < 0.02, (needs, misc, sav)
    assert abs(money(await text(pg, ".big")) - sav) < 0.01
    await pg.fill("#m-income", "6000"); await pg.wait_for_timeout(100)
    assert abs(money(await text(pg, ".big")) - (sav + 800)) < 0.02

@test
async def month_currency_switch(ctx):
    pg = await open_app(ctx)
    await pg.select_option("#m-cur", "GBP"); await pg.wait_for_timeout(150)
    assert "£" in await text(pg, ".big")
    assert (await state(pg))["cur"] == "GBP"

CHECK_MONEY = """(()=>{const bad=[];document.querySelectorAll('.money-in').forEach(box=>{const em=box.querySelector('em'),i=box.querySelector('input');if(!em||!i)return;const e=em.getBoundingClientRect(),r=i.getBoundingClientRect(),b=box.getBoundingClientRect();const after=em.compareDocumentPosition(i)&Node.DOCUMENT_POSITION_PRECEDING;const txt=r.left+parseFloat(getComputedStyle(i).paddingLeft);if((after?r.right>e.left+0.5:txt<e.right+4)||r.right>b.right+0.5||e.right>b.right+0.5)bad.push(em.textContent+' '+i.value)});return {n:document.querySelectorAll('.money-in').length,bad}})()"""

@test
async def currency_label_never_overlaps_amount_anywhere(ctx):
    pg = await open_app(ctx)
    for cur in ["USD", "GBP", "PKR", "AED", "INR"]:
        await tab(pg, "month"); await pg.select_option("#m-cur", cur); await pg.wait_for_timeout(120)
        r = await pg.evaluate(CHECK_MONEY); assert r["n"] >= 1 and not r["bad"], f"{cur} month: {r}"
        await tab(pg, "plan"); r = await pg.evaluate(CHECK_MONEY); assert r["n"] >= 10 and not r["bad"], f"{cur} plan: {r}"
        await tab(pg, "split"); await pg.click("[data-new-split]"); await pg.wait_for_timeout(80)
        r = await pg.evaluate(CHECK_MONEY); assert r["n"] >= 1 and not r["bad"], f"{cur} split form: {r}"
        await pg.click("[data-cancel-split]")
        await pg.locator("[data-settle-btn]").first.click(); await pg.wait_for_timeout(80)
        await pg.click("#history [data-pay-edit]"); await pg.wait_for_timeout(80)
        r = await pg.evaluate(CHECK_MONEY); assert not r["bad"], f"{cur} payment edit: {r}"
        await pg.click("#history [data-pay-del]"); await pg.wait_for_timeout(80)

@test
async def month_compare_chart(ctx):
    pg = await open_app(ctx)
    await pg.click("[data-compare]"); await pg.wait_for_timeout(150)
    vals = [money(t) for t in await pg.locator(".cmp-val").all_inner_texts()]
    big = money(await text(pg, "[data-out=dropCard] .bigsoft"))
    assert len(vals) == 2 and vals[1] > vals[0] and abs(vals[1] - big) < 0.01, (vals, big)
    await pg.locator(".cmp-col").first.click()
    assert await pg.locator(".cmp-col.on .cmp-tip").is_visible()
    await pg.click("[data-compare]"); await pg.wait_for_timeout(100)
    assert await pg.locator(".cmp").count() == 0

@test
async def month_say_it_plainly_and_ask(ctx):
    pg = await open_app(ctx)
    await pg.click("[data-plain]")
    t = await text(pg, "#ask-out")
    assert "yours to keep" in t and "barely use" in t, t
    await pg.click("[data-ask='Can I afford $300?']"); assert (await text(pg, "#ask-out")).startswith("Yes")
    await pg.click("[data-ask='What should I cancel?']"); assert "Your rules flag" in await text(pg, "#ask-out")
    await pg.click("[data-ask='Who owes me?']"); assert "owe" in await text(pg, "#ask-out")
    await pg.fill("#ask-in", "can I afford 999999"); await pg.press("#ask-in", "Enter")
    assert (await text(pg, "#ask-out")).startswith("Not without")

@test
async def month_hide_note_persists(ctx):
    pg = await open_app(ctx)
    await pg.click("[data-hide-note]"); await pg.reload(); await pg.wait_for_timeout(400)
    assert await pg.locator("[data-hide-note]").count() == 0

@test
async def month_envelope_details_and_set_aside(ctx):
    pg = await open_app(ctx)
    st0 = await state(pg); assert st0 is not None, "fresh install must be saved"
    ef0 = st0["efSaved"]
    await pg.click("[data-env-open=save]"); await pg.wait_for_timeout(100)
    assert "Nothing in this account yet" in await text(pg, ".env-body")
    amt = money(await text(pg, "[data-set-aside]"))
    head0 = money(re.search(r"ends with (\$[\d,.]+)", await text(pg, "[data-out=headline]")).group(1))
    await pg.click("[data-set-aside]"); await pg.wait_for_timeout(150)
    st = await state(pg)
    assert abs(st["efSaved"] - (ef0 + amt)) < 0.01 and len(st["deposits"]) == 1
    head1 = money(re.search(r"ends with (\$[\d,.]+)", await text(pg, "[data-out=headline]")).group(1))
    assert abs(head0 - head1) < 0.01, "month-end total must not double count"
    assert await pg.locator("[data-set-aside]").count() == 0
    await pg.click("[data-undo-dep]"); await pg.wait_for_timeout(150)
    assert abs((await state(pg))["efSaved"] - ef0) < 0.01

@test
async def month_envelope_add_and_remove_line(ctx):
    pg = await open_app(ctx)
    sav0 = money(await text(pg, ".big"))
    await pg.click("[data-env-open=misc]")
    await pg.fill("[data-new-name]", "Haircut"); await pg.fill("[data-new-amt]", "30"); await pg.click("[data-add-line-btn]"); await pg.wait_for_timeout(120)
    assert "Haircut" in await text(pg, ".env-body")
    assert abs(money(await text(pg, ".big")) - (sav0 - 30)) < 0.02
    await pg.locator(".env-body .line", has_text="Haircut").locator("[data-del-exp]").click(); await pg.wait_for_timeout(120)
    assert abs(money(await text(pg, ".big")) - sav0) < 0.02
    await pg.click("[data-add-line-btn]")  # empty name
    assert await pg.inner_text("#toast") == "Give the line a name."
    await pg.click("[data-env-open=needs]"); assert "Rent" in await text(pg, ".env-body")

@test
async def add_line_survives_a_slow_human_tap(ctx):
    # A real tap holds the button for ~100-300 ms; the redraw that follows leaving a field must not eat it.
    for w in (390, 1280):
        pg = await open_app(ctx, w=w)
        await pg.click("[data-env-open=needs]")
        await pg.fill(".env-body [data-new-name]", "Tax"); await pg.fill(".env-body [data-new-amt]", "1500")
        await pg.locator(".env-body [data-add-line-btn]").click(delay=250); await pg.wait_for_timeout(200)
        assert "Tax" in await text(pg, ".env-body"), f"{w}px: Tax line not shown right after Add"
        assert any(e["name"] == "Tax" and e["amount"] == 1500 and e["env"] == "needs" for e in (await state(pg))["expenses"])
        await pg.reload(); await pg.wait_for_timeout(400)
        await pg.click("[data-env-open=needs]"); assert "Tax" in await text(pg, ".env-body"), "Tax line lost after reload"
        await pg.close()
    pg = await open_app(ctx)  # Enter key adds too
    await pg.click("[data-env-open=misc]")
    await pg.fill(".env-body [data-new-name]", "Gym"); await pg.press(".env-body [data-new-name]", "Enter")
    await pg.keyboard.type("40"); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(200)
    assert "Gym" in await text(pg, ".env-body")

@test
async def legal_links_present(ctx):
    pg = await open_app(ctx)
    await tab(pg, "plan")
    hrefs = await pg.eval_on_selector_all(".legal-links a", "a => a.map(x => x.href)")
    assert any(h.endswith("/privacy.html") for h in hrefs) and any(h.endswith("/terms.html") for h in hrefs)
    root = os.path.join(HERE, "..", "src", "legal")
    for f in ("privacy.html", "terms.html"):
        body = open(os.path.join(root, f), encoding="utf-8").read()
        assert "—" not in body and "–" not in body, f"{f} has a long dash"
        p2 = await ctx.new_page(); await p2.goto("file://" + os.path.abspath(os.path.join(root, f)))
        assert await p2.locator("h1").count() == 1
        sw = await p2.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert sw, f"{f} scrolls sideways"
        await p2.close()

# ---------------- subs ----------------
@test
async def subs_flags_keep_drop_used(ctx):
    pg = await open_app(ctx); await tab(pg, "subs")
    sav0 = await pg.evaluate("0")
    row = pg.locator("[data-sub]", has_text="Hulu Premium")
    assert "Unused for" in await row.inner_text()
    await row.locator("[data-keep=drop]").click(); await pg.wait_for_timeout(100)
    st = await state(pg); assert [s for s in st["subs"] if s["name"] == "Hulu Premium"][0]["keep"] == "drop"
    await tab(pg, "month"); legend_misc = money(re.findall(r"Misc \$[\d,.]+", await text(pg, ".legend"))[0])
    await tab(pg, "subs")
    await pg.locator("[data-sub]", has_text="Hulu Premium").locator("[data-keep=auto]").click()
    await tab(pg, "month"); assert abs(money(re.findall(r"Misc \$[\d,.]+", await text(pg, ".legend"))[0]) - (legend_misc + 18.99)) < 0.02
    await tab(pg, "subs")
    row = pg.locator("[data-sub]", has_text="Planet Fitness")
    await row.locator("[data-used]").click(); await pg.wait_for_timeout(100)
    assert "Unused for" not in await pg.locator("[data-sub]", has_text="Planet Fitness").inner_text()

@test
async def subs_rule_days_add_remove(ctx):
    pg = await open_app(ctx); await tab(pg, "subs")
    await pg.fill("#rule-days", "100"); await pg.wait_for_timeout(100)
    assert "Unused for" not in await text(pg, "[data-out=subsList]")
    await pg.click("details summary >> text=Add a subscription")
    f = pg.locator("form[data-form=addSub]")
    await f.locator("[name=name]").fill("YouTube Premium"); await f.locator("[name=price]").fill("13.99")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(120)
    assert "YouTube Premium" in await text(pg, "[data-out=subsList]")
    await pg.locator("[data-sub]", has_text="YouTube Premium").locator("[data-del-sub]").click(); await pg.wait_for_timeout(100)
    assert "YouTube Premium" not in await text(pg, "[data-out=subsList]")

# ---------------- cheaper ----------------
@test
async def cheaper_swap_changes_month(ctx):
    pg = await open_app(ctx)
    sav0 = money(await text(pg, ".big"))
    await tab(pg, "cheaper")
    row = pg.locator("[data-swap]", has_text="Meal kit")
    save = money(await row.locator(".good").first.inner_text())
    await row.locator("[data-swap-on]").click(); await pg.wait_for_timeout(100)
    await tab(pg, "month"); assert abs(money(await text(pg, ".big")) - (sav0 + save)) < 0.02
    await tab(pg, "cheaper")
    inp = pg.locator("[data-swap]", has_text="Meal kit").locator("[data-alt]")
    await inp.click(); await inp.press("Control+a"); await pg.keyboard.type("100", delay=30); await pg.wait_for_timeout(100)
    assert await pg.evaluate("document.activeElement.dataset.alt") == "w1", "cost box lost focus while typing"
    assert await inp.input_value() == "100"
    await tab(pg, "month"); assert abs(money(await text(pg, ".big")) - (sav0 + 335.74 - 100)) < 0.02

@test
async def cheaper_add_and_remove(ctx):
    pg = await open_app(ctx); await tab(pg, "cheaper")
    await pg.click("text=Add your own comparison")
    f = pg.locator("form[data-form=addSwap]")
    await f.locator("[name=link]").select_option("expense:groc")
    await f.locator("[name=alt]").fill("Aldi"); await f.locator("[name=altCost]").fill("400")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(100)
    row = pg.locator("[data-swap]", has_text="Aldi"); assert await row.count() == 1
    assert "$120" in await row.inner_text()
    await row.locator("[data-del-swap]").click(); await pg.wait_for_timeout(100)
    assert await pg.locator("[data-swap]", has_text="Aldi").count() == 0

# ---------------- codes ----------------
@test
async def codes_search_vote_add(ctx):
    pg = await open_app(ctx); await tab(pg, "codes")
    await pg.fill("#code-q", "nike"); await pg.wait_for_timeout(80)
    assert await pg.locator("[data-code]").count() == 1
    await pg.fill("#code-q", "zzz"); await pg.wait_for_timeout(80)
    assert "No codes" in await text(pg, "[data-out=codeList]")
    await pg.fill("#code-q", "")
    row = pg.locator("[data-code]", has_text="Best Buy")
    await row.locator("[data-vote=worked]").click(); await pg.wait_for_timeout(80)
    assert [c for c in (await state(pg))["codes"] if c["store"] == "Best Buy"][0]["worked"] == 2
    await pg.click("text=Add a code you found")
    f = pg.locator("form[data-form=addCode]")
    await f.locator("[name=store]").fill("Zara"); await f.locator("[name=code]").fill("ZARA15")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(100)
    row = pg.locator("[data-code]", has_text="Zara"); assert "Added by you" in await row.inner_text()
    await row.locator("[data-del-code]").click(); await pg.wait_for_timeout(80)
    assert await pg.locator("[data-code]", has_text="Zara").count() == 0

# ---------------- plan ----------------
@test
async def plan_envelopes_lines_priority(ctx):
    pg = await open_app(ctx); await tab(pg, "plan")
    await pg.fill("[data-env=needs]", "70"); await pg.wait_for_timeout(80)
    assert "add up to 110%" in await text(pg, "[data-out=envCheck]")
    await pg.fill("[data-env=needs]", "60"); await pg.wait_for_timeout(80)
    assert "Adds up to 100%" in await text(pg, "[data-out=envCheck]")
    n0 = await pg.locator("[data-exp]").count()
    await pg.click("[data-add-exp]"); await pg.wait_for_timeout(100)
    assert await pg.locator("[data-exp]").count() == n0 + 1
    await pg.locator("[data-exp]").last.locator("[data-del-exp]").click(); await pg.wait_for_timeout(100)
    assert await pg.locator("[data-exp]").count() == n0
    await pg.select_option("select[data-bind=priority]", "goal"); await pg.wait_for_timeout(80)
    t = await text(pg, "[data-out=saveSplit]"); assert "to New laptop" in t
    assert abs(money(t.split("emergency fund, ")[1]) - 1200) < 0.01, t

@test
async def plan_reset_confirm_flow(ctx):
    pg = await open_app(ctx); await tab(pg, "plan")
    await pg.click("[data-reset=blank]"); await pg.click("[data-reset-no]")
    assert (await state(pg) or {}).get("income", 5200) == 5200
    await pg.click("[data-reset=blank]"); await pg.click("[data-reset-yes=blank]"); await pg.wait_for_timeout(250)
    st = await state(pg); assert st["income"] == 0 and st["expenses"] == [] and st["splits"] == []
    await pg.click("[data-reset=example]"); await pg.click("[data-reset-yes=example]"); await pg.wait_for_timeout(250)
    assert (await state(pg))["income"] == 5200

# ---------------- split (on this phone) ----------------
@test
async def split_balances_math(ctx):
    pg = await open_app(ctx); await tab(pg, "split")
    t = await text(pg, "[data-out=splitSum] .summary3")
    assert "You're owed $83" in t and "You owe $73.50" in t and "$9.50" in t, t

@test
async def split_new_equal_percent_exact_borrow(ctx):
    pg = await open_app(ctx); await tab(pg, "split")
    async def new(title, amount, method, parts, vals=None, paid=None, borrower=None):
        await pg.click("[data-new-split]")
        await pg.fill("[data-d=title]", title); await pg.fill("[data-d=amount]", amount)
        if paid: await pg.select_option("[data-d=paidBy]", paid); await pg.wait_for_timeout(60)
        await pg.select_option("[data-d=method]", method); await pg.wait_for_timeout(60)
        if method == "borrow":
            if borrower: await pg.select_option("[data-d=borrower]", borrower)
        else:
            for p in parts:
                await pg.click("[data-part-search]"); await pg.wait_for_timeout(60)
                await pg.click(f"[data-part-add={p}]"); await pg.wait_for_timeout(60)
            for p, v in (vals or {}).items(): await pg.fill(f"[data-part-val={p}]", v)
        await pg.click("form[data-form=split] button[type=submit]"); await pg.wait_for_timeout(120)
    # validation
    await pg.click("[data-new-split]"); await pg.click("form[data-form=split] button[type=submit]")
    assert "Say what" in await text(pg, ".err")
    await pg.click("[data-cancel-split]")
    await new("Tacos", "30", "equal", ["p1", "p5"])  # 3 people, 10 each
    owed = money(re.search(r"You're owed (\$[\d,.]+)", await text(pg, "[data-out=splitSum]")).group(1))
    assert abs(owed - 103) < 0.01, owed
    await new("Gift", "100", "percent", ["p1"], {"me": "50", "p1": "40"})
    assert "Percentages add up to 90%" in await text(pg, ".err")
    await pg.fill("[data-part-val=me]", "60"); await pg.click("form[data-form=split] button[type=submit]"); await pg.wait_for_timeout(120)
    await new("Bills", "50", "exact", ["p6"], {"me": "20", "p6": "20"})
    assert "Amounts add up to $40, not $50" in await text(pg, ".err")
    await pg.fill("[data-part-val=p6]", "30"); await pg.click("form[data-form=split] button[type=submit]"); await pg.wait_for_timeout(120)
    await new("Loan", "25", "borrow", [], borrower="p2")
    st = await state(pg)
    titles = [x["title"] for x in st["splits"]]
    assert all(t in titles for t in ["Tacos", "Gift", "Bills", "Loan"]), titles
    t = await text(pg, "[data-out=splitSum]")
    assert "Dad owes you $25" in t and "Priya owes you $42" in t, t

@test
async def split_edit_delete_filter(ctx):
    pg = await open_app(ctx); await tab(pg, "split")
    card = pg.locator("[data-split]", has_text="Dominos")
    await card.locator("[data-edit-split]").click(); await pg.wait_for_timeout(100)
    assert await pg.inner_text("form[data-form=split] h2") == "Edit split"
    await pg.fill("[data-d=amount]", "160"); await pg.click("form[data-form=split] button[type=submit]"); await pg.wait_for_timeout(120)
    assert "Alex owes you $40" in await text(pg, "[data-split]:has-text('Dominos')")
    assert len((await state(pg))["splits"]) == 5
    await pg.click("[data-filter=Borrow]"); await pg.wait_for_timeout(80)
    assert await pg.locator("[data-split]").count() == 1
    await pg.click("[data-filter=All]")
    await pg.locator("[data-split]", has_text="Movie tickets").locator("[data-del-split]").click(); await pg.wait_for_timeout(100)
    assert await pg.locator("[data-split]", has_text="Movie tickets").count() == 0

@test
async def split_settle_history_undo_edit(ctx):
    pg = await open_app(ctx); await tab(pg, "split")
    before = await text(pg, "[data-out=splitSum] .summary3")
    await pg.locator("[data-settle]", has_text="Jordan").locator("[data-settle-btn]").click(); await pg.wait_for_timeout(100)
    assert "You owe Jordan" not in await text(pg, "[data-out=splitSum]")
    assert "You paid Jordan $37.50" in await text(pg, "#history")
    await pg.click("#history [data-pay-edit]"); await pg.wait_for_timeout(80)
    fit = await pg.evaluate("(()=>{const d=document.querySelector('[data-pay-date]').getBoundingClientRect(),row=document.querySelector('#history .row').getBoundingClientRect(),a=document.querySelector('[data-pay-amt]').getBoundingClientRect();return {dr:d.right,rr:row.right,dh:d.height,ah:a.height}})()")
    assert fit["dr"] <= fit["rr"] + 0.5 and abs(fit["dh"] - fit["ah"]) <= 2, f"date box overflows or mismatched: {fit}"
    await pg.click("#history [data-pay-cancel]"); await pg.wait_for_timeout(80)
    await pg.click("#history [data-pay-edit]"); await pg.fill("[data-pay-amt]", "10"); await pg.click("[data-pay-save]"); await pg.wait_for_timeout(100)
    assert "You owe Jordan $27.50" in await text(pg, "[data-out=splitSum]")
    await pg.click("#history [data-pay-edit]"); await pg.wait_for_timeout(80)
    assert "Not paid, put it back" in await text(pg, "#history")
    await pg.click("#history [data-pay-del]"); await pg.wait_for_timeout(100)
    assert await pg.inner_text("#toast") == "Back in the list: you owe Jordan $37.50."
    assert await pg.locator("[data-settle]", has_text="Jordan").locator("[data-settle-btn]").inner_text() == "Paid"
    assert await text(pg, "[data-out=splitSum] .summary3") == before
    assert "No payments recorded yet" in await text(pg, "#history")

@test
async def split_people_add_remove_import(ctx):
    pg = await open_app(ctx); await tab(pg, "split")
    await pg.click("[data-add-person-open]"); await pg.fill("#new-person", "Zoe"); await pg.click("form[data-form=addPerson] button[type=submit]"); await pg.wait_for_timeout(100)
    assert any(p["name"] == "Zoe" for p in (await state(pg))["people"])
    await pg.locator("[data-person]", has_text="Alex").locator("[data-person-open]").click(); await pg.wait_for_timeout(60)
    assert "Owes you $21.50" in await pg.locator("[data-person]", has_text="Alex").inner_text()
    await pg.locator("[data-person]", has_text="Alex").locator("[data-del-person]").click()
    assert await pg.inner_text("#toast") == "Alex still owes you $21.50. Settle up first."
    # settled people can be removed; their past splits keep the name
    await pg.locator("[data-settle]", has_text="Priya").locator("[data-settle-btn]").click(); await pg.wait_for_timeout(100)
    await pg.locator("[data-person]", has_text="Priya").locator("[data-person-open]").click(); await pg.wait_for_timeout(60)
    assert "Settled up" in await pg.locator("[data-person]", has_text="Priya").inner_text()
    await pg.locator("[data-person]", has_text="Priya").locator("[data-del-person]").click(); await pg.wait_for_timeout(100)
    assert await pg.inner_text("#toast") == "Removed Priya. Past splits still show their name."
    assert await pg.locator("[data-person]", has_text="Priya").count() == 0
    assert "Priya owes you $12" in await text(pg, "[data-split]:has-text('Team lunch')")
    await pg.click("[data-new-split]"); await pg.wait_for_timeout(80)
    await pg.fill("[data-part-search]", "pri"); await pg.wait_for_timeout(80)
    assert await pg.locator("[data-part-add=p6]").count() == 0, "removed person not offered in new splits"
    await pg.click("[data-cancel-split]")
    await pg.click("[data-add-person-open]"); await pg.fill("#new-person", "priya"); await pg.click("form[data-form=addPerson] button[type=submit]"); await pg.wait_for_timeout(100)
    assert await pg.locator("[data-person]", has_text="Priya").count() == 1, "adding the name again brings them back"
    await pg.locator("[data-person]", has_text="Zoe").locator("[data-person-open]").click(); await pg.wait_for_timeout(60)
    await pg.locator("[data-person]", has_text="Zoe").locator("[data-del-person]").click(); await pg.wait_for_timeout(100)
    assert not any(p["name"] == "Zoe" for p in (await state(pg))["people"])
    vcf = os.path.join(TMP, "c.vcf")
    open(vcf, "w").write("BEGIN:VCARD\nVERSION:3.0\nFN:Omar Khan\nEND:VCARD\nBEGIN:VCARD\nFN:Alex\nEND:VCARD\n")
    await pg.set_input_files("#vcf", vcf); await pg.wait_for_timeout(200)
    st = await state(pg)
    assert [c["n"] for c in st["contacts"]] == ["Alex", "Omar Khan"] and not any(p["name"] == "Omar Khan" for p in st["people"]), "a contacts file fills the search, not the People list"

# ---------------- shared circle + notifications (mocked Claude storage) ----------------
@test
async def shared_off_shows_setup(ctx):
    pg = await open_app(ctx); await tab(pg, "split")
    await pg.click("[data-mode=shared]"); await pg.wait_for_timeout(100)
    assert "Friend sync is coming to the app" in await text(pg, "#view")  # standalone app, no Claude storage
    assert await pg.evaluate("document.getElementById('bell').hidden")
    await pg.close()
    pg = await ctx.new_page(); await pg.add_init_script("window.claude = {use: async () => null}")  # in Claude but signed out
    await pg.goto(URL); await pg.wait_for_timeout(400); await tab(pg, "split")
    await pg.click("[data-mode=shared]"); await pg.wait_for_timeout(150)
    assert "Share splits with friends" in await text(pg, "#view")

@test
async def shared_join_notify_inbox(ctx):
    pg = await open_app(ctx, mock=True)
    await pg.evaluate("__mock.db.doc('members/u_alex').set({joinedAt:1}); __mock.db.doc('members/u_sam').set({joinedAt:1});")
    await tab(pg, "split"); await pg.click("[data-mode=shared]"); await pg.wait_for_timeout(250)
    assert "members/u_me" in await pg.evaluate("[...__mock.store.keys()]")
    await pg.evaluate("__mock.db.doc('splits/abc').set({title:'Pizza night',amount:60,tag:'Dinner',paidBy:'u_alex',method:'equal',parts:{u_me:1,u_alex:1,u_sam:1},date:'2026-09-29',createdBy:'u_alex',createdAt:Date.now()})")
    await pg.wait_for_timeout(300)
    assert await pg.inner_text("#toast") == "Alex added you to “Pizza night”"
    assert await pg.inner_text("#bell-n") == "1"
    assert "You owe Alex $20" in await text(pg, "[data-out=splitSum]")
    # a split that doesn't involve me must not notify
    await pg.evaluate("__mock.db.doc('splits/xyz').set({title:'Their lunch',amount:10,tag:'Lunch',paidBy:'u_alex',method:'equal',parts:{u_alex:1,u_sam:1},createdBy:'u_alex',createdAt:Date.now()})")
    await pg.wait_for_timeout(250); assert await pg.inner_text("#bell-n") == "1"
    # friend edits it
    await pg.evaluate("__mock.db.doc('splits/abc').update({amount:90,updatedBy:'u_alex',updatedAt:Date.now()+5})")
    await pg.wait_for_timeout(250)
    assert "edited" in await pg.inner_text("#toast")
    await pg.click("#bell"); await pg.wait_for_timeout(250)
    v = await text(pg, "#view"); assert "Notifications" in v and "Pizza night" in v and "New" in v, v
    assert await pg.evaluate("document.getElementById('bell-n').hidden")
    st = await pg.evaluate("__mock.store.get('data/users/u_me/state')"); assert st and st["lastSeen"] > 0
    await pg.click("[data-go-split]"); await pg.wait_for_timeout(200)
    assert "You owe Alex $30" in await text(pg, "[data-out=splitSum]")

@test
async def shared_my_writes_go_to_db(ctx):
    pg = await open_app(ctx, mock=True)
    await pg.evaluate("__mock.db.doc('members/u_sam').set({joinedAt:1});")
    await tab(pg, "split"); await pg.click("[data-mode=shared]"); await pg.wait_for_timeout(250)
    await pg.click("[data-new-split]"); await pg.fill("[data-d=title]", "Cab"); await pg.fill("[data-d=amount]", "20")
    await pg.click("[data-part-search]"); await pg.click("[data-part-add=u_sam]"); await pg.wait_for_timeout(80)
    assert await pg.locator("[data-part-new]").count() == 0
    await pg.click("form[data-form=split] button[type=submit]"); await pg.wait_for_timeout(250)
    splits = await pg.evaluate("[...__mock.store.entries()].filter(([k])=>k.startsWith('splits/')).map(([k,v])=>v)")
    assert len(splits) == 1 and splits[0]["createdBy"] == "u_me" and splits[0]["parts"] == {"u_me": 1, "u_sam": 1}, splits
    assert "Sam owes you $10" in await text(pg, "[data-out=splitSum]")
    await pg.locator("[data-settle]", has_text="Sam").locator("[data-settle-btn]").click(); await pg.wait_for_timeout(250)
    pays = await pg.evaluate("[...__mock.store.entries()].filter(([k])=>k.startsWith('payments/')).map(([k,v])=>v)")
    assert len(pays) == 1 and pays[0]["from"] == "u_sam" and pays[0]["to"] == "u_me", pays
    await pg.click("#history [data-pay-del]"); await pg.wait_for_timeout(250)
    assert "Sam owes you $10" in await text(pg, "[data-out=splitSum]")
    await pg.locator("[data-split]", has_text="Cab").locator("[data-del-split]").click(); await pg.wait_for_timeout(250)
    assert (await pg.evaluate("[...__mock.store.entries()].find(([k])=>k.startsWith('splits/'))[1].deleted")) is True
    assert await pg.locator("[data-split]", has_text="Cab").count() == 0
    assert (await state(pg))["splits"][0]["title"] == "Dominos", "local splits untouched"

# ---------------- bank statement import ----------------
FIX = os.path.join(HERE, "fixtures")

async def check_statement_review(pg):
    v = await text(pg, "#view")
    assert "Your statement" in v, v[:200]
    assert "Acme Corp" in v and "$4,200/mo" in v and "usually on the 25th" in v, "salary and payday"
    for name in ["Netflix", "Spotify", "Planet Fitness", "Adobe Creative", "iCloud", "Disney Plus"]:
        assert name.lower() in v.lower(), f"subscription {name} missing"
    assert "Paying since Apr 2026 · 6 charges · $107.94 so far" in v, "Netflix history"
    assert "Paying since Jun 2026 · 4 charges" in v, "Disney+ history"
    for bill in ["Rent Oakview", "Con Ed", "Verizon Wireless", "Geico Auto"]:
        assert bill.lower() in v.lower(), f"bill {bill} missing"
    assert "$700 in this statement" in v, "tax payments"
    assert "Groceries" in v and "Eating out" in v and "Getting around" in v, "spending categories"
    assert "Zelle" not in v, "transfers must not count as income"
    return v

@test
async def import_csv_statement_and_apply(ctx):
    pg = await open_app(ctx)
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement.csv")); await pg.wait_for_timeout(500)
    await check_statement_review(pg)
    await pg.click("[data-import-apply=replace]"); await pg.wait_for_timeout(300)
    st = await state(pg)
    assert st["income"] == 4200 and st["payday"] == 25, (st["income"], st.get("payday"))
    names = [s["name"] for s in st["subs"]]
    assert "Netflix" in names and len(names) == 6, names
    nf = [s for s in st["subs"] if s["name"] == "Netflix"][0]
    assert nf["charges"] == 6 and nf["since"] == "2026-04-05" and nf["last"] is None
    leg = await text(pg, ".legend"); needs, misc, sav = [money(x) for x in re.findall(r"\$[\d,.]+", leg)]
    assert abs(4200 - needs - misc - sav) < 0.05, leg
    await tab(pg, "subs"); sl = await text(pg, "[data-out=subsList]")
    assert "Usage not checked yet" in sl and "Paying since" in sl
    assert "Unused for" not in sl, "unknown usage must not be flagged as unused"

@test
async def import_pdf_statement(ctx):
    pg = await open_app(ctx)
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement.pdf")); await pg.wait_for_timeout(3000)
    await check_statement_review(pg)
    await pg.click("[data-import-apply=merge]"); await pg.wait_for_timeout(300)
    st = await state(pg)
    assert st["income"] == 5200, "merge keeps existing income"
    assert any(s["name"] == "Netflix" and s.get("charges") == 6 for s in st["subs"]), "merge updates history on matching subscription"

@test
async def import_rejects_bad_files(ctx):
    pg = await open_app(ctx)
    bad = os.path.join(TMP, "bad.csv"); open(bad, "w").write("hello,world\n1,2\n")
    await pg.set_input_files("#stmt", bad); await pg.wait_for_timeout(300)
    assert "header row" in await pg.inner_text("#toast")
    assert "Your statement" not in await text(pg, "#view")

@test
async def subscription_check_in(ctx):
    pg = await open_app(ctx)
    card = pg.locator("[data-out=reviewCard] .review"); assert await card.count() == 1
    name = re.search(r"use (.+)\?", await card.inner_text()).group(1)
    await card.locator("[data-review=barely]").click(); await pg.wait_for_timeout(120)
    s = [x for x in (await state(pg))["subs"] if x["name"] == name][0]
    assert s["low"] is True and s["reviewedAt"]
    await tab(pg, "subs")
    assert "You said you barely use it" in await pg.locator(f"[data-sub={s['id']}]").inner_text()
    await tab(pg, "month")
    name2 = re.search(r"use (.+)\?", await pg.locator("[data-out=reviewCard] .review").inner_text()).group(1)
    assert name2 != name, "a reviewed subscription is not asked again"
    await pg.click("[data-out=reviewCard] [data-review=none]"); await pg.wait_for_timeout(120)
    assert [x for x in (await state(pg))["subs"] if x["name"] == name2][0]["keep"] == "drop"
    await pg.click("[data-out=reviewCard] [data-review=later]"); await pg.wait_for_timeout(120)
    assert await pg.locator("[data-out=reviewCard] .review").count() == 0

# ---------------- add a line keeps what was typed ----------------
@test
async def add_line_survives_tapping_away(ctx):
    pg = await open_app(ctx)
    await pg.click("[data-env-open=needs]"); await pg.wait_for_timeout(200)
    box = pg.locator("[data-add-line=needs]")
    await box.locator("[data-new-name]").click(); await pg.keyboard.type("Tax")
    await box.locator("[data-new-amt]").click(); await pg.keyboard.type("1500")
    # tap somewhere empty (or close the phone keyboard): the list redraws
    await pg.evaluate("document.activeElement.blur()"); await pg.wait_for_timeout(250)
    assert await box.locator("[data-new-name]").input_value() == "Tax", "typed name was wiped by a redraw"
    assert await box.locator("[data-new-amt]").input_value() == "1500", "typed amount was wiped by a redraw"
    await box.locator("[data-add-line-btn]").click(); await pg.wait_for_timeout(250)
    tax = [e for e in (await state(pg))["expenses"] if e["name"] == "Tax"]
    assert tax and tax[0]["amount"] == 1500 and tax[0]["env"] == "needs"
    assert "Tax" in await pg.locator("[data-out=envelopes]").inner_text()
    assert await box.locator("[data-new-name]").input_value() == "", "box clears after adding"
    await pg.reload(); await pg.wait_for_timeout(400)
    await pg.click("[data-env-open=needs]"); await pg.wait_for_timeout(200)
    assert "Tax" in await pg.locator("[data-out=envelopes]").inner_text(), "Tax is still there after reload"

# ---------------- legal ----------------
@test
async def legal_links_and_pages(ctx):
    pg = await open_app(ctx)
    await tab(pg, "plan")
    hrefs = await pg.eval_on_selector_all(".legal-links a", "as => as.map(a => a.href)")
    assert any(h.endswith("/privacy.html") for h in hrefs) and any(h.endswith("/terms.html") for h in hrefs), hrefs
    legal = os.path.join(HERE, "..", "src", "legal")
    for f, must in [("privacy.html", "Privacy Policy"), ("terms.html", "Terms of Use")]:
        body = open(os.path.join(legal, f), encoding="utf-8").read()
        assert must in body and "\u2014" not in body and "\u2013" not in body, f
        lp = await ctx.new_page(); await lp.goto("file://" + os.path.abspath(os.path.join(legal, f)))
        assert must in await lp.inner_text("h1")
        w = await lp.evaluate("[document.documentElement.scrollWidth, innerWidth]")
        await lp.set_viewport_size({"width": 320, "height": 640}); await lp.wait_for_timeout(100)
        w = await lp.evaluate("[document.documentElement.scrollWidth, innerWidth]")
        assert w[0] <= w[1], f"{f} scrolls sideways at 320px"
        await lp.close()

# ---------------- accounts ----------------
async def fs_docs(pg): return await pg.evaluate("JSON.parse(localStorage.getItem('__mock_fs') || '{}')")
async def open_account(pg):
    await pg.click("#acct-btn"); await pg.wait_for_timeout(250)
async def acc_err(pg): return await text(pg, "[data-out=accErr]")

@test
async def account_coming_soon_without_project(ctx):
    pg = await open_app(ctx)
    await open_account(pg)
    assert "Accounts are coming soon" in await text(pg, "#view")
    await pg.click("[data-close-account]"); await pg.wait_for_timeout(120)
    assert await pg.locator("[data-out=hero]").count() + await pg.locator("#m-income").count() > 0, "Done returns to the tab"

@test
async def account_in_claude_preview_points_to_website(ctx):
    pg = await open_app(ctx, mock=True, preview=True)
    await open_account(pg)
    v = await text(pg, "#view")
    assert "Sign in on the KeepWise website" in v and "Continue with Google" not in v
    assert await pg.get_attribute("#view a.btn.primary", "href") == "https://chillwillpill.github.io/keepwise/"
    assert await pg.evaluate("typeof window.firebase") == "undefined", "no sign-in code loaded in the preview"

@test
async def account_email_signup_and_profile(ctx):
    pg = await open_app(ctx, fb=True)
    await open_account(pg)
    v = await text(pg, "#view")
    assert "Continue with Google" in v and "Your budget, statements and subscriptions still stay on this phone" in v
    await pg.click("[data-acc-mode=create]"); await pg.wait_for_timeout(120)
    await pg.click("[data-form=acc-email] [type=submit]"); await pg.wait_for_timeout(120)
    assert "valid email" in await acc_err(pg)
    await pg.fill("#acc-email", "ada@example.com"); await pg.fill("#acc-pass", "short")
    await pg.click("[data-form=acc-email] [type=submit]"); await pg.wait_for_timeout(120)
    assert "at least 8" in await acc_err(pg)
    assert await pg.input_value("#acc-email") == "ada@example.com", "email kept after an error"
    await pg.fill("#acc-pass", "longenough1"); await pg.click("[data-form=acc-email] [type=submit]"); await pg.wait_for_timeout(400)
    assert await pg.evaluate("window.__mockMail.some(m => m.type === 'verify' && m.to === 'ada@example.com')"), "verification email sent"
    v = await text(pg, "#view")
    assert "Finish your profile" in v and "Verify your email" in v
    f = "[data-form=acc-profile]"
    assert not await pg.is_checked(f + " [name=marketing]"), "marketing opt-in starts unticked"
    await pg.fill(f + " [name=name]", "Ada Brook")
    await pg.click(f + " [type=submit]"); await pg.wait_for_timeout(120)
    assert "date of birth" in await acc_err(pg)
    await pg.fill(f + " [name=dob]", "2012-05-01"); await pg.click(f + " [type=submit]"); await pg.wait_for_timeout(120)
    assert "18 or older" in await acc_err(pg)
    await pg.fill(f + " [name=dob]", "1994-03-12"); await pg.fill(f + " [name=phone]", "call me")
    await pg.click(f + " [type=submit]"); await pg.wait_for_timeout(120)
    assert "valid phone" in await acc_err(pg)
    await pg.fill(f + " [name=phone]", "+44 7700 900123"); await pg.fill(f + " [name=city]", "Leeds")
    await pg.click(f + " [type=submit]"); await pg.wait_for_timeout(120)
    assert "agree to the Terms" in await acc_err(pg)
    assert await pg.input_value(f + " [name=name]") == "Ada Brook", "typed profile kept after an error"
    await pg.check(f + " [name=consent]"); await pg.click(f + " [type=submit]"); await pg.wait_for_timeout(400)
    d = (await fs_docs(pg))["users/u1"]
    assert d["name"] == "Ada Brook" and d["dob"] == "1994-03-12" and d["city"] == "Leeds" and d["phone"] == "+44 7700 900123"
    assert d["phoneVerified"] is False and d["marketing"] is False and d["termsAcceptedAt"] and d["termsVersion"]
    v = await text(pg, "#view")
    assert "Email not verified" in v and "Not yet verified" in v and "Save changes" in v
    assert (await pg.inner_text("#acct-btn")).strip() == "AB", "header shows the initials"
    await pg.evaluate("window.__mockVerify('ada@example.com')")
    await pg.click("[data-acc-verified]"); await pg.wait_for_timeout(300)
    assert "Email verified" in await text(pg, "#view")
    await pg.check(f + " [name=marketing]"); await pg.click(f + " [type=submit]"); await pg.wait_for_timeout(300)
    d = (await fs_docs(pg))["users/u1"]; assert d["marketing"] is True and d["marketingUpdatedAt"] and d["emailVerified"] is True
    await pg.reload(); await pg.wait_for_timeout(700)
    assert (await pg.inner_text("#acct-btn")).strip() == "AB", "still signed in after reopening"
    assert "users/u1" in await fs_docs(pg) and "income" not in (await fs_docs(pg))["users/u1"], "money data is not in the account"

@test
async def account_sign_in_errors_and_reset(ctx):
    pg = await open_app(ctx, fb=True)
    await open_account(pg)
    await pg.fill("#acc-email", "nobody@example.com"); await pg.fill("#acc-pass", "wrongpass1")
    await pg.click("[data-form=acc-email] [type=submit]"); await pg.wait_for_timeout(250)
    assert "incorrect" in await acc_err(pg)
    await pg.click("[data-acc-mode=reset]"); await pg.wait_for_timeout(120)
    assert await pg.locator("#acc-pass").count() == 0 and await pg.input_value("#acc-email") == "nobody@example.com"
    await pg.click("[data-form=acc-email] [type=submit]"); await pg.wait_for_timeout(250)
    assert await pg.evaluate("window.__mockMail.some(m => m.type === 'reset')")
    assert await pg.locator("[data-acc-mode=signin][aria-pressed=true]").count() == 1, "back on sign in after the reset email"

@test
async def account_google_signout_and_delete(ctx):
    pg = await open_app(ctx, fb=True)
    await open_account(pg)
    await pg.click("[data-acc-google]"); await pg.wait_for_timeout(400)
    f = "[data-form=acc-profile]"
    assert await pg.input_value(f + " [name=name]") == "Gina Park", "name comes from Google"
    assert "Verify your email" not in await text(pg, "#view"), "Google emails are already verified"
    await pg.fill(f + " [name=dob]", "1990-07-04"); await pg.check(f + " [name=consent]")
    await pg.click(f + " [type=submit]"); await pg.wait_for_timeout(400)
    assert (await fs_docs(pg))["users/g1"]["provider"] == "google.com"
    await pg.click("[data-acc-plus]"); await pg.wait_for_timeout(300)
    d = (await fs_docs(pg))["users/g1"]; assert d["plusInterest"] is True and d["plusInterestAt"]
    assert "on the waitlist" in await text(pg, "#view")
    await pg.click("[data-acc-plus-off]"); await pg.wait_for_timeout(300)
    assert (await fs_docs(pg))["users/g1"]["plusInterest"] is False and await pg.locator("[data-acc-plus]").count() == 1
    await pg.click("[data-acc-signout]"); await pg.wait_for_timeout(300)
    assert "Continue with Google" in await text(pg, "#view")
    await pg.click("[data-acc-google]"); await pg.wait_for_timeout(400)
    assert "Save changes" in await text(pg, "#view"), "a finished profile opens straight away"
    await pg.click("[data-acc-delete]"); await pg.wait_for_timeout(120)
    await pg.click("[data-acc-delete-no]"); await pg.wait_for_timeout(120)
    assert "users/g1" in await fs_docs(pg)
    await pg.click("[data-acc-delete]"); await pg.wait_for_timeout(120)
    await pg.click("[data-acc-delete-yes]"); await pg.wait_for_timeout(400)
    assert "users/g1" not in await fs_docs(pg), "profile erased"
    assert "Continue with Google" in await text(pg, "#view")

@test
async def account_screens_fit_small_phones(ctx):
    for scheme in ["light", "dark"]:
        pg = await open_app(ctx, fb=True, w=320, h=640, scheme=scheme)
        await open_account(pg)
        await pg.click("[data-acc-mode=create]"); await pg.wait_for_timeout(120)
        sw = await pg.evaluate("[document.documentElement.scrollWidth, innerWidth, document.querySelector('#main').scrollWidth, document.querySelector('#main').clientWidth]")
        assert sw[0] <= sw[1] and sw[2] <= sw[3], f"sign-in overflows at 320px: {sw}"
        await pg.click("[data-acc-google]"); await pg.wait_for_timeout(400)
        f = "[data-form=acc-profile]"
        await pg.fill(f + " [name=dob]", "1990-07-04"); await pg.check(f + " [name=consent]"); await pg.click(f + " [type=submit]"); await pg.wait_for_timeout(400)
        sw = await pg.evaluate("[document.documentElement.scrollWidth, innerWidth, document.querySelector('#main').scrollWidth, document.querySelector('#main').clientWidth]")
        assert sw[0] <= sw[1] and sw[2] <= sw[3], f"profile overflows at 320px: {sw}"
        await pg.screenshot(path=os.path.join(os.environ.get("SHOT_DIR", TMP), f"account-{scheme}.png"), full_page=False)
        await pg.click("[data-acc-delete]"); await pg.click("[data-acc-delete-yes]"); await pg.wait_for_timeout(300)
        await pg.close()

@test
async def logo_goes_back_to_month(ctx):
    pg = await open_app(ctx)
    await tab(pg, "codes"); await pg.click("#acct-btn"); await pg.wait_for_timeout(200)
    await pg.click("#home-link"); await pg.wait_for_timeout(200)
    assert await pg.locator("[data-tab=month][aria-current=page]").count() == 1 and await pg.locator("#m-income").count() == 1
    assert (await state(pg))["tab"] == "month"

@test
async def receipt_photo_is_a_plus_feature(ctx):
    pg = await open_app(ctx)
    await tab(pg, "split")
    if await pg.locator("[data-mode=local]").count(): await pg.click("[data-mode=local]"); await pg.wait_for_timeout(120)
    await pg.click("[data-new-split]"); await pg.wait_for_timeout(150)
    b = pg.locator("[data-receipt-plus]")
    assert await b.count() == 1 and "Plus" in await b.inner_text()
    await pg.fill("[data-d=title]", "Dinner")
    await b.click(); await pg.wait_for_timeout(150)
    note = await text(pg, ".receipt-note")
    assert "Receipt photos come with KeepWise Plus" in note and "Sign in to join the waitlist" in note
    assert await pg.input_value("[data-d=title]") == "Dinner", "typed split kept"
    await pg.click("[data-receipt-close]"); await pg.wait_for_timeout(150)
    assert await pg.locator(".receipt-note").count() == 0 and await pg.locator("[data-receipt-plus]").count() == 1
    await pg.click("[data-receipt-plus]"); await pg.click("[data-open-account]"); await pg.wait_for_timeout(200)
    assert "Account" in await text(pg, "#view")

@test
async def business_space_is_a_plus_preview(ctx):
    pg = await open_app(ctx)
    await pg.click("[data-space=business]"); await pg.wait_for_timeout(150)
    v = await text(pg, "#view")
    assert "Keep business and personal money apart" in v and "Tax set-aside" in v and "Sign in to join the waitlist" in v
    assert await pg.locator("#m-income").count() == 0, "personal month is hidden"
    assert await pg.get_attribute(".biz-demo", "aria-hidden") == "true", "example content is not read out as real data"
    sw = await pg.evaluate("[document.querySelector('#main').scrollWidth, document.querySelector('#main').clientWidth]")
    assert sw[0] <= sw[1]
    await pg.click(".biz-panel [data-space=personal]"); await pg.wait_for_timeout(150)
    assert await pg.locator("#m-income").count() == 1
    await pg.click("[data-space=business]"); await tab(pg, "subs"); await tab(pg, "month")
    assert await pg.locator("#m-income").count() == 1, "leaving the tab returns to Personal"

@test
async def moments_is_a_plus_preview(ctx):
    pg = await open_app(ctx)
    await tab(pg, "split")
    if await pg.locator("[data-mode=local]").count(): await pg.click("[data-mode=local]"); await pg.wait_for_timeout(120)
    assert "Moments over money" in await text(pg, ".moments-teaser")
    await pg.click("[data-moments]"); await pg.wait_for_timeout(150)
    v = await text(pg, "#view")
    assert "Private by design" in v and "Sign in to join the waitlist" in v and await pg.locator("[data-new-split]").count() == 0
    assert await pg.get_attribute(".biz-demo", "aria-hidden") == "true"
    sw = await pg.evaluate("[document.querySelector('#main').scrollWidth, document.querySelector('#main').clientWidth]")
    assert sw[0] <= sw[1]
    await pg.click("[data-moments-close]"); await pg.wait_for_timeout(150)
    assert await pg.locator("[data-new-split]").count() == 1

@test
async def split_people_picker_search(ctx):
    pg = await open_app(ctx); await tab(pg, "split")
    if await pg.locator("[data-mode=local]").count(): await pg.click("[data-mode=local]"); await pg.wait_for_timeout(120)
    await pg.click("[data-new-split]"); await pg.wait_for_timeout(100)
    assert await pg.locator(".part-row").count() == 1 and await pg.locator("[data-part-add]").count() == 0, "only You is shown; no long list"
    await pg.fill("[data-d=title]", "Brunch")
    await pg.fill("[data-part-search]", "jor"); await pg.wait_for_timeout(100)
    opts = await pg.locator("[data-part-add]").all_inner_texts()
    assert len(opts) == 1 and "Jordan" in opts[0]
    assert await pg.evaluate("document.activeElement.hasAttribute('data-part-search')"), "typing keeps focus"
    await pg.keyboard.press("Enter"); await pg.wait_for_timeout(120)
    assert "Jordan" in await text(pg, ".part-list")
    await pg.fill("[data-part-search]", "Zara Q"); await pg.wait_for_timeout(100)
    assert "Add “Zara Q” as a new person" in await text(pg, "[data-out=partResults]")
    await pg.click("[data-part-new]"); await pg.wait_for_timeout(150)
    assert "Zara Q" in await text(pg, ".part-list") and any(p["name"] == "Zara Q" for p in (await state(pg))["people"])
    await pg.locator(".part-row", has_text="Jordan").locator("[data-part-remove]").click(); await pg.wait_for_timeout(100)
    assert "Jordan" not in await text(pg, ".part-list")
    assert await pg.input_value("[data-d=title]") == "Brunch", "typed split kept"
    await pg.click("[data-part-search]"); await pg.wait_for_timeout(80)
    assert await pg.locator("[data-part-add]").count() >= 5, "tapping search shows people to pick"
    await pg.click("form[data-form=split] h2"); await pg.wait_for_timeout(100)
    assert await pg.locator("[data-part-add]").count() == 0, "tapping elsewhere closes the list"

@test
async def split_edit_in_place_and_icon(ctx):
    pg = await open_app(ctx); await tab(pg, "split")
    if await pg.locator("[data-mode=local]").count(): await pg.click("[data-mode=local]"); await pg.wait_for_timeout(120)
    card = pg.locator("[data-split]").nth(2); sid = await card.get_attribute("data-split")
    await card.scroll_into_view_if_needed(); await pg.wait_for_timeout(100)
    top_before = await pg.evaluate("document.getElementById('main').scrollTop")
    await card.locator("[data-edit-split]").click(); await pg.wait_for_timeout(300)
    assert await pg.locator(f"[data-split='{sid}']").count() == 0, "the card became the form"
    assert await pg.locator("form[data-form=split]").count() == 1 and await pg.locator("[data-new-split]").count() == 1, "form is in place; New split stays at the top"
    top_after = await pg.evaluate("document.getElementById('main').scrollTop")
    assert top_after > 200 and abs(top_after - top_before) < 400, (top_before, top_after)
    await pg.click("[data-icon=travel]"); await pg.wait_for_timeout(100)
    assert await pg.get_attribute("[data-icon=travel]", "aria-pressed") == "true"
    await pg.click("form[data-form=split] button[type=submit]"); await pg.wait_for_timeout(250)
    assert [x for x in (await state(pg))["splits"] if x["id"] == sid][0]["icon"] == "travel"
    assert await pg.evaluate("document.getElementById('main').scrollTop") > 200, "stays near the card after saving"
    assert await pg.locator(f"[data-split='{sid}'] .ico path").count() == 2, "card shows the chosen icon"


@test
async def removals_can_be_undone(ctx):
    pg = await open_app(ctx)
    # subscription
    await tab(pg, "subs"); n = len((await state(pg))["subs"])
    await pg.click("[data-sub=s1] [data-del-sub]"); await pg.wait_for_timeout(120)
    assert len((await state(pg))["subs"]) == n - 1 and "Removed Netflix." in await pg.inner_text("#toast")
    await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(150)
    st = await state(pg); assert len(st["subs"]) == n and any(w["link"] == "sub:s1" for w in st["swaps"]), "sub and its swap come back"
    assert await pg.locator("[data-sub=s1]").count() == 1 and st["tab"] == "subs"
    # split
    await tab(pg, "split"); m = len((await state(pg))["splits"])
    await pg.locator("[data-split]").first.locator("[data-del-split]").click(); await pg.wait_for_timeout(120)
    assert len((await state(pg))["splits"]) == m - 1
    await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(150)
    assert len((await state(pg))["splits"]) == m
    # plan line, code, swap
    await tab(pg, "plan"); k = len((await state(pg))["expenses"])
    await pg.locator("[data-exp]").first.locator("[data-del-exp]").click(); await pg.wait_for_timeout(120)
    await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(150)
    assert len((await state(pg))["expenses"]) == k
    await tab(pg, "codes"); await pg.click("text=Add a code you found")
    f = pg.locator("form[data-form=addCode]"); await f.locator("[name=store]").fill("Zara"); await f.locator("[name=code]").fill("ZARA15")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(120)
    c = len((await state(pg))["codes"])
    await pg.locator("[data-del-code]").first.click(); await pg.wait_for_timeout(120)
    assert len((await state(pg))["codes"]) == c - 1
    await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(150)
    assert len((await state(pg))["codes"]) == c
    await tab(pg, "cheaper"); w = len((await state(pg))["swaps"])
    await pg.locator("[data-del-swap]").first.click(); await pg.wait_for_timeout(120)
    await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(150)
    assert len((await state(pg))["swaps"]) == w

@test
async def amounts_are_never_negative(ctx):
    pg = await open_app(ctx)
    await pg.fill("#m-income", "-4000"); await pg.locator("#m-income").blur(); await pg.wait_for_timeout(200)
    assert (await state(pg))["income"] == 4000
    await tab(pg, "plan")
    amt = pg.locator("[data-exp-amt]").first; await amt.fill("-50"); await amt.blur(); await pg.wait_for_timeout(200)
    assert (await state(pg))["expenses"][0]["amount"] == 50
    await tab(pg, "split"); await pg.click("[data-new-split]")
    await pg.fill("[data-d=title]", "Refund trick"); await pg.fill("[data-d=amount]", "100")
    await pg.select_option("[data-d=method]", "exact"); await pg.wait_for_timeout(100)
    await pg.fill("[data-part-search]", "Alex"); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(120)
    await pg.fill("[data-part-val=me]", "-20"); await pg.fill("[data-part-val=p1]", "120")
    await pg.click("form[data-form=split] button[type=submit]"); await pg.wait_for_timeout(150)
    assert "add up to" in await text(pg, "form[data-form=split] .err"), "a negative share cannot balance the total"

@test
async def borrow_never_owes_yourself(ctx):
    pg = await open_app(ctx); await tab(pg, "split"); await pg.click("[data-new-split]")
    await pg.fill("[data-d=title]", "Loan"); await pg.fill("[data-d=amount]", "40")
    await pg.select_option("[data-d=method]", "borrow"); await pg.wait_for_timeout(100)
    await pg.select_option("[data-d=borrower]", "p1"); await pg.wait_for_timeout(80)
    await pg.select_option("[data-d=paidBy]", "p1"); await pg.wait_for_timeout(120)   # Alex paid, so Alex cannot be the one who owes
    shown = await pg.eval_on_selector("[data-d=borrower]", "e=>e.value")
    await pg.click("form[data-form=split] button[type=submit]"); await pg.wait_for_timeout(150)
    x = [s for s in (await state(pg))["splits"] if s["title"] == "Loan"][0]
    assert x["paidBy"] == "p1" and list(x["parts"]) == [shown] and shown != "p1", x

@test
async def icon_picker_grid_and_tag_default(ctx):
    pg = await open_app(ctx, w=320, h=640); await tab(pg, "split"); await pg.click("[data-new-split]")
    assert await pg.get_attribute(".icon-auto", "aria-pressed") == "true"
    assert await pg.locator(".icon-pick .icon-opt").count() == 12
    tops = await pg.eval_on_selector_all(".icon-pick .icon-opt", "els=>[...new Set(els.map(e=>Math.round(e.getBoundingClientRect().top)))].length")
    assert tops == 2, f"12 icons sit in two even rows, got {tops}"
    sizes = await pg.eval_on_selector_all(".icon-pick .icon-opt", "els=>els.map(e=>e.getBoundingClientRect().width)")
    assert min(sizes) >= 34, sizes
    before = await pg.inner_html(".icon-auto svg")
    await pg.select_option("[data-d=tag]", "Movie"); await pg.wait_for_timeout(120)
    assert await pg.inner_html(".icon-auto svg") != before, "Match the tag shows the tag's icon"
    await pg.click("[data-icon=gift]"); await pg.wait_for_timeout(80)
    assert await pg.get_attribute(".icon-auto", "aria-pressed") == "false"
    await pg.click(".icon-auto"); await pg.wait_for_timeout(80)
    assert await pg.get_attribute(".icon-auto", "aria-pressed") == "true"


@test
async def empty_start_says_true_things(ctx):
    pg = await open_app(ctx); await tab(pg, "plan")
    await pg.click("[data-reset=blank]"); await pg.click("[data-reset-yes]"); await pg.wait_for_timeout(200)
    await tab(pg, "month"); v = await text(pg, "#view")
    assert "Sample month" not in v and "Start with the money coming in" in v
    assert "Every subscription was used" not in v and "No subscriptions yet" in v
    assert "already using every swap" not in v and "shortfall" not in v
    await tab(pg, "codes"); assert "No codes yet." in await text(pg, "[data-out=codeList]") and "“”" not in await text(pg, "#view")
    await tab(pg, "cheaper"); await pg.click("text=Add your own comparison")
    assert "First add something you pay for" in await text(pg, "#view") and await pg.locator("form[data-form=addSwap]").count() == 0
    await tab(pg, "split"); assert "Just you" in await text(pg, "#view")


@test
async def offline_copy_is_always_the_app(ctx):
    """The service worker must only save the app itself as the offline copy (never Privacy, Terms or an error page)."""
    if not APP.endswith(os.path.join("www", "index.html")): return  # needs the built site with sw.js
    import http.server, threading, functools, socket
    root = os.path.dirname(APP)
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Quiet, directory=root))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        b = ctx.browser; c2 = await b.new_context(service_workers="allow"); pg = await c2.new_page()
        await pg.add_init_script("window.KEEPWISE_FIREBASE = null;")
        base = f"http://127.0.0.1:{port}/"
        await pg.goto(base)  # the app registers the worker on https only; localhost is also a secure context
        await pg.evaluate("navigator.serviceWorker.register('sw.js').then(()=>navigator.serviceWorker.ready)")
        await pg.reload(); await pg.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
        await pg.goto(base + "privacy.html"); await pg.wait_for_timeout(500)
        await pg.goto(base + "nope-404.html"); await pg.wait_for_timeout(500)
        saved = await pg.evaluate("caches.keys().then(ks => caches.open(ks[0])).then(c => c.match('index.html')).then(r => r ? r.text() : '')")
        assert 'id="tabbar"' in saved, "the offline copy is the app, not a page visited earlier: " + saved[:120]
        await c2.close()
    finally:
        try: httpd.shutdown(); httpd.server_close()
        except Exception: pass


@test
async def edit_cancel_keeps_the_card_in_view(ctx):
    pg = await open_app(ctx, w=390, h=700); await tab(pg, "split")
    card = pg.locator("[data-split]").nth(3); sid = await card.get_attribute("data-split")
    await card.scroll_into_view_if_needed(); await card.locator("[data-edit-split]").click(); await pg.wait_for_timeout(300)
    await pg.locator("form[data-form=split]").evaluate("f => f.scrollIntoView({block:'end'})"); await pg.wait_for_timeout(150)
    await pg.click("[data-cancel-split]"); await pg.wait_for_timeout(250)
    r = await pg.evaluate(f"(()=>{{const c=document.querySelector('[data-split=\"{sid}\"]').getBoundingClientRect(),m=document.getElementById('main').getBoundingClientRect();return [c.top,c.bottom,m.top,m.bottom]}})()")
    assert r[0] >= r[2] - 1 and r[1] <= r[3] + 1, f"card is visible after Cancel: {r}"
    await card.locator("[data-edit-split]").click(); await pg.wait_for_timeout(300)
    await pg.locator("form[data-form=split]").evaluate("f => f.scrollIntoView({block:'end'})"); await pg.wait_for_timeout(150)
    await pg.click("form[data-form=split] button[type=submit]"); await pg.wait_for_timeout(250)
    r = await pg.evaluate(f"(()=>{{const c=document.querySelector('[data-split=\"{sid}\"]').getBoundingClientRect(),m=document.getElementById('main').getBoundingClientRect();return [c.top,c.bottom,m.top,m.bottom]}})()")
    assert r[0] >= r[2] - 1 and r[1] <= r[3] + 1, f"card is visible after Save: {r}"


@test
async def used_today_shows_it_is_done(ctx):
    pg = await open_app(ctx); await tab(pg, "subs")
    row = pg.locator("[data-sub=s7]")   # iCloud+, used today in the example
    btn = row.locator("[data-used]")
    assert await btn.is_disabled() and "Used today" in await btn.inner_text(), "already used today: shows as done"
    assert "Last used today" in await row.inner_text()
    hulu = pg.locator("[data-sub=s4]")
    assert "Unused for" in await hulu.inner_text()
    await hulu.locator("[data-used]").click(); await pg.wait_for_timeout(150)
    hulu = pg.locator("[data-sub=s4]")
    t = await hulu.inner_text()
    assert "Unused for" not in t and "Last used today" in t and await hulu.locator("[data-used]").is_disabled()
    assert "no longer flagged" in await pg.inner_text("#toast")
    assert "flash" in (await hulu.get_attribute("class"))


# ---------------- first-run setup, statements, backup, renewals, cancel help, share ----------------
@test
async def first_run_setup_flow(ctx):
    pg = await open_app(ctx, welcome=True)
    assert await pg.locator(".welcome .w-title").count() == 1 and not await pg.locator("#tabbar").is_visible(), "setup first, no tab bar"
    assert (await state(pg)) is None, "nothing saved until setup is finished"
    await pg.click("[data-w-next]"); await pg.click("[data-w-next]")
    assert "Enter what comes in" in await pg.inner_text("#toast"), "income is needed"
    await pg.select_option("[data-w=cur]", "GBP"); await pg.wait_for_timeout(80)
    assert "£" in await text(pg, ".w-big em")
    await pg.fill("[data-w=income]", "4200"); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(100)
    await pg.fill("[data-w=home]", "1500"); await pg.click("[data-w-next]")
    await pg.click("[data-w-finish]"); await pg.wait_for_timeout(200)
    st = await state(pg)
    assert st["income"] == 4200 and st["cur"] == "GBP" and st["example"] is False and [e["amount"] for e in st["expenses"]] == [1500] and st["subs"] == []
    assert await pg.locator("#tabbar").is_visible() and "£2,700" in await text(pg, "[data-out=headline]")
    await pg.reload(); await pg.wait_for_timeout(300)
    assert await pg.locator(".welcome").count() == 0, "setup shows once"

@test
async def first_run_can_explore_the_example(ctx):
    pg = await open_app(ctx, welcome=True)
    await pg.click("[data-w-example]"); await pg.wait_for_timeout(200)
    assert (await state(pg))["example"] is True and "example month" in await text(pg, "#view")
    await pg.click("[data-w-start]"); await pg.wait_for_timeout(100)
    assert await pg.locator(".welcome [data-w=income]").count() == 1, "set up later from the example"
    await pg.reload(); await pg.wait_for_timeout(300)
    assert await pg.locator(".welcome").count() == 0, "leaving the setup keeps the example"

@test
async def existing_people_never_see_setup(ctx):
    pg = await open_app(ctx, welcome=True)
    await pg.evaluate("localStorage.setItem('keepwise-app-v1', JSON.stringify({v:1, tab:'subs', cur:'USD', income:100, env:{needs:50,misc:30,save:20}, efSaved:0, efMonths:3, goalName:'', goalAmt:0, priority:'ef', ruleDays:45, filter:'All', expenses:[], subs:[], swaps:[], codes:[], people:[{id:'me',name:'You'}], tags:['Friends'], splits:[], settlements:[]})); localStorage.removeItem('keepwise-welcome-done')")
    await pg.reload(); await pg.wait_for_timeout(300)
    assert await pg.locator(".welcome").count() == 0 and await pg.locator("[data-tab=subs][aria-current=page]").count() == 1

@test
async def monthly_statements(ctx):
    pg = await open_app(ctx)
    st = await state(pg); keys = sorted(st["statements"])
    assert len(keys) == 3 and sum(1 for k in keys if st["statements"][k].get("example")) == 2, keys
    cur = st["statements"][keys[-1]]
    assert abs(cur["kept"] - money(await text(pg, "[data-out=headline] .big"))) < 0.01
    assert await pg.locator("[data-out=historyCard] .hist-col").count() == 3
    await pg.fill("#m-income", "6000"); await pg.locator("#m-income").blur(); await pg.wait_for_timeout(250)
    assert (await state(pg))["statements"][keys[-1]]["income"] == 6000, "this month's statement follows the plan"
    assert (await state(pg))["statements"][keys[0]]["income"] == 5200, "closed months do not change"
    await pg.click("[data-history]"); await pg.wait_for_timeout(150)
    assert await pg.locator(".stmt-row").count() == 3 and "In progress" in await text(pg, ".stmt-row:first-child")
    await pg.locator(".stmt-row").nth(2).click(); await pg.wait_for_timeout(150)
    v = await text(pg, ".stmt")
    assert "Monthly statement" in v and "Closed" in v and "example statement" in v and "Rent" in v
    assert await pg.locator("[data-stmt-print]").count() == 1
    await pg.click("[data-stmt-back]"); await pg.click("[data-history-close]"); await pg.wait_for_timeout(100)
    assert await pg.locator("[data-out=headline]").count() == 1
    await pg.locator("[data-out=historyCard] .hist-col").last.click(); await pg.wait_for_timeout(150)
    assert "In progress" in await text(pg, ".stmt")
    await tab(pg, "subs"); assert await pg.locator(".stmt").count() == 0, "tabs leave the statement"

@test
async def statement_prints_cleanly(ctx):
    pg = await open_app(ctx)
    await pg.click("[data-history]"); await pg.locator(".stmt-row").first.click(); await pg.wait_for_timeout(150)
    await pg.emulate_media(media="print")
    hidden = await pg.evaluate("['.app-header','#tabbar','.no-print'].map(s => getComputedStyle(document.querySelector(s)).display)")
    assert hidden == ["none", "none", "none"], hidden
    pdf = await pg.pdf(); assert len(pdf) > 5000

@test
async def backup_download_and_restore(ctx):
    pg = await open_app(ctx); await tab(pg, "plan")
    assert "No backup yet" in await text(pg, "[data-out=backupBox]")
    async with pg.expect_download() as dl: await pg.click("[data-out=backupBox] [data-backup]")
    d = await dl.value; assert re.match(r"keepwise-backup-\d{4}-\d\d-\d\d\.json", d.suggested_filename)
    j = json.load(open(await d.path())); assert j["app"] == "KeepWise" and j["kind"] == "backup" and j["data"]["income"] == 5200
    await pg.wait_for_timeout(150); assert "Last backup today" in await text(pg, "[data-out=backupBox]")
    await pg.fill("[data-bind=income]", "99"); await pg.locator("[data-bind=income]").blur(); await pg.wait_for_timeout(200)
    bad = os.path.join(TMP, "notbackup.json"); open(bad, "w").write('{"hello":1}')
    await pg.set_input_files("#restore-in", bad); await pg.wait_for_timeout(200)
    assert "isn’t a KeepWise backup" in await pg.inner_text("#toast") and (await state(pg))["income"] == 99
    await pg.set_input_files("#restore-in", await d.path()); await pg.wait_for_timeout(200)
    assert "Replace everything" in await text(pg, "[data-out=backupBox]")
    await pg.click("[data-restore-no]"); await pg.wait_for_timeout(100); assert (await state(pg))["income"] == 99
    await pg.set_input_files("#restore-in", await d.path()); await pg.wait_for_timeout(200)
    await pg.click("[data-restore-yes]"); await pg.wait_for_timeout(200)
    assert (await state(pg))["income"] == 5200 and "Backup restored" in await pg.inner_text("#toast")

@test
async def keep_data_safe_reminders(ctx):
    pg = await ctx.new_page(); pg.errors = []
    await pg.add_init_script("Object.defineProperty(navigator, 'userAgent', {get: () => 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'}); window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;")
    await pg.set_viewport_size({"width": 390, "height": 844}); await pg.goto(URL); await pg.wait_for_timeout(400)
    assert "Add to Home Screen" in await text(pg, "[data-out=keepSafe]")
    await pg.click("[data-a2hs-hide]"); await pg.wait_for_timeout(100)
    assert await text(pg, "[data-out=keepSafe]") == "" and (await state(pg))["a2hsHide"] is True
    # a real plan, a few days in, with no backup: a gentle reminder that can wait
    pg2 = await open_app(ctx); await tab(pg2, "plan")
    await pg2.click("[data-reset=blank]"); await pg2.click("[data-reset-yes]"); await pg2.wait_for_timeout(150)
    await pg2.click("[data-add-exp]"); await pg2.wait_for_timeout(100); await tab(pg2, "month")
    assert await text(pg2, "[data-out=keepSafe]") == "", "not on day one"
    await pg2.close()
    import datetime
    pg2 = await ctx.new_page(); pg2.errors = []
    await pg2.clock.install(time=datetime.datetime.now() + datetime.timedelta(days=5))
    await pg2.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;"); await pg2.set_viewport_size({"width": 390, "height": 844}); await pg2.goto(URL); await pg2.wait_for_timeout(400)
    assert "Back up your KeepWise data" in await text(pg2, "[data-out=keepSafe]")
    await pg2.click("[data-backup-later]"); await pg2.wait_for_timeout(100)
    assert await text(pg2, "[data-out=keepSafe]") == ""

@test
async def coming_up_renewals(ctx):
    pg = await open_app(ctx)
    card = await text(pg, "[data-out=comingUp]")
    assert "Hulu Premium" in card and "Tomorrow" in card and "Netflix" in card and "In 3 days" in card and "Spotify" in card and "Audible" not in card
    assert "$48.97 will be charged this week" in card
    await tab(pg, "subs")
    assert "Renews tomorrow" in await text(pg, "[data-sub=s4]")
    await pg.click("[data-sub=s4] [data-keep=drop]"); await pg.wait_for_timeout(100)
    assert "How to cancel Hulu Premium" in await text(pg, "[data-sub=s4]")
    await pg.click("[data-sub=s5] [data-renew-open]"); await pg.wait_for_timeout(80)
    await pg.select_option("[data-sub=s5] [data-renew-day]", "28"); await pg.wait_for_timeout(120)
    assert (await state(pg))["subs"][4]["renewDay"] == 28 and "Disney+ renews" in await pg.inner_text("#toast")
    f = pg.locator("form[data-form=addSub]"); await pg.click("text=Add a subscription")
    await f.locator("[name=name]").fill("Crunchyroll"); await f.locator("[name=price]").fill("7.99"); await f.locator("[name=renew]").fill("2026-12-09")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(120)
    assert [x for x in (await state(pg))["subs"] if x["name"] == "Crunchyroll"][0]["renewDay"] == 9
    await tab(pg, "month")
    c = await text(pg, "[data-out=comingUp]"); assert "You chose to drop it" in c and "$29.98 will be charged" in c

@test
async def cancel_help_links(ctx):
    pg = await open_app(ctx); await tab(pg, "subs")
    await pg.click("[data-sub=s1] [data-keep=drop]"); await pg.click("[data-sub=s6] [data-keep=drop]"); await pg.wait_for_timeout(120)
    assert await pg.get_attribute("[data-sub=s1] .cancel-link", "href") == "https://help.netflix.com/en/node/407"
    assert await pg.get_attribute("[data-sub=s1] .cancel-link", "target") == "_blank"
    assert "google.com/search" in await pg.get_attribute("[data-sub=s6] .cancel-link", "href"), "no official page known: a search"
    assert await pg.locator("[data-sub=s3] .cancel-link").count() == 0, "only shown once you choose Drop"

@test
async def share_what_you_found(ctx):
    pg = await open_app(ctx)
    await pg.click("[data-share-open]"); await pg.wait_for_timeout(900)
    size = await pg.evaluate("new Promise(r => { const i = document.querySelector('.share-img'); const go = () => r([i.naturalWidth, i.naturalHeight]); i.complete ? go() : i.onload = go; })")
    assert size == [1080, 1080], size
    assert "No names, no income" in await text(pg, "#view")
    async with pg.expect_download() as dl: await pg.click("[data-share-save]")
    assert (await dl.value).suggested_filename == "keepwise.png"
    await pg.click("[data-share-close]"); await pg.wait_for_timeout(100)
    assert await pg.locator("[data-out=headline]").count() == 1

@test
async def import_sets_renewal_dates(ctx):
    pg = await open_app(ctx)
    csv = os.path.join(TMP, "renew.csv")
    open(csv, "w").write("Date,Description,Amount\n2026-07-04,NETFLIX.COM,-15.49\n2026-08-04,NETFLIX.COM,-15.49\n2026-09-04,NETFLIX.COM,-15.49\n2026-09-01,PAYROLL ACME,3000\n")
    await pg.set_input_files("#stmt", csv); await pg.wait_for_timeout(400)
    await pg.click("[data-import-apply=replace]"); await pg.wait_for_timeout(200)
    n = [x for x in (await state(pg))["subs"] if x["name"].lower().startswith("netflix")][0]
    assert n["renewDay"] == 4 and (await state(pg))["example"] is False


@test
async def contacts_search_quick_add_and_groups(ctx):
    pg = await open_app(ctx); await tab(pg, "split")
    vcf = os.path.join(TMP, "friends.vcf")
    open(vcf, "w").write("BEGIN:VCARD\nVERSION:3.0\nFN:Omar Khan\nTEL;TYPE=CELL:+1 (555) 010-2233\nEMAIL:omar@example.com\nEND:VCARD\n"
                         "BEGIN:VCARD\nVERSION:3.0\nN:Lee;Bella;;;\nTEL:555 010 7788\nEND:VCARD\n"
                         "BEGIN:VCARD\nVERSION:3.0\nFN:Chen Wu\nEMAIL:chen@example.com\nEND:VCARD\n")
    assert "Find friends from your contacts" in await text(pg, "#view")
    await pg.set_input_files("#vcf", vcf); await pg.wait_for_timeout(200)
    assert len((await state(pg))["contacts"]) == 3 and "3 contacts" in await text(pg, ".contacts-on")
    await pg.click("[data-new-split]"); await pg.fill("[data-d=title]", "Movie night"); await pg.fill("[data-d=amount]", "120")
    await pg.fill("[data-part-search]", "omar"); await pg.wait_for_timeout(100)
    assert "from your contacts" in (await text(pg, ".part-results")).lower()
    await pg.click(".part-results [data-part-contact]"); await pg.wait_for_timeout(150)
    om = [p for p in (await state(pg))["people"] if p["name"] == "Omar Khan"][0]
    assert om["phone"] == "+15550102233" and om["email"] == "omar@example.com"
    assert await pg.evaluate("document.activeElement.hasAttribute('data-part-search')") and await pg.locator(".part-results").count() == 1, "ready for the next person"
    await pg.keyboard.type("7788"); await pg.wait_for_timeout(100)
    assert "Bella Lee" in await text(pg, ".part-results"), "find by phone number"
    await pg.keyboard.press("Enter"); await pg.wait_for_timeout(150)
    for name in ["Alex", "Sam", "Jordan", "chen"]:
        await pg.keyboard.type(name); await pg.wait_for_timeout(80); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(120)
    parts = await pg.locator(".part-row").count(); assert parts == 7, f"you plus six friends, typed in a row: {parts}"
    await pg.click("[data-group-new]"); await pg.fill("[data-group-name]", "Movie crew"); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(150)
    g = (await state(pg))["groups"]; assert g[0]["name"] == "Movie crew" and len(g[0]["ids"]) == 6
    await pg.click("form[data-form=split] button[type=submit]"); await pg.wait_for_timeout(200)
    await pg.click("[data-new-split]"); await pg.wait_for_timeout(100)
    chips = await text(pg, ".group-chips"); assert "Movie crew" in chips
    await pg.click("[data-group]"); await pg.wait_for_timeout(120)
    assert await pg.locator(".part-row").count() == 7 and await pg.get_attribute("[data-group]", "aria-pressed") == "true", "a whole group in one tap"
    await pg.click("[data-cancel-split]"); await pg.wait_for_timeout(100)
    assert "Movie crew" in await text(pg, "#view")
    await pg.click(".contacts-on [data-contacts-forget]"); await pg.wait_for_timeout(120)
    assert (await state(pg))["contacts"] == [] and "Omar Khan" in [p["name"] for p in (await state(pg))["people"]], "removing contacts keeps people already in splits"

@test
async def contacts_from_phone_picker_and_app(ctx):
    pg = await ctx.new_page(); pg.errors = []
    await pg.add_init_script("""window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;
      navigator.contacts = {select: async (props, opts) => { window.__asked = [props, opts]; return [{name: ['Dina Park'], tel: ['+44 7700 900123'], email: []}, {name: ['Eli Roth'], tel: [], email: ['eli@example.com']}]; }};""")
    await pg.set_viewport_size({"width": 390, "height": 844}); await pg.goto(URL); await pg.wait_for_timeout(400); await tab(pg, "split")
    await pg.click("[data-contacts-sync]"); await pg.wait_for_timeout(200)
    asked = await pg.evaluate("window.__asked"); assert asked[0] == ["name", "tel", "email"] and asked[1]["multiple"] is True
    assert [c["n"] for c in (await state(pg))["contacts"]] == ["Dina Park", "Eli Roth"]
    # the Android app reads the address book with permission
    pg2 = await ctx.new_page(); pg2.errors = []
    await pg2.add_init_script("""window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;
      window.Capacitor = {Plugins: {Contacts: {requestPermissions: async () => ({contacts: 'granted'}),
        getContacts: async () => ({contacts: [{name: {display: 'Faisal Ali'}, phones: [{number: '0300 1234567'}], emails: []}, {name: {display: null, given: 'Gia', family: 'Moss'}, phones: [], emails: [{address: 'gia@example.com'}]}]})}}};""")
    await pg2.set_viewport_size({"width": 390, "height": 844}); await pg2.goto(URL); await pg2.wait_for_timeout(400); await tab(pg2, "split")
    await pg2.click("[data-contacts-sync]"); await pg2.wait_for_timeout(200)
    names = [c["n"] for c in (await state(pg2))["contacts"]]
    assert "Faisal Ali" in names and "Gia Moss" in names, names


@test
async def other_income_counts_and_logs(ctx):
    pg = await open_app(ctx)
    base = money(await text(pg, "[data-out=headline] .big"))
    await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]")
    await f.locator("button[type=submit]").click(); assert "where the money comes from" in await pg.inner_text("#toast")
    await f.locator("[name=name]").fill("YouTube"); await f.locator("[name=kind]").select_option("creator"); await f.locator("[name=amount]").fill("400")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    x = (await state(pg))["extras"][0]; assert x["name"] == "YouTube" and x["when"] == "any" and x["amount"] == 400
    assert abs(money(await text(pg, "[data-out=headline] .big")) - (base + 400)) < 0.01, "the plan counts it"
    assert await text(pg, "[data-out=incomeLabel]") == "Regular pay"
    await pg.click("[data-inc-log]"); lf = pg.locator("form[data-form=incomeLog]")
    await lf.locator("[name=amount]").fill("150"); await lf.locator("button[type=submit]").click(); await pg.wait_for_timeout(150)
    row = await text(pg, "[data-inc]"); assert "$150" in row and "received in" in row
    assert "$150 of $400" in await text(pg, ".inc-card")
    await pg.click("[data-inc-pay-del]"); await pg.wait_for_timeout(100); await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(150)
    assert len((await state(pg))["extras"][0]["got"]) == 1, "removing a payment can be undone"
    # scheduled: every Friday, 100 each, shows up in Coming up
    await pg.click("[data-inc-edit]"); f = pg.locator("form[data-form=income]")
    await f.locator("[name=when]").select_option("weekly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=income]"); assert "Each payment" in await f.inner_text()
    await f.locator("[name=wd]").select_option("5"); await f.locator("[name=amount]").fill("100")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    x = (await state(pg))["extras"][0]; assert x["when"] == "weekly" and x["wd"] == 5
    assert abs(money(await text(pg, "[data-out=headline] .big")) - (base + 100 * 52 / 12)) < 0.01
    up = await text(pg, "[data-out=comingUp]"); assert "YouTube" in up and "money in" in up and "+$100" in up
    # trading gets a careful note; the statement lists what came in
    await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]")
    await f.locator("[name=kind]").select_option("trading"); await pg.wait_for_timeout(100)
    assert "not gains on paper" in await pg.locator("form[data-form=income]").inner_text()
    await pg.click("[data-inc-cancel]")
    await pg.click("[data-history]"); await pg.locator(".stmt-row").first.click(); await pg.wait_for_timeout(150)
    v = await text(pg, ".stmt"); assert "what came in" in v.lower() and "Regular pay" in v and "YouTube" in v and "$150 received" in v

@test
async def month_start_check_in(ctx):
    import datetime
    pg = await open_app(ctx); await pg.wait_for_timeout(100)
    assert await text(pg, "[data-out=monthClose]") == "", "nothing to close in the first month"
    kept = money(await text(pg, "[data-out=headline] .big")); saved = (await state(pg))["efSaved"]
    await pg.close()
    async def later():
        p2 = await ctx.new_page(); p2.errors = []
        await p2.clock.install(time=datetime.datetime.now() + datetime.timedelta(days=40))
        await p2.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;"); await p2.set_viewport_size({"width": 390, "height": 844}); await p2.goto(URL); await p2.wait_for_timeout(400)
        return p2
    p2 = await later()
    card = await text(p2, "[data-out=monthClose]"); assert "is closed" in card.lower() and "You planned to keep" in card and "Did you?" in card
    await p2.click("[data-close-other]"); await p2.fill("form[data-form=closeMonth] [name=amount]", "1000"); await p2.click("form[data-form=closeMonth] button[type=submit]"); await p2.wait_for_timeout(200)
    st = await state(p2); assert abs(st["efSaved"] - (saved + 1000)) < 0.01
    closed = [v for v in st["statements"].values() if v.get("actual") == 1000]; assert len(closed) == 1 and abs(closed[0]["kept"] - kept) < 0.01
    assert await text(p2, "[data-out=monthClose]") == "", "asked once"
    await p2.click("#toast .toast-undo"); await p2.wait_for_timeout(200)
    assert abs((await state(p2))["efSaved"] - saved) < 0.01 and "is closed" in (await text(p2, "[data-out=monthClose]")).lower(), "undo brings the question back"
    await p2.click("[data-close-yes]"); await p2.wait_for_timeout(200)
    assert abs((await state(p2))["efSaved"] - (saved + kept)) < 0.01 and "Added" in await p2.inner_text("#toast")
    await p2.click("[data-history]"); await p2.wait_for_timeout(150)
    assert "Closed" in await text(p2, ".stmt-row:nth-child(2)")


@test
async def keepwise_never_flags_itself(ctx):
    pg = await open_app(ctx); await tab(pg, "subs")
    await pg.click("text=Add a subscription"); f = pg.locator("form[data-form=addSub]")
    await f.locator("[name=name]").fill("KeepWise Plus"); await f.locator("[name=price]").fill("15"); await f.locator("[name=last]").fill("2025-01-01"); await f.locator("[name=group]").fill("Video")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(150)
    row = pg.locator("[data-sub]", has_text="KeepWise Plus"); t = await row.inner_text()
    assert "Unused for" not in t and "Duplicate" not in t, t
    assert "$94.95" in await text(pg, "[data-out=subsSummary]"), "the flagged total does not include it"
    assert "Duplicate of KeepWise" not in await text(pg, "[data-out=subsList]")
    for _ in range(3):
        q = await text(pg, "[data-out=reviewCard]"); assert "KeepWise" not in q


@test
async def chosen_currency_shows_everywhere(ctx):
    pg = await open_app(ctx)
    await pg.select_option("#m-cur", "GBP"); await pg.wait_for_timeout(200)
    async def clean(where):
        v = await pg.inner_text("#view"); assert "$" not in v, f"{where}: " + v[max(0, v.index("$") - 40): v.index("$") + 20].replace("\n", " ")
    await clean("month"); await pg.click("[data-plain]"); await pg.locator("[data-ask]").nth(2).click(); await clean("ask")
    await pg.click("[data-inc-add]"); await clean("income form"); await pg.click("[data-inc-cancel]")
    await pg.click("[data-space=business]"); await clean("business"); await pg.click("[data-space=personal]")
    await pg.click("[data-history]"); await clean("statements")
    for i in range(3):
        await pg.locator(".stmt-row").nth(i).click(); await pg.wait_for_timeout(80); await clean(f"statement {i}"); await pg.click("[data-stmt-back]")
    for tb in ["subs", "cheaper", "codes", "plan", "split"]:
        await tab(pg, tb); await clean(tb)
    await pg.click("[data-new-split]"); await clean("split form"); await pg.click("[data-cancel-split]")
    await pg.click("[data-moments]"); await clean("moments"); await pg.click("[data-moments-close]")
    csv = os.path.join(TMP, "gbp.csv"); open(csv, "w").write("Date,Description,Amount\n01/09/2026,NETFLIX.COM,-10.99\n03/09/2026,PAYROLL ACME,2500\n")
    await pg.set_input_files("#stmt", csv); await pg.wait_for_timeout(400); await clean("import review")


@test
async def statement_in_another_currency(ctx):
    pg = await open_app(ctx)
    gbp = os.path.join(TMP, "uk.csv")
    open(gbp, "w").write("Date,Description,Amount\n2026-07-01,PAYROLL ACME,£2000.00\n2026-07-04,NETFLIX.COM,-£10.00\n2026-08-01,PAYROLL ACME,£2000.00\n2026-08-04,NETFLIX.COM,-£10.00\n2026-09-01,PAYROLL ACME,£2000.00\n2026-09-04,NETFLIX.COM,-£10.00\n")
    await pg.set_input_files("#stmt", gbp); await pg.wait_for_timeout(400)
    card = await text(pg, ".fx-card"); assert "British pound" in card and "Your plan is in US dollar" in card
    assert await pg.locator("[data-import-apply=replace]").is_disabled(), "a rate is needed before converting"
    await pg.fill("[data-fx-rate]", "1.25"); await pg.wait_for_timeout(150)
    body = await text(pg, "[data-out=importBody]"); assert "$12.50/mo" in body and "$2,500" in body and "£" not in body
    assert await pg.evaluate("document.activeElement.hasAttribute('data-fx-rate')"), "typing the rate is not interrupted"
    await pg.locator(".fx-opt input[value=switch]").check(); await pg.wait_for_timeout(150)
    body = await text(pg, "[data-out=importBody]"); assert "£10/mo" in body and "$" not in body, "previewed in the statement's own currency"
    await pg.locator(".fx-opt input[value=convert]").check(); await pg.wait_for_timeout(120)
    await pg.click("[data-import-apply=replace]"); await pg.wait_for_timeout(250)
    st = await state(pg); n = [x for x in st["subs"] if x["name"].lower().startswith("netflix")][0]
    assert n["price"] == 12.5 and st["income"] == 2500 and st["cur"] == "USD" and st["imported"]["cur"] == "GBP" and st["imported"]["rate"] == 1.25
    # switching the plan instead
    await pg.set_input_files("#stmt", gbp); await pg.wait_for_timeout(400)
    await pg.locator(".fx-opt input[value=switch]").check(); await pg.wait_for_timeout(120)
    await pg.click("[data-import-apply=replace]"); await pg.wait_for_timeout(250)
    st = await state(pg); assert st["cur"] == "GBP" and [x for x in st["subs"] if x["name"].lower().startswith("netflix")][0]["price"] == 10
    # no symbols in the file: nothing is assumed, but the question is one tap away
    plain = os.path.join(TMP, "plain.csv"); open(plain, "w").write("Date,Description,Amount\n2026-09-04,NETFLIX.COM,-10.00\n2026-09-01,PAYROLL ACME,2000.00\n")
    await pg.set_input_files("#stmt", plain); await pg.wait_for_timeout(400)
    assert await pg.locator(".fx-card").count() == 0 and not await pg.locator("[data-import-apply=replace]").is_disabled()
    await pg.click("[data-fx-open]"); await pg.wait_for_timeout(120); assert await pg.locator(".fx-card").count() == 1
    await pg.locator(".fx-opt input[value=same]").check(); await pg.wait_for_timeout(100)
    assert not await pg.locator("[data-import-apply=merge]").is_disabled()

async def open_at(ctx, when):
    import datetime
    pg = await ctx.new_page(); pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append("pageerror: " + str(e)))
    await pg.clock.install(time=datetime.datetime(*when))
    await pg.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;"); await pg.set_viewport_size({"width": 390, "height": 844}); await pg.goto(URL); await pg.wait_for_timeout(400)
    return pg

@test
async def pay_schedule_and_extra_paycheck(ctx):
    pg = await open_at(ctx, (2026, 10, 5, 10, 0))
    assert "How are you paid?" in await text(pg, "[data-out=payBox]")
    await pg.click("[data-payday-edit]"); f = pg.locator("form[data-form=pay]")
    await f.locator("[name=when]").select_option("biweekly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=pay]"); await f.locator("[name=next]").fill("2026-10-02"); await f.locator("[name=amount]").fill("2600")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    st = await state(pg); assert st["income"] == 5200 and st["pay"]["when"] == "biweekly"
    head = await text(pg, "[data-out=headline]"); assert "October has 3 paydays, so an extra $2,600 is counted" in head, head
    assert abs(money(await text(pg, "[data-out=headline] .big")) - (1456.99 + 2600)) < 0.01
    box = await text(pg, "[data-out=payBox]"); assert "every 2 weeks" in box and "next payday" in box and "Oct 16" in box
    how = await text(pg, "[data-out=howto]"); assert "Your next payday is Friday, Oct 16" in how and "each of October’s 3 paychecks" in how
    # the monthly number and the paycheck stay in step
    await pg.fill("#m-income", "6000"); await pg.locator("#m-income").blur(); await pg.wait_for_timeout(200)
    assert (await state(pg))["pay"]["amount"] == 3000
    await pg.click("[data-history]"); await pg.locator(".stmt-row").first.click(); await pg.wait_for_timeout(120)
    assert "Extra paycheck" in await text(pg, ".stmt")
    await pg.click("[data-stmt-back]"); await pg.click("[data-history-close]")
    await pg.click("[data-payday-edit]"); await pg.click("[data-payday-clear]"); await pg.wait_for_timeout(150)
    assert (await state(pg))["pay"] is None and "extra" not in await text(pg, "[data-out=headline]")

@test
async def month_can_start_on_payday(ctx):
    pg = await open_at(ctx, (2026, 10, 5, 10, 0))
    await pg.click("[data-payday-edit]"); f = pg.locator("form[data-form=pay]")
    await f.locator("[name=day]").select_option("25"); await f.locator("[name=amount]").fill("5200"); await f.locator("[name=monthStart]").select_option("25")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    note = await text(pg, "[data-out=planNote]"); assert "19 days left in October" in note and "Your October runs Sep 25 to Oct 24" in note, note
    st = await state(pg); assert st["monthStart"] == 25 and "2026-10" in st["statements"] and st["statements"]["2026-10"]["range"] == "Sep 25 to Oct 24"
    up = await text(pg, "[data-out=payBox]"); assert "on the 25th" in up and "Oct 25" in up
    # a payment logged on Sep 26 belongs to this October; one on Sep 20 does not
    await pg.click("[data-inc-add]"); g = pg.locator("form[data-form=income]"); await g.locator("[name=name]").fill("Tutoring"); await g.locator("[name=amount]").fill("300"); await g.locator("button[type=submit]").click(); await pg.wait_for_timeout(150)
    for d, a in [("2026-09-26", "80"), ("2026-09-20", "50")]:
        await pg.click("[data-inc-log]"); lf = pg.locator("form[data-form=incomeLog]"); await lf.locator("[name=amount]").fill(a); await lf.locator("[name=date]").fill(d); await lf.locator("button[type=submit]").click(); await pg.wait_for_timeout(150)
    assert "$80 of $300" in await text(pg, ".inc-card")
    await pg.close()
    p2 = await open_at(ctx, (2026, 10, 26, 10, 0))
    assert "is closed" in (await text(p2, "[data-out=monthClose]")).lower(), "the month closes on the 24th, not the 31st"
    assert "November" in await text(p2, "[data-out=planNote]")

# ---------------- owner dashboard ----------------
ADMIN = os.path.join(os.path.dirname(APP), "admin.html") if APP.endswith(os.path.join("www", "index.html")) else os.path.join(os.path.dirname(APP), "admin", "admin.html")
SEED = {
  "users/u1": {"name": "Ada Brook", "email": "ada@example.com", "createdAt": 0, "plusInterest": True, "plusInterestAt": 0, "marketing": True, "marketingUpdatedAt": 0, "city": "Leeds", "provider": "password", "emailVerified": True},
  "users/u2": {"name": "Ben, Jr.", "email": "ben@example.com", "createdAt": 0, "plusInterest": False, "marketing": True, "marketingUpdatedAt": 0, "provider": "google.com", "emailVerified": True},
  "users/u3": {"name": "Cy Diaz", "email": "cy@example.com", "createdAt": 0, "plusInterest": True, "plusInterestAt": 0, "marketing": False, "provider": "google.com", "emailVerified": False},
}
async def open_admin(ctx, owner=True, w=1100, h=900):
    pg = await ctx.new_page(); await pg.set_viewport_size({"width": w, "height": h})
    pg.errors = []; pg.on("pageerror", lambda e: pg.errors.append("pageerror: " + str(e)))
    now = "Date.now()"
    seed = json.dumps(SEED)
    await pg.add_init_script("window.KEEPWISE_FIREBASE = {apiKey:'t',projectId:'t'};" + f"window.__mockGoogleEmail = {json.dumps('notartist04@gmail.com' if owner else 'someone@example.com')};" +
        f"if (!localStorage.getItem('__mock_fs')) {{ const s = {seed}; const n = Date.now(); Object.values(s).forEach((u,i) => {{ u.createdAt = n - i*2*86400000; if (u.plusInterestAt === 0) u.plusInterestAt = n - i*3600000; if (u.marketingUpdatedAt === 0) u.marketingUpdatedAt = n; }}); localStorage.setItem('__mock_fs', JSON.stringify(s)); }}")
    async def serve_fb(route):
        if route.request.url.endswith("firebase-app-compat.js"): await route.fulfill(path=os.path.join(HERE, "mock_firebase.js"), content_type="application/javascript")
        else: await route.fulfill(body="", content_type="application/javascript")
    await pg.route("https://cdn.jsdelivr.net/npm/firebase@*/**", serve_fb)
    await pg.goto("file://" + ADMIN); await pg.wait_for_timeout(500)
    return pg

@test
async def admin_owner_sees_dashboard_and_lists(ctx):
    pg = await open_admin(ctx)
    assert "Owner sign-in" in await text(pg, "#app")
    await pg.click("[data-google]"); await pg.wait_for_timeout(500)
    tiles = await text(pg, ".tiles")
    assert "Accounts 3" in tiles and "Plus waitlist 2" in tiles and "67% of accounts" in tiles and "Email opt-ins 2" in tiles
    assert "2 of 200" in await text(pg, "#app") and "198 more" in await text(pg, "#app")
    assert await pg.locator("#chart .bar").count() == 30
    rows = await pg.locator("#table tbody tr").all_inner_texts()
    assert len(rows) == 2 and "Ada Brook" in "".join(rows) and "Ben" not in "".join(rows), "waitlist shows only people who joined"
    await pg.click("[data-tab=email]"); await pg.wait_for_timeout(150)
    rows = await pg.locator("#table tbody tr").all_inner_texts()
    assert len(rows) == 2 and "Cy Diaz" not in "".join(rows), "email list is opted-in people only"
    async with pg.expect_download() as dl: await pg.click("[data-export]")
    d = await dl.value; csv = open(await d.path()).read()
    assert csv.splitlines()[0].startswith("Name,Email,Opted in") and '"Ben, Jr."' in csv and len(csv.splitlines()) == 3
    await pg.click("[data-tab=all]"); await pg.fill("#q", "leeds"); await pg.wait_for_timeout(150)
    assert await pg.locator("#table tbody tr").count() == 1
    assert pg.errors == [], pg.errors

@test
async def admin_blocks_other_accounts(ctx):
    pg = await open_admin(ctx, owner=False)
    await pg.click("[data-google]"); await pg.wait_for_timeout(500)
    v = await text(pg, "#app")
    assert "No admin access" in v and "Accounts" not in v
    await pg.click("[data-signout]"); await pg.wait_for_timeout(300)
    assert "Owner sign-in" in await text(pg, "#app")

@test
async def admin_fits_phone_width(ctx):
    pg = await open_admin(ctx, w=360, h=780)
    await pg.click("[data-google]"); await pg.wait_for_timeout(500)
    sw = await pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    assert sw[0] <= sw[1], f"admin overflows at 360px: {sw}"

# ---------------- persistence ----------------
@test
async def data_persists_across_reload(ctx):
    pg = await open_app(ctx)
    await pg.fill("#m-income", "4321"); await pg.locator("#m-income").blur(); await pg.wait_for_timeout(300)
    await tab(pg, "codes"); await pg.reload(); await pg.wait_for_timeout(400)
    assert await pg.locator("[data-tab=codes][aria-current=page]").count() == 1
    await tab(pg, "month"); assert await pg.input_value("#m-income") == "4321"

async def main():
    passed, failed = 0, []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for fn in [t for t in TESTS if not os.environ.get('ONLY') or t.__name__ in os.environ['ONLY'].split(',')]:
            ctx = await b.new_context(is_mobile=False)
            try:
                await fn(ctx)
                errs = [e for pg in ctx.pages for e in getattr(pg, "errors", [])]
                assert not errs, "JS errors: " + "; ".join(errs)
                passed += 1; print(f"PASS  {fn.__name__}")
            except Exception as e:
                failed.append(fn.__name__); print(f"FAIL  {fn.__name__}: {e}")
                traceback.print_exc(limit=-1)
            await ctx.close()
        await b.close()
    print(f"\n{passed} passed, {len(failed)} failed" + (f": {', '.join(failed)}" if failed else ""))
    sys.exit(1 if failed else 0)

asyncio.run(main())
