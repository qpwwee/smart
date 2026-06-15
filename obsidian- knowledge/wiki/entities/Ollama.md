---
title: Ollama
created: 2026-05-10
updated: 2026-06-09
tags: [entity, tool, llm, local-model]
type: entity
---
# Ollama

> 本地大模型运行平台

## 身份

- 本地 LLM 运行框架
- 支持 macOS / Linux / Windows
- 提供 OpenAI 兼容 API（localhost:11434）

## 本项目配置

| 模型 | 类型 | 大小 | 用途 |
|------|------|------|------|
| qwen3-embedding:4b | 嵌入 [[嵌入模型]] | ~2.5 GB | MCP Server 向量化（已升级替代 0.6b） |

## 关键配置

- `OLLAMA_KEEP_ALIVE=-1`：模型永久常驻，不空闲卸载
- 已配置 .zshrc + launchctl + ~/.ollama/ollama.env

## API 端点

- 推理：`http://localhost:11434/v1`
- 嵌入：`http://localhost:11434/api/embeddings`

## 来源参考

- [[Obsidian+OpenCode+MCP Server AI知识库搭建全记录]] — Ollama 在本项目中的配置过程
- [[opencode_chromadb_rag_guide]] — Ollama 与 ChromaDB RAG 的集成指南

## 相关页面

- [[OpenCode]] — 使用 Ollama 模型 使用-关系（Ollama**使用**OpenCode）
- [[MCP Server]] — 使用 Ollama 嵌入模型 使用-关系（Ollama**使用**MCP Server）
- [[向量搜索]] — 嵌入模型的应用场景 使用-关系（Ollama**使用**向量搜索）
- [[嵌入模型]] — Ollama 运行的 qwen3-embedding:4b 基于-关系（Ollama**基于**嵌入模型）
- [[RAG]] — Ollama 是 RAG 管线的基础引擎 使用-关系（Ollama**使用**RAG）
- [[Obsidian]] — Ollama 通过 MCP Server 服务 Obsidian 知识库 使用-关系（Ollama**使用**Obsidian）

<!-- ai-link:start -->
## 🔗 相关笔记

- [[推理模型]] — ~~gemma4:e4b 与 gpt-oss:20b~~ 已从 Ollama 卸载，不再本地部署推理模型 影响-关系（本地推理策略变化**影响**Ollama）
- [[嵌入模型]] — Ollama 运行的 qwen3-embedding:4b 用于向量化，是嵌入模型 基于-关系（Ollama**基于**嵌入模型）

<!-- ai-link:end -->