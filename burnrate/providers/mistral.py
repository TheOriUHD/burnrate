"""Mistral: Le Chat Pro/Team plan budgets (included API + Vibe, from the admin console, unofficial) and credits;
or the official Admin API spend limit (Enterprise plans only)."""
import json, re, time
from datetime import datetime, timezone
from .. import core
from .base import Provider, Fields, Field, window, balance, month_bounds

ADMIN = "https://admin.mistral.ai"
VIBE = ("https://console.mistral.ai/api-ui/trpc/billing.vibeUsage?batch=1&input=%7B%220%22%3A%7B%22json%22%3Anull%2C"
        "%22meta%22%3A%7B%22values%22%3A%5B%22undefined%22%5D%2C%22v%22%3A1%7D%7D%7D")


def cookies(raw):
    raw = raw.strip()
    if raw.lower().startswith("cookie:"):
        raw = raw[7:].strip()
    parts = dict(p.strip().split("=", 1) for p in raw.split(";") if "=" in p)
    if not any(k.startswith("ory_session") for k in parts):
        raise ValueError("the cookie must contain an ory_session_… entry (copy the whole Cookie header)")
    return parts


PLANS = {"EDU": "Education", "PRO": "Pro", "TEAM": "Team", "FREE": "Free", "ENTERPRISE": "Enterprise", "STUDENT": "Education"}


def flight_texts(html):
    texts = [html]
    for m in re.finditer(r'self\.__next_f\.push\((\[1,\s*"(?:[^"\\]|\\.)*"\])\)', html, re.S):
        try:
            texts.append(json.loads(m.group(1))[1])
        except Exception:
            pass
    return texts


def flight_plans(html):
    """Le Chat / code / API plan codes from the page data, e.g. chatPlan "EDU", activeCodePlan null, active_api_plan "FREE"."""
    out = {}
    for t in flight_texts(html):
        for key, name in (("chatPlan", "chat"), ("active_chat_plan", "chat"), ("activeCodePlan", "code"),
                          ("active_code_plan", "code"), ("active_api_plan", "api"), ("apiPlan", "api")):
            m = re.search(r'"%s"\s*:\s*"([A-Za-z_]+)"' % key, t)
            if m and name not in out:
                out[name] = m.group(1).upper()
    return out


def plan_label(code):
    return PLANS.get(code, code.replace("_", " ").title()) if code else None


def flight_budget(html):
    """Find {"budget": {"api_budget": …, "vibe_budget": …}} in the Next.js flight data of /subscription."""
    dec = json.JSONDecoder()
    for t in flight_texts(html):
        for m in re.finditer(r'"budget"\s*:\s*\{', t):
            try:
                obj, _ = dec.raw_decode(t, m.end() - 1)
            except ValueError:
                continue
            if isinstance(obj, dict) and (obj.get("api_budget") or obj.get("vibe_budget")):
                return obj
    return None


class Mistral(Provider):
    id = "mistral"
    name = "Mistral"
    vendor = "Mistral AI"
    color = "#fa520f"
    blurb = "Plan budgets (included API, Vibe) with reset, credits; or the Enterprise Admin API spend limit"
    help = ("Le Chat has no readable message limit. With a Pro/Team plan you get the monthly included-API and Vibe "
            "budgets from the admin console.")
    auths = [Fields([Field("cookie", "Cookie header", "textarea", "ory_session_…=…; csrftoken=…",
                           help="DevTools on admin.mistral.ai → Network → any request → copy the Cookie header.")],
                    id="cookie", label="Console cookie"),
             Fields([Field("key", "Admin API key", "secret", help="Enterprise plans only (Admin API).")],
                    id="admin", label="Admin API key")]

    def fetch(self, acct):
        if acct.creds.get("_auth") == "admin":
            return self.admin(acct)
        ck = cookies(acct.creds["cookie"])
        hdr = {"Cookie": "; ".join(f"{k}={v}" for k, v in ck.items()), "Origin": ADMIN,
               "Referer": ADMIN + "/organization/usage", "Accept": "text/html,application/json"}
        if ck.get("csrftoken"):
            hdr["X-CSRFTOKEN"] = ck["csrftoken"]
        wins, bals = [], []
        try:
            html = core.http("GET", ADMIN + "/subscription", headers=hdr, raw=True).decode(errors="replace")
        except core.HttpError as e:
            raise RuntimeError(f"Mistral console refused the cookie ({e.code}): reconnect in Settings") from None
        if "self-service/login" in html[:3000] or "auth.mistral.ai" in html[:2000]:
            raise RuntimeError("Mistral session expired: paste a fresh cookie in Settings")
        b = flight_budget(html) or {}
        for key, label in (("api_budget", "Included API"), ("vibe_budget", "Vibe")):
            x = b.get(key)
            if isinstance(x, dict) and x.get("usage_percentage") is not None:
                lim = core.num(x.get("initial_budget"))
                pct = core.num(x["usage_percentage"])
                wins.append(window(key, label, pct, used=lim * pct / 100 if lim else None, limit=lim,
                                   unit=(x.get("currency") or "").upper() or None, resets=x.get("reset_at"),
                                   period=30 * 86400, primary=key == "vibe_budget"))
        if not any(w["id"] == "vibe_budget" for w in wins) and ck.get("csrftoken"):
            try:
                v = core.http("GET", VIBE, headers={"Cookie": f"csrftoken={ck['csrftoken']}; " + "; ".join(
                    f"{k}={v}" for k, v in ck.items() if k.startswith("ory_session")), "X-CSRFToken": ck["csrftoken"]})
                j = ((v[0].get("result") or {}).get("data") or {}).get("json") or {}
                if j.get("usage_percentage") is not None:
                    wins.append(window("vibe_budget", "Vibe", j["usage_percentage"], resets=j.get("reset_at"),
                                       period=30 * 86400, primary=True))
            except Exception:
                pass
        try:
            c = core.http("GET", ADMIN + "/api/billing/credits", headers=hdr)
            avail = (core.num(c.get("wallet_amount")) or 0) + (core.num(c.get("credit_notes_amount")) or 0) - \
                    (core.num(c.get("ongoing_usage_balance")) or 0)
            bals.append(balance("credits", "Credits", avail, (c.get("currency") or "EUR").upper()))
        except Exception:
            pass
        if wins and not any(w["primary"] for w in wins):
            wins[0]["primary"] = True
        plans = flight_plans(html)
        info = [{"label": f"{label} plan", "value": plan_label(plans[k])}
                for k, label in (("chat", "Le Chat"), ("code", "Code"), ("api", "API")) if plans.get(k)]
        return {"plan": plan_label(plans.get("chat") or plans.get("code")), "windows": wins, "balances": bals, "info": info}

    def admin(self, acct):
        d = self.get(acct, "https://api.mistral.ai/v1/admin/spend-limit")
        c = (d.get("limits") or {}).get("completion") or {}
        cur = (d.get("currency") or "EUR").upper()
        s, e = month_bounds()
        wins, bals = [], []
        if not c.get("no_monthly_limit") and c.get("usage_limit"):
            wins.append(window("spend", "Monthly spend limit", used=c.get("usage"), limit=c.get("usage_limit"), unit=cur,
                               resets=e, period=e - s, primary=True))
        bals.append(balance("spend", "Spend this month", c.get("usage"), cur, kind="spent",
                            limit=c.get("usage_limit") if not c.get("no_monthly_limit") else None))
        return {"plan": "Enterprise", "windows": wins, "balances": bals}
