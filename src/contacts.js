/* ================= phone contacts and groups (kept on this device only) ================= */
// The address book is copied into KeepWise on this device, so the split search can find anyone in it.
// Nothing here is uploaded. People only join your People list when you add them to a split.
const normPhone = p => String(p || "").replace(/[^\d+]/g, "");
const showPhone = p => { const d = digits(p); if (/^\+?1\d{10}$/.test(p) || (d.length === 11 && d[0] === "1")) return `+1 (${d.slice(1,4)}) ${d.slice(4,7)}-${d.slice(7)}`; if (d.length === 10 && !String(p).startsWith("+")) return `(${d.slice(0,3)}) ${d.slice(3,6)}-${d.slice(6)}`; return String(p).replace(/^(\+\d{2})(\d{3,4})(\d{3})(\d+)$/, "$1 $2 $3 $4"); };
const digits = p => String(p || "").replace(/\D/g, "");
function mergeContacts(list, source){
  const dir = S.contacts = S.contacts || [];
  const key = c => (c.p[0] ? digits(c.p[0]).slice(-9) : "") || (c.e[0] || "").toLowerCase() || c.n.toLowerCase();
  const seen = new Map(dir.map(c => [key(c), c]));
  let added = 0;
  list.forEach(raw => {
    const n = String(raw.n || "").trim(); if (!n) return;
    const c = {id: uid(), n, p: [...new Set((raw.p || []).map(normPhone).filter(x => digits(x).length >= 5))].slice(0, 3), e: [...new Set((raw.e || []).map(x => String(x).trim().toLowerCase()).filter(x => x.includes("@")))].slice(0, 2)};
    const k = key(c), old = seen.get(k);
    if (old){ old.n = old.n || c.n; old.p = [...new Set([...old.p, ...c.p])].slice(0, 3); old.e = [...new Set([...old.e, ...c.e])].slice(0, 2); return; }
    dir.push(c); seen.set(k, c); added++;
  });
  dir.sort((a, b) => a.n.localeCompare(b.n));
  S.contactsAt = isoDaysAgo(0); S.contactsFrom = source;
  return added;
}
function parseVcf(text){
  const out = []; let cur = null;
  String(text).replace(/\r?\n[ \t]/g, "").split(/\r?\n/).forEach(line => {
    if (/^BEGIN:VCARD/i.test(line)) cur = {n: "", p: [], e: []};
    else if (/^END:VCARD/i.test(line)){ if (cur && cur.n) out.push(cur); cur = null; }
    else if (cur){
      const i = line.indexOf(":"); if (i < 0) return; const k = line.slice(0, i).toUpperCase(), v = line.slice(i + 1).replace(/\\,/g, ",").replace(/\\;/g, ";").trim();
      if (/^FN\b/.test(k)) cur.n = v;
      else if (/^N\b/.test(k) && !cur.n){ const [last, first] = v.split(";"); cur.n = [first, last].filter(Boolean).join(" ").trim(); }
      else if (/(^|\.)TEL\b/.test(k)) cur.p.push(v);
      else if (/(^|\.)EMAIL\b/.test(k)) cur.e.push(v);
    }
  });
  return out;
}
const nativeContacts = () => { const C = window.Capacitor; if (!C) return null; return (C.Plugins && C.Plugins.Contacts) || (C.registerPlugin ? C.registerPlugin("Contacts") : null); };
async function syncContacts(){
  const P = IN_APP ? nativeContacts() : null;
  if (P){  // Android app: read the address book on the phone, with permission
    try {
      const perm = await P.requestPermissions();
      if (perm && perm.contacts && perm.contacts !== "granted" && perm.contacts !== "limited"){ toast("KeepWise needs permission to search your contacts. You can allow it in your phone’s settings."); return; }
      const r = await P.getContacts({projection: {name: true, phones: true, emails: true}});
      const list = (r.contacts || []).map(c => ({n: (c.name && (c.name.display || [c.name.given, c.name.family].filter(Boolean).join(" "))) || "", p: (c.phones || []).map(x => x.number), e: (c.emails || []).map(x => x.address)}));
      const n = mergeContacts(list, "phone"); save(); refreshAfterContacts(); toast(n ? `${S.contacts.length} contacts ready to search.` : "Your contacts are up to date."); return;
    } catch(e){ /* fall through to the picker or a file */ }
  }
  if (navigator.contacts && navigator.contacts.select){  // Chrome on Android: the phone's own picker, choose as many as you like
    try {
      const got = await navigator.contacts.select(["name", "tel", "email"], {multiple: true});
      if (!got || !got.length) return;
      const n = mergeContacts(got.map(c => ({n: (c.name || [])[0], p: c.tel || [], e: c.email || []})), "picker"); save(); refreshAfterContacts();
      toast(`Added ${n} contact${n === 1 ? "" : "s"} to search.`); return;
    } catch(e){ if (e && e.name === "AbortError") return; }
  }
  UI.contactsHelp = true; refreshAfterContacts();  // iPhone and computers: a contacts file
}
function refreshAfterContacts(){ if (splitDraft) { UI.partOpen = true; render(true); } else render(true); }
function forgetContacts(){ S.contacts = []; S.contactsAt = null; S.contactsFrom = null; save(); render(true); toast("Contacts removed from this device."); }
// Turn a contact into a person the first time they join a split.
function personFromContact(c){
  const ph = c.p[0] || "", d = digits(ph).slice(-9);
  const old = S.people.find(p => (d && digits(p.phone).slice(-9) === d) || p.name.toLowerCase() === c.n.toLowerCase());
  if (old){ old.archived = false; if (!old.phone && ph) old.phone = ph; if (!old.email && c.e[0]) old.email = c.e[0]; return old; }
  const p = {id: uid(), name: c.n, phone: ph || undefined, email: c.e[0] || undefined}; S.people.push(p); return p;
}
function contactMatches(q){
  if (!S.contacts || !S.contacts.length || !q) return [];
  const t = q.toLowerCase(), d = digits(q);
  const isPerson = c => S.people.some(p => !p.archived && (p.name.toLowerCase() === c.n.toLowerCase() || (c.p[0] && digits(p.phone).slice(-9) === digits(c.p[0]).slice(-9))));
  return S.contacts.filter(c => (c.n.toLowerCase().includes(t) || c.e.some(e => e.includes(t)) || (d.length >= 3 && c.p.some(p => digits(p).includes(d)))) && !isPerson(c)).slice(0, 20);
}
// ---- groups: the same friends again in one tap ----
function lastSplitPeople(){
  const last = [...S.splits].sort((a, b) => (b.date || "").localeCompare(a.date || ""))[0];
  if (!last) return null; const ids = last.method === "borrow" ? [last.paidBy, ...Object.keys(last.parts)] : Object.keys(last.parts);
  const uniq = [...new Set(ids)].filter(id => S.people.some(p => p.id === id && !p.archived));
  return uniq.length >= 2 ? {name: `Same as ${last.title}`, ids: uniq, last: true} : null;
}
function groupChips(){
  if (CTX().kind === "shared" || splitDraft.method === "borrow") return "";
  const groups = (S.groups || []).map(g => ({...g, ids: g.ids.filter(id => S.people.some(p => p.id === id && !p.archived))})).filter(g => g.ids.length >= 2);
  const last = lastSplitPeople(); if (last && !groups.some(g => g.ids.length === last.ids.length && g.ids.every(id => last.ids.includes(id)))) groups.push(last);
  if (!groups.length) return "";
  return `<div class="group-chips" role="group" aria-label="Add a group">${groups.map(g => { const all = g.ids.every(id => splitDraft.parts[id] !== undefined);
    return `<button type="button" class="gchip${all ? " on" : ""}" ${g.last ? "data-group-last" : `data-group="${esc(g.id)}"`} aria-pressed="${all}">${g.last ? I.redo : I.users}<span>${esc(g.name)}</span><b>${g.ids.length}</b></button>`; }).join("")}</div>`;
}
function addGroup(ids){ const m = splitDraft.method === "equal"; ids.forEach(id => { if (splitDraft.parts[id] === undefined) splitDraft.parts[id] = m ? 1 : ""; }); splitErr = ""; render(true); }
function saveGroupRow(){
  if (CTX().kind === "shared" || splitDraft.method === "borrow") return "";
  const ids = Object.keys(splitDraft.parts).filter(id => id !== CTX().me);
  if (ids.length < 2) return "";
  const exists = (S.groups || []).some(g => g.ids.length === ids.length && ids.every(id => g.ids.includes(id)));
  if (exists) return "";
  if (UI.groupName !== undefined) return `<div class="group-save"><input data-group-name placeholder="Group name, e.g. Movie crew" value="${esc(UI.groupName)}" enterkeyhint="done" aria-label="Group name"><button class="btn small" type="button" data-group-save>Save</button><button class="link plain small" type="button" data-group-cancel>Cancel</button></div>`;
  return `<button class="link plain small group-save-link" type="button" data-group-new>${I.users}Save these ${ids.length + 1} as a group</button>`;
}
function contactsCard(){
  const n = (S.contacts || []).length;
  if (UI.contactsHelp) return `<div class="card contacts-card"><b>Add your contacts from a file</b>
    <p class="muted small">${IS_IOS ? "On iPhone, open iCloud.com on a computer, go to Contacts, select all, then choose Export vCard. Send the file to this phone and pick it here." : "Export your contacts as a vCard (.vcf) file from your phone or email app, then pick it here."} KeepWise reads the file on this device and keeps names, phone numbers and emails only for searching.</p>
    <div class="grid2"><button class="btn" type="button" data-contacts-help-close>Not now</button><button class="btn primary" type="button" data-contacts-file>Choose a contacts file</button></div></div>`;
  if (!n) return `<button class="w-choice contacts-cta" type="button" data-contacts-sync><span class="w-ic">${I.users}</span><span><b>Find friends from your contacts</b><span class="muted small">Search your phone contacts when you add people to a split. They stay on this phone.</span></span>${I.chev}</button>`;
  return `<div class="contacts-on"><span class="w-ic">${I.users}</span><div class="co-txt"><b>${n} contact${n === 1 ? "" : "s"} ready to search</b><span class="muted small">They stay on this phone.</span></div><div class="co-act"><button class="link small" type="button" data-contacts-sync>Refresh</button><button class="link plain small" type="button" data-contacts-forget>Remove</button></div></div>`;
}
