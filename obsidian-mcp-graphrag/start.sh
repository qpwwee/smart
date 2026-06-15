#!/bin/bash
# Obsidian Graph RAG MCP Server 启动脚本
# 用法: ./start.sh [--skip-vector]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT="/Users/pon/Documents/obsidian- knowledge"
PORT=3004
OLLAMA_URL="http://localhost:11434"
EMBEDDING_MODEL="qwen3-embedding:4b"

echo "🔍 Obsidian Graph RAG MCP Server"
echo "   Vault: $VAULT"
echo "   Port:  $PORT"
echo ""

cd "$SCRIPT_DIR"
python3 server.py \
  --vault "$VAULT" \
  --port $PORT \
  --ollama-url "$OLLAMA_URL" \
  --embedding-model "$EMBEDDING_MODEL" \
  "$@"
