"""Z.ai / Zhipu GLM Coding Plan: 5-hour and weekly token windows, monthly tool quota (endpoint the console uses)."""
from .. import core
from .base import Provider, Fields, Field, window, balance

REGIONS = [["global", "Global (api.z.ai)"], ["cn", "China (open.bigmodel.cn)"]]
BASE = {"global": "https://api.z.ai", "cn": "https://open.bigmodel.cn"}
UNIT = {1: 86400, 3: 3600, 5: 60, 6: 7 * 86400}


class Zai(Provider):
    id = "zai"
    name = "Z.ai GLM Coding Plan"
    vendor = "Zhipu AI"
    color = "#2d5bff"
    mono = "Z"
    blurb = "Coding plan windows (5-hour, weekly), tool calls per month; China: account balance"
    options = [Field("region", "Region", "select", options=REGIONS, default="global",
                     help="A key only works in the region it was made in.")]
    auths = [Fields([Field("key", "API key", "secret", "your z.ai / bigmodel API key")])]

    def fetch(self, acct):
        base = BASE.get(acct.options.get("region"), BASE["global"])
        d = self.get(acct, base + "/api/monitor/usage/quota/limit")
        if d.get("success") is False or (d.get("code") not in (None, 200)):
            raise RuntimeError(f"Z.ai: {d.get('msg') or d.get('message') or 'error'} (does this account have a coding plan?)")
        out = parse(d.get("data") or {})
        if acct.options.get("region") == "cn":
            try:
                b = self.get(acct, "https://www.bigmodel.cn/api/biz/account/query-customer-account-report")
                v = (b.get("data") or {}).get("availableBalance")
                if v is not None:
                    out.setdefault("balances", []).append(balance("balance", "Account balance", v, "CNY"))
            except Exception:
                pass
        return out


def parse(data):
    wins = []
    for l in data.get("limits") or []:
        sec = UNIT.get(int(l.get("unit") or 0), 0) * int(l.get("number") or 0) or None
        typ = l.get("type") or "LIMIT"
        if typ == "TIME_LIMIT":
            label, sec = "Tool calls (monthly)", sec or 30 * 86400
        else:
            label = ("5-hour" if sec == 18000 else "Weekly" if sec == 604800 else "Daily" if sec == 86400
                     else f"{round(sec / 3600)}-hour" if sec else "Limit") + (" credits" if typ == "CREDIT_LIMIT" else "")
        used, lim, rem = core.num(l.get("currentValue")), core.num(l.get("usage")), core.num(l.get("remaining"))
        if used is None and lim is not None and rem is not None:
            used = lim - rem
        pct = core.num(l.get("percentage"))
        wins.append(window(f"{typ}_{sec}".lower(), label, pct, used=used, limit=lim, resets=l.get("nextResetTime"),
                           period=sec))
    long_ = [w for w in wins if not w["id"].startswith("time_limit")]
    if long_:
        max(long_, key=lambda w: w["period"] or 0)["primary"] = True
    plan = data.get("planName") or data.get("plan") or data.get("plan_type") or data.get("packageName") or data.get("level")
    return {"plan": plan, "windows": wins}
