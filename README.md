# Burnrate

**One self-hosted page for every AI plan you pay for.** Burnrate polls your Claude, ChatGPT, Copilot, Cursor, Gemini,
Z.ai, Kimi, Mistral, OpenRouter, DeepSeek … accounts, keeps the history, and tells you whether you are on pace: how much of
each limit is used, how much of the window has passed, and where you are likely to end up at the reset.

![Overview](docs/overview.png)

- **All accounts at once, or one provider at a time.** Every limit window (5-hour, weekly, monthly, per model) and every
  balance, with a graded verdict: *Slightly ahead of pace*, *Right on pace*, *Running hot*.
- **A forecast from your own usage pattern, not a straight line.** Recorded days are replayed hour by hour (recent days
  and the same weekday count more), 400 times, to give the likely end-of-window value, the 10–90 % range and the
  chance of hitting the limit, with the time it would happen.
- **History:** burn-up chart of the current window, 14-day hour heatmap, per hour, per day, peak of each past window,
  spend per day for balances, how long a balance lasts.
- **Sign-in flows in the browser:** API keys, OAuth with a pasted code, device codes (enter a short code at
  openai.com / github.com). Several accounts per provider are fine (work and personal).
- **Integrations:** Prometheus `/metrics`, a JSON API, and a compact `/api/wall` for dashboards and wall displays.
- **Tiny:** Python standard library only, SQLite, one process, ~30 MB RAM. Docker image or a plain `python -m burnrate`.

<p><img src="docs/account.png" width="58%" alt="Account page"> <img src="docs/add-account.png" width="40%" alt="Add account"></p>

## Quick start

### Docker

```bash
git clone https://github.com/OWNER/burnrate && cd burnrate
docker compose up -d
docker logs burnrate          # shows the one-time setup code
```

Open http://localhost:8090, enter the setup code, choose a password, then **Settings → Add account**.

### Without Docker

```bash
git clone https://github.com/OWNER/burnrate && cd burnrate
BURNRATE_DATA=./data python3 -m burnrate          # Python 3.11+, nothing to install
```

For a permanent install there is a hardened systemd unit in [`burnrate.service`](burnrate.service).

### Just look around

```bash
BURNRATE_DATA=/tmp/burnrate-demo python3 -m burnrate demo     # 7 made-up accounts, 3 weeks of history
BURNRATE_DATA=/tmp/burnrate-demo BURNRATE_AUTH=none python3 -m burnrate
```

## Configuration

Everything else (time zone, poll interval, theme, accounts, password, API token) is set in the web UI.

| Variable | Default | Meaning |
|---|---|---|
| `BURNRATE_DATA` | `./data` (`/data` in Docker) | Database and `secrets.json`. Back this directory up. |
| `BURNRATE_LISTEN` / `BURNRATE_PORT` | `0.0.0.0` / `8090` | Where the web server listens. |
| `BURNRATE_AUTH` | `password` | `none` turns the login off: **only** behind a reverse proxy that authenticates (Authelia, TinyAuth, oauth2-proxy, Cloudflare Access …). |
| `BURNRATE_PASSWORD` | – | Sets the password at start, so no setup code is needed. |
| `TZ` | `UTC` | Default time zone for a new instance. |

**Security.** Credentials are kept server-side in `secrets.json` (mode 0600) and never sent to the browser. The UI is
same-origin only (JSON + fetch-metadata checks), the session cookie is `HttpOnly`. Put it behind HTTPS if it is
reachable from outside your network. Anyone who can open the page can see your usage, so keep the password on or the
proxy in front.

### Reverse proxy

```caddyfile
usage.example.com {
    reverse_proxy burnrate:8090
}
```

Set `X-Forwarded-Proto` (Caddy does this) so the session cookie is marked `Secure`.

## Providers

Many plans have no public usage API. For those Burnrate reads the internal endpoint the provider's own app or CLI uses
(marked *internal endpoint*). These can change without notice, and using them may go against a provider's terms of
service. Sign-ins that reuse a provider's own CLI client (Claude Code, Codex, Gemini CLI, Copilot) are the same ones
those tools do on your machine; Burnrate never sees your password.

<!-- providers:start (generated: python -m burnrate providers --markdown) -->
PROVIDERS
<!-- providers:end -->

Not possible today: **Le Chat** message limits (no source; Mistral Pro/Team budgets work), **Gemini** consumer AI
Pro/Ultra (Google closed the Gemini CLI sign-in for personal accounts in June 2026), **JetBrains AI** (only local IDE
files). Missing one? See [CONTRIBUTING.md](CONTRIBUTING.md): a provider is one small Python class.

## API

| Endpoint | |
|---|---|
| `GET /api/overview` | All accounts with their windows, balances, verdicts and forecasts. |
| `GET /api/accounts/<id>` | One account with full history (hourly, daily, heatmap, burn-up, forecast curve). |
| `GET /api/wall?account=<id>` | Compact JSON of one account's main window (default: the *main account* from Settings). |
| `GET /metrics` | Prometheus: `burnrate_window_used_percent`, `burnrate_window_forecast_percent`, `burnrate_window_reset_timestamp`, `burnrate_balance`, `burnrate_up`, `burnrate_last_success_timestamp`. |
| `GET /healthz` | Liveness, no login. |

With a password set, scripts use the API token from **Settings → Security**:
`Authorization: Bearer <token>` or `?token=<token>` (read-only: overview, wall, metrics).

```yaml
# prometheus.yml
- job_name: burnrate
  metrics_path: /metrics
  authorization: { credentials: <token> }
  static_configs: [{ targets: ["burnrate:8090"] }]
```

## How the numbers work

- **Pace:** used % against the share of the window that has passed. Within ±1.5 points it is *right on pace*; ±5
  *slightly*; ±15 *ahead/under*; beyond that *well ahead/under*; more than 25 points ahead or ≥ 90 % used is *running hot*.
- **Forecast:** every past day with at least 20 sampled hours becomes a 24-hour usage profile. For the rest of the
  window each remaining day replays one of those days, chosen with weight 0.5^(age / 10 days), ×3 for the same weekday
  and ×1.5 for the same weekday/weekend kind. 400 runs give the median, the 10–90 % band, the share of runs that reach
  100 % and the median time they do. Until one full day is recorded it falls back to a straight line.
- **Per hour / per day:** increases of the used % between samples (a reset counts the new value); gaps put the whole
  increase into the first hour after the gap. Balances: spend is the drop of a remaining balance (top-ups ignored)
  or the rise of a spend figure.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). Tests: `python -m unittest discover -s tests -v`.

## License

MIT. Not affiliated with any of the providers; all names and trademarks belong to their owners.
