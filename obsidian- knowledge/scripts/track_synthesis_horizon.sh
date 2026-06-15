#!/bin/bash
# 合成上限追踪脚本
# 用途：统计 wiki/ 下 .md 文件数（排除 log.md 和 tracker 自身），追加到 tracker 页面
# 频率：每周一次（crontab 每周一 9:00）

VAULT="/Users/pon/Documents/obsidian- knowledge"
TRACKER="$VAULT/wiki/synthesis_horizon_tracker.md"
DATE=$(date "+%Y-%m-%d")

# 计算 wiki/ 下知识页面数（排除 log.md 和 synthesis_horizon_tracker.md）
PAGE_COUNT=$(find "$VAULT/wiki" -name "*.md" -not -name "log.md" -not -name "synthesis_horizon_tracker.md" | wc -l | tr -d ' ')

# 计算变化量（取上次记录的值）
LAST_COUNT=$(grep "| [0-9]" "$TRACKER" | tail -1 | awk -F'|' '{print $2}' | tr -d ' ')
if [ -z "$LAST_COUNT" ]; then
  DELTA="N/A"
else
  DELTA=$((PAGE_COUNT - LAST_COUNT))
  if [ "$DELTA" -ge 0 ]; then
    DELTA="+$DELTA"
  fi
fi

# 追加记录到 tracker
# 在 "## 历史记录" 区块后插入新行
sed -i '' "/^| [0-9]/a\\
| $DATE | $PAGE_COUNT | $DELTA | 自动追踪 |
" "$TRACKER" 2>/dev/null || {
  # 如果 sed 失败，直接追加
  echo "| $DATE | $PAGE_COUNT | $DELTA | 自动追踪 |" >> "$TRACKER"
}

echo "[$DATE] 页面数: $PAGE_COUNT (变化: $DELTA)" >> "$VAULT/wiki/cron_log.txt"
