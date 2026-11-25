"""Windsurf (Devin): daily and weekly quota from windsurf.com's GetPlanStatus (Connect protocol, binary protobuf).

Follows CodexBar's WindsurfWebFetcher.swift: the request is SeatManagementService/GetPlanStatus with
field 1 = auth token (string), field 2 = include_top_up_status (bool); the answer's field 1 is PlanStatus:
1 plan_info{1 teams_tier, 2 plan_name}, 2 plan_start{1 s}, 3 plan_end{1 s}, 12 grace_period_status,
14 daily_quota_remaining_percent, 15 weekly_quota_remaining_percent, 17 daily_reset_unix, 18 weekly_reset_unix."""
import json, re, urllib.error, urllib.request
from datetime import datetime, timezone
from .. import core
from .base import Provider, Fields, Field, window, DAY, WEEK

URL = "https://windsurf.com/_backend/exa.seat_management_pb.SeatManagementService/GetPlanStatus"
SNIPPET = ("On windsurf.com/profile open the DevTools console and run: copy(JSON.stringify(Object.fromEntries("
           "['devin_session_token','devin_auth1_token','devin_account_id','devin_primary_org_id']"
           ".map(k=>{let v=localStorage.getItem(k);try{v=JSON.parse(v)}catch(e){}return [k,v]})))) and paste the result.")


# ---------------------------------------------------------------- minimal protobuf
def varint(n):
    out = bytearray()
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def encode_request(token, top_up=True):
    t = token.encode()
    return varint((1 << 3) | 2) + varint(len(t)) + t + varint((2 << 3) | 0) + varint(1 if top_up else 0)


def read_varint(b, i):
    shift = n = 0
    while True:
        if i >= len(b):
            raise ValueError("truncated protobuf payload")
        c = b[i]
        i += 1
        n |= (c & 0x7F) << shift
        if not c & 0x80:
            return n, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def fields(b):
    """Yield (number, wire_type, value): value is int for varint/fixed, bytes for length-delimited."""
    i = 0
    while i < len(b):
        key, i = read_varint(b, i)
        num, wt = key >> 3, key & 7
        if num == 0:
            raise ValueError("malformed protobuf field key")
        if wt == 0:
            v, i = read_varint(b, i)
        elif wt == 1:
            v, i = int.from_bytes(b[i:i + 8], "little"), i + 8
        elif wt == 2:
            ln, i = read_varint(b, i)
            v, i = bytes(b[i:i + ln]), i + ln
        elif wt == 5:
            v, i = int.from_bytes(b[i:i + 4], "little"), i + 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wt}")
        if i > len(b):
            raise ValueError("truncated protobuf payload")
        yield num, wt, v


def _ts(b):
    return next((v for n, w, v in fields(b) if n == 1 and w == 0), 0)


def decode_plan_status(data):
    ps = next((v for n, w, v in fields(data) if n == 1 and w == 2), None)
    if ps is None:
        return None
    out = {}
    for n, w, v in fields(ps):
        if n == 1 and w == 2:
            for n2, w2, v2 in fields(v):
                if n2 == 1 and w2 == 0:
                    out["teams_tier"] = v2
                elif n2 == 2 and w2 == 2:
                    out["plan_name"] = v2.decode(errors="replace")
        elif n in (2, 3) and w == 2:
            out["plan_start" if n == 2 else "plan_end"] = _ts(v)
        elif w == 0 and n in (12, 14, 15, 17, 18):
            out[{12: "grace", 14: "daily_left", 15: "weekly_left", 17: "daily_reset", 18: "weekly_reset"}[n]] = v
    return out


def parse_windsurf(data):
    ps = decode_plan_status(data)
    if ps is None:
        raise RuntimeError("Windsurf answered without a plan status")
    wins = []
    if "daily_left" in ps:
        wins.append(window("daily", "Daily quota", max(0, min(100, 100 - ps["daily_left"])), resets=ps.get("daily_reset") or None,
                           period=DAY))
    if "weekly_left" in ps:
        wins.append(window("weekly", "Weekly quota", max(0, min(100, 100 - ps["weekly_left"])),
                           resets=ps.get("weekly_reset") or None, period=WEEK, primary=True))
    if not wins:
        raise RuntimeError("Windsurf: this plan reports no daily or weekly quota")
    if not any(w["primary"] for w in wins):
        wins[0]["primary"] = True
    info = []
    if ps.get("plan_end"):
        info.append({"label": "Plan ends", "value": datetime.fromtimestamp(ps["plan_end"], timezone.utc).strftime("%Y-%m-%d")})
    return {"plan": ps.get("plan_name"), "windows": wins, "info": info}


# ---------------------------------------------------------------- session bundle
KEYS = {"session": ["devin_session_token", "devinSessionToken", "sessionToken"],
        "auth1": ["devin_auth1_token", "devinAuth1Token", "auth1Token"],
        "account": ["devin_account_id", "devinAccountId", "accountID", "accountId"],
        "org": ["devin_primary_org_id", "devinPrimaryOrgId", "primaryOrgID", "primaryOrgId"]}


def parse_bundle(raw):
    raw = (raw or "").strip()
    vals = {}
    try:
        j = json.loads(raw)
        if isinstance(j, dict):
            vals = {k: v for k, v in j.items() if isinstance(v, str)}
    except ValueError:
        for seg in re.split(r"[\n,;]", raw.strip("{}")):
            m = re.match(r"\s*\"?([\w]+)\"?\s*[=:]\s*(.+?)\s*$", seg)
            if m:
                vals[m.group(1)] = m.group(2).strip("\"'")
    out = {}
    for k, names in KEYS.items():
        out[k] = next((vals[n].strip() for n in names if (vals.get(n) or "").strip()), None)
    if not all(out.values()):
        raise ValueError("expected devin_session_token, devin_auth1_token, devin_account_id and devin_primary_org_id")
    return out


class Windsurf(Provider):
    id = "windsurf"
    name = "Windsurf"
    vendor = "Cognition"
    color = "#0b9b8a"
    mono = "Ws"
    blurb = "Daily and weekly quota left, plan end"
    help = SNIPPET
    auths = [Fields([Field("bundle", "Session bundle (JSON)", "secret", '{"devin_session_token": "…", …}', help=SNIPPET)],
                    id="bundle", label="Session bundle")]

    def fetch(self, acct):
        try:
            a = parse_bundle(acct.creds["bundle"])
        except ValueError as e:
            raise RuntimeError("Windsurf session bundle: " + str(e)) from None
        h = {"Content-Type": "application/proto", "Connect-Protocol-Version": "1", "User-Agent": core.UA,
             "Origin": "https://windsurf.com", "Referer": "https://windsurf.com/profile",
             "x-auth-token": a["session"], "x-devin-session-token": a["session"], "x-devin-auth1-token": a["auth1"],
             "x-devin-account-id": a["account"], "x-devin-primary-org-id": a["org"]}
        req = urllib.request.Request(URL, data=encode_request(a["session"]), headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403):
                raise RuntimeError(f"Windsurf refused the session ({e.code}): paste a fresh session bundle") from None
            raise core.HttpError(e.code, e.read().decode(errors="replace"), URL) from None
        try:
            return parse_windsurf(body)
        except ValueError as e:
            raise RuntimeError("Windsurf answer could not be decoded: " + str(e)) from None
