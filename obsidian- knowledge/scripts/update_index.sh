#!/bin/bash
# index.md 自动重建脚本
# 修复：正确处理包含空格的路径

VAULT="/Users/pon/Documents/obsidian- knowledge"
INDEX="$VAULT/index.md"
DATE=$(date "+%Y-%m-%d")

# 安全地按行读取文件列表
get_files() {
  find "$VAULT/$1" -maxdepth 1 -name "*.md" 2>/dev/null | sort
}

count_files() {
  get_files "$1" | wc -l | tr -d ' '
}

# 统计
CONCEPT_CNT=$(count_files "wiki/concepts")
ENTITY_CNT=$(count_files "wiki/entities")
SOURCE_CNT=$(count_files "wiki/sources")
OVERVIEW_CNT=$(count_files "wiki/overview")
COMPARISON_CNT=$(count_files "wiki/comparisons")
OVERSIGHT_CNT=$(count_files "wiki/oversight")
ROOT_CNT=$(get_files "wiki" | grep -v "/log.md" | wc -l | tr -d ' ')
TOTAL=$((CONCEPT_CNT + ENTITY_CNT + SOURCE_CNT + OVERVIEW_CNT + COMPARISON_CNT + ROOT_CNT + OVERSIGHT_CNT))

# 生成分类列表（逐行读取，保证文件名中的空格正确处理）
write_section() {
  local title="$1"
  local dir="$2"
  echo "" >> "$INDEX"
  echo "## $title" >> "$INDEX"
  get_files "$dir" | while IFS= read -r f; do
    name=$(basename "$f" .md)
    echo "- [[${name}]]" >> "$INDEX"
  done
  echo "" >> "$INDEX"
}

# 写入文件
cat > "$INDEX" << ENDMARKER
# 📚 知识库索引

> 由 AI 自动维护 — ${DATE}
> 参考 Karpathy LLM Wiki 方法论

## 📊 统计

| 类别 | 数量 |
|------|------|
| 概念页 | ${CONCEPT_CNT} |
| 实体页 | ${ENTITY_CNT} |
| 来源页 | ${SOURCE_CNT} |
| 综述页 | ${OVERVIEW_CNT} |
| 对比页 | ${COMPARISON_CNT} |
| 监控页 | ${OVERSIGHT_CNT} |
| 根页 | ${ROOT_CNT} |
| **总计** | **${TOTAL}** |

---

ENDMARKER

write_section "🔬 概念页" "wiki/concepts"
write_section "🧩 实体页" "wiki/entities"
write_section "📖 来源页" "wiki/sources"
write_section "🗺️ 综述页" "wiki/overview"
write_section "⚖️ 对比页" "wiki/comparisons"
write_section "📊 监控页" "wiki/oversight"

echo "" >> "$INDEX"
echo "## 📄 根页" >> "$INDEX"
get_files "wiki" | grep -v "/log.md" | while IFS= read -r f; do
  name=$(basename "$f" .md)
  echo "- [[${name}]]" >> "$INDEX"
done

echo "" >> "$INDEX"
echo "---" >> "$INDEX"
echo "*共 ${TOTAL} 篇笔记 · 仅收录 wiki/ 知识页面 · 最后更新 ${DATE}*" >> "$INDEX"

echo "index.md auto-regeneration completed — ${TOTAL} pages"
