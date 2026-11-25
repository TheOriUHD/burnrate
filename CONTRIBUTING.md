# Contributing

Burnrate is plain Python (3.11+, standard library only) with a vanilla-JS front end. No build step, no dependencies.

```bash
BURNRATE_DATA=./data BURNRATE_AUTH=none python -m burnrate     # http://localhost:8090
python -m unittest discover -s tests -v
```

## Adding a provider

A provider is a small class in `burnrate/providers/`. It turns stored credentials into a *snapshot*:

```python
from .base import Provider, Fields, Field, window, balance, WEEK

class Example(Provider):
    id = "example"                   # stable, lowercase: stored in the database
    name = "Example AI"
    vendor = "Example Inc."
    color = "#3366ff"                # monogram colour
    mono = "EX"
    category = "subscription"        # subscription | api | credits
    official = False                 # True only for a documented public API
    blurb = "Weekly limit and credits"
    auths = [Fields([Field("key", "API key", "secret", "ex-…")])]

    def fetch(self, acct):
        d = self.get(acct, "https://api.example.com/v1/usage")   # Bearer key, 401 refresh handled
        return {
            "plan": d.get("plan"),
            "windows": [window("week", "Weekly", d["used_percent"], resets=d["reset_at"], period=WEEK, primary=True)],
            "balances": [balance("credits", "Credits", d["credits"], "USD")],
        }
```

Then add the module name to `MODULES` in `burnrate/providers/__init__.py` and a parser test in `tests/`.

- `window(id, label, pct=… | used=…, limit=…, resets=…, period=…)`: give `period` (seconds) and `resets` whenever you know
  them. They drive the pace verdict, the burn-up chart and the forecast.
- `balance(id, label, amount, currency, limit=None, kind="remaining" | "spent")`.
- Auth methods: `Fields` (keys, cookies), `OAuthPaste` (authorization code + PKCE where the user pastes the code or the
  redirect URL back), `DeviceFlow` (RFC 8628 device codes). Look at `claude.py`, `chatgpt.py` and `copilot.py`.
- Raise `RuntimeError("short plain message")` for expected failures (expired cookie, no plan). Never put secrets in it.
- Keep parsing in a pure `parse(...)` function so it can be tested with a recorded (and anonymised) response.
- Unofficial endpoints are welcome, but say so (`official = False`); they break, and tests make fixing them quick.
