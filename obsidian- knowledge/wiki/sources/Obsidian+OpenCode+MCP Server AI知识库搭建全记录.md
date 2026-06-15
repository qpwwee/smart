---
title: Obsidian+OpenCode+MCP Server AI知识库搭建全记录
created: 2026-05-11
updated: 2026-05-24
tags: [source, obsidian, opencode, mcp-server, ollama]
type: source
source: raw/sources/Obsidian+OpenCode+MCP Server AI知识库搭建全记录.md
---
# Obsidian+OpenCode+MCP Server AI知识库搭建全记录

> 本项目知识库从方案选型到插件安装配置的完整过程记录

## 来源信息

- 类型：项目实践记录
- 日期：2026-05-09
- 状态：进行中

## 核心要点

1. **最终架构**：Obsidian + OpenCode + MCP Server + Ollama，Obsidian 为前端，MCP Server 提供向量搜索，OpenCode 通过 SSE 连接，Ollama 提供本地模型
2. **关键问题**：MCP Server 插件目录名必须与 community-plugins.json 注册 id 一致（`obsidian-mcp-server` → `mcp-server`）；autoIndex 字段不存在，需在 GUI 手动触发索引
3. **SSE 连接方式**：MCP Server 不能独立运行，必须通过 SSE（localhost:3003）连接
4. **GitHub 网络问题**：国内无代理环境需用 ghproxy 镜像下载插件
5. **core-plugins.json**：安装社区插件后必须添加 `"community-plugins": true`

## 关键引用

> Obsidian 根据目录名匹配插件，不是 manifest.json 中的 id

> 插件代码中只有 autoStart（自动启动 MCP 服务器），没有 autoIndex（自动索引）

## 相关页面

- [[Obsidian]] — 知识管理前端 基于-关系（Obsidian+OpenCode+MCP Server AI知识库搭建全记录**基于**Obsidian）
- [[OpenCode]] — AI 编码助手 基于-关系（Obsidian+OpenCode+MCP Server AI知识库搭建全记录**基于**OpenCode）
- [[MCP Server]] — 核心插件 基于-关系（Obsidian+OpenCode+MCP Server AI知识库搭建全记录**基于**MCP Server）
- [[Ollama]] — 本地模型平台 使用-关系（Obsidian+OpenCode+MCP Server AI知识库搭建全记录**使用**Ollama）
- [[向量搜索]] — MCP Server 核心能力 使用-关系（Obsidian+OpenCode+MCP Server AI知识库搭建全记录**使用**向量搜索）

<!-- ai-link:start -->
## 🔗 相关笔记

- [[opencode_chromadb_rag_guide]] — 介绍使用 MCP 与 OpenCode 搭建 RAG 的完整流程，补充技术细节。 使用-关系（Obsidian+OpenCode+MCP Server AI知识库搭建全记录**使用**opencode_chromadb_rag_guide）

<!-- ai-link:end -->