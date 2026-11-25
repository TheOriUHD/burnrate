"""Provider framework.

A provider turns stored credentials into a normalized *snapshot*:

    {"plan": "Pro",                                   # optional
     "windows": [window(...), ...],                   # rate-limit windows / quotas
     "balances": [balance(...), ...],                 # money or credit balances
     "breakdown": {"window": "week", "rows": [{"key", "name", "pct"}]},   # optional split of one window
     "info": [{"label", "value"}]}                    # optional extra facts shown as text

Each provider offers one or more auth methods (API key fields, OAuth with a pasted code, device flow).
Add a provider: create a module in this package with a `Provider` subclass and list it in __init__.py.
"""
import json, secrets, time, urllib.parse
from .. import core


# ---------------------------------------------------------------- snapshot builders
def window(id, label, pct=None, used=None, limit=None, unit=None, resets=None, period=None, primary=False, note=None):
    """A quota window. Give pct (0-100) or used+limit (pct is then derived). resets = epoch s, period = seconds."""
    pct, used, limit = core.num(pct), core.num(used), core.num(limit)
    if pct is None and used is not None and limit:
        pct = 100.0 * used / limit
    return {"id": id, "label": label, "pct": None if pct is None else round(pct, 3), "used": used, "limit": limit,
            "unit": unit, "resets": core.iso_ts(resets), "period": period, "primary": primary, "note": note}


def balance(id, label, amount, currency="USD", limit=None, kind="remaining", note=None):
    """kind: remaining (credit left, goes down when used) | spent (spend so far, goes up)."""
    return {"id": id, "label": label, "amount": core.num(amount), "currency": currency, "limit": core.num(limit),
            "kind": kind, "note": note}


DAY, WEEK, HOUR = 86400, 7 * 86400, 3600


def month_bounds(ts=None, tz=None):
    """(start, next start) of the calendar month in UTC (providers bill per UTC month)."""
    from datetime import datetime, timezone
    d = datetime.fromtimestamp(ts or time.time(), tz or timezone.utc)
    s = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    n = s.replace(year=s.year + 1, month=1) if s.month == 12 else s.replace(month=s.month + 1)
    return int(s.timestamp()), int(n.timestamp())


# ---------------------------------------------------------------- auth methods
class Field:
    def __init__(self, name, label, kind="text", placeholder="", help="", options=None, required=True, default=None):
        self.name, self.label, self.kind, self.placeholder, self.help = name, label, kind, placeholder, help
        self.options, self.required, self.default = options, required, default

    def describe(self):
        return {"name": self.name, "label": self.label, "kind": self.kind, "placeholder": self.placeholder,
                "help": self.help, "options": self.options, "required": self.required, "default": self.default}


class Auth:
    kind = "?"
    id = "default"
    label = "Sign in"
    help = ""

    def describe(self):
        return {"id": self.id, "kind": self.kind, "label": self.label, "help": self.help}


class Fields(Auth):
    """User pastes an API key / cookie / token. creds = the field values."""
    kind = "fields"

    def __init__(self, fields, id="key", label="API key", help=""):
        self.fields, self.id, self.label, self.help = fields, id, label, help

    def describe(self):
        d = super().describe()
        d["fields"] = [f.describe() for f in self.fields]
        return d

    def build(self, values):
        out = {}
        for f in self.fields:
            v = (values.get(f.name) or "").strip()
            if f.required and not v:
                raise ValueError(f"{f.label} is required")
            if v:
                out[f.name] = v
        out["_auth"] = self.id
        return out


class OAuthPaste(Auth):
    """OAuth 2 authorization code + PKCE where the user pastes the code (or the whole redirect URL) back.

    Subclass or configure: authorize_url, token_url, client_id, redirect_uri, scope, extra (authorize params)."""
    kind = "oauth_paste"
    id = "oauth"
    label = "Sign in"
    token_form = False          # token endpoint wants form encoding instead of JSON
    client_secret = None
    paste_hint = "Paste the code (or the whole address of the page you end up on)."

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def start(self):
        verifier, challenge = core.pkce()
        state = core.b64u(secrets.token_bytes(24))
        q = {"response_type": "code", "client_id": self.client_id, "redirect_uri": self.redirect_uri,
             "scope": self.scope, "code_challenge": challenge, "code_challenge_method": "S256", "state": state}
        q.update(getattr(self, "extra", {}) or {})
        url = self.authorize_url + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
        return {"url": url, "state": state, "verifier": verifier}

    @staticmethod
    def parse_paste(pasted):
        """Accepts 'code', 'code#state', or a full redirect URL with ?code=...&state=..."""
        p = pasted.strip()
        if "code=" in p:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(p).query or p.split("?", 1)[-1])
            return (q.get("code") or [""])[0], (q.get("state") or [None])[0]
        code, _, state = p.partition("#")
        return code, state or None

    def finish(self, pasted, flow):
        code, state = self.parse_paste(pasted)
        if not code:
            raise ValueError("no code found in what you pasted")
        if state and state != flow["state"]:
            raise ValueError("this code belongs to a different sign-in attempt: start again")
        body = {"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri,
                "client_id": self.client_id, "code_verifier": flow["verifier"]}
        if self.client_secret:
            body["client_secret"] = self.client_secret
        body.update(self.token_extra(flow))
        d = core.http("POST", self.token_url, form=body) if self.token_form else core.http("POST", self.token_url, body)
        return self.token_creds(d)

    def token_extra(self, flow):
        return {}

    def token_creds(self, d, old=None):
        old = old or {}
        return {"access_token": d["access_token"], "refresh_token": d.get("refresh_token") or old.get("refresh_token"),
                "id_token": d.get("id_token") or old.get("id_token"),
                "expires_at": core.now() + int(d.get("expires_in") or 3600), "_auth": self.id,
                **{k: v for k, v in old.items() if k.startswith("x_")}}

    def refresh(self, c):
        if not c.get("refresh_token"):
            raise RuntimeError("access expired and there is no refresh token: sign in again in Settings")
        body = {"grant_type": "refresh_token", "refresh_token": c["refresh_token"], "client_id": self.client_id}
        if self.client_secret:
            body["client_secret"] = self.client_secret
        if getattr(self, "refresh_scope", None):
            body["scope"] = self.refresh_scope
        d = core.http("POST", self.token_url, form=body) if self.token_form else core.http("POST", self.token_url, body)
        return self.token_creds(d, c)


class DeviceFlow(Auth):
    """OAuth device authorization (RFC 8628): the user enters a short code on the provider's site."""
    kind = "device"
    id = "device"
    label = "Sign in"
    token_form = True

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def start(self):
        d = core.http("POST", self.device_url, form={"client_id": self.client_id, "scope": self.scope})
        return {"device_code": d["device_code"], "user_code": d["user_code"],
                "url": d.get("verification_uri_complete") or d.get("verification_uri"),
                "interval": int(d.get("interval") or 5), "expires": core.now() + int(d.get("expires_in") or 900),
                "next": 0}

    def poll(self, flow):
        """None while pending, creds when done; raises on denial/expiry."""
        if core.now() < flow.get("next", 0):
            return None
        flow["next"] = core.now() + flow["interval"]
        d = core.http("POST", self.token_url, form={"client_id": self.client_id, "device_code": flow["device_code"],
                                                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        err = d.get("error")
        if err == "authorization_pending":
            return None
        if err == "slow_down":
            flow["interval"] += 5
            return None
        if err:
            raise RuntimeError(d.get("error_description") or err)
        return self.token_creds(d)

    def token_creds(self, d):
        return {"access_token": d["access_token"], "refresh_token": d.get("refresh_token"),
                "expires_at": core.now() + int(d["expires_in"]) if d.get("expires_in") else None, "_auth": self.id}


# ---------------------------------------------------------------- provider
class Account:
    """What a provider's fetch() gets: the account row, its credentials and a way to save refreshed ones."""

    def __init__(self, row, creds):
        self.id = row["id"]
        self.label = row["label"]
        self.options = json.loads(row["options"] or "{}") if not isinstance(row["options"], dict) else row["options"]
        self.creds = creds or {}

    def save(self, new):
        self.creds = new
        core.save_creds(self.id, new)


class Provider:
    id = "?"
    name = "?"
    vendor = ""
    color = "#888888"            # monogram colour in the UI
    mono = None                  # 1-2 letters for the monogram (default: first letter of name)
    category = "subscription"    # subscription | api | credits
    official = False             # documented public API (True) or the provider's own internal endpoint (False)
    blurb = ""                   # one line: what you see
    help = ""                    # shown in the add-account dialog
    options = []                 # non-secret Field list (region, team id, ...)
    auths = []                   # list of Auth

    def fetch(self, acct):
        raise NotImplementedError

    # helpers -----------------------------------------------------
    def auth_for(self, acct):
        a = acct.creds.get("_auth")
        for x in self.auths:
            if x.id == a:
                return x
        return self.auths[0]

    def bearer(self, acct):
        """Access token, refreshed first when it expires within 5 minutes (OAuth auths)."""
        c = acct.creds
        au = self.auth_for(acct)
        exp = c.get("expires_at")
        if exp and exp - time.time() < 300 and c.get("refresh_token") and hasattr(au, "refresh"):
            acct.save(au.refresh(c))
        tok = acct.creds.get("access_token") or acct.creds.get("key") or acct.creds.get("token")
        if not tok:
            raise RuntimeError("no credentials stored for this account: reconnect it in Settings")
        return tok

    def get(self, acct, url, headers=None, auth_header=None, retry=True, **kw):
        """GET with the account's bearer; on 401 refresh once (OAuth) and retry."""
        tok = self.bearer(acct)
        h = {"Authorization": "Bearer " + tok} if auth_header is None else auth_header(tok)
        h.update(headers or {})
        try:
            return core.http(kw.pop("method", "GET"), url, headers=h, **kw)
        except core.HttpError as e:
            au = self.auth_for(acct)
            if e.code == 401 and retry and acct.creds.get("refresh_token") and hasattr(au, "refresh"):
                acct.save(au.refresh(acct.creds))
                return self.get(acct, url, headers, auth_header, retry=False, **kw)
            if e.code in (401, 403):
                raise RuntimeError(f"not authorized ({e.code}): the key/login may be wrong, expired or lack access. "
                                   f"{core.redact(e.body)[:160]}") from None
            raise

    def describe(self):
        return {"id": self.id, "name": self.name, "vendor": self.vendor, "color": self.color,
                "mono": self.mono or self.name[:1], "category": self.category, "official": self.official,
                "blurb": self.blurb, "help": self.help, "options": [f.describe() for f in self.options],
                "auths": [a.describe() for a in self.auths]}
