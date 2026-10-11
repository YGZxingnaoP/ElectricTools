"""AI 客户端：**流式** + 工具调用（无总超时，靠"停止"中断）。

设计（参考 D:\\YOder）：
- 请求用 stream=True，边收边把增量文本回调给上层（on_event("thinking"/"content", text)）；
- **不设总超时**：模型想多久就多久，用户点"停止"时由 should_stop() 在数据块之间中断；
- 工具调用沿用 OpenAI 兼容协议（delta.tool_calls 按 index 增量拼接）。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional


class DeepSeekError(Exception):
    pass


class Stopped(Exception):
    """用户点了停止。"""


def _build_body(cfg: Dict[str, Any], messages: List[dict], tools: Optional[List[dict]],
                stream: bool) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "model": cfg.get("model", "deepseek-flash"),
        "messages": messages,
        "stream": stream,
    }
    if str(cfg.get("thinking", "enabled")).lower() == "enabled":
        body["thinking"] = {"type": "enabled"}
        body["reasoning_effort"] = cfg.get("reasoning_effort", "high")
    if tools:
        body["tools"] = tools
    return body


def _url(cfg: Dict[str, Any]) -> str:
    return str(cfg.get("base_url") or "https://api.deepseek.com").rstrip("/") + "/chat/completions"


def _open(cfg: Dict[str, Any], body: Dict[str, Any]):
    """发请求。**timeout=None = 永不超时**（流式就该慢慢读）。"""
    api_key = cfg.get("api_key") or ""
    if not api_key:
        raise DeepSeekError("未配置 API Key（在设置里填，或 .env 写 DEEPSEEK_API_KEY）。")
    req = urllib.request.Request(
        _url(cfg), data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        return urllib.request.urlopen(req, timeout=None)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        # 第三方平台不认 thinking / reasoning_effort → 去掉重来（非流式降级见下）
        if e.code in (400, 404, 422) and ("thinking" in body or "reasoning_effort" in body):
            raise DeepSeekError(f"__RETRY_NO_THINK__{e.code}: {detail[:300]}") from e
        raise DeepSeekError(f"HTTP {e.code}: {detail[:400]}") from e
    except urllib.error.URLError as e:
        raise DeepSeekError(f"网络错误：{e}（base_url 通不通？{_url(cfg)}）") from e


def _consume(resp, on_event: Callable[[str, str], None],
             should_stop: Optional[Callable[[], bool]]) -> Dict[str, Any]:
    """读 SSE 流，边读边回调。返回累加出的 assistant 消息。"""
    content: List[str] = []
    reasoning: List[str] = []
    calls: Dict[int, Dict[str, Any]] = {}
    stopped = False

    for raw in resp:                      # HTTPResponse 可直接按行迭代
        if should_stop and should_stop():
            stopped = True
            break
        line = raw.decode("utf-8", "ignore").strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except Exception:
            continue
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        t = delta.get("reasoning_content")
        if t:
            reasoning.append(t)
            on_event("thinking", t)
        c = delta.get("content")
        if c:
            content.append(c)
            on_event("content", c)
        for tc in delta.get("tool_calls") or []:
            i = int(tc.get("index") or 0)
            slot = calls.setdefault(i, {"id": "", "type": "function",
                                        "function": {"name": "", "arguments": ""}})
            if tc.get("id"):
                slot["id"] = tc["id"]
            fn = tc.get("function") or {}
            if fn.get("name"):
                slot["function"]["name"] += fn["name"]
            if fn.get("arguments"):
                slot["function"]["arguments"] += fn["arguments"]

    if stopped and should_stop and should_stop():
        raise Stopped()
    return {
        "role": "assistant",
        "content": "".join(content),
        "reasoning_content": "".join(reasoning),
        "tool_calls": [calls[k] for k in sorted(calls)] or None,
        "stopped": stopped,
    }


def _chat_stream(cfg: Dict[str, Any], messages: List[dict], tools: Optional[List[dict]],
                 on_event: Callable[[str, str], None],
                 should_stop: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
    body = _build_body(cfg, messages, tools, stream=True)
    try:
        resp = _open(cfg, body)
    except DeepSeekError as e:
        if str(e).startswith("__RETRY_NO_THINK__"):
            body = {k: v for k, v in body.items() if k not in ("thinking", "reasoning_effort")}
            resp = _open(cfg, body)
        else:
            raise
    with resp:
        return _consume(resp, on_event, should_stop)


def _assistant_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """回传给模型的 assistant 消息（保留 reasoning_content：带 tools 时官方要求）。"""
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
    on_event: Optional[Callable[[str, Any], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """流式多轮工具调用。

    on_event: ("thinking"|"content", 文本增量) / ("tool", {name,args,result}) / ("round", i)
    """
    ev = on_event or (lambda *a: None)
    trace: List[Dict[str, Any]] = []
    for _ in range(max(1, int(max_rounds))):
        try:
            msg = _chat_stream(cfg, messages, tools, ev, should_stop)
        except Stopped:
            # 已流出的文本前端自己留着，这里不回正文
            return {"content": "", "reasoning": "", "trace": trace,
                    "messages": messages, "stopped": True}
        messages.append(_assistant_message(msg))

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return {"content": msg.get("content") or "",
                    "reasoning": msg.get("reasoning_content") or "",
                    "trace": trace, "messages": messages, "stopped": bool(msg.get("stopped"))}

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = executor(name, args)
            except Exception as exc:
                result = {"error": str(exc)}
            trace.append({"tool": name, "args": args, "result": result})
            ev("tool", {"name": name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "content": json.dumps(result, ensure_ascii=False)})
        if should_stop and should_stop():
            return {"content": "", "reasoning": "", "trace": trace,
                    "messages": messages, "stopped": True}

    return {"content": "（已达到最大工具调用轮数）", "reasoning": "", "trace": trace,
            "messages": messages, "stopped": False}
