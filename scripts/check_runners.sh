#!/usr/bin/env bash
# Check that paper UI runners are actually LISTENing.
# Out-of-repo supervise (~/.quantit/runners/supervise.sh) restarts on exit, not when a
# zombie child is still present but no longer bound to the port.
set -euo pipefail

BACKEND_PORT="${QUANTIT_BACKEND_PORT:-8000}"
VITE_PORT="${QUANTIT_VITE_PORT:-5173}"
CHECK_VITE="${QUANTIT_CHECK_VITE:-1}"

usage() {
  cat <<'EOF'
用法: scripts/check_runners.sh [--backend PORT] [--vite PORT] [--no-vite]

检查纸面终端相关端口是否真正处于 LISTEN（进程还在、日志写了 ready，但端口已不听时会失败）。

环境变量: QUANTIT_BACKEND_PORT（默认 8000）、QUANTIT_VITE_PORT（默认 5173）、QUANTIT_CHECK_VITE=0 等同 --no-vite。
退出码: 0 所需端口都在听；非 0 有端口未听。
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend)
      BACKEND_PORT="${2:?--backend 需要端口号}"
      shift 2
      ;;
    --vite)
      VITE_PORT="${2:?--vite 需要端口号}"
      shift 2
      ;;
    --no-vite)
      CHECK_VITE=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

is_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && ((10#$1 >= 1 && 10#$1 <= 65535))
}

if ! is_port "$BACKEND_PORT"; then
  echo "无效后端端口: $BACKEND_PORT" >&2
  exit 2
fi
if [[ "$CHECK_VITE" != "0" ]] && ! is_port "$VITE_PORT"; then
  echo "无效 Vite 端口: $VITE_PORT" >&2
  exit 2
fi

port_listening() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      return 0
    fi
  fi
  if command -v ss >/dev/null 2>&1; then
    if ss -lntH 2>/dev/null | awk -v want="$port" '
      {
        n = split($4, parts, ":")
        if (n >= 1 && parts[n] == want) { found = 1 }
      }
      END { exit found ? 0 : 1 }
    '; then
      return 0
    fi
  fi
  local hp
  hp=$(printf '%04X' "$port")
  local table
  for table in /proc/net/tcp /proc/net/tcp6; do
    [[ -r "$table" ]] || continue
    if awk -v hp="$hp" '
      NR > 1 && toupper($4) == "0A" {
        n = split($2, parts, ":")
        if (n >= 1 && toupper(parts[n]) == hp) { found = 1 }
      }
      END { exit found ? 0 : 1 }
    ' "$table"; then
      return 0
    fi
  done
  return 1
}

fail=0

echo "检查纸面 runners 端口是否 LISTEN …"

if port_listening "$BACKEND_PORT"; then
  echo "[OK]   后端 API 端口 ${BACKEND_PORT} 正在 LISTEN"
else
  echo "[FAIL] 后端 API 端口 ${BACKEND_PORT} 未在 LISTEN。quantit serve 可能已退出或僵死（日志写了 ready 但端口不听）。请按 README 或 knowledge_base/11_paper/runners.md 重启。"
  fail=1
fi

if [[ "$CHECK_VITE" != "0" ]]; then
  if port_listening "$VITE_PORT"; then
    echo "[OK]   Vite 开发服端口 ${VITE_PORT} 正在 LISTEN"
  else
    echo "[FAIL] Vite 开发服端口 ${VITE_PORT} 未在 LISTEN。~/.quantit/runners/supervise.sh 只在子进程退出时重启，僵死且不再 LISTEN 时不会拉起。"
    fail=1
  fi
else
  echo "[SKIP] 未检查 Vite 端口（--no-vite）"
fi

if [[ "$fail" -ne 0 ]]; then
  echo
  echo "若纸面 UI 报「API 返回了 HTML 而不是 JSON」或 Unexpected token '<'：多半拿到了静态页/错误代理，而不是 JSON API。请用 http://127.0.0.1:8000/ ，硬刷新，并重启 quantit serve；开发态确认 Vite 仍在代理到听着的 8000。"
  exit 1
fi

exit 0
