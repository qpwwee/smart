---
title: Transformer
created: 2026-05-11
updated: 2026-05-24
tags: [concept, transformer, architecture, deep-learning]
type: concept
related_entities: [深度学习, 大语言模型, 神经网络]
---
# Transformer

> 基于注意力机制的序列建模架构，是大语言模型的核心基础

## 定义

Transformer 是 2017 年 Google 在论文《Attention Is All You Need》中提出的深度学习架构，完全基于注意力机制（Attention），摒弃了传统的 RNN 和 CNN 结构。

## 核心组件

### 自注意力机制（Self-Attention）
- **Query**：查询向量
- **Key**：键向量
- **Value**：值向量
- **注意力权重**：通过 Q-K 点积计算相似度

### 架构组成
| 组件 | 说明 |
|------|------|
| 编码器 | 处理输入序列，提取特征 |
| 解码器 | 生成输出序列 |
| 多头注意力 | 并行学习不同子空间表示 |
| 前馈网络 | 逐位置的非线性变换 |
| 位置编码 | 注入序列位置信息 |

## 发展变体

| 模型 | 机构 | 特点 |
|------|------|------|
| BERT | Google | 仅编码器，双向理解 |
| GPT | OpenAI | 仅解码器，自回归生成 |
| T5 | Google | 编码器-解码器，统一框架 |
| ViT | Google | Transformer 用于图像 |

## 在本项目中的角色

Transformer 是 [[大语言模型]] 的核心架构：
- [[推理模型]] 使用 Transformer 解码器 影响-关系（推理模型**影响**了Transformer）
- [[嵌入模型]] 使用 Transformer 编码器 影响-关系（嵌入模型**影响**了Transformer）
- [[深度学习]] 的最新突破 是-关系（Transformer**是**深度学习的子概念/应用）

## 相关页面

- [[深度学习]] — Transformer 是深度学习的重大突破 是-关系（Transformer**是**深度学习的子概念/应用）
- [[神经网络]] — Transformer 是神经网络的新架构 是-关系（Transformer**是**神经网络的子概念/应用）
- [[大语言模型]] — LLM 基于 Transformer 架构 影响-关系（大语言模型**影响**了Transformer）
- [[嵌入模型]] — 嵌入模型使用 Transformer 影响-关系（嵌入模型**影响**了Transformer）
- [[推理模型]] — 推理模型使用 Transformer 影响-关系（推理模型**影响**了Transformer）

## 来源参考

- 《Attention Is All You Need》- Google Brain 2017
- [[机器学习_周志华_完整版]] — Transformer 理论基础

<!-- ai-link:start -->
## 🔗 相关笔记

- [[深度学习]] — Transformer 是深度学习的重要架构 是-关系（Transformer**是**深度学习的子概念/应用）
- [[大语言模型]] — 所有现代 LLM 都基于 Transformer 影响-关系（大语言模型**影响**了Transformer）
- [[神经网络]] — Transformer 是新型神经网络架构 是-关系（Transformer**是**神经网络的子概念/应用）
