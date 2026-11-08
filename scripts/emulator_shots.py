"""Screenshots of the real Android app on an emulator, for the emulator check in CI.

Installs nothing itself: the workflow installs the debug APK first. This starts the app, opens the example month through
the web view's debugging port (debug builds only), visits each main screen, and saves what the phone actually shows.
Run: python3 scripts/emulator_shots.py <out-dir> <label>
"""
import json, os, subprocess, sys, time, urllib.request
import websocket

PKG = "com.mykeepwise.app"
OUT, LABEL = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)

def adb(*a, check=True):
    return subprocess.run(["adb", *a], check=check, capture_output=True, text=True).stdout.strip()

def shot(name):
    with open(os.path.join(OUT, f"{LABEL}-{name}.png"), "wb") as f:
        f.write(subprocess.run(["adb", "exec-out", "screencap", "-p"], check=True, capture_output=True).stdout)

def start():
    adb("shell", "am", "force-stop", PKG)
    adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(12)

def devtools():
    for _ in range(30):
        socks = [l.split("@")[-1] for l in adb("shell", "cat", "/proc/net/unix").splitlines() if "webview_devtools_remote" in l]
        if socks:
            adb("forward", "tcp:9222", "localabstract:" + socks[-1])
            pages = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json"))
            pages = [p for p in pages if p.get("type") == "page"]
            if pages:
                return websocket.create_connection(pages[0]["webSocketDebuggerUrl"], suppress_origin=True)
        time.sleep(2)
    raise SystemExit("no web view to talk to")

N = [0]
def cdp(ws, method, **params):
    N[0] += 1; ws.send(json.dumps({"id": N[0], "method": method, "params": params}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == N[0]: return m

def js(_ws, code):
    global ws
    for attempt in range(3):
        try:
            r = cdp(ws, "Runtime.evaluate", expression=code, awaitPromise=True, returnByValue=True)
            return r.get("result", {}).get("result", {}).get("value")
        except Exception as e:   # the debugging link can drop on a slow emulator: connect again and retry
            print("reconnecting:", e); time.sleep(3)
            try: ws.close()
            except Exception: pass
            ws = devtools()

start()
shot("0-launch")                      # what a new person sees first
ws = devtools()
cdp(ws, "Page.enable")
cdp(ws, "Page.addScriptToEvaluateOnNewDocument", source="window.KEEPWISE_NO_SETUP = true;")
js(ws, "localStorage.clear()"); cdp(ws, "Page.reload"); time.sleep(6)
ws.close(); ws = devtools()

def tap_tab(k):
    js(ws, f"""(() => {{ document.querySelectorAll('.kw-page .sf-top button').forEach(b => b.click());
      const t = document.querySelector('[data-tab="{k}"]'); if (t) t.click(); document.getElementById('main') && (document.getElementById('main').scrollTop = 0); }})()""")
    time.sleep(2.5)

errs = []
for k in ("month", "subs", "banks", "split"):
    tap_tab(k); shot("1-" + k)
    w = js(ws, "[document.documentElement.scrollWidth, innerWidth, [...document.querySelectorAll('#view *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && (r.right > innerWidth + 1 || r.left < -1) && !e.closest('.chip-row,.quick-grid,[data-scroll-x]'); }).slice(0, 4).map(e => e.tagName + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().left) + '-' + Math.round(e.getBoundingClientRect().right) + ' in .' + e.parentElement.className + ' : ' + (e.innerText || '').slice(0, 30))]")
    if w and (w[0] > w[1] or w[2]): errs.append(f"{k}: wider than the screen {w}")
tap_tab("month")
js(ws, "document.getElementById('wise').click()"); time.sleep(2); shot("2-owl")
js(ws, "document.querySelector('.ask-back') && document.querySelector('.ask-back').click()"); time.sleep(1)
print(LABEL, "native bridges:", js(ws, "JSON.stringify(['WidgetBridge','VoiceBridge','IconBridge'].map(n => [n, !!(window.Capacitor && Capacitor.isPluginAvailable(n))]))"))
print(LABEL, "mic button shown:", js(ws, "(document.getElementById('wise').click(), new Promise(r => setTimeout(() => r(!!document.getElementById('ask-mic') && !document.getElementById('ask-mic').hidden), 1500)))"))
# the home screen icon follows the theme: pick Night Owl, leave the app, and see which launcher entry is on
js(ws, "(() => { const b = document.createElement('button'); b.setAttribute('data-skin-set', 'owl'); b.hidden = true; document.getElementById('view').appendChild(b); b.click(); b.remove(); })()")
time.sleep(2); print(LABEL, "theme now:", js(ws, "document.documentElement.dataset.skin"))
print(LABEL, "icon call:", js(ws, "Capacitor.registerPlugin('IconBridge').set({name: 'owl'}).then(() => 'ok', e => 'error: ' + (e && e.message))"))
print(LABEL, "prefs files:", adb("shell", "run-as", PKG, "ls", "shared_prefs", check=False))
adb("shell", "input", "keyevent", "KEYCODE_HOME"); time.sleep(6)
print(LABEL, "icon prefs:", adb("shell", "run-as", PKG, "cat", "shared_prefs/keepwise_icon.xml", check=False))
print(LABEL, "log:", "\n".join(l for l in adb("logcat", "-d", "-t", "400", check=False).splitlines() if "Icon" in l or "IconBridge" in l)[-1500:])
on = adb("shell", "cmd", "package", "query-activities", "--brief", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", check=False)
icon = [l.strip() for l in on.splitlines() if PKG in l]
print(LABEL, "launcher entry after picking Night Owl:", icon)
if not any("Icon_owl" in l for l in icon): errs.append(f"icon did not follow the theme: {icon}")
adb("shell", "input", "swipe", "500", "1500", "500", "300", "300", check=False); time.sleep(3); shot("3-app-drawer")
if errs:
    print("LAYOUT PROBLEMS", *errs, sep="\n"); sys.exit(1)
print(LABEL, "ok")
