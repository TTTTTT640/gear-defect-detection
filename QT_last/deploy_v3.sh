#!/bin/bash
# V3开发板一键部署脚本
# 使用方法: bash deploy_v3.sh

set -e

echo "========================================"
echo "  齿轮检测系统 - V3部署"
echo "========================================"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 1. 检查模型文件
echo ""
echo "[1/4] 检查模型文件..."
MISSING=0
for f in best.pt final2.pt; do
    if [ ! -f "$f" ]; then
        echo "  缺少: $f"
        MISSING=1
    else
        SIZE=$(du -h "$f" | cut -f1)
        echo "  找到: $f ($SIZE)"
    fi
done
if [ $MISSING -eq 1 ]; then
    echo "错误: 缺少模型文件，请将 best.pt 和 final2.pt 拷贝到 $SCRIPT_DIR"
    exit 1
fi

# 2. 检查Python依赖
echo ""
echo "[2/4] 检查Python依赖..."
pip3 install --quiet PyQt5 opencv-python-headless pyserial numpy 2>/dev/null || {
    echo "pip安装失败，尝试apt安装..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-pyqt5 python3-opencv python3-serial python3-numpy
}

# ultralytics: 使用项目内置的ultralytics目录
if [ -d "ultralytics" ]; then
    echo "  使用项目内置ultralytics库"
else
    echo "  安装ultralytics..."
    pip3 install --quiet ultralytics
fi

# 3. 串口权限
echo ""
echo "[3/4] 检查串口权限..."
SERIAL_PORT="/dev/ttyHS1"
if [ -e "$SERIAL_PORT" ]; then
    if [ -w "$SERIAL_PORT" ]; then
        echo "  $SERIAL_PORT 可写"
    else
        echo "  设置 $SERIAL_PORT 权限..."
        sudo chmod 666 "$SERIAL_PORT"
        sudo usermod -aG dialout "$USER" 2>/dev/null || true
    fi
else
    echo "  警告: $SERIAL_PORT 不存在，串口功能可能不可用"
    echo "  可用串口:"
    ls /dev/ttyHS* /dev/ttyUSB* /dev/ttyAMA* 2>/dev/null || echo "    (无)"
fi

# 4. 启动
echo ""
echo "[4/4] 启动齿轮检测系统..."
echo "========================================"
export QT_QPA_PLATFORM=xcb
python3 gp_main.py
