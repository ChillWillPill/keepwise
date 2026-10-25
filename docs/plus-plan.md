# KeepWise Plus: pricing and launch plan (agreed 18 Oct 2026)

- Free keeps everything in the new design (budget, bills, loans, cards, car insurance, trips, flights, checklist, subs, statements, splits, owl, app lock). "Everything free stays free."
- Plus = only what costs money to run: bank connect + Since last time (US, Plaid), Cheaper real prices (US first), split emails, Business space, sync across devices, live flight status (if an AeroDataBox key is added).
- Country-based, tier-based pricing, shown in local currency (country picker, else currency):
  - Tier 1 (US): $9.99/mo, $79/yr, 7-14 day free trial
  - Tier 2 (Canada, UK, EU, Australia, NZ, Gulf, Singapore, Japan): about $6.99/mo, $59/yr
  - Tier 3 (Mexico, Brazil, Turkey, Malaysia, South Africa, Eastern Europe): about $3.99/mo, $35/yr
  - Tier 4 (Pakistan, India, Bangladesh, Egypt, Nigeria, Philippines, Indonesia and similar): about $1.99/mo, $19/yr
- Launch: US first, once sync is built. Other countries stay on the waitlist until they have real features; then open at their tier.
- Plus screen lists only features that work in the person's country; others show "Coming to your country". Price kept if a country moves tiers.
- Android: no prices or checkout until Google Play Billing is added (Play sells subscriptions itself). Terms and Refund Policy get a line that prices vary by country.
- Post-launch update (after 1.1 (119) is live on Play): centre the Circle/Bars/Line switch on "Where your month goes", Google Play badge on the site, R8 shrinking, edge-to-edge clean-up.

## Sync across devices (agreed 18 Oct 2026)
- Opt-in "Sync across your devices" in Your data & backups, signed-in only. End-to-end encrypted on the phone with a separate sync passphrase; new device joins by passphrase or a QR code from the old phone. Server (Firebase) stores only encrypted data it cannot read.
- Per-item merge, newest change wins; app lock stays per device; works offline.
- Part of Plus. Privacy Policy, Data safety and store text updated when it ships.

## Free week of Plus (agreed 18 Oct 2026)
- 7 days free, then the country's tier price; cancel any time before the first payment (through Google Play on Android).
- Offered at natural moments only (tapping Connect your bank, opening KeepWise on a second device, the Plus screen), never as pop-ups or nags.
- The start screen states the date the free week ends and the price after it. KeepWise reminds 2 days before it ends, with how to cancel. No dark patterns.

## More in Plus (agreed 18 Oct 2026)
- Receipts: photograph or upload a receipt on any spending line, bill, trip item or card charge; KeepWise reads the amount, shop and date; kept encrypted and synced.
- Money memories: a photo and a note on any spending or trip ("first dinner in Miami"); a memories timeline by month and trip; year in review.
- Receipts on splits: attach the bill to a split; in a shared split everyone in it can see the receipt (only them). Amount and items can be read from the photo to fill the split; anyone in the split can view it free, adding one needs Plus.

## Next update: "Terminal" look (idea 18 Oct 2026)
- A new theme in Themes, inspired by a dark trading-dashboard style: near-black background, neon green for money kept, red for over, glowing card edges on the hero, monospace uppercase micro-labels (e.g. YOU'LL HAVE SAVED, TO GOAL 100%), big number with smaller cents, small sparkline of the month's savings, a "tape" strip of daily spending bars.
- Look only: same KeepWise content and promises, no trading wording.
- Decided (18 Oct 2026, for next week): ship Terminal with a Glow setting (Off / On / Max, default On = "as shown"), plus Ledger as the light companion theme, alongside the chart switch spacing fix.

## Next update: downloaded / printed statement redesign
Problem (Oct 19, user's PDF): in a dark theme the statement prints as a dark slab on white paper, with no inner padding (text touches the edges), the browser's URL/date/page footer, the Expenditures group split across pages, tiny icon boxes, and 14 subscriptions listed one per line (a whole page) even though Misc already totals them.
Plan:
- Print and Download always use a fixed light "paper" palette (white, dark ink, one green accent), whatever theme is on screen; dark backgrounds are never printed.
- @page with margins plus our own header and footer (KeepWise, month, page), so the browser's URL/date line isn't needed.
- Keep each group together (break-inside: avoid) and give section headings room so a page never starts with a lone row.
- Summary row: In / Out / Kept as three clean figures, with Kept highlighted.
- Subscriptions on the statement: a compact two-column list, and $0 items hidden.
- Day-to-day categories: a small bar beside each amount instead of icon boxes.
- Consistent money format (always cents, or always whole dollars, per statement).
- Savings: hide $0 lines and say "Nothing set aside this month" once.
- The Android "Download" saves a self-contained file using the same paper styles (it currently copies the on-screen dark CSS).
- Test: print-emulated screenshots in dark and light themes at A4 and Letter, plus the downloaded file.

## Next update: fixes from Oct 19 (built and tested locally, not deployed)
- Adding a subscription (from the form or the owl) lands on the new card, below the pinned Yours/Cheaper/Codes switch, highlighted. The same goes for bills and loans added by the owl.
- Everyday lines (groceries, fuel…): every charge is listed with its date, a mistaken one can be removed (with Undo), and more can be added right there. Going over shows in red ("$X over", red bar). Everyday lines no longer show a leftover "Paid" date.
- Giving can go out in parts: each gift is listed with its date ("Given $9 of $14.22 · $5.22 to go"), can be removed, and another can be added with its own date. The tick still means "given this month" (one tick = the full planned amount), and an old single tick reads as one gift.
- Charges and gifts stay folded behind a tappable "3 charges ›" / "2 gifts ›" and open in their own inset card, so the Budget page stays calm.
- Loan cards show Installments left as a fourth box when the grid has a gap (instead of a line of text under it).
- "More options" under Expenditures gets room from the add-a-line row.
- Loan cards no longer repeat "Left to pay" as "$X left" on the right; the right side shows "of $X borrowed" only when that is known.

## Next update: design polish (approved Oct 19, from the before/after mockups)
- Subs: calm rows (name, price, last used, renewal, flags, ›); Keep/Auto/Drop, "I used it today" and Edit move inside the opened row.
- Subs: a small icon tile per kind (🎬 video, 🎵 music, 💪 fitness, 🧩 apps, ☁️ storage, 🎮 games, 📰 news, 🎓 learning, 🔁 unknown), optionally a soft colour from the name. No real brand logos (privacy: no outside icon service; trademarks).
- One way to add: "+ Add …" buttons everywhere (replaces the inline Add a line row and More options).
- Loans in one place: the Loans & debts card opens into the full loan cards; the separate section below goes.
- Headings: sans for every card title (incl. Giving, Trips and events, loan names); serif only for big numbers, page titles and the logo.
- Links: green = opens something, grey = quiet action (Edit, History), red only for destructive.
- Header: theme switch moves to Settings (search, profile, bell stay).
- Status Oct 19 night: the new subscription rows with icons are built (commit 4fb5a73, the 17 sub-control test lines still to be updated to open the row first). Also approved: drop "Last used N days ago" when the "Unused for N days" tag shows (done in that commit), and statement totals listing every item (loans, each card, insurance, giving, overspend) so the lines add up to the cent. Still to build: the rest of the design pass, the statement, the themes, then the full tests and screenshots of every screen.
- Bills this month (Overview): name what is still to pay ("Still to pay: Aptamil $20 · Diapers $20") with a tick on each and a "See all ›" to Budget; when everything is paid, one line "All 11 bills paid ✓ $total ›" that opens the paid list (each bill, amount, paid date) with "See in Budget ›"; sans heading like the rest.
- Subs "Paid" tick (asked Oct 20): on and after a renewal day, the sub row and its Coming up line ask "Charged?" with a tick (like bills). Subs are already counted in the month's plan, so a tick does not take the money off twice; it moves the sub from "still to go" to "paid", and lets you fix the amount if the price changed (only a different amount changes what you keep). Subs summary gets "N of M charged this month". Once ticked, it leaves Coming up (bills, subs and loans alike); an Undo on the toast brings it back. Not ticked by the next day: it moves to "Needs you" as a question ("Did Claude Pro charge you $20 on Oct 20?" Yes / Different amount / I cancelled it); "I cancelled it" marks it dropped and stops it counting from next month.
- Ask sheet: in the empty space next to Misc / Expenditures, 2–3 "repeat" chips for the spends used most or daily (e.g. "Food delivered $4.32", "Cigarettes $4.19"); one tap logs it again with Undo. Day-to-day rows use the emoji icons, and "Again" shows the amount it will log.
- Easy start: every setup / sign-in screen has a clear "Skip for now"; skipping lands on an empty, usable Month with a gentle "Set up your month" card (dismissable) to finish later. No step is required to get in.
- Bank statement import: make reading and analysis clearly better. First collect what goes wrong (misread columns/dates, merchants not recognised, subscriptions or bills missed or wrongly flagged, transfers counted as spending, currency mix-ups), using made-up sample statements in many bank layouts (CSV, PDF, photo) — never real statements in tests. Then fix the parsing and the categorising, show a clearer review screen (what was found, how sure it is, one tap to correct), and add tests for each case.
- Ask sheet history: under the Misc / Expenditures switch, a "Quick add | History" toggle. History lists that envelope's entries this month (newest first, last ~6, "See all ›" to Budget), each with Again and Remove (with Undo) — the same actions as on the Misc / Expenditures cards, so nobody has to leave the sheet. The repeat chips stay at the top of Quick add.
- How your pay splits: drop both sentences. The monthly total sits in the title row ("$2,863.79 a month"), a thin three-colour bar shows the split, and the Savings box reads "$328.79 · 11%". The explanation (other income included, savings = what is left) moves into the (i).
- Step-by-step creation (idea from a travel app on Instagram, Oct 22 — principles only, not its look): one question per card, answered steps fold into one-line summaries above ("Where · Miami", "When · 3 days"), a big Next and a Clear at the bottom, emoji chips, "Skip for now" on optional steps. Use it for New trip / event (Where → When: specific dates or "about N days" → Budget → Staying: hotel / rental / friends / skip → Flights: add or skip) and for Set up your month (pay → bills → subscriptions, each skippable). No maps or place suggestions (would need paid outside data and send locations out).
- Step-by-step style also for: add loan / car insurance, add card, new split, savings goal, statement import review. Long forms become a few short questions; quick logging stays one tap.
- Look: the light KeepWise green from the step mockups is the default. Light / dark / auto and the themes (incl. Terminal, Ledger) live in Settings and in the side menu under the profile — as a single "Look" row near the bottom (opens the choices), below the everyday items (Settings, App lock, Statements, Data & backups); no theme button in the header.
- Coming up keeps its date-tile style (20 / OCT), just refined: the tick on the right, the amount aligned, and "money in" rows in green.
- Split: no emoji faces. People get initial avatars in soft colours (as now, refined); split items keep KeepWise's own drawn icons. Overall aim: premium — consistent spacing, one card pattern, restrained colour, no cheap-looking clip-art.
- Illustrated "what it really costs" cards (idea from a café ad, Oct 23 — concept only, our own art): one bold number + a simple illustration + a receipt-style breakdown. Use sparingly at moments, not on everyday screens: a monthly insight ("Food delivered: 11 times, $46.80 this month — $560 a year"), Cheaper swap ideas (home vs café cost side by side), the month-end recap / money memories (Plus), and shareable images for Instagram marketing.
  - Sharing (Oct 23): people won't share what they waste (trolling). Two kinds of card: (1) KeepWise's own Instagram posts about general habits — never anyone's real data; (2) in-app share cards only for wins — "I kept $375 this month", "Dropped 3 subscriptions: +$480 a year", "Umrah fund 25% there", streaks — with amounts hidden by default (percent / "goal reached" only, a switch to show figures). Spending-habit cards stay private in the app.
  - Update: both card kinds (habit cost and wins) are mainly for the user to see privately in the monthly recap. Share is offered where people actually like to post: monthly delivery orders ("11 orders this month") and fuel/petrol cost (relatable because of inflation, e.g. "Fuel this month: up 18% on last year").
