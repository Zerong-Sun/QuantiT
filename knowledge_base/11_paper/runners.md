# 纸面 UI runners：端口健康与重启

对象是本机 `quantit serve`（默认 **8000**）和开发态 Vite（默认 **5173**），不是策略参数或 gate。`~/.quantit/runners/` 在仓库外：那里的 `supervise.sh` **只在子进程退出时重启**，子进程变成僵死、日志仍写 `ready`、但端口已不再 LISTEN 时不会拉起。

## 症状：API 返回了 HTML

纸面 UI 若出现：

- `API 返回了 HTML 而不是 JSON；请用 http://127.0.0.1:8000/ …`
- 或旧的 `Unexpected token '<', "<!doctype"… is not valid JSON`

说明 `getJson` 拿到了 HTML（过期 `web/dist`、直接打开静态页、Vite 代理到已经不听的 8000），不要当 JSON 解析。应用 **http://127.0.0.1:8000/**（由 `quantit serve` 提供），硬刷新，并重启 serve；开发态再确认 Vite 仍代理到听着的后端。

## 检查端口是否真的在听

仓库内脚本（端口可用环境变量 / 参数改）：

```bash
bash scripts/check_runners.sh
# QUANTIT_BACKEND_PORT=8000 QUANTIT_VITE_PORT=5173 bash scripts/check_runners.sh
# 只跑 quantit serve、不跑 Vite 时：
bash scripts/check_runners.sh --no-vite
```

所需端口未 LISTEN 时非 0 退出。

## 一键重启 `~/.quantit/runners/`

监督脚本不在仓库里。下面假设你已经有 `~/.quantit/runners/supervise.sh`（以及可选的 Vite 监督）。**先杀监督组**（会带走僵死子进程），再拉起。

```bash
# 1) 看端口
bash scripts/check_runners.sh || true

# 2) 停掉监督组（按你的实际脚本名改）
pkill -f "$HOME/.quantit/runners/supervise" 2>/dev/null || true
# 若 supervise 是进程组组长，也可以：
# pgid=$(ps -o pgid= -p "$(pgrep -f "$HOME/.quantit/runners/supervise.sh" | head -1)" | tr -d ' ')
# [[ -n "$pgid" ]] && kill -- "-$pgid" 2>/dev/null || true

# 3) 再启动后端（QUANTIT_LOG_FILE 已由 quantit serve 做轮转，不必另写 logrotate）
mkdir -p "$HOME/.quantit/runners"
export QUANTIT_LOG_FILE="${QUANTIT_LOG_FILE:-$HOME/.quantit/runners/backend.log}"
nohup bash "$HOME/.quantit/runners/supervise.sh" >>"$HOME/.quantit/runners/supervise.log" 2>&1 &

# 4) 开发态 Vite（需要热更新时）
# cd web && npm run dev
# 生产纸面只用 8000：打开 http://127.0.0.1:8000/
```

`supervise.sh` 示例（**仓库不部署**；拷到 `~/.quantit/runners/supervise.sh` 后 `chmod +x`）：

```bash
#!/usr/bin/env bash
set -euo pipefail
# 退出就重启；僵死但仍占 PID、端口已不听时本循环不会触发 —— 请定期跑 scripts/check_runners.sh
export QUANTIT_LOG_FILE="${QUANTIT_LOG_FILE:-$HOME/.quantit/runners/backend.log}"
cd "${QUANTIT_ROOT:-$HOME/src/QuantiT}"
while true; do
  quantit serve --host 127.0.0.1 --port 8000 --no-open
  echo "quantit serve exited $?; restarting in 2s" >&2
  sleep 2
done
```

Vite 若也用监督，同样只在进程退出时重启；5173 不听时用 `check_runners.sh` 发现后，杀掉 Vite 监督组再 `cd web && npm run dev`。

`QUANTIT_LOG_FILE` 的轮转（默认 5 MB × 5 份，可用 `QUANTIT_LOG_MAX_BYTES` / `QUANTIT_LOG_BACKUPS` 改）已在 `quantit serve` 里实现，见仓库 README。监督脚本只要导出该变量即可，不要再叠一套轮转。
