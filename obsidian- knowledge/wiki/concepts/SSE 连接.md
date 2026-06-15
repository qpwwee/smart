---
title: SSE 连接
created: 2026-05-11
updated: 2026-05-24
tags: [concept, sse, mcp, protocol]
type: concept
---
# SSE 连接

> Server-Sent Events，本项目 OpenCode 连接 MCP Server 的通信方式

## 定义

SSE（Server-Sent Events）是一种基于 HTTP 的单向实时通信协议。服务器可以持续向客户端推送事件流，客户端通过 EventSource API 接收。在本项目中，[[OpenCode]] 通过 SSE 连接 [[MCP Server]] 插件。

## 为什么使用 SSE

 [[Obsidian]][[MCP Server]] 插件运行在 [[Obsidian]] 内部，不能独立通过命令行启动。因此无法使用 MCP 标准的 stdio 传输方式，必须改用 SSE 远程连接：

| 传输方式 | 适用场景 | 本项目 |
|----------|----------|--------|
| stdio | 独立进程，命令行启动 | ❌ MCP Server 不能独立运行 |
| SSE | 已运行的服务，HTTP 连接 | ✅ 通过 localhost:3003 连接 |

## 本项目配置

```json
{
  "obsidian": {
    "type": "remote",
    "url": "http://localhost:3003/sse",
    "enabled": true
  }
}
```

- 端口：3003
- 协议：SSE + JSON-RPC over HTTP POST

## 连接流程

1. 建立 SSE 连接 → 获取 session URL
2. 发送 `initialize` 请求 → 返回协议版本和服务器信息
3. 后续请求通过 POST 发送 JSON-RPC 到 session URL
4. 响应通过 SSE 事件流 [[MCP Server]]返回

## 来源参考

- [[Obsidian+OpenCode+MCP Server AI知识库搭建全记录]] — SSE 连接的配置过程

## 相关页面

- [[MCP Server]] — SSE 连接的目标服务 是-关系（SSE 连接是MCP Server的子概念/应用）
- [[OpenCode]] — SSE 连接的发起客户端 使用-关系（SSE 连接使用OpenCode）
- [[Obsidian]] — MCP Server 的运行宿主 使用-关系（SSE 连接**使用**Obsidian）
- [[LLM Wiki 方法论]] — SSE 是实现此方法论的技术基础 使用-关系（SSE 连接**使用**LLM Wiki 方法论）
- [[嵌入模型]] — OpenCode 通过 SSE 调用嵌入模型 使用-关系（SSE 连接**使用**嵌入模型）
- [[推理模型]] — OpenCode 通过 SSE 触发推理模型 使用-关系（SSE 连接**使用**推理模型）
- [[向量搜索]] — SSE 通道上执行的向量搜索请求 使用-关系（SSE 连接**使用**向量搜索）
- [[Ingest]] — OpenCode 通过 SSE 执行 Ingest 操作 使用-关系（SSE 连接**使用**Ingest）

<!-- ai-link:start -->
## 🔗 相关笔记

- [[MCP Server]] — MCP Server 是 SSE 连接的服务器端。 是-关系（SSE 连接**是**MCP Server的子概念/应用）
- [[Obsidian]] — MCP Server 在 Obsidian 内部运行，Obsidian 是宿主 IDE。 使用-关系（SSE 连接**使用**Obsidian）
- [[Obsidian+OpenCode+MCP Server AI知识库搭建全记录]] — 记录完整的项目搭建过程，可进一步了解 SSE 连接背景。

<!-- ai-link:end -->
- [[synthesis_horizon_tracker]] — 相关内容补充