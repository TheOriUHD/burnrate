"""Cursor (Free, Pro, Pro+, Ultra, Teams): included plan usage and on-demand spend (dashboard endpoints, unofficial)."""
import urllib.parse
from .. import core
from .base import Provider, Fields, Field, window, balance


def cookie(raw):
    v = raw.strip()
    if "WorkosCursorSessionToken=" in v:
        v = v.split("WorkosCursorSessionToken=", 1)[1].split(";", 1)[0]
    v = urllib.parse.unquote(v)
    if "::" not in v:      # bare JWT: prefix the user id from its sub claim
        sub = core.jwt_claims(v).get("sub", "")
        v = sub.split("|")[-1] + "::" + v
    return "WorkosCursorSessionToken=" + urllib.parse.quote(v, safe="")


class Cursor(Provider):
    id = "cursor"
    name = "Cursor"
    vendor = "Anysphere"
    color = "#3b3b3b"
    blurb = "Included usage of your plan this billing cycle, on-demand spend"
    help = ("Paste the WorkosCursorSessionToken cookie from cursor.com (DevTools → Application → Cookies). "
            "It lasts weeks; reconnect when it expires.")
    auths = [Fields([Field("cookie", "Session cookie", "secret", "WorkosCursorSessionToken value")], id="cookie",
                    label="Session cookie")]

    def fetch(self, acct):
        h = {"Cookie": cookie(acct.creds["cookie"]), "Origin": "https://cursor.com", "Referer": "https://cursor.com/dashboard"}
        try:
            d = core.http("GET", "https://cursor.com/api/usage-summary", headers=h)
        except core.HttpError as e:
            if e.code in (401, 403):
                raise RuntimeError("Cursor refused the session cookie (expired?): reconnect in Settings") from None
            raise
        return parse(d)


def parse(d):
    start, end = core.iso_ts(d.get("billingCycleStart")), core.iso_ts(d.get("billingCycleEnd"))
    period = (end - start) if start and end else None
    iu = d.get("individualUsage") or {}
    plan = iu.get("plan") or {}
    wins, bals = [], []
    if plan.get("limit") or plan.get("totalPercentUsed") is not None:
        wins.append(window("plan", "Included usage", plan.get("totalPercentUsed"),
                           used=(core.num(plan.get("used")) or 0) / 100 if plan.get("used") is not None else None,
                           limit=(core.num(plan.get("limit")) or 0) / 100 if plan.get("limit") is not None else None,
                           unit="USD", resets=end, period=period, primary=True))
    od = iu.get("onDemand") or {}
    if od.get("used") is not None:
        bals.append(balance("ondemand", "On-demand", (core.num(od.get("used")) or 0) / 100, "USD",
                            limit=(core.num(od["limit"]) / 100) if od.get("limit") else None, kind="spent"))
    tu = (d.get("teamUsage") or {}).get("onDemand") or {}
    if tu.get("used") is not None:
        bals.append(balance("team_ondemand", "Team on-demand", (core.num(tu.get("used")) or 0) / 100, "USD",
                            limit=(core.num(tu["limit"]) / 100) if tu.get("limit") else None, kind="spent"))
    m = d.get("membershipType")
    return {"plan": str(m).replace("_", " ").title() if m else None, "windows": wins, "balances": bals,
            "info": [{"label": "Unlimited", "value": "yes"}] if d.get("isUnlimited") else []}
