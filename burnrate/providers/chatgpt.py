"""ChatGPT plans (Free, Go, Plus, Pro, Team/Business, Enterprise, Edu): Codex 5-hour and weekly limits, credits.
Reads the endpoint the Codex CLI's /status uses (unofficial). Sign-in uses the Codex CLI's own OAuth client."""
from .. import core
from .base import Provider, Auth, OAuthPaste, window, balance

ISSUER = "https://auth.openai.com"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"      # Codex CLI's public client
USAGE = "https://chatgpt.com/backend-api/wham/usage"


def account_id(creds):
    for tok in (creds.get("id_token"), creds.get("access_token")):
        c = core.jwt_claims(tok or "")
        a = c.get("https://api.openai.com/auth") or {}
        aid = c.get("chatgpt_account_id") or a.get("chatgpt_account_id")
        if aid:
            return aid
        orgs = c.get("organizations") or a.get("organizations") or []
        if orgs and isinstance(orgs[0], dict) and orgs[0].get("id"):
            return orgs[0]["id"]
    return None


class CodexPaste(OAuthPaste):
    id = "oauth"
    label = "Sign in (paste address)"
    help = ("Fallback if device sign-in is not enabled for your account. After you log in, the browser tries to open "
            "http://127.0.0.1:1455/… and shows an error page: copy that whole address and paste it here.")
    authorize_url = ISSUER + "/oauth/authorize"
    token_url = ISSUER + "/oauth/token"
    redirect_uri = "http://127.0.0.1:1455/auth/callback"
    client_id = CLIENT_ID
    scope = "openid profile email offline_access"
    token_form = True
    extra = {"id_token_add_organizations": "true", "codex_cli_simplified_flow": "true", "originator": "codex_cli_rs"}
    paste_hint = "Paste the full address of the error page (it starts with http://127.0.0.1:1455/auth/callback?code=…)."


class CodexDevice(Auth):
    """OpenAI's own device-code login (not RFC 8628): poll until approved, then a normal code exchange."""
    kind = "device"
    id = "device"
    label = "Sign in with a code"
    help = "Uses the Codex CLI's sign-in: you enter a short code on auth.openai.com. No password ever reaches this app."

    def start(self):
        d = core.http("POST", ISSUER + "/api/accounts/deviceauth/usercode", {"client_id": CLIENT_ID})
        return {"device_auth_id": d["device_auth_id"], "user_code": d.get("user_code") or d.get("usercode"),
                "url": ISSUER + "/codex/device", "interval": int(str(d.get("interval") or 5).strip() or 5),
                "expires": core.now() + 900, "next": 0}

    def poll(self, flow):
        if core.now() < flow.get("next", 0):
            return None
        flow["next"] = core.now() + flow["interval"]
        try:
            d = core.http("POST", ISSUER + "/api/accounts/deviceauth/token",
                          {"device_auth_id": flow["device_auth_id"], "user_code": flow["user_code"]})
        except core.HttpError as e:
            if e.code in (403, 404):
                return None
            raise
        t = core.http("POST", ISSUER + "/oauth/token", form={
            "grant_type": "authorization_code", "client_id": CLIENT_ID, "code": d["authorization_code"],
            "redirect_uri": ISSUER + "/deviceauth/callback", "code_verifier": d["code_verifier"]})
        return CodexPaste().token_creds(t) | {"_auth": self.id}

    def refresh(self, c):
        return CodexPaste().refresh(c) | {"_auth": self.id}


class ChatGPT(Provider):
    id = "chatgpt"
    name = "ChatGPT / Codex"
    vendor = "OpenAI"
    color = "#10a37f"
    mono = "AI"
    blurb = "Codex 5-hour and weekly limits of your ChatGPT plan, extra limits, credits"
    help = "Works with every ChatGPT plan that includes Codex. Sign-in is the same one the Codex CLI uses."
    auths = [CodexDevice(), CodexPaste()]

    def fetch(self, acct):
        tok = self.bearer(acct)
        aid = account_id(acct.creds)
        h = {"Accept": "application/json", "originator": "codex_cli_rs"}
        if aid:
            h["ChatGPT-Account-Id"] = aid
        return parse(self.get(acct, USAGE, headers=h))


def _win(rl, key, label, primary=False):
    w = (rl or {}).get(key)
    if not isinstance(w, dict) or w.get("used_percent") is None:
        return None
    return window(key.replace("_window", ""), label, w["used_percent"], resets=w.get("reset_at"),
                  period=w.get("limit_window_seconds"), primary=primary)


def _label(sec, fallback):
    if not sec:
        return fallback
    return "5-hour" if sec == 18000 else "Weekly" if sec == 604800 else "Daily" if sec == 86400 else f"{round(sec / 3600)}-hour"


def parse(d):
    rl = d.get("rate_limit") or {}
    wins = []
    p, s = rl.get("primary_window") or {}, rl.get("secondary_window") or {}
    long_is_secondary = (s.get("limit_window_seconds") or 0) >= (p.get("limit_window_seconds") or 0)
    for key, w in (("primary_window", p), ("secondary_window", s)):
        x = _win(rl, key, _label(w.get("limit_window_seconds"), "Limit"),
                 primary=(key == "secondary_window") == long_is_secondary and bool(w))
        if x:
            wins.append(x)
    if wins and not any(w["primary"] for w in wins):
        wins[-1]["primary"] = True
    for extra in d.get("additional_rate_limits") or []:
        r = extra.get("rate_limit") or {}
        name = extra.get("limit_name") or extra.get("metered_feature") or "extra"
        for key in ("primary_window", "secondary_window"):
            w = r.get(key)
            if isinstance(w, dict) and w.get("used_percent") is not None:
                wins.append(window(f"x_{name}_{key}"[:60], f"{name} · {_label(w.get('limit_window_seconds'), '')}".strip(" ·"),
                                   w["used_percent"], resets=w.get("reset_at"), period=w.get("limit_window_seconds")))
    crl = d.get("code_review_rate_limit") or {}
    for key in ("primary_window", "secondary_window"):
        w = crl.get(key)
        if isinstance(w, dict) and w.get("used_percent") is not None:
            wins.append(window(f"code_review_{key}", f"Code review · {_label(w.get('limit_window_seconds'), '')}".strip(" ·"),
                               w["used_percent"], resets=w.get("reset_at"), period=w.get("limit_window_seconds")))
    bals = []
    cr = d.get("credits") or {}
    if cr.get("has_credits") and not cr.get("unlimited") and cr.get("balance") is not None:
        bals.append(balance("credits", "Codex credits", cr.get("balance"), "credits"))
    sc = ((d.get("spend_control") or {}).get("individual_limit")) or {}
    if sc.get("limit") is not None:
        wins.append(window("spend", "Spend limit", 100 - (core.num(sc.get("remaining_percent")) or 0)
                           if sc.get("remaining_percent") is not None else None, used=sc.get("used"),
                           limit=sc.get("limit"), resets=sc.get("resets_at")))
    plan = d.get("plan_type")
    info = []
    rc = d.get("rate_limit_reset_credits") or {}
    if rc.get("available_count") is not None:
        info.append({"label": "Limit reset credits", "value": f"{rc['available_count']} available"})
    return {"plan": PLANS.get(plan, plan.replace("_", " ").title()) if plan else None, "windows": wins, "balances": bals,
            "info": info}


PLANS = {"prolite": "Pro Lite", "free_workspace": "Free workspace", "k12": "K-12", "edu": "Edu"}
