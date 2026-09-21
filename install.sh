#!/usr/bin/env bash
# Pi Onboarding Console — installer.
#
# Installs the system dependencies, the Wi-Fi sudoers allowlist and the systemd
# *user* service, then starts it. Run it as the account the console should run
# as (NOT as root) from inside the checkout:
#
#   ./install.sh
#
# It is safe to re-run: every step is idempotent.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="onboarding"
UNIT_SRC="$REPO_DIR/deploy/$SERVICE_NAME.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SUDOERS_SRC="$REPO_DIR/deploy/sudoers.d/pi-console"
SUDOERS_DST="/etc/sudoers.d/pi-console"

do_apt=1
do_sudoers=1
do_service=1
do_connect=1

usage() {
    cat <<'EOF'
Usage: ./install.sh [options]

  --skip-apt        don't apt-install the Python/camera dependencies
  --skip-sudoers    don't install the Wi-Fi sudoers allowlist
  --skip-service    don't install/start the systemd user service
  --no-connect      don't apt-install rpi-connect
  -h, --help        show this help

Run it as the user the console should run as; it calls sudo where needed.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --skip-apt)     do_apt=0 ;;
        --skip-sudoers) do_sudoers=0 ;;
        --skip-service) do_service=0 ;;
        --no-connect)   do_connect=0 ;;
        -h|--help)      usage; exit 0 ;;
        *) echo "unknown option: $arg" >&2; usage >&2; exit 2 ;;
    esac
done

# --- output helpers ---------------------------------------------------------
if [ -t 1 ]; then
    BOLD=$'\e[1m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; GREEN=$'\e[32m'; OFF=$'\e[0m'
else
    BOLD=''; RED=''; YELLOW=''; GREEN=''; OFF=''
fi
step() { printf '\n%s==> %s%s\n' "$BOLD" "$*" "$OFF"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '%s    warning: %s%s\n' "$YELLOW" "$*" "$OFF" >&2; }
die()  { printf '%s    error: %s%s\n' "$RED" "$*" "$OFF" >&2; exit 1; }

# --- preflight --------------------------------------------------------------
step "Checking the environment"

[ "$(uname -s)" = "Linux" ] || die "this installer targets Raspberry Pi OS / Debian Linux."
[ "$(id -u)" -ne 0 ] || die "don't run this as root — run it as the user the console should run as; it calls sudo itself."
[ -f "$REPO_DIR/main.py" ] || die "run this from inside the checkout (main.py not found next to install.sh)."

SERVICE_USER="$(id -un)"
info "user:       $SERVICE_USER"
info "checkout:   $REPO_DIR"

# Read the camera backend and port straight out of app/config.py so the
# installer can never disagree with the app.
CAMERA_BACKEND="$(sed -n 's/^CAMERA_BACKEND[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$REPO_DIR/app/config.py")"
PORT="$(sed -n 's/^PORT[[:space:]]*=[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$REPO_DIR/app/config.py")"
CAMERA_BACKEND="${CAMERA_BACKEND:-picamera2}"
PORT="${PORT:-8000}"
info "camera:     $CAMERA_BACKEND"
info "port:       $PORT"

# Prompt for the sudo password once, up front — but only if a step needs root.
if [ $((do_apt + do_sudoers + do_service)) -gt 0 ]; then
    sudo -v || die "sudo is required (for apt, the sudoers allowlist and lingering)."
fi

# --- dependencies -----------------------------------------------------------
if [ "$do_apt" -eq 1 ]; then
    step "Installing dependencies (apt)"
    pkgs=(python3-fastapi python3-uvicorn python3-jinja2)
    case "$CAMERA_BACKEND" in
        picamera2) pkgs+=(python3-picamera2) ;;
        usb)       pkgs+=(python3-imageio python3-simplejpeg) ;;
        *)         warn "unknown CAMERA_BACKEND '$CAMERA_BACKEND' — installing no camera packages." ;;
    esac
    if [ "$do_connect" -eq 1 ]; then
        pkgs+=(rpi-connect)
    fi

    info "${pkgs[*]}"
    sudo apt-get update -qq
    if ! sudo apt-get install -y "${pkgs[@]}"; then
        # rpi-connect only exists in the Raspberry Pi OS archive; on plain
        # Debian the whole transaction fails because of it. Retry without it.
        if [ "$do_connect" -eq 1 ]; then
            warn "apt failed — retrying without rpi-connect (the Connect page will be inert)."
            without_connect=()
            for p in "${pkgs[@]}"; do
                [ "$p" = "rpi-connect" ] || without_connect+=("$p")
            done
            sudo apt-get install -y "${without_connect[@]}"
        else
            die "apt install failed."
        fi
    fi
else
    step "Skipping apt (--skip-apt)"
fi

step "Verifying the Python imports"
python3 - <<'EOF' || die "core dependencies are missing — re-run without --skip-apt, or install them by hand (see README)."
import importlib.util
import sys

missing = [m for m in ("fastapi", "uvicorn", "jinja2") if not importlib.util.find_spec(m)]
if missing:
    print("    missing:", ", ".join(missing), file=sys.stderr)
    sys.exit(1)
EOF
info "fastapi, uvicorn, jinja2 ok"

has_module() { python3 -c 'import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in sys.argv[1:]) else 1)' "$@"; }
case "$CAMERA_BACKEND" in
    picamera2)
        has_module picamera2 && info "picamera2 ok" \
            || warn "picamera2 is not importable — the camera page will show an error." ;;
    usb)
        has_module imageio simplejpeg && info "imageio, simplejpeg ok" \
            || warn "imageio/simplejpeg are not importable — the camera page will show an error." ;;
esac

# --- sudoers allowlist ------------------------------------------------------
if [ "$do_sudoers" -eq 1 ]; then
    step "Installing the Wi-Fi sudoers allowlist ($SUDOERS_DST)"

    if ! command -v nmcli >/dev/null 2>&1; then
        warn "nmcli not found — the Wi-Fi page needs NetworkManager."
    elif [ "$(command -v nmcli)" != "/usr/bin/nmcli" ]; then
        warn "nmcli is at $(command -v nmcli) but the allowlist expects /usr/bin/nmcli — edit $SUDOERS_SRC."
    fi

    tmp_sudoers="$(mktemp)"
    trap 'rm -f "$tmp_sudoers"' EXIT
    # The shipped file grants the rules to `pi`; point them at this account.
    sed "s/^pi ALL=/$SERVICE_USER ALL=/" "$SUDOERS_SRC" > "$tmp_sudoers"
    grep -q "^$SERVICE_USER ALL=" "$tmp_sudoers" || die "no 'pi ALL=' line in $SUDOERS_SRC — nothing was installed."

    sudo visudo -cqf "$tmp_sudoers" || die "the generated sudoers file is invalid — nothing was installed."
    sudo install -o root -g root -m 440 "$tmp_sudoers" "$SUDOERS_DST"
    rm -f "$tmp_sudoers"
    trap - EXIT
    info "granted to $SERVICE_USER, mode 440"

    sudo visudo -cq || die "/etc/sudoers is now invalid — inspect $SUDOERS_DST."
    if sudo -n nmcli connection reload >/dev/null 2>&1; then
        info "verified: passwordless nmcli works"
    else
        warn "'sudo -n nmcli connection reload' still fails — Wi-Fi changes won't work. Check $SUDOERS_DST."
    fi
else
    step "Skipping the sudoers allowlist (--skip-sudoers)"
fi

# --- systemd user service ---------------------------------------------------
if [ "$do_service" -eq 1 ]; then
    step "Installing the systemd user service"

    systemctl --user show-environment >/dev/null 2>&1 || \
        die "no systemd user session (is XDG_RUNTIME_DIR set?). Log in as $SERVICE_USER on the console or over SSH and re-run, or pass --skip-service."

    mkdir -p "$UNIT_DIR"
    # Point WorkingDirectory at this checkout — %h-relative when it lives under
    # $HOME, absolute otherwise.
    case "$REPO_DIR" in
        "$HOME"/*) workdir="%h/${REPO_DIR#"$HOME"/}" ;;
        *)         workdir="$REPO_DIR" ;;
    esac
    sed "s|^WorkingDirectory=.*|WorkingDirectory=$workdir|" "$UNIT_SRC" > "$UNIT_DIR/$SERVICE_NAME.service"
    info "$UNIT_DIR/$SERVICE_NAME.service (WorkingDirectory=$workdir)"

    systemctl --user daemon-reload
    systemctl --user enable "$SERVICE_NAME" >/dev/null
    systemctl --user restart "$SERVICE_NAME"

    # Keep it running at boot / when nobody is logged in.
    if [ "$(loginctl show-user "$SERVICE_USER" -p Linger --value 2>/dev/null)" = "yes" ]; then
        info "lingering already enabled"
    elif sudo loginctl enable-linger "$SERVICE_USER"; then
        info "lingering enabled (starts at boot)"
    else
        warn "couldn't enable lingering — the service will stop when you log out."
    fi

    sleep 2
    if systemctl --user is-active --quiet "$SERVICE_NAME"; then
        info "${GREEN}service is running${OFF}"
    else
        systemctl --user status "$SERVICE_NAME" --no-pager --lines=20 || true
        die "the service failed to start — see the status above and 'journalctl --user -u $SERVICE_NAME -e'."
    fi
else
    step "Skipping the systemd service (--skip-service)"
fi

# --- done -------------------------------------------------------------------
ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
: "${ip:=$(hostname)}"
step "Done"
info "Console:  http://$ip:$PORT"
if [ "$do_service" -eq 1 ]; then
    info "Status:   systemctl --user status $SERVICE_NAME"
    info "Logs:     journalctl --user -u $SERVICE_NAME -f"
    info "Restart:  systemctl --user restart $SERVICE_NAME"
else
    info "Run:      python3 main.py"
fi
echo
