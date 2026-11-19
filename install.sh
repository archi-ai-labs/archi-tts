#!/usr/bin/env bash
# archi-tts installer for a cloned repo (Apple Silicon Mac).
# Prefer the Claude Code plugin if you only use Claude Code — see README.
#
#   ./install.sh                 set up, then ask where to register (Claude Code / Claude Desktop / HTTP)
#   ./install.sh --yes           register Claude Code + Claude Desktop without asking
#   ./install.sh --no-register   set up and self-test only
#   ./install.sh --full          full edition: adds OmniVoice voice cloning (~1 GB libraries + 3.3 GB model)
#   ./install.sh --lite          back to the lite edition (built-in VieNeu voices only; the default)
#   ./install.sh --whisper       also download Whisper (add_voice without a transcript; full only)
#   ./install.sh --http          run one shared HTTP server in the background (LaunchAgent)
#   ./install.sh --uninstall     remove registrations and the background server (keeps ~/.archi-tts and models)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DATA="${ARCHI_TTS_DATA:-$HOME/.archi-tts}"
LAUNCHER="$ROOT/bin/archi-tts-mcp"
PORT=8766
URL="http://127.0.0.1:$PORT/mcp"
AGENT_ID="com.archi-ai-labs.archi-tts"
AGENT_PLIST="$HOME/Library/LaunchAgents/$AGENT_ID.plist"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

YES=0; REGISTER=1; WHISPER=0; HTTP=0; UNINSTALL=0; EDITION=""
for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --no-register) REGISTER=0 ;;
    --whisper) WHISPER=1 ;;
    --full) EDITION=full ;;
    --lite) EDITION=lite ;;
    --http) HTTP=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "Tham số không hợp lệ: $arg"; exit 2 ;;
  esac
done

say()  { printf "\n\033[1m==> %s\033[0m\n" "$*"; }
ask()  { # ask "question" default(y/n)
  if [[ $YES -eq 1 ]]; then [[ $2 == y ]]; return; fi
  local hint="[y/N]"; [[ $2 == y ]] && hint="[Y/n]"
  read -r -p "$1 $hint " reply || reply=""
  [[ ${reply:-$2} =~ ^[Yy] ]]
}
have_claude() { command -v claude >/dev/null 2>&1; }
setup_cli() { ARCHI_TTS_HOME="$DATA/home" "$DATA/venv/bin/archi-tts-setup" "$@"; }

if [[ $UNINSTALL -eq 1 ]]; then
  say "Gỡ đăng ký archi-tts"
  if have_claude; then
    claude mcp remove -s user archi-tts >/dev/null 2>&1 && echo "Đã gỡ khỏi Claude Code (mcp)." || true
    claude plugin uninstall archi-tts@archi-ai-labs >/dev/null 2>&1 && echo "Đã gỡ plugin Claude Code." || true
  fi
  [[ -x "$DATA/venv/bin/archi-tts-setup" ]] && setup_cli register-desktop --remove || true
  if [[ -f "$AGENT_PLIST" ]]; then
    launchctl bootout "gui/$(id -u)" "$AGENT_PLIST" 2>/dev/null || true
    rm -f "$AGENT_PLIST"; echo "Đã gỡ server HTTP chạy nền."
  fi
  echo "Giữ nguyên $DATA (giọng, từ điển, môi trường) và model trong ~/.cache/huggingface."
  exit 0
fi

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Cảnh báo: archi-tts được thử trên Mac Apple Silicon; máy này là $(uname -s) $(uname -m)."
fi

if [[ -z "$EDITION" && ! -f "$DATA/edition" ]] &&
   ask "Cài bản full (thêm giọng clone OmniVoice, ~4.3 GB)? Không thì cài bản lite (15 giọng VieNeu, ~2 GB)." n; then
  EDITION=full
fi
say "Cài đặt (thư viện, môi trường Python, model, chạy thử)"
"$ROOT/bin/archi-tts-bootstrap" ${EDITION:+--$EDITION}

if [[ "$(cat "$DATA/edition" 2>/dev/null)" == full ]]; then
  if [[ $WHISPER -eq 0 ]] && ask "Tải thêm Whisper (~1.6 GB) để add_voice tự nhận dạng lời trong clip?" n; then WHISPER=1; fi
  [[ $WHISPER -eq 1 ]] && HF_HUB_OFFLINE=0 setup_cli download --whisper
fi

if [[ $REGISTER -eq 1 ]]; then
  if [[ $HTTP -eq 0 && $YES -eq 0 ]] && ask "Chạy MỘT server HTTP chung ở nền (tiết kiệm RAM khi dùng nhiều client)?" n; then HTTP=1; fi

  if [[ $HTTP -eq 1 ]]; then
    say "Server HTTP chạy nền ($URL)"
    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
    cat > "$AGENT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$AGENT_ID</string>
  <key>ProgramArguments</key><array>
    <string>$LAUNCHER</string><string>--http</string><string>--port</string><string>$PORT</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/archi-tts.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/archi-tts.log</string>
</dict></plist>
PLIST
    launchctl bootout "gui/$(id -u)" "$AGENT_PLIST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$AGENT_PLIST"
    for _ in $(seq 1 60); do nc -z 127.0.0.1 "$PORT" 2>/dev/null && break; sleep 0.5; done
    nc -z 127.0.0.1 "$PORT" && echo "Đang chạy tại $URL (log: ~/Library/Logs/archi-tts.log)" \
      || echo "Server chưa lên, xem ~/Library/Logs/archi-tts.log"
  fi

  if have_claude && ask "Đăng ký cho Claude Code ở mọi project?" y; then
    claude mcp remove -s user archi-tts >/dev/null 2>&1 || true
    if [[ $HTTP -eq 1 ]]; then
      claude mcp add -s user --transport http archi-tts "$URL"
    else
      claude mcp add -s user archi-tts -- "$LAUNCHER"
    fi
  fi

  if [[ -d "$HOME/Library/Application Support/Claude" ]] && ask "Đăng ký cho Claude Desktop?" y; then
    setup_cli register-desktop --command "$LAUNCHER"
  fi
fi

say "Xong"
setup_cli doctor || true
cat <<EOF

Dùng thử: trong Claude, nói "Dùng archi-tts đọc câu: Xin chào các bạn, hôm nay chúng ta tìm hiểu về chip AI."
File xuất ra: ~/archi-tts-output/   Giọng & từ điển của bạn: $DATA/home/   Gỡ: ./install.sh --uninstall
EOF
