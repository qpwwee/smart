# AI 学习进化训练 v2.0 — 部署完成报告

**时间**: 2026-06-14 23:59  
**状态**: ✅ 部署完成并验证通过

---

## 完成的工作

### 1. learn_engine.py（新建）
**路径**: `/Users/pon/Documents/obsidian-mcp-graphrag/learn_engine.py`

核心学习引擎，提供：
- 反馈提交（去重/更新）
- 偏好规则自动蒸馏（6 种模式匹配 + 7 种启发式分析）
- 嵌入计算（调用 Ollama qwen3-embedding:4b → 2560 维）
- 余弦相似度检索（Top-K 相似历史记忆）
- 增强 prompt 组装（偏好规则 + 相似案例 + 基础 prompt）
- 记忆 CRUD（分页、删除含媒体文件）
- 媒体文件管理（base64 → 本地存储 → 缩略图 API）
- 设置管理（auto_apply 模式开关）

### 2. web_ui.py（修改）
**修改内容**：
- 导入 LearnEngine + compute_image_hash
- 初始化学习引擎在 main() 中
- `/vision` 端点（JSON + multipart 两种模式）集成学习引擎：
  - 计算图片 SHA-256 哈希
  - 去重检查（相同图片复用缓存分析）
  - 构建增强 prompt（注入偏好 + 相似案例）
  - 返回 image_hash 供前端反馈使用
- 新增 9 个 API 路由：
  - `POST /learn/feedback` — 提交用户反馈
  - `GET /learn/memories` — 分页获取记忆列表
  - `GET /learn/stats` — 获取统计（总数/评分率/近7天/偏好数）
  - `DELETE /learn/memories/{mem_id}` — 删除记忆
  - `GET /learn/preferences` — 获取偏好规则清单
  - `DELETE /learn/preferences` — 删除指定偏好规则
  - `PUT /learn/settings` — 更新设置
  - `GET /learn/settings` — 获取当前设置
  - `GET /learn/media/{mem_id}` — 获取记忆关联图片

### 3. static/index.html（修改）
- 市场 Tab 栏新增「🧠 学习中心」按钮
- 学习中心面板（统计卡片 + 设置开关 + 偏好规则列表 + 记忆列表 + 分页）
- 页面右侧固定反馈浮层（横向展开/折叠）

### 4. static/style.css（修改）
- 反馈浮层样式（渐变侧边栏、展开/折叠、评分按钮、文本域、保存动画）
- 学习中心样式（统计网格、规则列表、记忆卡片含缩略图、分页、Toggle 开关）

### 5. static/app.js（修改）
- 反馈浮层交互（showFeedback、rateFeedback、submitFeedback、折叠/展开）
- 学习中心数据加载（loadLearnCenter、loadMemories、deleteMemory、deletePreference）
- auto_apply 双开关同步
- fetch 拦截器 → 自动捕获 /vision 和 /video-analysis 结果并弹出反馈浮层

### 6. 模型拉取
- ✅ `qwen3-vl:4b`（3.3GB, Q4_K_M）→ 已拉取
- ❌ `gemma2:4b` → Ollama registry 中不存在该模型名（备用模型，非关键）
- ⚠️ `bge-m3` → 已由现有 `qwen3-embedding:4b` 替代（2560 维）

---

## 验证结果

所有 Smoketent 通过：
- ✅ learn_engine.py 语法编译通过
- ✅ web_ui.py 语法编译通过
- ✅ 引擎初始化（learn_data/ 目录 + 三个数据文件）
- ✅ 偏好规则蒸馏（模式匹配 + 启发式分析）
- ✅ 反馈提交（去重/更新）
- ✅ Ollama 嵌入计算正常（2560 维）
- ✅ API 路由全部响应正确
- ✅ 登录认证 + Cookie 会话正常
- ✅ Web UI 正常渲染（localhost:8080 + bore 隧道）

---

## 运行状态

```
Web UI:  ● 运行中 (PID: 97328, 端口: 8080)
         http://localhost:8080
bore:    ● 运行中
         公网: http://bore.pub:45821
Ollama:  ● 运行中
         模型: qwen3-vl:4b, qwen3-embedding:4b
```

**密码**: `kb123`

---

## 数据文件

```
learn_data/
├── media/           # 反馈图片存储
├── memories.jsonl   # 记忆记录（每行一条 JSON）
├── preferences.json # 偏好规则（含计数和来源）
└── settings.json    # 引擎设置
```
