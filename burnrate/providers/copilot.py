"""GitHub Copilot (Free, Pro, Pro+, Business): premium requests, chat and completions quotas (internal endpoint)."""
from .. import core
from .base import Provider, DeviceFlow, Fields, Field, window

H = {"Editor-Version": "vscode/1.96.2", "Editor-Plugin-Version": "copilot-chat/0.26.7",
     "User-Agent": "GitHubCopilotChat/0.26.7", "X-Github-Api-Version": "2025-04-01"}


class GitHubDevice(DeviceFlow):
    id = "device"
    label = "Sign in with GitHub"
    help = "You enter a short code on github.com (the same sign-in VS Code uses for Copilot)."
    device_url = "https://github.com/login/device/code"
    token_url = "https://github.com/login/oauth/access_token"
    client_id = "Iv1.b507a08c87ecfe98"
    scope = "read:user"


class Copilot(Provider):
    id = "copilot"
    name = "GitHub Copilot"
    vendor = "GitHub"
    color = "#8957e5"
    mono = "GH"
    blurb = "Premium requests, chat and completions quotas per month"
    auths = [GitHubDevice(),
             Fields([Field("token", "GitHub OAuth token", "secret", "gho_…",
                           help="A token from a Copilot editor sign-in (e.g. ~/.config/github-copilot/apps.json).")],
                    id="token", label="Paste a token")]

    def fetch(self, acct):
        d = self.get(acct, "https://api.github.com/copilot_internal/user", headers=H,
                     auth_header=lambda t: {"Authorization": "token " + t})
        return parse(d)


NAMES = {"premium_interactions": "Premium requests", "chat": "Chat", "completions": "Completions"}


def parse(d):
    reset = d.get("quota_reset_date") or d.get("limited_user_reset_date")
    wins = []
    for key, q in (d.get("quota_snapshots") or {}).items():
        if not isinstance(q, dict) or q.get("unlimited"):
            continue
        ent, rem = core.num(q.get("entitlement")), core.num(q.get("remaining"))
        if not ent and not rem:
            continue
        pct = 100 - core.num(q.get("percent_remaining")) if q.get("percent_remaining") is not None else None
        wins.append(window(key, NAMES.get(key, key.replace("_", " ").title()), pct,
                           used=(ent - rem) if ent is not None and rem is not None else None, limit=ent,
                           unit="requests", resets=reset, period=30 * 86400, primary=key == "premium_interactions"))
    if not wins:   # Free plan: monthly_quotas (limit) + limited_user_quotas (remaining)
        mq, lq = d.get("monthly_quotas") or {}, d.get("limited_user_quotas") or {}
        for key, lim in mq.items():
            lim, rem = core.num(lim), core.num(lq.get(key))
            if lim:
                wins.append(window(key, NAMES.get(key, key.title()), used=lim - (rem or 0), limit=lim, unit="requests",
                                   resets=reset, period=30 * 86400, primary=key == "chat"))
    return {"plan": plan_name(d), "windows": wins}


def plan_name(d):
    """access_type_sku says what the plan really is (copilot_plan is just 'individual' for every personal plan)."""
    sku = (d.get("access_type_sku") or "").lower()
    cp = (d.get("copilot_plan") or "").lower()
    if "educational" in sku or "student" in sku or "teacher" in sku:
        return "Education"
    if cp in ("business", "enterprise"):
        return cp.title()
    if "free_limited" in sku or sku.startswith("free"):
        return "Free"
    if "plus" in sku:
        return "Pro+"
    if "subscriber" in sku or "pro" in sku or "trial" in sku:
        return "Pro" + (" (trial)" if "trial" in sku else "")
    return (cp or sku).replace("_", " ").title() or None
