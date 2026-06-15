#!/bin/bash
cd "$(dirname "$0")/../.."
echo "═══════════════════════════════════════════"
echo "  内容质量巡检 — 检查链接/标注/frontmatter"
echo "═══════════════════════════════════════════"
echo ""
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 scripts/auto_optimize.py --lint
echo ""
echo "按回车键关闭此窗口..."
read