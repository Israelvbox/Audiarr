#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="audiarr"
APP_USER="${APP_USER:-audiarr}"
INSTALL_DIR="/opt/$APP_NAME"
VENV_DIR="$INSTALL_DIR/.venv"
SERVICE_FILE="/etc/systemd/system/$APP_NAME.service"

echo "==> Audiarr install script"
echo ""

# ── 1. Check dependencies ──
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 is required. Install it with: apt install python3"
  exit 1
fi
if ! python3 -c "import ensurepip" &>/dev/null 2>&1; then
  echo "ERROR: python3-venv is required. Install it with: apt install python3-venv"
  exit 1
fi
if ! command -v ffmpeg &>/dev/null; then
  echo "Installing ffmpeg..."
  apt-get update -qq && apt-get install -y -qq ffmpeg
fi

# ── 2. Create system user ──
if ! id -u "$APP_USER" &>/dev/null; then
  echo "Creating system user: $APP_USER"
  useradd --system --no-create-home --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$APP_USER"
else
  echo "User $APP_USER already exists"
fi

# ── 3. Create install directory ──
echo "Installing to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"
cp -r "$REPO_DIR/app" "$INSTALL_DIR/app"
cp "$REPO_DIR/requirements.txt" "$INSTALL_DIR/"

# ── 4. Create .env (preserve existing) ──
if [ -f "$INSTALL_DIR/.env" ]; then
  echo ".env already exists, keeping it"
else
  if [ -f "$REPO_DIR/.env.example" ]; then
    cp "$REPO_DIR/.env.example" "$INSTALL_DIR/.env"
    echo ".env created from .env.example — edit $INSTALL_DIR/.env to add your Spotify API keys"
  else
    cat > "$INSTALL_DIR/.env" << EOF
AUDIARR_SPOTIFY_CLIENT_ID=your_spotify_client_id
AUDIARR_SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
EOF
    echo ".env created — edit $INSTALL_DIR/.env to add your Spotify API keys"
  fi
fi

# ── 5. Create virtualenv ──
echo "Creating virtualenv"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
echo "Installing Python dependencies (this may take a while)..."
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
echo "Installing spotdl (standalone)..."
"$VENV_DIR/bin/pip" install spotdl==4.5.0 --no-deps --quiet
"$VENV_DIR/bin/pip" install rich beautifulsoup4 mutagen platformdirs pykakasi python-slugify rapidfuzz syncedlyrics ytmusicapi soundcloud-v2 jinja2 python-multipart datastar-py spotipyfree --quiet

# ── 6. Set ownership ──
chown -R "$APP_USER":"$APP_USER" "$INSTALL_DIR"

# ── 7. Create systemd service ──
echo "Creating systemd service"
cat > "$SERVICE_FILE" << SERVICEEOF
[Unit]
Description=Audiarr - Music download manager
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
AmbientCapabilities=
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
SERVICEEOF

# ── 8. Enable and start ──
systemctl daemon-reload
systemctl enable "$APP_NAME"
systemctl start "$APP_NAME"

# ── 9. Wait and show admin credentials ──
echo ""
echo "Waiting for service to start..."
for i in $(seq 1 10); do
  if curl -s -o /dev/null -w "" http://localhost:8000/ 2>/dev/null; then
    break
  fi
  sleep 1
done
echo ""
echo "==> Installation complete!"
echo "    Service: $APP_NAME (systemctl status $APP_NAME)"
echo "    URL: http://localhost:8000"
echo "    Users are created via Register or admin panel"
echo ""

ADMIN_LINE=$(journalctl -u "$APP_NAME" --since "1 minute ago" --no-pager 2>/dev/null | grep "AUTO-GENERATED ADMIN" -A 3 | tail -3)
if [ -n "$ADMIN_LINE" ]; then
  echo "    ════════════════════════════════════════"
  echo "    AUTO-GENERATED ADMIN CREDENTIALS:"
  echo "$ADMIN_LINE" | while IFS= read -r line; do
    echo "    $line"
  done
  echo "    Log in, create another admin, then delete this one."
  echo "    ════════════════════════════════════════"
fi
echo ""
echo "    IMPORTANT: Configure Spotify API keys in $INSTALL_DIR/.env"
echo "    Then set the download directory in Settings (admin panel)"
echo "    and restart: systemctl restart $APP_NAME"
echo ""
