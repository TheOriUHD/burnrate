"""Gemini Code Assist / Gemini CLI quotas (daily requests per model). Google ended Gemini CLI sign-in for personal
AI Pro/Ultra accounts in June 2026; Workspace, education and Code Assist Standard/Enterprise accounts still work."""
import re
from .. import core
from .base import Provider, OAuthPaste, window, DAY

API = "https://cloudcode-pa.googleapis.com/v1internal:"


SOURCE = "https://raw.githubusercontent.com/google-gemini/gemini-cli/main/packages/core/src/code_assist/oauth2.ts"
_client = {}


def cli_client():
    """The Gemini CLI's installed-app OAuth client. Google publishes it in the Gemini CLI source and documents such
    secrets as not secret, but Burnrate does not ship it: set BURNRATE_GEMINI_CLIENT_ID/_SECRET, or it is read once
    from the official source on first use."""
    if not _client:
        cid, sec = core.env("GEMINI_CLIENT_ID"), core.env("GEMINI_CLIENT_SECRET")
        if not (cid and sec):
            try:
                src = core.http("GET", SOURCE, raw=True, headers={"Accept": "text/plain"}).decode()
            except Exception as e:
                raise RuntimeError(f"could not read the Gemini CLI's sign-in client from GitHub ({e}); set "
                                   "BURNRATE_GEMINI_CLIENT_ID and BURNRATE_GEMINI_CLIENT_SECRET") from None
            m1 = re.search(r"OAUTH_CLIENT_ID\s*=\s*['\"]([^'\"]+)['\"]", src)
            m2 = re.search(r"OAUTH_CLIENT_SECRET\s*=\s*['\"]([^'\"]+)['\"]", src)
            if not (m1 and m2):
                raise RuntimeError("the Gemini CLI source changed; set BURNRATE_GEMINI_CLIENT_ID and _SECRET")
            cid, sec = m1.group(1), m2.group(1)
        _client.update(id=cid, secret=sec)
    return _client


class GoogleCLI(OAuthPaste):
    id = "oauth"
    label = "Sign in with Google"
    help = "Uses the Gemini CLI's own sign-in in its no-browser mode: Google shows you a code to paste here."
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    redirect_uri = "https://codeassist.google.com/authcode"
    scope = ("https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email "
             "https://www.googleapis.com/auth/userinfo.profile")
    token_form = True
    extra = {"access_type": "offline", "prompt": "consent"}
    paste_hint = "Paste the authorization code Google shows you."

    @property
    def client_id(self):
        return cli_client()["id"]

    @property
    def client_secret(self):
        return cli_client()["secret"]


class Gemini(Provider):
    id = "gemini"
    name = "Gemini Code Assist"
    vendor = "Google"
    color = "#4285f4"
    mono = "G"
    blurb = "Daily request quotas per model (Gemini CLI / Code Assist)"
    help = ("For Google Workspace, education and Code Assist Standard/Enterprise accounts. Personal AI Pro/Ultra "
            "accounts are no longer accepted by the Gemini CLI sign-in (Google, June 2026).")
    auths = [GoogleCLI()]

    def fetch(self, acct):
        meta = {"metadata": {"ideType": "GEMINI_CLI", "pluginType": "GEMINI"}}
        la = self.get(acct, API + "loadCodeAssist", method="POST", body=meta)
        proj = la.get("cloudaicompanionProject")
        if isinstance(proj, dict):
            proj = proj.get("id") or proj.get("projectId")
        tier = (la.get("paidTier") or {}).get("name") or (la.get("currentTier") or {}).get("name")
        if not la.get("currentTier") and any((t.get("reasonCode") or "") == "UNSUPPORTED_CLIENT"
                                             for t in la.get("ineligibleTiers") or []):
            raise RuntimeError("Google no longer lets the Gemini CLI sign-in read this (personal) account's quota")
        if not proj:
            ps = self.get(acct, "https://cloudresourcemanager.googleapis.com/v1/projects")
            proj = next((p["projectId"] for p in ps.get("projects") or [] if p.get("projectId", "").startswith("gen-lang-client")), None)
        if not proj:
            raise RuntimeError("no Code Assist project found for this account")
        q = self.get(acct, API + "retrieveUserQuota", method="POST", body={"project": proj})
        out = parse(q)
        out["plan"] = tier
        out["info"] = [{"label": "Project", "value": proj}]
        return out


def parse(q):
    wins = []
    for b in q.get("buckets") or []:
        rf = core.num(b.get("remainingFraction"))
        if rf is None:
            continue
        mid = b.get("modelId") or "model"
        kind = b.get("tokenType") or "REQUESTS"
        wins.append(window(f"{mid}_{kind}".lower(), mid + ("" if kind == "REQUESTS" else f" ({kind.lower()})"),
                           (1 - rf) * 100, resets=b.get("resetTime"), period=DAY))
    if wins:
        pro = [w for w in wins if "pro" in w["label"].lower()] or wins
        max(pro, key=lambda w: w["pct"] or 0)["primary"] = True
    return {"windows": wins}
