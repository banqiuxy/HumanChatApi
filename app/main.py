# -*- coding: utf-8 -*-
"""
应用入口（main.py）
纯标准库 HTTP 服务：ThreadingHTTPServer + 路由分发。
每个请求独立线程，支持阻塞等待人工回复的高并发。

路由：
  GET  /v1/models            → api_routes.list_models
  POST /v1/chat/completions  → api_routes.chat_completions
  GET  /admin                → admin_routes.admin_index
  GET  /admin/chat           → admin_routes.admin_chat
  GET  /admin/ctx            → admin_routes.admin_ctx
  GET  /admin/msg            → admin_routes.admin_msg
  POST /admin/submit         → admin_routes.admin_submit
  POST /admin/close          → admin_routes.admin_close
  POST /admin/set_mode       → admin_routes.admin_set_mode
  GET  /admin/api/status     → admin_routes.admin_status
"""
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import api_routes, admin_routes

# 基础配置（V1.0 固定）
HOST = "0.0.0.0"
PORT = 1234

# webui 静态资源目录（logo 图片等）
_WEBUI_DIR = Path(__file__).resolve().parent / "webui"


class Handler(BaseHTTPRequestHandler):
    """HTTP 请求处理器。"""

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------
    def log_message(self, fmt, *args):  # 精简日志
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _read_body(self) -> bytes:
        """读取请求体。"""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        """发送响应。"""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if content_type == "text/event-stream":
            # SSE：禁止缓冲，确保客户端能收到
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
        self.end_headers()
        if body:
            self.wfile.write(body)
            self.wfile.flush()

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json")

    def _send_html(self, status: int, text: str) -> None:
        self._send(status, text.encode("utf-8"), "text/html; charset=utf-8")

    def _serve_static(self, path: str) -> None:
        """提供 webui 目录下的静态资源（如图片）。"""
        # 去掉 /webui/ 前缀，并防止路径穿越
        rel = path[len("/webui/"):]
        file_path = (_WEBUI_DIR / rel).resolve()
        if not str(file_path).startswith(str(_WEBUI_DIR.resolve())) or not file_path.is_file():
            self._send(404, b"Not Found", "text/plain")
            return
        try:
            data = file_path.read_bytes()
        except Exception:
            self._send(404, b"Not Found", "text/plain")
            return
        ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self._send(200, data, ctype)

    # ------------------------------------------------------------------
    # OPTIONS（CORS 预检）
    # ------------------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # webui 静态资源（logo 图片等）
        if path.startswith("/webui/"):
            self._serve_static(path)
            return

        if path == "/v1/models":
            status, body, ctype = api_routes.list_models()
            self._send(status, body, ctype)
        elif path == "/admin":
            status, body, ctype = admin_routes.admin_index()
            self._send(status, body, ctype)
        elif path == "/admin/chat":
            sid = (query.get("sid") or [""])[0]
            status, body, ctype = admin_routes.admin_chat(sid)
            self._send(status, body, ctype)
        elif path == "/admin/msg":
            sid = (query.get("sid") or [""])[0]
            idx = (query.get("idx") or [""])[0]
            status, body, ctype = admin_routes.admin_msg(sid, idx)
            self._send(status, body, ctype)
        elif path == "/admin/ctx":
            sid = (query.get("sid") or [""])[0]
            status, body, ctype = admin_routes.admin_ctx(sid)
            self._send(status, body, ctype)
        elif path == "/admin/api/status":
            status, body, ctype = admin_routes.admin_status()
            self._send(status, body, ctype)
        else:
            self._send(404, b"Not Found", "text/plain")

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body_bytes = self._read_body()

        if path == "/v1/chat/completions":
            # OpenAI 兼容对话接口（阻塞等待人工回复）
            status, body, ctype = api_routes.chat_completions(body_bytes)
            self._send(status, body, ctype)
        elif path == "/admin/submit":
            form = parse_qs(body_bytes.decode("utf-8"))
            status, body, ctype = admin_routes.admin_submit(form)
            self._send(status, body, ctype)
        elif path == "/admin/close":
            form = parse_qs(body_bytes.decode("utf-8"))
            status, body, ctype = admin_routes.admin_close(form)
            self._send(status, body, ctype)
        elif path == "/admin/set_mode":
            form = parse_qs(body_bytes.decode("utf-8"))
            status, body, ctype = admin_routes.admin_set_mode(form)
            self._send(status, body, ctype)
        else:
            self._send(404, b"Not Found", "text/plain")


def create_server(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    """创建 HTTP 服务器。"""
    return ThreadingHTTPServer((host, port), Handler)


def run_server(host: str = HOST, port: int = PORT) -> None:
    """启动 HTTP 服务（阻塞运行）。"""
    server = create_server(host, port)
    print(f"[HumanChatApi] 服务已启动: http://{host}:{port}/v1")
    print(f"[HumanChatApi] 管理后台:  http://127.0.0.1:{port}/admin")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[HumanChatApi] 服务已停止")
        server.server_close()