#!/usr/bin/env python3
"""
向量索引重建工具
===============
重建 graph-rag 的向量索引缓存，然后重启服务加载新缓存。

用法:
  python3 rebuild_vectors.py          # 重建 + 重启服务
  python3 rebuild_vectors.py --force  # 强制重建（忽略已有缓存）
"""

import os
import sys
import subprocess
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import VectorSearcher, VECTOR_CACHE_FILE

VAULT = "/Users/pon/Documents/obsidian- knowledge"
LAUNCH_AGENT = os.path.expanduser("~/Library/LaunchAgents/com.obsidian.graphrag.plist")


def rebuild(force: bool = False):
    """重建向量索引缓存"""
    print("🔨 重建向量索引...")
    v = VectorSearcher()
    v.index_vault(Path(VAULT) / "wiki", force_reindex=force)
    print(f"✅   {len(v.chunks)} 块, {len(v.embeddings)} 嵌入")
    print(f"💾   缓存: {VECTOR_CACHE_FILE}")


def restart_service():
    """重启 graph-rag MCP 服务（通过 launchctl）"""
    print("🔄 重启 graph-rag 服务...")
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/com.obsidian.graphrag"],
                   capture_output=True)
    time.sleep(2)
    result = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{os.getuid()}", LAUNCH_AGENT],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("✅ 服务已重启（从缓存加载）")
    else:
        print(f"❌ 重启失败: {result.stderr}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    rebuild(force)
    restart_service()
