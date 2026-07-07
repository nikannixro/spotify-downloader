#!/usr/bin/env bash
#
# install.sh — Quick Start installer for Spotify-Downloader
#
# Sets up the project end-to-end on Debian/Ubuntu:
#   1. apt update / upgrade / install system deps (incl. Docker)
#   2. clone (or update) the repository
#   3. create config.env from example.env and prompt for required secrets
#   4. docker compose up -d --build
#
# Usage:  ./install.sh
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

    [[ "$(id -u)" -eq 0 ]] && die "Run this script as a non-root user with sudo access, not as root."

    if ! command -v sudo >/dev/null 2>&1; then
        die "sudo is required but not found."
    fi

    # Validate sudo access up front (may prompt for password).
    sudo -v || die "sudo access is required."

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

  bash <(curl -Ls https://raw.githubusercontent.com/nikannixro/Spotify-Downloader/main/install.sh)

or download then run:

  curl -Ls -o install.sh https://raw.githubusercontent.com/nikannixro/Spotify-Downloader/main/install.sh
  bash install.sh
EOF
        exit 1
    fi
}

# ── System dependencies ──────────────────────────────────────────────────────
install_system_deps() {
    log "Updating package index and upgrading system (this may take a while)..."
    sudo apt update && sudo apt upgrade -y

    log "Installing core dependencies: python3-pip, python-is-python3, git, ffmpeg"
    sudo apt install -y python3-pip python-is-python3 git ffmpeg

    log "Installing Docker (docker.io + docker-compose-plugin)"
    sudo apt install -y docker.io docker-compose-plugin

    # Ensure the current user can use Docker without sudo.
    if ! id -nG "$USER" | grep -qw docker; then
        log "Adding user '$USER' to the 'docker' group..."
        sudo usermod -aG docker "$USER"
        warn "You were added to the 'docker' group. You may need to log out and back in"
        warn "(or run 'newgrp docker') before Docker works without sudo."
        DOCKER_GROUP_ADDED=1
    else
        ok "User '$USER' already in 'docker' group."
        DOCKER_GROUP_ADDED=0
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

    # If docker group was just added and current shell can't see it, fall back to sudo.
    if ! docker ps >/dev/null 2>&1; then
        warn "Docker daemon not accessible as current user; retrying with sudo."
        sudo docker compose up -d --build
    else
        docker compose up -d --build
    fi
    ok "Container started."
}

# ── Final summary ────────────────────────────────────────────────────────────
print_summary() {
    echo
    printf '%s━━━ Installation Complete ━━━%s\n' "${C_GREEN}" "${C_RESET}"
    echo
    log "Container status:"
    if docker ps >/dev/null 2>&1; then
        docker compose ps || true
    else
        sudo docker compose ps || true
    fi
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
    printf '%s║   Spotify-Downloader — Quick Start Installer         ║%s\n' "${C_BLUE}" "${C_RESET}"
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
