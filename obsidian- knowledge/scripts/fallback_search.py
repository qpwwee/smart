#!/usr/bin/env python3
"""
Fallback Search — simple_vector_search 超时降级方案
====================================================
当 Obsidian MCP simple_vector_search 超时或失败时，
自动降级到本地搜索工具：

  层级1: qmd (BM25 全文搜索，已索引 wiki/ 23 个文件)
  层级2: ripgrep (正则搜索，覆盖完整 vault)
  层级3: grep (最后兜底)

用法:
  python3 scripts/fallback_search.py <query> [--max-results N]

示例:
  python3 scripts/fallback_search.py "深度学习"
  python3 scripts/fallback_search.py "伦理" --max-results 5
  python3 scripts/fallback_search.py "UNESCO AI"
"""

import subprocess
import sys
import re
import os
from pathlib import Path
from datetime import datetime

VAULT_PATH = os.environ.get(
    "OBSIDIAN_VAULT_PATH",
    "/Users/pon/Documents/obsidian- knowledge"
)

# ============================================================
# 层级1: qmd 搜索
# ============================================================
def search_qmd(query: str, max_results: int = 5) -> list[dict]:
    """
    使用 qmd BM25 全文搜索。
    qmd 已为 wiki/ 目录建索引（23 个文件）。
    返回 sorted list of {path, score, snippet}
    """
    results = []
    try:
        # qmd search 输出格式: "<filename>\n<filepath>\n<score>\n<snippet>"
        proc = subprocess.run(
            ["qmd", "search", query],
            capture_output=True, text=True, timeout=10,
            cwd=VAULT_PATH
        )
        if proc.returncode != 0:
            print(f"[qmd] 搜索失败: {proc.stderr.strip()}", file=sys.stderr)
            return results
        
        output = proc.stdout.strip()
        if not output:
            return results
        
        # Parse qmd output (filename, path, score, snippet blocks)
        blocks = re.split(r'\n(?=\S+\n/)', output)
        for block in blocks[:max_results]:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                result = {
                    "filename": lines[0].strip(),
                    "path": lines[1].strip(),
                    "score": lines[2].strip(),
                    "snippet": '\n'.join(lines[3:]).strip() if len(lines) > 3 else ""
                }
                results.append(result)
    except subprocess.TimeoutExpired:
        print("[qmd] 超时", file=sys.stderr)
    except FileNotFoundError:
        print("[qmd] qmd 未安装", file=sys.stderr)
    except Exception as e:
        print(f"[qmd] 错误: {e}", file=sys.stderr)
    
    return results


# ============================================================
# 层级2: ripgrep 搜索
# ============================================================
def search_ripgrep(query: str, max_results: int = 5) -> list[dict]:
    """
    使用 ripgrep 进行正则搜索。
    搜索整个 vault (排除 .obsidian/ 和 node_modules/)。
    返回排序后的结果（按匹配行数降序）。
    """
    results = []
    try:
        # 智能构建 rg 参数
        rg_args = [
            "rg", "-i", "--no-heading", "--line-number",
            "--max-count", "10",
            "-g", "*.md",
            "-g", "!.obsidian/",
            "-g", "!node_modules/",
            query, VAULT_PATH
        ]
        
        # 如果是英文查询，添加单词边界匹配
        if re.match(r'^[a-zA-Z\s]+$', query):
            rg_args = [
                "rg", "-i", "--no-heading", "--line-number",
                "--max-count", "10",
                "-g", "*.md",
                "-g", "!.obsidian/",
                "-g", "!node_modules/",
                "-w",
                query, VAULT_PATH
            ]
        
        proc = subprocess.run(
            rg_args,
            capture_output=True, text=True, timeout=15
        )
        
        if proc.returncode not in (0, 1):  # 1 = no matches
            print(f"[ripgrep] 搜索失败: {proc.stderr.strip()}", file=sys.stderr)
            return results
        
        if not proc.stdout.strip():
            return results
        
        # 按文件分组
        file_matches = {}
        for line in proc.stdout.strip().split('\n'):
            if ':' in line:
                parts = line.split(':', 2)
                if len(parts) >= 2:
                    filepath = parts[0]
                    line_no = parts[1]
                    content = parts[2] if len(parts) > 2 else ""
                    if filepath not in file_matches:
                        file_matches[filepath] = {"lines": [], "count": 0}
                    file_matches[filepath]["lines"].append(f"L{line_no}: {content.strip()[:200]}")
                    file_matches[filepath]["count"] += 1
        
        # 按匹配数排序
        sorted_files = sorted(file_matches.items(), key=lambda x: x[1]["count"], reverse=True)
        
        for filepath, data in sorted_files[:max_results]:
            # 获取相对路径
            rel_path = os.path.relpath(filepath, VAULT_PATH)
            results.append({
                "path": rel_path,
                "matches": data["count"],
                "snippet": '\n'.join(data["lines"][:3])  # 最多显示 3 行
            })
    
    except subprocess.TimeoutExpired:
        print("[ripgrep] 超时", file=sys.stderr)
    except FileNotFoundError:
        print("[ripgrep] ripgrep 未安装", file=sys.stderr)
    except Exception as e:
        print(f"[ripgrep] 错误: {e}", file=sys.stderr)
    
    return results


# ============================================================
# 层级3: grep 兜底
# ============================================================
def search_grep(query: str, max_results: int = 5) -> list[dict]:
    """
    grep 最后兜底方案。
    """
    results = []
    try:
        proc = subprocess.run(
            ["grep", "-ril", query, VAULT_PATH + "/wiki/"],
            capture_output=True, text=True, timeout=15
        )
        if proc.returncode not in (0, 1):
            return results
        
        files = [f for f in proc.stdout.strip().split('\n') if f]
        for filepath in files[:max_results]:
            rel_path = os.path.relpath(filepath, VAULT_PATH)
            # 提取包含关键词的行
            proc2 = subprocess.run(
                ["grep", "-i", query, filepath],
                capture_output=True, text=True, timeout=5
            )
            first_line = proc2.stdout.strip().split('\n')[0] if proc2.stdout.strip() else ""
            results.append({
                "path": rel_path,
                "matches": 0,
                "snippet": first_line[:200] if first_line else ""
            })
    except Exception as e:
        print(f"[grep] 错误: {e}", file=sys.stderr)
    
    return results


# ============================================================
# 主入口：三级降级
# ============================================================
def search(query: str, max_results: int = 5) -> list[dict]:
    """
    三级降级搜索：
    1. qmd (语义 BM25，有索引)
    2. ripgrep (正则，全覆盖)
    3. grep (兜底)
    
    返回 deduplicated, 按来源排名的结果列表。
    """
    seen_paths = set()
    all_results = []
    
    # 层级 1: qmd
    print(f"[search] 层级1: qmd '{query}'", file=sys.stderr)
    qmd_results = search_qmd(query, max_results)
    for r in qmd_results:
        path = r.get("path", "")
        if path and path not in seen_paths:
            seen_paths.add(path)
            r["source"] = "qmd"
            all_results.append(r)
    
    if len(all_results) >= max_results:
        return all_results[:max_results]
    
    # 层级 2: ripgrep
    print(f"[search] 层级2: ripgrep '{query}'", file=sys.stderr)
    rg_results = search_ripgrep(query, max_results - len(all_results))
    for r in rg_results:
        path = r.get("path", "")
        if path and path not in seen_paths:
            seen_paths.add(path)
            r["source"] = "ripgrep"
            all_results.append(r)
    
    if len(all_results) >= max_results:
        return all_results[:max_results]
    
    # 层级 3: grep
    print(f"[search] 层级3: grep '{query}'", file=sys.stderr)
    grep_results = search_grep(query, max_results - len(all_results))
    for r in grep_results:
        path = r.get("path", "")
        if path and path not in seen_paths:
            seen_paths.add(path)
            r["source"] = "grep"
            all_results.append(r)
    
    return all_results[:max_results]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    query = sys.argv[1]
    max_results = 5
    
    # 解析可选参数
    if "--max-results" in sys.argv:
        idx = sys.argv.index("--max-results")
        if idx + 1 < len(sys.argv):
            max_results = int(sys.argv[idx + 1])
    
    print(f"🔍 Fallback Search: \"{query}\" (max={max_results})")
    print(f"   Vault: {VAULT_PATH}")
    print(f"   时间: {datetime.now().strftime('%H:%M:%S')}")
    print()
    
    results = search(query, max_results)
    
    if not results:
        print("❌ 未找到匹配结果")
        sys.exit(0)
    
    print(f"✅ 找到 {len(results)} 个结果:\n")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] [{'qmd' if r.get('source') == 'qmd' else 'rg' if r.get('source') == 'ripgrep' else 'grep'}] {r.get('path', '?')}")
        if r.get("score"):
            print(f"      评分: {r['score']}")
        if r.get("matches"):
            print(f"      匹配: {r['matches']} 处")
        if r.get("snippet"):
            snippet = r['snippet'][:250]
            print(f"      片段: {snippet}")
        print()


if __name__ == "__main__":
    main()
