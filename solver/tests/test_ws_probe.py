"""WS 节点探针 + 设置接口 端到端测试。
    env\\python.exe solver\\tests\\test_ws_probe.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import uvicorn
import websockets

from solver.app.main import app

PORT = 8896


def start_server():
    cfg = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(cfg)
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


async def ws_flow():
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
        await ws.send(json.dumps({"type": "solve_request", "id": "1",
                                  "payload": {"session_id": "wp", "mode": "both", "schematic": sch()}}))
        solved = json.loads(await ws.recv())["payload"]
        mid = [n for n in solved["node_order"] if abs(solved["nodes"][n]["voltage"] - 2.5) < 1e-9][0]

        await ws.send(json.dumps({"type": "node_probe", "id": "2",
                                  "payload": {"session_id": "wp", "node": mid, "schematic": sch()}}))
        detail = json.loads(await ws.recv())["payload"]
        return mid, detail


def http(path, method="GET", body=None):
    url = f"http://127.0.0.1:{PORT}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())


def main():
    start_server()
    mid, detail = asyncio.run(ws_flow())
    print("探针节点:", detail["node"], "电压:", detail["voltage"])
    print("KCL:", detail["kcl_latex"][:60], "...")
    print("支路:", [(b["component"], b["leaving"]) for b in detail["branches"]])
    assert abs(detail["voltage"] - 2.5) < 1e-9
    assert detail["kcl_latex"].endswith("= 0")
    assert detail["method"]

    s = http("/api/settings")
    print("设置(默认): memory_enabled =", s["ai"]["memory_enabled"], "| api_key_set =", s["ai"]["api_key_set"])
    assert "memory_enabled" in s["ai"]

    s2 = http("/api/settings", "POST", {"ai": {"memory_enabled": False, "memory_max_turns": 2}})
    assert s2["ai"]["memory_enabled"] is False and s2["ai"]["memory_max_turns"] == 2
    print("设置(写入后):", s2["ai"]["memory_enabled"], s2["ai"]["memory_max_turns"])

    http("/api/settings", "POST", {"ai": {"memory_enabled": True, "memory_max_turns": 10}})
    http("/api/memory/clear", "POST", {"session_id": "wp"})
    print("WS PROBE + SETTINGS OK")


if __name__ == "__main__":
    main()
