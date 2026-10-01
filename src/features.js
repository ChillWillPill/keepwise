/* ================= monthly statements (made and kept on this device) ================= */
const monthKey = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
const keyDate = k => { const [y, m] = k.split("-").map(Number); return new Date(y, m - 1, 1); };
const keyLabel = (k, short) => keyDate(k).toLocaleString("en-US", short ? {month:"short"} : {month:"long", year:"numeric"});
const shiftKey = (k, n) => { const d = keyDate(k); d.setMonth(d.getMonth() + n); return monthKey(d); };
const inMonth = (iso, k) => !!iso && iso.slice(0, 7) === k;
// What a month looked like, saved as you go. Past months stop changing once the plan moves on to the next month.
function buildStatement(){
  const C = compute(), k = C.planKey;
  const live = S.subs.map(s => { const w = swapFor("sub", s.id); return {n: s.name, m: r2(w ? +w.altCost : subMonthly(s)), k: s.keep}; });
  const lines = S.expenses.map(e => { const w = swapFor("expense", e.id); return {n: e.name, a: r2(w ? +w.altCost : +e.amount || 0), e: e.env}; });
  const swaps = S.swaps.filter(w => w.on && linkedItem(w)).map(w => ({t: w.title || linkedItem(w).name, a: w.alt, s: r2(swapSaving(w))}));
  const splits = S.splits.filter(x => inMonth(x.date, k)), pays = (S.settlements || []).filter(x => inMonth(x.date, k));
  const old = (S.statements || {})[k] || {};
  const inc = (S.extras || []).length ? [{n: "Regular pay", a: r2(+S.income || 0)}, ...S.extras.map(x => ({n: x.name, a: r2(extraMonthly(x)), got: r2(gotIn(x, k))}))] : undefined;
  return {key: k, updated: isoDaysAgo(0), income: r2(C.income), incomeLines: inc, confirmed: old.confirmed, actual: old.actual, needs: r2(C.needs), misc: r2(C.misc), kept: r2(C.savings),
    setAside: r2(C.setAside), efSaved: r2(S.efSaved), cur: S.cur, lines, subs: live, swaps,
    splits: {count: splits.length, total: r2(splits.reduce((a, x) => a + (+x.amount || 0), 0))},
    settled: {count: pays.length, total: r2(pays.reduce((a, x) => a + (+x.amount || 0), 0))}};
}
function recordStatement(){
  if (UI.welcome != null) return;  // nothing to record while setting up
  try { const st = buildStatement(); S.statements = S.statements || {}; const old = S.statements[st.key];
    if (old && old.example) return;
    S.statements[st.key] = st; } catch(e){}
}
const statementKeys = () => Object.keys(S.statements || {}).sort().reverse();
const currentKey = () => compute().planKey;
function keptBars(keys){
  const list = keys.slice(0, 6).reverse(), vals = list.map(k => keptOf(S.statements[k])), max = Math.max(1, ...vals.map(Math.abs));
  return `<div class="hist-bars" role="img" aria-label="Money kept, last ${list.length} months">${list.map((k, i) => { const v = vals[i];
    return `<button type="button" class="hist-col" data-stmt="${k}" aria-label="${esc(keyLabel(k))}: kept ${fmt(v)}"><span class="hist-v tnum ${v < 0 ? "bad" : ""}">${fmt(v)}</span><span class="hist-bar ${v < 0 ? "neg" : ""}${k === currentKey() ? " now" : ""}" style="height:${Math.max(6, Math.abs(v) / max * 96)}px"></span><span class="hist-m">${esc(keyLabel(k, true))}</span></button>`; }).join("")}</div>`;
}
OUT.historyCard = () => {
  const keys = statementKeys(); if (!keys.length) return "";
  const cur = S.statements[keys[0]], prev = S.statements[keys[1]];
  const diff = prev ? cur.kept - keptOf(prev) : 0;
  return `<section class="card"><div class="inline" style="justify-content:space-between;align-items:baseline"><h2>Monthly statements</h2>${keys.some(k => S.statements[k].example) ? `<span class="pill grey">Example</span>` : ""}</div>
    ${keys.length > 1 ? keptBars(keys) : `<div class="st-one"><span class="muted small">${esc(keyLabel(keys[0]))} so far</span><b class="tnum ${cur.kept < 0 ? "bad" : "good"}">${fmt(cur.kept)} kept</b></div>`}
    <p class="small ${diff > 0.005 ? "good" : "muted"}">${prev ? (Math.abs(diff) < 0.005 ? `Same as ${keyLabel(prev.key, true)}.` : diff > 0 ? `On track to keep ${fmt(diff)} more than ${keyLabel(prev.key).split(" ")[0]}.` : `${fmt(-diff)} less than ${keyLabel(prev.key).split(" ")[0]} so far.`) : "KeepWise writes a statement for every month. Your first one is in progress."}</p>
    <button class="btn" type="button" data-history>See all statements</button></section>`;
};
V.history = () => {
  const keys = statementKeys(), now = currentKey();
  return `<div class="inline" style="justify-content:space-between"><h1>Statements</h1><button class="btn small" type="button" data-history-close>Done</button></div>
  <p class="muted">A statement for every month, written by KeepWise on this device. Nothing is uploaded.</p>
  ${keys.length ? `${keys.length > 1 ? `<section class="card">${keptBars(keys)}</section>` : ""}
  <div class="rows">${keys.map(k => { const s = S.statements[k];
    return `<button type="button" class="row stmt-row" data-stmt="${k}"><div class="row-top"><div><div class="name">${esc(keyLabel(k))}</div><div class="muted small">${k === now ? "In progress" : "Closed"}${s.example ? " · Example" : ""} · ${fmt(s.income)} in, ${fmt(s.needs + s.misc)} out</div></div>
      <div class="inline" style="gap:6px"><span class="name tnum ${keptOf(s) < 0 ? "bad" : "good"}">${fmt(keptOf(s))}</span>${I.chev}</div></div></button>`; }).join("")}</div>` : `<p class="empty">No statements yet. Your first one starts this month.</p>`}`;
};
V.statement = () => {
  const s = S.statements && S.statements[UI.stmt]; if (!s) { UI.stmt = null; return V.history(); }
  const f = fmt;  // statements use the currency you have selected, like every other number
  const open = s.key === currentKey(), out = s.needs + s.misc;
  const row = (a, b, cls) => `<div class="st-line"><span>${a}</span><span class="tnum ${cls || ""}">${b}</span></div>`;
  const live = s.subs.filter(x => x.k !== "drop"), dropped = s.subs.filter(x => x.k === "drop");
  return `<div class="inline no-print" style="justify-content:space-between"><button class="btn small" type="button" data-stmt-back>${I.chevl}Statements</button><button class="btn small" type="button" data-stmt-print>${IN_APP ? "Download" : "Print or save PDF"}</button></div>
  <article class="stmt" aria-label="Statement for ${esc(keyLabel(s.key))}">
    <header class="st-head"><div class="st-brand"><b class="wordmark">Keep<span>Wise</span></b><span class="muted small">Monthly statement</span></div>
      <h2 class="st-title">${esc(keyLabel(s.key))}</h2><span class="st-status small ${open ? "open" : ""}">${open ? `In progress · updated ${esc(shortDate(s.updated))}` : `Closed · final numbers from ${esc(shortDate(s.updated))}`}</span></header>
    ${s.example ? `<p class="note small">This is an example statement. Your own appear here as the months go by.</p>` : ""}
    <div class="st-sum"><div><span class="label">In</span><b class="tnum">${f(s.income)}</b></div><div><span class="label">Out</span><b class="tnum">${f(out)}</b></div><div><span class="label">Kept</span><b class="tnum ${keptOf(s) < 0 ? "bad" : "good"}">${f(keptOf(s))}</b></div></div>
    ${s.actual != null && Math.abs(s.actual - s.kept) > 0.005 ? `<p class="muted small" style="margin-top:-8px">You confirmed ${f(s.actual)} kept. The plan was ${f(s.kept)}.</p>` : ""}
    ${s.incomeLines ? `<section><h3>What came in</h3>${s.incomeLines.map(l => row(esc(l.n), f(l.a) + (l.got != null ? ` <span class="muted small">(${f(l.got)} received)</span>` : ""))).join("")}</section>` : ""}
    <section><h3>What went out</h3>
      ${s.lines.filter(l => l.e === "needs").map(l => row(esc(l.n), f(l.a))).join("")}
      ${row("<b>Expenditures</b>", `<b>${f(s.needs)}</b>`)}
      ${s.lines.filter(l => l.e !== "needs").map(l => row(esc(l.n), f(l.a))).join("")}
      ${live.length ? row(`Subscriptions (${live.length})`, f(live.reduce((a, x) => a + x.m, 0))) : ""}
      ${row("<b>Miscellaneous</b>", `<b>${f(s.misc)}</b>`)}</section>
    ${s.subs.length ? `<section><h3>Subscriptions</h3>${live.map(x => row(esc(x.n), f(x.m) + "/mo")).join("")}${dropped.length ? dropped.map(x => row(`${esc(x.n)} <span class="pill flag">Dropped</span>`, `<s class="muted">${f(x.m)}</s>`)).join("") : ""}</section>` : ""}
    ${s.swaps.length ? `<section><h3>Cheaper swaps in use</h3>${s.swaps.map(x => row(`${esc(x.t)} → ${esc(x.a)}`, `<span class="good">${f(x.s)}/mo kept</span>`)).join("")}</section>` : ""}
    <section><h3>Savings</h3>${row("Set aside this month", f(s.setAside))}${row("Emergency fund balance", f(s.efSaved))}</section>
    ${s.splits.count || s.settled.count ? `<section><h3>Splits</h3>${s.splits.count ? row(`${s.splits.count} new split${s.splits.count > 1 ? "s" : ""}`, f(s.splits.total)) : ""}${s.settled.count ? row(`${s.settled.count} payment${s.settled.count > 1 ? "s" : ""} settled`, f(s.settled.total)) : ""}</section>` : ""}
    <footer class="st-foot muted small">Written by KeepWise on your device from the numbers in your plan. Estimates, not financial advice.</footer>
  </article>`;
};
function statementFile(){
  const css = [...document.querySelectorAll("style")].map(x => x.textContent).join("\n");
  const art = document.querySelector(".stmt"); if (!art) return;
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>KeepWise statement ${esc(keyLabel(UI.stmt))}</title><style>${css}body{padding:16px;background:#fff}</style></head><body>${art.outerHTML}</body></html>`;
  saveFile(new Blob([html], {type:"text/html"}), `keepwise-statement-${UI.stmt}.html`);
}

/* ================= renewals ================= */
const daysInMonth = (y, m) => new Date(y, m + 1, 0).getDate();
function nextRenewal(s){
  const t = todayMid();
  if (s.cycle === "yr"){
    if (!s.renewDate) return null; const [y, m, d] = s.renewDate.split("-").map(Number); let r = new Date(y, m - 1, d);
    while (r < t) r.setFullYear(r.getFullYear() + 1); return r;
  }
  if (!s.renewDay) return null;
  let r = new Date(t.getFullYear(), t.getMonth(), Math.min(s.renewDay, daysInMonth(t.getFullYear(), t.getMonth())));
  if (r < t) r = new Date(t.getFullYear(), t.getMonth() + 1, Math.min(s.renewDay, daysInMonth(t.getFullYear(), t.getMonth() + 1)));
  return r;
}
const daysUntil = d => Math.round((d - todayMid()) / DAY);
const whenLabel = n => n === 0 ? "Today" : n === 1 ? "Tomorrow" : `In ${n} days`;
function setRenewalFrom(s, iso){  // iso date of a charge
  if (!iso) return; const [y, m, d] = iso.split("-").map(Number);
  if (s.cycle === "yr") s.renewDate = isoOf(new Date(y + 1, m - 1, d)); else s.renewDay = d;
}
OUT.comingUp = () => {
  const soon = S.subs.map(s => ({s, d: nextRenewal(s)})).filter(x => x.d && daysUntil(x.d) <= 7).sort((a, b) => a.d - b.d);
  const arriving = (S.extras || []).map(x => ({x, d: nextIncome(x)})).filter(v => v.d && daysUntil(v.d) <= 7).sort((a, b) => a.d - b.d);
  if (!soon.length && !arriving.length) return "";
  const inRows = arriving.map(({x, d}) => `<div class="up-row in"><div class="up-date"><b>${d.getDate()}</b><span>${d.toLocaleString("en-US", {month:"short"})}</span></div>
        <div class="up-main"><div class="name">${esc(x.name)}</div><div class="small good">${whenLabel(daysUntil(d))} · money in</div></div><div class="tnum name good">+${fmt(x.amount)}</div></div>`).join("");
  const total = soon.filter(x => x.s.keep !== "drop").reduce((a, x) => a + x.s.price, 0);
  return `<section class="card"><div class="inline" style="justify-content:space-between;align-items:baseline"><h2>Coming up</h2><span class="muted small">Next 7 days</span></div>
    <div class="up-list">${soon.map(({s, d}) => { const n = daysUntil(d), drop = s.keep === "drop";
      return `<div class="up-row${drop ? " drop" : ""}"><div class="up-date"><b>${d.getDate()}</b><span>${d.toLocaleString("en-US", {month:"short"})}</span></div>
        <div class="up-main"><div class="name">${esc(s.name)}</div><div class="small ${drop ? "bad" : "muted"}">${drop ? `You chose to drop it. Cancel before ${n === 0 ? "today ends" : "it renews"}.` : whenLabel(n)}</div></div>
        <div class="tnum name">${fmt(s.price)}</div></div>`; }).join("")}${inRows}</div>
    ${total ? `<p class="small muted">${fmt(total)} will be charged this week.</p>` : ""}
    ${soon.length ? `<div class="linkrow"><button class="link" type="button" data-go="subs">All subscriptions</button></div>` : ""}</section>`;
};

/* ================= how to cancel (official help pages, checked by hand) ================= */
const CANCEL_HELP = [
  [/netflix/i, "https://help.netflix.com/en/node/407"],
  [/spotify/i, "https://support.spotify.com/us/article/cancel-premium/"],
  [/hulu/i, "https://help.hulu.com/article/hulu-cancel-hulu-subscription"],
  [/disney/i, "https://help.disneyplus.com/article/disneyplus-account-management-faq"],
  [/youtube/i, "https://support.google.com/youtube/answer/6308278"],
  [/google one/i, "https://support.google.com/googleone/answer/9056360"],
  [/apple|icloud|itunes/i, "https://support.apple.com/en-us/118428"],
  [/adobe|photoshop|lightroom|acrobat/i, "https://helpx.adobe.com/manage-account/using/cancel-subscription.html"],
  [/chatgpt|openai/i, "https://help.openai.com/en/articles/7232927-how-do-i-cancel-my-chatgpt-plus-subscription"],
  [/claude|anthropic/i, "https://support.claude.com/en/articles/8325617-cancel-your-pro-or-max-subscription"],
  [/audible/i, "https://help.audible.com/s/article/cancel-membership?language=en_US"],
  [/amazon prime|prime video|^prime\b/i, "https://www.amazon.com/gp/help/customer/display.html?nodeId=TvpAfjoQat32uK1VwP"],
  [/paramount/i, "https://support.paramountplus.com/s/article/PI-How-do-I-cancel-my-subscription?language=en_US"],
  [/peacock/i, "https://www.peacocktv.com/help/article/cancellation"],
  [/microsoft 365|office 365/i, "https://support.microsoft.com/en-us/accounts-billing/subscriptions/cancel-a-microsoft-365-subscription"],
  [/duolingo/i, "https://www.duolingo.com/help/cancel-my-super-duolingo-subscription"],
  [/dropbox/i, "https://help.dropbox.com/plans/downgrade-dropbox-individual-plans"],
  [/uber one/i, "https://help.uber.com/en/riders/article/how-can-i-cancel-my-uber-one-membership?nodeId=8f62fc7a-6cc9-4ac7-a59a-3f5627bf616c"],
  [/dashpass|doordash/i, "https://help.doordash.com/en-us/consumers/article/how-do-i-cancel-my-dashpass-subscription"],
  [/playstation|ps plus/i, "https://www.playstation.com/en-us/support/subscriptions/cancel-playstation-plus/"],
  [/linkedin/i, "https://www.linkedin.com/help/linkedin/answer/a545578"],
  [/peloton/i, "https://support.onepeloton.com/s/article/Peloton-Membership-How-to-Manage-Your-All-Access-Membership?language=en_US"]
];
const cancelHelp = name => { const hit = CANCEL_HELP.find(([re]) => re.test(name)); return hit ? hit[1] : null; };
function cancelLink(s){
  const url = cancelHelp(s.name);
  return url ? `<a class="cancel-link" href="${url}" target="_blank" rel="noopener">How to cancel ${esc(s.name)}${I.ext}</a>`
             : `<a class="cancel-link" href="https://www.google.com/search?q=${encodeURIComponent("how to cancel " + s.name)}" target="_blank" rel="noopener">Find how to cancel${I.ext}</a>`;
}

/* ================= files: backup, restore, saving ================= */
async function saveFile(blob, name){
  try {
    const file = new File([blob], name, {type: blob.type});
    if (IN_APP && navigator.canShare && navigator.canShare({files: [file]})){ await navigator.share({files: [file], title: name}); return true; }
  } catch(e){ if (e && e.name === "AbortError") return false; }
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500); return true;
}
async function downloadBackup(){
  const data = JSON.parse(JSON.stringify(S)); delete data.tab;
  const body = JSON.stringify({app: "KeepWise", kind: "backup", version: 1, made: new Date().toISOString(), data}, null, 1);
  const ok = await saveFile(new Blob([body], {type: "application/json"}), `keepwise-backup-${isoDaysAgo(0)}.json`);
  if (ok){ S.lastBackup = isoDaysAgo(0); save(); render(true); toast("Backup saved. Keep the file somewhere safe."); }
}
function readBackup(text){
  let j; try { j = JSON.parse(text); } catch(e){ throw new Error("That file isn’t a KeepWise backup."); }
  const d = j && j.app === "KeepWise" && j.kind === "backup" ? j.data : null;
  if (!d || d.v !== 1 || !Array.isArray(d.expenses) || !Array.isArray(d.subs) || !Array.isArray(d.splits) || typeof d.env !== "object")
    throw new Error("That file isn’t a KeepWise backup.");
  return {data: d, made: j.made};
}
OUT.backupBox = () => {
  if (UI.restore) return `<div class="note"><p><b>Replace everything on this device</b> with the backup from ${esc(new Date(UI.restore.made || Date.now()).toLocaleDateString("en-US", {month:"long", day:"numeric", year:"numeric"}))}?</p>
    <div class="inline" style="margin-top:10px"><button class="btn" type="button" data-restore-no>Keep what’s here</button><button class="btn primary" type="button" data-restore-yes>Restore backup</button></div></div>`;
  const b = S.lastBackup, d = b ? daysSince(b) : null;
  return `<div class="backup ${b && d <= 30 ? "" : "due"}"><div><b>${b ? `Last backup ${d === 0 ? "today" : d === 1 ? "yesterday" : `${d} days ago`}` : "No backup yet"}</b><span class="muted small">A backup is a file with everything in KeepWise. Restore it on any phone or browser.</span></div>
    <div class="grid2"><button class="btn" type="button" data-backup>${I.download}Download a backup</button><button class="btn" type="button" data-restore>Restore from a backup</button></div></div>`;
};
// iPhone clears website data after about a week away unless the site is on the Home Screen.
const IS_IOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const STANDALONE = (window.matchMedia && matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;
let installEvt = null;
window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); installEvt = e; if (S.tab === "plan" || S.tab === "month") refreshOuts(); });
OUT.keepSafe = () => {
  if (IN_APP || STANDALONE) return "";
  if (IS_IOS && !S.a2hsHide) return `<div class="note keep-safe"><div><b>Keep your data safe on iPhone</b><p class="small">Safari can clear website data after about a week away. Tap ${I.share}<b>Share</b>, then <b>Add to Home Screen</b>.</p></div><button class="link plain" type="button" data-a2hs-hide>Got it</button></div>`;
  const real = !S.example && (S.expenses.length || S.subs.length || S.splits.length) && daysSince(S.started) >= 3;  // give a new person a few days first
  if (real && (!S.lastBackup || daysSince(S.lastBackup) > 30) && !(S.backupSnooze && daysSince(S.backupSnooze) < 30))
    return `<div class="note keep-safe"><div><b>${S.lastBackup ? "Time for a fresh backup" : "Back up your KeepWise data"}</b><p class="small">Everything lives on this device. A backup file keeps it safe if you clear your browser or change phones.</p></div><div class="inline" style="flex-direction:column;align-items:flex-end;gap:6px"><button class="btn small" type="button" data-backup style="white-space:nowrap">Back up</button><button class="link plain small" type="button" data-backup-later>Later</button></div></div>`;
  return "";
};
OUT.installBtn = () => installEvt && !STANDALONE ? `<button class="btn" type="button" data-install>${I.download}Install KeepWise on this device</button>` : "";

/* ================= share what you found (image made on this device) ================= */
function shareFacts(){
  const C = compute(), dropped = S.subs.filter(s => s.keep === "drop"), droppedAmt = dropped.reduce((a, s) => a + subMonthly(s), 0);
  const swapsOn = S.swaps.filter(w => w.on).reduce((a, w) => a + swapSaving(w), 0);
  if (droppedAmt + swapsOn >= 1) return {kicker: "With KeepWise I cut", amount: droppedAmt + swapsOn, line: `${dropped.length ? `${dropped.length} subscription${dropped.length > 1 ? "s" : ""} I didn’t use` : ""}${dropped.length && swapsOn >= 1 ? " and " : ""}${swapsOn >= 1 ? "a few cheaper swaps" : ""}.`};
  if (C.flaggedSave >= 1) return {kicker: "KeepWise found", amount: C.flaggedSave, line: "in subscriptions I barely use."};
  const best = C.inactiveSwaps.reduce((a, x) => a + x.save, 0);
  if (best >= 1) return {kicker: "KeepWise found", amount: best, line: "I could keep with cheaper swaps."};
  return null;
}
async function drawShareCard(F){
  const W = 1080, H = 1080, c = document.createElement("canvas"); c.width = W; c.height = H; const g = c.getContext("2d");
  try { await Promise.all(["600 150px Fraunces", "700 44px Figtree", "500 40px Figtree"].map(f => document.fonts.load(f))); } catch(e){}
  const ser = 'Fraunces, Georgia, serif', sans = 'Figtree, system-ui, sans-serif';
  g.fillStyle = "#f3efe6"; g.fillRect(0, 0, W, H);
  const rr = (x, y, w, h, r) => { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); };
  g.fillStyle = "#fbf8f2"; rr(70, 70, W - 140, H - 140, 56); g.fill(); g.strokeStyle = "#e0d5c5"; g.lineWidth = 3; g.stroke();
  const logo = document.querySelector("img.logo");
  if (logo && logo.complete) { g.save(); g.beginPath(); g.arc(178, 182, 58, 0, Math.PI * 2); g.clip(); g.drawImage(logo, 120, 124, 116, 116); g.restore(); }
  g.textBaseline = "alphabetic"; g.font = `700 54px ${ser}`; g.fillStyle = "#0e8571"; g.fillText("Keep", 262, 200); const kw = g.measureText("Keep").width; g.fillStyle = "#a57d2c"; g.fillText("Wise", 262 + kw, 200);
  g.fillStyle = "#4d564e"; g.font = `500 44px ${sans}`; g.fillText(F.kicker, 130, 430);
  const amt = new Intl.NumberFormat("en-US", {style: "currency", currency: S.cur, maximumFractionDigits: F.amount % 1 < 0.005 ? 0 : 2, minimumFractionDigits: F.amount % 1 < 0.005 ? 0 : 2}).format(r2(F.amount));
  let size = 190; g.font = `600 ${size}px ${ser}`; while (g.measureText(amt).width > W - 260 && size > 80){ size -= 8; g.font = `600 ${size}px ${ser}`; }
  g.fillStyle = "#1b6843"; g.fillText(amt, 124, 430 + size * 0.95);
  g.fillStyle = "#1c2420"; g.font = `600 52px ${sans}`; g.fillText("a month", 130, 430 + size * 0.95 + 80);
  g.fillStyle = "#4d564e"; g.font = `500 40px ${sans}`;
  const words = F.line.split(" "); let ln = "", y = 430 + size * 0.95 + 150;
  for (const w of words){ const t = ln ? ln + " " + w : w; if (g.measureText(t).width > W - 260){ g.fillText(ln, 130, y); ln = w; y += 54; } else ln = t; } if (ln) g.fillText(ln, 130, y);
  g.fillStyle = "#1b6843"; g.font = `600 40px ${sans}`; g.fillText(`That’s ${new Intl.NumberFormat("en-US", {style: "currency", currency: S.cur, maximumFractionDigits: 0}).format(Math.round(F.amount * 12))} a year.`, 130, y + 76);
  g.fillStyle = "#e0d5c5"; g.fillRect(130, H - 220, W - 260, 3);
  { const foot = "Free and private. It stays on your phone."; let fs = 36; g.font = `500 ${fs}px ${sans}`; while (g.measureText(foot).width > W - 260 && fs > 22){ fs -= 2; g.font = `500 ${fs}px ${sans}`; } g.fillStyle = "#4d564e"; g.fillText(foot, 130, H - 150); }
  return new Promise(ok => c.toBlob(b => ok(b), "image/png"));
}
const SHARE = {blob: null, url: "", facts: null};
async function openShare(){
  const F = shareFacts(); if (!F) { toast("Drop a subscription or turn on a swap first, then share what you saved."); return; }
  SHARE.facts = F; SHARE.blob = await drawShareCard(F); if (SHARE.url) URL.revokeObjectURL(SHARE.url); SHARE.url = URL.createObjectURL(SHARE.blob);
  UI.share = true; render(false);
}
V.share = () => `<div class="inline" style="justify-content:space-between"><h1>Share</h1><button class="btn small" type="button" data-share-close>Done</button></div>
  <img class="share-img" src="${SHARE.url}" alt="${esc(SHARE.facts.kicker)} ${fmt(SHARE.facts.amount)} a month">
  <p class="muted small" style="text-align:center">Only this amount is shown. No names, no income, no list of what you pay for.</p>
  <div class="grid2"><button class="btn" type="button" data-share-save>${I.download}Save image</button><button class="btn primary" type="button" data-share-go>${I.share}Share</button></div>`;
async function doShare(){
  const file = new File([SHARE.blob], "keepwise.png", {type: "image/png"});
  const text = `${SHARE.facts.kicker} ${fmt(SHARE.facts.amount)} a month. ${SITE_URL}`;
  try {
    if (navigator.canShare && navigator.canShare({files: [file]})) { await navigator.share({files: [file], text}); return; }
    if (navigator.share) { await navigator.share({text}); return; }
  } catch(e){ if (e && e.name === "AbortError") return; }
  saveFile(SHARE.blob, "keepwise.png"); toast("Image saved. Attach it to your post.");
}

/* ================= first-run setup ================= */
const WELCOME_KEY = "keepwise-welcome-done";
const welcomeDone = () => { try { localStorage.setItem(WELCOME_KEY, "1"); } catch(e){} };
const DRAFT = {cur: "USD", income: "", home: ""};
V.welcome = () => {
  const step = UI.welcome, dots = n => `<div class="w-dots" aria-label="Step ${n} of 3">${[1,2,3].map(i => `<i class="${i <= n ? "on" : ""}"></i>`).join("")}</div>`;
  if (step === 0) return `<div class="welcome"><img class="w-logo" src="${document.querySelector("img.logo").src}" alt="">
    <h1 class="w-title">See what you keep.</h1><p class="w-sub">KeepWise shows where your money goes each month and where to keep more of it.</p>
    <ul class="w-points">
      <li>${I.subs}<span><b>Finds subscriptions</b> you forgot you pay for</span></li>
      <li>${I.cheaper}<span><b>Shows cheaper swaps</b> for what you already buy</span></li>
      <li>${I.split}<span><b>Splits bills</b> with friends and family</span></li></ul>
    <p class="w-safe">${I.lock}Everything stays on your phone. No bank login.</p>
    <button class="btn primary w-cta" type="button" data-w-next>Set up my month</button>
    <button class="link plain w-alt" type="button" data-w-example>Look around with an example first</button></div>`;
  if (step === 1) return `<div class="welcome">${dots(1)}<h1 class="w-title">What comes in each month?</h1><p class="w-sub">Your take-home pay after tax, from everything you earn.</p>
    <label class="field"><span>Currency</span><select data-w="cur">${CURRENCIES.map(([c, n]) => `<option value="${c}" ${c === DRAFT.cur ? "selected" : ""}>${c} · ${n}</option>`).join("")}</select></label>
    <label class="field"><span>Money coming in</span><span class="money-in w-big"><em>${esc((() => { try { return new Intl.NumberFormat("en-US", {style:"currency", currency: DRAFT.cur, maximumFractionDigits:0}).formatToParts(0).find(p => p.type === "currency").value; } catch(e){ return "$"; } })())}</em><input data-w="income" inputmode="decimal" enterkeyhint="next" placeholder="0" value="${esc(DRAFT.income)}" aria-label="Money coming in each month"></span></label>
    <button class="btn primary w-cta" type="button" data-w-next>Continue</button><button class="link plain w-alt" type="button" data-w-back>Back</button></div>`;
  if (step === 2) return `<div class="welcome">${dots(2)}<h1 class="w-title">What do you pay for your home?</h1><p class="w-sub">Rent or mortgage each month. Usually the biggest bill.</p>
    <label class="field"><span>Rent or mortgage</span><span class="money-in w-big"><em>${esc((() => { try { return new Intl.NumberFormat("en-US", {style:"currency", currency: DRAFT.cur, maximumFractionDigits:0}).formatToParts(0).find(p => p.type === "currency").value; } catch(e){ return "$"; } })())}</em><input data-w="home" inputmode="decimal" enterkeyhint="next" placeholder="0" value="${esc(DRAFT.home)}" aria-label="Rent or mortgage each month"></span></label>
    <button class="btn primary w-cta" type="button" data-w-next>Continue</button><button class="link plain w-alt" type="button" data-w-skip>I don’t pay rent</button><button class="link plain w-alt" type="button" data-w-back>Back</button></div>`;
  return `<div class="welcome">${dots(3)}<h1 class="w-title">Add the rest your way</h1><p class="w-sub">You can always do the other one later.</p>
    <button class="w-choice" type="button" data-w-import><span class="w-ic">${I.receipt}</span><span><b>Import a bank statement</b><span class="muted small">CSV or PDF. KeepWise finds your bills and every subscription. Read on this phone only.</span></span>${I.chev}</button>
    <button class="w-choice" type="button" data-w-finish><span class="w-ic">${I.plan}</span><span><b>Add things myself</b><span class="muted small">Start with what you entered and add bills as you go.</span></span>${I.chev}</button>
    <button class="link plain w-alt" type="button" data-w-back>Back</button></div>`;
};
function finishWelcome(){
  const ex = example();
  Object.assign(ex, {cur: DRAFT.cur, income: numv(DRAFT.income), efSaved: 0, expenses: numv(DRAFT.home) ? [{id: uid(), name: "Rent or mortgage", amount: numv(DRAFT.home), env: "needs"}] : [],
    subs: [], swaps: [], codes: [], splits: [], settlements: [], people: [{id: "me", name: "You"}], goalName: "", goalAmt: 0, statements: {}, example: false, hideNote: false, tab: "month", started: isoDaysAgo(0)});
  S = ex; UI.welcome = null; welcomeDone(); save();
}
