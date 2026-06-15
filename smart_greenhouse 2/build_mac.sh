#!/bin/bash
# macOS 打包脚本
# 用法: bash build_mac.sh
cd "$(dirname "$0")"

echo "=== 智能温室监控系统 - macOS 打包 ==="

# 检查依赖
pip3 install -r requirements.txt

# 打包
python3 -m PyInstaller \
    --name=SmartGreenhouse \
    --windowed \
    --noconfirm \
    --clean \
    --onefile \
    --osx-bundle-identifier=com.smartgreenhouse.app \
    --hidden-import=serial \
    --hidden-import=serial.tools.list_ports \
    --hidden-import=matplotlib \
    --hidden-import=matplotlib.backends.backend_tkagg \
    --hidden-import=matplotlib.figure \
    --hidden-import=matplotlib.backends.backend_agg \
    --hidden-import=kiwisolver \
    --hidden-import=matplotlib.font_manager \
    main.py

echo ""
echo "=== 打包完成！==="
echo "应用程序: dist/SmartGreenhouse.app"
echo "可复制到 /Applications 或桌面使用"
