#!/bin/bash
cd "$(dirname "$0")/../.."
echo "═══════════════════════════════════════════"
echo "  知识图谱自愈 — 发现并修复孤立页面"
echo "═══════════════════════════════════════════"
echo ""
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 scripts/auto_optimize.py --graph
echo ""
echo "按回车键关闭此窗口..."
read