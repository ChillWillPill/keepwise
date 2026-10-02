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
const TELL_FOOT = "\nTracked with KeepWise: https://chillwillpill.github.io/keepwise/";
function tellGroup(x, kind){
  if (kind === "delete") return `${x.title} was removed. It no longer counts for anyone.`;
  const sh = shares(x), who = id => id === "me" ? "Me" : tellName(id);
  return `${x.title}${kind === "edit" ? " (updated)" : ""}: ${fmt(x.amount)}, paid by ${x.paidBy === "me" ? "me" : tellName(x.paidBy)}.\n${Object.keys(sh).map(id => `${who(id)}: ${fmt(sh[id])}`).join("\n")}${TELL_FOOT}`;
}
function tellAbout(kind, x, old){  // kind: add, edit, delete
  if (S.splitMode === "shared" || !x) { UI.tell = null; return; }
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
  if (S.splitMode === "shared"){ UI.tell = null; return; }
  const name = tellName(pid);
  UI.tell = {kind: "settle", title: name, at: null, group: null, each: false,
    rows: [{id: pid, name, text: gotPaid ? `Got your ${fmt(amount)}, thank you. We are all square.` : `I paid you ${fmt(amount)}. We are all square.`}]};
}
const TELL_HEAD = {add: t => `Let everyone in ${t} know`, edit: t => `${t} changed. Let them know`, delete: t => `${t} was deleted. Let them know`, settle: t => `Let ${t} know`};
function tellCard(){
  const t = UI.tell; if (!t || splitDraft) return "";
  const one = t.rows.length === 1, row = r => `<div class="tell-row" data-tell-id="${esc(r.id)}"><div class="tell-txt"><b>${esc(r.name)}</b><span class="muted small">${esc(r.text.replace(TELL_FOOT, ""))}</span></div><button class="btn small${r.sent ? " done" : ""}" type="button" data-tell-send aria-label="Send to ${esc(r.name)}">${r.sent ? "✓ Sent" : "Send"}</button></div>`;
  return `<section class="card tell-card" data-tell><div class="inline" style="justify-content:space-between"><p class="label">Tell them</p><button class="link plain small" type="button" data-tell-close>${t.rows.every(r => r.sent) || t.groupSent ? "Done" : "Not now"}</button></div>
    <h3>${esc(TELL_HEAD[t.kind](t.title))}</h3>
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
