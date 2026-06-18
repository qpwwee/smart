#!/bin/bash
# Knowledge Base Web UI 一键控制脚本
# 用法: ./kb.sh [start|stop|status|restart|tunnel|help]
#
# 功能:
#   start   - 启动 Web UI 服务
#   stop    - 停止 Web UI + 隧道
#   status  - 查看运行状态
#   restart - 重启服务
#   tunnel  - 仅启动/重启 Cloudflare 隧道
#   help    - 显示帮助

set -euo pipefail

BORE_SERVER="bore.pub"
# 如需自建 bore server: BORE_SERVER="your-server.com"
# 如需用 cloudflared: 手动执行 ./kb.sh tunnel-cf

# ====== 配置 ======
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT="/Users/pon/Documents/obsidian- knowledge"
PORT=8081
PASSWORD="wiki2026"
LLM_MODEL="qwen/qwen3-vl-4b"
EMBEDDING_MODEL="qwen3-embedding:4b"
OLLAMA_URL="http://localhost:11434"
LM_STUDIO_URL="http://localhost:1234/v1"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
PID_FILE="$SCRIPT_DIR/.kb-webui.pid"
TUNNEL_PID_FILE="$SCRIPT_DIR/.kb-tunnel.pid"
LOG_FILE="$SCRIPT_DIR/.kb-webui.log"
TUNNEL_LOG_FILE="$SCRIPT_DIR/.kb-tunnel.log"
CF_PID_FILE="$SCRIPT_DIR/.kb-cf-tunnel.pid"
CF_LOG_FILE="$SCRIPT_DIR/.kb-cf-tunnel.log"

# ====== 颜色 ======
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ====== 函数 ======

is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        # PID 文件在但进程已死，清理
        rm -f "$pid_file"
    fi
    return 1
}

get_tunnel_url() {
    if [ -f "$TUNNEL_LOG_FILE" ]; then
        local port=$(grep -o "$BORE_SERVER:[0-9]*" "$TUNNEL_LOG_FILE" 2>/dev/null | tail -1 | cut -d: -f2)
        if [ -n "$port" ]; then
            echo "http://${BORE_SERVER}:${port}"
            return 0
        fi
        # fallback: cloudflared格式
        grep -a -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG_FILE" | tail -1
    fi
}

do_start() {
    echo -e "${CYAN}🚀 启动 Knowledge Base Web UI${NC}"
    
    # 检查端口占用
    if lsof -ti:$PORT >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  端口 $PORT 已被占用，先停止${NC}"
        do_stop
        sleep 1
    fi
    
    # 检查 Ollama
    if ! curl -s "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
        echo -e "${RED}❌ Ollama 未运行！请先启动 Ollama${NC}"
        echo "   ollama serve"
        exit 1
    fi
    
    # 检查嵌入模型
    if ! curl -s "$OLLAMA_URL/api/tags" | grep -q "$EMBEDDING_MODEL"; then
        echo -e "${YELLOW}⚠️  嵌入模型 $EMBEDDING_MODEL 未找到，向量搜索可能不可用${NC}"
    fi
    
    # 启动 Web UI
    cd "$SCRIPT_DIR"
    KB_PASSWORD="$PASSWORD" nohup $PYTHON web_ui.py \
        --vault "$VAULT" \
        --port $PORT \
        --ollama-url "$OLLAMA_URL" \
        --embedding-model "$EMBEDDING_MODEL" \
        --lm-studio-url "$LM_STUDIO_URL" \
        --llm-model "$LLM_MODEL" \
        > "$LOG_FILE" 2>&1 &
    
    local pid=$!
    echo "$pid" > "$PID_FILE"
    
    # 等待启动
    echo -n "   等待服务启动"
    for i in $(seq 1 15); do
        sleep 1
        echo -n "."
        if curl -s "http://localhost:$PORT/" >/dev/null 2>&1; then
            echo ""
            echo -e "${GREEN}✅ Web UI 已启动${NC}"
            echo "   本地: http://localhost:$PORT"
            echo "   PID:  $pid"
            echo "   日志: $LOG_FILE"
            return 0
        fi
    done
    echo ""
    echo -e "${RED}❌ 启动超时，检查日志: $LOG_FILE${NC}"
    tail -20 "$LOG_FILE"
    return 1
}

do_tunnel() {
    echo -e "${CYAN}🌐 启动 bore 内网穿透${NC}"
    
    # 先杀旧的隧道
    if is_running "$TUNNEL_PID_FILE"; then
        echo -e "${YELLOW}   停止旧隧道...${NC}"
        kill "$(cat "$TUNNEL_PID_FILE")" 2>/dev/null || true
        sleep 1
    fi
    
    # 检查 bore
    if ! command -v bore &>/dev/null; then
        echo -e "${RED}❌ bore 未安装${NC}"
        echo "   curl -fsSL https://github.com/ekzhang/bore/releases/latest - see releases"
        echo "   或 brew install bore-cli"
        exit 1
    fi
    
    # 检查 Web UI 是否在跑
    if ! curl -s "http://localhost:$PORT/" >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Web UI 未运行，先启动${NC}"
        do_start
        sleep 1
    fi
    
    # 启动 bore
    nohup bore local $PORT --to "$BORE_SERVER" > "$TUNNEL_LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$TUNNEL_PID_FILE"
    
    # 等待地址出现
    echo -n "   等待隧道连接"
    local port=""
    for i in $(seq 1 10); do
        sleep 1
        echo -n "."
        port=$(grep -o "$BORE_SERVER:[0-9]*" "$TUNNEL_LOG_FILE" 2>/dev/null | tail -1 | cut -d: -f2)
        if [ -n "$port" ]; then
            echo ""
            echo -e "${GREEN}✅ 隧道已启动${NC}"
            echo "   公网: http://${BORE_SERVER}:${port}"
            echo "   PID:  $pid"
            echo "   日志: $TUNNEL_LOG_FILE"
            echo ""
            echo -e "${YELLOW}💡 bore 端口重启后可能变化，建议收藏当前地址${NC}"
            return 0
        fi
    done
    echo ""
    port=$(grep -o "$BORE_SERVER:[0-9]*" "$TUNNEL_LOG_FILE" 2>/dev/null | tail -1 | cut -d: -f2)
    if [ -n "$port" ]; then
        echo -e "${GREEN}✅ 隧道已启动${NC}"
        echo "   公网: http://${BORE_SERVER}:${port}"
    else
        echo -e "${RED}❌ 隧道启动失败，检查日志: $TUNNEL_LOG_FILE${NC}"
        tail -5 "$TUNNEL_LOG_FILE"
    fi
}

do_stop() {
    echo -e "${CYAN}🛑 停止 Knowledge Base 服务${NC}"
    
    # 停 bore 隧道
    if is_running "$TUNNEL_PID_FILE"; then
        kill "$(cat "$TUNNEL_PID_FILE")" 2>/dev/null || true
        rm -f "$TUNNEL_PID_FILE"
        echo -e "${GREEN}   ✅ bore 隧道已停止${NC}"
    fi
    # 停 CF 隧道
    if [ -f "$CF_PID_FILE" ] && kill -0 "$(cat "$CF_PID_FILE")" 2>/dev/null; then
        kill "$(cat "$CF_PID_FILE")" 2>/dev/null || true
        rm -f "$CF_PID_FILE"
        echo -e "${GREEN}   ✅ CF 隧道已停止${NC}"
    fi
    
    # 停 Web UI（先尝试 PID 文件）
    if is_running "$PID_FILE"; then
        kill "$(cat "$PID_FILE")" 2>/dev/null || true
        rm -f "$PID_FILE"
        echo -e "${GREEN}   ✅ Web UI 已停止${NC}"
    else
        # 兜底：按端口杀
        local pids=$(lsof -ti:$PORT 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo "$pids" | xargs kill 2>/dev/null || true
            echo -e "${GREEN}   ✅ Web UI 已停止（端口清理）${NC}"
        else
            echo "   Web UI 未运行"
        fi
    fi
}

do_status() {
    echo -e "${CYAN}📊 Knowledge Base 服务状态${NC}"
    echo ""
    
    # Web UI
    if is_running "$PID_FILE"; then
        local pid=$(cat "$PID_FILE")
        echo -e "  Web UI:  ${GREEN}● 运行中${NC} (PID: $pid, 端口: $PORT)"
        echo "           http://localhost:$PORT"
    else
        local pids=$(lsof -ti:$PORT 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo -e "  Web UI:  ${YELLOW}● 运行中（无 PID 文件）${NC} (端口: $PORT)"
        else
            echo -e "  Web UI:  ${RED}○ 未运行${NC}"
        fi
    fi
    
    # bore 隧道
    if is_running "$TUNNEL_PID_FILE"; then
        local url=$(get_tunnel_url)
        echo -e "  bore:    ${GREEN}● 运行中${NC} (PID: $(cat "$TUNNEL_PID_FILE"))"
        [ -n "$url" ] && echo "           $url"
    else
        echo -e "  bore:    ${RED}○ 未运行${NC}"
    fi
    # CF 隧道
    if [ -f "$CF_PID_FILE" ] && kill -0 "$(cat "$CF_PID_FILE")" 2>/dev/null; then
        local cf_url=$(grep -a -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$CF_LOG_FILE" 2>/dev/null | tail -1)
        echo -e "  CF:      ${GREEN}● 运行中${NC} (PID: $(cat "$CF_PID_FILE"))"
        [ -n "$cf_url" ] && echo "           $cf_url"
    else
        echo -e "  CF:      ${RED}○ 未运行${NC}"
    fi
    
    # Ollama
    if curl -s "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
        local models=$(curl -s "$OLLAMA_URL/api/tags" | grep -o '"name":"[^"]*"' | sed 's/"name":"//;s/"//' | tr '\n' ', ' | sed 's/,$//')
        echo -e "  Ollama:  ${GREEN}● 运行中${NC}"
        echo "           模型: $models"
    else
        echo -e "  Ollama:  ${RED}○ 未运行${NC}"
    fi
    
    # 磁盘
    echo ""
    local vault_size=$(du -sh "$VAULT" 2>/dev/null | cut -f1 || echo "?")
    local cache_size=$(du -sh "$SCRIPT_DIR/.vector_cache" 2>/dev/null | cut -f1 || echo "?")
    echo "  知识库:  $vault_size ($VAULT)"
    echo "  向量缓存: $cache_size"
}

do_restart() {
    echo -e "${CYAN}🔄 重启 Knowledge Base 服务${NC}"
    local with_tunnel="${1:-}"
    do_stop
    sleep 2
    do_start
    if [ "$with_tunnel" = "--with-tunnel" ]; then
        do_tunnel
    elif [ "$with_tunnel" = "--with-tunnel-full" ]; then
        do_tunnel_full
    elif is_running "$TUNNEL_PID_FILE"; then
        do_tunnel
    fi
}

do_tunnel_cf() {
    echo -e "${CYAN}🌐 启动 Cloudflare Tunnel（HTTPS，支持摄像头）${NC}"
    
    # 只杀旧的 CF 隧道
    if [ -f "$CF_PID_FILE" ] && kill -0 "$(cat "$CF_PID_FILE")" 2>/dev/null; then
        echo -e "${YELLOW}   停止旧 CF 隧道...${NC}"
        kill "$(cat "$CF_PID_FILE")" 2>/dev/null || true
        sleep 1
    fi
    
    if ! command -v cloudflared &>/dev/null; then
        echo -e "${RED}❌ cloudflared 未安装${NC}"
        echo "   brew install cloudflare/cloudflare/cloudflared"
        exit 1
    fi
    
    if ! curl -s "http://localhost:$PORT/" >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Web UI 未运行，先启动${NC}"
        do_start
        sleep 1
    fi
    
    nohup cloudflared tunnel --url "http://localhost:$PORT" > "$CF_LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$CF_PID_FILE"
    
    echo -n "   等待隧道连接"
    for i in $(seq 1 30); do
        sleep 1
        echo -n "."
        local url=$(grep -a -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$CF_LOG_FILE" | tail -1)
        if [ -n "$url" ]; then
            echo ""
            echo -e "${GREEN}✅ CF 隧道已启动${NC}"
            echo "   公网: $url"
            echo "   PID:  $pid"
            echo "   ⚠️  URL 重启后变化 | 长请求可能超时"
            return 0
        fi
    done
    local url=$(grep -a -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$CF_LOG_FILE" | tail -1)
    [ -n "$url" ] && echo -e "${GREEN}✅ 公网: $url${NC}" || echo -e "${YELLOW}⏳ 仍在连接中${NC}"
}

do_tunnel_full() {
    echo -e "${CYAN}🌐 启动双隧道（bore + Cloudflare）${NC}"
    echo ""
    do_tunnel
    echo ""
    do_tunnel_cf
    echo ""
    echo -e "${GREEN}✅ 双隧道就绪${NC}"
    if [ -f "$TUNNEL_PID_FILE" ]; then
        local bp=$(grep -o "$BORE_SERVER:[0-9]*" "$TUNNEL_LOG_FILE" 2>/dev/null | tail -1 | cut -d: -f2) || true
        [ -n "$bp" ] && echo "   bore (HTTP):  http://${BORE_SERVER}:${bp}  ← 日常使用，稳定"
    fi
    if [ -f "$CF_PID_FILE" ]; then
        local cu=$(grep -a -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$CF_LOG_FILE" | tail -1) || true
        [ -n "$cu" ] && echo "   CF   (HTTPS): ${cu}  ← 需要摄像头时用这个"
    fi
    echo ""
    echo -e "${YELLOW}💡 摄像头: 浏览器要求 HTTPS 或 localhost${NC}"
    echo -e "${YELLOW}   CF 隧道提供 HTTPS → 摄像头可用${NC}"
    echo -e "${YELLOW}   bore 走 HTTP → 摄像头不可用，其他功能正常${NC}"
}

do_help() {
    echo -e "${CYAN}Knowledge Base Web UI 控制脚本${NC}"
    echo ""
    echo "用法: ./kb.sh <命令>"
    echo ""
    echo "命令:"
    echo "  start     启动 Web UI 服务"
    echo "  stop      停止所有服务（Web UI + 隧道）"
    echo "  restart   重启服务"
    echo "  status    查看运行状态"
    echo "  tunnel      启动 bore 内网穿透（HTTP，稳定）"
    echo "  tunnel-cf   启动 Cloudflare 隧道（HTTPS，支持摄像头）"
    echo "  tunnel-full 同时启动双隧道（推荐）"
    echo "  help        显示此帮助"
    echo ""
    echo "💡 摄像头只能工作在 HTTPS 或 localhost："
    echo "   localhost:8080 → 摄像头 ✅"
    echo "   CF 隧道 HTTPS  → 摄像头 ✅"
    echo "   bore HTTP      → 摄像头 ❌"
    echo ""
    echo "快捷组合:"
    echo "  ./kb.sh start && ./kb.sh tunnel-full  # 启动服务 + 双隧道"
    echo "  ./kb.sh stop                          # 一键全关"
    echo ""
    echo "配置（修改脚本顶部变量）:"
    echo "  PORT=$PORT"
    echo "  PASSWORD=$PASSWORD"
    echo "  LLM_MODEL=$LLM_MODEL"
    echo "  EMBEDDING_MODEL=$EMBEDDING_MODEL"
    echo "  VAULT=$VAULT"
}

# ====== 主入口 ======
case "${1:-help}" in
    start)   do_start ;;
    stop)    do_stop ;;
    status)  do_status ;;
    restart) do_restart ;;
    tunnel)      do_tunnel ;;
    tunnel-cf)   do_tunnel_cf ;;
    tunnel-full) do_tunnel_full ;;
    help|*)      do_help ;;
esac
