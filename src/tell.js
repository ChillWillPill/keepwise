/* ================= tell them (messages you send yourself; KeepWise sends nothing) ================= */
// After a split on this phone is added, changed, deleted or settled, KeepWise writes a short message for each person in it.
// You send it from your own apps (the phone's share sheet), or copy it. Nothing leaves the phone unless you send it.
const tellOthers = x => x ? [...new Set([x.paidBy, ...Object.keys(x.parts || {})])].filter(id => id !== "me") : [];
const tellName = id => (S.people.find(p => p.id === id) || {}).name || "Someone";
function tellLine(x, id){  // what one split means for one person, written from you to them
  const sh = shares(x), mine = sh.me || 0, theirs = sh[id] || 0;
  if (x.method === "borrow"){ const who = Object.keys(x.parts)[0];
    return x.paidBy === "me" ? (who === id ? `I lent you ${fmt(x.amount)}` : `I lent ${tellName(who)} ${fmt(x.amount)}`)
      : x.paidBy === id ? `you lent ${who === "me" ? "me" : tellName(who)} ${fmt(x.amount)}` : `${tellName(x.paidBy)} lent you ${fmt(x.amount)}`; }
  if (x.paidBy === "me") return `I paid ${fmt(x.amount)}. Your share is ${fmt(theirs)}`;
  if (x.paidBy === id) return mine > 0 ? `you paid ${fmt(x.amount)}. My share is ${fmt(mine)}, so I owe you ${fmt(mine)}` : `you paid ${fmt(x.amount)}`;
  return `${tellName(x.paidBy)} paid ${fmt(x.amount)}. Your share is ${fmt(theirs)}, owed to ${tellName(x.paidBy)}`;
}
const TELL_FOOT = "\nTracked with KeepWise: https://mykeepwise.com/";
function tellGroup(x, kind){
  if (kind === "delete") return `${x.title} was removed. It no longer counts for anyone.`;
  const sh = shares(x), who = id => id === "me" ? "Me" : tellName(id);
  return `${x.title}${kind === "edit" ? " (updated)" : ""}: ${fmt(x.amount)}, paid by ${x.paidBy === "me" ? "me" : tellName(x.paidBy)}.\n${Object.keys(sh).map(id => `${who(id)}: ${fmt(sh[id])}`).join("\n")}${TELL_FOOT}`;
}
function tellAbout(kind, x, old){  // kind: add, edit, delete
  if (shared() || !x) { UI.tell = null; return; }
  const now = tellOthers(x), before = old ? tellOthers(old) : [], rows = [];
  now.forEach(id => {
    let text;
    if (kind === "delete") text = `${x.title} was removed. It no longer counts between us.`;
    else if (kind === "edit"){ const was = before.includes(id) ? (shares(old)[id] || 0) : null, is = shares(x)[id] || 0;
      text = `${x.title} was updated: ${tellLine(x, id)}.${was != null && Math.abs(was - is) > 0.005 && x.method !== "borrow" ? ` Before, your share was ${fmt(was)}.` : ""}`; }
    else text = `${x.title}: ${tellLine(x, id)}.${TELL_FOOT}`;
    rows.push({id, name: tellName(id), text});
  });
  before.filter(id => !now.includes(id)).forEach(id => rows.push({id, name: tellName(id), text: `You are no longer part of ${old.title}. It no longer counts between us.`}));
  if (!rows.length){ UI.tell = null; return; }
  UI.tell = {kind, title: x.title, at: kind === "edit" ? x.id : null, rows, group: now.length >= 2 && x.method !== "borrow" ? tellGroup(x, kind) : null, each: false};
}
function tellSettled(pid, amount, gotPaid){
  if (shared()){ UI.tell = null; return; }
  const name = tellName(pid);
  UI.tell = {kind: "settle", title: name, at: null, group: null, each: false,
    rows: [{id: pid, name, text: gotPaid ? `Got your ${fmt(amount)}, thank you. We are all square.` : `I paid you ${fmt(amount)}. We are all square.`}]};
}
const TELL_HEAD = {add: (t, who) => who ? `Let ${who} know about ${t}` : `Let everyone in ${t} know`, edit: (t, who) => `${t} changed. Let ${who || "them"} know`, delete: (t, who) => `${t} was deleted. Let ${who || "them"} know`, settle: t => `Let ${t} know`};
function tellCard(){
  const t = UI.tell; if (!t || splitDraft) return "";
  const one = t.rows.length === 1, row = r => `<div class="tell-row" data-tell-id="${esc(r.id)}"><div class="tell-txt"><b>${esc(r.name)}</b><span class="muted small">${esc(r.text.replace(TELL_FOOT, ""))}</span></div><button class="btn small${r.sent ? " done" : ""}" type="button" data-tell-send aria-label="Send to ${esc(r.name)}">${r.sent ? "✓ Sent" : "Send"}</button></div>`;
  return `<section class="card tell-card" data-tell><div class="inline" style="justify-content:space-between"><p class="label">Tell them</p><button class="link plain small" type="button" data-tell-close>${t.rows.every(r => r.sent) || t.groupSent ? "Done" : "Not now"}</button></div>
    <h3>${esc(TELL_HEAD[t.kind](t.title, one ? firstWord(t.rows[0].name) : ""))}</h3>
    ${t.group ? `<div class="tell-msg">${esc(t.group.replace(TELL_FOOT, "")).replace(/\n/g, "<br>")}</div>
      <button class="btn primary" type="button" data-tell-all>${I.share}${t.groupSent ? "Sent. Send again" : "Send to everyone"}</button>
      ${t.each ? `<div class="tell-rows">${t.rows.map(row).join("")}</div>` : `<button class="link small" type="button" data-tell-each style="align-self:center">Or tell each person separately</button>`}`
    : one ? `<div class="tell-msg">${esc(t.rows[0].text.replace(TELL_FOOT, ""))}</div><div data-tell-id="${esc(t.rows[0].id)}"><button class="btn primary" type="button" data-tell-send>${I.share}${t.rows[0].sent ? "Sent. Send again" : `Send to ${esc(firstWord(t.rows[0].name))}`}</button></div>`
    : `<div class="tell-rows">${t.rows.map(row).join("")}</div>`}
    <p class="muted small">KeepWise does not message anyone. You send this yourself, from your own apps.</p></section>`;
}
const firstWord = n => String(n || "").trim().split(/\s+/)[0] || "them";
async function tellSend(text, name){
  try { if (navigator.share){ await navigator.share({text}); return true; } }
  catch(e){ if (e && e.name === "AbortError") return false; }
  const said = () => toast(`Copied. Paste it into a message${name ? " to " + name : ""}.`);
  try { await navigator.clipboard.writeText(text); said(); return true; } catch(e){}
  try { const ta = document.createElement("textarea"); ta.value = text; ta.style.cssText = "position:fixed;opacity:0"; document.body.append(ta); ta.select(); const ok = document.execCommand("copy"); ta.remove(); if (ok){ said(); return true; } } catch(e){}
  toast("Couldn’t share or copy that. Press and hold the message to copy it."); return false;
}

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
    await P.cancel({notifications: REMIND_IDS.map(id => ({id}))});
    const plan = remindPlan(); if (!plan.length) return;
    await P.schedule({notifications: plan.map(x => ({id: x.id, ...remindText(x), schedule: {at: x.at, allowWhileIdle: true}, actionTypeId: "KW_USE", extra: {subId: x.sub.id, cycle: x.cycle}}))});
  } catch(e){}
}
// Answering, or opening Subs during the 10 days, ends this month's reminders.
function remindSeen(){ const R = S.remind, c = R && R.on ? remindCycles()[0] : null; if (c && todayMid() >= c.start) R.seen = c.key; }
function remindAnswer(e){
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
    <p class="muted">In the 10 days before ${esc(what)}, KeepWise asks about one subscription a day, with one-tap answers. It stops as soon as you answer or open this tab, and eases off if you ignore it.</p>
    <div class="grid2"><button class="btn" type="button" data-remind-hide>Not now</button><button class="btn primary" type="button" data-remind-on>Turn on reminders</button></div>
    <p class="muted small">Reminders are set on this phone. Nothing is sent to us.</p></section>`;
};
async function remindTurnOn(){
  const P = notifPlugin(); if (!P) return;
  let ok = false; try { const r = await P.requestPermissions(); ok = !!r && r.display === "granted"; } catch(e){}
  if (!ok){ toast("Notifications are off for KeepWise. You can allow them in your phone’s settings."); return; }
  S.remind = {on: true}; save(); render(true); toast("Reminders are on.");
}
