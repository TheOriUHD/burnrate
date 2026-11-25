"""LiteLLM proxy (self-hosted): personal and team budgets of the key's owner, key spend.

Follows CodexBar's litellm.js: GET /key/info, then /user/info?user_id= (or /team/info?team_id= for team keys);
falls back to /key/spend/report or /user/spend/report when /key/info is not allowed."""
import time
import urllib.parse
from datetime import datetime, timezone
from .. import core
from .base import Provider, Fields, Field, window, balance, month_bounds


def _base(url):
    b = (url or "").strip().rstrip("/")
    if not b:
        raise RuntimeError("Set the LiteLLM proxy URL in the account options")
    if b.endswith("/v1"):
        b = b[:-3]
    return b


class LiteLLM(Provider):
    id = "litellm"
    name = "LiteLLM"
    vendor = "LiteLLM (self-hosted)"
    color = "#4f46e5"
    mono = "LL"
    category = "api"
    official = True
    blurb = "Personal and team budget of your LiteLLM proxy key, spend so far"
    help = "Works with any LiteLLM proxy you can reach from the Burnrate server (LAN addresses are fine)."
    options = [Field("base_url", "Proxy URL", placeholder="https://litellm.example.lan", help="The proxy's address, with or without /v1.")]
    auths = [Fields([Field("key", "API key", "secret", "sk-…", help="A virtual key (or the master key) of the proxy.")])]

    def _get(self, acct, url, optional=False):
        try:
            return self.get(acct, url)
        except (core.HttpError, RuntimeError) as e:
            code = getattr(e, "code", None) or (401 if "(401)" in str(e) else 403 if "(403)" in str(e) else None)
            if optional and code in (401, 403, 404):
                return None
            raise

    def fetch(self, acct):
        base = _base(acct.options.get("base_url"))
        ki = self._get(acct, base + "/key/info", optional=True)
        if ki is None:
            end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            q = f"?start_date={end[:7]}-01&end_date={end}"
            scope, rows = "Key", self._get(acct, base + "/key/spend/report" + q, optional=True)
            if rows is None:
                scope, rows = "User", self._get(acct, base + "/user/spend/report" + q)
            return parse_spend_report(rows, scope)
        info = ki.get("info") or {}
        uid, tid = (info.get("user_id") or "").strip(), (info.get("team_id") or "").strip()
        if uid:
            u = self._get(acct, base + "/user/info?user_id=" + urllib.parse.quote(uid, safe=""))
            return parse_litellm(info, user=u)
        if tid:
            t = self._get(acct, base + "/team/info?team_id=" + urllib.parse.quote(tid, safe=""))
            return parse_litellm(info, team=t)
        raise RuntimeError("LiteLLM key info has neither a user_id nor a team_id")


def _budget(x, wid, label, primary):
    spend, lim = core.num(x.get("spend")) or 0, max(0.0, core.num(x.get("max_budget")) or 0)
    if lim > 0:
        return window(wid, label, used=spend, limit=lim, unit="USD", resets=x.get("budget_reset_at"), primary=primary), None
    return None, balance(wid, label + " spend", spend, "USD", kind="spent")


def parse_litellm(key, user=None, team=None):
    wins, bals, info, plan = [], [], [], None
    tid = (key.get("team_id") or "").strip()
    if user is not None:
        ui = user.get("user_info") or {}
        w, b = _budget(ui, "personal", "Personal budget", True)
        wins += [w] if w else []
        bals += [b] if b else []
        for t in user.get("teams") or []:
            if tid and t.get("team_id") == tid:
                w, b = _budget(t, "team", "Team " + (t.get("team_alias") or tid), not wins)
                wins += [w] if w else []
                bals += [b] if b and not w else []
        who = (ui.get("user_email") or ui.get("user_alias") or "").strip()
        if who:
            info.append({"label": "User", "value": who})
    elif team is not None:
        ti = team.get("team_info") or {}
        w, b = _budget(ti, "team", "Team " + (ti.get("team_alias") or tid or "budget"), True)
        wins += [w] if w else []
        bals += [b] if b else []
        plan = ti.get("team_alias")
    if core.num(key.get("spend")) is not None:
        bals.append(balance("key", "This key's spend", key["spend"], "USD", kind="spent"))
    if key.get("key_name"):
        info.append({"label": "Key", "value": key["key_name"]})
    exp = core.iso_ts(key.get("expires"))
    if exp:
        info.append({"label": "Key expires", "value": datetime.fromtimestamp(exp, timezone.utc).strftime("%Y-%m-%d")})
    if not wins and not bals:
        raise RuntimeError("LiteLLM returned no budget or spend for this key")
    return {"plan": plan, "windows": wins, "balances": bals, "info": info}


def parse_spend_report(rows, scope):
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("LiteLLM returned an empty spend report")
    used = sum(core.num(r.get("total_cost")) or 0 for r in rows)
    return {"balances": [balance("month", f"{scope} spend this month", used, "USD", kind="spent")]}
