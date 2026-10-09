"""AI 编排：把「用户提问 + 当前电路 + @节点」组织成一次带工具的对话。

短期记忆：
- ai.memory_enabled=false → 每次提问都是无历史的一次性问答（不读写记忆）。
- ai.memory_max_turns=N    → 只保留最近 N 轮用户提问及其后续（按 user 边界裁剪，
  不会切断 assistant(tool_calls) 与 tool 响应的配对）。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from solver.app import tools as T
from solver.app.analysis import STORE, analyze
from solver.app.models import Schematic, SolveRequest

from . import conversation_store as conv
from .context_builder import SYSTEM_PROMPT, build_context_block
from .deepseek_client import run_conversation
from .tool_schemas import TOOLS


def _make_executor(session_id: str) -> Callable[[str, dict], Any]:
    def ex(name: str, args: Dict[str, Any]) -> Any:
        if name == "get_circuit_netlist":
            return T.get_circuit_netlist(session_id)
        if name == "solve_node_voltage":
            return T.solve_node_voltage(session_id, args.get("node", ""))
        if name == "solve_branch_current":
            return T.solve_branch_current(session_id, args.get("component", ""))
        if name == "get_kcl_equations":
            return T.get_kcl_equations(session_id, args.get("node", ""))
        if name == "apply_thevenin":
            return T.apply_thevenin(session_id, args.get("node_a", ""), args.get("node_b", ""))
        if name == "apply_norton":
            return T.apply_norton(session_id, args.get("node_a", ""), args.get("node_b", ""))
        return {"error": f"未知工具：{name}"}
    return ex


def _trim(messages: List[dict], max_turns: int) -> List[dict]:
    """按 user 边界裁剪历史，保留 system + 最近 max_turns 轮。"""
    if max_turns <= 0:
        return messages
    user_idx = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_idx) <= max_turns:
        return messages
    start = user_idx[-max_turns]
    head = [m for i, m in enumerate(messages) if i < start and m.get("role") == "system"]
    return head + messages[start:]


def answer(
    cfg: Dict[str, Any],
    session_id: str,
    message: str,
    schematic: Optional[Schematic] = None,
    mentions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if schematic is not None:
        STORE.set_schematic(session_id, schematic)

    sch = STORE.get_schematic(session_id)
    res = None
    if sch is not None:
        res = analyze(SolveRequest(session_id=session_id, schematic=sch, mode="both"), True)

    memory_enabled = bool(cfg.get("memory_enabled", True))
    max_turns = int(cfg.get("memory_max_turns", 10) or 10)

    if memory_enabled:
        messages = conv.get(session_id)
        if not messages:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages = _trim(messages, max_turns)
    else:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    context = build_context_block(res, mentions)
    messages.append({"role": "user", "content": f"{context}\n\n[用户提问]\n{message}"})

    out = run_conversation(
        cfg, messages, TOOLS, _make_executor(session_id),
        max_rounds=cfg.get("max_tool_rounds", 8),
    )

    if memory_enabled:
        conv.set_messages(session_id, out["messages"])
    else:
        conv.clear(session_id)

    return {
        "content": out["content"],
        "reasoning": out["reasoning"],
        "trace": out["trace"],
        "memory": {"enabled": memory_enabled, "max_turns": max_turns},
    }
