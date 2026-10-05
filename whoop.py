"""Export WHOOP data (profile, body, recovery, cycles, sleep, workouts) to whoop_data.json.

First run:   python whoop.py login     # opens the consent URL, paste back the redirect URL
   or:       python whoop.py code <code or full redirect URL>   # if you built the consent URL yourself
After that:  python whoop.py           # refreshes tokens as needed and exports

Credentials come from the environment, never from this file:
    export WHOOP_CLIENT_ID=...
    export WHOOP_CLIENT_SECRET=...
"""
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request
import webbrowser

CLIENT_ID = os.environ.get("WHOOP_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("WHOOP_CLIENT_SECRET", "")
REDIRECT = os.environ.get("WHOOP_REDIRECT_URI", "https://localhost:8080/callback")
AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
BASE = "https://api.prod.whoop.com/developer"
SCOPES = "offline read:profile read:body_measurement read:recovery read:cycles read:sleep read:workout"
STORE = "whoop_tokens.json"
UA = "whoop-dashboard/1.0"


def post(data):
    req = urllib.request.Request(
        TOKEN_URL, data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=30))


def save(t):
    t["expires_at"] = time.time() + t["expires_in"]
    # write BEFORE using: each refresh kills the old pair, so a lost write locks you out
    with open(STORE, "w") as f:
        json.dump(t, f)
    return t


def login():
    state = secrets.token_urlsafe(12)  # WHOOP requires state of at least 8 chars
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT,
        "scope": SCOPES, "state": state})
    print("Open this URL, approve access, then copy the URL your browser lands on")
    print("(it will fail to load -- that's fine, it just needs to contain ?code=...):\n")
    print(url + "\n")
    webbrowser.open(url)
    back = input("Paste the redirect URL here: ").strip()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(back).query)
    if q.get("state", [None])[0] != state:
        sys.exit("State mismatch -- paste the URL from this login attempt.")
    if "code" not in q:
        sys.exit("No ?code= in that URL: " + back)
    exchange(q["code"][0])


def exchange(code):
    save(post({"grant_type": "authorization_code", "code": code,
               "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
               "redirect_uri": REDIRECT}))
    print(f"Saved tokens to {STORE}.")


def from_code(arg):
    # accepts a bare code or the whole redirect URL; no state check since we didn't make the URL
    q = urllib.parse.parse_qs(urllib.parse.urlparse(arg).query)
    exchange(q["code"][0] if "code" in q else arg)


def tokens():
    if not os.path.exists(STORE):
        sys.exit(f"No {STORE} yet -- run: python whoop.py login")
    with open(STORE) as f:
        t = json.load(f)
    if t["expires_at"] > time.time() + 120:
        return t
    return save(post({"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
                      "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                      "scope": "offline"}))


def get(path, at):
    req = urllib.request.Request(BASE + path,
        headers={"Authorization": "Bearer " + at, "User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=30))


def page(path, at, cap=2000):
    out, tok = [], None
    while True:
        sep = "&" if "?" in path else "?"
        url = f"{path}{sep}limit=25" + (f"&nextToken={urllib.parse.quote(tok)}" if tok else "")
        d = get(url, at)
        out += d.get("records", [])
        tok = d.get("next_token")
        if not tok or len(out) >= cap:
            return out
        time.sleep(0.15)


def export():
    at = tokens()["access_token"]
    data = {
        "profile":  get("/v2/user/profile/basic", at),
        "body":     get("/v2/user/measurement/body", at),
        "recovery": page("/v2/recovery", at),
        "cycles":   page("/v2/cycle", at),
        "sleep":    page("/v2/activity/sleep", at),
        "workouts": page("/v2/activity/workout", at),
    }
    with open("whoop_data.json", "w") as f:
        json.dump(data, f, indent=2)
    print({k: (len(v) if isinstance(v, list) else 1) for k, v in data.items()})


if __name__ == "__main__":
    if not (CLIENT_ID and CLIENT_SECRET):
        sys.exit("Set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET first.")
    args = sys.argv[1:]
    if args == ["login"]:
        login()
    elif len(args) == 2 and args[0] == "code":
        from_code(args[1])
    else:
        export()
