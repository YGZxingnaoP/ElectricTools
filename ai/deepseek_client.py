"""DeepSeek 客户端：thinking 思维链 + 工具调用。

用标准库 urllib 直接发 HTTP，**精确控制 reasoning_content 的逐轮回传**
（官方规则：带 tools 时必须回传所有历史轮次的 reasoning_content，否则 400）。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional


class DeepSeekError(Exception):
    pass


def _chat(cfg: Dict[str, Any], messages: List[dict], tools: Optional[List[dict]], timeout: int = 120) -> Dict[str, Any]:
    api_key = cfg.get("api_key") or ""
    if not api_key:
        raise DeepSeekError("未配置 API Key（请在 .env 设置 DEEPSEEK_API_KEY）。")

    body: Dict[str, Any] = {
        "model": cfg.get("model", "deepseek-flash"),
        "messages": messages,
        "stream": False,
    }
    if str(cfg.get("thinking", "enabled")).lower() == "enabled":
        body["thinking"] = {"type": "enabled"}
        body["reasoning_effort"] = cfg.get("reasoning_effort", "high")
    if tools:
        body["tools"] = tools

    url = cfg.get("base_url", "https://api.deepseek.com").rstrip("/") + "/chat/completions"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        raise DeepSeekError(f"HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise DeepSeekError(f"网络错误：{e}") from e


def _assistant_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """构造回传的 assistant 消息：保留 reasoning_content（带 tools 时必需）。"""
    out: Dict[str, Any] = {"role": "assistant", "content": msg.get("content")}
    if msg.get("reasoning_content") is not None:
        out["reasoning_content"] = msg["reasoning_content"]
    if msg.get("tool_calls"):
        out["tool_calls"] = msg["tool_calls"]
    return out


def run_conversation(
    cfg: Dict[str, Any],
    messages: List[dict],
    tools: List[dict],
    executor: Callable[[str, dict], Any],
    max_rounds: int = 8,
) -> Dict[str, Any]:
    """执行一轮用户提问（含多轮工具调用）。

    返回 {content, reasoning, trace, messages}
    """
    trace: List[Dict[str, Any]] = []
    for _ in range(max(1, int(max_rounds))):
        resp = _chat(cfg, messages, tools)
        choices = resp.get("choices") or []
        if not choices:
            raise DeepSeekError(f"响应异常：{resp}")
        msg = choices[0].get("message", {})
        messages.append(_assistant_message(msg))

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return {
                "content": msg.get("content") or "",
                "reasoning": msg.get("reasoning_content") or "",
                "trace": trace,
                "messages": messages,
            }

        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = executor(name, args)
            except Exception as exc:  # 工具异常也回传，让模型知晓
                result = {"error": str(exc)}
            trace.append({"tool": name, "args": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    return {
        "content": "（已达到最大工具调用轮数）",
        "reasoning": "",
        "trace": trace,
        "messages": messages,
    }
