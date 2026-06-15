---
title: Python3脚本构建全局向量索引知识库
created: 2026-05-11
updated: 2026-05-24
tags: [source, script, python, vector-index]
type: source
source: raw/sources/python3脚本构建全局向量索引知识库：.md
---
# Python3脚本构建全局向量索引知识库

> 使用 Python3 脚本构建全局向量索引知识库的简要笔记

## 来源信息

- 类型：脚本笔记
- 大小：108 字节（极简内容）

## 核心要点

1. **执行路径**：`/Users/pon/Documents/知识库/scripts`
2. **运行命令**：`nohup python3 -u ingest.py import "文件路径" > _log.txt 2>&1 &`
3. **后台执行**：使用 nohup 后台运行，日志输出到 `_log.txt`

## 关键引用 [[opencode_chromadb_rag_guide]]

> nohup python3 -u ingest.py import "文件路径" > _log.txt 2>&1 &

## 备注 [[Obsidian+OpenCode+MCP Server AI知识库搭建全记录]]

此文件内容极其简短（仅一行命令），可能是完整文档的草稿或备忘。建议后续补充完整的脚本说明和使用方法。

## 相关页面 [[嵌入模型]]

- [[向量搜索]] — 向量索引的核心技术 使用-关系（python3脚本构建全局向量索引知识库：**使用**向量搜索）
- [[RAG]] — 向量索引的应用场景 使用-关系（python3脚本构建全局向量索引知识库：**使用**RAG）
- [[嵌入模型]] — 构建向量索引依赖嵌入模型 使用-关系（python3脚本构建全局向量索引知识库：**使用**嵌入模型）
- [[MCP Server]] — 替代方案：MCP Server 内置向量索引 使用-关系（python3脚本构建全局向量索引知识库：**使用**MCP Server）
- [[Ingest]] — 使用脚本执行 Ingest 操作 使用-关系（python3脚本构建全局向量索引知识库：**使用**Ingest）
- [[Ollama]] — 嵌入模型的运行平台 基于-关系（python3脚本构建全局向量索引知识库：**基于**Ollama）

<!-- ai-link:start -->
## 🔗 相关笔记

- [[opencode_chromadb_rag_guide]] — 涵盖使用 ChromaDB 搭建向量索引的完整流程，直接相关。 使用-关系（python3脚本构建全局向量索引知识库：**使用**opencode_chromadb_rag_guide）
- [[嵌入模型]] — 脚本需要嵌入模型生成向量，概念相互关联。 使用-关系（python3脚本构建全局向量索引知识库：**使用**嵌入模型）
- [[Obsidian+OpenCode+MCP Server AI知识库搭建全记录]] — 记录完整知识库搭建过程，补充背景与实践。 使用-关系（python3脚本构建全局向量索引知识库：**使用**Obsidian+OpenCode+MCP Server AI知识库搭建全记录）

<!-- ai-link:end -->