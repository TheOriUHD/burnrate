"""Coding-agent subscriptions with a simple key: Factory (Droid), Warp, Amp, Synthetic, Ollama Cloud."""
import platform, re
from .. import core
from .base import Provider, Fields, Field, window, balance, HOUR, WEEK


class Factory(Provider):
    id = "factory"
    name = "Factory (Droid)"
    vendor = "Factory"
    color = "#ff6a00"
    mono = "F"
    blurb = "5-hour, weekly and monthly limits, standard/premium token allowance, extra usage balance"
    auths = [Fields([Field("key", "API key", "secret", "fk-…", help="app.factory.ai → Settings → API keys.")])]

    def fetch(self, acct):
        h = {"Origin": "https://app.factory.ai", "x-factory-client": "web-app"}
        wins, bals = [], []
        lim = self.get(acct, "https://api.factory.ai/api/billing/limits", headers=h)
        L = lim.get("limits") or lim
        for tier in ("standard", "premium"):
            for key, label, per in (("fiveHour", "5-hour", 5 * HOUR), ("weekly", "Weekly", WEEK), ("monthly", "Monthly", 30 * 86400)):
                x = ((L.get(tier) or {}).get(key)) or {}
                if x.get("usedPercent") is not None:
                    wins.append(window(f"{tier}_{key}", f"{tier.title()} · {label}", x["usedPercent"],
                                       resets=x.get("windowEnd"), period=per, primary=(tier, key) == ("standard", "weekly")))
        if lim.get("extraUsageBalanceCents") is not None:
            bals.append(balance("extra", "Extra usage", core.num(lim["extraUsageBalanceCents"]) / 100, "USD"))
        try:
            u = (self.get(acct, "https://api.factory.ai/api/organization/subscription/usage?useCache=true", headers=h).get("usage")) or {}
            s, e = core.iso_ts(u.get("startDate")), core.iso_ts(u.get("endDate"))
            for tier in ("standard", "premium"):
                t = u.get(tier) or {}
                if t.get("totalAllowance"):
                    wins.append(window(f"{tier}_tokens", f"{tier.title()} tokens", (core.num(t.get("usedRatio")) or 0) * 100
                                       if t.get("usedRatio") is not None else None, used=t.get("userTokens"),
                                       limit=t.get("totalAllowance"), unit="tokens", resets=e, period=(e - s) if s and e else None,
                                       primary=not wins and tier == "standard"))
        except core.HttpError:
            pass
        if wins and not any(w["primary"] for w in wins):
            wins[0]["primary"] = True
        return {"windows": wins, "balances": bals}


WARP_Q = """query GetRequestLimitInfo($requestContext: RequestContext!) { user(requestContext: $requestContext) { __typename
 ... on UserOutput { user { requestLimitInfo { isUnlimited nextRefreshTime requestLimit requestsUsedSinceLastRefresh }
 bonusGrants { requestCreditsGranted requestCreditsRemaining expiration }
 workspaces { bonusGrantsInfo { grants { requestCreditsGranted requestCreditsRemaining expiration } } } } } } }"""


class Warp(Provider):
    id = "warp"
    name = "Warp"
    vendor = "Warp"
    color = "#01a4ff"
    mono = "W"
    blurb = "AI requests used in this refresh period, bonus credits"
    auths = [Fields([Field("key", "API key", "secret", "wk-…", help="Warp → Settings → Platform → API keys.")])]

    def fetch(self, acct):
        osc = {"category": "Linux", "name": "Linux", "version": platform.release() or "6.0"}
        d = self.get(acct, "https://app.warp.dev/graphql/v2?op=GetRequestLimitInfo", method="POST",
                     headers={"User-Agent": "Warp/1.0", "x-warp-client-id": "warp-app", "x-warp-os-category": osc["category"],
                              "x-warp-os-name": osc["name"], "x-warp-os-version": osc["version"]},
                     body={"query": WARP_Q, "operationName": "GetRequestLimitInfo",
                           "variables": {"requestContext": {"clientContext": {}, "osContext": osc}}})
        u = (((d.get("data") or {}).get("user") or {}).get("user")) or {}
        if not u:
            raise RuntimeError("Warp: " + str((d.get("errors") or [{}])[0].get("message", "no user in answer")))
        r = u.get("requestLimitInfo") or {}
        wins, bals = [], []
        if not r.get("isUnlimited") and r.get("requestLimit"):
            wins.append(window("requests", "AI requests", used=r.get("requestsUsedSinceLastRefresh"), limit=r.get("requestLimit"),
                               unit="requests", resets=r.get("nextRefreshTime"), period=30 * 86400, primary=True))
        grants = list(u.get("bonusGrants") or [])
        for ws in u.get("workspaces") or []:
            grants += ((ws.get("bonusGrantsInfo") or {}).get("grants")) or []
        rem = sum(core.num(g.get("requestCreditsRemaining")) or 0 for g in grants)
        if grants:
            bals.append(balance("bonus", "Bonus credits", rem, "credits"))
        return {"plan": "Unlimited" if r.get("isUnlimited") else None, "windows": wins, "balances": bals}


class Amp(Provider):
    id = "amp"
    name = "Amp"
    vendor = "Sourcegraph"
    color = "#f34e3f"
    blurb = "Amp Free daily allowance and credit balances"
    auths = [Fields([Field("key", "API key", "secret", help="ampcode.com → Settings → access token (AMP_API_KEY).")])]

    def fetch(self, acct):
        d = self.get(acct, "https://ampcode.com/api/internal?userDisplayBalanceInfo", method="POST",
                     body={"method": "userDisplayBalanceInfo", "params": {}})
        return parse_amp(((d.get("result") or {}).get("displayText")) or "")


def parse_amp(t):
    money = r"\$([\d,]+(?:\.\d+)?)"
    f = lambda s: float(s.replace(",", ""))
    wins, bals = [], []
    m = re.search(r"Amp Free:\s*" + money + r"\s*/\s*" + money + r"\s*remaining", t)
    if m:
        rem, tot = f(m.group(1)), f(m.group(2))
        wins.append(window("free", "Amp Free", used=tot - rem, limit=tot, unit="USD", primary=True,
                           note=(re.search(r"replenishes[^)]*", t) or [None])[0]))
    m = re.search(r"Individual credits:\s*" + money, t)
    if m:
        bals.append(balance("credits", "Credits", f(m.group(1)), "USD"))
    for m in re.finditer(r"Workspace ([^:]+):\s*" + money, t):
        bals.append(balance("ws_" + m.group(1).strip().lower()[:20], "Workspace " + m.group(1).strip(), f(m.group(2)), "USD"))
    if not wins and not bals:
        raise RuntimeError("Amp answered with text Burnrate cannot read: " + t[:120])
    return {"windows": wins, "balances": bals}


class Synthetic(Provider):
    id = "synthetic"
    name = "Synthetic"
    vendor = "Synthetic"
    color = "#6d28d9"
    mono = "S"
    official = True
    blurb = "Weekly plan limit and rolling 5-hour limit"
    auths = [Fields([Field("key", "API key", "secret")])]

    def fetch(self, acct):
        d = self.get(acct, "https://api.synthetic.new/v2/quotas")
        wins = []
        for key, label, per in (("planWeeklyLimit", "Weekly", WEEK), ("weeklyTokenLimit", "Weekly", WEEK),
                                ("rollingFiveHourLimit", "5-hour", 5 * HOUR), ("subscription", "Plan", None)):
            x = d.get(key)
            if not isinstance(x, dict) or any(w["label"] == label for w in wins):
                continue
            pct = x.get("percentUsed") if x.get("percentUsed") is not None else x.get("usedPercent")
            used, lim = x.get("used") if x.get("used") is not None else x.get("requests"), x.get("limit")
            if pct is None and used is None:
                continue
            wins.append(window(key, label, pct, used=used, limit=lim, resets=x.get("renewsAt") or x.get("nextRegenAt") or x.get("resetsAt"),
                               period=per, primary=label == "Weekly"))
        if wins and not any(w["primary"] for w in wins):
            wins[0]["primary"] = True
        return {"windows": wins}


class Ollama(Provider):
    id = "ollama"
    name = "Ollama Cloud"
    vendor = "Ollama"
    color = "#3a3a3a"
    mono = "O"
    blurb = "Included cloud usage (session/weekly or monthly allowance), purchased credit"
    auths = [Fields([Field("key", "API key", "secret", help="ollama.com → Settings → Keys.")])]

    def fetch(self, acct):
        d = self.get(acct, "https://ollama.com/api/balance")
        inc, wins, bals = d.get("included") or {}, [], []
        for key, label, per in (("session", "Session", 5 * HOUR), ("weekly", "Weekly", WEEK)):
            x = inc.get(key)
            if isinstance(x, dict) and x.get("remaining_percent") is not None:
                wins.append(window(key, label, 100 - core.num(x["remaining_percent"]), resets=x.get("resets_at"),
                                   period=per, primary=key == "weekly"))
        if inc.get("allowance_usd") is not None:
            a, b = core.num(inc.get("allowance_usd")), core.num(inc.get("balance_usd"))
            wins.append(window("monthly", "Monthly allowance", used=(a - b) if a is not None and b is not None else None,
                               limit=a, unit="USD", resets=(inc.get("period") or {}).get("until"), period=30 * 86400,
                               primary=not wins))
        p = d.get("purchased") or {}
        if p.get("balance_usd") is not None:
            bals.append(balance("purchased", "Purchased credit", p["balance_usd"], "USD"))
        return {"plan": d.get("plan"), "windows": wins, "balances": bals}
