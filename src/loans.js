/* ================= loans and debt ================= */
// A loan is a payment with a finish line. The payment counts toward Expenditures until the end date passes.
// With a total and no end date, the finish is worked out from the payments alone, without interest, and says so.
const LOAN_KINDS = [["bank","Bank loan"],["personal","Personal loan"],["student","Student debt"],["card","Credit card"],["car","Car loan"],["home","Mortgage"],["other","Other debt"]];
const LOAN_EVERY = [["mo","Every month","a month"],["wk","Every week","a week"],["2wk","Every 2 weeks","every 2 weeks"],["yr","Every year","a year"]];
const CARD_TYPES = ["Visa", "Mastercard", "American Express", "Discover", "UnionPay", "Other"];
const loanKind = k => (LOAN_KINDS.find(x => x[0] === k) || LOAN_KINDS[6])[1];
const loanList = () => S.loans || (S.loans = []);
const loanMonthly = l => { const a = +l.pay || 0, fee = l.kind === "card" ? (+l.fee || 0) / 12 : 0; return fee + (l.every === "wk" ? a * 52 / 12 : l.every === "2wk" ? a * 26 / 12 : l.every === "yr" ? a / 12 : a); };
const loanDone = l => !!l.end && l.end < isoDaysAgo(0);
const loansMonthly = () => r2((S.loans || []).filter(l => !loanDone(l)).reduce((a, l) => a + loanMonthly(l), 0));
function loanFinish(l){
  const t = todayMid();
  if (l.end){ const [y, m, d] = l.end.split("-").map(Number), dt = new Date(y, m - 1, d); return {date: dt, months: Math.max(0, Math.round((dt - t) / (30.44 * DAY))), est: false}; }
  const mth = loanMonthly(l); if (+l.total > 0 && mth > 0){ const n = Math.ceil(l.total / mth); return {date: new Date(t.getFullYear(), t.getMonth() + n, 1), months: n, est: true}; }
  return null;
}
// Interest is worked out only when every number is there and makes sense: a payment, the amount left, whole installments
// left and a real end date still ahead. It is the yearly rate at which those payments exactly clear the amount left.
const LOAN_PPY = {mo: 12, wk: 52, "2wk": 26, yr: 1};
function loanRate(l){
  const A = +l.pay, P = +l.total, n = +l.left, end = String(l.end || "");
  if (!(A > 0) || !(P > 0) || !(n >= 1) || !Number.isInteger(n) || n > 1200) return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(end) || isNaN(new Date(end + "T00:00:00").getTime()) || end < isoDaysAgo(0)) return null;
  const paid = A * n; if (paid < P - 0.005) return {short: true};
  if (paid - P < 0.005) return {apr: 0, paid, cost: 0};
  let lo = 0, hi = 1; const pv = r => A * (1 - Math.pow(1 + r, -n)) / r;
  while (pv(hi) > P && hi < 64) hi *= 2;
  for (let i = 0; i < 80; i++){ const mid = (lo + hi) / 2; if (pv(mid) > P) lo = mid; else hi = mid; }
  const apr = (lo + hi) / 2 * (LOAN_PPY[l.every] || 12) * 100;
  return isFinite(apr) && apr < 1000 ? {apr: Math.round(apr * 10) / 10, paid, cost: r2(paid - P)} : null;
}
function loanCalc(f){ const v = n => String(f.elements[n] ? f.elements[n].value : "").trim(), leftRaw = v("left");
  const d = {pay: numv(v("pay")), total: numv(v("total")), left: /^\d{1,4}$/.test(leftRaw) ? +leftRaw : 0, end: v("end"), every: v("every")};
  f.elements.rate.value = loanRateText(d); const n = f.querySelector("[data-loan-ratenote]"); if (n) n.textContent = loanRateNote(d); }
const loanRateNote = l => { const r = loanRate(l); return !r ? "Fill in the payment, amount left, installments left and end date, and the interest is worked out for you."
  : r.short ? "These payments add up to less than the amount left. Check the payment, the amount left or the installments."
  : r.apr === 0 ? "Your payments add up to exactly the amount left, so there is no interest." : `You will pay ${fmt(r.paid)} in all, which is ${fmt(r.cost)} in interest.`; };
const loanRateText = l => { const r = loanRate(l); return !r ? "" : r.short ? "Check the numbers" : `${r.apr}% a year`; };
const monthYear = d => d.toLocaleDateString("en-US", {month: "short", year: "numeric"});
function loanForm(l){
  const d = UI.loanDraft, cardSel = !d.card ? "Visa" : CARD_TYPES.includes(d.card) ? d.card : "Other", sel = (name, list, v) => `<select name="${name}">${list.map(([k, n]) => `<option value="${k}" ${v === k ? "selected" : ""}>${n}</option>`).join("")}</select>`;
  return `<form class="inc-form" data-form="loan"><div class="grid2"><label class="field"><span>Type</span>${sel("kind", LOAN_KINDS, d.kind)}</label>
      <label class="field"><span>Name <small class="muted">optional</small></span><input name="name" value="${esc(d.name)}" placeholder="e.g. Bank of America" enterkeyhint="next" autocomplete="off"></label></div>
    <div class="grid2" data-loan-cardrow ${d.kind === "card" ? "" : "hidden"}><label class="field"><span>Card</span>${sel("card", CARD_TYPES.map(c => [c, c]), cardSel)}</label>
      <label class="field"><span>Yearly fee <small class="muted">optional</small></span><span class="money-in"><em>${esc(sym())}</em><input name="fee" inputmode="decimal" enterkeyhint="next" placeholder="0" value="${esc(d.fee || "")}"></span></label></div>
    <label class="field" data-loan-cardother ${d.kind === "card" && cardSel === "Other" ? "" : "hidden"}><span>Card name</span><input name="cardOther" value="${esc(cardSel === "Other" && d.card !== "Other" ? d.card || "" : "")}" placeholder="e.g. Store card" maxlength="30" enterkeyhint="next" autocomplete="off"></label>
    <div class="grid2"><label class="field"><span>Payment</span><span class="money-in"><em>${esc(sym())}</em><input name="pay" inputmode="decimal" enterkeyhint="next" placeholder="0" value="${esc(d.pay)}"></span></label>
      <label class="field"><span>How often</span>${sel("every", LOAN_EVERY, d.every)}</label></div>
    <div class="grid2"><label class="field"><span>Left to pay <small class="muted">optional</small></span><span class="money-in"><em>${esc(sym())}</em><input name="total" inputmode="decimal" enterkeyhint="next" placeholder="0" value="${esc(d.total)}"></span></label>
      <label class="field"><span>Installments left <small class="muted">optional</small></span><input name="left" inputmode="numeric" enterkeyhint="next" placeholder="e.g. 24" value="${esc(d.left || "")}"></label></div>
    <div class="grid2"><label class="field"><span>End date <small class="muted">optional</small></span><input name="end" type="date" value="${esc(d.end || "")}"></label>
      <label class="field"><span>Interest</span><input name="rate" readonly tabindex="-1" class="calc" placeholder="Worked out for you" value="${esc(loanRateText(d))}" aria-label="Interest, worked out from your numbers"></label></div>
    <p class="muted small" data-loan-ratenote>${loanRateNote(d)}</p>
    <div class="grid2">${l ? `<button class="btn danger" type="button" data-loan-del>Remove</button>` : `<button class="btn" type="button" data-loan-cancel>Cancel</button>`}<button class="btn primary" type="submit" style="padding:10px">${l ? "Save" : "Add loan"}</button></div>
    ${l ? `<button class="link plain small" type="button" data-loan-cancel style="align-self:center">Cancel</button>` : ""}</form>`;
}
OUT.loans = () => {
  const list = S.loans || [], live = list.filter(l => !loanDone(l)), owed = r2(live.reduce((a, l) => a + (+l.total || 0), 0));
  const rows = list.map(l => {
    if (UI.loanEdit === l.id) return `<div class="inc-row editing" data-loan="${l.id}">${loanForm(l)}</div>`;
    const f = loanFinish(l), done = loanDone(l), rate = loanRate(l), ev = (LOAN_EVERY.find(x => x[0] === l.every) || LOAN_EVERY[0])[2];
    return `<div class="inc-row" data-loan="${l.id}"><div class="row-top"><div><div class="name">${esc(l.name || loanKind(l.kind))}</div><div class="muted small">${esc(loanKind(l.kind))}${l.kind === "card" && l.card ? " · " + esc(l.card) : ""} · ${fmt(l.pay)} ${ev}${l.kind === "card" && +l.fee > 0 ? ` · ${fmt(l.fee)} yearly fee` : ""}</div></div>
        <div style="text-align:right">${done ? `<span class="pill ok">Paid off</span>` : `<div class="name tnum">${fmt(loanMonthly(l))}<span class="muted small">/mo</span></div>`}${+l.total > 0 && !done ? `<div class="muted small tnum">${fmt(l.total)} left</div>` : ""}</div></div>
      ${!done && (+l.left > 0 || (rate && !rate.short)) ? `<p class="small">${[+l.left > 0 ? `${l.left} installment${+l.left === 1 ? "" : "s"} left` : "", rate && !rate.short ? `interest about ${rate.apr}% a year` : ""].filter(Boolean).join(" · ").replace(/^./, c => c.toUpperCase())}</p>` : ""}
      ${done ? `<p class="muted small">Ended ${shortDate(l.end)}. It no longer counts in your plan.</p>` : f ? `<p class="small ${f.est ? "muted" : ""}">${f.est ? `About ${f.months} month${f.months === 1 ? "" : "s"} to go at this pace, around ${monthYear(f.date)}. Interest is not included.` : f.months === 0 ? `Ends ${shortDate(l.end)}.` : `Ends ${monthYear(f.date)}, ${f.months} month${f.months === 1 ? "" : "s"} from now.`}</p>` : ""}
      <button class="link plain small" type="button" data-loan-edit aria-label="Edit ${esc(l.name || loanKind(l.kind))}" style="align-self:flex-end">Edit</button></div>`; }).join("");
  return `<section class="card inc-card loan-card"><div class="inline" style="justify-content:space-between;align-items:baseline"><h2 class="h-info">Loans and debt${infoBtn("loans", "About loans and debt")}</h2>${live.length ? `<span class="muted small tnum">${fmt(loansMonthly())}/mo</span>` : ""}</div>
    ${infoTip("loans", "Loan and credit card payments count toward Expenditures until the end date passes. A card’s yearly fee is spread across the year. Interest is worked out only when the payment, amount left, installments left and end date are all filled in. With an amount left and no end date, the finish is estimated from your payments and does not include interest.")}
    ${rows}${UI.loanAdd ? `<div class="inc-row editing">${loanForm(null)}</div>` : `<button class="btn" type="button" data-loan-add>${I.plus}Add a loan or credit card</button>`}
    ${live.length && owed > 0 ? `<p class="muted small">You owe ${fmt(owed)} in total across ${live.filter(l => +l.total > 0).length} of these.</p>` : !list.length && !UI.loanAdd ? `<p class="muted small">Bank loans, student debt, credit cards and anything else you are paying back.</p>` : ""}</section>`;
};
