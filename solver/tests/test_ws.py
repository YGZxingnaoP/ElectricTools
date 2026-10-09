"""WebSocket 全链路测试：启动 uvicorn（线程）→ websockets 客户端请求 → 校验结果。
    env\\python.exe solver\\tests\\test_ws.py
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

PORT = 8899


def start_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return server
        time.sleep(0.1)
    raise RuntimeError("server 未能在 10s 内启动")


def payload():
    return {
        "session_id": "ws-test",
        "mode": "both",
        "analysis": "dc",
        "schematic": {
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
        },
    }


async def client_once():
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
        await ws.send(json.dumps({"type": "ping", "id": "0", "payload": {}}))
        pong = json.loads(await ws.recv())
        assert pong["type"] == "pong", pong

        await ws.send(json.dumps({"type": "solve_request", "id": "1", "payload": payload()}))
        res = json.loads(await ws.recv())
        return res


def main():
    start_server()
    res = asyncio.run(client_once())
    assert res["type"] == "solve_result", res
    p = res["payload"]
    assert p["ok"], p.get("diagnostics")
    volts = sorted(round(p["nodes"][n]["voltage"], 4) for n in p["node_order"] if n != "0")
    assert volts == [2.5, 5.0], volts
    mid = [n for n in p["node_order"] if abs(p["nodes"][n]["voltage"] - 2.5) < 1e-9][0]
    print("WS OK  node volts:", {n: p["nodes"][n]["voltage"] for n in p["node_order"]})
    print("WS OK  latex:", p["nodes"][mid]["voltage_latex"])
    print("WS OK  validation:", p["validation"]["ok"])
    print("WS OK  netlist:", " | ".join((p["netlist"] or "").splitlines()))


if __name__ == "__main__":
    main()
