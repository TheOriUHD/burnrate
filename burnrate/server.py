"""HTTP server: static UI, JSON API, connect flows, app login, Prometheus metrics."""
import hashlib, hmac, json, mimetypes, os, re, secrets, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import core, engine
from .providers import REGISTRY
from .providers.base import Account

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
flows = {}                      # flow id -> pending sign-in (in memory; a restart cancels it)
flows_lock = threading.Lock()
SETUP_CODE = None               # one-time code printed to the log until a password exists
_fails = []                     # timestamps of failed logins / setup-code tries (all clients)
_fails_lock = threading.Lock()


def throttled():
    with _fails_lock:
        cut = time.time() - 600
        _fails[:] = [t for t in _fails if t > cut]
        return len(_fails) >= 10


def failed():
    with _fails_lock:
        _fails.append(time.time())


# ---------------------------------------------------------------- app auth
def _key():
    k = core.get_secret("app:key")
    if not k:
        k = secrets.token_hex(32)
        core.put_secret("app:key", k)
    return k.encode()


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    return {"salt": salt, "hash": hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 310000).hex()}


def check_pw(pw):
    h = core.get_secret("app:password")
    return bool(h) and hmac.compare_digest(hash_pw(pw, h["salt"])["hash"], h["hash"])


def make_session():
    exp = str(int(time.time()) + 30 * 86400)
    body = exp + "." + secrets.token_hex(8)
    return body + "." + hmac.new(_key(), body.encode(), "sha256").hexdigest()


def valid_session(v):
    try:
        exp, nonce, sig = v.split(".")
        body = exp + "." + nonce
        return hmac.compare_digest(sig, hmac.new(_key(), body.encode(), "sha256").hexdigest()) and int(exp) > time.time()
    except Exception:
        return False


def init_auth():
    global SETUP_CODE
    pw = core.env("PASSWORD")
    if pw:
        core.put_secret("app:password", hash_pw(pw))
    if core.AUTH == "password" and not core.get_secret("app:password"):
        SETUP_CODE = "-".join(secrets.token_hex(2) for _ in range(3))
        core.log(f"First run: open the web UI and enter this setup code to choose a password: {SETUP_CODE}")


# ---------------------------------------------------------------- helpers
class TempAccount(Account):
    """Used while testing new credentials: saving refreshed tokens only updates memory."""

    def save(self, new):
        self.creds = new


def test_and_save(provider, creds, label, options, account_id=None):
    """Fetch once with the new credentials; on success create/update the account and store the snapshot."""
    row = {"id": account_id or 0, "label": label, "options": options}
    acct = TempAccount(row, creds)
    snap = provider.fetch(acct)
    if not isinstance(snap, dict) or not (snap.get("windows") or snap.get("balances")):
        raise RuntimeError("signed in, but the provider returned no limits or balances for this account")
    with core.db() as c:
        if account_id:
            c.execute("UPDATE accounts SET options=? WHERE id=?", (json.dumps(options), account_id))
            aid = account_id
        else:
            srt = (c.execute("SELECT MAX(sort) FROM accounts").fetchone()[0] or 0) + 1
            aid = c.execute("INSERT INTO accounts(provider,label,options,enabled,sort,created) VALUES(?,?,?,?,?,?)",
                            (provider.id, label or provider.name, json.dumps(options), 1, srt, core.now())).lastrowid
    core.save_creds(aid, acct.creds)
    engine.store(aid, snap)
    s = engine.st(aid)
    s.update(last_ok=core.now(), error=None, fails=0, next=core.now() + int(core.setting("interval")))
    if not core.setting("primary_account"):
        core.set_setting("primary_account", aid)
    return aid


def clean_options(provider, given):
    out = {}
    for f in provider.options:
        v = (given or {}).get(f.name, f.default)
        if isinstance(v, str):
            v = v.strip()
        if f.required and not v:
            raise ValueError(f"{f.label} is required")
        if f.options and v and v not in [o[0] if isinstance(o, (list, tuple)) else o for o in f.options]:
            raise ValueError(f"{f.label}: invalid choice")
        if v:
            out[f.name] = v
    return out


def metrics():
    lines = ["# HELP burnrate_window_used_percent Share of a usage window used (0-100).",
             "# TYPE burnrate_window_used_percent gauge",
             "# HELP burnrate_window_reset_timestamp When the window resets (unix seconds).",
             "# TYPE burnrate_window_reset_timestamp gauge",
             "# HELP burnrate_window_forecast_percent Pattern forecast of the share used at the reset (median).",
             "# TYPE burnrate_window_forecast_percent gauge",
             "# HELP burnrate_balance Balance amount (remaining credit or spend so far, see kind).",
             "# TYPE burnrate_balance gauge",
             "# HELP burnrate_last_success_timestamp Last successful poll (unix seconds).",
             "# TYPE burnrate_last_success_timestamp gauge",
             "# HELP burnrate_up 1 if the last poll worked.", "# TYPE burnrate_up gauge"]
    esc = lambda s: str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    for a in engine.overview()["accounts"]:
        base = f'account="{esc(a["label"])}",id="{a["id"]}",provider="{a["provider"]}"'
        lines.append(f"burnrate_up{{{base}}} {0 if a['error'] else 1}")
        if a["last_ok"]:
            lines.append(f"burnrate_last_success_timestamp{{{base}}} {a['last_ok']}")
        for w in a.get("windows") or []:
            lb = f'{base},window="{esc(w["id"])}",label="{esc(w["label"])}"'
            if w.get("pct") is not None:
                lines.append(f"burnrate_window_used_percent{{{lb}}} {w['pct']}")
            if w.get("resets"):
                lines.append(f"burnrate_window_reset_timestamp{{{lb}}} {w['resets']}")
            if w.get("projected") is not None:
                lines.append(f"burnrate_window_forecast_percent{{{lb}}} {w['projected']}")
        for b in a.get("balances") or []:
            if b.get("amount") is not None:
                lines.append(f'burnrate_balance{{{base},balance="{esc(b["id"])}",currency="{esc(b["currency"])}",'
                             f'kind="{b.get("kind")}"}} {b["amount"]}')
    return "\n".join(lines) + "\n"


def wall(aid=None):
    """Compact JSON of one account's main window (kept compatible with the old claude-usage /api/wall)."""
    aid = aid or core.setting("primary_account")
    a = engine.account(int(aid)) if aid else None
    if not a:
        return {"signed_in": False, "error": "no account"}
    v = engine.account_view(a)
    w = next((x for x in v["windows"] if x["id"] == v.get("primary")), {}) if v.get("windows") else {}
    fc = w.get("forecast") or {}
    return {"account": v["label"], "provider": v["provider"], "signed_in": v["connected"], "last_ok": v["last_ok"],
            "error": v["error"], "interval": v["interval"], "used": w.get("pct"), "elapsed": w.get("elapsed"),
            "diff": w.get("diff"), "state": w.get("state"), "level": w.get("level"), "reset": w.get("resets"),
            "projected": w.get("projected"), "per_day_left": w.get("per_day_left"), "today": w.get("today"),
            "proj_lo": fc.get("p10"), "proj_hi": fc.get("p90"), "hit_prob": fc.get("hit_prob"), "hit_at": fc.get("hit_at"),
            "hourly": w.get("spark")}


# ---------------------------------------------------------------- handler
class H(BaseHTTPRequestHandler):
    server_version = "burnrate"

    def log_message(self, fmt, *a):
        pass

    def send(self, code, body, ctype="application/json", extra=None):
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body)
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    # auth ---------------------------------------------------------
    def cookie(self, name):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return None

    def logged_in(self):
        if core.AUTH == "none":
            return True
        s = self.cookie("burnrate_session")
        return bool(s and valid_session(s))

    def token_ok(self, q):
        tok = core.get_secret("app:api_token")
        if not tok:
            return False
        given = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip() or (q.get("token") or [""])[0]
        return bool(given) and hmac.compare_digest(given, tok)

    def secure(self):
        return self.headers.get("X-Forwarded-Proto") == "https"

    # GET ----------------------------------------------------------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        try:
            if p == "/healthz":
                return self.send(200, {"ok": True, "version": core.VERSION})
            if p in ("/", "/index.html"):
                return self.static("index.html")
            if re.fullmatch(r"/(app\.js|style\.css|favicon\.svg)", p):
                return self.static(p[1:])
            if p == "/api/session":
                return self.send(200, {"auth": core.AUTH, "logged_in": self.logged_in(), "version": core.VERSION,
                                       "setup_needed": core.AUTH == "password" and not core.get_secret("app:password"),
                                       "title": core.setting("title"), "demo": bool(core.setting("demo"))})
            if not self.logged_in() and not (p in ("/metrics", "/api/wall", "/api/overview") and self.token_ok(q)):
                return self.send(401, {"error": "login required"})
            if p == "/api/overview":
                return self.send(200, engine.overview())
            if p == "/api/wall":
                return self.send(200, wall((q.get("account") or [None])[0]))
            if p == "/metrics":
                return self.send(200, metrics(), "text/plain; version=0.0.4")
            m = re.fullmatch(r"/api/accounts/(\d+)", p)
            if m:
                a = engine.account(int(m.group(1)))
                return self.send(200, engine.account_view(a, full=True)) if a else self.send(404, {"error": "no such account"})
            if p == "/api/providers":
                return self.send(200, sorted((pv.describe() for pv in REGISTRY.values()),
                                             key=lambda d: (d["category"] != "subscription", d["name"].lower())))
            if p == "/api/settings":
                s = core.all_settings()
                s["api_token"] = bool(core.get_secret("app:api_token"))
                s["auth"] = core.AUTH
                s["data_dir"] = core.DATA
                return self.send(200, s)
            m = re.fullmatch(r"/api/connect/([\w-]+)", p)
            if m:
                return self.send(200, self.device_poll(m.group(1)))
            return self.send(404, {"error": "not found"})
        except Exception as e:
            core.log("GET", p, repr(e))
            return self.send(500, {"error": f"{type(e).__name__}: {core.redact(e)}"})

    def static(self, name):
        path = os.path.join(WEB, name)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        with open(path, "rb") as f:
            return self.send(200, f.read(), ctype)

    # POST ---------------------------------------------------------
    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 100000:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        # CSRF: JSON only (cross-site forms can't send it without a preflight) and same-origin fetch metadata.
        sfs = self.headers.get("Sec-Fetch-Site")
        if (self.headers.get("Content-Type") or "").split(";")[0] != "application/json" or (sfs and sfs not in ("same-origin", "none")):
            return self.send(403, {"error": "cross-origin or non-JSON request refused"})
        try:
            b = self.body()
            if p in ("/api/login", "/api/first-run") and throttled():
                return self.send(429, {"error": "too many failed attempts: wait a few minutes"})
            if p == "/api/login":
                time.sleep(0.4)
                if core.AUTH == "password" and check_pw(b.get("password") or ""):
                    return self.send(200, {"ok": True}, extra={"Set-Cookie": self.session_cookie(make_session())})
                failed()
                return self.send(401, {"error": "wrong password"})
            if p == "/api/first-run":
                global SETUP_CODE
                if core.get_secret("app:password") or not SETUP_CODE:
                    return self.send(409, {"error": "a password is already set"})
                time.sleep(0.4)
                if not hmac.compare_digest((b.get("code") or "").strip().lower(), SETUP_CODE):
                    failed()
                    return self.send(401, {"error": "wrong setup code (see the server log)"})
                if len(b.get("password") or "") < 8:
                    return self.send(400, {"error": "use at least 8 characters"})
                core.put_secret("app:password", hash_pw(b["password"]))
                SETUP_CODE = None
                return self.send(200, {"ok": True}, extra={"Set-Cookie": self.session_cookie(make_session())})
            if p == "/api/logout":
                return self.send(200, {"ok": True}, extra={"Set-Cookie": self.session_cookie("", 0)})
            if not self.logged_in():
                return self.send(401, {"error": "login required"})
            return self.send(200, self.api(p, b))
        except (ValueError, RuntimeError, KeyError, core.HttpError) as e:
            return self.send(400, {"error": core.redact(str(e))})
        except Exception as e:
            core.log("POST", p, repr(e))
            return self.send(500, {"error": f"{type(e).__name__}: {core.redact(e)}"})

    def session_cookie(self, v, age=30 * 86400):
        return (f"burnrate_session={v}; Path=/; Max-Age={age}; HttpOnly; SameSite=Lax" + ("; Secure" if self.secure() else ""))

    def api(self, p, b):
        if p == "/api/connect":
            return self.connect_start(b)
        m = re.fullmatch(r"/api/connect/([\w-]+)/finish", p)
        if m:
            return self.connect_finish(m.group(1), b)
        m = re.fullmatch(r"/api/accounts/(\d+)(?:/(\w+))?", p)
        if m:
            aid, act = int(m.group(1)), m.group(2)
            a = engine.account(aid)
            if not a:
                raise ValueError("no such account")
            if act is None:
                with core.db() as c:
                    if "label" in b:
                        c.execute("UPDATE accounts SET label=? WHERE id=?", ((b["label"] or "").strip()[:80] or a["label"], aid))
                    if "enabled" in b:
                        c.execute("UPDATE accounts SET enabled=? WHERE id=?", (1 if b["enabled"] else 0, aid))
                    if "interval" in b:
                        iv = int(b["interval"]) if b["interval"] else None
                        if iv is not None and not 60 <= iv <= 86400:
                            raise ValueError("interval must be 60-86400 seconds")
                        c.execute("UPDATE accounts SET interval=? WHERE id=?", (iv, aid))
                    if "options" in b:
                        prov = REGISTRY[a["provider"]]
                        c.execute("UPDATE accounts SET options=? WHERE id=?", (json.dumps(clean_options(prov, b["options"])), aid))
                return {"ok": True}
            if act == "poll":
                engine.poll_now(aid)
                return {"ok": True, "error": engine.st(aid)["error"]}
            if act == "disconnect":
                core.save_creds(aid, None)
                return {"ok": True}
            if act == "delete":
                with core.db() as c:
                    for t in ("accounts", "snapshots", "points", "errors"):
                        c.execute(f"DELETE FROM {t} WHERE {'id' if t == 'accounts' else 'account'}=?", (aid,))
                core.save_creds(aid, None)
                engine.status.pop(aid, None)
                if core.setting("primary_account") == aid:
                    core.set_setting("primary_account", None)
                return {"ok": True}
            raise ValueError("unknown action")
        if p == "/api/accounts/order":
            with core.db() as c:
                for i, aid in enumerate(b.get("ids") or []):
                    c.execute("UPDATE accounts SET sort=? WHERE id=?", (i, int(aid)))
            return {"ok": True}
        if p == "/api/settings":
            for k in ("title", "timezone", "theme", "primary_account", "retention_days", "interval"):
                if k in b:
                    v = b[k]
                    if k == "timezone":
                        from zoneinfo import ZoneInfo
                        ZoneInfo(v)
                    if k == "interval" and not 60 <= int(v) <= 86400:
                        raise ValueError("interval must be 60-86400 seconds")
                    if k == "retention_days" and not 7 <= int(v) <= 3650:
                        raise ValueError("retention must be 7-3650 days")
                    core.set_setting(k, v)
            if b.get("new_password"):
                if core.AUTH != "password":
                    raise ValueError("password login is off (BURNRATE_AUTH=none)")
                if not check_pw(b.get("old_password") or ""):
                    raise ValueError("current password is wrong")
                if len(b["new_password"]) < 8:
                    raise ValueError("use at least 8 characters")
                core.put_secret("app:password", hash_pw(b["new_password"]))
            if b.get("api_token") == "new":
                tok = secrets.token_urlsafe(24)
                core.put_secret("app:api_token", tok)
                return {"ok": True, "api_token": tok}
            if b.get("api_token") == "delete":
                core.put_secret("app:api_token", None)
            engine.wake.set()
            return {"ok": True}
        raise ValueError("not found")

    # connect flows -----------------------------------------------
    def connect_start(self, b):
        prov = REGISTRY.get(b.get("provider") or "")
        if not prov:
            raise ValueError("unknown provider")
        au = next((x for x in prov.auths if x.id == b.get("auth")), prov.auths[0])
        aid = int(b["account"]) if b.get("account") else None
        if aid and not engine.account(aid):
            raise ValueError("no such account")
        options = clean_options(prov, b.get("options") or (json.loads(engine.account(aid)["options"]) if aid else {}))
        label = (b.get("label") or "").strip()[:80] or prov.name
        if au.kind == "fields":
            aid = test_and_save(prov, au.build(b.get("fields") or {}), label, options, aid)
            return {"done": True, "account": aid}
        fid = secrets.token_hex(12)
        flow = {"provider": prov.id, "auth": au.id, "account": aid, "label": label, "options": options, "t": time.time()}
        flow.update(au.start(options) if _wants_options(au.start) else au.start())
        with flows_lock:
            for k in [k for k, v in flows.items() if time.time() - v["t"] > 1800]:
                flows.pop(k, None)
            flows[fid] = flow
        if au.kind == "device":
            return {"flow": fid, "kind": "device", "url": flow["url"], "user_code": flow["user_code"]}
        return {"flow": fid, "kind": "oauth_paste", "url": flow["url"], "hint": au.paste_hint}

    def _flow(self, fid):
        with flows_lock:
            f = flows.get(fid)
        if not f:
            raise ValueError("this sign-in expired or the app restarted: start again")
        prov = REGISTRY[f["provider"]]
        return f, prov, next(x for x in prov.auths if x.id == f["auth"])

    def connect_finish(self, fid, b):
        f, prov, au = self._flow(fid)
        creds = au.finish(b.get("pasted") or "", f)
        aid = test_and_save(prov, creds, f["label"], f["options"], f["account"])
        with flows_lock:
            flows.pop(fid, None)
        return {"done": True, "account": aid}

    def device_poll(self, fid):
        f, prov, au = self._flow(fid)
        if time.time() > f.get("expires", 1e18):
            raise ValueError("the code expired: start again")
        try:
            creds = au.poll(f)
        except Exception as e:
            with flows_lock:
                flows.pop(fid, None)
            return {"error": core.redact(str(e))}
        if not creds:
            return {"pending": True}
        try:
            aid = test_and_save(prov, creds, f["label"], f["options"], f["account"])
        except Exception as e:
            return {"error": core.redact(str(e))}
        finally:
            with flows_lock:
                flows.pop(fid, None)
        return {"done": True, "account": aid}


def _wants_options(fn):
    import inspect
    try:
        return len(inspect.signature(fn).parameters) >= 1
    except (TypeError, ValueError):
        return False


def serve():
    ThreadingHTTPServer.request_queue_size = 64
    srv = ThreadingHTTPServer((core.LISTEN, core.PORT), H)
    srv.daemon_threads = True
    core.log(f"burnrate {core.VERSION} on http://{core.LISTEN}:{core.PORT}  data={core.DATA}  auth={core.AUTH}")
    srv.serve_forever()
