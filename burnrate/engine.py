"""Polling, history and analysis (pace verdicts, pattern forecasts, spend runway) for every account."""
import json, random, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from . import core
from .providers import REGISTRY
from .providers.base import Account

status = {}            # account id -> {last_ok, last_try, error, error_at, fails, next}
wake = threading.Event()
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="poll")
_busy = set()
_busy_lock = threading.Lock()


# ---------------------------------------------------------------- accounts
def accounts(enabled_only=False):
    with core.db() as c:
        q = "SELECT * FROM accounts" + (" WHERE enabled=1" if enabled_only else "") + " ORDER BY sort, id"
        return [dict(r) for r in c.execute(q)]


def account(aid):
    with core.db() as c:
        r = c.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
    return dict(r) if r else None


def st(aid):
    return status.setdefault(aid, {"last_ok": None, "last_try": None, "error": None, "error_at": None, "fails": 0,
                                   "next": 0})


def load_status():
    with core.db() as c:
        for r in c.execute("SELECT account, MAX(ts) t FROM snapshots GROUP BY account"):
            st(r["account"])["last_ok"] = r["t"]
        for r in c.execute("SELECT account, ts, msg FROM errors e WHERE ts=(SELECT MAX(ts) FROM errors WHERE account=e.account)"):
            s = st(r["account"])
            if not s["last_ok"] or r["ts"] > s["last_ok"]:
                s.update(error=r["msg"], error_at=r["ts"])


def log_error(aid, msg):
    msg = core.redact(msg)[:600]
    s = st(aid)
    s.update(error=msg, error_at=core.now(), fails=s["fails"] + 1)
    with core.db() as c:
        c.execute("INSERT INTO errors VALUES(?,?,?)", (aid, core.now(), msg))
        c.execute("DELETE FROM errors WHERE ts < ?", (core.now() - 30 * 86400,))
    core.log(f"account {aid}: {msg}")


# ---------------------------------------------------------------- polling
def store(aid, snap, ts=None):
    ts = ts or core.now()
    pts = []
    for w in snap.get("windows") or []:
        if w.get("pct") is not None:
            pts.append((aid, ts, "w:" + w["id"], w["pct"], w.get("resets")))
    for b in snap.get("balances") or []:
        if b.get("amount") is not None:
            pts.append((aid, ts, "b:" + b["id"], b["amount"], None))
    br = snap.get("breakdown") or {}
    reset = next((w.get("resets") for w in snap.get("windows") or [] if w["id"] == br.get("window")), None)
    for r in br.get("rows") or []:
        pts.append((aid, ts, "s:" + r["key"], r["pct"], reset))
    with core.db() as c:
        c.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?)", (aid, ts, json.dumps(snap)))
        c.executemany("INSERT INTO points VALUES(?,?,?,?,?)", pts)


def poll(aid):
    with _busy_lock:
        if aid in _busy:
            return
        _busy.add(aid)
    s = st(aid)
    s["last_try"] = core.now()
    try:
        row = account(aid)
        if not row:
            return
        prov = REGISTRY.get(row["provider"])
        if not prov:
            raise RuntimeError(f"unknown provider {row['provider']!r} (removed in this version?)")
        cr = core.creds(aid)
        if not cr:
            raise RuntimeError("not signed in: open Settings and connect this account")
        snap = prov.fetch(Account(row, cr))
        if not isinstance(snap, dict) or not (snap.get("windows") or snap.get("balances")):
            raise RuntimeError("the provider answered, but without any limit or balance (format changed?)")
        store(aid, snap)
        s.update(last_ok=core.now(), error=None, fails=0)
    except Exception as e:
        log_error(aid, f"{type(e).__name__}: {e}" if not isinstance(e, RuntimeError) else str(e))
        if not isinstance(e, (RuntimeError, core.HttpError, OSError, ValueError, KeyError)):
            traceback.print_exc()
    finally:
        base = row.get("interval") if row and row.get("interval") else core.setting("interval")
        s["next"] = core.now() + int(base) * (min(2 ** s["fails"], 12) if s["fails"] else 1)
        with _busy_lock:
            _busy.discard(aid)


def poll_now(aid):
    """Poll right away (blocking, used after connecting an account)."""
    st(aid)["next"] = 0
    poll(aid)


def poller():
    last_prune = 0
    while True:
        try:
            for a in ([] if core.setting("demo") else accounts(enabled_only=True)):
                if st(a["id"])["next"] <= core.now() and a["id"] not in _busy:
                    _pool.submit(poll, a["id"])
            if time.time() - last_prune > 6 * 3600:
                prune()
                last_prune = time.time()
        except Exception:
            traceback.print_exc()
        wake.wait(15)
        wake.clear()


def prune():
    keep = int(core.setting("retention_days") or 400) * 86400
    with core.db() as c:
        c.execute("DELETE FROM points WHERE ts < ?", (core.now() - keep,))
        # full snapshots only for 14 days (the latest per account always stays)
        c.execute("DELETE FROM snapshots WHERE ts < ? AND ts NOT IN (SELECT MAX(ts) FROM snapshots GROUP BY account)",
                  (core.now() - 14 * 86400,))


# ---------------------------------------------------------------- analysis
def verdict(used, diff):
    """Graded pace text (diff = used % minus elapsed % of the window) and a level good|warn|crit."""
    if used >= 100:
        return "Limit reached", "crit"
    if diff > 25 or used >= 90:
        return "Running hot", "crit"
    for lo, text, lvl in ((15, "Well ahead of pace", "warn"), (5, "Ahead of pace", "warn"),
                          (1.5, "Slightly ahead of pace", "good"), (-1.5, "Right on pace", "good"),
                          (-5, "Slightly under pace", "good"), (-15, "Under pace", "good")):
        if diff > lo:
            return text, lvl
    return "Well under pace", "good"


def series(aid, key, since):
    with core.db() as c:
        return [(r["ts"], r["value"], r["reset"]) for r in c.execute(
            "SELECT ts, value, reset FROM points WHERE account=? AND key=? AND ts>? ORDER BY ts", (aid, key, since))]


def hour_key(ts, z):
    return int(datetime.fromtimestamp(ts, z).replace(minute=0, second=0, microsecond=0).timestamp())


def window_deltas(rows):
    """[(ts, value, reset)] -> [(ts, used since previous sample)], counting a reset as the new value."""
    out, prev = [], None
    for ts, v, reset in rows:
        if prev is not None:
            pr = prev[2]
            is_reset = (reset and pr and abs(reset - pr) > 3600) or (v < prev[1] - 0.5 and not (reset and pr))
            out.append((ts, v if is_reset else max(0.0, v - prev[1])))
        prev = (ts, v, reset)
    return out


def spend_deltas(rows, kind):
    """Money used between samples. remaining: drops count (top-ups ignored); spent: rises count, a drop = new cycle."""
    out, prev = [], None
    for ts, v, _ in rows:
        if prev is not None:
            if kind == "remaining":
                d = max(0.0, prev - v)
            else:
                d = v - prev if v >= prev else v
            out.append((ts, d))
        prev = v
    return out


def coverage(aid, since, z):
    with core.db() as c:
        return {hour_key(r["ts"], z) for r in c.execute("SELECT ts FROM snapshots WHERE account=? AND ts>?", (aid, since))} | \
            {hour_key(r["ts"], z) for r in c.execute("SELECT DISTINCT ts FROM points WHERE account=? AND ts>?", (aid, since))}


def bucket_hours(deltas, z):
    h = {}
    for ts, v in deltas:
        if v > 0:
            k = hour_key(ts, z)
            h[k] = h.get(k, 0) + v
    return h


FC_RUNS, FC_HALF_LIFE = 400, 10


def forecast(hourly, covered, now, used, reset, z):
    """Replay recorded days hour by hour (recency- and weekday-weighted) FC_RUNS times until the reset.
    Returns median/10-90 % band at the reset, the chance of reaching 100 % and when; None without a full past day."""
    today = datetime.fromtimestamp(now, z).date()
    count = {}
    for k in covered:
        d = datetime.fromtimestamp(k, z).date()
        if d < today and (today - d).days <= 42:
            count[d] = count.get(d, 0) + 1
    days = sorted(d for d, n in count.items() if n >= 20)
    if not days or not reset or reset <= now:
        return None
    prof = {d: [hourly.get(int(datetime(d.year, d.month, d.day, h, tzinfo=z).timestamp()), 0) for h in range(24)]
            for d in days}
    slots = []
    t = datetime.fromtimestamp(now, z).replace(minute=0, second=0, microsecond=0)
    while t.timestamp() < reset and len(slots) < 24 * 62:
        a, b = max(t.timestamp(), now), min((t + timedelta(hours=1)).timestamp(), reset)
        slots.append((t.date(), t.hour, max(0.0, (b - a) / 3600), int(b)))
        t += timedelta(hours=1)
    targets = sorted({s[0] for s in slots})
    weights = {}
    for td in targets:
        weights[td] = [0.5 ** ((today - d).days / FC_HALF_LIFE) *
                       (3 if d.weekday() == td.weekday() else 1.5 if (d.weekday() >= 5) == (td.weekday() >= 5) else 1)
                       for d in days]
    rng = random.Random(now // 3600)
    curves, hits = [], []
    for _ in range(FC_RUNS):
        pick = {td: prof[rng.choices(days, weights[td])[0]] for td in targets}
        v, hit, cur = used, None, []
        for d, h, frac, end in slots:
            v += pick[d][h] * frac
            if hit is None and v >= 100:
                hit = end
            cur.append(v)
        curves.append(cur)
        hits.append(hit)
    n = FC_RUNS
    q = lambda vals, p: vals[min(n - 1, int(p * n))]
    step = max(1, len(slots) // 200)
    curve = []
    for i in list(range(0, len(slots), step)) + ([len(slots) - 1] if (len(slots) - 1) % step else []):
        col = sorted(c[i] for c in curves)
        curve.append([slots[i][3], round(q(col, .1), 2), round(q(col, .5), 2), round(q(col, .9), 2)])
    ends = sorted(c[-1] for c in curves)
    hit_ts = sorted(h for h in hits if h is not None)
    prob = len(hit_ts) / n
    typical = [round(sum(prof[d][h] for d in days) / len(days), 3) for h in range(24)]
    return {"p10": round(q(ends, .1), 2), "p50": round(q(ends, .5), 2), "p90": round(q(ends, .9), 2),
            "hit_prob": prob, "hit_at": hit_ts[len(hit_ts) // 2] if prob >= .5 else None,
            "hit_early": hit_ts[int(len(hit_ts) * .2)] if hit_ts else None, "days": len(days),
            "curve": curve, "typical_day": typical, "typical_total": round(sum(typical), 2)}


def latest(aid):
    with core.db() as c:
        r = c.execute("SELECT ts, data FROM snapshots WHERE account=? ORDER BY ts DESC LIMIT 1", (aid,)).fetchone()
    return (r["ts"], json.loads(r["data"])) if r else (None, None)


def analyse_window(w, now, aid=None, z=None, full=False):
    out = dict(w)
    if w.get("pct") is None:
        return out
    used = w["pct"]
    if w.get("resets") and w.get("period"):
        start = w["resets"] - w["period"]
        el = min(max((now - start) / w["period"], 0), 1) * 100
        out.update(start=start, elapsed=round(el, 2), diff=round(used - el, 2))
        out["state"], out["level"] = verdict(used, used - el)
        out["projected"] = round(used / (el / 100), 1) if el > 2 else None
        out["per_day_left"] = max(100 - used, 0) / max((w["resets"] - now) / 86400, 0.01) if w["period"] >= 86400 else None
    else:
        out["level"] = "crit" if used >= 100 else "crit" if used >= 90 else "warn" if used >= 75 else "good"
        out["state"] = "Limit reached" if used >= 100 else f"{round(used)} % used"
    if aid is not None:
        rows = series(aid, "w:" + w["id"], now - 43 * 86400)
        d = window_deltas(rows)
        hourly = bucket_hours(d, z)
        t0 = datetime.fromtimestamp(now, z).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        out["today"] = round(sum(v for ts, v in d if ts >= t0), 3)
        out["spark"] = [round(hourly.get(hour_key(now - i * 3600, z), 0), 3) for i in range(23, -1, -1)]
        if w.get("resets") and w.get("period") and w["period"] >= 86400 and used < 100 and w.get("note") != "inactive":
            fc = forecast(hourly, coverage(aid, now - 43 * 86400, z), now, used, w["resets"], z)
            out["forecast"] = fc if full else ({k: v for k, v in fc.items() if k not in ("curve", "typical_day")} if fc else None)
            if fc:
                out["projected_linear"] = out.get("projected")
                out["projected"] = fc["p50"]
        if full:
            out["burn"] = [[ts, v] for ts, v, r in rows if out.get("start") and ts >= out["start"]]
    return out


def analyse_balance(b, now, aid, z):
    out = dict(b)
    rows = series(aid, "b:" + b["id"], now - 31 * 86400)
    d = spend_deltas(rows, b.get("kind") or "remaining")
    t0 = datetime.fromtimestamp(now, z).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    out["today"] = round(sum(v for ts, v in d if ts >= t0), 4)
    week = [v for ts, v in d if ts >= now - 7 * 86400]
    span = min(7, max((now - rows[0][0]) / 86400, 0)) if rows else 0
    out["per_day"] = round(sum(week) / span, 4) if span >= 0.5 else None
    hourly = bucket_hours(d, z)
    out["spark"] = [round(hourly.get(hour_key(now - i * 3600, z), 0), 4) for i in range(23, -1, -1)]
    if b.get("kind", "remaining") == "remaining" and out["per_day"] and b.get("amount") is not None:
        out["runway_days"] = round(b["amount"] / out["per_day"], 1)
    if b.get("limit") and b.get("amount") is not None:
        out["pct"] = round(100 * (b["amount"] if b.get("kind") == "spent" else b["limit"] - b["amount"]) / b["limit"], 2)
    return out


def account_view(a, full=False, now=None):
    now = now or core.now()
    z = core.tz()
    aid = a["id"]
    prov = REGISTRY.get(a["provider"])
    ts, snap = latest(aid)
    s = st(aid)
    v = {"id": aid, "provider": a["provider"], "label": a["label"], "enabled": bool(a["enabled"]),
         "provider_name": prov.name if prov else a["provider"], "color": prov.color if prov else "#888",
         "mono": (prov.mono or prov.name[:1]) if prov else "?", "official": prov.official if prov else False,
         "category": prov.category if prov else "?", "connected": bool(core.creds(aid)),
         "last_ok": s["last_ok"], "last_try": s["last_try"], "error": s["error"], "error_at": s["error_at"],
         "interval": a.get("interval") or core.setting("interval"), "sample_ts": ts}
    if not snap:
        v.update(windows=[], balances=[], plan=None)
        return v
    v["plan"] = snap.get("plan")
    v["options"] = json.loads(a["options"] or "{}")
    v["breakdown"] = (snap.get("breakdown") or {}).get("rows") or []
    v["info"] = snap.get("info") or []
    wins = snap.get("windows") or []
    # a window whose reset passed since the last sample is back at 0 until the next poll confirms it
    fixed = []
    for w in wins:
        if w.get("resets") and w["resets"] < now - 60 and w.get("period") and w.get("pct") is not None:
            r = w["resets"]
            while r < now:
                r += w["period"]
            w = dict(w, pct=0.0, used=0.0 if w.get("used") is not None else None, resets=r)
        fixed.append(w)
    wins = fixed
    v["windows"] = [analyse_window(w, now, aid, z, full and (w.get("primary") or w is wins[0])) for w in wins]
    v["balances"] = [analyse_balance(b, now, aid, z) for b in snap.get("balances") or []]
    pw = next((w for w in v["windows"] if w.get("primary")), v["windows"][0] if v["windows"] else None)
    v["primary"] = pw["id"] if pw else None
    if full:
        v.update(history(aid, pw, snap, now, z))
    return v


def history(aid, pw, snap, now, z):
    """Charts for the account page: per hour (48 h), per day (30 d), 14-day heatmap, peaks per window, spend."""
    out = {"names": {}}
    if pw:
        rows = series(aid, "w:" + pw["id"], now - 100 * 86400)
        br = snap.get("breakdown") or {}
        parts_rows = {}
        if br.get("window") == pw["id"]:
            for r in br.get("rows") or []:
                out["names"][r["key"]] = r["name"]
                parts_rows[r["key"]] = {ts: v for ts, v, _ in series(aid, "s:" + r["key"], now - 100 * 86400)}
        hourly, daily = {}, {}
        prev = None
        for ts, v, reset in rows:
            if prev is not None:
                is_reset = (reset and prev[2] and abs(reset - prev[2]) > 3600) or (v < prev[1] - 0.5 and not (reset and prev[2]))
                total = v if is_reset else max(0.0, v - prev[1])
                parts = {}
                for k, m in parts_rows.items():
                    if ts in m:
                        pv = 0 if is_reset else m.get(prev[0], m[ts])
                        parts[k] = max(0.0, m[ts] - pv)
                known = sum(parts.values())
                if known > total and known > 0:
                    parts = {k: x * total / known for k, x in parts.items()}
                elif total - known > 0.001:
                    share = {k: m.get(ts, 0) for k, m in parts_rows.items() if m.get(ts, 0) > 0}
                    stt = sum(share.values())
                    if stt > 0:
                        for k, x in share.items():
                            parts[k] = parts.get(k, 0) + (total - known) * x / stt
                    else:
                        parts["_total"] = parts.get("_total", 0) + total - known
                t = datetime.fromtimestamp(ts, z)
                for bucket, key in ((hourly, hour_key(ts, z)), (daily, t.strftime("%Y-%m-%d"))):
                    b = bucket.setdefault(key, {})
                    for k, x in parts.items():
                        if x > 0:
                            b[k] = b.get(k, 0) + x
            prev = (ts, v, reset)
        rnd = lambda d: {k: round(x, 3) for k, x in d.items()}
        t0 = datetime.fromtimestamp(now, z).replace(minute=0, second=0, microsecond=0)
        out["hourly"] = [[int((t0 - timedelta(hours=i)).timestamp()), rnd(hourly.get(int((t0 - timedelta(hours=i)).timestamp()), {}))]
                         for i in range(47, -1, -1)]
        d0 = datetime.fromtimestamp(now, z).date()
        out["daily"] = [[(d0 - timedelta(days=i)).isoformat(), rnd(daily.get((d0 - timedelta(days=i)).isoformat(), {}))]
                        for i in range(29, -1, -1)]
        heat = []
        for i in range(13, -1, -1):
            day = d0 - timedelta(days=i)
            heat.append([day.isoformat(), [round(sum(hourly.get(int(datetime(day.year, day.month, day.day, h, tzinfo=z).timestamp()), {}).values()), 3)
                                           for h in range(24)]])
        out["heat"] = heat
        peaks = []
        for ts, v, reset in rows:
            if reset and peaks and abs(reset - peaks[-1][0]) <= 3600:
                peaks[-1][1] = max(peaks[-1][1], v)
            elif reset:
                peaks.append([reset, v])
        out["peaks"] = peaks[-12:]
    spend = {}
    for b in snap.get("balances") or []:
        d = spend_deltas(series(aid, "b:" + b["id"], now - 31 * 86400), b.get("kind") or "remaining")
        days = {}
        for ts, x in d:
            k = datetime.fromtimestamp(ts, z).strftime("%Y-%m-%d")
            days[k] = days.get(k, 0) + x
        d0 = datetime.fromtimestamp(now, z).date()
        spend[b["id"]] = [[(d0 - timedelta(days=i)).isoformat(), round(days.get((d0 - timedelta(days=i)).isoformat(), 0), 4)]
                          for i in range(29, -1, -1)]
    out["spend"] = spend
    with core.db() as c:
        out["errors"] = [dict(r) for r in c.execute("SELECT ts, msg FROM errors WHERE account=? ORDER BY ts DESC LIMIT 5", (aid,))]
        out["samples"] = c.execute("SELECT COUNT(*) FROM snapshots WHERE account=?", (aid,)).fetchone()[0]
    return out


def overview():
    now = core.now()
    return {"now": now, "accounts": [account_view(a, now=now) for a in accounts()],
            "settings": {k: core.setting(k) for k in ("title", "timezone", "primary_account", "demo")}}
