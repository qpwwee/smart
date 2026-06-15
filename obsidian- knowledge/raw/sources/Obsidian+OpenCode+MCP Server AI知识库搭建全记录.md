# Obsidian + OpenCode + MCP Server AI 知识库搭建全记录

> 本文记录了从方案选型到插件安装配置的完整过程，包括所有遇到的问题和解决方案。

---

## 一、项目目标

构建本地 AI 知识库系统，实现：
- Obsidian 作为知识管理前端
- MCP Server 插件提供向量搜索能力
- OpenCode 作为 AI 编码助手，通过 MCP 协议连接 Obsidian 知识库
- Ollama 本地模型提供嵌入和推理能力

最终架构：**Obsidian + OpenCode + MCP Server + Ollama**

---

## 二、环境信息

| 组件 | 版本/信息 |
|------|-----------|
| 操作系统 | macOS Darwin 25.4.0 (arm64, Apple Silicon) |
| Ollama | v0.23.1 |
| OpenCode | v1.14.41 |
| Node.js | v22.16.0 |
| npm | 10.9.8 |
| Obsidian Vault 路径 | `/Users/pon/Documents/obsidian- knowledge`（⚠️ 路径含空格） |
| OpenCode 配置 | `~/.config/opencode/opencode.json` |

### Ollama 模型

| 模型 | 用途 | 大小 |
|------|------|------|
| `gemma4:e4b` | 推理模型 | 9163 MB |
| `gpt-oss:20b` | 推理模型 | 13154 MB |
| `qwen3-embedding:4b` | 嵌入模型 | 2381 MB |

### OpenCode 已有 MCP 配置

- `my-kb`：chroma 本地向量数据库（路径 `/opt/homebrew/bin/chroma-mcp-server`）
- `local-knowledge-base`：自定义 Python 脚本（路径 `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`）

---

## 三、插件安装流程

### 3.1 BRAT 插件 (v2.0.4)

**用途**：Obsidian 社区插件管理器，支持从 GitHub 安装非官方插件

**安装步骤**：
1. 创建插件目录 `.obsidian/plugins/obsidian42-brat/`
2. 下载 `main.js`、`manifest.json`、`styles.css`

**遇到的问题**：
- ❌ **GitHub 网络不通**：无法直接访问 `github.com`（无代理环境）
- ✅ **解决方案**：改用 **ghproxy 镜像** 下载，URL 格式：`https://ghproxy.com/https://github.com/...`
- 安装结果：main.js 83194 字节 ✅

**注册信息**：
- 目录名：`obsidian42-brat`
- community-plugins.json id：`obsidian42-brat`

---

### 3.2 Markitdown 插件 (v2.1.0)

**用 opencode_chromadb_rag_guide途**：文件格式转换（PDF→Markdown 等）

**安装步骤**：
1. 从 Obsidian 社区插件 release 渠道下载
2. 创建目录 `.obsidian/plugins/markitdown/`

**遇到的问题**：
- Agent Client 和 obsidian-opencode 插件的 GitHub release 路径不正确，下载到 9 字节的 Not Found 文件
- 改用 Obsidian 社区插件 release 渠道成功安装

**安装结果**：main.js 46212 字节 ✅

**实际使用**：通过 markitdown CLI 成功将两本 PDF 转换为 Markdown：
- 《中国文化概况》精简版.pdf (1.8MB → 63KB)
- 《生命3.0》.pdf (16MB → 755KB)
- 清理了水印，添加了 frontmatter，存入 vault

---

### 3.3 MCP Server 插件 (v1.1.0，作者 Minhao Zhang)

**用途**：在 Obsidian 内部运行 MCP 服务器，提供向量搜索、文件读写等工具

**安装步骤**：
1. 从 Obsidian 社区插件 release 渠道下载
2. 创建目录 `.obsidian/plugins/obsidian-mcp-server/`

**遇到的问题**：

#### 问题 A：目录名与注册 id 不一致

- **原因**：下载时目录名为 `obsidian-mcp-server`，但 `community-plugins.json` 中注册的 id 为 `mcp-server`
- **影响**：Obsidian 根据**目录名**匹配插件（而非 manifest.json 中的 id），名字对不上导致插件加载失败，影响整个插件系统
- **解决**：将目录从 `obsidian-mcp-server` 重命名为 `mcp-server`

#### 问题 B：不能独立运行

- **原因**：MCP Server 插件依赖 `obsidian` 模块，不能直接用 `node main.js` 独立启动
- **解决**：OpenCode 配置改为 **SSE 连接方式**，而非 local node 命令启动
  ```json
  {
    "obsidian": {
      "type": "remote",
      "url": "http://localhost:3003/sse",
      "enabled": true
    }
  }
  ```

#### 问题 C：索引为空（⚠️ 核心问题）

- **现象**：MCP Server 正常运行（端口 3003 监听），SSE 端点可用，但 `count_entries` 返回 0
- **原因**：`data.json` 中配置的 `autoIndex` 和 `watchForChanges` 字段在插件代码中**根本不存在**
- **关键发现**：插件代码中只有 `autoStart`（自动启动 MCP 服务器），没有 `autoIndex`（自动索引）
- **影响**：AI 知识库核心功能不可用——没有索引就没有搜索能力
- **解决**：需要在 Obsidian GUI 中手动触发索引
  - 方法一：`Cmd+P` → 输入 "Index Vault" → 回车
  - 方法二：设置 → 社区插件 → MCP Server ⚙️ → Dangerous Zone → Reindex 按钮

**安装结果**：main.js 1624348 字节 ✅

**MCP Server 配置** (`data.json`)：
```json
{
  "port": 3003,
  "startOnStartup": true,
  "modelProviderUrl": "http://localhost:11434/v1",
  "embeddingModel": "qwen3-embedding:4b",
  "apiKey": "ollama:localhost",
  "ignorePatterns": ".*/\n*.png\n*.jpg\n*.jpeg\n*.gif\n*.svg\n*.webp\n*.pdf",
  "chunkSize": 1000,
  "chunkOverlap": 200,
  "separators": ["\n\n", "\n", ".", "?", "!", " ", ""],
  "tools": {
    "simple_vector_search": true,
    "count_entries": true,
    "list_files": true,
    "read_file": true,
    "create_file": true,
    "edit_file": true,
    "delete_file": true,
    "create_folder": true,
    "delete_folder": true
  },
  "embeddingProvider": "ollama",
  "ollamaBaseUrl": "http://localhost:11434",
  "vectorStorePath": "mcp-vectors"
}
```

**MCP Server 提供的工具**（9个）：

| 工具名 | 说明 |
|--------|------|
| `simple_vector_search` | 语义向量搜索 |
| `count_entries` | 统计索引条目数 |
| `list_files` | 列出 Vault 文件 |
| `read_file` | 读取文件内容 |
| `create_file` | 创建文件 |
| `edit_file` | 编辑文件指定行 |
| `delete_file` | 删除文件 |
| `create_folder` | 创建文件夹 |
| `delete_folder` | 删除文件夹 |

---

### 3.4 obsidian-opencode 插件 (v1.0.0，作者 linxinhong)

**用途**：在 Obsidian 中嵌入 OpenCode Web 应用，同时作为独立的 MCP 服务器（名为 `obsidian-operator`）

**安装步骤**：
1. 最初尝试从 GitHub release 下载 → 失败（9字节 Not Found）
2. 从源码构建（`/tmp/obsidian-opencode-build`）→ 成功

**遇到的问题**：

#### 问题 A：GitHub release 路径不正确

- **原因**：作者未发布正式 release，GitHub release URL 返回 404
- **解决**：从源码仓库 clone 后用 esbuild 构建

#### 问题 B：端口 4096 未监听

- **原因**：插件通过 `spawn` 执行 `opencode web --port 4096` 启动 OpenCode Web 服务器，但未成功启动
- **可能原因**：
  - 插件首次加载时 `opencodePath` 指向默认占位路径 `/path/to/opencode/bin/opencode`
  - 后续虽在 `data.json` 中更新为 `/usr/local/bin/opencode`，但可能需要重启 Obsidian
- **影响**：obsidian-opencode 插件是**非核心组件**，主要用于嵌入 OpenCode Web UI 视图
- **状态**：暂不处理，核心功能（MCP 搜索）不依赖此插件

**安装结果**：main.js 1608937 字节 ✅

**插件配置** (`data.json`)：
```json
{
  "serverPort": 4096,
  "opencodePath": "/usr/local/bin/opencode",
  "serverPath": "/usr/local/bin/opencode",
  "autoStart": true,
  "startupTimeout": 30000,
  "enableLogging": true
}
```

---

## 四、Obsidian 配置修改

### 4.1 community-plugins.json

```json
[
  "obsidian42-brat",
  "mcp-server",
  "obsidian-opencode",
  "markitdown"
]
```

> ⚠️ **重要**：此列表中的 id 必须与 `.obsidian/plugins/` 下的**目录名**完全一致！

### 4.2 core-plugins.json 修改

**问题**：首次安装社区插件后，Obsidian 处于受限模式（Restricted Mode），所有社区插件无法加载。

**原因**：`core-plugins.json` 缺少 `"community-plugins": true` 字段。

**修复**：添加该字段：
```json
{
  ...
  "community-plugins": true
}
```

> ⚠️ **注意**：此修改在 Obsidian 运行时可能被覆盖。最可靠的方式是在 Obsidian GUI 中点击"Turn off Restricted Mode"按钮。

### 4.3 CLAUDE.md

在 Vault 根目录创建了 `CLAUDE.md`，为 AI 助手提供项目上下文信息。

---

## 五、OpenCode 配置更新

文件路径：`~/.config/opencode/opencode.json`

**关键变更**：添加 obsidian MCP 连接，使用 SSE 方式连接 localhost:3003

```json
{
  "mcp": {
    "my-kb": {
      "type": "local",
      "command": ["/opt/homebrew/bin/chroma-mcp-server", "--client-type", "persistent", "--data-dir", "/Users/pon/Documents/buddy_claw_my/.rag-knowledge/chroma_db"],
      "enabled": true
    },
    "local-knowledge-base": {
      "type": "local",
      "command": ["/Library/Frameworks/Python.framework/Versions/3.13/bin/python3", "/Users/pon/Documents/知识库/scripts/kb_mcp_server.py"],
      "enabled": true
    },
    "obsidian": {
      "type": "remote",
      "url": "http://localhost:3003/sse",
      "enabled": true
    }
  }
}
```

---

## 六、MCP Server SSE 连接验证

通过 Python 脚本验证了完整的 MCP SSE 交互流程：

1. ✅ 建立 SSE 连接 → 获取 session URL
2. ✅ 发送 `initialize` 请求 → 返回协议版本和服务器信息
3. ✅ 发送 `tools/list` → 返回 9 个可用工具
4. ✅ 发送 `count_entries` → 返回 `{"count": 0}`（索引为空）
5. ✅ 发送 `list_files` → 正确列出 Vault 文件
6. ❌ 发送 `simple_vector_search` → 返回空结果（因索引为空）

---

## 七、Vault 内容

| 文件 | 大小 | 说明 |
|------|------|------|
| `opencode_chromadb_rag_guide.md` | 14 KB | OpenCode + ChromaDB RAG 指南 |
| `中国文化概况（精简版）.md` | 63 KB | PDF 转换，已清理水印 |
| `欢迎.md` | 221 B | 欢迎页 |
| `生命3.0.md` | 755 KB | PDF 转换，已清理水印 |

---

## 八、问题汇总

| # | 问题 | 严重程度 | 状态 | 解决方案 |
|---|------|----------|------|----------|
| 1 | GitHub 网络不通 | 🔴 阻塞 | ✅ 已解决 | 使用 ghproxy 镜像下载 |
| 2 | 插件目录名与注册 id 不一致 | 🔴 阻塞 | ✅ 已解决 | 重命名目录 `obsidian-mcp-server` → `mcp-server` |
| 3 | core-plugins.json 缺少 community-plugins | 🔴 阻塞 | ✅ 已解决 | 添加 `"community-plugins": true` |
| 4 | MCP Server 索引为空 | 🔴 核心 | ⏳ 待处理 | 需在 Obsidian GUI 手动触发索引 |
| 5 | MCP Server 不能独立运行 | 🟡 中等 | ✅ 已解决 | 改用 SSE 连接方式 |
| 6 | data.json 中 autoIndex/watchForChanges 无效 | 🟡 中等 | ✅ 已确认 | 插件不支持自动索引，需手动触发 |
| 7 | obsidian-opencode 端口未监听 | 🟢 低 | ⏳ 暂不处理 | 非核心组件，不影响搜索功能 |
| 8 | GitHub release 404 | 🟡 中等 | ✅ 已解决 | 从源码构建 |

---

## 九、待完成事项

- [ ] **在 Obsidian 中触发 MCP Server 索引**（Cmd+P → "Index Vault"）
- [ ] 验证索引完成后向量搜索是否正常
- [ ] 验证 OpenCode 通过 MCP 协议搜索 Obsidian 知识库
- [ ] 排查 obsidian-opencode 插件端口 4096 未启动问题
- [ ] 配置 MCP Server 嵌入模型参数优化
- [ ] 测试更多文件格式导入和索引

---

## 十、关键经验教训

1. **目录名必须与 community-plugins.json 中的 id 一致**：Obsidian 根据目录名匹配插件，不是 manifest.json 中的 id
2. **MCP Server 插件不能独立运行**：必须在 Obsidian 内部运行，外部通过 SSE 连接
3. **autoIndex 不存在**：配置文件中的 `autoIndex` 和 `watchForChanges` 是无效字段，索引需手动触发
4. **GitHub 网络问题**：国内无代理环境需使用 ghproxy 等镜像
5. **core-plugins.json 需要手动启用**：安装社区插件后，必须确保 `"community-plugins": true` 存在
6. **SSE 连接流程**：先建立 SSE 连接获取 session URL，然后通过 POST 发送 JSON-RPC 请求
