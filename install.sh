#!/bin/sh
# Install, update or remove Burnrate on Linux or macOS (per user, no root needed).
#
#   curl -fsSL https://raw.githubusercontent.com/TheOriUHD/burnrate/main/install.sh | sh
#   curl -fsSL https://raw.githubusercontent.com/TheOriUHD/burnrate/main/install.sh | sh -s -- --lan --port 9000
#
# What it does: finds Python 3.11+, puts Burnrate (standard library only: no pip, no venv) in ~/.local/share/burnrate,
# starts it now and at every login (systemd user service on Linux, LaunchAgent on macOS), prints the address.
# Run it again to update; your data (~/.local/share/burnrate/data) is kept.
#
# Options:
#   --port N        port (default 8090)
#   --lan           reachable from other devices (password login; the first-run setup code is in the log)
#   --no-autostart  don't start at login
#   --source S      install from a folder or zip instead of GitHub main
#   --uninstall     remove Burnrate (asks before deleting your data)
#
# On a server, Docker (compose.yaml) or the systemd unit in burnrate.service are the better fit.
set -eu

PORT=8090 LAN=0 AUTOSTART=1 UNINSTALL=0
SOURCE="https://github.com/TheOriUHD/burnrate/archive/refs/heads/main.zip"
while [ $# -gt 0 ]; do
    case "$1" in
        --port) PORT="$2"; shift ;;
        --lan) LAN=1 ;;
        --no-autostart) AUTOSTART=0 ;;
        --source) SOURCE="$2"; shift ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help) sed -n '2,17p' "$0" 2>/dev/null || true; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

HOME_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/burnrate"
APP="$HOME_DIR/app"
DATA="$HOME_DIR/data"
ENVFILE="$HOME_DIR/burnrate.env"
OS="$(uname -s)"
UNIT="$HOME/.config/systemd/user/burnrate.service"
PLIST="$HOME/Library/LaunchAgents/io.github.theoriuhd.burnrate.plist"
say() { printf '\033[36m==> %s\033[0m\n' "$*"; }

stop_service() {
    if [ "$OS" = Darwin ]; then
        launchctl unload "$PLIST" 2>/dev/null || true
    elif command -v systemctl >/dev/null 2>&1; then
        systemctl --user stop burnrate 2>/dev/null || true
    fi
    if [ -f "$DATA/burnrate.pid" ]; then
        pid="$(cat "$DATA/burnrate.pid")"
        if ps -p "$pid" -o args= 2>/dev/null | grep -q burnrate; then kill "$pid" 2>/dev/null || true; sleep 1; fi
        rm -f "$DATA/burnrate.pid"
    fi
}

if [ "$UNINSTALL" = 1 ]; then
    say "Stopping Burnrate"
    stop_service
    if [ "$OS" = Darwin ]; then rm -f "$PLIST"
    else systemctl --user disable burnrate 2>/dev/null || true; rm -f "$UNIT"; systemctl --user daemon-reload 2>/dev/null || true
    fi
    rm -rf "$APP" "$ENVFILE" "$HOME_DIR/run.sh"
    if [ -d "$DATA" ] && [ -z "${CI:-}" ]; then
        printf 'Also delete your Burnrate data in %s? [y/N] ' "$DATA"
        { read -r a </dev/tty; } 2>/dev/null || a=n
        case "$a" in [yY]*) rm -rf "$HOME_DIR" ;; esac
    fi
    say "Burnrate removed."
    exit 0
fi

say "Looking for Python 3.11 or newer"
PY=""
for c in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        PY="$(command -v "$c")"; break
    fi
done
if [ -z "$PY" ]; then
    echo "Python 3.11+ is required. Install it (e.g. 'sudo apt install python3', 'brew install python') and run this again." >&2
    exit 1
fi
say "Using $PY"

mkdir -p "$HOME_DIR" "$DATA"
chmod 700 "$HOME_DIR" "$DATA"
stop_service
say "Installing Burnrate from $SOURCE"
# fetch a zip (URL or file) or copy a folder into $APP.new, then swap it in: an update never leaves half a copy
"$PY" - "$SOURCE" "$APP" <<'PYEOF'
import io, os, shutil, sys, urllib.request, zipfile
src, app = sys.argv[1], sys.argv[2]
new = app + ".new"
shutil.rmtree(new, ignore_errors=True)
if os.path.isdir(src):
    root = src
else:
    raw = urllib.request.urlopen(src, timeout=60).read() if "://" in src else open(src, "rb").read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    tmp = new + ".zip.d"
    shutil.rmtree(tmp, ignore_errors=True)
    z.extractall(tmp)
    tops = os.listdir(tmp)
    root = os.path.join(tmp, tops[0]) if len(tops) == 1 and os.path.isdir(os.path.join(tmp, tops[0])) else tmp
if not os.path.isfile(os.path.join(root, "burnrate", "__main__.py")):
    sys.exit("no burnrate package in " + src)
shutil.copytree(os.path.join(root, "burnrate"), os.path.join(new, "burnrate"),
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
shutil.rmtree(new + ".zip.d", ignore_errors=True)
shutil.rmtree(app, ignore_errors=True)
os.replace(new, app)
PYEOF

if [ "$LAN" = 1 ]; then LISTEN=0.0.0.0 AUTH=password; else LISTEN=127.0.0.1 AUTH=none; fi
cat > "$ENVFILE" <<EOF
# Burnrate settings (written by install.sh). Change and restart, or re-run the installer.
BURNRATE_DATA=$DATA
BURNRATE_LISTEN=$LISTEN
BURNRATE_PORT=$PORT
BURNRATE_AUTH=$AUTH
PYTHONUNBUFFERED=1
EOF
cat > "$HOME_DIR/run.sh" <<EOF
#!/bin/sh
set -a; . "$ENVFILE"; set +a
cd "$APP" && exec "$PY" -m burnrate
EOF
chmod 755 "$HOME_DIR/run.sh"
LOG="$DATA/burnrate.log"

started=0
if [ "$AUTOSTART" = 1 ] && [ "$OS" = Darwin ]; then
    say "Starting at login (LaunchAgent)"
    mkdir -p "$(dirname "$PLIST")"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>io.github.theoriuhd.burnrate</string>
  <key>ProgramArguments</key><array><string>$HOME_DIR/run.sh</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
EOF
    launchctl load "$PLIST" && started=1
elif [ "$AUTOSTART" = 1 ] && command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    say "Starting at login (systemd user service)"
    mkdir -p "$(dirname "$UNIT")"
    cat > "$UNIT" <<EOF
[Unit]
Description=Burnrate usage tracker
After=network-online.target

[Service]
EnvironmentFile=$ENVFILE
WorkingDirectory=$APP
ExecStart=$PY -m burnrate
Restart=on-failure

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now burnrate && started=1
    LOG="journalctl --user -u burnrate"
fi
if [ "$started" = 0 ]; then
    [ "$AUTOSTART" = 1 ] && echo "(no systemd user session / launchd found: starting it in the background for now only)"
    say "Starting Burnrate"
    nohup "$HOME_DIR/run.sh" >>"$DATA/burnrate.log" 2>&1 &
fi

URL="http://127.0.0.1:$PORT"
i=0
until "$PY" -c "import urllib.request,sys; urllib.request.urlopen(sys.argv[1], timeout=2)" "$URL/healthz" 2>/dev/null; do
    i=$((i + 1))
    if [ $i -ge 30 ]; then echo "Burnrate did not come up on $URL. Log: $LOG" >&2; exit 1; fi
    sleep 0.5
done

printf '\n\033[32mBurnrate is running: %s\033[0m\n' "$URL"
echo "  data:     $DATA"
echo "  log:      $LOG"
echo "  settings: $ENVFILE"
[ "$LAN" = 1 ] && echo "  On first visit Burnrate asks for a setup code: it is in the log."
echo "  update: run the same command again; remove: add --uninstall (… | sh -s -- --uninstall)"
if [ -n "${CI:-}" ]; then :
elif [ "$OS" = Darwin ]; then open "$URL" 2>/dev/null || true
elif [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
fi
