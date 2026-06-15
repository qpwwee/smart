"""
学习引擎核心 — AI 学习进化训练 v2.0
========================================
负责：反馈处理、偏好蒸馏、检索增强、记忆管理

完全本地化，基于 Python 标准库 + httpx 调用 Ollama API。
"""

import base64
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx

# ============================================================
# 配置
# ============================================================

DATA_DIR = Path(__file__).parent / "learn_data"
MEMORIES_FILE = DATA_DIR / "memories.jsonl"
PREFERENCES_FILE = DATA_DIR / "preferences.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
MEDIA_DIR = DATA_DIR / "media"

# 嵌入模型配置
EMBEDDING_URL = "http://localhost:11434/api/embeddings"
EMBEDDING_MODEL = "qwen3-embedding:4b"  # 替代 bge-m3
EMBEDDING_TIMEOUT = 60  # 秒

# 偏好规则最大活跃数
MAX_ACTIVE_PREFERENCES = 20

# 检索增强取 top-k 相似记忆
RETRIEVAL_TOP_K = 3

# 图片描述最大长度（降低二次推理开销）
DESC_MAX_LENGTH = 30


# ============================================================
# 推理互斥锁
# ============================================================

_inference_lock = threading.Lock()


def get_inference_lock():
    """获取推理互斥锁——确保同一时间只有一个模型在推理"""
    return _inference_lock


# ============================================================
# 偏好蒸馏规则
# ============================================================

# 规则模版：(关键词模式, 提取规则文本)
PREFERENCE_PATTERNS = [
    # 泛称 → 具体品种
    (r"一只动物", "用具体品种代替泛称'动物'"),
    (r"一只狗", "用具体品种代替泛称'狗'"),
    (r"一只猫", "用具体品种代替泛称'猫'"),
    (r"一只鸟", "用具体品种代替泛称'鸟'"),
    (r"一个人", "描述人物时包含外貌特征（发型/眼镜/服饰）"),
    # 食物具体化
    (r"桌上有食物", "具体化食物种类和配料"),
    (r"一碗(\S{0,3})$", "具体化食物种类和配料"),
    (r"一些食物", "具体化食物种类和配料"),
    # 汽车细节
    (r"红色汽车", "补充品牌型号等细节信息"),
    (r"一辆(\S{0,3})$", "补充品牌型号等细节信息"),
    (r"白色汽车", "补充品牌型号等细节信息"),
    # 场景细节
    (r"一个房间", "描述房间类型和装饰风格"),
    (r"户外场景", "说明具体地点和环境特征"),
    (r"一座建筑", "说明建筑类型和风格特征"),
    # 人物细节
    (r"一个男人|一个女人", "描述人物时包含外貌特征（发型/眼镜/服饰）"),
    (r"一个小孩", "描述人物时包含外貌特征（发型/服饰/动作）"),
    # 通用细节化
    (r"一个(\S{1,3})$", "尽量使用更具体的描述词"),
]


def extract_preferences(original: str, correction: str) -> list[str]:
    """对比原始分析与用户修正，提取可复用的偏好规则"""
    rules = []
    import re

    orig = original.strip()
    corr = correction.strip()

    if not orig or not corr or orig == corr:
        return rules

    origin_len = len(orig)
    corr_len = len(corr)

    # 1. 模式匹配
    for pattern, rule in PREFERENCE_PATTERNS:
        if re.search(pattern, orig) and rule not in rules:
            rules.append(rule)

    # 2. 长度差异分析：修正明显更长 → 用户偏好更详细描述
    if corr_len > origin_len * 1.5 and corr_len > 30:
        rule = "偏好更详细的描述（包含更多细节）"
        if rule not in rules:
            rules.append(rule)

    # 3. 具体数字增多
    orig_numbers = len(re.findall(r"\d+", orig))
    corr_numbers = len(re.findall(r"\d+", corr))
    if corr_numbers > orig_numbers + 1:
        rule = "偏好包含具体数字/数据的描述"
        if rule not in rules:
            rules.append(rule)

    # 4. 颜色词增多
    color_words = ["红色", "蓝色", "绿色", "黄色", "黑色", "白色", "紫色",
                   "粉色", "灰色", "橙色", "棕色", "金色", "银色"]
    orig_colors = sum(1 for c in color_words if c in orig)
    corr_colors = sum(1 for c in color_words if c in corr)
    if corr_colors > orig_colors:
        rule = "偏好包含颜色信息的描述"
        if rule not in rules:
            rules.append(rule)

    # 5. 专有名词/品牌检测
    brand_words = ["特斯拉", "苹果", "华为", "小米", "耐克", "阿迪达斯", "LV", "Gucci",
                   "星巴克", "麦当劳", "肯德基", "BMW", "奔驰", "奥迪", "丰田", "本田"]
    orig_brands = sum(1 for b in brand_words if b in orig)
    corr_brands = sum(1 for b in brand_words if b in corr)
    if corr_brands > orig_brands:
        rule = "偏好识别并标注品牌名称"
        if rule not in rules:
            rules.append(rule)

    # 6. 情感/氛围词增多
    emotion_words = ["温馨", "浪漫", "神秘", "热闹", "安静", "混乱", "整洁",
                     "温馨的", "浪漫的", "神秘的", "热闹的", "安静的", "混乱的", "整洁的"]
    orig_emotion = sum(1 for e in emotion_words if e in orig)
    corr_emotion = sum(1 for e in emotion_words if e in corr)
    if corr_emotion > orig_emotion:
        rule = "偏好描述场景氛围/情感"
        if rule not in rules:
            rules.append(rule)

    # 如果没有匹配到任何规则但有修正，添加通用规则
    if not rules and corr_len > origin_len * 1.2:
        rules.append("偏好更具体详尽的描述")

    return rules


# ============================================================
# 学习引擎核心类
# ============================================================


class LearnEngine:
    """学习引擎：管理记忆、偏好、检索增强"""

    def __init__(self, embedding_url: str = None, embedding_model: str = None):
        self.embedding_url = embedding_url or EMBEDDING_URL
        self.embedding_model = embedding_model or EMBEDDING_MODEL
        self._init_files()

    # ─── 文件初始化 ───────────────────────────────────────

    def _init_files(self):
        """创建数据目录和初始文件"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)

        if not MEMORIES_FILE.exists():
            MEMORIES_FILE.touch()
            print(f"  📝 创建: {MEMORIES_FILE}")

        if not PREFERENCES_FILE.exists():
            self._save_preferences([])
            print(f"  📝 创建: {PREFERENCES_FILE}")

        if not SETTINGS_FILE.exists():
            self._save_settings({
                "auto_apply": True,
                "total_feedbacks": 0,
                "auto_popup": True,
            })
            print(f"  📝 创建: {SETTINGS_FILE}")

    def _save_preferences(self, prefs: list):
        with open(PREFERENCES_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)

    def _load_preferences(self) -> list:
        if PREFERENCES_FILE.exists():
            with open(PREFERENCES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_settings(self, settings: dict):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

    def _load_settings(self) -> dict:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"auto_apply": True, "total_feedbacks": 0, "auto_popup": True}

    def _read_memories(self) -> list[dict]:
        """读取所有记忆"""
        memories = []
        if MEMORIES_FILE.exists():
            with open(MEMORIES_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            memories.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return memories

    def _write_memories(self, memories: list[dict]):
        """全量写入记忆（替换）"""
        with open(MEMORIES_FILE, "w", encoding="utf-8") as f:
            for m in memories:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")

    def _append_memory(self, memory: dict):
        """追加一条记忆"""
        with open(MEMORIES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(memory, ensure_ascii=False) + "\n")

    # ─── 嵌入计算 ────────────────────────────────────────

    def compute_embedding(self, text: str) -> Optional[list[float]]:
        """计算文本的嵌入向量（通过 Ollama）"""
        if not text or not text.strip():
            return None

        with _inference_lock:
            try:
                with httpx.Client(timeout=EMBEDDING_TIMEOUT) as client:
                    resp = client.post(
                        self.embedding_url,
                        json={
                            "model": self.embedding_model,
                            "prompt": text.strip(),
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return data.get("embedding")
                    print(f"  ⚠️ 嵌入计算失败 HTTP {resp.status_code}: {resp.text[:200]}")
                    return None
            except Exception as e:
                print(f"  ⚠️ 嵌入计算异常: {e}")
                return None

    # ─── 图片描述生成（用于检索嵌入） ──────────────────────

    def generate_image_description(self, image_base64: str, mime_type: str,
                                   vision_fn) -> str:
        """
        对图片生成简短描述（≤30字），作为检索的语义锚点。
        vision_fn: 函数 (query, img_b64, mime) -> 文本描述
        """
        query = "用一句话（不超过30字）描述这张图片的核心内容，不要任何额外说明。"
        try:
            desc = vision_fn(query, image_base64, mime_type, max_tokens=64)
            if desc and len(desc) > DESC_MAX_LENGTH:
                desc = desc[:DESC_MAX_LENGTH]
            return desc or ""
        except Exception as e:
            print(f"  ⚠️ 图片描述生成失败: {e}")
            return ""

    # ─── 相似度检索 ──────────────────────────────────────

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """余弦相似度"""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def search_similar_memories(self, query_embedding: list[float],
                                top_k: int = None) -> list[dict]:
        """
        从记忆库中检索语义最相似的历史修正记录。
        仅返回有用户修正的记忆。
        """
        if not query_embedding:
            return []

        k = top_k or RETRIEVAL_TOP_K
        memories = self._read_memories()

        # 筛选有嵌入且有修正的记录
        scored = []
        for m in memories:
            if m.get("embedding") and m.get("correction"):
                sim = self._cosine_similarity(query_embedding, m["embedding"])
                scored.append((sim, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:k]]

    # ─── 反馈处理 ────────────────────────────────────────

    def submit_feedback(self, feedback_type: str, image_hash: str,
                        analysis: str, correction: str,
                        rating: int = None, image_base64: str = None,
                        mime_type: str = "image/jpeg") -> dict:
        """
        提交用户反馈：去重 → 蒸馏偏好 → 存储记忆 → 异步计算嵌入

        Returns: {"id": str, "status": "created"|"updated"}
        """
        memories = self._read_memories()

        # 去重：根据 image_hash 查找已有记忆
        existing = None
        for m in memories:
            if m.get("image_hash") == image_hash:
                existing = m
                break

        # 蒸馏偏好规则
        new_rules = extract_preferences(analysis, correction)

        if existing:
            # 更新已有记忆
            existing["correction"] = correction
            existing["rating"] = rating
            existing["preferences"] = list(set(
                existing.get("preferences", []) + new_rules
            ))
            existing["created_at"] = _now_iso()
            self._write_memories(memories)

            # 后台异步计算嵌入
            threading.Thread(
                target=self._background_embed, args=(existing,),
                daemon=True,
            ).start()

            # 更新偏好库
            self._update_preference_rules(new_rules, existing["id"])

            return {"id": existing["id"], "status": "updated"}

        # 创建新记忆
        mem_id = f"mem_{uuid.uuid4().hex[:8]}"

        # 保存图片到媒体目录
        media_path = ""
        if image_base64:
            media_path = self._save_media(mem_id, image_base64, mime_type)

        memory = {
            "id": mem_id,
            "type": feedback_type,
            "image_hash": image_hash,
            "analysis": analysis,
            "correction": correction,
            "rating": rating,
            "preferences": new_rules,
            "media_path": media_path,
            "embedding": None,
            "created_at": _now_iso(),
        }

        self._append_memory(memory)

        # 后台异步计算嵌入（需要先有描述）
        threading.Thread(
            target=self._background_embed, args=(memory,),
            daemon=True,
        ).start()

        # 更新偏好库
        self._update_preference_rules(new_rules, mem_id)

        # 更新总反馈计数
        settings = self._load_settings()
        settings["total_feedbacks"] = settings.get("total_feedbacks", 0) + 1
        self._save_settings(settings)

        return {"id": mem_id, "status": "created"}

    def _background_embed(self, memory: dict):
        """后台上传内存计算嵌入"""
        # 用原始分析文本计算嵌入（因为 correction 可能不是对图片的描述）
        text = memory.get("correction") or memory.get("analysis", "")
        if not text.strip():
            return

        embedding = self.compute_embedding(text)
        if embedding:
            # 更新磁盘上的记录
            memories = self._read_memories()
            for m in memories:
                if m["id"] == memory["id"]:
                    m["embedding"] = embedding
                    break
            self._write_memories(memories)

    # ─── 媒体文件保存 ─────────────────────────────────────

    def _save_media(self, mem_id: str, image_base64: str,
                    mime_type: str = "image/jpeg") -> str:
        """保存 base64 图片到媒体目录，返回相对路径"""
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }
        ext = ext_map.get(mime_type, ".jpg")
        filename = f"{mem_id}{ext}"
        filepath = MEDIA_DIR / filename

        try:
            img_data = base64.b64decode(image_base64)
            filepath.write_bytes(img_data)
            return str(filepath)
        except Exception as e:
            print(f"  ⚠️ 保存媒体失败: {e}")
            return ""

    def get_media(self, mem_id: str) -> Optional[Path]:
        """根据记忆 ID 获取媒体文件路径"""
        memories = self._read_memories()
        for m in memories:
            if m["id"] == mem_id and m.get("media_path"):
                path = Path(m["media_path"])
                if path.exists():
                    return path
        # 后备：直接查找
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            candidate = MEDIA_DIR / f"{mem_id}{ext}"
            if candidate.exists():
                return candidate
        return None

    # ─── 偏好规则维护 ─────────────────────────────────────

    def _update_preference_rules(self, new_rules: list[str], source_id: str):
        """更新偏好规则库：新规则追加，已有规则递增计数"""
        prefs = self._load_preferences()

        for rule_text in new_rules:
            found = None
            for p in prefs:
                if p["rule"] == rule_text:
                    found = p
                    break
            if found:
                found["count"] = found.get("count", 1) + 1
                if source_id not in found.get("sources", []):
                    found.setdefault("sources", []).append(source_id)
            else:
                prefs.append({
                    "rule": rule_text,
                    "sources": [source_id],
                    "count": 1,
                    "active": True,
                })

        # 按频次排序，保留 top MAX_ACTIVE_PREFERENCES
        prefs.sort(key=lambda x: x["count"], reverse=True)
        # 归档超出部分（保留但标记 inactive）
        for i, p in enumerate(prefs):
            p["active"] = i < MAX_ACTIVE_PREFERENCES

        self._save_preferences(prefs)

    def get_preferences(self, active_only: bool = True) -> list[dict]:
        """获取偏好规则列表"""
        prefs = self._load_preferences()
        if active_only:
            prefs = [p for p in prefs if p.get("active", True)]
        return prefs[:MAX_ACTIVE_PREFERENCES]

    def delete_preference(self, rule_text: str):
        """删除指定偏好规则"""
        prefs = self._load_preferences()
        prefs = [p for p in prefs if p["rule"] != rule_text]
        self._save_preferences(prefs)

    # ─── 设置管理 ────────────────────────────────────────

    def get_settings(self) -> dict:
        return self._load_settings()

    def update_settings(self, updates: dict) -> dict:
        settings = self._load_settings()
        settings.update(updates)
        self._save_settings(settings)
        return settings

    # ─── 记忆 CRUD ───────────────────────────────────────

    def get_memories(self, page: int = 1, page_size: int = 20) -> dict:
        """分页获取记忆列表（倒序）"""
        memories = self._read_memories()
        memories.sort(key=lambda m: m.get("created_at", ""), reverse=True)

        total = len(memories)
        start = (page - 1) * page_size
        end = start + page_size
        page_data = memories[start:end]

        return {
            "memories": page_data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    def delete_memory(self, mem_id: str) -> bool:
        """删除指定记忆及其关联媒体文件"""
        memories = self._read_memories()

        target = None
        for m in memories:
            if m["id"] == mem_id:
                target = m
                break

        if not target:
            return False

        # 删除媒体文件
        if target.get("media_path"):
            try:
                Path(target["media_path"]).unlink(missing_ok=True)
            except Exception:
                pass

        # 更新文件
        memories = [m for m in memories if m["id"] != mem_id]
        self._write_memories(memories)
        return True

    def get_stats(self) -> dict:
        """获取统计数据"""
        memories = self._read_memories()
        total = len(memories)
        rated = sum(1 for m in memories if m.get("rating") is not None)
        prefs = self.get_preferences()

        # 近 7 天趋势
        now = time.time()
        seven_days_ago = now - 7 * 86400
        recent_7d = 0
        for m in memories:
            try:
                ts = _parse_iso(m.get("created_at", ""))
                if ts and ts > seven_days_ago:
                    recent_7d += 1
            except Exception:
                pass

        return {
            "total": total,
            "rated": rated,
            "rated_pct": round(rated / total * 100, 1) if total > 0 else 0,
            "recent_7d": recent_7d,
            "preferences_count": len(prefs),
        }

    # ─── 增强 prompt 组装 ─────────────────────────────────

    def build_enhanced_prompt(self, image_base64: str, mime_type: str,
                              vision_fn, base_prompt: str = None) -> str:
        """
        组装增强 prompt：偏好规则 + 检索相似案例 + 基础 prompt

        vision_fn: 用于生成图片简短描述（检索用）
        返回增强后的完整系统提示词
        """
        settings = self._load_settings()
        base = base_prompt or "请描述这张图片的内容。"

        if not settings.get("auto_apply", True):
            return base

        prompt_parts = []

        # 1. 注入偏好规则
        prefs = self.get_preferences(active_only=True)
        if prefs:
            pref_lines = []
            for p in prefs:
                pref_lines.append(f"- {p['rule']}")
            prompt_parts.append(
                "[用户偏好参考]\n"
                "根据历史修正记录，用户偏好以下描述方式：\n" +
                "\n".join(pref_lines)
            )

        # 2. 检索相似案例
        try:
            desc = self.generate_image_description(
                image_base64, mime_type, vision_fn
            )
            if desc:
                query_emb = self.compute_embedding(desc)
                if query_emb:
                    similar = self.search_similar_memories(query_emb)
                    if similar:
                        examples = []
                        for i, m in enumerate(similar, 1):
                            orig = m["analysis"][:150]
                            corr = m["correction"][:150]
                            examples.append(
                                f"示例{i}：\n"
                                f"  原始分析：{orig}\n"
                                f"  用户修正：{corr}"
                            )
                        prompt_parts.append(
                            "[相似案例参考]\n"
                            "以下是用户对类似图片的修正记录，请参考其描述风格：\n\n" +
                            "\n\n".join(examples)
                        )
        except Exception as e:
            print(f"  ⚠️ 检索增强跳过: {e}")

        if prompt_parts:
            return "\n\n".join(prompt_parts) + f"\n\n---\n\n{base}"

        return base


# ============================================================
# 工具函数
# ============================================================


def _now_iso() -> str:
    """当前 UTC 时间 ISO 格式"""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_iso(ts: str) -> Optional[float]:
    """解析 ISO 时间戳为 Unix 时间"""
    try:
        import datetime
        dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
    except Exception:
        return None


def compute_image_hash(image_bytes: bytes) -> str:
    """计算图片 SHA-256 哈希"""
    return hashlib.sha256(image_bytes).hexdigest()[:16]
