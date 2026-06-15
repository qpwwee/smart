#!/usr/bin/env python3
"""
知识库自动优化系统
===================
基于 Karpathy LLM Wiki 方法论 + OpenCode Agent Teams 模式
调用本地 Ollama 模型实现自我优化。

四大功能:
  1. 内容质量巡检 - 检查链接密度、标注格式、内容完整性
  2. 知识图谱自愈 - 发现孤立页面并自动添加入站链接
  3. 概念自动补全 - 发现缺失概念并创建 stub 页
  4. 自动索引维护 - 重建 index.md

用法:
  python3 scripts/auto_optimize.py             # 全部 5 项
  python3 scripts/auto_optimize.py --lint      # 仅巡检
  python3 scripts/auto_optimize.py --graph     # 仅图谱自愈
  python3 scripts/auto_optimize.py --complete  # 仅概念补全
  python3 scripts/auto_optimize.py --index     # 仅索引维护
  python3 scripts/auto_optimize.py --vector    # 仅重建向量索引
"""

import os
import re
import json
import sys
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

VAULT = os.path.expanduser("/Users/pon/Documents/obsidian- knowledge")
# 注意：路径包含空格，所有 shell 调用须使用引号包裹
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gpt-oss-cn"  # 中文内容首选
LOG_FILE = f"{VAULT}/wiki/cron_log.txt"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def llm_ask(prompt, max_tokens=300):
    """调用本地 Ollama 模型"""
    import urllib.request
    data = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.3}
    }).encode()
    try:
        req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:  # 5 分钟超时
            result = json.loads(resp.read())
            # 有些模型输出在 response，有些在 thinking
            answer = result.get("response", "")
            if not answer.strip():
                answer = result.get("thinking", "")
            return answer.strip()
    except Exception as e:
        log(f"⚠️ LLM 调用失败: {e}")
        return ""

def get_wiki_files():
    """获取所有 wiki 知识页（排除 log.md）"""
    files = []
    for root, dirs, fnames in os.walk(f"{VAULT}/wiki"):
        for f in fnames:
            if f.endswith(".md") and f != "log.md":
                rel = os.path.relpath(os.path.join(root, f), VAULT)
                files.append(rel)
    return sorted(files)

def read_file(path):
    try:
        with open(f"{VAULT}/{path}") as f:
            return f.read()
    except:
        return ""

def write_file(path, content):
    with open(f"{VAULT}/{path}", "w") as f:
        f.write(content)

def count_wiki_links(content):
    """统计 wiki 链接数量"""
    return len(re.findall(r'\[\[([^\[\]]+?)(?:\|[^\[\]]+?)?\]\]', content))

def has_frontmatter(content):
    return content.startswith("---")

def get_page_title(filepath):
    """从 frontmatter 或文件名获取标题"""
    content = read_file(filepath)
    m = re.search(r'^title:\s*(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return Path(filepath).stem

# ────────────── 1. 内容质量巡检 ──────────────

def task_lint():
    log("=" * 50)
    log("📋 任务1: 内容质量巡检")
    log("=" * 50)

    issues = []
    files = get_wiki_files()

    for f in files:
        content = read_file(f)
        if not content:
            continue

        # 检查 frontmatter
        if not has_frontmatter(content):
            issues.append(f"  ❌ {f}: 缺少 frontmatter")
            continue

        # 检查链接密度
        links = count_wiki_links(content)
        if links < 4:
            issues.append(f"  🟡 {f}: 链接过少 ({links}个, 建议≥8)")

        # 检查相关页面区块
        if "相关页面" not in content:
            issues.append(f"  🟡 {f}: 缺少「相关页面」区块")

        # 检查关系标注（在相关页面区块中）
        related_section = re.search(r'相关页面\n(.*?)(?:\n## |\Z)', content, re.DOTALL)
        if related_section:
            section = related_section.group(1)
            # 检查是否使用了标准标注格式
            has_annotation = bool(re.search(r'\*\*是\*\*|\*\*使用\*\*|\*\*基于\*\*|\*\*影响\*\*', section))
            if not has_annotation:
                # 检查是否有非标准标注
                has_any_ref = bool(re.findall(r'\[\[', section))
                if has_any_ref:
                    issues.append(f"  🟡 {f}: 相关页面缺少关系标注（是/使用/基于/影响）")

    # 输出报告
    if issues:
        for i in issues:
            log(i)

        # ── 自动修复 ──
        fixed = 0
        for issue in issues:
            # 修复链接过少：用 LLM 推荐相关页面并补充
            if "链接过少" in issue:
                f = issue.split(":")[0].split()[-1]  # 提取文件名
                content = read_file(f)
                title = get_page_title(f)
                existing_links = [m.group(1) for m in re.finditer(r'\[\[([^\[\]]+?)\]\]', content)]

                # 收集所有可用页面名
                all_pages = []
                for root, dirs, fnames in os.walk(f"{VAULT}/wiki"):
                    for fn in fnames:
                        if fn.endswith(".md") and fn != "log.md":
                            all_pages.append(fn.replace(".md", ""))

                prompt = f"""知识库页面「{title}」当前有 {len(existing_links)} 个链接，需要补充到至少 8 个。
已有链接: {', '.join(existing_links)}

页面内容:
{content[:1500]}

请从以下可用页面中推荐 5 个最相关的页面来补充链接，并为每个页面标注关系类型（是/使用/基于/影响）和一句简短说明。
可用页面:
{chr(10).join(sorted(all_pages)[:40])}

格式要求：每行一个，严格按以下格式：
[[页面名]] — 关系-类型（说明）"""
                suggestions = llm_ask(prompt, max_tokens=500)
                if suggestions:
                    # 找到相关页面区块或文件末尾
                    if "## 相关页面" in content:
                        # 在相关页面区块末尾插入
                        content = content.rstrip()
                        # 移除末尾的 ai-link 区块避免重复
                        content = re.sub(r'\n<!-- ai-link:start -->.*?<!-- ai-link:end -->', '', content, flags=re.DOTALL)
                        content += "\n" + suggestions.strip() + "\n"
                    else:
                        content += f"\n\n## 相关页面\n\n{suggestions.strip()}\n"
                    write_file(f, content)
                    log(f"  ✅ 已自动修复: {f} — 补充了相关页面链接")
                    fixed += 1

            # 修复缺少相关页面区块：用 LLM 生成
            elif "缺少「相关页面」区块" in issue:
                f = issue.split(":")[0].split()[-1]
                content = read_file(f)
                title = get_page_title(f)
                prompt = f"""知识库页面「{title}」缺少「相关页面」区块。
请分析页面内容，推荐 5-8 个相关的知识库页面并附上关系类型标注。

页面内容:
{content[:1500]}

格式：每行一个「[[页面名]] — 关系-类型（说明）」"""
                suggestions = llm_ask(prompt, max_tokens=500)
                if suggestions:
                    content = content.rstrip()
                    content += f"\n\n## 相关页面\n\n{suggestions.strip()}\n"
                    write_file(f, content)
                    log(f"  ✅ 已自动修复: {f} — 创建了相关页面区块")
                    fixed += 1

        if fixed:
            log(f"  🔧 自动修复了 {fixed} 个问题")
        else:
            log("  ℹ️ 未自动修复的问题需人工处理")
    else:
        log("  ✅ 全部页面达标，无问题")

    log(f"  巡检完成: {len(files)} 个文件，{len(issues)} 个问题")
    return issues

# ────────────── 2. 知识图谱自愈 ──────────────

def task_graph():
    log("=" * 50)
    log("🔗 任务2: 知识图谱自愈")
    log("=" * 50)

    # 收集所有 wiki 页面和入站链接
    all_pages = {}  # page_name -> path
    inbound = {}    # page_name -> list of sources

    for root, dirs, fnames in os.walk(f"{VAULT}/wiki"):
        for f in fnames:
            if f.endswith(".md") and f != "log.md":
                name = f.replace(".md", "")
                rel = os.path.relpath(os.path.join(root, f), VAULT)
                all_pages[name] = rel
                inbound[name] = []

    # 扫描所有页面，收集出站链接
    for root, dirs, fnames in os.walk(f"{VAULT}/wiki"):
        for f in fnames:
            if f.endswith(".md") and f != "log.md":
                content = read_file(os.path.relpath(os.path.join(root, f), VAULT))
                for m in re.finditer(r'\[\[([^\[\]]+?)(?:\|[^\[\]]+?)?\]\]', content):
                    target = m.group(1)
                    if target in inbound:
                        inbound[target].append(f.replace(".md", ""))

    # 找出孤立页面（入站链接数 = 0）
    orphans = [name for name, sources in inbound.items() if len(sources) == 0 and name != "index"]
    # 排除 index.md 中的引用（index 不算知识图谱中的语义链接）
    # 重新计算：排除只有 index.md 引用的
    true_orphans = []
    for name in orphans:
        sources = [s for s in inbound[name] if s != "index"]
        if len(sources) == 0:
            true_orphans.append(name)

    if not true_orphans:
        log("  ✅ 无孤立页面，图谱健康")
        return

    log(f"  发现 {len(true_orphans)} 个孤立页面:")
    for name in true_orphans:
        log(f"    📄 {name} ({all_pages.get(name, '?')})")

    # 用 LLM 为每个孤立页面推荐入站链接来源
    for name in true_orphans:
        path = all_pages.get(name, f"wiki/concepts/{name}.md")
        content = read_file(path)

        if not content:
            continue

        # 提取页面摘要
        title = get_page_title(path)
        content_preview = content[:1000].replace("---", "").strip()[:500]

        prompt = f"""你是一个知识库图谱优化专家。以下是知识库中的一个孤立页面（没有任何其他页面链接到它）。

页面标题: {title}
页面内容摘要:
{content_preview}

请分析这个页面的内容，从知识库的其他页面中推荐 3-5 个应该链接到此页面的相关概念/实体页。
只需要返回页面名称列表，每行一个，不要解释。

可用页面:
{chr(10).join(sorted([n for n in all_pages.keys() if n != name][:30]))}"""

        recommendations = llm_ask(prompt, max_tokens=200)
        if recommendations:
            log(f"  💡 为「{title}」推荐的入站链接来源:")
            for line in recommendations.strip().split("\n"):
                line = line.strip().strip("-").strip()
                if line and line in all_pages and line != name:
                    target_path = all_pages[line]
                    target_content = read_file(target_path)
                    # 在相关页面区块添加链接
                    link_entry = f"\n- [[{name}]] — 相关内容补充"
                    if "相关页面" in target_content:
                        # 在相关页面区块末尾添加
                        target_content = re.sub(
                            r'(<!-- ai-link:end -->)',
                            f"\\1{link_entry}",
                            target_content
                        )
                    else:
                        target_content += f"\n## 相关页面\n{link_entry}\n"
                    write_file(target_path, target_content)
                    log(f"      ✅ 已添加到「{line}」")

    log("  ✅ 图谱自愈完成")

# ────────────── 3. 概念自动补全 ──────────────

def task_complete():
    log("=" * 50)
    log("🧩 任务3: 概念自动补全")
    log("=" * 50)

    # 收集现有概念列表
    existing_concepts = set()
    for f in os.listdir(f"{VAULT}/wiki/concepts/"):
        if f.endswith(".md"):
            existing_concepts.add(f.replace(".md", ""))

    # 收集所有页面中出现的 [[链接]]，找出哪些指向不存在的页面
    all_links = set()
    linked_exists = set()
    for root, dirs, fnames in os.walk(f"{VAULT}/wiki"):
        for f in fnames:
            if f.endswith(".md"):
                content = read_file(os.path.relpath(os.path.join(root, f), VAULT))
                for m in re.finditer(r'\[\[([^\[\]]+?)(?:\|[^\[\]]+?)?\]\]', content):
                    target = m.group(1)
                    all_links.add(target)

    # 检查哪些链接指向不存在的页面
    missing_pages = []
    for link in sorted(all_links):
        # 跳过非概念类链接
        if link in existing_concepts:
            continue
        # 检查文件是否存在
        found = False
        for root, dirs, fnames in os.walk(f"{VAULT}/wiki"):
            if f"{link}.md" in fnames:
                found = True
                break
        if not found and link not in ["index", "log"]:
            missing_pages.append(link)

    if not missing_pages:
        log("  ✅ 无缺失概念页面")
        return

    log(f"  发现 {len(missing_pages)} 个被引用但不存在的页面:")
    for p in missing_pages[:10]:
        log(f"    📌 {p}")

    # 用 LLM 分析最有价值创建的前 3 个概念
    prompt = f"""以下是被反复引用但知识库中不存在的概念页面。请分析其中哪些最值得创建（有实质内容可写、与其他页面关联度高）。

不存在的概念:
{chr(10).join(missing_pages[:20])}

请选出最多 3 个最值得创建的概念，对每个给出:
- 概念名
- 一句话定义
- 3 个与该概念相关的现有页面名

格式:
概念名 | 定义 | 相关页面1, 相关页面2, 相关页面3"""

    recommendations = llm_ask(prompt, max_tokens=500)
    log(f"  💡 LLM 推荐创建的概念:")
    log(f"  {recommendations[:600]}")

    log("  ✅ 概念分析完成（需人工确认后自动创建）")

# ────────────── 4. 自动索引维护 ──────────────

def task_index():
    log("=" * 50)
    log("📑 任务4: 自动索引维护")
    log("=" * 50)

    try:
        result = subprocess.run(
            ["bash", f"{VAULT}/scripts/update_index.sh"],
            capture_output=True, text=True, timeout=30
        )
        log(f"  update_index.sh 输出: {result.stdout.strip()[:200]}")
        if result.returncode == 0:
            log("  ✅ index.md 重建成功" if "placeholder" not in result.stdout else "  ⚠️ 脚本为占位版本，需完善")
        else:
            log(f"  ❌ index.md 重建失败: {result.stderr[:200]}")
    except Exception as e:
        log(f"  ❌ index.md 重建异常: {e}")

    log("  ✅ 索引维护完成")

# ────────────── 5. 向量索引重建 ──────────────

def task_vector():
    log("=" * 50)
    log("🔬 任务5: 重建向量索引")
    log("=" * 50)

    rebuild_script = f"{VAULT}/../obsidian-mcp-graphrag/rebuild_vectors.py"
    rebuild_script = os.path.normpath(rebuild_script)

    if not os.path.exists(rebuild_script):
        log(f"  ❌ 重建脚本不存在: {rebuild_script}")
        return

    try:
        result = subprocess.run(
            ["python3", rebuild_script, "--force"],
            capture_output=True, text=True, timeout=600  # 最多 10 分钟
        )
        log(f"  {result.stdout.strip()[:300]}")
        if result.returncode == 0:
            log("  ✅ 向量索引重建成功")
        else:
            log(f"  ❌ 重建失败: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        log("  ❌ 重建超时（>10分钟）")
    except Exception as e:
        log(f"  ❌ 重建异常: {e}")

    log("  ✅ 向量索引重建完成")

# ────────────── 主入口 ──────────────

def main():
    parser = argparse.ArgumentParser(description="知识库自动优化系统")
    parser.add_argument("--lint", action="store_true", help="仅内容质量巡检")
    parser.add_argument("--graph", action="store_true", help="仅知识图谱自愈")
    parser.add_argument("--complete", action="store_true", help="仅概念自动补全")
    parser.add_argument("--index", action="store_true", help="仅索引维护")
    parser.add_argument("--vector", action="store_true", help="仅重建向量索引")
    args = parser.parse_args()

    # 检查 Ollama 是否运行
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
    except:
        log("❌ Ollama 未运行，请先启动 Ollama")
        sys.exit(1)

    log(f"\n{'#' * 60}")
    log(f"# 🤖 知识库自动优化系统启动")
    log(f"#    模型: {MODEL}")
    log(f"#    时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"{'#' * 60}\n")

    # 确定运行哪些任务
    run_all = not (args.lint or args.graph or args.complete or args.index or args.vector)

    if run_all or args.lint:
        task_lint()
    if run_all or args.graph:
        task_graph()
    if run_all or args.complete:
        task_complete()
    if run_all or args.index:
        task_index()
    if run_all or args.vector:
        task_vector()

    log(f"\n{'#' * 60}")
    log(f"# ✅ 自动优化完成")
    log(f"{'#' * 60}\n")

if __name__ == "__main__":
    main()
