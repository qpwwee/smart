---
title: Obsidian
created: 2026-05-10
updated: 2026-06-09
tags: [entity, tool, knowledge-management]
type: entity
---
# Obsidian

> 本项目的知识管理前端和可视化 IDE

## 身份

- 本地 Markdown 笔记工具
- 支持双向链接 `[[]]` 语法
- 关系图谱视图
- 丰富的插件生态

## 在本项目中的角色

按照 Karpathy 方法论：**Obsidian 是 IDE**
- 人类通过 Obsidian 浏览和阅读 Wiki
- 图谱视图展示知识节点间的链接关系和方向
- MCP Server 插件提供 AI 工具接口

## 关键插件

| 插件 | 用途 |
|------|------|
| [[MCP Server]] | 提供 AI 工具接口（向量搜索、文件读写） |
| BRAT | 社区插件管理 |
| Markitdown | PDF → Markdown 转换 |
| obsidian-opencode | 嵌入 OpenCode Web [[OpenCode]] UI |

## 版本信息

当前安装版本：**v1.12.7**（2026-03-23 发布）

### v1.12.x 核心新特性
| 特性 | 说明 |
|------|------|
| **Obsidian CLI** | 官方命令行界面，捆绑二进制文件，终端交互更快（替代 Electron binary 调用方式） |
| **Image resizing** | 拖拽调整图片大小（Live Preview 中） |
| **自动附件清理** | 删除文件时询问是否同时删除附件 |
| **Bases 增强** | 搜索工具栏、拖拽导入、右键菜单 |
| **Canvas 反向链接** | Canvas 文件的链接现在出现在反向链接视图和图谱中 |
| **Electron v39.8.3** | 底层框架升级 |

建议保持版本更新以获取最新安全补丁和性能优化。

## Vault 配置

- 路径：`/Users/pon/Documents/obsidian- knowledge/`
- [[MCP Server]] 端口：3003（SSE 模式） — 使用-关系（Obsidian**使用**MCP Server）
- 嵌入模型：qwen3-embedding:4b（通过 [[Ollama]]，已从 0.6b 升级）

## 来源参考

- [[Obsidian+OpenCode+MCP Server AI知识库搭建全记录]] — 记录 Obsidian 在本项目中的搭建过程

## 相关页面

- [[OpenCode]] — 配合使用的 AI 助手 影响-关系（OpenCode影响了Obsidian的使用方式）
- [[MCP Server]] — 核心插件 使用-关系（Obsidian使用MCP Server）
- [[LLM Wiki 方法论]] — Obsidian 在方法论中的角色 使用-关系（Obsidian使用LLM Wiki 方法论）
- [[向量搜索]] — MCP Server 提供的核心能力 使用-关系（Obsidian使用向量搜索）
- [[Ollama]] — 为 MCP Server 提供嵌入模型 使用-关系（Obsidian使用Ollama）
- [[SSE 连接]] — MCP Server 通过 SSE 对外暴露接口 使用-关系（Obsidian使用SSE 连接）
- [[嵌入模型]] — Obsidian 索引使用的嵌入模型 使用-关系（Obsidian使用嵌入模型）
- [[知识编译]] — Obsidian 是知识编译的展示层 使用-关系（Obsidian使用知识编译）

