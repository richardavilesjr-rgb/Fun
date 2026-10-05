"""Phone-friendly WHOOP export: prompts for the secret and the redirect URL, writes whoop_data.json."""
import json, os, time, urllib.error, urllib.parse, urllib.request
CLIENT_ID = "32aaeea5-8ee0-4f63-9c9c-c6552341d207"
REDIRECT = "https://localhost:8080/callback"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
BASE = "https://api.prod.whoop.com/developer"
UA = {"User-Agent": "whoop-dashboard/1.0"}
SECRET = input("Paste your WHOOP client secret, then press return: ").strip()


def fetch(req, tries=6):
    # iSH connections drop a lot; retry with backoff instead of dying on the first hiccup
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == tries - 1:
                print("\nWHOOP said:", e.code, e.read().decode(errors="replace")[:300])
                raise
        except Exception as e:
            if i == tries - 1:
                raise
            print("  connection hiccup (%s), retrying..." % type(e).__name__)
        time.sleep(2 ** i)


def post(d):
    r = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(d).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", **UA})
    return fetch(r)


def save(t):
    t["expires_at"] = time.time() + t["expires_in"]
    json.dump(t, open("whoop_tokens.json", "w"))
    return t


def tokens():
    if os.path.exists("whoop_tokens.json"):
        t = json.load(open("whoop_tokens.json"))
        if t["expires_at"] > time.time() + 120:
            return t
        return save(post({"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
            "client_id": CLIENT_ID, "client_secret": SECRET, "scope": "offline"}))
    print("\nTAP AND HOLD THIS LINK, open it, and tap Allow:\n")
    print("https://api.prod.whoop.com/oauth/oauth2/auth?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": "read:recovery read:cycles read:sleep read:workout read:profile read:body_measurement offline",
        "state": "pickanystring12"}) + "\n")
    url = input("Paste the broken-page address here, then press return: ").strip()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    code = q["code"][0] if "code" in q else url
    return save(post({"grant_type": "authorization_code", "code": code,
        "client_id": CLIENT_ID, "client_secret": SECRET, "redirect_uri": REDIRECT}))


def get(p, at):
    r = urllib.request.Request(BASE + p, headers={"Authorization": "Bearer " + at, **UA})
    return fetch(r)


def page(p, at):
    out, tok = [], None
    print("Getting " + p.rsplit("/", 1)[-1] + "...")
    while True:
        d = get(p + "?limit=25" + ("&nextToken=" + urllib.parse.quote(tok) if tok else ""), at)
        out += d.get("records", [])
        print("  %d so far" % len(out))
        tok = d.get("next_token")
        if not tok or len(out) >= 2000:
            return out
        time.sleep(0.15)


at = tokens()["access_token"]
print("Logged in. Downloading your data (keep this screen open)...")
data = {"profile": get("/v2/user/profile/basic", at), "body": get("/v2/user/measurement/body", at),
    "recovery": page("/v2/recovery", at), "cycles": page("/v2/cycle", at),
    "sleep": page("/v2/activity/sleep", at), "workouts": page("/v2/activity/workout", at)}
json.dump(data, open("whoop_data.json", "w"), indent=2)
print("\nDONE! Go back to Claude.", {k: (len(v) if isinstance(v, list) else 1) for k, v in data.items()})
