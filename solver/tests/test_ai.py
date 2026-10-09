"""AI 链路连通性测试（无 API Key 时应优雅返回错误）。
    env\\python.exe solver\\tests\\test_ai.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import uvicorn
import websockets

from solver.app.main import app

PORT = 8898


def start_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return server
        time.sleep(0.1)
    raise RuntimeError("server 未启动")


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


async def client():
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
        await ws.send(json.dumps({
            "type": "ai_chat", "id": "1",
            "payload": {"session_id": "ai", "message": "这个节点电压多少？", "schematic": sch(), "mentions": []}
        }))
        return json.loads(await ws.recv())


def main():
    start_server()
    res = asyncio.run(client())
    assert res["type"] == "ai_reply", res
    p = res["payload"]
    print("ai_reply payload keys:", list(p.keys()))
    if "error" in p and p["error"]:
        assert "API Key" in p["error"] or "Key" in p["error"], p["error"]
        print("优雅报错（无密钥）:", p["error"])
    else:
        print("AI 回复:", (p.get("content") or "")[:120])
        print("工具轨迹条数:", len(p.get("trace") or []))
    print("AI WIRING OK")


if __name__ == "__main__":
    main()
