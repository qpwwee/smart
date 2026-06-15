---
title: A2A 协议
created: 2026-05-13
updated: 2026-05-24
tags: [concept, a2a, protocol, agent-communication, multi-agent]
type: concept
---
# A2A 协议（Agent-to-Agent Protocol）

> 让不同框架、不同供应商的 AI 智能体能够互相发现、协商、委派任务并交换结果的开放协议。2026 年 4 月达到 v1.0 稳定版，由 Linux Foundation 的 AAIF 管理。

## 定义

A2A（Agent-to-Agent）协议是 Google 于 2025 年 4 月发布、2025 年 6 月捐赠给 Linux Foundation 的开放标准，用于解决多智能体系统中智能体间的通信和协作问题。截至 2026 年 4 月，已有 **150+ 组织** 在生产环境中使用，SDK 覆盖 Python/JavaScript/Java/Go/.NET 五种语言。

## 核心概念

### 1. Agent Card（智能体名片）
每个 A2A 兼容智能体发布一个 `/.well-known/agent-card.json`，描述：
- 身份和端点
- 技能列表（能做什么）
- 输入/输出格式
- 认证要求

类比：机器可读的简历，让其他智能体知道"你能帮我做什么"。

### 2. Task（任务）
A2A 的基本工作单元。一个智能体创建 Task 并分配给另一个智能体，Task 包含输入、元数据和状态（进行中/已完成/失败）。

### 3. 传输层
基于 JSON-RPC + SSE（Server-Sent Events），与 MCP 共享类似的通信模式。v1.0 新增 gRPC 支持。

## A2A vs MCP

| 维度 | MCP | A2A |
|------|-----|-----|
| **方向** | 智能体 → 工具（垂直） | 智能体 → 智能体（水平） |
| **类比** | USB — 外设接入电脑 | TCP/IP — 电脑间通信 |
| **解决** | 工具接入标准化 | 智能体协作标准化 |
| **关系** | 上下级 | 对等 |
| **卡片** | 工具描述 | Agent Card（能力描述） |

**两者互补**：一个智能体用 MCP 操作工具，用 A2A 与其他智能体协作。

## 在本项目中的潜力

目前 OpenCode (v1.14.48) 已支持 Agent Teams（扁平团队架构），但团队内通信是内部的。A2A 可扩展的场景： [[多智能体 vs 单一智能体 适用场景对比]]

| 场景 | 说明 |
|------|------|
| **跨工具协作** | OpenCode Agent → A2A → Claude Code Agent 做代码审查 |
| **专业化分流** | build-agent 遇到图像问题 → A2A → 专业的视觉分析智能体 |
| **后台巡逻** | lint-agent 通过 A2A 定时唤醒 ingest-agent 处理新资料 |

当前 OpenCode Agent Teams 使用扁平主导-队友模式，与 A2A 的编排器模式兼容。当 OpenCode 原生支持 A2A 时可直接集成。

## 相关页面

- [[MCP Server]] — MCP **是** A2A 的互补协议（智能体-工具 vs 智能体-智能体）
- [[SSE 连接]] — A2A **使用** SSE 作为传输层
- [[多智能体系统]] — A2A **是**多智能体系统的通信标准
- [[智能体]] — A2A **是**智能体间通信的协议
- [[OpenCode]] — OpenCode Agent Teams **与** A2A 架构兼容（使用-关系）
- [[大语言模型]] — 智能体**使用**大语言模型，A2A 传输任务结果

<!-- ai-link:start -->
## 🔗 相关笔记

- [[MCP vs A2A vs 传统API]] — 比较 A2A、MCP 与传统 REST，阐明三者的区别与适用场景
- [[多智能体 vs 单一智能体 适用场景对比]] — 提供多智能体与单一智能体的适用场景对照，补充 A2A 的使用场景分析

<!-- ai-link:end -->
- [[synthesis_horizon_tracker]] — 相关内容补充
- [[控制面板]] — 相关内容补充