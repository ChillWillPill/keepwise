"""Full-page screenshots of every screen and key state, for a by-eye review."""
import asyncio, os, sys
sys.argv = [sys.argv[0], sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "www", "index.html")] + sys.argv[2:]
OUTDIR = os.environ.get("SHOTS", "/tmp/shots"); os.makedirs(OUTDIR, exist_ok=True)
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "explore.py")).read().split("async def main():")[0])

async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for w, h, scheme in [(390, 844, "light"), (390, 844, "dark"), (320, 568, "light"), (1280, 800, "light")]:
            ctx = await b.new_context(device_scale_factor=1)
            pg = await new_page(ctx, w, h, scheme)
            tag = f"{w}{scheme[0]}"
            async def shot(name):
                await pg.wait_for_timeout(250)
                full = await pg.evaluate("Math.max(document.documentElement.scrollHeight, ...[...document.querySelectorAll('main,#view,.scroll')].map(e=>e.scrollHeight+200))")
                await pg.set_viewport_size({"width": w, "height": min(int(full), 6000)}); await pg.wait_for_timeout(200)
                await pg.screenshot(path=f"{OUTDIR}/{tag}-{name}.png")
                await pg.set_viewport_size({"width": w, "height": h})
            for s in ["month", "subs", "cheaper", "codes", "plan", "split"]:
                await goto_screen(pg, s); await shot(s)
            if w == 390 and scheme == "light":
                await goto_screen(pg, "month")
                await pg.click("[data-space=business]"); await shot("month-business"); await pg.click("[data-space=personal]")
                await goto_screen(pg, "split")
                await pg.click("[data-new-split]"); await shot("split-new")
                await pg.click("[data-part-search]"); await pg.keyboard.type("a"); await shot("split-new-search")
                await pg.keyboard.press("Escape"); await pg.click("[data-cancel-split]")
                await pg.locator("[data-edit-split]").nth(2).click(); await shot("split-edit")
                await pg.click("[data-cancel-split]")
                await pg.click("[data-moments]"); await shot("moments"); await pg.click("[data-moments-close]")
                await goto_screen(pg, "account"); await shot("account")
                if await pg.locator("#bell").is_visible(): await goto_screen(pg, "inbox"); await shot("inbox")
                await goto_screen(pg, "month")
                async with pg.expect_file_chooser() as fc: await pg.click("[data-import-open]")
                await (await fc.value).set_files(CSV); await pg.wait_for_timeout(700); await shot("import-review")
            await ctx.close()
        await b.close()
asyncio.run(run())
