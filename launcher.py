"""ElectricTools 启动器（打包 exe 的入口，也可直接用 python 运行）。

做的事：
1. 在后台线程里跑 uvicorn（127.0.0.1）；
2. 端口被占用时自动往后换（8765 → 8766 …）；
3. 等服务就绪后，用 **系统默认浏览器** 打开页面（可在页面里正常复制/粘贴文本）；
4. 控制台保留日志，按 Ctrl+C 或关闭窗口即退出。

用法：
    env\\python.exe launcher.py            # 源码方式
    ElectricTools.exe                      # 打包后双击即可
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("MPLBACKEND", "Agg")      # lcapy 可能拉 matplotlib，强制无界面后端

HOST = "127.0.0.1"
try:
    DEFAULT_PORT = int(os.environ.get("ET_PORT") or 8765)
except ValueError:
    DEFAULT_PORT = 8765

BANNER = r"""
  ______ _          _         _______          _
 |  ____| |        | |       |__   __|        | |
 | |__  | |  ___ __| |_   _  ___| | ___   ___ | |___
 |  __| | | / _ \ _| | | | |/ __| |/ _ \ / _ \| / __|
 | |____| ||  __/ |_| | |_| | (__| | (_) | (_) | \__ \
 |______|_| \___|\__|_|\__,_|\___|_|\___/ \___/|_|___/

 本地电路原理图求解器 · 正在启动…
"""


def _pick_port(start: int, tries: int = 20) -> int:
    """从 start 起找一个空闲端口。"""
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((HOST, p))
            except OSError:
                continue
            return p
    return start


def _wait_ready(port: int, timeout: float = 60.0) -> bool:
    import urllib.request

    url = f"http://{HOST}:{port}/health"
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if getattr(r, "status", 200) == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def main() -> int:
    print(BANNER)
    port = _pick_port(DEFAULT_PORT)
    if port != DEFAULT_PORT:
        print(f"[提示] 端口 {DEFAULT_PORT} 被占用，改用 {port}")

    try:
        import uvicorn
        from solver.app.main import app
    except Exception as exc:  # pragma: no cover
        print("[错误] 导入服务失败：", exc)
        input("按回车退出…")
        return 1

    cfg = uvicorn.Config(app, host=HOST, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(cfg)
    th = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    th.start()

    url = f"http://{HOST}:{port}/"
    if _wait_ready(port):
        print(f"[就绪] 打开浏览器：{url}")
        if not os.environ.get("ET_NO_BROWSER"):
            try:
                webbrowser.open(url)
            except Exception:
                pass
    else:
        print("[警告] 等待服务就绪超时，请手动打开：" + url)

    print("\n" + "=" * 56)
    print(f"  ElectricTools 正在运行： {url}")
    print("  关闭本窗口（或按 Ctrl+C）即可退出。")
    print("=" * 56 + "\n")

    try:
        while th.is_alive():
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\n正在退出…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
