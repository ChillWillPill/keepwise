"""Opens every add / edit / new sheet on every tab at small and normal phone sizes and checks that its buttons can be
seen and pressed: nothing on top of them (like the tab bar), none past the bottom unless the sheet scrolls to them,
and no switch whose labels wrap onto two lines. Run: python3 tests/sheets.py www/index.html"""
import os, sys, asyncio
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "test_app.py")).read()
sys.argv = [sys.argv[0], sys.argv[1] if len(sys.argv) > 1 else "www/index.html"]
exec(compile(src[:src.index("async def main(")], "test_app.py", "exec"))
CHECK = r"""() => { const out = [], H = innerHeight, W = innerWidth;
  const mods = [...document.querySelectorAll('[aria-modal="true"], .kw-modal, .cf-back, #io-sheet, #mfa-ask, #pay-oops')].filter(m => { const r = m.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  for (const m of mods){ for (const b of m.querySelectorAll('button, [type=submit], a.btn')){ const r = b.getBoundingClientRect(); if (r.width < 2 || r.height < 2 || getComputedStyle(b).visibility === 'hidden') continue;
      const nm = (b.getAttribute('aria-label') || b.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 30);
      if (r.top >= 0 && r.bottom <= H){ const t = document.elementFromPoint(Math.min(W - 1, r.left + r.width / 2), r.top + r.height / 2); if (t && !b.contains(t) && !t.contains(b) && !m.contains(t)) out.push(['covered', nm + ' by ' + (t.className || t.tagName).toString().slice(0, 30)]); }
      else if (r.bottom > H){ let sc = false; for (let p = b.parentElement; p && p !== document.body; p = p.parentElement){ const s = getComputedStyle(p); if (/(auto|scroll)/.test(s.overflowY) && p.scrollHeight > p.clientHeight + 2) { sc = true; break; } } if (!sc) out.push(['off screen', nm]); } } }
  for (const b of document.querySelectorAll('.seg button, [role=group] > button')){ const r = b.getBoundingClientRect(), s = getComputedStyle(b); if (r.width < 2) continue; const lh = parseFloat(s.lineHeight) || parseFloat(s.fontSize) * 1.25;
    if (b.scrollHeight > lh * 1.9 + parseFloat(s.paddingTop) + parseFloat(s.paddingBottom)) out.push(['switch wraps', (b.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 30)]);
    if (r.right > W + 1) out.push(['switch off screen', (b.innerText || '').trim().slice(0, 30)]); }
  return out; }"""
OPEN = r"""() => [...document.querySelectorAll('#view button, #view [role=button]')].filter(b => { const r = b.getBoundingClientRect(); return r.width > 0 && [...b.attributes].some(a => /^data-.*(add|edit|new|open|change|set)/.test(a.name) && !/data-(env-open|io-open|mseg|tab|kws)/.test(a.name)); }).map(b => [...b.attributes].filter(a => a.name.startsWith('data-')).map(a => a.value ? `[${a.name}="${CSS.escape(a.value)}"]` : `[${a.name}]`).join(''))"""
TABS = [("month", "now"), ("month", "budget"), ("month", "more"), ("subs", None), ("banks", None), ("split", None)]
async def go():
    issues = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for w, h in ((320, 640), (390, 844)):
            ctx = await b.new_context(device_scale_factor=1)
            for t, seg in TABS:
                async def at(pg):
                    if t == "banks": await pg.click("[data-tab=banks]")
                    else: await tab(pg, t)
                    if seg: await pg.click(f"#view [data-mseg={seg}]")
                    await pg.wait_for_timeout(250)
                pg = await open_app(ctx, w=w, h=h); await at(pg)
                for x in await pg.evaluate(CHECK): issues.setdefault((x[0], x[1]), set()).add(f"{w}px {t}/{seg or ''}")
                sels = list(dict.fromkeys(await pg.evaluate(OPEN)))[:40]; await pg.close()
                for sel in sels:
                    pg = await open_app(ctx, w=w, h=h); await at(pg)
                    try:
                        el = pg.locator(sel).first; await el.scroll_into_view_if_needed(timeout=2000); await el.click(timeout=2000); await pg.wait_for_timeout(350)
                        for x in await pg.evaluate(CHECK): issues.setdefault((x[0], x[1]), set()).add(f"{w}px {t}/{seg or ''} {sel[:40]}")
                    except Exception: pass
                    await pg.close()
            await ctx.close()
        await b.close()
    print(f"{len(issues)} problems")
    for (k, n), where in issues.items(): print(k, "|", n, "|", sorted(where)[0], f"(+{len(where) - 1})" if len(where) > 1 else "")
asyncio.run(go())
