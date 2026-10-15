#!/usr/bin/env bash
# Emile, local: the Emile curriculum collaborator as a web app, on one box that already runs Ollama.
#
#   ./setup.sh          install or update, start the service, warm the local model, print the URL
#   ./setup.sh key      store an Anthropic API key (typed hidden, root-only file) so Claude plays Emile;
#                       the local model stays as automatic backup. ./setup.sh key --remove = local only
#   ./setup.sh status   health of Emile's files, Claude, and the local model
#   ./setup.sh stop     stop the service
#
# Env overrides: PORT (8091), CLAUDE_MODEL (claude-sonnet-5), MODEL (qwen2.5:7b),
#                OLLAMA_URL (http://127.0.0.1:11434), DEMO_DIR (/opt/emile-local),
#                EMILE_REPO (https://github.com/mrmeaswell/emile-public)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="${DEMO_DIR:-/opt/emile-local}"
EMILE_REPO="${EMILE_REPO:-https://github.com/mrmeaswell/emile-public}"
PORT="${PORT:-8091}"
MODEL="${MODEL:-qwen2.5:7b}"
CLAUDE_MODEL="${CLAUDE_MODEL:-claude-sonnet-5}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
EMILE_DIR="$DEMO_DIR/emile"
SECRETS="$DEMO_DIR/secrets.env"
ADDENDA="$DEMO_DIR/addenda"   # add-on modes (e.g. a college-owned addendum); kept outside the repo
OTHER_SECRETS=/opt/baylog-demo/secrets.env   # key saved earlier for the Bay Log demo, if any

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
need_root() { [ "$(id -u)" = 0 ] || { echo "Run as root (inside the container)."; exit 1; }; }
status() { printf 'Emile : '; curl -s -m 10 "http://127.0.0.1:$PORT/api/health" || echo "DOWN"; echo; }

case "${1:-install}" in
  status) status; exit 0 ;;
  stop)   need_root; systemctl stop emile-local; echo "Stopped."; exit 0 ;;
  key)
    need_root; mkdir -p "$DEMO_DIR"
    if [ "${2:-}" = "--remove" ]; then rm -f "$SECRETS"; echo "Key removed: on-prem model only."
    elif [ -f "$OTHER_SECRETS" ] && { read -rp "Reuse the key already saved for the Bay Log demo? [Y/n] " A; [ "${A:-Y}" != "n" ] && [ "${A:-Y}" != "N" ]; }; then
      install -m 600 "$OTHER_SECRETS" "$SECRETS"; echo "Reused. Saved to $SECRETS (root only)."
    else
      read -rsp "Paste the Anthropic API key (input hidden), then Enter: " K; echo
      case "$K" in sk-ant-*) ;; *) echo "That doesn't look like an Anthropic key (sk-ant-...). Nothing saved."; exit 1 ;; esac
      ( umask 077; printf 'ANTHROPIC_API_KEY=%s\n' "$K" > "$SECRETS" ); unset K
      chmod 600 "$SECRETS"; echo "Saved to $SECRETS (root only)."
    fi
    systemctl restart emile-local 2>/dev/null || true; sleep 2; status; exit 0 ;;
  install) ;;
  *) echo "usage: $0 [install|key [--remove]|status|stop]"; exit 2 ;;
esac

need_root
say "Packages"
apt-get install -y -qq git python3-venv curl >/dev/null

say "Emile (prompt, specs, MSCB, validators) from $EMILE_REPO"
mkdir -p "$DEMO_DIR" "$ADDENDA"
if [ -d "$EMILE_DIR/.git" ]; then git -C "$EMILE_DIR" pull -q --ff-only
else git clone -q --depth 1 "$EMILE_REPO" "$EMILE_DIR"; fi

say "Python environments"
[ -x "$DEMO_DIR/emile-venv/bin/python" ] || python3 -m venv "$DEMO_DIR/emile-venv"
"$DEMO_DIR/emile-venv/bin/pip" install -q --upgrade pip >/dev/null
"$DEMO_DIR/emile-venv/bin/pip" install -q --require-hashes -r "$EMILE_DIR/requirements.txt"   # Emile's server, pinned
[ -x "$DEMO_DIR/venv/bin/python" ] || python3 -m venv "$DEMO_DIR/venv"
"$DEMO_DIR/venv/bin/pip" install -q --upgrade pip >/dev/null
"$DEMO_DIR/venv/bin/pip" install -q "fastapi>=0.110" "uvicorn>=0.29" "httpx>=0.27" "mcp>=1.2,<2" "typing_extensions"

say "Service"
cat > /etc/systemd/system/emile-local.service <<EOF
[Unit]
Description=Emile, local (curriculum collaborator web app)
After=network-online.target ollama.service
[Service]
WorkingDirectory=$HERE
Environment=EMILE_DIR=$EMILE_DIR
Environment=EMILE_PYTHON=$DEMO_DIR/emile-venv/bin/python
Environment=OLLAMA_URL=$OLLAMA_URL
Environment=MODEL=$MODEL
Environment=CLAUDE_MODEL=$CLAUDE_MODEL
Environment=EMILE_ADDENDA=$ADDENDA
EnvironmentFile=-$SECRETS
ExecStart=$DEMO_DIR/venv/bin/uvicorn app:app --host 0.0.0.0 --port $PORT
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q --now emile-local
systemctl restart emile-local

say "Warming the local model ($MODEL), the backup voice"
curl -s -m 600 "$OLLAMA_URL/api/generate" -d "{\"model\":\"$MODEL\",\"prompt\":\"ok\",\"stream\":false,\"keep_alive\":\"60m\",\"options\":{\"num_predict\":1}}" >/dev/null \
  || echo "   (warm-up failed — is Ollama running and is $MODEL pulled?)"
sleep 2; status
IP="$(hostname -I | awk '{print $1}')"
say "Open http://$IP:$PORT"
[ -f "$SECRETS" ] || echo "Voice: on-prem model only. To let Claude play Emile (on-prem stays as backup):  ./setup.sh key"
echo "Test run:  EMILE_DIR=$EMILE_DIR EMILE_PYTHON=$DEMO_DIR/emile-venv/bin/python $DEMO_DIR/venv/bin/python -u evals/run_evals.py"
