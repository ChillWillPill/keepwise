// ================= accounts (optional; the profile lives in Firebase, money data never leaves this device) =================
// The project's public web config (safe to ship; access is controlled by Firebase security rules).
// Tests can override it with window.KEEPWISE_FIREBASE (null turns accounts off).
const FB_PROJECT = {
  apiKey: "AIzaSyD8vgylgp_MxETFmZrRaw3j-T01ruaYknM",
  authDomain: "keepwise-c28c3.firebaseapp.com",
  projectId: "keepwise-c28c3",
  storageBucket: "keepwise-c28c3.firebasestorage.app",
  messagingSenderId: "514732112999",
  appId: "1:514732112999:web:bb670a443dd04d7b0668c2"
};
const FB_CONFIG = "KEEPWISE_FIREBASE" in window ? window.KEEPWISE_FIREBASE : FB_PROJECT;
const FB_BASE = "https://cdn.jsdelivr.net/npm/firebase@10.14.1/";
const TERMS_VERSION = "2026-09-30";
const IN_APP = !!window.Capacitor; // Google blocks its sign-in page inside app web views
// Inside the Claude preview the page runs in a locked frame where sign-in windows cannot open.
const PREVIEW = !!window.claude && !("KEEPWISE_FIREBASE" in window);
const SITE_URL = "https://chillwillpill.github.io/keepwise/";
const ACC = {state: PREVIEW ? "preview" : FB_CONFIG ? "idle" : "off", user: null, profile: null, mode: "signin", err: "", email: "", draft: {}, del: false, busy: false};
I.user = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/></svg>';
I.google = '<svg viewBox="0 0 24 24" width="18" height="18" style="vertical-align:-4px;margin-right:8px" aria-hidden="true"><path fill="#4285F4" d="M22.5 12.3c0-.8-.1-1.5-.2-2.2H12v4.2h5.9a5 5 0 0 1-2.2 3.3v2.7h3.5c2.1-1.9 3.3-4.7 3.3-8z"/><path fill="#34A853" d="M12 23c3 0 5.5-1 7.3-2.7l-3.5-2.7c-1 .7-2.3 1.1-3.8 1.1-2.9 0-5.4-2-6.3-4.6H2.1v2.8A11 11 0 0 0 12 23z"/><path fill="#FBBC05" d="M5.7 14.1a6.6 6.6 0 0 1 0-4.2V7.1H2.1a11 11 0 0 0 0 9.8z"/><path fill="#EA4335" d="M12 5.4c1.6 0 3.1.6 4.2 1.7l3.1-3.1A11 11 0 0 0 2.1 7.1l3.6 2.8C6.6 7.3 9.1 5.4 12 5.4z"/></svg>';

function loadScript(src){ return new Promise((ok, bad) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = () => bad(new Error("Could not load " + src)); document.head.appendChild(s); }); }
function accInit(){
  if (ACC.state !== "idle") return ACC.ready || Promise.resolve();
  ACC.state = "loading";
  ACC.ready = (async () => {
    try {
      for (const f of ["firebase-app-compat.js", "firebase-auth-compat.js", "firebase-firestore-compat.js"]) await loadScript(FB_BASE + f);
      if (!firebase.apps.length) firebase.initializeApp(FB_CONFIG);
      ACC.auth = firebase.auth(); ACC.db = firebase.firestore();
      await new Promise(done => {
        let first = true;
        ACC.auth.onAuthStateChanged(async u => {
          ACC.user = u; ACC.profile = null; ACC.draft = {}; ACC.del = false;
          if (u) await accLoadProfile();
          S.acctOn = !!u; save(); ACC.state = "ready"; renderAcctBtn();
          if (UI.account) render(true);
          if (first){ first = false; done(); }
        });
      });
    } catch(e){ ACC.state = "error"; renderAcctBtn(); if (UI.account) render(true); }
  })();
  return ACC.ready;
}
async function accLoadProfile(){
  try { const snap = await ACC.db.collection("users").doc(ACC.user.uid).get(); ACC.profile = snap.exists ? snap.data() : {}; }
  catch(e){ ACC.profile = {}; }
}
const accDoc = () => ACC.db.collection("users").doc(ACC.user.uid);
const accComplete = () => !!(ACC.profile && ACC.profile.name && ACC.profile.dob && ACC.profile.termsAcceptedAt);
const accName = () => (ACC.profile && ACC.profile.name) || (ACC.user && ACC.user.displayName) || "";
const accPhoto = () => { const d = ACC.draft; if ("photo" in d) return d.photo || ""; return (ACC.profile && ACC.profile.photo) || (ACC.user && ACC.user.photoURL) || ""; };
function ageOn(dob, now = new Date()){ const b = new Date(dob + "T00:00:00"); if (isNaN(b)) return -1; let a = now.getFullYear() - b.getFullYear(); const m = now.getMonth() - b.getMonth(); if (m < 0 || (m === 0 && now.getDate() < b.getDate())) a--; return a; }
function accErrText(e){
  const c = (e && e.code) || "";
  return ({
    "auth/invalid-email": "That email address doesn’t look right.",
    "auth/missing-password": "Enter your password.",
    "auth/weak-password": "Use at least 8 characters for your password.",
    "auth/email-already-in-use": "An account already uses this email. Sign in instead.",
    "auth/invalid-credential": "The email or password is incorrect.",
    "auth/wrong-password": "The email or password is incorrect.",
    "auth/user-not-found": "The email or password is incorrect.",
    "auth/too-many-requests": "Too many attempts. Wait a few minutes and try again.",
    "auth/network-request-failed": "No connection. Check your internet and try again.",
    "auth/popup-closed-by-user": "Google sign-in was closed before it finished.",
    "auth/cancelled-popup-request": "Google sign-in was closed before it finished.",
    "auth/popup-blocked": "Your browser blocked the Google window. Allow pop-ups for this site and try again.",
    "auth/account-exists-with-different-credential": "This email already has an account. Sign in with email and password.",
    "auth/requires-recent-login": "For your security, sign out, sign in again, then try once more."
  })[c] || `Sign-in didn’t work${c ? ` (${c.replace("auth/", "")})` : ""}. Please try again.`;
}
function renderAcctBtn(){
  const b = $("acct-btn"); if (!b) return;
  const on = ACC.user && ACC.profile, ph = on ? accPhoto() : "", nm = on ? accName() : "";
  b.innerHTML = ph ? `<img src="${esc(ph)}" alt="" referrerpolicy="no-referrer">` : nm ? `<span class="avatar sm" style="--h:${avatarHue(nm)}">${esc(initials(nm))}</span>` : I.user;
  b.setAttribute("aria-label", on ? `Account: ${nm || ACC.user.email || "signed in"}` : "Account and sign in");
}

// ---- views ----
function accHeader(){ return `<div class="inline" style="justify-content:space-between"><h1>Account</h1><button class="btn small" type="button" data-close-account>Done</button></div>`; }
const accErrBox = () => `<div data-out="accErr">${OUT.accErr()}</div>`;
OUT.accErr = () => ACC.err ? `<p class="err" role="alert">${esc(ACC.err)}</p>` : "";
const legalLinks = `<a href="https://chillwillpill.github.io/keepwise/terms.html" target="_blank" rel="noopener">Terms of Use</a> and <a href="https://chillwillpill.github.io/keepwise/privacy.html" target="_blank" rel="noopener">Privacy Policy</a>`;
V.account = () => {
  if (ACC.state === "preview") return `${accHeader()}<section class="card"><h2>Sign in on the KeepWise website</h2><p class="muted">Accounts can’t open inside this preview. Open the website to sign in with Google or email. Everything else works here as normal.</p><a class="btn primary" href="${SITE_URL}" target="_blank" rel="noopener">Open KeepWise</a></section>`;
  if (ACC.state === "off") return `${accHeader()}<section class="card"><h2>Accounts are coming soon</h2><p class="muted">KeepWise works fully without an account. Everything you enter stays on this phone.</p></section>`;
  if (ACC.state === "idle" || ACC.state === "loading") return `${accHeader()}<section class="card"><p class="muted">Connecting…</p></section>`;
  if (ACC.state === "error") return `${accHeader()}<section class="card"><h2>Can’t reach sign-in</h2><p class="muted">Check your connection and try again. KeepWise still works on this phone without an account.</p><button class="btn" type="button" data-acc-retry>Try again</button></section>`;
  if (!ACC.user) return accSignIn();
  return accComplete() ? accProfile() : accFinish();
};
function accSignIn(){
  const m = ACC.mode;
  return `${accHeader()}
  <p class="muted">An account saves your profile so friends can find you. Your budget, statements and subscriptions still stay on this phone.</p>
  <section class="card acc-card">
    ${IN_APP ? `<p class="note small">Google sign-in is coming to the Android app. Use email here, or sign in with Google on the website.</p>`
             : `<button class="btn g-btn" type="button" data-acc-google>${I.google}Continue with Google</button><div class="or" role="separator"><span>or use email</span></div>`}
    ${m === "reset" ? `<h2>Reset your password</h2><p class="muted small">We’ll email you a link to choose a new password.</p>`
      : `<div class="seg acc-seg" role="group" aria-label="Sign in or create an account"><button type="button" data-acc-mode="signin" aria-pressed="${m === "signin"}">Sign in</button><button type="button" data-acc-mode="create" aria-pressed="${m === "create"}">Create account</button></div>`}
    <form data-form="acc-email" class="acc-form" novalidate>
      <label class="field"><span>Email</span><input id="acc-email" name="email" type="email" autocomplete="email" inputmode="email" autocapitalize="off" spellcheck="false" enterkeyhint="${m === "reset" ? "send" : "next"}" value="${esc(ACC.email)}"></label>
      ${m === "reset" ? "" : `<label class="field"><span>Password</span><input id="acc-pass" name="password" type="password" autocomplete="${m === "create" ? "new-password" : "current-password"}" enterkeyhint="go" ${m === "create" ? 'minlength="8"' : ""}>${m === "create" ? `<small class="muted small">At least 8 characters.</small>` : ""}</label>`}
      ${accErrBox()}
      <button class="btn primary" type="submit" ${ACC.busy ? "disabled" : ""}>${m === "create" ? "Create account" : m === "reset" ? "Send reset link" : "Sign in"}</button>
    </form>
    ${m === "signin" ? `<button class="link small" type="button" data-acc-mode="reset">Forgot your password?</button>` : m === "reset" ? `<button class="link small" type="button" data-acc-mode="signin">Back to sign in</button>` : ""}
  </section>
  <p class="muted small legal-links acc-legal">By continuing, you agree to the ${legalLinks}.</p>`;
}
function accVerifyNote(){
  const u = ACC.user; if (!u || u.emailVerified) return "";
  return `<div class="note acc-verify"><p><b>Verify your email.</b> We sent a link to ${esc(u.email)}. Open it, then come back here.</p><div class="inline"><button class="btn small" type="button" data-acc-verified>I’ve verified it</button><button class="btn small" type="button" data-acc-resend>Send the link again</button></div></div>`;
}
function accFields(first){
  const p = ACC.profile || {}, d = ACC.draft, v = k => esc(k in d ? d[k] : (p[k] ?? ""));
  const name = "name" in d ? d.name : (p.name || (ACC.user && ACC.user.displayName) || "");
  const loc = "location" in d ? d.location : p.location;
  const mk = "marketing" in d ? d.marketing : !!p.marketing;
  return `
    <label class="field"><span>Full name</span><input name="name" data-acc-field="name" type="text" autocomplete="name" enterkeyhint="next" value="${esc(name)}"></label>
    <label class="field"><span>Date of birth</span><input name="dob" data-acc-field="dob" type="date" autocomplete="bday" max="${isoDaysAgo(0)}" value="${v("dob")}"><small class="muted small">You must be 18 or older to have an account.</small></label>
    <label class="field"><span>Phone number <span class="pill grey">Not yet verified</span></span><input name="phone" data-acc-field="phone" type="tel" autocomplete="tel" inputmode="tel" enterkeyhint="next" placeholder="Optional, e.g. +1 555 010 0123" value="${v("phone")}"><small class="muted small">Optional. Lets friends who have your number find you for splits.</small></label>
    <label class="field"><span>City</span><input name="city" data-acc-field="city" type="text" autocomplete="address-level2" enterkeyhint="done" placeholder="Optional" value="${v("city")}"></label>
    <div class="field"><span>Location for local offers</span>
      ${loc ? `<p class="small">Approximate location saved (to about 1 km).</p><div class="inline"><button class="btn small" type="button" data-acc-loc>Update</button><button class="btn small danger" type="button" data-acc-loc-clear>Remove</button></div>`
            : `<p class="muted small">Optional. If you choose to get offers, we may use this to show deals available near you. We save only an approximate area, never your exact location.</p><button class="btn small" type="button" data-acc-loc style="align-self:flex-start">Use my approximate location</button>`}
    </div>
    <label class="check"><input type="checkbox" name="marketing" data-acc-field="marketing" ${mk ? "checked" : ""}><span>Email me offers, birthday deals and news from KeepWise. You can unsubscribe at any time.</span></label>
    ${first ? `<label class="check"><input type="checkbox" name="consent" data-acc-field="consent" ${d.consent ? "checked" : ""}><span>I’m 18 or older and I agree to the ${legalLinks}.</span></label>` : ""}`;
}
function accFinish(){
  return `${accHeader()}
  ${accVerifyNote()}
  <section class="card"><h2>Finish your profile</h2><p class="muted small">Signed in as ${esc(ACC.user.email || "")}. Your name and date of birth are required. Everything else is optional.</p>
    <form data-form="acc-profile" class="acc-form" novalidate>${accFields(true)}${accErrBox()}<button class="btn primary" type="submit" ${ACC.busy ? "disabled" : ""}>Save profile</button></form></section>
  <button class="btn" type="button" data-acc-signout>Sign out</button>`;
}
function accProfile(){
  const u = ACC.user, nm = accName(), ph = accPhoto();
  return `${accHeader()}
  ${accVerifyNote()}
  <section class="card acc-head">
    <div class="acc-photo">${ph ? `<img src="${esc(ph)}" alt="Profile photo" referrerpolicy="no-referrer">` : `<span class="avatar lg" style="--h:${avatarHue(nm)}" aria-hidden="true">${esc(initials(nm))}</span>`}</div>
    <div class="acc-id"><b>${esc(nm)}</b><span class="muted small">${esc(u.email || "")}</span>${u.emailVerified ? `<span class="pill ok">Email verified</span>` : `<span class="pill gold">Email not verified</span>`}</div>
    <div class="inline acc-photo-btns"><button class="btn small" type="button" data-acc-photo>${ph ? "Change photo" : "Add photo"}</button>${ph ? `<button class="btn small danger" type="button" data-acc-photo-clear>Remove photo</button>` : ""}</div>
  </section>
  <section class="card"><h2>Profile</h2>
    <form data-form="acc-profile" class="acc-form" novalidate>${accFields(false)}${accErrBox()}<button class="btn primary" type="submit" ${ACC.busy ? "disabled" : ""}>Save changes</button></form></section>
  <section class="card plus-card"><div class="inline" style="justify-content:space-between"><h2>KeepWise Plus</h2><span class="pill gold">Coming soon</span></div>
    <p class="small">Back up your budget with end-to-end encryption and use it on all your devices. Add receipt photos to splits, keep business money in its own space, and turn shared occasions into Moments. Only you can read your data.</p>
    ${ACC.profile && ACC.profile.plusInterest ? `<p class="small"><span class="pill ok">You’re on the waitlist</span> We’ll email you when KeepWise Plus launches.</p><button class="link small" type="button" data-acc-plus-off style="align-self:flex-start">Leave the waitlist</button>`
      : `<button class="btn primary" type="button" data-acc-plus>Join the Plus waitlist</button>`}
  </section>
  <section class="card"><h2>Account</h2>
    <p class="muted small">Your budget and statements stay on this phone. They are not part of your account.</p>
    <button class="btn" type="button" data-acc-signout>Sign out</button>
    ${ACC.del ? `<div class="note"><p><b>Delete your account?</b> Your profile is erased for good. What’s saved on this phone stays until you clear it on the Plan tab.</p><div class="inline" style="margin-top:10px"><button class="btn danger" type="button" data-acc-delete-yes>Delete my account</button><button class="btn" type="button" data-acc-delete-no>Keep it</button></div></div>`
             : `<button class="btn danger" type="button" data-acc-delete>Delete account</button>`}
    <p class="small legal-links">${legalLinks.replace(" and ", " · ")}</p>
  </section>`;
}

// ---- photo: shrink to a small square so it fits in the profile record ----
function shrinkPhoto(file){
  return new Promise((ok, bad) => {
    if (!file || !/^image\//.test(file.type)) return bad(new Error("type"));
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => { const n = 192, c = document.createElement("canvas"); c.width = c.height = n; const s = Math.min(img.width, img.height);
      c.getContext("2d").drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, n, n); URL.revokeObjectURL(url); ok(c.toDataURL("image/jpeg", .82)); };
    img.onerror = () => { URL.revokeObjectURL(url); bad(new Error("read")); };
    img.src = url;
  });
}
const photoIn = document.createElement("input"); photoIn.type = "file"; photoIn.accept = "image/*"; photoIn.className = "sr"; photoIn.id = "acc-photo-in"; photoIn.tabIndex = -1; photoIn.setAttribute("aria-hidden", "true"); photoIn.setAttribute("aria-label", "Profile photo"); document.body.appendChild(photoIn);
photoIn.addEventListener("change", async () => {
  const f = photoIn.files[0]; photoIn.value = ""; if (!f) return;
  try { ACC.draft.photo = await shrinkPhoto(f); render(true); toast("Photo ready. Tap Save changes to keep it."); }
  catch(e){ toast("That file isn’t a photo KeepWise can read."); }
});

function setAccErr(msg){ ACC.err = msg; refreshOuts(); }
function accBusy(on){ ACC.busy = on; document.querySelectorAll("#view .acc-form [type=submit]").forEach(b => b.disabled = on); }

// ---- events ----
$("acct-btn").addEventListener("click", () => { UI.account = !UI.account; UI.inbox = false; ACC.err = ""; if (UI.account) accInit(); render(false); });
$("view").addEventListener("input", e => {
  const t = e.target;
  if (t.id === "acc-email") ACC.email = t.value;
  const k = t.dataset && t.dataset.accField; if (k) ACC.draft[k] = t.type === "checkbox" ? t.checked : t.value;
});
$("view").addEventListener("change", e => { const t = e.target, k = t.dataset && t.dataset.accField; if (k && t.type === "checkbox") ACC.draft[k] = t.checked; });
$("view").addEventListener("click", async e => {
  const b = e.target.closest("button"); if (!b) return;
  const has = a => b.hasAttribute(a);
  if (has("data-close-account")){ UI.account = false; ACC.err = ""; render(false); return; }
  if (has("data-acc-retry")){ ACC.state = "idle"; ACC.ready = null; render(true); accInit(); return; }
  if (b.dataset.accMode){ ACC.mode = b.dataset.accMode; ACC.err = ""; render(true); return; }
  if (has("data-acc-google")){
    ACC.err = ""; refreshOuts();
    try { await ACC.auth.signInWithPopup(new firebase.auth.GoogleAuthProvider()); }
    catch(err){ setAccErr(accErrText(err)); }
    return;
  }
  if (has("data-acc-signout")){ await ACC.auth.signOut(); toast("Signed out."); return; }
  if (has("data-acc-resend")){ try { await ACC.user.sendEmailVerification(); toast("Verification link sent. Check your inbox."); } catch(err){ toast(accErrText(err)); } return; }
  if (has("data-acc-verified")){
    try { await ACC.user.reload(); ACC.user = ACC.auth.currentUser; } catch(err){}
    if (ACC.user.emailVerified){ try { await accDoc().set({emailVerified: true, updatedAt: Date.now()}, {merge: true}); ACC.profile.emailVerified = true; } catch(err){} toast("Email verified. Thank you."); }
    else toast("Not verified yet. Open the link in the email, then try again.");
    render(true); return;
  }
  if (has("data-acc-plus") || has("data-acc-plus-off")){
    const on = has("data-acc-plus"), data = {plusInterest: on, plusInterestAt: Date.now(), updatedAt: Date.now()};
    try { await accDoc().set(data, {merge: true}); Object.assign(ACC.profile, data); render(true); toast(on ? "You’re on the KeepWise Plus waitlist." : "You’ve left the Plus waitlist."); }
    catch(err){ toast("Couldn’t save that. Check your connection and try again."); }
    return;
  }
  if (has("data-acc-photo")){ photoIn.click(); return; }
  if (has("data-acc-photo-clear")){ ACC.draft.photo = ""; render(true); return; }
  if (has("data-acc-loc")){
    if (!navigator.geolocation){ toast("This device can’t share its location."); return; }
    navigator.geolocation.getCurrentPosition(pos => {
      const r = x => Math.round(x * 100) / 100; // about 1 km: enough for nearby deals, not an exact address
      ACC.draft.location = {lat: r(pos.coords.latitude), lng: r(pos.coords.longitude)};
      render(true); toast("Approximate location added. Tap Save to keep it.");
    }, () => toast("Location wasn’t shared. You can still add your city."), {enableHighAccuracy: false, timeout: 15000, maximumAge: 600000});
    return;
  }
  if (has("data-acc-loc-clear")){ ACC.draft.location = null; render(true); return; }
  if (has("data-acc-delete")){ ACC.del = true; render(true); return; }
  if (has("data-acc-delete-no")){ ACC.del = false; render(true); return; }
  if (has("data-acc-delete-yes")){
    const keep = ACC.profile;
    try { await accDoc().delete(); await ACC.user.delete(); S.acctOn = false; save(); toast("Your account was deleted."); }
    catch(err){
      if (keep) try { await accDoc().set(keep); } catch(x){}
      ACC.del = false; ACC.err = accErrText(err); render(true);
    }
    return;
  }
});
$("view").addEventListener("submit", async e => {
  const f = e.target, kind = f.dataset.form;
  if (kind === "acc-email"){
    e.preventDefault();
    const email = (f.querySelector("#acc-email").value || "").trim(), pw = f.querySelector("#acc-pass") ? f.querySelector("#acc-pass").value : "";
    ACC.email = email;
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)){ setAccErr("Enter a valid email address."); return; }
    if (ACC.mode !== "reset" && !pw){ setAccErr("Enter your password."); return; }
    if (ACC.mode === "create" && pw.length < 8){ setAccErr("Use at least 8 characters for your password."); return; }
    ACC.err = ""; refreshOuts(); accBusy(true);
    try {
      if (ACC.mode === "reset"){ await ACC.auth.sendPasswordResetEmail(email); ACC.mode = "signin"; accBusy(false); render(true); toast("If an account uses that email, a reset link is on its way."); return; }
      if (ACC.mode === "create"){ const r = await ACC.auth.createUserWithEmailAndPassword(email, pw); try { await r.user.sendEmailVerification(); } catch(x){} toast("Account created. We sent you a link to verify your email."); }
      else await ACC.auth.signInWithEmailAndPassword(email, pw);
    } catch(err){ setAccErr(accErrText(err)); }
    accBusy(false);
    return;
  }
  if (kind === "acc-profile"){
    e.preventDefault();
    const fd = new FormData(f), first = !accComplete();
    const name = String(fd.get("name") || "").trim(), dob = String(fd.get("dob") || ""), phone = String(fd.get("phone") || "").trim(), city = String(fd.get("city") || "").trim();
    const marketing = fd.get("marketing") === "on", consent = fd.get("consent") === "on";
    if (!name){ setAccErr("Enter your full name."); return; }
    const age = ageOn(dob);
    if (!dob || age < 0 || dob > isoDaysAgo(0)){ setAccErr("Enter your date of birth."); return; }
    if (age < 18){ setAccErr("You must be 18 or older to create a KeepWise account."); return; }
    if (age > 120){ setAccErr("Check your date of birth."); return; }
    const digits = phone.replace(/\D/g, "");
    if (phone && (!/^\+?[\d\s().-]+$/.test(phone) || digits.length < 7 || digits.length > 15)){ setAccErr("Enter a valid phone number, or leave it empty."); return; }
    if (first && !consent){ setAccErr("Please confirm you’re 18 or older and agree to the Terms of Use and Privacy Policy."); return; }
    const p = ACC.profile || {}, now = Date.now(), u = ACC.user;
    const data = {name, dob, phone, phoneVerified: false, city, marketing, email: u.email || "", emailVerified: !!u.emailVerified, updatedAt: now};
    if (marketing !== !!p.marketing || first) data.marketingUpdatedAt = now;
    if ("photo" in ACC.draft) data.photo = ACC.draft.photo || null;
    if ("location" in ACC.draft) data.location = ACC.draft.location || null;
    if (first){ data.createdAt = p.createdAt || now; data.termsAcceptedAt = now; data.termsVersion = TERMS_VERSION; data.provider = (u.providerData && u.providerData[0] && u.providerData[0].providerId) || "password"; }
    ACC.err = ""; accBusy(true);
    try {
      await accDoc().set(data, {merge: true});
      ACC.profile = {...p, ...data}; ACC.draft = {}; accBusy(false); renderAcctBtn(); render(!first);
      toast(first ? `Welcome, ${name.split(" ")[0]}.` : "Profile saved.");
    } catch(err){ accBusy(false); setAccErr("Couldn’t save your profile. Check your connection and try again."); }
    return;
  }
});
if (FB_CONFIG && S.acctOn) accInit();
renderAcctBtn();
