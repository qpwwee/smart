#!/bin/bash
cd "$(dirname "$0")/../.."
echo "═══════════════════════════════════════════"
echo "  知识库自动优化 — 全部 4 项"
echo "═══════════════════════════════════════════"
echo ""
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 scripts/auto_optimize.py
echo ""
echo "按回车键关闭此窗口..."
read