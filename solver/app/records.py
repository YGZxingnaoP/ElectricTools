"""兼容层：早期版本叫 records，现已统一为 archive（存档）。

保留此模块以兼容旧引用；新代码请直接用 solver.app.archive。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .archive import archives_dir as records_dir
from .archive import delete, list_archives, load, path_of, safe_name, save


def safe_id(sid: Optional[str]) -> str:
    return safe_name(sid)


def list_records() -> List[Dict[str, Any]]:
    return list_archives()
