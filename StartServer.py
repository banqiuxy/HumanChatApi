# -*- coding: utf-8 -*-
"""
HumanChatApi V1.0 Final · 启动入口（StartServer.py）
====================================================
最终启动文件：整合并启动整个项目，同时启动 Web 管理后台界面。

【零依赖】纯 Python 标准库实现（http.server / threading / json），
Android Termux / 任何 Python 3.8+ 环境直接运行，无需 pip 安装任何包。

作用：
  1. 从 app 包导入已拆分好的各业务模块
  2. 启动 HTTP 服务（默认 0.0.0.0:1234）
  3. 同时提供 Web 管理后台界面（/admin）

启动命令：
    python3 StartServer.py

OpenAI 客户端 base_url：http://127.0.0.1:1234/v1
后台管理界面：          http://127.0.0.1:1234/admin
"""
import sys
from pathlib import Path

# 确保可以 import app 包（无论从哪个目录启动）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import run_server  # noqa: E402

if __name__ == "__main__":
    run_server()