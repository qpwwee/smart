#!/usr/bin/env python3
"""
Knowledge Base Web UI — 密码保护的搜索界面（重构版 v2）
=========================================================
室友友好：浏览器打开 → 输入密码 → 搜索 → 看答案

启动方式：
  KB_PASSWORD=your_password python3 web_ui.py --vault "/path/to/vault" [--port 8080]

架构：
  室友浏览器 ──HTTPS──▶ cloudflared ──▶ localhost:8080 (本文件)
                                               │
                                               ▼
                                     WikiGraph + VectorSearcher (只读)

v2 改进：
  - 前端代码拆分到 static/ 目录（index.html, style.css, app.js）
  - SSE 流式输出（/query/stream 端点）
  - 对话上下文支持
  - 移动端响应式优化
  - 暗色模式切换
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import time
import uuid
import asyncio
from pathlib import Path
from typing import Optional, AsyncGenerator
import urllib.parse
import re
import concurrent.futures

import httpx
from fastapi import FastAPI, Request, Response, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# 导入 server.py 中的核心类
from server import WikiGraph, VectorSearcher, QueryRouter

# 导入学习引擎
from learn_engine import LearnEngine, compute_image_hash

# ============================================================
# 配置
# ============================================================

PASSWORD_ENV = "KB_PASSWORD"
SESSION_COOKIE = "kb_session"
SESSION_MAX_AGE = 86400  # 24h

# LLM 生成配置
LLM_MODEL_ENV = "KB_LLM_MODEL"
DEFAULT_LLM_MODEL = "qwen/qwen3-vl-4b"
LLM_MAX_TOKENS = 2048
LLM_TIMEOUT = 120  # 秒
MAX_LLM_CONTEXT_CHARS = 6000  # 加大上下文

# ============================================================
# 全局状态
# ============================================================

graph: Optional[WikiGraph] = None
vector: Optional[VectorSearcher] = None
router = QueryRouter()
learn: Optional[LearnEngine] = None

# session token -> 过期时间
sessions: dict[str, float] = {}

# 密码的 SHA256
password_hash: Optional[str] = None

# LLM 配置
lm_studio_url: str = "http://localhost:1234/v1"
llm_model: str = DEFAULT_LLM_MODEL

# Vision 调用封装（供 LearnEngine 检索增强使用）
def _vision_for_learn(query: str, img_b64: str, mime: str, max_tokens: int = 64):
    """供 LearnEngine 调用的短描述生成，直接走 Ollama VL"""
    return _ask_vision(query, img_b64, mime, max_tokens)

# 静态文件目录
STATIC_DIR = Path(__file__).parent / "static"


# ============================================================
# LLM 调用（含流式）
# ============================================================

def _ask_llm(query: str, context: str, history: list = None) -> str:
    """调用 LM Studio 本地 LLM (OpenAI 兼容 API)，基于检索上下文生成回答
    
    含重试逻辑：LM Studio 模型空闲卸载后，首次请求可能返回 400（模型加载中），
    自动重试最多 3 次，每次间隔递增。
    """
    messages = _build_messages(query, context, history)
    
    last_error = ""
    for attempt in range(3):
        try:
            with httpx.Client(timeout=LLM_TIMEOUT) as client:
                resp = client.post(
                    f"{lm_studio_url}/chat/completions",
                    json={
                        "model": llm_model,
                        "messages": messages,
                        "max_tokens": LLM_MAX_TOKENS,
                        "temperature": 0.7,
                        "stream": False,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = msg.get("content", "")
                        if not content:
                            content = msg.get("reasoning_content", "")
                        return content.strip() if content else "[LLM 返回空内容]"
                    return "[LLM 返回空 choices]"
                try:
                    err_detail = resp.text[:500]
                except:
                    err_detail = "(无法读取响应体)"
                print(f"  ❌ LLM 返回 {resp.status_code}: {err_detail}")
                last_error = f"[LLM 错误: HTTP {resp.status_code}]"
                if attempt < 2:
                    wait = (attempt + 1) * 5
                    print(f"  ⏳ {wait}s 后重试 (第 {attempt+2}/3 次)...")
                    time.sleep(wait)
                    continue
        except httpx.TimeoutException:
            last_error = "[LLM 超时，请稍后重试]"
            if attempt < 2:
                wait = (attempt + 1) * 5
                print(f"  ⏳ LLM 超时，{wait}s 后重试 (第 {attempt+2}/3 次)...")
                time.sleep(wait)
                continue
        except Exception as e:
            last_error = f"[LLM 错误: {e}]"
            if attempt < 2:
                wait = (attempt + 1) * 5
                print(f"  ⏳ LLM 异常: {e}，{wait}s 后重试 (第 {attempt+2}/3 次)...")
                time.sleep(wait)
                continue
    
    return last_error


async def _ask_llm_stream(query: str, context: str, history: list = None) -> AsyncGenerator[str, None]:
    """流式调用 LM Studio 本地 LLM，逐个 token 产出
    
    Yields SSE 格式字符串: data: {"type":"token","data":"..."}\n\n
    """
    messages = _build_messages(query, context, history)
    
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{lm_studio_url}/chat/completions",
                json={
                    "model": llm_model,
                    "messages": messages,
                    "max_tokens": LLM_MAX_TOKENS,
                    "temperature": 0.7,
                    "stream": True,
                },
            ) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    yield f'data: {{"type":"error","data":"LLM 返回 {resp.status_code}"}}\n\n'
                    return
                
                buffer = ""
                async for chunk in resp.aiter_lines():
                    if not chunk:
                        continue
                    if chunk.startswith("data: "):
                        data_str = chunk[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield f'data: {{"type":"token","data":{json.dumps(content)}}}\n\n'
                        except json.JSONDecodeError:
                            continue
    except Exception as e:
        yield f'data: {{"type":"error","data":{json.dumps(str(e))}}}\n\n'


def _build_messages(query: str, context: str, history: list = None) -> list:
    """构建 LLM 消息列表，包含 system prompt 和可选的对话历史"""
    system_prompt = """你是一个知识库助手。根据下面的参考资料回答用户的问题。

规则：
1. 只根据参考资料回答，不要编造信息
2. 如果参考资料来自网络搜索，请基于网络信息直接回答，不需要额外声明"网络搜索"或"知识库中没有"
3. 用清晰简洁的中文回答
4. 适当引用来源名称
5. 如果多个来源信息有矛盾，指出矛盾点"""
    
    # 截断 context 到安全长度
    safe_context = context
    if len(context) > MAX_LLM_CONTEXT_CHARS:
        lines = context.split('\n')
        truncated_lines = []
        total = 0
        for line in lines:
            if total + len(line) + 1 > MAX_LLM_CONTEXT_CHARS - 100:
                break
            truncated_lines.append(line)
            total += len(line) + 1
        safe_context = '\n'.join(truncated_lines)
        if len(truncated_lines) < len(lines):
            safe_context += f'\n...(另有 {len(lines)-len(truncated_lines)} 个来源因长度限制未包含)'
        print(f"  ✂️ Context 截断: {len(context)} → {len(safe_context)} 字符")
    
    user_msg = f"参考资料：\n{safe_context}\n\n用户问题：{query}"
    print(f"  📊 LLM 请求: model={llm_model}, context_len={len(safe_context)}, history_len={len(history or [])}")
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # 添加对话历史（最多 3 轮）
    if history:
        for h in history[-3:]:
            messages.append({"role": "user", "content": h.get("query", "")})
            messages.append({"role": "assistant", "content": h.get("answer", "")})
    
    messages.append({"role": "user", "content": user_msg})
    return messages


def _ask_llm_raw(system_prompt: str, user_message: str, max_tokens: int = None, temperature: float = None) -> str:
    """直接调用 LLM，不注入任何 KB 上下文或截断逻辑"""
    max_tok = max_tokens or LLM_MAX_TOKENS
    temp = temperature if temperature is not None else 0.7
    last_error = ""
    for attempt in range(3):
        try:
            with httpx.Client(timeout=LLM_TIMEOUT) as client:
                resp = client.post(
                    f"{lm_studio_url}/chat/completions",
                    json={
                        "model": llm_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "max_tokens": max_tok,
                        "temperature": temp,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = msg.get("content", "")
                        if not content:
                            content = msg.get("reasoning_content", "")
                        return content.strip() if content else "[LLM 返回空内容]"
                print(f"  ❌ LLM raw 返回 {resp.status_code}")
                last_error = f"[LLM 错误: HTTP {resp.status_code}]"
                if attempt < 2:
                    time.sleep((attempt + 1) * 5)
                    continue
        except httpx.TimeoutException:
            last_error = "[LLM 超时]"
            if attempt < 2:
                time.sleep((attempt + 1) * 5)
                continue
        except Exception as e:
            last_error = f"[LLM 错误: {e}]"
            if attempt < 2:
                time.sleep((attempt + 1) * 5)
                continue
    return last_error


async def _ask_llm_stream_raw(system_prompt: str, user_message: str) -> AsyncGenerator[str, None]:
    """流式调用 LLM，不注入 KB 上下文，用于知识库未命中时的自主推理"""
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{lm_studio_url}/chat/completions",
                json={
                    "model": llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "max_tokens": LLM_MAX_TOKENS,
                    "temperature": 0.7,
                    "stream": True,
                },
            ) as resp:
                if resp.status_code != 200:
                    yield f'data: {{"type":"error","data":"LLM 返回 {resp.status_code}"}}\n\n'
                    return
                async for chunk in resp.aiter_lines():
                    if not chunk:
                        continue
                    if chunk.startswith("data: "):
                        data_str = chunk[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield f'data: {{"type":"token","data":{json.dumps(content)}}}\n\n'
                        except json.JSONDecodeError:
                            continue
    except Exception as e:
        yield f'data: {{"type":"error","data":{json.dumps(str(e))}}}\n\n'


def _schedule_save_if_new(question: str, answer: str, retrieval: dict):
    """2 秒后将问答写入 Obsidian 知识库（后台线程）"""
    def _delayed_save():
        time.sleep(2)
        try:
            _save_to_obsidian(question, answer, retrieval.get("source_type", "llm"))
        except Exception as e:
            print(f"  ⚠️ 自动保存失败: {e}")

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    executor.submit(_delayed_save)
    print(f"  💾 已调度自动保存（2s 后）: {question[:40]}...")


def _save_to_obsidian(question: str, answer: str, source_type: str):
    """将问答存入 Obsidian 知识库，严格遵守 TheSchema 规范"""
    vault = "/Users/pon/Documents/obsidian- knowledge"
    wiki_dir = os.path.join(vault, "wiki", "concepts")
    os.makedirs(wiki_dir, exist_ok=True)

    # 生成 slug
    slug = re.sub(r'[^\w\u4e00-\u9fff]+', '-', question[:30]).strip('-')
    if not slug:
        slug = str(uuid.uuid4())[:8]
    today = time.strftime("%Y-%m-%d")

    # 生成标签
    tags = ["auto-saved", source_type]

    # 构造 frontmatter + 正文
    note = f"""---
title: {question[:80]}
created: {today}
updated: {today}
tags: [{', '.join(tags)}]
source: auto-saved-qa
type: concept
---

# {question}

## 回答

{answer}

---
*此页由 AI 自动生成于 {today}，来源: {source_type}*
"""

    path = os.path.join(wiki_dir, f"{slug}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(note)
    print(f"  ✅ 自动保存到 Obsidian: {path}")


def _ask_vision(query: str, image_base64: str, mime_type: str = "image/jpeg", max_tokens: int = None) -> str:
    """调用 LM Studio 本地视觉模型识别图片内容"""
    mt = max_tokens or LLM_MAX_TOKENS
    system_prompt = "你是一个视觉助手。请仔细观察图片，用中文清晰准确地描述图片内容。如果用户提出了具体问题，请重点回答."
    
    user_content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
        },
        {"type": "text", "text": query},
    ]
    
    print(f"  👁️ 视觉请求: model={llm_model}, query='{query[:60]}', image={len(image_base64)//1024}KB")
    
    last_error = ""
    for attempt in range(3):
        try:
            with httpx.Client(timeout=LLM_TIMEOUT) as client:
                resp = client.post(
                    f"{lm_studio_url}/chat/completions",
                    json={
                        "model": llm_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content},
                        ],
                        "max_tokens": mt,
                        "temperature": 0.7,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = msg.get("content", "")
                        if not content:
                            content = msg.get("reasoning_content", "")
                        return content.strip() if content else "[LLM 返回空内容]"
                    return "[LLM 返回空 choices]"
                try:
                    err_detail = resp.text[:500]
                except:
                    err_detail = "(无法读取响应体)"
                print(f"  ❌ LLM 返回 {resp.status_code}: {err_detail}")
                last_error = f"[LLM 错误: HTTP {resp.status_code}]"
                if attempt < 2:
                    wait = (attempt + 1) * 5
                    time.sleep(wait)
                    continue
        except httpx.TimeoutException:
            last_error = "[LLM 超时，请稍后重试]"
            if attempt < 2:
                wait = (attempt + 1) * 5
                time.sleep(wait)
                continue
        except Exception as e:
            last_error = f"[LLM 错误: {e}]"
            if attempt < 2:
                wait = (attempt + 1) * 5
                time.sleep(wait)
                continue
    return last_error if last_error else "[LLM 无可用响应]"


def _ask_vision_multi(query: str, images: list[tuple[str, str]], max_tokens: int = None) -> str:
    """调用 VL 模型一次分析多张图片（真正的视频多帧分析）"""
    mt = max_tokens or LLM_MAX_TOKENS
    system_prompt = "你是一个视频分析助手。你会收到一段视频的多帧截图（按时间顺序排列）。请综合分析这段视频的完整内容：1)视频主题和场景 2)出现的人物/物体及其变化 3)关键动作和事件顺序 4)整体氛围和环境。用中文详细列出，标注对应帧号。"
    
    user_content = []
    for i, (img_b64, mime) in enumerate(images):
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{img_b64}"},
        })
        user_content.append({"type": "text", "text": f"[帧{i+1}]"})
    user_content.append({"type": "text", "text": query})
    
    print(f"  🎬 多帧分析: model={llm_model}, {len(images)}帧, query='{query[:60]}'")
    
    last_error = ""
    for attempt in range(3):
        try:
            with httpx.Client(timeout=max(LLM_TIMEOUT, 300)) as client:
                resp = client.post(
                    f"{lm_studio_url}/chat/completions",
                    json={
                        "model": llm_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content},
                        ],
                        "max_tokens": mt,
                        "temperature": 0.7,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = msg.get("content", "")
                        if not content:
                            content = msg.get("reasoning_content", "")
                        return content.strip() if content else "[LLM 返回空内容]"
                    return "[LLM 返回空 choices]"
                try:
                    err_detail = resp.text[:500]
                except:
                    err_detail = "(无法读取响应体)"
                print(f"  ❌ LLM 返回 {resp.status_code}: {err_detail}")
                last_error = f"[LLM 错误: HTTP {resp.status_code}]"
                if attempt < 2:
                    wait = (attempt + 1) * 5
                    time.sleep(wait)
                    continue
        except httpx.TimeoutException:
            last_error = "[LLM 超时，请稍后重试]"
            if attempt < 2:
                wait = (attempt + 1) * 5
                time.sleep(wait)
                continue
        except Exception as e:
            last_error = f"[LLM 错误: {e}]"
            if attempt < 2:
                wait = (attempt + 1) * 5
                time.sleep(wait)
                continue
    return last_error if last_error else "[LLM 无可用响应]"


# ============================================================
# 联网搜索（知识库不足时的降级补充）
# ============================================================

WEB_SEARCH_ENABLED = True
NEED_WEB_THRESHOLD = 0.4


# ============================================================
# 股市行情（NeoData 实时数据）
# ============================================================

NEODATA_PROXY = os.environ.get("AUTH_GATEWAY_PORT", "19000")
NEODATA_URL = f"http://localhost:{NEODATA_PROXY}/proxy/api"
NEODATA_REMOTE = "https://jprx.m.qq.com/aizone/skillserver/v1/proxy/teamrouter_neodata/query"


def _query_neodata(query: str, data_type: str = "api") -> dict:
    """调用 NeoData 金融搜索 API"""
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                NEODATA_URL,
                headers={
                    "Content-Type": "application/json",
                    "Remote-URL": NEODATA_REMOTE,
                },
                json={
                    "query": query,
                    "request_id": uuid.uuid4().hex[:16],
                    "data_type": data_type,
                },
            )
            if resp.status_code == 200:
                return resp.json()
            print(f"  ⚠️ NeoData HTTP {resp.status_code}: {resp.text[:200]}")
            return {}
    except Exception as e:
        print(f"  ⚠️ NeoData 连接失败: {e}")
        return {}


def _parse_index_data(api_recall: list) -> list[dict]:
    """从 NeoData apiRecall 中解析指数行情"""
    target = ["上证指数", "深证成指", "创业板指", "科创50", "沪深300"]
    indices = []
    found_names = set()
    for recall in api_recall:
        text = recall.get("content", "")
        for name in target:
            if name in text and name not in found_names:
                idx = text.find(name)
                block = text[idx:idx + 600]
                def _ext(field):
                    m = re.search(f"{field}:([^;]+)", block)
                    return m.group(1).strip() if m else "-"
                change_str = _ext("当日涨跌幅")
                try:
                    change = float(change_str.replace("%", "").replace("+", ""))
                except ValueError:
                    change = 0.0
                price = _ext("最新价格")
                indices.append({
                    "name": name,
                    "price": price,
                    "change_pct": round(change, 2),
                    "change_str": change_str,
                })
                found_names.add(name)
    indices.sort(key=lambda x: x["change_pct"], reverse=True)
    return indices


def _get_sector_comparison() -> list[dict]:
    """查询板块涨跌对比数据（解析 markdown 表格）"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_up = ex.submit(_query_neodata, "A股板块今日涨幅榜", data_type="api")
        f_down = ex.submit(_query_neodata, "A股板块今日跌幅榜", data_type="api")
        results_up = f_up.result()
        results_down = f_down.result()
    
    sectors = []
    INVALID_NAMES = {"降序", "升序", "排行类型", "行业名", ""}
    
    for result in [results_up, results_down]:
        api_data = result.get("data", {}).get("apiData", {})
        api_recall = api_data.get("apiRecall", [])
        for recall in api_recall:
            content = recall.get("content", "")
            for line in content.split("\n"):
                line = line.strip()
                if not line or not line.startswith("|"):
                    continue
                if "排行类型" in line or "---" in line:
                    continue
                cols = [c.strip() for c in line.split("|")]
                if len(cols) >= 7:
                    sector_name = cols[2]
                    if sector_name in INVALID_NAMES or len(sector_name) < 2:
                        continue
                    try:
                        change = float(cols[6]) if cols[6] else 0
                    except ValueError:
                        continue
                    if sector_name and abs(change) < 20:
                        sectors.append({"name": sector_name, "change": change})
    
    # 去重
    seen = set()
    unique = []
    for s in sectors:
        if s["name"] not in seen:
            seen.add(s["name"])
            unique.append(s)
    sectors = unique
    
    # 涨幅前 8 + 跌幅前 4
    up = sorted([s for s in sectors if s["change"] > 0], key=lambda x: x["change"], reverse=True)[:8]
    down = sorted([s for s in sectors if s["change"] <= 0], key=lambda x: x["change"])[:4]
    combined = up + list(reversed(down))
    return combined if combined else sectors[:12]


# 缓存市场/涨停/异动数据
_market_cache: dict = {"data": None, "time": 0}
_limit_up_cache: dict = {"data": None, "time": 0}
_abnormal_cache: dict = {"data": None, "time": 0}
CACHE_TTL = 25


def _parse_stock_table(content: str) -> list[dict]:
    """通用解析 NeoData 股票排行榜表格"""
    rows = []
    col_map = {}
    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.split("|")]
        if "股票代码" in line and "股票名称" in line:
            for i, c in enumerate(cols):
                c = c.strip()
                key = {"股票代码":"code","股票名称":"name","最新价":"price","涨跌幅":"change",
                       "量比":"vol_ratio","振幅":"amplitude","换手率":"turnover",
                       "主力净流入":"net_flow","总市值":"mcap","市盈率":"pe"}.get(c)
                if key:
                    col_map[key] = i
            col_map["_rank_type"] = 1
            continue
        if "---" in line:
            continue
        if len(cols) < 5:
            continue
        code = cols[col_map.get("code", 2)] if col_map else cols[2]
        name = cols[col_map.get("name", 3)] if col_map else cols[3]
        if not code or len(code) < 6 or not name:
            continue
        def _col(key, default="--"):
            i = col_map.get(key, -1)
            return cols[i] if i >= 0 and i < len(cols) else default
        try:
            change = float(_col("change", "0"))
        except ValueError:
            change = 0.0
        try:
            vol_ratio = float(_col("vol_ratio", "0"))
        except ValueError:
            vol_ratio = 0.0
        try:
            amplitude = float(_col("amplitude", "0"))
        except ValueError:
            amplitude = 0.0
        try:
            turnover = float(_col("turnover", "0"))
        except ValueError:
            turnover = 0.0
        net_flow = _col("net_flow")
        mcap = _col("mcap")
        rank_type = cols[col_map.get("_rank_type", 1)] if col_map else ""
        rows.append({
            "code": code, "name": name, "price": _col("price"),
            "change": change, "change_str": f"{change:+.2f}%",
            "vol_ratio": vol_ratio, "amplitude": amplitude,
            "turnover": turnover, "net_flow": net_flow,
            "mcap": mcap, "rank_type": rank_type,
        })
    return rows


def _query_limit_up() -> dict:
    """涨停板 + 热门飙升"""
    result = _query_neodata("今日涨停股票 涨幅排行 涨停板", data_type="api")
    api_recall = result.get("data", {}).get("apiData", {}).get("apiRecall", [])
    limit_up = []
    top_gainers = []
    for recall in api_recall:
        content = recall.get("content", "")
        for row in _parse_stock_table(content):
            if row["change"] >= 19.9:
                limit_up.append(row)
            elif row["change"] >= 5:
                top_gainers.append(row)
    seen = set()
    lu, tg = [], []
    for r in limit_up:
        if r["code"] not in seen:
            seen.add(r["code"]); lu.append(r)
    for r in top_gainers:
        if r["code"] not in seen and len(tg) < 10:
            seen.add(r["code"]); tg.append(r)
    return {"limit_up": lu[:15], "top_gainers": tg[:10], "time": time.strftime("%H:%M:%S"), "date": time.strftime("%Y-%m-%d")}


def _query_abnormal() -> dict:
    """异动监控：量比/振幅/换手率 TOP"""
    result = _query_neodata("今日A股异动 量比最高 振幅最大 换手率最高", data_type="api")
    all_recalls = result.get("data", {}).get("apiData", {}).get("apiRecall", [])
    
    all_rows = []
    seen = set()
    for recall in all_recalls:
        for row in _parse_stock_table(recall.get("content", "")):
            if row["code"] not in seen:
                seen.add(row["code"])
                all_rows.append(row)
    
    def _top(key, threshold, count=8):
        filt = [r for r in all_rows if r[key] >= threshold]
        return sorted(filt, key=lambda x: x[key], reverse=True)[:count]
    
    return {
        "vol_ratio": _top("vol_ratio", 1.5, 10),
        "amplitude": _top("amplitude", 8.0, 10),
        "turnover": _top("turnover", 12.0, 10),
        "time": time.strftime("%H:%M:%S"),
        "date": time.strftime("%Y-%m-%d"),
    }


def _extract_keywords(query: str) -> list:
    """从查询中提取实体关键词"""
    raw = re.sub(r"site:[\w.]+", "", query).strip()
    years = re.findall(r"\d{4}", raw)
    english = re.findall(r"[a-zA-Z]{3,}", raw)
    chinese_text = "".join(re.findall(r"[\u4e00-\u9fff]+", raw))
    stops = r"(?:的|了|在|是|怎么|如何|什么|哪里|哪个|这个|那个|与|和|或|对|从|到|把|被|让|给|为|以|由|于|向|往|跟|比|除|吗|呢|吧|呀|啊)"
    parts = [p for p in re.split(stops, chinese_text) if len(p) >= 2]
    short_parts = []
    for p in parts:
        if len(p) >= 4:
            for wlen in (4, 3, 2):
                for i in range(len(p) - wlen + 1):
                    short_parts.append(p[i:i + wlen])
        else:
            short_parts.append(p)

    PREFIXES = {"年", "月", "日", "第", "时", "分", "秒"}
    core_parts = []
    for w in short_parts:
        if w not in core_parts:
            core_parts.append(w)
            for pfx in PREFIXES:
                if w.startswith(pfx) and len(w) > len(pfx):
                    stripped = w[len(pfx):]
                    if len(stripped) >= 2 and stripped not in core_parts:
                        core_parts.append(stripped)

    return years + english + core_parts


def _bing_search(query: str, max_results: int) -> list:
    """执行一次 Bing 搜索"""
    from bs4 import BeautifulSoup
    import ssl, urllib.request

    ctx = ssl._create_unverified_context()
    url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    soup = BeautifulSoup(html, "lxml")

    keywords = [kw.lower() for kw in _extract_keywords(query)]

    def _calc_score(item_title, item_snippet, kw_list):
        text = (item_title + " " + item_snippet).lower()
        score = 0.0
        for kw in kw_list:
            kwl = kw.lower()
            if kwl in text:
                score += 1.0
            if kwl in item_title.lower():
                score += 0.5
        return score

    fallback_kw = []
    for kw in keywords:
        if len(kw) >= 4:
            for i in range(len(kw) - 1):
                fallback_kw.append(kw[i:i+2])

    results = []
    for li in soup.select("li.b_algo"):
        h2 = li.find("h2")
        if not h2:
            continue
        a = h2.find("a")
        if not a or not a.get("href"):
            continue
        snippet = ""
        for cap in li.find_all(["p", "div"], recursive=True):
            txt = cap.get_text(strip=True)
            if len(txt) > 15:
                snippet = txt[:300]
                break
        title = a.get_text(strip=True)

        score = _calc_score(title, snippet, keywords)
        if score == 0 and fallback_kw:
            score = _calc_score(title, snippet, fallback_kw) * 0.3

        results.append({
            "title": title,
            "snippet": snippet,
            "url": a["href"],
            "_score": score,
        })

    results.sort(key=lambda x: x["_score"], reverse=True)
    for r in results:
        r.pop("_score", None)
    return results[:max_results]


def web_search(query: str, max_results: int = 5) -> list:
    """联网搜索（国内可用）：多关键词尝试，取最佳结果"""
    if not WEB_SEARCH_ENABLED:
        return []
    try:
        keywords = [kw.lower() for kw in _extract_keywords(query)]
        strong_entities = [k for k in keywords if re.search(r'[\u4e00-\u9fff]', k) and len(k) >= 2]

        search_queries = [query]
        if strong_entities:
            search_queries.append(" ".join(strong_entities))
        core_clean = []
        for e in strong_entities:
            for pfx in ["年", "月", "日", "第"]:
                if e.startswith(pfx):
                    e = e[len(pfx):]
            if len(e) >= 2:
                core_clean.append(e)
        if core_clean:
            clean_q = " ".join(core_clean)
            if clean_q not in search_queries:
                search_queries.append(clean_q)
            years = re.findall(r"\d{4}", query)
            if years:
                search_queries.append(f"{' '.join(years)} {clean_q}")
        en_words = re.findall(r"[a-zA-Z]{3,}", query)
        if en_words:
            search_queries.append(" ".join(en_words))

        seen_urls = set()
        all_results = []
        for sq in search_queries:
            try:
                results = _bing_search(sq, max_results=10)
                for r in results:
                    if r["url"] not in seen_urls:
                        all_results.append(r)
                        seen_urls.add(r["url"])
            except Exception:
                pass

        def _relevance(item) -> float:
            text = (item["title"] + " " + item["snippet"]).lower()
            score = 0.0
            for kw in keywords:
                if len(kw) >= 2 and kw in text:
                    score += 1.0
                if len(kw) >= 2 and kw in item["title"].lower():
                    score += 0.5
            return score

        all_results.sort(key=_relevance, reverse=True)

        filtered = []
        for r in all_results:
            if "baike.baidu.com" in r["url"]:
                continue
            if strong_entities:
                text = (r["title"] + " " + r["snippet"]).lower()
                if any(e in text for e in strong_entities):
                    filtered.append(r)
            elif _relevance(r) > 0:
                filtered.append(r)

        if len(filtered) < max_results // 2:
            relaxed = [r for r in all_results if _relevance(r) > 0 and "baike.baidu.com" not in r["url"]]
            seen_urls = {r["url"] for r in filtered}
            for r in relaxed:
                if r["url"] not in seen_urls:
                    filtered.append(r)
                    seen_urls.add(r["url"])

        final = filtered[:max_results] if filtered else all_results[:max_results]

        # 尝试补充摘要
        for r in final:
            if len(r.get("snippet", "")) < 30 and r.get("url") and "baike.baidu.com" not in r["url"]:
                try:
                    import ssl, urllib.request
                    ctx2 = ssl._create_unverified_context()
                    req2 = urllib.request.Request(r["url"], headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    })
                    with urllib.request.urlopen(req2, context=ctx2, timeout=5) as resp2:
                        page_html = resp2.read().decode("utf-8", errors="ignore")
                    from bs4 import BeautifulSoup
                    soup2 = BeautifulSoup(page_html, "lxml")
                    desc = ""
                    for meta in soup2.select("meta[name=description], meta[property='og:description']"):
                        desc = meta.get("content", "")
                        if desc:
                            break
                    if not desc:
                        for p in soup2.select("p"):
                            txt = p.get_text(strip=True)
                            if len(txt) > 30:
                                desc = txt[:300]
                                break
                    if desc:
                        r["snippet"] = f"[页面摘要] {desc}"
                except Exception:
                    pass

        print(f"🌐 联网搜索 '{query}': {len(all_results)} 总 → {len(filtered)} 相关 → {len(final)} 最终")
        return final
    except ImportError:
        print("⚠️ 联网搜索: BeautifulSoup 未安装")
        return []
    except Exception as e:
        print(f"⚠️ 联网搜索失败: {e}")
        return []


app = FastAPI(title="Knowledge Base Search")


def _check_password(pwd: str) -> bool:
    if not password_hash:
        return False
    return hashlib.sha256(pwd.encode()).hexdigest() == password_hash


def _is_authenticated(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    if not token or token not in sessions:
        return False
    if sessions[token] < time.time():
        del sessions[token]
        return False
    return True


# ============================================================
# 路由
# ============================================================


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if _is_authenticated(request):
        html_path = STATIC_DIR / "index.html"
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h2>index.html not found in static/</h2>")
    # 登录页 - 简单内嵌
    return LOGIN_PAGE


LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Knowledge Base</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div class="login-box">
<h1>🔒 Knowledge Base</h1>
<form id="loginForm">
<input type="password" id="pwd" placeholder="输入密码" autofocus required>
<button type="submit">进入</button>
</form>
<div class="error" id="err"></div>
</div>
<script>
document.getElementById('loginForm').onsubmit=async e=>{
e.preventDefault();
const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'password='+encodeURIComponent(document.getElementById('pwd').value)});
if(r.ok){window.location.reload()}else{document.getElementById('err').textContent='密码错误'}}
</script>
</body>
</html>"""


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if _check_password(password):
        token = secrets.token_hex(32)
        sessions[token] = time.time() + SESSION_MAX_AGE
        response = Response(status_code=200)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response
    return Response(status_code=401)


@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token and token in sessions:
        del sessions[token]
    response = Response(status_code=302, headers={"Location": "/"})
    response.delete_cookie(SESSION_COOKIE)
    return response


# ============================================================
# API - 知识图谱
# ============================================================

@app.get("/api/check-auth")
async def api_check_auth(request: Request):
    """轻量认证检查，返回 200 或 401"""
    if _is_authenticated(request):
        return Response(status_code=200)
    return Response(status_code=401)


@app.get("/api/graph")
async def api_graph(request: Request):
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    if not graph:
        return JSONResponse(content={"nodes": [], "edges": []})

    cat_colors = {"concepts": "#6c63ff", "entities": "#00d4aa", "sources": "#ff9f43"}
    nodes = []
    for name, node in graph.nodes.items():
        cat = node.get("category", "unknown")
        nodes.append({
            "id": name, "name": name, "category": cat,
            "symbolSize": min(6 + len(node.get("links", [])) * 0.8 + len(node.get("backlinks", [])) * 0.5, 22),
            "itemStyle": {"color": cat_colors.get(cat, "#888")},
        })
    edges = [{"source": e["source"], "target": e["target"],
              "label": {"show": True, "formatter": e.get("relation", "")}} for e in graph.edges]
    return JSONResponse(content={"nodes": nodes, "edges": edges})


# ============================================================
# API - 知识检索（含流式）
# ============================================================

def _do_retrieve(query_text: str) -> dict:
    """执行完整的检索流程（路由→向量→图谱→网络），返回结果字典"""
    routing = router.route(query_text)
    strategy = routing["strategy"]

    results = []
    vec_results = []

    # 关键词直搜兜底
    keywords = _extract_keywords(query_text)
    keyword_matches = {}
    if graph:
        for page_name, node in graph.nodes.items():
            score = 0.0
            page_lower = page_name.lower()
            for kw in keywords:
                if kw.lower() in page_lower:
                    score = max(score, 0.85)
                    break
            if score == 0 and node.get("full_path"):
                try:
                    content = Path(node["full_path"]).read_text(encoding="utf-8")
                    if content.startswith("---"):
                        end = content.find("---", 3)
                        if end != -1:
                            content = content[end + 3:]
                    content_lower = content.lower()
                    kw_count = sum(1 for kw in keywords if kw.lower() in content_lower)
                    if kw_count > 0:
                        score = 0.7 + kw_count * 0.05
                except Exception:
                    pass
            if score > 0:
                keyword_matches[page_name] = score
        for page_name, score in sorted(keyword_matches.items(), key=lambda x: x[1], reverse=True)[:5]:
            node = graph.nodes.get(page_name, {})
            excerpt = ""
            if node.get("full_path"):
                try:
                    content = Path(node["full_path"]).read_text(encoding="utf-8")
                    if content.startswith("---"):
                        end = content.find("---", 3)
                        if end != -1:
                            content = content[end + 3:]
                    excerpt = content.strip()[:200]
                except Exception:
                    pass
            results.append({
                "page": page_name,
                "category": node.get("category", ""),
                "score": round(score, 4),
                "excerpt": excerpt,
                "source": "keyword",
            })

    if strategy in ("hybrid", "vector_search", "graph_traverse"):
        vec_results = vector.search(query_text, top_k=5) if vector else []
        for r in vec_results:
            results.append({**r, "source": "semantic"})

    if strategy in ("hybrid", "graph_traverse") and graph:
        start_pages = []
        for page_name in graph.nodes:
            if page_name.lower() in query_text.lower():
                start_pages.append(page_name)
        if vec_results:
            for vr in vec_results[:2]:
                if vr["page"] in graph.nodes and vr["page"] not in start_pages:
                    start_pages.append(vr["page"])

        seen = set(r["page"] for r in results)
        for sp in start_pages[:3]:
            traversed = graph.traverse(sp, max_hops=2, max_results=8)
            for t in traversed:
                if t["page"] not in seen:
                    node = graph.nodes.get(t["page"], {})
                    excerpt = ""
                    if node.get("full_path"):
                        try:
                            content = Path(node["full_path"]).read_text(encoding="utf-8")
                            if content.startswith("---"):
                                end = content.find("---", 3)
                                if end != -1:
                                    content = content[end + 3:]
                            excerpt = content.strip()[:200]
                        except Exception:
                            pass
                    results.append({
                        "page": t["page"],
                        "category": t.get("category", ""),
                        "relation": t.get("relation", ""),
                        "hops": t.get("hops", 0),
                        "relevance": round(1.0 / (t["hops"] + 1), 3),
                        "excerpt": excerpt,
                        "source": "graph",
                    })
                    seen.add(t["page"])

    results.sort(key=lambda x: x.get("score", x.get("relevance", 0)), reverse=True)
    top_results = results[:15]

    # 联网补充 — 始终执行，确保 KB 无匹配时有后备
    top_score = top_results[0].get("score", top_results[0].get("relevance", 0)) if top_results else 0
    needs_web = (not top_results) or (top_score < NEED_WEB_THRESHOLD)

    print(f"  🔍 查询: {query_text}")
    print(f"  📊 Top 3 分数: {[(r.get('page','?'), round(r.get('score',r.get('relevance',0)),3)) for r in top_results[:3]]}")
    print(f"  📊 top_score={round(top_score,3)}, threshold={NEED_WEB_THRESHOLD}, needs_web={needs_web}")

    # 联网搜索 — 始终执行以覆盖 KB 覆盖不到的领域
    web_results = web_search(query_text, max_results=5)
    print(f"  🌐 联网搜索: {len(web_results)} 条结果")

    # 构建上下文：KB 优先，网络补充
    kb_context = "\n\n".join(
        f"【来源: {r['page']} ({r.get('category', '')})】\n{r.get('excerpt', r.get('text', ''))}"
        for r in top_results[:5]
    ) if top_results else ""

    source_type = "knowledge"
    full_context = kb_context

    # 判断 KB 是否真正命中：top_score 高 + 结果数 > 0 + 核心词匹配
    real_kb_hit = top_results and top_score >= 0.85
    if real_kb_hit and top_results:
        # 额外检查：top1 结果必须包含查询中至少一个核心关键词（≥3字符）
        top1_excerpt = (top_results[0].get("excerpt", "") + " " + top_results[0].get("page", "")).lower()
        core_kws = [kw.lower() for kw in _extract_keywords(query_text) if len(kw) >= 3]
        kw_match = any(kw in top1_excerpt for kw in core_kws)
        if not kw_match:
            real_kb_hit = False
            print(f"  ⚠️ KB top1 不含查询核心关键词({core_kws[:3]}...)，降级为 web")

    if web_results:
        web_context_parts = []
        for i, wr in enumerate(web_results, 1):
            web_context_parts.append(
                f"【网络来源 {i}】{wr['title']}\n{wr['snippet']}\n来源: {wr['url']}"
            )
        web_context = "\n\n".join(web_context_parts)

        if real_kb_hit:
            # KB 强势命中，网络仅作补充
            full_context = f"【知识库结果（优先参考）】\n{kb_context}\n\n【网络搜索补充（仅供参考）】\n{web_context}"
            source_type = "hybrid"
        elif kb_context:
            # KB 弱匹配，网络同等权重
            full_context = f"【知识库结果（可能不相关）】\n{kb_context}\n\n【网络搜索结果（请优先参考）】\n{web_context}"
            source_type = "web"
        else:
            full_context = f"【网络搜索结果】\n{web_context}"
            source_type = "web"
    else:
        if not real_kb_hit:
            # KB 弱匹配且无网络结果
            source_type = "llm"

    return {
        "query": query_text,
        "strategy": strategy,
        "source_type": source_type,
        "context": full_context,
        "results": top_results,
        "web_results": web_results,
        "top_score": top_score,
    }


@app.post("/query")
async def query(request: Request):
    """非流式查询（兼容旧客户端）"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})

    body = await request.json()
    query_text = body.get("query", "").strip()
    history = body.get("history", [])
    if not query_text:
        return JSONResponse(content={"results": [], "strategy": "empty"})

    retrieval = _do_retrieve(query_text)
    context = retrieval["context"]
    top_score = retrieval.get("top_score", 0)
    source_type = retrieval["source_type"]

    answer = ""
    if context.strip() and source_type != "llm":
        answer = _ask_llm(query_text, context, history)
    else:
        # 知识库 + 网络均无结果，LLM 自主推理
        answer = _ask_llm_raw(
            "你是一个博学的AI助手。请基于你自身的知识直接回答用户问题，尽可能准确和详细。可以引用网络上的公开信息。如果涉及实时数据请说明信息来源。",
            query_text
        )
        source_type = "llm"

    if source_type in ("web", "llm"):
        _schedule_save_if_new(query_text, answer, retrieval)

    return JSONResponse(content={
        "query": query_text,
        "strategy": retrieval["strategy"],
        "answer": answer,
        "source_type": source_type,
        "top_score": top_score,
        "results": retrieval["results"],
    })


@app.post("/query/stream")
async def query_stream(request: Request):
    """SSE 流式查询——逐个 token 返回"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})

    body = await request.json()
    query_text = body.get("query", "").strip()
    history = body.get("history", [])
    if not query_text:
        return JSONResponse(content={"results": [], "strategy": "empty"})

    retrieval = _do_retrieve(query_text)
    top_score = retrieval.get("top_score", 0)
    source_type = retrieval["source_type"]

    fallback_answer = None

    async def event_generator():
        nonlocal fallback_answer
        # 1. 发送来源数据
        yield f'data: {json.dumps({"type": "sources", "data": retrieval["results"]})}\n\n'
        yield f'data: {json.dumps({"type": "meta", "data": {"strategy": retrieval["strategy"], "source_type": retrieval["source_type"]}})}\n\n'

        # 2. 流式发送 LLM tokens
        context = retrieval["context"]
        full_answer = ""

        if context.strip() and source_type != "llm":
            async for chunk in _ask_llm_stream(query_text, context, history):
                yield chunk
                try:
                    if chunk.startswith("data: "):
                        data = json.loads(chunk[6:])
                        if data.get("type") == "token":
                            full_answer += data.get("data", "")
                except:
                    pass
        else:
            # KB + web 均无结果，LLM 自行推理
            retrieval["source_type"] = "llm"
            async for chunk in _ask_llm_stream_raw(
                "你是一个博学的AI助手。请基于你自己的知识回答用户问题，尽可能准确和详细。积极搜索参考网络上的最新信息。如果涉及实时信息，请说明信息来源。",
                query_text
            ):
                yield chunk
                try:
                    if chunk.startswith("data: "):
                        data = json.loads(chunk[6:])
                        if data.get("type") == "token":
                            full_answer += data.get("data", "")
                except:
                    pass
            fallback_answer = full_answer

        # 3. 发送完成事件
        yield f'data: {json.dumps({"type": "done", "data": {"answer": full_answer, "source_type": retrieval["source_type"], "strategy": retrieval["strategy"], "results": retrieval["results"]}})}\n\n'

        # 4. 2 秒后自动写入知识库（仅当知识库未命中时）
        if retrieval["source_type"] in ("web", "llm") and full_answer:
            _schedule_save_if_new(query_text, full_answer, retrieval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# API - 视觉识别
# ============================================================

@app.post("/vision")
async def vision(request: Request):
    """视觉识别：支持 multipart 上传（文件）和 JSON 模式（摄像头 base64）"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})

    content_type = request.headers.get("content-type", "")

    # JSON 模式（摄像头实时识别）
    if "application/json" in content_type:
        body = await request.json()
        data_url = body.get("image", "")
        if not data_url:
            return JSONResponse(content={"error": "缺少 image 字段", "answer": ""})
        # 解析 data:image/jpeg;base64,xxx
        match = re.match(r"data:image/(\w+);base64,(.+)", data_url)
        if not match:
            return JSONResponse(content={"error": "无效的图片格式，需要 data: URL", "answer": ""})
        img_fmt = match.group(1)
        img_b64 = match.group(2)
        mime = f"image/{img_fmt}"
        query_text = body.get("query", "一句话描述画面内容")
        max_tokens = body.get("max_tokens", 256)

        # 计算图片哈希
        img_bytes = __import__('base64').b64decode(img_b64)
        img_hash = compute_image_hash(img_bytes)

        # 学习引擎：去重 + 增强 prompt
        enhanced_prompt = query_text
        if learn:
            for m in learn._read_memories():
                if m.get("image_hash") == img_hash and m.get("correction"):
                    return JSONResponse(content={
                        "description": m["correction"],
                        "query": query_text,
                        "image_hash": img_hash,
                        "from_cache": True,
                    })
            enhanced_prompt = learn.build_enhanced_prompt(
                img_b64, mime, _vision_for_learn,
                base_prompt=query_text
            )

        answer = _ask_vision(enhanced_prompt, img_b64, mime, max_tokens)
        return JSONResponse(content={
            "description": answer,
            "query": query_text,
            "image_hash": img_hash,
        })

    # multipart/form-data 模式（图片/摄像头截图上传）
    form = await request.form()
    image = form.get("file") or form.get("image")
    if image and hasattr(image, "read"):
        img_bytes = await image.read()
        if len(img_bytes) == 0:
            return JSONResponse(content={"error": "图片为空", "answer": ""})
        if len(img_bytes) > 10 * 1024 * 1024:
            return JSONResponse(content={"error": "图片过大（最大 10MB）", "answer": ""})
        img_b64 = base64.b64encode(img_bytes).decode("ascii")
        mime = getattr(image, "content_type", None) or "image/jpeg"
        if mime not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            filename = getattr(image, "filename", "") or ""
            ext = filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
            mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                         "webp": "image/webp", "gif": "image/gif"}
            mime = mime_map.get(ext, "image/jpeg")
        query_text = form.get("query", "请描述这张图片的内容")
        if isinstance(query_text, str):
            query_text = query_text.strip() or "请描述这张图片的内容"
        max_tokens = form.get("max_tokens", LLM_MAX_TOKENS)
        if isinstance(max_tokens, str):
            max_tokens = int(max_tokens)

        # 计算图片哈希 + 学习引擎集成
        img_hash = compute_image_hash(img_bytes)
        enhanced_prompt = query_text
        if learn:
            for m in learn._read_memories():
                if m.get("image_hash") == img_hash and m.get("correction"):
                    return JSONResponse(content={
                        "query": query_text,
                        "answer": m["correction"],
                        "filename": getattr(image, "filename", "") or "",
                        "image_size_kb": len(img_bytes) // 1024,
                        "image_hash": img_hash,
                        "from_cache": True,
                    })
            enhanced_prompt = learn.build_enhanced_prompt(
                img_b64, mime, _vision_for_learn,
                base_prompt=query_text
            )

        answer = _ask_vision(enhanced_prompt, img_b64, mime, max_tokens)
        return JSONResponse(content={
            "query": query_text,
            "answer": answer,
            "filename": getattr(image, "filename", "") or "",
            "image_size_kb": len(img_bytes) // 1024,
            "image_hash": img_hash,
        })

    return JSONResponse(content={"error": "请上传图片文件或发送 JSON 格式的 base64 图片", "answer": ""})


@app.post("/video-analysis")
async def video_analysis(
    request: Request,
    images: list[UploadFile] = File(...),
    query: str = Form(default="请综合分析这段视频的完整内容"),
    max_tokens: int = Form(default=LLM_MAX_TOKENS),
):
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})

    if not images:
        return JSONResponse(content={"error": "未上传图片", "answer": ""})
    if len(images) > 20:
        return JSONResponse(content={"error": f"最多20帧，收到{len(images)}张", "answer": ""})

    frames = []
    total_size = 0
    for img in images:
        img_bytes = await img.read()
        if len(img_bytes) == 0:
            continue
        total_size += len(img_bytes)
        if total_size > 20 * 1024 * 1024:
            return JSONResponse(content={"error": "总图片过大（最大 20MB）", "answer": ""})
        img_b64 = base64.b64encode(img_bytes).decode("ascii")
        mime = img.content_type or "image/jpeg"
        if mime not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            ext = img.filename.rsplit(".", 1)[-1].lower() if img.filename and "." in img.filename else ""
            mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}
            mime = mime_map.get(ext, "image/jpeg")
        frames.append((img_b64, mime))

    if not frames:
        return JSONResponse(content={"error": "所有帧解析失败", "answer": ""})

    # 视频哈希（取第一帧的原始字节）
    first_frame_raw = base64.b64decode(frames[0][0])
    video_hash = compute_image_hash(first_frame_raw)

    query_text = query.strip() or "请综合分析这段视频的完整内容"
    answer = _ask_vision_multi(query_text, frames, max_tokens)

    return JSONResponse(content={
        "query": query_text,
        "answer": answer,
        "image_hash": video_hash,
        "frame_count": len(frames),
        "total_size_kb": total_size // 1024,
    })


# ============================================================
# API - 股市行情
# ============================================================

@app.get("/market")
async def market_data(request: Request):
    """股市行情面板：指数 + 板块对比（带缓存）"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})

    now = time.time()
    if _market_cache["data"] and (now - _market_cache["time"]) < CACHE_TTL:
        return JSONResponse(content=_market_cache["data"])

    index_data = _query_neodata("上证指数 深证成指 创业板指 科创50 沪深300 今日行情", data_type="api")
    index_recall = index_data.get("data", {}).get("apiData", {}).get("apiRecall", [])
    indices = _parse_index_data(index_recall)

    sectors = _get_sector_comparison()

    market_overview = _query_neodata("今日A股市场整体行情和成交额", data_type="api")
    overview_text = ""
    for recall in market_overview.get("data", {}).get("apiData", {}).get("apiRecall", []):
        content = recall.get("content", "")
        if content:
            overview_text = content[:500]
            break

    result = {
        "time": time.strftime("%H:%M:%S"),
        "date": time.strftime("%Y-%m-%d"),
        "indices": indices,
        "sectors": sectors,
        "overview": overview_text,
    }
    # 只有当拿到有效数据时才更新缓存
    if indices or sectors:
        _market_cache["data"] = result
        _market_cache["time"] = now
    elif _market_cache["data"]:
        # 本次没拿到数据，复用缓存
        return JSONResponse(content=_market_cache["data"])
    return JSONResponse(content=result)


@app.post("/stock-pick")
async def stock_pick(request: Request):
    """AI 荐股：并行多源数据 → 规则预筛 → LLM 深度分析 → 置信度评分"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})

    body = await request.json()
    user_query = body.get("query", "").strip()
    if not user_query:
        return JSONResponse(content={"error": "请输入选股问题", "answer": "", "picks": []})

    # ── Phase 1: 并行多源 NeoData 查询（async，~3 秒）──
    async def _fetch_neodata(q: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    NEODATA_URL,
                    headers={"Content-Type": "application/json", "Remote-URL": NEODATA_REMOTE},
                    json={"query": q, "request_id": uuid.uuid4().hex[:16], "data_type": "api"},
                )
                return resp.json() if resp.status_code == 200 else {}
        except Exception:
            return {}

    t0 = time.time()
    results = await asyncio.gather(
        _fetch_neodata(f"{user_query} 龙头股 成分股 今日行情 市盈率"),
        _fetch_neodata(f"{user_query} 资金流向 换手率 量比 主力净流入"),
        _fetch_neodata(f"{user_query} 热门概念 涨停板 异动 涨幅榜"),
    )
    print(f"  ⏱ NeoData parallel queries: {time.time()-t0:.1f}s")

    # ── Phase 2: 多源合并 + 去重 + 规则预筛 ──
    all_rows = []
    extra_texts = []
    seen_codes = set()

    def _parse_table(content: str) -> list:
        rows = []
        lines = content.split("\n")
        col_map = {}
        for line in lines:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cols = [c.strip() for c in line.split("|")]
            if "股票代码" in line and "股票名称" in line:
                for i, c in enumerate(cols):
                    c = c.strip()
                    if c in ("股票代码","股票名称","价格","涨跌幅","市盈率ttm","总市值",
                             "主力资金净流入（万元）","换手率","量比","个股标签","涨跌额"):
                        col_map[c] = i
                continue
            if "---" in line or len(cols) < 3:
                continue
            try:
                code = cols[col_map.get("股票代码", 1)] if col_map else cols[1]
                name = cols[col_map.get("股票名称", 2)] if col_map else cols[2]
                price = cols[col_map.get("价格", 3)] if col_map else cols[4]
                change = cols[col_map.get("涨跌幅", 4)] if col_map else cols[5]
                pe    = cols[col_map.get("市盈率ttm", -3)] if col_map else cols[-3]
                mcap  = cols[col_map.get("总市值", -2)] if col_map else cols[6]
                inflow = cols[col_map.get("主力资金净流入（万元）", -5)] if "主力资金净流入（万元）" in col_map else ""
                turn   = cols[col_map.get("换手率", -4)] if "换手率" in col_map else ""
                vol_r  = cols[col_map.get("量比", -3)] if "量比" in col_map else ""
                tag    = cols[col_map.get("个股标签", -1)] if col_map else cols[-2]
            except IndexError:
                continue
            if code and name and len(code) > 5:
                rows.append({
                    "code": code, "name": name, "price": price, "change": change,
                    "pe": pe, "mcap": mcap, "inflow": inflow, "turnover": turn,
                    "vol_ratio": vol_r, "note": tag,
                })
        return rows

    for result in results:
        api_recall = result.get("data", {}).get("apiData", {}).get("apiRecall", [])
        for recall in api_recall:
            ct = recall.get("content", "")
            if "股票代码" in ct and "股票名称" in ct:
                for r in _parse_table(ct):
                    if r["code"] not in seen_codes:
                        seen_codes.add(r["code"])
                        all_rows.append(r)
            elif len(ct) > 50:
                extra_texts.append(ct[:500])

    # 规则预评分
    for r in all_rows:
        try:
            r["_chg"] = float(str(r.get("change", "0")).replace("%", "").replace("+", ""))
        except ValueError:
            r["_chg"] = 0.0
        try:
            vor = float(str(r.get("vol_ratio", "0")).replace("-", "0"))
        except ValueError:
            vor = 0.0
        try:
            tor = float(str(r.get("turnover", "0")).replace("%", "").replace("-", "0"))
        except ValueError:
            tor = 0.0
        try:
            pe = float(str(r.get("pe", "999")).replace("-", "999"))
        except ValueError:
            pe = 999.0
        # 综合评分：涨幅权重最高 + 量比/换手辅助 - PE异常惩罚
        r["_score"] = r["_chg"] * 10 + vor * 3 + tor * 1.5
        if pe < 0 or pe > 500:   # 负PE或超高PE → 数据不可靠，严厉降权
            r["_score"] -= 30
        elif pe > 200:           # 高PE但尚可接受，小幅降权
            r["_score"] -= 10

    # 取 Top 15 送 LLM（保证覆盖度+减 token 消耗）
    all_rows.sort(key=lambda x: x["_score"], reverse=True)
    candidates = all_rows[:15]

    if not candidates:
        return JSONResponse(content={"answer": "未找到相关股票数据，请尝试更具体的选股方向", "picks": []})

    # ── Phase 3: LLM 深度分析（一次性生成，避免多轮）──
    context_lines = []
    for r in candidates:
        extras = []
        if r.get("inflow"):
            extras.append(f"主力流入{r['inflow']}万")
        if r.get("turnover"):
            extras.append(f"换手{r['turnover']}%")
        if r.get("vol_ratio"):
            extras.append(f"量比{r['vol_ratio']}")
        ext_str = " " + " ".join(extras) if extras else ""
        context_lines.append(
            f"{r['code']} {r['name']} 现价{r['price']} 涨跌{r['change']}% "
            f"PE{r['pe']} 市值{r['mcap']} 标签:{r['note']}{ext_str}"
        )

    full_context = (
        f"候选股（{len(candidates)}支，已按综合评分排序）：\n"
        f"{chr(10).join(context_lines)[:4000]}\n\n"
        f"市场背景：\n{chr(10)+'---'+chr(10).join(extra_texts[:3])[:1200]}"
    )

    system_prompt = """你是资深A股分析师。严格按以下标准从候选股中精选5支做对比推荐，输出纯JSON。

选股标准：
1. 涨幅趋势：涨停/持续强势优先，避免追高估值严重偏离的
2. 资金面：量比>2者优先，主力净流入为正加分
3. 估值安全：PE不宜过高（科技赛道放宽至80），市值过小（<30亿）需标注风险
4. 行业地位：龙头/白马/权重标签加分
5. 分散：5支覆盖≥3个板块，避免同质化

输出JSON格式（严格复制，不要任何额外文字、不要markdown）：
{"summary":"市场总结+热门方向（40字内）","confidence":0.85,"picks":[
  {"code":"000001","name":"平安银行","price":"12.34","change":"+5.2%",
   "analysis":{"technical":"放量突破前高 量比2.8","fundamental":"PE=8.5 银行股估值洼地","risk":"权重股波动小 短线空间有限"},
   "confidence":0.88}
]}

注意：
- summary 要包含市场情绪判断（如"资金偏好科技成长"）
- analysis 三要素必填：technical（技术面 含关键指标 12字内）、fundamental（基本面 含估值数据 15字内）、risk（风险点 12字内）
- confidence 是你对该推荐的把握度（0-1），涨幅证据链越强越接近1
- 整体confidence是所有pick的加权均值
- ⚠️ 不要选PE为负或PE>500的股票（数据不可靠）"""

    user_msg = f"选股需求：{user_query}\n\n{full_context}"

    t_llm = time.time()
    raw_answer = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _ask_llm_raw(system_prompt, user_msg, max_tokens=1536, temperature=0.3)
    )
    print(f"  ⏱ LLM analysis: {time.time()-t_llm:.1f}s")

    if not raw_answer or raw_answer.startswith("[LLM"):
        # LLM 不可用，返回规则评分 Top5 + 基本数据
        fallback_picks = []
        for r in candidates[:5]:
            fallback_picks.append({
                "code": r["code"], "name": r["name"], "price": r["price"],
                "change": r["change"] + ("" if "%" in str(r["change"]) else "%"),
                "analysis": {
                    "technical": f"综合评分{r.get('_score',0):.0f}",
                    "fundamental": f"PE={r['pe']} 市值{r['mcap']}亿",
                    "risk": "LLM离线 仅规则筛选"
                },
                "confidence": 0.4
            })
        return JSONResponse(content={
            "query": user_query, "summary": f"⚠️ AI分析暂时不可用，以下为规则筛选Top5（{raw_answer or '超时'}）",
            "confidence": 0.35, "picks": fallback_picks,
        })

    # ── Phase 4: JSON 解析 + 置信度后校验 ──
    picks = []
    summary = ""
    overall_conf = 0.0

    try:
        # 括号计数匹配最外层 JSON
        idx = raw_answer.find('"picks"')
        if idx >= 0:
            depth = 0
            start = idx
            while start > 0:
                start -= 1
                if raw_answer[start] == '}':
                    depth += 1
                elif raw_answer[start] == '{':
                    if depth == 0:
                        break
                    depth -= 1
            depth = 0
            end = idx
            while end < len(raw_answer):
                if raw_answer[end] == '{':
                    depth += 1
                elif raw_answer[end] == '}':
                    if depth == 0:
                        end += 1
                        break
                    depth -= 1
                end += 1
            parsed = json.loads(raw_answer[start:end])
            picks = parsed.get("picks", [])[:5]
            summary = parsed.get("summary", "")
            overall_conf = float(parsed.get("confidence", 0.5))
    except Exception:
        pass

    if not picks:
        # 最后一次降级：规则 Top5
        for r in candidates[:5]:
            picks.append({
                "code": r["code"], "name": r["name"], "price": r["price"],
                "change": r["change"] + ("" if "%" in str(r["change"]) else "%"),
                "analysis": {
                    "technical": "综合评分{}" % format(r.get("_score", 0), ".0f"),
                    "fundamental": f"PE={r['pe']} 市值{r['mcap']}亿",
                    "risk": "LLM解析失败 仅规则筛选",
                },
                "confidence": 0.4,
            })
        if not summary:
            summary = "LLM输出解析失败，以下为规则筛选Top5"
        overall_conf = 0.35

    # 后校验：对比规则评分 vs LLM 置信度，标注差异
    for p in picks:
        code = p.get("code", "")
        matched = [r for r in candidates if r["code"] == code]
        if matched:
            rule_score = matched[0].get("_score", 0)
            llm_conf = float(p.get("confidence", 0.5))
            # 规则评分高但LLM置信度低 → 置信度取均值
            if rule_score > 30 and llm_conf < 0.6:
                p["confidence"] = round((llm_conf + 0.6) / 2, 2)
                p["analysis"]["risk"] = (p.get("analysis", {}).get("risk", "") + " | 规则高评分").strip(" | ")
        # 确保 analysis 字段存在
        if "analysis" not in p or not isinstance(p.get("analysis"), dict):
            p["analysis"] = {"technical": "待补充", "fundamental": "待补充", "risk": "待分析"}

    print(f"  ✅ stock-pick done: {len(picks)} picks in {time.time()-t0:.1f}s total")
    return JSONResponse(content={
        "query": user_query,
        "summary": summary,
        "confidence": round(overall_conf, 2),
        "picks": picks,
    })


@app.get("/limit-up")
async def limit_up(request: Request):
    """涨停板 & 热门飙升"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    now = time.time()
    if _limit_up_cache["data"] and (now - _limit_up_cache["time"]) < CACHE_TTL:
        return JSONResponse(content=_limit_up_cache["data"])
    data = _query_limit_up()
    _limit_up_cache["data"] = data
    _limit_up_cache["time"] = now
    return JSONResponse(content=data)


@app.get("/abnormal")
async def abnormal(request: Request):
    """异动监控：量比/振幅/换手"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    now = time.time()
    if _abnormal_cache["data"] and (now - _abnormal_cache["time"]) < CACHE_TTL:
        return JSONResponse(content=_abnormal_cache["data"])
    data = _query_abnormal()
    _abnormal_cache["data"] = data
    _abnormal_cache["time"] = now
    return JSONResponse(content=data)


# ============================================================
# API - 管理员日志查看
# ============================================================

LOG_FILE = Path(__file__).parent / ".kb-webui.log"
BORE_LOG_FILE = Path(__file__).parent / ".kb-tunnel.log"


@app.get("/admin/access-log")
async def admin_access_log(request: Request, lines: int = 100):
    """查看访问日志 —— 需要管理员密码验证（前端 already gates with LINyao）"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    
    result = {"web_log": [], "bore_log": [], "total_requests": 0, "unique_ips": []}
    
    # 读web日志
    if LOG_FILE.exists():
        raw = LOG_FILE.read_text(errors="replace")
        web_lines = raw.strip().split("\n")[-lines:]
        # 提取重要行：请求行、错误、启动信息
        important = []
        for line in web_lines:
            stripped = line.strip()
            if not stripped:
                continue
            # 过滤掉标准uvicorn INFO日志里的无聊内容
            if any(kw in stripped for kw in ['GET ', 'POST ', 'DELETE ', 'PUT ', 'ERROR', 'WARNING', '启动', '密码', '模型', '图谱', '引擎', '前端', '向量', '公网', 'HTTP']):
                important.append(stripped)
        result["web_log"] = important
        
        # 统计
        ip_counts = {}
        for line in web_lines:
            match = __import__("re").search(r'(\d+\.\d+\.\d+\.\d+)', line)
            if match:
                ip = match.group(1)
                ip_counts[ip] = ip_counts.get(ip, 0) + 1
        result["total_requests"] = len(web_lines)
        result["unique_ips"] = sorted(ip_counts.items(), key=lambda x: -x[1])
    
    # 读bore日志
    if BORE_LOG_FILE.exists():
        raw = BORE_LOG_FILE.read_text(errors="replace")
        result["bore_log"] = [l.strip() for l in raw.strip().split("\n")[-20:] if l.strip()]
    
    return JSONResponse(content=result)


# ============================================================
# API - 学习引擎（反馈闭环）
# ============================================================


@app.post("/learn/feedback")
async def learn_feedback(request: Request):
    """提交用户反馈"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    if not learn:
        return JSONResponse(content={"error": "学习引擎未初始化"})

    body = await request.json()
    analysis_type = body.get("type", "vision")
    image_hash = body.get("image_hash", "")
    analysis = body.get("analysis", "")
    correction = body.get("correction", "").strip()
    rating = body.get("rating")
    image_base64 = body.get("image_base64", "")
    mime_type = body.get("mime_type", "image/jpeg")

    if not image_hash:
        return JSONResponse(content={"error": "缺少 image_hash"})
    if not correction or correction == analysis:
        return JSONResponse(content={"error": "修正内容不可为空或与原始相同"})

    result = learn.submit_feedback(
        feedback_type=analysis_type,
        image_hash=image_hash,
        analysis=analysis,
        correction=correction,
        rating=rating,
        image_base64=image_base64 if image_base64 else None,
        mime_type=mime_type,
    )
    return JSONResponse(content=result)


@app.get("/learn/memories")
async def learn_memories(request: Request, page: int = 1, page_size: int = 20):
    """获取记忆列表（分页）"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    if not learn:
        return JSONResponse(content={"memories": [], "total": 0, "page": 1})
    return JSONResponse(content=learn.get_memories(page=page, page_size=page_size))


@app.get("/learn/stats")
async def learn_stats(request: Request):
    """获取统计数据"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    if not learn:
        return JSONResponse(content={"total": 0, "rated": 0, "rated_pct": 0, "recent_7d": 0, "preferences_count": 0})
    return JSONResponse(content=learn.get_stats())


@app.delete("/learn/memories/{mem_id}")
async def learn_delete_memory(request: Request, mem_id: str):
    """删除指定记忆（含媒体文件）"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    if not learn:
        return JSONResponse(content={"error": "学习引擎未初始化"})
    ok = learn.delete_memory(mem_id)
    return JSONResponse(content={"status": "deleted" if ok else "not_found"})


@app.get("/learn/preferences")
async def learn_preferences(request: Request):
    """获取当前偏好规则列表"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    if not learn:
        return JSONResponse(content={"preferences": []})
    return JSONResponse(content={"preferences": learn.get_preferences()})


@app.put("/learn/settings")
async def learn_settings(request: Request):
    """更新设置（如 auto_apply）"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    if not learn:
        return JSONResponse(content={"error": "学习引擎未初始化"})
    body = await request.json()
    settings = learn.update_settings(body)
    return JSONResponse(content={"status": "saved", "settings": settings})


@app.get("/learn/settings")
async def learn_get_settings(request: Request):
    """获取当前设置"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    if not learn:
        return JSONResponse(content={"auto_apply": True, "total_feedbacks": 0})
    return JSONResponse(content=learn.get_settings())


@app.get("/learn/media/{mem_id}")
async def learn_media(request: Request, mem_id: str):
    """获取记忆关联的图片（缩略图）"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    if not learn:
        return JSONResponse(status_code=404, content={"error": "引擎未初始化"})

    media_path = learn.get_media(mem_id)
    if not media_path:
        return JSONResponse(status_code=404, content={"error": "媒体文件不存在"})

    from fastapi.responses import FileResponse
    ext = media_path.suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
    }
    return FileResponse(
        media_path,
        media_type=media_type_map.get(ext, "image/jpeg"),
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.delete("/learn/preferences")
async def learn_delete_preference(request: Request):
    """删除指定偏好规则"""
    if not _is_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "未认证"})
    if not learn:
        return JSONResponse(content={"error": "学习引擎未初始化"})
    body = await request.json()
    rule_text = body.get("rule", "")
    if not rule_text:
        return JSONResponse(content={"error": "缺少 rule 参数"})
    learn.delete_preference(rule_text)
    return JSONResponse(content={"status": "deleted"})


# ============================================================
# 静态文件服务
# ============================================================

# 挂载 /static 路由
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    print(f"  📁 静态文件目录: {STATIC_DIR}")
else:
    print(f"  ⚠️ 静态文件目录不存在: {STATIC_DIR}")


# ============================================================
# 启动
# ============================================================

def main():
    global graph, vector, password_hash

    parser = argparse.ArgumentParser(description="Knowledge Base Web UI")
    parser.add_argument("--vault", required=True, help="Obsidian vault 路径")
    parser.add_argument("--port", type=int, default=8080, help="Web UI 端口（默认 8080）")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama API 地址（仅用于嵌入模型）")
    parser.add_argument("--embedding-model", default="qwen3-embedding:4b", help="嵌入模型名")
    parser.add_argument("--lm-studio-url", default="http://localhost:1234/v1", help="LM Studio API 地址（LLM 生成）")
    parser.add_argument("--llm-model", default=None, help="LLM 生成模型（可通过环境变量 KB_LLM_MODEL 覆盖）")
    parser.add_argument("--skip-vector", action="store_true", help="跳过向量索引（仅图谱模式）")
    args = parser.parse_args()

    # 密码检查
    pwd = os.environ.get(PASSWORD_ENV)
    if not pwd:
        print(f"❌ 请设置环境变量 {PASSWORD_ENV}")
        print(f"   例: {PASSWORD_ENV}=yoursecret python3 web_ui.py --vault /path/to/vault")
        exit(1)
    password_hash = hashlib.sha256(pwd.encode()).hexdigest()
    print(f"🔑 密码已设置（SHA256: {password_hash[:12]}...）")

    # LLM 配置
    global lm_studio_url, llm_model
    lm_studio_url = args.lm_studio_url
    llm_model = args.llm_model or os.environ.get(LLM_MODEL_ENV, DEFAULT_LLM_MODEL)
    print(f"🤖 LLM 模型: {llm_model}")
    print(f"🔗 LM Studio API: {lm_studio_url}")

    # 构建图谱
    print(f"🏗️  构建 Wiki 图谱: {args.vault}")
    import time as _t
    start = _t.time()
    graph = WikiGraph(args.vault)
    print(f"✅ 图谱: {len(graph.nodes)} 页面, {len(graph.edges)} 边 ({_t.time()-start:.1f}s)")

    # 构建向量索引
    if not args.skip_vector:
        print(f"📊 初始化向量检索（模型: {args.embedding_model}）...")
        start = _t.time()
        vector = VectorSearcher(args.ollama_url, args.embedding_model)
        vector.index_vault(Path(args.vault) / "wiki")
        print(f"✅ 向量: {len(vector.chunks)} 块 ({_t.time()-start:.1f}s)")
    else:
        print("⏭️  跳过向量索引")

    # 初始化学习引擎
    global learn
    learn = LearnEngine()
    settings = learn.get_settings()
    print(f"🧠 学习引擎已初始化（auto_apply={settings.get('auto_apply', True)}, 总反馈={settings.get('total_feedbacks', 0)}）")

    # 检查静态文件
    static_index = STATIC_DIR / "index.html"
    if not static_index.exists():
        print(f"⚠️  {static_index} 不存在！前端页面将不可用。")
    else:
        print(f"✅ 前端页面: {static_index}")

    # 启动
    import uvicorn
    print(f"🚀 Web UI: http://0.0.0.0:{args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
