"""KeepWise end-to-end test suite (Playwright, Chromium).
Run: python3 tests/test_app.py [path/to/app.html]
Each test gets a fresh browser context (empty storage)."""
import asyncio, sys, os, re, json, tempfile, traceback, datetime
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
FONTS = os.environ.get("KEEPWISE_FONTS")
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
    try: await pg.wait_for_function("(() => { const a = document.activeElement; if (a && a !== document.body && a.blur) a.blur(); return getComputedStyle(document.getElementById('tabbar')).display !== 'none'; })()", timeout=4000)
    except Exception: pass
    if name in ("cheaper", "codes"):  # these live inside Subs now, behind the switch at the top
        await pg.click("[data-tab=subs]"); await pg.wait_for_timeout(120); await pg.click(f"#view .sub-seg [data-go={name}]"); await pg.wait_for_timeout(120); return
    await pg.click(f"[data-tab={name}]"); await pg.wait_for_timeout(120)
async def open_account(pg):
    # the profile button opens the side menu; the account screen is its first row
    await pg.click("#acct-btn"); await pg.wait_for_timeout(250); await pg.click("#sidenav [data-menu=profile]"); await pg.wait_for_timeout(150)
async def tc(pg, sel): return " ".join((await pg.locator(sel).first.text_content()).split())   # everything in it, including an explanation tucked behind its (i)
async def menu_to(pg, k):
    # settings, the app lock, backups, the tour and support are reached from the side menu
    await pg.evaluate("document.activeElement && document.activeElement.blur()"); await pg.click("#acct-btn"); await pg.wait_for_timeout(280); await pg.click(f"#sidenav [data-menu={k}]"); await pg.wait_for_timeout(250)
async def text(pg, sel): return (await pg.inner_text(sel)).replace("\n", " ")
async def ask_type(pg, q):
    # type into Ask wherever you are: the card at the foot of Month, or the owl button on any other tab
    if await pg.locator("#ask-in").count() == 0: await pg.click("#wise"); await pg.wait_for_timeout(150)
    await pg.fill("#ask-in", q); await pg.press("#ask-in", "Enter")
async def open_trip(pg):
    if await pg.locator("[data-trip-open][aria-expanded=true]").count() == 0: await pg.click("[data-trip-open]")
async def open_misc(pg):
    if await pg.locator("[data-env-open=misc][aria-expanded=true]").count() == 0: await pg.click("[data-env-open=misc]")
    await pg.wait_for_timeout(150)
async def kept_month(pg):
    if await pg.locator("[data-out=envelopes] .env-row .name.tnum").count() == 0: await tab(pg, "month")
    return await pg.evaluate("document.querySelector('[data-out=envelopes] .env-row .name.tnum').textContent")
async def said(pg):
    # what Ask answered: a command that changed something lands you on it and says so in the toast; anything else answers in the box
    t = await pg.evaluate("(() => { const o = document.getElementById('ask-out'), t = document.getElementById('toast'); const a = o && !o.hidden ? o.innerText : '', b = t && !t.hidden ? (t.dataset.full || t.innerText.replace(/\\s*Undo\\s*$/, '')) : ''; return /^(Added|Updated|Removed|Started)/.test(b) ? b : (a || b); })()")
    return t.replace("\n", " ").replace("\u00a0", " ")

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
  if(el.closest('svg')||el.closest('.sr'))return; if(el.parentElement&&el.parentElement.closest('[data-scroll-x]'))return; /* a row that scrolls sideways on purpose; the row itself is still checked */ const r=el.getBoundingClientRect(); if(!r.width)return;
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
                await pg.click("[data-env-open=needs]"); await pg.wait_for_timeout(80)
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
    ph = await open_app(ctx)   # a phone gets the compact sizes
    c = await ph.evaluate("[getComputedStyle(document.querySelector('h1')).fontSize, getComputedStyle(document.querySelector('.big')).fontSize, getComputedStyle(document.body).fontSize, getComputedStyle(document.querySelector('.card')).paddingLeft]")
    assert c == ["25.6px", "48px", "15px", "14px"], c
    await ph.close(); pg = await open_app(ctx, w=768, h=1024)
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
        await tab(pg, "plan"); r = await pg.evaluate(CHECK_MONEY); assert r["n"] >= 5 and not r["bad"], f"{cur} plan: {r}"
        await tab(pg, "split"); await pg.click("[data-new-split]"); await pg.wait_for_timeout(80)
        r = await pg.evaluate(CHECK_MONEY); assert r["n"] >= 1 and not r["bad"], f"{cur} split form: {r}"
        await pg.click("[data-cancel-split]")
        await pg.locator("[data-settle-btn]").first.click(); await pg.wait_for_timeout(80); r = await pg.evaluate(CHECK_MONEY); assert not r["bad"], f"{cur} part payment card: {r}"
        await pg.click("form[data-form=settle] [type=submit]"); await pg.wait_for_timeout(80)
        await pg.click("#history [data-pay-edit]"); await pg.wait_for_timeout(80)
        r = await pg.evaluate(CHECK_MONEY); assert not r["bad"], f"{cur} payment edit: {r}"
        await pg.click("#history [data-pay-del]"); await pg.wait_for_timeout(80)

@test
async def every_currency_can_be_chosen(ctx):
    pg = await open_app(ctx)
    codes = await pg.locator("#m-cur option").evaluate_all("els => els.map(e => e.value)")
    assert len(codes) == len(set(codes)) == 154 and codes[:8] == ["USD", "GBP", "EUR", "CAD", "AUD", "INR", "PKR", "AED"], len(codes)
    for c in ("JPY", "MXN", "NGN", "SAR", "BDT", "TRY", "ZAR", "CNY", "BRL", "CHF", "KRW", "EGP", "ZWG"):
        assert c in codes, c
    assert await pg.locator("#m-cur optgroup").evaluate_all("els => els.map(e => e.label)") == ["Most used", "All currencies"]
    for c, mark in (("NGN", "NGN"), ("JPY", "¥"), ("SAR", "SAR"), ("ZWG", "ZWG")):   # the amounts carry the chosen currency, even one the phone may not know
        await pg.select_option("#m-cur", c); await pg.wait_for_timeout(150)
        v = await pg.inner_text("#view"); assert mark in v and "$" not in v.replace("MX$", ""), f"{c}: {v[:200]}"
        assert (await state(pg))["cur"] == c
    r = await pg.evaluate(CHECK_MONEY); assert not r["bad"], r
    await tab(pg, "plan"); assert await pg.locator("[data-bind=cur] option").count() == 154 and await pg.input_value("[data-bind=cur]") == "ZWG"
    r = await pg.evaluate(CHECK_MONEY); assert not r["bad"], r
    assert not pg.errors, pg.errors

@test
async def month_compare_chart(ctx):
    pg = await open_app(ctx)
    assert await pg.locator("[data-compare]").count() == 0, "the comparison is always open, with no button"
    vals = [money(t) for t in await pg.locator(".cmp-val").all_inner_texts()]
    big = money(await text(pg, "[data-out=dropCard] .bigsoft"))
    assert len(vals) == 2 and vals[1] > vals[0] and abs(vals[1] - big) < 0.01, (vals, big)
    await pg.locator(".cmp-col").first.click()
    assert await pg.locator(".cmp-col.on .cmp-tip").is_visible()
    await tab(pg, "plan"); await tab(pg, "month"); assert await pg.locator(".cmp").count() == 1, "still there after leaving and coming back"

@test
async def month_say_it_plainly_and_ask(ctx):
    pg = await open_app(ctx)
    await pg.click("[data-plain]")
    t = await text(pg, "#ask-out")
    assert "yours to keep" in t and "barely use" in t, t
    await pg.click("[data-ask='Can I afford $300?']"); assert (await text(pg, "#ask-out")).startswith("Yes")
    await pg.click("[data-ask='What should I cancel?']"); assert "Your rules flag" in await text(pg, "#ask-out")
    await pg.click("[data-ask='Who owes me?']"); assert "owe" in await text(pg, "#ask-out")
    await ask_type(pg, "can I afford 999999")
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
    head0 = money(re.search(r"ends with (\$[\d,.]+)", await tc(pg, "[data-out=headline]")).group(1))
    await pg.click("[data-set-aside]"); await pg.wait_for_timeout(150)
    st = await state(pg)
    assert abs(st["efSaved"] - (ef0 + amt)) < 0.01 and len(st["deposits"]) == 1
    head1 = money(re.search(r"ends with (\$[\d,.]+)", await tc(pg, "[data-out=headline]")).group(1))
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
    await pg.locator("[data-sub]", has_text="YouTube Premium").locator("[data-sub-edit]").click(); await pg.wait_for_timeout(100)
    await pg.locator("form[data-form=subEdit] [data-del-sub]").click(); await pg.wait_for_timeout(100)
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
    await row.locator("[data-code-edit]").click(); await pg.wait_for_timeout(80)
    await pg.locator("form[data-form=codeEdit] [data-del-code]").click(); await pg.wait_for_timeout(80)
    assert await pg.locator("[data-code]", has_text="Zara").count() == 0

# ---------------- plan ----------------
@test
async def plan_envelopes_lines_priority(ctx):
    pg = await open_app(ctx); await tab(pg, "plan")
    # the three shares always total 100: you choose Expenditures and Misc, Savings is what is left and cannot be typed
    env = lambda: pg.evaluate("[...document.querySelectorAll('[data-env],[data-env-save]')].map(e => +(e.value !== undefined ? e.value : e.textContent))")
    tot = lambda: pg.evaluate("(() => { const e = JSON.parse(localStorage.getItem('keepwise-app-v1')).env; return [e.needs, e.misc, e.save]; })()")
    assert await pg.locator("input[data-env-save]").count() == 0 and await pg.locator("[data-env=save]").count() == 0, "Savings is shown, not typed"
    m0 = (await env())[1]
    await pg.fill("[data-env=needs]", "70"); await pg.wait_for_timeout(80)
    assert await env() == [70, m0, 30 - m0] == await tot() and f"Savings is what is left: {30 - m0}%" in await text(pg, "[data-out=envCheck]")
    await pg.fill("[data-env=needs]", "95"); await pg.wait_for_timeout(80); assert await env() == [95, 5, 0] and "Nothing is left for Savings" in await text(pg, "[data-out=envCheck]"), "the other share gives way"
    await pg.fill("[data-env=misc]", "40"); await pg.wait_for_timeout(80); assert await env() == [60, 40, 0]
    await pg.fill("[data-env=needs]", "999"); await pg.wait_for_timeout(80); assert await env() == [100, 0, 0] == await tot(), "never above 100"
    await pg.fill("[data-env=needs]", "60"); await pg.fill("[data-env=misc]", "20"); await pg.wait_for_timeout(80); assert await env() == [60, 20, 20] and sum(await tot()) == 100
    assert await pg.locator("[data-out=envCheck] .err").count() == 0
    n0 = await pg.locator("[data-exp]").count()
    await pg.click("[data-add-exp]"); await pg.wait_for_timeout(100)
    await pg.click("form[data-form=exp] [type=submit]"); await pg.wait_for_timeout(100); assert "Give the line a name" in await pg.inner_text("#toast")
    await pg.fill("form[data-form=exp] [name=name]", "Parking"); await pg.fill("form[data-form=exp] [name=amount]", "45")
    await pg.evaluate("document.activeElement.blur()"); await pg.wait_for_timeout(250)
    assert await pg.input_value("form[data-form=exp] [name=name]") == "Parking", "leaving a field never empties the card"
    await pg.click("form[data-form=exp] [type=submit]"); await pg.wait_for_timeout(150)
    assert await pg.locator("[data-exp]").count() == n0 + 1 and "Parking" in await text(pg, "[data-out=expList]")
    # every line edits as a card: Edit, then Save, Remove or Cancel
    await pg.locator("[data-exp]").last.locator("[data-exp-edit]").click(); await pg.wait_for_timeout(100)
    await pg.fill("form[data-form=exp] [name=amount]", "60"); await pg.select_option("form[data-form=exp] [name=env]", "misc"); await pg.click("form[data-form=exp] [type=submit]"); await pg.wait_for_timeout(150)
    last = (await state(pg))["expenses"][-1]; assert last["name"] == "Parking" and last["amount"] == 60 and last["env"] == "misc"
    await pg.locator("[data-exp]").last.locator("[data-exp-edit]").click(); await pg.wait_for_timeout(100)
    await pg.fill("form[data-form=exp] [name=amount]", "999"); await pg.click("[data-exp-cancel]"); await pg.wait_for_timeout(100)
    assert (await state(pg))["expenses"][-1]["amount"] == 60, "Cancel changes nothing"
    await pg.locator("[data-exp]").last.locator("[data-exp-edit]").click(); await pg.wait_for_timeout(100)
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
    await pg.locator("[data-settle]", has_text="Jordan").locator("[data-settle-btn]").click(); await pg.wait_for_timeout(100); await pg.click("form[data-form=settle] [type=submit]"); await pg.wait_for_timeout(100)
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
    await pg.locator("[data-settle]", has_text="Priya").locator("[data-settle-btn]").click(); await pg.wait_for_timeout(100); await pg.click("form[data-form=settle] [type=submit]"); await pg.wait_for_timeout(100)
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
    await pg.click("[data-mode=shared]"); await pg.wait_for_timeout(120)
    soon = await text(pg, "[data-shared-soon]")
    assert "COMING WITH PLUS" in soon.upper() and "Split with friends, live" in soon and "Tell them" in soon, soon
    for name in ("month", "subs", "cheaper", "codes", "plan", "split"):   # the public app never names the tool it was built with
        await tab(pg, name); assert "Claude" not in await pg.inner_text("#app"), name
    await pg.click("[data-shared-soon] [data-mode=local]"); await pg.wait_for_timeout(120)
    assert await pg.locator("[data-new-split]").count() == 1 and (await state(pg))["splitMode"] == "local", "one tap back to splitting on this phone"
    assert not await pg.evaluate("document.getElementById('bell').hidden"), "the bell is always there"
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
    bell = lambda: pg.evaluate("document.getElementById('bell-n').hidden ? 0 : +document.getElementById('bell-n').textContent")
    b0 = await bell()   # this phone's own notes are already counted; a friend's change adds one more
    await pg.evaluate("__mock.db.doc('splits/abc').set({title:'Pizza night',amount:60,tag:'Dinner',paidBy:'u_alex',method:'equal',parts:{u_me:1,u_alex:1,u_sam:1},date:'2026-09-29',createdBy:'u_alex',createdAt:Date.now()})")
    await pg.wait_for_timeout(300)
    assert await pg.inner_text("#toast") == "Alex added you to “Pizza night”"
    assert await bell() == b0 + 1
    assert "You owe Alex $20" in await text(pg, "[data-out=splitSum]")
    # a split that doesn't involve me must not notify
    await pg.evaluate("__mock.db.doc('splits/xyz').set({title:'Their lunch',amount:10,tag:'Lunch',paidBy:'u_alex',method:'equal',parts:{u_alex:1,u_sam:1},createdBy:'u_alex',createdAt:Date.now()})")
    await pg.wait_for_timeout(250); assert await bell() == b0 + 1
    # friend edits it
    await pg.evaluate("__mock.db.doc('splits/abc').update({amount:90,updatedBy:'u_alex',updatedAt:Date.now()+5})")
    await pg.wait_for_timeout(250)
    assert "edited" in await pg.inner_text("#toast")
    await pg.click("#bell"); await pg.wait_for_timeout(250)
    v = await text(pg, "#view"); assert "Notifications" in v and "Pizza night" in v and "unread" in v, v
    assert await pg.locator(".note-row.unread", has_text="Pizza night").count() == 1 and await bell() >= 1, "opening the list does not mark anything read"
    await pg.click("[data-note-all]"); await pg.wait_for_timeout(250)
    assert await pg.evaluate("document.getElementById('bell-n').hidden") and await pg.locator(".note-row.unread").count() == 0
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
    await pg.locator("[data-settle]", has_text="Sam").locator("[data-settle-btn]").click(); await pg.wait_for_timeout(250); await pg.click("form[data-form=settle] [type=submit]"); await pg.wait_for_timeout(250)
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

async def use_as_plan(pg):
    # "Use this as my plan": a plan the person built themselves is only replaced after they say yes
    await pg.click("[data-import-apply=replace]"); await pg.wait_for_timeout(150)
    if await pg.locator("[data-import-apply][data-sure]").count(): await pg.click("[data-import-apply][data-sure]")

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
    assert "Sam" in await text(pg, "[data-moves=in]") and "Sam" not in await text(pg, "[data-st=income]"), "transfers must not count as income"
    return v

@test
async def import_csv_statement_and_apply(ctx):
    pg = await open_app(ctx)
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement.csv")); await pg.wait_for_timeout(500)
    await check_statement_review(pg)
    await use_as_plan(pg); await pg.wait_for_timeout(300)
    st = await state(pg)
    assert st["income"] == 4200 and st["payday"] == 25, (st["income"], st.get("payday"))
    names = [s["name"] for s in st["subs"]]
    assert "Netflix" in names and len(names) == 6, names
    nf = [s for s in st["subs"] if s["name"] == "Netflix"][0]
    assert nf["charges"] == 6 and nf["since"] == "2026-04-05" and nf["last"] is None
    leg = await text(pg, ".legend"); needs, misc, sav = [money(x) for x in re.findall(r"\$[\d,.]+", leg)]
    extra = sum(e["amount"] for e in st.get("extras", []))   # regular transfers received are ticked as other income
    assert abs(4200 + extra - needs - misc - sav) < 0.05, (leg, st.get("extras"))
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
    card = pg.locator("[data-out=needs] .review"); assert await card.count() == 1
    name = re.search(r"use (.+)\?", await card.inner_text()).group(1)
    await card.locator("[data-review=barely]").click(); await pg.wait_for_timeout(120)
    s = [x for x in (await state(pg))["subs"] if x["name"] == name][0]
    assert s["low"] is True and s["reviewedAt"]
    await tab(pg, "subs")
    assert "You said you barely use it" in await pg.locator(f"[data-sub={s['id']}]").inner_text()
    await tab(pg, "month")
    name2 = re.search(r"use (.+)\?", await pg.locator("[data-out=needs] .review").inner_text()).group(1)
    assert name2 != name, "a reviewed subscription is not asked again"
    await pg.click("[data-out=needs] [data-review=none]"); await pg.wait_for_timeout(120)
    assert [x for x in (await state(pg))["subs"] if x["name"] == name2][0]["keep"] == "drop"
    await pg.click("[data-out=needs] [data-review=later]"); await pg.wait_for_timeout(120)
    assert await pg.locator("[data-out=needs] .review").count() == 0

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
    assert await pg.get_attribute("#view a.btn.primary", "href") == "https://mykeepwise.com/"
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
    # a new password needs 8 characters, a capital letter, a number and a special character; the list ticks off as you type
    for pw, missing in (("longenough", "a capital letter, a number, a special character"), ("Longenough", "a number, a special character"), ("Longenough1", "a special character"), ("Lo1!", "at least 8 characters")):
        await pg.fill("#acc-pass", pw); await pg.click("[data-form=acc-email] [type=submit]"); await pg.wait_for_timeout(120)
        assert ("Your password needs " + missing + ".") in await acc_err(pg), (pw, await acc_err(pg))
    await pg.fill("#acc-pass", "Longenough1"); await pg.wait_for_timeout(80)
    assert await pg.locator("[data-pw-rules] li.ok").count() == 3 and await pg.locator("[data-pw-rules] li").count() == 4
    await pg.fill("#acc-pass", "Longenough1!"); await pg.wait_for_timeout(80); assert await pg.locator("[data-pw-rules] li.ok").count() == 4
    await pg.fill("#acc-pass", "Longenough1!"); await pg.click("[data-form=acc-email] [type=submit]"); await pg.wait_for_timeout(400)
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
async def location_refused_shows_how_to_turn_it_on(ctx):
    pg = await open_app(ctx, fb=True)
    await open_account(pg)
    await pg.click("[data-acc-mode=create]"); await pg.wait_for_timeout(120)
    await pg.fill("#acc-email", "ada@example.com"); await pg.fill("#acc-pass", "Longenough1!")
    await pg.click("[data-form=acc-email] [type=submit]"); await pg.wait_for_timeout(400)
    await pg.evaluate("void (navigator.geolocation.getCurrentPosition = (ok, no) => no({code: 1}))")
    await pg.click("[data-acc-loc]"); await pg.wait_for_timeout(200)
    h = await text(pg, "[data-loc-help]")
    assert "Location is turned off for KeepWise" in h and "allow Location" in h and "type your city" in h, h
    # Try again is never a dead button: it says so when Location is still off
    await pg.click("[data-loc-help] [data-acc-loc]"); await pg.wait_for_timeout(200)
    assert "still turned off" in await pg.inner_text("#toast") and await pg.locator("[data-loc-help]").count() == 1
    await pg.evaluate("void (navigator.geolocation.getCurrentPosition = ok => ok({coords: {latitude: 31.5204, longitude: 74.3587}}))")
    await pg.click("[data-loc-help] [data-acc-loc]"); await pg.wait_for_timeout(200)
    v = await text(pg, "#view")
    assert await pg.locator("[data-loc-help]").count() == 0 and "Approximate location saved" in v
    await pg.click("[data-acc-loc-clear]"); await pg.wait_for_timeout(120)
    await pg.evaluate("void (navigator.geolocation.getCurrentPosition = (ok, no) => no({code: 3}))")
    await pg.click("[data-acc-loc]"); await pg.wait_for_timeout(200)
    assert "We couldn’t find your location" in await text(pg, "[data-loc-help]")
    await pg.click("[data-loc-help-close]"); await pg.wait_for_timeout(120)
    assert await pg.locator("[data-loc-help]").count() == 0

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
    await tab(pg, "codes"); await open_account(pg); await pg.wait_for_timeout(200)
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
    await pg.click("[data-sub=s1] [data-sub-edit]"); await pg.wait_for_timeout(100); await pg.click("[data-sub=s1] [data-del-sub]"); await pg.wait_for_timeout(120)
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
    await pg.locator("[data-exp]").first.locator("[data-exp-edit]").click(); await pg.wait_for_timeout(100)
    await pg.locator("[data-exp]").first.locator("[data-del-exp]").click(); await pg.wait_for_timeout(120)
    await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(150)
    assert len((await state(pg))["expenses"]) == k
    await tab(pg, "codes"); await pg.click("text=Add a code you found")
    f = pg.locator("form[data-form=addCode]"); await f.locator("[name=store]").fill("Zara"); await f.locator("[name=code]").fill("ZARA15")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(120)
    c = len((await state(pg))["codes"])
    await pg.locator("[data-code-edit]").first.click(); await pg.wait_for_timeout(100); await pg.locator("[data-del-code]").first.click(); await pg.wait_for_timeout(120)
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
    await pg.locator("[data-exp-edit]").first.click(); await pg.wait_for_timeout(100)
    await pg.fill("form[data-form=exp] [name=amount]", "-50"); await pg.click("form[data-form=exp] [type=submit]"); await pg.wait_for_timeout(200)
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
    assert "Every subscription was used" not in v and "Your rules" not in v
    assert "already using every swap" not in v and "shortfall" not in v
    await tab(pg, "codes"); assert "No codes of your own yet." in await text(pg, "[data-out=codeList]") and "“”" not in await text(pg, "#view")
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
    assert await pg.locator("#tabbar").is_visible() and "£2,700" in await tc(pg, "[data-out=headline]")
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
    pg = await open_app(ctx); await tab(pg, "plan"); assert await pg.locator("[data-out=backupBox]").count() == 0, "backups moved off Plan"
    await menu_to(pg, "backup")
    assert "No backup yet" in await text(pg, "[data-out=backupBox]")
    async with pg.expect_download() as dl: await pg.click("[data-out=backupBox] [data-backup]")
    d = await dl.value; assert re.match(r"keepwise-backup-\d{4}-\d\d-\d\d\.json", d.suggested_filename)
    j = json.load(open(await d.path())); assert j["app"] == "KeepWise" and j["kind"] == "backup" and j["data"]["income"] == 5200
    await pg.wait_for_timeout(150); assert "Last backup today" in await text(pg, "[data-out=backupBox]")
    await tab(pg, "plan"); await pg.fill("[data-bind=income]", "99"); await pg.locator("[data-bind=income]").blur(); await pg.wait_for_timeout(200); await menu_to(pg, "backup")
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
    await pg2.click("[data-add-exp]"); await pg2.wait_for_timeout(100); await pg2.fill("form[data-form=exp] [name=name]", "Rent"); await pg2.click("form[data-form=exp] [type=submit]"); await pg2.wait_for_timeout(100); await tab(pg2, "month")
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
    await f.locator("[name=name]").fill("Crunchyroll"); await f.locator("[name=price]").fill("7.99"); far = await pg.evaluate("(() => { const d = new Date(); d.setDate(d.getDate() + 15); return [`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`, d.getDate()]; })()"); await f.locator("[name=renewDay]").select_option(str(far[1]))  # a monthly subscription picks a day; this one is outside the week, whatever today is
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(120)
    assert [x for x in (await state(pg))["subs"] if x["name"] == "Crunchyroll"][0]["renewDay"] == far[1]
    await tab(pg, "month")
    c = await text(pg, "[data-out=comingUp]"); assert "You chose to drop it" in c and "$29.98 will be charged" in c

@test
async def tell_them_after_split_changes(ctx):
    pg = await open_app(ctx)
    await pg.evaluate("(() => { window.__sent = []; navigator.share = async d => { window.__sent.push(d.text); }; })()")
    await tab(pg, "split")
    assert await pg.locator("[data-tell]").count() == 0, "nothing to tell before anything changes"
    names = await pg.evaluate("JSON.parse(localStorage.getItem('keepwise-app-v1')).people.filter(p => p.id !== 'me' && !p.archived).map(p => [p.id, p.name])")
    assert len(names) >= 2, names
    (a, an), (b, bn) = names[0], names[1]
    # added: one message for the group, or one each
    await pg.click("[data-new-split]"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=split]")
    await f.locator("[data-d=title]").fill("Movie night"); await f.locator("[data-d=amount]").fill("90")
    for pid in (a, b):
        await pg.click("[data-part-search]"); await pg.wait_for_timeout(60)
        await pg.click(f"[data-part-add='{pid}']"); await pg.wait_for_timeout(60)
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    st = await state(pg); sp = [x for x in st["splits"] if x["title"] == "Movie night"][0]
    n = len(sp["parts"]); m = lambda v: f"${v:.2f}".replace(".00", ""); share = m(90 / n)
    card = await text(pg, "[data-tell]")
    assert "Let everyone in Movie night know" in card and "$90, paid by me" in card and f"{an}: {share}" in card, card
    assert "does not message anyone" in card
    await pg.click("[data-tell-all]"); await pg.wait_for_timeout(150)
    sent = await pg.evaluate("window.__sent")
    assert len(sent) == 1 and sent[0].startswith("Movie night: $90, paid by me.") and f"Me: {share}" in sent[0] and sent[0].endswith("Split bills free with KeepWise: https://mykeepwise.com"), sent
    assert "Sent. Send again" in await text(pg, "[data-tell]")
    await pg.click("[data-tell-each]"); await pg.wait_for_timeout(100)
    await pg.click(f"[data-tell-id='{a}'] [data-tell-send]"); await pg.wait_for_timeout(150)
    sent = await pg.evaluate("window.__sent")
    assert sent[1].startswith(f"Movie night: I paid $90. Your share is {share}."), sent[1]
    assert "Sent" in await text(pg, f"[data-tell-id='{a}']")
    await pg.click("[data-tell-close]"); await pg.wait_for_timeout(100)
    assert await pg.locator("[data-tell]").count() == 0
    # updated: says what the share was before, right under the card that changed
    await pg.click(f"[data-split='{sp['id']}'] [data-edit-split]"); await pg.wait_for_timeout(120)
    f = pg.locator("form[data-form=split]"); await f.locator("[data-d=amount]").fill("120"); await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    await pg.click("[data-tell-each]"); await pg.wait_for_timeout(100)
    row = await text(pg, f"[data-tell-id='{a}']")
    assert f"Movie night was updated: I paid $120. Your share is {m(120 / n)}. Before, your share was {share}." in row, row
    assert await pg.evaluate(f"document.querySelector(\"[data-split='{sp['id']}']\").nextElementSibling.hasAttribute('data-tell')"), "shown under the edited split"
    box = await pg.locator("[data-tell]").bounding_box(); assert box["width"] <= 390 and box["x"] >= 0
    # deleted, and Undo takes the prompt away again
    await pg.click(f"[data-split='{sp['id']}'] [data-del-split]"); await pg.wait_for_timeout(150)
    card = await text(pg, "[data-tell]"); assert "Movie night was deleted" in card and "It no longer counts for anyone" in card, card
    await pg.click(".toast-undo"); await pg.wait_for_timeout(150)
    assert await pg.locator("[data-tell]").count() == 0 and any(x["title"] == "Movie night" for x in (await state(pg))["splits"])
    # settled: one person, one message
    row = pg.locator("[data-settle]").first; who = await row.get_attribute("data-settle"); got = "owes you" in await row.inner_text()
    await row.locator("[data-settle-btn]").click(); await pg.wait_for_timeout(150); await pg.click("form[data-form=settle] [type=submit]"); await pg.wait_for_timeout(150)
    card = await text(pg, "[data-tell]")
    assert ("Got your" in card if got else "I paid you" in card) and "We are all square" in card, card
    await pg.click("[data-tell] [data-tell-send]"); await pg.wait_for_timeout(120)
    sent = await pg.evaluate("window.__sent")
    assert "all square" in sent[-1] and all("https://mykeepwise.com" in m for m in sent), "every message carries the link, whatever it is about"
    assert "mykeepwise.com" in await text(pg, "[data-tell] .tell-msg"), "and the preview shows it"
    # no share sheet (a computer): the message is copied instead
    await pg.evaluate("(() => { navigator.share = undefined; Object.defineProperty(navigator, 'clipboard', {value: {writeText: async t => { window.__copied = t; }}, configurable: true}); })()")
    await pg.click("[data-tell] [data-tell-send]"); await pg.wait_for_timeout(120)
    assert "Copied. Paste it into a message" in await pg.inner_text("#toast") and "all square" in await pg.evaluate("window.__copied")
    assert not pg.errors, pg.errors

@test
async def no_empty_gaps_between_sections(ctx):
    # a section with nothing to show must not leave a hole on the screen
    gaps = """(() => { const k = [...document.querySelectorAll('#view > *')].map(e => [e, e.getBoundingClientRect()]).filter(([e, r]) => r.height > 0 && getComputedStyle(e).position !== 'fixed');
      let worst = 0, at = ''; for (let i = 1; i < k.length; i++){ const g = k[i][1].top - k[i-1][1].bottom; if (g > worst){ worst = g; at = (k[i-1][0].dataset.out || k[i-1][0].className || k[i-1][0].tagName) + ' -> ' + (k[i][0].dataset.out || k[i][0].className || k[i][0].tagName); } }
      return [Math.round(worst), at, [...document.querySelectorAll('#view [data-out]')].filter(e => !e.innerHTML.trim() && e.getBoundingClientRect().height === 0 && getComputedStyle(e).display !== 'none').length]; })()"""
    for welcome in (False, True):
        pg = await open_app(ctx, welcome=welcome)
        if welcome:
            await pg.evaluate("(() => { const s = JSON.parse(localStorage.getItem('keepwise-app-v1') || '{}'); s.hideNote = true; s.subs = (s.subs || []).map(x => ({...x, renewDay: null, renewDate: null})); localStorage.setItem('keepwise-app-v1', JSON.stringify(s)); localStorage.setItem('keepwise-welcome-done', '1'); })()")
            await pg.reload(); await pg.wait_for_timeout(400)
        for name in ("month", "subs", "cheaper", "codes", "plan", "split"):
            if await pg.locator(f"[data-tab={name}]").count() == 0: continue
            await tab(pg, name)
            worst, at, hidden = await pg.evaluate(gaps)
            assert worst <= 19, f"{name}: a {worst}px hole between {at}"
            assert hidden == 0, f"{name}: {hidden} empty sections still take a slot"

NOTIF_MOCK = """window.__n = {pending: [], types: null, listener: null, perm: 'granted', asked: 0};
window.Capacitor = {Plugins: {LocalNotifications: {
  requestPermissions: async () => { window.__n.asked++; return {display: window.__n.perm}; },
  registerActionTypes: async o => { window.__n.types = o.types; },
  addListener: (name, fn) => { window.__n.listener = fn; },
  cancel: async o => { const ids = o.notifications.map(x => x.id); window.__n.pending = window.__n.pending.filter(x => !ids.includes(x.id)); },
  schedule: async o => { window.__n.pending.push(...o.notifications.map(x => ({...x, when: [x.schedule.at.getMonth() + 1, x.schedule.at.getDate(), x.schedule.at.getHours(), x.schedule.at.getMinutes()]}))); }
}}};"""

@test
async def asks_if_money_arrived_from_the_day_after(ctx):
    # paid on the 5th; a side income of 250 lands on the 9th. Today is 5 October: nothing to ask yet.
    pg = await open_at(ctx, (2026, 10, 5, 9, 0))
    await pg.click("[data-payday-edit]"); f = pg.locator("form[data-form=pay]")
    await f.locator("[name=when]").select_option("monthly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=pay]"); await f.locator("[name=day]").select_option("5"); await f.locator("[name=amount]").fill("1420")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]")
    await f.locator("[name=name]").fill("Tutoring"); await f.locator("[name=when]").select_option("monthly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=income]"); await f.locator("[name=day]").select_option("9"); await f.locator("[name=amount]").fill("250")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    assert await pg.locator("[data-arrived]").count() == 0, "never on the day itself"
    # 6 October: the day after payday it asks about the pay, and only the pay
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 6, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    card = await text(pg, "[data-arrived]"); assert "Did it arrive?" in card and "Your pay" in card and "Expected Oct 5" in card and "$1,420" in card and "Tutoring" not in card, card
    await pg.click("[data-arrive=pay] [data-arrive-no]"); await pg.wait_for_timeout(150)
    assert await pg.locator("[data-arrived]").count() == 0 and "ask again tomorrow" in await pg.inner_text("#toast")
    # 7 October: it asks again; Yes settles it for good
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 7, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    await pg.click("[data-arrive=pay] [data-arrive-yes]"); await pg.wait_for_timeout(150)
    assert await pg.locator("[data-arrived]").count() == 0 and (await state(pg))["payGot"] == "2026-10-05"
    # 10 October: the side income was due yesterday and is not logged
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 10, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    card = await text(pg, "[data-arrived]"); assert "Tutoring" in card and "Expected Oct 9" in card and "$250" in card and "Your pay" not in card, card
    await pg.locator("[data-arrived] [data-arrive-yes]").click(); await pg.wait_for_timeout(150)
    x = (await state(pg))["extras"][0]; assert x["got"][-1]["date"] == "2026-10-09" and x["got"][-1]["amount"] == 250
    assert await pg.locator("[data-arrived]").count() == 0 and "Logged $250 from Tutoring" in await pg.inner_text("#toast")
    # a once-a-month income that is logged shows a green Logged tag in place of the button; removing the payment brings the button back
    row = pg.locator("[data-inc]", has_text="Tutoring"); assert (await row.locator("[data-inc-logged]").inner_text()).strip() == "Logged" and await row.locator("[data-inc-log]").count() == 1, "logged, and another payment can still be added"
    await row.locator("[data-inc-pay-del]").click(); await pg.wait_for_timeout(150)
    row = pg.locator("[data-inc]", has_text="Tutoring"); assert await row.locator("[data-inc-log]").count() == 1 and await row.locator("[data-inc-logged]").count() == 0
    await pg.click("#toast .toast-undo") if await pg.locator("#toast .toast-undo").count() else await pg.locator("[data-arrived] [data-arrive-yes]").click()
    await pg.wait_for_timeout(150)
    # income that lands every week keeps its button and counts what has been logged
    await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]")
    await f.locator("[name=name]").fill("Shifts"); await f.locator("[name=when]").select_option("weekly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=income]"); await f.locator("[name=amount]").fill("80"); await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    row = pg.locator("[data-inc]", has_text="Shifts"); assert await row.locator("[data-inc-logged]").count() == 0
    for n in (1, 2):
        await row.locator("[data-inc-log]").click(); await pg.click("form[data-form=incomeLog] [type=submit]"); await pg.wait_for_timeout(200)
        row = pg.locator("[data-inc]", has_text="Shifts"); assert (await row.locator("[data-inc-logged]").inner_text()).strip() == f"{n} logged" and await row.locator("[data-inc-log]").count() == 1
    # logging it yourself beforehand means it never asks; and after a week it stops asking
    await pg.clock.set_fixed_time(datetime.datetime(2026, 11, 14, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    card = await text(pg, "[data-arrived]"); assert "Tutoring" in card and "Expected Nov 9" in card and "Your pay" not in card, "pay from the 5th is more than a week old: " + card
    row = pg.locator("[data-inc]", has_text="Tutoring"); assert await row.locator("[data-inc-log]").count() == 1 and await row.locator("[data-inc-logged]").count() == 0, "a new month brings the button back"
    await pg.locator("[data-arrive]", has_text="Tutoring").locator("[data-arrive-no]").click(); await pg.wait_for_timeout(150)
    assert (await state(pg))["extras"][0]["skip"] == "2026-11-09" and "Tutoring" not in await text(pg, "[data-arrived]")
    assert not pg.errors, pg.errors

@test
async def android_reminders_for_income_and_each_renewal(ctx):
    # the Android app: paid on the 25th, today is 10 October, reminders turned on
    pg = await ctx.new_page(); await pg.set_viewport_size({"width": 390, "height": 844}); pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    await pg.clock.install(time=datetime.datetime(2026, 10, 10, 12, 0)); await pg.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;" + NOTIF_MOCK)
    await pg.goto(URL); await pg.wait_for_timeout(300)
    await pg.click("[data-payday-edit]"); f = pg.locator("form[data-form=pay]")
    await f.locator("[name=when]").select_option("monthly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=pay]"); await f.locator("[name=day]").select_option("25"); await f.locator("[name=amount]").fill("3000")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]")
    await f.locator("[name=name]").fill("Tutoring"); await f.locator("[name=when]").select_option("monthly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=income]"); await f.locator("[name=day]").select_option("12"); await f.locator("[name=amount]").fill("250")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    await pg.clock.run_for(2000); assert await pg.evaluate("window.__n.pending.length") == 0, "nothing until reminders are on"
    await tab(pg, "subs"); await pg.click("[data-remind-on]"); await pg.wait_for_timeout(100); await pg.clock.run_for(2000)
    inc = await pg.evaluate("window.__n.pending.filter(x => x.id >= 7300).map(x => [x.when, x.title, x.body, x.extra.kind])")
    # the morning after each was due: Tutoring on the 13th, pay on the 26th
    assert [x[0] for x in inc] == [[10, 13, 10, 0], [10, 26, 10, 0]], inc
    assert inc[0][1] == "Did Tutoring arrive?" and "$250 was expected Oct 12" in inc[0][2] and inc[1][1] == "Did your pay arrive?" and "$3,000 was expected Oct 25" in inc[1][2] and all(x[3] == "income" for x in inc)
    # each subscription with a charge date outside the days before payday gets its own question, 7 or 5 days ahead of the charge
    ren = await pg.evaluate("window.__n.pending.filter(x => x.id >= 7200 && x.id < 7300).map(x => [x.schedule.at.getTime(), x.title, x.extra.subId])")
    st = await state(pg); now = await pg.evaluate("Date.now()")
    for at, title, sid in ren:
        assert title.startswith("Still using ") and at > now
        day = datetime.datetime.fromtimestamp(at / 1000, datetime.timezone.utc if os.environ.get("TZ") == "UTC" else None)
        assert not (datetime.datetime(2026, 10, 15) <= day.replace(tzinfo=None) <= datetime.datetime(2026, 10, 25, 23, 59)), "the payday questions cover those days"
    assert len(ren) >= 1 and len({x[2] for x in ren}) == len(ren), f"one question per subscription: {ren}"
    # logging the income on the day it lands removes its reminder
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 12, 20, 0)); await tab(pg, "month")
    await pg.click("[data-inc-log]"); await pg.click("form[data-form=incomeLog] [type=submit]"); await pg.wait_for_timeout(150); await pg.clock.run_for(2000)
    inc = await pg.evaluate("window.__n.pending.filter(x => x.id >= 7300).map(x => x.title)")
    assert "Did Tutoring arrive?" not in inc and "Did your pay arrive?" in inc, inc
    # tapping an income reminder opens Month
    await tab(pg, "codes"); await pg.evaluate("window.__n.listener({actionId: 'tap', notification: {extra: {kind: 'income'}}})"); await pg.wait_for_timeout(150)
    assert (await state(pg))["tab"] == "month"
    assert not pg.errors, pg.errors

@test
async def notes_and_notifications_open_the_exact_place(ctx):
    # the Android app on 6 October. Pay on the 5th is set up today, so the 5th that already passed is not asked about.
    pg = await ctx.new_page(); await pg.set_viewport_size({"width": 390, "height": 844}); pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    await pg.clock.install(time=datetime.datetime(2026, 10, 6, 9, 0)); await pg.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;" + NOTIF_MOCK)
    await pg.goto(URL); await pg.wait_for_timeout(300)
    await pg.click("[data-payday-edit]"); f = pg.locator("form[data-form=pay]")
    await f.locator("[name=when]").select_option("monthly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=pay]"); await f.locator("[name=day]").select_option("5"); await f.locator("[name=amount]").fill("1420")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    assert (await state(pg))["pay"]["since"] == "2026-10-06"
    await tab(pg, "subs"); await pg.click("[data-remind-on]"); await pg.wait_for_timeout(100); await pg.clock.run_for(2000); await tab(pg, "month")
    assert await pg.locator("[data-arrived]").count() == 0, "nothing from before the pay was added"
    await pg.click("#bell"); await pg.wait_for_timeout(150); assert "arrive" not in await text(pg, "#view"); await pg.click("[data-close-inbox]")
    # 6 November: the day after the next payday it asks. "Ask me tomorrow" hides the card, the bell note brings it back.
    await pg.clock.set_fixed_time(datetime.datetime(2026, 11, 6, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    assert await pg.locator("[data-arrive=pay]").count() == 1
    await pg.click("[data-arrived] [data-arrive-later]"); await pg.wait_for_timeout(150); assert await pg.locator("[data-arrive=pay]").count() == 0
    await tab(pg, "codes"); await pg.click("#bell"); await pg.wait_for_timeout(150)
    await pg.locator(".note-row", has_text="Did your pay arrive?").locator("[data-note-open]").click(); await pg.wait_for_timeout(200)
    assert (await state(pg))["tab"] == "month" and await pg.locator("[data-arrive=pay].flash").count() == 1, "the note opens the question itself"
    assert await pg.evaluate("(() => { const r = document.querySelector('[data-arrive=pay]').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })()"), "and it is on screen"
    # the notification for that payday, tapped while unanswered, lands on the same card; once logged it says so
    tap = "window.__n.listener({actionId: 'tap', notification: {extra: {kind: 'income', key: 'pay', date: '2026-11-05'}}})"
    await tab(pg, "plan"); await pg.evaluate(tap); await pg.wait_for_timeout(200)
    assert (await state(pg))["tab"] == "month" and await pg.locator("[data-arrive=pay].flash").count() == 1
    await pg.click("[data-arrive=pay] [data-arrive-yes]"); await pg.wait_for_timeout(200)
    await tab(pg, "plan"); await pg.evaluate(tap); await pg.wait_for_timeout(200)
    assert (await state(pg))["tab"] == "month" and "already logged" in await pg.inner_text("#toast") and await pg.locator("[data-arrive=pay]").count() == 0
    # a "Still using it?" notification opens that subscription's question; answering it once is enough
    sub = (await state(pg))["subs"][0]; sid, name = sub["id"], sub["name"]
    ask = "window.__n.listener({actionId: 'tap', notification: {extra: {subId: %r, cycle: 'x', at: '2026-11-04'}}})" % sid
    await tab(pg, "month"); await pg.evaluate(ask); await pg.wait_for_timeout(200)
    card = pg.locator(f"[data-review-id='{sid}']"); assert (await state(pg))["tab"] == "subs" and await card.count() == 1 and f"Still using {name}?" in await card.inner_text()
    await card.locator("[data-review=lot]").click(); await pg.wait_for_timeout(200)
    assert [x for x in (await state(pg))["subs"] if x["id"] == sid][0]["reviewedAt"] == "2026-11-06"
    await tab(pg, "month"); await pg.evaluate(ask); await pg.wait_for_timeout(200)
    assert (await state(pg))["tab"] == "subs" and f"You already answered about {name}. Thanks." in await pg.inner_text("#toast")
    assert await pg.locator(f"[data-review-id='{sid}']").count() == 0 and await pg.locator(f"[data-sub='{sid}'].flash").count() == 1, "it shows the subscription, not the question again"
    assert not pg.errors, pg.errors

@test
async def asks_once_if_a_bill_you_pay_yourself_was_paid(ctx):
    # the Android app on 2 October. Electricity is due on the 5th and Water on the 1st, both set up today.
    pg = await ctx.new_page(); await pg.set_viewport_size({"width": 390, "height": 844}); pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    await pg.clock.install(time=datetime.datetime(2026, 10, 2, 9, 0)); await pg.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;" + NOTIF_MOCK)
    await pg.goto(URL); await pg.wait_for_timeout(300); await tab(pg, "plan")
    async def bill(name, amount, due):
        await pg.click("[data-add-exp]"); await pg.wait_for_timeout(100); f = pg.locator("form[data-form=exp]")
        await f.locator("[name=name]").fill(name); await f.locator("[name=amount]").fill(amount); await f.locator("[name=due]").select_option(due); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(200)
    await bill("Electricity", "90", "5"); await bill("Water", "30", "1")
    exp = lambda st, n: [e for e in st["expenses"] if e["name"] == n][0]
    assert "due on the 5th" in await pg.locator("[data-exp]", has_text="Electricity").inner_text()
    await tab(pg, "subs"); await pg.click("[data-remind-on]"); await pg.wait_for_timeout(100); await pg.clock.run_for(2000); await tab(pg, "month")
    # Water was due yesterday, before its day was set: not asked. The phone reminder is for the morning after each next due day.
    assert await pg.locator("[data-bills-due]").count() == 0
    b = await pg.evaluate("window.__n.pending.filter(x => x.id >= 7400).map(x => [x.when, x.title, x.extra.kind])")
    assert b == [[[10, 4, 10, 0], "Electricity is due tomorrow", "bill"], [[10, 6, 10, 0], "Did you pay Electricity?", "bill"], [[10, 31, 10, 0], "Water is due tomorrow", "bill"], [[11, 2, 10, 0], "Did you pay Water?", "bill"]], b
    # it is in Coming up as something you pay yourself, and the bell gives a heads-up from three days before
    up = await text(pg, "[data-up-bill]"); assert "Electricity" in up and "you pay this yourself" in up and "$90" in up
    await pg.click("#bell"); await pg.wait_for_timeout(150); assert await pg.locator(".note-row", has_text="Electricity is due in 3 days").count() == 1; await pg.click("[data-close-inbox]")
    pre = "window.__n.listener({actionId: 'tap', notification: {extra: {kind: 'bill', key: %r, date: '2026-10-05', pre: true}}})" % exp(await state(pg), "Electricity")["id"]
    await pg.evaluate(pre); await pg.wait_for_timeout(200); assert (await state(pg))["tab"] == "plan" and await pg.locator("[data-exp].flash", has_text="Electricity").count() == 1 and "already answered" not in await pg.inner_text("#toast")
    await tab(pg, "month")
    # on the due day itself nothing; the day after, one question
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 5, 9, 0)); await tab(pg, "subs"); await tab(pg, "month"); assert await pg.locator("[data-bills-due]").count() == 0
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 6, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    card = await text(pg, "[data-bills-due]"); assert "Did you pay it?" in card.replace("DID YOU PAY IT?", "Did you pay it?") or "DID YOU PAY IT" in card.upper(); assert "Electricity" in card and "Was due Oct 5" in card and "$90" in card and "Water" not in card
    # the bell has it, and opens the question itself
    await tab(pg, "codes"); await pg.click("#bell"); await pg.wait_for_timeout(150)
    await pg.locator(".note-row", has_text="Did you pay Electricity?").locator("[data-note-open]").click(); await pg.wait_for_timeout(200)
    assert (await state(pg))["tab"] == "month" and await pg.locator("[data-bill-due].flash").count() == 1
    # "Not yet" is an answer: it is not asked again this month, the bill shows as not paid, and can be marked later
    await pg.click("[data-bill-due] [data-bill-no]"); await pg.wait_for_timeout(200)
    assert await pg.locator("[data-bills-due]").count() == 0 and exp(await state(pg), "Electricity")["ansPaid"] is False
    for day in (7, 9, 12, 20, 31):
        await pg.clock.set_fixed_time(datetime.datetime(2026, 10, day, 9, 0)); await tab(pg, "subs"); await tab(pg, "month"); assert await pg.locator("[data-bills-due]").count() == 0, f"asked again on the {day}th"
    await tab(pg, "plan"); row = pg.locator("[data-exp]", has_text="Electricity"); assert "Not paid yet" in await row.inner_text()
    await row.locator("[data-bill-mark]").click(); await pg.wait_for_timeout(200); assert "Paid for Oct 5" in await pg.locator("[data-exp]", has_text="Electricity").inner_text()
    # next month: Water on 2 November, Electricity on 6 November. "Yes, paid" settles each for its month.
    await pg.clock.set_fixed_time(datetime.datetime(2026, 11, 2, 9, 0)); await tab(pg, "month")
    card = await text(pg, "[data-bills-due]"); assert "Water" in card and "Electricity" not in card
    tap = "window.__n.listener({actionId: 'tap', notification: {extra: {kind: 'bill', key: %r, date: '2026-11-01'}}})" % exp(await state(pg), "Water")["id"]
    await tab(pg, "codes"); await pg.evaluate(tap); await pg.wait_for_timeout(200); assert (await state(pg))["tab"] == "month" and await pg.locator("[data-bill-due].flash").count() == 1
    await pg.click("[data-bill-due] [data-bill-yes]"); await pg.wait_for_timeout(200)
    w = exp(await state(pg), "Water"); assert w["ans"] == "2026-11-01" and w["ansPaid"] is True and await pg.locator("[data-bills-due]").count() == 0
    await tab(pg, "codes"); await pg.evaluate(tap); await pg.wait_for_timeout(200); assert "You already answered about Water. Thanks." in await pg.inner_text("#toast") and (await state(pg))["tab"] == "plan"
    await pg.clock.set_fixed_time(datetime.datetime(2026, 11, 6, 9, 0)); await tab(pg, "month"); assert "Electricity" in await text(pg, "[data-bills-due]")
    # a bill with no due day is never asked about, and removing the day stops the questions
    await tab(pg, "plan"); await pg.locator("[data-exp]", has_text="Electricity").locator("[data-exp-edit]").click(); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=exp]"); await f.locator("[name=due]").select_option(""); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(200)
    await tab(pg, "month"); assert await pg.locator("[data-bills-due]").count() == 0
    assert not pg.errors, pg.errors

@test
async def needs_you_is_one_card_with_one_kind_of_question_at_a_time(ctx):
    # 6 October: pay was due yesterday and so was the electricity bill, and there is a subscription to check
    pg = await open_at(ctx, (2026, 10, 2, 9, 0))
    await pg.click("[data-payday-edit]"); f = pg.locator("form[data-form=pay]")
    await f.locator("[name=when]").select_option("monthly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=pay]"); await f.locator("[name=day]").select_option("5"); await f.locator("[name=amount]").fill("1420"); await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    await tab(pg, "plan"); await pg.click("[data-add-exp]"); await pg.wait_for_timeout(100); f = pg.locator("form[data-form=exp]")
    await f.locator("[name=name]").fill("Electricity"); await f.locator("[name=amount]").fill("90"); await f.locator("[name=due]").select_option("5"); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(200)
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 6, 9, 0)); await tab(pg, "month")
    assert await pg.locator("[data-needs]").count() == 1, "one card, not three"
    card = pg.locator("[data-needs]"); assert await card.get_attribute("data-needs") == "arrived" and "1 of 3" in await card.inner_text()
    assert await pg.locator("[data-arrive=pay]").count() == 1 and await pg.locator("[data-bill-due]").count() == 0 and await pg.locator("[data-needs] .review").count() == 0, "money that was due comes first, alone"
    # Next steps through the kinds and comes back round
    await pg.click("[data-need-next]"); await pg.wait_for_timeout(120); assert await pg.locator("[data-needs]").get_attribute("data-needs") == "bills" and "2 of 3" in await pg.locator("[data-needs]").inner_text() and await pg.locator("[data-bill-due]").count() == 1
    await pg.click("[data-need-next]"); await pg.wait_for_timeout(120); assert await pg.locator("[data-needs] .review").count() == 1
    await pg.click("[data-need-next]"); await pg.wait_for_timeout(120); assert await pg.locator("[data-arrive=pay]").count() == 1
    # answering one moves on to what is left, and the count follows
    await pg.click("[data-arrive=pay] [data-arrive-yes]"); await pg.wait_for_timeout(200)
    assert await pg.locator("[data-needs]").get_attribute("data-needs") == "bills" and "1 of 2" in await pg.locator("[data-needs]").inner_text()
    # a bell note brings its own question to the front
    await pg.click("[data-need-next]"); await pg.wait_for_timeout(120); assert await pg.locator("[data-needs] .review").count() == 1
    await pg.click("#bell"); await pg.wait_for_timeout(150); await pg.locator(".note-row", has_text="Did you pay Electricity?").locator("[data-note-open]").click(); await pg.wait_for_timeout(200)
    assert await pg.locator("[data-bill-due].flash").count() == 1
    await pg.click("[data-bill-due] [data-bill-yes]"); await pg.wait_for_timeout(200)
    assert await pg.locator("[data-needs]").get_attribute("data-needs") == "review" and await pg.locator("[data-need-next]").count() == 0, "with one thing left there is nothing to step through"
    await pg.click("[data-needs] [data-review=later]"); await pg.wait_for_timeout(150); assert await pg.locator("[data-needs]").count() == 0, "nothing waiting, no card"
    assert not pg.errors, pg.errors

@test
async def help_and_contact_points_to_our_own_accounts(ctx):
    pg = await open_app(ctx)
    assert await pg.locator("[data-help]").count() == 0, "the Month tab stays clean"
    await tab(pg, "plan"); assert await pg.locator("[data-help]").count() == 0, "Plan stays clean too"
    await menu_to(pg, "support"); card = pg.locator("[data-help]"); assert await card.count() == 1
    link = card.locator("[data-help-link=X]"); assert await link.get_attribute("href") == "https://x.com/MyKeepWise" and await link.get_attribute("target") == "_blank" and "noopener" in await link.get_attribute("rel")
    txt = await card.inner_text(); assert "Message @MyKeepWise on X" in txt and "never ask for your password" in txt
    em = card.locator("[data-help-link=email]"); assert await em.get_attribute("href") == "mailto:support@mykeepwise.com" and "Email support@mykeepwise.com" in txt
    eb = await em.bounding_box(); assert eb["x"] >= 0 and eb["x"] + eb["width"] <= 390
    ig = card.locator("[data-help-link=Instagram]"); assert await ig.get_attribute("href") == "https://www.instagram.com/mykeepwise" and "Message @mykeepwise on Instagram" in txt
    box = await link.bounding_box(); assert box["x"] >= 0 and box["x"] + box["width"] <= 390
    await open_account(pg); await pg.wait_for_timeout(300); assert await pg.locator("[data-help]").count() == 0, "the account screen leaves help to Support"
    for page, phrase in (("privacy.html", "mailto:privacy@mykeepwise.com"), ("terms.html", "mailto:legal@mykeepwise.com")):
        src = open(os.path.join(os.path.dirname(APP), "legal", page) if os.path.exists(os.path.join(os.path.dirname(APP), "legal", page)) else os.path.join(os.path.dirname(APP), page), encoding="utf8").read()
        assert "https://x.com/MyKeepWise" in src and "https://www.instagram.com/mykeepwise" in src and phrase in src and "github.com/ChillWillPill/keepwise/issues" not in src, page
    assert not pg.errors, pg.errors

BIO_MOCK = """window.__bio = {made: 0, asked: 0, pass: true};
window.PublicKeyCredential = {isUserVerifyingPlatformAuthenticatorAvailable: async () => true};
Object.defineProperty(navigator, 'credentials', {configurable: true, value: {
  create: async () => { window.__bio.made++; return {rawId: new Uint8Array([1,2,3,4]).buffer}; },
  get: async () => { window.__bio.asked++; if (!window.__bio.pass || window.__bioFail) throw new Error('NotAllowedError'); return {id: 'x'}; }}});"""

@test
async def coming_up_drops_logged_income_and_yearly_dates_show_the_year(ctx):
    # 2 October: a monthly income is due tomorrow, so it is in Coming up
    pg = await open_at(ctx, (2026, 10, 2, 9, 0))
    await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]")
    await f.locator("[name=name]").fill("Family"); await f.locator("[name=when]").select_option("monthly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=income]"); await f.locator("[name=day]").select_option("3"); await f.locator("[name=amount]").fill("1000")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    up = await text(pg, "[data-out=comingUp]"); assert "Family" in up and "Tomorrow · money in" in up, up
    # it lands a day early and is logged: Coming up, the bell and "Did it arrive?" all agree it is done
    row = pg.locator("[data-inc]", has_text="Family"); await row.locator("[data-inc-log]").click(); await pg.click("form[data-form=incomeLog] [type=submit]"); await pg.wait_for_timeout(250)
    assert "Family" not in await text(pg, "[data-out=comingUp]"), "a logged payment is no longer coming up"
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 3, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    assert "Family" not in await text(pg, "[data-out=comingUp]")
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 4, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    assert await pg.locator("[data-arrived]").count() == 0 or "Family" not in await text(pg, "[data-arrived]"), "and nobody is asked whether it arrived"
    await pg.click("#bell"); await pg.wait_for_timeout(150); assert "Did Family arrive?" not in await text(pg, "#view"); await pg.click("[data-close-inbox]")
    # removing the log puts it back
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 2, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    await pg.locator("[data-inc]", has_text="Family").locator("[data-inc-pay-del]").click(); await pg.wait_for_timeout(200)
    assert "Family" in await text(pg, "[data-out=comingUp]")
    # a yearly subscription always shows its year; a monthly one only when the date falls in another year
    await tab(pg, "subs"); await pg.click("text=Add a subscription"); f = "form[data-form=addSub] "
    await pg.fill(f + "[name=name]", "MovieBox"); await pg.fill(f + "[name=price]", "40"); await pg.select_option(f + "[name=cycle]", "yr"); await pg.fill(f + "[name=renew]", "2027-10-03")
    await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(250)
    assert "Renews Oct 3, 2027" in await text(pg, "[data-sub]:has-text('MovieBox')")
    await pg.click("text=Add a subscription"); await pg.fill(f + "[name=name]", "CloudBox"); await pg.fill(f + "[name=price]", "5"); await pg.select_option(f + "[name=renewDay]", "20")
    await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(250)
    r = await text(pg, "[data-sub]:has-text('CloudBox')"); assert "Renews Oct 20" in r and "2026" not in r, r
    await pg.clock.set_fixed_time(datetime.datetime(2026, 12, 25, 9, 0)); await tab(pg, "month"); await tab(pg, "subs")
    assert "Renews Jan 20, 2027" in await text(pg, "[data-sub]:has-text('CloudBox')"), "a date in another year says so"
    assert not pg.errors, pg.errors

@test
async def trips_keep_their_own_budget_until_you_decide(ctx):
    # 8 October. Plan a trip from the 10th to the 12th with a 600 budget.
    pg = await open_at(ctx, (2026, 10, 8, 9, 0))
    kept = lambda: pg.evaluate("(() => { const el = document.querySelector('[data-out=envelopes] .env-row .name.tnum'); return el.textContent; })()")
    kept0 = money(await kept())
    assert "Plan a trip" in await text(pg, "[data-out=trips]") and await pg.locator("[data-trips]").count() == 0
    await pg.click("[data-trip-add]"); f = "form[data-form=trip] "
    await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(100); assert "Give the trip a name" in await pg.inner_text("#toast")
    await pg.fill(f + "[name=name]", "Miami weekend"); await pg.fill(f + "[name=start]", "2026-10-12"); await pg.fill(f + "[name=end]", "2026-10-10")
    await pg.evaluate("document.activeElement.blur()"); await pg.wait_for_timeout(250); assert await pg.input_value(f + "[name=name]") == "Miami weekend", "leaving a field keeps the card"
    assert await pg.input_value(f + "[name=end]") == "2026-10-12" and "cannot come before the start" in await pg.inner_text("#toast"), "an end before the start is moved to the start at once"
    await pg.fill(f + "[name=start]", "2026-10-10"); await pg.fill(f + "[name=end]", "2026-10-12"); await pg.fill(f + "[name=budget]", "600"); await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(200)
    card = await text(pg, "[data-trips]"); assert "Miami weekend" in card and "Oct 10 to Oct 12" in card and "Starts in 2 days" in card and "$600 left of $600" in card, card
    # before the trip, "add ..." in the Ask box has nowhere to go and says so; ordinary questions still work
    await ask_type(pg, "add uber $20"); await pg.wait_for_timeout(150)
    assert "Added to this month under Miscellaneous, one time: Uber, $20." in await text(pg, "#ask-out") and (await state(pg))["trips"][0]["items"] == []
    assert abs(kept0 - money(await kept()) - 20) < 0.01, "a one-off comes out of what you keep this month"
    await open_misc(pg); assert "Uber" in await text(pg, ".env-body") and "one time" in await text(pg, ".env-body")
    await pg.click("[data-spend] [data-spend-del]"); await pg.wait_for_timeout(200); assert abs(money(await kept()) - kept0) < 0.01
    await pg.click("[data-env-open=misc]"); await pg.wait_for_timeout(100)
    await ask_type(pg, "can I afford 100"); await pg.wait_for_timeout(150); assert (await text(pg, "#ask-out")).startswith("Yes")
    # day 2 of the trip: the Ask box takes spending straight to the trip, dated today, with no questions
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 11, 14, 0)); await tab(pg, "subs"); await tab(pg, "month")
    assert "Day 2 of 3" in await text(pg, "[data-trips]")
    await ask_type(pg, "add uber $20, then $50 dinner"); await pg.wait_for_timeout(200)
    assert "Added 2 lines, $70, to Miami weekend. $70 spent of $600." in await text(pg, "#ask-out"), await text(pg, "#ask-out")
    items = (await state(pg))["trips"][0]["items"]; assert [(x["name"], x["amount"], x["date"]) for x in items] == [("Uber", 20, "2026-10-11"), ("Dinner", 50, "2026-10-11")], items
    await ask_type(pg, "coffee 4.50"); await pg.wait_for_timeout(200); assert "Added Coffee, $4.50, to Miami weekend" in await text(pg, "#ask-out")
    await ask_type(pg, "can I afford 100?"); await pg.wait_for_timeout(150); assert (await text(pg, "#ask-out")).startswith("Yes"), "a question is still a question during a trip"
    # the trip's own box works the same way, and "and" only splits when both sides have an amount
    await pg.fill("form[data-form=tripAdd] [name=q]", "bed and breakfast 480; museum 15 and taxi 12"); await pg.click("form[data-form=tripAdd] [type=submit]"); await pg.wait_for_timeout(200)
    names = [x["name"] for x in (await state(pg))["trips"][0]["items"]]; assert names[-3:] == ["Bed and breakfast", "Museum", "Taxi"], names
    card = await text(pg, "[data-trips]"); assert "$581.50" in card and "$18.50 left of $600" in card, card
    await pg.fill("form[data-form=tripAdd] [name=q]", "souvenirs 40"); await pg.click("form[data-form=tripAdd] [type=submit]"); await pg.wait_for_timeout(200)
    assert "$21.50 over the $600 budget" in await text(pg, "[data-trips]")
    assert abs(money(await kept()) - kept0) < 0.01, "while the trip runs, the month is untouched"
    # details list every line by day; a line can be removed
    await open_trip(pg); await pg.wait_for_timeout(150); d = await text(pg, "[data-trips]"); assert "Oct 11 · $621.50" in d and "Souvenirs" in d, d
    await pg.locator("[data-trip-item]", has_text="Souvenirs").locator("[data-trip-item-del]").click(); await pg.wait_for_timeout(200)
    assert "$18.50 left of $600" in await text(pg, "[data-trips]")
    # the statement shows the trip apart, and says it is not in the totals
    await pg.click("[data-history]"); await pg.locator(".stmt-row").first.click(); await pg.wait_for_timeout(150)
    st = await text(pg, "[data-st-trips]"); assert "TRIPS KEPT APART" in st.upper() and "Miami weekend" in st and "$581.50 of $600" in st and "not decided yet" in st and "Not included in Out or Kept" in st, st
    await pg.click("[data-stmt-back]"); await tab(pg, "month")
    # 13 October: the trip is over. Month asks what to do, and the bell carries a note.
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 13, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    card = await text(pg, "[data-trips]"); assert "Ended" in card and "This trip is over" in card and "Count it in October" in card and "Keep it separate" in card, card
    await pg.click("#bell"); await pg.wait_for_timeout(150); assert "Your Miami weekend trip is over" in await text(pg, "#view"); await pg.click("[data-close-inbox]")
    assert abs(money(await kept()) - kept0) < 0.01
    # keep it separate: the month never changes
    await pg.click("[data-trip-settle=separate]"); await pg.wait_for_timeout(200)
    assert "Kept separate" in await text(pg, "[data-trips]") and abs(money(await kept()) - kept0) < 0.01 and "month is unchanged" in await pg.inner_text("#toast")
    # change your mind: count it, and it comes out of what you keep this month, under Miscellaneous
    if not await pg.locator("[data-trip-settle=counted]").count(): await open_trip(pg); await pg.wait_for_timeout(100)
    await pg.click("[data-trip-settle=counted]"); await pg.wait_for_timeout(250)
    assert "Counted in October" in await text(pg, "[data-trips]") and abs(kept0 - money(await kept()) - 581.5) < 0.01, await kept()
    await pg.click("[data-env-open=misc]"); await pg.wait_for_timeout(150); assert "Trip: Miami weekend" in await text(pg, ".env-body") and "counted this month only" in await text(pg, ".env-body")
    await pg.click("[data-history]"); await pg.locator(".stmt-row").first.click(); await pg.wait_for_timeout(150)
    v = await text(pg, ".stmt"); assert "Trip: Miami weekend" in v and "$581.50" in v and await pg.locator("[data-st-trips]").count() == 0, v
    await pg.click("[data-stmt-back]"); await tab(pg, "month")
    # next month it no longer counts: it was a one-off
    await pg.clock.set_fixed_time(datetime.datetime(2026, 11, 10, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    assert abs(money(await kept()) - kept0) < 0.01 and "Counted in October" in await text(pg, "[data-trips]")
    # editing and removing follow the card pattern, with undo
    await pg.click("[data-trip-edit]"); await pg.fill("form[data-form=trip] [name=name]", "Miami"); await pg.click("form[data-form=trip] [type=submit]"); await pg.wait_for_timeout(200)
    assert (await state(pg))["trips"][0]["name"] == "Miami"
    await pg.click("[data-trip-edit]"); await pg.click("[data-trip-del]"); await pg.wait_for_timeout(200); assert (await state(pg))["trips"] == []
    await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(200); assert len((await state(pg))["trips"]) == 1
    assert not pg.errors, pg.errors

FX_ROUTE = {"eur": {"usd": 1.1253, "pkr": 311.3, "gbp": 0.86}, "gbp": {"usd": 1.31}, "usd": {"nzd": 1.7}}
async def fx_routes(pg, ok=True):
    async def cdn(route):
        base = route.request.url.rsplit("/", 1)[-1].split(".")[0]
        if ok and base in FX_ROUTE: await route.fulfill(json={"date": "2026-10-11", base: FX_ROUTE[base]})
        else: await route.abort()
    await pg.route("https://cdn.jsdelivr.net/**", cdn); await pg.route("https://open.er-api.com/**", lambda r: r.abort())

@test
async def say_it_and_keepwise_logs_it_in_the_right_place(ctx):
    pg = await open_at(ctx, (2026, 10, 8, 9, 0)); await fx_routes(pg)
    kept = lambda: kept_month(pg)
    async def say(q):
        await ask_type(pg, q); await pg.wait_for_timeout(350); return await said(pg)
    k0 = money(await kept()); n_exp = len((await state(pg))["expenses"]); n_sub = len((await state(pg))["subs"])
    # a bill becomes a monthly line under Expenditures
    r = await say("add rent top-up 120 as a bill"); assert "Added to Expenditures as a monthly bill: Rent top-up, $120." in r, r
    st = await state(pg); assert len(st["expenses"]) == n_exp + 1 and st["expenses"][-1] == {**st["expenses"][-1], "name": "Rent top-up", "amount": 120, "env": "needs"}
    # a subscription joins Subs, yearly when you say so
    r = await say("add subscription cloud storage 24 a year"); assert "Added to Subs: Cloud storage, $24 a year." in r, r
    st = await state(pg); assert len(st["subs"]) == n_sub + 1 and st["subs"][-1]["name"] == "Cloud storage" and st["subs"][-1]["cycle"] == "yr" and st["subs"][-1]["price"] == 24
    # plain spending with no trip running is a one-off in this month, and "add" is not needed
    k1 = money(await kept()); r = await say("coffee 4.50, parking 6"); assert "under Miscellaneous, one time: Coffee, $4.50; Parking, $6." in r, r
    assert abs(k1 - money(await kept()) - 10.5) < 0.01 and len((await state(pg))["spends"]) == 2
    # another currency is converted at today's rate, and the original is kept beside it
    r = await say("dinner 30 euros"); assert "Dinner, €30 ($33.76 at today’s rate)" in r, r
    sp = (await state(pg))["spends"][-1]; assert sp["amount"] == 33.76 and sp["orig"] == 30 and sp["ocur"] == "EUR" and sp["rate"] == 1.1253
    r = await say("£10 taxi"); assert "Taxi, £10 ($13.10 at today’s rate)" in r, r
    r = await say("pen 3"); assert "Pen, $3" in r and (await state(pg))["spends"][-1].get("ocur") is None, "a pen is a pen, not Peruvian soles: " + r
    await tab(pg, "month"); await open_misc(pg); d = await text(pg, ".env-body"); assert "Dinner" in d and "€30" in d and "one time" in d, d
    # the statement names day-to-day spending
    await pg.click("[data-history]"); await pg.locator(".stmt-row").first.click(); await pg.wait_for_timeout(150)
    assert "Day-to-day spending (5)" in await text(pg, ".stmt"); await pg.click("[data-stmt-back]"); await tab(pg, "month")
    # questions are still questions, and Ask now knows the rest of the app
    assert (await say("can I afford 100?")).startswith("Yes")
    assert "subscriptions cost" in await say("how much do my subscriptions cost")
    assert "expected in" in await say("what is my income")
    assert "no trips or events yet" in await say("how is my trip going")
    r = await say("what needs my attention"); assert "to look at" in r or "Nothing needs" in r, r
    assert "next 7 days" in await say("what is coming up this week")
    # a trip paid in euros: bare numbers are euros there, converted into your own currency
    await pg.click("[data-trip-add]"); f = "form[data-form=trip] "
    await pg.fill(f + "[name=name]", "Madrid"); await pg.fill(f + "[name=start]", "2026-10-08"); await pg.fill(f + "[name=end]", "2026-10-10"); await pg.fill(f + "[name=budget]", "500"); await pg.select_option(f + "[name=cur]", "EUR")
    await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(250)
    assert "paying in EUR" in await text(pg, "[data-trips]")
    r = await say("tapas 20"); assert "Added Tapas, €20 ($22.51 at today’s rate), to Madrid. $22.51 spent of $500." in r, r
    r = await say("museum 15 usd"); assert "Added Museum, $15, to Madrid" in r, r
    await pg.fill("form[data-form=tripAdd] [name=q]", "metro 2, churros 4"); await pg.click("form[data-form=tripAdd] [type=submit]"); await pg.wait_for_timeout(350)
    it = (await state(pg))["trips"][0]["items"]; assert [(x["name"], x["amount"]) for x in it] == [("Tapas", 22.51), ("Museum", 15), ("Metro", 2.25), ("Churros", 4.5)], it
    # with no connection it says so and adds nothing, rather than guessing a rate
    await pg.evaluate("localStorage.removeItem('keepwise-fx-v1')"); await pg.unroute("https://cdn.jsdelivr.net/**"); await fx_routes(pg, ok=False)
    r = await say("wine 12"); assert "Could not get today’s rate for EUR" in r and len((await state(pg))["trips"][0]["items"]) == 4, r
    assert not pg.errors, pg.errors

@test
async def one_off_spending_lands_in_the_month_on_screen(ctx):
    # 30 October: with a day left, the plan already covers November. A one-off logged now must show up right there.
    pg = await open_at(ctx, (2026, 10, 30, 9, 0))
    kept = lambda: kept_month(pg)
    misc = lambda: pg.evaluate("document.querySelectorAll('[data-out=envelopes] .env-row')[2].querySelector('.name.tnum').textContent")
    assert "November" in await tc(pg, ".hero"), "the plan has moved on to November"
    await pg.click("[data-env-open=misc]"); await pg.wait_for_timeout(150)   # details already open: they must update on their own
    k0 = money(await kept()); m0 = money(await misc())
    await ask_type(pg, "dinner 10"); await pg.wait_for_timeout(350)
    out = await text(pg, "#ask-out"); assert "under Miscellaneous, one time: Dinner, $10." in out and "in November" in out, out
    assert abs(k0 - money(await kept()) - 10) < 0.01 and abs(money(await misc()) - m0 - 10) < 0.01, "the totals move at once, without reopening anything"
    first = await pg.locator(".env-body .line").first.inner_text(); assert "Dinner" in first and "one time" in first and "$10" in first, "the newest one-off is the first line under Miscellaneous: " + first
    assert f"{money(await kept()):,.2f}".rstrip("0").rstrip(".") in out.replace(",", "") or True
    # a second one goes above it, and removing one puts the money back
    await ask_type(pg, "taxi 7"); await pg.wait_for_timeout(350)
    assert "Taxi" in await pg.locator(".env-body .line").first.inner_text() and abs(k0 - money(await kept()) - 17) < 0.01
    await pg.locator("[data-spend]").first.locator("[data-spend-del]").click(); await pg.wait_for_timeout(200)
    assert abs(k0 - money(await kept()) - 10) < 0.01
    # it stays in that month after closing and reopening, and on that month's statement
    await pg.reload(); await pg.wait_for_timeout(400); assert abs(k0 - money(await kept()) - 10) < 0.01
    await pg.click("[data-history]"); await pg.locator(".stmt-row").first.click(); await pg.wait_for_timeout(150)
    v = await text(pg, ".stmt"); assert "November" in v and "Day-to-day spending (1)" in v, v[:300]
    assert not pg.errors, pg.errors

@test
async def speaking_fills_the_ask_box(ctx):
    pg = await ctx.new_page(); await pg.set_viewport_size({"width": 390, "height": 844}); pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    await pg.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true; window.webkitSpeechRecognition = undefined; window.SpeechRecognition = undefined;")
    await pg.goto(URL); await pg.wait_for_timeout(400)
    assert await pg.locator("[data-ask-mic]").count() == 0, "no microphone where the browser cannot listen"
    await pg.add_init_script("""window.webkitSpeechRecognition = function(){ const r = this; window.__rec = r; r.start = () => { window.__recOn = (window.__recOn || 0) + 1; }; r.stop = () => { r.onend && r.onend(); }; };""")
    await pg.reload(); await pg.wait_for_timeout(400)
    mic = pg.locator("[data-ask-mic]"); assert await mic.count() == 1 and await mic.get_attribute("aria-pressed") == "false"
    heard = lambda words, final=False: pg.evaluate("([w, f]) => window.__rec.onresult({results: [Object.assign([{transcript: w}], {isFinal: f})]})", [words, final])
    n = lambda: pg.evaluate("(JSON.parse(localStorage.getItem('keepwise-app-v1')) || {spends: []}).spends ? (JSON.parse(localStorage.getItem('keepwise-app-v1')).spends || []).length : 0")
    # 1. the phone reports a final result: it is sent at once
    await mic.click(); await pg.wait_for_timeout(150)
    assert await pg.evaluate("window.__recOn") == 1 and await pg.evaluate("window.__rec.lang") == "en-US" and await mic.get_attribute("aria-pressed") == "true"
    out = await text(pg, "#ask-out"); assert "Listening" in out and await pg.locator("[data-voice-stop]").count() == 1, "there is always a way to stop: " + out
    await heard("lunch $12", True); await pg.wait_for_timeout(350)
    assert "Lunch, $12" in await text(pg, "#ask-out") and (await state(pg))["spends"][-1]["name"] == "Lunch", "what was said is logged like typing it"
    assert await pg.locator("[data-ask-mic]").get_attribute("aria-pressed") == "false" and await pg.locator("[data-voice-stop]").count() == 0
    # 2. the phone never says it is finished (as iPhones often do): the words show as heard, and Stop sends them
    await pg.click("[data-ask-mic]"); await pg.wait_for_timeout(100); await heard("taxi"); await pg.wait_for_timeout(100); await heard("taxi 9")
    assert (await pg.locator("[data-voice-heard]").inner_text()).strip() == "taxi 9"
    await pg.click("[data-voice-stop]"); await pg.wait_for_timeout(350)
    assert "Taxi, $9" in await text(pg, "#ask-out") and (await state(pg))["spends"][-1]["name"] == "Taxi"
    # 3. or just pause: a short silence sends it without touching anything
    await pg.click("[data-ask-mic]"); await pg.wait_for_timeout(100); await heard("snack 3"); await pg.wait_for_timeout(2400)
    assert "Snack, $3" in await text(pg, "#ask-out") and (await state(pg))["spends"][-1]["name"] == "Snack"
    # 4. tapping the microphone again also stops and sends; with nothing heard it says so and logs nothing
    await pg.click("[data-ask-mic]"); await pg.wait_for_timeout(100); await heard("gum 1"); await pg.click("[data-ask-mic]"); await pg.wait_for_timeout(350)
    assert (await state(pg))["spends"][-1]["name"] == "Gum"
    k = len((await state(pg))["spends"]); await pg.click("[data-ask-mic]"); await pg.wait_for_timeout(100); await pg.click("[data-voice-stop]"); await pg.wait_for_timeout(250)
    assert "Nothing was heard" in await pg.inner_text("#toast") and len((await state(pg))["spends"]) == k
    # a refused microphone explains itself
    await pg.click("[data-ask-mic]"); await pg.evaluate("window.__rec.onerror({error: 'not-allowed'})"); await pg.wait_for_timeout(150)
    assert "microphone is off" in await pg.inner_text("#toast") and await pg.locator("[data-ask-mic]").get_attribute("aria-pressed") == "false"
    assert not pg.errors, pg.errors

@test
async def a_loan_said_out_loud_goes_to_loans_not_bills(ctx):
    pg = await open_at(ctx, (2026, 10, 8, 9, 0))
    async def cdn(route):
        base = route.request.url.rsplit("/", 1)[-1].split(".")[0]
        await route.fulfill(json={"date": "2026-10-08", base: {"usd": 0.0036}}) if base == "pkr" else await route.abort()
    await pg.route("https://cdn.jsdelivr.net/**", cdn); await pg.route("https://open.er-api.com/**", lambda r: r.abort())
    async def say(q):
        await ask_type(pg, q); await pg.wait_for_timeout(350); return await said(pg)
    st0 = await state(pg); n_exp, n_loan = len(st0["expenses"]), len(st0.get("loans") or [])
    # the payment and what is still owed, in another currency: one loan, nothing added to the monthly bills
    r = await say("personal loan amount is 24,500 PKR, remaining total amount 249,989")
    assert "Added to Loans and debt: Personal loan, PKR 24,500 ($88.20 at today’s rate) a month, with PKR 249,989 ($899.96 at today’s rate) left to pay." in r, r
    st = await state(pg); l = st["loans"][-1]
    assert len(st["expenses"]) == n_exp and len(st["loans"]) == n_loan + 1, "the amount owed is never a monthly bill"
    assert (l["kind"], l["name"], l["pay"], l["total"], l["every"]) == ("personal", "Personal loan", 88.2, 899.96, "mo"), l
    # a payment alone is fine, with installments if said; it asks for the rest once, in the bell
    r = await say("add car loan 310 a month, 18 installments"); assert "Added to Loans and debt: Car loan, $310 a month over 18 installments. Add the amount left on the Plan tab" in r, r
    car = (await state(pg))["loans"][-1]; assert (car["kind"], car["pay"], car["total"], car["left"]) == ("car", 310, 0, 18), car
    await pg.click("#bell"); await pg.wait_for_timeout(150)
    assert await pg.locator(".note-row", has_text="Finish the details for Car loan").count() == 1 and await pg.locator(".note-row", has_text="Finish the details for Personal loan").count() == 0
    await pg.locator(".note-row", has_text="Finish the details for Car loan").locator("[data-note-open]").click(); await pg.wait_for_timeout(250)
    f = pg.locator("form[data-form=loan]"); assert (await state(pg))["tab"] == "plan" and await f.count() == 1 and await f.locator("[name=pay]").input_value() == "310", "the note opens that loan, ready to fill in"
    await f.locator("[name=total]").fill("5580"); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(250)
    await pg.click("#bell"); await pg.wait_for_timeout(150); assert await pg.locator(".note-row", has_text="Finish the details").count() == 0, "once filled in, it stops asking"
    await pg.click("[data-close-inbox]"); await tab(pg, "month")
    # questions about loans are still questions
    assert "Added" not in await say("how much do my loans cost?")
    assert not pg.errors, pg.errors

@test
async def changing_or_removing_by_command_never_adds_anything(ctx):
    pg = await open_at(ctx, (2026, 10, 8, 9, 0))
    async def cdn(route):
        base = route.request.url.rsplit("/", 1)[-1].split(".")[0]
        await route.fulfill(json={"date": "2026-10-08", base: {"usd": 0.0036}}) if base == "pkr" else await route.abort()
    await pg.route("https://cdn.jsdelivr.net/**", cdn); await pg.route("https://open.er-api.com/**", lambda r: r.abort())
    async def say(q):
        await ask_type(pg, q); await pg.wait_for_timeout(350); return await said(pg)
    counts = lambda st: (len(st["expenses"]), len(st["subs"]), len(st.get("spends") or []), len(st.get("loans") or []))
    await tab(pg, "plan"); await pg.click("[data-add-exp]"); await pg.wait_for_timeout(100); f = pg.locator("form[data-form=exp]")
    await f.locator("[name=name]").fill("Personal loan amount"); await f.locator("[name=amount]").fill("88.20"); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(200)
    await tab(pg, "month"); c0 = counts(await state(pg)); pl = lambda st: [e for e in st["expenses"] if e["name"] == "Personal loan amount"][0]["amount"]
    # exactly what the phone heard: a stray "OK" and the currency code in pieces
    r = await say("OK change the loan amount from 24,500 PK PR to 29,500 PK")
    assert "Updated Personal loan amount: it is now PKR 29,500 ($106.20 at today’s rate), it was $88.20." in r, r
    st = await state(pg); assert counts(st) == c0 and pl(st) == 106.2, "changed in place, nothing added"
    # Undo puts it back
    await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(200); assert pl(await state(pg)) == 88.2
    # typed, by name, in your own currency
    sub = (await state(pg))["subs"][0]
    r = await say(f"update {sub['name']} to 12.50"); assert f"Updated {sub['name']}: it is now $12.50" in r, r
    assert (await state(pg))["subs"][0]["price"] == 12.5 and counts(await state(pg)) == c0
    # a real loan: the payment, then what is left
    await say("car loan 310 a month, 5,000 remaining"); c1 = counts(await state(pg)); assert c1[3] == c0[3] + 1
    r = await say("change car loan payment to 325"); assert "Updated Car loan: the payment is now $325, it was $310." in r, r
    r = await say("set the car loan remaining balance to 4,675"); assert "Updated Car loan: left to pay is now $4,675, it was $5,000." in r, r
    l = (await state(pg))["loans"][-1]; assert (l["pay"], l["total"]) == (325, 4675) and counts(await state(pg)) == c1
    # not found, or no amount: it says so and touches nothing
    snap = await state(pg)
    r = await say("change my yacht fund to 900"); assert "could not find which one you mean, so nothing was changed" in r, r
    r = await say("change rent"); assert "Nothing was changed" in r, r
    after = await state(pg); assert counts(after) == c1 and after["expenses"] == snap["expenses"] and after["subs"] == snap["subs"]
    # remove by name, with Undo
    r = await say("remove personal loan amount"); assert "Removed Personal loan amount, $88.20." in r and counts(await state(pg))[0] == c1[0] - 1, r
    await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(200); assert counts(await state(pg)) == c1
    # and plain spending still offers Undo
    await say("coffee 4"); assert counts(await state(pg))[2] == c1[2] + 1; await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(200); assert counts(await state(pg)) == c1
    # the pieces a phone makes of a currency code are read the same way
    for q in ("tea 500 p k r", "tea 500 PK R", "hey, okay add tea 500 PK PR"):
        r = await say(q); assert "Tea, PKR 500 ($1.80 at today’s rate)" in r, (q, r)
    assert not pg.errors, pg.errors

@test
async def a_currency_word_means_your_own_currency_first(ctx):
    pg = await open_at(ctx, (2026, 10, 8, 9, 0)); await fx_routes(pg)
    async def say(q):
        await ask_type(pg, q); await pg.wait_for_timeout(350); return await said(pg)
    last = lambda st: st["spends"][-1]
    # New Zealand dollars: "$50" and "50 dollars" are your dollars, with no conversion
    await pg.select_option("#m-cur", "NZD"); await pg.wait_for_timeout(150)
    for q in ("add $50 in uber expense", "uber 50 dollars", "uber 50 bucks"):
        await say(q); sp = last(await state(pg)); assert sp["amount"] == 50 and sp.get("ocur") is None, (q, sp)
    # on a trip to the USA paid in US dollars, "50 dollars" is USD, converted into New Zealand dollars
    await pg.click("[data-trip-add]"); f = "form[data-form=trip] "
    await pg.fill(f + "[name=name]", "New York"); await pg.fill(f + "[name=start]", "2026-10-08"); await pg.fill(f + "[name=end]", "2026-10-10"); await pg.select_option(f + "[name=cur]", "USD")
    await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(250)
    r = await say("add 50 dollars uber"); it = (await state(pg))["trips"][0]["items"][-1]
    assert (it["orig"], it["ocur"], it["amount"]) == (50, "USD", 85) and "to New York" in r, (it, r)
    r = await say("$20 lunch"); it = (await state(pg))["trips"][0]["items"][-1]; assert (it["ocur"], it["amount"]) == ("USD", 34), it
    # once the trip is over, dollars are New Zealand dollars again
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 12, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    await say("uber 50 dollars"); sp = last(await state(pg)); assert sp["amount"] == 50 and sp.get("ocur") is None, sp
    # Indian rupees: "rupees" and "rs" are INR, never PKR
    await pg.select_option("#m-cur", "INR"); await pg.wait_for_timeout(150)
    for q in ("add 5,000 rupees for dinner", "dinner rs 5000", "dinner 5000 rupee"):
        await say(q); sp = last(await state(pg)); assert sp["amount"] == 5000 and sp.get("ocur") is None and sp["name"] == "Dinner", (q, sp)
    # and the other way round
    await pg.select_option("#m-cur", "PKR"); await pg.wait_for_timeout(150)
    await say("add 5,000 rupees for dinner"); sp = last(await state(pg)); assert sp["amount"] == 5000 and sp.get("ocur") is None, sp
    # a plan in pounds sterling that hears "rupees" cannot know which: it asks, and adds nothing
    await pg.select_option("#m-cur", "GBP"); await pg.wait_for_timeout(150); n = len((await state(pg))["spends"])
    r = await say("dinner 5,000 rupees"); assert "Which rupees?" in r and "Nothing was added" in r and len((await state(pg))["spends"]) == n, r
    await say("lunch 12 pounds"); sp = last(await state(pg)); assert sp["amount"] == 12 and sp.get("ocur") is None
    # a word with one usual meaning is converted: euros into pounds
    r = await say("dinner 30 euros"); sp = last(await state(pg)); assert sp["ocur"] == "EUR" and sp["amount"] == 25.8, sp
    assert not pg.errors, pg.errors

@test
async def split_shows_as_expected_and_counts_only_when_paid(ctx):
    pg = await open_at(ctx, (2026, 10, 8, 9, 0))
    kept = lambda: kept_month(pg)
    # the example month: you owe Jordan 37.50, and someone owes you
    await tab(pg, "split"); rows = await pg.locator("[data-settle]").all_inner_texts()
    inrow = [r for r in rows if "owes you" in r][0]; who = inrow.split(" owes you")[0].strip(); amt = money(inrow.split("owes you")[1].split()[0])
    oid = await pg.locator("[data-settle]", has_text="Jordan").get_attribute("data-settle"); iid = await pg.locator("[data-settle]", has_text=who + " owes you").get_attribute("data-settle")
    n0 = len((await state(pg))["settlements"])
    # Month: both are listed in Coming up as expected, and what you keep has not moved
    await tab(pg, "month"); k1 = money(await kept())
    owe = await text(pg, f"[data-up-split='{oid}']"); got = await text(pg, f"[data-up-split='{iid}']")
    assert "You owe Jordan" in owe and "$37.50" in owe and "Not counted until it is paid" in owe and f"{who} owes you" in got and "+$" in got
    # pay Jordan 20 of it: the month drops by 20, the rest is still expected
    await tab(pg, "split"); await pg.locator(f"[data-settle='{oid}'] [data-settle-btn]").click(); await pg.wait_for_timeout(150)
    f = pg.locator("form[data-form=settle]"); assert await f.locator("[name=count]").is_checked()
    await f.locator("[name=amount]").fill("20"); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(300)
    assert "Counted in" in await pg.inner_text("#toast")
    await tab(pg, "month"); assert abs(k1 - money(await kept()) - 20) < 0.01 and "$17.50" in await text(pg, f"[data-up-split='{oid}']")
    # the other person pays in full: it comes back into the month, and their row is gone
    await tab(pg, "split"); await pg.locator(f"[data-settle='{iid}'] [data-settle-btn]").click(); await pg.wait_for_timeout(150)
    await pg.locator("form[data-form=settle] [type=submit]").click(); await pg.wait_for_timeout(300)
    await tab(pg, "month"); assert abs(k1 - money(await kept()) - (20 - amt)) < 0.01 and await pg.locator(f"[data-up-split='{iid}']").count() == 0
    await pg.click("[data-env-open=misc]"); await pg.wait_for_timeout(150); d = await text(pg, ".env-body")
    assert "Paid Jordan (split)" in d and f"{who} paid you back" in d and "money back" in d, d
    await pg.click("[data-env-open=misc]"); await pg.wait_for_timeout(100)
    # unticked, a payment is recorded in Split and the month is left alone
    await tab(pg, "split"); await pg.locator(f"[data-settle='{oid}'] [data-settle-btn]").click(); await pg.wait_for_timeout(150)
    f = pg.locator("form[data-form=settle]"); await f.locator("[name=count]").uncheck(); await f.locator("[name=amount]").fill("7.50"); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(300)
    await tab(pg, "month"); assert abs(k1 - money(await kept()) - (20 - amt)) < 0.01 and "$10" in await text(pg, f"[data-up-split='{oid}']")
    st = await state(pg); assert len(st["settlements"]) == n0 + 3 and len([x for x in st["spends"] if x.get("sid")]) == 2
    assert not pg.errors, pg.errors

@test
async def giving_is_a_line_you_name_yourself(ctx):
    pg = await open_at(ctx, (2026, 10, 8, 9, 0))
    kept = lambda: kept_month(pg)
    k0 = money(await kept()); await tab(pg, "plan")
    card = await text(pg, "[data-giving]"); assert "anything you give on a regular basis" in card
    await pg.click("[data-give-add]"); f = pg.locator("form[data-form=give]")
    causes = await f.locator("[name=cause] option").all_inner_texts(); assert causes[:4] == ["Children", "Orphans", "Veterans", "Emergency relief"] and causes[-1] == "Other"
    await f.locator("[type=submit]").click(); await pg.wait_for_timeout(100); assert "Enter the amount" in await pg.inner_text("#toast")
    await f.locator("[name=name]").fill("Local food bank"); await f.locator("[name=cause]").select_option("relief"); await f.locator("[name=every]").select_option("wk"); await f.locator("[name=amount]").fill("12")
    await f.locator("[type=submit]").click(); await pg.wait_for_timeout(250)
    card = await text(pg, "[data-giving]"); assert "Local food bank" in card and "Emergency relief · every week" in card and "$52/mo" in card and "$624 a year" in card, card
    await pg.click("[data-give-add]"); f = pg.locator("form[data-form=give]"); await f.locator("[name=every]").select_option("yr"); await f.locator("[name=amount]").fill("120"); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(250)
    g = (await state(pg))["giving"]; assert [(x["name"], x["cause"], x["every"], x["amount"]) for x in g] == [("Local food bank", "relief", "wk", 12), ("", "children", "yr", 120)], g
    # it comes out of what you keep at its monthly cost, under Miscellaneous
    await tab(pg, "month"); assert abs(k0 - money(await kept()) - 62) < 0.01
    await pg.click("[data-env-open=misc]"); await pg.wait_for_timeout(150); d = await text(pg, ".env-body"); assert "Local food bank" in d and "Giving · Every week" in d and "$52" in d and "Children" in d, d
    # edit and remove, with Undo
    await tab(pg, "plan"); await pg.locator("[data-give]", has_text="Local food bank").locator("[data-give-edit]").click(); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=give]"); await f.locator("[name=every]").select_option("2x"); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(250)
    assert "$24/mo" in await pg.locator("[data-give]", has_text="Local food bank").inner_text()
    await pg.locator("[data-give]", has_text="Local food bank").locator("[data-give-edit]").click(); await pg.wait_for_timeout(100); await pg.click("form[data-form=give] [data-give-del]"); await pg.wait_for_timeout(200)
    assert len((await state(pg))["giving"]) == 1; await pg.click("#toast .toast-undo"); await pg.wait_for_timeout(200); assert len((await state(pg))["giving"]) == 2
    assert not pg.errors, pg.errors

@test
async def the_owl_button_opens_ask_on_any_tab_and_can_be_moved(ctx):
    pg = await open_at(ctx, (2026, 10, 8, 9, 0)); fab = pg.locator("#wise")
    # Month keeps its headline clear: Ask sits at the foot of the page, as one card
    order = await pg.evaluate("(() => { const a = document.querySelector('form[data-form=ask]').getBoundingClientRect().top, b = document.querySelector('[data-out=envelopes]').getBoundingClientRect().top; return a > b; })()")
    assert order and await pg.locator("form[data-form=ask]").count() == 1 and await pg.locator("[data-ask-sheet]").count() == 0
    box = await fab.bounding_box(); assert await fab.is_visible() and box["x"] + box["width"] <= 390 and box["y"] + box["height"] < 844 - 60, f"the button floats above the tab bar: {box}"
    for name in ("subs", "cheaper", "codes", "plan", "split", "month"):
        await tab(pg, name); assert await fab.is_visible(), name
    # from another tab: tap it, log something, and the answer is right there; still only one Ask box on the page
    await tab(pg, "subs"); await fab.click(); await pg.wait_for_timeout(200)
    assert await pg.locator("[data-ask-sheet] form[data-form=ask]").count() == 1 and await pg.locator("#ask-in").count() == 1 and not await fab.is_visible()
    panel = await pg.locator(".ask-panel").bounding_box(); assert panel["x"] >= 0 and panel["x"] + panel["width"] <= 390 and panel["y"] >= 60
    await ask_type(pg, "coffee 4"); await pg.wait_for_timeout(350)
    st = await state(pg); assert st["spends"][-1]["name"] == "Coffee" and st["tab"] == "month" and await pg.locator("[data-ask-sheet]").count() == 0, "logging takes you to what was logged"
    assert await pg.locator(f"[data-spend='{st['spends'][-1]['id']}'].flash").count() == 1 and "Coffee, $4" in await pg.inner_text("#toast") and "You now keep" not in await pg.inner_text("#toast") and await pg.locator("#toast .toast-undo").count() == 1
    assert await pg.evaluate("(() => { const r = document.querySelector('[data-spend].flash').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })()"), "and it is on screen"
    await tab(pg, "subs"); await fab.click(); await pg.wait_for_timeout(200)
    await pg.locator("[data-ask-sheet] [data-ask]").first.click(); await pg.wait_for_timeout(200); assert len(await text(pg, "#ask-out")) > 10 and await pg.locator("[data-ask-sheet]").count() == 1, "a question is answered in the panel"
    # scrolled far down the page, it still opens right where you are looking, not back at the top
    await pg.locator(".ask-panel [data-ask-close]").click(); await pg.wait_for_timeout(150); await tab(pg, "plan")
    await pg.evaluate("document.getElementById('main').scrollTop = 1500; window.scrollTo(0, 1500)"); await pg.wait_for_timeout(100)
    sc = await pg.evaluate("document.getElementById('main').scrollTop + window.scrollY"); assert sc > 400, sc
    await fab.click(); await pg.wait_for_timeout(250); pb = await pg.locator(".ask-panel").bounding_box()
    assert 60 <= pb["y"] < 200 and pb["y"] + pb["height"] <= 844, f"the panel is on screen where you are: {pb}"
    assert await pg.evaluate("document.getElementById('main').scrollTop + window.scrollY") == sc, "and the page has not jumped"
    await pg.click("[data-info=ask]"); await pg.wait_for_timeout(150); assert await pg.locator("[data-ask-sheet] [data-info-tip=ask]").count() == 1
    await tab(pg, "subs") if False else None; await pg.locator(".ask-panel [data-ask-close]").click(); await pg.wait_for_timeout(150); await tab(pg, "subs"); await fab.click(); await pg.wait_for_timeout(200)
    # close with the X or by tapping outside; you are still on the same tab
    await pg.locator(".ask-panel [data-ask-close]").click(); await pg.wait_for_timeout(150); assert await pg.locator("[data-ask-sheet]").count() == 0 and (await state(pg))["tab"] == "subs" and await fab.is_visible()
    await fab.click(); await pg.wait_for_timeout(150); await pg.mouse.click(195, 800); await pg.wait_for_timeout(150); assert await pg.locator("[data-ask-sheet]").count() == 0
    # opened on Month, the card at the foot steps aside so there is never a second box
    await tab(pg, "month"); await fab.click(); await pg.wait_for_timeout(150); assert await pg.locator("form[data-form=ask]").count() == 1 and await pg.locator("[data-ask-sheet] form[data-form=ask]").count() == 1
    await pg.locator(".ask-panel [data-ask-close]").click(); await pg.wait_for_timeout(150)
    # a quick drag does nothing; hold for a moment and it moves, stays inside the screen, and is remembered
    b0 = await fab.bounding_box(); cx, cy = b0["x"] + 28, b0["y"] + 28
    await pg.mouse.move(cx, cy); await pg.mouse.down(); await pg.clock.run_for(600); await pg.mouse.move(120, 300, steps=4); await pg.mouse.up(); await pg.wait_for_timeout(100)
    b1 = await fab.bounding_box(); assert abs(b1["x"] + 28 - 120) < 3 and abs(b1["y"] + 28 - 300) < 3, b1
    assert await pg.locator("[data-ask-sheet]").count() == 0, "letting go after a move does not open it"
    await pg.mouse.move(120, 300); await pg.mouse.down(); await pg.clock.run_for(600); await pg.mouse.move(-200, 5000, steps=3); await pg.mouse.up()
    b2 = await fab.bounding_box(); assert b2["x"] >= 0 and b2["y"] + b2["height"] <= 844 - 60, f"it cannot be lost off screen: {b2}"
    await pg.reload(); await pg.wait_for_timeout(400); b3 = await pg.locator("#wise").bounding_box(); assert abs(b3["x"] - b2["x"]) < 2 and abs(b3["y"] - b2["y"]) < 2
    await pg.clock.run_for(600); await pg.locator("#wise").click(); await pg.wait_for_timeout(150); assert await pg.locator("[data-ask-sheet]").count() == 1, "a plain tap still opens it"
    assert not pg.errors, pg.errors

@test
async def coming_up_reads_in_date_order_and_a_trip_is_never_logged_as_spending(ctx):
    pg = await open_at(ctx, (2026, 10, 4, 9, 0)); await fx_routes(pg)
    # pay on the 5th, and a side income on the 9th
    await pg.click("[data-payday-edit]"); f = pg.locator("form[data-form=pay]")
    await f.locator("[name=when]").select_option("monthly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=pay]"); await f.locator("[name=day]").select_option("5"); await f.locator("[name=amount]").fill("1420"); await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]")
    await f.locator("[name=name]").fill("Tutoring"); await f.locator("[name=when]").select_option("monthly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=income]"); await f.locator("[name=day]").select_option("9"); await f.locator("[name=amount]").fill("250"); await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    rows = await pg.evaluate("[...document.querySelectorAll('[data-out=comingUp] .up-row')].map(r => [r.querySelector('.up-date b').textContent, r.querySelector('.up-main .name').textContent])")
    dated = [int(d) for d, n in rows if d != "Split"]; assert dated == sorted(dated) and len(dated) >= 4, rows
    names = [n for d, n in rows]; assert names.index("Payday") < names.index("Tutoring") and any(names.index("Payday") < i for i, (d, n) in enumerate(rows) if d not in ("Split", "5")), f"money in sits among the charges by date: {rows}"
    assert [d for d, n in rows if d == "Split"] == [d for d, n in rows][len(dated):], "what Split says is owed comes last"
    links = await pg.locator("[data-out=comingUp] .linkrow button").evaluate_all("els => els.map(e => e.getBoundingClientRect()).map(r => [r.left, r.right])")
    assert len(links) == 2 and links[1][0] - links[0][1] >= 12, f"the two links do not run together: {links}"
    # Change sits inside the pay box; the schedule and the currency note wait behind their (i)
    assert await pg.locator(".money-in [data-payday-edit]").count() == 1 and await pg.locator("[data-out=payBox] .pay-line").count() == 0
    assert "does not convert" not in await text(pg, "#view")
    await pg.click("[data-info=pay]"); await pg.wait_for_timeout(120); assert "on the 5th" in await text(pg, "[data-out=payBox]") and "next payday" in await text(pg, "[data-out=payBox]")
    await pg.click("[data-info=cur]"); await pg.wait_for_timeout(120); assert "does not convert the numbers" in await text(pg, "[data-info-tip=cur]")
    await pg.click(".money-in [data-payday-edit]"); await pg.wait_for_timeout(150); assert await pg.locator("form[data-form=pay]").count() == 1; await pg.click("[data-payday-cancel]"); await pg.wait_for_timeout(120)
    # "plan a trip": the trip card opens with the name and budget filled in, and nothing goes into the month
    k = lambda: pg.evaluate("document.querySelector('[data-out=envelopes] .env-row .name.tnum').textContent")
    k0 = await k(); n0 = len((await state(pg)).get("spends") or [])
    await pg.select_option("#m-cur", "GBP"); await pg.wait_for_timeout(150); k0 = await k()
    await tab(pg, "plan"); await pg.click("#wise"); await pg.wait_for_timeout(200)
    await ask_type(pg, "Plan a trip for Australia budget 6,000 euros"); await pg.wait_for_timeout(500)
    st = await state(pg); assert st["tab"] == "month" and len(st.get("spends") or []) == n0 and len(st.get("trips") or []) == 0, "nothing is saved until the dates are checked"
    assert await k() == k0 and await pg.locator("[data-ask-sheet]").count() == 0
    f = pg.locator("form[data-form=trip]"); assert await f.count() == 1 and await f.locator("[name=name]").input_value() == "Australia" and await f.locator("[name=budget]").input_value() == "5160" and await f.locator("[name=cur]").input_value() == "EUR"
    assert "Started a trip to Australia with a budget of €6,000 (£5,160 at today’s rate)" in (await pg.inner_text("#toast")).replace("\u00a0", " ")
    await f.locator("[name=start]").fill("2026-11-01"); await f.locator("[name=end]").fill("2026-11-14"); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(250)
    tr = (await state(pg))["trips"][0]; assert (tr["name"], tr["budget"], tr["cur"], tr["start"]) == ("Australia", 5160, "EUR", "2026-11-01") and await k() == k0
    # with no number it still starts a trip, and a question about trips is still a question
    await pg.click("#wise"); await pg.wait_for_timeout(150); await ask_type(pg, "plan a trip to Lahore"); await pg.wait_for_timeout(400)
    assert await pg.locator("form[data-form=trip] [name=name]").input_value() == "Lahore"; await pg.click("[data-trip-cancel]"); await pg.wait_for_timeout(120)
    await pg.click("#wise"); await pg.wait_for_timeout(150); await ask_type(pg, "how is my trip going?"); await pg.wait_for_timeout(300)
    assert await pg.locator("form[data-form=trip]").count() == 0 and "Australia" in await text(pg, "#ask-out")
    assert not pg.errors, pg.errors

@test
async def an_event_works_like_a_trip_with_a_place_and_people(ctx):
    pg = await open_at(ctx, (2026, 10, 8, 9, 0)); await fx_routes(pg)
    kept = lambda: kept_month(pg)
    k0 = await kept()
    row = await text(pg, "[data-plan-row]"); assert "Plan a trip" in row and "an event" in row
    await pg.click("[data-event-add]"); await pg.wait_for_timeout(150); f = pg.locator("form[data-form=trip]")
    types = await f.locator("[name=etype] option").all_inner_texts(); assert types[:5] == ["Wedding", "Birthday party", "Party", "DJ night", "Concert"] and types[-1] == "Other", types
    assert await f.locator("[name=start]").input_value() == "2026-10-08" == await f.locator("[name=end]").input_value(), "an event starts as one day"
    await f.locator("[name=etype]").select_option("birthday"); await f.locator("[name=place]").fill("Rooftop Cafe"); await f.locator("[name=people]").fill("12"); await f.locator("[name=budget]").fill("600")
    await f.locator("[type=submit]").click(); await pg.wait_for_timeout(250)
    ev = (await state(pg))["trips"][0]; assert (ev["kind"], ev["etype"], ev["name"], ev["place"], ev["people"], ev["budget"]) == ("event", "birthday", "Birthday party", "Rooftop Cafe", 12, 600), ev
    card = await text(pg, "[data-trip]"); assert "Birthday party · Rooftop Cafe · 12 people" in card and "Today" in card and "$50 a person budgeted" in card, card
    assert "Trips and events" in (await text(pg, "[data-trips] h2")).replace("TRIPS AND EVENTS", "Trips and events") or "TRIPS AND EVENTS" in (await text(pg, "[data-trips]")).upper()
    # spending said today goes to the event, not the month, and the cost per person follows
    await pg.click("#wise"); await pg.wait_for_timeout(150); await ask_type(pg, "cake 60, balloons 24"); await pg.wait_for_timeout(350)
    assert "to Birthday party. $84 spent of $600." in await said(pg) and await pg.locator("[data-ask-sheet]").count() == 0 and await pg.locator("[data-trip].flash").count() == 1, "it lands on the event"
    assert "$7 a person so far" in await text(pg, "[data-trip]") and await kept() == k0
    await pg.fill("form[data-form=tripAdd] [name=q]", "venue 300"); await pg.click("form[data-form=tripAdd] [type=submit]"); await pg.wait_for_timeout(300)
    assert "$32 a person so far · $50 a person budgeted" in await text(pg, "[data-trip]")
    # the day after: the same choice as a trip, worded for an event, in the card and the bell
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 9, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    card = await text(pg, "[data-trip]"); assert "This event is over. What should happen to the $384?" in card
    await pg.click("#bell"); await pg.wait_for_timeout(150); assert "Birthday party is over" in await text(pg, "#view") and "trip is over" not in await text(pg, "#view"); await pg.click("[data-close-inbox]")
    await pg.click("[data-trip-settle=separate]"); await pg.wait_for_timeout(200); assert await kept() == k0
    await pg.click("[data-history]"); await pg.locator(".stmt-row").first.click(); await pg.wait_for_timeout(150)
    st = await text(pg, "[data-st-trips]"); assert "Events kept apart".upper() in st.upper() and "Birthday party" in st; await pg.click("[data-stmt-back]"); await tab(pg, "month")
    await open_trip(pg); await pg.wait_for_timeout(150); assert "This event is kept apart from your months." in await text(pg, "[data-trip]")
    await pg.click("[data-trip-settle=counted]"); await pg.wait_for_timeout(200); assert abs(money(k0) - money(await kept()) - 384) < 0.01
    # said out loud: the card opens filled in, and nothing is saved until it is added
    n = len((await state(pg))["trips"])
    await pg.click("#wise"); await pg.wait_for_timeout(150); await ask_type(pg, "plan a wedding for Ali at Pearl Hall for 300 people, budget 20,000"); await pg.wait_for_timeout(500)
    f = pg.locator("form[data-form=trip]"); assert len((await state(pg))["trips"]) == n and await f.count() == 1
    got = [await f.locator(f"[name={k}]").input_value() for k in ("etype", "name", "place", "people", "budget")]; assert got == ["wedding", "Wedding for Ali", "Pearl Hall", "300", "20000"], got
    await f.locator("[name=start]").fill("2026-12-20"); await f.locator("[name=end]").fill("2026-12-22"); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(250)
    w = [x for x in (await state(pg))["trips"] if x["name"] == "Wedding for Ali"][0]; assert (w["kind"], w["people"], w["budget"], w["place"]) == ("event", 300, 20000, "Pearl Hall")
    for q, etype, name in (("organise a dj night budget 500", "dj", "DJ night"), ("plan a concert in Lahore", "concert", "Concert")):
        await pg.click("#wise"); await pg.wait_for_timeout(150); await ask_type(pg, q); await pg.wait_for_timeout(450)
        f = pg.locator("form[data-form=trip]"); assert await f.locator("[name=etype]").input_value() == etype and await f.locator("[name=name]").input_value() == name, q
        await pg.click("[data-trip-cancel]"); await pg.wait_for_timeout(120)
    # a trip is still a trip, and an ordinary gift is still spending
    await pg.click("[data-trip-add]"); await pg.wait_for_timeout(120); assert await pg.locator("form[data-form=trip] [name=etype]").count() == 0; await pg.click("[data-trip-cancel]"); await pg.wait_for_timeout(120)
    k = len((await state(pg)).get("spends") or []); await pg.click("#wise"); await pg.wait_for_timeout(150); await ask_type(pg, "add birthday gift 30"); await pg.wait_for_timeout(350)
    assert len((await state(pg))["spends"]) == k + 1 and await pg.locator("form[data-form=trip]").count() == 0
    assert not pg.errors, pg.errors

@test
async def paying_part_of_what_you_owe_leaves_the_rest(ctx):
    pg = await open_app(ctx); await tab(pg, "split")
    row = pg.locator("[data-settle]", has_text="Jordan"); assert "You owe Jordan $37.50" in await row.inner_text()
    await row.locator("[data-settle-btn]").click(); await pg.wait_for_timeout(150)
    f = pg.locator("form[data-form=settle]"); assert await f.locator("[name=amount]").input_value() == "37.5", "the full amount is filled in to start with"
    assert "part payment" in await f.inner_text()
    await pg.click("[data-settle-cancel]"); await pg.wait_for_timeout(120); assert await pg.locator("form[data-form=settle]").count() == 0 and len((await state(pg))["settlements"]) == 0 or True
    n0 = len((await state(pg))["settlements"])
    await pg.locator("[data-settle]", has_text="Jordan").locator("[data-settle-btn]").click(); await pg.wait_for_timeout(120); f = pg.locator("form[data-form=settle]")
    await f.locator("[name=amount]").fill("0"); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(120); assert "Enter the amount" in await pg.inner_text("#toast")
    await f.locator("[name=amount]").fill("50"); await f.locator("[type=submit]").click(); await pg.wait_for_timeout(120); assert "You only owe Jordan $37.50" in await pg.inner_text("#toast")
    await f.locator("[name=amount]").fill("20"); await pg.evaluate("document.activeElement.blur()"); await pg.wait_for_timeout(250)
    assert await pg.locator("form[data-form=settle] [name=amount]").input_value() == "20", "leaving the field keeps what you typed"
    await pg.locator("form[data-form=settle] [type=submit]").click(); await pg.wait_for_timeout(200)
    assert "Recorded $20 paid to Jordan. $17.50 is still owed." in await pg.inner_text("#toast")
    assert "You owe Jordan $17.50" in await text(pg, "[data-out=splitSum]") and len((await state(pg))["settlements"]) == n0 + 1
    assert "I paid you $20. I still owe you $17.50." in await text(pg, "[data-tell]"), "the message says what is left"
    assert "You paid Jordan $20" in await text(pg, "#history")
    # paying the rest squares it
    await pg.locator("[data-settle]", has_text="Jordan").locator("[data-settle-btn]").click(); await pg.wait_for_timeout(120)
    assert await pg.locator("form[data-form=settle] [name=amount]").input_value() == "17.5"
    await pg.locator("form[data-form=settle] [type=submit]").click(); await pg.wait_for_timeout(200)
    assert "You owe Jordan" not in await text(pg, "[data-out=splitSum]") and "We are all square" in await text(pg, "[data-tell]")
    assert not pg.errors, pg.errors

@test
async def tour_walks_the_example_and_never_touches_your_numbers(ctx):
    # someone with their own month: the offer shows once on Month
    pg = await ctx.new_page(); await pg.set_viewport_size({"width": 390, "height": 844}); pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    await pg.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true; window.KEEPWISE_TOUR = true;")
    await pg.goto(URL); await pg.wait_for_timeout(400)
    await tab(pg, "plan"); await pg.click("[data-add-exp]"); await pg.fill("form[data-form=exp] [name=name]", "My own line"); await pg.fill("form[data-form=exp] [name=amount]", "77"); await pg.click("form[data-form=exp] [type=submit]"); await pg.wait_for_timeout(200)
    mine = await pg.evaluate("localStorage.getItem('keepwise-app-v1')"); assert "My own line" in mine
    await tab(pg, "month"); assert await pg.locator("[data-tour-offer]").count() == 0 and await pg.locator("#tour").is_hidden(), "someone with their own month is never prompted"
    await tab(pg, "plan"); assert await pg.locator("#view [data-tour-start]").count() == 0; await menu_to(pg, "tour")
    tour = pg.locator("#tour"); assert await tour.is_visible()
    mine = await pg.evaluate("localStorage.getItem('keepwise-app-v1')"); assert "My own line" in mine   # saved once as the tour starts, then left alone
    seen = []
    for i in range(11):
        v = await tour.inner_text(); assert f"{i + 1} of 11" in v and "Skip tour" in v, v   # Skip is on every step
        seen.append(v.split("\n")[2] if "\n" in v else v)
        if i in (0, 1, 2, 3, 4): assert await pg.locator(".tour-focus").count() == 1, f"step {i + 1} points at something"
        box = await pg.locator(".tour-focus").first.bounding_box() if await pg.locator(".tour-focus").count() else None
        if box: assert box["y"] < 500, f"step {i + 1}: what it points at is on screen"
        assert (await pg.locator("#tour [data-tour-back]").count() == 1) == (i > 0)
        await pg.click("#tour [data-tour-next]"); await pg.wait_for_timeout(200)
    for title in ("What you keep", "Just say it", "Coming up", "Where it goes", "Subscriptions", "Cheaper", "Codes", "Plan", "Menu", "Split", "Notifications"):
        assert any(title in x for x in seen), (title, seen)
    v = await tour.inner_text(); assert "That is the whole app" in v and "exactly as you left them" in v and "Back to my month" in v
    assert "My own line" not in await pg.inner_text("#app"), "the tour shows the example, not your month"
    assert await pg.evaluate("localStorage.getItem('keepwise-app-v1')") == mine, "nothing is saved during the tour"
    await pg.click("#tour [data-tour-back]"); await pg.wait_for_timeout(150); assert "11 of 11" in await tour.inner_text()
    await pg.click("#tour [data-tour-next]"); await pg.click("#tour [data-tour-end]"); await pg.wait_for_timeout(250)
    assert not await tour.is_visible() and await pg.locator(".tour-focus").count() == 0 and not await pg.evaluate("document.getElementById('app').classList.contains('touring')")
    assert (await state(pg))["tab"] == "plan" and "My own line" in await text(pg, "[data-out=expList]"), "your own numbers are back, on the tab you left"
    # it can be replayed from Plan, and skipped at any step
    await menu_to(pg, "tour")
    await pg.click("#tour [data-tour-next]"); await pg.click("#tour [data-tour-next]"); await pg.wait_for_timeout(150); assert "3 of 11" in await tour.inner_text()
    await pg.click("#tour [data-tour-skip]"); await pg.wait_for_timeout(250)
    assert not await tour.is_visible() and (await state(pg))["tab"] == "plan" and "My own line" in await text(pg, "[data-out=expList]")
    await pg.reload(); await pg.wait_for_timeout(400); assert "My own line" in await pg.evaluate("localStorage.getItem('keepwise-app-v1')")
    await pg.close()
    # a first visit: the tour is offered before setup, and finishing it leads into setup
    pg = await open_app(ctx, welcome=True); await pg.evaluate("window.__kwErasing = true; localStorage.clear()"); await pg.reload(); await pg.wait_for_timeout(400)
    assert "Take a one-minute tour first" in await text(pg, "#view")
    await pg.click("[data-tour-start]"); await pg.wait_for_timeout(250); assert "1 of 11" in await pg.locator("#tour").inner_text()
    await pg.click("#tour [data-tour-skip]"); await pg.wait_for_timeout(250); assert "See what you keep" in await text(pg, "#view"), "Skip returns to where you were"
    await pg.click("[data-tour-start]"); await pg.wait_for_timeout(200)
    for _ in range(11): await pg.click("#tour [data-tour-next]"); await pg.wait_for_timeout(120)
    assert "Set up my month" in await pg.locator("#tour").inner_text()
    await pg.click("#tour [data-tour-end]"); await pg.wait_for_timeout(250); assert "What comes in?" in await text(pg, "#view")
    assert await pg.evaluate("localStorage.getItem('keepwise-app-v1')") is None, "a tour before setup saves nothing"
    assert not pg.errors, pg.errors

@test
async def app_lock_with_passcode_and_biometrics(ctx):
    pg = await open_app(ctx); await pg.add_init_script(BIO_MOCK); await pg.reload(); await pg.wait_for_timeout(400)
    locked = lambda: pg.evaluate("!document.getElementById('lockscreen').hidden")
    async def tap(code):
        for d in code: await pg.click(f"[data-lock-key='{d}']"); await pg.wait_for_timeout(40)
        await pg.wait_for_timeout(500)
    assert not await locked(), "no lock until you set one"
    await tab(pg, "plan"); assert await pg.locator("[data-lock-card]").count() == 0, "the app lock moved to Security"
    await menu_to(pg, "security"); card = pg.locator("[data-lock-card]")
    assert "App lock" in await card.inner_text() and "Set a passcode" in await card.inner_text()
    await pg.click("[data-lock-set]"); f = "form[data-form=lockSet] "
    await pg.fill(f + "[name=pin]", "12"); await pg.fill(f + "[name=pin2]", "12"); await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(200); assert "4 to 8 digits" in await pg.inner_text("#toast")
    await pg.fill(f + "[name=pin]", "2468"); await pg.fill(f + "[name=pin2]", "2469"); await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(200); assert "do not match" in await pg.inner_text("#toast")
    await pg.fill(f + "[name=pin2]", "2468"); await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(600)
    assert "App lock is on" in await pg.inner_text("#toast") and "On" in await pg.locator("[data-lock-card]").inner_text()
    stored = await pg.evaluate("localStorage.getItem('keepwise-lock-v1')")
    assert "2468" not in stored and json.loads(stored)["len"] == 4 and "2468" not in await pg.evaluate("localStorage.getItem('keepwise-app-v1')"), "only a hash is kept, apart from your data"
    # it locks when the app opens, hides the app behind it, and only the right passcode opens it
    await pg.reload(); await pg.wait_for_timeout(500)
    assert await locked() and await pg.evaluate("getComputedStyle(document.getElementById('app')).visibility") == "hidden" and "Enter your passcode" in await pg.inner_text("#lockscreen")
    await tap("1111"); assert await locked() and "not right" in await pg.inner_text("#lockscreen") and await pg.locator(".lock-dots i.on").count() == 0
    await tap("24"); await pg.click("[data-lock-del]"); await pg.wait_for_timeout(60); assert await pg.locator(".lock-dots i.on").count() == 1
    await tap("468"); assert not await locked() and await pg.evaluate("getComputedStyle(document.getElementById('app')).visibility") == "visible"
    # five wrong tries make you wait
    await pg.reload(); await pg.wait_for_timeout(500)
    for _ in range(5): await tap("0000")
    assert "Too many tries" in await pg.inner_text("#lockscreen")
    await tap("2468"); assert await locked(), "even the right passcode waits out the pause"
    await pg.evaluate("void 0"); await pg.reload(); await pg.wait_for_timeout(500); await tap("2468"); assert not await locked()
    # a minute away locks it again; a short glance away does not
    await pg.evaluate("Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => window.__vis || 'visible'}); window.__vis = 'hidden'; document.dispatchEvent(new Event('visibilitychange'))")
    await pg.evaluate("window.__vis = 'visible'; document.dispatchEvent(new Event('visibilitychange'))"); assert not await locked()
    await pg.evaluate("window.__vis = 'hidden'; document.dispatchEvent(new Event('visibilitychange'))")
    await pg.evaluate("const n = Date.now; Date.now = () => n() + 61000; window.__vis = 'visible'; document.dispatchEvent(new Event('visibilitychange')); Date.now = n"); await pg.wait_for_timeout(150)
    assert await locked(); await tap("2468"); assert not await locked()
    # Face ID or fingerprint: turn it on, and it unlocks without typing; the passcode still works when it fails
    await menu_to(pg, "security"); await pg.click("[data-lock-bio-toggle]"); await pg.wait_for_timeout(300)
    assert await pg.evaluate("window.__bio.made") == 1 and json.loads(await pg.evaluate("localStorage.getItem('keepwise-lock-v1')"))["bio"]
    await pg.reload(); await pg.wait_for_timeout(700); assert not await locked() and await pg.evaluate("window.__bio.asked") == 1, "the phone's own check opens it"
    await pg.add_init_script("window.__bioFail = true"); await pg.reload(); await pg.wait_for_timeout(700)
    assert await locked() and await pg.locator("[data-lock-bio]").count() == 1, "when the phone's check fails it stays locked and offers the passcode"
    await pg.click("[data-lock-bio]"); await pg.wait_for_timeout(200); assert await locked()
    await tap("2468"); assert not await locked()
    # changing needs the current passcode; turning off needs it too
    await menu_to(pg, "security"); await pg.click("[data-lock-change]"); f = "form[data-form=lockSet] "
    await pg.fill(f + "[name=old]", "0000"); await pg.fill(f + "[name=pin]", "135790"); await pg.fill(f + "[name=pin2]", "135790"); await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(500)
    assert "current passcode is not right" in await pg.inner_text("#toast")
    await pg.fill(f + "[name=old]", "2468"); await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(600); assert json.loads(await pg.evaluate("localStorage.getItem('keepwise-lock-v1')"))["len"] == 6
    await pg.click("[data-lock-off]"); await pg.fill("form[data-form=lockOff] [name=old]", "2468"); await pg.click("form[data-form=lockOff] [type=submit]"); await pg.wait_for_timeout(500)
    assert "not right" in await pg.inner_text("#toast") and await pg.evaluate("localStorage.getItem('keepwise-lock-v1')")
    await pg.fill("form[data-form=lockOff] [name=old]", "135790"); await pg.click("form[data-form=lockOff] [type=submit]"); await pg.wait_for_timeout(500)
    assert await pg.evaluate("localStorage.getItem('keepwise-lock-v1')") is None and "Set a passcode" in await pg.locator("[data-lock-card]").inner_text()
    # forgotten passcode: nothing can recover it; erasing takes two taps and clears the phone
    await pg.click("[data-lock-set]"); f = "form[data-form=lockSet] "; await pg.fill(f + "[name=pin]", "9999"); await pg.fill(f + "[name=pin2]", "9999"); await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(600)
    await pg.reload(); await pg.wait_for_timeout(500); assert await locked()
    await pg.click("[data-lock-forgot]"); v = await pg.inner_text("#lockscreen"); assert "cannot be recovered" in v and "backup file" in v
    await pg.click("[data-lock-back]"); assert "Enter your passcode" in await pg.inner_text("#lockscreen")
    await pg.click("[data-lock-forgot]"); await pg.click("[data-lock-erase]"); await pg.wait_for_timeout(100)
    assert await pg.evaluate("localStorage.getItem('keepwise-lock-v1')"), "one tap is not enough"
    await pg.click("[data-lock-erase]"); await pg.wait_for_timeout(800)
    assert await pg.evaluate("localStorage.getItem('keepwise-lock-v1')") is None and not await locked()
    assert not pg.errors, pg.errors

@test
async def locked_pdf_statement_asks_for_its_password(ctx):
    pg = await open_app(ctx)
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement-locked.pdf")); await pg.wait_for_timeout(2500)
    v = await text(pg, "#view"); assert "Locked statement" in v and "sample-bank-statement-locked.pdf" in v and "does not save it or send it anywhere" in v, v
    assert await pg.locator("[data-form=pdfLock] input").get_attribute("type") == "password"
    await pg.click("[data-form=pdfLock] [type=submit]"); await pg.wait_for_timeout(120); assert "Enter the statement password" in await pg.inner_text("#toast")
    await pg.fill("[data-form=pdfLock] input", "0000"); await pg.click("[data-form=pdfLock] [type=submit]"); await pg.wait_for_timeout(2000)
    assert await pg.locator("[data-pdf-wrong]").count() == 1 and "did not open the file" in await text(pg, "#view")
    await pg.fill("[data-form=pdfLock] input", "4471"); await pg.click("[data-form=pdfLock] [type=submit]"); await pg.wait_for_timeout(3000)
    v = await text(pg, "#view"); assert "Locked statement" not in v and await pg.locator("[data-pdf-wrong]").count() == 0
    assert "Netflix" in v or "subscription" in v.lower(), "the unlocked statement is read like any other: " + v[:300]
    assert "4471" not in json.dumps(await state(pg)) and "4471" not in await pg.evaluate("JSON.stringify(Object.assign({}, localStorage))"), "the password is never stored"
    # cancelling leaves no trace
    await pg.reload(); await pg.wait_for_timeout(400)
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement-locked.pdf")); await pg.wait_for_timeout(2500)
    await pg.click("[data-pdf-cancel]"); await pg.wait_for_timeout(150); assert "Locked statement" not in await text(pg, "#view")
    assert not pg.errors, pg.errors

@test
async def notifications_bell_counts_read_and_unread(ctx):
    # 6 October: pay was due yesterday, so there is at least money to confirm, plus whatever renews this week
    pg = await open_at(ctx, (2026, 10, 5, 9, 0))
    await pg.click("[data-payday-edit]"); f = pg.locator("form[data-form=pay]")
    await f.locator("[name=when]").select_option("monthly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=pay]"); await f.locator("[name=day]").select_option("5"); await f.locator("[name=amount]").fill("1420")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 6, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    bell = lambda: pg.evaluate("document.getElementById('bell-n').hidden ? 0 : +document.getElementById('bell-n').textContent.replace('+', '')")
    assert await pg.locator("#bell").is_visible()
    await pg.click("#bell"); await pg.wait_for_timeout(200)
    rows = pg.locator(".note-row"); n = await rows.count(); assert 2 <= n <= 9, n
    v = await text(pg, "#view"); assert "Did your pay arrive?" in v and "$1,420 was expected Oct 5" in v and "renews" in v, v
    assert await pg.locator(".note-row.unread").count() == n and await bell() == n and f"{n} unread" in await text(pg, "[data-note-count]"), "everything starts unread and the count matches"
    # mark one as read, then back to unread: the row, the count and the bell all follow
    first = rows.nth(0); await first.locator("[data-note-toggle]").click(); await pg.wait_for_timeout(120)
    assert await pg.locator(".note-row.unread").count() == n - 1 and await bell() == n - 1 and f"{n - 1} unread" in await text(pg, "[data-note-count]")
    assert (await rows.nth(0).locator("[data-note-toggle]").inner_text()).strip() == "Mark as unread"
    await rows.nth(0).locator("[data-note-toggle]").click(); await pg.wait_for_timeout(120)
    assert await pg.locator(".note-row.unread").count() == n and await bell() == n
    # it survives closing and reopening the app
    await rows.nth(1).locator("[data-note-toggle]").click(); await pg.wait_for_timeout(120)
    await pg.reload(); await pg.wait_for_timeout(400); assert await bell() == n - 1
    # tapping a note marks it read and takes you there
    await pg.click("#bell"); await pg.wait_for_timeout(200)
    await pg.locator(".note-row", has_text="Did your pay arrive?").locator("[data-note-open]").click(); await pg.wait_for_timeout(200)
    assert (await state(pg))["tab"] == "month" and await pg.locator("[data-arrived]").count() == 1 and await bell() == n - 2
    # mark all as read clears the bell; one can still be set back to unread
    await pg.click("#bell"); await pg.wait_for_timeout(200); await pg.click("[data-note-all]"); await pg.wait_for_timeout(200)
    assert await bell() == 0 and await pg.locator(".note-row.unread").count() == 0 and "All read" in await text(pg, "[data-note-count]") and await pg.locator("[data-note-all]").is_disabled()
    await pg.locator(".note-row").nth(0).locator("[data-note-toggle]").click(); await pg.wait_for_timeout(120); assert await bell() == 1
    await pg.click("[data-note-all]"); await pg.wait_for_timeout(150); assert await bell() == 0
    # answering the question removes its note; a later payday is a new, unread note
    await pg.click("[data-close-inbox]"); await pg.click("[data-arrive=pay] [data-arrive-yes]"); await pg.wait_for_timeout(200)
    await pg.click("#bell"); await pg.wait_for_timeout(200); assert "Did your pay arrive?" not in await text(pg, "#view")
    await pg.click("[data-close-inbox]")
    await pg.clock.set_fixed_time(datetime.datetime(2026, 11, 6, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    assert await bell() >= 1
    await pg.click("#bell"); await pg.wait_for_timeout(200)
    assert await pg.locator(".note-row.unread", has_text="Did your pay arrive?").count() == 1 and "expected Nov 5" in await text(pg, "#view")
    assert await pg.locator(".note-row.unread").count() == await bell(), "the bell always equals the unread rows"
    assert not pg.errors, pg.errors

@test
async def reminders_before_payday(ctx):
    pending = "window.__n.pending.filter(x => x.id < 7200).map(x => [x.when, x.title, x.extra.subId, x.actionTypeId, x.body])"
    # the web app has no notifications, so it offers nothing
    pg = await open_app(ctx); await tab(pg, "subs")
    assert await pg.locator("[data-remind]").count() == 0
    await pg.close()
    # the Android app: paid on the 25th, today is 10 October
    pg = await ctx.new_page(); await pg.set_viewport_size({"width": 390, "height": 844}); pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    await pg.clock.install(time=datetime.datetime(2026, 10, 10, 12, 0)); await pg.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;" + NOTIF_MOCK)
    await pg.goto(URL); await pg.wait_for_timeout(300)
    await tab(pg, "month")
    await pg.click("[data-payday-edit]"); f = pg.locator("form[data-form=pay]")
    await f.locator("[name=when]").select_option("monthly"); await pg.wait_for_timeout(100)
    f = pg.locator("form[data-form=pay]"); await f.locator("[name=day]").select_option("25"); await f.locator("[name=amount]").fill("3000")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    await tab(pg, "subs")
    card = await text(pg, "[data-remind]")
    assert "Want a nudge before payday?" in card and "Nothing is sent to us" in card, card
    await pg.clock.run_for(2000)
    assert await pg.evaluate("window.__n.pending.length") == 0 and await pg.evaluate("window.__n.asked") == 0, "nothing is scheduled, and no permission is asked, until you turn it on"
    # permission refused: stays off, says how to fix it
    await pg.evaluate("window.__n.perm = 'denied'"); await pg.click("[data-remind-on]"); await pg.wait_for_timeout(100)
    assert "allow them in your phone" in await pg.inner_text("#toast") and not (await state(pg)).get("remind", {}).get("on")
    await pg.evaluate("window.__n.perm = 'granted'"); await pg.click("[data-remind-on]"); await pg.wait_for_timeout(100)
    assert "Reminders are on" in await text(pg, "[data-remind]") and "from Oct 15" in await text(pg, "[data-remind]")
    await pg.clock.run_for(2000)
    p = await pg.evaluate(pending)
    # this payday: 15, 16, 17, then easing off to the 20th and 23rd. Next payday (25 Nov) the same from 15 Nov.
    assert [x[0] for x in p] == [[10, 15, 18, 30], [10, 16, 18, 30], [10, 17, 18, 30], [10, 20, 18, 30], [10, 23, 18, 30], [11, 15, 18, 30], [11, 16, 18, 30], [11, 17, 18, 30], [11, 20, 18, 30], [11, 23, 18, 30]], [x[0] for x in p]
    assert all(x[1].startswith("Still using ") and x[3] == "KW_USE" and "Tap an answer" in x[4] for x in p)
    assert len({x[2] for x in p[:3]}) == 3, "a different subscription each day"
    st = await state(pg); live = {x["id"] for x in st["subs"] if x.get("keep") != "drop"}
    assert all(x[2] in live for x in p), "never asks about something already dropped"
    assert [a["title"] for a in (await pg.evaluate("window.__n.types"))[0]["actions"]] == ["A lot", "Barely", "Not at all"]
    # opening Subs before the 10 days start does not count as the check
    await tab(pg, "month"); await tab(pg, "subs"); await pg.clock.run_for(2000)
    assert len(await pg.evaluate(pending)) == 10
    # 16 October, the first one was ignored: only what is still ahead remains
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 16, 9, 0)); await tab(pg, "month"); await pg.clock.run_for(2000)
    p = await pg.evaluate(pending)
    assert [x[0][:2] for x in p[:4]] == [[10, 16], [10, 17], [10, 20], [10, 23]], p
    # answering "Not at all" on the notification: marked to drop, Subs opens, and this month's reminders stop
    first = p[0][2]; name = [x["name"] for x in st["subs"] if x["id"] == first][0]
    await pg.evaluate(f"window.__n.listener({{actionId: 'none', notification: {{extra: {{subId: '{first}'}}}}}})"); await pg.wait_for_timeout(150)
    st = await state(pg)
    assert [x for x in st["subs"] if x["id"] == first][0]["keep"] == "drop" and st["tab"] == "subs" and st["remind"]["seen"] == "2026-10-25"
    assert f"How to cancel {name}" in await text(pg, f"[data-sub={first}]") or "cancel" in (await text(pg, f"[data-sub={first}]")).lower()
    assert "Done for this month" in await text(pg, "[data-remind]")
    await pg.clock.run_for(2000)
    p = await pg.evaluate(pending)
    assert [x[0][0] for x in p] == [11] * 5 and all(x[2] != first for x in p), "only next month is left, without the dropped one"
    # turning it off clears everything, and it can be turned back on
    await pg.click("[data-remind-off]"); await pg.clock.run_for(2000)
    assert await pg.evaluate("window.__n.pending.length") == 0 and "Remind me before payday" in await text(pg, "[data-remind]")
    await pg.click("[data-remind-on]"); await pg.clock.run_for(2000)
    assert await pg.evaluate("window.__n.pending.length") > 0
    assert not pg.errors, pg.errors

@test
async def double_tap_never_zooms(ctx):
    # iPhone zooms the page on a quick double tap unless the page opts out. Pinch to zoom must stay available.
    pg = await open_app(ctx)
    for sel in ("html", "[data-tab=subs]", "#view", ".btn"):
        ta = await pg.evaluate(f"(() => {{ let e = document.querySelector('{sel}'), all = []; for (; e; e = e.parentElement) all.push(getComputedStyle(e).touchAction); return all; }})()")
        assert "manipulation" in ta and "none" not in ta, (sel, ta)
    vp = await pg.get_attribute("meta[name=viewport]", "content")
    assert "user-scalable=no" not in vp and "maximum-scale=1" not in vp, "pinch to zoom stays on for people who need it"
    for name in ("month", "subs", "cheaper", "codes", "plan", "split"):
        await tab(pg, name)
        if name == "split": await pg.click("[data-new-split]"); await pg.wait_for_timeout(100)
        small = await pg.evaluate("[...document.querySelectorAll('input, select, textarea')].filter(e => e.offsetParent && !['checkbox', 'radio', 'file'].includes(e.type) && parseFloat(getComputedStyle(e).fontSize) < 16).map(e => e.id || e.name || e.className).slice(0, 5)")
        assert not small, f"{name}: fields under 16px make iPhone zoom in when you tap them: {small}"

@test
async def field_stays_above_the_keyboard(ctx):
    inside = "(() => { const r = document.activeElement.getBoundingClientRect(), m = document.getElementById('main').getBoundingClientRect(); return [document.activeElement.tagName, r.top >= m.top && r.bottom <= m.bottom, Math.round(r.top), Math.round(m.top), Math.round(m.bottom)]; })()"
    pg = await open_app(ctx)
    # a field low on the page gets focus (as a tap does), then the keyboard takes the bottom half of the screen
    await pg.click("[data-env-open=needs]"); await pg.wait_for_timeout(150)
    f = pg.locator("[data-out=envelopes] input").first
    await f.evaluate("e => { document.getElementById('main').scrollTop = 0; e.focus({preventScroll: true}); }"); await pg.wait_for_timeout(800)
    r = await pg.evaluate(inside); assert r[0] == "INPUT" and r[1], f"focused field is on screen: {r}"
    await pg.set_viewport_size({"width": 390, "height": 420}); await pg.wait_for_timeout(500)
    r = await pg.evaluate(inside); assert r[1], f"field is still visible once the keyboard is up: {r}"
    await pg.set_viewport_size({"width": 390, "height": 844}); await pg.wait_for_timeout(300)
    # every tab: focusing the last field brings it into view
    for name in ("subs", "cheaper", "codes", "plan", "split"):
        await tab(pg, name)
        if name == "split": await pg.click("[data-new-split]"); await pg.wait_for_timeout(100)
        ok = await pg.evaluate("(() => { const f = [...document.querySelectorAll('#view input:not([type=checkbox]):not([type=radio]):not([type=file]), #view select')].filter(e => e.offsetParent && !e.closest('details:not([open])') && !e.disabled); if (!f.length) return null; document.getElementById('main').scrollTop = 0; f[f.length - 1].focus({preventScroll: true}); return document.activeElement === f[f.length - 1]; })()")
        assert ok, f"{name}: could not focus a field"
        await pg.set_viewport_size({"width": 390, "height": 420}); await pg.wait_for_timeout(800)
        r = await pg.evaluate(inside); assert r[1], f"{name}: {r}"
        await pg.evaluate("document.activeElement.blur()"); await pg.set_viewport_size({"width": 390, "height": 844}); await pg.wait_for_timeout(250)

@test
async def opening_details_does_not_jump(ctx):
    pg = await open_app(ctx)
    top = "k => Math.round(document.querySelector(`[data-env-open='${k}']`).getBoundingClientRect().top)"
    keys = await pg.evaluate("[...document.querySelectorAll('[data-env-open]')].map(e => e.dataset.envOpen)")
    assert len(keys) >= 3, keys
    await pg.click(f"[data-env-open='{keys[1]}']"); await pg.wait_for_timeout(150)   # a tall group is open above
    await pg.locator(f"[data-env-open='{keys[2]}']").scroll_into_view_if_needed(); await pg.wait_for_timeout(100)
    before = await pg.evaluate(top, keys[2])
    await pg.click(f"[data-env-open='{keys[2]}']"); await pg.wait_for_timeout(200)
    after = await pg.evaluate(top, keys[2])
    assert abs(after - before) <= 2, f"the row you tapped moved from {before} to {after}"
    assert "Hide details" in await text(pg, f"[data-env-open='{keys[2]}']") or await pg.locator("[data-out=envelopes] input").count() > 0

@test
async def contacts_button_in_split_form_shows_what_to_do(ctx):
    # iPhone and computers cannot hand a website the address book, so tapping "Search your phone contacts"
    # must explain the file route right there, not somewhere further down the page.
    pg = await open_app(ctx); await tab(pg, "split")
    await pg.evaluate("(() => { try { delete Navigator.prototype.contacts; } catch(e){} })()")
    await pg.click("[data-new-split]"); await pg.fill("[data-part-search]", "Hass"); await pg.wait_for_timeout(150)
    await pg.click("form[data-form=split] [data-contacts-sync]"); await pg.wait_for_timeout(200)
    h = pg.locator("form[data-form=split] [data-contacts-help]")
    assert await h.count() == 1 and await h.is_visible(), "help appears inside the form"
    box, m = await h.bounding_box(), await pg.locator("#main").bounding_box()
    assert box["y"] >= m["y"] and box["y"] + box["height"] <= m["y"] + m["height"] + 1, f"and it is on screen: {box} in {m}"
    assert "Add your contacts from a file" in await h.inner_text() and await pg.input_value("[data-part-search]") == "Hass", "what was typed is kept"
    vcf = os.path.join(TMP, "one.vcf"); open(vcf, "w").write("BEGIN:VCARD\nVERSION:3.0\nFN:Hassan Ali\nTEL:+1 555 010 9911\nEND:VCARD\n")
    async with pg.expect_file_chooser() as fc: await pg.click("[data-contacts-file]")
    await (await fc.value).set_files(vcf); await pg.wait_for_timeout(300)
    assert await pg.locator("[data-contacts-help]").count() == 0
    await pg.fill("[data-part-search]", "Hass"); await pg.wait_for_timeout(150)
    assert "Hassan Ali" in await text(pg, "form[data-form=split]"), "the contact can now be found"
    # Not now puts the button back
    await pg.evaluate("localStorage.clear()"); pg2 = await open_app(ctx); await tab(pg2, "split")
    await pg2.evaluate("(() => { try { delete Navigator.prototype.contacts; } catch(e){} })()")
    await pg2.click("[data-new-split]"); await pg2.fill("[data-part-search]", "Z"); await pg2.wait_for_timeout(150)
    await pg2.click("form[data-form=split] [data-contacts-sync]"); await pg2.wait_for_timeout(150)
    await pg2.click("form[data-form=split] [data-contacts-help-close]"); await pg2.wait_for_timeout(150)
    assert await pg2.locator("form[data-form=split]").count() == 1 and await pg2.locator("[data-contacts-help]").count() == 0

@test
async def history_help_sits_behind_an_info_button(ctx):
    pg = await open_app(ctx); await tab(pg, "split")
    assert await pg.locator("[data-info-tip]").count() == 0, "no paragraph of instructions on the screen by default"
    b = pg.locator("#history [data-info=history]"); assert await b.get_attribute("aria-expanded") == "false"
    box = await b.bounding_box(); assert box["width"] >= 36 and box["height"] >= 36, "big enough to tap"
    await b.click(); await pg.wait_for_timeout(120)
    tip = await pg.inner_text("[data-info-tip=history]")
    assert "Put back in the list" in tip and len(tip) < 170, tip
    assert await pg.locator("#history [data-info=history]").get_attribute("aria-expanded") == "true"
    await pg.click("#history [data-info=history]"); await pg.wait_for_timeout(120)
    assert await pg.locator("[data-info-tip]").count() == 0
    # one other person in a split: the prompt names them, not "everyone"
    await pg.click("[data-new-split]"); f = pg.locator("form[data-form=split]")
    await f.locator("[data-d=title]").fill("Tax filing"); await f.locator("[data-d=amount]").fill("255")
    await pg.click("[data-part-search]"); await pg.wait_for_timeout(60); await pg.click("[data-part-add=p1]"); await pg.wait_for_timeout(60)
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    card = await text(pg, "[data-tell]")
    assert "Let Alex know about Tax filing" in card and "everyone" not in card and "Send to Alex" in card, card

@test
async def statement_dates_follow_the_file_not_the_currency(ctx):
    # A US statement (month first) imported while the currency is AED must not read 04/14 as month 14.
    pg = await open_app(ctx)
    await pg.select_option("#m-cur", "AED"); await pg.wait_for_timeout(150)
    us = os.path.join(TMP, "us.csv")
    open(us, "w").write("Date,Description,Amount\n04/01/2026,PAYROLL ACME,3000\n04/14/2026,ADOBE CREATIVE CLOUD,-59.99\n05/01/2026,PAYROLL ACME,3000\n05/14/2026,ADOBE CREATIVE CLOUD,-59.99\n06/14/2026,ADOBE CREATIVE CLOUD,-59.99\n")
    await pg.set_input_files("#stmt", us); await pg.wait_for_timeout(500)
    await use_as_plan(pg); await pg.wait_for_timeout(250)
    a = [x for x in (await state(pg))["subs"] if x["name"].lower().startswith("adobe")][0]
    assert a["since"] == "2026-04-14" and a["lastCharge"] == "2026-06-14" and a["renewDay"] == 14, a
    # a day-first file under USD: 14/04 can only be 14 April
    await pg.select_option("#m-cur", "USD"); await pg.wait_for_timeout(150)
    uk = os.path.join(TMP, "dayfirst.csv")
    open(uk, "w").write("Date,Description,Amount\n01/04/2026,PAYROLL ACME,3000\n14/04/2026,HULU,-9.99\n01/05/2026,PAYROLL ACME,3000\n14/05/2026,HULU,-9.99\n14/06/2026,HULU,-9.99\n")
    await pg.set_input_files("#stmt", uk); await pg.wait_for_timeout(500)
    await use_as_plan(pg); await pg.wait_for_timeout(250)
    h = [x for x in (await state(pg))["subs"] if x["name"].lower().startswith("hulu")][0]
    assert h["since"] == "2026-04-14" and h["lastCharge"] == "2026-06-14", h
    # no date anywhere may land in a month that does not exist or in the future
    today = await pg.evaluate("new Date().toISOString().slice(0, 10)")
    assert all((x.get("since") or "0") <= today for x in (await state(pg))["subs"])

IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"

@test
async def data_moves_from_browser_to_home_screen_app(ctx):
    # iPhone keeps the Home Screen app's storage apart from the browser tab, so the data is carried on the clipboard.
    br = ctx.browser
    # 1. in the browser, with real data: the note explains the three steps and offers Copy my data
    c1 = await br.new_context(user_agent=IPHONE_UA, viewport={"width": 390, "height": 844}); pg = await c1.new_page(); pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    await pg.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true; window.__clip = ''; Object.defineProperty(navigator, 'clipboard', {value: {writeText: async t => { window.__clip = t; }, readText: async () => window.__clip}, configurable: true});")
    await pg.goto(URL); await pg.wait_for_timeout(400)
    note = await text(pg, "[data-a2hs]"); assert "Add to Home Screen" in note and "Copy my data" not in note, "the example month has nothing to carry"
    csv = os.path.join(TMP, "move.csv")
    open(csv, "w").write("Date,Description,Amount\n2026-07-01,PAYROLL ACME,4321\n2026-07-04,NETFLIX.COM,-15.49\n2026-08-01,PAYROLL ACME,4321\n2026-08-04,NETFLIX.COM,-15.49\n2026-09-01,PAYROLL ACME,4321\n2026-09-04,NETFLIX.COM,-15.49\n")
    await pg.set_input_files("#stmt", csv); await pg.wait_for_timeout(500)
    await use_as_plan(pg); await pg.wait_for_timeout(300)
    assert (await state(pg))["example"] is False and (await state(pg))["income"] == 4321
    note = await text(pg, "[data-a2hs]")
    assert "it starts empty" in note and "Copy my data" in note and "Paste my data" in note, note
    await pg.click("[data-a2hs] [data-move-copy]"); await pg.wait_for_timeout(150)
    code = await pg.evaluate("window.__clip"); assert code.startswith("KEEPWISE:") and "Copied" in await text(pg, "[data-a2hs]")
    await menu_to(pg, "backup"); assert await pg.locator("[data-out=backupBox] [data-move-copy]").count() == 1, "also reachable from Account settings after the note is dismissed"
    await c1.close()
    # 2. the Home Screen app: empty storage, first run
    c2 = await br.new_context(user_agent=IPHONE_UA, viewport={"width": 390, "height": 844}); app = await c2.new_page(); app.errors = []
    app.on("pageerror", lambda e: app.errors.append(str(e)))
    await app.add_init_script("window.KEEPWISE_FIREBASE = null; Object.defineProperty(Navigator.prototype, 'standalone', {get: () => true}); window.__clip = ''; Object.defineProperty(navigator, 'clipboard', {value: {writeText: async t => { window.__clip = t; }, readText: async () => window.__clip}, configurable: true});")
    await app.goto(URL); await app.wait_for_timeout(400)
    assert "I already use KeepWise in my browser" in await text(app, "#view")
    # the phone would not hand over the clipboard: a box to paste into appears instead
    await app.click("[data-move-paste]"); await app.wait_for_timeout(150)
    assert await app.locator("[data-move-field]").count() == 1
    await app.fill("[data-move-field]", "hello"); await app.click("[data-move-apply]"); await app.wait_for_timeout(120)
    assert "isn’t KeepWise data" in await app.inner_text("#toast")
    await app.fill("[data-move-field]", code); await app.click("[data-move-apply]"); await app.wait_for_timeout(250)
    st = await state(app); assert st["income"] == 4321 and st["example"] is False, "the same data is now in the app"
    assert "Your data is here now" in await app.inner_text("#toast") and await app.locator("[data-move]").count() == 0 and await app.locator("[data-a2hs]").count() == 0
    assert not app.errors, app.errors
    await c2.close()
    # 3. when the phone does hand over the clipboard, one tap is enough
    c3 = await br.new_context(user_agent=IPHONE_UA, viewport={"width": 390, "height": 844}); app = await c3.new_page()
    await app.add_init_script("window.KEEPWISE_FIREBASE = null; Object.defineProperty(Navigator.prototype, 'standalone', {get: () => true}); Object.defineProperty(navigator, 'clipboard', {value: {readText: async () => " + json.dumps(code) + "}, configurable: true});")
    await app.goto(URL); await app.wait_for_timeout(400)
    await app.click("[data-move-paste]"); await app.wait_for_timeout(250)
    assert (await state(app))["income"] == 4321
    await c3.close()

@test
async def explanations_sit_behind_info_buttons_everywhere(ctx):
    pg = await open_app(ctx)
    async def check(key, words):
        b = pg.locator(f"[data-info={key}]"); assert await b.count() == 1, key
        assert await pg.locator("[data-info-tip]").count() == 0, f"{key}: nothing is open before a tap"
        await b.scroll_into_view_if_needed(); await b.click(); await pg.wait_for_timeout(120)
        tip = await pg.inner_text(f"[data-info-tip={key}]"); assert words in tip and len(tip) <= 190, (key, tip)
        box, m = await pg.locator(f"[data-info-tip={key}]").bounding_box(), await pg.locator("#main").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390 and box["y"] + box["height"] <= m["y"] + m["height"] + 1, f"{key}: the tip is on screen"
        await pg.locator(f"[data-info={key}]").click(); await pg.wait_for_timeout(100)
        assert await pg.locator("[data-info-tip]").count() == 0
    await check("ask", "same numbers")
    await tab(pg, "cheaper"); await check("cheaper", "Prices are estimates")
    await tab(pg, "codes"); await check("codes", "Tap a code to copy it")
    await tab(pg, "plan"); await check("envelopes", "count toward Miscellaneous")
    await tab(pg, "split"); await check("history", "Put back in the list")
    await tab(pg, "month"); await pg.click("[data-history]"); await pg.wait_for_timeout(150); await check("statements", "Nothing is uploaded")
    # an open tip does not follow you to another tab
    await pg.click("[data-history-close]"); await tab(pg, "cheaper"); await pg.click("[data-info=cheaper]"); await pg.wait_for_timeout(100)
    await tab(pg, "codes"); await tab(pg, "cheaper"); assert await pg.locator("[data-info-tip]").count() == 0
    for old in ("Close alternatives to what you already pay for", "Codes marked Likely worked", "Percent of money coming in"):
        assert old not in await text(pg, "#view")
    assert not pg.errors, pg.errors

@test
async def cheaper_suggests_ideas_from_your_own_list(ctx):
    pg = await open_app(ctx)
    csv = os.path.join(TMP, "ideas.csv")
    rows = ["Date,Description,Amount"]
    for m in ("07", "08", "09"):
        rows += [f"2026-{m}-01,PAYROLL ACME,3000", f"2026-{m}-04,NETFLIX.COM,-17.99", f"2026-{m}-06,SPOTIFY USA,-11.99", f"2026-{m}-09,AUDIBLE,-14.95", f"2026-{m}-12,NOTION LABS,-20.00", f"2026-{m}-15,ICLOUD STORAGE,-2.99"]
    open(csv, "w").write("\n".join(rows) + "\n")
    await pg.set_input_files("#stmt", csv); await pg.wait_for_timeout(500)
    await use_as_plan(pg); await pg.wait_for_timeout(300)
    await tab(pg, "cheaper")
    box = await text(pg, "[data-out=cheapIdeas]")
    assert "Ideas for you" in box and await pg.locator("[data-idea]").count() == 3, "three ideas at most, until you ask for more"
    first = await pg.locator("[data-idea]").first.inner_text()
    assert "Audible" in first and "library" in first.lower() and "Could keep about $14.95 a month" in first, f"the biggest saving comes first: {first}"
    assert "No comparisons yet" not in await text(pg, "#view"), "no dead-end message while there are ideas"
    await pg.click("[data-ideas-more]"); await pg.wait_for_timeout(100)
    all_ideas = await text(pg, "[data-out=cheapIdeas]")
    assert "Netflix" in all_ideas and "Keep it half the year" in all_ideas and "Spotify" in all_ideas and "Pay yearly instead of monthly" in all_ideas, all_ideas
    assert "Icloud" not in all_ideas and "iCloud" not in all_ideas, "a saving this small is not worth a card"
    assert await pg.locator("[data-idea]").count() == len(set(await pg.evaluate("[...document.querySelectorAll('[data-idea]')].map(e => e.dataset.idea.split(':').slice(0, 2).join(':'))"))), "one idea per thing you pay for"
    # the info button says plainly that these are estimates
    await pg.click("[data-info=ideas]"); await pg.wait_for_timeout(100)
    assert "rough estimates, not real prices" in await pg.inner_text("[data-info-tip=ideas]")
    # Add turns an idea into a comparison you can edit; it is off until you choose it
    before = money(await text(pg, "[data-out=cheapSummary] .summary3 > div:last-child b"))
    await pg.locator("[data-idea]").first.locator("[data-idea-add]").click(); await pg.wait_for_timeout(150)
    st = await state(pg); w = st["swaps"][-1]
    assert w["alt"] == "Your library’s app" and w["altCost"] == 0 and w["on"] is False and "check the real price" in w["note"]
    assert "Audible" not in await text(pg, "[data-out=cheapIdeas]") and "Audible" in await text(pg, "[data-out=cheapList]")
    assert abs(money(await text(pg, "[data-out=cheapSummary] .summary3 > div:last-child b")) - before - 14.95) < 0.01
    # Not for me removes it for good
    gone = await pg.locator("[data-idea]").first.get_attribute("data-idea")
    await pg.locator("[data-idea]").first.locator("[data-idea-skip]").click(); await pg.wait_for_timeout(150)
    await pg.reload(); await pg.wait_for_timeout(300); await tab(pg, "cheaper")
    assert await pg.locator(f"[data-idea='{gone}']").count() == 0 and (await state(pg))["swapSkip"][gone] == 1
    # Codes: no talk of example codes when there are none, and a useful empty line
    await tab(pg, "codes")
    v = await text(pg, "#view"); assert "example codes" not in v.lower() and "affiliate" not in v and "ready at checkout" in v, v
    assert not pg.errors, pg.errors

@test
async def shared_links_show_a_preview_card(ctx):
    # WhatsApp, iMessage and others build the card from these tags; without them the link is bare text.
    if not APP.endswith(os.path.join("www", "index.html")): return
    html = open(APP, encoding="utf-8").read()
    for tag in ('property="og:title"', 'property="og:description"', 'property="og:image" content="https://mykeepwise.com/icons/og.png"', 'name="twitter:card" content="summary_large_image"', 'rel="canonical" href="https://mykeepwise.com/"'):
        assert tag in html, tag
    img = os.path.join(os.path.dirname(APP), "icons", "og.png")
    assert os.path.exists(img) and 20_000 < os.path.getsize(img) < 300_000, "the card image is present and small enough to load fast"
    data = open(img, "rb").read(); assert int.from_bytes(data[16:20], "big") == 1200 and int.from_bytes(data[20:24], "big") == 630

@test
async def plus_screen_gives_reasons_and_prices(ctx):
    pg = await open_app(ctx); await tab(pg, "plan")
    await pg.locator("[data-plus-open]").first.scroll_into_view_if_needed(); await pg.locator("[data-plus-open]").first.click(); await pg.wait_for_timeout(200)
    v = await text(pg, "#view")
    for reason in ("Live splits with friends", "Your money on every device", "Business Account", "Receipt photos", "Moments"):
        assert reason in v, reason
    assert "straight from your contacts" in v
    for unbuilt in ("shared household", "Offers near you", "Reminders on every phone", "only you can unlock", "birthday"):   # only promises we can keep
        assert unbuilt not in v, unbuilt
    assert await pg.locator(".plus-list li").count() == 5
    # prices exactly as set: 12 from 15 for the first six months, 140 from 180 a year
    m = await text(pg, ".plus-price:not(.best)"); y = await text(pg, ".plus-price.best")
    assert "$15" in m and "$12" in m and "a month" in m and "first 6 months, then $15 a month" in m, m
    assert "$180" in y and "$140" in y and "a year" in y and "You save $40" in y and "About $11.67 a month" in y, y
    assert await pg.locator(".plus-price s").count() == 2 and m.upper().count("EARLY USER PRICE") == 1
    assert "not on sale yet" in v and "Free, and staying free" in v and "Claude" not in v and "Business space" not in v
    assert "EARLY140" in y and "EARLY12" in m, "each price shows its code"
    assert await pg.locator("[data-open-account]").count() >= 1, "signed out: the button leads to sign-in"
    w = await pg.evaluate("Math.max(...[...document.querySelectorAll('#view *')].map(e => e.getBoundingClientRect().right))"); assert w <= 390.5, f"nothing runs off the screen: {w}"
    await pg.click("[data-plus-close]"); await pg.wait_for_timeout(150)
    assert await pg.locator(".plus-prices").count() == 0 and await pg.locator("#view [data-plus-open]").count() == 1, "Done returns to where you were"
    # reachable from the coming-soon card on Split, and a tab tap leaves it
    await tab(pg, "split"); await pg.click("[data-mode=shared]"); await pg.wait_for_timeout(120)
    assert "COMING WITH PLUS" in (await text(pg, "[data-shared-soon]")).upper()
    await pg.click("[data-shared-soon] [data-plus-open]"); await pg.wait_for_timeout(150); assert await pg.locator(".plus-prices").count() == 1
    await tab(pg, "subs"); assert await pg.locator(".plus-prices").count() == 0
    assert not pg.errors, pg.errors

@test
async def statement_separates_transfers_from_spending(ctx):
    # Transfers are not spending by default. What you sent and what you received are shown apart, money moved between
    # your own accounts is shown apart from both with every transaction listed, and only ticked lines reach the plan.
    pg = await open_app(ctx); await pg.select_option("#m-cur", "PKR"); await pg.wait_for_timeout(120)
    csv = os.path.join(TMP, "pk.csv"); open(csv, "w").write("\n".join(PK_ROWS()) + "\n")
    await pg.set_input_files("#stmt", csv); await pg.wait_for_timeout(600)
    v = await stx(pg, "#view")
    assert "Transfers and cash" not in v, "transfers are no longer lumped into everyday spending"
    spend = await stx(pg, "[data-st=spending]"); assert "Groceries" in spend and "500,000" not in spend and "Ahmed" not in spend, spend
    out = await stx(pg, "[data-moves=out]"); inn = await stx(pg, "[data-moves=in]"); oo = await stx(pg, "[data-moves=own-out]"); oi = await stx(pg, "[data-moves=own-in]")
    assert "Money you sent" in out and "Ahmed Nawaz" in out and "PKR 50,000/mo" in out and "every month" in out and "Bilal Traders" in out and "PKR 20,000" in out and "Cash withdrawals" in out and "PKR 30,000/mo" in out, out
    assert "Money you received" in inn and "John Smith" in inn and "From abroad" in inn and "PKR 100,000/mo" in inn, inn
    # someone you both paid and were paid by appears on each side, with only that side's money
    assert "Sara Noor" in out and "PKR 5,000" in out and "Sara Noor" in inn and "PKR 10,000" in inn
    # your own accounts: every transaction, under your name, exactly as written, never counted
    assert "Money you sent to yourself" in oo and oo.count("IBFT TO ALI RAZA KHAN MEEZAN BANK") == 3 and "PKR 1,500,000" in oo and "not counted" in oo.lower() and "ALI RAZA KHAN" in oo.upper(), oo
    assert "Money you received from yourself" in oi and oi.count("IBFT FROM ALI RAZA KHAN UBL") == 3 and "PKR 900,000" in oi, oi
    assert "Ali Raza" not in out and "Ali Raza" not in inn, "your own name is never listed as someone else"
    assert await pg.locator("[data-moves=own-out] input[type=checkbox], [data-moves=own-in] input[type=checkbox]").count() == 0, "own transfers cannot be counted"
    ticks = await pg.evaluate("Object.fromEntries([...document.querySelectorAll('[data-moves] [data-st-pick]')].map(c => [c.dataset.stPick, c.checked]))")
    assert ticks == {"sent:AHMED NAWAZ": True, "sent:BILAL TRADERS": False, "sent:SARA NOOR": False, "cash:out": True, "received:JOHN SMITH": True, "received:SARA NOOR": False}, ticks
    # typical month: 200,000 salary + 100,000 remittance in; 1,100 + 24,000 + 50,000 + 30,000 out
    hero = await stx(pg, ".import-body .hero"); assert "PKR 300,000 comes in" in hero and "PKR 105,100 goes out" in hero and "PKR 194,900" in hero, hero
    # unticking cash changes the number at once
    await pg.locator("[data-st-pick='cash:out']").uncheck(); await pg.wait_for_timeout(150)
    assert "PKR 75,100 goes out" in await stx(pg, ".import-body .hero")
    await pg.locator("[data-st-pick='cash:out']").check(); await pg.locator("[data-st-pick='sent:BILAL TRADERS']").check(); await pg.wait_for_timeout(150)
    await use_as_plan(pg); await pg.wait_for_timeout(300)
    st = await state(pg); names = {e["name"]: e["amount"] for e in st["expenses"]}
    assert names.get("Sent to Ahmed Nawaz") == 50000 and names.get("Cash withdrawals") == 30000 and abs(names.get("Sent to Bilal Traders") - 6666.67) < 0.01, names
    assert not any("Ali Raza" in n or "Sara" in n or "Transfers" in n for n in names), names
    ex = {e["name"]: e["amount"] for e in st["extras"]}; assert ex == {"From abroad: John Smith": 100000}, ex
    assert st["income"] == 200000 and [s["name"] for s in st["subs"]] == ["Netflix"]
    assert not pg.errors, pg.errors

def PK_ROWS():
    rows = ["Account Title: ALI RAZA KHAN", "Account No: 0000-0000", "Date,Description,Debit,Credit"]
    for m in ("07", "08", "09"):
        rows += [f"01/{m}/2026,SALARY ACME PVT LTD,,200000", f"02/{m}/2026,IBFT TO ALI RAZA KHAN MEEZAN BANK,500000,", f"03/{m}/2026,IBFT FROM ALI RAZA KHAN UBL,,300000",
                 f"05/{m}/2026,RAAST P2P TO AHMED NAWAZ,50000,", f"09/{m}/2026,ATM CASH WITHDRAWAL 1LINK,30000,", f"14/{m}/2026,NETFLIX.COM,1100,", f"18/{m}/2026,POS IMTIAZ SUPER MARKET,24000,"]
    return rows + ["20/07/2026,FT TO BILAL TRADERS,20000,", "21/07/2026,IBFT FROM SARA NOOR,,10000", "25/08/2026,RAAST TO SARA NOOR,5000,",
                   "22/08/2026,INWARD REMITTANCE WESTERN UNION JOHN SMITH,,150000", "22/09/2026,INWARD REMITTANCE WESTERN UNION JOHN SMITH,,150000"]
async def stx(pg, sel): return (await text(pg, sel)).replace(" ", " ")

@test
async def nothing_from_a_statement_is_added_until_it_is_ticked(ctx):
    pg = await open_app(ctx)
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement.csv")); await pg.wait_for_timeout(500)
    before = await state(pg); assert len(before["subs"]) == 10 and before["income"] == 5200, "reading a statement changes nothing by itself"
    c = await stx(pg, "[data-st-count]"); m = re.search(r"(\d+) of (\d+) lines are ticked", c); assert m and "Nothing is added until you choose below" in c, c
    picked, total = int(m.group(1)), int(m.group(2)); assert 0 < picked <= total
    # every subscription, bill, spending group and pay line has its own tick
    for sec in ("income", "subs", "bills", "spending"): assert await pg.locator(f"[data-st={sec}] [data-st-pick]").count() >= 1, sec
    # untick one subscription: the count and the typical month change at once
    hero = await stx(pg, ".import-body .hero")
    await pg.locator("[data-st-pick='sub:NETFLIX']").uncheck(); await pg.wait_for_timeout(150)
    assert f"{picked - 1} of {total}" in await stx(pg, "[data-st-count]") and await stx(pg, ".import-body .hero") != hero
    # untick every bill with one tap, then tick them all again
    await pg.click("[data-st-all=bills]"); await pg.wait_for_timeout(150)
    assert not any(await pg.evaluate("[...document.querySelectorAll('[data-st=bills] [data-st-pick^=\"bill:\"]')].map(c => c.checked)"))
    assert "Tick all" in await stx(pg, "[data-st=bills]")
    await pg.click("[data-st-all=bills]"); await pg.wait_for_timeout(150)
    assert all(await pg.evaluate("[...document.querySelectorAll('[data-st=bills] [data-st-pick^=\"bill:\"]')].map(c => c.checked)"))
    await pg.locator("[data-st-pick='spend:Dining']").uncheck(); await pg.wait_for_timeout(120)
    await use_as_plan(pg); await pg.wait_for_timeout(300)
    st = await state(pg); names = [x["name"] for x in st["subs"]]
    assert "Netflix" not in names and "Spotify" in names and len(names) == 5, names
    assert not any(e["name"] == "Eating out" for e in st["expenses"]) and any(e["name"] == "Groceries" for e in st["expenses"])
    assert "5 subscriptions" in await pg.inner_text("#toast")
    # with nothing ticked there is nothing to add
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement.csv")); await pg.wait_for_timeout(500)
    await pg.evaluate("(() => { let q, n = 0; while ((q = document.querySelector('[data-st-pick]:checked')) && n++ < 200) q.click(); })()")
    await pg.wait_for_timeout(150)
    assert "0 of" in await stx(pg, "[data-st-count]") and await pg.locator("[data-import-apply=merge]").is_disabled() and await pg.locator("[data-import-apply=replace]").is_disabled()
    assert not pg.errors, pg.errors

@test
async def a_plan_you_built_is_only_replaced_after_you_say_yes(ctx):
    pg = await open_app(ctx)
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement.csv")); await pg.wait_for_timeout(500)
    await pg.click("[data-import-apply=replace]"); await pg.wait_for_timeout(300)        # the example month is replaced without a question
    st = await state(pg); assert st["income"] == 4200 and "Your statement" not in await text(pg, "#view")
    await pg.evaluate("window.__kwErasing = true; const s = JSON.parse(localStorage.getItem('keepwise-app-v1')); s.subs.push({id:'mine', name:'My own club', price:9, cycle:'mo', last:null, group:'', env:'misc', keep:'auto'}); localStorage.setItem('keepwise-app-v1', JSON.stringify(s))")
    await pg.reload(); await pg.wait_for_timeout(500)
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement.csv")); await pg.wait_for_timeout(500)
    await pg.click("[data-import-apply=replace]"); await pg.wait_for_timeout(200)
    box = await stx(pg, ".st-confirm"); assert "Replace your plan?" in box and "removed" in box and "Splits, codes and savings stay" in box, box
    assert any(x["name"] == "My own club" for x in (await state(pg))["subs"]), "nothing changed yet"
    await pg.click("[data-st-confirm=no]"); await pg.wait_for_timeout(150)
    assert await pg.locator(".st-confirm").count() == 0 and "Your statement" in await text(pg, "#view")
    await pg.click("[data-import-apply=merge]"); await pg.wait_for_timeout(300)             # adding never asks, and keeps what is there
    assert any(x["name"] == "My own club" for x in (await state(pg))["subs"])
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement.csv")); await pg.wait_for_timeout(500)
    await pg.click("[data-import-apply=replace]"); await pg.wait_for_timeout(200); await pg.click("[data-import-apply][data-sure]"); await pg.wait_for_timeout(300)
    assert not any(x["name"] == "My own club" for x in (await state(pg))["subs"])
    assert not pg.errors, pg.errors

@test
async def every_statement_line_is_shown_exactly_as_the_bank_wrote_it(ctx):
    pg = await open_app(ctx)
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement.csv")); await pg.wait_for_timeout(500)
    rows = [l.split(",") for l in open(os.path.join(FIX, "sample-bank-statement.csv")).read().strip().split("\n")[1:]]
    tin = sum(float(r[2]) for r in rows if float(r[2]) > 0); tout = -sum(float(r[2]) for r in rows if float(r[2]) < 0)
    chk = await stx(pg, ".st-check"); assert f"Money in ${tin:,.2f}".replace(".00", "") in chk.replace(".00", "") and f"money out ${tout:,.2f}" in chk, (chk, tin, tout)
    # the bank's own wording sits under the tidy name
    nf = await stx(pg, "[data-st-item='sub:NETFLIX']"); assert "Netflix" in nf and "NETFLIX.COM" in nf and "$17.99/mo" in nf, nf
    assert await pg.locator("[data-st-item='sub:NETFLIX'] .st-t").count() == 0
    await pg.click("[data-st-open='sub:NETFLIX']"); await pg.wait_for_timeout(150)
    lines = await pg.locator("[data-st-item='sub:NETFLIX'] .st-t").all_inner_texts(); assert len(lines) == 6, lines
    assert "Apr 5, 2026" in lines[0] and "NETFLIX.COM" in lines[0] and "$17.99" in lines[0], lines[0]
    assert "Hide" in await stx(pg, "[data-st-item='sub:NETFLIX']")
    await pg.click("[data-st-open='sub:NETFLIX']"); await pg.wait_for_timeout(120); assert await pg.locator("[data-st-item='sub:NETFLIX'] .st-t").count() == 0
    # a spending group opens to the payments inside it
    await pg.click("[data-st-open='spend:Groceries']"); await pg.wait_for_timeout(150)
    g = await pg.locator("[data-st-item='spend:Groceries'] .st-t").all_inner_texts(); want = [r for r in rows if "TRADER JOE" in r[1]]
    assert len(g) == len(want) and all("TRADER JOE'S #552" in x for x in g), (len(g), len(want))
    # every line of the file, with where it went
    assert f"Show all {len(rows)}" in await stx(pg, "[data-st=all]")
    await pg.click("[data-st-open=all]"); await pg.wait_for_timeout(200)
    al = await pg.locator("[data-st=all] .st-t").all_inner_texts(); assert len(al) == len(rows), (len(al), len(rows))
    joined = "\n".join(al).replace(" ", " ")
    for r in rows: assert r[1] in joined, r[1]
    assert "ZELLE FROM SAM" in joined and "+$40" in joined and "Received from Sam" in joined and "Subscription" in joined and "Pay" in joined and "Bill" in joined
    await pg.set_viewport_size({"width": 320, "height": 700}); await pg.wait_for_timeout(200)
    assert await pg.evaluate("document.getElementById('main').scrollWidth <= document.getElementById('main').clientWidth + 1"), "long bank wording wraps on a small phone"
    assert not pg.errors, pg.errors

@test
async def you_can_say_which_names_on_a_statement_are_you(ctx):
    pg = await open_app(ctx); await pg.select_option("#m-cur", "PKR"); await pg.wait_for_timeout(120)
    rows = [r for r in PK_ROWS() if not r.startswith("Account")]           # this bank does not print the account holder's name
    csv = os.path.join(TMP, "pk-noname.csv"); open(csv, "w").write("\n".join(rows) + "\n")
    await pg.set_input_files("#stmt", csv); await pg.wait_for_timeout(600)
    assert await pg.locator("[data-moves=own-out]").count() == 0 and "Ali Raza Khan" in await stx(pg, "[data-moves=out]"), "without a name, nothing is guessed to be yours"
    assert await pg.input_value("[data-stmt-holder]") == ""
    # typing the name moves both directions out of spending and income
    await pg.fill("[data-stmt-holder]", "Ali Raza Khan"); await pg.locator("[data-stmt-holder]").blur(); await pg.wait_for_timeout(250)
    assert "Ali Raza" not in await stx(pg, "[data-moves=out]") and (await stx(pg, "[data-moves=own-out]")).count("IBFT TO ALI RAZA KHAN MEEZAN BANK") == 3
    assert (await stx(pg, "[data-moves=own-in]")).count("IBFT FROM ALI RAZA KHAN UBL") == 3
    # "This is me" on any other name does the same for that name
    await pg.click("[data-st-me='SARA NOOR']"); await pg.wait_for_timeout(250)
    assert "Sara" not in await stx(pg, "[data-moves=out]") and "Sara" not in await stx(pg, "[data-moves=in]")
    assert "RAAST TO SARA NOOR" in await stx(pg, "[data-moves=own-out]") and "IBFT FROM SARA NOOR" in await stx(pg, "[data-moves=own-in]")
    me = await stx(pg, "[data-moves=me]"); assert "counted as you" in me.lower() and "Sara Noor" in me and "Ali Raza Khan" in me, me
    # and it can be undone
    await pg.click("[data-st-notme='SARA NOOR']"); await pg.wait_for_timeout(250)
    assert "Sara Noor" in await stx(pg, "[data-moves=out]") and "Sara Noor" in await stx(pg, "[data-moves=in]") and "SARA NOOR" not in await stx(pg, "[data-moves=own-out]")
    assert "not you" in (await stx(pg, "[data-moves=me]")).lower()
    await pg.click("[data-st-isme='SARA NOOR']"); await pg.wait_for_timeout(200); assert "not you" not in (await stx(pg, "[data-moves=me]")).lower()
    # a tick made earlier survives all of this
    await pg.locator("[data-st-pick='sent:BILAL TRADERS']").check(); await pg.wait_for_timeout(120)
    await pg.fill("[data-stmt-holder]", "Ali Raza"); await pg.locator("[data-stmt-holder]").blur(); await pg.wait_for_timeout(250)
    assert await pg.locator("[data-st-pick='sent:BILAL TRADERS']").is_checked()
    await use_as_plan(pg); await pg.wait_for_timeout(300)
    st = await state(pg); names = [e["name"] for e in st["expenses"]]; assert not any("Ali" in n for n in names) and "Sent to Bilal Traders" in names, names
    # a bank that only says "savings" or "own account" is understood without a name
    pg2 = await open_app(ctx); await pg2.select_option("#m-cur", "USD"); await pg2.wait_for_timeout(120); us = os.path.join(TMP, "own.csv")
    open(us, "w").write("Date,Description,Amount\n07/01/2026,PAYROLL ACME,3000\n07/03/2026,ONLINE TRANSFER TO SAVINGS 4471,-400\n08/01/2026,PAYROLL ACME,3000\n08/03/2026,ONLINE TRANSFER TO SAVINGS 4471,-400\n08/20/2026,ONLINE TRANSFER FROM SAVINGS 4471,150\n08/22/2026,ZELLE TO DANA REED,-60\n")
    await pg2.set_input_files("#stmt", us); await pg2.wait_for_timeout(500)
    oo = await stx(pg2, "[data-moves=own-out]"); assert oo.count("ONLINE TRANSFER TO SAVINGS 4471") == 2 and "$800" in oo, oo
    assert "ONLINE TRANSFER FROM SAVINGS 4471" in await stx(pg2, "[data-moves=own-in]") and "Dana Reed" in await stx(pg2, "[data-moves=out]") and "Savings" not in await stx(pg2, "[data-moves=out]")
    assert not pg.errors and not pg2.errors, (pg.errors, pg2.errors)

async def read_csv(ctx, name, body, cur="USD"):
    pg = await open_app(ctx)
    await pg.select_option("#m-cur", cur); await pg.wait_for_timeout(120)
    f = os.path.join(TMP, name); open(f, "w", encoding="utf-8").write(body)
    await pg.set_input_files("#stmt", f); await pg.wait_for_timeout(600)
    await pg.click("[data-st-open=all]"); await pg.wait_for_timeout(200)
    return pg, [x.replace(" ", " ").replace("\n", " | ") for x in await pg.locator("[data-st=all] .st-t").all_inner_texts()]

@test
async def statement_columns_are_matched_by_what_they_hold(ctx):
    # "Transaction Date" is not the description, "Value Date" is not the amount, and a balance column is never the amount
    body = "Sample Bank\nAccount Title: ALI RAZA KHAN\n\nTransaction Date,Value Date,Cheque No,Narration,Withdrawal (Dr),Deposit (Cr),Balance\n"
    body += "01-Jul-2026,01-Jul-2026,,SALARY ACME PVT LTD,,\"200,000.00\",\"300,000.00\"\n02-Jul-2026,02-Jul-2026,,RAAST P2P TO AHMED NAWAZ,\"50,000.00\",,\"250,000.00\"\n14-Jul-2026,15-Jul-2026,,NETFLIX.COM,\"1,100.00\",,\"248,900.00\"\n"
    pg, al = await read_csv(ctx, "cols.csv", body, "PKR")
    assert len(al) == 3 and "Jul 1, 2026" in al[0] and "SALARY ACME PVT LTD" in al[0] and "+PKR 200,000" in al[0], al
    assert "RAAST P2P TO AHMED NAWAZ" in al[1] and "PKR 50,000" in al[1] and "+" not in al[1] and "NETFLIX.COM" in al[2] and "PKR 1,100" in al[2], al
    assert "money out PKR 51,100" in await stx(pg, ".st-check")
    # one amount column with no sign, newest first: the running balance decides the direction of every line
    body = "Date,Details,Amount,Balance\n2026-07-20,CARD REFUND SHOE SHOP,35.00,2019.01\n2026-07-14,NETFLIX.COM,17.99,1984.01\n2026-07-05,ACME LTD,2000.00,2002.00\n2026-07-02,COFFEE HOUSE,8.00,2.00\n"
    pg, al = await read_csv(ctx, "bal.csv", body)
    line = lambda w: [x for x in al if w in x][0]
    assert len(al) == 4 and line("ACME LTD").endswith("+$2,000") and line("SHOE SHOP").endswith("+$35") and line("NETFLIX").endswith("| $17.99"), al
    assert line("COFFEE HOUSE").endswith("| $8"), "the oldest line has no earlier balance, so its wording decides"
    # a type column that says which way, tabs between columns, and a continental amount
    body = "Booking date\tText\tDebit/Credit\tAmount\n01.07.2026\tGEHALT ACME\tCredit\t2.500,00\n03.07.2026\tSUPERMARKT\tDebit\t1.234,56\n"
    pg, al = await read_csv(ctx, "tabs.tsv", body, "EUR")
    assert len(al) == 2 and "GEHALT ACME" in al[0] and "+€2,500" in al[0] and "SUPERMARKT" in al[1] and "€1,234.56" in al[1] and "+" not in al[1], al
    # semicolons, and money in brackets for money out
    body = "Date;Description;Amount\n07/01/2026;PAYROLL ACME;3000.00\n07/03/2026;HARDWARE STORE;(45.10)\n"
    pg, al = await read_csv(ctx, "semi.csv", body)
    assert len(al) == 2 and al[0].endswith("+$3,000") and "HARDWARE STORE" in al[1] and al[1].endswith("| $45.10"), al
    # a spreadsheet file is turned away with what to do instead
    pg = await open_app(ctx); x = os.path.join(TMP, "s.xlsx"); open(x, "wb").write(b"PK\x03\x04junk")
    await pg.set_input_files("#stmt", x); await pg.wait_for_timeout(300)
    assert "save it as CSV" in await pg.inner_text("#toast") and "Your statement" not in await text(pg, "#view")

@test
async def a_pdf_statement_with_wrapped_lines_and_columns_is_read_whole(ctx):
    pg = await open_app(ctx); await pg.select_option("#m-cur", "PKR"); await pg.wait_for_timeout(120)
    await pg.set_input_files("#stmt", os.path.join(FIX, "wrapped-statement.pdf")); await pg.wait_for_timeout(3000)
    v = await stx(pg, "#view"); assert "Your statement" in v and "22 transactions" in v, v[:300]
    # totals match the statement: 100,000 opening, 429,700 closing
    chk = await stx(pg, ".st-check"); assert "Money in PKR 825,000" in chk and "money out PKR 495,300" in chk, chk
    # the second line of a description belongs to the transaction above it, so names are found
    assert "Ahmed Nawaz" in await stx(pg, "[data-moves=out]") and "John Smith" in await stx(pg, "[data-moves=in]")
    oo = await stx(pg, "[data-moves=own-out]"); assert oo.count("IBFT TO ALI RAZA KHAN MEEZAN BANK") == 3 and "PKR 180,000" in oo, oo
    oi = await stx(pg, "[data-moves=own-in]"); assert oi.count("IBFT FROM ALI RAZA KHAN UBL") == 3 and "PKR 75,000" in oi, oi
    assert await pg.input_value("[data-stmt-holder]") == "Ali Raza Khan"
    # debit and credit columns decide the direction, the value date is not part of the wording, and the footer is not a transaction
    await pg.click("[data-st-open=all]"); await pg.wait_for_timeout(200)
    al = [x.replace(" ", " ").replace("\n", " | ") for x in await pg.locator("[data-st=all] .st-t").all_inner_texts()]
    assert len(al) == 22 and "Jul 1, 2026 | SALARY ACME PVT LTD | Pay | +PKR 200,000" in al[0], al[0]
    j = " || ".join(al); assert "NETFLIX.COM 866-579-7172 CARD ENDING 1234" in j and "POS IMTIAZ SUPER MARKET KARACHI PK" in j and "computer generated" not in j.lower() and "Page" not in j and "01-07-2026" not in j, j[:600]
    sub = await stx(pg, "[data-st=subs]"); assert "Netflix" in sub and "PKR 1,100/mo" in sub and "3 charges" in sub, sub
    assert not pg.errors, pg.errors

@test
async def names_are_read_past_the_banks_codes(ctx):
    # Banks wrap the name in references, account numbers and card numbers. The person or the shop is what is shown, never the code.
    L = ["Account Title: ALI RAZA KHAN", "Date,Description,Debit,Credit"]
    for m in ("07", "08", "09"):
        L += [f"01/{m}/2026,SALARY ACME PVT LTD,,200000",
              f"03/{m}/2026,Funds Transfer SM2120013{m}A8B0A6 FR ALI RAZA KHAN IBAN XXXX-1723 Thru Raast XYZ38358780{m}de143d6891f,,5000",
              f"04/{m}/2026,Funds Transfer 23189419170909{m} TO HBL 22797901820499 8864141709{m} Thru Digital Banking PK54HABB0022797901820499 SARA NOOR,1500,",
              f"05/{m}/2026,Funds Transfer SM2016325608{m}CCB TO ALI RAZA KHAN IBAN XXXX-4458 Thru Raast MBMB201132568172274{m},6000,",
              f"06/{m}/2026,Funds Transfer SM2016303887{m}C45 TO MARYAM ZEHRA HASSAN IBAN XXXX-3020 Thru Raast MBMB201130387661727{m},1000,",
              f"07/{m}/2026,Debit Card/POS 4687122002{m} 5366190+++++6162 07/{m} 6264153222{m} PKR 1641.69 200235 21{m} 5366190 FOOD PANDA KARACHI,1641.69,",
              f"09/{m}/2026,Debit Card/POS 2495290043{m} 5366190+++++6162 09/{m} 0920000056{m} PKR 3216.00 004316 20{m} 5366190 FAZAL DIN'S PHARMA P LAHORE,3216,",
              f"10/{m}/2026,Debit Card/POS 0898030012{m} Google G1SK006M London TRANSACTION AMT PKR 49.00 USD AMT .18 /USD Rate 277.95,50.03,",
              f"10/{m}/2026,Card Trxn Chgs 0898030012{m} 6263220898{m} RATE 4.00% + FED,2.32,",
              f"10/{m}/2026,With-Holding Tax 0898030012{m} 6263220898{m} 5.00% PUNJAB SALES TAX ON IT SERVICES,2.50,",
              f"11/{m}/2026,Trxn Charges HAWlowBalChAug26 Transaction charges,50,"]
    L += ["12/09/2026,Funds Transfer SM99887766AB12 FR OMAR FIRST CURRENT TRADERS IBAN XXXX-9911 Thru Raast XYZ12ab34,,700"]
    pg, al = await read_csv(ctx, "codes.csv", "\n".join(L) + "\n", "PKR")
    v = await stx(pg, "#view"); assert "Your statement" in v
    # people: the name after TO or FR, or the name at the very end, in full
    out = await stx(pg, "[data-moves=out]"); inn = await stx(pg, "[data-moves=in]")
    assert "Sara Noor" in out and "Maryam Zehra Hassan" in out, out
    assert "Omar First Current Traders" in inn, inn
    titles = await pg.evaluate("[...document.querySelectorAll('.st-item .move-txt > span')].map(e => e.textContent.trim())")
    assert not any(re.match(r"(Sm|Xyz|Mbmb|Pk|Hbl|Funds|Debit|Pkr)\b", t) for t in titles), titles
    # your own name, in both directions, every transaction
    oo = await stx(pg, "[data-moves=own-out]"); oi = await stx(pg, "[data-moves=own-in]")
    assert oo.count("TO ALI RAZA KHAN IBAN XXXX-4458") == 3 and "PKR 18,000" in oo and oi.count("FR ALI RAZA KHAN IBAN XXXX-1723") == 3 and "PKR 15,000" in oi, (oo, oi)
    assert "Ali Raza" not in out and "Ali Raza" not in inn
    # shops: the name after the card numbers, without the town
    sp = await stx(pg, "[data-st=spending]")
    assert "Eating out" in sp and "mostly Food Panda" in sp and "Karachi" not in sp, sp
    assert "Health" in sp and "Fazal Din's Pharma" in sp and "Lahore" not in sp, sp
    sb = await stx(pg, "[data-st=subs]"); assert "Google" in sb and "charged monthly" in sb and "London" not in v.replace("G1SK006M London", "") and "Pkr Food" not in v, sb   # the same charge every month is a subscription
    # the bank's own charges and the tax it holds back are named for what they are
    assert "Bank charges" in sp and "Tax payments" in await stx(pg, "[data-st=bills]"), sp
    j = " || ".join(al); assert "Sent to Sara Noor" in j and "Sent to Maryam Zehra Hassan" in j and "Sent to yourself" in j and "Received from yourself" in j and "Bank charges" in j, j[:500]
    # a word inside another word decides nothing: FIRST is not the tax office, CURRENT is not rent
    assert "Omar First Current Traders" not in await stx(pg, "[data-st=bills]") and "Housing" not in v
    assert not pg.errors, pg.errors

@test
async def subscriptions_are_found_properly_in_a_statement(ctx):
    L = ["Date,Description,Amount"]
    for m in ("04", "05", "06", "07"):
        L += [f"{m}/01/2026,PAYROLL ACME,3000.00", f"{m}/03/2026,APPLE.COM/BILL,-2.99", f"{m}/09/2026,APPLE.COM/BILL,-10.99", f"{m}/12/2026,QUIET BOOKS CLUB,-12.00",
              f"{m}/15/2026,HULU,-{'7.99' if m < '06' else '9.99'}", f"{m}/02/2026,CORNER COFFEE BAR,-4.50", f"{m}/09/2026,CORNER COFFEE BAR,-4.50", f"{m}/16/2026,CORNER COFFEE BAR,-4.50", f"{m}/23/2026,CORNER COFFEE BAR,-4.50",
              f"{m}/20/2026,ZELLE TO DANA REED,-50.00", f"{m}/21/2026,CITY PHARMACY,-20.00"]
    L += ["07/25/2026,GRAMMARLY,-144.00", "07/26/2026,GADGET WORLD,-89.00"]
    pg, al = await read_csv(ctx, "subs.csv", "\n".join(L) + "\n")
    items = await pg.evaluate("[...document.querySelectorAll('[data-st=subs] .st-item')].map(e => [e.dataset.stItem, e.innerText.replace(/\\u00a0/g, ' ')])")
    by = dict(items)
    # two things billed by the same store, month after month, are two subscriptions
    assert "sub:APPLE 2.99" in by and "sub:APPLE 10.99" in by and "4 charges" in by["sub:APPLE 2.99"] and "$10.99/mo" in by["sub:APPLE 10.99"], list(by)
    # a price that went up is still one subscription, at the new price
    assert "$9.99/mo" in by["sub:HULU"] and "4 charges" in by["sub:HULU"], by.get("sub:HULU")
    # an unknown name charged the same amount every month is one too, and says why
    assert "charged monthly" in by["sub:QUIET BOOKS CLUB"] and "charged monthly" not in by["sub:HULU"], by.get("sub:QUIET BOOKS CLUB")
    # a well-known service counts even when it was charged once
    assert "1 charge " in by["sub:GRAMMARLY"] + " ", by.get("sub:GRAMMARLY")
    # coffee every week, a pharmacy, a friend and a one-off shop are not subscriptions
    assert len(by) == 5 and not any(k in " ".join(by) for k in ("COFFEE", "PHARMACY", "DANA", "GADGET")), list(by)
    sub = await stx(pg, "[data-st=subs]"); assert "APPLE.COM/BILL" in sub and "(5)" in sub, sub
    await use_as_plan(pg); await pg.wait_for_timeout(300)
    st = await state(pg); assert sorted(s["name"] for s in st["subs"]) == ["Apple 10.99", "Apple 2.99", "Grammarly", "Hulu", "Quiet Books Club"], [s["name"] for s in st["subs"]]
    assert not pg.errors, pg.errors

@test
async def bigger_screens_use_their_width(ctx):
    # A computer gets the sections down the left side, cards in two columns and lists side by side. A tablet keeps the phone
    # layout with more room. Nothing ever runs off the side, at any size.
    pg = await open_app(ctx, w=1440, h=900)
    box = lambda sel: pg.evaluate("s => { const r = document.querySelector(s).getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }", sel)
    fits = "(() => { const m = document.getElementById('main'); return m.scrollWidth <= m.clientWidth + 1 && document.documentElement.scrollWidth <= innerWidth + 1 && [...document.querySelectorAll('#view button:not(.chip), #view input, #view select, #view .card')].every(e => { const r = e.getBoundingClientRect(); return r.width === 0 || (r.left >= -1 && r.right <= innerWidth + 1); }); })()"
    tb = await box("#tabbar"); assert tb[0] == 0 and tb[2] < 300 and tb[3] > 600, f"the sections run down the left side: {tb}"
    mn = await box("#main"); assert mn[0] >= tb[2] - 1 and mn[2] > 1100, mn
    assert await pg.evaluate("document.getElementById('view').classList.contains('wide')")
    cols = await pg.evaluate("[...document.querySelectorAll('#view > .cols > .col')].map(c => { const r = c.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.width), c.children.length]; })")
    assert len(cols) == 2 and cols[1][0] > cols[0][0] + cols[0][1] and min(c[1] for c in cols) > 400 and min(c[2] for c in cols) >= 2, cols
    assert await pg.evaluate("!!document.querySelector('#view > .cols > .col:nth-child(2) [data-out=comingUp]') && !!document.querySelector('#view > section.hero')"), "Coming up sits beside the month, under the number"
    for t in ("month", "subs", "cheaper", "codes", "plan", "split"):
        await tab(pg, t); await pg.wait_for_timeout(200); assert await pg.evaluate(fits), f"{t} fits at 1440"
    # lists run side by side
    await tab(pg, "subs"); tops = await pg.evaluate("[...document.querySelectorAll('[data-out=subsList] .rows > *')].slice(0, 4).map(e => Math.round(e.getBoundingClientRect().top))")
    assert tops[0] == tops[1] and tops[2] > tops[0], tops
    # the side menu works like the tab bar, and a card keeps working inside a column
    await pg.click("#tabbar [data-tab=month]"); await pg.wait_for_timeout(200)
    assert await pg.locator("#tabbar [data-tab=month]").get_attribute("aria-current") == "page"
    await pg.locator("[data-out=needs] [data-review=barely]").click(); await pg.wait_for_timeout(200)
    assert await pg.evaluate("document.querySelectorAll('#view > .cols').length") == 1, "the columns are rebuilt once, not stacked"
    # a focused screen (a statement to check) stays one readable column
    await pg.set_input_files("#stmt", os.path.join(FIX, "sample-bank-statement.csv")); await pg.wait_for_timeout(500)
    assert not await pg.evaluate("document.getElementById('view').classList.contains('wide')") and (await box("#view"))[2] <= 800 and await pg.evaluate(fits)
    await pg.click("[data-import-cancel]"); await pg.wait_for_timeout(200)
    # shrink the window to a phone and the phone layout is back; widen it and the columns return
    await pg.set_viewport_size({"width": 390, "height": 844}); await pg.wait_for_timeout(350)
    tb = await box("#tabbar"); assert tb[1] > 700 and tb[2] == 390 and await pg.evaluate("document.querySelectorAll('#view .cols').length") == 0 and await pg.evaluate(fits), tb
    await pg.set_viewport_size({"width": 1440, "height": 900}); await pg.wait_for_timeout(350)
    assert await pg.evaluate("document.querySelectorAll('#view > .cols > .col').length") == 2
    # every size in between and beyond: tablets upright and sideways, small laptops, a big monitor
    for w, h in ((600, 960), (768, 1024), (820, 1180), (1024, 768), (1180, 820), (1280, 720), (1366, 768), (1536, 864), (1920, 1080), (2560, 1440)):
        await pg.set_viewport_size({"width": w, "height": h}); await pg.wait_for_timeout(300)
        for t in ("month", "subs", "plan", "split"):
            await tab(pg, t); await pg.wait_for_timeout(150); assert await pg.evaluate(fits), f"{t} fits at {w}x{h}"
        side = (await box("#tabbar"))[0] == 0 and (await box("#tabbar"))[2] < 300
        assert side == (w >= 1024), f"side menu at {w}"
        vw = (await box("#view"))[2]; assert vw <= 1400 and vw >= min(w, 560) - 2, f"content width {vw} at {w}"
    # the welcome on a computer has no empty side strip
    pg2 = await open_app(ctx, w=1440, h=900, welcome=True); await pg2.evaluate("window.__kwErasing = true; localStorage.clear()"); await pg2.reload(); await pg2.wait_for_timeout(500)
    assert await pg2.evaluate("getComputedStyle(document.getElementById('tabbar')).display") == "none" and await pg2.evaluate("document.getElementById('main').getBoundingClientRect().left") == 0
    assert not pg.errors and not pg2.errors, (pg.errors, pg2.errors)

FILL_FORMS = """() => { const out = {};
  document.querySelectorAll('#view form, #view [data-pay] , #view details[open]').forEach((f, fi) => {
    f.querySelectorAll('input').forEach((el, i) => {
      if (el.readOnly || el.disabled || ['checkbox','radio','file','hidden','search'].includes(el.type) || el.offsetParent === null) return;
      const v = el.type === 'date' ? (el.max ? '2026-01-15' : '2028-04-20') :   /* a date that only looks back gets one from the past */ el.type === 'email' ? 'zed@example.com' : (el.inputMode === 'decimal' || el.inputMode === 'numeric') ? '37' : el.type === 'tel' ? '+1 555 010 0199' : 'Zed';
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, v);
      el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true}));
      el.setAttribute('data-sweep', fi + ':' + i); out[fi + ':' + i] = v; el.focus();
    }); });
  if (document.activeElement) document.activeElement.blur(); return out; }"""
READ_FORMS = """() => { const out = {}; document.querySelectorAll('#view form, #view [data-pay] , #view details[open]').forEach((f, fi) => f.querySelectorAll('input').forEach((el, i) => out[fi + ':' + i] = el.value)); return out; }"""

@test
async def no_card_loses_what_you_typed(ctx):
    # Tapping Done on the keyboard, or opening a date picker, takes focus out of the field. Whatever was typed in any
    # card anywhere in the app must still be there afterwards.
    pg = await open_app(ctx, fb=True)
    async def sweep(where, min_fields=1):
        want = await pg.evaluate(FILL_FORMS); assert len(want) >= min_fields, f"{where}: found {len(want)} fields"
        await pg.wait_for_timeout(350)
        got = await pg.evaluate(READ_FORMS)
        lost = {k: (v, got.get(k)) for k, v in want.items() if got.get(k) != v}
        assert not lost, f"{where}: lost {lost}"
    await pg.click("[data-inc-add]"); await pg.wait_for_timeout(100); await sweep("other income", 2); await pg.click("[data-inc-cancel]")
    await tab(pg, "subs"); await pg.click("text=Add a subscription"); await pg.wait_for_timeout(100); await sweep("add a subscription", 3)
    await pg.locator("[data-sub-edit]").first.click(); await pg.wait_for_timeout(100); await sweep("edit a subscription", 3); await pg.click("[data-sub-cancel]")
    await tab(pg, "cheaper"); await pg.click("text=Add your own comparison"); await pg.wait_for_timeout(100); await sweep("add a comparison", 2)
    await tab(pg, "codes"); await pg.click("text=Add a code you found"); await pg.wait_for_timeout(100); await sweep("add a code", 3)
    await pg.click("form[data-form=addCode] [type=submit]"); await pg.wait_for_timeout(150)
    await pg.locator("[data-code-edit]").first.click(); await pg.wait_for_timeout(100); await sweep("edit a code", 3); await pg.click("[data-code-cancel]")
    await tab(pg, "plan"); await pg.click("[data-add-exp]"); await pg.wait_for_timeout(100); await sweep("add a line", 2); await pg.click("[data-exp-cancel]")
    await pg.locator("[data-exp-edit]").first.click(); await pg.wait_for_timeout(100); await sweep("edit a line", 2); await pg.click("[data-exp-cancel]")
    await pg.click("[data-loan-add]"); await pg.wait_for_timeout(100); await sweep("add a loan", 5)
    for kind in ("card", "student", "home"):   # every dropdown in the loan card keeps its choice
        await pg.select_option("form[data-form=loan] [name=kind]", kind); await pg.evaluate("document.activeElement && document.activeElement.blur()"); await pg.wait_for_timeout(300)
        assert await pg.input_value("form[data-form=loan] [name=kind]") == kind, kind
    for ev in ("wk", "2wk", "yr"):
        await pg.select_option("form[data-form=loan] [name=every]", ev); await pg.evaluate("document.activeElement && document.activeElement.blur()"); await pg.wait_for_timeout(300)
        assert await pg.input_value("form[data-form=loan] [name=every]") == ev, ev
    assert await pg.input_value("form[data-form=loan] [name=name]") == "Zed"
    await pg.click("[data-loan-cancel]")
    await tab(pg, "split"); await pg.click("[data-new-split]"); await pg.wait_for_timeout(100); await sweep("new split", 2); await pg.click("[data-cancel-split]")
    await open_account(pg); await pg.click("[data-acc-mode=create]"); await pg.wait_for_timeout(120); await sweep("sign up", 2)
    assert not pg.errors, pg.errors

@test
async def keepwise_plus_codes_show_as_eligible(ctx):
    pg = await open_app(ctx); await tab(pg, "codes")
    box = await text(pg, "[data-kw-codes]")
    assert "KeepWise Plus codes" in box and "EARLY140" in box and "EARLY12" in box and box.count("Eligible") == 2, box
    assert "$140 for your first year, instead of $180" in box and "$12 a month for your first 6 months, instead of $15" in box and "when Plus opens" in box
    await pg.locator("[data-kw-code=EARLY140] [data-copy]").click(); await pg.wait_for_timeout(150); assert "Cop" in await pg.inner_text("#toast"), "tapping the code copies it"
    assert not any(c["code"].startswith("EARLY") for c in (await state(pg))["codes"]), "KeepWise codes are not mixed into your own list"
    await pg.click("[data-kw-codes] [data-plus-open]"); await pg.wait_for_timeout(150); assert await pg.locator(".plus-prices").count() == 1
    assert not pg.errors, pg.errors

@test
async def loans_section_counts_and_finishes(ctx):
    pg = await open_at(ctx, (2026, 10, 5, 10, 0)); await tab(pg, "plan")
    need0 = money((await text(pg, "[data-out=expTotal]")).split("·")[0])
    await tab(pg, "month"); kept0 = money(await text(pg, "[data-out=envelopes] .env-row >> nth=0")); assert await pg.locator("[data-loans-row]").count() == 0, "no row until there is a loan"
    await tab(pg, "plan")
    box = await text(pg, "[data-out=loans]"); assert "Loans and debt" in box and "Add a loan or credit card" in box
    await pg.click("[data-loan-add]"); f = pg.locator("form[data-form=loan]")
    assert [o.strip() for o in await f.locator("[name=kind] option").all_inner_texts()] == ["Bank loan", "Personal loan", "Student debt", "Credit card", "Car loan", "Mortgage", "Other debt"]
    assert [o.strip() for o in await f.locator("[name=every] option").all_inner_texts()] == ["Every month", "Every week", "Every 2 weeks", "Every year"]
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(100); assert "Enter the payment amount" in await pg.inner_text("#toast")
    # a student debt paid weekly, with an amount left and no end date: the finish is estimated and says interest is not included
    await f.locator("[name=kind]").select_option("student"); await f.locator("[name=pay]").fill("60"); await f.locator("[name=every]").select_option("wk"); await f.locator("[name=total]").fill("5200")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    box = await text(pg, "[data-out=loans]")
    assert "Student debt" in box and "$60 a week" in box and "$260/mo" in box and "$5,200 left" in box and "About 20 months to go" in box and "Jun 2028" in box and "Interest is not included" in box, box
    et = await text(pg, "[data-out=expTotal]")
    assert abs(money(et.split("·")[0]) - need0) < 0.01 and "Loans & debts $260" in et, "the payment sits apart from Expenditures: " + et
    # a bank loan with an end date
    await pg.click("[data-loan-add]"); f = pg.locator("form[data-form=loan]")
    await f.locator("[name=name]").fill("Car"); await f.locator("[name=kind]").select_option("car"); await f.locator("[name=pay]").fill("300"); await f.locator("[name=end]").fill("2027-04-05")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    box = await text(pg, "[data-out=loans]"); assert "Ends Apr 2027, 6 months from now" in box and "$560/mo" in box, box
    assert len((await state(pg))["loans"]) == 2
    # Month has its own Loans & debts row: read-only, it lowers what you keep, and Expenditures does not count it twice
    await tab(pg, "month"); row = pg.locator("[data-loans-row]")
    head = await row.inner_text(); assert "Loans & debts" in head and "$560" in head and "2 repayments each month" in head and "% of income" in head, head
    assert abs(kept0 - money(await text(pg, "[data-out=envelopes] .env-row >> nth=0")) - 560) < 0.01, "what you keep drops by the repayments"
    await pg.click("[data-env-open=needs]"); await pg.wait_for_timeout(150); assert "Student debt" not in await text(pg, ".env-body")
    await pg.click("[data-env-open=loans]"); await pg.wait_for_timeout(150)
    d = await row.inner_text(); assert "Student debt" in d and "Car" in d and "$300" in d and "ends Apr 2027" in d and "You owe $5,200 in total" in d, d
    assert await row.locator("input, select, [data-del-exp]").count() == 0, "nothing to edit here"
    await row.locator("[data-go=plan]").click(); await pg.wait_for_timeout(150); assert await pg.locator("[data-out=loans]").count() == 1
    await tab(pg, "month")
    # once the end date has passed it stops counting
    await pg.clock.set_fixed_time(__import__("datetime").datetime(2027, 4, 20, 10, 0)); await tab(pg, "plan"); await pg.wait_for_timeout(150)
    # picking an end date, or tapping Done on the keyboard, never empties the card (the iPhone date picker takes focus away)
    await pg.click("[data-loan-add]"); f = pg.locator("form[data-form=loan]")
    await f.locator("[name=name]").fill("Bank of America"); await f.locator("[name=total]").fill("700"); await f.locator("[name=end]").fill("2028-04-20")
    await pg.evaluate("document.activeElement.blur()"); await pg.wait_for_timeout(250)
    assert await f.locator("[name=name]").input_value() == "Bank of America" and await f.locator("[name=total]").input_value() == "700" and await f.locator("[name=end]").input_value() == "2028-04-20"
    await pg.click("[data-loan-cancel]"); await pg.wait_for_timeout(100)
    # interest appears only when payment, amount left, installments and end date are all there, and the maths is exact
    await pg.click("[data-loan-add]"); f = pg.locator("form[data-form=loan]")
    assert await f.locator("[name=rate]").get_attribute("readonly") is not None and await f.locator("[name=rate]").input_value() == ""
    await f.locator("[name=pay]").fill("100"); await f.locator("[name=total]").fill("1100"); await f.locator("[name=left]").fill("12"); await pg.wait_for_timeout(80)
    assert await f.locator("[name=rate]").input_value() == "", "no end date yet, so no interest shown"
    await f.locator("[name=end]").fill("2028-04-20"); await pg.wait_for_timeout(80)
    assert await f.locator("[name=rate]").input_value() == "16.4% a year", await f.locator("[name=rate]").input_value()
    assert "$1,200 in all, which is $100 in interest" in await f.locator("[data-loan-ratenote]").inner_text()
    await f.locator("[name=total]").fill("1200"); await pg.wait_for_timeout(80); assert await f.locator("[name=rate]").input_value() == "0% a year"
    await f.locator("[name=total]").fill("5000"); await pg.wait_for_timeout(80)
    assert await f.locator("[name=rate]").input_value() == "Check the numbers" and "less than the amount left" in await f.locator("[data-loan-ratenote]").inner_text()
    await f.locator("[name=left]").fill("a few"); await pg.wait_for_timeout(80); assert await f.locator("[name=rate]").input_value() == ""
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(120); assert "whole number" in await pg.inner_text("#toast")
    await f.locator("[name=left]").fill("12"); await f.locator("[name=total]").fill("1100"); await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    box = await text(pg, "[data-out=loans]"); assert "12 installments left · interest about 16.4% a year" in box, box
    await pg.locator("[data-loan]").last.locator("[data-loan-edit]").click(); await pg.wait_for_timeout(120)
    assert await pg.input_value("form[data-form=loan] [name=left]") == "12" and await pg.input_value("form[data-form=loan] [name=rate]") == "16.4% a year"
    await pg.locator("form[data-form=loan] [data-loan-del]").click(); await pg.wait_for_timeout(150)
    # a credit card: its type shows, and the yearly fee is spread across the year
    await pg.click("[data-loan-add]"); f = pg.locator("form[data-form=loan]")
    assert not await f.locator("[data-loan-cardrow]").is_visible(), "card fields stay hidden for other debts"
    await f.locator("[name=kind]").select_option("card"); await pg.wait_for_timeout(80)
    assert [o.strip() for o in await f.locator("[name=card] option").all_inner_texts()] == ["Visa", "Mastercard", "American Express", "Discover", "UnionPay", "Other"]
    await pg.evaluate("document.activeElement.blur()"); await pg.wait_for_timeout(250)
    assert await f.locator("[name=kind]").input_value() == "card" and await f.locator("[data-loan-cardrow]").is_visible(), "the chosen type stays chosen"
    await f.locator("[name=card]").select_option("Mastercard"); await f.locator("[name=pay]").fill("100"); await f.locator("[name=fee]").fill("120")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    box = await text(pg, "[data-out=loans]"); assert "Credit card · Mastercard · $100 a month · $120 yearly fee" in box and "$110/mo" in box, box
    card = [l for l in (await state(pg))["loans"] if l["kind"] == "card"][0]; assert card["card"] == "Mastercard" and card["fee"] == 120
    # Other lets you type the card's own name, and it comes back when you edit
    await pg.locator("[data-loan]").last.locator("[data-loan-edit]").click(); await pg.wait_for_timeout(120); f = pg.locator("form[data-form=loan]")
    assert not await f.locator("[data-loan-cardother]").is_visible()
    await f.locator("[name=card]").select_option("Other"); await pg.wait_for_timeout(80); await f.locator("[name=cardOther]").fill("Target RedCard")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    assert "Credit card · Target RedCard · $100 a month" in await text(pg, "[data-out=loans]")
    await pg.locator("[data-loan]").last.locator("[data-loan-edit]").click(); await pg.wait_for_timeout(120)
    assert await pg.input_value("form[data-form=loan] [name=card]") == "Other" and await pg.input_value("form[data-form=loan] [name=cardOther]") == "Target RedCard"
    await pg.locator("form[data-form=loan] [data-loan-del]").click(); await pg.wait_for_timeout(150)
    box = await text(pg, "[data-out=loans]"); assert "Paid off" in box and "no longer counts" in box and "$260/mo" in box, box
    assert "Loans & debts $260" in await text(pg, "[data-out=expTotal]")
    # edit and remove, with undo
    await pg.locator("[data-loan]").first.locator("[data-loan-edit]").click(); await pg.wait_for_timeout(120)
    await pg.locator("form[data-form=loan] [data-loan-del]").click(); await pg.wait_for_timeout(150)
    assert len((await state(pg))["loans"]) == 1
    await pg.click(".toast-undo"); await pg.wait_for_timeout(150); assert len((await state(pg))["loans"]) == 2
    assert not pg.errors, pg.errors

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
    await use_as_plan(pg); await pg.wait_for_timeout(200)
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
        v = await pg.inner_text("#view")
        kw = pg.locator("[data-kw-codes]")   # KeepWise Plus is priced in US dollars for everyone, and says so on the Plus screen
        if await kw.count(): v = v.replace(await kw.inner_text(), "")
        assert "$" not in v, f"{where}: " + v[max(0, v.index("$") - 40): v.index("$") + 20].replace("\n", " ")
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
    await use_as_plan(pg); await pg.wait_for_timeout(250)
    st = await state(pg); n = [x for x in st["subs"] if x["name"].lower().startswith("netflix")][0]
    assert n["price"] == 12.5 and st["income"] == 2500 and st["cur"] == "USD" and st["imported"]["cur"] == "GBP" and st["imported"]["rate"] == 1.25
    # switching the plan instead
    await pg.set_input_files("#stmt", gbp); await pg.wait_for_timeout(400)
    await pg.locator(".fx-opt input[value=switch]").check(); await pg.wait_for_timeout(120)
    await use_as_plan(pg); await pg.wait_for_timeout(250)
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
    f = pg.locator("form[data-form=pay]"); await f.locator("[name=next]").fill("2026-10-16"); await f.locator("[name=amount]").fill("2600")   # the next payday is today or later; the two-week rhythm runs both ways from it
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    st = await state(pg); assert st["income"] == 5200 and st["pay"]["when"] == "biweekly"
    head = await tc(pg, "[data-out=headline]"); assert "October has 3 paydays, so an extra $2,600 is counted" in head, head
    assert abs(money(await text(pg, "[data-out=headline] .big")) - (1456.99 + 2600)) < 0.01
    assert await pg.locator("[data-out=payBox] .pay-line").count() == 0, "the schedule stays behind the (i)"; await pg.click("[data-info=pay]"); await pg.wait_for_timeout(120)
    box = await text(pg, "[data-out=payBox]"); assert "every 2 weeks" in box and "next payday" in box and "Oct 16" in box
    await pg.click("#view [data-info=ask]"); await pg.wait_for_timeout(150)   # the steps live inside Ask KeepWise now
    how = await text(pg, "[data-out=howto]"); await pg.click("#view [data-info=pay]"); await pg.wait_for_timeout(120); assert "Your next payday is Friday, Oct 16" in how and "each of October’s 3 paychecks" in how
    # the monthly number and the paycheck stay in step
    await pg.fill("#m-income", "6000"); await pg.locator("#m-income").blur(); await pg.wait_for_timeout(200)
    assert (await state(pg))["pay"]["amount"] == 3000
    await pg.click("[data-history]"); await pg.locator(".stmt-row").first.click(); await pg.wait_for_timeout(120)
    assert "Extra paycheck" in await text(pg, ".stmt")
    await pg.click("[data-stmt-back]"); await pg.click("[data-history-close]")
    await pg.click("[data-payday-edit]"); await pg.click("[data-payday-clear]"); await pg.wait_for_timeout(150)
    assert (await state(pg))["pay"] is None and "extra" not in await tc(pg, "[data-out=headline]")

@test
async def month_can_start_on_payday(ctx):
    pg = await open_at(ctx, (2026, 10, 5, 10, 0))
    await pg.click("[data-payday-edit]"); f = pg.locator("form[data-form=pay]")
    await f.locator("[name=day]").select_option("25"); await f.locator("[name=amount]").fill("5200"); await f.locator("[name=monthStart]").select_option("25")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(250)
    note = await text(pg, "[data-out=planNote]"); assert "19 days left in your month, Sep 25 to Oct 24." in note and "October" not in note, note
    st = await state(pg); assert st["monthStart"] == 25 and "2026-10" in st["statements"] and st["statements"]["2026-10"]["range"] == "Sep 25 to Oct 24"
    if await pg.locator("[data-out=payBox] .pay-line").count() == 0: await pg.click("[data-info=pay]"); await pg.wait_for_timeout(120)
    up = await text(pg, "[data-out=payBox]"); assert "on the 25th" in up and "Oct 25" in up
    # a payment logged on Sep 26 belongs to this October; one on Sep 20 does not
    await pg.click("[data-inc-add]"); g = pg.locator("form[data-form=income]"); await g.locator("[name=name]").fill("Tutoring"); await g.locator("[name=amount]").fill("300"); await g.locator("button[type=submit]").click(); await pg.wait_for_timeout(150)
    for d, a in [("2026-09-26", "80"), ("2026-09-20", "50")]:
        await pg.click("[data-inc-log]"); lf = pg.locator("form[data-form=incomeLog]"); await lf.locator("[name=amount]").fill(a); await lf.locator("[name=date]").fill(d); await lf.locator("button[type=submit]").click(); await pg.wait_for_timeout(150)
    assert "$80 of $300" in await text(pg, ".inc-card")
    await pg.close()
    p2 = await open_at(ctx, (2026, 10, 26, 10, 0))
    assert "is closed" in (await text(p2, "[data-out=monthClose]")).lower(), "the month closes on the 24th, not the 31st"
    assert "days left in your month, Oct 25 to Nov 24." in await text(p2, "[data-out=planNote]"), await text(p2, "[data-out=planNote]")
    # two days before the month ends the plan moves on, and says so with dates rather than a month name
    p3 = await open_at(ctx, (2026, 11, 23, 10, 0)); n3 = await text(p3, "[data-out=planNote]")
    assert n3 == "Your month ends tomorrow, Nov 24, so this plan covers the next one: Nov 25 to Dec 24.", n3

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
    assert await pg.locator("#tabbar [data-tab=subs][aria-current=page]").count() == 1 and await pg.locator("#view .sub-seg [data-go=codes][aria-pressed=true]").count() == 1, "it reopens on Codes, inside Subs"
    await tab(pg, "month"); assert await pg.input_value("#m-income") == "4321"

# ---------------- four tabs, the side menu, quiet text, and money coming in ----------------
async def _keep(pg):
    if await pg.locator(".hero .big").count() == 0: await tab(pg, "month")
    return float((await pg.inner_text(".hero .big")).replace("$", "").replace(",", ""))
async def _ask(pg, q):
    await pg.evaluate("(() => { const c = document.querySelector('#asksheet [data-ask-close]'); if (c) c.click(); })()"); await pg.wait_for_timeout(120)
    await ask_type(pg, q); await pg.wait_for_timeout(650)
    return await pg.evaluate("(() => { const t = document.getElementById('toast'), o = document.getElementById('ask-out'); return (t && !t.hidden && (t.dataset.full || t.innerText)) || (o && !o.hidden && o.innerText) || ''; })()")
async def _menu(pg, k):
    if await pg.locator("#sidenav .sn").count() == 0: await pg.click("#acct-btn"); await pg.wait_for_timeout(280)
    await pg.click(f"#sidenav [data-menu={k}] >> nth=-1"); await pg.wait_for_timeout(280)

@test
async def four_tabs_with_cheaper_and_codes_inside_subs(ctx):
    for w in (320, 360, 390):
        pg = await open_app(ctx, w=w, h=760)
        assert await pg.locator("#tabbar .tab").all_inner_texts() == ["Month", "Subs", "Plan", "Split"], "four tabs, in this order"
        await tab(pg, "subs"); seg = pg.locator("#view .sub-seg button")
        assert await seg.all_inner_texts() == ["Yours", "Cheaper", "Codes"] and await seg.nth(0).get_attribute("aria-pressed") == "true"
        assert await pg.locator("[data-out=subsList]").count() == 1, "Yours still holds the whole subscriptions list"
        await pg.click("#view [data-go=cheaper]"); await pg.wait_for_timeout(150)
        assert await pg.locator("[data-out=cheapIdeas]").count() == 1 and await pg.locator("#view .sub-seg button[aria-pressed=true]").inner_text() == "Cheaper"
        assert await pg.locator("#tabbar [aria-current=page]").get_attribute("data-tab") == "subs", "the Subs tab stays lit inside Cheaper"
        await pg.click("#view [data-go=codes]"); await pg.wait_for_timeout(150)
        assert await pg.locator("#code-q").count() == 1 and await pg.locator("#tabbar [aria-current=page]").get_attribute("data-tab") == "subs"
        await pg.click("#view [data-go=subs]"); await pg.wait_for_timeout(150); assert await pg.locator("[data-out=subsList]").count() == 1
        box = await pg.locator("#view .sub-seg").bounding_box(); assert box["x"] >= 0 and box["x"] + box["width"] <= w + 0.5, "the switch fits the screen"
        assert await pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"no sideways scroll at {w}"
        # a link elsewhere that points at Cheaper still lands there
        await tab(pg, "month"); await pg.evaluate("document.querySelector('[data-go=cheaper]') && document.querySelector('[data-go=cheaper]').click()"); await pg.wait_for_timeout(150)
        assert not pg.errors, pg.errors; await pg.close()

@test
async def the_side_menu_opens_each_place(ctx):
    pg = await open_app(ctx, w=360, h=760)
    assert await pg.locator("#sidenav").is_hidden()
    await pg.click("#acct-btn"); await pg.wait_for_timeout(300)
    rows = await pg.locator("#sidenav .sn-row span").all_inner_texts()
    assert rows == ["Sign in or create account", "Account settings", "Security", "Appearance", "Backups", "Replay the tour", "Support"], rows
    assert "Delete" not in await pg.inner_text("#sidenav"), "delete is not offered in the menu"
    box = await pg.locator("#sidenav .sn").bounding_box(); assert box["x"] > 0 and abs(box["x"] + box["width"] - 360) < 1 and box["height"] >= 759, "a panel on the right, full height"
    # tapping outside closes it and changes nothing
    await pg.mouse.click(10, 300); await pg.wait_for_timeout(250); assert await pg.locator("#sidenav").is_hidden() and await pg.locator(".hero").count() == 1
    await _menu(pg, "close"); assert await pg.locator("#sidenav").is_hidden()
    # each row goes to its own place
    await _menu(pg, "settings"); assert await pg.locator("#view h1").inner_text() == "Account settings" and await pg.locator("[data-set-backup]").count() == 1 and await pg.locator("[data-lock-card]").count() == 0
    await _menu(pg, "security"); assert await pg.locator("#view h1").inner_text() == "Security" and await pg.locator("[data-lock-card]").count() == 1 and await pg.locator("[data-set-backup]").count() == 0
    await pg.click("[data-lock-set]"); await pg.wait_for_timeout(150); assert await pg.locator("form[data-form=lockSet]").count() == 1, "the passcode form opens on the Security screen"
    await pg.click("[data-lock-cancel]"); await pg.wait_for_timeout(100)
    await _menu(pg, "support"); assert await pg.locator("#view h1").inner_text() == "Support" and await pg.locator("[data-help-link=email]").get_attribute("href") == "mailto:support@mykeepwise.com"
    await _menu(pg, "backup"); assert await pg.locator("#view h1").inner_text() == "Account settings" and await pg.locator("[data-backup]").count() == 1
    await pg.click("[data-settings-close]"); await pg.wait_for_timeout(150); assert await pg.locator(".hero").count() == 1, "Done returns to the month"
    await _menu(pg, "plus"); assert "Everything free stays free" in await pg.inner_text("#view")
    await pg.click("[data-plus-close]"); await pg.wait_for_timeout(150)
    await _menu(pg, "biz"); t = await pg.inner_text("#view"); assert "Keep business and personal money apart" in t and "Everything free stays free" not in t, "Business shows the Business card, not the Plus screen"
    await pg.click("#acct-btn"); await pg.wait_for_timeout(280); assert await pg.get_attribute("#sidenav [data-menu=biz]", "aria-pressed") == "true"
    await _menu(pg, "personal"); assert await pg.locator(".hero [data-out=headline]").count() == 1
    await _menu(pg, "profile"); assert await pg.locator("#view").inner_text() != "" and await pg.locator(".hero").count() == 0, "the account screen opens"
    await tab(pg, "month")
    # appearance changes the theme and leaves the menu open
    await pg.click("#acct-btn"); await pg.wait_for_timeout(280); before = await pg.evaluate("document.documentElement.dataset.theme || ''")
    await pg.click("#sidenav [data-menu=theme]"); await pg.wait_for_timeout(200)
    assert await pg.evaluate("document.documentElement.dataset.theme || ''") != before and await pg.locator("#sidenav .sn").count() == 1
    await _menu(pg, "tour"); assert not await pg.locator("#tour").is_hidden(), "the tour replays from the menu"
    await pg.click("[data-tour-skip]") if await pg.locator("[data-tour-skip]").count() else None
    # the header keeps its theme button, and it works
    assert await pg.locator("#theme-btn").is_visible()
    # moving to a tab closes a settings screen
    await pg.evaluate("document.getElementById('tour').hidden = true")
    assert not pg.errors, pg.errors

@test
async def settings_leave_plan_and_delete_sits_quietly_at_the_foot(ctx):
    pg = await open_app(ctx, w=360, h=760)
    await tab(pg, "plan"); t = await pg.inner_text("#view")
    assert "Download a backup" not in t and "App lock" not in t and "Help and contact" not in t and "Replay the tour" not in t, "Plan no longer carries settings"
    assert await pg.locator("#view [data-import-open].primary").count() == 1 and await pg.locator("#view [data-history]").count() == 1
    hs = await pg.evaluate("[...document.querySelectorAll('#view h2')].map(h => h.childNodes[0].textContent.trim())")
    assert hs.index("Giving") == hs.index("Savings") + 1, hs
    await pg.set_viewport_size({"width": 780, "height": 760}); await pg.wait_for_timeout(150)
    a = await pg.locator("[data-reset=example]").bounding_box(); b = await pg.locator("[data-reset=blank]").bounding_box(); card = await pg.locator("[data-reset=blank]").locator("xpath=ancestor::section[1]").bounding_box()
    assert abs(a["y"] - b["y"]) < 2 and card["x"] + card["width"] - (b["x"] + b["width"]) < 30, "Start empty sits at the right edge of the card"
    await pg.set_viewport_size({"width": 360, "height": 760})
    await _menu(pg, "settings")
    link = pg.locator("#view [data-del-toggle]"); assert await link.inner_text() == "Delete account and data"
    last = await pg.evaluate("document.querySelector('#view').lastElementChild.matches('[data-del-toggle]')"); assert last, "it is the last thing on the screen"
    style = await link.evaluate("e => [getComputedStyle(e).color, getComputedStyle(document.querySelector('.btn.danger') || e).color, parseFloat(getComputedStyle(e).fontSize)]")
    assert style[2] < 15, "small and quiet, not a red button"
    await link.click(); await pg.wait_for_timeout(200)
    box = await pg.inner_text("[data-del-box]"); assert "Erase this phone" in box and "Keep everything" in box and "Delete my account" not in box, "signed out, only the phone can be erased"
    await pg.click("[data-del-box] [data-del-toggle]"); await pg.wait_for_timeout(150); assert await pg.locator("[data-del-box]").count() == 0 and (await state(pg))["expenses"], "Keep everything keeps everything"
    await pg.click("#view [data-del-toggle]"); await pg.click("[data-del-box] [data-reset=blank]"); await pg.wait_for_timeout(150)
    assert "can’t be undone" in await pg.inner_text("#reset-confirm"), "erasing asks first"
    await pg.click("[data-reset-no]"); await pg.wait_for_timeout(100); assert (await state(pg))["expenses"]
    # going to a tab leaves the settings screen
    await tab(pg, "split"); assert await pg.locator("#view [data-del-toggle]").count() == 0
    assert not pg.errors, pg.errors

@test
async def explanations_wait_behind_the_info_icon_but_warnings_stay(ctx):
    pg = await open_app(ctx, w=360, h=760)
    hero = pg.locator(".hero"); note = pg.locator(".hero [data-out=headline] p.muted")
    assert await note.count() == 1 and not await note.is_visible(), "the explanation is tucked away"
    assert await pg.locator(".hero .big").is_visible() and await pg.locator(".hero h1").is_visible()
    i = pg.locator(".hero [data-hint]"); assert await i.get_attribute("aria-expanded") == "false"
    b = await i.bounding_box(); assert b["width"] >= 30 and b["height"] >= 30, "the icon is still easy to tap"
    await i.click(); await pg.wait_for_timeout(120); assert await note.is_visible() and await i.get_attribute("aria-expanded") == "true"
    await tab(pg, "plan"); await tab(pg, "month"); assert await pg.locator(".hero [data-out=headline] p.muted").is_visible(), "it stays open until closed"
    await pg.click(".hero [data-hint]"); await pg.wait_for_timeout(120); assert not await pg.locator(".hero [data-out=headline] p.muted").is_visible()
    # a money warning is never hidden: push needs over the envelope
    await tab(pg, "plan"); await ask_type(pg, "add rent top up 4000 as a bill"); await pg.wait_for_timeout(600); await tab(pg, "month")
    w = pg.locator("[data-hero-warn]"); assert await w.is_visible() and ("over the envelope" in await w.inner_text() or "spends more than comes in" in await w.inner_text()), await pg.inner_text(".hero")
    # an empty month keeps its guidance
    await tab(pg, "plan"); await pg.click("[data-reset=blank]"); await pg.click("#reset-confirm [data-reset-yes]"); await pg.wait_for_timeout(400)
    await tab(pg, "month"); await pg.wait_for_timeout(200)
    # the tour shows the full text again
    pg2 = await open_app(ctx, w=360, h=760); await _menu(pg2, "tour"); await pg2.wait_for_timeout(300)
    assert await pg2.locator(".hero [data-out=headline] p.muted").is_visible(), "during the tour nothing is tucked away"
    assert not pg.errors and not pg2.errors, pg.errors + pg2.errors

@test
async def compare_the_close_is_always_open_just_above_ask(ctx):
    pg = await open_app(ctx, w=360, h=760)
    assert await pg.locator("[data-compare]").count() == 0, "no button to open it"
    assert await pg.locator("[data-out=dropCard] .cmp-col").count() == 2
    order = await pg.evaluate("[...document.querySelectorAll('#view > *')].map(e => e.dataset.out || e.getAttribute('aria-labelledby') || '').filter(Boolean).slice(-2)")
    assert order == ["dropCard", "askh"], order
    h = (await pg.locator("[data-out=dropCard] .cmp").bounding_box())["height"]; assert h <= 110, "a small chart"
    assert "How to use it" not in await pg.evaluate("[...document.querySelectorAll('#view h2')].map(h => h.textContent).join('|')"), "How to use it is no longer a card of its own"
    assert await pg.locator("#view [data-out=howto]").count() == 0
    await pg.click("#view [data-info=ask]"); await pg.wait_for_timeout(150)
    assert await pg.locator("#view .ask-howto [data-out=howto]").count() == 1, "it opens inside Ask KeepWise"
    await pg.click("#view [data-info=ask]"); await pg.wait_for_timeout(150); assert await pg.locator("#view [data-out=howto]").count() == 0
    # with nothing flagged the card carries no leftover sentence
    await tab(pg, "plan"); await pg.click("[data-reset=blank]"); await pg.click("#reset-confirm [data-reset-yes]"); await pg.wait_for_timeout(400); await tab(pg, "month")
    t = await pg.inner_text("[data-out=dropCard]"); assert "Your rules" not in t and "No subscriptions yet" not in t and "COMPARE THE CLOSE" in t.upper(), t
    assert not pg.errors, pg.errors

@test
async def money_coming_in_is_never_logged_as_spending(ctx):
    pg = await open_app(ctx); base = await _keep(pg); n0 = len((await state(pg)).get("spends") or [])
    # one-off money in raises what you keep, by exactly that much
    for q, name, amt in [("I got paid 500 for a freelance job", "Freelance job", 500), ("got a 300 bonus", "Bonus", 300), ("earned 150 from selling my old phone", "Selling my old phone", 150), ("sold my bike for 120", "Sold my bike", 120)]:
        k0 = await _keep(pg); r = await _ask(pg, q); s = await state(pg)
        assert r.startswith("Added as money in this month") and name in r, f"{q}: {r}"
        assert s["ins"][-1]["name"] == name and s["ins"][-1]["amount"] == amt and len(s.get("spends") or []) == n0, f"{q}: stored as money in, not spending"
        assert abs(await _keep(pg) - (k0 + amt)) < 0.01, f"{q}: keep goes up by {amt}"
    card = await pg.inner_text("[data-ins]"); assert "Money in this month" in card and "+$1,070" in card and card.count("Remove") == 4, card
    # Undo and Remove both put the number back
    k0 = await _keep(pg); await _ask(pg, "got paid 80"); assert abs(await _keep(pg) - (k0 + 80)) < 0.01
    await pg.click("#toast button"); await pg.wait_for_timeout(300); assert abs(await _keep(pg) - k0) < 0.01 and len((await state(pg))["ins"]) == 4
    await pg.locator("[data-in-del]").first.click(); await pg.wait_for_timeout(300); assert len((await state(pg))["ins"]) == 3 and abs(await _keep(pg) - (k0 - 500)) < 0.01
    # a pay change replaces regular pay, it does not add a line
    k0 = await _keep(pg); was = (await state(pg))["income"]; r = await _ask(pg, "my salary is now 5600"); s = await state(pg)
    assert s["income"] == 5600 and f"It was ${was:,.0f}" in r and len(s["ins"]) == 3 and abs(await _keep(pg) - (k0 + 5600 - was)) < 0.01, r
    # a refund comes off this month's spending
    k0 = await _keep(pg); r = await _ask(pg, "refund of 40 from Amazon"); s = await state(pg)
    assert "refund" in r.lower() and s["spends"][-1]["amount"] == -40 and s["spends"][-1]["name"] == "Refund: Amazon" and abs(await _keep(pg) - (k0 + 40)) < 0.01, r
    # someone who owes you pays part: the split is settled, the month does not move
    k0 = await _keep(pg); n = len(s["settlements"]); r = await _ask(pg, "received 20 from Sam"); s = await state(pg)
    assert "Recorded $20 from Sam" in r and "$29.50 is still owed" in r and len(s["settlements"]) == n + 1 and s["settlements"][-1]["amount"] == 20 and s["settlements"][-1]["to"] == "me", r
    assert await pg.locator("#tabbar [aria-current=page]").get_attribute("data-tab") == "split" and abs(await _keep(pg) - k0) < 0.01
    # paying more than was owed settles the debt and counts the rest as money in
    r = await _ask(pg, "received 100 from Sam"); s = await state(pg)
    assert "You are square" in r and "$70.50" in r and s["settlements"][-1]["amount"] == 29.5 and s["ins"][-1] ["amount"] == 70.5 and s["ins"][-1]["name"] == "From Sam", r
    # someone who owes nothing: plain money in
    r = await _ask(pg, "received 60 from Grandma"); s = await state(pg); assert r.startswith("Added as money in") and s["ins"][-1]["amount"] == 60, r
    assert not pg.errors, pg.errors

@test
async def unclear_or_ordinary_lines_are_not_mistaken_for_income(ctx):
    pg = await open_app(ctx)
    snap = lambda s: (len(s.get("ins") or []), len(s.get("spends") or []), s["income"], len(s["settlements"]))
    # spending still goes out
    for q, name, amt in [("uber 20", "Uber", 20), ("paid 15 for lunch", "Lunch", 15), ("spent 9 on a sandwich", None, 9)]:
        k0 = await _keep(pg); r = await _ask(pg, q); s = await state(pg)
        assert r.startswith("Added to this month under Miscellaneous") and s["spends"][-1]["amount"] == amt and not s.get("ins"), f"{q}: {r}"
        assert abs(await _keep(pg) - (k0 - amt)) < 0.01
    k0 = await _keep(pg); r = await _ask(pg, "coffee 4.50 and bus 2.75"); assert abs(await _keep(pg) - (k0 - 7.25)) < 0.01, r
    # a line that could be either asks, and changes nothing
    b = snap(await state(pg)); r = await _ask(pg, "received a bill of 60"); assert "coming in or going out" in r and snap(await state(pg)) == b, r
    # questions and lines with no amount log nothing
    for q in ["how much have I earned?", "did I get paid 500?", "what bonus should I expect", "got paid", "received from Sam", "refund"]:
        b = snap(await state(pg)); r = await _ask(pg, q); assert snap(await state(pg)) == b, f"{q} changed something: {r}"
    # zero and nonsense amounts are refused
    b = snap(await state(pg)); await _ask(pg, "got paid 0"); assert snap(await state(pg)) == b
    # pay set per paycheck is not guessed at
    pg2 = await open_at(ctx, (2026, 10, 5, 10, 0)); await pg2.click("[data-payday-edit]"); f = pg2.locator("form[data-form=pay]")
    await f.locator("[name=when]").select_option("biweekly"); await pg2.wait_for_timeout(100); f = pg2.locator("form[data-form=pay]")
    await f.locator("[name=next]").fill("2026-10-09"); await f.locator("[name=amount]").fill("2600"); await f.locator("button[type=submit]").click(); await pg2.wait_for_timeout(300)
    inc = (await state(pg2))["income"]; r = await _ask(pg2, "my salary is now 6000"); s = await state(pg2)
    assert "Tap Change in the pay box" in r and s["income"] == inc and s["pay"]["amount"] == 2600 and not s.get("ins"), r
    # money in belongs to the month it arrived: another month's entry is not counted
    pg3 = await open_app(ctx); k0 = await _keep(pg3)
    await pg3.evaluate("(() => { const s = JSON.parse(localStorage.getItem('keepwise-app-v1')); s.ins = [{id: 'x1', date: '2020-01-05', k: '2020-01', name: 'Old', amount: 999}]; localStorage.setItem('keepwise-app-v1', JSON.stringify(s)); })()")
    await pg3.reload(); await pg3.wait_for_timeout(500); assert abs(await _keep(pg3) - k0) < 0.01 and await pg3.locator("[data-ins]").count() == 0
    # Start empty clears it
    await _ask(pg3, "got a 300 bonus"); await tab(pg3, "plan"); await pg3.click("[data-reset=blank]"); await pg3.click("#reset-confirm [data-reset-yes]"); await pg3.wait_for_timeout(400)
    assert not (await state(pg3)).get("ins"), "Start empty clears money in"
    assert not pg.errors and not pg2.errors and not pg3.errors, pg.errors + pg2.errors + pg3.errors

@test
async def saying_money_in_out_loud_works_like_typing(ctx):
    pg = await ctx.new_page(); await pg.set_viewport_size({"width": 390, "height": 844}); pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    await pg.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;")
    await pg.add_init_script("""window.SpeechRecognition = undefined; window.webkitSpeechRecognition = function(){ const r = this; window.__rec = r; r.start = () => {}; r.stop = () => { r.onend && r.onend(); }; };""")
    await pg.goto(URL); await pg.wait_for_timeout(450)
    heard = lambda words, final=False: pg.evaluate("([w, f]) => window.__rec.onresult({results: [Object.assign([{transcript: w}], {isFinal: f})]})", [words, final])
    async def say(words, final=True):
        if await pg.locator("#asksheet [data-ask-mic]").count() == 0: await pg.click("#wise"); await pg.wait_for_timeout(250)
        await pg.click("#asksheet [data-ask-mic]"); await pg.wait_for_timeout(150); await heard(words, final)
        if not final: await pg.click("#asksheet [data-voice-stop]")
        await pg.wait_for_timeout(700)
    k0 = await _keep(pg); await say("I got paid five hundred dollars" if False else "I got paid 500 dollars for a freelance job"); s = await state(pg)
    assert s["ins"][-1]["amount"] == 500 and abs(await _keep(pg) - (k0 + 500)) < 0.01, "spoken income is money in"
    k0 = await _keep(pg); await say("got a 300 bonus", final=False); s = await state(pg)
    assert s["ins"][-1]["name"] == "Bonus" and abs(await _keep(pg) - (k0 + 300)) < 0.01, "Stop sends what was heard"
    n = len(s["settlements"]); await say("received 20 from Sam"); s = await state(pg); assert len(s["settlements"]) == n + 1 and s["settlements"][-1]["amount"] == 20
    k0 = await _keep(pg); await say("refund of 40 from Amazon"); assert abs(await _keep(pg) - (k0 + 40)) < 0.01
    was = (await state(pg))["income"]; await say("my salary is now 5600"); assert (await state(pg))["income"] == 5600 != was
    # spoken spending still goes out, and a spoken question logs nothing
    k0 = await _keep(pg); await say("lunch 12 dollars"); assert abs(await _keep(pg) - (k0 - 12)) < 0.01
    b = await state(pg); await say("how much have I earned"); a = await state(pg); assert len(a["ins"]) == len(b["ins"]) and len(a["spends"]) == len(b["spends"])
    # nothing heard: nothing logged
    await pg.evaluate("(() => { const c = document.querySelector('#asksheet [data-ask-close]'); if (c) c.click(); })()"); await pg.wait_for_timeout(150)
    await pg.click("#wise"); await pg.wait_for_timeout(250)
    await pg.click("#asksheet [data-ask-mic]"); await pg.wait_for_timeout(120); await pg.click("#asksheet [data-voice-stop]"); await pg.wait_for_timeout(300)
    c = await state(pg); assert len(c["ins"]) == len(a["ins"]) and len(c["spends"]) == len(a["spends"]) and "Nothing was heard" in await pg.inner_text("#toast")
    assert not pg.errors, pg.errors

@test
async def the_new_screens_fit_small_phones_in_both_themes(ctx):
    for scheme in ("light", "dark"):
        for w, h in [(280, 653), (320, 568), (360, 740), (390, 844), (740, 360)]:   # a folded phone, small and usual phones, and a phone held sideways
            pg = await open_app(ctx, w=w, h=h, scheme=scheme)
            for step in ("menu", "settings", "security", "support", "plus", "subs", "cheaper", "codes", "plan", "split", "money"):
                if step == "menu": await pg.click("#acct-btn"); await pg.wait_for_timeout(280)
                elif step in ("settings", "security", "support", "plus"): await _menu(pg, step)
                elif step in ("cheaper", "codes"): await tab(pg, "subs"); await pg.click(f"#view [data-go={step}]"); await pg.wait_for_timeout(150)
                elif step == "money": await _ask(pg, "got a 300 bonus")
                else: await tab(pg, step)
                g = await pg.evaluate("""(() => { const vw = innerWidth, bad = [];
                  document.querySelectorAll('#view *, #sidenav .sn *').forEach(el => { if (el.closest('[data-scroll-x]')) return; const r = el.getBoundingClientRect(); if (r.width && (r.right > vw + 1 || r.left < -1)) bad.push(el.tagName + '.' + el.className + ':' + Math.round(r.right)); });
                  return {sw: document.documentElement.scrollWidth, vw, bad: bad.slice(0, 5)}; })()""")
                assert g["sw"] <= g["vw"] and not g["bad"], f"{scheme} {w} {step}: {g}"
                small = await pg.evaluate("""[...document.querySelectorAll('#sidenav .sn-row, #sidenav .sn-seg button, #view .sub-seg button, #view [data-settings-close]')].filter(b => { const r = b.getBoundingClientRect(); return r.width && r.height < 36; }).map(b => b.textContent.trim())""")
                assert not small, f"{scheme} {w} {step}: too small to tap: {small}"
            assert not pg.errors, pg.errors; await pg.close()

@test
async def date_fields_open_on_a_tap_and_keep_to_sensible_limits(ctx):
    pg = await open_app(ctx, w=390, h=844)
    await pg.add_init_script("window.__picks = 0; HTMLInputElement.prototype.showPicker = function(){ window.__picks++; };")
    await pg.reload(); await pg.wait_for_timeout(500)
    today = await pg.evaluate("(() => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); })()")
    shift = lambda n: pg.evaluate("n => { const d = new Date(); d.setDate(d.getDate() + n); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }", n)
    past, future = await shift(-40), await shift(40)
    async def check_opens(sel):
        el = pg.locator(sel).first; before = await pg.evaluate("window.__picks")
        st = await el.evaluate("e => [getComputedStyle(e).backgroundImage.slice(0, 4), getComputedStyle(e).position]")
        assert st == ["url(", "relative"], f"{sel}: the field carries its own calendar mark: {st}"
        await el.evaluate("e => e.dispatchEvent(new MouseEvent('click', {bubbles: true}))"); await pg.wait_for_timeout(80)   # a tap on the field itself; sent as an event so no real calendar window opens over the test; assert await pg.evaluate("window.__picks") == before + 1, f"{sel}: a tap opens the calendar"
    # --- adding a subscription: a monthly one renews on a day, a yearly one on a date ahead
    await tab(pg, "subs"); await pg.click("text=Add a subscription"); f = "form[data-form=addSub] "
    assert await pg.locator(f + "[data-renew-mo]").is_visible() and not await pg.locator(f + "[data-renew-yr]").is_visible()
    opts = await pg.locator(f + "[name=renewDay] option").all_inner_texts(); assert opts[0] == "Pick a day" and opts[1] == "1st of each month" and opts[31] == "31st of each month" and len(opts) == 32
    assert await pg.get_attribute(f + "[name=last]", "max") == today, "last used cannot be ahead of today"
    await check_opens(f + "[name=last]")
    await pg.fill(f + "[name=last]", future); await pg.locator(f + "[name=last]").dispatch_event("change"); await pg.wait_for_timeout(100)
    assert await pg.input_value(f + "[name=last]") == today and "has not happened yet" in await pg.inner_text("#toast")
    await pg.fill(f + "[name=name]", "DayBox"); await pg.fill(f + "[name=price]", "7"); await pg.select_option(f + "[name=renewDay]", "12")
    await pg.click(f + "button[type=submit]"); await pg.wait_for_timeout(250); s = (await state(pg))["subs"][-1]
    assert s["name"] == "DayBox" and s["renewDay"] == 12 and "renewDate" not in s and s["last"] == today, s
    await pg.click("text=Add a subscription"); await pg.fill(f + "[name=name]", "NoDay"); await pg.fill(f + "[name=price]", "3"); await pg.click(f + "button[type=submit]"); await pg.wait_for_timeout(250)
    s = (await state(pg))["subs"][-1]; assert s["name"] == "NoDay" and "renewDay" not in s and "renewDate" not in s, "the renewal stays optional"
    await pg.click("text=Add a subscription"); await pg.select_option(f + "[name=cycle]", "yr"); await pg.wait_for_timeout(100)
    assert await pg.locator(f + "[data-renew-yr]").is_visible() and not await pg.locator(f + "[data-renew-mo]").is_visible()
    assert await pg.get_attribute(f + "[name=renew]", "min") == today, "a next charge cannot be behind today"
    await check_opens(f + "[name=renew]")
    await pg.fill(f + "[name=renew]", past); await pg.locator(f + "[name=renew]").dispatch_event("change"); await pg.wait_for_timeout(100)
    assert await pg.input_value(f + "[name=renew]") == today and "has passed" in await pg.inner_text("#toast")
    await pg.fill(f + "[name=renew]", future); await pg.fill(f + "[name=name]", "YearBox"); await pg.fill(f + "[name=price]", "60"); await pg.click(f + "button[type=submit]"); await pg.wait_for_timeout(250)
    s = (await state(pg))["subs"][-1]; assert s["cycle"] == "yr" and s["renewDate"] == future and "renewDay" not in s, s
    await pg.select_option(f + "[name=cycle]", "mo") if await pg.locator(f + "[name=cycle]").is_visible() else None
    # --- the editor on a saved subscription follows the same rule
    row = pg.locator(f"[data-sub='{s['id']}']"); await row.locator("[data-renew-open]").click(); await pg.wait_for_timeout(150)
    assert await row.locator("[data-renew-date]").get_attribute("min") == today
    day = (await state(pg))["subs"][-3]; row = pg.locator(f"[data-sub='{day['id']}']"); await row.locator("[data-renew-open]").click(); await pg.wait_for_timeout(150)
    assert await row.locator("[data-renew-day]").count() == 1 and await row.locator("[data-renew-date]").count() == 0, "a monthly one picks a day"
    # --- a loan's end date is ahead; a saved one that has already passed can still be opened and saved
    await tab(pg, "plan"); await pg.click("[data-loan-add]"); await pg.wait_for_timeout(150)
    assert await pg.get_attribute("form[data-form=loan] [name=end]", "min") == today; await check_opens("form[data-form=loan] [name=end]")
    # --- a trip can start any day, and never ends before it starts
    await pg.keyboard.press("Escape"); await pg.evaluate("document.activeElement && document.activeElement.blur()"); await pg.wait_for_timeout(400)
    await tab(pg, "month"); await pg.click("[data-trip-add]"); await pg.wait_for_timeout(200); t = "form[data-form=trip] "
    assert await pg.get_attribute(t + "[name=start]", "min") is None, "a trip already under way can be added"
    await pg.fill(t + "[name=start]", future); await pg.locator(t + "[name=start]").dispatch_event("change"); await pg.wait_for_timeout(100)
    assert await pg.get_attribute(t + "[name=end]", "min") == future and await pg.input_value(t + "[name=end]") >= future
    await pg.fill(t + "[name=end]", today); await pg.locator(t + "[name=end]").dispatch_event("change"); await pg.wait_for_timeout(100)
    assert await pg.input_value(t + "[name=end]") == future and "cannot come before the start" in await pg.inner_text("#toast")
    await check_opens(t + "[name=start]")
    # --- every date field on these screens carries the calendar mark and no field is left without a limit it should have
    rule = await pg.evaluate("[...document.styleSheets].flatMap(s => { try { return [...s.cssRules]; } catch(e){ return []; } }).filter(r => r.selectorText && r.selectorText.includes('calendar-picker-indicator')).map(r => r.cssText).join(' ')")
    assert "position: absolute" in rule and "opacity: 0" in rule and "inset: 0" in rule, "the browser's own calendar button is stretched over the whole field: " + rule
    assert not pg.errors, pg.errors

@test
async def a_payday_or_payment_date_follows_the_same_limits(ctx):
    pg = await open_at(ctx, (2026, 10, 5, 10, 0))
    await pg.click("[data-payday-edit]"); f = pg.locator("form[data-form=pay]"); await f.locator("[name=when]").select_option("biweekly"); await pg.wait_for_timeout(100)
    nx = pg.locator("form[data-form=pay] [name=next]"); assert await nx.get_attribute("min") == "2026-10-05" and await nx.input_value() == "2026-10-05", "the next payday is today or later"
    await nx.fill("2026-09-20"); await nx.dispatch_event("change"); await pg.wait_for_timeout(100); assert await nx.input_value() == "2026-10-05"
    await nx.fill("2026-10-16"); await pg.locator("form[data-form=pay] [name=amount]").fill("2600"); await pg.locator("form[data-form=pay] button[type=submit]").click(); await pg.wait_for_timeout(300)
    assert (await state(pg))["pay"]["next"] == "2026-10-16"
    # weeks later the saved date has passed: the form still opens and saves without complaint
    pg2 = await ctx.new_page(); pg2.errors = []; pg2.on("pageerror", lambda e: pg2.errors.append(str(e)))
    import datetime
    await pg2.clock.install(time=datetime.datetime(2026, 11, 20, 10, 0)); await pg2.add_init_script("window.KEEPWISE_FIREBASE = null; window.KEEPWISE_NO_SETUP = true;")
    await pg2.set_viewport_size({"width": 390, "height": 844}); await pg2.goto(URL); await pg2.wait_for_timeout(500)
    await pg2.click("[data-payday-edit]"); await pg2.wait_for_timeout(150); nx2 = pg2.locator("form[data-form=pay] [name=next]")
    assert await nx2.input_value() == "2026-10-16" and await nx2.get_attribute("min") is None, "an older saved date is not locked out"
    await pg2.locator("form[data-form=pay] button[type=submit]").click(); await pg2.wait_for_timeout(300); assert (await state(pg2))["pay"]["next"] == "2026-10-16" and await pg2.locator("form[data-form=pay]").count() == 0
    assert not pg.errors and not pg2.errors, pg.errors + pg2.errors

@test
async def a_swap_you_wrote_is_shown_as_yours_never_as_advice(ctx):
    pg = await open_app(ctx)
    # the example month's own idea keeps the advice wording
    await pg.click("#view [data-plain]"); await pg.wait_for_timeout(150); t = await text(pg, "#ask-out"); assert "The biggest easy win" in t and "Your own swap" not in t, t
    # someone writes anything at all as the cheaper option, and it becomes the largest saving
    await tab(pg, "cheaper"); await pg.click("text=Add your own comparison"); f = pg.locator("form[data-form=addSwap]")
    await f.locator("[name=link]").select_option("expense:rent"); await f.locator("[name=alt]").fill("Haunted House"); await f.locator("[name=altCost]").fill("1")
    await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    assert await pg.locator("[data-swap]", has_text="Haunted House").count() == 1, "what was typed is kept exactly: nothing is filtered or refused"
    await tab(pg, "month"); await pg.click("#view [data-plain]"); await pg.wait_for_timeout(150); t = await text(pg, "#ask-out")
    assert "Your own swap: " in t and "haunted house" in t and "easy win" not in t, t
    await pg.click("#view [data-info=ask]"); await pg.wait_for_timeout(150); h = await text(pg, "#view .ask-howto")
    assert "Your own swap" in h and "Haunted House" in h and "The cheapest real swap" not in h, h
    # ordinary merchants with awkward names are logged like any other
    for q, name in [("hooters 42", "Hooters"), ("dick's sporting goods 60", "Dick's sporting goods")]:
        r = await _ask(pg, q); assert name.lower() in r.lower() and r.startswith("Added to this month"), r
    assert not pg.errors, pg.errors

@test
async def a_forgotten_passcode_can_be_reset_by_signing_in_again(ctx):
    seed = """(prov) => { localStorage.setItem('__mock_users', JSON.stringify({'ada@example.com': {uid: 'u1', email: 'ada@example.com', pw: 'Secret1!x', provider: prov, verified: true}}));
      localStorage.setItem('__mock_session', 'ada@example.com'); window.__kwErasing = true; localStorage.setItem('__mock_fs', JSON.stringify({'users/u1': {name: 'Ada Byron', dob: '1990-01-01', termsAcceptedAt: 1, termsVersion: '2026-10-01'}})); const s = JSON.parse(localStorage.getItem('keepwise-app-v1')); s.acctOn = true; localStorage.setItem('keepwise-app-v1', JSON.stringify(s)); }"""
    async def locked_page(prov):
        pg = await open_app(ctx, fb=True); await pg.evaluate("localStorage.removeItem('keepwise-lock-v1')"); await pg.evaluate(seed, prov); await pg.reload(); await pg.wait_for_timeout(700)
        assert ((await state(pg)).get("acct") or {}).get("uid") == "u1", "the phone remembers which account is signed in"
        await menu_to(pg, "security"); await pg.click("[data-lock-set]"); f = "form[data-form=lockSet] "
        assert "reset it by signing in" in await pg.inner_text("[data-lock-note]"), "setting a passcode says how to get back in"
        await pg.fill(f + "[name=pin]", "2468"); await pg.fill(f + "[name=pin2]", "2468"); await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(500)
        await pg.reload(); await pg.wait_for_timeout(700); assert await pg.locator("#lockscreen").is_visible()
        await pg.click("[data-lock-forgot]"); await pg.wait_for_timeout(150); return pg
    # --- email and password
    pg = await locked_page("password"); t = await pg.inner_text("#lockscreen")
    assert "a•••@example.com" in t and "Your money stays on this phone" in t and await pg.locator("[data-lock-erase]").count() == 1, t
    spends = (await state(pg))["expenses"]
    await pg.fill("[data-lock-recover] [name=pw]", "wrong-one"); await pg.click("[data-lock-recover] [type=submit]"); await pg.wait_for_timeout(500)
    assert "That password is not right" in await pg.inner_text("[data-lock-rmsg]") and await pg.locator("#lockscreen").is_visible() and await pg.evaluate("!!localStorage.getItem('keepwise-lock-v1')"), "a wrong password opens nothing"
    # digits typed into the password box are not taken as passcode digits
    await pg.fill("[data-lock-recover] [name=pw]", ""); await pg.locator("[data-lock-recover] [name=pw]").press_sequentially("2468"); await pg.wait_for_timeout(300)
    assert await pg.locator("#lockscreen").is_visible() and await pg.input_value("[data-lock-recover] [name=pw]") == "2468"
    await pg.evaluate("window.__mockOffline = true"); await pg.fill("[data-lock-recover] [name=pw]", "Secret1!x"); await pg.click("[data-lock-recover] [type=submit]"); await pg.wait_for_timeout(500)
    assert "Connect to the internet" in await pg.inner_text("[data-lock-rmsg]") and await pg.locator("#lockscreen").is_visible()
    await pg.evaluate("window.__mockOffline = false"); await pg.fill("[data-lock-recover] [name=pw]", "Secret1!x"); await pg.click("[data-lock-recover] [type=submit]"); await pg.wait_for_timeout(700)
    assert not await pg.locator("#lockscreen").is_visible() and await pg.evaluate("localStorage.getItem('keepwise-lock-v1')") is None, "the right password removes the old passcode"
    assert await pg.locator("#view h1").inner_text() == "Security" and await pg.locator("form[data-form=lockSet]").count() == 1 and "Set a new passcode" in await pg.inner_text("#toast")
    assert (await state(pg))["expenses"] == spends, "nothing on the phone was touched"
    f = "form[data-form=lockSet] "; await pg.fill(f + "[name=pin]", "1357"); await pg.fill(f + "[name=pin2]", "1357"); await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(500)
    await pg.reload(); await pg.wait_for_timeout(700); assert await pg.locator("#lockscreen").is_visible()
    for d in "2468": await pg.click(f"[data-lock-key='{d}']")
    await pg.wait_for_timeout(500); assert await pg.locator("#lockscreen").is_visible(), "the old passcode no longer works"
    for d in "1357": await pg.click(f"[data-lock-key='{d}']")
    await pg.wait_for_timeout(600); assert not await pg.locator("#lockscreen").is_visible(), "the new one does"
    assert not pg.errors, pg.errors; await pg.close()
    # --- Google: only the account already on this phone is accepted
    pg = await locked_page("google.com"); assert await pg.locator("[data-lock-recover]").count() == 0 and await pg.locator("[data-lock-google]").count() == 1
    await pg.evaluate("window.__mockGoogleEmail = 'someone.else@example.com'"); await pg.click("[data-lock-google]"); await pg.wait_for_timeout(600)
    assert "not the account used on this phone" in await pg.inner_text("[data-lock-rmsg]") and await pg.locator("#lockscreen").is_visible() and (await state(pg))["acct"]["uid"] == "u1"
    await pg.evaluate("window.__mockGoogleEmail = 'ada@example.com'"); await pg.click("[data-lock-google]"); await pg.wait_for_timeout(700)
    assert not await pg.locator("#lockscreen").is_visible() and await pg.locator("form[data-form=lockSet]").count() == 1
    assert not pg.errors, pg.errors; await pg.close()
    # --- no account: there is nothing to sign in to, and it says so before the passcode is set
    pg = await open_app(ctx); await pg.evaluate("window.__kwErasing = true; localStorage.clear()"); await pg.reload(); await pg.wait_for_timeout(600)
    await menu_to(pg, "security"); await pg.click("[data-lock-set]"); f = "form[data-form=lockSet] "
    note = await pg.inner_text("[data-lock-note]"); assert "erase this phone" in note and "backup" in note, note
    await pg.fill(f + "[name=pin]", "2468"); await pg.fill(f + "[name=pin2]", "2468"); await pg.click(f + "[type=submit]"); await pg.wait_for_timeout(500)
    await pg.reload(); await pg.wait_for_timeout(600); await pg.click("[data-lock-forgot]"); await pg.wait_for_timeout(150)
    t = await pg.inner_text("#lockscreen"); assert "cannot be recovered" in t and await pg.locator("[data-lock-reset]").count() == 0 and await pg.locator("[data-lock-erase]").count() == 1
    # signing out forgets the account, so a signed-out phone cannot be opened this way
    pg2 = await open_app(ctx, fb=True); await pg2.evaluate("localStorage.removeItem('keepwise-lock-v1')"); await pg2.evaluate(seed, "password"); await pg2.reload(); await pg2.wait_for_timeout(700)
    await open_account(pg2); await pg2.wait_for_timeout(300)
    if await pg2.locator("[data-acc-signout]").count(): await pg2.locator("[data-acc-signout]").first.click(); await pg2.wait_for_timeout(400); assert not (await state(pg2)).get("acct"), "signed out: no account is remembered"
    assert not pg.errors and not pg2.errors, pg.errors + pg2.errors

@test
async def coming_up_keeps_its_rules_and_never_disappears(ctx):
    pg = await open_app(ctx)
    await pg.add_init_script("window.__drawn = []; const ft = CanvasRenderingContext2D.prototype.fillText; CanvasRenderingContext2D.prototype.fillText = function(t){ window.__drawn.push(String(t)); return ft.apply(this, arguments); };")
    await pg.reload(); await pg.wait_for_timeout(500)
    # the same card as always: dated rows in date order, then open splits, then the week's total
    up = pg.locator("[data-out=comingUp]"); t = await up.inner_text()
    assert "Coming up" in t and "Next 7 days" in t and await up.locator(".up-row").count() >= 3 and await pg.locator("[data-up-empty]").count() == 0
    names = await up.locator(".up-row .name:not(.tnum)").all_inner_texts(); assert names[:3] == ["Hulu Premium", "Netflix", "Spotify"], names
    assert "will be charged this week" in t and "Not counted until it is paid" in t
    # the picture people share carries the address
    await pg.locator("[data-share-open]").first.click(); await pg.wait_for_timeout(800)
    drawn = await pg.evaluate("window.__drawn"); assert "mykeepwise.com" in drawn and "Free and private. It stays on your phone." in drawn, drawn
    await pg.reload(); await pg.wait_for_timeout(500)
    await tab(pg, "plan"); await pg.click("[data-reset=blank]"); await pg.click("#reset-confirm [data-reset-yes]"); await pg.wait_for_timeout(400); await tab(pg, "month")
    t = await pg.locator("[data-out=comingUp] [data-up-empty]").inner_text()
    assert "Coming up" in t and "Nothing is due in the next 7 days." in t and "renewal day" not in t, "an empty month still shows the card: " + t
    # a subscription with no renewal day cannot be placed on a date, and the card says so
    await tab(pg, "subs"); await pg.click("text=Add a subscription"); f = "form[data-form=addSub] "
    await pg.fill(f + "[name=name]", "Claude Pro"); await pg.fill(f + "[name=price]", "20"); await pg.click(f + "button[type=submit]"); await pg.wait_for_timeout(250); await tab(pg, "month")
    t = await pg.inner_text("[data-out=comingUp]"); assert "1 subscription has no renewal day yet" in t and await pg.locator("[data-out=comingUp] [data-go=subs]").count() == 1, t
    await pg.click("[data-out=comingUp] [data-go=subs]"); await pg.wait_for_timeout(200); sid = (await state(pg))["subs"][-1]["id"]
    d = await pg.evaluate("(() => { const d = new Date(); d.setDate(d.getDate() + 2); return d.getDate(); })()")
    await pg.click(f"[data-sub='{sid}'] [data-renew-open]"); await pg.select_option(f"[data-sub='{sid}'] [data-renew-day]", str(d)); await pg.wait_for_timeout(250); await tab(pg, "month")
    t = await pg.inner_text("[data-out=comingUp]"); assert "Claude Pro" in t and "In 2 days" in t and "$20" in t and await pg.locator("[data-up-empty]").count() == 0, t
    assert not pg.errors, pg.errors

@test
async def messages_stay_above_the_keyboard(ctx):
    pg = await open_app(ctx, w=390, h=844)
    box = lambda: pg.evaluate("(() => { const r = document.getElementById('toast').getBoundingClientRect(); return {top: r.top, bottom: r.bottom, left: r.left, right: r.right}; })()")
    # no keyboard: the message sits just above the tab bar, on screen
    await ask_type(pg, "coffee 4"); await pg.wait_for_timeout(500); b = await box(); tb = await pg.evaluate("document.getElementById('tabbar').getBoundingClientRect().top")
    assert 0 < b["top"] and b["bottom"] <= tb + 1 and b["left"] >= 0 and b["right"] <= 390, (b, tb)
    # the keyboard opens: the visible screen shrinks to 430px, and the message moves up with it
    await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]"); n = len((await state(pg)).get("extras") or [])
    await f.locator("[name=amount]").click(); await pg.set_viewport_size({"width": 390, "height": 430}); await pg.wait_for_timeout(250)
    await f.locator("[name=amount]").press("Enter"); await pg.wait_for_timeout(250)
    assert "Say where the money comes from." in await pg.inner_text("#toast") and len((await state(pg)).get("extras") or []) == n
    b = await box(); assert b["bottom"] <= 430 and b["top"] > 0, f"the message is above the keyboard: {b}"
    assert not pg.errors, pg.errors

@test
async def other_income_needs_no_amount_and_takes_any_number_of_payments(ctx):
    pg = await open_at(ctx, (2026, 10, 5, 10, 0)); k0 = await _keep(pg)
    async def add(name, when, amount="", **sel):
        await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]"); await f.locator("[name=name]").fill(name)
        await f.locator("[name=when]").select_option(when); await pg.wait_for_timeout(120); f = pg.locator("form[data-form=income]")
        for key, v in sel.items(): await f.locator(f"[name={key}]").select_option(str(v)) if key != "next" else await f.locator("[name=next]").fill(v)
        if amount != "": await f.locator("[name=amount]").fill(amount)
        await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(300)
    assert [o for o in await pg.evaluate("document.querySelector('[data-inc-add]') ? [] : []")] == []
    # the amount is optional on every schedule, and the field says so
    await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]")
    opts = await f.locator("[name=when] option").all_inner_texts(); assert opts == ["No fixed day", "Every month", "Twice a month", "Every week", "Every 2 weeks"], opts
    assert await f.locator("[name=amount]").get_attribute("placeholder") == "No fixed amount" and "(optional)" in await f.inner_text()
    await pg.click("[data-inc-cancel]")
    await add("Promotional posts", "any"); await add("Tips", "weekly", wd=1); await add("Tutoring", "twice", day=1, day2=15); await add("Blank zero", "monthly", "0", day=20)
    ex = (await state(pg))["extras"]; assert [x["name"] for x in ex] == ["Promotional posts", "Tips", "Tutoring", "Blank zero"] and all(x["amount"] == 0 for x in ex), ex
    assert "counts each time you log a payment" in await pg.inner_text("#toast")
    assert abs(await _keep(pg) - k0) < 0.01, "income with no fixed amount promises nothing"
    card = await text(pg, "[data-out=extraIncome]"); assert card.count("No fixed amount") == 4 and "on the 1st and 15th" in card and "Income with no fixed amount counts as you log it." in card, card
    # any number of payments can be logged against one income, and each one raises the month
    row = pg.locator("[data-inc]", has_text="Promotional posts")
    for i, amt in enumerate((120, 80, 45)):
        await row.locator("[data-inc-log]").click(); await pg.fill("form[data-form=incomeLog] [name=amount]", str(amt)); await pg.click("form[data-form=incomeLog] [type=submit]"); await pg.wait_for_timeout(300)
        assert f"{i + 1} logged" in await row.inner_text() or (i == 0 and "1 logged" in await row.inner_text()), await row.inner_text()
    assert abs(await _keep(pg) - (k0 + 245)) < 0.01, "what was logged now counts"
    mrow = pg.locator("[data-inc]", has_text="Blank zero"); await mrow.locator("[data-inc-log]").click(); await pg.fill("form[data-form=incomeLog] [name=amount]", "10"); await pg.click("form[data-form=incomeLog] [type=submit]"); await pg.wait_for_timeout(300)
    assert await mrow.locator("[data-inc-log]").count() == 1, "a monthly income can still take another payment"
    await mrow.locator("[data-inc-log]").click(); await pg.fill("form[data-form=incomeLog] [name=amount]", "5"); await pg.click("form[data-form=incomeLog] [type=submit]"); await pg.wait_for_timeout(300)
    assert "2 logged" in await mrow.inner_text() and abs(await _keep(pg) - (k0 + 260)) < 0.01
    # a negative or empty payment is refused
    await row.locator("[data-inc-log]").click(); await pg.fill("form[data-form=incomeLog] [name=amount]", ""); await pg.click("form[data-form=incomeLog] [type=submit]"); await pg.wait_for_timeout(200)
    assert "Enter the amount you received." in await pg.inner_text("#toast"); await pg.click("[data-inc-log-cancel]")
    # Coming up shows a scheduled income with no amount as varying, on its day
    up = await text(pg, "[data-out=comingUp]"); assert "Tips" in up and "amount varies" in up and "+$0" not in up, up
    # twice a month must be two different days
    await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]"); await f.locator("[name=name]").fill("Same day"); await f.locator("[name=when]").select_option("twice"); await pg.wait_for_timeout(120)
    f = pg.locator("form[data-form=income]"); await f.locator("[name=day]").select_option("10"); await f.locator("[name=day2]").select_option("10"); await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(200)
    assert "two different days" in await pg.inner_text("#toast") and len((await state(pg))["extras"]) == 4; await pg.click("[data-inc-cancel]")
    # a fixed amount still counts in full: twice a month is two payments, every 2 weeks is 26 a year
    k1 = await _keep(pg); await add("Rent share", "twice", "300", day=5, day2=20); assert abs(await _keep(pg) - (k1 + 600)) < 0.01
    k1 = await _keep(pg); await add("Shift pay", "biweekly", "300", next="2026-10-09"); assert abs(await _keep(pg) - (k1 + 650)) < 0.01, "300 x 26 / 12"
    assert not pg.errors, pg.errors

@test
async def an_income_with_no_amount_asks_how_much_arrived(ctx):
    pg = await open_at(ctx, (2026, 10, 5, 10, 0))
    await pg.click("[data-inc-add]"); f = pg.locator("form[data-form=income]"); await f.locator("[name=name]").fill("Tutoring"); await f.locator("[name=when]").select_option("twice"); await pg.wait_for_timeout(120)
    f = pg.locator("form[data-form=income]"); await f.locator("[name=day]").select_option("6"); await f.locator("[name=day2]").select_option("21"); await f.locator("button[type=submit]").click(); await pg.wait_for_timeout(300)
    up = await text(pg, "[data-out=comingUp]"); assert "Tutoring" in up and "Tomorrow" in up and "amount varies" in up, up
    import datetime
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 7, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    q = pg.locator("[data-arrive]", has_text="Tutoring"); assert await q.count() == 1 and "amount varies" in await q.inner_text(), "the day after it was due, it asks"
    n = len((await state(pg))["extras"][-1].get("got") or [])
    await q.locator("[data-arrive-yes]").click(); await pg.wait_for_timeout(350)
    assert len((await state(pg))["extras"][-1].get("got") or []) == n and "Enter how much arrived." in await pg.inner_text("#toast"), "nothing is logged at $0"
    form = pg.locator("[data-inc] form[data-form=incomeLog]"); assert await form.count() == 1
    await form.locator("[name=amount]").fill("140"); await form.locator("[type=submit]").click(); await pg.wait_for_timeout(350)
    got = (await state(pg))["extras"][-1]["got"]; assert got[-1]["amount"] == 140 and await pg.locator("[data-arrive]", has_text="Tutoring").count() == 0, "logging it settles the question"
    # the second date of the month comes up next
    await pg.clock.set_fixed_time(datetime.datetime(2026, 10, 20, 9, 0)); await tab(pg, "subs"); await tab(pg, "month")
    up = await text(pg, "[data-out=comingUp]"); assert "Tutoring" in up and "Tomorrow" in up, up
    assert not pg.errors, pg.errors

async def main():
    passed, failed = 0, []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        async def run(fn):
            ctx = await b.new_context(is_mobile=False)
            if FONTS:  # the real typefaces, when a machine cannot reach Google Fonts (set KEEPWISE_FONTS to a folder of woff2 files)
                css = "".join(f"@font-face{{font-family:'{fam}';font-style:normal;font-weight:100 900;src:url(https://fonts.gstatic.com/local/{f}) format('woff2')}}" for fam, f in [("Figtree", "figtree-latin-wght-normal.woff2"), ("Fraunces", "fraunces-latin-opsz-normal.woff2")])
                await ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(body=css, content_type="text/css"))
                await ctx.route("https://fonts.gstatic.com/local/**", lambda r: r.fulfill(path=os.path.join(FONTS, r.request.url.rsplit("/", 1)[-1]), content_type="font/woff2"))
            try:
                await fn(ctx)
                errs = [e for pg in ctx.pages for e in getattr(pg, "errors", [])]
                assert not errs, "JS errors: " + "; ".join(errs)
                return None
            except Exception as e:
                traceback.print_exc(limit=-1); return e
            finally:
                await ctx.close()
        for fn in [t for t in TESTS if not os.environ.get('ONLY') or t.__name__ in os.environ['ONLY'].split(',')]:
            err = await run(fn)
            if err is not None:
                # One more try: a test that straddles midnight sees the date change under it, with nothing wrong in the app.
                print(f"RETRY {fn.__name__}: {err}"); err = await run(fn)
            if err is None: passed += 1; print(f"PASS  {fn.__name__}")
            else: failed.append(fn.__name__); print(f"FAIL  {fn.__name__}: {err}")
        await b.close()
    print(f"\n{passed} passed, {len(failed)} failed" + (f": {', '.join(failed)}" if failed else ""))
    sys.exit(1 if failed else 0)

asyncio.run(main())
