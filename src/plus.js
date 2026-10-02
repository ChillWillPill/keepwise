/* ================= KeepWise Plus: what it adds and what it costs ================= */
// One screen that gathers every Plus feature, the price and the waitlist. Plus is not on sale yet, and the screen says so.
const PLUS_PRICE = {monthly: 15, monthlyEarly: 12, earlyMonths: 6, yearly: 180, yearlyEarly: 140};
const usd = n => "$" + (Number.isInteger(n) ? n : n.toFixed(2));
const PLUS_REASONS = () => [
  [I.users, "Split with friends, live", "Add friends straight from your contacts. Everyone sees the same split on their own phone and is notified when it changes."],
  [I.redo, "Your month on every device", "Sign in and your budget follows you to your phone, tablet and computer, backed up with encryption only you can unlock."],
  [I.work, "A Business space", "Keep work money apart from personal, with a running tax set-aside and a year-end export."],
  [I.camera, "Receipt photos", "Attach the receipt to a split, so everyone sees what was paid."],
  [I.heart, "Moments", "Turn the splits from a trip or a wedding into a private album."],
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
      <p class="muted small">About ${usd(Math.round(perMonth * 100) / 100)} a month. You save ${usd(P.yearly - P.yearlyEarly)}.</p></div>
    <div class="card plus-price"><span class="pill gold">Early user price</span><span class="label">Monthly</span>
      <div class="plus-amt"><s>${usd(P.monthly)}</s><b>${usd(P.monthlyEarly)}</b><span>a month</span></div>
      <p class="muted small">For your first ${P.earlyMonths} months, then ${usd(P.monthly)} a month.</p></div>
  </section>
  <p class="muted small" style="text-align:center">Prices in US dollars. Plus is not on sale yet. Join the waitlist and we will email you when it opens.</p>
  ${plusCta()}
  <section class="card"><h2 style="font-size:1.2rem">Free, and staying free</h2><ul class="plus-free">${PLUS_FREE.map(t => `<li>${I.check}<span>${t}</span></li>`).join("")}</ul></section>`; };
const plusLink = (label = "See everything in Plus") => `<button class="link small" type="button" data-plus-open style="align-self:center">${label}</button>`;
