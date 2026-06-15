---
title: OpenCode ChromaDB RAG 指南
created: 2026-05-11
updated: 2026-05-24
tags: [source, opencode, chromadb, rag, ollama]
type: source
source: raw/sources/opencode_chromadb_rag_guide.md
---
# OpenCode ChromaDB RAG 指南

> 本地 RAG 知识库搭建指南，使用 ChromaDB [[opencode_chromadb_rag_guide]] + Ollama + OpenCode TUI

## 来源信息

- 类型：技术文档
- 核心技术栈：ChromaDB + Ollama + OpenCode

## 核心要点

1. **架构**：ChromaDB 作为向量数据库 + Ollama qwen3-embedding:0.6b 嵌入模型 + MCP 协议连接 OpenCode TUI
2. **两种索引脚本**：`index_project.py`（索引代码文件，按50行分块）和 `index_pdf.py`（索引 PDF 文档，按500字符分块）
3. **批量嵌入**：OllamaEmbedder 类实现批量嵌入（batch_size=32），含错误处理和零向量占位
4. **ChromaDB 持久化**：使用 PersistentClient，数据存储在 `~/.rag-knowledge/chroma_db/`
5. **OpenCode 集成**：通过 `chroma-mcp-server` 作为 MCP 服务连接，配置在 `opencode.json` 中

## 关键引用

> 使用 nohup 后台运行避免超时

> 首次运行索引可能需要较长时间（取决于数据量和模型速度）

## 相关页面

- [[RAG]] — 检索增强生成 使用-关系（opencode_chromadb_rag_guide**使用**RAG）
- [[向量搜索]] — 底层技术 使用-关系（opencode_chromadb_rag_guide**使用**向量搜索）
- [[OpenCode]] — AI 编码助手 使用-关系（opencode_chromadb_rag_guide**使用**OpenCode）
- [[Ollama]] — 嵌入模型提供者 基于-关系（opencode_chromadb_rag_guide**基于**Ollama）

<!-- ai-link:start -->
## 🔗 相关笔记

- [[opencode_chromadb_rag_guide]] — 相同主题的另一份指南

<!-- ai-link:end -->