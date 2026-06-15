---
title: LLM Wiki 方法论
created: 2026-05-10
updated: 2026-05-24
tags: [concept, karpathy, wiki, knowledge-management]
type: concept
---
# LLM Wiki 方法论

> 核心思想：**不要让 LLM 在查询时去理解原始文档，而是提前让 LLM 把文档「编译」成结构化的知识。**

[[LLM Wiki 方法论]] 是一套由 [[Andrej Karpathy]] 提出的知识管理方法论，详见 [[LLM Wiki 方法论原文]]。

## 定义

由 Andrej Karpathy 于 2026 年提出的个人知识管理方法论。核心区别在于：

- **传统 RAG**：每次查询从原始文档重新检索、重新拼凑，知识没有积累
- **LLM Wiki**：知识编译一次，持久存在，持续更新，复利增长

## 三层架构

1. **Raw Sources（原始资料）** — 只读不可变，保证事实来源可靠
2. **The Wiki（知识层）** — LLM 生成和维护的 Markdown 文件集
3. **The Schema（配置层）** — 告诉 LLM 如何组织、维护 Wiki

## 三个核心操作

- [[Ingest]] — 摄入新资料，更新 Wiki 影响-关系（Ingest**影响**了LLM Wiki 方法论）
- 检索查询（Query）— 查询知识，好的回答可回存 Wiki
- 代码检查（Lint）— 健康检查，修复矛盾、补全链接

## 链接方向语义

在 Karpathy 方法论中，**链接方向即知识流向**：

- 子概念 → 父概念（`[[神经网络]]` 在 [[机器学习]] 页）
- 实现 → 理论（`[[Transformer]]` 在 [[大语言模型]] 页）
- 工具 → 领域（`Python` 在 `数据分析` 页）

## 为什么有效

> 维护知识库最繁琐的部分不是阅读或思考，而是日常的管理维护工作。人们放弃 wiki 是因为维护成本的增长速度超过了知识价值的增长速度。LLM 不会感到厌倦，一次就能处理 15 个文件。

## 来源参考

- [[中国文化概况（精简版）]] — Karpathy 方法论应用于文化知识的案例
- [[AI 知识库架构综述]] — 本方法论在项目中的架构全景 基于-关系（LLM Wiki 方法论**基于**AI 知识库架构综述）

## 相关页面

- [[Andrej Karpathy]] — 方法论提出者（LLM Wiki 方法论 **基于** Karpathy 的洞察）
- [[RAG]] — 被替代的传统方案（LLM Wiki 方法论 **是** RAG 的升级替代） 基于-关系（LLM Wiki 方法论**基于**RAG）
- [[知识编译]] — 核心机制（LLM Wiki 方法论 **基于** 知识编译概念） 影响-关系（知识编译**影响**了LLM Wiki 方法论）
- [[MCP Server]] — 底层工具（LLM Wiki 方法论 **使用** MCP Server） 影响-关系（MCP Server**影响**了LLM Wiki 方法论）
- [[Obsidian]] — Wiki 的可视化界面（LLM Wiki 方法论 **使用** Obsidian） 影响-关系（Obsidian**影响**了LLM Wiki 方法论）

<!-- ai-link:start -->
## 🔗 相关笔记

- [[index]] — 索引页面展示了所有笔记，符合三层架构的管理需求。

<!-- ai-link:end -->