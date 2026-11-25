"""API accounts with a balance or a spend you can read with a normal or admin key (mostly official APIs)."""
import time
from datetime import datetime, timezone
from .. import core
from .base import Provider, Fields, Field, window, balance, month_bounds


def key(label="API key", ph="", help=""):
    return [Fields([Field("key", label, "secret", ph, help=help)])]


class OpenRouter(Provider):
    id = "openrouter"
    name = "OpenRouter"
    vendor = "OpenRouter"
    color = "#6467f2"
    mono = "OR"
    category = "api"
    official = True
    blurb = "Credit balance, key spend limit, spend today/this week/this month"
    auths = key("API key", "sk-or-v1-…", "Any key works; a management key also shows the account credits.")

    def fetch(self, acct):
        k = (self.get(acct, "https://openrouter.ai/api/v1/key").get("data")) or {}
        wins, bals, info = [], [], []
        try:
            c = (self.get(acct, "https://openrouter.ai/api/v1/credits").get("data")) or {}
            bals.append(balance("credits", "Credits", (core.num(c.get("total_credits")) or 0) - (core.num(c.get("total_usage")) or 0), "USD"))
        except Exception:
            pass
        if k.get("limit"):
            reset = {"daily": 86400, "weekly": 7 * 86400, "monthly": 30 * 86400}.get(k.get("limit_reset") or "")
            wins.append(window("key_limit", "Key spend limit", used=(core.num(k["limit"]) - (core.num(k.get("limit_remaining")) or 0)),
                               limit=k["limit"], unit="USD", period=reset, primary=True))
        for f, label in (("usage_daily", "Spent today"), ("usage_weekly", "Spent this week"), ("usage_monthly", "Spent this month")):
            if k.get(f) is not None:
                info.append({"label": label, "value": f"${core.num(k[f]):.2f}"})
        if not bals:
            bals.append(balance("usage", "Key spend (all time)", k.get("usage"), "USD", kind="spent"))
        return {"plan": "Free tier" if k.get("is_free_tier") else None, "windows": wins, "balances": bals, "info": info}


class DeepSeek(Provider):
    id = "deepseek"
    name = "DeepSeek"
    vendor = "DeepSeek"
    color = "#4d6bfe"
    mono = "DS"
    category = "api"
    official = True
    blurb = "Account balance (topped up and granted)"
    auths = key("API key", "sk-…")

    def fetch(self, acct):
        d = self.get(acct, "https://api.deepseek.com/user/balance")
        bals = []
        for b in d.get("balance_infos") or []:
            cur = b.get("currency") or "USD"
            bals.append(balance("total_" + cur.lower(), f"Balance ({cur})", b.get("total_balance"), cur,
                                note=f"granted {b.get('granted_balance')}, topped up {b.get('topped_up_balance')}"))
        return {"balances": bals, "info": [] if d.get("is_available", True) else [{"label": "Status", "value": "balance too low"}]}


class Poe(Provider):
    id = "poe"
    name = "Poe"
    vendor = "Quora"
    color = "#5d5cde"
    category = "credits"
    official = True
    blurb = "Compute points balance"
    auths = key("API key", help="poe.com/api/keys")

    def fetch(self, acct):
        d = self.get(acct, "https://api.poe.com/usage/current_balance")
        return {"balances": [balance("points", "Points", d.get("current_point_balance"), "points")]}


class V0(Provider):
    id = "v0"
    name = "v0"
    vendor = "Vercel"
    color = "#111111"
    category = "credits"
    official = True
    blurb = "v0 credit balance and on-demand balance"
    auths = key("API key", help="v0.dev → Settings → Keys")

    def fetch(self, acct):
        d = self.get(acct, "https://api.v0.dev/v1/user/billing")
        data = d.get("data") or d
        b = data.get("balance") or {}
        wins, bals = [], []
        if b.get("total"):
            wins.append(window("credits", "Credits", used=core.num(b["total"]) - (core.num(b.get("remaining")) or 0),
                               limit=b["total"], unit="USD", period=30 * 86400, primary=True))
        if b.get("remaining") is not None:
            bals.append(balance("remaining", "Credits left", b["remaining"], "USD"))
        od = (data.get("onDemand") or {}).get("balance")
        if od is not None:
            bals.append(balance("ondemand", "On-demand", od, "USD"))
        return {"plan": d.get("billingType") or data.get("billingType"), "windows": wins, "balances": bals}


class VercelGateway(Provider):
    id = "vercel_gateway"
    name = "Vercel AI Gateway"
    vendor = "Vercel"
    color = "#000000"
    mono = "▲"
    category = "credits"
    official = True
    blurb = "AI Gateway credit balance and total used"
    auths = key("AI Gateway key")

    def fetch(self, acct):
        d = self.get(acct, "https://ai-gateway.vercel.sh/v1/credits")
        return {"balances": [balance("balance", "Credits", d.get("balance"), "USD")],
                "info": [{"label": "Used in total", "value": f"${core.num(d.get('total_used')) or 0:.2f}"}]}


class Fireworks(Provider):
    id = "fireworks"
    name = "Fireworks AI"
    vendor = "Fireworks"
    color = "#6720ff"
    mono = "FW"
    category = "api"
    official = True
    blurb = "Spend this month"
    auths = key("API key", "fw_…")

    def fetch(self, acct):
        accs = self.get(acct, "https://api.fireworks.ai/v1/accounts").get("accounts") or []
        if not accs:
            raise RuntimeError("no Fireworks account visible to this key")
        slug = accs[0]["name"].split("/")[-1]
        s, e = month_bounds()
        iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        d = self.get(acct, f"https://api.fireworks.ai/v1/accounts/{slug}/billing/summary?startTime={iso(s)}&endTime={iso(min(e, time.time()))}")
        tot, cur = 0.0, "USD"
        for li in d.get("lineItems") or []:
            c = li.get("totalCost") or {}
            cur = c.get("currencyCode") or cur
            tot += (core.num(c.get("units")) or 0) + (core.num(c.get("nanos")) or 0) / 1e9
        return {"balances": [balance("month", "Spend this month", tot, cur, kind="spent")]}


class XAI(Provider):
    id = "xai"
    name = "xAI API"
    vendor = "xAI"
    color = "#222222"
    mono = "X"
    category = "api"
    official = True
    blurb = "Prepaid credit balance (team billing, management API)"
    options = [Field("team_id", "Team ID", "text", "UUID", help="console.x.ai → Settings → Team")]
    auths = key("Management key", help="console.x.ai → Settings → Management keys (inference keys are refused).")

    def fetch(self, acct):
        tid = acct.options.get("team_id")
        if not tid:
            raise RuntimeError("the team ID is missing (Settings → this account → Reconnect)")
        base = f"https://management-api.x.ai/v1/billing/teams/{tid}"
        b = self.get(acct, base + "/prepaid/balance")
        left = -(core.num((b.get("total") or {}).get("val")) or 0) / 100      # ledger: negative = credit
        try:
            inv = self.get(acct, base + "/postpaid/invoice/preview")
            pending = (core.num(((inv.get("coreInvoice") or {}).get("amountAfterVat"))) or 0) / 100
            left -= pending
        except Exception:
            pass
        return {"balances": [balance("prepaid", "Prepaid credits", left, "USD")]}


class OpenAIAdmin(Provider):
    id = "openai_api"
    name = "OpenAI API"
    vendor = "OpenAI"
    color = "#0d0d0d"
    mono = "OA"
    category = "api"
    official = True
    blurb = "Organization spend this month (Costs API), optional monthly budget"
    options = [Field("budget", "Monthly budget (USD)", "text", "e.g. 100", required=False,
                     help="Optional: shows the spend as a share of this budget with a forecast.")]
    auths = key("Admin key", "sk-admin-…", "platform.openai.com → Settings → Organization → Admin keys.")

    def fetch(self, acct):
        s, e = month_bounds()
        tot, cur, url = 0.0, "USD", f"https://api.openai.com/v1/organization/costs?start_time={s}&bucket_width=1d&limit=31"
        for _ in range(5):
            d = self.get(acct, url)
            for bk in d.get("data") or []:
                for r in bk.get("results") or []:
                    a = r.get("amount") or {}
                    tot += core.num(a.get("value")) or 0
                    cur = (a.get("currency") or cur).upper()
            if not d.get("has_more") or not d.get("next_page"):
                break
            url = f"https://api.openai.com/v1/organization/costs?start_time={s}&bucket_width=1d&limit=31&page={d['next_page']}"
        return month_spend(tot, cur, acct.options.get("budget"), s, e)


class AnthropicAdmin(Provider):
    id = "anthropic_api"
    name = "Anthropic API"
    vendor = "Anthropic"
    color = "#c96442"
    mono = "AN"
    category = "api"
    official = True
    blurb = "Organization spend this month (cost report), optional monthly budget"
    options = [Field("budget", "Monthly budget (USD)", "text", "e.g. 100", required=False)]
    auths = key("Admin key", "sk-ant-admin01-…", "Console → Settings → Admin keys (organizations only).")

    def fetch(self, acct):
        s, e = month_bounds()
        iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tot, page = 0.0, None
        for _ in range(5):
            url = f"https://api.anthropic.com/v1/organizations/cost_report?starting_at={iso(s)}&bucket_width=1d&limit=31" + (f"&page={page}" if page else "")
            d = self.get(acct, url, auth_header=lambda t: {"x-api-key": t, "anthropic-version": "2023-06-01"})
            for bk in d.get("data") or []:
                for r in bk.get("results") or []:
                    tot += (core.num(r.get("amount")) or 0) / 100     # decimal string in cents
            if not d.get("has_more"):
                break
            page = d.get("next_page")
        return month_spend(tot, "USD", acct.options.get("budget"), s, e)


def month_spend(tot, cur, budget, s, e):
    budget = core.num(budget)
    wins = [window("budget", "Monthly budget", used=tot, limit=budget, unit=cur, resets=e, period=e - s, primary=True)] if budget else []
    return {"windows": wins, "balances": [balance("month", "Spend this month", tot, cur, kind="spent", limit=budget)]}
