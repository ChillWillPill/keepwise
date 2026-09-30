"""Keepwise end-to-end test suite (Playwright, Chromium).
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

async def open_app(ctx, mock=False, w=390, h=844, scheme="light"):
    pg = await ctx.new_page()
    await pg.set_viewport_size({"width": w, "height": h})
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append("pageerror: " + str(e)))
    pg.on("console", lambda m: m.type == "error" and "ERR_TUNNEL" not in m.text and "fonts.g" not in m.text and "net::" not in m.text and pg.errors.append("console: " + m.text))
    if mock: await pg.add_init_script(path=MOCK)
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
            for p in parts: await pg.check(f"[data-part={p}]"); await pg.wait_for_timeout(40)
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
    await pg.fill("form[data-form=addPerson] [name=name]", "Zoe"); await pg.click("form[data-form=addPerson] button"); await pg.wait_for_timeout(100)
    assert any(p["name"] == "Zoe" for p in (await state(pg))["people"])
    await pg.locator("[data-person]").filter(has=pg.locator("input[value=Alex]")).locator("[data-del-person]").click()
    assert "is in a split" in await pg.inner_text("#toast")
    await pg.locator("[data-person]").filter(has=pg.locator("input[value=Zoe]")).locator("[data-del-person]").click(); await pg.wait_for_timeout(100)
    assert not any(p["name"] == "Zoe" for p in (await state(pg))["people"])
    vcf = os.path.join(TMP, "c.vcf")
    open(vcf, "w").write("BEGIN:VCARD\nVERSION:3.0\nFN:Omar Khan\nEND:VCARD\nBEGIN:VCARD\nFN:Alex\nEND:VCARD\n")
    await pg.set_input_files("#vcf", vcf); await pg.wait_for_timeout(200)
    names = [p["name"] for p in (await state(pg))["people"]]
    assert "Omar Khan" in names and names.count("Alex") == 1, names

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
    await pg.check("[data-part=u_sam]"); await pg.click("form[data-form=split] button[type=submit]"); await pg.wait_for_timeout(250)
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
        for fn in TESTS:
            ctx = await b.new_context(is_mobile=False)
            try:
                await fn(ctx)
                errs = [e for pg in ctx.pages for e in getattr(pg, "errors", [])]
                assert not errs, "JS errors: " + "; ".join(errs)
                passed += 1; print(f"PASS  {fn.__name__}")
            except Exception as e:
                failed.append(fn.__name__); print(f"FAIL  {fn.__name__}: {e}")
                traceback.print_exc(limit=1)
            await ctx.close()
        await b.close()
    print(f"\n{passed} passed, {len(failed)} failed" + (f": {', '.join(failed)}" if failed else ""))
    sys.exit(1 if failed else 0)

asyncio.run(main())
