#!/bin/bash
# 检索网关启动器 - 双击即可运行
# 为 Web UI 提供多策略检索能力

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="/tmp/retrieval_gateway.pid"
PORT=3007

# 检查是否已在运行
if lsof -ti:$PORT &>/dev/null; then
    osascript -e "display dialog \"检索网关已在运行\n端口: $PORT\" buttons {\"好的\"} default button 1"
    exit 0
fi

# 启动网关
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    "$SCRIPT_DIR/retrieval_gateway.py" $PORT &
echo $! > "$PID_FILE"

sleep 3

# 验证
if lsof -ti:$PORT &>/dev/null; then
    osascript -e "display dialog \"✅ 检索网关启动成功\n端口: $PORT\n\n测试: curl http://localhost:$PORT/search?q=测试\" buttons {\"好的\"} default button 1"
else
    osascript -e "display dialog \"❌ 检索网关启动失败\n请检查终端日志\" buttons {\"好的\"} default button 1"
fi
