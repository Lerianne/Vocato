#!/usr/bin/env bash
#
# Vocato installer — the private, local career coach.
#   curl -fsSL https://raw.githubusercontent.com/Lerianne/Vocato/main/install.sh | bash
#
# Idempotent: re-run any time to update to the latest version.
set -euo pipefail

# --- config (override via env vars) -----------------------------------------
REPO_URL="${VOCATO_REPO:-https://github.com/Lerianne/Vocato.git}"
INSTALL_DIR="${VOCATO_HOME:-$HOME/.vocato}"
BIN_DIR="${VOCATO_BIN:-$HOME/.local/bin}"
CHAT_MODEL="llama3.2:3b"
EMBED_MODEL="nomic-embed-text"

# --- pretty output ----------------------------------------------------------
if [ -t 1 ]; then BOLD=$'\033[1m'; DIM=$'\033[2m'; GRN=$'\033[32m'; YLW=$'\033[33m'; RED=$'\033[31m'; RST=$'\033[0m'
else BOLD=""; DIM=""; GRN=""; YLW=""; RED=""; RST=""; fi
info() { printf "%s▸%s %s\n" "$BOLD" "$RST" "$*"; }
ok()   { printf "%s✓%s %s\n" "$GRN" "$RST" "$*"; }
warn() { printf "%s!%s %s\n" "$YLW" "$RST" "$*"; }
die()  { printf "%s✗ %s%s\n" "$RED" "$*" "$RST" >&2; exit 1; }

printf "\n%s🎯 Vocato%s — answer the calling.\n%sA private career coach that runs entirely on your Mac.%s\n\n" \
  "$BOLD" "$RST" "$DIM" "$RST"

# --- 1. preflight -----------------------------------------------------------
[ "$(uname)" = "Darwin" ] || die "This installer targets macOS. (Linux: install Ollama + Python yourself, then clone the repo.)"
command -v git     >/dev/null 2>&1 || die "git not found. Install Xcode Command Line Tools:  xcode-select --install"
command -v curl    >/dev/null 2>&1 || die "curl not found (it ships with macOS — odd that it's missing)."
command -v python3 >/dev/null 2>&1 || die "python3 not found. Install it:  xcode-select --install   (or: brew install python)"
ok "macOS, git, curl, python3 present"

# --- 2. Ollama (the local model runtime) ------------------------------------
if ! command -v ollama >/dev/null 2>&1 && [ ! -d "/Applications/Ollama.app" ]; then
  info "Installing Ollama (the local AI runtime)…"
  if command -v brew >/dev/null 2>&1; then
    brew install ollama
  else
    die "Ollama isn't installed and Homebrew wasn't found.
    Install Ollama from https://ollama.com/download (drag to Applications), then re-run this installer."
  fi
fi
ok "Ollama installed"

# --- 3. make sure the Ollama server is running ------------------------------
if ! curl -fsS --max-time 2 http://localhost:11434/api/version >/dev/null 2>&1; then
  info "Starting Ollama…"
  if [ -d "/Applications/Ollama.app" ]; then open -a Ollama --hide; else (ollama serve >/dev/null 2>&1 &); fi
  for _ in $(seq 1 30); do
    curl -fsS --max-time 2 http://localhost:11434/api/version >/dev/null 2>&1 && break
    sleep 1
  done
fi
curl -fsS --max-time 2 http://localhost:11434/api/version >/dev/null 2>&1 \
  || die "Ollama server didn't come up. Open the Ollama app once, then re-run this installer."
ok "Ollama is running"

# --- 4. pull the models (~2 GB on first install) ----------------------------
info "Pulling models (first run downloads ~2 GB; cached afterward)…"
ollama pull "$CHAT_MODEL"
ollama pull "$EMBED_MODEL"
ok "Models ready: $CHAT_MODEL + $EMBED_MODEL"

# --- 5. clone or update the repo --------------------------------------------
if [ -d "$INSTALL_DIR/.git" ]; then
  info "Updating existing install at ${INSTALL_DIR}..."
  git -C "$INSTALL_DIR" pull --ff-only
else
  info "Cloning Vocato into ${INSTALL_DIR}..."
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
ok "Source ready"

# --- 6. python virtualenv + dependencies ------------------------------------
info "Setting up the Python environment…"
APP_DIR="$INSTALL_DIR/app"
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
ok "Dependencies installed"

# --- 7. install the `vocato` command on PATH --------------------------------
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/vocato" <<EOF
#!/bin/sh
# Vocato launcher — runs the coach from its install dir.
exec "$APP_DIR/coach" "\$@"
EOF
chmod +x "$BIN_DIR/vocato"
ok "Installed the 'vocato' command to $BIN_DIR"

# --- 8. done ----------------------------------------------------------------
printf "\n%s✓ Vocato is installed.%s\n\n" "$GRN$BOLD" "$RST"
case ":$PATH:" in
  *":$BIN_DIR:"*)
    printf "Start a session:\n  %svocato%s\n" "$BOLD" "$RST" ;;
  *)
    warn "$BIN_DIR isn't on your PATH yet. Add it (zsh):"
    printf "  echo 'export PATH=\"%s:\$PATH\"' >> ~/.zshrc && source ~/.zshrc\n" "$BIN_DIR"
    printf "Then start a session:\n  %svocato%s\n" "$BOLD" "$RST" ;;
esac
printf "%sFirst run walks you through setup (name, pronouns, weekly reminder) and\ncreates memory/profile.md and memory/goals.md for you to fill in.%s\n\n" "$DIM" "$RST"
