"""路径解析：区分「只读资源」与「可写数据」，兼容 PyInstaller 打包后的 exe。

- bundle_root()：只读资源（前端 dist、config.example.yaml 等），打包后被解包到 sys._MEIPASS；
- app_root()   ：可写数据（config.local.yaml、.env、storage/ 存档），打包后是 exe 所在目录。

开发（源码）运行时两者都等于项目根。
"""
from __future__ import annotations

import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def app_root() -> Path:
    if FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]
