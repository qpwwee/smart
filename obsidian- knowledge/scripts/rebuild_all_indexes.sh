#!/bin/bash
# ============================================================
# 一键重建所有索引
# 由 crontab 每 6 小时执行，确保内容变更后索引最新
# ============================================================
set -e
VAULT="/Users/pon/Documents/obsidian- knowledge"
LOG="$VAULT/wiki/cron_log.txt"
TS=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TS] === 索引重建开始 ===" >> "$LOG"

# 1. graph-rag 向量索引重建（增量模式，不强制）
echo "[$TS] 1/3 重建 graph-rag 向量索引..." >> "$LOG"
cd /Users/pon/Documents/obsidian-mcp-graphrag
python3 rebuild_vectors.py >> "$LOG" 2>&1
echo "[$TS]     graph-rag 完成" >> "$LOG"

# 2. qmd 全文搜索重索引
echo "[$TS] 2/3 重建 qmd 全文索引..." >> "$LOG"
cd "$VAULT"
/usr/local/bin/qmd collection remove wiki 2>/dev/null
/usr/local/bin/qmd collection add wiki "$VAULT/wiki" --pattern "**/*.md" >> "$LOG" 2>&1
echo "[$TS]     qmd 完成" >> "$LOG"

# 3. 检查 raw/sources/ 新文件
echo "[$TS] 3/3 检查新源文件..." >> "$LOG"
cd "$VAULT"
python3 scripts/check_new_sources.py >> "$LOG" 2>&1
echo "[$TS]     源文件检查完成" >> "$LOG"

echo "[$TS] === 索引重建完成 ===" >> "$LOG"
