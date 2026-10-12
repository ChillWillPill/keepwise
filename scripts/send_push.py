"""Sends the KeepWise payday nudge to web app users who turned notifications on.

Runs once a day from GitHub Actions. It reads only the push collection (a push address, the nudge
dates the phone worked out, and a time zone). Nothing about anyone's money is stored or sent.
Needs the FCM_SERVICE_ACCOUNT secret; without it, it does nothing.
"""
import datetime, json, os, sys, urllib.request, urllib.error
from zoneinfo import ZoneInfo

PROJECT = "keepwise-c28c3"
TITLE = "Payday is in two days"
BODY = "A good moment to check what you pay for. Open KeepWise and see what you keep this month."

def main():
    raw = os.environ.get("FCM_SERVICE_ACCOUNT", "").strip()
    if not raw:
        print("No FCM_SERVICE_ACCOUNT secret yet: nothing sent."); return
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    cred = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=[
        "https://www.googleapis.com/auth/firebase.messaging", "https://www.googleapis.com/auth/datastore"])
    cred.refresh(Request()); auth = {"Authorization": "Bearer " + cred.token, "Content-Type": "application/json"}

    def call(url, body=None, method=None):
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=auth, method=method)
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read() or b"{}")

    base = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"
    docs, page = [], None
    while True:
        res = call(f"{base}/push?pageSize=300" + (f"&pageToken={page}" if page else ""))
        docs += res.get("documents", []); page = res.get("nextPageToken")
        if not page: break
    sent = gone = 0
    for d in docs:
        f = d.get("fields", {}); token = f.get("token", {}).get("stringValue", "")
        dates = [v.get("stringValue", "") for v in f.get("dates", {}).get("arrayValue", {}).get("values", [])]
        try: tz = ZoneInfo(f.get("tz", {}).get("stringValue", "UTC"))
        except Exception: tz = ZoneInfo("UTC")
        today = datetime.datetime.now(tz).date().isoformat()
        if not token or today not in dates: continue
        msg = {"message": {"token": token, "webpush": {"headers": {"Urgency": "normal", "TTL": "43200"},
               "data": {"title": TITLE, "body": BODY, "tag": "keepwise-payday", "url": "https://mykeepwise.com/"}}}}
        try:
            call(f"https://fcm.googleapis.com/v1/projects/{PROJECT}/messages:send", msg); sent += 1
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):   # the browser forgot this address: remove it
                try: call(f"https://firestore.googleapis.com/v1/{d['name']}", method="DELETE"); gone += 1
                except Exception: pass
            else: print("send failed:", e.code, file=sys.stderr)
    print(f"{len(docs)} devices, {sent} nudged, {gone} removed")

if __name__ == "__main__":
    main()
