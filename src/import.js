// ================= bank statement import (CSV or PDF, read on this device only) =================
const STMT = {result:null, busy:false, err:""};
const STOP_WORDS = new Set(["POS","DEBIT","CREDIT","CARD","PURCHASE","RECURRING","PAYMENT","PMT","ACH","COM","WWW","INC","LLC","LTD","USA","US","UK","THE","STORE","ORDER","TRIP","MKTPLACE","OIL","DIRECT","DEP","DD","SO","FPI","BGC","TFR","REF","ONLINE","VISA","MASTERCARD","CONTACTLESS","APPLE","PAY","GOOGLE","SQ","TST","PP","PAYPAL","BILL"]);
const KEEP_FIRST = /^(APPLE|GOOGLE|PAYPAL|AMAZON)$/;
const CAT_RULES = [
  ["Salary",/PAYROLL|SALARY|WAGES|DIRECT DEP|PAYCHECK|BGC|NET PAY/],
  ["Tax",/\bTAX\b|IRS|HMRC|FBR|REVENUE SERVICE|COUNCIL TAX|INCOME TAX|WITHHOLDING/],
  ["Housing",/RENT|MORTGAGE|APARTMENT|PROPERTY|LETTING|LANDLORD|HOA/],
  ["Utilities",/ELECTRIC|ENERGY|WATER|GAS BILL|COMCAST|XFINITY|VERIZON|AT&T|T MOBILE|TMOBILE|INTERNET|BROADBAND|CON ED|BRITISH GAS|OCTOPUS|VODAFONE|EE LIMITED|JAZZ|ZONG|TELENOR|PTCL|K ELECTRIC|SUI GAS/],
  ["Insurance",/GEICO|INSURANCE|STATE FARM|PROGRESSIVE|ALLSTATE|AVIVA|DIRECT LINE|ADMIRAL|JUBILEE/],
  ["Loans",/LOAN|CREDIT CARD PAYMENT|STUDENT|FINANCE|AFFIRM|KLARNA/],
  ["Subscriptions",/NETFLIX|SPOTIFY|HULU|DISNEY|ICLOUD|APPLE COM BILL|APPLE COM|ADOBE|AUDIBLE|PRIME|YOUTUBE|PARAMOUNT|PEACOCK|MAX\b|HBO|FITNESS|GYM|PELOTON|DROPBOX|MICROSOFT|OFFICE 365|OPENAI|CHATGPT|CLAUDE|ANTHROPIC|NOTION|DUOLINGO|PATREON|NOW TV|BRITBOX|CRUNCHYROLL|XBOX|PLAYSTATION|NINTENDO|CANVA|GRAMMARLY|LINKEDIN|TINDER|BUMBLE|HEADSPACE|CALM|NYTIMES|WSJ/],
  ["Groceries",/TRADER JOE|KROGER|WHOLE FOODS|ALDI|TESCO|SAINSBURY|SAFEWAY|LIDL|WALMART|GROCERY|ASDA|COSTCO|CARREFOUR|IMTIAZ|METRO CASH|MORRISONS|WAITROSE/],
  ["Dining",/STARBUCKS|CHIPOTLE|MCDONALD|DOORDASH|UBER EATS|GRUBHUB|RESTAURANT|CAFE|COFFEE|PIZZA|DELIVEROO|JUST EAT|GREGGS|FOODPANDA|KFC|SUBWAY|BURGER|DOMINO/],
  ["Transport",/UBER|LYFT|CAREEM|SHELL|EXXON|CHEVRON|\bBP\b|PSO|METRO|TRANSIT|PARKING|TFL|TRAINLINE|FUEL|PETROL/],
  ["Health",/CVS|WALGREENS|PHARMACY|BOOTS|CLINIC|DENTAL|HOSPITAL/],
  ["Shopping",/AMAZON|TARGET|BEST BUY|ETSY|EBAY|ARGOS|DARAZ|IKEA|ZARA|H&M|NIKE|APPLE STORE/],
  ["Transfers",/TRANSFER|ZELLE|VENMO|CASH APP|WISE|ATM|WITHDRAWAL|EASYPAISA|JAZZCASH|RAAST/]
];
const catOfDesc = d => { const u = " " + d.toUpperCase().replace(/[^A-Z0-9& ]/g, " ") + " "; for (const [c, re] of CAT_RULES) if (re.test(u)) return c; return "Other"; };
const NEEDS_CATS = new Set(["Housing","Utilities","Insurance","Loans","Groceries","Transport","Health","Tax"]);
const BILL_CAT = new Set(["Housing","Utilities","Insurance","Loans"]);
const CAT_LABEL = {Groceries:"Groceries", Dining:"Eating out", Transport:"Getting around", Health:"Health", Shopping:"Shopping", Other:"Everything else", Transfers:"Transfers and cash", Tax:"Tax payments"};

function merchantKey(desc){
  const words = desc.toUpperCase().replace(/[^A-Z& ]/g, " ").split(/\s+/).filter(w => w.length > 1);
  const kept = words.filter((w, i) => !STOP_WORDS.has(w) || (i === 0 && KEEP_FIRST.test(w) && words.length === 1));
  return (kept.slice(0, 2).join(" ") || words.slice(0, 2).join(" ") || desc.toUpperCase()).trim();
}
const titleCase = k => k.toLowerCase().replace(/\b[a-z]/g, c => c.toUpperCase()).replace(/\bIcloud\b/, "iCloud").replace(/\bAt&t\b/i, "AT&T");

// ---- dates and amounts ----
const MONTHS = {jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,sept:8,oct:9,nov:10,dec:11};
// 04/05/2026 is 5 April in the US and 4 May elsewhere. The file itself usually settles it: any date with a number above 12
// shows which position holds the day. Only when every date is ambiguous does the chosen currency decide.
function dayFirstIn(texts){
  let dayFirst = 0, monthFirst = 0;
  for (const t of texts){ const m = String(t || "").trim().match(/^(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}/); if (!m) continue; if (+m[1] > 12) dayFirst++; else if (+m[2] > 12) monthFirst++; }
  return dayFirst || monthFirst ? dayFirst > monthFirst : ["GBP","EUR","PKR","INR","AUD","AED"].includes(S.cur);
}
function parseAnyDate(s, yearHint, dayFirst){
  s = String(s || "").trim(); let m;
  if ((m = s.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/))) return new Date(+m[1], +m[2]-1, +m[3]);
  if ((m = s.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})/))){
    let a = +m[1], b = +m[2], y = +m[3]; if (y < 100) y += 2000;
    const df = b > 12 ? false : a > 12 ? true : !!dayFirst; return new Date(y, (df ? b : a) - 1, df ? a : b);  // a month is never above 12
  }
  if ((m = s.match(/^(\d{1,2})[\s-]+([A-Za-z]{3,4})[a-z]*[\s-,]*(\d{2,4})?/)) && MONTHS[m[2].toLowerCase()] !== undefined){
    let y = m[3] ? +m[3] : yearHint; if (y < 100) y += 2000; return new Date(y, MONTHS[m[2].toLowerCase()], +m[1]);
  }
  if ((m = s.match(/^([A-Za-z]{3,4})[a-z]*\.?\s+(\d{1,2}),?\s*(\d{2,4})?/)) && MONTHS[m[1].toLowerCase()] !== undefined){
    let y = m[3] ? +m[3] : yearHint; if (y < 100) y += 2000; return new Date(y, MONTHS[m[1].toLowerCase()], +m[2]);
  }
  const t = Date.parse(s); return isNaN(t) ? null : new Date(t);
}
function parseMoney(s){
  if (s == null) return NaN; s = String(s).trim(); if (!s) return NaN;
  const neg = /^\(.*\)$/.test(s) || /^-|-$/.test(s.replace(/[^\d\-()]/g, "")) || /\bDR\b/i.test(s);
  const v = parseFloat(s.replace(/[^0-9.]/g, "")); if (isNaN(v)) return NaN;
  return neg ? -v : v;
}
const isoOf = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;

// ---- CSV ----
function csvRows(text){
  const rows = []; let row = [], f = "", q = false;
  for (let i = 0; i < text.length; i++){
    const c = text[i];
    if (q){ if (c === '"'){ if (text[i+1] === '"'){ f += '"'; i++; } else q = false; } else f += c; }
    else if (c === '"') q = true;
    else if (c === "," || c === ";" && !text.slice(0, 200).includes(",")) { row.push(f); f = ""; }
    else if (c === "\n" || c === "\r"){ if (c === "\r" && text[i+1] === "\n") i++; row.push(f); if (row.some(x => x.trim())) rows.push(row); row = []; f = ""; }
    else f += c;
  }
  row.push(f); if (row.some(x => x.trim())) rows.push(row);
  return rows;
}
function txFromCSV(text){
  const rows = csvRows(text.replace(/^﻿/, ""));
  let hi = rows.findIndex(r => r.some(c => /date/i.test(c)) && r.some(c => /desc|name|merchant|payee|details|narrative|memo|particular|transaction/i.test(c)));
  if (hi < 0) throw new Error("Couldn't find the header row. The file needs columns for date, description and amount.");
  const h = rows[hi].map(x => x.trim().toLowerCase()), find = re => h.findIndex(x => re.test(x));
  const di = find(/date/), de = find(/desc|name|merchant|payee|details|narrative|memo|particular|transaction/);
  const cr = find(/credit|paid in|deposit|money in|inflow/), db = find(/debit|paid out|withdraw|money out|outflow/);
  const am = find(/^amount|amount$|value|^sum/), ty = find(/^type$|dr\/cr|cr\/dr|direction/);
  if (di < 0 || de < 0 || (am < 0 && cr < 0 && db < 0)) throw new Error("Couldn't find date, description and amount columns.");
  const year = new Date().getFullYear(), dayFirst = dayFirstIn(rows.slice(hi + 1).map(r => r[di]));
  let tx = rows.slice(hi + 1).map(r => {
    const date = parseAnyDate(r[di], year, dayFirst), desc = (r[de] || "").trim();
    let amt;
    if (cr >= 0 || db >= 0){ const c = parseMoney(r[cr]), d = parseMoney(r[db]); amt = !isNaN(c) && c !== 0 ? Math.abs(c) : !isNaN(d) && d !== 0 ? -Math.abs(d) : NaN; }
    else { amt = parseMoney(r[am]); if (ty >= 0 && !isNaN(amt)){ const t = (r[ty] || "").toLowerCase(); if (/^d|debit|out|withdraw/.test(t)) amt = -Math.abs(amt); else if (/^c|credit|in|deposit/.test(t)) amt = Math.abs(amt); } }
    return {date, desc, amt};
  }).filter(t => t.date && !isNaN(t.date) && t.desc && !isNaN(t.amt) && t.amt !== 0);
  if (!tx.length) throw new Error("No transactions found in that file.");
  if (am >= 0 && cr < 0 && db < 0 && ty < 0 && tx.every(t => t.amt > 0)){
    // one unsigned column: payroll-looking lines are money in, everything else is money out
    tx.forEach(t => { if (catOfDesc(t.desc) !== "Salary") t.amt = -t.amt; });
  }
  return tx;
}

// ---- PDF (pdf.js loaded on first use) ----
function loadScript(src){ return new Promise((ok, no) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = () => no(new Error("Couldn't load the PDF reader. Check your connection and try again.")); document.head.appendChild(s); }); }
async function pdfLib(){
  if (window.pdfjsLib) return window.pdfjsLib;
  const base = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/";
  await loadScript(base + "pdf.min.js");
  await loadScript(base + "pdf.worker.min.js"); // runs on the page itself, no separate worker needed
  return window.pdfjsLib;
}
async function pdfLines(buf){
  const lib = await pdfLib();
  const doc = await lib.getDocument({data: buf, isEvalSupported: false, disableFontFace: true}).promise;
  const lines = [];
  for (let p = 1; p <= doc.numPages; p++){
    const page = await doc.getPage(p), content = await page.getTextContent(), rows = new Map();
    content.items.forEach(it => { if (!it.str.trim()) return; const y = Math.round(it.transform[5] / 3) * 3; if (!rows.has(y)) rows.set(y, []); rows.get(y).push({x: it.transform[4], s: it.str}); });
    [...rows.entries()].sort((a, b) => b[0] - a[0]).forEach(([, items]) => lines.push(items.sort((a, b) => a.x - b.x).map(i => i.s).join(" ").replace(/\s+/g, " ").trim()));
  }
  return lines;
}
const MONEY_RE = /\(?-?[£$€₹]?\s?(?:Rs\.?\s?)?\d{1,3}(?:,\d{3})*\.\d{2}\)?(?:\s?(?:CR|DR))?-?/gi;
const DATE_RE = /^(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}[\s-][A-Za-z]{3,4}[a-z]*(?:[\s-,]+\d{2,4})?|[A-Za-z]{3,4}\.?\s\d{1,2}(?:,?\s\d{4})?)\b/;
function txFromLines(lines){
  const joined = lines.join(" "), yearHint = +((joined.match(/\b(20\d{2})\b/) || [])[1] || new Date().getFullYear());
  const dayFirst = dayFirstIn(lines.map(l => (l.match(DATE_RE) || [])[1]));
  const out = []; let prevBal = null;
  for (const line of lines){
    const dm = line.match(DATE_RE); if (!dm) continue;
    const date = parseAnyDate(dm[1], yearHint, dayFirst); if (!date || isNaN(date)) continue;
    const rest = line.slice(dm[0].length), nums = rest.match(MONEY_RE); if (!nums) continue;
    const desc = rest.replace(MONEY_RE, " ").replace(/\s+/g, " ").trim(); if (!desc || /opening|closing|brought forward|carried forward|balance b\/f|balance c\/f/i.test(desc)) { if (nums.length) prevBal = Math.abs(parseMoney(nums[nums.length-1])); continue; }
    let amt = parseMoney(nums.length >= 2 ? nums[nums.length - 2] : nums[0]);
    const bal = nums.length >= 2 ? parseMoney(nums[nums.length - 1]) : null;
    const signed = /-|\(|DR|CR/i.test(nums.length >= 2 ? nums[nums.length - 2] : nums[0]);
    if (nums.length >= 3){ // separate debit and credit columns: whichever is non-zero
      const a = parseMoney(nums[nums.length - 3]), b = parseMoney(nums[nums.length - 2]);
      amt = a && !b ? -Math.abs(a) : Math.abs(b);
    } else if (!signed){
      if (bal != null && prevBal != null && Math.abs(Math.abs(prevBal - bal) - Math.abs(amt)) < 0.02) amt = bal > prevBal ? Math.abs(amt) : -Math.abs(amt);
      else amt = catOfDesc(desc) === "Salary" || /\b(CR|CREDIT|DEPOSIT|REFUND|RECEIVED|FROM)\b/i.test(desc) ? Math.abs(amt) : -Math.abs(amt);
    } else if (/CR/i.test(nums[nums.length >= 2 ? nums.length - 2 : 0])) amt = Math.abs(amt);
    if (bal != null) prevBal = bal;
    if (amt) out.push({date, desc, amt});
  }
  if (!out.length) throw new Error("Couldn't read transactions from that PDF. Scanned statements (photos) can't be read; try the CSV export from your bank's website instead.");
  return out;
}

// ---- analysis ----
function analyzeStatement(tx, fileName){
  tx.sort((a, b) => a.date - b.date);
  const first = tx[0].date, last = tx[tx.length - 1].date;
  const months = Math.max(1, Math.round((last - first) / (30.44 * DAY) + 0.5));
  const group = list => { const g = {}; list.forEach(t => { const k = merchantKey(t.desc); (g[k] = g[k] || []).push(t); }); return g; };
  const cadenceOf = list => {
    if (list.length < 2) return null;
    const gaps = list.slice(1).map((t, i) => (t.date - list[i].date) / DAY), amts = list.map(t => Math.abs(t.amt));
    const steady = Math.max(...amts) / Math.min(...amts) <= 1.25, avgGap = gaps.reduce((a, b) => a + b, 0) / gaps.length;
    if (steady && gaps.every(g => g >= 25 && g <= 36)) return "monthly";
    if (steady && gaps.every(g => g >= 12 && g <= 16)) return "biweekly";
    if (steady && gaps.every(g => g >= 6 && g <= 8)) return "weekly";
    if (steady && gaps.every(g => g >= 350 && g <= 380)) return "yearly";
    if (avgGap >= 25 && avgGap <= 36 && steady) return "monthly";
    return null;
  };
  const perMonth = (amt, cad) => cad === "weekly" ? amt * 52 / 12 : cad === "biweekly" ? amt * 26 / 12 : cad === "yearly" ? amt / 12 : amt;
  // money in
  const credits = tx.filter(t => t.amt > 0), cg = group(credits), income = [];
  let otherIn = 0;
  for (const [k, list] of Object.entries(cg)){
    const cad = cadenceOf(list), isPay = list.some(t => catOfDesc(t.desc) === "Salary");
    const total = list.reduce((a, t) => a + t.amt, 0);
    if (isPay || (cad && catOfDesc(list[0].desc) !== "Transfers")){
      const avg = total / list.length, days = list.map(t => t.date.getDate());
      const payday = days.sort((a, b) => days.filter(v => v === b).length - days.filter(v => v === a).length)[0];
      income.push({name: titleCase(k), monthly: r2(cad ? perMonth(avg, cad) : total / months), cadence: cad || "irregular", payday, count: list.length});
    } else otherIn += total;
  }
  income.sort((a, b) => b.monthly - a.monthly);
  const monthlyIncome = r2(income.reduce((a, s) => a + s.monthly, 0));
  // money out
  const debits = tx.filter(t => t.amt < 0), dg = group(debits), subs = [], bills = [], taxes = [], spend = {};
  for (const [k, list] of Object.entries(dg)){
    const cat = catOfDesc(list[0].desc), cad = cadenceOf(list), amts = list.map(t => -t.amt), total = amts.reduce((a, b) => a + b, 0);
    const lastAmt = amts[amts.length - 1];
    if (cat === "Tax"){ taxes.push({name: titleCase(k), total: r2(total), monthly: r2(total / months)}); continue; }
    if (cad && BILL_CAT.has(cat)){ bills.push({name: titleCase(k), cat, monthly: r2(perMonth(lastAmt, cad)), cadence: cad}); continue; }
    if (cat === "Subscriptions" || (cad && cat !== "Groceries" && cat !== "Transfers" && cat !== "Transport" && lastAmt < 150)){
      if (cat === "Subscriptions" || cad){
        subs.push({name: titleCase(k), price: r2(lastAmt), cycle: cad === "yearly" ? "yr" : "mo", monthly: r2(perMonth(lastAmt, cad || "monthly")), since: isoOf(list[0].date), lastCharge: isoOf(list[list.length - 1].date), charges: list.length, paid: r2(total), cadence: cad || "monthly"});
        continue;
      }
    }
    spend[cat] = (spend[cat] || 0) + total;
  }
  subs.sort((a, b) => b.monthly - a.monthly); bills.sort((a, b) => b.monthly - a.monthly);
  const spending = Object.entries(spend).map(([cat, total]) => ({cat, name: CAT_LABEL[cat] || cat, monthly: r2(total / months), env: NEEDS_CATS.has(cat) ? "needs" : "misc"})).filter(x => x.monthly >= 1).sort((a, b) => b.monthly - a.monthly);
  const taxMonthly = r2(taxes.reduce((a, t) => a + t.monthly, 0));
  const out = r2(bills.reduce((a, b) => a + b.monthly, 0) + subs.reduce((a, s) => a + s.monthly, 0) + spending.reduce((a, s) => a + s.monthly, 0) + taxMonthly);
  return {fileName, count: tx.length, first: isoOf(first), last: isoOf(last), months, income, monthlyIncome, otherIn: r2(otherIn / months), subs, bills, taxes, taxMonthly, spending, monthlyOut: out};
}

// ---- apply to the plan ----
function applyStatement(R, mode){
  const expenses = [
    ...R.bills.map(b => ({id: uid(), name: b.name, amount: b.monthly, env: "needs", source: "statement"})),
    ...(R.taxMonthly ? [{id: uid(), name: "Tax payments", amount: R.taxMonthly, env: "needs", source: "statement"}] : []),
    ...R.spending.filter(s => s.cat !== "Transfers").map(s => ({id: uid(), name: s.name, amount: s.monthly, env: s.env, source: "statement"}))
  ];
  const subs = R.subs.map(s => ({id: uid(), name: s.name, price: s.price, cycle: s.cycle, last: null, group: "", env: "misc", keep: "auto", since: s.since, charges: s.charges, paid: s.paid, lastCharge: s.lastCharge, source: "statement"}));
  subs.forEach(s => setRenewalFrom(s, s.lastCharge));
  if (mode === "replace"){
    if (R.monthlyIncome) S.income = R.monthlyIncome;
    S.expenses = expenses; S.subs = subs;
    S.swaps = S.swaps.filter(w => linkedItem(w));
    if (S.example) S.codes = S.codes.filter(c => c.mine);  // the sample promo codes leave with the example month
    S.example = false;
  } else {
    if (R.monthlyIncome && !S.income) S.income = R.monthlyIncome;
    const has = (list, n) => list.some(x => x.name.toLowerCase() === n.toLowerCase());
    expenses.forEach(e => { if (!has(S.expenses, e.name)) S.expenses.push(e); });
    subs.forEach(s => { const old = S.subs.find(x => x.name.toLowerCase() === s.name.toLowerCase()); if (old){ Object.assign(old, {since: s.since, charges: s.charges, paid: s.paid, lastCharge: s.lastCharge}); if (!old.renewDay && !old.renewDate) setRenewalFrom(old, s.lastCharge); } else S.subs.push(s); });
  }
  S.payday = R.income[0] ? R.income[0].payday : S.payday;
  S.imported = {file: R.fileName, when: isoDaysAgo(0), from: R.first, to: R.last};
  S.hideNote = true;
  save();
}

async function readStatementFile(file){
  const name = file.name || "statement";
  if (/\.pdf$/i.test(name) || file.type === "application/pdf"){
    const buf = await file.arrayBuffer();
    const lines = await pdfLines(buf), R = analyzeStatement(txFromLines(lines), name); R.cur = detectCurrency(lines.join(" ")); return R;
  }
  const text = await file.text(), R = analyzeStatement(txFromCSV(text), name); R.cur = detectCurrency(text); return R;
}
// ---- statements in another currency ----
// Guess the statement's currency from symbols and codes in the file. Dollars and rupees are shared by several
// currencies, so those only count as different when the plan is not in one of them.
const CUR_FAMILY = {USD: "$", CAD: "$", AUD: "$", INR: "Rs", PKR: "Rs"};
function detectCurrency(text){
  const t = String(text).slice(0, 200000), n = re => (t.match(re) || []).length;
  const score = {GBP: n(/£|\bGBP\b/g), EUR: n(/€|\bEUR\b/g), AED: n(/\bAED\b|\bDhs?\b/g), USD: n(/\bUSD\b|US\$/g), CAD: n(/\bCAD\b|C\$|CA\$/g), AUD: n(/\bAUD\b|A\$|AU\$/g), INR: n(/₹|\bINR\b/g), PKR: n(/\bPKR\b/g)};
  const dollars = n(/\$/g), rupees = n(/\bRs\.?\s?\d/g);
  const best = Object.entries(score).sort((a, b) => b[1] - a[1])[0];
  if (best[1] >= 2 && best[1] >= dollars / 2) return best[0];
  if (dollars >= 2) return CUR_FAMILY[S.cur] === "$" ? S.cur : "USD";
  if (rupees >= 2) return CUR_FAMILY[S.cur] === "Rs" ? S.cur : "PKR";
  return best[1] >= 1 ? best[0] : null;
}
const curName = c => (CURRENCIES.find(x => x[0] === c) || [c, c])[1];
function fxScaled(R){  // the statement's numbers in the plan's currency
  const fx = STMT.fx, k = fx && fx.mode === "convert" ? numv(fx.rate) : 1; if (!k || k === 1) return R;
  const m = v => r2((+v || 0) * k);
  return {...R, monthlyIncome: m(R.monthlyIncome), otherIn: m(R.otherIn), taxMonthly: m(R.taxMonthly), monthlyOut: m(R.monthlyOut),
    income: R.income.map(x => ({...x, monthly: m(x.monthly)})), subs: R.subs.map(x => ({...x, price: m(x.price), monthly: m(x.monthly), paid: m(x.paid)})),
    bills: R.bills.map(x => ({...x, monthly: m(x.monthly)})), taxes: R.taxes.map(x => ({...x, total: m(x.total), monthly: m(x.monthly)})), spending: R.spending.map(x => ({...x, monthly: m(x.monthly)}))};
}
const fxReady = () => { const fx = STMT.fx; return !fx || fx.mode !== "convert" || numv(fx.rate) > 0; };
function fxCard(){
  const fx = STMT.fx, R = STMT.result;
  if (!fx) return `<button class="link plain small" type="button" data-fx-open style="align-self:center">Is this statement in another currency?</button>`;
  const opt = (mode, title, body) => `<label class="fx-opt${fx.mode === mode ? " on" : ""}"><input type="radio" name="fxmode" value="${mode}" ${fx.mode === mode ? "checked" : ""}><span><b>${title}</b>${body || ""}</span></label>`;
  return `<section class="card fx-card"><h3>${R.cur && R.cur === fx.from ? `This statement looks like it’s in ${esc(curName(fx.from))}s.` : "Which currency is this statement in?"}</h3>
    <p class="muted small">Your plan is in ${esc(curName(S.cur))}s (${S.cur}). Choose what to do with these numbers.</p>
    <label class="field"><span>Statement currency</span><select data-fx-from>${CURRENCIES.filter(([c]) => c !== S.cur).map(([c, n]) => `<option value="${c}" ${c === fx.from ? "selected" : ""}>${c} · ${n}</option>`).join("")}</select></label>
    ${opt("convert", `Convert to ${S.cur}`, `<span class="fx-rate">1 ${esc(fx.from)} = <input data-fx-rate inputmode="decimal" enterkeyhint="done" placeholder="rate" value="${esc(fx.rate)}" aria-label="How many ${S.cur} one ${esc(fx.from)} is worth"> ${S.cur}</span><small class="muted">Use the rate your bank gave you. KeepWise does not look rates up.</small>`)}
    ${opt("same", "Use the numbers as they are", `<small class="muted">Pick this if the statement is really in ${S.cur}.</small>`)}
    ${opt("switch", `Switch my plan to ${esc(fx.from)}`, `<small class="muted">Your existing numbers stay as typed. Only the currency label changes.</small>`)}</section>`;
}

// ---- review screen ----
const monthsLabel = iso => { if (!iso) return ""; const [y, m] = iso.split("-").map(Number); return new Date(y, m - 1, 1).toLocaleString("en-US", {month: "short", year: "numeric"}); };
function paidFor(s){ if (!s.since) return ""; const [y, m, d] = s.since.split("-").map(Number); const mo = Math.max(1, Math.round((todayMid() - new Date(y, m - 1, d)) / (30.44 * DAY))); return `Paying since ${monthsLabel(s.since)} · ${s.charges} charge${s.charges === 1 ? "" : "s"} · ${fmt(s.paid)} so far`; }
V.importReview = () => {
  const R = STMT.result;
  if (!R) return "";
  return `<div class="inline" style="justify-content:space-between"><h1>Your statement</h1><button class="btn small" type="button" data-import-cancel>Cancel</button></div>
  <p class="muted" style="text-align:center">${esc(R.fileName)} · ${R.count} transactions · ${monthsLabel(R.first)} to ${monthsLabel(R.last)} (${R.months} month${R.months > 1 ? "s" : ""}). Read on this phone only.</p>
  <div data-out="fxCard">${fxCard()}</div>
  <div data-out="importBody" class="import-body">${OUT.importBody()}</div>`;
};
OUT.fxCard = fxCard;
OUT.importBody = () => {
  const R = fxScaled(STMT.result), fx = STMT.fx; FMT_CUR = fx && fx.mode === "switch" ? fx.from : null;
  const row = (a, b, c) => `<div class="line"><div><div>${esc(a)}</div>${c ? `<div class="muted small">${esc(c)}</div>` : ""}</div><span class="tnum">${b}</span></div>`;
  const left = R.monthlyIncome - R.monthlyOut;
  const html = `  <section class="hero"><p class="label">A typical month</p>
    <div class="big tnum" style="${fitSize(fmt(left), 3, 88)}${left < 0 ? ";color:var(--rust)" : ""}">${fmt(left)}</div>
    <p class="muted">${fmt(R.monthlyIncome)} comes in, ${fmt(R.monthlyOut)} goes out${R.taxMonthly ? `, including ${fmt(R.taxMonthly)} of tax payments` : ""}.</p></section>
  <section class="card"><h2>Money coming in</h2>
    ${R.income.length ? R.income.map(s => row(s.name, fmt(s.monthly) + "/mo", s.count === 1 ? `One deposit${s.payday ? `, on the ${ordinal(s.payday)}` : ""}` : `${s.cadence === "irregular" ? "Irregular" : s.cadence[0].toUpperCase() + s.cadence.slice(1)}${s.payday ? ` · usually on the ${ordinal(s.payday)}` : ""} · ${s.count} deposits`)).join("") : `<p class="muted">No regular salary found. You can type your income on the Month tab.</p>`}
    ${R.otherIn ? `<p class="muted small">Plus about ${fmt(R.otherIn)}/mo of transfers and refunds, left out of the plan.</p>` : ""}</section>
  <section class="card"><h2>Subscriptions <span class="muted small">(${R.subs.length})</span></h2>
    ${R.subs.length ? R.subs.map(s => row(s.name, fmt(s.price) + (s.cycle === "yr" ? "/yr" : "/mo"), paidFor(s))).join("") : `<p class="muted">No subscriptions found.</p>`}
    ${R.subs.length ? `<p class="small"><b>${fmt(R.subs.reduce((a, s) => a + s.monthly, 0))}</b> a month, <b>${fmt(R.subs.reduce((a, s) => a + s.paid, 0))}</b> paid in this statement.</p>` : ""}</section>
  <section class="card"><h2>Bills</h2>${R.bills.length ? R.bills.map(b => row(b.name, fmt(b.monthly) + "/mo", b.cat)).join("") : `<p class="muted">No regular bills found.</p>`}
    ${R.taxes.length ? R.taxes.map(t => row(t.name, fmt(t.monthly) + "/mo", `Tax · ${fmt(t.total)} in this statement`)).join("") : ""}</section>
  <section class="card"><h2>Everyday spending</h2>${R.spending.length ? R.spending.map(s => row(s.name, fmt(s.monthly) + "/mo", s.env === "needs" ? "Expenditures" : "Miscellaneous")).join("") : `<p class="muted">Nothing else found.</p>`}</section>
  ${fxReady() ? "" : `<p class="err" style="text-align:center">Type the exchange rate above, or pick another option, before adding this to your plan.</p>`}
  <div class="grid2"><button class="btn" type="button" data-import-apply="merge" ${fxReady() ? "" : "disabled"}>Add to my plan</button><button class="btn primary" type="button" data-import-apply="replace" style="padding:10px" ${fxReady() ? "" : "disabled"}>Use this as my plan</button></div>
  <p class="muted small" style="text-align:center">“Use this as my plan” replaces your income, lines and subscriptions. Splits, codes and savings stay.</p>`;
  FMT_CUR = null; return html;
};
const ordinal = n => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th","st","nd","rd"][n % 10] || "th");

// ---- occasional subscription check-in ----
function reviewPick(){
  const today = isoDaysAgo(0);
  if (S.reviewSnooze === today) return null;
  const cands = S.subs.filter(s => s.keep !== "drop" && !isOurs(s) && (!s.reviewedAt || daysSince(s.reviewedAt) > 30)).sort((a, b) => subMonthly(b) - subMonthly(a)).slice(0, 5);
  if (!cands.length) return null;
  let h = 0; for (const ch of today) h = (h * 31 + ch.charCodeAt(0)) >>> 0; // same pick all day, a different one tomorrow
  return cands[h % cands.length];
}
OUT.reviewCard = () => {
  const s = reviewPick(); if (!s) return "";
  const since = s.since ? `You’ve paid ${fmt(s.paid || 0)} since ${monthsLabel(s.since)}.` : `It costs ${fmt(subMonthly(s))} a month.`;
  return `<section class="card review" data-review-id="${s.id}"><p class="label">Quick check</p>
    <h3 style="font-size:1.15rem">How much do you use ${esc(s.name)}?</h3>
    <p class="muted">${since}</p>
    <div class="review-btns"><button class="btn" type="button" data-review="lot">A lot</button><button class="btn" type="button" data-review="barely">Barely</button><button class="btn danger" type="button" data-review="none">Not at all</button></div>
    <button class="link plain small" type="button" data-review="later" style="align-self:center">Ask me later</button></section>`;
};
function handleReview(kind, id){
  if (kind === "later"){ S.reviewSnooze = isoDaysAgo(0); save(); refreshOuts(); return; }
  const s = S.subs.find(x => x.id === id); if (!s) return;
  s.reviewedAt = isoDaysAgo(0); remindSeen();
  if (kind === "lot"){ s.last = isoDaysAgo(0); s.low = false; toast(`Keeping ${s.name}.`); }
  if (kind === "barely"){ s.low = true; s.keep = "auto"; toast(`${s.name} is flagged. Review it on Subs.`); }
  if (kind === "none"){ s.keep = "drop"; toast(`${s.name} marked to drop. Your month updated.`); }
  save(); refreshOuts();
}
