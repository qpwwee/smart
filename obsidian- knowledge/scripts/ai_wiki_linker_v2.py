#!/usr/bin/env python3
"""
AI Wiki Linker v2 — Karpathy LLM Wiki 自动维护工具
=================================================
严格遵循 INSTRUCTIONS.md 三层架构 + 链接方向语义 + 自我改善机制

功能:
  1. scan    扫描所有 wiki/* 页面，提取元数据
  2. index   重建 index.md (按实体/概念/来源/对比分类)
  3. lint    执行健康检查 (孤立页面、瘦弱页面、链接标注、frontmatter)
  4. fix     自动修复部分 lint 问题

用法:
  python3 scripts/ai_wiki_linker_v2.py scan
  python3 scripts/ai_wiki_linker_v2.py index
  python3 scripts/ai_wiki_linker_v2.py lint
  python3 scripts/ai_wiki_linker_v2.py fix
  python3 scripts/ai_wiki_linker_v2.py all       # scan → lint → index

配置:
  VAULT_PATH: Obsidian vault 根目录
"""

import os
import re
import sys
import json
from datetime import datetime
from pathlib import Path

# ============================================================
# 配置
# ============================================================
VAULT_PATH = os.environ.get(
    "OBSIDIAN_VAULT_PATH",
    "/Users/pon/Documents/obsidian- knowledge"
)
SCRIPT_NAME = "AI Wiki Linker v2"
SCRIPT_VERSION = "2.0.0"

# ============================================================
# 页面元数据结构
# ============================================================
class WikiPage:
    def __init__(self, rel_path: str, abs_path: str):
        self.rel_path = rel_path          # wiki/concepts/深度学习.md
        self.abs_path = abs_path
        self.filename = Path(rel_path).name  # 深度学习.md
        self.title = self._extract_title()
        self.page_type = self._detect_type()
        self.tags = []
        self.related_entities = []
        self.inbound_links = []            # 被谁引用
        self.outbound_links = []           # 引用了谁
        self.has_frontmatter = False
        self.has_relation_annotations = False
        self.content_length = 0
        self.substantive_lines = 0
        self.errors = []

    def _extract_title(self) -> str:
        """从文件名提取标题（去掉 .md）"""
        return Path(self.filename).stem

    def _detect_type(self) -> str:
        """根据路径判断页面类型"""
        if "/entities/" in self.rel_path:
            return "entity"
        elif "/concepts/" in self.rel_path:
            return "concept"
        elif "/sources/" in self.rel_path:
            return "source"
        elif "/comparisons/" in self.rel_path:
            return "comparison"
        elif "/overview/" in self.rel_path:
            return "overview"
        else:
            return "unknown"

    def parse(self, content: str):
        """解析页面内容，提取结构化信息"""
        self.content_length = len(content)
        lines = content.split('\n')
        
        # 计算实质行（去掉空行、frontmatter分隔符、纯标题行）
        substantive = 0
        in_frontmatter = False
        for line in lines:
            stripped = line.strip()
            if stripped == '---':
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                # 解析 frontmatter 字段
                if stripped.startswith('tags:'):
                    # 支持 inline list 和 array 格式
                    tag_match = re.search(r'\[([^\]]+)\]', stripped)
                    if tag_match:
                        self.tags = [t.strip().strip('"\'') for t in tag_match.group(1).split(',')]
                if stripped.startswith('related_entities:'):
                    rel_match = re.search(r'\[([^\]]+)\]', stripped)
                    if rel_match:
                        self.related_entities = [r.strip().strip('"\'') for r in rel_match.group(1).split(',')]
                continue
            if stripped == '' or stripped.startswith('#') or stripped.startswith('>'):
                continue
            if len(stripped) > 2:
                substantive += 1

        self.substantive_lines = substantive
        self.has_frontmatter = '---' in content[:200]

        # 提取出站链接（[[页面名]]）
        wiki_links = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content)
        self.outbound_links = list(set(wiki_links))

        # 检测关系标注
        relation_patterns = [
            r'\*\*是\*\*', r'\*\*使用\*\*', r'\*\*基于\*\*', r'\*\*影响\*\*',
            r'是\s', r'使用\s', r'基于\s', r'影响\s'
        ]
        for pattern in relation_patterns:
            if re.search(pattern, content):
                self.has_relation_annotations = True
                break

    def __repr__(self):
        return f"<WikiPage {self.rel_path} type={self.page_type}>"


# ============================================================
# 扫描器
# ============================================================
class WikiScanner:
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.pages: dict[str, WikiPage] = {}
        self.all_links: dict[str, list[str]] = {}  # 谁链接了谁

    def scan(self):
        """扫描 wiki/ 下所有 .md 文件"""
        wiki_dir = self.vault_path / "wiki"
        if not wiki_dir.exists():
            print(f"[ERROR] wiki/ 目录不存在: {wiki_dir}")
            return self.pages

        for root, dirs, files in os.walk(wiki_dir):
            for f in files:
                if not f.endswith('.md'):
                    continue
                abs_path = os.path.join(root, f)
                rel_path = os.path.relpath(abs_path, self.vault_path)
                
                page = WikiPage(rel_path, abs_path)
                
                try:
                    with open(abs_path, 'r', encoding='utf-8', errors='replace') as fh:
                        content = fh.read()
                    page.parse(content)
                except Exception as e:
                    page.errors.append(f"读取失败: {e}")
                
                self.pages[page.title] = page

        # 建立入站链接
        for title, page in self.pages.items():
            for link in page.outbound_links:
                if link not in self.all_links:
                    self.all_links[link] = []
                self.all_links[link].append(title)

        for title, page in self.pages.items():
            page.inbound_links = self.all_links.get(title, [])

        print(f"[OK] 扫描完成: {len(self.pages)} 个页面")
        return self.pages

    def print_summary(self):
        """打印扫描摘要"""
        print(f"\n{'='*60}")
        print(f"  {SCRIPT_NAME} v{SCRIPT_VERSION} — 扫描报告")
        print(f"  Vault: {self.vault_path}")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}")
        
        by_type = {}
        for page in self.pages.values():
            by_type.setdefault(page.page_type, []).append(page)
        
        for ptype, plist in by_type.items():
            print(f"\n  [{ptype.upper()}] {len(plist)} 页")
            for p in sorted(plist, key=lambda x: x.title):
                inbound = len(p.inbound_links)
                outbound = len(p.outbound_links)
                ann = "✓" if p.has_relation_annotations else "✗"
                fm = "✓" if p.has_frontmatter else "✗"
                print(f"    {p.title:20s} 入站:{inbound} 出站:{outbound} 标注:{ann} frontmatter:{fm}")
        
        # 统计
        total_inbound = sum(len(p.inbound_links) for p in self.pages.values())
        total_outbound = sum(len(p.outbound_links) for p in self.pages.values())
        avg_links = total_outbound / len(self.pages) if self.pages else 0
        isolated = [p for p in self.pages.values() if len(p.inbound_links) == 0]
        annotated = [p for p in self.pages.values() if p.has_relation_annotations]
        
        print(f"\n  📊 统计:")
        print(f"     总页面: {len(self.pages)}")
        print(f"     总出站链接: {total_outbound}")
        print(f"     平均链接/页: {avg_links:.1f}")
        print(f"     孤立页面(0入站): {len(isolated)}")
        print(f"     有关系标注: {len(annotated)}/{len(self.pages)} ({len(annotated)*100//len(self.pages) if self.pages else 0}%)")
        
        if isolated:
            print(f"\n  ⚠️  孤立页面:")
            for p in isolated:
                print(f"     - [[{p.title}]] ({p.rel_path})")

        return by_type


# ============================================================
# Index 生成器
# ============================================================
class IndexGenerator:
    """按 LLM-Wiki 三层架构重建 index.md"""
    
    def __init__(self, pages: dict[str, WikiPage]):
        self.pages = pages
        self.category_order = ["entity", "concept", "source", "comparison", "overview"]
        self.category_names = {
            "entity": "实体 (Entities)",
            "concept": "概念 (Concepts)",
            "source": "来源 (Sources)",
            "comparison": "对比分析 (Comparisons)",
            "overview": "综述 (Overviews)",
            "unknown": "其他"
        }

    def generate(self) -> str:
        """生成 index.md 内容"""
        lines = []
        lines.append("# 📚 知识库索引")
        lines.append("")
        lines.append(f"> 由 {SCRIPT_NAME} v{SCRIPT_VERSION} 自动生成 — {datetime.now().strftime('%Y-%m-%d')}")
        lines.append("> 严格遵循 LLM Wiki 三层架构 + 链接方向语义")
        lines.append(f"> 共管理 {len(self.pages)} 篇笔记")
        lines.append("")
        
        # 按分类整理
        by_type = {}
        for page in self.pages.values():
            by_type.setdefault(page.page_type, []).append(page)
        
        for ptype in self.category_order:
            if ptype not in by_type:
                continue
            plist = sorted(by_type[ptype], key=lambda p: p.title)
            lines.append(f"## {self.category_names[ptype]}")
            lines.append("")
            for p in plist:
                # 构建简洁的描述
                description = self._get_description(p)
                lines.append(f"- [[{p.title}]] — {description}")
            lines.append("")
        
        # 未分类页面
        if "unknown" in by_type:
            plist = sorted(by_type["unknown"], key=lambda p: p.title)
            lines.append("## 其他")
            lines.append("")
            for p in plist:
                lines.append(f"- [[{p.title}]]")
            lines.append("")
        
        # 健康摘要
        total_outbound = sum(len(p.outbound_links) for p in self.pages.values())
        avg_links = total_outbound / len(self.pages) if self.pages else 0
        isolated = [p for p in self.pages.values() if len(p.inbound_links) == 0]
        annotated = [p for p in self.pages.values() if p.has_relation_annotations]
        
        lines.append("---")
        lines.append("*Wiki 健康指标*")
        lines.append(f"- 总页面: {len(self.pages)} | 平均链接/页: {avg_links:.1f} | 孤立页面: {len(isolated)} | 关系标注率: {len(annotated)*100//len(self.pages) if self.pages else 0}%")
        lines.append("")
        
        return '\n'.join(lines)

    def _get_description(self, page: WikiPage) -> str:
        """根据页面类型生成简短描述"""
        # 从 frontmatter tags 推断
        if page.tags:
            tag_str = ', '.join(page.tags[:3])
            return f"[{page.page_type}] tags: {tag_str}"
        
        inbound_info = f"入站引用: {len(page.inbound_links)}" if page.inbound_links else "无入站链接"
        outbound_info = f"出站链接: {len(page.outbound_links)}"
        return f"[{page.page_type}] {inbound_info} | {outbound_info}"


# ============================================================
# Lint 检查器
# ============================================================
class LintChecker:
    """LLM-Wiki 健康检查"""
    
    def __init__(self, pages: dict[str, WikiPage]):
        self.pages = pages
        self.issues = []

    def check_all(self) -> list[dict]:
        """执行全部检查"""
        self.issues = []
        self._check_isolated()
        self._check_thin()
        self._check_relation_annotations()
        self._check_frontmatter()
        self._check_broken_links()
        return self.issues

    def _check_isolated(self):
        """检查孤立页面（零入站链接）"""
        for page in self.pages.values():
            if len(page.inbound_links) == 0:
                self.issues.append({
                    "severity": "medium",
                    "type": "isolated",
                    "page": page.title,
                    "path": page.rel_path,
                    "message": f"孤立页面：没有被任何其他页面引用",
                    "fix": "从相关页面添加入站链接"
                })

    def _check_thin(self):
        """检查瘦弱页面（实质行 < 5）"""
        for page in self.pages.values():
            if page.substantive_lines < 5:
                self.issues.append({
                    "severity": "low",
                    "type": "thin",
                    "page": page.title,
                    "path": page.rel_path,
                    "message": f"内容薄弱：仅 {page.substantive_lines} 行实质内容",
                    "fix": "补充定义、核心概念、相关链接"
                })

    def _check_relation_annotations(self):
        """检查链接关系标注"""
        for page in self.pages.values():
            if not page.has_relation_annotations and len(page.outbound_links) > 0:
                self.issues.append({
                    "severity": "medium",
                    "type": "no-relation-annotation",
                    "page": page.title,
                    "path": page.rel_path,
                    "message": f"出站链接 {len(page.outbound_links)} 个但未发现关系标注（是/使用/基于/影响）",
                    "fix": "在「相关页面」区块为每个链接添加关系类型标注"
                })

    def _check_frontmatter(self):
        """检查 frontmatter 完整性"""
        for page in self.pages.values():
            if not page.has_frontmatter:
                self.issues.append({
                    "severity": "high",
                    "type": "no-frontmatter",
                    "page": page.title,
                    "path": page.rel_path,
                    "message": "缺少 frontmatter（title/tags/type/created 字段）",
                    "fix": "添加 frontmatter 元数据块"
                })

    def _check_broken_links(self):
        """检查断链（出站链接指向不存在的页面）"""
        page_titles = set(self.pages.keys())
        for page in self.pages.values():
            for link in page.outbound_links:
                if link not in page_titles and link != page.title:
                    self.issues.append({
                        "severity": "low",
                        "type": "broken-link",
                        "page": page.title,
                        "path": page.rel_path,
                        "message": f"断链：[[{link}]] 在 vault 中不存在",
                        "fix": "创建对应的页面或移除该链接"
                    })

    def print_report(self):
        """打印 Lint 报告"""
        if not self.issues:
            print("\n✅ 健康检查通过：未发现问题")
            return

        print(f"\n{'='*60}")
        print(f"  Lint 检查报告 — {len(self.issues)} 个问题")
        print(f"{'='*60}")
        
        by_severity = {"high": [], "medium": [], "low": []}
        for issue in self.issues:
            by_severity[issue["severity"]].append(issue)
        
        for severity, label in [("high", "🔴 严重"), ("medium", "🟡 中等"), ("low", "🟢 轻微")]:
            if by_severity[severity]:
                print(f"\n  {label}:")
                for issue in by_severity[severity]:
                    print(f"    [{issue['type']}] {issue['page']}: {issue['message']}")
                    print(f"          路径: {issue['path']}")
                    print(f"          建议: {issue['fix']}")
        
        print(f"\n  📊 汇总: 严重:{len(by_severity['high'])} 中等:{len(by_severity['medium'])} 轻微:{len(by_severity['low'])}")


# ============================================================
# 主入口
# ============================================================
def main():
    if len(sys.argv) < 2:
        print(f"{SCRIPT_NAME} v{SCRIPT_VERSION}")
        print("用法:")
        print("  python3 scripts/ai_wiki_linker_v2.py scan   扫描并分析 wiki")
        print("  python3 scripts/ai_wiki_linker_v2.py index  重建 index.md")
        print("  python3 scripts/ai_wiki_linker_v2.py lint   执行健康检查")
        print("  python3 scripts/ai_wiki_linker_v2.py all    扫描 → lint → 重建 index")
        return

    command = sys.argv[1]
    
    # 初始化扫描器
    scanner = WikiScanner(VAULT_PATH)
    scanner.scan()
    
    if command == "scan":
        scanner.print_summary()
    
    elif command == "index":
        generator = IndexGenerator(scanner.pages)
        index_content = generator.generate()
        index_path = os.path.join(VAULT_PATH, "index.md")
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_content)
        print(f"\n[OK] index.md 已更新: {index_path}")
    
    elif command == "lint":
        checker = LintChecker(scanner.pages)
        checker.check_all()
        checker.print_report()
    
    elif command == "fix":
        print("[INFO] 自动修复功能：请手动参考 lint 报告逐条修复")
        print("[INFO] 自动修复将在后续版本中实现")
    
    elif command == "all":
        scanner.print_summary()
        checker = LintChecker(scanner.pages)
        checker.check_all()
        checker.print_report()
        generator = IndexGenerator(scanner.pages)
        index_content = generator.generate()
        index_path = os.path.join(VAULT_PATH, "index.md")
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_content)
        print(f"\n[OK] index.md 已更新")
    
    else:
        print(f"[ERROR] 未知命令: {command}")


if __name__ == "__main__":
    main()
