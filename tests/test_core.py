"""Parser and engine tests with sample responses (no network)."""
import json, os, tempfile, time, unittest

os.environ["BURNRATE_DATA"] = tempfile.mkdtemp(prefix="burnrate-test-")
from burnrate import core, engine  # noqa: E402
from burnrate.providers import REGISTRY, claude, chatgpt, copilot, cursor, gemini, zai, kimi, minimax, devtools, mistral  # noqa: E402
from burnrate.providers.base import OAuthPaste  # noqa: E402

NOW = int(time.time())


class Parsers(unittest.TestCase):
    def test_claude(self):
        d = {"five_hour": None, "seven_day": {"utilization": 44, "resets_at": "2026-11-24T06:00:00Z"},
             "seven_day_breakdown": {"window_started_at": "2026-11-17T06:00:00Z", "rows": [
                 {"key": "claude_code", "display_name": "Claude Code", "percent_of_limit": 40}]},
             "extra_usage": {"is_enabled": False, "monthly_limit": 2000, "used_credits": 0, "currency": "EUR", "decimal_places": 2}}
        s = claude.parse(d)
        w = s["windows"][0]
        self.assertEqual((w["id"], w["pct"], w["period"], w["primary"]), ("week", 44, 7 * 86400, True))
        self.assertEqual(s["balances"][0]["limit"], 20.0)
        self.assertEqual(s["breakdown"]["rows"][0]["pct"], 40)

    def test_claude_plan(self):
        self.assertEqual(claude.plan_of({"organization": {"plan_display_name": "Ultra", "rate_limit_tier": "default_claude_max_20x"}})[0], "Ultra")
        self.assertEqual(claude.plan_of({"organization": {"plan_display_label": "Ultra plan"}})[0], "Ultra")
        self.assertEqual(claude.plan_of({"organization": {"organization_type": "claude_max", "rate_limit_tier": "default_claude_max_5x"}})[0], "Max 5x")
        self.assertEqual(claude.plan_of({"account": {"has_claude_pro": True}, "organization": {}})[0], "Pro")

    def test_chatgpt(self):
        d = {"plan_type": "plus", "rate_limit": {
            "primary_window": {"used_percent": 12, "reset_at": NOW + 3600, "limit_window_seconds": 18000},
            "secondary_window": {"used_percent": 40, "reset_at": NOW + 86400, "limit_window_seconds": 604800}},
            "credits": {"has_credits": True, "unlimited": False, "balance": "5"}}
        s = chatgpt.parse(d)
        self.assertEqual(s["plan"], "Plus")
        for raw, name in (("prolite", "Pro 100"), ("pro", "Pro 200"), ("pro_max", "Pro 500")):
            self.assertEqual(chatgpt.parse(dict(d, plan_type=raw))["plan"], name)
        wk = [w for w in s["windows"] if w["primary"]]
        self.assertEqual((len(wk), wk[0]["label"], wk[0]["pct"]), (1, "Weekly", 40))
        self.assertEqual(s["balances"][0]["amount"], 5)

    def test_chatgpt_account_id(self):
        import base64
        payload = base64.urlsafe_b64encode(json.dumps({"https://api.openai.com/auth": {"chatgpt_account_id": "acc-1"}}).encode()).decode().rstrip("=")
        self.assertEqual(chatgpt.account_id({"id_token": "x." + payload + ".y"}), "acc-1")

    def test_copilot(self):
        s = copilot.parse({"copilot_plan": "individual", "quota_reset_date": "2026-12-01", "quota_snapshots": {
            "premium_interactions": {"entitlement": 300, "remaining": 210, "percent_remaining": 70, "unlimited": False},
            "chat": {"unlimited": True}}})
        self.assertEqual(len(s["windows"]), 1)
        self.assertEqual((s["windows"][0]["pct"], s["windows"][0]["used"]), (30, 90))
        self.assertEqual(copilot.parse({"copilot_plan": "individual", "access_type_sku": "free_educational_quota"})["plan"], "Education")
        self.assertEqual(copilot.plan_name({"copilot_plan": "individual", "access_type_sku": "monthly_subscriber_quota"}), "Pro")
        self.assertEqual(copilot.plan_name({"copilot_plan": "individual", "access_type_sku": "free_limited_copilot"}), "Free")
        self.assertEqual(copilot.plan_name({"copilot_plan": "business"}), "Business")
        free = copilot.parse({"monthly_quotas": {"chat": 50, "completions": 2000}, "limited_user_quotas": {"chat": 40, "completions": 1500}})
        self.assertEqual(free["windows"][0]["pct"], 20)

    def test_cursor(self):
        s = cursor.parse({"billingCycleStart": "2026-11-01T00:00:00Z", "billingCycleEnd": "2026-12-01T00:00:00Z", "membershipType": "pro",
                          "individualUsage": {"plan": {"used": 1240, "limit": 2000, "totalPercentUsed": 62.0}, "onDemand": {"used": 150, "limit": 1000}}})
        self.assertEqual((s["windows"][0]["pct"], s["windows"][0]["limit"]), (62.0, 20.0))
        self.assertEqual(s["balances"][0]["amount"], 1.5)
        self.assertTrue(cursor.cookie("abc|user_1::jwt").startswith("WorkosCursorSessionToken="))

    def test_gemini(self):
        s = gemini.parse({"buckets": [{"modelId": "gemini-2.5-pro", "tokenType": "REQUESTS", "remainingFraction": 0.8, "resetTime": "2026-11-26T00:00:00Z"},
                                      {"modelId": "gemini-2.5-flash", "tokenType": "REQUESTS", "remainingFraction": 0.5}]})
        self.assertAlmostEqual(s["windows"][0]["pct"], 20)
        self.assertTrue(s["windows"][0]["primary"])

    def test_zai(self):
        s = zai.parse({"planName": "Pro", "limits": [
            {"type": "TOKENS_LIMIT", "unit": 3, "number": 5, "percentage": 30, "nextResetTime": (NOW + 3600) * 1000},
            {"type": "TOKENS_LIMIT", "unit": 6, "number": 1, "percentage": 10},
            {"type": "TIME_LIMIT", "unit": 5, "number": 1, "currentValue": 20, "usage": 100}]})
        self.assertEqual([w["label"] for w in s["windows"]], ["5-hour", "Weekly", "Tool calls (monthly)"])
        self.assertTrue(s["windows"][1]["primary"])
        self.assertEqual(s["windows"][2]["pct"], 20)
        self.assertEqual(s["windows"][0]["resets"], NOW + 3600)

    def test_kimi(self):
        s = kimi.parse({"limit_5h": {"used_ratio": 0.25, "reset_time": "2026-11-25T10:00:00Z"}, "limit_7d": {"used_ratio": 0.5}, "level": "LEVEL_BASIC"})
        self.assertEqual((s["plan"], s["windows"][1]["pct"], s["windows"][1]["primary"]), ("Basic", 50, True))
        old = kimi.parse({"usage": {"limit": "100", "used": "25", "resetTime": "2026-11-30T00:00:00Z"}})
        self.assertEqual(old["windows"][0]["pct"], 25)

    def test_minimax(self):
        s = minimax.parse({"model_remains": [{"model_name": "MiniMax-M2", "current_interval_total_count": 100,
                                              "current_interval_usage_count": 70, "start_time": NOW * 1000, "end_time": (NOW + 18000) * 1000}]})
        self.assertAlmostEqual(s["windows"][0]["pct"], 30)     # usage_count means remaining
        self.assertEqual(s["windows"][0]["period"], 18000)

    def test_amp(self):
        s = devtools.parse_amp("Amp Free: $7.50 / $10 remaining (replenishes +$0.42 / hour)\nIndividual credits: $3.20 remaining")
        self.assertAlmostEqual(s["windows"][0]["pct"], 25)
        self.assertEqual(s["balances"][0]["amount"], 3.2)

    def test_mistral_flight(self):
        inner = json.dumps(["$", "div", None, {"budget": {"api_budget": {"usage_percentage": 12.5, "initial_budget": 20, "currency": "eur",
                                                                         "reset_at": "2026-12-01T00:00:00Z"}}}])
        html = '<script>self.__next_f.push(' + json.dumps([1, "5:" + inner + "\n"]) + ')</script>'
        self.assertEqual(mistral.flight_budget(html)["api_budget"]["usage_percentage"], 12.5)
        page = '<script>self.__next_f.push(' + json.dumps([1, '7:{"chatPlan":"EDU","activeCodePlan":null,"active_api_plan":"FREE"}\n']) + ')</script>'
        self.assertEqual(mistral.flight_plans(page), {"chat": "EDU", "api": "FREE"})
        self.assertEqual(mistral.plan_label("EDU"), "Education")

    def test_mistral_api_key(self):
        from unittest import mock
        from burnrate.providers.base import Account
        answers = {
            "/billing/subscription": {"enterprise": False, "payg_enabled": False, "plan_name": "EDU", "vibe_payg_enabled": True},
            "/billing/budget": {"api_budget": {"usage_percentage": 1.0, "initial_budget": 12.75, "currency": "EUR",
                                               "reset_at": "2026-12-01T00:00:00Z"},
                                "vibe_budget": {"usage_percentage": 7.4, "initial_budget": 127.5, "currency": "EUR",
                                                "reset_at": "2026-12-01T00:00:00Z", "payg_enabled": True}},
            "/api/vibe/whoami": {"plan_type": "chat", "plan_name": "EDU", "organization_kind": "personal"},
        }

        def fake(method, url, headers=None, **kw):
            self.assertEqual(headers["Authorization"], "Bearer k1")
            for k, v in answers.items():
                if url.endswith(k):
                    return v
            raise core.HttpError(404, "", url)
        acct = Account({"id": 1, "label": "m", "options": "{}"}, {"key": "k1", "_auth": "key"})
        with mock.patch.object(core, "http", side_effect=fake):
            out = REGISTRY["mistral"].fetch(acct)
        self.assertEqual(out["plan"], "Education")
        w = {x["id"]: x for x in out["windows"]}
        self.assertTrue(w["vibe_budget"]["primary"])
        self.assertAlmostEqual(w["vibe_budget"]["used"], 127.5 * 7.4 / 100)
        self.assertEqual(w["api_budget"]["limit"], 12.75)
        self.assertIn({"label": "Key", "value": "Vibe plan key"}, out["info"])
        answers.pop("/billing/budget")
        answers["/billing/subscription"]["plan_name"] = "INDIVIDUAL"
        with mock.patch.object(core, "http", side_effect=fake):
            out = REGISTRY["mistral"].fetch(acct)
        self.assertEqual(out["plan"], "Pro")

    def test_paste_parsing(self):
        self.assertEqual(OAuthPaste.parse_paste("abc#st"), ("abc", "st"))
        self.assertEqual(OAuthPaste.parse_paste("http://127.0.0.1:1455/auth/callback?code=xyz&state=s1"), ("xyz", "s1"))
        self.assertEqual(OAuthPaste.parse_paste("4/0Abc"), ("4/0Abc", None))

    def test_registry(self):
        for p in REGISTRY.values():
            d = p.describe()
            self.assertTrue(d["auths"], p.id)
            self.assertIn(d["category"], ("subscription", "api", "credits"), p.id)
        self.assertGreaterEqual(len(REGISTRY), 20)

    def test_redact(self):
        self.assertNotIn("sk-abcdefghijklmnop", core.redact("Bearer sk-abcdefghijklmnop failed"))


class Engine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core.init()
        core.set_setting("timezone", "UTC")
        with core.db() as c:
            cls.aid = c.execute("INSERT INTO accounts(provider,label,options) VALUES('claude','t','{}')").lastrowid
        reset = NOW + 2 * 86400
        # 5 days of samples, 1 % every daytime hour
        v = 0.0
        for i in range(5 * 24 * 12, -1, -1):
            ts = NOW - i * 300
            if i % 12 == 0 and 8 <= time.gmtime(ts).tm_hour < 20:
                v += 1
            engine.store(cls.aid, {"windows": [{"id": "week", "label": "Weekly", "pct": v, "resets": reset, "period": 7 * 86400,
                                                "primary": True}]}, ts)

    def test_view_and_forecast(self):
        v = engine.account_view(engine.account(self.aid), full=True)
        w = v["windows"][0]
        self.assertIn(w["pct"], (60, 61))                                 # 5 days x 12 daytime hours, +1 by clock time
        self.assertIn(w["level"], ("good", "warn", "crit"))
        fc = w["forecast"]
        self.assertIsNotNone(fc)
        self.assertGreaterEqual(fc["days"], 4)
        self.assertAlmostEqual(fc["typical_total"], 12, delta=1.5)        # 12 active hours x 1 %
        self.assertTrue(80 <= fc["p50"] <= 90)                           # ~2 more days of ~12 %
        self.assertLessEqual(fc["p10"], fc["p50"])
        self.assertLessEqual(fc["p50"], fc["p90"])
        self.assertEqual(len(v["hourly"]), 48)
        self.assertEqual(len(v["daily"]), 30)

    def test_rolled_window(self):
        a = engine.account(self.aid)
        later = NOW + 3 * 86400
        v = engine.account_view(a, now=later)
        self.assertEqual(v["windows"][0]["pct"], 0.0)
        self.assertGreater(v["windows"][0]["resets"], later)

    def test_spend_deltas(self):
        rows = [(1, 10.0, None), (2, 9.0, None), (3, 12.0, None), (4, 11.5, None)]
        self.assertEqual([d for _, d in engine.spend_deltas(rows, "remaining")], [1.0, 0.0, 0.5])
        rows = [(1, 1.0, None), (2, 3.0, None), (3, 0.5, None)]
        self.assertEqual([d for _, d in engine.spend_deltas(rows, "spent")], [2.0, 0.5])

    def test_verdict(self):
        self.assertEqual(engine.verdict(44, 3)[0], "Slightly ahead of pace")
        self.assertEqual(engine.verdict(100, 0)[0], "Limit reached")
        self.assertEqual(engine.verdict(10, -30)[0], "Well under pace")


if __name__ == "__main__":
    unittest.main()
