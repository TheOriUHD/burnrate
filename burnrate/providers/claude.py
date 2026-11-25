"""Claude.ai subscriptions (Pro, Max, Team, Enterprise, ...) via the endpoint Claude Code's /usage uses (unofficial)."""
from .. import core
from .base import Provider, OAuthPaste, Fields, Field, window, balance, HOUR, WEEK

USAGE = "https://api.anthropic.com/api/oauth/usage"


class ClaudeOAuth(OAuthPaste):
    id = "oauth"
    label = "Sign in with Claude.ai"
    help = ("Uses Claude Code's own sign-in. You log in on claude.com; afterwards platform.claude.com shows a code "
            "(code#state). Paste all of it here.")
    authorize_url = "https://claude.com/cai/oauth/authorize"
    token_url = "https://platform.claude.com/v1/oauth/token"
    redirect_uri = "https://platform.claude.com/oauth/code/callback"
    client_id = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"     # Claude Code's public OAuth client
    scope = "user:profile"
    refresh_scope = "user:profile"
    extra = {"code": "true"}
    paste_hint = "Paste the code shown on platform.claude.com, including the part after #."

    def token_extra(self, flow):
        return {"state": flow["state"]}


class Claude(Provider):
    id = "claude"
    name = "Claude"
    vendor = "Anthropic"
    color = "#d97757"
    blurb = "5-hour and weekly limits, per-model limits, extra usage, where the week went (Code / Chat / Cowork)"
    auths = [ClaudeOAuth(),
             Fields([Field("access_token", "OAuth access token", "secret", "sk-ant-oat01-…"),
                     Field("refresh_token", "Refresh token", "secret", "sk-ant-ort01-…", required=False)],
                    id="token", label="Paste a token",
                    help="An OAuth token from Claude Code (e.g. ~/.claude/.credentials.json). `claude setup-token` "
                         "tokens may lack the user:profile scope.")]

    def fetch(self, acct):
        d = self.get(acct, USAGE, headers={"anthropic-beta": "oauth-2025-04-20"})
        if not isinstance(d, dict) or "seven_day" not in d:
            raise RuntimeError("unexpected answer from the usage endpoint (format changed?)")
        return parse(d)


def parse(d):
    w = []
    fh = d.get("five_hour")
    if isinstance(fh, dict) and fh.get("utilization") is not None:
        w.append(window("session", "5-hour session", fh["utilization"], resets=fh.get("resets_at"), period=5 * HOUR))
    sd = d.get("seven_day") or {}
    start = core.iso_ts(((d.get("seven_day_breakdown") or {}).get("window_started_at")))
    reset = core.iso_ts(sd.get("resets_at"))
    w.append(window("week", "Weekly", sd.get("utilization"), resets=reset,
                    period=(reset - start) if (reset and start) else WEEK, primary=True))
    seen = set()
    for l in d.get("limits") or []:
        if not isinstance(l, dict) or l.get("kind") == "weekly_all":
            continue
        sc = l.get("scope") or {}
        name = ((sc.get("model") or {}).get("display_name")) or (
            (sc.get("surface") or {}).get("display_name") if isinstance(sc.get("surface"), dict) else sc.get("surface"))
        label = (name + " weekly") if name else (l.get("kind") or "limit").replace("_", " ")
        seen.add(label.lower())
        w.append(window("lim_" + "".join(ch for ch in label.lower() if ch.isalnum()), label, l.get("percent"),
                        resets=l.get("resets_at"), period=WEEK, note=None if l.get("is_active") else "inactive"))
    for key, label in (("seven_day_sonnet", "Sonnet weekly"), ("seven_day_opus", "Opus weekly")):
        v = d.get(key)
        if isinstance(v, dict) and v.get("utilization") is not None and label.lower() not in seen:
            w.append(window(key, label, v["utilization"], resets=v.get("resets_at"), period=WEEK))
    bals = []
    ex = d.get("extra_usage")
    if isinstance(ex, dict) and ex.get("monthly_limit") is not None:
        dp = ex.get("decimal_places") or 0
        f = 10 ** dp
        bals.append(balance("extra", "Extra usage", (ex.get("used_credits") or 0) / f, ex.get("currency") or "USD",
                            limit=(ex.get("monthly_limit") or 0) / f, kind="spent",
                            note=None if ex.get("is_enabled") else ((ex.get("disabled_reason") or "off").replace("_", " "))))
    rows = ((d.get("seven_day_breakdown") or {}).get("rows")) or []
    br = [{"key": r["key"], "name": r.get("display_name") or r["key"], "pct": core.num(r.get("percent_of_limit")) or 0}
          for r in rows if isinstance(r, dict) and r.get("key")]
    return {"windows": w, "balances": bals, "breakdown": {"window": "week", "rows": br} if br else None}
