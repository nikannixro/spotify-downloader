#!/usr/bin/env bash
#
# install.sh — Installer for Spotify-Downloader
#
# Sets up the project end-to-end on Debian/Ubuntu:
#   1. apt update / upgrade / install system deps (incl. Docker)
#   2. clone (or update) the repository
#   3. create config.env from example.env and prompt for required secrets
#   4. docker compose up -d --build
#
# Usage:  sudo ./install.sh
#
# Re-runs are safe: existing clones are pulled, existing .env secrets
# are preserved (only empty/placeholder values are re-prompted).
#

set -euo pipefail

# ── Constants ────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/nikannixro/Spotify-Downloader.git"
PROJECT_DIR="Spotify-Downloader"
ENV_FILE="config.env"
EXAMPLE_ENV="example.env"

# Required secret keys (no defaults — bot won't start without them).
REQUIRED_KEYS=(
    TELEGRAM_BOT_TOKEN
    ADMIN_ID
    TELEGRAM_API_ID
    TELEGRAM_API_HASH
    SPOTIFY_CLIENT_ID
    SPOTIFY_CLIENT_SECRET
)

# Placeholder strings from example.env that count as "not configured".
PLACEHOLDERS=(
    "your_bot_token"
    "your_admin_id"
    "your_api_id"
    "your_api_hash"
    "your_spotify_client_id"
    "your_spotify_client_secret"
)

# ── Pretty output ────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    C_RED=$'\033[0;31m'
    C_GREEN=$'\033[0;32m'
    C_YELLOW=$'\033[1;33m'
    C_BLUE=$'\033[0;34m'
    C_BOLD=$'\033[1m'
    C_RESET=$'\033[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_RESET=""
fi

log()  { printf '%s==>%s %s\n'  "${C_BLUE}"   "${C_RESET}" "$*"; }
ok()   { printf '%s✓%s %s\n'    "${C_GREEN}"  "${C_RESET}" "$*"; }
warn() { printf '%s!%s %s\n'    "${C_YELLOW}" "${C_RESET}" "$*" >&2; }
die()  { printf '%s✗%s %s\n'    "${C_RED}"    "${C_RESET}" "$*" >&2; exit 1; }

trap 'die "Install failed at line $LINENO."' ERR

# ── Preflight ────────────────────────────────────────────────────────────────
preflight() {
    log "Preflight checks"

    if [[ "$(id -u)" -ne 0 ]]; then
        die "This installer must be run as root. Re-run with:
  sudo bash <(curl -Ls https://raw.githubusercontent.com/nikannixro/Spotify-Downloader/main/install.sh)
  — or —
  sudo bash install.sh"
    fi
    ok "Running as root."

    if [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        ok "Detected OS: ${PRETTY_NAME:-unknown}"
        case "${ID:-}" in
            debian|ubuntu|linuxmint|pop) : ;;
            *) warn "This script targets Debian/Ubuntu. Proceeding anyway — apt commands may fail." ;;
        esac
    else
        warn "/etc/os-release not found; cannot detect OS. Proceeding anyway."
    fi
}

# ── Interactive-mode guard ────────────────────────────────────────────────────
check_interactive() {
    if [[ ! -t 0 ]]; then
        printf '%s✗%s This installer is interactive and needs a terminal for stdin.\n' \
            "${C_RED}" "${C_RESET}" >&2
        cat >&2 <<'EOF'
You appear to be piping it (e.g.  curl ... | bash), which breaks the
configuration prompts because they would read the script itself instead
of your keyboard.

Run it one of these ways instead:

  sudo bash <(curl -Ls https://raw.githubusercontent.com/nikannixro/Spotify-Downloader/main/install.sh)

or download then run:

  curl -Ls -o install.sh https://raw.githubusercontent.com/nikannixro/Spotify-Downloader/main/install.sh
  sudo bash install.sh
EOF
        exit 1
    fi
}

# ── System dependencies ──────────────────────────────────────────────────────
install_system_deps() {
    log "Updating package index and upgrading system (this may take a while)..."
    apt update && apt upgrade -y

    log "Installing core dependencies: python3-pip, python-is-python3, git, ffmpeg"
    apt install -y python3-pip python-is-python3 git ffmpeg

    # Docker: skip if already installed. Docker's official repo ships
    # containerd.io, which conflicts with Ubuntu's docker.io -> containerd, so
    # blindly installing docker.io on a host that already has Docker (e.g. from
    # download.docker.com) fails with "containerd.io: Conflicts: containerd".
    if command -v docker >/dev/null 2>&1; then
        ok "Docker already installed: $(docker --version 2>&1 | head -n1)"
        # Best-effort: ensure the compose plugin is present.
        if ! docker compose version >/dev/null 2>&1; then
            apt install -y docker-compose-plugin 2>/dev/null || \
                warn "docker-compose-plugin not found in configured repos. Install it manually if 'docker compose' fails."
        else
            ok "Docker Compose plugin available."
        fi
    else
        log "Installing Docker (docker.io + docker-compose-plugin)"
        apt install -y docker.io docker-compose-plugin
    fi

    # Ensure the invoking user can use Docker without sudo.
    local target_user="${SUDO_USER:-$USER}"
    if [[ -z "$target_user" || "$target_user" == "root" ]]; then
        warn "No non-root invoking user detected (logged in as root directly). Skipping docker group setup."
        DOCKER_GROUP_ADDED=0
    elif id -nG "$target_user" | grep -qw docker; then
        ok "User '$target_user' already in 'docker' group."
        DOCKER_GROUP_ADDED=0
    else
        log "Adding user '$target_user' to the 'docker' group..."
        usermod -aG docker "$target_user"
        warn "User '$target_user' added to the 'docker' group — they may need to log out/in or run 'newgrp docker'."
        DOCKER_GROUP_ADDED=1
    fi
    export DOCKER_GROUP_ADDED
}

# ── Clone / update repository ────────────────────────────────────────────────
clone_or_update() {
    if [[ -d "$PROJECT_DIR/.git" ]]; then
        log "Existing clone found at ./$PROJECT_DIR — pulling latest changes..."
        (
            cd "$PROJECT_DIR"
            git pull --ff-only
        )
        ok "Repository updated."
    else
        log "Cloning repository from $REPO_URL"
        git clone "$REPO_URL" "$PROJECT_DIR"
        ok "Repository cloned."
    fi
}

# ── Env file helpers ─────────────────────────────────────────────────────────

# True if a value is empty or one of the known example.env placeholders.
is_placeholder() {
    local value="$1"
    [[ -z "$value" ]] && return 0
    local p
    for p in "${PLACEHOLDERS[@]}"; do
        [[ "$value" == "$p" ]] && return 0
    done
    return 1
}

# Read the current value of KEY from $ENV_FILE (empty if missing).
get_env_value() {
    local key="$1"
    # Match 'KEY=' at start of line (ignoring leading whitespace/export).
    local line
    line=$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" 2>/dev/null | head -n1 || true)
    # Strip up to and including the first '='.
    echo "${line#*=}"
}

# Set KEY=VALUE in $ENV_FILE, replacing existing line or appending.
# Values containing spaces or special chars are single-quoted if needed.
set_env_value() {
    local key="$1" value="$2"
    local quoted

    # Quote if value has whitespace, #, or quote chars; otherwise leave bare.
    if [[ "$value" =~ [[:space:]\"\'] ]] || [[ "$value" == *#* ]]; then
        # Escape any single quotes for safe embedding.
        local escaped=${value//\'/\'\\\'\'}
        quoted="'${escaped}'"
    else
        quoted="$value"
    fi

    local tmp
    tmp=$(mktemp)
    # Replace existing KEY= line; if none, append.
    if grep -qE "^[[:space:]]*${key}=" "$ENV_FILE"; then
        awk -v k="$key" -v v="$quoted" '
            BEGIN { p = k "=" }
            $0 ~ "^[[:space:]]*" k "=" { print p v; next }
            { print }
        ' "$ENV_FILE" > "$tmp"
    else
        cp "$ENV_FILE" "$tmp"
        printf '%s=%s\n' "$key" "$quoted" >> "$tmp"
    fi
    mv "$tmp" "$ENV_FILE"
}

# Validation helpers ----------------------------------------------------------
valid_token()    { [[ "$1" =~ ^[0-9]{6,}:.+$ ]]; }
valid_numeric()  { [[ "$1" =~ ^[0-9]+$ ]]; }
valid_nonempty() { [[ -n "$1" ]]; }

prompt_for_value() {
    local key="$1" label="$2" hint="$3"
    local current valid value

    current=$(get_env_value "$key")
    if ! is_placeholder "$current"; then
        ok "$key already configured (keeping existing value)."
        return 0
    fi

    while :; do
        printf '%s%s%s %s [%s]: ' "${C_BOLD}" "$label" "${C_RESET}" "$hint" "$key"
        read -r value
        if [[ -z "$value" ]] && ! valid_nonempty "$value"; then
            warn "Value cannot be empty. Please try again."
            continue
        fi
        case "$key" in
            TELEGRAM_BOT_TOKEN)   valid=$(valid_token    "$value" && echo 1 || echo 0) ;;
            ADMIN_ID)             valid=$(valid_numeric  "$value" && echo 1 || echo 0) ;;
            TELEGRAM_API_ID)      valid=$(valid_numeric  "$value" && echo 1 || echo 0) ;;
            TELEGRAM_API_HASH)    valid=$(valid_nonempty "$value" && echo 1 || echo 0) ;;
            SPOTIFY_CLIENT_ID)    valid=$(valid_nonempty "$value" && echo 1 || echo 0) ;;
            SPOTIFY_CLIENT_SECRET)valid=$(valid_nonempty "$value" && echo 1 || echo 0) ;;
            *)                    valid=1 ;;
        esac
        if [[ "$valid" -eq 1 ]]; then
            set_env_value "$key" "$value"
            ok "$key saved."
            return 0
        fi
        warn "Invalid value for $key. Please try again."
    done
}

configure_env() {
    log "Preparing ${ENV_FILE} from ${EXAMPLE_ENV}"

    if [[ ! -f "$EXAMPLE_ENV" ]]; then
        die "${EXAMPLE_ENV} not found in project root."
    fi

    # On a fresh run, seed .env from example.env. On re-runs, keep existing .env.
    if [[ ! -f "$ENV_FILE" ]]; then
        cp "$EXAMPLE_ENV" "$ENV_FILE"
        ok "Created ${ENV_FILE} from ${EXAMPLE_ENV}."
    else
        ok "${ENV_FILE} already exists — preserving current values."
    fi

    log "You will now be prompted for the 6 required configuration values."
    echo    "Optional settings keep their defaults from ${EXAMPLE_ENV}."
    echo    "Press Ctrl+C at any time to abort."
    echo

    prompt_for_value "TELEGRAM_BOT_TOKEN"    "Telegram Bot Token"    "from @BotFather"
    prompt_for_value "ADMIN_ID"              "Your Telegram user ID" "numeric, e.g. 123456789"
    prompt_for_value "TELEGRAM_API_ID"       "Telegram API ID"       "from my.telegram.org"
    prompt_for_value "TELEGRAM_API_HASH"     "Telegram API Hash"     "from my.telegram.org"
    prompt_for_value "SPOTIFY_CLIENT_ID"     "Spotify Client ID"     "from developer.spotify.com"
    prompt_for_value "SPOTIFY_CLIENT_SECRET" "Spotify Client Secret" "from developer.spotify.com"

    ok "Configuration complete."
}

# ── Docker launch ────────────────────────────────────────────────────────────
docker_up() {
    log "Building image and starting container (docker compose up -d --build)..."
    docker compose up -d --build
    ok "Container started."
}

# ── Final summary ────────────────────────────────────────────────────────────
print_summary() {
    echo
    printf '%s━━━ Installation Complete ━━━%s\n' "${C_GREEN}" "${C_RESET}"
    echo
    log "Container status:"
    docker compose ps || true
    echo
    printf '%sLogs:%s        docker compose logs -f\n'   "${C_BOLD}" "${C_RESET}"
    printf '%sStop:%s        docker compose down\n'      "${C_BOLD}" "${C_RESET}"
    printf '%sRestart:%s     docker compose restart\n'   "${C_BOLD}" "${C_RESET}"
    echo
    if [[ "${DOCKER_GROUP_ADDED:-0}" -eq 1 ]]; then
        warn "NOTE: Log out and back in (or run 'newgrp docker') so Docker works without sudo."
        echo
    fi
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    check_interactive
    echo
    printf '%s╔══════════════════════════════════════════════════════╗%s\n' "${C_BLUE}" "${C_RESET}"
    printf '%s║   Spotify-Downloader — Installer                     ║%s\n' "${C_BLUE}" "${C_RESET}"
    printf '%s╚══════════════════════════════════════════════════════╝%s\n' "${C_BLUE}" "${C_RESET}"
    echo

    preflight
    install_system_deps
    clone_or_update

    # Run the rest from inside the project directory.
    cd "$PROJECT_DIR"
    configure_env
    docker_up
    print_summary
}

main "$@"
