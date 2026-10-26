"""Sends "Sam shared a split with you" to friends on KeepWise who turned notifications on.

Runs every 10 minutes from GitHub Actions. Reads only the ping collection (who to nudge and the sender's first name)
and the push addresses saved for that person. No amounts or split details are sent. Each ping is removed once handled.
Needs the FCM_SERVICE_ACCOUNT secret; without it, it does nothing.
"""
import json, os, sys, time, urllib.request, urllib.error

PROJECT = "keepwise-c28c3"

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
    def listall(col):
        docs, page = [], None
        while True:
            res = call(f"{base}/{col}?pageSize=300" + (f"&pageToken={page}" if page else ""))
            docs += res.get("documents", []); page = res.get("nextPageToken")
            if not page: return docs
    pings = listall("ping")
    if not pings: print("No pings."); return
    tokens = {}
    for d in listall("push"):
        f = d.get("fields", {}); uid = f.get("uid", {}).get("stringValue", ""); tok = f.get("token", {}).get("stringValue", "")
        if uid and tok: tokens.setdefault(uid, []).append((tok, d["name"]))
    who = {}
    for p in pings:
        f = p.get("fields", {}); uid = f.get("uid", {}).get("stringValue", ""); name = f.get("from", {}).get("stringValue", "")[:40] or "A friend"
        who.setdefault(uid, set()).add(name)
        try: call(f"https://firestore.googleapis.com/v1/{p['name']}", method="DELETE")
        except Exception: pass
    sent = 0
    for uid, names in who.items():
        names = sorted(names); body = f"{names[0]} shared a split with you." if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]} shared splits with you."
        for tok, name in tokens.get(uid, []):
            msg = {"message": {"token": tok, "webpush": {"headers": {"Urgency": "normal", "TTL": "86400"},
                   "data": {"title": "KeepWise", "body": body + " Open KeepWise to add it.", "tag": "keepwise-split", "url": "https://mykeepwise.com/"}}}}
            try: call(f"https://fcm.googleapis.com/v1/projects/{PROJECT}/messages:send", msg); sent += 1
            except urllib.error.HTTPError as e:
                if e.code in (404, 410):
                    try: call(f"https://firestore.googleapis.com/v1/{name}", method="DELETE")
                    except Exception: pass
                else: print("send failed:", e.code, file=sys.stderr)
    print(f"{len(pings)} pings, {sent} sent")

if __name__ == "__main__":
    main()
