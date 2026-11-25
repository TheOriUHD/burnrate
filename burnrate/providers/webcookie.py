"""Consumer plans read with a pasted web session cookie: Perplexity, Augment Code."""
from .. import core
from .base import Provider, Fields, Field, window, balance


def cookie_field(name, help):
    return Fields([Field("cookie", "Session cookie", "secret", name + "=…", help=help)], id="cookie", label="Session cookie")


def norm(raw, name):
    raw = raw.strip()
    if raw.lower().startswith("cookie:"):
        raw = raw[7:].strip()
    return raw if "=" in raw else f"{name}={raw}"


class Perplexity(Provider):
    id = "perplexity"
    name = "Perplexity"
    vendor = "Perplexity AI"
    color = "#20808d"
    mono = "P"
    blurb = "Credit balance, usage this period, renewal date"
    auths = [cookie_field("__Secure-next-auth.session-token", "DevTools on perplexity.ai → Application → Cookies.")]

    def fetch(self, acct):
        try:
            d = core.http("GET", "https://www.perplexity.ai/rest/billing/credits?version=2.18&source=default", headers={
                "Cookie": norm(acct.creds["cookie"], "__Secure-next-auth.session-token"), "Origin": "https://www.perplexity.ai",
                "Referer": "https://www.perplexity.ai/account/usage"})
        except core.HttpError as e:
            raise RuntimeError(f"Perplexity refused the cookie ({e.code}): reconnect in Settings") from None
        c = lambda k: (core.num(d.get(k)) or 0) / 100
        bals = [balance("credits", "Credits", c("balance_cents"), "USD")]
        per = d.get("renewal_date_ts")
        wins = []
        if d.get("current_period_purchased_cents") is not None and d.get("total_usage_cents") is not None and c("current_period_purchased_cents"):
            wins.append(window("period", "This period", used=c("total_usage_cents"), limit=c("current_period_purchased_cents"),
                               unit="USD", resets=per, period=30 * 86400, primary=True))
        return {"windows": wins, "balances": bals}


class Augment(Provider):
    id = "augment"
    name = "Augment Code"
    vendor = "Augment"
    color = "#2f6f4f"
    mono = "A"
    blurb = "Credits used this billing cycle and remaining"
    auths = [cookie_field("_session", "DevTools on app.augmentcode.com → Application → Cookies (_session).")]

    def fetch(self, acct):
        h = {"Cookie": norm(acct.creds["cookie"], "_session")}
        try:
            c = core.http("GET", "https://app.augmentcode.com/api/credits", headers=h)
        except core.HttpError as e:
            raise RuntimeError(f"Augment refused the cookie ({e.code}): reconnect in Settings") from None
        s = {}
        try:
            s = core.http("GET", "https://app.augmentcode.com/api/subscription", headers=h)
        except Exception:
            pass
        used, rem = core.num(c.get("usageUnitsConsumedThisBillingCycle")), core.num(c.get("usageUnitsRemaining"))
        lim = core.num(c.get("usageUnitsAvailable")) or ((used or 0) + (rem or 0)) or None
        wins = [window("cycle", "Credits this cycle", used=used, limit=lim, unit="credits", resets=s.get("billingPeriodEnd"),
                       period=30 * 86400, primary=True)] if lim else []
        return {"plan": s.get("planName"), "windows": wins,
                "balances": [balance("remaining", "Credits left", rem, "credits")] if rem is not None else []}
