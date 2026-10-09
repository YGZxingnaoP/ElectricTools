"""关键验证：AI 写聊天记录时，存档里的「图」与「结果」必须完好。
    env\\python.exe solver\\tests\\test_archive_ai.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import uvicorn
import websockets

from solver.app.main import app

PORT = 8893
NAME = "AI联调-存档"


def start_server():
    cfg = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return server
        time.sleep(0.1)
    raise RuntimeError("server 未启动")


def http(path, method="GET", body=None):
    url = f"http://127.0.0.1:{PORT}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())


def sch():
    return {
        "components": [
            {"id": "V1", "type": "vsource", "value": 5.0, "pins": [
                {"name": "p0", "x": 200, "y": 270}, {"name": "p1", "x": 200, "y": 330}]},
            {"id": "R1", "type": "resistor", "value": 1000.0, "pins": [
                {"name": "p0", "x": 320, "y": 270}, {"name": "p1", "x": 380, "y": 270}]},
            {"id": "R2", "type": "resistor", "value": 1000.0, "pins": [
                {"name": "p0", "x": 320, "y": 400}, {"name": "p1", "x": 380, "y": 400}]},
            {"id": "GND1", "type": "ground", "pins": [{"name": "p0", "x": 200, "y": 400}]},
        ],
        "wires": [
            {"id": "w1", "vertices": [{"x": 200, "y": 270}, {"x": 320, "y": 270}]},
            {"id": "w2", "vertices": [{"x": 380, "y": 270}, {"x": 430, "y": 270}, {"x": 430, "y": 400}, {"x": 380, "y": 400}]},
            {"id": "w3", "vertices": [{"x": 320, "y": 400}, {"x": 200, "y": 400}]},
            {"id": "w4", "vertices": [{"x": 200, "y": 400}, {"x": 200, "y": 330}]},
        ],
        "junctions": [],
    }


async def ask(message):
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
        await ws.send(json.dumps({
            "type": "ai_chat", "id": "1",
            "payload": {"session_id": NAME, "message": message, "schematic": sch(), "mentions": []}
        }))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") == "ai_reply":
                return msg["payload"]


def main():
    start_server()
    q = urllib.parse.quote

    # 1) 先存一个存档：图 + 结果
    canvas = {"components": [{"id": "R1", "type": "resistor", "x": 100, "y": 100, "rotation": 0,
                              "mirror": False, "value": 1000, "unit": "Ω"}],
              "wires": [{"id": "w1", "vertices": [{"x": 0, "y": 0}, {"x": 50, "y": 0}]}],
              "junctions": []}
    results = {"ok": True, "node_order": ["0", "n1"],
               "nodes": {"n1": {"id": "n1", "voltage": 2.5}}, "branches": []}
    http("/api/archive/save", "POST", {"name": NAME, "canvas": canvas, "results": results})

    before = http(f"/api/archive?name={q(NAME)}")
    print("AI 提问前 -> 元件", len(before["canvas"]["components"]),
          "| 结果", before["results"]["nodes"]["n1"]["voltage"],
          "| 消息", len(before["conversation"]["messages"]))

    # 2) 让 AI 回答（会写入聊天记录）
    out = asyncio.run(ask("这个节点电压是多少？"))
    if out.get("error"):
        print("AI 返回错误（可能无密钥）:", out["error"][:60])
    else:
        print("AI 回复长度:", len(out.get("content") or ""), "| 工具调用:", len(out.get("trace") or []))
        print("AI 回复片段:", (out.get("content") or "")[:80].replace("\n", " "))

    # 3) 再读存档：图与结果必须还在，聊天记录增加
    after = http(f"/api/archive?name={q(NAME)}")
    print("AI 提问后 -> 元件", len(after["canvas"]["components"]),
          "| 结果", (after["results"] or {}).get("nodes", {}).get("n1", {}).get("voltage"),
          "| 消息", len(after["conversation"]["messages"]))

    assert after["canvas"]["components"][0]["id"] == "R1", "图被 AI 覆盖了！"
    assert after["results"]["nodes"]["n1"]["voltage"] == 2.5, "结果被 AI 覆盖了！"
    if not out.get("error"):
        assert len(after["conversation"]["messages"]) >= 2, "聊天记录未写入"

    http("/api/archive/delete", "POST", {"name": NAME})
    print("ARCHIVE + AI OK")


if __name__ == "__main__":
    main()
