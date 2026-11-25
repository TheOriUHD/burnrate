"""Kimi Code subscription windows (Moonshot), plus the Moonshot open platform balance."""
from .. import core
from .base import Provider, Fields, Field, window, balance, HOUR, WEEK

CODE = {"cn": "https://api.kimi.com/coding/v1/usages", "global": "https://api.kimi.ai/coding/v1/usages"}
UNITS = {"TIME_UNIT_MINUTE": 60, "TIME_UNIT_HOUR": 3600, "TIME_UNIT_DAY": 86400}


class KimiCode(Provider):
    id = "kimi"
    name = "Kimi Code"
    vendor = "Moonshot AI"
    color = "#1a1a1a"
    mono = "K"
    blurb = "Kimi coding plan: 5-hour, weekly and monthly windows"
    options = [Field("region", "Service", "select", options=[["global", "kimi.ai (international)"], ["cn", "kimi.com (China)"]],
                     default="global")]
    auths = [Fields([Field("key", "Kimi Code API key", "secret", "sk-…", help="Create it in the Kimi Code console.")])]

    def fetch(self, acct):
        return parse(self.get(acct, CODE.get(acct.options.get("region"), CODE["global"])))


def parse(d):
    wins = []
    for key, label, period in (("limit_5h", "5-hour", 5 * HOUR), ("limit_7d", "Weekly", WEEK),
                               ("limit_month_total", "Monthly", 30 * 86400), ("limit_month_code", "Monthly (code)", 30 * 86400)):
        v = d.get(key)
        if isinstance(v, dict) and v.get("used_ratio") is not None:
            wins.append(window(key, label, core.num(v["used_ratio"]) * 100, resets=v.get("reset_time"), period=period,
                               primary=key == "limit_7d"))
    if not wins:
        u = d.get("usage") or {}
        if u.get("limit") is not None:
            wins.append(window("week", "Weekly", used=u.get("used"), limit=u.get("limit"), resets=u.get("resetTime"),
                               period=WEEK, primary=True))
        for l in d.get("limits") or []:
            w, det = l.get("window") or {}, l.get("detail") or {}
            sec = (core.num(w.get("duration")) or 0) * UNITS.get(w.get("timeUnit"), 60)
            if det.get("limit") is not None:
                wins.append(window(f"w{int(sec)}", f"{round(sec / 3600)}-hour" if sec else "Limit", used=det.get("used"),
                                   limit=det.get("limit"), resets=det.get("resetTime"), period=int(sec) or None))
    lvl = d.get("level") or (d.get("user") or {}).get("level")
    return {"plan": str(lvl).replace("LEVEL_", "").title() if lvl else None, "windows": wins}


class Moonshot(Provider):
    id = "moonshot"
    name = "Moonshot API"
    vendor = "Moonshot AI"
    color = "#16191e"
    mono = "M"
    category = "api"
    official = True
    blurb = "Open platform balance (cash and voucher)"
    options = [Field("region", "Platform", "select", options=[["global", "platform.moonshot.ai (USD)"], ["cn", "platform.moonshot.cn (CNY)"]],
                     default="global")]
    auths = [Fields([Field("key", "API key", "secret", "sk-…")])]

    def fetch(self, acct):
        cn = acct.options.get("region") == "cn"
        d = (self.get(acct, f"https://api.moonshot.{'cn' if cn else 'ai'}/v1/users/me/balance").get("data")) or {}
        cur = "CNY" if cn else "USD"
        b = [balance("available", "Available", d.get("available_balance"), cur)]
        if core.num(d.get("voucher_balance")):
            b.append(balance("voucher", "Vouchers", d.get("voucher_balance"), cur))
        return {"balances": b}
