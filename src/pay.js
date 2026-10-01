/* ================= your month and your paydays ================= */
// A month normally runs from the 1st. It can start on another day (for example the 25th, payday), and is then named
// after the month most of it falls in: 25 Oct to 24 Nov is "November".
function planPeriodNow(){ const now = new Date(), P0 = periodOf(now); return Math.round((P0.end - todayMid()) / DAY) <= 2 ? periodOf(new Date(P0.end.getFullYear(), P0.end.getMonth(), P0.end.getDate() + 1)) : P0; }
const monthStartDay = () => Math.min(28, Math.max(1, +S.monthStart || 1));
function periodOf(date){
  const ms = monthStartDay(), d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const start = d.getDate() >= ms ? new Date(d.getFullYear(), d.getMonth(), ms) : new Date(d.getFullYear(), d.getMonth() - 1, ms);
  const end = new Date(start.getFullYear(), start.getMonth() + 1, ms - 1);
  const named = ms <= 15 ? start : new Date(start.getFullYear(), start.getMonth() + 1, 1);
  return {start, end, key: `${named.getFullYear()}-${String(named.getMonth() + 1).padStart(2, "0")}`, name: named.toLocaleString("en-US", {month: "long"})};
}
function periodForKey(k){ const [y, m] = k.split("-").map(Number), ms = monthStartDay(); return periodOf(ms <= 15 ? new Date(y, m - 1, ms) : new Date(y, m - 2, ms)); }
const periodKeyOfIso = iso => { if (!iso) return ""; const [y, m, d] = iso.split("-").map(Number); return periodOf(new Date(y, m - 1, d)).key; };
const dayMonth = d => d.toLocaleDateString("en-US", {month: "short", day: "numeric"});
const rangeText = p => `${dayMonth(p.start)} to ${dayMonth(p.end)}`;

// ---- how you are paid (optional) ----
const PAY_WHEN = [["monthly","Once a month"],["twice","Twice a month"],["biweekly","Every 2 weeks"],["weekly","Every week"]];
const PAY_BASE = {monthly: 1, twice: 2, biweekly: 2, weekly: 4};  // paychecks in an ordinary month; any more is a bonus
const payOn = () => !!(S.pay && S.pay.when);
const payBase = () => PAY_BASE[(S.pay || {}).when] || 1;
function paydaysBetween(a, b){  // every payday from a to b, both included
  const p = S.pay || {}, out = [], clamp = (y, m, day) => new Date(y, m, Math.min(day, daysInMonth(y, m)));
  if (p.when === "monthly" || p.when === "twice"){
    const days = [p.day, p.when === "twice" ? p.day2 : null].filter(Boolean);
    for (const c = new Date(a.getFullYear(), a.getMonth(), 1); c <= b; c.setMonth(c.getMonth() + 1)) days.forEach(day => { const d = clamp(c.getFullYear(), c.getMonth(), +day); if (d >= a && d <= b) out.push(d); });
  } else if (p.when === "weekly" && p.wd != null){
    const d = new Date(a); d.setDate(d.getDate() + ((+p.wd - d.getDay() + 7) % 7)); for (; d <= b; d.setDate(d.getDate() + 7)) out.push(new Date(d));
  } else if (p.when === "biweekly" && p.next){
    const [y, m, dd] = p.next.split("-").map(Number), d = new Date(y, m - 1, dd);
    while (d > a) d.setDate(d.getDate() - 14); while (d < a) d.setDate(d.getDate() + 14);
    for (; d <= b; d.setDate(d.getDate() + 14)) out.push(new Date(d));
  }
  return out.sort((x, y) => x - y);
}
const nextPayday = () => { const t = todayMid(), far = new Date(t); far.setDate(far.getDate() + 45); return paydaysBetween(t, far)[0] || null; };
function payBonus(p){  // extra paychecks in this month, beyond the ordinary number
  if (!payOn() || !(S.pay.when === "biweekly" || S.pay.when === "weekly")) return {count: 0, extra: 0};
  const n = paydaysBetween(p.start, p.end).length;
  return {count: n, extra: Math.max(0, n - payBase()) * (+S.pay.amount || 0)};
}
const payWhenText = () => { const p = S.pay || {};
  return p.when === "monthly" ? (p.day ? `on the ${p.day >= 31 ? "last day" : ordinal(p.day)}` : "once a month")
    : p.when === "twice" ? (p.day && p.day2 ? `on the ${ordinal(p.day)} and ${p.day2 >= 31 ? "last day" : ordinal(p.day2)}` : "twice a month")
    : p.when === "biweekly" ? "every 2 weeks" : p.when === "weekly" ? (p.wd != null ? `every ${WEEKDAYS[p.wd]}` : "every week") : ""; };
OUT.payBox = () => {
  if (UI.payEdit){ const d = UI.payDraft, dayOpts = (sel, last) => Array.from({length: 31}, (_, i) => `<option value="${i + 1}" ${+sel === i + 1 ? "selected" : ""}>${i === 30 && last ? "Last day" : ordinal(i + 1)}</option>`).join("");
    return `<form class="card pay-form" data-form="pay"><h3>How you’re paid</h3>
      <div class="grid2"><label class="field"><span>How often</span><select name="when" data-pay-when>${PAY_WHEN.map(([k, n]) => `<option value="${k}" ${d.when === k ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      ${d.when === "monthly" ? `<label class="field"><span>Payday</span><select name="day">${dayOpts(d.day, true)}</select></label>`
        : d.when === "weekly" ? `<label class="field"><span>Payday</span><select name="wd">${WEEKDAYS.map((n, i) => `<option value="${i}" ${+d.wd === i ? "selected" : ""}>${n}</option>`).join("")}</select></label>`
        : d.when === "biweekly" ? `<label class="field"><span>Next payday</span><input name="next" type="date" value="${esc(d.next || isoDaysAgo(0))}"></label>` : `<label class="field"><span>First payday</span><select name="day">${dayOpts(d.day)}</select></label>`}</div>
      ${d.when === "twice" ? `<label class="field"><span>Second payday</span><select name="day2">${dayOpts(d.day2, true)}</select></label>` : ""}
      <label class="field"><span>Each paycheck, after tax</span><span class="money-in"><em>${esc(sym())}</em><input name="amount" inputmode="decimal" enterkeyhint="done" placeholder="0" value="${esc(d.amount)}"></span>
        ${d.when === "biweekly" || d.when === "weekly" ? `<small class="muted small">Your plan counts ${PAY_BASE[d.when]} paychecks a month. A month with one more shows it as extra you can save.</small>` : ""}</label>
      <label class="field"><span>My month starts on</span><select name="monthStart">${Array.from({length: 28}, (_, i) => `<option value="${i + 1}" ${+d.monthStart === i + 1 ? "selected" : ""}>${i === 0 ? "The 1st (calendar month)" : "The " + ordinal(i + 1)}</option>`).join("")}</select>
        <small class="muted small">Paid near the end of the month? Start your month on payday so each statement covers one paycheck.</small></label>
      <div class="grid2"><button class="btn" type="button" data-payday-cancel>Cancel</button><button class="btn primary" type="submit" style="padding:10px">Save</button></div>
      ${payOn() ? `<button class="link plain small" type="button" data-payday-clear style="align-self:center">Remove my pay schedule</button>` : ""}</form>`; }
  if (!payOn()) return `<button class="link small inc-add" type="button" data-payday-edit>${I.month.replace("<svg ", '<svg width="16" height="16" style="vertical-align:-3px;margin-right:6px" ')}How are you paid? <span class="muted">optional</span></button>`;
  const n = nextPayday(), ms = monthStartDay(), P = periodOf(new Date());
  return `<div class="pay-line"><span>${I.month.replace("<svg ", '<svg width="18" height="18" ')}<span><b>${fmt(+S.pay.amount || 0)}</b> ${esc(payWhenText())}${n ? ` · next payday <b>${daysUntil(n) === 0 ? "today" : daysUntil(n) === 1 ? "tomorrow" : n.toLocaleDateString("en-US", {weekday: "short", month: "short", day: "numeric"})}</b>` : S.pay.when === "biweekly" ? " · add your next payday" : ""}${ms !== 1 ? `<br><span class="muted small">Your ${esc(P.name)} runs ${rangeText(P)}.</span>` : ""}</span></span><button class="link small" type="button" data-payday-edit>Change</button></div>`;
};
