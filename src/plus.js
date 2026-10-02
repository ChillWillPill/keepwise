/* ================= KeepWise Plus: what it adds and what it costs ================= */
// One screen that gathers every Plus feature, the price and the waitlist. Plus is not on sale yet, and the screen says so.
const PLUS_PRICE = {monthly: 15, monthlyEarly: 12, earlyMonths: 6, yearly: 180, yearlyEarly: 140};
const usd = n => "$" + (Number.isInteger(n) ? n : n.toFixed(2));
const HOME_IC = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11l8-7 8 7"/><path d="M6 10v9h12v-9"/></svg>';
const PIN_IC = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-6.500-5.700-6.500-10.500a6.500 6.500 0 0 1 13 0C18.500 15.300 12 21 12 21z"/><circle cx="12" cy="10.500" r="2.300"/></svg>';
const PLUS_REASONS = () => [
  [I.users, "Live splits with friends", "Add friends straight from your contacts. Everyone sees the same split on their own phone, and knows the moment it changes."],
  [I.redo, "Your money on every device", "Sign in once and your month follows you to your phone, tablet and computer. It is backed up with encryption only you can unlock."],
  [I.work, "Business Account", "Give your work money its own books. Income, costs and subscriptions stay separate from personal, with a running tax set-aside and a year-end export ready for your accountant."],
  [HOME_IC, "A shared household", "Run one month with your partner or family. Each person keeps their own sign-in, and you all see the same plan."],
  [PIN_IC, "Offers near you", "Official discounts, vouchers and promo codes from stores in your city, matched to your approximate area and nothing more precise."],
  [BELL, "Reminders on every phone", "Renewal and payday reminders on iPhone and the web too, so a charge never arrives unannounced."],
  [I.camera, "Receipt photos", "Attach the receipt to a split, so nobody has to ask what was paid."],
  [I.heart, "Moments", "Turn the splits from a trip or a wedding into a private album worth keeping."],
];
const PLUS_FREE = ["Your month-end number and plan", "Subscriptions, with reminders before payday", "Ideas to pay less, and your promo codes", "Splits on this phone, with ready-made messages", "Statement import, monthly statements and backups"];
function plusCta(){
  const signedIn = typeof ACC !== "undefined" && ACC.user && ACC.profile, joined = signedIn && ACC.profile.plusInterest;
  return joined ? `<p class="plus-joined"><span class="pill ok">You’re on the waitlist</span> We’ll email you when KeepWise Plus opens.</p>`
    : signedIn ? `<button class="btn primary" type="button" data-acc-plus>Join the waitlist</button>`
    : `<button class="btn primary" type="button" data-open-account>Sign in to join the waitlist</button>`;
}
V.plus = () => { const P = PLUS_PRICE, perMonth = P.yearlyEarly / 12;
  return `<div class="inline" style="justify-content:space-between"><span class="pill gold">KeepWise Plus</span><button class="btn small" type="button" data-plus-close>Done</button></div>
  <h1 class="plus-h">Everything free stays free.</h1>
  <p class="plus-sub">Plus adds what one phone cannot do alone.</p>
  <section class="card"><ul class="plus-list">${PLUS_REASONS().map(([ic, t, d]) => `<li><span class="plus-ic">${ic}</span><div><b>${t}</b><span class="muted small">${d}</span></div></li>`).join("")}</ul></section>
  <section class="plus-prices" aria-label="Prices">
    <div class="card plus-price best"><span class="pill gold">Early user price</span><span class="label">Yearly</span>
      <div class="plus-amt"><s>${usd(P.yearly)}</s><b>${usd(P.yearlyEarly)}</b><span>a year</span></div>
      <p class="muted small">About ${usd(Math.round(perMonth * 100) / 100)} a month. You save ${usd(P.yearly - P.yearlyEarly)}.</p>${kwCodeChip(KW_CODES[0])}</div>
    <div class="card plus-price"><span class="pill gold">Early user price</span><span class="label">Monthly</span>
      <div class="plus-amt"><s>${usd(P.monthly)}</s><b>${usd(P.monthlyEarly)}</b><span>a month</span></div>
      <p class="muted small">For your first ${P.earlyMonths} months, then ${usd(P.monthly)} a month.</p>${kwCodeChip(KW_CODES[1])}</div>
  </section>
  <p class="muted small" style="text-align:center">Prices in US dollars. Plus is not on sale yet. Join the waitlist and we will email you when it opens.</p>
  ${plusCta()}
  <section class="card"><h2 style="font-size:1.2rem">Free, and staying free</h2><ul class="plus-free">${PLUS_FREE.map(t => `<li>${I.check}<span>${t}</span></li>`).join("")}</ul></section>`; };
// KeepWise's own codes for Plus. They carry the early user prices, so the Codes tab and the Plus screen always agree.
const KW_CODES = [
  {code: "EARLY140", plan: "Yearly", offer: `${usd(PLUS_PRICE.yearlyEarly)} for your first year, instead of ${usd(PLUS_PRICE.yearly)}`},
  {code: "EARLY12", plan: "Monthly", offer: `${usd(PLUS_PRICE.monthlyEarly)} a month for your first ${PLUS_PRICE.earlyMonths} months, instead of ${usd(PLUS_PRICE.monthly)}`},
];
const kwCodeChip = c => `<button class="code" type="button" data-copy="${c.code}" aria-label="Copy code ${c.code}">${c.code}</button>`;
OUT.kwCodes = () => `<section class="card" data-kw-codes><div class="inline" style="justify-content:space-between;align-items:baseline"><h2 style="font-size:1.2rem">KeepWise Plus codes</h2><span class="pill gold">Early user</span></div>
  <div class="rows">${KW_CODES.map(c => `<div class="row" data-kw-code="${c.code}"><div class="row-top"><div><div class="name">${c.plan} plan</div><div class="muted small">${c.offer}</div></div><div><span class="pill ok">Eligible</span></div></div>
    <div class="inline" style="justify-content:space-between"><button class="code" type="button" data-copy="${c.code}" aria-label="Copy code ${c.code}">${c.code}</button><span class="muted small">Use it at checkout when Plus opens</span></div></div>`).join("")}</div>
  ${plusLink("See what Plus adds")}</section>`;
const plusLink = (label = "See everything in Plus") => `<button class="link small" type="button" data-plus-open style="align-self:center">${label}</button>`;
