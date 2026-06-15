#!/usr/bin/env python3
"""知识库优化 API 后端 — 供 Obsidian 插件调用的本地 HTTP 服务"""

import http.server
import json
import subprocess
import urllib.parse
from pathlib import Path

VAULT = Path("/Users/pon/Documents/obsidian- knowledge")
SCRIPT = VAULT / "scripts" / "auto_optimize.py"
PORT = 3006

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        task = path.strip("/")

        valid_tasks = {
            "all": [],
            "lint": ["--lint"],
            "graph": ["--graph"],
            "complete": ["--complete"],
            "index": ["--index"],
        }

        if task not in valid_tasks:
            self.send_json({"error": f"未知任务: {task}", "valid": list(valid_tasks.keys())})
            return

        try:
            args = [str(SCRIPT)] + valid_tasks[task]
            result = subprocess.run(
                ["python3"] + args,
                capture_output=True, text=True, timeout=300
            )
            output = result.stdout + result.stderr
            self.send_json({
                "success": result.returncode == 0,
                "output": output[-3000:],  # 只返回最后 3000 字符
                "task": task
            })
        except subprocess.TimeoutExpired:
            self.send_json({"success": False, "error": "执行超时（>5分钟）", "task": task})
        except Exception as e:
            self.send_json({"success": False, "error": str(e), "task": task})

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, format, *args):
        pass  # 静默日志

if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"🚀 Optimizer API 运行在 http://localhost:{PORT}")
    print(f"   全部优化: http://localhost:{PORT}/all")
    print(f"   质量巡检: http://localhost:{PORT}/lint")
    print(f"   图谱自愈: http://localhost:{PORT}/graph")
    print(f"   概念补全: http://localhost:{PORT}/complete")
    print(f"   重建索引: http://localhost:{PORT}/index")
    server.serve_forever()
