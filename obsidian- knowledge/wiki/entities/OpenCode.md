---
title: OpenCode
created: 2026-05-10
updated: 2026-06-09
tags: [entity, tool, ai-assistant]
type: entity
---
# OpenCode

> 本项目中充当「Wiki 程序员」角色的 AI 编码助手

## 身份

- AI 编码助手，支持 MCP 协议
- 通过 SSE 连接 [[Obsidian]] 的 [[MCP Server]]
- 本项目中的角色：**Wiki 维护者 + 知识编译器**

## 在本项目中的角色

按照 Karpathy 方法论：
- **Obsidian 是 IDE**
- **OpenCode 是程序员**
- **Wiki 是代码库**

## 配置

- 配置文件：`~/.config/opencode/opencode.json`
- 本地模型：[[Ollama]]（嵌入用 qwen3-embedding:4b；推理模型已迁移至云端）
- 模型档位：支持多档思考深度，**Ctrl+T** 循环切换（详见 [[推理模型#思考深度档位（Variants）与温度设置]]）
- MCP 连接：[[MCP Server]] (SSE, localhost:3003)

## 自我改善能力

OpenCode 通过以下方式不断优化：
1. 每次回答问题后自省 → 检查知识完整性
2. 发现知识缺口 → 记录到 [[log]] 并建议补充
3. 好的问答回存 Wiki → 知识复利增长
4. 定期 代码检查（Lint） → 维护知识库健康

## 来源参考

- [[Obsidian+OpenCode+MCP Server AI知识库搭建全记录]] — OpenCode 的配置与集成过程
- [[opencode_chromadb_rag_guide]] — OpenCode 与 ChromaDB RAG 的集成指南
- [[python3脚本构建全局向量索引知识库：]] — OpenCode 使用的向量化脚本

## 相关页面

- [[Obsidian]] — 配合使用的知识管理工具 使用-关系（OpenCode**使用**Obsidian）
- [[MCP Server]] — 连接 Obsidian 的桥梁 使用-关系（OpenCode**使用**MCP Server）
- [[Ollama]] — 提供本地模型能力 使用-关系（OpenCode**使用**Ollama）
- [[LLM Wiki 方法论]] — OpenCode 遵循的工作方法论 使用-关系（OpenCode**使用**LLM Wiki 方法论）
- [[推理模型]] — OpenCode 使用的 LLM 使用-关系（OpenCode**使用**推理模型）
- [[SSE 连接]] — OpenCode 连接 MCP Server 的方式 使用-关系（OpenCode**使用**SSE 连接）
- [[Ingest]] — OpenCode 执行的摄入操作 使用-关系（OpenCode**使用**Ingest）
- [[知识编译]] — OpenCode 作为知识编译器的角色 使用-关系（OpenCode**使用**知识编译）
- [[向量搜索]] — OpenCode 查询知识的方式 使用-关系（OpenCode**使用**向量搜索）
- [[OpenCode API Bridge]] — 将 OpenCode 模型能力通过 OpenAI/Ollama 兼容 API 暴露给第三方工具 基于-关系（OpenCode 模型能力**基于**OpenCode）

<!-- ai-link:start -->
## 🔗 相关笔记

- [[Obsidian+OpenCode+MCP Server AI知识库搭建全记录]] — 详细记录 OpenCode 与 Obsidian、MCP Server 的集成流程，直接支持配置与部署
- [[AI 知识库架构综述]] — 提供系统整体架构与 Karpathy 方法论的概览，便于快速定位各组件关系

<!-- ai-link:end -->