---
title: MCP Server
created: 2026-05-10
updated: 2026-06-09
tags: [entity, tool, mcp, plugin]
type: entity
---
# MCP Server

> 连接 [[Obsidian]] 和 [[OpenCode]] 的桥梁

## 身份

- Obsidian 社区插件（作者：Minhao Zhang）
- 在 Obsidian 内部运行 MCP 服务器
- 通过 SSE 协议向外部提供工具接口 [[SSE 连接]]

## 提供的工具

| 工具 | 说明 |
|------|------|
| `simple_vector_search` | 语义向量搜索（最常用） |
| `count_entries` | 统计索引条目数 |
| `list_files` | 列出 Vault 文件 |
| `read_file` | 读取文件内容 |
| `create_file` | 创建文件 |
| `edit_file` | 编辑文件指定行 |
| `delete_file` | 删除文件 |
| `create_folder` | 创建文件夹 |
| `delete_folder` | 删除文件夹 |

## 配置

- 端口：3003
- 连接方式：SSE（Server-Sent Events）
- 嵌入模型：qwen3-embedding:4b（已从 0.6b 升级）
- 向量存储：Orama（本地 JSON）
- chunkSize：1000，chunkOverlap：200

## 注意事项

- 不能独立运行，必须在 Obsidian 内部启动
- `autoIndex` 字段无效，需手动触发索引
- 索引需在 Obsidian GUI 中触发：Cmd+P → "Index Vault"

## 来源参考

- [[Obsidian+OpenCode+MCP Server AI知识库搭建全记录]] — MCP Server 的安装配置过程

## 相关页面

- [[Obsidian]] — 运行 MCP Server 的宿主 基于-关系（MCP Server**基于**Obsidian）
- [[OpenCode]] — 通过 SSE 连接 MCP Server 基于-关系（MCP Server**基于**OpenCode）
- [[向量搜索]] — MCP Server 的核心能力 使用-关系（MCP Server**使用**向量搜索）
- [[Ollama]] — 提供嵌入模型 使用-关系（MCP Server**使用**Ollama）
- [[SSE 连接]] — OpenCode 连接 MCP Server 的通信协议 基于-关系（MCP Server**基于**SSE 连接）
- [[嵌入模型]] — MCP Server 使用的 qwen3-embedding:4b 使用-关系（MCP Server**使用**嵌入模型）
- [[RAG]] — MCP Server 是 RAG 检索的执行者 使用-关系（MCP Server**使用**RAG）
- [[Ingest]] — Ingest 操作依赖 MCP Server 查找相关页面 使用-关系（MCP Server**使用**Ingest）
