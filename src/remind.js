/* ================= reminders before payday (scheduled on this phone; no server sends them) ================= */
// In the Android app, KeepWise can ask "Still using Netflix?" in a notification with one-tap answers. The phone itself
// schedules them: one a day at most, thinning out if they are ignored, and none once you answer or open Subs.
const REMIND_AT = [18, 30], REMIND_DAYS = [0, 1, 2, 5, 8], REMIND_LEAD = 10, REMIND_IDS = Array.from({length: 12}, (_, i) => 7100 + i);
const BELL = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9.5a6 6 0 0 1 12 0c0 5 2 6.5 2 6.5H4s2-1.500 2-6.5z"/><path d="M10 19.500a2.200 2.200 0 0 0 4 0"/></svg>';
function notifPlugin(){ try { const C = window.Capacitor; if (!C) return null; return (C.Plugins && C.Plugins.LocalNotifications) || (C.registerPlugin ? C.registerPlugin("LocalNotifications") : null); } catch(e){ return null; } }
function remindCycles(){  // the next two paydays (or month starts) at least 25 days apart, each with the 10 days before it
  const t = todayMid(), plus = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n), picks = [];
  let cand;
  if (payOn()) cand = paydaysBetween(t, plus(t, 80));
  else { const a = plus(periodOf(t).end, 1); cand = [a, plus(periodOf(a).end, 1)]; }
  cand.forEach(d => { if (!picks.length || (d - picks[picks.length - 1]) / DAY >= 25) picks.push(d); });
  return picks.slice(0, 2).map(a => ({key: isoOf(a), anchor: a, start: plus(a, -REMIND_LEAD)}));
}
function remindQueue(c){  // who to ask about: soonest renewal first, then the most expensive
  const from = isoOf(c.start), far = 9e15;
  return S.subs.filter(s => s.keep !== "drop" && !isOurs(s) && !(s.reviewedAt && s.reviewedAt >= from))
    .sort((a, b) => ((nextRenewal(a) || far) - (nextRenewal(b) || far)) || subMonthly(b) - subMonthly(a));
}
function remindPlan(){
  const R = S.remind || {}; if (!R.on) return [];
  const now = new Date(), out = [];
  remindCycles().forEach(c => {
    if (R.seen === c.key) return;
    const q = remindQueue(c); if (!q.length) return; let n = 0;
    REMIND_DAYS.forEach(off => { const at = new Date(c.start.getFullYear(), c.start.getMonth(), c.start.getDate() + off, REMIND_AT[0], REMIND_AT[1]);
      if (at > now) out.push({at, sub: q[n++ % q.length], cycle: c.key}); });
  });
  return out.slice(0, REMIND_IDS.length).map((x, i) => ({...x, id: REMIND_IDS[i]}));
}
// A subscription that renews outside the days before payday gets its own question, a week before the charge
// (or 5 days before, if a week has already passed). One answered in the last 20 days is left alone.
const RENEW_IDS = Array.from({length: 12}, (_, i) => 7200 + i), ARRIVE_IDS = Array.from({length: 10}, (_, i) => 7300 + i);
function renewPlan(){
  const R = S.remind || {}; if (!R.on) return [];
  const now = new Date(), cyc = remindCycles(), recent = isoDaysAgo(20), out = [];
  S.subs.filter(s => s.keep !== "drop" && !isOurs(s) && !(s.reviewedAt && s.reviewedAt >= recent)).forEach(s => {
    const r = nextRenewal(s); if (!r) return;
    const at = [7, 5].map(n => new Date(r.getFullYear(), r.getMonth(), r.getDate() - n, REMIND_AT[0], REMIND_AT[1])).find(d => d > now); if (!at) return;
    const day = new Date(at.getFullYear(), at.getMonth(), at.getDate());
    if (cyc.some(c => R.seen !== c.key && day >= c.start && day <= c.anchor)) return;  // the payday questions already cover it
    out.push({at, sub: s, cycle: "renew"}); });
  return out.sort((a, b) => a.at - b.at).slice(0, RENEW_IDS.length).map((x, i) => ({...x, id: RENEW_IDS[i]}));
}
function arrivePlan(){  // the morning after money was due, if it has not been logged by then
  const R = S.remind || {}; if (!R.on) return [];
  const now = new Date(), t = todayMid(), out = [], at = d => new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1, 10, 0);
  const add = (name, amount, d) => { const when = at(d) > now ? at(d) : at(t); out.push({at: when, title: `Did ${name} arrive?`, body: `${fmt(amount)} was expected ${dayMonth(d)}. Open KeepWise to log it.`}); };
  arrivals().forEach(a => add(a.key === "pay" ? "your pay" : a.name, a.amount, a.date));
  if (payOn()){ const d = paydaysBetween(t, dayPlus(t, 40))[0]; if (d && !((S.payGot || "") >= isoOf(d))) add("your pay", +S.pay.amount || 0, d); }
  (S.extras || []).forEach(x => { const d = nextIncome(x); if (d && !incomeLogged(x, isoOf(d))) add(x.name, +x.amount || 0, d); });
  return out.sort((a, b) => a.at - b.at).slice(0, ARRIVE_IDS.length).map((x, i) => ({...x, id: ARRIVE_IDS[i]}));
}
function remindText(x){ const s = x.sub, r = nextRenewal(s);
  return {title: `Still using ${s.name}?`, body: `${fmt(s.price)} a ${s.cycle === "yr" ? "year" : "month"}${r && r >= x.at ? `, renews ${dayMonth(r)}` : ""}. Tap an answer.`}; }
let remindT = 0, remindReady = false;
function remindSync(){ if (!window.Capacitor || !notifPlugin()) return; clearTimeout(remindT); remindT = setTimeout(remindApply, 1200); }
async function remindApply(){
  const P = notifPlugin(); if (!P) return;
  try {
    if (!remindReady){ remindReady = true;
      await P.registerActionTypes({types: [{id: "KW_USE", actions: [{id: "lot", title: "A lot"}, {id: "barely", title: "Barely"}, {id: "none", title: "Not at all"}]}]});
      P.addListener("localNotificationActionPerformed", remindAnswer); }
    await P.cancel({notifications: [...REMIND_IDS, ...RENEW_IDS, ...ARRIVE_IDS].map(id => ({id}))});
    const plan = [...remindPlan(), ...renewPlan()], inc = arrivePlan(); if (!plan.length && !inc.length) return;
    await P.schedule({notifications: [...plan.map(x => ({id: x.id, ...remindText(x), schedule: {at: x.at, allowWhileIdle: true}, actionTypeId: "KW_USE", extra: {subId: x.sub.id, cycle: x.cycle}})),
      ...inc.map(x => ({id: x.id, title: x.title, body: x.body, schedule: {at: x.at, allowWhileIdle: true}, extra: {kind: "income"}}))]});
  } catch(e){}
}
// Answering, or opening Subs during the 10 days, ends this month's reminders.
function remindSeen(){ const R = S.remind, c = R && R.on ? remindCycles()[0] : null; if (c && todayMid() >= c.start) R.seen = c.key; }
function remindAnswer(e){
  if (e && e.notification && e.notification.extra && e.notification.extra.kind === "income"){ UI.inbox = false; UI.account = false; UI.biz = false; UI.history = false; UI.stmt = null; UI.share = false; UI.plus = false; S.tab = "month"; render(false); save(); return; }
  const id = e && e.notification && e.notification.extra && e.notification.extra.subId, s = S.subs.find(x => x.id === id);
  UI.inbox = false; UI.account = false; UI.biz = false; UI.history = false; UI.stmt = null; UI.share = false; S.tab = "subs";
  remindSeen(); render(false);
  if (s && ["lot", "barely", "none"].includes(e.actionId)) handleReview(e.actionId, id); else save();
  if (s){ UI.flashSub = id; clearTimeout(UI.flashT); UI.flashT = setTimeout(() => { UI.flashSub = null; }, 1500); render(true);
    const el = document.querySelector(`[data-sub="${id}"]`); if (el) el.scrollIntoView({block: "center"}); }
}
OUT.remindBox = () => {
  if (!notifPlugin()) return "";
  const R = S.remind || {}, c = remindCycles()[0], what = payOn() ? "payday" : "a new month";
  if (R.on) return `<div class="pay-line" data-remind><span>${BELL}<span><b>Reminders are on.</b><br><span class="muted small">${c && R.seen === c.key ? `Done for this month. They start again before the next ${payOn() ? "payday" : "month"}.` : c ? `One question a day at most, from ${dayMonth(c.start)}. They stop when you answer or open this tab.` : ""}</span></span></span><button class="link small" type="button" data-remind-off>Turn off</button></div>`;
  if (R.hide) return `<button class="link small inc-add" type="button" data-remind-on data-remind>${BELL.replace('width="18" height="18"', 'width="16" height="16" style="vertical-align:-3px;margin-right:6px"')}Remind me before ${esc(what)}</button>`;
  return `<section class="card remind-card" data-remind><p class="label">Before ${esc(what)}</p><h3>Want a nudge before ${esc(what)}?</h3>
    <p class="muted">In the 10 days before ${esc(what)}, KeepWise asks about one subscription a day, with one-tap answers. It stops as soon as you answer or open this tab, and eases off if you ignore it. A subscription that renews at another time is asked about a week before its charge, and you get one reminder the morning after pay or other income was due, if it has not been logged.</p>
    <div class="grid2"><button class="btn" type="button" data-remind-hide>Not now</button><button class="btn primary" type="button" data-remind-on>Turn on reminders</button></div>
    <p class="muted small">Reminders are set on this phone. Nothing is sent to us.</p></section>`;
};
async function remindTurnOn(){
  const P = notifPlugin(); if (!P) return;
  let ok = false; try { const r = await P.requestPermissions(); ok = !!r && r.display === "granted"; } catch(e){}
  if (!ok){ toast("Notifications are off for KeepWise. You can allow them in your phone’s settings."); return; }
  S.remind = {on: true}; save(); render(true); toast("Reminders are on.");
}
