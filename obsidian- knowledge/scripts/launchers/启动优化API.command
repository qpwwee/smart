#!/bin/bash
cd "$(dirname "$0")/../.."
echo "启动知识库优化 API 服务..."
echo "端口: 3006"
echo "关闭: Ctrl+C"
echo ""
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 scripts/optimizer_api.py