---
title: TheSchema - LLM Wiki 工作手册
created: 2026-05-10
tags: [schema, wiki, karpathy-llm-wiki]
---
# TheSchema — LLM Wiki 工作手册

> 本文件是 OpenCode 的「工作手册」，定义了这个 Obsidian LLM Wiki 的结构、规范和工作流程。
> 基于 Karpathy LLM Wiki 方法论构建，由人类和 AI 协同进化。
> **⚠️ 查询时不需要读此文件！直接 simple_vector_search 即可。此文件仅在 Ingest/Lint 时参考。**

---

## 一、核心架构（三层）

```
Obsidian Vault
├── raw/                         ← 原始资料层（只读）
│   ├── sources/                  ← 原始文档（PDF/书籍/笔记的 Markdown 转换文件）
│   │   ├── *.md                  ← 原始文档本身，不可修改
│   │   └── ...
│   └── dialogue-summaries/       ← 自动生成的对话精华摘要（AI 生成，人类提供）
│       ├── QClaw对话精华/
│       └── OpenCode对话精华/
├── wiki/                        ← 知识层（AI 完全拥有和维护）
│   ├── entities/                ← 实体页：人物、项目、工具、书籍
│   ├── concepts/                ← 概念页：方法论、理论、技术
│   ├── comparisons/             ← 对比分析页
│   ├── overview/               ← 主题综述页
│   ├── sources/                ← 原始文档摘要页（由 AI 根据 raw/sources/ 生成）
│   └── ...
├── log.md                      ← 操作日志（时间线）
└── index.md                    ← 内容索引（内容导向）
```

### 层与层的规则

| 层 | 规则 | 负责人 |
|---|---|---|
| **raw/** | 只读，不可修改 | 人类 |
| **raw/sources/** | 原始文档，不可修改 | 人类 |
| **raw/dialogue-summaries/** | 自动生成，AI 只写入不读取 | AI |
| **wiki/** | AI 负责所有读写、更新、维护 | AI (OpenCode) |
| **Schema** | 人机共同演进 | 人类 + AI |

### ⚠️ 严格遵守存储格式

**OpenCode 必须严格遵守以下存储规则，不得违反：**

1. **原始文档** → `raw/sources/`（人类放入，AI 只读）
2. **对话精华摘要** → `raw/dialogue-summaries/<QClaw或OpenCode>/`（AI 自动写入）
3. **Wiki 知识页** → `wiki/entities/`、`wiki/concepts/`、`wiki/comparisons/`、`wiki/overview/`（AI 维护）
4. **Wiki 摘要页** → `wiki/sources/`（AI 根据 raw/sources/ 生成）
5. **严禁**将实体页放入 `wiki/sources/`
6. **严禁**将 wiki 知识页放入 `raw/`

---

## 二、Wiki 页面规范

### 2.1 命名规则

- **实体页**：`wiki/entities/<实体名>.md`
- **概念页**：`wiki/concepts/<概念名>.md`
- **对比页**：`wiki/comparisons/<对比名>.md`
- **综述页**：`wiki/overview/<主题名>.md`
- **来源摘要**：`wiki/sources/<来源名>.md`

### 2.2 Frontmatter 要求

每个 Wiki 页面必须包含：

```yaml
---
title: <页面标题>
created: <创建日期 YYYY-MM-DD>
updated: <最后更新日期 YYYY-MM-DD>
tags: [<标签>]
source: <来源（如果有）>
type: <entity|concept|comparison|overview|source>
---
```

### 2.3 页面内链接规范（Karpathy 关键原则）

**链接方向即知识流向！**

- `[[页面名]]` — 正向链接，表示「这个页面引用/关联了那个概念」
- 反向链接 — Obsidian 自动展示，不需手动维护

**关系方向语义（四种类型，必须标注）**：

| 关系 | 方向 | 示例 | 标注格式 |
|------|------|------|----------|
| 是-关系 | 子→父 | `[[嵌入模型]]` → [[机器学习]] | `— 是-关系（嵌入模型**是**机器学习的应用）` |
| 使用-关系 | 工具→领域 | `[[OpenCode]]` → [[MCP Server]] | `— 使用-关系（OpenCode**使用**MCP Server）` |
| 基于-关系 | 实现→理论 | `[[Ollama]]` → [[LLM]] | `— 基于-关系（Ollama**基于**LLM架构）` |
| 影响-关系 | 原因→结果 | `[[RAG]]` → [[知识编译]] | `— 影响-关系（RAG的缺陷**影响了**知识编译的提出）` |

**在「相关页面」区块中，每个链接必须标注关系类型**，使图谱可视化时有向加权图的语义完全明确。

### 2.4 自我链接要求

每个 Wiki 页面应该：
1. 包含 5-10 个指向其他 Wiki 页面的链接（含关系标注）
2. 在底部有「相关页面」区块，每个链接标注关系类型（是/使用/基于/影响）
3. 如有对应原始资料，在「来源参考」区块引用 wiki/sources/ 页面
4. 被至少 1 个其他页面引用（避免孤立页面）
5. 被 3+ 个页面引用为佳（确保知识连通性）

---

## 三、三个核心操作

### 3.1 Ingest（摄入） [[Ingest]]— 录入新资料

**触发**：人类把新文件放入 `raw/` 目录，告诉 OpenCode「请处理它」

**OpenCode 执行流程**：
1. 读取原始文件内容
2. 识别核心主题、关键实体、关键概念
3. 创建 `wiki/sources/<文件名>.md` 摘要页（必须包含：来源信息、核心要点 3-5 条、关键引用）
4. 为每个新识别的实体创建/更新 `wiki/entities/` 页面
5. 为每个新识别的概念创建/更新 `wiki/concepts/` 页面
6. 检查并更新 `index.md`
7. 在 `log.md` 中追加记录：`## [YYYY-MM-DD] ingest | <来源标题>`
8. 如有新发现的关系，更新相关页面的链接

**自我改善触发**：
- 如果新资料挑战了现有结论 → 在 `log.md` 中记录矛盾，并更新受影响页面
- 如果新资料强化了现有结论 → 在相关页面追加引用
- 如果发现可以合并的重复页面 → 合并并重定向

### 3.2 Query（查询）— 回答问题

**触发**：人类向 OpenCode 提问

**OpenCode 执行流程**：
1. 读取 `index.md` 了解知识库全貌
2. 使用 Obsidian MCP 的 `simple_vector_search` 搜索相关页面
3. 读取相关性最高的 3-5 个页面
4. 综合回答，附上来源链接 `[[页面名]]`
5. **重要**：如果回答包含有价值的新洞见 → 问人类「需要把这个保存回 Wiki 吗？」

**自我改善触发**：
- 如果现有页面回答不完整 → 标记「待补充」，并在 `log.md` 中记录
- 如果发现两个页面的矛盾 → 创建 `wiki/comparisons/` 对比页
- 如果发现缺失的重要概念 → 建议人类去研究

### 3.3 Lint（健康检查）— 维护 Wiki 健康度

**触发**：
- 人类说「请对 Wiki 做一次体检」
- **每 2-4 周自动深度 Lint 一次**（由 AI 主动触发，检查图谱指标 + 内容新鲜度 + 文件健康度）
- **每次对话后自动轻量检查**（5.2 内容保鲜检查）

**定期检查日历**（自动跟踪）：
```
上次深度 Lint: 2026-06-04 ← 本次
下次深度 Lint: 2026-06-18 ~ 2026-07-02
```
检查记录在 [[log.md]] 中追踪，每次深度 Lint 后更新下次检查日期。

**OpenCode 执行流程**：
1. 扫描所有 Wiki 页面，查找：
   - ❌ 孤立页面（没有被任何其他页面引用）
   - ❌ 过时内容（时间敏感信息超过 3 个月未更新）
   - ❌ 矛盾内容（同一主题的不同页面结论不一致）
   - ❌ 缺失链接（概念页应该有指向实体的链接，但没有）
   - ❌ 孤立的来源摘要（应该被概念/实体页面引用）
2. 运行 `graph-rag_graph_stats` 获取图谱指标
3. 运行 Vault Health Checker 扫描空/薄文件
4. 检查所有页面的 `frontmatter.updated`，标注 stale（>30 天）/ aging（7-30 天）/ fresh（<7 天）
5. 生成报告，在 `log.md` 中记录：`## [YYYY-MM-DD] lint | health-check`（含完整指标）
6. 逐个修复或建议人类决策
7. 更新 `index.md` 反映最新结构

**自动修复项目**：
- 补全缺失的 frontmatter
- 修复断链（Obsidian 双链语法）
- 更新 `updated` 时间戳

---

## 四、关系图谱链接方法论（Karpathy 严格规则）

### 4.1 链接是知识结构

Obsidian 的关系图谱展示的是**有向加权图**。每个链接都有方向：

```
[页面A] ──→ [页面B]
   ↑          ↑
 链接起点   链接终点
```

**链接方向的语义规则**：
1. **「是-关系」**：子类 → 父类
   - `[[神经网络]]` 在 [[机器学习]] 页 → 「机器学习包含神经网络」
2. **「使用-关系」**：工具/方法 → 领域
   - `[[Python]]` 在 [[数据分析]] 页 → 「数据分析使用Python」
3. **「基于-关系」**：实现 → 理论/架构
   - `[[Transformer]]` 在 [[大语言模型]] 页 → 「LLM基于Transformer」
4. **「影响-关系」**：原因 → 结果
   - `[[注意力机制]]` 在 [[Transformer]] 页 → 「Transformer使用注意力机制」

### 4.2 图谱导航规则

OpenCode 应该：
- 定期检查图谱，识别高度连接的「枢纽页面」（hub）
- 识别孤立页面，尝试建立链接
- 识别单向关系，寻找反向链接的可能

### 4.3 自我完善图谱

当 OpenCode 发现知识缺口时：
1. 在 `log.md` 中记录：「建议研究：<主题>（当前无相关页面）」
2. 当人类提供新资料后，更新图谱
3. 持续迭代，直到知识图谱反映用户的完整认知框架

---

## 五、OpenCode 自我改善机制

### 5.1 每次对话后的自省

在回答完人类问题后，OpenCode 应该**静默执行**（除非需要人类决策）：

1. **检查是否产生了新知识？**
   - 如果有 → 自动写入 Wiki 相关页面（Ingest 微操作）
   
2. **检查 Wiki 是否能回答这个问题？**
   - 如果不能 → 记录到 `wiki/log.md`：`## [日期] gap | <缺口描述>`
   
3. **检查回答中是否引用了 Wiki 页面？**
   - 如果没有 → 检查是否应该创建新页面
   
4. **检查是否发现了更好的工作方式？**
   - 如果有 → 建议更新 INSTRUCTIONS.md

### 5.2 内容保鲜检查（Content Freshness Check）

在步骤 1（检查新知识）之后、步骤 2（检查缺口）之前执行。确保回答引用的已有页面内容与回答一致，避免知识库过时。

**执行流程**：
1. **提取引用页面** — 从回答中提取所有 `[[页面名]]`，排除 TheSchema / index / log / 控制面板
2. **双模型评估**：
   - 调用 **gpt-oss-cn** 读取每个页面的 `frontmatter.updated`，按天数评分
   - 新鲜度分级：>30 天 → `stale` / 7-30 天 → `aging` / <7 天 → `fresh`
   - 对比回答内容与页面内容的语义重叠度：
     - 页面已覆盖 → `covered`，跳过
     - 回答有新信息 → `gap-filled`，需要追加
     - 回答修正页面 → `conflict`，需要修正
     - 页面完全缺失 → `missing`，建议创建
3. **执行更新**（调用 **gemma4-cn**）：
   - 更新 frontmatter：`updated` → 当天日期
   - 用 `<!-- auto-fresh: YYYY-MM-DD -->` 标记每次追加内容
   - 新增 `[[链接]]` 必须带关系类型标注
   - 调用 `edit_file` / `create_file`
4. **记录日志** — 追加到 `log.md`：`## [YYYY-MM-DD] fresh | <页面名>`
5. **触发向量重建** — 调用 `rebuild_vectors.py`

### 5.3 知识缺口自动检测

当出现以下情况时，在 `log.md` 追加记录：
- 搜索返回 0 结果 → 记录「无相关页面」
- 搜索结果质量差 → 记录「页面内容不足」
- 回答依赖自身知识而非 Wiki → 记录「Wiki 未覆盖」
- 发现两个页面矛盾 → 创建 `wiki/comparisons/` 对比页

### 5.4 好问答回存

**触发条件**（满足任一即回存）：
- 回答包含 3+ 条结构化信息
- 回答澄清了一个之前模糊的概念
- 回答建立了新的知识关联

**回存流程**：创建/更新 wiki 页面 → 补充交叉链接（标注关系类型） → 更新 log.md → 更新 index.md

### 5.5 长期学习积累

OpenCode 的成长体现在：
- Wiki 越来越丰富 → OpenCode 知识越来越多
- INSTRUCTIONS.md 越来越完善 → OpenCode 工作越来越高效
- 图谱越来越密集 → OpenCode 对用户领域理解越来越深

### 5.6 反馈循环

```
人类提问 → OpenCode 回答 → 检查 Wiki 完整性 → 
  ↓
Wiki 不完整 → 补充/建议补充 → 人类提供新资料 →
  ↓
OpenCode Ingest → 更新图谱 → 下次回答更准确
```

---

## 六、特殊情况处理

### 6.1 冲突知识

当发现 Wiki 中存在矛盾时：
1. 创建 `wiki/comparisons/<主题A-vs-主题B>.md` 对比页
2. 在 `log.md` 中记录矛盾
3. 标注「待人类判断」

### 6.2 快速摄入 vs 深度摄入

- **快速摄入**：只创建来源摘要页，其他页面泛泛更新
- **深度摄入**（人类明确要求）：完整更新所有相关页面，细化每个概念

### 6.3 多模态内容

- 图片保存到 `raw/assets/`，在 Wiki 中引用 `![](raw/assets/图片名.png)`
- OpenCode 无法原生读取图片内联内容 → 先读文本，再单独请求查看相关图片

---

## 七、工具使用规则

### 7.1 Obsidian MCP 工具优先级

1. `simple_vector_search` — 首选，用于语义搜索
2. `read_file` — 读取具体页面内容
3. `list_files` — 浏览目录结构
4. `create_file` — 创建新 Wiki 页面
5. `edit_file` — 更新已有页面

### 7.2 自我改善专用

- `create_file`/`edit_file` — 写入新知识到 Wiki
- 更新 `log.md` — 记录操作历史
- 更新 `index.md` — 维护目录索引

---

## 八、欢迎来到 LLM Wiki

> Obsidian 是 IDE，OpenCode 是程序员，Wiki 是代码库。
> — Karpathy

**OpenCode 的角色**：
- 不知疲倦的图书管理员
- 知识的编译器和维护者
- 图谱的建造者和优化者

**人类的角色**：
- 策展人：决定什么值得进入知识库
- 提问者：提出深刻的问题
- 思考者：思考这一切的意义

---

## 九、工具链扩展（Karpathy 增强）

### 9.1 网页摄入 — Obsidian Web Clipper

**用途**：将网页内容一键转换为 Markdown 并保存到 Obsidian

**安装**：
- Chrome/Firefox/Safari 扩展商店搜索 "Obsidian Web Clipper"
- 或使用增强版 "MarkSnip"（支持 AI 提取、批量导出）

**配置**：
1. 安装扩展后，在浏览器工具栏点击扩展图标
2. 连接你的 Obsidian Vault
3. **保存路径设为** `raw/sources/`
4. 可选：设置模板自动提取 `title`、`url`、`date`

**工作流**：
```
浏览网页 → 点击 Clipper 扩展 → 自动转 Markdown → 保存到 raw/sources/ → 手动触发 Ingest
```

**推荐设置**：
- 快捷键：Ctrl+Shift+S（快速剪藏）
- 模板变量：`{pageTitle}`, `{pageURL}`, `{date:YYYY-MM-DD}`

---

### 9.2 本地搜索 — qmd

**用途**：本地 Markdown 文件的 BM25/向量混合搜索工具（Karpathy 推荐）

**安装**：
```bash
npm install -g @tobilu/qmd
```

**配置**：
```bash
# 添加 wiki 目录到索引
cd /Users/pon/Documents/obsidian\ knowledge
qmd collection add wiki wiki

# 查看索引状态
qmd status
```

**使用命令**：
| 命令 | 说明 |
|------|------|
| `qmd search "关键词"` | BM25 全文搜索（快速） |
| `qmd vsearch "语义"` | 向量语义搜索 |
| `qmd query "混合"` | 混合搜索 + 重排序 |
| `qmd mcp` | 启动 MCP Server（供 AI 调用） |

**OpenCode 集成**：
- 当 Wiki 规模 >200 页时，可调用 qmd 作为备用搜索
- 输出格式：`--json` 或 `--md` 便于 AI 处理

---

### 9.3 幻灯片输出 — Marp

**用途**：将 Markdown 转换为幻灯片（Karpathy 提到的输出格式之一）

**安装**：
1. Obsidian → 设置 → 第三方插件 → 关闭安全模式
2. 搜索 "Marp" → 安装 "Marp Slides"
3. 启用插件

**语法**：
```markdown
---
marp: true
---

# 第一页标题

---

## 第二页标题

内容...
```

**快捷键**：Ctrl+P 预览/导出

---

### 9.4 图表输出 — matplotlib

**用途**：生成数据可视化图表并嵌入 Wiki

**脚本**：`scripts/gen_chart.py`

**使用**：
```bash
# 柱状图
python3 scripts/gen_chart.py \
  --type bar \
  --data "Q1:30,Q2:45,Q3:60,Q4:55" \
  --output quarterly.png \
  --title "季度销售额"

# 折线图
python3 scripts/gen_chart.py \
  --type line \
  --data "1月:10,2月:15,3月:20,4月:25" \
  --output trend.png \
  --title "增长趋势" \
  --xlabel "月份" \
  --ylabel "销量"

# 饼图
python3 scripts/gen_chart.py \
  --type pie \
  --data "产品A:35,产品B:25,产品C:40" \
  --output distribution.png \
  --title "市场份额"
```

**输出位置**：`raw/assets/<filename>.png`

**在 Wiki 中引用**：
```markdown
![图表描述](raw/assets/quarterly.png)
```

---

### 9.5 资源目录结构

新增目录：
```
raw/
├── assets/              ← 图表、图片等资源
│   └── *.png, *.jpg
├── sources/             ← 原始文档
└── dialogue-summaries/  ← 对话精华
scripts/
└── gen_chart.py         ← 图表生成脚本
```

---

*本文档由人类和 OpenCode 协同创建和演进。*
*最后更新：2026-05-11*

<!-- ai-link:start -->
## 🔗 相关笔记

- [[AI 知识库架构综述]] — 提供整体架构概览，与当前结构匹配
- [[Ingest]] — 说明将原始资料转化为 Wiki 的步骤

<!-- ai-link:end -->