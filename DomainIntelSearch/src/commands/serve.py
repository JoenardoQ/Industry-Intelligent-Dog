"""Explicit local/LAN read-only archive sharing."""

from __future__ import annotations

import http.server
import socket
import socketserver
from pathlib import Path


def serve_archive(root: str | Path, host: str, port: int) -> None:
    root = Path(root)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    ip = "127.0.0.1"
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80)); ip = sock.getsockname()[0]; sock.close()
    except OSError:
        pass
    print("=" * 56)
    print("  DomainIntelData 只读服务已启动（Ctrl+C 停止）")
    print(f"  本机访问: http://127.0.0.1:{port}/")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print(f"  局域网访问: http://{ip}:{port}/")
        print("  警告: 已显式对外暴露本地研究数据，该服务不提供认证。")
    print("=" * 56)
    with socketserver.ThreadingTCPServer((host, port), Handler) as httpd:
        httpd.allow_reuse_address = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[停止] 服务已关闭")
