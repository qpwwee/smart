---
title: OpenCode API Bridge
created: 2026-05-21
updated: 2026-06-09
tags: [concept, tool, bridge, api]
type: concept
---

# OpenCode API Bridge

> 将 OpenCode 当前对话模型的 LLM 能力通过 OpenAI/Ollama 兼容 API 暴露给第三方工具和插件的桥接服务器。

## 概述

OpenCode API Bridge 是一个 Node.js 中间件服务器（端口 11555），它作为翻译层，将行业标准 API 格式（OpenAI 兼容、Ollama 原生）转换为 OpenCode 内部协议（通过 @opencode-ai/sdk 与 OpenCode 后台通信）。这使得所有原本只支持 OpenAI/Ollama 的工具可以透明地使用 OpenCode 的当前对话模型（deepseek-v4-flash-free）。

## API 端点

| 方法 | 路径 | 格式标准 | 用途 |
|------|------|---------|------|
| POST | `/v1/chat/completions` | OpenAI 兼容 | 聊天补全（→ OpenCode） |
| POST | `/api/chat` | Ollama 原生 | 聊天（→ OpenCode） |
| POST | `/v1/embeddings` | OpenAI 兼容 | 嵌入向量（→ 本地 Ollama qwen3-embedding:4b） |
| GET | `/v1/models` | OpenAI 兼容 | 模型列表 |
| GET | `/health` | 自定义 | 健康检查 |

## 架构

```
第三方工具 / Obsidian 插件
  ↓ OpenAI / Ollama 标准 API
OpenCode API Bridge (port 11555)
  ↓ @opencode-ai/sdk 内部协议
OpenCode 后台 (port 4096)
  ↓
deepseek-v4-flash-free（当前对话模型）
```

- **聊天请求**（`/v1/chat/completions`、`/api/chat`）通过 @opencode-ai/sdk 代理到 OpenCode
- **嵌入请求**（`/v1/embeddings`）直接代理到本地 Ollama（qwen3-embedding:4b，2560 维），因为 OpenCode 自身没有嵌入 API

## 使用场景

1. **ai-auto-link 插件**：从 ollama 模式（gemma4-cn:latest）切换为 cloud 模式，指向 bridge
2. **vault-health-checker 插件**：将硬编码的 Ollama base URL 改为 bridge 地址
3. 任何支持 OpenAI/Ollama API 的工具都可以透明使用 OpenCode 模型

## 部署

- **进程管理**：LaunchAgent `~/Library/LaunchAgents/com.opencode.bridge.plist`
- **自动启动**：用户登录时自动运行，崩溃自动恢复
- **手动启动**：`node /Users/pon/Documents/opencode-api-bridge/server.js 11555`

## 限制

- 仅支持非流式请求（`stream: false`），流式响应未测试
- 向量嵌入仍需本地 Ollama 实例（端口 11434）
- 依赖 OpenCode 后台运行（端口 4096）

## 参考

- [[OpenCode]] — OpenCode 是本 Bridge 的后端引擎 基于-关系（Bridge**基于**OpenCode 的模型能力）
- [[MCP Server]] — MCP 协议与 Bridge 的 API 代理是互补机制 影响-关系（Bridge**扩展**了 MCP 无法覆盖的协议范围）
- [[Ollama]] — 嵌入向量代理到本地 Ollama 使用-关系（Bridge**使用**Ollama 的嵌入模型）
- [[ai-auto-link]] — ai-auto-link 是 Bridge 的主要消费者 使用-关系（ai-auto-link**使用**Bridge）
- [[SSE 连接]] — 与 OpenCode 后台的底层通信机制 基于-关系（Bridge**基于**SSE 会话与 OpenCode 通信）

<!-- ai-link:start -->
## 🔗 相关笔记

- [[OpenCode]] — Bridge 的后端引擎，提供 deepseek-v4-flash-free 模型能力
- [[Obsidian]] — Bridge 的主要使用环境，支持 Obsidian 插件统一使用对话模型

<!-- ai-link:end -->
