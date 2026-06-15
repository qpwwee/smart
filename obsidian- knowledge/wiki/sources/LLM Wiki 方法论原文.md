---
title: LLM Wiki 方法论原文
created: 2026-05-11
updated: 2026-05-24
tags: [source, karpathy, wiki, knowledge-management]
type: source
source: raw/sources/llm-wiki.md
---
# LLM Wiki 方法论原文

> 来自 Andrej Karpathy 的 LLM Wiki 方法论原始描述

## 来源信息

- **原始文件**：`raw/sources/llm-wiki.md`
- **作者**：Andrej Karpathy
- **内容**：Karpathy 提出的个人知识库构建模式原文
- **状态**：✅ 已 Ingest

## 核心思想

**不要让 LLM 在查询时去理解原始文档，而是提前让 LLM 把文档「编译」成结构化的知识。**

### RAG vs Wiki

| 传统 RAG | LLM Wiki |
|----------|----------|
| 每次查询从原始文档重新检索 | 知识编译一次，持久存在 |
| LLM 每次都从零重新发现知识 | 交叉引用已经建好 |
| 问完答案就没了 | 矛盾已经标记 |
| 零积累 | 持续更新，复利增长 |

## 三层架构

1. **Raw Sources（原始资料）**
   - 原始文档、PDF、文章、图片
   - 不可变，LLM 只读不改
   - 是事实来源

2. **The Wiki（知识层）**
   - LLM 生成和维护的 Markdown 文件
   - 摘要页、实体页、概念页、对比页
   - LLM 完全拥有和维护

3. **The Schema（配置层）**
   - 告诉 LLM 如何组织 Wiki 的规则
   - 人机共进，持续更新

## 三个核心操作

### Ingest（摄入）
- LLM 读取原始文档
- 与用户讨论要点
- 写入摘要页
- 更新索引和实体/概念页
- 记录日志

### Query（查询）
- LLM 搜索相关页面
- 读取并综合回答
- 引用来源
- **好答案可以回存 Wiki**

### Lint（健康检查）
- 检查矛盾
- 检查过时内容
- 检查孤立页面
- 检查缺失链接

## 工具建议

- **Obsidian**：IDE，可视化 Wiki
- **qmd**：本地搜索，BM25+向量混合
- **Marp**：Markdown 幻灯片
- **Obsidian Web Clipper**：网页剪藏
- **Dataview**：动态查询

## 关键引用

> "LLM 不感到厌倦，一次能处理 15 个文件。"

> "Wiki 是一个持久、复利积累的产物。"

> "Obsidian 是 IDE；LLM 是程序员；Wiki 是代码库。"

> "人类的任务是策展、探索、问好问题、思考意义。LLM 做其余的工作。"

## 适用场景

- **个人**：跟踪目标、健康、心理学、自我提升
- **研究**：深入研究某个主题，阅读论文，构建综述
- **读书**：每章作为条目，构建人物、主题、情节的维基
- **商业/团队**：内部维基，Slack、会议的摘要整理
- **竞争分析、尽职调查、旅行规划、课程笔记、爱好研究**

## 相关页面

- [[LLM Wiki 方法论]] — 本 Wiki 中对方法论的理解 是-关系（LLM Wiki 方法论原文**是**LLM Wiki 方法论的子概念/应用）
- [[知识编译]] — 核心机制 基于-关系（LLM Wiki 方法论原文**基于**知识编译）
- [[Andrej Karpathy]] — 方法论提出者 基于-关系（LLM Wiki 方法论原文**基于**Andrej Karpathy）
- [[Ingest]] — 摄入操作 基于-关系（LLM Wiki 方法论原文**基于**Ingest）
- [[Obsidian]] — Wiki 可视化工具 基于-关系（LLM Wiki 方法论原文**基于**Obsidian）

<!-- ai-link:start -->
## 🔗 相关笔记

- [[LLM Wiki 方法论]] — 在 Wiki 中的方法论详解 是-关系（LLM Wiki 方法论原文**是**LLM Wiki 方法论的子概念/应用）
- [[知识编译]] — LLM Wiki 的核心机制 基于-关系（LLM Wiki 方法论原文**基于**知识编译）
- [[Obsidian]] — Wiki 的展示平台 基于-关系（LLM Wiki 方法论原文**基于**Obsidian）