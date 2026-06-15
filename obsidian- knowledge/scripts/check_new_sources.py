#!/usr/bin/env python3
"""
检测 raw/sources/ 中的新文件并记录到 log.md
每小时由 crontab 触发执行
"""
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path

VAULT = Path("/Users/pon/Documents/obsidian- knowledge")
RAW_SOURCES = VAULT / "raw" / "sources"
STATE_FILE = VAULT / "scripts" / ".source_checksums.json"
LOG_FILE = VAULT / "wiki" / "log.md"

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))

def get_file_info(path):
    return {
        "mtime": path.stat().st_mtime,
        "size": path.stat().st_size,
        "hash": hashlib.md5(path.read_bytes()).hexdigest()
    }

def check():
    state = load_state()
    changes = []
    
    for f in sorted(RAW_SOURCES.glob("*.md")):
        name = f.name
        info = get_file_info(f)
        
        if name not in state:
            changes.append(("NEW", name, info))
        elif (state[name]["mtime"] != info["mtime"] or 
              state[name]["size"] != info["size"]):
            changes.append(("MODIFIED", name, info))
    
    if changes:
        today = datetime.now().strftime("%Y-%m-%d")
        entry = f"\n## [{today}] auto-detect | raw/sources/ 变更\n\n"
        for kind, name, info in changes:
            entry += f"- **{kind}**: `{name}` (大小:{info['size']}B, MD5:{info['hash'][:12]})\n"
        entry += "\n> ⚠️ 新源文件需要执行 Ingest 流程：AI 读取→创建摘要页→更新实体/概念页\n\n"
        
        with open(LOG_FILE, "a") as f:
            f.write(entry)
        
        for kind, name, info in changes:
            print(f"{kind}: {name}")
    
    # 更新状态快照
    new_state = {}
    for f in RAW_SOURCES.glob("*.md"):
        new_state[f.name] = get_file_info(f)
    save_state(new_state)
    
    return len(changes)

if __name__ == "__main__":
    n = check()
    print(f"检测到 {n} 个变更")
