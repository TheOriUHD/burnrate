"""Parse tests for the providers in more_api, more_subs, more_web, litellm and windsurf.

Each sample is shaped like the response the CodexBar source code reads (no network)."""
import json, time, unittest
from burnrate.providers import more_api as A, more_subs as S, more_web as W, litellm as L, windsurf as WS


def prim(out):
    p = [w for w in out.get("windows", []) if w["primary"]]
    return p[0] if p else None


def bal(out, id):
    return next(b for b in out["balances"] if b["id"] == id)


class Api(unittest.TestCase):
    def test_deepinfra(self):
        o = A.parse_deepinfra({"stripe_balance": -12.5, "recent": 2.5, "limit": 50, "suspended": False},
                              {"months": [{"period": "2026-10", "total_cost": 100}, {"period": "2026-11", "total_cost": 734}]})
        self.assertEqual(bal(o, "available")["amount"], 10.0)
        self.assertEqual(bal(o, "month")["amount"], 7.34)
        self.assertEqual(prim(o)["pct"], 5.0)

    def test_deepinfra_owed(self):
        o = A.parse_deepinfra({"stripe_balance": 3, "recent": 1, "suspended": True, "suspend_reason": "unpaid"}, {"months": []})
        self.assertEqual(bal(o, "owed")["amount"], 4.0)
        self.assertIn("unpaid", o["info"][0]["value"])

    def test_venice(self):
        o = A.parse_venice({"canConsume": True, "consumptionCurrency": "diem", "balances": {"diem": "7.5", "usd": 3},
                            "diemEpochAllocation": 10})
        self.assertEqual(prim(o)["pct"], 25.0)
        self.assertEqual(bal(o, "usd")["amount"], 3)

    def test_siliconflow(self):
        o = A.parse_siliconflow({"code": 20000, "status": True, "data": {"totalBalance": "12.34", "chargeBalance": "10",
                                                                         "balance": "2.34", "status": "normal"}}, "USD")
        self.assertEqual(bal(o, "total")["amount"], 12.34)
        self.assertEqual(o["info"], [])
        with self.assertRaises(RuntimeError):
            A.parse_siliconflow({"code": 20092}, "CNY")

    def test_fal(self):
        o = A.parse_fal({"username": "me", "credits": {"current_balance": "42.10", "currency": "USD"}})
        self.assertEqual(bal(o, "credits")["amount"], 42.1)

    def test_exa(self):
        self.assertEqual(bal(A.parse_exa({"total_cost_usd": 1.25, "period": {}}), "month")["kind"], "spent")

    def test_tavily(self):
        o = A.parse_tavily({"account": {"current_plan": "Researcher", "plan_usage": 250, "plan_limit": 1000,
                                        "paygo_usage": 0, "paygo_limit": 0}, "key": {"usage": 10, "limit": None}})
        self.assertEqual(o["plan"], "Researcher")
        self.assertEqual(prim(o)["pct"], 25.0)

    def test_elevenlabs(self):
        o = A.parse_elevenlabs({"tier": "creator", "status": "active", "character_count": 5000, "character_limit": 100000,
                                "next_character_count_reset_unix": 1767225600, "voice_slots_used": 2, "voice_limit": 10})
        self.assertEqual(o["plan"], "Creator")
        self.assertEqual(prim(o)["pct"], 5.0)
        self.assertEqual(len(o["windows"]), 2)

    def test_deepgram(self):
        o = A.parse_deepgram([{"start": "2026-11-01", "end": "2026-11-25", "resolution": {"units": "day", "amount": 1},
                               "results": [{"hours": 1.5, "total_hours": 2, "requests": 10, "tokens_in": 5, "tokens_out": 5},
                                           {"requests": 3, "tts_characters": 100}]}], [{"project_id": "p1", "name": "Main"}])
        self.assertEqual(bal(o, "requests")["amount"], 13)
        self.assertEqual(bal(o, "tts")["amount"], 100)

    def test_huggingface(self):
        o = A.parse_huggingface({"usage": {"inferenceProviders": {"usedNanoUsd": 3e9, "includedNanoUsd": 2e9,
                                                                  "limitNanoUsd": 10e9, "numRequests": 7}}},
                                {"base": 1500, "current": 900, "resetsAt": 1767225600}, {"name": "me", "isPro": True},
                                (1761955200, 1764547200))
        self.assertEqual(o["plan"], "PRO")
        self.assertEqual(prim(o)["pct"], 100.0)
        self.assertEqual(bal(o, "billable")["amount"], 1.0)
        self.assertEqual(len(o["windows"]), 3)

    def test_neuralwatt(self):
        o = A.parse_neuralwatt({"balance": {"credits_remaining_usd": 4.5, "total_credits_usd": 10},
                                "subscription": {"plan": "pro_plan", "kwh_included": 20, "kwh_used": 5,
                                                 "current_period_start": "2026-11-01T00:00:00Z",
                                                 "current_period_end": "2026-12-01T00:00:00Z"},
                                "key": {"allowance": {"limit_usd": 10, "spent_usd": 1, "period": "daily"}}})
        self.assertEqual(prim(o)["pct"], 25.0)
        self.assertEqual(prim(o)["period"], 30 * 86400)
        self.assertEqual(bal(o, "credits")["amount"], 4.5)
        self.assertEqual(o["plan"], "Pro Plan")


class Subs(unittest.TestCase):
    def test_mimo(self):
        o = S.parse_mimo({"object": "token_plan", "plan_code": "pro", "quota": {"total_credits": 1000, "used_credits": 250,
                                                                                 "remaining_credits": 750},
                          "period": {"start_at": "2026-11-01 00:00:00", "end_at": "2026-12-01 00:00:00"}})
        w = prim(o)
        self.assertEqual(w["pct"], 25.0)
        self.assertEqual(w["period"], 30 * 86400)
        self.assertEqual(w["resets"], 1796083200)

    def test_zenmux(self):
        o = S.parse_zenmux({"success": True, "data": {"plan": {"tier": "pro", "expires_at": "2026-12-01T00:00:00Z"},
                                                      "account_status": "healthy",
                                                      "quota_5_hour": {"usage_percentage": 0.4, "max_flows": 100, "used_flows": 40,
                                                                       "remaining_flows": 60, "resets_at": "2026-11-25T15:00:00Z"},
                                                      "quota_7_day": {"usage_percentage": 0.1, "max_flows": 1000, "used_flows": 100,
                                                                      "remaining_flows": 900}}},
                           {"success": True, "data": {"currency": "usd", "total_credits": 12.5}})
        self.assertEqual(prim(o)["pct"], 40.0)
        self.assertEqual(o["plan"], "Pro plan")
        self.assertEqual(bal(o, "payg")["amount"], 12.5)

    def test_clinepass(self):
        o = S.parse_clinepass({"success": True, "data": {"limits": [
            {"type": "five_hour", "percentUsed": 12, "resetsAt": "2026-11-25T15:00:00Z"},
            {"type": "weekly", "percentUsed": 30}, {"type": "monthly", "percentUsed": 140}, {"type": "other", "percentUsed": 1}]}})
        self.assertEqual(len(o["windows"]), 3)
        self.assertEqual(prim(o)["id"], "weekly")
        self.assertEqual(o["windows"][2]["pct"], 100.0)

    def test_devpass(self):
        o = S.parse_devpass({"data": {"devPlan": "pro", "usage": "5.00", "limit": None, "devPlanCreditsUsed": "20",
                                      "devPlanCreditsLimit": "80", "devPlanCreditsRemaining": "60", "devPlanPremiumCreditsUsed": "1",
                                      "devPlanPremiumWeeklyLimit": "4", "devPlanPremiumWeekResetsAt": "2026-11-30T00:00:00Z"}})
        self.assertEqual(o["plan"], "DevPass Pro")
        self.assertEqual(prim(o)["pct"], 25.0)
        self.assertEqual(o["windows"][1]["pct"], 25.0)
        self.assertEqual(S.parse_devpass({"data": {"devPlan": "none", "usage": "1.5", "limit": "10"}})["plan"], "Pay as you go")

    def test_codebuff(self):
        o = S.parse_codebuff({"usage": 300, "quota": 1000, "remainingBalance": 700, "next_quota_reset": "2026-12-01T00:00:00Z",
                              "autoTopupEnabled": False},
                             {"subscription": {"displayName": "Pro", "status": "active"},
                              "rateLimit": {"weeklyUsed": 50, "weeklyLimit": 200, "weeklyResetsAt": 1764547200000}})
        self.assertEqual(o["plan"], "Pro")
        self.assertEqual(prim(o)["pct"], 30.0)
        self.assertEqual(o["windows"][1]["resets"], 1764547200)

    def test_kilo(self):
        o = S.parse_kilo([
            {"result": {"data": {"json": {"creditBlocks": [{"amount_mUsd": 10_000_000, "balance_mUsd": 4_000_000}]}}}},
            {"result": {"data": {"json": {"subscription": {"tier": "tier_49", "currentPeriodUsageUsd": 12,
                                                           "currentPeriodBaseCreditsUsd": 49, "currentPeriodBonusCreditsUsd": 1,
                                                           "nextBillingAt": "2026-12-01T00:00:00Z"}}}}},
            {"error": {"json": {"message": "not found"}}}])
        self.assertEqual(o["plan"], "Pro")
        self.assertEqual(prim(o)["pct"], 24.0)
        self.assertEqual(bal(o, "credits")["amount"], 4.0)

    def test_opencodego(self):
        o = S.parse_opencodego({"usage": {"rolling": {"percent": 12.5, "resetInSec": 600}, "weekly": {"percent": 40},
                                          "monthly": {"percent": 100, "resetAt": "2026-12-01T00:00:00Z"}}}, now=1764000000)
        self.assertEqual(prim(o)["pct"], 12.5)
        self.assertEqual(prim(o)["resets"], 1764000600)
        self.assertEqual(o["windows"][2]["resets"], 1796083200)

    def test_stepfun_windows(self):
        o = S.parse_stepfun({"status": 1, "five_hour_usage_left_rate": 0.75, "weekly_usage_left_rate": "0.9",
                             "five_hour_usage_reset_time": "1764000000", "weekly_usage_reset_time": 1764500000}, "Plus")
        self.assertEqual(o["plan"], "Plus")
        self.assertAlmostEqual(prim(o)["pct"], 25.0)
        self.assertEqual(prim(o)["resets"], 1764000000)

    def test_stepfun_credit(self):
        o = S.parse_stepfun({"status": 1, "five_hour_usage_left_rate": 0, "five_hour_usage_reset_time": "0", "plan_family": 2,
                             "plan_credit_rate_limit": {"subscription_credit_left_rate": 0.5, "credit_buckets": [
                                 {"credit_total": 100, "credit_residual": 80, "next_reset_at": "1764547200"},
                                 {"credit_total": 100, "credit_residual": 40}]}})
        self.assertEqual(len(o["windows"]), 1)
        self.assertAlmostEqual(prim(o)["pct"], 40.0)
        self.assertEqual(prim(o)["resets"], 1764547200)

    def test_alibaba(self):
        inner = {"codingPlanInstanceInfos": [{"planName": "Lite", "codingPlanQuotaInfo": {
            "per5HourUsedQuota": 120, "per5HourTotalQuota": 1200, "per5HourQuotaNextRefreshTime": 1764000000000,
            "perWeekUsedQuota": 900, "perWeekTotalQuota": 9000, "perBillMonthUsedQuota": 1000, "perBillMonthTotalQuota": 18000}}]}
        o = S.parse_alibaba({"code": "200", "data": {"DataV2": json.dumps({"data": inner})}})
        self.assertEqual(o["plan"], "Lite")
        self.assertEqual(prim(o)["pct"], 10.0)
        self.assertEqual(prim(o)["resets"], 1764000000)
        self.assertEqual(len(o["windows"]), 3)
        with self.assertRaises(RuntimeError):
            S.parse_alibaba({"code": "ConsoleNeedLogin", "message": "need login"})


class Web(unittest.TestCase):
    def test_t3chat(self):
        body = "\n".join([json.dumps({"json": {"0": [[0], [None, 0, 0]]}}),
                          json.dumps({"json": [2, 0, [[{"usageFourHourPercentage": 33, "usageMonthPercentage": 5,
                                                         "usageFourHourNextResetAt": 1764000000000, "usageBand": "normal",
                                                         "subscription": {"productName": "t3-pro", "currentPeriodStart": 1761955200,
                                                                          "currentPeriodEnd": 1764547200}}]]]})])
        o = W.parse_t3chat(body)
        self.assertEqual(o["plan"], "T3 Pro")
        self.assertEqual(prim(o)["pct"], 33)
        self.assertEqual(prim(o)["resets"], 1764000000)
        self.assertEqual(o["windows"][1]["period"], 1764547200 - 1761955200)

    def test_zed(self):
        o = W.parse_zed({"plan": "zed_pro", "current_usage": {"edit_predictions": {"used": 50, "limit": "unlimited"},
                                                              "token_spend": {"spend_in_cents": 1250, "limit_in_cents": 5000}}})
        self.assertEqual(o["plan"], "Zed Pro")
        self.assertEqual(prim(o)["pct"], 25.0)
        self.assertEqual(len(o["windows"]), 1)

    def test_abacus(self):
        o = W.parse_abacus({"success": True, "result": {"totalComputePoints": 20000, "computePointsLeft": 15000}},
                           {"success": True, "result": {"nextBillingDate": "2026-12-03T00:00:00Z", "currentTier": "Basic"}})
        self.assertEqual(o["plan"], "Basic")
        self.assertEqual(prim(o)["pct"], 25.0)
        with self.assertRaises(RuntimeError):
            W.parse_abacus({"success": False, "error": "Session expired"})

    def test_qoder(self):
        o = W.parse_qoder({"totalQuota": {"quotaSummary": {"usedValue": 30, "limitValue": 100, "remainingValue": 70}},
                           "sharedQuota": {"quota_summary": {"used_value": 10, "limit_value": 100}},
                           "nextResetAt": 1764547200000})
        self.assertEqual(prim(o)["pct"], 20.0)
        self.assertEqual(bal(o, "left")["amount"], 160)
        self.assertEqual(prim(o)["resets"], 1764547200)

    def test_traecn(self):
        o = W.parse_traecn({"is_credits_billing": True, "usage_summary": {"total_amount": 600, "consumed_amount": 150},
                            "user_entitlement_pack_list": [{"group_type": 0, "status": 1, "display_desc": "Pro"}]})
        self.assertEqual(o["plan"], "Pro")
        self.assertEqual(prim(o)["pct"], 25.0)

    def test_raycast(self):
        o = W.parse_raycast({"remaining_balance_credits": "750", "total_balance_credits": 1000,
                             "next_credits_at": "2026-12-01T00:00:00Z", "funding_subscription": {"tier": "pro_plus"}})
        self.assertEqual(o["plan"], "Pro+")
        self.assertEqual(prim(o)["pct"], 25.0)

    def test_longcat(self):
        acct = W.longcat_unwrap({"code": 0, "data": {"name": "cat"}})
        usage = W.longcat_unwrap({"code": 0, "data": {"usage": {"totalToken": 1000, "usedToken": 100}}})
        fuel = W.longcat_unwrap({"code": 0, "data": {"totalQuota": 500, "list": [
            {"availableToken": 200, "expireTime": "2026-12-01 00:00:00"}, {"availableToken": 100, "expireTime": 1767225600000}]}})
        o = W.parse_longcat(acct, None, usage, fuel)
        self.assertEqual(prim(o)["pct"], 10.0)
        self.assertEqual(o["windows"][1]["pct"], 40.0)
        self.assertEqual(bal(o, "fuel_left")["amount"], 300)
        o2 = W.parse_longcat(acct, {"status": "ACTIVE", "totalToken": 400, "consumedToken": 100})
        self.assertEqual(prim(o2)["pct"], 25.0)
        with self.assertRaises(RuntimeError):
            W.longcat_unwrap({"code": 401})

    def test_langdock(self):
        o = W.parse_langdock([{"result": {"data": {"json": {"hasIncludedUsageLimits": True, "planUsage": {
            "sessionUsageLimitsEnabled": True, "sessionUsagePercent": 12, "sessionResetsAt": "2026-11-25T15:00:00Z",
            "weeklyUsagePercent": 40, "weeklyResetsAt": "2026-11-30T00:00:00Z"}}}}}])
        self.assertEqual(len(o["windows"]), 2)
        self.assertEqual(prim(o)["pct"], 40)
        with self.assertRaises(RuntimeError):
            W.parse_langdock([{"error": {"json": {"data": {"code": "UNAUTHORIZED"}}}}])

    def test_manus(self):
        o = W.parse_manus({"totalCredits": 4300, "freeCredits": 300, "periodicCredits": 3000, "proMonthlyCredits": 4000,
                           "refreshCredits": 200, "maxRefreshCredits": 300, "refreshInterval": "DAILY",
                           "nextRefreshTime": "2026-11-26T00:00:00Z"})
        self.assertEqual(prim(o)["pct"], 25.0)
        self.assertEqual(o["windows"][1]["period"], 86400)
        self.assertEqual(bal(o, "total")["amount"], 4300)
        o2 = W.parse_manus({"data": {"totalCredits": 1, "maxRefreshCredits": 10, "refreshCredits": 5, "nextRefreshTime": 786000000}})
        self.assertEqual(o2["windows"][0]["resets"], 786000000 + 978307200)

    def test_replicate(self):
        html = ('<html><script type="application/json" id="react-component-props-billing">'
                + json.dumps({"props": {"account": {"kind": "organization", "username": "acme"}}}) + '</script></html>')
        self.assertEqual(W.replicate_account(html), ("organization", "acme"))
        o = W.parse_replicate({"invoices": [{"type": "monthly-usage", "ended_before": "2020-01-01T00:00:00Z",
                                             "total_cost_before_adjustments": "1.00"},
                                            {"type": "monthly-usage", "ended_before": None, "total_cost_before_adjustments": "3.25"}]},
                              {"unused_credit": "10.00"}, "acme")
        self.assertEqual(bal(o, "month")["amount"], 3.25)
        self.assertEqual(bal(o, "credit")["amount"], 10.0)
        with self.assertRaises(RuntimeError):
            W.replicate_account("<title>Sign in | Replicate</title>")

    def test_groq(self):
        now = 1764072000  # 2026-11-25 12:00 UTC
        o = W.parse_groq({"data": [{"organization_name": "Acme", "model": "llama", "timestamp": 1763942400, "num_requests": 10,
                                    "n_context_tokens_total": 100, "n_generated_tokens_total": 50, "cost": 0.5},
                                   {"model": "llama", "timestamp": 1764028800, "num_requests": 2, "cost": 0.25}]}, now=now)
        self.assertEqual(bal(o, "month")["amount"], 0.75)
        self.assertEqual(bal(o, "today")["amount"], 0.25)
        import base64
        p = base64.urlsafe_b64encode(json.dumps({"https://groq.com/organization": {"id": "org_1"}}).encode()).decode().rstrip("=")
        self.assertEqual(W.groq_org("h." + p + ".s"), "org_1")


class LiteLLMTest(unittest.TestCase):
    def test_user_key(self):
        o = L.parse_litellm({"user_id": "u1", "team_id": "t1", "key_name": "sk-...abcd", "spend": 1.5},
                            user={"user_id": "u1", "user_info": {"user_id": "u1", "user_email": "a@b.c", "spend": 25,
                                                                 "max_budget": 100, "budget_reset_at": "2026-12-01T00:00:00Z"},
                                  "teams": [{"team_id": "t1", "team_alias": "eng", "spend": 10, "max_budget": 0}]})
        self.assertEqual(prim(o)["pct"], 25.0)
        self.assertEqual(bal(o, "key")["amount"], 1.5)
        self.assertEqual(bal(o, "team")["amount"], 10)

    def test_team_key(self):
        o = L.parse_litellm({"team_id": "t1", "spend": 2}, team={"team_id": "t1", "team_info": {"team_id": "t1", "team_alias": "eng",
                                                                                                 "spend": 50, "max_budget": 200}})
        self.assertEqual(prim(o)["label"], "Team eng")
        self.assertEqual(prim(o)["pct"], 25.0)

    def test_spend_report(self):
        o = L.parse_spend_report([{"total_cost": 1.0}, {"total_cost": 2.5}], "Key")
        self.assertEqual(o["balances"][0]["amount"], 3.5)

    def test_base(self):
        self.assertEqual(L._base("http://10.0.0.5:4000/v1/"), "http://10.0.0.5:4000")


class WindsurfTest(unittest.TestCase):
    @staticmethod
    def ld(num, payload):
        return WS.varint((num << 3) | 2) + WS.varint(len(payload)) + payload

    @staticmethod
    def vi(num, v):
        return WS.varint(num << 3) + WS.varint(v)

    def test_roundtrip(self):
        req = WS.encode_request("tok")
        self.assertEqual(list(WS.fields(req)), [(1, 2, b"tok"), (2, 0, 1)])
        info = self.vi(1, 2) + self.ld(2, b"Pro")
        ps = (self.ld(1, info) + self.ld(3, self.vi(1, 1767225600)) + self.vi(14, 70) + self.vi(15, 40)
              + self.vi(17, 1764100000) + self.vi(18, 1764500000) + self.ld(99, b"\x01\x02"))
        o = WS.parse_windsurf(self.ld(1, ps))
        self.assertEqual(o["plan"], "Pro")
        self.assertEqual(o["windows"][0]["pct"], 30)
        self.assertEqual(prim(o)["pct"], 60)
        self.assertEqual(prim(o)["resets"], 1764500000)
        self.assertEqual(o["info"][0]["value"], "2026-01-01")

    def test_bundle(self):
        b = WS.parse_bundle(json.dumps({"devin_session_token": "s", "devin_auth1_token": "a", "devin_account_id": "acc",
                                        "devin_primary_org_id": "org"}))
        self.assertEqual(b, {"session": "s", "auth1": "a", "account": "acc", "org": "org"})
        self.assertEqual(WS.parse_bundle("devin_session_token=s\ndevin_auth1_token=a\ndevin_account_id=acc\n"
                                         "devin_primary_org_id=org")["org"], "org")
        with self.assertRaises(ValueError):
            WS.parse_bundle('{"devin_session_token": "s"}')

    def test_truncated(self):
        with self.assertRaises(ValueError):
            list(WS.fields(b"\x0a\x05ab"))


if __name__ == "__main__":
    unittest.main()
