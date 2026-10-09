"""启动后端（分离进程），供浏览器手动/自动访问。
    env\\python.exe tools\\devserver.py [port]
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = sys.argv[1] if len(sys.argv) > 1 else "8765"
PY = os.path.join(ROOT, "env", "python.exe")

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

log = open(os.path.join(ROOT, ".server.log"), "w", encoding="utf-8")
proc = subprocess.Popen(
    [PY, "-m", "uvicorn", "solver.app.main:app", "--host", "127.0.0.1", "--port", PORT],
    cwd=ROOT,
    stdout=log,
    stderr=subprocess.STDOUT,
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
)
print("started pid", proc.pid, "port", PORT)
