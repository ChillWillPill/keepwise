// Stand-in for the Firebase compat SDK (app, auth, firestore) so sign-in can be tested offline.
// Accounts, the signed-in session and Firestore documents persist in localStorage like the real SDK.
(() => {
  const L = (k, d) => { try { return JSON.parse(localStorage.getItem(k) || "null") || d; } catch(e){ return d; } };
  const users = L("__mock_users", {}), store = L("__mock_fs", {});
  const saveUsers = () => localStorage.setItem("__mock_users", JSON.stringify(users));
  const saveStore = () => localStorage.setItem("__mock_fs", JSON.stringify(store));
  window.__mockMail = [];
  window.__mockVerify = email => { users[email].verified = true; saveUsers(); };
  let current = null; const cbs = [];
  const err = code => Object.assign(new Error(code), {code});
  function mk(rec){
    return {
      uid: rec.uid, email: rec.email, displayName: rec.displayName || null, photoURL: rec.photoURL || null,
      get emailVerified(){ return !!(users[rec.email] && users[rec.email].verified); },
      providerData: [{providerId: rec.provider}],
      sendEmailVerification: async () => { window.__mockMail.push({to: rec.email, type: "verify"}); },
      reload: async () => {},
      reauthenticateWithCredential: async c => { if (!c || c.email !== rec.email) throw err("auth/user-mismatch"); if (window.__mockOffline) throw err("auth/network-request-failed"); if (c.pw !== rec.pw) throw err("auth/wrong-password"); },
      reauthenticateWithPopup: async () => { const e = window.__mockGoogleEmail || "gina@example.com"; if (e !== rec.email) throw err("auth/user-mismatch"); },
      delete: async () => { delete users[rec.email]; saveUsers(); setUser(null); }
    };
  }
  function setUser(rec){
    current = rec ? mk(rec) : null;
    localStorage.setItem("__mock_session", rec ? rec.email : "");
    cbs.forEach(cb => setTimeout(() => cb(current), 0));
  }
  const s = localStorage.getItem("__mock_session"); if (s && users[s]) current = mk(users[s]);
  const auth = {
    get currentUser(){ return current; },
    onAuthStateChanged(cb){ cbs.push(cb); setTimeout(() => cb(current), 0); return () => {}; },
    async createUserWithEmailAndPassword(email, pw){
      if (users[email]) throw err("auth/email-already-in-use");
      if (pw.length < 6) throw err("auth/weak-password");
      users[email] = {uid: "u" + (Object.keys(users).length + 1), email, pw, provider: "password", verified: false}; saveUsers();
      setUser(users[email]); return {user: current};
    },
    async signInWithEmailAndPassword(email, pw){
      const u = users[email]; if (!u || u.pw !== pw) throw err("auth/invalid-credential");
      setUser(u); return {user: current};
    },
    async signInWithPopup(){
      const email = window.__mockGoogleEmail || "gina@example.com";
      users[email] = users[email] || {uid: email === "gina@example.com" ? "g1" : "g" + Object.keys(users).length, email, displayName: "Gina Park", photoURL: "", provider: "google.com", verified: true}; saveUsers();
      setUser(users[email]); return {user: current};
    },
    async sendPasswordResetEmail(email){ window.__mockMail.push({to: email, type: "reset"}); },
    async signOut(){ setUser(null); }
  };
  const fs = {
    collection(c){ return {
      async get(){  // listing the whole collection: only the owner's verified Google account, like the real rules
        if (!current || current.email !== (window.__mockOwner || "notartist04@gmail.com") || current.providerData[0].providerId !== "google.com") throw err("permission-denied");
        const docs = Object.keys(store).filter(k => k.startsWith(c + "/")).map(k => ({id: k.slice(c.length + 1), data: () => JSON.parse(JSON.stringify(store[k]))}));
        return {docs, size: docs.length};
      },
      doc(id){ const key = c + "/" + id; return {
      async get(){ if (!current || current.uid !== id) throw err("permission-denied"); const has = key in store; return {exists: has, data: () => has ? JSON.parse(JSON.stringify(store[key])) : undefined}; },
      async set(d, o){ if (!current || current.uid !== id) throw err("permission-denied"); store[key] = o && o.merge ? {...(store[key] || {}), ...d} : d; saveStore(); },
      async delete(){ if (!current || current.uid !== id) throw err("permission-denied"); delete store[key]; saveStore(); }
    }; } }; }
  };
  const authFn = () => auth; authFn.GoogleAuthProvider = function(){}; authFn.EmailAuthProvider = {credential: (email, pw) => ({email, pw})};
  window.firebase = { apps: [], initializeApp(c){ this.apps.push(c); return {}; }, app(){ return {}; }, auth: authFn, firestore: () => fs };
})();
