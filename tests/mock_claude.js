(() => {
  const store = new Map(), subs = [];
  const snapDoc = (path) => ({ id: path.split("/").pop(), exists: store.has(path), data: () => store.get(path), metadata:{} });
  const notify = () => subs.forEach(s => s.fire());
  const collSnap = (cp) => { const docs=[...store.keys()].filter(k => k.startsWith(cp+"/") && k.split("/").length === cp.split("/").length+1).map(snapDoc); return {docs, size:docs.length, empty:!docs.length, docChanges:()=>[], metadata:{}}; };
  const docRef = (path) => ({ path, id: path.split("/").pop(),
    get: async () => snapDoc(path),
    set: async (d) => { store.set(path, JSON.parse(JSON.stringify(d))); notify(); },
    update: async (d) => { if (!store.has(path)) throw {code:"invalid_argument"}; store.set(path, {...store.get(path), ...JSON.parse(JSON.stringify(d))}); notify(); },
    delete: async () => { store.delete(path); notify(); },
    onSnapshot: (n) => { const s={fire:()=>n(snapDoc(path))}; subs.push(s); setTimeout(s.fire,10); return ()=>{}; } });
  const collRef = (cp) => ({ path: cp, doc: (id) => docRef(cp + "/" + (id || Math.random().toString(36).slice(2))),
    onSnapshot: (n) => { const s={fire:()=>n(collSnap(cp))}; subs.push(s); setTimeout(s.fire,10); return ()=>{}; } });
  const db = { doc: docRef, collection: collRef };
  const names = {u_me:"Me", u_alex:"Alex", u_sam:"Sam"};
  const user = { id: async () => "u_me", profiles: async (ids) => Object.fromEntries([].concat(ids).map(i => [i, {id:i, name:names[i]||""}])) };
  window.claude = { use: async (n) => n === "db" ? db : n === "user" ? user : null };
  window.__mock = { store, db, notify };
})();
