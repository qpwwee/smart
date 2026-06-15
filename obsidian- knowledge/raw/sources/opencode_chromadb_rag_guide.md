# OpenCode + ChromaDB RAG 知识库搭建指南

## 概述
本指南介绍如何搭建本地 RAG（检索增强生成）知识库系统，使用 ChromaDB 作为向量数据库，Ollama 运行 embedding 模型，并通过 MCP 协议与 OpenCode TUI 集成。完成后，在 OpenCode 中提问即可自动检索知识库内容。

## 系统要求
- macOS / Linux（建议 macOS）
- Python 3.8+
- 已安装 Ollama（用于运行 embedding 模型）
- OpenCode CLI 已安装并可用

## 一、环境准备

### 1. 安装 Ollama
如果尚未安装 Ollama，请从官网下载安装：
```bash
# 访问 https://ollama.com/ 下载安装包
# 或使用命令行安装（macOS）
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. 下载 embedding 模型
使用 Ollama 下载一个轻量级的 embedding 嵌入模型 模型，建议使用 qwen3-embedding:4b：
```bash
ollama pull qwen3-embedding:4b
```
下载完成后验证：
```bash
ollama list
```
应能看到 `qwen3-embedding:4b` 模型。

## 二、安装 ChromaDB
使用 pip 安装 ChromaDB：
```bash
pip install chromadb
```
建议使用虚拟环境。

## 三、创建 RAG 知识库目录结构
在项目根目录或专门位置创建以下目录结构：
```
~/.rag-knowledge/
├── chroma_db/          # ChromaDB 持久化存储
├── index_project.py    # 索引项目代码的脚本
├── index_pdf.py        # 索引 PDF 文档的脚本
└── README.md
```

## 四、编写索引脚本

### 1. 索引项目代码脚本 (`index_project.py`)
创建 `/Users/pon/Documents/buddy_claw_my/.rag-knowledge/index_project.py`：

```python
import os
import chromadb
from chromadb.config import Settings
import requests
import json
import time

class OllamaEmbedder:
    def __init__(self, model_name="qwen3-embedding:4b", base_url="http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        self.batch_size = 32  # 批量处理大小
    
    def embed(self, texts):
        """嵌入文本列表，返回向量列表"""
        if not texts:
            return []
        
        vectors = []
        # 分批处理避免超时
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i+self.batch_size]
            try:
                response = requests.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model_name, "prompt": batch[0] if len(batch) == 1 else batch}
                )
                if response.status_code == 200:
                    result = response.json()
                    if len(batch) == 1:
                        vectors.append(result["embedding"])
                    else:
                        vectors.extend([item["embedding"] for item in result.get("embeddings", [])])
                else:
                    print(f"嵌入失败: {response.status_code}")
                    # 添加零向量作为占位符
                    vectors.extend([[0.0] * 1024] * len(batch))
            except Exception as e:
                print(f"嵌入异常: {e}")
                vectors.extend([[0.0] * 1024] * len(batch))
            time.sleep(0.1)  # 少量延迟避免压力过大
        
        return vectors

def index_project(project_path, collection_name="project_code"):
    """索引项目代码到 ChromaDB"""
    # 初始化 ChromaDB 客户端
    chroma_client = chromadb.PersistentClient(
        path="/Users/pon/Documents/buddy_claw_my/.rag-knowledge/chroma_db",
        settings=Settings(allow_reset=True)
    )
    
    # 创建或获取集合
    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )
    
    # 初始化嵌入器
    embedder = OllamaEmbedder()
    
    # 收集所有代码文件
    code_files = []
    text_chunks = []
    metadatas = []
    ids = []
    
    for root, dirs, files in os.walk(project_path):
        for file in files:
            if file.endswith(('.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.md', '.txt')):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 按行分块（每50行一个块）
                    lines = content.split('\n')
                    for i in range(0, len(lines), 50):
                        chunk = '\n'.join(lines[i:i+50])
                        if chunk.strip():
                            chunk_id = f"{file_path}:{i}"
                            text_chunks.append(chunk)
                            metadatas.append({
                                "source": file_path,
                                "type": "code",
                                "language": os.path.splitext(file)[1][1:],
                                "line_start": i,
                                "line_end": min(i+49, len(lines)-1)
                            })
                            ids.append(chunk_id)
                    
                    code_files.append(file_path)
                except Exception as e:
                    print(f"读取文件失败 {file_path}: {e}")
    
    print(f"找到 {len(code_files)} 个代码文件，生成 {len(text_chunks)} 个文本块")
    
    # 批量嵌入和添加
    batch_size = 32
    for i in range(0, len(text_chunks), batch_size):
        batch_end = min(i + batch_size, len(text_chunks))
        print(f"处理块 {i+1} 到 {batch_end} / {len(text_chunks)}")
        
        batch_texts = text_chunks[i:batch_end]
        batch_metadatas = metadatas[i:batch_end]
        batch_ids = ids[i:batch_end]
        
        # 嵌入
        embeddings = embedder.embed(batch_texts)
        
        # 添加到集合
        if embeddings:
            collection.add(
                embeddings=embeddings,
                documents=batch_texts,
                metadatas=batch_metadatas,
                ids=batch_ids
            )
    
    print(f"索引完成！集合 '{collection_name}' 已保存")

if __name__ == "__main__":
    # 示例：索引企业仪表板项目
    project_path = "/Users/pon/Documents/buddy_claw_my/enterprise-dashboard"
    index_project(project_path)
```

### 2. 索引 PDF 文档脚本 (`index_pdf.py`)
创建 `/Users/pon/Documents/buddy_claw_my/.rag-knowledge/index_pdf.py`：

```python
import os
import chromadb
from chromadb.config import Settings
import requests
import time
import PyPDF2

class OllamaEmbedder:
    def __init__(self, model_name="qwen3-embedding:4b", base_url="http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        self.batch_size = 32
    
    def embed(self, texts):
        if not texts:
            return []
        
        vectors = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i+self.batch_size]
            try:
                response = requests.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model_name, "prompt": batch[0] if len(batch) == 1 else batch}
                )
                if response.status_code == 200:
                    result = response.json()
                    if len(batch) == 1:
                        vectors.append(result["embedding"])
                    else:
                        vectors.extend([item["embedding"] for item in result.get("embeddings", [])])
                else:
                    print(f"嵌入失败: {response.status_code}")
                    vectors.extend([[0.0] * 1024] * len(batch))
            except Exception as e:
                print(f"嵌入异常: {e}")
                vectors.extend([[0.0] * 1024] * len(batch))
            time.sleep(0.1)
        
        return vectors

def extract_text_from_pdf(pdf_path):
    """从 PDF 提取文本"""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                text += page.extract_text() + "\n"
    except Exception as e:
        print(f"提取 PDF 失败 {pdf_path}: {e}")
    return text

def index_pdf(pdf_path, collection_name="pdf_documents"):
    """索引 PDF 文档到 ChromaDB"""
    chroma_client = chromadb.PersistentClient(
        path="/Users/pon/Documents/buddy_claw_my/.rag-knowledge/chroma_db",
        settings=Settings(allow_reset=True)
    )
    
    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )
    
    embedder = OllamaEmbedder()
    
    # 提取文本
    print(f"提取 PDF: {pdf_path}")
    full_text = extract_text_from_pdf(pdf_path)
    
    # 分块（每500字符一个块）
    chunk_size = 500
    text_chunks = []
    metadatas = []
    ids = []
    
    for i in range(0, len(full_text), chunk_size):
        chunk = full_text[i:i+chunk_size]
        if chunk.strip():
            chunk_id = f"{os.path.basename(pdf_path)}:{i}"
            text_chunks.append(chunk)
            metadatas.append({
                "source": pdf_path,
                "type": "pdf",
                "chunk_index": i // chunk_size,
                "total_chunks": len(full_text) // chunk_size + 1
            })
            ids.append(chunk_id)
    
    print(f"PDF 提取完成，生成 {len(text_chunks)} 个文本块")
    
    # 批量嵌入和添加
    batch_size = 32
    for i in range(0, len(text_chunks), batch_size):
        batch_end = min(i + batch_size, len(text_chunks))
        print(f"处理块 {i+1} 到 {batch_end} / {len(text_chunks)}")
        
        batch_texts = text_chunks[i:batch_end]
        batch_metadatas = metadatas[i:batch_end]
        batch_ids = ids[i:batch_end]
        
        embeddings = embedder.embed(batch_texts)
        
        if embeddings:
            collection.add(
                embeddings=embeddings,
                documents=batch_texts,
                metadatas=batch_metadatas,
                ids=batch_ids
            )
    
    print(f"PDF 索引完成！集合 '{collection_name}' 已保存")

if __name__ == "__main__":
    # 示例：索引 PDF 文件
    pdf_path = "/Users/pon/Documents/buddy_claw_my/生命3.0.pdf"  # 替换为你的 PDF 路径
    index_pdf(pdf_path)
```

## 五、配置 OpenCode MCP 服务

### 1. 编辑 OpenCode 配置文件
编辑 `~/.config/opencode/opencode.json`，添加 MCP 服务配置：

```json
{
  "mcpServers": {
    "my-kb": {
      "command": "chroma-mcp-server",
      "args": ["serve", "--chroma-db-path", "/Users/pon/Documents/buddy_claw_my/.rag-knowledge/chroma_db"],
      "env": {
        "CHROMA_DB_PATH": "/Users/pon/Documents/buddy_claw_my/.rag-knowledge/chroma_db"
      }
    }
  }
}
```

### 2. 安装 chroma-mcp-server
如果未安装 chroma-mcp-server，需要先安装：
```bash
pip install chroma-mcp-server
```

## 六、运行索引

### 1. 索引项目代码
```bash
cd /Users/pon/Documents/buddy_claw_my/.rag-knowledge
python index_project.py
```
这将遍历项目文件，分块并嵌入到 ChromaDB。

### 2. 索引 PDF 文档
```bash
python index_pdf.py
```
确保 PDF 文件路径正确。

### 3. 后台运行避免超时
如果嵌入过程较慢，可以使用 `nohup` 后台运行：
```bash
nohup python index_project.py > project_index.log 2>&1 &
nohup python index_pdf.py > pdf_index.log 2>&1 &
```
检查日志：
```bash
tail -f project_index.log
```

## 七、使用 OpenCode TUI 检索知识库

### 1. 启动 OpenCode TUI
```bash
opencode
```

### 2. 在 TUI 中提问
进入 OpenCode TUI 后，直接提问即可。系统会自动检索知识库并返回相关上下文。

示例问题：
- "企业仪表板项目的登录功能是如何实现的？"
- "生命3.0这本书讲了什么内容？"

### 3. 验证知识库连接
在 OpenCode TUI 中，可以检查 MCP 服务状态：
```
/mcp status
```

## 八、故障排除

### 1. Ollama 服务未启动
确保 Ollama 服务正在运行：
```bash
ollama serve
# 或在后台运行
ps aux | grep ollama
```

### 2. Embedding 模型响应慢
- 检查模型是否已下载：`ollama list`
- 尝试使用更小的批量大小（如16）
- 考虑使用更轻量的模型

### 3. ChromaDB 连接失败
- 检查 chroma_db 目录是否存在且可写
- 确保 chromadb 版本兼容

### 4. OpenCode MCP 服务不工作
- 检查 `opencode.json` 配置语法
- 确保 chroma-mcp 已安装
- 重启 OpenCode TUI

### 5. 索引进程中断
- 使用 `nohup` 或 `tmux` 后台运行
- 检查日志文件中的错误信息

## 九、维护和更新

### 1. 添加新的数据源
- 修改索引脚本以支持新文件类型
- 运行对应索引脚本
- 无需重启 OpenCode，ChromaDB 会自动更新

### 2. 清除知识库
```python
import chromadb
from chromadb.config import Settings

client = chromadb.PersistentClient(
    path="/Users/pon/Documents/buddy_claw_my/.rag-knowledge/chroma_db"
)
client.reset()  # 谨慎：这将删除所有数据
```

### 3. 查看已索引内容
```python
import chromadb
from chromadb.config import Settings

client = chromadb.PersistentClient(
    path="/Users/pon/Documents/buddy_claw_my/.rag-knowledge/chroma_db"
)
collection = client.get_collection("project_code")
print(f"集合中有 {collection.count()} 个文档")
```

## 十、性能优化建议

1. **批量处理**：使用合适的批量大小（32-64）以提高嵌入效率
2. **缓存机制**：对已索引文件进行哈希校验，避免重复索引
3. **增量更新**：仅索引新增或修改的文件
4. **模型选择**：根据硬件性能选择合适的 embedding 模型大小
5. **并行处理**：对多个数据源使用多进程索引

## 总结
通过以上步骤，你已经搭建了一个完整的本地 RAG 知识库系统。这个系统可以：
- 索引项目代码和文档
- 通过向量检索快速查找相关信息
- 与 OpenCode TUI 无缝集成
- 完全离线运行，保护隐私

下次需要索引新项目或文档时，只需运行相应的索引脚本即可。知识库会自动更新，OpenCode 提问时会检索最新内容。

---

**注意**：首次运行索引可能需要较长时间（取决于数据量和模型速度）。建议在后台运行，并监控日志文件。如果遇到问题，请参考故障排除部分或检查日志中的错误信息。
