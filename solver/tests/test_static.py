"""静态托管检查：后端应能返回前端构建产物。
    env\\python.exe solver\\tests\\test_static.py
"""
from __future__ import annotations

import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import uvicorn

from solver.app.main import app

PORT = 8897


def main():
    cfg = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)

    html = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=10).read().decode("utf-8", "ignore")
    assert "ElectricTools" in html, html[:200]
    print("GET / -> index.html OK, length =", len(html))

    health = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=10).read().decode()
    print("GET /health ->", health)
    assert '"ok":true' in health.replace(" ", "")
    print("STATIC OK")


if __name__ == "__main__":
    main()
