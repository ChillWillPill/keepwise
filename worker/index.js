// KeepWise API (Cloudflare Worker). Lets the KeepWise app read a business's own sales from Stripe and PayPal.
// The phone sends its own read-only key with each request; it is used once, forwarded, and never stored or logged.
// Only read requests to a short list of endpoints are allowed.

const ORIGINS = [/^https:\/\/mykeepwise\.com$/, /^https:\/\/www\.mykeepwise\.com$/, /^https:\/\/chillwillpill\.github\.io$/, /^capacitor:\/\/localhost$/, /^https?:\/\/localhost(:\d+)?$/, /^null$/];
const STRIPE_PATHS = new Set(["balance", "balance_transactions"]);
const MAX_BODY = 16384;

const cors = origin => ({
  "Access-Control-Allow-Origin": origin && ORIGINS.some(r => r.test(origin)) ? origin : "https://mykeepwise.com",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
  "Vary": "Origin",
});
const reply = (origin, status, body) => new Response(JSON.stringify(body), {status, headers: {"Content-Type": "application/json", "Cache-Control": "no-store", ...cors(origin)}});
const fail = (origin, status, msg) => reply(origin, status, {error: msg});

async function readJson(req){
  const text = await req.text(); if (text.length > MAX_BODY) throw new Error("too big");
  return JSON.parse(text || "{}");
}

async function stripe(origin, b){
  const key = String(b.key || "");
  if (!/^(rk_live_|rk_test_|sk_test_)[A-Za-z0-9]{10,200}$/.test(key)) return fail(origin, 400, "Use a restricted Stripe key (it starts with rk_).");
  const path = String(b.path || ""); if (!STRIPE_PATHS.has(path)) return fail(origin, 400, "Not allowed.");
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(b.query || {})) if (/^(limit|starting_after|created\[gte\]|created\[lte\])$/.test(k) && /^[A-Za-z0-9_]{1,80}$/.test(String(v))) q.set(k, String(v));
  const r = await fetch(`https://api.stripe.com/v1/${path}${q.size ? "?" + q : ""}`, {headers: {Authorization: `Bearer ${key}`, "Stripe-Version": "2024-06-20"}});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return fail(origin, r.status === 401 || r.status === 403 ? 401 : 502, (data.error && data.error.message) || "Stripe didn't answer.");
  return reply(origin, 200, data);
}

async function paypal(origin, b){
  const id = String(b.id || ""), secret = String(b.secret || ""), live = b.env !== "sandbox";
  if (!/^[A-Za-z0-9_-]{20,128}$/.test(id) || !/^[A-Za-z0-9_-]{20,128}$/.test(secret)) return fail(origin, 400, "Check the PayPal Client ID and Secret.");
  const iso = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?Z$/;
  if (!iso.test(String(b.start || "")) || !iso.test(String(b.end || ""))) return fail(origin, 400, "Bad dates.");
  const page = Math.max(1, Math.min(50, +b.page || 1));
  const base = live ? "https://api-m.paypal.com" : "https://api-m.sandbox.paypal.com";
  const t = await fetch(`${base}/v1/oauth2/token`, {method: "POST", headers: {Authorization: "Basic " + btoa(`${id}:${secret}`), "Content-Type": "application/x-www-form-urlencoded"}, body: "grant_type=client_credentials"});
  const tok = await t.json().catch(() => ({}));
  if (!t.ok || !tok.access_token) return fail(origin, 401, "PayPal didn't accept that Client ID and Secret.");
  const q = new URLSearchParams({start_date: b.start, end_date: b.end, fields: "transaction_info,payer_info", page_size: "500", page: String(page)});
  const r = await fetch(`${base}/v1/reporting/transactions?${q}`, {headers: {Authorization: `Bearer ${tok.access_token}`}});
  const data = await r.json().catch(() => ({}));
  if (r.status === 403) return fail(origin, 403, "Turn on Transaction search for this app in the PayPal developer dashboard.");
  if (!r.ok) return fail(origin, 502, data.message || "PayPal didn't answer.");
  return reply(origin, 200, {transaction_details: data.transaction_details || [], total_pages: data.total_pages || 1, page: data.page || page});
}

// ---- Plaid (KeepWise Plus bank connection) ----
// KeepWise keeps no database. Plaid's access token is sealed here with a key only this server has (AES-GCM,
// derived from the Plaid secret) and handed to the phone as an unreadable blob. The phone sends it back to sync;
// on its own it is useless, and the server forgets it after each request.
const PLAID_HOST = env => env.PLAID_ENV === "production" ? "https://production.plaid.com" : "https://sandbox.plaid.com";
const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64u = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), c => c.charCodeAt(0));
async function sealKey(env){
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.PLAID_SECRET), "HKDF", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({name: "HKDF", hash: "SHA-256", salt: new TextEncoder().encode("keepwise-plaid-v1"), info: new TextEncoder().encode(env.PLAID_CLIENT_ID)}, base, {name: "AES-GCM", length: 256}, false, ["encrypt", "decrypt"]);
}
async function seal(env, text){ const iv = crypto.getRandomValues(new Uint8Array(12)), ct = await crypto.subtle.encrypt({name: "AES-GCM", iv}, await sealKey(env), new TextEncoder().encode(text)); const out = new Uint8Array(12 + ct.byteLength); out.set(iv); out.set(new Uint8Array(ct), 12); return b64u(out); }
async function unseal(env, blob){ const all = unb64u(String(blob || "")); if (all.length < 29) throw new Error("bad"); const pt = await crypto.subtle.decrypt({name: "AES-GCM", iv: all.slice(0, 12)}, await sealKey(env), all.slice(12)); return new TextDecoder().decode(pt); }
async function plaidCall(env, path, body){
  const r = await fetch(PLAID_HOST(env) + path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({client_id: env.PLAID_CLIENT_ID, secret: env.PLAID_SECRET, ...body})});
  const data = await r.json().catch(() => ({})); return {ok: r.ok, data};
}
const plaidErr = d => (d && (d.display_message || d.error_message)) || "The bank connection didn't answer. Try again in a minute.";
async function plaid(origin, env, path, b){
  if (!env.PLAID_CLIENT_ID || !env.PLAID_SECRET) return fail(origin, 503, "Bank connection isn't switched on yet.");
  if (path === "/plaid/link"){
    const uid = String(b.uid || ""); if (!/^[a-z0-9]{8,40}$/.test(uid)) return fail(origin, 400, "Bad request.");
    const {ok, data} = await plaidCall(env, "/link/token/create", {client_name: "KeepWise", language: "en", country_codes: ["US"], user: {client_user_id: uid}, products: ["transactions"], transactions: {days_requested: 90}, ...(env.PLAID_REDIRECT ? {redirect_uri: env.PLAID_REDIRECT} : {})});
    return ok ? reply(origin, 200, {link_token: data.link_token, env: env.PLAID_ENV || "sandbox"}) : fail(origin, 502, plaidErr(data));
  }
  if (path === "/plaid/exchange"){
    const pt = String(b.public_token || ""); if (!/^public-[a-z]+-[0-9a-f-]{20,80}$/.test(pt)) return fail(origin, 400, "Bad request.");
    const {ok, data} = await plaidCall(env, "/item/public_token/exchange", {public_token: pt});
    return ok ? reply(origin, 200, {item: await seal(env, data.access_token)}) : fail(origin, 502, plaidErr(data));
  }
  let access; try { access = await unseal(env, b.item); } catch(e){ return fail(origin, 401, "This bank link isn't valid anymore. Disconnect it and connect again."); }
  if (path === "/plaid/sync"){
    const cursor = String(b.cursor || ""); if (cursor.length > 512) return fail(origin, 400, "Bad request.");
    const {ok, data} = await plaidCall(env, "/transactions/sync", {access_token: access, count: 500, ...(cursor ? {cursor} : {})});
    if (!ok) return fail(origin, data.error_code === "ITEM_LOGIN_REQUIRED" ? 409 : 502, plaidErr(data));
    const tx = t => ({id: t.transaction_id, acct: t.account_id, amount: t.amount, date: t.date, name: t.merchant_name || t.name, cur: t.iso_currency_code, pending: !!t.pending});
    return reply(origin, 200, {added: (data.added || []).map(tx), modified: (data.modified || []).map(tx), removed: (data.removed || []).map(t => t.transaction_id), next_cursor: data.next_cursor, has_more: !!data.has_more,
      accounts: (data.accounts || []).map(a => ({id: a.account_id, name: a.official_name || a.name, mask: a.mask, type: a.subtype || a.type, kind: a.type, balance: a.balances && a.balances.current, cur: a.balances && a.balances.iso_currency_code}))});
  }
  if (path === "/plaid/institution"){
    const {ok, data} = await plaidCall(env, "/item/get", {access_token: access});
    return reply(origin, 200, {name: ok && data.item && data.item.institution_name || ""});
  }
  if (path === "/plaid/remove"){ const {ok, data} = await plaidCall(env, "/item/remove", {access_token: access}); return ok ? reply(origin, 200, {removed: true}) : fail(origin, 502, plaidErr(data)); }
  return fail(origin, 404, "Not found.");
}

// ---- KeepWise Plus: email the people in a split ----
// Only a signed-in KeepWise account with a verified email can send, at most 10 people at a time. Each person gets their
// own message (nobody sees the others' addresses), sent by Resend from splits@notify.mykeepwise.com, with replies going to the sender.
const FB_PROJECT = "keepwise-c28c3";
let JWKS = {at: 0, keys: {}};
async function firebaseUser(idToken){
  const parts = String(idToken || "").split("."); if (parts.length !== 3) throw new Error("bad");
  const dec = s => JSON.parse(new TextDecoder().decode(unb64u(s))), head = dec(parts[0]), body = dec(parts[1]), now = Math.floor(Date.now() / 1000);
  if (head.alg !== "RS256" || body.aud !== FB_PROJECT || body.iss !== "https://securetoken.google.com/" + FB_PROJECT || !(body.exp > now) || !(body.iat <= now + 300) || !body.sub) throw new Error("bad");
  if (!JWKS.keys[head.kid] || Date.now() - JWKS.at > 3600e3){ const r = await fetch("https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"); const j = await r.json(); JWKS = {at: Date.now(), keys: Object.fromEntries((j.keys || []).map(k => [k.kid, k]))}; }
  const jwk = JWKS.keys[head.kid]; if (!jwk) throw new Error("bad");
  const key = await crypto.subtle.importKey("jwk", jwk, {name: "RSASSA-PKCS1-v1_5", hash: "SHA-256"}, false, ["verify"]);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, unb64u(parts[2]), new TextEncoder().encode(parts[0] + "." + parts[1]));
  if (!ok) throw new Error("bad"); return body;
}
const escH = s => String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const EMAIL_RE = /^[^\s@<>",;]{1,64}@[^\s@<>",;]{1,190}\.[A-Za-z]{2,24}$/;
function splitMail(from, name, text, title){
  const html = `<!doctype html><html><body style="margin:0;background:#f6f1e7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1c2420">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f1e7;padding:24px 12px"><tr><td align="center">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#ffffff;border-radius:18px;padding:28px">
  <tr><td style="font-size:15px;color:#4d564e">Hi ${escH(name)},</td></tr>
  <tr><td style="padding:12px 0 4px;font-size:20px;font-weight:700;line-height:1.35">${escH(from)} shared a split with you: ${escH(title)}</td></tr>
  <tr><td style="padding:14px 16px;margin-top:12px;background:#f2ede2;border-radius:12px;font-size:16px;line-height:1.5">${escH(text)}</td></tr>
  <tr><td style="padding-top:16px;font-size:14px;color:#4d564e">Reply to this email to answer ${escH(from)} directly.</td></tr>
  <tr><td style="padding-top:22px"><a href="https://mykeepwise.com/?utm_source=split_email" style="display:inline-block;background:#1b6843;color:#fff;text-decoration:none;font-weight:600;padding:12px 18px;border-radius:12px">Split bills free with KeepWise</a></td></tr>
  <tr><td style="padding-top:22px;font-size:12px;color:#8a8f87">Sent by KeepWise because ${escH(from)} added you to a split. KeepWise doesn't keep your address or send you anything else.</td></tr>
  </table></td></tr></table></body></html>`;
  return {html, text: `Hi ${name},\n\n${from} shared a split with you: ${title}\n\n${text}\n\nReply to this email to answer ${from} directly.\n\nSplit bills free with KeepWise: https://mykeepwise.com\n\nSent by KeepWise because ${from} added you to a split. KeepWise doesn't keep your address or send you anything else.`};
}
async function splitEmail(origin, env, b){
  if (!env.RESEND_API_KEY) return fail(origin, 503, "Email isn't switched on yet.");
  let user; try { user = await firebaseUser(b.idToken); } catch(e){ return fail(origin, 401, "Sign in again to send emails."); }
  if (!user.email || !user.email_verified) return fail(origin, 403, "Verify your account email first, then try again.");
  const from = String(b.from || "").replace(/[\r\n<>"]/g, " ").replace(/\s+/g, " ").trim().slice(0, 40) || "A friend", title = String(b.title || "").replace(/[\r\n]/g, " ").trim().slice(0, 60) || "a split";
  const items = (Array.isArray(b.items) ? b.items : []).slice(0, 10).map(x => ({to: String(x.to || "").trim(), name: String(x.name || "").replace(/[\r\n<>]/g, " ").trim().slice(0, 40) || "there", text: String(x.text || "").trim().slice(0, 400)})).filter(x => EMAIL_RE.test(x.to) && x.text);
  if (!items.length) return fail(origin, 400, "Nobody in this split has an email address yet.");
  const batch = items.map(x => { const m = splitMail(from, x.name, x.text, title); return {from: `${from} via KeepWise <splits@notify.mykeepwise.com>`, to: [x.to], reply_to: user.email, subject: `${from} shared a split with you: ${title}`, html: m.html, text: m.text}; });
  const r = await fetch("https://api.resend.com/emails/batch", {method: "POST", headers: {Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json"}, body: JSON.stringify(batch)});
  if (!r.ok){ const d = await r.json().catch(() => ({})); return fail(origin, 502, r.status === 429 ? "Too many emails today. Try again tomorrow." : (d.message || "The email service didn't answer.")); }
  return reply(origin, 200, {sent: items.length});
}

export default {
  async fetch(req, env = {}){
    const origin = req.headers.get("Origin"), url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, {status: 204, headers: cors(origin)});
    if (req.method === "GET" && url.pathname === "/") return new Response("KeepWise API", {headers: {"Content-Type": "text/plain", ...cors(origin)}});
    if (req.method !== "POST") return fail(origin, 405, "Not allowed.");
    if (origin && !ORIGINS.some(r => r.test(origin))) return fail(origin, 403, "Not allowed.");
    let b; try { b = await readJson(req); } catch(e){ return fail(origin, 400, "Bad request."); }
    try {
      if (url.pathname === "/stripe") return await stripe(origin, b);
      if (url.pathname === "/paypal") return await paypal(origin, b);
      if (url.pathname.startsWith("/plaid/")) return await plaid(origin, env, url.pathname, b);
      if (url.pathname === "/split/email") return await splitEmail(origin, env, b);
    } catch(e){ return fail(origin, 502, "That service didn't answer. Try again in a minute."); }
    return fail(origin, 404, "Not found.");
  },
};
