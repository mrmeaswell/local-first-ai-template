#!/usr/bin/env bash
# Shop Helper demo: Bay Log (sample data only) + read-only AI helper, on one box that already runs Ollama.
#
#   ./setup.sh          install or update, start both services, warm the model, print the URL
#   ./setup.sh reset    put Bay Log back to its sample data (run before you present)
#   ./setup.sh status   health of Bay Log, the model, and the helper
#   ./setup.sh stop     stop both services
#
# Env overrides: MODEL (qwen2.5:7b), OLLAMA_URL (http://127.0.0.1:11434), PORT (8090),
#                DEMO_DIR (/opt/baylog-demo), BAYLOG_REPO (https://github.com/mrmeaswell/blend-zones)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="${DEMO_DIR:-/opt/baylog-demo}"
BAYLOG_REPO="${BAYLOG_REPO:-https://github.com/mrmeaswell/blend-zones}"
MODEL="${MODEL:-qwen2.5:7b}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
PORT="${PORT:-8090}"
BAYLOG_DIR="$DEMO_DIR/blend-zones/examples/bay-log"
VENV="$DEMO_DIR/venv"
DB="$DEMO_DIR/data/baylog.db"

say() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
need_root() { [ "$(id -u)" = 0 ] || { echo "Run as root (inside the demo container)."; exit 1; }; }

status() {
  printf 'Bay Log : '; curl -s -m 5 http://127.0.0.1:8080/api/health || echo "DOWN"; echo
  printf 'Helper  : '; curl -s -m 10 "http://127.0.0.1:$PORT/helper/health" || echo "DOWN"; echo
}

case "${1:-install}" in
  status) status; exit 0 ;;
  stop)   need_root; systemctl stop shop-helper baylog-demo; echo "Stopped."; exit 0 ;;
  reset)
    need_root; say "Resetting Bay Log to sample data"
    systemctl stop baylog-demo
    rm -f "$DB" "$DB-wal" "$DB-shm"
    systemctl start baylog-demo
    for _ in $(seq 30); do curl -sf http://127.0.0.1:8080/api/health >/dev/null && break; sleep 1; done
    status; exit 0 ;;
  install) ;;
  *) echo "usage: $0 [install|reset|status|stop]"; exit 2 ;;
esac

need_root
say "Packages"
apt-get install -y -qq git python3-venv curl >/dev/null

say "Bay Log code (sample data only; production is never touched)"
mkdir -p "$DEMO_DIR/data"
if [ -d "$DEMO_DIR/blend-zones/.git" ]; then git -C "$DEMO_DIR/blend-zones" pull -q --ff-only
else git clone -q --depth 1 "$BAYLOG_REPO" "$DEMO_DIR/blend-zones"; fi

say "Python environment"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip >/dev/null
"$VENV/bin/pip" install -q -r "$BAYLOG_DIR/requirements.txt" "mcp>=1.2,<2" "httpx>=0.27"
( cd "$BAYLOG_DIR" && "$VENV/bin/python" scripts/generate_keys.py >/dev/null )

say "Services"
cat > /etc/systemd/system/baylog-demo.service <<EOF
[Unit]
Description=Bay Log (demo, sample data)
After=network-online.target
[Service]
WorkingDirectory=$BAYLOG_DIR
Environment=BZ_DB_PATH=$DB
Environment=BZ_UPLOAD_DIR=$DEMO_DIR/data/uploads
Environment=BZ_DEV_AUTH=1
ExecStart=$VENV/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8080
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/shop-helper.service <<EOF
[Unit]
Description=Shop Helper (read-only AI helper for Bay Log)
After=baylog-demo.service ollama.service
Wants=baylog-demo.service
[Service]
WorkingDirectory=$HERE
Environment=BAYLOG_API=http://127.0.0.1:8080
Environment=OLLAMA_URL=$OLLAMA_URL
Environment=MODEL=$MODEL
ExecStart=$VENV/bin/uvicorn helper:app --host 0.0.0.0 --port $PORT
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q --now baylog-demo shop-helper
systemctl restart baylog-demo shop-helper

say "Waiting for Bay Log"
for _ in $(seq 30); do curl -sf http://127.0.0.1:8080/api/health >/dev/null && break; sleep 1; done

say "Warming the model ($MODEL) — the first load on CPU takes a minute"
curl -s -m 600 "$OLLAMA_URL/api/generate" -d "{\"model\":\"$MODEL\",\"prompt\":\"ok\",\"stream\":false,\"keep_alive\":\"60m\",\"options\":{\"num_predict\":1}}" >/dev/null \
  || echo "   (model warm-up failed — is Ollama running and is $MODEL pulled?)"

status
IP="$(hostname -I | awk '{print $1}')"
say "Open http://$IP:$PORT  (Bay Log with the Shop Helper button, bottom right)"
echo "Before presenting:  ./setup.sh reset    Test run:  $VENV/bin/python -u evals/run_evals.py"
