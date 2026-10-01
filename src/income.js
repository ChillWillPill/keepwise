/* ================= other income and the month-start check-in ================= */
// Regular pay is S.income. Anything else (side job, creator income, trading, rental) is a source with an expected
// monthly amount that counts toward the plan, plus the payments actually received, logged as they arrive.
const INCOME_KINDS = [["side","Side job"],["creator","Creator income"],["trading","Trading"],["rental","Rental"],["services","Services"],["other","Other"]];
const kindLabel = k => (INCOME_KINDS.find(x => x[0] === k) || INCOME_KINDS[5])[1];
const extras = () => S.extras || (S.extras = []);
const INCOME_WHEN = [["any","No fixed day"],["monthly","Every month"],["weekly","Every week"],["biweekly","Every 2 weeks"]];
const WEEKDAYS = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
// amount is per payment for scheduled income, and per month when it has no fixed day
const extraMonthly = x => { const a = +x.amount || 0; return x.when === "weekly" ? a * 52 / 12 : x.when === "biweekly" ? a * 26 / 12 : a; };
const extraExpected = () => r2((S.extras || []).reduce((a, x) => a + extraMonthly(x), 0));
function nextIncome(x){
  const t = todayMid();
  if (x.when === "monthly" && x.day){ let r = new Date(t.getFullYear(), t.getMonth(), Math.min(x.day, daysInMonth(t.getFullYear(), t.getMonth())));
    if (r < t) r = new Date(t.getFullYear(), t.getMonth() + 1, Math.min(x.day, daysInMonth(t.getFullYear(), t.getMonth() + 1))); return r; }
  if (x.when === "weekly" && x.wd != null){ const r = new Date(t); r.setDate(r.getDate() + ((+x.wd - r.getDay() + 7) % 7)); return r; }
  if (x.when === "biweekly" && x.next){ const [y, m, d] = x.next.split("-").map(Number); const r = new Date(y, m - 1, d); while (r < t) r.setDate(r.getDate() + 14); return r; }
  return null;
}
const whenText = x => x.when === "monthly" && x.day ? `on the ${ordinal(x.day)}` : x.when === "weekly" && x.wd != null ? `every ${WEEKDAYS[x.wd]}` : x.when === "biweekly" ? "every 2 weeks" : "no fixed day";
const gotIn = (x, k) => (x.got || []).filter(p => inMonth(p.date, k)).reduce((a, p) => a + (+p.amount || 0), 0);
const todayKey = () => periodOf(new Date()).key;
function extraAverage(x){  // the last three finished months that have payments
  const by = {}; (x.got || []).forEach(p => { const k = periodKeyOfIso(p.date); if (k && k < todayKey()) by[k] = (by[k] || 0) + (+p.amount || 0); });
  const keys = Object.keys(by).sort().slice(-3); if (keys.length < 2) return null;
  return {avg: r2(keys.reduce((a, k) => a + by[k], 0) / keys.length), n: keys.length};
}
function incomeForm(x){
  const d = UI.incDraft;
  return `<form class="inc-form" data-form="income"><div class="grid2"><label class="field"><span>Where it comes from</span><input name="name" value="${esc(d.name)}" placeholder="e.g. YouTube, weekend shifts" enterkeyhint="next" autocomplete="off"></label>
    <label class="field"><span>Kind</span><select name="kind" data-inc-kind>${INCOME_KINDS.map(([k, n]) => `<option value="${k}" ${d.kind === k ? "selected" : ""}>${n}</option>`).join("")}</select></label></div>
    <div class="grid2"><label class="field"><span>When it arrives</span><select name="when" data-inc-when>${INCOME_WHEN.map(([k, n]) => `<option value="${k}" ${d.when === k ? "selected" : ""}>${n}</option>`).join("")}</select></label>
    ${d.when === "monthly" ? `<label class="field"><span>Day of the month</span><select name="day">${Array.from({length: 31}, (_, i) => `<option value="${i + 1}" ${+d.day === i + 1 ? "selected" : ""}>${ordinal(i + 1)}</option>`).join("")}</select></label>`
      : d.when === "weekly" ? `<label class="field"><span>Day of the week</span><select name="wd">${WEEKDAYS.map((n, i) => `<option value="${i}" ${+d.wd === i ? "selected" : ""}>${n}</option>`).join("")}</select></label>`
      : d.when === "biweekly" ? `<label class="field"><span>Next payment</span><input name="next" type="date" value="${esc(d.next || isoDaysAgo(0))}"></label>` : `<div></div>`}</div>
    <label class="field"><span>${d.when === "any" ? "Expected in a typical month" : "Each payment"}</span><span class="money-in"><em>${esc(sym())}</em><input name="amount" inputmode="decimal" enterkeyhint="done" placeholder="0" value="${esc(d.amount)}"></span><small class="muted small">${d.when === "any" ? "Payments can land on any day. Log each one when it arrives." : "Use a careful number."} This is what your plan counts on.</small></label>
    ${d.kind === "trading" ? `<p class="note small">Count only money you have actually taken out, not gains on paper. Trading income can fall to zero, so keep this number low.</p>` : ""}
    <div class="grid2">${x ? `<button class="btn danger" type="button" data-inc-del>Remove</button>` : `<button class="btn" type="button" data-inc-cancel>Cancel</button>`}<button class="btn primary" type="submit" style="padding:10px">${x ? "Save" : "Add income"}</button></div>
    ${x ? `<button class="link plain small" type="button" data-inc-cancel style="align-self:center">Cancel</button>` : ""}</form>`;
}
OUT.extraIncome = () => {
  const list = S.extras || [], k = todayKey(), mName = periodOf(new Date()).name;
  if (!list.length && !UI.incAdd) return `<button class="link small inc-add" type="button" data-inc-add>${I.plus}Add other income <span class="muted">side job, creator, trading, rental</span></button>`;
  const rows = list.map(x => {
    if (UI.incEdit === x.id) return `<div class="inc-row editing" data-inc="${x.id}">${incomeForm(x)}</div>`;
    const got = gotIn(x, k), exp = extraMonthly(x), pct = exp > 0 ? Math.min(100, got / exp * 100) : (got ? 100 : 0), av = extraAverage(x);
    const pays = (x.got || []).filter(p => inMonth(p.date, k)).sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    return `<div class="inc-row" data-inc="${x.id}"><div class="row-top"><div><div class="name">${esc(x.name)}</div><div class="muted small">${fmt(extraMonthly(x))}/mo · ${esc(whenText(x))}</div></div>
        <div style="text-align:right"><div class="name tnum ${got >= exp && got > 0 ? "good" : ""}">${fmt(got)}</div><div class="muted small">received in ${mName}</div></div></div>
      <div class="meter"><i style="width:${pct}%"></i></div>
      ${UI.incLog === x.id ? `<form class="inc-log" data-form="incomeLog"><span class="money-in" style="flex:1 1 110px"><em>${esc(sym())}</em><input name="amount" inputmode="decimal" enterkeyhint="done" placeholder="Amount" value="${x.when && x.when !== "any" ? esc(x.amount) : ""}" aria-label="Amount received"></span><input name="date" type="date" value="${isoDaysAgo(0)}" max="${isoDaysAgo(0)}" aria-label="Date received" style="flex:1 1 130px"><button class="btn small primary" type="submit">Save</button><button class="link plain small" type="button" data-inc-log-cancel>Cancel</button></form>`
        : `<div class="inline" style="justify-content:space-between"><button class="btn small" type="button" data-inc-log>${I.plus}Log a payment</button><button class="link plain small" type="button" data-inc-edit aria-label="Edit ${esc(x.name)}">Edit</button></div>`}
      ${pays.length ? `<div class="inc-pays">${pays.map(p => `<div class="line" data-pay-in="${p.id}"><span class="muted small">${shortDate(p.date)}</span><span class="inline"><span class="tnum good">+${fmt(p.amount)}</span><button class="link danger-link small" type="button" data-inc-pay-del aria-label="Remove this payment">Remove</button></span></div>`).join("")}</div>` : ""}
      ${av && (!x.when || x.when === "any") && Math.abs(av.avg - x.amount) > Math.max(1, x.amount * 0.05) ? `<div class="inc-avg small"><span>Your average over the last ${av.n} months is <b>${fmt(av.avg)}</b>.</span><button class="link small" type="button" data-inc-use-avg="${av.avg}">Use ${fmt(av.avg)}</button></div>` : ""}</div>`; }).join("");
  const total = extraExpected(), gotAll = list.reduce((a, x) => a + gotIn(x, k), 0);
  return `<section class="card inc-card"><div class="inline" style="justify-content:space-between;align-items:baseline"><h2>Other income</h2>${list.length ? `<span class="muted small tnum">${fmt(gotAll)} of ${fmt(total)}</span>` : ""}</div>
    ${rows}${UI.incAdd ? `<div class="inc-row editing">${incomeForm(null)}</div>` : `<button class="btn" type="button" data-inc-add>${I.plus}Add other income</button>`}
    ${list.length ? `<p class="muted small">Your plan counts ${fmt((+S.income || 0) + total)} coming in: ${fmt(+S.income || 0)} regular pay plus ${fmt(total)} expected here.</p>` : ""}</section>`;
};
OUT.incomeLabel = () => (S.extras || []).length ? "Regular pay" : "Money coming in";

// ---- when a month has ended: did you keep what you planned? ----
const keptOf = s => s.actual != null ? s.actual : s.kept;
function monthToClose(){
  const cur = currentKey(), real = todayKey();
  const k = statementKeys().find(x => x < cur && x < real && !S.statements[x].example && S.statements[x].confirmed == null);
  if (!k) return null; const s = S.statements[k];
  if (s.kept > 0 && s.setAside >= s.kept - 0.005){ s.confirmed = isoDaysAgo(0); s.actual = s.kept; return monthToClose(); }  // already set aside in full
  return s;
}
OUT.monthClose = () => {
  const s = monthToClose(); if (!s) return "";
  const name = keyLabel(s.key).split(" ")[0], rest = r2(Math.max(0, s.kept - s.setAside));
  if (UI.closeOther) return `<section class="card close-card" data-close="${s.key}"><p class="label">${esc(name)} is closed</p><h3>What did you actually keep in ${esc(name)}?</h3>
    <form class="inline" data-form="closeMonth"><span class="money-in" style="flex:1 1 140px"><em>${esc(sym())}</em><input name="amount" inputmode="decimal" enterkeyhint="done" placeholder="0" aria-label="Amount kept in ${esc(name)}"></span><button class="btn primary" type="submit" style="width:auto;padding:10px 18px">Save</button></form>
    <button class="link plain small" type="button" data-close-back style="align-self:center">Back</button></section>`;
  return `<section class="card close-card" data-close="${s.key}"><p class="label">${esc(name)} is closed</p>
    ${s.kept > 0 ? `<h3>You planned to keep ${fmt(s.kept)}. Did you?</h3>${s.setAside > 0 ? `<p class="muted">You already set aside ${fmt(s.setAside)} of it.</p>` : ""}
      <button class="btn primary" type="button" data-close-yes>Yes, add ${fmt(rest)} to my savings</button>`
    : `<h3>Your plan for ${esc(name)} was ${fmt(-s.kept)} short.</h3><p class="muted">If the month went better than planned, say what you kept.</p>
      <button class="btn primary" type="button" data-close-zero>That’s right, nothing kept</button>`}
    <div class="inline" style="justify-content:space-between"><button class="link small" type="button" data-close-other>I kept a different amount</button><button class="link plain small" type="button" data-close-skip>Skip</button></div></section>`;
};
function closeMonth(key, actual){
  const s = S.statements[key]; if (!s) return; const u = undoable();
  const add = r2(actual - (s.setAside || 0));
  S.efSaved = r2(Math.max(0, (+S.efSaved || 0) + add)); s.actual = r2(actual); s.confirmed = isoDaysAgo(0); UI.closeOther = false;
  save(); render(true);
  toast(add > 0 ? `Added ${fmt(add)} to your savings. Your balance is ${fmt(S.efSaved)}.` : add < 0 ? `Savings adjusted by ${fmt(add)}. Your balance is ${fmt(S.efSaved)}.` : `${keyLabel(key).split(" ")[0]} is recorded.`, u);
}
