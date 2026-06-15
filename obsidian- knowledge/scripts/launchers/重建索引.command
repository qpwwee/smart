#!/bin/bash
cd "$(dirname "$0")/../.."
echo "═══════════════════════════════════════════"
echo "  自动索引维护 — 重建 index.md"
echo "═══════════════════════════════════════════"
echo ""
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 scripts/auto_optimize.py --index
echo ""
echo "按回车键关闭此窗口..."
read