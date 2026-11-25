"""Seed a data directory with made-up accounts and 3 weeks of history (for trying the UI and for screenshots)."""
import math, random, time
from . import core, engine

ACCOUNTS = [  # provider, label, plan, windows [(id, label, period_s, primary, daily %)], balances
    ("claude", "Claude", "Max", [("week", "Weekly", 7 * 86400, True, 11.5), ("session", "5-hour session", 5 * 3600, False, 0)], []),
    ("chatgpt", "ChatGPT", "Pro", [("secondary", "Weekly", 7 * 86400, True, 9.0), ("primary", "5-hour", 5 * 3600, False, 0)], []),
    ("copilot", "Copilot", "Pro", [("premium_interactions", "Premium requests", 30 * 86400, True, 2.6)], []),
    ("cursor", "Cursor", "Pro", [("plan", "Included usage", 30 * 86400, True, 3.4)], [("ondemand", "On-demand", "USD", "spent", 0.4, 20)]),
    ("zai", "GLM Coding Plan", "Pro", [("tokens_limit_604800", "Weekly", 7 * 86400, True, 15.5), ("tokens_limit_18000", "5-hour", 5 * 3600, False, 0)], []),
    ("openrouter", "OpenRouter", None, [], [("credits", "Credits", "USD", "remaining", 1.8, None)]),
    ("deepseek", "DeepSeek", None, [], [("total_usd", "Balance (USD)", "USD", "remaining", 0.35, None)]),
]


def run(days=21, seed=7):
    core.init()
    with core.db() as c:
        if c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:
            raise SystemExit("this data directory already has accounts; use an empty BURNRATE_DATA for the demo")
    rnd = random.Random(seed)
    now = core.now()
    start = now - days * 86400
    for i, (prov, label, plan, wins, bals) in enumerate(ACCOUNTS):
        with core.db() as c:
            aid = c.execute("INSERT INTO accounts(provider,label,options,enabled,sort,created) VALUES(?,?,?,?,?,?)",
                            (prov, label, "{}", 1, i, start)).lastrowid
        core.save_creds(aid, {"demo": True})
        state = {w[0]: 0.0 for w in wins}
        money = {b[0]: (40.0 if b[3] == "remaining" else 0.0) for b in bals}
        resets = {w[0]: start + rnd.randint(1, w[2]) for w in wins}
        for ts in range(start, now + 1, 600):
            lt = time.localtime(ts)
            busy = (9 <= lt.tm_hour < 13 or 14 <= lt.tm_hour < 19 or (lt.tm_wday < 5 and 21 <= lt.tm_hour < 23))
            weekend = lt.tm_wday >= 5
            snap = {"plan": plan, "windows": [], "balances": []}
            for wid, wl, per, prim, daily in wins:
                while ts >= resets[wid]:
                    resets[wid] += per
                    state[wid] = 0.0
                rate = daily / 11 / 6 if daily else 1.4                               # % per busy 10 min
                if busy and rnd.random() < (0.35 if weekend else 0.6):
                    state[wid] = min(100.0, state[wid] + rate * rnd.uniform(0.5, 2.6) * (0.6 if weekend else 1))
                snap["windows"].append({"id": wid, "label": wl, "pct": round(state[wid]), "used": None, "limit": None, "unit": None,
                                        "resets": resets[wid], "period": per, "primary": prim, "note": None})
            for bid, bl, cur, kind, daily, lim in bals:
                if busy and rnd.random() < 0.5:
                    d = daily / 11 / 6 * rnd.uniform(0.3, 2.2)
                    money[bid] += -d if kind == "remaining" else d
                    if kind == "remaining" and money[bid] < 5:
                        money[bid] += 50                                            # top-up
                snap["balances"].append({"id": bid, "label": bl, "amount": round(money[bid], 2), "currency": cur,
                                         "limit": lim, "kind": kind, "note": None})
            engine.store(aid, snap, ts)
    core.set_setting("primary_account", 1)
    core.set_setting("demo", True)          # the poller leaves demo accounts alone
    print(f"demo data written to {core.DATA}: {len(ACCOUNTS)} accounts, {days} days")
