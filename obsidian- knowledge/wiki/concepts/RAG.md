---
title: RAG
created: 2026-05-10
updated: 2026-05-24
tags: [concept, rag, knowledge-management]
type: concept
---
# RAG（检索增强生成）

> Retrieval-Augmented Generation，当前主流的知识库技术方案

## 定义

RAG 的工作流程：上传文档 → 提问时检索相关片段 → LLM 基于片段生成答案。

## 核心问题

Karpathy 指出 RAG 的致命缺陷： [[RAG vs 知识编译]]
- **没有积累**：每次查询都从原始文档重新检索、重新拼凑
- **零启动**：LLM 每次回答问题都从零重新发现知识
- **不持久**：问完了答案就没了，下次还得重新推导

## 与 LLM Wiki 的对比

| 维度 | RAG | [[LLM Wiki 方法论]] |
|------|-----|-------------------|
| 知识存在方式 | 临时拼凑 | 持久结构化 |
| 每次查询 | 重新检索 | 直接查已有 Wiki |
| 知识积累 | 无 | 复利增长 |
| 交叉引用 | 不维护 | 自动建立 |
| 矛盾处理 | 无 | 标记和追踪 |

## 本项目中的 RAG 使用

虽然本项目以 [[LLM Wiki 方法论]] 为核心，但 [[MCP Server]] 的 `simple_vector_search` 本质上仍是 RAG 方案。LLM Wiki 方法论通过在 RAG 之上增加结构化知识层来弥补纯 RAG 的不足。

## 来源参考

- [[opencode_chromadb_rag_guide]] — RAG 在 OpenCode 中的实现指南 使用-关系（RAG**使用**opencode_chromadb_rag_guide）

## 相关页面

- [[LLM Wiki 方法论]] — 超越 RAG 的新方案 使用-关系（RAG**使用**LLM Wiki 方法论）
- [[opencode_chromadb_rag_guide]] — 本项目使用的 RAG 向量数据库 使用-关系（RAG**使用**opencode_chromadb_rag_guide）
- [[知识编译]] — LLM Wiki 替代 RAG 的核心机制 影响-关系（知识编译**影响**了RAG）
- [[嵌入模型]] — RAG 检索依赖嵌入模型 基于-关系（RAG**基于**嵌入模型）
- [[推理模型]] — RAG 生成答案依赖推理模型 使用-关系（RAG**使用**推理模型）
- [[Ingest]] — Ingest 是将 RAG 原始资料升级为 Wiki 知识的过程 使用-关系（RAG**使用**Ingest）
- [[MCP Server]] — 提供 RAG 向量搜索能力 使用-关系（RAG**使用**MCP Server）

<!-- ai-link:start -->
## 🔗 相关笔记

- [[RAG vs 知识编译]] — 比较 RAG 与知识编译的区别

<!-- ai-link:end -->
- [[synthesis_horizon_tracker]] — 相关内容补充
- [[控制面板]] — 相关内容补充