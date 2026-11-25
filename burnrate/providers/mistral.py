"""Mistral Vibe (Le Chat and Vibe Code are one plan since 2026) and the Mistral API.

Primary: just an API key (a Vibe key from chat.mistral.ai/code/extensions, or a console API key). With it, Burnrate reads
the same documented billing endpoints the Vibe CLI uses: /v1/billing/subscription (plan) and /v1/billing/budget (the
monthly Vibe budget and the included-API budget), plus the console's /api/vibe/whoami (key scope, plan fallback).
Optional extras: an Admin API key (month spend and spend limit) and the console cookie (prepaid credits)."""
import json, re, time
from datetime import datetime, timezone
from .. import core
from .base import Provider, Fields, Field, window, balance, month_bounds

ADMIN = "https://admin.mistral.ai"
API = "https://api.mistral.ai/v1"
CONSOLE = "https://console.mistral.ai"
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


PLANS = {"EDU": "Education", "PRO": "Pro", "INDIVIDUAL": "Pro", "TEAM": "Team", "FREE": "Free", "ENTERPRISE": "Enterprise", "STUDENT": "Education"}


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


def budget_windows(b):
    """Windows from a budget object {"vibe_budget": {...}, "api_budget": {...}} (billing API or console page)."""
    wins = []
    for key, label in (("vibe_budget", "Vibe"), ("api_budget", "Included API")):
        x = (b or {}).get(key)
        if not isinstance(x, dict) or x.get("usage_percentage") is None:
            continue
        lim = core.num(x.get("initial_budget"))
        if lim is not None and lim <= 0:
            continue                       # no allowance of this kind on the plan
        pct = max(0.0, core.num(x["usage_percentage"]) or 0)
        wins.append(window(key, label, pct, used=lim * pct / 100 if lim else None, limit=lim,
                           unit=(x.get("currency") or "").upper() or None, resets=x.get("reset_at"),
                           period=30 * 86400, primary=key == "vibe_budget",
                           note="pay-as-you-go after the budget" if x.get("payg_enabled") else None))
    if wins and not any(w["primary"] for w in wins):
        wins[0]["primary"] = True
    return wins


def _quiet(fn, *a, **kw):
    """(result, http status or None): billing reads are optional, a 403/404 only means 'not for this key'."""
    try:
        return fn(*a, **kw), None
    except core.HttpError as e:
        return None, e.code
    except RuntimeError as e:          # Provider.get turns 401/403 into RuntimeError
        m = re.search(r"\((\d{3})\)", str(e))
        return None, int(m.group(1)) if m else 0


class Mistral(Provider):
    id = "mistral"
    name = "Mistral"
    vendor = "Mistral AI"
    color = "#fa520f"
    official = True
    blurb = "Vibe plan budget (chat + code) and the included-API budget with reset; spend limit and credits optional"
    help = ("Paste an API key: a Vibe key (chat.mistral.ai → Code → Extensions / Vibe CLI → API key) or a console API key. "
            "Le Chat is now Vibe: chat and Vibe Code share one monthly budget. The key needs the "
            "\"see organization usage\" permission (plan keys and owner keys have it).")
    auths = [Fields([Field("key", "API key", "secret", "Vibe or console API key",
                           help="Vibe key: chat.mistral.ai/code/extensions?focus=key. Console key: console.mistral.ai/api-keys."),
                     Field("admin_key", "Admin API key (optional)", "secret",
                           help="Adds this month's spend and the spend limit (Admin panel → Admin API keys).", required=False),
                     Field("cookie", "Console cookie (optional)", "textarea", "ory_session_…=…; csrftoken=…",
                           help="Adds prepaid credits: DevTools on admin.mistral.ai → Network → copy the Cookie header.",
                           required=False)],
                    id="key", label="API key"),
             Fields([Field("cookie", "Cookie header", "textarea", "ory_session_…=…; csrftoken=…",
                           help="DevTools on admin.mistral.ai → Network → any request → copy the Cookie header.")],
                    id="cookie", label="Console cookie"),
             Fields([Field("key", "Admin API key", "secret", help="Spend and spend limit only (Admin API).")],
                    id="admin", label="Admin API key only")]

    def fetch(self, acct):
        a = acct.creds.get("_auth")
        if a == "admin":
            return self.admin(acct, acct.creds.get("key"))
        if a == "cookie":
            return self.console(acct.creds["cookie"])
        return self.with_key(acct)

    # ---------------------------------------------------------------- API key (primary)
    def with_key(self, acct):
        key = self.bearer(acct)
        hdr = {"Authorization": "Bearer " + key, "Accept": "application/json"}
        sub, sub_err = _quiet(core.http, "GET", API + "/billing/subscription", headers=hdr)
        bud, bud_err = _quiet(core.http, "GET", API + "/billing/budget", headers=hdr)
        who, _ = _quiet(core.http, "GET", CONSOLE + "/api/vibe/whoami", headers=hdr)
        if sub is None and bud is None and who is None:
            if 401 in (sub_err, bud_err):
                raise RuntimeError("Mistral rejected the API key (401): check it or create a new one")
            raise RuntimeError(f"Mistral billing API unreachable (HTTP {sub_err or bud_err})")
        out = {"windows": budget_windows(bud), "balances": [], "info": []}
        info = out["info"]
        sub = sub if isinstance(sub, dict) else {}
        who = who if isinstance(who, dict) else {}
        out["plan"] = plan_label((sub.get("plan_name") or "").upper() or None) or self._who_plan(who)
        if sub.get("enterprise"):
            out["plan"] = (out["plan"] + " · Enterprise") if out["plan"] else "Enterprise"
        scope = {"chat": "Vibe plan key", "api": "API (workspace) key", "mistral_code": "Codestral key"}.get(
            (who.get("plan_type") or "").lower())
        if scope:
            info.append({"label": "Key", "value": scope})
        if who.get("organization_kind"):
            info.append({"label": "Organization", "value": str(who["organization_kind"]).replace("_", " ")})
        for k, label in (("vibe_payg_enabled", "Vibe pay-as-you-go"), ("payg_enabled", "API pay-as-you-go")):
            if sub.get(k) is not None:
                info.append({"label": label, "value": "on" if sub[k] else "off"})
        if bud is None and bud_err == 403:
            info.append({"label": "Budget", "value": "this key can't read organization usage (needs see_org_inference_usage)"})
        adm = acct.creds.get("admin_key")
        if adm:
            try:
                x = self.admin(acct, adm)
                out["windows"] += [w for w in x["windows"] if w["id"] not in {y["id"] for y in out["windows"]}]
                out["balances"] += x["balances"]
            except Exception as e:
                info.append({"label": "Admin API", "value": str(e)[:120]})
        if acct.creds.get("cookie"):
            try:
                out["balances"] += self.credits(cookies(acct.creds["cookie"]))
            except Exception:
                info.append({"label": "Credits", "value": "console cookie expired: paste a fresh one"})
        if not out["windows"] and not out["balances"]:
            info.append({"label": "Budget", "value": "no monthly budget on this plan/key"})
        return out

    @staticmethod
    def _who_plan(who):
        name = (who.get("plan_name") or "").upper()
        kind = (who.get("plan_type") or "").lower()
        if kind == "chat":
            return plan_label(name) if name else None
        if kind == "api" and name:
            return "Free API" if "FREE" in name else "API (pay as you go)"
        if kind == "mistral_code":
            return {"F": "Codestral (free)", "E": "Code Enterprise"}.get(name)
        return None

    # ---------------------------------------------------------------- console cookie (fallback)
    @staticmethod
    def _hdr(ck):
        hdr = {"Cookie": "; ".join(f"{k}={v}" for k, v in ck.items()), "Origin": ADMIN,
               "Referer": ADMIN + "/organization/usage", "Accept": "text/html,application/json"}
        if ck.get("csrftoken"):
            hdr["X-CSRFTOKEN"] = ck["csrftoken"]
        return hdr

    def credits(self, ck):
        c = core.http("GET", ADMIN + "/api/billing/credits", headers=self._hdr(ck))
        avail = (core.num(c.get("wallet_amount")) or 0) + (core.num(c.get("credit_notes_amount")) or 0) - \
                (core.num(c.get("ongoing_usage_balance")) or 0)
        return [balance("credits", "Credits", avail, (c.get("currency") or "EUR").upper())]

    def console(self, raw):
        ck = cookies(raw)
        hdr = self._hdr(ck)
        try:
            html = core.http("GET", ADMIN + "/subscription", headers=hdr, raw=True).decode(errors="replace")
        except core.HttpError as e:
            raise RuntimeError(f"Mistral console refused the cookie ({e.code}): reconnect in Settings") from None
        if "self-service/login" in html[:3000] or "auth.mistral.ai" in html[:2000]:
            raise RuntimeError("Mistral session expired: paste a fresh cookie in Settings, or switch to an API key")
        wins = budget_windows(flight_budget(html))
        if not any(w["id"] == "vibe_budget" for w in wins) and ck.get("csrftoken"):
            try:
                v = core.http("GET", VIBE, headers={"Cookie": f"csrftoken={ck['csrftoken']}; " + "; ".join(
                    f"{k}={v}" for k, v in ck.items() if k.startswith("ory_session")), "X-CSRFToken": ck["csrftoken"]})
                j = ((v[0].get("result") or {}).get("data") or {}).get("json") or {}
                if j.get("usage_percentage") is not None:
                    wins += budget_windows({"vibe_budget": j})
            except Exception:
                pass
        bals = []
        try:
            bals = self.credits(ck)
        except Exception:
            pass
        if wins and not any(w["primary"] for w in wins):
            wins[0]["primary"] = True
        plans = flight_plans(html)
        info = [{"label": f"{label} plan", "value": plan_label(plans[k])}
                for k, label in (("chat", "Vibe"), ("code", "Code"), ("api", "API")) if plans.get(k)]
        return {"plan": plan_label(plans.get("chat") or plans.get("code")), "windows": wins, "balances": bals, "info": info}

    # ---------------------------------------------------------------- Admin API
    def admin(self, acct, key):
        if not key:
            raise RuntimeError("no Admin API key stored: reconnect in Settings")
        try:
            d = core.http("GET", API + "/admin/spend-limit", headers={"Authorization": "Bearer " + key})
        except core.HttpError as e:
            raise RuntimeError(f"Admin API refused the key ({e.code}): it must be an Admin API key") from None
        lim = d.get("limits") or d
        c = lim.get("completion") or {}
        cur = (lim.get("currency") or d.get("currency") or "EUR").upper()
        s, e = month_bounds()
        wins, bals = [], []
        if not c.get("no_monthly_limit") and c.get("usage_limit"):
            wins.append(window("spend", "Monthly spend limit", used=c.get("usage"), limit=c.get("usage_limit"), unit=cur,
                               resets=e, period=e - s, primary=True,
                               note="limit reached" if c.get("monthly_limit_reached") else None))
        bals.append(balance("spend", "Spend this month", c.get("total_usage", c.get("usage")), cur, kind="spent",
                            limit=c.get("usage_limit") if not c.get("no_monthly_limit") else None))
        return {"plan": "Enterprise", "windows": wins, "balances": bals}
