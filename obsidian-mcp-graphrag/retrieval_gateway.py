#!/usr/bin/env python3
"""
检索网关 API - 为 Web UI 提供 graph-rag 多策略检索能力
======================================================
暴露 HTTP REST API，自动执行 query_route → 多策略检索 → 返回结果

启动:  python3 retrieval_gateway.py [端口]
默认:  http://localhost:3007

API:
  GET /search?q=你的问题     → 多策略检索结果
  GET /search?q=xxx&raw=1   → 返回完整页面内容
  GET /health               → 服务状态

Web UI 接入方式：将 RAG 的搜索请求改为调此 API
"""

import json
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

# ── 添加 graph-rag 路径 ──
GRAPH_RAG_DIR = "/Users/pon/Documents/obsidian-mcp-graphrag"
sys.path.insert(0, GRAPH_RAG_DIR)
from server import WikiGraph, VectorSearcher, QueryRouter

VAULT_PATH = "/Users/pon/Documents/obsidian- knowledge"
WIKI_PATH = os.path.join(VAULT_PATH, "wiki")


# ══════════════════════════════════════════════════════════════
# 初始化检索引擎
# ══════════════════════════════════════════════════════════════
print("🔄 初始化检索网关...")

graph = WikiGraph(VAULT_PATH)
print(f"  ✅ WikiGraph: {len(graph.nodes)} 页面, {len(graph.edges)} 条链接")

vector = VectorSearcher()
cache_loaded = vector.load_cache(Path(WIKI_PATH))
if not cache_loaded:
    print("  ⚠️  向量缓存加载失败，尝试重建...")
    vector.index_vault(Path(WIKI_PATH))
print(f"  ✅ VectorSearcher: {len(vector.chunks)} 个文本块")

router = QueryRouter()
print(f"  ✅ QueryRouter 就绪")
print(f"🚀 检索网关初始化完成")


# ══════════════════════════════════════════════════════════════
# HTTP 服务
# ══════════════════════════════════════════════════════════════
class SearchHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/health":
            return self._json({
                "status": "ok",
                "pages": len(graph.nodes),
                "links": len(graph.edges),
                "chunks": len(vector.chunks),
                "top_hubs": graph.top_hubs[:5] if hasattr(graph, 'top_hubs') else []
            })

        if path == "/search":
            query = params.get("q", [None])[0]
            if not query:
                return self._json({"error": "缺少 ?q= 参数"}, 400)

            raw_mode = params.get("raw", ["0"])[0] in ("1", "true")
            results = self._search(query, raw_mode)
            return self._json(results)

        # 页面内容查询
        if path == "/page":
            page = params.get("name", [None])[0]
            if page and page in graph.nodes:
                info = graph.nodes[page]
                file_path = os.path.join(WIKI_PATH, info["path"])
                try:
                    content = Path(file_path).read_text(encoding="utf-8")
                    return self._json({
                        "page": page,
                        "path": info["path"],
                        "category": info.get("category", ""),
                        "links": info.get("links", []),
                        "backlinks": info.get("backlinks", []),
                        "content": content[:3000]
                    })
                except Exception as e:
                    return self._json({"error": str(e)}, 500)
            return self._json({"error": "页面不存在"}, 404)

        return self._json({"error": "Not found"}, 404)

    # ── 核心检索逻辑 ──
    def _search(self, query: str, raw_mode: bool = False) -> dict:
        """多策略检索：自动选择最佳策略"""
        
        # 1️⃣ 查询路由
        route = router.route(query)
        strategy = route["strategy"]
        
        result = {
            "query": query,
            "route": route,
            "strategy": strategy,
        }

        if raw_mode:
            # 原始模式：直接返回向量搜索结果（给 Web UI 做 RAG 注入用）
            vec_results = vector.search(query, top_k=5)
            result["results"] = [{
                "page": r["page"],
                "category": r["category"],
                "path": r["path"],
                "score": r["score"],
                "excerpt": r["excerpt"],
                "content": self._read_full_content(r["path"])
            } for r in vec_results]
            result["total"] = len(result["results"])
            return result

        # 2️⃣ 按路由策略执行
        if strategy == "graph_traverse":
            # 关系/对比查询 → 向量找起点 → 图谱遍历
            vec_results = vector.search(query, top_k=3)
            pages_found = []
            for vr in vec_results:
                pages_found.append({
                    "page": vr["page"],
                    "score": vr["score"],
                    "category": vr["category"],
                    "excerpt": vr["excerpt"],
                })
            
            # 从 top 结果出发做图遍历
            graph_expansions = []
            for vr in vec_results[:2]:
                traversed = graph.traverse(vr["page"], max_hops=2, max_results=10)
                for t in traversed:
                    graph_expansions.append({
                        "page": t["page"],
                        "relation": t.get("relation", "related"),
                        "category": t.get("category", ""),
                        "hops": t.get("hops", 1),
                    })
            
            result["vector_hits"] = pages_found
            result["graph_expansions"] = graph_expansions
            result["total"] = len(pages_found) + len(graph_expansions)

        elif strategy == "vector_search":
            # 事实查询 → 向量搜索
            vec_results = vector.search(query, top_k=5)
            result["results"] = [{
                "page": r["page"],
                "category": r["category"],
                "score": r["score"],
                "excerpt": r["excerpt"],
            } for r in vec_results]
            result["total"] = len(result["results"])

        else:
            # 混合/通用 → 向量 + 图谱
            vec_results = vector.search(query, top_k=3)
            all_pages = []
            for r in vec_results:
                all_pages.append({
                    "page": r["page"],
                    "source": "vector",
                    "score": r["score"],
                    "excerpt": r["excerpt"],
                })
            
            # 图谱扩展
            seen = set(r["page"] for r in vec_results)
            for vr in vec_results[:2]:
                traversed = graph.traverse(vr["page"], max_hops=1, max_results=5)
                for t in traversed:
                    if t["page"] not in seen:
                        all_pages.append({
                            "page": t["page"],
                            "source": "graph",
                            "relation": t.get("relation", "related"),
                        })
                        seen.add(t["page"])
            
            result["results"] = all_pages
            result["total"] = len(all_pages)

        return result

    def _read_full_content(self, path: str) -> str:
        """读取页面完整内容"""
        file_path = os.path.join(WIKI_PATH, path)
        try:
            content = Path(file_path).read_text(encoding="utf-8")
            # 去掉 frontmatter
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    content = content[end+3:]
            return content.strip()[:2000]
        except Exception:
            return ""

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[网关] {args[0]} {args[1]} {args[2]}")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3007
    server = HTTPServer(("0.0.0.0", port), SearchHandler)
    print(f"\n{'='*50}")
    print(f"🚀 检索网关已启动: http://localhost:{port}")
    print(f"{'='*50}")
    print(f"  测试: curl http://localhost:{port}/search?q=多智能体与单一智能体")
    print(f"  测试: curl http://localhost:{port}/health")
    print(f"  模式: raw=1 返回完整内容（适合 RAG 注入）")
    print(f"\n  Web UI 接入: 将 RAG 搜索改为调此 API")
    print(f"  或在 Web UI 中加一层：先调此网关，结果注入 prompt")
    print(f"{'='*50}")
    server.serve_forever()
