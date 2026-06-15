---
title: LLM (Large Language Model)
created: 2026-05-22
updated: 2026-05-22
tags: [concept, llm, ai, language-model, foundation-model]
type: concept
---

# LLM (Large Language Model)

> 大规模语言模型——基于海量文本预训练的深度学习模型，具备自然语言理解与生成、推理、编程等涌现能力

## 定义

LLM（Large Language Model，大语言模型）是指基于 [[Transformer]] 架构、在 Web-scale 文本数据上进行自监督预训练的深度学习模型，参数规模通常在十亿（Billion）到数万亿（Trillion）之间。当模型规模跨越某个阈值后，会涌现出小模型不具备的**推理能力**、**指令遵循**、**上下文学习（In-Context Learning）**、**思维链（Chain-of-Thought）** 等高级能力。

LLM 是当代 [[人工智能]] 的核心引擎，也是本知识库中 [[OpenCode]]、[[Ollama]]、[[MCP Server]] 等工具运转的底层基础。详见中文实体页 [[大语言模型]]（LLM **是** 大语言模型的英文缩写）。

## 核心涌现能力

| 能力 | 描述 | 首次涌现规模 |
|------|------|-------------|
| **In-Context Learning** | 通过 Prompt 提供示例即可执行新任务，无需参数更新 | ~1B+ |
| **Instruction Following** | 理解自然语言指令并按意图执行 | ~7B+ |
| **Chain-of-Thought (CoT)** | 生成中间推理步骤解决复杂逻辑问题 | ~70B+ |
| **Code Generation** | 理解编程语言并生成可执行代码 | ~70B+ |
| **Multi-turn Dialogue** | 保持上下文连贯的多轮对话能力 | ~70B+ |
| **Tool Calling** | 自主决定调用外部工具/API 完成子任务 | ~70B+ |

## 技术架构

### 模型架构

| 组件 | 说明 | 代表方案 |
|------|------|---------|
| 基础架构 | 仅解码器（Decoder-only）Transformer | GPT 系列、Llama、Qwen |
| 分词器 | 子词分词，平衡词表大小与编码效率 | BPE、SentencePiece、BBPE |
| 位置编码 | 注入序列位置信息 | RoPE（旋转位置编码）、ALiBi |
| 注意力机制 | 多头注意力优化 | GQA（分组查询注意力）、MQA（多查询注意力） |
| 激活函数 | 非线性变换 | SwiGLU、GeGLU |
| 归一化 | 稳定深层网络训练 | RMSNorm、LayerNorm |
| MoE | 混合专家，仅激活部分参数 | DeepSeek-MoE、Mixtral |

### 训练管线

LLM 的训练遵循**三阶段范式**：

1. **Pre-training（预训练）** — 在大规模语料上进行自监督学习（Next Token Prediction），学习语言知识、事实知识和推理模式。耗费最多算力（数万 GPU 小时）。
2. **Post-training（后训练）** — 包括 SFT（监督微调，Supervised Fine-Tuning）使模型遵循指令、RLHF（基于人类反馈的强化学习，Reinforcement Learning from Human Feedback）使输出对齐人类偏好。
3. **Alignment（对齐）** — 确保模型输出安全、有用、诚实。主流方法：RLHF、DPO、Constitutional AI。

### 推理优化

| 技术 | 原理 | 加速比 |
|------|------|--------|
| KV Cache | 缓存历史 Key-Value 避免重复计算 | 2-5x |
| Speculative Decoding | 小模型草稿 + 大模型验证 | 2-3x |
| Flash Attention | 融合注意力计算，减少显存 IO | 2-4x |
| Quantization | 降低权重精度（INT8/INT4/FP8） | 2-4x+ |
| Structured Pruning | 移除冗余参数 | 1.5-3x |

## 关键挑战

### 规模与成本

- **训练成本**：前沿模型训练需数千到数万 GPU 天，单次训练成本达千万至亿美元
- **推理成本**：大参数模型推理延迟和显存消耗高，推动量化、蒸馏、MoE 等优化
- **能源消耗**：大规模训练和推理的碳排放成为环境关注点

### 可信与安全

- **幻觉（Hallucination）** — 模型生成看似合理但事实错误的内容
- **有毒内容** — 需要复杂的 safety guardrail 来过滤有害输出
- **偏见放大** — 训练数据中的社会偏见可能被模型放大（详见 [[算法偏见]]）
- **对抗攻击** — Prompt Injection、Jailbreak 等手段操纵模型行为

### 评估难题

LLM 的评估缺乏标准化基准。传统 NLP 评测（如 GLUE、SuperGLUE）对大模型区分度不足，新基准（MMLU、BIG-bench、HumanEval）仍在演进中。指令遵循、安全性、诚实性的评估尤其困难。

## 应用范式

| 范式 | 描述 | 代表 | 本知识库应用 |
|------|------|------|-------------|
| **Prompt Engineering** | 通过精心设计的 Prompt 引导模型行为 | Chain-of-Thought、Few-shot | [[推理模型]] 沟通方式 |
| **RAG** | 检索增强生成：外部知识库 + LLM 生成 | [[RAG]] 管线 | MCP Server 提供检索增强 |
| **Fine-tuning** | 在特定领域数据上继续训练 | LoRA、QLoRA | [[本地模型开发]] |
| **Agent/Tool Use** | LLM 自主调用工具完成复杂任务 | Function Calling、MCP | [[MCP Server]]、[[A2A 协议]] |
| **知识编译** | 将 LLM 查询转化为结构化知识库 | [[LLM Wiki 方法论]] | 本知识库的核心方法论 |

## 模型生态概览

### 闭源模型

| 模型 | 机构 | 特点 |
|------|------|------|
| GPT-4 / GPT-4o | OpenAI | 多模态，最强综合能力 |
| Claude 3/4 | Anthropic | 长上下文，安全对齐领先 |
| Gemini | Google | 原生多模态，100万+ token 上下文 |
| DeepSeek | 深度求索 | MoE 架构，推理成本低 |

### 开源模型

| 模型 | 机构 | 参数 | 特点 |
|------|------|------|------|
| Llama 3 | Meta | 8B-405B | 社区生态最活跃 |
| Qwen 2.5 | 阿里 | 0.5B-72B | 中文能力领先 |
| Mistral / Mixtral | Mistral AI | 7B-8x22B | 小模型效率高 |
| Gemma | Google | 2B-27B | 轻量、安全 |
| DeepSeek-V2/V3 | 深度求索 | 16B-671B | MoE 极致性价比 |
| Command R+ | Cohere | 104B | 企业级 RAG 优化 |

## 在本知识库中的角色

LLM 是本知识库的**基础设施和核心研究对象**：

- [[OpenCode]] **使用** LLM 作为推理引擎执行编码辅助、知识编译、查询回答
- [[Ollama]] **提供** 本地 LLM 推理运行环境
- [[MCP Server]] **使用** 嵌入模型（一种 LLM 应用形态）构建向量索引
- [[推理模型]] **是** LLM 的一种应用形态，侧重逻辑推理和对话
- [[嵌入模型]] **是** LLM 的另一种应用形态，侧重文本向量化
- [[LLM Wiki 方法论]] **基于** LLM 的查询和生成能力来维护知识库
- [[本地模型开发]] **使用** LLM 架构作为学习和开发对象
- [[大语言模型]] **是** LLM 的中文完整实体页，提供更详尽的本地项目视角

## 相关页面

- [[大语言模型]] — 是-关系（LLM **是** 大语言模型的英文缩写条目）
- [[Transformer]] — 基于-关系（LLM **基于** Transformer 架构）
- [[深度学习]] — 是-关系（LLM **是** 深度学习的子领域）
- [[自然语言处理]] — 是-关系（LLM **是** 自然语言处理的最新发展阶段）
- [[机器学习]] — 使用-关系（LLM **使用** 机器学习训练方法）
- [[强化学习]] — 使用-关系（LLM **使用** 强化学习进行 RLHF 对齐训练）
- [[人工智能]] — 是-关系（LLM **是** 人工智能的核心组成部分）
- [[RAG]] — 影响-关系（RAG 技术 **拓展了** LLM 的应用边界）
- [[推理模型]] — 是-关系（推理模型 **是** LLM 的重要应用形态）
- [[嵌入模型]] — 是-关系（嵌入模型 **是** LLM 的另一种应用形态）
- [[神经网络]] — 是-关系（LLM **是** 神经网络的一种大规模实现）
- [[MCP Server]] — 使用-关系（MCP Server **使用** LLM 嵌入模型构建索引）
- [[OpenCode]] — 使用-关系（OpenCode **使用** LLM 作为推理引擎）
- [[Ollama]] — 使用-关系（Ollama **提供** 本地 LLM 运行环境）
- [[知识编译]] — 影响-关系（LLM 的发展 **催生了** 知识编译方法论）
- [[算法偏见]] — 影响-关系（LLM **需要防范** 算法偏见）
- [[人工智能伦理]] — 影响-关系（LLM **需要遵守** 人工智能伦理规范）

## 来源参考

- [[大语言模型]] — LLM 的中文完整实体页，涵盖本项目中的详细配置和角色
- [[Obsidian+OpenCode+MCP Server AI知识库搭建全记录]] — 详述 LLM 在本项目中的工程集成
- [[机器学习_周志华_完整版]] — LLM 的机器学习理论基础
- [[生命3.0]] — AI（含 LLM）对人类社会影响的哲学探讨
- [[llm-wiki]] — LLM 用于知识库维护的方法论原文

<!-- auto-fresh: 2026-05-22 -->
