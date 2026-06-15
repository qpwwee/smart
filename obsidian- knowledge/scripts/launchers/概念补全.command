#!/bin/bash
cd "$(dirname "$0")/../.."
echo "═══════════════════════════════════════════"
echo "  概念自动补全 — 扫描缺失概念"
echo "═══════════════════════════════════════════"
echo ""
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 scripts/auto_optimize.py --complete
echo ""
echo "按回车键关闭此窗口..."
read