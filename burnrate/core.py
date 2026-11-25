"""Shared plumbing: configuration, SQLite storage, the secrets file, the HTTP client and small helpers."""
import base64, contextlib, hashlib, json, os, secrets, sqlite3, sys, threading, time
import urllib.error, urllib.parse, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

VERSION = "0.1.0"


def env(name, default=None):
    return os.environ.get("BURNRATE_" + name, default)


DATA = env("DATA", os.path.abspath("data"))
LISTEN = env("LISTEN", "0.0.0.0")
PORT = int(env("PORT", "8090"))
AUTH = env("AUTH", "password")            # password | none (only behind an authenticating reverse proxy)
DB_FILE = os.path.join(DATA, "burnrate.db")
SECRETS_FILE = os.path.join(DATA, "secrets.json")
UA = "burnrate/" + VERSION

_lock = threading.RLock()


# ---------------------------------------------------------------- storage
@contextlib.contextmanager
def db():
    """Connection that commits on success, rolls back on error and is always closed."""
    c = sqlite3.connect(DB_FILE, timeout=15)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts(
  id INTEGER PRIMARY KEY, provider TEXT NOT NULL, label TEXT NOT NULL, options TEXT NOT NULL DEFAULT '{}',
  enabled INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, interval INTEGER, created INTEGER);
CREATE TABLE IF NOT EXISTS snapshots(account INTEGER, ts INTEGER, data TEXT, PRIMARY KEY(account, ts));
CREATE TABLE IF NOT EXISTS points(account INTEGER, ts INTEGER, key TEXT, value REAL, reset INTEGER);
CREATE INDEX IF NOT EXISTS points_idx ON points(account, key, ts);
CREATE TABLE IF NOT EXISTS errors(account INTEGER, ts INTEGER, msg TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""

DEFAULTS = {"timezone": os.environ.get("TZ") or "UTC", "interval": 300, "theme": "auto", "primary_account": None,
            "title": "Burnrate", "api_token": None, "retention_days": 400}


def init():
    os.makedirs(DATA, mode=0o700, exist_ok=True)
    with db() as c:
        c.executescript(SCHEMA)
        c.execute("PRAGMA journal_mode=WAL")
    os.chmod(DB_FILE, 0o600)


def setting(key):
    with db() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(r["value"]) if r else DEFAULTS.get(key)


def set_setting(key, value):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))


def all_settings():
    out = dict(DEFAULTS)
    with db() as c:
        for r in c.execute("SELECT key, value FROM settings"):
            out[r["key"]] = json.loads(r["value"])
    return out


def tz():
    try:
        return ZoneInfo(setting("timezone") or "UTC")
    except Exception:
        return ZoneInfo("UTC")


# ---------------------------------------------------------------- secrets (0600 JSON, never sent to the browser)
def _read_secrets():
    try:
        with open(SECRETS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _write_secrets(d):
    tmp = SECRETS_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(d, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, SECRETS_FILE)


def get_secret(name):
    with _lock:
        return _read_secrets().get(str(name))


def put_secret(name, value):
    with _lock:
        d = _read_secrets()
        if value is None:
            d.pop(str(name), None)
        else:
            d[str(name)] = value
        _write_secrets(d)


def creds(account_id):
    return get_secret(f"account:{account_id}")


def save_creds(account_id, value):
    put_secret(f"account:{account_id}", value)


# ---------------------------------------------------------------- http client
class HttpError(Exception):
    def __init__(self, code, body, url=""):
        host = urllib.parse.urlparse(url).netloc
        super().__init__(f"HTTP {code} from {host}: {redact(body)[:240]}")
        self.code = code
        self.body = body


def redact(s):
    """Best effort: never let something that looks like a token end up in an error message."""
    import re
    s = str(s).replace("\n", " ")
    return re.sub(r"(?i)(bearer\s+|token[\"'=:\s]+|key[\"'=:\s]+)[A-Za-z0-9._\-~+/=]{12,}", r"\1[redacted]", s)


def http(method, url, body=None, headers=None, form=None, timeout=30, raw=False):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read()
            if raw:
                return b
            return json.loads(b or b"{}")
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode(errors="replace"), url) from None
    except json.JSONDecodeError:
        raise RuntimeError(f"{urllib.parse.urlparse(url).netloc} did not answer with JSON (format changed, or a login page?)")


# ---------------------------------------------------------------- helpers
def now():
    return int(time.time())


def b64u(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def pkce():
    v = b64u(secrets.token_bytes(32))
    return v, b64u(hashlib.sha256(v.encode()).digest())


def iso_ts(s):
    """ISO-8601 string or epoch seconds/milliseconds -> epoch seconds (None if unusable)."""
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        return int(s / 1000) if s > 1e11 else int(s)
    try:
        s = str(s)
        if s.isdigit():
            return iso_ts(int(s))
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def jwt_claims(token):
    """Decode a JWT payload without verifying it (only to read ids/expiry the token itself carries)."""
    try:
        p = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    except Exception:
        return {}


def log(*a):
    print(*a, file=sys.stderr, flush=True)
