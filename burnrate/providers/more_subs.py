"""Coding/token plans read with an API or management key: Xiaomi MiMo token plan, ZenMux, ClinePass, DevPass.

Endpoints and fields follow CodexBar's provider plugins (Sources/CodexBarCore/Resources/Plugins/<id>.js)."""
from datetime import datetime, timezone
from .. import core
from .base import Provider, Fields, Field, window, balance, HOUR, WEEK, DAY


def key(label="API key", ph="", help=""):
    return [Fields([Field("key", label, "secret", ph, help=help)])]


# ---------------------------------------------------------------- Xiaomi MiMo
class MiMo(Provider):
    id = "mimo"
    name = "Xiaomi MiMo Token Plan"
    vendor = "Xiaomi"
    color = "#ff6900"
    mono = "Mi"
    blurb = "Token-plan credits used this period"
    options = [Field("region", "Region", "select", options=[["cn", "China (token-plan-cn)"], ["sgp", "Singapore (token-plan-sgp)"]],
                     default="cn")]
    auths = key("API key")

    def fetch(self, acct):
        region = "sgp" if acct.options.get("region") == "sgp" else "cn"
        return parse_mimo(self.get(acct, f"https://token-plan-{region}.xiaomimimo.com/v1/platform/token_plan"))


def _utc_naive(s):
    """'2026-11-01 00:00:00' documented as UTC -> epoch."""
    if not s:
        return None
    try:
        return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
    except (TypeError, ValueError):
        return None


def parse_mimo(root):
    if root.get("object") != "token_plan" or not isinstance(root.get("quota"), dict):
        raise RuntimeError("MiMo answered in a format Burnrate does not know")
    q, p = root["quota"], root.get("period") or {}
    total, used, rem = core.num(q.get("total_credits")), core.num(q.get("used_credits")), core.num(q.get("remaining_credits"))
    if not total:
        raise RuntimeError("MiMo: this key has no token plan")
    s, e = _utc_naive(p.get("start_at")), _utc_naive(p.get("end_at"))
    wins = [window("credits", "Plan credits", used=used, limit=total, unit="credits", resets=e,
                   period=(e - s) if s and e and e > s else None, primary=True)]
    bals = [balance("remaining", "Credits left", rem, "credits")] if rem is not None else []
    return {"plan": root.get("plan_code") if isinstance(root.get("plan_code"), str) else None, "windows": wins, "balances": bals}


# ---------------------------------------------------------------- ZenMux
class ZenMux(Provider):
    id = "zenmux"
    name = "ZenMux"
    vendor = "ZenMux"
    color = "#111827"
    mono = "ZM"
    blurb = "Subscription 5-hour and 7-day flow quotas, pay-as-you-go balance"
    auths = key("Management API key", help="zenmux.ai → Settings → Management API keys (inference keys do not work).")

    def fetch(self, acct):
        base = "https://zenmux.ai/api/v1/management/"
        d = self.get(acct, base + "subscription/detail")
        payg = None
        try:
            payg = self.get(acct, base + "payg/balance")
        except Exception:
            pass
        return parse_zenmux(d, payg)


def parse_zenmux(env, payg_env=None):
    if env.get("success") is not True or not isinstance(env.get("data"), dict):
        raise RuntimeError("ZenMux answered in a format Burnrate does not know")
    d = env["data"]
    wins = []
    for k, wid, label, per in (("quota_5_hour", "5h", "5-hour", 5 * HOUR), ("quota_7_day", "7d", "7-day", WEEK)):
        q = d.get(k)
        if isinstance(q, dict) and q.get("usage_percentage") is not None:
            wins.append(window(wid, label, max(0.0, min(100.0, core.num(q["usage_percentage"]) * 100)), used=q.get("used_flows"),
                               limit=q.get("max_flows"), unit="flows", resets=q.get("resets_at"), period=per,
                               primary=wid == "5h"))
    if wins and not any(w["primary"] for w in wins):
        wins[0]["primary"] = True
    bals = []
    pd = (payg_env or {}).get("data") if (payg_env or {}).get("success") is True else None
    if isinstance(pd, dict) and str(pd.get("currency") or "").strip().lower() == "usd" and core.num(pd.get("total_credits")) is not None:
        bals.append(balance("payg", "Pay-as-you-go balance", pd["total_credits"], "USD"))
    tier = ((d.get("plan") or {}).get("tier") or "").strip()
    st = (d.get("account_status") or "").strip()
    plan = tier.title() + " plan" if tier else None
    info = []
    if st and st.lower() != "healthy":
        info.append({"label": "Account", "value": st.title()})
    exp = core.iso_ts((d.get("plan") or {}).get("expires_at"))
    if exp:
        info.append({"label": "Plan expires", "value": datetime.fromtimestamp(exp, timezone.utc).strftime("%Y-%m-%d")})
    if not wins and not bals:
        raise RuntimeError("ZenMux: no subscription quota and no pay-as-you-go balance")
    return {"plan": plan, "windows": wins, "balances": bals, "info": info}


# ---------------------------------------------------------------- ClinePass
class ClinePass(Provider):
    id = "clinepass"
    name = "ClinePass"
    vendor = "Cline"
    color = "#5a32a3"
    mono = "Cl"
    blurb = "5-hour, weekly and monthly plan limits"
    auths = key("API key", help="app.cline.bot → Settings → API keys.")

    def fetch(self, acct):
        return parse_clinepass(self.get(acct, "https://api.cline.bot/api/v1/users/me/plan/usage-limits"))


def parse_clinepass(p):
    if p.get("success") is not True or not isinstance((p.get("data") or {}).get("limits"), list):
        raise RuntimeError("ClinePass answered in a format Burnrate does not know")
    per = {"five_hour": (5 * HOUR, "5-hour"), "weekly": (WEEK, "Weekly"), "monthly": (30 * DAY, "Monthly")}
    wins = []
    for l in p["data"]["limits"]:
        t = l.get("type")
        if t not in per or core.num(l.get("percentUsed")) is None:
            continue
        wins.append(window(t, per[t][1], max(0.0, min(100.0, core.num(l["percentUsed"]))), resets=l.get("resetsAt"),
                           period=per[t][0], primary=t == "weekly"))
    if not wins:
        raise RuntimeError("ClinePass: no plan limits on this account")
    if not any(w["primary"] for w in wins):
        wins[0]["primary"] = True
    return {"windows": wins}


# ---------------------------------------------------------------- DevPass (LLM Gateway)
class DevPass(Provider):
    id = "devpass"
    name = "DevPass"
    vendor = "LLM Gateway"
    color = "#2563eb"
    mono = "DP"
    blurb = "DevPass cycle credits, premium weekly allowance, key spend"
    auths = key("Gateway API key", help="llmgateway.io → API keys (a regular gateway key).")

    def fetch(self, acct):
        return parse_devpass(self.get(acct, "https://api.llmgateway.io/v1/key"))


def parse_devpass(body):
    d = body.get("data")
    if not isinstance(d, dict) or d.get("devPlan") not in ("none", "lite", "pro", "max"):
        raise RuntimeError("DevPass answered in a format Burnrate does not know")
    m = lambda k: core.num(d.get(k))
    bals = [balance("key", "Key spend (all time)", m("usage"), "USD", kind="spent",
                    limit=m("limit") if d.get("limit") is not None else None)]
    if d["devPlan"] == "none":
        return {"plan": "Pay as you go", "balances": bals}
    wins = []
    if m("devPlanCreditsLimit"):
        wins.append(window("cycle", "Cycle credits", used=m("devPlanCreditsUsed"), limit=m("devPlanCreditsLimit"), unit="USD",
                           primary=True))
    if m("devPlanPremiumWeeklyLimit"):
        wins.append(window("premium_week", "Premium weekly", used=m("devPlanPremiumCreditsUsed"),
                           limit=m("devPlanPremiumWeeklyLimit"), unit="USD", resets=d.get("devPlanPremiumWeekResetsAt"),
                           period=WEEK, primary=not wins))
    if m("devPlanCreditsRemaining") is not None:
        bals.insert(0, balance("cycle_left", "Cycle credits left", m("devPlanCreditsRemaining"), "USD"))
    return {"plan": "DevPass " + d["devPlan"].title(), "windows": wins, "balances": bals}


# ---------------------------------------------------------------- Codebuff
class Codebuff(Provider):
    id = "codebuff"
    name = "Codebuff"
    vendor = "Codebuff"
    color = "#22c55e"
    mono = "Cb"
    blurb = "Credits used of the quota, weekly subscription limit, credits left"
    auths = key("API key", help="codebuff.com → Settings → API keys (or the authToken from ~/.config/manicode/credentials.json).")

    def fetch(self, acct):
        u = self.get(acct, "https://www.codebuff.com/api/v1/usage", method="POST", body={"fingerprintId": "burnrate-usage"})
        s = None
        try:
            s = self.get(acct, "https://www.codebuff.com/api/user/subscription")
        except Exception:
            pass
        return parse_codebuff(u, s)


def _first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and core.num(d.get(k)) is not None:
            return core.num(d[k])
    return None


def parse_codebuff(u, s=None):
    used, total, rem = _first(u, "usage", "used"), _first(u, "quota", "limit"), _first(u, "remainingBalance", "remaining")
    if used is None and total is None and rem is None:
        raise RuntimeError("Codebuff answered without credit numbers")
    wins, bals, plan = [], [], None
    if total and total > 0 and used is not None:
        wins.append(window("credits", "Credits", used=used, limit=total, unit="credits", resets=u.get("next_quota_reset"),
                           primary=True))
    if rem is not None:
        bals.append(balance("left", "Credits left", rem, "credits"))
    if isinstance(s, dict):
        sub, rl = s.get("subscription") if isinstance(s.get("subscription"), dict) else {}, s.get("rateLimit") or {}
        wu, wl = _first(rl, "weeklyUsed", "used"), _first(rl, "weeklyLimit", "limit")
        if wl and wl > 0 and wu is not None:
            wins.append(window("weekly", "Weekly limit", used=wu, limit=wl, resets=rl.get("weeklyResetsAt"), period=WEEK,
                               primary=not wins))
        for v in (sub.get("displayName"), s.get("displayName"), sub.get("tier"), s.get("tier"), sub.get("scheduledTier")):
            if isinstance(v, str) and v.strip():
                plan = v.strip()
                break
    info = [{"label": "Auto top-up", "value": "on" if u.get("autoTopupEnabled", u.get("auto_topup_enabled")) else "off"}] \
        if isinstance(u.get("autoTopupEnabled", u.get("auto_topup_enabled")), bool) else []
    return {"plan": plan, "windows": wins, "balances": bals, "info": info}


# ---------------------------------------------------------------- Kilo Code
KILO_PROCS = ["user.getCreditBlocks", "kiloPass.getState", "user.getAutoTopUpPaymentMethod"]
KILO_TIERS = {"tier_19": "Starter", "tier_49": "Pro", "tier_199": "Expert"}


class Kilo(Provider):
    id = "kilo"
    name = "Kilo Code"
    vendor = "Kilo Code"
    color = "#f8f675"
    mono = "K"
    blurb = "Kilo Pass credits used this period, credit balance"
    options = [Field("org", "Organization ID", required=False, help="Leave empty for your personal account.")]
    auths = key("API key", help="app.kilo.ai → Profile → API key.")

    def fetch(self, acct):
        import json as _json, urllib.parse as _up
        inp = _json.dumps({str(i): {"json": None} for i in range(len(KILO_PROCS))}, separators=(",", ":"))
        url = "https://app.kilo.ai/api/trpc/" + ",".join(KILO_PROCS) + "?batch=1&input=" + _up.quote(inp)
        h = {"X-KILOCODE-ORGANIZATIONID": acct.options["org"].strip()} if (acct.options.get("org") or "").strip() else {}
        return parse_kilo(self.get(acct, url, headers=h))


def _trpc_payload(entry):
    r = (entry or {}).get("result")
    if not isinstance(r, dict):
        return None
    if isinstance(r.get("data"), dict):
        return r["data"].get("json", r["data"]) if "json" in r["data"] else r["data"]
    return r.get("json")


def parse_kilo(root):
    if isinstance(root, dict) and ("result" in root or "error" in root):
        entries = [root]
    elif isinstance(root, list):
        entries = root[:len(KILO_PROCS)]
    elif isinstance(root, dict):
        entries = [root.get(str(i)) for i in range(len(KILO_PROCS))]
    else:
        raise RuntimeError("Kilo answered in a format Burnrate does not know")
    for i, e in enumerate(entries[:2]):
        if isinstance(e, dict) and isinstance(e.get("error"), dict):
            txt = str(e["error"]).lower()
            if "unauthorized" in txt or "forbidden" in txt:
                raise RuntimeError("Kilo rejected the API key")
            raise RuntimeError(f"Kilo: {KILO_PROCS[i]} failed")
    credits = _trpc_payload(entries[0]) if entries else None
    state = _trpc_payload(entries[1]) if len(entries) > 1 else None
    wins, bals, plan = [], [], None
    if isinstance(credits, dict):
        blocks = credits.get("creditBlocks")
        if isinstance(blocks, list) and blocks:
            tot = sum(core.num(b.get("amount_mUsd")) or 0 for b in blocks if isinstance(b, dict)) / 1e6
            rem = sum(core.num(b.get("balance_mUsd")) or 0 for b in blocks if isinstance(b, dict)) / 1e6
            bals.append(balance("credits", "Credit balance", max(0.0, rem), "USD", limit=max(0.0, tot) or None))
        elif core.num(credits.get("totalBalance_mUsd")) is not None:
            bals.append(balance("credits", "Credit balance", max(0.0, core.num(credits["totalBalance_mUsd"]) / 1e6), "USD"))
    sub = None
    if isinstance(state, dict):
        sub = state.get("subscription") if isinstance(state.get("subscription"), dict) else \
            (state if any(k in state for k in ("currentPeriodUsageUsd", "currentPeriodBaseCreditsUsd", "tier")) and
             "subscription" not in state else None)
    if sub:
        used, base = core.num(sub.get("currentPeriodUsageUsd")), core.num(sub.get("currentPeriodBaseCreditsUsd"))
        bonus = max(0.0, core.num(sub.get("currentPeriodBonusCreditsUsd")) or 0)
        reset = next((sub[k] for k in ("nextBillingAt", "nextRenewalAt", "renewsAt", "renewAt") if sub.get(k)), None)
        if base is not None and used is not None and base + bonus > 0:
            wins.append(window("pass", "Kilo Pass credits", used=max(0.0, used), limit=base + bonus, unit="USD", resets=reset,
                               period=30 * DAY, primary=True, note=f"incl. ${bonus:.2f} bonus" if bonus else None))
        tier = (sub.get("tier") or "").strip() if isinstance(sub.get("tier"), str) else ""
        plan = KILO_TIERS.get(tier, tier) or "Kilo Pass"
    if not wins and not bals:
        raise RuntimeError("Kilo returned no credits and no Kilo Pass for this account")
    return {"plan": plan, "windows": wins, "balances": bals}


# ---------------------------------------------------------------- OpenCode Go
OC_PCT = ["usagePercent", "usedPercent", "percentUsed", "percent", "usage_percent", "used_percent", "utilization",
          "utilizationPercent", "utilization_percent", "usage"]
OC_RESET_IN = ["resetInSec", "resetInSeconds", "resetSeconds", "reset_sec", "reset_in_sec", "resetsInSec", "resetsInSeconds",
               "resetIn", "resetSec"]
OC_RESET_AT = ["resetAt", "resetsAt", "reset_at", "resets_at", "nextReset", "next_reset", "renewAt", "renew_at"]


class OpenCodeGo(Provider):
    id = "opencodego"
    name = "OpenCode Go"
    vendor = "OpenCode"
    color = "#211e1e"
    mono = "OC"
    blurb = "Go subscription 5-hour, weekly and monthly quotas"
    auths = key("API key", help="opencode.ai → Zen → API keys (the key you use with OpenCode Go).")

    def fetch(self, acct):
        return parse_opencodego(self.get(acct, "https://opencode.ai/zen/go/v1/usage"))


def _oc_window(d, now):
    if not isinstance(d, dict):
        return None
    pct = next((core.num(d[k]) for k in OC_PCT if core.num(d.get(k)) is not None), None)
    if pct is None:
        u = next((core.num(d[k]) for k in ("used", "usage", "consumed", "count", "usedTokens", "usedMicroCents")
                  if core.num(d.get(k)) is not None), None)
        l = next((core.num(d[k]) for k in ("limit", "total", "quota", "max", "cap", "tokenLimit", "limitMicroCents")
                  if core.num(d.get(k)) is not None), None)
        if u is not None and l:
            pct = u / l * 100
    if pct is None:
        return None
    rin = next((core.num(d[k]) for k in OC_RESET_IN if core.num(d.get(k)) is not None), None)
    reset = now + int(rin) if rin is not None else next((core.iso_ts(d[k]) for k in OC_RESET_AT if core.iso_ts(d.get(k))), None)
    return max(0.0, min(100.0, pct)), reset


def parse_opencodego(root, now=None):
    import time as _t
    now = int(now or _t.time())
    u = root.get("usage")
    if not isinstance(u, dict) or not isinstance(u.get("rolling"), dict):
        raise RuntimeError("OpenCode Go answered without usage (no Go subscription?)")
    wins = []
    for k, wid, label, per in (("rolling", "5h", "5-hour", 5 * HOUR), ("weekly", "week", "Weekly", WEEK),
                               ("monthly", "month", "Monthly", 30 * DAY)):
        w = _oc_window(u.get(k), now)
        if w:
            wins.append(window(wid, label, w[0], resets=w[1], period=per, primary=k == "rolling"))
    if not wins:
        raise RuntimeError("OpenCode Go answered without readable quota windows")
    return {"plan": "OpenCode Go", "windows": wins}


# ---------------------------------------------------------------- StepFun Step Plan
STEPFUN_WEBID = "c8a1002d2c457e758785a9979832217c7c0b884c"


class StepFun(Provider):
    id = "stepfun"
    name = "StepFun Step Plan"
    vendor = "StepFun"
    color = "#0052d9"
    mono = "St"
    blurb = "Coding Plan 5-hour and weekly windows, or Token Plan credit pool"
    auths = [Fields([Field("token", "Oasis-Token", "secret", help="DevTools on platform.stepfun.com → Application → Cookies → "
                                                                  "Oasis-Token (the whole value).")], id="token", label="Session token")]

    def fetch(self, acct):
        tok = acct.creds["token"].strip()
        if tok.lower().startswith("oasis-token="):
            tok = tok.split("=", 1)[1].split(";", 1)[0]
        wid = stepfun_webid(tok)
        h = {"oasis-appid": "10300", "oasis-platform": "web", "oasis-webid": wid,
             "Cookie": f"Oasis-Token={tok}; Oasis-Webid={wid}"}
        base = "https://platform.stepfun.com/api/step.openapi.devcenter.Dashboard/"
        try:
            rl = core.http("POST", base + "QueryStepPlanRateLimit", body={}, headers=h)
        except core.HttpError as e:
            if e.code in (401, 403):
                raise RuntimeError("StepFun refused the token: paste a fresh Oasis-Token") from None
            raise
        name = None
        try:
            name = ((core.http("POST", base + "GetStepPlanStatus", body={}, headers=h).get("subscription")) or {}).get("name")
        except Exception:
            pass
        return parse_stepfun(rl, name)


def stepfun_webid(tok):
    """The Oasis-Webid must match the token's device_id claim (refresh half of an 'access...refresh' pair)."""
    for half in reversed(tok.split("...")):
        d = core.jwt_claims(half).get("device_id")
        if d:
            return d
    return STEPFUN_WEBID


def _ts(v):
    n = core.num(v)
    return int(n) if n and n > 0 else None


def parse_stepfun(d, plan=None):
    if d.get("status") not in (None, 1):
        raise RuntimeError("StepFun: " + str(d.get("message") or d.get("desc") or "request failed")[:100])
    cr = d.get("plan_credit_rate_limit") if isinstance(d.get("plan_credit_rate_limit"), dict) else {}
    live = (_ts(d.get("five_hour_usage_reset_time")) or _ts(d.get("weekly_usage_reset_time")))
    credit = not live and (cr.get("subscription_credit_left_rate") is not None or cr.get("topup_credit_left_rate") is not None
                           or bool(cr.get("credit_buckets")) or (not cr and core.num(d.get("plan_family")) == 2))
    wins = []
    if credit:
        left = None
        bk = cr.get("credit_buckets") or []
        good = [(core.num(b.get("credit_total")), core.num(b.get("credit_residual"))) for b in bk if isinstance(b, dict)]
        good = [(t, r) for t, r in good if t and t > 0 and r is not None and 0 <= r <= t]
        if bk and len(good) == len(bk):
            left = sum(r for _, r in good) / sum(t for t, _ in good)
        if left is None:
            left = core.num(cr.get("subscription_credit_left_rate"))
            if left is None:
                left = core.num(cr.get("topup_credit_left_rate"))
        reset = _ts(cr.get("subscription_credit_reset_time")) or min(
            [t for t in (_ts(b.get("next_reset_at")) for b in bk if isinstance(b, dict)) if t] or [0]) or None
        if left is not None:
            wins.append(window("credit", "Credit", (1 - left) * 100, resets=reset, primary=True))
    else:
        for k, wid, label, per in (("five_hour", "5h", "5-hour", 5 * HOUR), ("weekly", "week", "Weekly", WEEK)):
            r = core.num(d.get(f"{k}_usage_left_rate"))
            if r is not None:
                wins.append(window(wid, label, (1 - r) * 100, resets=_ts(d.get(f"{k}_usage_reset_time")), period=per,
                                   primary=wid == "5h"))
    if not wins:
        raise RuntimeError("StepFun: no Step Plan usage on this account yet")
    return {"plan": plan, "windows": wins}


# ---------------------------------------------------------------- Alibaba Model Studio Coding Plan (API key mode)
ALI = {"intl": ("https://modelstudio.console.alibabacloud.com", "ap-southeast-1", "sfm_codingplan_public_intl",
                "https://modelstudio.console.alibabacloud.com/ap-southeast-1/?tab=coding-plan#/efm/coding_plan"),
       "cn": ("https://bailian.console.aliyun.com", "cn-beijing", "sfm_codingplan_public_cn",
              "https://bailian.console.aliyun.com/cn-beijing/?tab=model#/efm/coding_plan")}


class AlibabaCodingPlan(Provider):
    id = "alibaba"
    name = "Alibaba Coding Plan"
    vendor = "Alibaba Cloud"
    color = "#ff6a00"
    mono = "Al"
    blurb = "Model Studio / Bailian Coding Plan 5-hour, weekly and monthly quotas"
    help = "API-key mode only: some China mainland accounts answer 'console login required' and cannot be read this way."
    options = [Field("region", "Region", "select", options=[["intl", "International (Model Studio)"], ["cn", "China mainland (Bailian)"]],
                     default="intl")]
    auths = key("API key", "sk-…", "The Coding Plan / DashScope API key.")

    def fetch(self, acct):
        base, rid, code, dash = ALI["cn" if acct.options.get("region") == "cn" else "intl"]
        url = (base + "/data/api.json?action=zeldaEasy.broadscope-bailian.codingPlan.queryCodingPlanInstanceInfoV2"
               f"&product=broadscope-bailian&api=queryCodingPlanInstanceInfoV2&currentRegionId={rid}")
        d = self.get(acct, url, method="POST", body={"queryCodingPlanInstanceInfoRequest": {"commodityCode": code}},
                     auth_header=lambda t: {"Authorization": "Bearer " + t, "x-api-key": t, "X-DashScope-API-Key": t},
                     headers={"Origin": base, "Referer": dash})
        return parse_alibaba(d)


def _expand(v):
    import json as _json
    if isinstance(v, str) and v[:1] in "{[":
        try:
            return _expand(_json.loads(v))
        except ValueError:
            return v
    if isinstance(v, dict):
        return {k: _expand(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_expand(x) for x in v]
    return v


def _find(v, keys, kind):
    """Breadth-first search for the first value under one of `keys` that is of type `kind`."""
    q = [v]
    while q:
        x = q.pop(0)
        if isinstance(x, dict):
            for k in keys:
                if isinstance(x.get(k), kind):
                    return x[k]
            q += [y for y in x.values() if isinstance(y, (dict, list))]
        elif isinstance(x, list):
            q += [y for y in x if isinstance(y, (dict, list))]
    return None


def parse_alibaba(raw):
    d = _expand(raw)
    code = _find(d, ["statusCode", "status_code", "code"], (int, str))
    msg = str(_find(d, ["statusMessage", "status_msg", "message", "msg"], str) or "")
    if "login" in str(code).lower() or "log in" in msg.lower() or "login" in msg.lower():
        raise RuntimeError("Alibaba answered 'console login required': this account cannot be read with an API key")
    if isinstance(code, int) and code not in (0, 200):
        raise RuntimeError("Alibaba: " + (msg or f"status code {code}")[:100])
    infos = [i for i in (_find(d, ["codingPlanInstanceInfos", "coding_plan_instance_infos"], list) or []) if isinstance(i, dict)]
    inst = next((i for i in infos if _find(i, ["codingPlanQuotaInfo", "coding_plan_quota_info"], dict)), infos[0] if infos else {})
    q = _find(inst, ["codingPlanQuotaInfo", "coding_plan_quota_info"], dict) or _find(d, ["codingPlanQuotaInfo", "coding_plan_quota_info"], dict)
    if not q:
        raise RuntimeError("Alibaba answered without coding-plan quota data (no active plan?)")
    g = lambda *ks: next((q[k] for k in ks if core.num(q.get(k)) is not None or (k.endswith("Time") and q.get(k))), None)
    wins = []
    for wid, label, per, u, t, r in (
            ("5h", "5-hour", 5 * HOUR, ("per5HourUsedQuota", "perFiveHourUsedQuota"), ("per5HourTotalQuota", "perFiveHourTotalQuota"),
             ("per5HourQuotaNextRefreshTime", "perFiveHourQuotaNextRefreshTime")),
            ("week", "Weekly", WEEK, ("perWeekUsedQuota",), ("perWeekTotalQuota",), ("perWeekQuotaNextRefreshTime",)),
            ("month", "Monthly", 30 * DAY, ("perBillMonthUsedQuota", "perMonthUsedQuota"), ("perBillMonthTotalQuota", "perMonthTotalQuota"),
             ("perBillMonthQuotaNextRefreshTime", "perMonthQuotaNextRefreshTime"))):
        tot = core.num(g(*t))
        if tot:
            wins.append(window(wid, label, used=core.num(g(*u)) or 0, limit=tot, resets=g(*r), period=per,
                               primary=wid == "5h"))
    if not wins:
        raise RuntimeError("Alibaba coding plan has no quota windows")
    if not any(w["primary"] for w in wins):
        wins[0]["primary"] = True
    plan = _find(inst, ["planName", "plan_name", "packageName", "package_name"], str) or \
        _find(d, ["planName", "plan_name", "packageName", "package_name"], str)
    return {"plan": plan, "windows": wins}
