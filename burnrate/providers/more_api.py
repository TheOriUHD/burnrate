"""Pay-as-you-go API accounts read with an API / admin key: DeepInfra, Venice, SiliconFlow, fal, Exa, Tavily,
ElevenLabs, Deepgram, Hugging Face, Neuralwatt.

Endpoints and fields follow CodexBar's provider plugins (Sources/CodexBarCore/Resources/Plugins/<id>.js)."""
import time
import urllib.parse
from datetime import datetime, timezone
from .. import core
from .base import Provider, Fields, Field, window, balance, month_bounds, DAY, HOUR, WEEK

MONTH = 30 * DAY


def key(label="API key", ph="", help=""):
    return [Fields([Field("key", label, "secret", ph, help=help)])]


def _cents_or(v, div=1):
    n = core.num(v)
    return None if n is None else n / div


# ---------------------------------------------------------------- DeepInfra
class DeepInfra(Provider):
    id = "deepinfra"
    name = "DeepInfra"
    vendor = "DeepInfra"
    color = "#5f3dc4"
    mono = "DI"
    category = "api"
    blurb = "Prepaid balance (or amount owed), spend this month, billing-cycle limit"
    auths = key("API key", help="deepinfra.com → Dashboard → API keys.")

    def fetch(self, acct):
        c = self.get(acct, "https://api.deepinfra.com/payment/checklist?compute_owed=true")
        u = self.get(acct, "https://api.deepinfra.com/payment/usage?from=current")
        return parse_deepinfra(c, u)


def parse_deepinfra(checklist, usage):
    recent = max(0.0, core.num(checklist.get("recent")) or 0)
    sb = core.num(checklist.get("stripe_balance"))
    if sb is None:
        raise RuntimeError("DeepInfra answered without a balance")
    bal = sb + recent                      # > 0: owed, <= 0: credit available
    months = usage.get("months") or []
    month_cost = max(0.0, (core.num(months[-1].get("total_cost")) or 0) / 100) if months else recent
    s, e = month_bounds()
    bals = [balance("available", "Available", max(0.0, -bal), "USD"),
            balance("month", "Spent this month", month_cost, "USD", kind="spent")]
    if bal > 0:
        bals.append(balance("owed", "Owed", bal, "USD", kind="spent"))
    wins = []
    lim = core.num(checklist.get("limit"))
    if lim and lim > 0:
        wins.append(window("cycle", "Billing-cycle limit", used=recent, limit=lim, unit="USD", primary=True))
    info = []
    if checklist.get("suspended"):
        info.append({"label": "Status", "value": "Suspended" + (": " + checklist["suspend_reason"].strip()
                                                               if (checklist.get("suspend_reason") or "").strip() else "")})
    return {"windows": wins, "balances": bals, "info": info}


# ---------------------------------------------------------------- Venice
class Venice(Provider):
    id = "venice"
    name = "Venice"
    vendor = "Venice.ai"
    color = "#d94f30"
    mono = "V"
    category = "api"
    blurb = "USD and DIEM balances, DIEM used of this epoch's allocation"
    auths = key("API key", help="venice.ai → Settings → API.")

    def fetch(self, acct):
        return parse_venice(self.get(acct, "https://api.venice.ai/api/v1/billing/balance"))


def parse_venice(d):
    if not isinstance(d.get("balances"), dict):
        raise RuntimeError("Venice answered without balances")
    b = d["balances"]
    diem, usd, alloc = core.num(b.get("diem")), core.num(b.get("usd")), core.num(d.get("diemEpochAllocation"))
    cur = (d.get("consumptionCurrency") or "").upper() or None
    wins, bals = [], []
    if diem is not None and alloc and alloc > 0:
        wins.append(window("diem", "DIEM epoch allocation", used=alloc - diem, limit=alloc, unit="DIEM", primary=True))
    if usd is not None:
        bals.append(balance("usd", "USD balance", usd, "USD"))
    if diem is not None:
        bals.append(balance("diem", "DIEM balance", diem, "DIEM"))
    info = [{"label": "Pays with", "value": cur}] if cur else []
    if d.get("canConsume") is False:
        info.append({"label": "Status", "value": "balance cannot be used for API calls"})
    if not wins and not bals:
        raise RuntimeError("Venice answered without a usable balance")
    return {"windows": wins, "balances": bals, "info": info}


# ---------------------------------------------------------------- SiliconFlow
class SiliconFlow(Provider):
    id = "siliconflow"
    name = "SiliconFlow"
    vendor = "SiliconFlow"
    color = "#7c3aed"
    mono = "SF"
    category = "api"
    blurb = "Account balance (purchased and bonus)"
    options = [Field("region", "Platform", "select", options=[["com", "api.siliconflow.com (USD)"],
                                                              ["cn", "api.siliconflow.cn (CNY)"]], default="com",
                     help="SiliconFlow retired the China balance API in August 2026; the China option may stop working.")]
    auths = key("API key", "sk-…")

    def fetch(self, acct):
        cn = acct.options.get("region") == "cn"
        try:
            d = self.get(acct, f"https://api.siliconflow.{'cn' if cn else 'com'}/v1/user/info")
        except core.HttpError as e:
            if e.code == 410:
                raise RuntimeError("SiliconFlow retired this balance API: check the balance in the console") from None
            raise
        return parse_siliconflow(d, "CNY" if cn else "USD")


def parse_siliconflow(root, cur):
    if root.get("code") == 20092:
        raise RuntimeError("SiliconFlow retired this balance API: check the balance in the console")
    if root.get("code") == 30014:
        raise RuntimeError("SiliconFlow rejected the API key")
    if root.get("code") != 20000 or root.get("status") is not True or not isinstance(root.get("data"), dict):
        raise RuntimeError("SiliconFlow answered in a format Burnrate does not know")
    d = root["data"]
    bals = [balance("total", "Balance", d.get("totalBalance"), cur)]
    if d.get("chargeBalance") is not None:
        bals.append(balance("charge", "Purchased", d.get("chargeBalance"), cur))
    if d.get("balance") is not None:
        bals.append(balance("bonus", "Bonus", d.get("balance"), cur))
    info = [{"label": "Status", "value": d["status"]}] if d.get("status") not in (None, "normal") else []
    return {"balances": bals, "info": info}


# ---------------------------------------------------------------- fal
class Fal(Provider):
    id = "fal"
    name = "fal"
    vendor = "fal.ai"
    color = "#ec0648"
    mono = "fa"
    category = "credits"
    official = True
    blurb = "Credit balance"
    auths = key("Admin/billing API key", help="fal.ai → Keys; needs the billing:usage:read permission (BILLING, READONLY or FULL).")

    def fetch(self, acct):
        try:
            d = self.get(acct, "https://api.fal.ai/v1/account/billing?expand=credits", auth_header=lambda t: {"Authorization": "Key " + t})
        except RuntimeError as e:
            if "(403)" in str(e):
                raise RuntimeError("fal: this key lacks the billing:usage:read permission") from None
            raise
        return parse_fal(d)


def parse_fal(d):
    c = d.get("credits")
    if not isinstance(c, dict):
        raise RuntimeError("fal did not return the credit balance this time")
    amt = core.num(c.get("current_balance"))
    if amt is None:
        raise RuntimeError("fal returned an unreadable credit balance")
    cur = c.get("currency") if isinstance(c.get("currency"), str) and len(c["currency"]) == 3 else "USD"
    info = [{"label": "Account", "value": d["username"].strip()}] if (d.get("username") or "").strip() else []
    return {"balances": [balance("credits", "Credits", amt, cur)], "info": info}


# ---------------------------------------------------------------- Exa
class Exa(Provider):
    id = "exa"
    name = "Exa"
    vendor = "Exa"
    color = "#1f40ed"
    mono = "Ex"
    category = "api"
    official = True
    blurb = "Spend of one API key this month (Team Management API)"
    options = [Field("key_id", "API key ID", placeholder="the id of the search key to watch",
                     help="dashboard.exa.ai → API keys: the key's ID, not the key itself.")]
    auths = key("Service key", help="A Team Management service key (ordinary search keys do not work).")

    def fetch(self, acct):
        kid = (acct.options.get("key_id") or "").strip()
        if not kid:
            raise RuntimeError("Set the Exa API key ID in the account options")
        now = int(time.time())
        s, e = month_bounds(now)
        f = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        url = (f"https://admin-api.exa.ai/team-management/api-keys/{urllib.parse.quote(kid, safe='')}/usage"
               f"?start_date={urllib.parse.quote(f(s))}&end_date={urllib.parse.quote(f(now))}")
        return parse_exa(self.get(acct, url, auth_header=lambda t: {"x-api-key": t}))


def parse_exa(d):
    v = core.num(d.get("total_cost_usd"))
    if v is None:
        raise RuntimeError("Exa answered without total_cost_usd")
    return {"balances": [balance("month", "Key spend this month", v, "USD", kind="spent")]}


# ---------------------------------------------------------------- Tavily
class Tavily(Provider):
    id = "tavily"
    name = "Tavily"
    vendor = "Tavily"
    color = "#3b5bdb"
    mono = "Tv"
    category = "api"
    official = True
    blurb = "Plan credits used, key limit, pay-as-you-go credits"
    help = "The usage endpoint allows only ten requests per ten minutes: keep the refresh interval above a minute."
    auths = key("API key", "tvly-…")

    def fetch(self, acct):
        return parse_tavily(self.get(acct, "https://api.tavily.com/usage"))


def parse_tavily(d):
    a, k = d.get("account"), d.get("key")
    if not isinstance(a, dict) or not isinstance(k, dict):
        raise RuntimeError("Tavily answered in a format Burnrate does not know")
    wins = []
    if core.num(a.get("plan_limit")):
        wins.append(window("plan", "Plan credits", used=a.get("plan_usage"), limit=a.get("plan_limit"), unit="credits", primary=True))
    if core.num(k.get("limit")):
        wins.append(window("key", "Key limit", used=k.get("usage"), limit=k.get("limit"), unit="credits", primary=not wins))
    if core.num(a.get("paygo_limit")):
        wins.append(window("paygo", "Pay as you go", used=a.get("paygo_usage"), limit=a.get("paygo_limit"), unit="credits"))
    info = [{"label": "Key credits used", "value": str(int(core.num(k.get("usage")) or 0))}]
    if not wins:
        wins.append(window("plan", "Plan credits", used=a.get("plan_usage"), limit=None, unit="credits", primary=True))
    plan = a.get("current_plan").strip() if isinstance(a.get("current_plan"), str) and a["current_plan"].strip() else None
    return {"plan": plan, "windows": wins, "info": info}


# ---------------------------------------------------------------- ElevenLabs
class ElevenLabs(Provider):
    id = "elevenlabs"
    name = "ElevenLabs"
    vendor = "ElevenLabs"
    color = "#000000"
    mono = "11"
    category = "subscription"
    official = True
    blurb = "Credits (characters) used this cycle, voice slots"
    auths = key("API key", help="elevenlabs.io → Developers → API keys; needs the user_read permission.")

    def fetch(self, acct):
        return parse_elevenlabs(self.get(acct, "https://api.elevenlabs.io/v1/user/subscription",
                                         auth_header=lambda t: {"xi-api-key": t}))


def parse_elevenlabs(d):
    if d.get("character_limit") is None:
        raise RuntimeError("ElevenLabs answered without a character limit")
    wins = [window("credits", "Credits", used=d.get("character_count"), limit=d.get("character_limit") or None, unit="credits",
                   resets=d.get("next_character_count_reset_unix"), period=MONTH, primary=True)]
    for wid, label, u, l in (("voices", "Voice slots", "voice_slots_used", "voice_limit"),
                             ("pro_voices", "Professional voices", "professional_voice_slots_used", "professional_voice_limit")):
        if d.get(u) is not None and core.num(d.get(l)):
            wins.append(window(wid, label, used=d[u], limit=d[l], unit="slots"))
    tier = (d.get("tier") or "").strip()
    plan = tier.replace("_", " ").title() if tier else None
    st = d.get("status")
    if plan and st and st.lower() != "active":
        plan += " · " + st
    return {"plan": plan or st, "windows": wins}


# ---------------------------------------------------------------- Deepgram
class Deepgram(Provider):
    id = "deepgram"
    name = "Deepgram"
    vendor = "Deepgram"
    color = "#13ef93"
    mono = "DG"
    category = "api"
    official = True
    blurb = "Requests, audio hours, tokens and TTS characters in the current usage period (all projects)"
    options = [Field("project", "Project ID", required=False, help="Leave empty to add up every project the key can see.")]
    auths = key("API key", help="console.deepgram.com → API keys (needs Management API access).")

    def fetch(self, acct):
        base = "https://api.deepgram.com/v1"
        ah = lambda t: {"Authorization": "Token " + t}
        pid = (acct.options.get("project") or "").strip()
        if pid:
            projects = [{"project_id": pid, "name": None}]
        else:
            projects = self.get(acct, base + "/projects", auth_header=ah).get("projects") or []
        if not projects:
            raise RuntimeError("Deepgram returned no projects for this key")
        rows = [self.get(acct, f"{base}/projects/{urllib.parse.quote(p['project_id'], safe='')}/usage/breakdown", auth_header=ah)
                for p in projects]
        return parse_deepgram(rows, projects)


def parse_deepgram(payloads, projects):
    t = dict(hours=0.0, total_hours=0.0, agent_hours=0.0, tokens_in=0.0, tokens_out=0.0, tts_characters=0.0, requests=0.0)
    start = end = None
    for p in payloads:
        if not isinstance(p.get("results"), list):
            raise RuntimeError("Deepgram usage answer has no results")
        if p.get("start") and (not start or p["start"] < start):
            start = p["start"]
        if p.get("end") and (not end or p["end"] > end):
            end = p["end"]
        for r in p["results"]:
            for k in t:
                t[k] += core.num(r.get(k)) or 0
    bals = [balance("requests", "Requests this period", t["requests"], "requests", kind="spent")]
    if t["hours"] or t["total_hours"]:
        bals.append(balance("hours", "Audio hours", t["hours"], "hours", kind="spent",
                            note=f"{t['total_hours']:.1f} billable hours"))
    if t["agent_hours"]:
        bals.append(balance("agent_hours", "Agent hours", t["agent_hours"], "hours", kind="spent"))
    if t["tokens_in"] or t["tokens_out"]:
        bals.append(balance("tokens", "Tokens", t["tokens_in"] + t["tokens_out"], "tokens", kind="spent"))
    if t["tts_characters"]:
        bals.append(balance("tts", "TTS characters", t["tts_characters"], "characters", kind="spent"))
    info = []
    if start and end:
        info.append({"label": "Period", "value": f"{start} to {end}"})
    info.append({"label": "Projects", "value": str(len(projects)) if len(projects) > 1 else (projects[0].get("name") or projects[0]["project_id"])})
    return {"balances": bals, "info": info}


# ---------------------------------------------------------------- Hugging Face
class HuggingFace(Provider):
    id = "huggingface"
    name = "Hugging Face"
    vendor = "Hugging Face"
    color = "#ffb000"
    mono = "HF"
    category = "api"
    blurb = "Inference Providers usage this month (included credits, billable, limit), ZeroGPU quota"
    auths = key("Access token", "hf_…", "huggingface.co → Settings → Access tokens: a classic read token, or a "
                                        "fine-grained one with Billing read.")

    def fetch(self, acct):
        now = int(time.time())
        s, e = month_bounds(now)
        u = self.get(acct, f"https://huggingface.co/api/settings/billing/usage-v2?startDate={s}&endDate={now}")
        gpu = who = None
        try:
            gpu = self.get(acct, "https://huggingface.co/api/spaces/zero-gpu/quota")
        except Exception:
            pass
        try:
            who = self.get(acct, "https://huggingface.co/api/whoami-v2")
        except Exception:
            pass
        return parse_huggingface(u, gpu, who, (s, e))


def parse_huggingface(u, gpu=None, who=None, bounds=None):
    s, e = bounds or month_bounds()
    inf = ((u.get("usage") or {}).get("inferenceProviders"))
    if not isinstance(inf, dict) or inf.get("usedNanoUsd") is None:
        raise RuntimeError("Hugging Face answered without inference usage")
    gross = (core.num(inf.get("usedNanoUsd")) or 0) / 1e9
    incl = (core.num(inf.get("includedNanoUsd")) or 0) / 1e9
    lim = (core.num(inf.get("limitNanoUsd")) or 0) / 1e9
    billable = max(0.0, gross - incl)
    wins, info = [], []
    if incl > 0:
        wins.append(window("included", "Included inference credits", used=min(gross, incl), limit=incl, unit="USD",
                           resets=e, period=e - s, primary=True))
    if lim > 0:
        wins.append(window("limit", "Spending limit", used=billable, limit=lim, unit="USD", resets=e, period=e - s,
                           primary=not wins))
    if isinstance(gpu, dict) and core.num(gpu.get("base")):
        tot, cur = core.num(gpu["base"]), core.num(gpu.get("current")) or 0
        wins.append(window("zerogpu", "ZeroGPU quota", used=max(0.0, tot - cur) / 60, limit=tot / 60, unit="min",
                           resets=gpu.get("resetsAt"), primary=not wins))
    bals = [balance("billable", "Billable this month", billable, "USD", kind="spent")]
    if inf.get("numRequests") is not None:
        info.append({"label": "Requests this month", "value": str(int(core.num(inf["numRequests"]) or 0))})
    plan = None
    if isinstance(who, dict):
        if isinstance(who.get("isPro"), bool):
            plan = "PRO" if who["isPro"] else "Free"
        if who.get("name"):
            info.append({"label": "Account", "value": who["name"]})
    return {"plan": plan, "windows": wins, "balances": bals, "info": info}


# ---------------------------------------------------------------- Neuralwatt
class Neuralwatt(Provider):
    id = "neuralwatt"
    name = "Neuralwatt"
    vendor = "Neuralwatt"
    color = "#10b981"
    mono = "NW"
    category = "subscription"
    blurb = "kWh used of the plan's energy allowance, prepaid balance, key allowance"
    options = [Field("base_url", "API URL", required=False, default="https://api.neuralwatt.com",
                     placeholder="https://api.neuralwatt.com")]
    auths = key("API key", help="portal.neuralwatt.com → Dashboard → API keys.")

    def fetch(self, acct):
        base = (acct.options.get("base_url") or "https://api.neuralwatt.com").rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        return parse_neuralwatt(self.get(acct, base + "/quota"))


def parse_neuralwatt(root):
    b = root.get("balance")
    if not isinstance(b, dict):
        raise RuntimeError("Neuralwatt answered without a balance")
    sub = root.get("subscription") or {}
    allow = ((root.get("key") or {}).get("allowance")) or {}
    nn = lambda v: v if v is not None and v >= 0 else None
    rem, used, tot = nn(core.num(b.get("credits_remaining_usd"))), nn(core.num(b.get("credits_used_usd"))), core.num(b.get("total_credits_usd"))
    if rem is None and tot and used is not None:
        rem = max(0.0, tot - used)
    if rem is None and used is None and not tot:
        raise RuntimeError("Neuralwatt answered without credit amounts")
    wins, bals = [], []
    inc, ku, kr = core.num(sub.get("kwh_included")), nn(core.num(sub.get("kwh_used"))), nn(core.num(sub.get("kwh_remaining")))
    if not inc and ku is not None and kr is not None:
        inc = ku + kr
    if ku is None and inc and kr is not None:
        ku = max(0.0, inc - kr)
    s, e = core.iso_ts(sub.get("current_period_start")), core.iso_ts(sub.get("current_period_end"))
    if inc and inc > 0 and ku is not None:
        wins.append(window("energy", "Energy allowance", used=ku, limit=inc, unit="kWh", resets=e,
                           period=(e - s) if s and e and e > s else MONTH, primary=True))
    if allow.get("blocked") is True:
        wins.append(window("key", "Key " + (allow.get("period") or "allowance"), 100, primary=not wins))
    elif allow.get("spent_usd") is not None and core.num(allow.get("limit_usd")):
        wins.append(window("key", "Key " + (allow.get("period") or "allowance"), used=allow["spent_usd"],
                           limit=allow["limit_usd"], unit="USD", primary=not wins))
    if rem is not None:
        bals.append(balance("credits", "Prepaid balance", rem, "USD"))
    plan = (sub.get("plan") or "").strip()
    plan = plan.replace("_", " ").title() if plan else ((b.get("accounting_method") or "").title() or None)
    info = [{"label": "In overage", "value": "yes"}] if sub.get("in_overage") else []
    return {"plan": plan, "windows": wins, "balances": bals, "info": info}
