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


def forget(name: str) -> None:
    """只丢内存缓存，**绝不碰存档文件**。

    切档 / 重开同名档时用这个：下次 get() 会从存档目录重新读回来。
    （曾经这里误用了 clear()，导致一切档就把存档里的对话写空 —— 血的教训。）
    """
    _cache.pop(name, None)


def clear(name: str) -> None:
    """★ 破坏性：会把存档里的对话**写空**。

    只允许"用户明确要求清空对话"时调用，任何自动流程（切档、reset_session、
    memory_enabled=false…）都必须改用 forget()。
    """
    _cache.pop(name, None)
    archive.save_module(name, "conversation", {"messages": []})
    _cache[name] = []


def drop_from_round(name: str, round_index: int) -> int:
    """删除第 round_index 轮（从第 N 条 user 消息开始）及其之后的全部记录。

    按 user 边界切，保证不会把 assistant(tool_calls) 与 tool 响应的配对切坏。
    返回删掉的消息条数。
    """
    msgs = list(get(name))
    user_idx = [i for i, m in enumerate(msgs) if m.get("role") == "user"]
    if round_index < 0 or round_index >= len(user_idx):
        return 0
    cut = user_idx[round_index]
    removed = len(msgs) - cut
    set_messages(name, msgs[:cut])
    return removed


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
