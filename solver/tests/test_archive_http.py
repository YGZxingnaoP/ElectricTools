"""存档 HTTP 接口端到端测试（图 + 结果 + 聊天记录）。
    env\\python.exe solver\\tests\\test_archive_http.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import uvicorn

from solver.app.archive import path_of
from solver.app.main import app

PORT = 8894
NAME = "HTTP测试-存档"


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
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())


def main():
    start_server()
    q = urllib.parse.quote

    cfg = http("/api/config")
    print("存档目录:", cfg["paths"]["archives_dir"])
    assert cfg["paths"]["archives_dir"]

    canvas = {"components": [{"id": "V1", "type": "vsource", "x": 10, "y": 10, "value": 5, "unit": "V"}],
              "wires": [], "junctions": []}
    results = {"ok": True, "node_order": ["0", "n1"], "nodes": {"n1": {"id": "n1", "voltage": 5.0}}}

    r = http("/api/archive/save", "POST", {"name": NAME, "canvas": canvas, "results": results})
    print("save ->", r)
    assert r["ok"] and Path(r["dir"]).is_dir(), r
    mods = sorted(p.name for p in Path(r["dir"]).iterdir())
    print("模块文件:", mods)
    assert "canvas.json" in mods and "results.json" in mods and "meta.json" in mods
    assert "conversation.json" not in mods, "保存图/结果不应产生 conversation.json"

    doc = http(f"/api/archive?name={q(NAME)}")
    assert doc["canvas"]["components"][0]["id"] == "V1"
    assert doc["results"]["nodes"]["n1"]["voltage"] == 5.0
    assert "messages" in doc["conversation"]
    print("读回：元件", len(doc["canvas"]["components"]),
          "| 结果", doc["results"]["nodes"]["n1"]["voltage"],
          "| 消息", len(doc["conversation"]["messages"]))

    # 分模块接口
    md = http(f"/api/archive/module?name={q(NAME)}&module=canvas")
    assert md["data"]["components"][0]["id"] == "V1"
    print("模块接口 canvas ->", md["data"]["components"][0]["id"])

    lst = http("/api/archives")["archives"]
    assert any(x["name"] == NAME for x in lst), lst
    print("列表命中:", [x for x in lst if x["name"] == NAME][0]["name"])

    new_name = NAME + "-改名"
    rr = http("/api/archive/rename", "POST", {"name": NAME, "new_name": new_name})
    assert rr["ok"], rr
    assert Path(path_of(new_name)).is_dir()
    print("改名 ->", rr["name"])

    d2 = http("/api/archive/delete", "POST", {"name": new_name})
    assert d2["ok"]
    assert not Path(path_of(new_name)).exists()
    print("已删除")

    print("ARCHIVE HTTP OK")


if __name__ == "__main__":
    main()
