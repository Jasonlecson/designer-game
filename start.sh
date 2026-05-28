#!/bin/bash
# 设计师模拟器 - 一键启动脚本

PORT=8765
DIR="$(cd "$(dirname "$0")" && pwd)"

# 杀掉已有进程
echo ">>> 检查端口 $PORT ..."
PID=$(lsof -ti :$PORT 2>/dev/null)
if [ -n "$PID" ]; then
    kill $PID 2>/dev/null
    sleep 1
    # 如果还没死就强制杀
    kill -9 $PID 2>/dev/null
    echo "    已终止旧进程 (PID $PID)"
else
    echo "    端口空闲"
fi

sleep 1

# 启动服务
echo ">>> 启动服务 ..."
cd "$DIR"
nohup venv/bin/python server.py > server.log 2>&1 &

sleep 3

# 验证
if curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/ | grep -q 200; then
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    echo ""
    echo "=========================================="
    echo "  设计师模拟器已启动"
    [ -n "$IP" ] && echo "  局域网访问: http://$IP:$PORT"
    echo "  本地访问:   http://localhost:$PORT"
    echo "  日志文件:   $DIR/server.log"
    echo "=========================================="
else
    echo "启动失败，请查看 $DIR/server.log"
    exit 1
fi
