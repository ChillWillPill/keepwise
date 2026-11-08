// Draws every KeepWise owl icon from one drawing (owlkit.js): the Android launcher icon for each theme, the splash
// screens, the web icons and the Play Store icon. Run from the repo root: node scripts/icons/make_icons.js
// (needs Playwright's Chromium), then python3 scripts/icons/shrink.py. Output is committed; CI does not run this.
const {chromium} = require('playwright'), fs = require('fs'), path = require('path');
const {owl, T} = require('./owlkit');
const RES = 'android/app/src/main/res', WEB = 'www/icons';
const D = {ldpi: .75, mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4};
const mk = d => fs.mkdirSync(d, {recursive: true});
const page = (w, h, body) => `<html><body style="margin:0;width:${w}px;height:${h}px;overflow:hidden">${body}</body></html>`;
const sized = (svg, s) => svg.replace('<svg ', `<svg width="${s}" height="${s}" `);
(async () => {
  const b = await chromium.launch(), p = await b.newPage();
  const shot = async (file, w, h, html, transparent) => { mk(path.dirname(file)); await p.setViewportSize({width: w, height: h}); await p.setContent(page(w, h, html)); await p.screenshot({path: file, omitBackground: !!transparent}); };
  const icon = (bg, c, s, r) => `<div style="width:${s}px;height:${s}px;border-radius:${r};background:${bg};display:grid;place-items:center;overflow:hidden">${sized(owl(c), s * .86)}</div>`;
  for (const [k, , bg, c] of T){
    const id = k === 'classic' ? 'ic_launcher' : 'ic_kw_' + k;
    for (const [d, f] of Object.entries(D)){
      const L = Math.round(48 * f), A = Math.round(108 * f);
      await shot(`${RES}/mipmap-${d}/${id}.png`, L, L, icon(bg, c, L, Math.round(L * .22) + 'px'), true);
      await shot(`${RES}/mipmap-${d}/${id}_round.png`, L, L, icon(bg, c, L, '50%'), true);
      // adaptive icon: the owl sits inside the 66dp safe circle of a 108dp canvas
      await shot(`${RES}/mipmap-${d}/${id}_foreground.png`, A, A, `<div style="width:${A}px;height:${A}px;display:grid;place-items:center">${sized(owl(c), A * .6)}</div>`, true);
      await shot(`${RES}/mipmap-${d}/${id}_background.png`, A, A, `<div style="width:${A}px;height:${A}px;background:${bg}"></div>`);
    }
    mk(`${RES}/mipmap-anydpi-v26`);
    for (const suf of ['', '_round']) fs.writeFileSync(`${RES}/mipmap-anydpi-v26/${id}${suf}.xml`,
      `<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n    <background android:drawable="@mipmap/${id}_background" />\n    <foreground android:drawable="@mipmap/${id}_foreground" />\n</adaptive-icon>\n`);
  }
  const [, , mbg, mc] = T[0];
  // splash: the owl on the app's own background, light and dark
  for (const f of fs.readdirSync(RES).filter(x => x.startsWith('drawable')))
    if (fs.existsSync(`${RES}/${f}/splash.png`)){
      const buf = fs.readFileSync(`${RES}/${f}/splash.png`); const W = buf.readUInt32BE(16), H = buf.readUInt32BE(20);
      const s = Math.round(Math.min(W, H) * .42), bgc = f.includes('night') ? '#0c1713' : '#f2faf6';
      await shot(`${RES}/${f}/splash.png`, W, H, `<div style="width:${W}px;height:${H}px;background:${bgc};display:grid;place-items:center">${icon(mbg, mc, s, Math.round(s * .24) + 'px')}</div>`);
    }
  // web and store icons (Mint Pop)
  await shot(`${WEB}/icon-512.png`, 512, 512, icon(mbg, mc, 512, '112px'), true);
  await shot(`${WEB}/icon-192.png`, 192, 192, icon(mbg, mc, 192, '42px'), true);
  await shot(`${WEB}/apple-touch-icon.png`, 180, 180, icon(mbg, mc, 180, '0'));
  await shot(`${WEB}/favicon-64.png`, 64, 64, icon(mbg, mc, 64, '50%'), true);
  await shot(`${WEB}/maskable-512.png`, 512, 512, `<div style="width:512px;height:512px;background:${mbg};display:grid;place-items:center">${sized(owl(mc), 330)}</div>`);
  await shot('android/play-store-icon-512.png', 512, 512, icon(mbg, mc, 512, '0'));
  // the small round logo inside the app and the website
  await shot(`${RES}/drawable-nodpi/kw_owl.png`, 192, 192, `<div style="width:192px;height:192px;display:grid;place-items:center">${sized(owl(mc), 184)}</div>`, true);   // the quick add widget's owl
  await shot('scripts/icons/logo-96.png', 96, 96, icon(mbg, mc, 96, '50%'), true);
  await b.close();
})();
