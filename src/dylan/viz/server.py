"""Local read-only page. Binds 127.0.0.1 and never creates a missing brain."""

from __future__ import annotations

import json
from datetime import timezone, tzinfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from dylan.viz.read import graph_payload

_PAGE = Path(__file__).with_name("page.html").read_text(encoding="utf-8")


class MemoryHandler(BaseHTTPRequestHandler):
    db_path: Path
    tz: tzinfo

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path in {"/", "/index.html"}:
                self._send(200, "text/html; charset=utf-8", _PAGE.encode("utf-8"))
                return
            if path == "/api/graph":
                body = json.dumps(graph_payload(self.db_path, self.tz), ensure_ascii=False)
                self._send(200, "application/json; charset=utf-8", body.encode("utf-8"))
                return
            self._send(404, "text/plain; charset=utf-8", "未找到\n".encode("utf-8"))
        except Exception as exc:
            message = str(exc) or "无法读取"
            self._send(500, "text/plain; charset=utf-8", (message + "\n").encode("utf-8"))

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def make_server(
    db_path: Path, host: str = "127.0.0.1", port: int = 8765, tz: tzinfo = timezone.utc
) -> ThreadingHTTPServer:
    handler = type("BoundMemoryHandler", (MemoryHandler,), {"db_path": db_path, "tz": tz})
    return ThreadingHTTPServer((host, port), handler)


def serve(
    db_path: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    stdout: object,
    tz: tzinfo = timezone.utc,
) -> int:
    graph_payload(db_path, tz)
    try:
        httpd = make_server(db_path, host, port, tz)
    except OSError:
        stdout.write(f"端口无法绑定：{port}\n")  # type: ignore[attr-defined]
        return 1
    bound = httpd.server_address[1]
    stdout.write(f"http://{host}:{bound}/\n")  # type: ignore[attr-defined]
    stdout.flush()  # type: ignore[attr-defined]
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return 0
