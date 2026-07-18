#!/bin/bash
# Minecraft Wiki 翻译推送服务 - 启动脚本
# 用法: ./start.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查依赖
if ! python3 -c "import deep_translator" 2>/dev/null; then
    echo "正在安装依赖..."
    pip3 install -r requirements.txt --break-system-packages
fi

echo "========================================"
echo "  Minecraft Wiki 翻译推送服务"
echo "  RSS: Fandom Minecraft Wiki"
echo "  翻译: Google Translate → MyMemory 备用"
echo "  API:  http://0.0.0.0:8765"
echo "  频率:  每 60 分钟自动抓取"
echo "========================================"
echo ""

# 启动服务
python3 server.py