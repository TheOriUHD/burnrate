"""MiniMax Coding / Token Plan: prompts left in the current window and this week, per model group."""
from .. import core
from .base import Provider, Fields, Field, window, balance

BASE = {"global": "https://api.minimax.io", "cn": "https://api.minimaxi.com"}


class MiniMax(Provider):
    id = "minimax"
    name = "MiniMax Coding Plan"
    vendor = "MiniMax"
    color = "#e2443b"
    mono = "MM"
    blurb = "Coding/token plan: current window and weekly quota"
    options = [Field("region", "Region", "select", options=[["global", "Global (minimax.io)"], ["cn", "China (minimaxi.com)"]], default="global")]
    auths = [Fields([Field("key", "Coding plan key", "secret", "sk-cp-…")])]

    def fetch(self, acct):
        base = BASE.get(acct.options.get("region"), BASE["global"])
        try:
            d = self.get(acct, base + "/v1/token_plan/remains")
        except core.HttpError as e:
            if e.code != 404:
                raise
            d = self.get(acct, base + "/v1/api/openplatform/coding_plan/remains")
        br = d.get("base_resp") or {}
        if br.get("status_code") not in (None, 0):
            raise RuntimeError(f"MiniMax: {br.get('status_msg') or br.get('status_code')}")
        return parse(d.get("data") or d)


def _pct(m, used_pct, rem_pct, total, remaining):
    if m.get(used_pct) is not None:
        return core.num(m[used_pct])
    if m.get(rem_pct) is not None:
        return 100 - core.num(m[rem_pct])
    t, r = core.num(m.get(total)), core.num(m.get(remaining))
    return 100 * (t - r) / t if t else None


def parse(d):
    wins = []
    for i, m in enumerate(d.get("model_remains") or []):
        name = m.get("model_name") or f"model {i + 1}"
        s, e = core.iso_ts(m.get("start_time")), core.iso_ts(m.get("end_time"))
        p = _pct(m, "current_interval_used_percent", "current_interval_remaining_percent",
                 "current_interval_total_count", "current_interval_usage_count")   # usage_count = remaining (sic)
        if p is not None:
            t, r = core.num(m.get("current_interval_total_count")), core.num(m.get("current_interval_usage_count"))
            wins.append(window(f"{name}_interval", f"{name} · window", p, used=(t - r) if t and r is not None else None,
                               limit=t, unit="prompts", resets=e, period=(e - s) if s and e else None))
        ws, we = core.iso_ts(m.get("weekly_start_time")), core.iso_ts(m.get("weekly_end_time"))
        wp = _pct(m, "current_weekly_used_percent", "current_weekly_remaining_percent",
                  "current_weekly_total_count", "current_weekly_usage_count")
        if wp is not None:
            wins.append(window(f"{name}_weekly", f"{name} · weekly", wp, resets=we, period=(we - ws) if ws and we else 7 * 86400,
                               primary=i == 0))
    if wins and not any(w["primary"] for w in wins):
        wins[0]["primary"] = True
    bals = [balance("points", "Points", d["points_balance"], "points")] if d.get("points_balance") is not None else []
    return {"plan": d.get("current_subscribe_title") or d.get("plan_name"), "windows": wins, "balances": bals}
