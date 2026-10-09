"""聊天记录：**存档的一个模块**（conversation.json）。

- AI 只读写 conversation.json，**完全不碰** canvas.json / results.json。
- 内存仅作缓存；未命中时从存档目录恢复。
- 因请求带 tools，必须保留每轮 assistant 的 reasoning_content（DeepSeek 官方规则）。
"""
from __future__ import annotations

from typing import Any, Dict, List

from solver.app import archive

_cache: Dict[str, List[dict]] = {}


def get(name: str) -> List[dict]:
    if name in _cache:
        return _cache[name]
    conv = archive.load_module(name, "conversation") or {}
    msgs = conv.get("messages") or []
    _cache[name] = msgs
    return msgs


def set_messages(name: str, messages: List[dict]) -> None:
    _cache[name] = messages
    archive.save_module(name, "conversation", {"messages": messages})

    meta = archive.load_module(name, "meta") or {}
    if not meta.get("title"):
        title = _derive_title(messages)
        if title:
            archive.save(name, {"meta": {"title": title}})   # 只更新 meta，不触碰其他模块


def clear(name: str) -> None:
    _cache.pop(name, None)
    archive.save_module(name, "conversation", {"messages": []})
    _cache[name] = []


def _derive_title(messages: List[dict]) -> str:
    for m in messages or []:
        if m.get("role") == "user":
            text = str(m.get("content") or "")
            marker = "[用户提问]"
            if marker in text:
                text = text.split(marker, 1)[-1]
            text = " ".join(text.split())
            if text:
                return text[:40]
    return ""


def path_info(name: str) -> Dict[str, Any]:
    return {"name": archive.safe_name(name), "dir": str(archive.archive_dir(name))}
