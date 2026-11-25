"""Consumer plans read with a pasted web session cookie (or session token): T3 Chat, Zed, Abacus AI, Qoder, Trae CN,
Raycast, LongCat, Langdock, Manus, Replicate.

Endpoints and fields follow CodexBar's provider plugins (Sources/CodexBarCore/Resources/Plugins/<id>.js).
These are the providers' own web endpoints, so they can change without notice."""
import json, re, time, urllib.parse
from .. import core
from .base import Provider, Fields, Field, window, balance, HOUR, WEEK, DAY, month_bounds
from .webcookie import cookie_field, norm

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/143.0.0.0 Safari/537.36")
HEADER_HELP = "DevTools → Network → any request to {site} → copy the whole Cookie request header."


def whole_cookie(help_site, name="cookie"):
    return Fields([Field("cookie", "Cookie header", "secret", name + "=…; …", help=HEADER_HELP.format(site=help_site))],
                  id="cookie", label="Session cookie")


def web(who, method, url, cookie=None, headers=None, body=None, raw=False):
    h = {"User-Agent": BROWSER_UA}
    if cookie:
        h["Cookie"] = cookie
    h.update(headers or {})
    try:
        return core.http(method, url, body=body, headers=h, raw=raw)
    except core.HttpError as e:
        if e.code in (401, 403) or 300 <= e.code < 400:
            raise RuntimeError(f"{who} refused the session ({e.code}): paste a fresh cookie in Settings") from None
        if e.code == 429:
            raise RuntimeError(f"{who} is rate limiting usage requests: try again later") from None
        raise


def _cookie(acct, name):
    return norm(acct.creds["cookie"], name)


# ---------------------------------------------------------------- T3 Chat
class T3Chat(Provider):
    id = "t3chat"
    name = "T3 Chat"
    vendor = "T3 Tools"
    color = "#a23b67"
    mono = "T3"
    blurb = "4-hour base usage window and monthly overage"
    help = "T3 Chat sits behind a Vercel bot check: a server request may be challenged even with a valid cookie."
    auths = [whole_cookie("t3.chat")]

    def fetch(self, acct):
        inp = urllib.parse.quote(json.dumps({"0": {"json": {"sessionId": None}, "meta": {"values": {"sessionId": ["undefined"]}}}},
                                            separators=(",", ":")))
        try:
            body = web("T3 Chat", "GET", f"https://t3.chat/api/trpc/getCustomerData?batch=1&input={inp}", acct.creds["cookie"],
                       {"Accept": "*/*", "Referer": "https://t3.chat/settings/customization", "Origin": "https://t3.chat",
                        "trpc-accept": "application/jsonl", "x-trpc-source": "web-client", "x-trpc-batch": "true"}, raw=True)
        except core.HttpError as e:
            if e.code == 429:
                raise RuntimeError("T3 Chat answered with a Vercel security challenge") from None
            raise
        return parse_t3chat(body.decode(errors="replace"))


def _find_t3(v):
    if isinstance(v, dict):
        if "usageFourHourPercentage" in v or "usageMonthPercentage" in v or ("subscription" in v and "usageBand" in v):
            return v
        v = list(v.values())
    if isinstance(v, list):
        for c in v:
            f = _find_t3(c)
            if f:
                return f
    return None


def parse_t3chat(text):
    data = None
    for line in text.splitlines():
        try:
            data = _find_t3(json.loads(line))
        except ValueError:
            continue
        if data:
            break
    if not data:
        raise RuntimeError("T3 Chat answered without customer data (cookie expired?)")
    sub = data.get("subscription") if isinstance(data.get("subscription"), dict) else {}
    mo = data.get("usageMonthPercentage")
    if mo is None:
        mo = data.get("usagePeriodPercentage")
    wins = [window("4h", "Base (4-hour)", max(0.0, min(100.0, core.num(data.get("usageFourHourPercentage")) or 0)),
                   resets=data.get("usageFourHourNextResetAt") or data.get("usageWindowNextResetAt"), period=4 * HOUR,
                   primary=True, note=("band " + data["usageBand"].strip()) if (data.get("usageBand") or "").strip() else None),
            window("month", "Overage (period)", max(0.0, min(100.0, core.num(mo) or 0)), resets=sub.get("currentPeriodEnd") or None,
                   period=(core.iso_ts(sub["currentPeriodEnd"]) - core.iso_ts(sub["currentPeriodStart"]))
                   if sub.get("currentPeriodEnd") and sub.get("currentPeriodStart") else None)]
    raw = (sub.get("productName") or data.get("subTier") or "").strip()
    plan = " ".join(p[:1].upper() + p[1:] for p in raw.split("-") if p) or None
    return {"plan": plan, "windows": wins}


# ---------------------------------------------------------------- Zed
class Zed(Provider):
    id = "zed"
    name = "Zed"
    vendor = "Zed Industries"
    color = "#084ccf"
    mono = "Zd"
    blurb = "Edit predictions used, token spend against your spend limit"
    auths = [whole_cookie("zed.dev (cloud.zed.dev)")]

    def fetch(self, acct):
        return parse_zed(web("Zed", "GET", "https://cloud.zed.dev/frontend/billing/usage", acct.creds["cookie"]))


def parse_zed(root):
    plan, usage = root.get("plan"), root.get("current_usage")
    if not isinstance(plan, str) or not isinstance(usage, dict):
        raise RuntimeError("Zed answered in a format Burnrate does not know")
    wins, bals = [], []
    p = usage.get("edit_predictions") or {}
    lim = p.get("limit")
    if isinstance(lim, dict):
        lim = lim.get("limited")
    if lim not in (None, "unlimited") and core.num(lim):
        wins.append(window("predictions", "Edit predictions", used=min(core.num(p.get("used")) or 0, core.num(lim)), limit=lim,
                           unit="predictions"))
    s = usage.get("token_spend") or {}
    spent = (core.num(s.get("spend_in_cents")) or 0) / 100
    if s.get("limit_in_cents") is not None and core.num(s["limit_in_cents"]):
        wins.insert(0, window("spend", "Token spend", used=spent, limit=core.num(s["limit_in_cents"]) / 100, unit="USD", primary=True))
    else:
        bals.append(balance("spend", "Token spend this period", spent, "USD", kind="spent"))
    if wins and not any(w["primary"] for w in wins):
        wins[0]["primary"] = True
    return {"plan": " ".join(w.title() for w in plan.replace("_", " ").split()), "windows": wins, "balances": bals}


# ---------------------------------------------------------------- Abacus AI
class Abacus(Provider):
    id = "abacus"
    name = "Abacus AI"
    vendor = "Abacus.AI"
    color = "#1a73e8"
    mono = "Ab"
    blurb = "Compute points used this billing month (ChatLLM / DeepAgent)"
    auths = [whole_cookie("apps.abacus.ai")]

    def fetch(self, acct):
        c = acct.creds["cookie"]
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        pts = web("Abacus AI", "GET", "https://apps.abacus.ai/api/_getOrganizationComputePoints", c, h)
        bill = {}
        try:
            bill = web("Abacus AI", "POST", "https://apps.abacus.ai/api/_getBillingInfo", c, h, body={})
        except Exception:
            pass
        return parse_abacus(pts, bill)


def _abacus_result(root):
    if root.get("success") is not True or not isinstance(root.get("result"), dict):
        msg = str(root.get("error") or "unknown error").lower()
        if re.search(r"expired|session|login|authenticate|unauthori[sz]ed|unauthenticated|forbidden", msg):
            raise RuntimeError("Abacus AI session expired: paste a fresh cookie in Settings")
        raise RuntimeError("Abacus AI: " + msg[:100])
    return root["result"]


def parse_abacus(points, billing=None):
    p = _abacus_result(points)
    total, left = core.num(p.get("totalComputePoints")), core.num(p.get("computePointsLeft"))
    if total is None or left is None:
        raise RuntimeError("Abacus AI answered without compute points")
    b = {}
    try:
        b = _abacus_result(billing) if billing else {}
    except RuntimeError:
        pass
    nxt = b.get("nextBillingDate") if isinstance(b.get("nextBillingDate"), str) else None
    wins = [window("points", "Compute points", used=total - left, limit=total or None, unit="credits", resets=nxt,
                   period=30 * DAY, primary=True)]
    return {"plan": b.get("currentTier") if isinstance(b.get("currentTier"), str) else None, "windows": wins,
            "balances": [balance("left", "Compute points left", left, "credits")]}


# ---------------------------------------------------------------- Qoder
class Qoder(Provider):
    id = "qoder"
    name = "Qoder"
    vendor = "Alibaba"
    color = "#2dd4bf"
    mono = "Qo"
    blurb = "Model credits used (own + shared quota), next reset"
    options = [Field("site", "Site", "select", options=[["com", "qoder.com"], ["cn", "qoder.com.cn"]], default="com")]
    auths = [whole_cookie("qoder.com")]

    def fetch(self, acct):
        origin = "https://qoder.com.cn" if acct.options.get("site") == "cn" else "https://qoder.com"
        d = web("Qoder", "GET", origin + "/api/v2/me/usages/big_model_credits", acct.creds["cookie"],
                {"Accept": "application/json, text/plain, */*", "Origin": origin, "Referer": origin + "/account/usage",
                 "X-Requested-With": "XMLHttpRequest", "Bx-V": "2.5.35"})
        return parse_qoder(d)


def _f(o, camel, snake):
    v = o.get(camel)
    return o.get(snake) if v is None else v


def _qoder_quota(s):
    if not isinstance(s, dict):
        raise RuntimeError("Qoder answered without a quota summary")
    used, tot = core.num(_f(s, "usedValue", "used_value")), core.num(_f(s, "limitValue", "limit_value"))
    if used is None or tot is None:
        raise RuntimeError("Qoder answered with unreadable quota numbers")
    rem = core.num(_f(s, "remainingValue", "remaining_value"))
    return used, tot, max(0.0, tot - used) if rem is None else rem, core.num(_f(s, "usagePercentage", "usage_percentage"))


def parse_qoder(root):
    tq = _f(root, "totalQuota", "total_quota")
    if not isinstance(tq, dict):
        raise RuntimeError("Qoder answered in a format Burnrate does not know")
    used, tot, rem, pct = _qoder_quota(_f(tq, "quotaSummary", "quota_summary"))
    sq = _f(root, "sharedQuota", "shared_quota")
    ss = _f(sq, "quotaSummary", "quota_summary") if isinstance(sq, dict) else None
    if ss is not None:
        u2, t2, r2, _ = _qoder_quota(ss)
        used, tot, rem, pct = used + u2, tot + t2, rem + r2, None
    if pct is None:
        pct = used / tot * 100 if tot > 0 else 100
    return {"windows": [window("credits", "Credits", max(0.0, min(100.0, pct)), used=used, limit=tot, unit="credits",
                               resets=_f(root, "nextResetAt", "next_reset_at"), primary=True)],
            "balances": [balance("left", "Credits left", rem, "credits")]}


# ---------------------------------------------------------------- Trae CN
class TraeCN(Provider):
    id = "traecn"
    name = "Trae CN"
    vendor = "ByteDance"
    color = "#ff4d4f"
    mono = "Tr"
    blurb = "Credits used of the current entitlement (trae.cn)"
    auths = [whole_cookie("trae.cn")]

    def fetch(self, acct):
        h = {"Origin": "https://www.trae.cn", "Referer": "https://www.trae.cn/"}
        t = web("Trae CN", "POST", "https://api.trae.cn/cloudide/api/v3/common/GetUserToken", acct.creds["cookie"], h, body={})
        tok = ((t.get("Result") or {}).get("Token") or "").strip()
        if not tok:
            raise RuntimeError("Trae CN did not hand out a user token: paste a fresh cookie")
        d = web("Trae CN", "POST", "https://api.trae.cn/trae/api/v2/pay/user_current_entitlement_list", acct.creds["cookie"],
                {**h, "Authorization": "Cloud-IDE-JWT " + tok}, body={"require_usage": True, "full_data": True})
        return parse_traecn(d)


def parse_traecn(p):
    if p.get("code") == 1001:
        raise RuntimeError("Trae CN session expired: paste a fresh cookie")
    s = p.get("usage_summary") or {}
    tot, used = core.num(s.get("total_amount")), core.num(s.get("consumed_amount"))
    if p.get("is_credits_billing") is not True or tot is None or used is None:
        raise RuntimeError("Trae CN answered in a format Burnrate does not know (not a credits plan?)")
    packs = p.get("user_entitlement_pack_list") or []
    sub = next((x for x in packs if isinstance(x, dict) and x.get("group_type") == 0 and x.get("status") in (None, 1)), {})
    wins = [window("credits", "Credits", used=used, limit=tot, unit="credits", primary=True)] if tot > 0 else []
    return {"plan": (sub.get("display_desc") or "").strip() or None, "windows": wins,
            "balances": [balance("left", "Credits left", max(0.0, tot - used), "credits")]}


# ---------------------------------------------------------------- Raycast
class Raycast(Provider):
    id = "raycast"
    name = "Raycast AI"
    vendor = "Raycast"
    color = "#ff6363"
    mono = "R"
    blurb = "AI credits left of this period's total, next refill"
    auths = [cookie_field("__raycast_session", "DevTools on www.raycast.com → Application → Cookies (__raycast_session).")]

    def fetch(self, acct):
        parts = [x.strip() for x in _cookie(acct, "__raycast_session").split(";")]
        c = "; ".join(x for x in parts if re.match(r"^(__raycast_session|csrf_token)=", x))
        if not re.search(r"__raycast_session=[^;]+", c):
            raise RuntimeError("No __raycast_session cookie in what you pasted")
        d = web("Raycast", "GET", "https://www.raycast.com/frontend_api/current_user/ai_credits", c,
                {"Origin": "https://www.raycast.com", "Referer": "https://www.raycast.com/settings"})
        return parse_raycast(d)


def parse_raycast(d):
    rem, tot = core.num(d.get("remaining_balance_credits")), core.num(d.get("total_balance_credits"))
    if rem is None and tot is None:
        raise RuntimeError("Raycast answered without credit amounts")
    tier = ((d.get("funding_subscription") or {}).get("tier") or "").strip()
    plan = {"pro": "Pro", "pro_plus": "Pro+", "max": "Max"}.get(tier, tier or None)
    wins = [window("credits", "AI credits", used=max(0.0, tot - rem), limit=tot, unit="credits", resets=d.get("next_credits_at"),
                   period=30 * DAY, primary=True)] if rem is not None and tot else []
    bals = [balance("left", "Credits left", rem, "credits")] if rem is not None else []
    return {"plan": plan, "windows": wins, "balances": bals}


# ---------------------------------------------------------------- LongCat
class LongCat(Provider):
    id = "longcat"
    name = "LongCat"
    vendor = "Meituan"
    color = "#ffc300"
    mono = "LC"
    blurb = "Token allowance used, fuel packs left"
    auths = [whole_cookie("longcat.chat")]

    def fetch(self, acct):
        c = acct.creds["cookie"]
        h = {"Accept": "application/json, text/plain, */*", "Origin": "https://longcat.chat",
             "Referer": "https://longcat.chat/platform/usage"}
        req = lambda path, post=False: longcat_unwrap(web("LongCat", "POST" if post else "GET", "https://longcat.chat" + path, c, h,
                                                          body={} if post else None))

        def opt(path, post=False):
            try:
                return req(path, post)
            except Exception:
                return None
        account = req("/api/v1/user-current")
        summary = opt("/api/pay/quota/metering/token-packs/summary", True)
        lot = (summary or {}).get("currentLot") if isinstance((summary or {}).get("currentLot"), dict) else None
        usage = None
        if not (lot and str(lot.get("status") or "").upper() == "ACTIVE" and (core.num(lot.get("totalToken")) or 0) > 0):
            lot = None
            usage = req("/api/lc-platform/v1/tokenUsage")
        fuel = opt("/api/lc-platform/v1/pending-fuel-packages")
        return parse_longcat(account, lot, usage, fuel)


def longcat_unwrap(env):
    if not isinstance(env, dict):
        raise RuntimeError("LongCat answered in a format Burnrate does not know")
    if "code" in env:
        code = int(core.num(env["code"]) or 0)
        if code in (401, 403):
            raise RuntimeError("LongCat session expired: paste a fresh cookie in Settings")
        if code not in (0, 200):
            raise RuntimeError("LongCat: " + str(env.get("message") or env.get("msg") or f"code {code}")[:100])
    d = env.get("data", env) if "data" in env else env
    if not isinstance(d, dict):
        raise RuntimeError("LongCat answered without data")
    return d


def parse_longcat(account, lot=None, usage=None, fuel=None):
    if lot:
        total, used = core.num(lot.get("totalToken")), core.num(lot.get("consumedToken")) or 0
    else:
        u = usage.get("usage") if isinstance((usage or {}).get("usage"), dict) else (usage or {})
        total = core.num(u.get("totalToken"))
        if total is None:
            raise RuntimeError("LongCat token usage has no totalToken")
        used = core.num(u.get("usedToken"))
        if used is None:
            avail = core.num(u.get("availableToken"))
            used = total - (total if avail is None else avail)
    wins, bals = [], []
    if total and total > 0:
        wins.append(window("tokens", "Token allowance", used=max(0.0, used), limit=total, unit="tokens", primary=True))
    if isinstance(fuel, dict):
        ftot = core.num(fuel.get("totalQuota"))
        rem, saw, reset = 0.0, False, None
        for pk in fuel.get("list") or []:
            a = core.num((pk or {}).get("availableToken"))
            if a is not None:
                rem, saw = rem + a, True
            exp = (pk or {}).get("expireTime")
            t = core.iso_ts(exp) if not (isinstance(exp, str) and re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$", exp)) \
                else core.iso_ts(exp.replace(" ", "T"))
            if t and (reset is None or t < reset):
                reset = t
        if not saw:
            rem = ftot or 0
        if ftot and ftot > 0:
            wins.append(window("fuel", "Fuel packs", used=max(0.0, ftot - rem), limit=ftot, unit="tokens", resets=reset,
                               primary=not wins))
            bals.append(balance("fuel_left", "Fuel tokens left", rem, "tokens"))
    if not wins:
        raise RuntimeError("LongCat: no token allowance on this account")
    name = account.get("name") or account.get("nickName")
    return {"windows": wins, "balances": bals, "info": [{"label": "Account", "value": str(name)}] if name else []}


# ---------------------------------------------------------------- Langdock
class Langdock(Provider):
    id = "langdock"
    name = "Langdock"
    vendor = "Langdock"
    color = "#0f172a"
    mono = "Ld"
    blurb = "Personal 5-hour session and weekly usage limits"
    auths = [cookie_field("auth_token", "DevTools on app.langdock.com → Application → Cookies (auth_token).")]

    def fetch(self, acct):
        inp = urllib.parse.quote(json.dumps({"0": {"json": None, "meta": {"values": ["undefined"], "v": 1}}}, separators=(",", ":")))
        d = web("Langdock", "GET", f"https://app.langdock.com/api/trpc/usageSettings.getPersonalUsage?batch=1&input={inp}",
                _cookie(acct, "auth_token"), {"Accept": "application/json", "Referer": "https://app.langdock.com/settings/account/usage"})
        return parse_langdock(d)


def parse_langdock(raw):
    if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
        raise RuntimeError("Langdock answered in a format Burnrate does not know")
    env = raw[0]
    if env.get("error") is not None:
        code = ((((env["error"] or {}).get("json") or {}).get("data") or {}).get("code"))
        if code == "UNAUTHORIZED":
            raise RuntimeError("Langdock session expired: paste a fresh cookie in Settings")
        raise RuntimeError("Langdock rejected the usage request" + (f" ({code})" if code else ""))
    p = (((env.get("result") or {}).get("data") or {}).get("json")) or {}
    if p.get("hasIncludedUsageLimits") is False or p.get("planUsage") is None:
        raise RuntimeError("Langdock: this workspace has no included usage limits")
    pu = p["planUsage"]
    wins = []
    if pu.get("sessionUsageLimitsEnabled"):
        wins.append(window("session", "5-hour session", pu.get("sessionUsagePercent"), resets=pu.get("sessionResetsAt"), period=5 * HOUR))
    wins.append(window("weekly", "Weekly", pu.get("weeklyUsagePercent"), resets=pu.get("weeklyResetsAt"), period=WEEK, primary=True))
    return {"windows": wins}


# ---------------------------------------------------------------- Manus
class Manus(Provider):
    id = "manus"
    name = "Manus"
    vendor = "Manus AI"
    color = "#34322d"
    mono = "Ma"
    blurb = "Monthly plan credits, refresh credits, total balance"
    auths = [cookie_field("session_id", "DevTools on manus.im → Application → Cookies (session_id).")]

    def fetch(self, acct):
        raw = acct.creds["cookie"].strip()
        m = re.search(r"(?:^|;)\s*session_id\s*=\s*([^;]+)", raw, re.I)
        tok = m.group(1).strip() if m else (raw if not re.search(r"[=;]", raw) else "")
        if not tok:
            raise RuntimeError("No session_id in what you pasted")
        d = web("Manus", "POST", "https://api.manus.im/user.v1.UserService/GetAvailableCredits", None,
                {"Authorization": "Bearer " + tok, "Origin": "https://manus.im", "Referer": "https://manus.im/",
                 "Connect-Protocol-Version": "1"}, body={})
        return parse_manus(d)


MANUS_KEYS = ("totalCredits", "freeCredits", "periodicCredits", "addonCredits", "refreshCredits", "maxRefreshCredits",
              "proMonthlyCredits", "eventCredits")


def parse_manus(root):
    d = next((x for x in (root.get("data"), root.get("result"), root.get("response"), root.get("availableCredits"), root)
              if x is not None), root)
    if not isinstance(d, dict) or not any(k in d for k in MANUS_KEYS):
        raise RuntimeError("Manus answered without credit fields")
    n = lambda k: core.num(d.get(k)) or 0
    r = d.get("nextRefreshTime")
    reset = r + 978307200 if isinstance(r, (int, float)) else r      # numeric dates use the 2001 reference epoch
    wins = []
    if n("proMonthlyCredits") > 0:
        wins.append(window("monthly", "Monthly credits", used=n("proMonthlyCredits") - n("periodicCredits"),
                           limit=n("proMonthlyCredits"), unit="credits", period=30 * DAY, primary=True))
    if n("maxRefreshCredits") > 0:
        iv = (d.get("refreshInterval") or "").strip()
        wins.append(window("refresh", (iv.title() + " refresh") if iv else "Refresh credits",
                           used=n("maxRefreshCredits") - n("refreshCredits"), limit=n("maxRefreshCredits"), unit="credits",
                           resets=reset, period=DAY if iv.lower() == "daily" else None, primary=not wins))
    bals = [balance("total", "Credits", n("totalCredits"), "credits", note=f"free {n('freeCredits'):.0f}")]
    return {"windows": wins, "balances": bals}


# ---------------------------------------------------------------- Replicate
class Replicate(Provider):
    id = "replicate"
    name = "Replicate"
    vendor = "Replicate"
    color = "#3d3d3d"
    mono = "Rp"
    category = "api"
    blurb = "Spend this month (current invoice), prepaid credit"
    auths = [whole_cookie("replicate.com")]

    def fetch(self, acct):
        c = acct.creds["cookie"]
        html = web("Replicate", "GET", "https://replicate.com/account/billing", c, {"Accept": "text/html"}, raw=True)
        kind, user = replicate_account(html.decode(errors="replace"))
        base = f"https://replicate.com/api/{'organizations' if kind == 'organization' else 'users'}/{urllib.parse.quote(user, safe='')}"
        inv = web("Replicate", "GET", base + "/invoices", c)
        credit = None
        try:
            credit = web("Replicate", "GET", base + "/unused-credit", c)
        except Exception:
            pass
        return parse_replicate(inv, credit, user)


def replicate_account(html):
    for m in re.finditer(r"<script\b([^>]*)>([\s\S]*?)</script\s*>", html, re.I):
        attrs = m.group(1)
        if not re.search(r"\bid\s*=\s*([\"'])react-component-props[^\"']*\1", attrs, re.I) or \
                not re.search(r"\btype\s*=\s*([\"'])application/json\1", attrs, re.I):
            continue
        try:
            queue = [json.loads(m.group(2))]
        except ValueError:
            continue
        seen = 0
        while queue and seen < 4000:
            item, seen = queue.pop(0), seen + 1
            if isinstance(item, dict):
                a = item.get("account")
                if isinstance(a, dict) and a.get("kind") in ("user", "organization") and (a.get("username") or "").strip():
                    return a["kind"], a["username"].strip()
                queue += [v for v in item.values() if isinstance(v, (dict, list))]
            elif isinstance(item, list):
                queue += [v for v in item if isinstance(v, (dict, list))]
    if re.search(r"<title>\s*Sign in\s*\|\s*Replicate\s*</title>", html, re.I):
        raise RuntimeError("Replicate session expired: paste a fresh cookie in Settings")
    raise RuntimeError("Replicate billing page has no account data Burnrate can read")


def _money(v):
    return float(v) if isinstance(v, str) and re.match(r"^\d+(\.\d+)?$", v.strip()) else None


def parse_replicate(inv, credit=None, user=None, now=None):
    now = now or time.time()
    cur = None
    for i in (inv or {}).get("invoices") or []:
        if not isinstance(i, dict) or i.get("type") != "monthly-usage":
            continue
        end = i.get("ended_before")
        if end is None or (core.iso_ts(end) or 0) > now:
            cur = i
            break
    if not cur:
        raise RuntimeError("Replicate has no current monthly-usage invoice")
    used = _money(cur.get("total_cost_before_adjustments"))
    if used is None:
        raise RuntimeError("Replicate invoice has no readable total")
    bals = [balance("month", "Spent this month", used, "USD", kind="spent")]
    left = _money((credit or {}).get("unused_credit"))
    if left is not None:
        bals.append(balance("credit", "Credit balance", left, "USD"))
    return {"balances": bals, "info": [{"label": "Account", "value": user}] if user else []}


# ---------------------------------------------------------------- GroqCloud console
GROQ_STYTCH_PUBLIC = "public-token-live-58df57a9-a1f5-4066-bc0c-2ff942db684f"


class GroqConsole(Provider):
    id = "groq"
    name = "GroqCloud"
    vendor = "Groq"
    color = "#f55036"
    mono = "Gq"
    category = "api"
    blurb = "Spend, requests and tokens this month and today (console activity)"
    auths = [cookie_field("stytch_session", "DevTools on console.groq.com → Application → Cookies (stytch_session, "
                                            "the long-lived opaque token, not stytch_session_jwt).")]

    def fetch(self, acct):
        import base64
        tok = acct.creds["cookie"].strip()
        m = re.search(r"(?:^|;)\s*stytch_session=([^;]+)", tok)
        tok = m.group(1).strip() if m else tok
        sdk = base64.b64encode(b'{"app":{"identifier":"console.groq.com"},'
                               b'"sdk":{"identifier":"Stytch.js Javascript SDK","version":"5.43.0"}}').decode()
        try:
            a = core.http("POST", "https://api.stytchb2b.groq.com/sdk/v1/b2b/sessions/authenticate",
                          body={"session_token": tok, "session_duration_minutes": 30},
                          headers={"Authorization": "Basic " + base64.b64encode(f"{GROQ_STYTCH_PUBLIC}:{tok}".encode()).decode(),
                                   "Origin": "https://console.groq.com", "X-SDK-Parent-Host": "https://console.groq.com",
                                   "X-SDK-Client": sdk})
        except core.HttpError as e:
            if e.code in (400, 401, 403, 404):
                raise RuntimeError("Groq console session expired: paste a fresh stytch_session cookie") from None
            raise
        jwt = (((a.get("data") or {}).get("session_jwt")) or "").strip()
        if not jwt:
            raise RuntimeError("Groq login service answered without a session")
        org = groq_org(jwt)
        if not org:
            raise RuntimeError("Groq session has no organization")
        s, e = month_bounds()
        rows = web("Groq", "GET", f"https://api.groq.com/platform/v1/organizations/{urllib.parse.quote(org, safe='')}/activity"
                                  f"?start_date={s}&end_date={min(e, int(time.time()) + DAY)}", None,
                   {"Authorization": "Bearer " + jwt, "Accept": "application/json"})
        return parse_groq(rows)


def groq_org(jwt):
    c = core.jwt_claims(jwt)
    o = c.get("https://groq.com/organization")
    if isinstance(o, dict) and o.get("id"):
        return o["id"]
    o = c.get("https://stytch.com/organization")
    return o.get("slug") if isinstance(o, dict) else None


def parse_groq(d, now=None):
    if not isinstance(d.get("data"), list):
        raise RuntimeError("Groq activity answer has no data")
    now = now or time.time()
    day0 = int(now // DAY * DAY)
    cost = today = req = tok = 0.0
    org = None
    for r in d["data"]:
        c = core.num(r.get("cost")) or 0
        cost += c
        if (core.num(r.get("timestamp")) or 0) >= day0:
            today += c
        req += core.num(r.get("num_requests")) or 0
        tok += (core.num(r.get("n_context_tokens_total")) or 0) + (core.num(r.get("n_generated_tokens_total")) or 0)
        org = org or r.get("organization_name") or None
    info = [{"label": "Requests this month", "value": f"{int(req):,}"}, {"label": "Tokens this month", "value": f"{int(tok):,}"}]
    if org:
        info.insert(0, {"label": "Organization", "value": org})
    return {"balances": [balance("month", "Spent this month", cost, "USD", kind="spent"),
                         balance("today", "Spent today (UTC)", today, "USD", kind="spent")], "info": info}
