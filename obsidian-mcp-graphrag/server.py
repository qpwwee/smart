#!/usr/bin/env python3
"""
Obsidian Graph RAG MCP Server
==============================
分层检索架构：向量语义搜索 + Wiki 图谱遍历 + 动态查询路由

启动方式：
  python3 server.py --vault "/path/to/vault" --port 3004

工具列表：
  - graph_vector_search: 混合检索（语义+图谱）
  - vector_search: 纯语义向量检索
  - graph_traverse: 纯图谱遍历（多跳推理）
  - query_route: 智能查询路由（自动选择最佳检索策略）
  - graph_stats: 知识图谱统计信息
"""

import argparse
import json
import os
import re
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import httpx
from fastmcp import FastMCP

# ============================================================
# 核心数据结构
# ============================================================

class WikiGraph:
    """从 Obsidian Wiki 的 [[链接]] 构建 knowledge graph"""
    
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.wiki_path = self.vault_path / "wiki"
        self.nodes: dict = {}          # page_name -> {path, links, backlinks, category, ...}
        self.edges: list = []          # [{source, target, relation}, ...]
        self._build()
    
    def _build(self):
        """扫描 wiki/ 下所有 .md 文件，提取 [[链接]] 和关系标注"""
        link_pattern = re.compile(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]')
        relation_pattern = re.compile(r'\*?\*?(\u662f|\u4f7f\u7528|\u57fa\u4e8e|\u5f71\u54cd)\*?\*?')
        
        # 先收集所有页面
        for md_file in self.wiki_path.rglob("*.md"):
            if md_file.name == "log.md":
                continue
            rel = md_file.relative_to(self.wiki_path)
            page_name = md_file.stem
            parts = rel.parts
            category = parts[0] if len(parts) > 1 else "root"
            
            self.nodes[page_name] = {
                "path": str(rel),
                "full_path": str(md_file),
                "category": category,
                "links": [],        # 出站链接
                "backlinks": [],    # 入站链接
                "relations": {},    # target -> relation_type
            }
        
        # 解析链接和关系
        for page_name, node in self.nodes.items():
            try:
                content = Path(node["full_path"]).read_text(encoding="utf-8")
            except Exception:
                continue
            
            links_found = link_pattern.findall(content)
            for target in links_found:
                target = target.strip()
                if target in self.nodes and target != page_name:
                    if target not in node["links"]:
                        node["links"].append(target)
                    
                    # 检测关系标注
                    # 在链接前后搜索关系词
                    rel_type = self._detect_relation(content, target)
                    if rel_type:
                        node["relations"][target] = rel_type
                    
                    # 添加边
                    edge = {"source": page_name, "target": target, "relation": rel_type or "related"}
                    if edge not in self.edges:
                        self.edges.append(edge)
        
        # 计算反向链接
        for page_name, node in self.nodes.items():
            for target in node["links"]:
                if target in self.nodes:
                    if page_name not in self.nodes[target]["backlinks"]:
                        self.nodes[target]["backlinks"].append(page_name)
    
    def _detect_relation(self, content: str, target: str) -> Optional[str]:
        """在内容中检测指向 target 的链接的关系标注"""
        escaped = re.escape(target)

        # 方式1: 链接后面的标准关系标注 (如 "[[target]] — 是-关系")
        post_patterns = [
            (r'\[\[' + escaped + r'\]\].*?是-关系', '是'),
            (r'\[\[' + escaped + r'\]\].*?使用-关系', '使用'),
            (r'\[\[' + escaped + r'\]\].*?基于-关系', '基于'),
            (r'\[\[' + escaped + r'\]\].*?影响-关系', '影响'),
            # 行内括号格式 (如 "[[target]] 描述 【是-关系：...")")
            (r'\[\[' + escaped + r'\]\].*?【是-关系', '是'),
            (r'\[\[' + escaped + r'\]\].*?【使用-关系', '使用'),
            (r'\[\[' + escaped + r'\]\].*?【基于-关系', '基于'),
            (r'\[\[' + escaped + r'\]\].*?【影响-关系', '影响'),
        ]
        for pattern, rel_type in post_patterns:
            if re.search(pattern, content):
                return rel_type

        # 方式2: 链接前面的关系词 (如 "**是**...[[target]]")
        pre_patterns = [
            (r'\*\*是\*\*.*?\[\[' + escaped + r'\]\]', '是'),
            (r'\*\*使用\*\*.*?\[\[' + escaped + r'\]\]', '使用'),
            (r'\*\*基于\*\*.*?\[\[' + escaped + r'\]\]', '基于'),
            (r'\*\*影响\*\*.*?\[\[' + escaped + r'\]\]', '影响'),
            (r'是.*?\[\[' + escaped + r'\]\]', '是'),
            (r'使用.*?\[\[' + escaped + r'\]\]', '使用'),
            (r'基于.*?\[\[' + escaped + r'\]\]', '基于'),
            (r'影响.*?\[\[' + escaped + r'\]\]', '影响'),
        ]
        for pattern, rel_type in pre_patterns:
            if re.search(pattern, content):
                return rel_type

        return None
    def traverse(self, start: str, max_hops: int = 2, max_results: int = 20) -> list:
        """从 start 页面出发，沿链接做多跳遍历（BFS）"""
        if start not in self.nodes:
            return []
        
        visited = {start}
        queue = [(start, 0)]
        results = []
        
        while queue:
            current, hops = queue.pop(0)
            if hops >= max_hops:
                continue
            
            for neighbor in self.nodes[current]["links"]:
                if neighbor not in visited and len(results) < max_results:
                    visited.add(neighbor)
                    relation = self.nodes[current]["relations"].get(neighbor, "related")
                    results.append({
                        "page": neighbor,
                        "category": self.nodes[neighbor]["category"],
                        "relation": relation,
                        "hops": hops + 1,
                        "path": self.nodes[neighbor]["path"],
                    })
                    queue.append((neighbor, hops + 1))
            
            for neighbor in self.nodes[current]["backlinks"]:
                if neighbor not in visited and len(results) < max_results:
                    visited.add(neighbor)
                    relation = self.nodes[neighbor]["relations"].get(current, "related-to")
                    results.append({
                        "page": neighbor,
                        "category": self.nodes[neighbor]["category"],
                        "relation": f"referenced-by ({relation})",
                        "hops": hops + 1,
                        "path": self.nodes[neighbor]["path"],
                    })
                    queue.append((neighbor, hops + 1))
        
        return results
    
    def get_stats(self) -> dict:
        """返回图谱统计信息"""
        total_links = sum(len(n["links"]) for n in self.nodes.values())
        annotated = sum(1 for n in self.nodes.values() if n["relations"])
        total_edges_annotated = sum(1 for e in self.edges if e["relation"] != "related")
        
        hubs = sorted(self.nodes.keys(), key=lambda x: len(self.nodes[x]["backlinks"]), reverse=True)[:5]
        
        return {
            "total_pages": len(self.nodes),
            "total_edges": len(self.edges),
            "total_links": total_links,
            "avg_links_per_page": round(total_links / max(len(self.nodes), 1), 1),
            "pages_with_relations": annotated,
            "annotation_ratio": round(total_edges_annotated / max(len(self.edges), 1), 3),
            "top_hubs": [{"page": h, "backlinks": len(self.nodes[h]["backlinks"])} for h in hubs],
            "categories": defaultdict(int, {n["category"]: len([1 for x in self.nodes.values() if x["category"] == n["category"]]) for n in self.nodes.values()}),
        }


VECTOR_CACHE_FILE = Path(__file__).parent / "vector_cache.json"


class VectorSearcher:
    """通过 Ollama 嵌入模型做语义检索（支持持久化缓存）"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434", embedding_model: str = "qwen3-embedding:4b"):
        self.ollama_url = ollama_url
        self.embedding_model = embedding_model
        self.chunks: list = []      # [{text, page, category, path}, ...]
        self.embeddings: list = []  # 对应的向量
    
    def _get_file_manifest(self, wiki_path: Path) -> dict:
        """扫描 wiki/ 下所有 .md 文件，返回 {相对路径: 修改时间戳}"""
        manifest = {}
        for md_file in sorted(wiki_path.rglob("*.md")):
            if md_file.name == "log.md":
                continue
            rel = str(md_file.relative_to(wiki_path))
            manifest[rel] = md_file.stat().st_mtime
        return manifest
    
    def load_cache(self, wiki_path: Optional[Path] = None) -> bool:
        """从磁盘加载缓存的向量索引。
        如果提供 wiki_path，还会检查文件是否变化，变化时自动触发重建。
        成功返回 True。
        """
        if not VECTOR_CACHE_FILE.exists():
            return False
        try:
            data = json.loads(VECTOR_CACHE_FILE.read_text(encoding="utf-8"))
            self.chunks = data.get("chunks", [])
            self.embeddings = data.get("embeddings", [])
            
            # 检测文件是否变化：如果提供 wiki_path，对比文件清单
            if wiki_path:
                old_manifest = data.get("file_manifest", {})
                new_manifest = self._get_file_manifest(wiki_path)
                if old_manifest != new_manifest:
                    added = set(new_manifest) - set(old_manifest)
                    removed = set(old_manifest) - set(new_manifest)
                    modified = {f for f in new_manifest if f in old_manifest and new_manifest[f] != old_manifest[f]}
                    if added or removed or modified:
                        print(f"🔄 检测到文件变化: +{len(added)} 新增, -{len(removed)} 删除, ~{len(modified)} 修改")
                        print(f"   触发向量重索引...")
                        return False  # 返回 False 让调用方走重建流程
            
            print(f"✅ 从缓存加载向量索引: {len(self.chunks)} 块, {len(self.embeddings)} 嵌入")
            return True
        except Exception as e:
            print(f"⚠️ 缓存加载失败: {e}")
            return False
    
    def save_cache(self, wiki_path: Optional[Path] = None):
        """将向量索引保存到磁盘（同时保存文件清单用于过期检测）"""
        try:
            data = {
                "chunks": self.chunks,
                "embeddings": self.embeddings,
                "model": self.embedding_model,
                "file_manifest": self._get_file_manifest(wiki_path) if wiki_path else {},
            }
            VECTOR_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print(f"💾 向量索引已缓存: {len(self.chunks)} 块, {len(self.embeddings)} 嵌入")
        except Exception as e:
            print(f"⚠️ 缓存保存失败: {e}")
    
    def index_vault(self, wiki_path: Path, chunk_size: int = 500, force_reindex: bool = False):
        """索引 wiki/ 下所有页面。优先加载缓存（自动检测过期），force_reindex 时强制重建。"""
        # 尝试加载缓存（传入 wiki_path 用于过期检测）
        if not force_reindex and self.load_cache(wiki_path=wiki_path):
            return
        
        link_pattern = re.compile(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]')
        
        self.chunks = []
        self.embeddings = []
        
        for md_file in wiki_path.rglob("*.md"):
            if md_file.name == "log.md":
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            
            # 去掉 frontmatter
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    content = content[end+3:]
            
            # 清理链接标记
            clean = link_pattern.sub(r'\1', content)
            clean = re.sub(r'#+ ', '', clean)
            clean = re.sub(r'\*+', '', clean)
            clean = re.sub(r'> ', '', clean)
            clean = clean.strip()
            
            if not clean:
                continue
            
            rel = md_file.relative_to(wiki_path)
            parts = rel.parts
            category = parts[0] if len(parts) > 1 else "root"
            
            # 分块
            chunks = self._split_text(clean, chunk_size)
            for chunk in chunks:
                self.chunks.append({
                    "text": chunk,
                    "page": md_file.stem,
                    "category": category,
                    "path": str(rel),
                })
        
        # 批量生成嵌入（并发加速）
        self._generate_embeddings()
        # 缓存到磁盘（携带文件清单用于下次启动时的过期检测）
        self.save_cache(wiki_path=wiki_path)
    
    def _split_text(self, text: str, chunk_size: int) -> list:
        """按段落分块"""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current = ""
        for p in paragraphs:
            if len(current) + len(p) > chunk_size and current:
                chunks.append(current.strip())
                current = p
            else:
                current += "\n\n" + p if current else p
        if current.strip():
            chunks.append(current.strip())
        return chunks
    
    def _generate_embeddings(self):
        """通过 Ollama API 生成嵌入向量（使用并发池加速）"""
        if not self.chunks:
            return
        
        import concurrent.futures
        
        def _get_embedding(text: str) -> list:
            try:
                with httpx.Client(timeout=120) as client:
                    resp = client.post(
                        f"{self.ollama_url}/api/embeddings",
                        json={"model": self.embedding_model, "prompt": text[:1000]}
                    )
                    if resp.status_code == 200:
                        return resp.json().get("embedding", [])
            except Exception:
                pass
            return []
        
        total = len(self.chunks)
        print(f"🔄 生成 {total} 个嵌入向量（并发 5 路，模型: {self.embedding_model}）...", flush=True)
        
        self.embeddings = [None] * total
        done = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            future_map = {pool.submit(_get_embedding, c["text"]): i for i, c in enumerate(self.chunks)}
            for future in concurrent.futures.as_completed(future_map):
                idx = future_map[future]
                try:
                    self.embeddings[idx] = future.result()
                except Exception:
                    self.embeddings[idx] = []
                done += 1
                if done % 10 == 0 or done == total:
                    print(f"  📊 嵌入进度: {done}/{total}", flush=True)
        
        print(f"✅ 嵌入完成: {sum(1 for e in self.embeddings if e)}/{total} 成功", flush=True)
    
    def search(self, query: str, top_k: int = 5) -> list:
        """语义搜索：返回与 query 最相似的 top_k 个块"""
        if not self.embeddings or not self.chunks:
            return []
        
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"{self.ollama_url}/api/embeddings",
                    json={"model": self.embedding_model, "prompt": query}
                )
                if resp.status_code != 200:
                    return []
                query_vec = resp.json().get("embedding", [])
        except Exception:
            return []
        
        if not query_vec:
            return []
        
        # 计算余弦相似度
        scores = []
        for i, emb in enumerate(self.embeddings):
            if not emb or len(emb) != len(query_vec):
                scores.append(0)
                continue
            dot = sum(a * b for a, b in zip(query_vec, emb))
            norm_a = sum(a * a for a in query_vec) ** 0.5
            norm_b = sum(b * b for b in emb) ** 0.5
            scores.append(dot / (norm_a * norm_b) if norm_a and norm_b else 0)
        
        # 排序取 top_k
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        seen_pages = set()
        for idx, score in ranked:
            if len(results) >= top_k:
                break
            chunk = self.chunks[idx]
            if chunk["page"] not in seen_pages or top_k <= 3:
                results.append({
                    "page": chunk["page"],
                    "category": chunk["category"],
                    "path": chunk["path"],
                    "score": round(score, 4),
                    "excerpt": chunk["text"][:200],
                })
                seen_pages.add(chunk["page"])
        
        return results


class QueryRouter:
    """智能查询路由：根据查询类型选择最佳检索策略"""
    
    # 事实性查询关键词
    FACT_KEYWORDS = ["是什么", "什么是", "定义", "概念", "意思", "介绍", "how", "what", "define"]
    # 关系推理关键词
    RELATION_KEYWORDS = ["关系", "联系", "区别", "对比", "影响", "依赖", "基于", "vs", "和", "与", "之间"]
    # 操作指导关键词
    HOWTO_KEYWORDS = ["如何", "怎么", "方法", "步骤", "教程", "how to", "guide"]
    
    def route(self, query: str) -> dict:
        """分析查询，返回推荐检索策略"""
        q = query.lower()
        
        is_relation = any(kw in q for kw in self.RELATION_KEYWORDS)
        is_fact = any(kw in q for kw in self.FACT_KEYWORDS)
        is_howto = any(kw in q for kw in self.HOWTO_KEYWORDS)
        
        if is_relation:
            strategy = "graph_traverse"
            reason = "检测到关系/对比查询，优先使用图谱遍历"
        elif is_fact:
            strategy = "vector_search"
            reason = "检测到事实性查询，优先使用向量语义检索"
        elif is_howto:
            strategy = "hybrid"
            reason = "检测到操作指导查询，使用混合检索（向量+图谱）"
        else:
            strategy = "hybrid"
            reason = "通用查询，使用混合检索"
        
        return {
            "strategy": strategy,
            "reason": reason,
            "query_type": "relation" if is_relation else ("fact" if is_fact else ("howto" if is_howto else "general")),
        }


# ============================================================
# MCP Server 定义
# ============================================================

mcp = FastMCP(
    name="obsidian-graph-rag",
    version="1.0.0",
)

# 全局状态（在 main 中初始化）
graph: Optional[WikiGraph] = None
vector: Optional[VectorSearcher] = None
router = QueryRouter()


@mcp.tool()
def graph_vector_search(query: str, top_k: int = 5, max_hops: int = 2) -> str:
    """混合检索：向量语义搜索 + 图谱遍历，返回合并排序结果。
    
    适合：需要全面信息的通用查询
    
    Args:
        query: 查询文本
        top_k: 向量搜索返回的最大结果数
        max_hops: 图谱遍历的最大跳数
    """
    # 向量搜索
    vec_results = vector.search(query, top_k=top_k) if vector else []
    
    # 图谱扩展：从向量搜索的 top 结果出发做图谱遍历
    graph_results = []
    seen = set(r["page"] for r in vec_results)
    for vr in vec_results[:2]:  # 从 top 2 结果出发
        traversed = graph.traverse(vr["page"], max_hops=max_hops, max_results=10)
        for t in traversed:
            if t["page"] not in seen:
                graph_results.append(t)
                seen.add(t["page"])
    
    # 合并结果
    merged = []
    for r in vec_results:
        merged.append({**r, "source": "vector", "relevance": r["score"]})
    for r in graph_results:
        merged.append({**r, "source": "graph", "relevance": round(1.0 / (r["hops"] + 1), 3)})
    
    # 按 relevance 排序
    merged.sort(key=lambda x: x["relevance"], reverse=True)
    
    return json.dumps({
        "query": query,
        "strategy": "hybrid",
        "vector_results": len(vec_results),
        "graph_expansions": len(graph_results),
        "results": merged[:top_k * 2],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def vector_search(query: str, top_k: int = 5) -> str:
    """纯语义向量检索。适合：事实性查询（"什么是XX"）。
    
    Args:
        query: 查询文本
        top_k: 返回的最大结果数
    """
    results = vector.search(query, top_k=top_k) if vector else []
    return json.dumps({
        "query": query,
        "strategy": "vector",
        "results": results,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def graph_traverse(start_page: str, max_hops: int = 2, max_results: int = 15) -> str:
    """图谱遍历：从指定页面出发，沿 [[链接]] 做多跳推理。
    
    适合：关系推理（"XX和YY的关系""XX vs YY"）
    
    Args:
        start_page: 起始页面名（Wiki 链接名，如 "深度学习"）
        max_hops: 最大跳数（1=直接链接，2=二跳邻居）
        max_results: 返回的最大结果数
    """
    results = graph.traverse(start_page, max_hops=max_hops, max_results=max_results)
    node_info = graph.nodes.get(start_page, {})
    return json.dumps({
        "start_page": start_page,
        "strategy": "graph",
        "category": node_info.get("category", "unknown"),
        "direct_links": len(node_info.get("links", [])),
        "backlinks": len(node_info.get("backlinks", [])),
        "relations": node_info.get("relations", {}),
        "traversed": results,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def query_route(query: str) -> str:
    """智能查询路由：分析查询类型，推荐最佳检索策略。
    
    返回推荐的检索策略和参数，供调用方决定使用哪个工具。
    
    Args:
        query: 查询文本
    """
    routing = router.route(query)
    
    # 如果有图谱，尝试找到最相关的起始页面
    suggestions = []
    if graph:
        for page_name in graph.nodes:
            if page_name.lower() in query.lower() or query.lower() in page_name.lower():
                suggestions.append({
                    "page": page_name,
                    "category": graph.nodes[page_name]["category"],
                    "links": len(graph.nodes[page_name]["links"]),
                })
    
    return json.dumps({
        **routing,
        "suggested_start_pages": suggestions[:5],
        "recommended_tool": {
            "vector_search": "vector_search",
            "graph_traverse": "graph_traverse", 
            "hybrid": "graph_vector_search",
        }.get(routing["strategy"], "graph_vector_search"),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def graph_stats() -> str:
    """返回知识图谱的统计信息和健康指标。"""
    stats = graph.get_stats() if graph else {}
    vector_stats = {
        "indexed_chunks": len(vector.chunks) if vector else 0,
        "embedding_dim": len(vector.embeddings[0]) if vector and vector.embeddings else 0,
    } if vector else {}
    
    return json.dumps({
        "graph": stats,
        "vector_index": vector_stats,
    }, ensure_ascii=False, indent=2)


# ============================================================
# 后台自动刷新：定期检测文件变化并重建向量索引
# ============================================================

WIKI_PATH_FOR_REFRESH: Optional[Path] = None
VAULT_PATH_FOR_REFRESH: Optional[str] = None


def _background_refresh_loop():
    """每 5 分钟检查一次 wiki 文件是否变化，变化时自动重建向量索引"""
    global vector, graph, WIKI_PATH_FOR_REFRESH
    CHECK_INTERVAL = 300  # 5 分钟

    while True:
        time.sleep(CHECK_INTERVAL)
        if vector is None or WIKI_PATH_FOR_REFRESH is None:
            continue

        # 检查文件是否变化
        new_manifest = vector._get_file_manifest(WIKI_PATH_FOR_REFRESH)
        old_manifest = {}  # 将从当前缓存中提取
        try:
            if VECTOR_CACHE_FILE.exists():
                old_data = json.loads(VECTOR_CACHE_FILE.read_text(encoding="utf-8"))
                old_manifest = old_data.get("file_manifest", {})
        except Exception:
            pass

        if old_manifest == new_manifest:
            continue  # 无变化

        added = set(new_manifest) - set(old_manifest)
        removed = set(old_manifest) - set(new_manifest)
        modified = {f for f in new_manifest if f in old_manifest and new_manifest[f] != old_manifest[f]}

        print(f"\n🔄 [后台刷新] 检测到文件变化: +{len(added)} 新增, -{len(removed)} 删除, ~{len(modified)} 修改")
        print(f"   ⚡ 自动重建向量索引...")

        # 重建（使用新的 VectorSearcher 避免影响当前正在服务的实例）
        try:
            new_vector = VectorSearcher(vector.ollama_url, vector.embedding_model)
            new_vector.index_vault(WIKI_PATH_FOR_REFRESH, force_reindex=True)
            # 切换引用
            vector = new_vector
            # 同时重建图谱
            graph = WikiGraph(VAULT_PATH_FOR_REFRESH)
            print(f"✅ [后台刷新] 向量索引和图谱已更新 ({len(new_vector.chunks)} 块)")
        except Exception as e:
            print(f"❌ [后台刷新] 重建失败: {e}")


def _start_background_refresh(vault_path: str, wiki_path: Path):
    """启动后台刷新线程"""
    global WIKI_PATH_FOR_REFRESH, VAULT_PATH_FOR_REFRESH
    WIKI_PATH_FOR_REFRESH = wiki_path
    VAULT_PATH_FOR_REFRESH = vault_path
    t = threading.Thread(target=_background_refresh_loop, daemon=True)
    t.start()
    print(f"⏰ 后台刷新已启动（每 5 分钟检测文件变化）")


# ============================================================
# 启动入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Obsidian Graph RAG MCP Server")
    parser.add_argument("--vault", required=True, help="Obsidian vault 路径")
    parser.add_argument("--port", type=int, default=3004, help="SSE 端口（默认 3004）")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama API 地址")
    parser.add_argument("--embedding-model", default="qwen3-embedding:4b", help="嵌入模型名")
    parser.add_argument("--skip-vector", action="store_true", help="跳过向量索引（仅图谱模式）")
    parser.add_argument("--reindex", action="store_true", help="强制重建向量索引（忽略缓存）")
    parser.add_argument("--transport", default="sse", choices=["sse", "stdio"], help="MCP 传输模式（默认 sse）")
    args = parser.parse_args()
    
    global graph, vector
    
    print(f"🏗️  构建 Wiki 图谱: {args.vault}")
    start = time.time()
    graph = WikiGraph(args.vault)
    print(f"✅ 图谱构建完成: {len(graph.nodes)} 页面, {len(graph.edges)} 边 ({time.time()-start:.1f}s)")
    
    if not args.skip_vector:
        print(f"📊 初始化向量检索（模型: {args.embedding_model}）...")
        start = time.time()
        vector = VectorSearcher(args.ollama_url, args.embedding_model)
        # 尝试加载缓存；缓存不存在时自动构建
        if args.reindex:
            print("🔄 强制重建向量索引（--reindex）")
        vector.index_vault(Path(args.vault) / "wiki", force_reindex=args.reindex)
        elapsed = time.time() - start
        print(f"✅ 向量检索就绪: {len(vector.chunks)} 块, {len(vector.embeddings)} 嵌入 ({elapsed:.1f}s)")
    else:
        print("⏭️  跳过向量索引（--skip-vector）")
    
    # 启动后台刷新（每 5 分钟检测文件变化）
    if not args.skip_vector:
        _start_background_refresh(args.vault, Path(args.vault) / "wiki")
    
    if args.transport == "stdio":
        print(f"🚀 启动 MCP Server (stdio 模式)")
        mcp.run(transport="stdio")
    else:
        print(f"🚀 启动 MCP Server: http://localhost:{args.port}/sse")
        mcp.run(transport="sse", port=args.port)


if __name__ == "__main__":
    main()
